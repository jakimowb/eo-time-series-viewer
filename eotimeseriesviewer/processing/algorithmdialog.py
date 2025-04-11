"""
Modifies the following QGIS processing classes to become usable with
self-defined QgsProcessingContext and own QgisInterfaces:

AlgorithmDialog - original: processing/gui/AlgorithmDialog.py
BatchAlgorithmDialog - original: processing/gui/BatchAlgorithmDialog.py
BatchPanel - original: processing/gui/BatchPanel.py
ParametersPanel - original: processing/gui/ParametersPanel.py

createContext - original: processing/tools/dataobjects.py
createExpressionContext - original: processing/tools/dataobjects.py


"""
import codecs
import datetime
import json
import time
import traceback
from typing import Optional

from processing.tools import dataobjects
from qgis.PyQt.QtCore import QCoreApplication, QDir, QFileInfo
from qgis.PyQt.QtWidgets import QDialogButtonBox, QFileDialog, QHeaderView, QMessageBox, QPushButton, QTableWidgetItem
from qgis.core import Qgis, QgsApplication, QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextUtils, \
    QgsFeatureRequest, QgsFileUtils, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsLayerTreeNode, QgsLayerTreeRegistryBridge, \
    QgsMapLayer, QgsMessageLog, QgsProcessingAlgorithm, QgsProcessingAlgRunnerTask, QgsProcessingContext, \
    QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback, QgsProcessingModelAlgorithm, \
    QgsProcessingOutputBoolean, QgsProcessingOutputHtml, QgsProcessingOutputLayerDefinition, QgsProcessingOutputNumber, \
    QgsProcessingOutputString, QgsProcessingParameterDefinition, QgsProcessingParameterExtent, \
    QgsProcessingParameterFeatureSink, QgsProcessingParameterRasterDestination, QgsProcessingParameterVectorDestination, \
    QgsProcessingUtils, QgsProject, QgsProxyProgressTask, QgsSettings
from qgis.gui import QgisInterface, QgsGui, QgsPanelWidget, QgsProcessingAlgorithmDialogBase, \
    QgsProcessingBatchAlgorithmDialogBase, QgsProcessingContextGenerator, QgsProcessingGui, \
    QgsProcessingHiddenWidgetWrapper, QgsProcessingParametersGenerator, QgsProcessingParametersWidget, \
    QgsProcessingParameterWidgetContext
from processing.gui.BatchOutputSelectionPanel import BatchOutputSelectionPanel
from processing.gui.AlgorithmExecutor import execute, execute_in_place, executeIterating
from processing.gui.BatchPanel import BatchPanelFillWidget, WIDGET
from processing.gui.Postprocessing import create_layer_tree_layer, determine_output_name, get_layer_tree_results_group, \
    post_process_layer, SORT_ORDER_CUSTOM_PROPERTY
from processing.gui.wrappers import WidgetWrapper, WidgetWrapperFactory
from qgis.PyQt.QtGui import QColor, QPalette
import qgis.utils
from processing import getTempFilename, ProcessingConfig
from processing.core.ProcessingResults import resultsList
from processing.gui.AlgorithmDialogBase import AlgorithmDialogBase


def handleAlgorithmResults(
        alg: QgsProcessingAlgorithm,
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback] = None,
        iface: Optional[QgisInterface] = None,
        parameters: Optional[dict] = None,
):
    if not parameters:
        parameters = {}
    if feedback is None:
        feedback = QgsProcessingFeedback()
    wrong_layers = []

    feedback.setProgressText(
        QCoreApplication.translate("Postprocessing", "Loading resulting layers")
    )
    i = 0

    added_layers: list[
        tuple[QgsMapLayer, Optional[QgsLayerTreeGroup], QgsLayerTreeLayer, QgsProject]
    ] = []
    layers_to_post_process: list[
        tuple[QgsMapLayer, QgsProcessingContext.LayerDetails]
    ] = []

    for dest_id, details in context.layersToLoadOnCompletion().items():
        if feedback.isCanceled():
            return False

        if len(context.layersToLoadOnCompletion()) > 2:
            # only show progress feedback if we're loading a bunch of layers
            feedback.setProgress(
                100 * i / float(len(context.layersToLoadOnCompletion()))
            )

        try:
            layer = QgsProcessingUtils.mapLayerFromString(
                dest_id, context, typeHint=details.layerTypeHint
            )
            if layer is not None:
                details.setOutputLayerName(layer)

                output_name = determine_output_name(
                    dest_id, details, alg, context, parameters
                )
                post_process_layer(output_name, layer, alg)

                # Load layer to layer tree root or to a specific group
                results_group = get_layer_tree_results_group(details, context)

                # note here that we may not retrieve an owned layer -- eg if the
                # output layer already exists in the destination project
                owned_map_layer = context.temporaryLayerStore().takeMapLayer(layer)
                if owned_map_layer:
                    # we don't add the layer to the tree yet -- that's done
                    # later, after we've sorted all added layers
                    layer_tree_layer = create_layer_tree_layer(owned_map_layer, details)
                    added_layers.append(
                        (
                            owned_map_layer,
                            results_group,
                            layer_tree_layer,
                            details.project,
                        )
                    )

                if details.postProcessor():
                    # we defer calling the postProcessor set in the context
                    # until the layer has been added to the project's layer
                    # tree, just in case the postProcessor contains logic
                    # relating to layer tree handling
                    layers_to_post_process.append((layer, details))

            else:
                wrong_layers.append(str(dest_id))
        except Exception:
            QgsMessageLog.logMessage(
                QCoreApplication.translate(
                    "Postprocessing", "Error loading result layer:"
                )
                + "\n"
                + traceback.format_exc(),
                "Processing",
                Qgis.MessageLevel.Critical,
            )
            wrong_layers.append(str(dest_id))
        i += 1

    # sort added layer tree layers
    sorted_layer_tree_layers = sorted(
        added_layers, key=lambda x: x[2].customProperty(SORT_ORDER_CUSTOM_PROPERTY, 0)
    )
    have_set_active_layer = False

    current_selected_node: Optional[QgsLayerTreeNode] = None
    if iface is not None:
        current_selected_node = iface.layerTreeView().currentNode()
        iface.layerTreeView().setUpdatesEnabled(False)

    for layer, group, layer_node, project in sorted_layer_tree_layers:
        if not project:
            project = context.project()

        # store the current insertion point to restore it later
        previous_insertion_point = None
        if project:
            previous_insertion_point = (
                project.layerTreeRegistryBridge().layerInsertionPoint()
            )

        layer_node.removeCustomProperty(SORT_ORDER_CUSTOM_PROPERTY)
        insertion_point: Optional[QgsLayerTreeRegistryBridge.InsertionPoint] = None
        if group is not None:
            insertion_point = QgsLayerTreeRegistryBridge.InsertionPoint(group, 0)
        else:
            # no destination group for this layer, so should be placed
            # above the current layer
            if isinstance(current_selected_node, QgsLayerTreeLayer):
                current_node_group = current_selected_node.parent()
                current_node_index = current_node_group.children().index(
                    current_selected_node
                )
                insertion_point = QgsLayerTreeRegistryBridge.InsertionPoint(
                    current_node_group, current_node_index
                )
            elif isinstance(current_selected_node, QgsLayerTreeGroup):
                insertion_point = QgsLayerTreeRegistryBridge.InsertionPoint(
                    current_selected_node, 0
                )
            elif project:
                insertion_point = QgsLayerTreeRegistryBridge.InsertionPoint(
                    project.layerTreeRoot(), 0
                )

        if project and insertion_point:
            project.layerTreeRegistryBridge().setLayerInsertionPoint(insertion_point)

        project.addMapLayer(layer_node.layer())

        if not have_set_active_layer and iface is not None:
            iface.setActiveLayer(layer_node.layer())
            have_set_active_layer = True

        # reset to the previous insertion point
        if project:
            project.layerTreeRegistryBridge().setLayerInsertionPoint(
                previous_insertion_point
            )

    # all layers have been added to the layer tree, so safe to call
    # postProcessors now
    for layer, details in layers_to_post_process:
        details.postProcessor().postProcessLayer(layer, context, feedback)

    if iface is not None:
        iface.layerTreeView().setUpdatesEnabled(True)

    feedback.setProgress(100)

    if wrong_layers:
        msg = QCoreApplication.translate(
            "Postprocessing", "The following layers were not correctly generated."
        )
        msg += "\n" + "\n".join([f"• {lay}" for lay in wrong_layers]) + "\n"
        msg += QCoreApplication.translate(
            "Postprocessing",
            "You can check the 'Log Messages Panel' in QGIS main window "
            "to find more information about the execution of the algorithm.",
        )
        feedback.reportError(msg)

    return len(wrong_layers) == 0


# changing this signature? make sure you update the signature in
# python/processing/__init__.py too!
# Docstring for this function is in python/processing/__init__.py
def createContext(feedback: Optional[QgsProcessingFeedback] = None,
                  project: Optional[QgsProject] = None,
                  iface: Optional[QgisInterface] = None):
    if project is None:
        project = QgsProject.instance()

    if iface is None:
        iface = qgis.utils.iface

    context = QgsProcessingContext()
    context.setProject(project)
    context.setFeedback(feedback)

    invalid_features_method = ProcessingConfig.getSetting(
        ProcessingConfig.FILTER_INVALID_GEOMETRIES
    )
    if invalid_features_method is None:
        invalid_features_method = (
            QgsFeatureRequest.InvalidGeometryCheck.GeometryAbortOnInvalid
        )
    else:
        invalid_features_method = QgsFeatureRequest.InvalidGeometryCheck(
            int(invalid_features_method)
        )
    context.setInvalidGeometryCheck(invalid_features_method)

    settings = QgsSettings()
    context.setDefaultEncoding(
        QgsProcessingUtils.resolveDefaultEncoding(
            settings.value("/Processing/encoding")
        )
    )

    context.setExpressionContext(createExpressionContext(iface=iface, project=context.project()))

    if iface and iface.mapCanvas() and iface.mapCanvas().mapSettings().isTemporal():
        context.setCurrentTimeRange(iface.mapCanvas().mapSettings().temporalRange())

    return context


def createExpressionContext(iface: Optional[QgisInterface] = None,
                            project: Optional[QgsProject] = None):
    if not isinstance(project, QgsProject):
        project = QgsProject.instance()

    context = QgsExpressionContext()
    context.appendScope(QgsExpressionContextUtils.globalScope())
    context.appendScope(QgsExpressionContextUtils.projectScope(project))

    if iface and iface.mapCanvas():
        context.appendScope(
            QgsExpressionContextUtils.mapSettingsScope(iface.mapCanvas().mapSettings())
        )

    processingScope = QgsExpressionContextScope()

    if iface and iface.mapCanvas():
        extent = iface.mapCanvas().fullExtent()
        processingScope.setVariable("fullextent_minx", extent.xMinimum())
        processingScope.setVariable("fullextent_miny", extent.yMinimum())
        processingScope.setVariable("fullextent_maxx", extent.xMaximum())
        processingScope.setVariable("fullextent_maxy", extent.yMaximum())

    context.appendScope(processingScope)
    return context


class AlgorithmDialog(QgsProcessingAlgorithmDialogBase):

    def __init__(self, alg, in_place=False, parent=None,
                 context: Optional[QgsProcessingContext] = None,
                 iface: Optional[QgisInterface] = None,
                 ):
        super().__init__(parent)

        if not isinstance(iface, QgisInterface):
            iface = qgis.utils.iface

        self._iface = iface
        self._context = context

        self.feedback_dialog = None
        self.in_place = in_place
        self.active_layer = self._iface.activeLayer() if self.in_place else None

        self.context = None
        self.feedback = None
        self.history_log_id = None
        self.history_details = {}

        self.setAlgorithm(alg)
        self.setMainWidget(self.getParametersPanel(alg, self))

        if not self.in_place:
            self.runAsBatchButton = QPushButton(
                QCoreApplication.translate("AlgorithmDialog", "Run as Batch Process…")
            )
            self.runAsBatchButton.clicked.connect(self.runAsBatch)
            self.buttonBox().addButton(
                self.runAsBatchButton, QDialogButtonBox.ButtonRole.ResetRole
            )  # reset role to ensure left alignment
        else:
            in_place_input_parameter_name = "INPUT"
            if hasattr(alg, "inputParameterName"):
                in_place_input_parameter_name = alg.inputParameterName()

            self.mainWidget().setParameters(
                {in_place_input_parameter_name: self.active_layer}
            )

            self.runAsBatchButton = None
            has_selection = self.active_layer and (
                    self.active_layer.selectedFeatureCount() > 0
            )
            self.buttonBox().button(QDialogButtonBox.StandardButton.Ok).setText(
                QCoreApplication.translate(
                    "AlgorithmDialog", "Modify Selected Features"
                )
                if has_selection
                else QCoreApplication.translate(
                    "AlgorithmDialog", "Modify All Features"
                )
            )
            self.setWindowTitle(self.windowTitle() + " | " + self.active_layer.name())

        self.updateRunButtonVisibility()

    def getParametersPanel(self, alg, parent):
        panel = ParametersPanel(parent, alg, in_place=self.in_place, active_layer=self.active_layer,
                                context=self._context,
                                iface=self._iface)
        return panel

    def runAsBatch(self):
        self.close()
        dlg = BatchAlgorithmDialog(self.algorithm().create(), parent=self._iface.mainWindow(),
                                   context=self._context,
                                   iface=self._iface)
        dlg.show()
        dlg.exec()

    def resetAdditionalGui(self):
        if not self.in_place:
            self.runAsBatchButton.setEnabled(True)

    def blockAdditionalControlsWhileRunning(self):
        if not self.in_place:
            self.runAsBatchButton.setEnabled(False)

    def setParameters(self, parameters):
        self.mainWidget().setParameters(parameters)

    def flag_invalid_parameter_value(self, message: str, widget):
        """
        Highlights a parameter with an invalid value
        """
        try:
            self.buttonBox().accepted.connect(lambda w=widget: w.setPalette(QPalette()))
            palette = widget.palette()
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 0))
            widget.setPalette(palette)
        except Exception:
            pass
        self.messageBar().clearWidgets()
        self.messageBar().pushMessage(
            "",
            self.tr("Wrong or missing parameter value: {0}").format(message),
            level=Qgis.MessageLevel.Warning,
            duration=5,
        )

    def flag_invalid_output_extension(self, message: str, widget):
        """
        Highlights a parameter with an invalid output extension
        """
        try:
            self.buttonBox().accepted.connect(lambda w=widget: w.setPalette(QPalette()))
            palette = widget.palette()
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 0))
            widget.setPalette(palette)
        except Exception:
            pass
        self.messageBar().clearWidgets()
        self.messageBar().pushMessage(
            "", message, level=Qgis.MessageLevel.Warning, duration=5
        )

    def createProcessingParameters(
            self, flags=QgsProcessingParametersGenerator.Flags()
    ):
        if self.mainWidget() is None:
            return {}

        try:
            return self.mainWidget().createProcessingParameters(flags)
        except AlgorithmDialogBase.InvalidParameterValue as e:
            self.flag_invalid_parameter_value(e.parameter.description(), e.widget)
        except AlgorithmDialogBase.InvalidOutputExtension as e:
            self.flag_invalid_output_extension(e.message, e.widget)
        return {}

    def processingContext(self):
        if self.context is None:
            self.feedback = self.createFeedback()
            self.context = createContext(feedback=self.feedback,
                                         project=self._context.project() if self._context else None,
                                         iface=self._iface)

        self.applyContextOverrides(self.context)
        return self.context

    def runAlgorithm(self):
        self.feedback = self.createFeedback()
        self.context = createContext(feedback=self.feedback,
                                     project=self._context.project() if self._context else None,
                                     iface=self._iface,
                                     )
        self.applyContextOverrides(self.context)
        self.algorithmAboutToRun.emit(self.context)

        checkCRS = ProcessingConfig.getSetting(ProcessingConfig.WARN_UNMATCHING_CRS)
        try:
            # messy as all heck, but we don't want to call the dialog's implementation of
            # createProcessingParameters as we want to catch the exceptions raised by the
            # parameter panel instead...
            parameters = (
                {}
                if self.mainWidget() is None
                else self.mainWidget().createProcessingParameters()
            )

            if checkCRS and not self.algorithm().validateInputCrs(
                    parameters, self.context
            ):
                reply = QMessageBox.question(
                    self,
                    self.tr("Unmatching CRS's"),
                    self.tr(
                        "Parameters do not all use the same CRS. This can "
                        "cause unexpected results.\nDo you want to "
                        "continue?"
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            ok, msg = self.algorithm().checkParameterValues(parameters, self.context)
            if not ok:
                QMessageBox.warning(self, self.tr("Unable to execute algorithm"), msg)
                return

            self.blockControlsWhileRunning()
            self.setExecutedAnyResult(True)
            self.cancelButton().setEnabled(False)

            self.iterateParam = None

            for param in self.algorithm().parameterDefinitions():
                if (
                        isinstance(
                            parameters.get(param.name(), None),
                            QgsProcessingFeatureSourceDefinition,
                        )
                        and parameters[param.name()].flags
                        & QgsProcessingFeatureSourceDefinition.Flag.FlagCreateIndividualOutputPerInputFeature
                ):
                    self.iterateParam = param.name()
                    break

            self.clearProgress()
            self.feedback.pushVersionInfo(self.algorithm().provider())
            if (
                    self.algorithm().provider()
                    and self.algorithm().provider().warningMessage()
            ):
                self.feedback.reportError(self.algorithm().provider().warningMessage())

            self.feedback.pushInfo(
                QCoreApplication.translate(
                    "AlgorithmDialog", "Algorithm started at: {}"
                ).format(datetime.datetime.now().replace(microsecond=0).isoformat())
            )

            self.setInfo(
                QCoreApplication.translate(
                    "AlgorithmDialog", "<b>Algorithm '{0}' starting&hellip;</b>"
                ).format(self.algorithm().displayName()),
                escapeHtml=False,
            )

            self.feedback.pushInfo(self.tr("Input parameters:"))
            display_params = []
            for k, v in parameters.items():
                display_params.append(
                    "'"
                    + k
                    + "' : "
                    + self.algorithm()
                    .parameterDefinition(k)
                    .valueAsPythonString(v, self.context)
                )
            self.feedback.pushCommandInfo("{ " + ", ".join(display_params) + " }")
            self.feedback.pushInfo("")
            start_time = time.time()

            def elapsed_time(start_time) -> str:
                delta_t = time.time() - start_time
                hours = int(delta_t / 3600)
                minutes = int((delta_t % 3600) / 60)
                seconds = delta_t - hours * 3600 - minutes * 60

                str_hours = [self.tr("hour"), self.tr("hours")][hours > 1]
                str_minutes = [self.tr("minute"), self.tr("minutes")][minutes > 1]
                str_seconds = [self.tr("second"), self.tr("seconds")][seconds != 1]

                if hours > 0:
                    elapsed = "{0:0.2f} {1} ({2} {3} {4} {5} {6:0.0f} {1})".format(
                        delta_t,
                        str_seconds,
                        hours,
                        str_hours,
                        minutes,
                        str_minutes,
                        seconds,
                    )
                elif minutes > 0:
                    elapsed = "{0:0.2f} {1} ({2} {3} {4:0.0f} {1})".format(
                        delta_t, str_seconds, minutes, str_minutes, seconds
                    )
                else:
                    elapsed = f"{delta_t:0.2f} {str_seconds}"

                return elapsed

            if self.iterateParam:
                # Make sure the Log tab is visible before executing the algorithm
                try:
                    self.showLog()
                    self.repaint()
                except Exception:
                    pass

                self.cancelButton().setEnabled(
                    self.algorithm().flags() & QgsProcessingAlgorithm.Flag.FlagCanCancel
                )
                if executeIterating(
                        self.algorithm(),
                        parameters,
                        self.iterateParam,
                        self.context,
                        self.feedback,
                ):
                    self.feedback.pushInfo(
                        self.tr("Execution completed in {}").format(
                            elapsed_time(start_time)
                        )
                    )
                    self.cancelButton().setEnabled(False)
                    self.finish(True, parameters, self.context, self.feedback)
                else:
                    self.cancelButton().setEnabled(False)
                    self.resetGui()
            else:
                self.history_details = {
                    "python_command": self.algorithm().asPythonCommand(
                        parameters, self.context
                    ),
                    "algorithm_id": self.algorithm().id(),
                    "parameters": self.algorithm().asMap(parameters, self.context),
                }
                process_command, command_ok = self.algorithm().asQgisProcessCommand(
                    parameters, self.context
                )
                if command_ok:
                    self.history_details["process_command"] = process_command
                self.history_log_id, _ = QgsGui.historyProviderRegistry().addEntry(
                    "processing", self.history_details
                )

                QgsGui.instance().processingRecentAlgorithmLog().push(
                    self.algorithm().id()
                )
                self.cancelButton().setEnabled(
                    self.algorithm().flags() & QgsProcessingAlgorithm.Flag.FlagCanCancel
                )

                def on_complete(ok, results):
                    if ok:
                        self.feedback.pushInfo(
                            self.tr("Execution completed in {}").format(
                                elapsed_time(start_time)
                            )
                        )
                        self.feedback.pushFormattedResults(
                            self.algorithm(), self.context, results
                        )
                    else:
                        self.feedback.reportError(
                            self.tr("Execution failed after {}").format(
                                elapsed_time(start_time)
                            )
                        )
                    self.feedback.pushInfo("")

                    if self.history_log_id is not None:
                        # can't deepcopy this!
                        self.history_details["results"] = {
                            k: v for k, v in results.items() if k != "CHILD_INPUTS"
                        }
                        self.history_details["log"] = self.feedback.htmlLog()

                        QgsGui.historyProviderRegistry().updateEntry(
                            self.history_log_id, self.history_details
                        )

                    if self.feedback_dialog is not None:
                        self.feedback_dialog.close()
                        self.feedback_dialog.deleteLater()
                        self.feedback_dialog = None

                    self.cancelButton().setEnabled(False)

                    self.finish(
                        ok, results, self.context, self.feedback, in_place=self.in_place
                    )

                    self.feedback = None
                    self.context = None

                if not self.in_place and not (
                        self.algorithm().flags()
                        & QgsProcessingAlgorithm.Flag.FlagNoThreading
                ):
                    # Make sure the Log tab is visible before executing the algorithm
                    self.showLog()

                    task = QgsProcessingAlgRunnerTask(
                        self.algorithm(), parameters, self.context, self.feedback
                    )
                    if task.isCanceled():
                        on_complete(False, {})
                    else:
                        task.executed.connect(on_complete)
                        self.setCurrentTask(task)
                else:
                    self.proxy_progress = QgsProxyProgressTask(
                        QCoreApplication.translate(
                            "AlgorithmDialog", "Executing “{}”"
                        ).format(self.algorithm().displayName())
                    )
                    QgsApplication.taskManager().addTask(self.proxy_progress)
                    self.feedback.progressChanged.connect(
                        self.proxy_progress.setProxyProgress
                    )
                    self.feedback_dialog = self.createProgressDialog()
                    self.feedback_dialog.show()
                    if self.in_place:
                        ok, results = execute_in_place(
                            self.algorithm(), parameters, self.context, self.feedback
                        )
                    else:
                        ok, results = execute(
                            self.algorithm(), parameters, self.context, self.feedback
                        )
                    self.feedback.progressChanged.disconnect()
                    self.proxy_progress.finalize(ok)
                    on_complete(ok, results)

        except AlgorithmDialogBase.InvalidParameterValue as e:
            self.flag_invalid_parameter_value(e.parameter.description(), e.widget)
        except AlgorithmDialogBase.InvalidOutputExtension as e:
            self.flag_invalid_output_extension(e.message, e.widget)

    def finish(self, successful, result, context, feedback, in_place=False):
        keepOpen = not successful or ProcessingConfig.getSetting(
            ProcessingConfig.KEEP_DIALOG_OPEN
        )
        generated_html_outputs = False

        if not in_place and self.iterateParam is None:

            # add html results to results dock
            for out in self.algorithm().outputDefinitions():
                if (
                        isinstance(out, QgsProcessingOutputHtml)
                        and out.name() in result
                        and result[out.name()]
                ):
                    resultsList.addResult(
                        icon=self.algorithm().icon(),
                        name=out.description(),
                        timestamp=time.localtime(),
                        result=result[out.name()],
                    )
                    generated_html_outputs = True
            if not handleAlgorithmResults(self.algorithm(), context,
                                          feedback=feedback, parameters=result,
                                          iface=self._iface):
                self.resetGui()
                return

        self.setExecuted(True)
        self.setResults(result)
        self.setInfo(
            self.tr("Algorithm '{0}' finished").format(self.algorithm().displayName()),
            escapeHtml=False,
        )
        self.algorithmFinished.emit(successful, result)

        if not in_place and not keepOpen:
            self.close()
        else:
            self.resetGui()
            if generated_html_outputs:
                self.setInfo(
                    self.tr(
                        "HTML output has been generated by this algorithm."
                        "\nOpen the results dialog to check it."
                    ),
                    escapeHtml=False,
                )


class ParametersPanel(QgsProcessingParametersWidget):

    def __init__(self, parent, alg, in_place=False, active_layer=None,
                 context: Optional[QgsProcessingContext] = None,
                 iface: Optional[QgisInterface] = None):
        super().__init__(alg, parent)
        self.in_place = in_place
        self.active_layer = active_layer

        if isinstance(context, QgsProcessingContext):
            _project = context.project()
        else:
            _project = QgsProject.instance()

        if not isinstance(iface, QgisInterface):
            iface = qgis.utils.iface

        self._iface = iface

        self.wrappers = {}

        self.extra_parameters = {}

        self.processing_context = createContext(project=_project, iface=self._iface)

        class ContextGenerator(QgsProcessingContextGenerator):

            def __init__(self, context):
                super().__init__()
                self.processing_context = context

            def processingContext(self):
                return self.processing_context

        self.context_generator = ContextGenerator(self.processing_context)

        self.initWidgets()

        _project.layerWasAdded.connect(self.layerRegistryChanged)
        _project.layersWillBeRemoved.connect(self.layerRegistryChanged)

    def layerRegistryChanged(self, layers):
        for wrapper in list(self.wrappers.values()):
            try:
                wrapper.refresh()
            except AttributeError:
                pass

    def initWidgets(self):
        super().initWidgets()

        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(self.processing_context.project())
        if self._iface is not None:
            widget_context.setMapCanvas(self._iface.mapCanvas())
            widget_context.setBrowserModel(self._iface.browserModel())
            widget_context.setActiveLayer(self._iface.activeLayer())

        widget_context.setMessageBar(self.parent().messageBar())
        if isinstance(self.algorithm(), QgsProcessingModelAlgorithm):
            widget_context.setModel(self.algorithm())

        in_place_input_parameter_name = "INPUT"
        if hasattr(self.algorithm(), "inputParameterName"):
            in_place_input_parameter_name = self.algorithm().inputParameterName()

        # Create widgets and put them in layouts
        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                continue

            if param.isDestination():
                continue
            else:
                if self.in_place and param.name() in (
                        in_place_input_parameter_name,
                        "OUTPUT",
                ):
                    # don't show the input/output parameter widgets in in-place mode
                    # we still need to CREATE them, because other wrappers may need to interact
                    # with them (e.g. those parameters which need the input layer for field
                    # selections/crs properties/etc)
                    self.wrappers[param.name()] = QgsProcessingHiddenWidgetWrapper(
                        param, QgsProcessingGui.WidgetType.Standard, self
                    )
                    self.wrappers[param.name()].setLinkedVectorLayer(self.active_layer)
                    continue

                wrapper = WidgetWrapperFactory.create_wrapper(param, self.parent())
                wrapper.setWidgetContext(widget_context)
                wrapper.registerProcessingContextGenerator(self.context_generator)
                wrapper.registerProcessingParametersGenerator(self)
                self.wrappers[param.name()] = wrapper

                # For compatibility with 3.x API, we need to check whether the wrapper is
                # the deprecated WidgetWrapper class. If not, it's the newer
                # QgsAbstractProcessingParameterWidgetWrapper class
                # TODO QGIS 4.0 - remove
                is_python_wrapper = issubclass(wrapper.__class__, WidgetWrapper)
                stretch = 0
                if not is_python_wrapper:
                    widget = wrapper.createWrappedWidget(self.processing_context)
                    stretch = wrapper.stretch()
                else:
                    widget = wrapper.widget

                if widget is not None:
                    if is_python_wrapper:
                        widget.setToolTip(param.toolTip())

                    label = None
                    if not is_python_wrapper:
                        label = wrapper.createWrappedLabel()
                    else:
                        label = wrapper.label

                    if label is not None:
                        self.addParameterLabel(param, label)
                    elif is_python_wrapper:
                        desc = param.description()
                        if isinstance(param, QgsProcessingParameterExtent):
                            desc += self.tr(" (xmin, xmax, ymin, ymax)")
                        if (
                                param.flags()
                                & QgsProcessingParameterDefinition.Flag.FlagOptional
                        ):
                            desc += self.tr(" [optional]")
                        widget.setText(desc)

                    self.addParameterWidget(param, widget, stretch)

        for output in self.algorithm().destinationParameterDefinitions():
            if output.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                continue

            if self.in_place and output.name() in (
                    in_place_input_parameter_name,
                    "OUTPUT",
            ):
                continue

            wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(
                output, QgsProcessingGui.WidgetType.Standard
            )
            wrapper.setWidgetContext(widget_context)
            wrapper.registerProcessingContextGenerator(self.context_generator)
            wrapper.registerProcessingParametersGenerator(self)
            self.wrappers[output.name()] = wrapper

            label = wrapper.createWrappedLabel()
            if label is not None:
                self.addOutputLabel(label)

            widget = wrapper.createWrappedWidget(self.processing_context)
            self.addOutputWidget(widget, wrapper.stretch())

            #    def skipOutputChanged(widget, checkbox, skipped):
            # TODO
            #        enabled = not skipped
            #
            #        # Do not try to open formats that are write-only.
            #        value = widget.value()
            #        if value and isinstance(value, QgsProcessingOutputLayerDefinition) and isinstance(output, (
            #                QgsProcessingParameterFeatureSink, QgsProcessingParameterVectorDestination)):
            #            filename = value.sink.staticValue()
            #            if filename not in ('memory:', ''):
            #                path, ext = os.path.splitext(filename)
            #                format = QgsVectorFileWriter.driverForExtension(ext)
            #                drv = gdal.GetDriverByName(format)
            #                if drv:
            #                    if drv.GetMetadataItem(gdal.DCAP_OPEN) is None:
            #                        enabled = False
            #
            #        checkbox.setEnabled(enabled)
            #        checkbox.setChecked(enabled)

        for wrapper in list(self.wrappers.values()):
            wrapper.postInitialize(list(self.wrappers.values()))

    def createProcessingParameters(
            self, flags=QgsProcessingParametersGenerator.Flags()
    ):
        include_default = not (
                flags & QgsProcessingParametersGenerator.Flag.SkipDefaultValueParameters
        )
        parameters = {}
        for p, v in self.extra_parameters.items():
            parameters[p] = v

        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                continue
            if not param.isDestination():
                try:
                    wrapper = self.wrappers[param.name()]
                except KeyError:
                    continue

                # For compatibility with 3.x API, we need to check whether the wrapper is
                # the deprecated WidgetWrapper class. If not, it's the newer
                # QgsAbstractProcessingParameterWidgetWrapper class
                # TODO QGIS 4.0 - remove
                if issubclass(wrapper.__class__, WidgetWrapper):
                    widget = wrapper.widget
                else:
                    widget = wrapper.wrappedWidget()

                if (
                        not isinstance(wrapper, QgsProcessingHiddenWidgetWrapper)
                        and widget is None
                ):
                    continue

                value = wrapper.parameterValue()
                if param.defaultValue() != value or include_default:
                    parameters[param.name()] = value

                if not param.checkValueIsAcceptable(value):
                    raise AlgorithmDialogBase.InvalidParameterValue(param, widget)
            else:
                if self.in_place and param.name() == "OUTPUT":
                    parameters[param.name()] = "memory:"
                    continue

                try:
                    wrapper = self.wrappers[param.name()]
                except KeyError:
                    continue

                widget = wrapper.wrappedWidget()
                value = wrapper.parameterValue()

                dest_project = None
                if wrapper.customProperties().get("OPEN_AFTER_RUNNING"):
                    dest_project = self.processing_context.project()

                if value and isinstance(value, QgsProcessingOutputLayerDefinition):
                    value.destinationProject = dest_project
                if value and (param.defaultValue() != value or include_default):
                    parameters[param.name()] = value

                    context = createContext()
                    ok, error = param.isSupportedOutputValue(value, context)
                    if not ok:
                        raise AlgorithmDialogBase.InvalidOutputExtension(widget, error)

        return self.algorithm().preprocessParameters(parameters)

    def setParameters(self, parameters):
        self.extra_parameters = {}
        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                if param.name() in parameters:
                    self.extra_parameters[param.name()] = parameters[param.name()]
                continue

            if not param.name() in parameters:
                continue

            value = parameters[param.name()]

            wrapper = self.wrappers[param.name()]
            wrapper.setParameterValue(value, self.processing_context)


class BatchAlgorithmDialog(QgsProcessingBatchAlgorithmDialogBase):

    def __init__(self, alg, parent=None,
                 context: Optional[QgsProcessingContext] = None,
                 iface: Optional[QgisInterface] = None):

        super().__init__(parent)

        if not isinstance(iface, QgisInterface):
            iface = qgis.utils.iface
        self._iface = iface
        self._context = context
        self._project = context.project() if isinstance(context, QgsProcessingContext) else QgsProject.instance()

        self.setAlgorithm(alg)

        self.setWindowTitle(
            self.tr("Batch Processing - {0}").format(self.algorithm().displayName())
        )
        self.setMainWidget(BatchPanel(self, self.algorithm(), context=self._context, iface=self._iface))

        self.context = None
        self.hideShortHelp()

    def runAsSingle(self):
        self.close()
        dlg = AlgorithmDialog(self.algorithm().create(), parent=self._iface.mainWindow(),
                              context=self._context,
                              iface=self._iface)
        dlg.show()
        dlg.exec()

    def processingContext(self):
        if self.context is None:
            self.feedback = self.createFeedback()
            self.context = createContext(self.feedback,
                                         iface=self._iface,
                                         project=self._project)
            self.context.setLogLevel(self.logLevel())
        return self.context

    def createContext(self, feedback):
        return createContext(feedback, project=self._project, iface=self._iface)

    def runAlgorithm(self):
        alg_parameters = []

        load_layers = self.mainWidget().checkLoadLayersOnCompletion.isChecked()
        project = self.processingContext().project() if load_layers else None

        for row in range(self.mainWidget().batchRowCount()):
            parameters, ok = self.mainWidget().parametersForRow(
                row=row,
                context=self.processingContext(),
                destinationProject=project,
                warnOnInvalid=True,
            )
            if ok:
                alg_parameters.append(parameters)
        if not alg_parameters:
            return

        self.execute(alg_parameters)

    def handleAlgorithmResults(self, algorithm, context, feedback, parameters):
        handleAlgorithmResults(alg=algorithm, context=context, feedback=feedback, parameters=parameters)

    def loadHtmlResults(self, results, num):
        for out in self.algorithm().outputDefinitions():
            if (
                    isinstance(out, QgsProcessingOutputHtml)
                    and out.name() in results
                    and results[out.name()]
            ):
                resultsList.addResult(
                    icon=self.algorithm().icon(),
                    name=f"{out.description()} [{num}]",
                    result=results[out.name()],
                )

    def createSummaryTable(self, algorithm_results, errors):
        createTable = False

        for out in self.algorithm().outputDefinitions():
            if isinstance(
                    out,
                    (
                            QgsProcessingOutputNumber,
                            QgsProcessingOutputString,
                            QgsProcessingOutputBoolean,
                    ),
            ):
                createTable = True
                break

        if not createTable and not errors:
            return

        outputFile = getTempFilename("html")
        with codecs.open(outputFile, "w", encoding="utf-8") as f:
            if createTable:
                for i, res in enumerate(algorithm_results):
                    results = res["results"]
                    params = res["parameters"]
                    if i > 0:
                        f.write("<hr>\n")
                    f.write(self.tr("<h3>Parameters</h3>\n"))
                    f.write("<table>\n")
                    for param in self.algorithm().parameterDefinitions():
                        if not param.isDestination():
                            if param.name() in params:
                                f.write(
                                    "<tr><th>{}</th><td>{}</td></tr>\n".format(
                                        param.description(), params[param.name()]
                                    )
                                )
                    f.write("</table>\n")
                    f.write(self.tr("<h3>Results</h3>\n"))
                    f.write("<table>\n")
                    for out in self.algorithm().outputDefinitions():
                        if out.name() in results:
                            f.write(
                                f"<tr><th>{out.description()}</th><td>{results[out.name()]}</td></tr>\n"
                            )
                    f.write("</table>\n")
            if errors:
                f.write('<h2 style="color: red">{}</h2>\n'.format(self.tr("Errors")))
            for i, res in enumerate(errors):
                errors = res["errors"]
                params = res["parameters"]
                if i > 0:
                    f.write("<hr>\n")
                f.write(self.tr("<h3>Parameters</h3>\n"))
                f.write("<table>\n")
                for param in self.algorithm().parameterDefinitions():
                    if not param.isDestination():
                        if param.name() in params:
                            f.write(
                                f"<tr><th>{param.description()}</th><td>{params[param.name()]}</td></tr>\n"
                            )
                f.write("</table>\n")
                f.write("<h3>{}</h3>\n".format(self.tr("Error")))
                f.write('<p style="color: red">{}</p>\n'.format("<br>".join(errors)))

        resultsList.addResult(
            icon=self.algorithm().icon(),
            name=f"{self.algorithm().name()} [summary]",
            timestamp=time.localtime(),
            result=outputFile,
        )


class BatchPanel(QgsPanelWidget, WIDGET):
    PARAMETERS = "PARAMETERS"
    OUTPUTS = "OUTPUTS"
    ROWS = "rows"
    FORMAT = "format"
    CURRENT_FORMAT = "batch_3.40"

    def __init__(self, parent, alg, context: QgsProcessingContext,
                 iface: Optional[QgisInterface] = None):
        super().__init__(None)
        self.setupUi(self)

        self._context = context

        if not isinstance(iface, QgisInterface):
            iface = qgis.utils.iface
        self._iface = iface

        self.wrappers = []

        self.btnAdvanced.hide()

        # Set icons
        self.btnAdd.setIcon(QgsApplication.getThemeIcon("/symbologyAdd.svg"))
        self.btnRemove.setIcon(QgsApplication.getThemeIcon("/symbologyRemove.svg"))
        self.btnOpen.setIcon(QgsApplication.getThemeIcon("/mActionFileOpen.svg"))
        self.btnSave.setIcon(QgsApplication.getThemeIcon("/mActionFileSave.svg"))
        self.btnAdvanced.setIcon(
            QgsApplication.getThemeIcon("/processingAlgorithm.svg")
        )

        self.alg = alg
        self.parent = parent

        self.btnAdd.clicked.connect(lambda: self.addRow(1))
        self.btnRemove.clicked.connect(self.removeRows)
        self.btnOpen.clicked.connect(self.load)
        self.btnSave.clicked.connect(self.save)
        self.btnAdvanced.toggled.connect(self.toggleAdvancedMode)

        self.tblParameters.horizontalHeader().resizeSections(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tblParameters.horizontalHeader().setDefaultSectionSize(250)
        self.tblParameters.horizontalHeader().setMinimumSectionSize(150)

        self.processing_context = createContext(iface=self._iface, project=context.project())

        class ContextGenerator(QgsProcessingContextGenerator):

            def __init__(self, context):
                super().__init__()
                self.processing_context = context

            def processingContext(self):
                return self.processing_context

        self.context_generator = ContextGenerator(self.processing_context)

        self.column_to_parameter_definition = {}
        self.parameter_to_column = {}

        self.initWidgets()

    def layerRegistryChanged(self):
        pass

    def initWidgets(self):
        # If there are advanced parameters — show corresponding button
        for param in self.alg.parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.Flag.FlagAdvanced:
                self.btnAdvanced.show()
                break

        # Determine column count
        self.tblParameters.setColumnCount(len(self.alg.parameterDefinitions()))

        # Table headers
        column = 0
        for param in self.alg.parameterDefinitions():
            if param.isDestination():
                continue
            self.tblParameters.setHorizontalHeaderItem(
                column, QTableWidgetItem(param.description())
            )
            if (
                    param.flags() & QgsProcessingParameterDefinition.Flag.FlagAdvanced
                    or param.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden
            ):
                self.tblParameters.setColumnHidden(column, True)

            self.column_to_parameter_definition[column] = param.name()
            self.parameter_to_column[param.name()] = column
            column += 1

        for out in self.alg.destinationParameterDefinitions():
            if not out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                self.tblParameters.setHorizontalHeaderItem(
                    column, QTableWidgetItem(out.description())
                )
                self.column_to_parameter_definition[column] = out.name()
                self.parameter_to_column[out.name()] = column
                column += 1

        self.addFillRow()

        # Add an empty row to begin
        self.addRow()

        self.tblParameters.horizontalHeader().resizeSections(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tblParameters.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tblParameters.horizontalHeader().setStretchLastSection(True)

    def batchRowCount(self):
        """
        Returns the number of rows corresponding to execution iterations
        """
        return len(self.wrappers)

    def clear(self):
        self.tblParameters.setRowCount(1)
        self.wrappers = []

    def load(self):
        if self.alg.flags() & Qgis.ProcessingAlgorithmFlag.SecurityRisk:
            message_box = QMessageBox()
            message_box.setWindowTitle(self.tr("Security warning"))
            message_box.setText(
                self.tr(
                    "This algorithm is a potential security risk if executed with unchecked inputs, and may result in system damage or data leaks. Only continue if you trust the source of the file. Continue?"
                )
            )
            message_box.setIcon(QMessageBox.Icon.Warning)
            message_box.addButton(QMessageBox.StandardButton.Yes)
            message_box.addButton(QMessageBox.StandardButton.No)
            message_box.setDefaultButton(QMessageBox.StandardButton.No)
            message_box.exec()
            if message_box.result() != QMessageBox.StandardButton.Yes:
                return

        settings = QgsSettings()
        last_path = settings.value("/Processing/LastBatchPath", QDir.homePath())
        filters = ";;".join(
            [
                self.tr("Batch Processing files (*.batch)"),
                self.tr("JSON files (*.json)"),
            ]
        )
        filename, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open Batch"), last_path, filters
        )
        if not filename:
            return

        last_path = QFileInfo(filename).path()
        settings.setValue("/Processing/LastBatchPath", last_path)
        with open(filename) as f:
            values = json.load(f)

        if isinstance(values, dict):
            if values.get(self.FORMAT) == self.CURRENT_FORMAT:
                self.load_batch_file_3_40_version(values)
            else:
                QMessageBox.critical(
                    self,
                    self.tr("Load Batch Parameters"),
                    self.tr(
                        "This file format is unknown and cannot be opened as batch parameters."
                    ),
                )
        else:
            self.load_old_json_batch_file(values)

    def load_batch_file_3_40_version(self, values: dict):
        """
        Loads the newer version 3.40 batch parameter JSON format
        """
        context = dataobjects.createContext()
        rows: list = values.get(self.ROWS, [])

        self.clear()
        for row_number, row in enumerate(rows):
            self.addRow()
            this_row_params = row[self.PARAMETERS]
            this_row_outputs = row[self.OUTPUTS]

            for param in self.alg.parameterDefinitions():
                if param.isDestination():
                    continue
                if param.name() in this_row_params:
                    column = self.parameter_to_column[param.name()]
                    value = this_row_params[param.name()]
                    wrapper = self.wrappers[row_number][column]
                    wrapper.setParameterValue(value, context)

            for out in self.alg.destinationParameterDefinitions():
                if out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                    continue
                if out.name() in this_row_outputs:
                    column = self.parameter_to_column[out.name()]
                    value = this_row_outputs[out.name()].strip("'")
                    widget = self.tblParameters.cellWidget(row_number + 1, column)
                    widget.setValue(value)

    def load_old_json_batch_file(self, values: list):
        """
        Loads the old, insecure batch parameter JSON format
        """
        message_box = QMessageBox()
        message_box.setWindowTitle(self.tr("Security warning"))
        message_box.setText(
            self.tr(
                "Opening older QGIS batch Processing files from an untrusted source can harm your computer. Only continue if you trust the source of the file. Continue?"
            )
        )
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.addButton(QMessageBox.StandardButton.Yes)
        message_box.addButton(QMessageBox.StandardButton.No)
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        message_box.exec()
        if message_box.result() != QMessageBox.StandardButton.Yes:
            return

        self.clear()
        context = dataobjects.createContext()
        try:
            for row, alg in enumerate(values):
                self.addRow()
                params = alg[self.PARAMETERS]
                outputs = alg[self.OUTPUTS]

                for param in self.alg.parameterDefinitions():
                    if param.isDestination():
                        continue
                    if param.name() in params:
                        column = self.parameter_to_column[param.name()]
                        value = eval(params[param.name()])
                        wrapper = self.wrappers[row][column]
                        wrapper.setParameterValue(value, context)

                for out in self.alg.destinationParameterDefinitions():
                    if out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                        continue
                    if out.name() in outputs:
                        column = self.parameter_to_column[out.name()]
                        value = outputs[out.name()].strip("'")
                        widget = self.tblParameters.cellWidget(row + 1, column)
                        widget.setValue(value)
        except TypeError:
            QMessageBox.critical(
                self,
                self.tr("Load Batch Parameters"),
                self.tr("An error occurred while reading the batch parameters file."),
            )

    def save(self):
        row_parameters = []
        context = dataobjects.createContext()
        for row in range(self.batchRowCount()):
            this_row_params = {}
            this_row_outputs = {}
            alg = self.alg
            for param in alg.parameterDefinitions():
                if param.isDestination():
                    continue

                col = self.parameter_to_column[param.name()]
                wrapper = self.wrappers[row][col]

                value = wrapper.parameterValue()

                if not param.checkValueIsAcceptable(value, context):
                    msg = self.tr(
                        "Wrong or missing parameter value: {0} (row {1})"
                    ).format(param.description(), row + 2)
                    self.parent.messageBar().pushMessage(
                        "", msg, level=Qgis.MessageLevel.Warning, duration=5
                    )
                    return
                this_row_params[param.name()] = param.valueAsJsonObject(value, context)

            for out in alg.destinationParameterDefinitions():
                if out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                    continue
                col = self.parameter_to_column[out.name()]
                widget = self.tblParameters.cellWidget(row + 1, col)
                text = widget.getValue()
                if text.strip() != "":
                    this_row_outputs[out.name()] = text.strip()
                else:
                    self.parent.messageBar().pushMessage(
                        "",
                        self.tr("Wrong or missing output value: {0} (row {1})").format(
                            out.description(), row + 2
                        ),
                        level=Qgis.MessageLevel.Warning,
                        duration=5,
                    )
                    return
            row_parameters.append(
                {self.PARAMETERS: this_row_params, self.OUTPUTS: this_row_outputs}
            )

        output_json = {self.FORMAT: self.CURRENT_FORMAT, self.ROWS: row_parameters}

        settings = QgsSettings()
        last_path = settings.value("/Processing/LastBatchPath", QDir.homePath())
        filename, __ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Batch"),
            last_path,
            self.tr("Batch Processing files (*.batch)"),
        )
        if not filename:
            return

        filename = QgsFileUtils.ensureFileNameHasExtension(filename, ["batch"])
        last_path = QFileInfo(filename).path()
        settings.setValue("/Processing/LastBatchPath", last_path)
        with open(filename, "w") as f:
            json.dump(output_json, f, indent=2)

    def setCellWrapper(self, row, column, wrapper, context):
        self.wrappers[row - 1][column] = wrapper

        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(self.processing_context.project())
        if self._iface is not None:
            widget_context.setActiveLayer(self._iface.activeLayer())
            widget_context.setMapCanvas(self._iface.mapCanvas())

        widget_context.setMessageBar(self.parent.messageBar())

        if isinstance(self.alg, QgsProcessingModelAlgorithm):
            widget_context.setModel(self.alg)
        wrapper.setWidgetContext(widget_context)
        wrapper.registerProcessingContextGenerator(self.context_generator)

        # For compatibility with 3.x API, we need to check whether the wrapper is
        # the deprecated WidgetWrapper class. If not, it's the newer
        # QgsAbstractProcessingParameterWidgetWrapper class
        # TODO QGIS 4.0 - remove
        is_cpp_wrapper = not issubclass(wrapper.__class__, WidgetWrapper)
        if is_cpp_wrapper:
            widget = wrapper.createWrappedWidget(context)
        else:
            widget = wrapper.widget

        self.tblParameters.setCellWidget(row, column, widget)

    def addFillRow(self):
        self.tblParameters.setRowCount(1)
        for col, name in self.column_to_parameter_definition.items():
            param_definition = self.alg.parameterDefinition(
                self.column_to_parameter_definition[col]
            )
            self.tblParameters.setCellWidget(
                0, col, BatchPanelFillWidget(param_definition, col, self)
            )

    def addRow(self, nb=1):
        self.tblParameters.setUpdatesEnabled(False)
        self.tblParameters.setRowCount(self.tblParameters.rowCount() + nb)

        context = dataobjects.createContext()

        wrappers = {}
        row = self.tblParameters.rowCount() - nb
        while row < self.tblParameters.rowCount():
            self.wrappers.append([None] * self.tblParameters.columnCount())
            for param in self.alg.parameterDefinitions():
                if param.isDestination():
                    continue

                column = self.parameter_to_column[param.name()]
                wrapper = WidgetWrapperFactory.create_wrapper(
                    param, self.parent, row, column
                )
                wrappers[param.name()] = wrapper
                self.setCellWrapper(row, column, wrapper, context)

            for out in self.alg.destinationParameterDefinitions():
                if out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                    continue

                column = self.parameter_to_column[out.name()]
                self.tblParameters.setCellWidget(
                    row,
                    column,
                    BatchOutputSelectionPanel(out, self.alg, row, column, self),
                )

            for wrapper in list(wrappers.values()):
                wrapper.postInitialize(list(wrappers.values()))
            row += 1

        self.tblParameters.setUpdatesEnabled(True)

    def removeRows(self):
        rows = set()
        for index in self.tblParameters.selectedIndexes():
            if index.row() == 0:
                continue
            rows.add(index.row())

        for row in sorted(rows, reverse=True):
            if self.tblParameters.rowCount() <= 2:
                break

            del self.wrappers[row - 1]
            self.tblParameters.removeRow(row)

        # resynchronize stored row numbers for table widgets
        for row in range(1, self.tblParameters.rowCount()):
            for col in range(0, self.tblParameters.columnCount()):
                cell_widget = self.tblParameters.cellWidget(row, col)
                if not cell_widget:
                    continue

                if isinstance(cell_widget, BatchOutputSelectionPanel):
                    cell_widget.row = row

    def toggleAdvancedMode(self, checked):
        for param in self.alg.parameterDefinitions():
            if (
                    param.flags() & QgsProcessingParameterDefinition.Flag.FlagAdvanced
                    and not (
                    param.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden
            )
            ):
                self.tblParameters.setColumnHidden(
                    self.parameter_to_column[param.name()], not checked
                )

    def valueForParameter(self, row, parameter_name):
        """
        Returns the current value for a parameter in a row
        """
        wrapper = self.wrappers[row][self.parameter_to_column[parameter_name]]
        return wrapper.parameterValue()

    def parametersForRow(
            self,
            row: int,
            context: QgsProcessingContext,
            destinationProject: Optional[QgsProject] = None,
            warnOnInvalid: bool = True,
    ):
        """
        Returns the parameters dictionary corresponding to a row in the batch table
        """
        parameters = {}
        for param in self.alg.parameterDefinitions():
            if param.isDestination():
                continue
            col = self.parameter_to_column[param.name()]
            wrapper = self.wrappers[row][col]
            parameters[param.name()] = wrapper.parameterValue()
            if warnOnInvalid and not param.checkValueIsAcceptable(
                    wrapper.parameterValue()
            ):
                self.parent.messageBar().pushMessage(
                    "",
                    self.tr("Wrong or missing parameter value: {0} (row {1})").format(
                        param.description(), row + 2
                    ),
                    level=Qgis.MessageLevel.Warning,
                    duration=5,
                )
                return {}, False

        count_visible_outputs = 0
        for out in self.alg.destinationParameterDefinitions():
            if out.flags() & QgsProcessingParameterDefinition.Flag.FlagHidden:
                continue

            col = self.parameter_to_column[out.name()]

            count_visible_outputs += 1
            widget = self.tblParameters.cellWidget(row + 1, col)
            text = widget.getValue()
            if warnOnInvalid:
                if not out.checkValueIsAcceptable(text):
                    msg = self.tr(
                        "Wrong or missing output value: {0} (row {1})"
                    ).format(out.description(), row + 2)
                    self.parent.messageBar().pushMessage(
                        "", msg, level=Qgis.MessageLevel.Warning, duration=5
                    )
                    return {}, False

                ok, error = out.isSupportedOutputValue(text, context)
                if not ok:
                    self.parent.messageBar().pushMessage(
                        "", error, level=Qgis.MessageLevel.Warning, duration=5
                    )
                    return {}, False

            if isinstance(
                    out,
                    (
                            QgsProcessingParameterRasterDestination,
                            QgsProcessingParameterVectorDestination,
                            QgsProcessingParameterFeatureSink,
                    ),
            ):
                # load rasters and sinks on completion
                parameters[out.name()] = QgsProcessingOutputLayerDefinition(
                    text, destinationProject
                )
            else:
                parameters[out.name()] = text

        return parameters, True
