from typing import Dict, Optional

from processing import AlgorithmDialog, handleAlgorithmResults
from processing.gui.AlgorithmExecutor import execute
from processing.gui.BatchAlgorithmDialog import BatchAlgorithmDialog
from processing.gui.MessageBarProgress import MessageBarProgress
from processing.gui.MessageDialog import MessageDialog
from processing.tools import dataobjects
from PyQt5.QtCore import QMetaType
from qgis._core import Qgis, QgsFields, QgsMapLayer, QgsProcessing, \
    QgsProcessingException, QgsProcessingFeedback, QgsProcessingParameterCrs, QgsProcessingParameterFeatureSink, \
    QgsProcessingParameterField, QgsProcessingParameterFile, QgsProcessingParameterString, \
    QgsProcessingParameterVectorLayer, QgsProcessingRegistry, QgsVectorLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import edit, QgsApplication, QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingProvider
from qgis.gui import QgisInterface

from eotimeseriesviewer import icon
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from eotimeseriesviewer.timeseries import TimeSeries


# re-implementation of processingPlugin.executeAlgorithm(alg_id, parent, in_place=in_place, as_batch=as_batch)
# but with possibility to define the QgsProcessingContext
def executeAlgorithm(self,
                     alg_id,
                     parent: QWidget,
                     in_place: bool = False,
                     as_batch: bool = False,
                     context: Optional[QgsProcessingContext] = None,
                     iface: Optional[QgisInterface] = None
                     ):
    config = {}
    if in_place:
        config['IN_PLACE'] = True

    if iface is None:
        from qgis.utils import iface as qgisIface
        iface = qgisIface

    alg = QgsApplication.instance().processingRegistry().createAlgorithmById(alg_id, config)

    if alg is not None:

        ok, message = alg.canExecute()
        if not ok:
            dlg = MessageDialog()
            dlg.setTitle(self.tr('Error executing algorithm'))
            dlg.setMessage(
                self.tr('<h3>This algorithm cannot '
                        'be run :-( </h3>\n{0}').format(message))
            dlg.exec()
            return

        if as_batch:
            # dlg = BatchAlgorithmDialog(alg, iface.mainWindow())
            dlg = BatchAlgorithmDialog(alg, parent)
            dlg.show()
            dlg.exec()
        else:
            in_place_input_parameter_name = 'INPUT'
            if hasattr(alg, 'inputParameterName'):
                in_place_input_parameter_name = alg.inputParameterName()

            if in_place and not [d for d in alg.parameterDefinitions() if
                                 d.name() not in (in_place_input_parameter_name, 'OUTPUT')]:
                raise NotImplementedError()

                parameters = {}
                feedback = MessageBarProgress(algname=alg.displayName())
                ok, results = execute_in_place(alg, parameters, feedback=feedback)
                if ok:
                    iface.messageBar().pushSuccess('', self.tr('{algname} completed. %n feature(s) processed.',
                                                               n=results['__count']).format(algname=alg.displayName()))
                feedback.close()
                # MessageBarProgress handles errors
                return

            if alg.countVisibleParameters() > 0:
                dlg = alg.createCustomParametersWidget(parent)

                if not dlg:
                    dlg = AlgorithmDialog(alg, in_place, iface.mainWindow())
                canvas = iface.mapCanvas()
                prevMapTool = canvas.mapTool()
                dlg.show()
                dlg.exec()
                if canvas.mapTool() != prevMapTool:
                    try:
                        canvas.mapTool().reset()
                    except Exception:
                        pass
                    try:
                        canvas.setMapTool(prevMapTool)
                    except RuntimeError:
                        pass
            else:
                feedback = MessageBarProgress(algname=alg.displayName())
                context = dataobjects.createContext(feedback)
                parameters = {}
                ret, results = execute(alg, parameters, context, feedback)
                handleAlgorithmResults(alg, context, feedback)
                feedback.close()


class CreateEmptyTemporalProfileLayer(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    FIELD_NAME = 'FIELD_NAME'
    CRS = 'CRS'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def initAlgorithm(self, config: Dict = None):
        # self.addParameter(
        #    QgsProcessingParameterGeometry(
        #        self.GEOMETRY,
        #        description="Geometry Type",
        #        defaultValue=Qgis.GeometryType.Point,
        #        geometryTypes=[Qgis.GeometryType.Point]
        #    )
        # )

        p1 = QgsProcessingParameterCrs(
            self.CRS,
            description="Coordinate Reference System",
            defaultValue='EPSG:4326'
        )
        p1.setHelp('Coordinate Reference System for the output layer.')

        p2 = QgsProcessingParameterString(
            self.FIELD_NAME,
            description="Field Name",
            defaultValue="profiles")
        p2.setHelp(
            'Name of the field to store the temporal profiles. Profiles are stored either as JSON or as a string.')

        p3 = QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            description="Output Vector Layer",
            type=Qgis.ProcessingSourceType.VectorPoint,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT,
            createByDefault=True)
        p3.setHelp('Path of output vector.')

        for p in [p1, p2, p3]:
            self.addParameter(p)

    def processAlgorithm(self, parameters, context, feedback):
        # geom_type = self.parameterAsEnum(parameters, self.GEOMETRY, context)

        feedback.pushInfo(f"Parameters: {parameters}")
        geom_type = Qgis.WkbType.Point
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        field_name = self.parameterAsString(parameters, self.FIELD_NAME, context)

        fields = QgsFields()
        fields.append(TemporalProfileUtils.createProfileField(field_name))

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields=fields,
                                               geometryType=geom_type,
                                               crs=crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        sink.finalize()
        del sink
        lyr = QgsVectorLayer(dest_id)

        i = lyr.fields().indexFromName(field_name)
        lyr.setEditorWidgetSetup(i, TemporalProfileUtils.widgetSetup())
        lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return ReadTemporalProfiles()

    def name(self):
        return self.__class__.__name__.lower()

    def displayName(self):
        return "Creates Temporal Profile Layer"

    def group(self):
        return self._name

    def groupId(self):
        return self._groupID

    def shortHelpString(self):
        return "Create a new point layer with a field to store temporal profiles."


class AddTemporalProfileField(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    FIELD_NAME = 'FIELD_NAME'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def initAlgorithm(self, config: Dict = None):

        p1 = QgsProcessingParameterFeatureSink(
            self.INPUT,
            description="Vector Layer",
            type=Qgis.ProcessingSourceType.VectorPoint,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT,
            createByDefault=True)
        p1.setHelp('The vector Layer to append a field for temporal profiles.')

        p2 = QgsProcessingParameterString(
            self.FIELD_NAME,
            description="Field Name",
            defaultValue="profiles")
        p2.setHelp(
            'Name of the field to store temporal profiles.')

        for p in [p1, p2]:
            self.addParameter(p)

    def prepareAlgorithm(self, parameters: dict, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        field_name = self.parameterAsString(parameters, self.FIELD_NAME, context)
        lyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        if not (isinstance(lyr, QgsVectorLayer) and lyr.isValid()):
            feedback.pushError(f"Unable to open {parameters[self.INPUT]} as a vector layer.")
            return False

        if field_name in lyr.fields().names():
            feedback.pushInfo(f'Field "{field_name}" already exists.')
            return False

        return True

    def processAlgorithm(self, parameters, context, feedback):
        # geom_type = self.parameterAsEnum(parameters, self.GEOMETRY, context)

        field_name = self.parameterAsString(parameters, self.FIELD_NAME, context)
        lyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)

        with edit(lyr):
            lyr.addAttribute(TemporalProfileUtils.createProfileField(field_name))
        i = lyr.fields().indexFromName(field_name)
        lyr.setEditorWidgetSetup(i, TemporalProfileUtils.widgetSetup())
        lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)

        return {self.INPUT: lyr}

    def createInstance(self):
        return ReadTemporalProfiles()

    def name(self):
        return self.__class__.__name__.lower()

    def displayName(self):
        return "Add a field to store temporal profiles"

    def group(self):
        return self._name

    def groupId(self):
        return self._groupID

    def shortHelpString(self):
        return "Adds a field to store temporal profiles."


class ReadTemporalProfiles(QgsProcessingAlgorithm):
    INPUT = 'LAYER'
    TIMESERIES = 'TIMESERIES'
    FIELD_NAME = 'FIELD_NAME'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self._layer = None
        self._sources = []
        self._field_name = None

    def initAlgorithm(self, config: Dict = None):
        p1 = QgsProcessingParameterVectorLayer(
            self.INPUT,
            "Input Vector Layer",
            [QgsProcessing.TypeVectorPoint]
        )

        p2 = QgsProcessingParameterFile(
            self.TIMESERIES,
            description='Time Series',
            optional=True,
            defaultValue=None,
        )

        p3 = QgsProcessingParameterField(
            self.FIELD_NAME,
            description="Temporal Profile Field",
            parentLayerParameterName=self.INPUT,
            defaultValue='profiles',
            optional=True
        )

        for p in [p1, p2, p3]:
            self.addParameter(p)

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        input_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        time_series = self.parameterAsFile(parameters, self.TIMESERIES, context)
        profile_field = self.parameterAsStrings(parameters, self.FIELD_NAME, context)

        if not isinstance(input_layer, QgsVectorLayer) or not input_layer.isValid():
            feedback.pushError(f"Invalid input layer {parameters[self.INPUT]}")
            return False

        if not input_layer.wkbType() == Qgis.WkbType.Point:
            feedback.pushError(f"Input layer must be a point layer.")
            return False

        if not len(profile_field) == 1:
            feedback.pushError(f"Invalid field name {profile_field}")
            return False

        profile_field = profile_field[0]
        if profile_field in input_layer.fields().names():
            field = input_layer.fields()[profile_field]

            if not field.type() in [QMetaType.QString, QMetaType.QVariantMap]:
                feedback.pushError(f"Field {profile_field} does not support storing of temporal profiles.")
                return False

        sources = None
        if time_series in [None, '']:
            from eotimeseriesviewer.main import EOTimeSeriesViewer
            tsv = EOTimeSeriesViewer.instance()
            if isinstance(tsv, EOTimeSeriesViewer):
                sources = [s.source() for s in tsv.timeSeries().sources()]

        elif isinstance(time_series, str):
            sources = TimeSeries.sourcesFromFile(time_series)

        if not (isinstance(sources, list) and len(sources) > 0):
            feedback.pushError("No time series sources defined. Define CSV file with sources or "
                               "open EO Time Series Viewer with source files.")
            return False

        self._field_name = profile_field
        self._layer = input_layer
        self._sources = sources
        return True

    def processAlgorithm(self, parameters: dict, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> dict:

        # collect geometries
        crs = self._layer.crs()

        points = []
        fids = []
        for f in self._layer.getFeatures():
            fids.append(f.id())
            points.append(f.geometry().asPoint())
        n_threads = 4
        task = LoadTemporalProfileTask(self._sources,
                                       points,
                                       self._layer.crs(),
                                       n_threads=n_threads)

        def onProgress(progress: float):
            feedback.setProgress(progress)

        task.progressChanged.connect(onProgress)
        try:
            task.run()
        except Exception as ex:
            feedback.pushError(str(ex))
            return {}

        points, profiles = task.profilePoints(), task.profiles()

        s = ""

        return {self.INPUT: parameters[self.INPUT]}

    def createInstance(self):
        return ReadTemporalProfiles()

    def name(self):
        return "readtemporalprofiles"

    def displayName(self):
        return "Read Temporal Profiles"

    def group(self):
        return self._name

    def groupId(self):
        return self._groupID

    def shortHelpString(self):
        return "Adds a new field 'name' to the input vector layer and populates it with extracted temporal profiles."


class EOTSVProcessingProvider(QgsProcessingProvider):
    NAME = 'EOTimeSeriesViewer'

    _INSTANCE = None

    @staticmethod
    def instance() -> 'EOTSVProcessingProvider':
        if EOTSVProcessingProvider._INSTANCE is None:
            EOTSVProcessingProvider._INSTANCE = EOTSVProcessingProvider()
        return EOTSVProcessingProvider._INSTANCE

    @staticmethod
    def registerProvider() -> bool:
        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        provider = registry.providerById(EOTSVProcessingProvider.id())
        if not isinstance(provider, EOTSVProcessingProvider):
            return registry.addProvider(EOTSVProcessingProvider.instance())
        return True

    @staticmethod
    def unregisterProvider() -> bool:
        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        provider = registry.providerById(EOTSVProcessingProvider.id())
        if isinstance(provider, EOTSVProcessingProvider):
            if registry.removeProvider(provider):
                EOTSVProcessingProvider._INSTANCE = None
                return True
        return False

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._algs = []

    def load(self):
        self.refreshAlgorithms()
        return True

    def refreshAlgorithms(self):

        self._algs.clear()
        self._algs.extend([
            ReadTemporalProfiles(),
            CreateEmptyTemporalProfileLayer(),
            ReadTemporalProfiles(),
        ])
        s = ""

    def name(self):
        return self.NAME

    def longName(self):
        return self.NAME

    @classmethod
    def id(cls):
        return cls.NAME.lower()

    def helpId(self):
        return self.id()

    def icon(self) -> QIcon:
        return icon()

    def svgIconPath(self):
        return r':/qps/ui/icons/profile_expression.svg'

    def loadAlgorithms(self):
        for a in self._algs:
            self.addAlgorithm(a.createInstance())

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True

    def addAlgorithm(self, algorithm: QgsProcessingAlgorithm, **kwargs) -> bool:
        result = super().addAlgorithm(algorithm)
        if result:
            # keep a reference
            self._algs.append(algorithm)
        return result
