# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2017-08-04
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
import sys
import weakref
from itertools import chain
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QDateTime, QItemSelectionModel, QModelIndex, QObject, \
    QPoint, Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMenu, QProgressBar, QSlider, QTableView, QToolButton, QWidgetAction
from qgis.core import QgsApplication, QgsCoordinateTransform, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsFeature, QgsFeatureRequest, QgsField, QgsFields, QgsGeometry, QgsPointXY, QgsProject, \
    QgsTaskManager, QgsVectorLayer, QgsVectorLayerUtils
from qgis.gui import QgsDockWidget, QgsFilterLineEdit
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from .datetimeplot import DateTimePlotDataItem, DateTimePlotWidget
from .plotsettings import PlotSettingsProxyModel, PlotSettingsTreeModel, PlotSettingsTreeView, \
    PlotSettingsTreeViewDelegate, TPVisGroup
from .temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from ..qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from ..qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from ..qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkBrush, mkPen, PlotCurveItem
from ..qgispluginsupport.qps.pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent
from ..qgispluginsupport.qps.utils import loadUi, SpatialPoint
from ..qgispluginsupport.qps.vectorlayertools import VectorLayerTools
from ..sensors import SensorInstrument
from ..utils import addFeatures, doEdit

DEBUG = False
OPENGL_AVAILABLE = False
ENABLE_OPENGL = False

try:
    __import__('OpenGL')

    OPENGL_AVAILABLE = True

except ModuleNotFoundError as ex:
    print('unable to import OpenGL based packages:\n{}'.format(ex))


def getTextColorWithContrast(c):
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')


def selectedModelIndices(tableView):
    assert isinstance(tableView, QTableView)
    result = {}

    sm = tableView.selectionModel()
    m = tableView.model()
    if isinstance(sm, QItemSelectionModel) and isinstance(m, QAbstractItemModel):
        for idx in sm.selectedIndexes():
            assert isinstance(idx, QModelIndex)
            if idx.row() not in result.keys():
                result[idx.row()] = idx
    return result.values()


class _SensorPoints(pg.PlotDataItem):
    def __init__(self, *args, **kwds):
        super(_SensorPoints, self).__init__(*args, **kwds)
        # menu creation is deferred because it is expensive and often
        # the user will never see the menu anyway.
        self.menu = None

    def boundingRect(self):
        return super(_SensorPoints, self).boundingRect()

    def paint(self, p, *args):
        super(_SensorPoints, self).paint(p, *args)

    # On right-click, raise the context menu
    def mouseClickEvent(self, ev):
        if ev.button() == Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def getContextMenus(self, event=None):
        if self.menu is None:
            self.menu = QMenu()
            self.menu.setTitle(self.name() + " options..")

            green = QAction("Turn green", self.menu)
            green.triggered.connect(self.setGreen)
            self.menu.addAction(green)
            self.menu.green = green

            blue = QAction("Turn blue", self.menu)
            blue.triggered.connect(self.setBlue)
            self.menu.addAction(blue)
            self.menu.green = blue

            alpha = QWidgetAction(self.menu)
            alphaSlider = QSlider()
            alphaSlider.setOrientation(Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu


class TemporalProfileVisualization(QObject):
    loadingProgress = pyqtSignal(float)
    moveToDate = pyqtSignal(QDateTime, str)

    featureSelectionChanged = pyqtSignal(dict)

    def __init__(self,
                 treeView: PlotSettingsTreeView,
                 plotWidget: DateTimePlotWidget,
                 *args, **kwds):
        super().__init__(*args, **kwds)

        self.mTreeView = treeView
        self.mPlotWidget = plotWidget
        self.mPlotWidget.plotItem.vb.moveToDate.connect(self.moveToDate)
        self.mPlotWidget.preUpdateTask.connect(self.addPreUpdateTask)
        self.mPlotWidget.sigMapDateRequest.connect(self.moveToDate)
        # plotWidget.setBackground('white')
        self.mPreUpdateTasks = list()

        self.mModel = PlotSettingsTreeModel()
        self.mModel.setPlotWidget(self.mPlotWidget)
        self.mModel.itemChanged.connect(self.onStyleChanged)

        settingsActions = [
            self.mPlotWidget.dateTimeViewBox().mActionShowMapViewRange,
            self.mPlotWidget.dateTimeViewBox().mActionShowCrosshair,
            self.mPlotWidget.dateTimeViewBox().mActionShowCursorValues,
        ]
        # for a in settingsActions:
        #    self.mModel.mSettingsNode.createActionItem(a)

        self.mProxyModel = PlotSettingsProxyModel()
        self.mProxyModel.setSourceModel(self.mModel)
        self.mTreeView.setModel(self.mProxyModel)
        self.mDelegate = PlotSettingsTreeViewDelegate(self.mTreeView)
        self.mTreeView.setItemDelegate(self.mDelegate)

        self.mLastStyle: dict = dict()
        self.mTasks: List[LoadTemporalProfileTask] = list()
        self.mIsInitialized: bool = False

        self.mProfileCandidates: Dict[Tuple[str, str], List[int]] = dict()

        self.mSelectedFeatures: Dict[str, List[int]] = dict()

        self.mShowSelectedOnly = False

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.timeout.connect(self.preUpdates)
        self.mUpdateTimer.setInterval(1000)
        self.mUpdateTimer.start()

    def setShowSelectedOnly(self, show: bool):
        update = self.mShowSelectedOnly != show
        self.mShowSelectedOnly = show

        if update:
            self.updatePlot()

    def showSelectedOnly(self) -> bool:
        return self.mShowSelectedOnly

    def acceptCandidates(self):
        if len(self.mProfileCandidates) > 0:
            self.mProfileCandidates.clear()
            self.updatePlot()

    def profileCandidates(self) -> Dict[Tuple[str, str], List[int]]:
        return self.mProfileCandidates

    def temporalProfileLayerFields(self) -> List[Tuple[QgsVectorLayer, str]]:
        """
        Returns a list with all layer ids and field names which are used in
        profile visualizations
        :return:
        """
        results = []
        for vis in self.mModel.visualizations():
            lyr = vis.layer()
            field = vis.field()

            if TemporalProfileUtils.isProfileLayer(lyr) and field in lyr.fields().names():
                results.append((lyr, field))

        return results

    def loadTemporalProfile(self,
                            point: SpatialPoint,
                            run_async: bool = True,
                            layer: Optional[QgsVectorLayer] = None,
                            field: Optional[Union[str, QgsField]] = None) -> bool:
        """
        Starts the loading of a new temporal profile
        :param field: the field to add the temporal profile. Must be a temporal profile field
        :param layer: the QgsVectorLayer to add new temporal profile
        :param point: SpatialPoint
        :param run_async: bool, set True (default) to load the temporal profile using the QgsTaskManager
        :return: bool, True, if loading was started.
        """
        assert isinstance(point, SpatialPoint)

        ts: TimeSeries = self.timeSeries()
        if not isinstance(ts, TimeSeries):
            return False

        generalSettings = self.mModel.mSettingsNode.settingsMap()

        if not isinstance(layer, QgsVectorLayer):
            for (lyr, fn) in self.temporalProfileLayerFields():
                layer = lyr
                field = fn
                break

        if isinstance(field, QgsField):
            field = field.name()

        if not (isinstance(layer, QgsVectorLayer)
                and field in layer.fields().names()
                and TemporalProfileUtils.isProfileField(layer.fields()[field])):
            return False

        trans = QgsCoordinateTransform(point.crs(), layer.crs(), QgsProject.instance())
        if not trans.isValid():
            print(f'Unable to transform coordinates: {trans}', file=sys.stderr)
            return False
        point = point.toCrs(layer.crs())
        if not isinstance(point, SpatialPoint):
            return False

        # delete previous profile candidates / make them persistent
        k = (layer.id(), field)
        if not layer.isEditable():
            layer.startEditing()

        replace = True
        if replace:
            old_fids = self.mProfileCandidates.get(k, [])
            if len(old_fids) > 0:
                with doEdit(layer):
                    layer.deleteFeatures(old_fids)

        g = QgsGeometry.fromPointXY(point)
        attribute_map = dict()
        f = QgsVectorLayerUtils.createFeature(layer, geometry=g, attributes=attribute_map)

        # todo: settings? Edit graceful
        added_features = None
        with doEdit(layer):
            added_fids = addFeatures(layer, [f])
            added_features = list(layer.getFeatures(added_fids))

        if added_features:
            points = [QgsPointXY(f.geometry().asQPointF()) for f in added_features]
            fids = [f.id() for f in added_features]

            self.mProfileCandidates[k] = fids

            # create a new feature in the target layer
            taskInfo = {'fids': fids,
                        'lid': layer.id(),
                        'field': field,
                        }
            task = LoadTemporalProfileTask(ts.sourceUris(),
                                           points=points,
                                           crs=layer.crs(),
                                           n_threads=min(6, os.cpu_count(), ),
                                           info=taskInfo,
                                           description='Load temporal profiles',
                                           )
            task.executed.connect(self.onTemporalProfileLoaded)
            task.taskCompleted.connect(self.onTaskFinished)
            task.taskTerminated.connect(self.onTaskFinished)
            task.progressChanged.connect(self.loadingProgress)
            task.interimResults.connect(self.onInterimResults)
            self.mTasks.append(task)
            if run_async:
                tm: QgsTaskManager = QgsApplication.instance().taskManager()
                tid = tm.addTask(task)
            else:
                task.finished(task.run_serial())
        return True

    def onInterimResults(self, *args):

        s = ""

    def onTaskFinished(self):
        task = self.sender()

        if task in self.mTasks:
            self.mTasks.remove(task)

        self.loadingProgress.emit(0)

    def onTemporalProfileLoaded(self, success, results):
        task = self.sender()

        if not isinstance(task, LoadTemporalProfileTask):
            return
        if success:
            # where should we add the profiles to?
            taskInfo = task.info()
            lid = taskInfo.get('lid')
            field = taskInfo.get('field')
            fids = taskInfo.get('fids')

            any_change = False
            lyr = self.project().mapLayer(lid)
            if isinstance(lyr, QgsVectorLayer):
                with doEdit(lyr):
                    i_field = lyr.fields().lookupField(field)
                    if i_field >= 0:
                        all_fids = lyr.allFeatureIds()
                        for fid, profile in zip(fids, task.profiles()):
                            if fid in all_fids:
                                changed = lyr.changeAttributeValue(fid, i_field, profile)
                                if not changed:
                                    print(lyr.error())
                                    break
                                else:
                                    any_change = True
            if any_change:
                self.updatePlot()
        s = ""

    def setFilter(self, filter: str):
        self.mProxyModel.setFilterWildcard(filter)

    def treeView(self) -> PlotSettingsTreeView:
        self.mTreeView

    def initVisualization(self, vis: TPVisGroup):
        ts = self.timeSeries()
        if isinstance(ts, TimeSeries):
            vis.setTimeSeries(ts)

        vis.addSensors(self.timeSeries().sensors())

        is_initialized = TemporalProfileUtils.isProfileLayer(vis.layer())

        for v in reversed(self.mModel.visualizations()):
            lyr = v.layer()
            field = v.field()

            if (TemporalProfileUtils.isProfileLayer(lyr)
                    and field in lyr.fields().names()
                    and TemporalProfileUtils.isProfileField(lyr.fields()[field])):
                v.setLayer(lyr)
                v.setField(field)
                # other settings to copy?

                is_initialized = True
                break

        if not is_initialized:
            # take 1st temporal profile layer from project layers
            for lyr in self.project().mapLayers().values():
                if TemporalProfileUtils.isProfileLayer(lyr):
                    field = TemporalProfileUtils.profileFields(lyr).field(0)
                    vis.setLayer(lyr)
                    vis.setField(field)
                    is_initialized = True
                    break

    def cancelLoadingTask(self):
        for task in self.mTasks[:]:
            task.cancel()

    def createVisualization(self, *args) -> TPVisGroup:

        v = TPVisGroup()
        # append missing sensors

        self.initVisualization(v)

        self.mModel.addVisualizations(v)

        return v

    def selectedVisualizations(self) -> List[TPVisGroup]:
        """
        Returns the currently selected visualizations
        :return: list
        """
        indices = self.mTreeView.selectedIndexes()
        selected = []
        for idx in indices:
            item = idx.data(Qt.UserRole)
            if isinstance(item, TPVisGroup) and item not in selected:
                selected.append(item)
        return selected

    def removeSelectedVisualizations(self):

        to_remove = self.selectedVisualizations()
        if len(to_remove) > 0:
            self.mModel.removeVisualizations(to_remove)

    def onStyleChanged(self, *args):

        settings = self.mModel.settingsMap()
        if settings != self.mLastStyle:
            # print(f'STYLE CHANGE {args} {id(args[0])}')
            self.updatePlot(settings)
            # self.mLastStyle = settings

    def addPreUpdateTask(self, task_name: str, task_kwds: dict):

        self.mPreUpdateTasks.append((task_name, task_kwds))

    def preUpdates(self):
        """Handles task that need to be done before updatePlot()"""
        self.mUpdateTimer.stop()

        updates = self.mPreUpdateTasks[:]

        for update in updates:
            k, v = update
            if k == 'select_features':
                lyr = v.get('layer')
                fids = v.get('fids')
                if isinstance(lyr, QgsVectorLayer) and isinstance(fids, list):
                    lyr.selectByIds(fids)

            else:
                s = ""
            self.mPreUpdateTasks.remove(update)

        self.mUpdateTimer.start()

    def updatePlot(self, settings: dict = None):

        if settings is None:
            settings = self.mModel.settingsMap()

        # print('# Update plot')

        errors = dict()

        pw = self.mPlotWidget
        #
        cand_target_layer, cand_target_field = settings.get('candidates', {}).get('candidate_target', (None, None))
        cand_linestyle = settings.get('candidates', {}).get('candidate_line_style')
        if cand_linestyle is None:
            cand_linestyle = PlotStyle()
            cand_linestyle.setLineColor(QColor('green'))
            cand_linestyle.setLineWidth(3)
        elif isinstance(cand_linestyle, dict):
            cand_linestyle = PlotStyle.fromMap(cand_linestyle)

        assert isinstance(cand_linestyle, PlotStyle)

        new_plotitems = []
        project = self.project()
        PROFILE_CANDIDATES = self.profileCandidates()

        # collects information required to calculate the x and y values for each sensor
        # using use-defined expressions

        # Lookup for spensor specifications
        SENSOR_SPECS: Dict[str, Dict] = dict()

        selectedProfiles = dict()
        layers = []
        for i, vis in enumerate(settings['visualizations']):
            vis: dict
            if not vis.get('show', False):
                continue

            vis_layer = vis['layer']
            if not isinstance(vis_layer, dict):
                continue
            lyr = project.mapLayer(vis_layer['id'])
            if not isinstance(lyr, QgsVectorLayer):
                lyr = QgsVectorLayer(vis_layer['name'])

            if not isinstance(lyr, QgsVectorLayer):
                continue

            vis_field = vis['field']
            if vis_field not in lyr.fields().names():
                continue

            VIS_PROFILE_CANDIDATES: List[int] = PROFILE_CANDIDATES.get((lyr.id(), vis_field), [])
            layers.append(lyr)

            # prepare/compile sensor expressions
            # compiles the expressions that are used to calculate the x and y values

            request = QgsFeatureRequest()

            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.globalScope())
            context.appendScope(QgsExpressionContextUtils.projectScope(project))
            context.appendScope(QgsExpressionContextUtils.layerScope(lyr))
            request.setExpressionContext(context)

            if len(VIS_PROFILE_CANDIDATES) > 0:
                requestCandidates = QgsFeatureRequest()
                requestCandidates.setExpressionContext(QgsExpressionContext(context))
                requestCandidates.setFilterFids(VIS_PROFILE_CANDIDATES)
                candidateFeatures = lyr.getFeatures(requestCandidates)
            else:
                candidateFeatures = []

            filter_expression = vis.get('filter')
            if filter_expression and filter_expression != '':
                # print(f'# SET FEATURE FILTER {filter_expression}')
                request.setFilterExpression(filter_expression)

            layer_line_style: PlotStyle = PlotStyle.fromMap(vis['line_style'])

            # LUT_SENSOR = {s['sensor_id']: s for s in vis['sensors']}
            selected_fids: List[int] = lyr.selectedFeatureIds()
            if self.showSelectedOnly():
                request.setFilterFids(selected_fids)
                selected_fids.clear()

            BAND_EXPRESSIONS = dict()
            SENSOR_VISUALS = dict()

            LABEL_EXPRESSION = QgsExpression(vis.get('label', lyr.displayExpression()))
            s = ""

            fid_done = set()
            for feature in chain(candidateFeatures, lyr.getFeatures(request)):
                feature: QgsFeature
                is_candidate: bool = feature.id() in VIS_PROFILE_CANDIDATES
                if feature.id() in fid_done:
                    continue
                else:
                    fid_done.add(feature.id())

                feature_context = QgsExpressionContext(context)
                feature_context.setFeature(feature)

                attributeMap: dict = feature.attributeMap()
                tpData = TemporalProfileUtils.profileDict(attributeMap.get(vis_field))
                if not isinstance(tpData, dict):
                    continue

                missing_sensor_settings = []
                # collect for each sensor some specifications that we need to calculate the x and y values
                for i_sid, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
                    if sid not in SENSOR_SPECS:
                        spec = TemporalProfileUtils.sensorSpecs(sid)
                        SENSOR_SPECS[sid] = spec

                        # check if the same sensor is already known,
                        # e.g. with different name from the sensor panels
                        match = self.timeSeries().findMatchingSensor(sid)
                        if isinstance(match, SensorInstrument):
                            if match.id() not in SENSOR_SPECS:
                                SENSOR_SPECS[match.id()] = spec

                        requires_new_sensor_vis = True
                        for vis_sensor in vis['sensors']:
                            vis_sensor_id = vis_sensor['sensor_id']
                            if vis_sensor_id in SENSOR_SPECS:
                                if vis_sensor['show']:
                                    prepared_expr, error = TemporalProfileUtils.prepareBandExpression(
                                        vis_sensor['expression'])
                                else:
                                    # skip values of this sensor
                                    prepared_expr = None

                                BAND_EXPRESSIONS[sid] = prepared_expr
                                BAND_EXPRESSIONS[vis_sensor_id] = prepared_expr
                                SENSOR_VISUALS[sid] = vis_sensor
                                SENSOR_VISUALS[vis_sensor_id] = vis_sensor

                                if isinstance(match, SensorInstrument):
                                    BAND_EXPRESSIONS[match.id()] = prepared_expr
                                    SENSOR_VISUALS[match.id()] = vis_sensor

                                requires_new_sensor_vis = False

                        # no sensor visualization (e.g. plot styles etc.) found for this sensor?
                        if requires_new_sensor_vis:
                            missing_sensor_settings.append(sid)

                if len(missing_sensor_settings) > 0:
                    # stop here, add sensors to plot settings model and update again
                    missing_sensors = [SensorInstrument(s) for s in missing_sensor_settings]
                    self.mModel.addSensors(missing_sensors)
                    return

                # get the x and y values to show
                try:
                    results = TemporalProfileUtils.applyExpressions(tpData, feature, BAND_EXPRESSIONS, SENSOR_SPECS)
                except Exception as ex:
                    print(ex, file=sys.stderr)
                    break
                for e in results.get('errors', []):
                    errors[e] = errors.get(e, 0) + 1
                n = results['n']
                all_x = results['x']
                all_y = results['y']

                all_symbols = np.empty(n, dtype=object)
                all_symbol_pens = np.empty(n, dtype=object)
                all_symbol_brushes = np.empty(n, dtype=object)
                all_symbol_sizes = np.empty(n, dtype=int)

                # set the sensor-specific style vor the data values
                for sid, is_sensor in results['sensor_indices'].items():
                    vis_sensor = SENSOR_VISUALS[sid]
                    if vis_sensor['show'] or is_candidate:

                        symbol_style: PlotStyle = PlotStyle.fromMap(vis_sensor['symbol_style'])
                        if is_candidate:
                            symbol_style.setMarkerLinecolor(cand_linestyle.linePen.color())

                        all_symbols[is_sensor] = symbol_style.markerSymbol
                        all_symbol_pens[is_sensor] = mkPen(symbol_style.markerPen)
                        all_symbol_brushes[is_sensor] = mkBrush(symbol_style.markerBrush)
                        all_symbol_sizes[is_sensor] = symbol_style.markerSize

                # data = {'x': timestamps,
                #        'y': all_y.astype(float)}
                if np.any(np.isfinite(all_y)):
                    feature_line_style = layer_line_style.clone()
                    if is_candidate:
                        # style profile candidate
                        feature_line_style.setLinePen(cand_linestyle.linePen)
                    if feature.id() in selected_fids:
                        # style selected feature profiles
                        selectedProfiles[lyr.id()] = selectedProfiles.get(lyr.id(), []) + [feature.id()]
                        feature_line_style.setLineColor(QColor('yellow'))
                        feature_line_style.setLineWidth(layer_line_style.lineWidth() + 3)

                    name = None

                    if LABEL_EXPRESSION.isValid():
                        expr = QgsExpression(LABEL_EXPRESSION)
                        result = expr.evaluate(feature_context)
                        if expr.hasParserError():
                            s = ""
                        elif expr.hasEvalError():
                            s = ""
                        else:
                            if result is None:
                                name = None
                            else:
                                name = f'{result}'

                    pdi = DateTimePlotDataItem(all_x, all_y,
                                               pen=feature_line_style.linePen,
                                               name=name,
                                               symbol=all_symbols,
                                               symbolSize=all_symbol_sizes,
                                               symbolPen=all_symbol_pens,
                                               symbolBrush=all_symbol_brushes,
                                               hoverable=True,
                                               pxMode=True,
                                               )
                    # print(f'#PDI={pdi}')
                    pdi.setTemporalProfile(tpData, results['indices'])
                    pdi.curve.setClickable(True)
                    # pdi = DateTimePlotDataItem(data)
                    # pdi.setCurveClickable(True)
                    pdi.scatter.opts['hoverable'] = True
                    pdi.scatter.setData(hoverSize=all_symbol_sizes[0] + 2,
                                        hoverPen=mkPen('yellow'))
                    # pdi.scatter.opts['hoverSymbol'] = all_symbols
                    # pdi.scatter.opts['hoverSymbolSize'] = all_symbol_sizes + 2
                    # pdi.scatter.opts['hoverPen'] = QPen(QColor('yellow'))

                    pdi.scatter.opts['tip'] = None  # self.onTip
                    # pdi.scatter.setAcceptHoverEvents(True)
                    # pdi.curve.setToolTip('Foobar')
                    # pdi.setAcceptHoverEvents(True)
                    # Create a new plot item that uses one line
                    # color but different symbols for each sensor
                    # pdi.setAcceptHoverEvents(True)
                    # pdi.setAcceptHoverEvents(True)
                    # pdi.curve.setAcceptHoverEvents(True)
                    # pdi.setAcceptTouchEvents(True)
                    pdi.mLayer = weakref.ref(lyr)
                    pdi.mFeatureID = feature.id()
                    if is_candidate:
                        pdi.setZValue(999998)
                    # pdi.sigPointsClicked.connect(self.mPlotWidget.onPointsClicked)
                    # pdi.sigPointsHovered.connect(self.mPlotWidget.onPointsHovered)
                    # pdi.sigClicked.connect(self.mPlotWidget.onCurveClicked)
                    new_plotitems.append(pdi)

        self.mPlotWidget.plotItem.clearPlots()
        for item in new_plotitems:
            # item.scatter.sigHovered.connect(self.mPlotWidget.onPointsHovered)
            # item.scatter.sigClicked.connect(self.mPlotWidget.onPointsClicked)
            # item.sigClicked.connect(self.itemClicked)
            # item.sigPointsHovered.connect(self.pointsHovered)
            self.mPlotWidget.plotItem.addItem(item)

        self.setSelectedFeatures(selectedProfiles)

        if len(errors) > 0:
            info = ['TemporalProfile plotting errors:']
            for e, cnt in errors.items():
                info.append(f'{cnt}x: {e}')
            print('\n'.join(info), file=sys.stderr)

    def onTip(self, *args, **kwds) -> str:
        return None

    def setSelectedFeatures(self, selected_features: dict):

        if selected_features != self.mSelectedFeatures:
            self.mSelectedFeatures.clear()
            self.mSelectedFeatures.update(selected_features)
            self.featureSelectionChanged.emit(self.mSelectedFeatures)

    def selectedFeatures(self) -> dict:
        return self.mSelectedFeatures

    def __depr__itemClicked(self, item: Union[PlotCurveItem], event: MouseClickEvent):
        s = ""
        # print(f'Clicked {item}')

        pdi = None
        if isinstance(item, DateTimePlotDataItem):
            pdi = item

        if isinstance(item, PlotCurveItem) and isinstance(item.parentItem(), DateTimePlotDataItem):
            pdi = item.parentItem()

        if isinstance(pdi, DateTimePlotDataItem):
            s = ""
            lyr = pdi.mLayer()
            fid = pdi.mFeatureID

            if isinstance(lyr, QgsVectorLayer) and isinstance(fid, int):
                fids: list = lyr.selectedFeatureIds()
                if event.modifiers() & Qt.ControlModifier:
                    if fid in fids:
                        # remove from selection if already in
                        fids = [f for f in fids if f != fid]
                    else:
                        # add to selection
                        fids.append(fid)
                else:
                    fids = [fid]
                self.mPreUpdateTasks.append(
                    ('select_features', {'layer': lyr, 'fids': fids})
                )

                # lyr.selectByIds([fid])
            # select feature in layer
            event.accept()

    def initPlot(self):

        # create a visualization for each temporal profile layer
        for lyr in TemporalProfileUtils.profileLayers(self.project()):
            fields: QgsFields = TemporalProfileUtils.profileFields(lyr)
            exampleData = exampleField = None
            for feature in lyr.getFeatures():
                for exampleField in fields:
                    dump = TemporalProfileUtils.profileDict(feature[exampleField.name()])
                    if dump:
                        exampleData = dump
                        break
                if exampleData:
                    break
            vis = TPVisGroup()
            self.initVisualization(vis)

            if False:
                vis.setLayer(lyr)
                vis.setField(exampleField)
                vis.setTimeSeries(self.timeSeries())

                if exampleData:
                    sensor_ids = exampleData[TemporalProfileUtils.SensorIDs]

                    ts = self.timeSeries()
                    if ts:
                        sensors = []
                        for sid in sensor_ids:
                            match = ts.findMatchingSensor(sid)
                            if match:
                                if match.id() not in sensors:
                                    sensors.append(match.id())
                            elif sid not in sensors:
                                sensors.append(sid)
                        for sensor in ts.sensors():
                            if sensor.id() not in sensors:
                                sensors.append(sensor.id())
                    else:
                        sensors = sensor_ids

                    vis.addSensors(sensors)

            self.mModel.addVisualizations(vis)
            if len(self.mModel.visualizations()) > 0:
                try:
                    self.project().layersAdded.disconnect(self.initPlot)
                except Exception as ex:
                    pass
                self.updatePlot()

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mModel.setTimeSeries(timeseries)

    def timeSeries(self) -> TimeSeries:
        return self.mModel.timeSeries()

    def project(self) -> QgsProject:
        return self.mModel.project()

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)
        self.mTreeView.setProject(project)

        if len(self.mModel.visualizations()) == 0:
            project.layersAdded.connect(self.initPlot)

        if not self.mIsInitialized:
            self.initPlot()


class TemporalProfileDock(QgsDockWidget):
    sigMoveToDate = pyqtSignal(QDateTime, str)
    layerAttributeTableRequest = pyqtSignal(list)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        ui_path = DIR_UI / f'{self.__class__.__name__.lower()}.ui'
        loadUi(ui_path, self)

        self.mPlotWidget: DateTimePlotWidget
        self.mTreeView.layerAttributeTableRequest.connect(self.layerAttributeTableRequest)
        self.mTreeView.model()
        self.mVectorLayerTool: Optional[VectorLayerTools] = None

        self.mVis = TemporalProfileVisualization(self.mTreeView, self.mPlotWidget)
        self.mTreeView.selectionModel().selectionChanged.connect(self.updateActions)
        self.mVis.loadingProgress.connect(self.setProgress)
        self.mVis.moveToDate.connect(self.sigMoveToDate)
        self.mVis.featureSelectionChanged.connect(self.onFeatureSelectionChanged)
        self.mLineEdit: QgsFilterLineEdit
        self.mLineEdit.valueChanged.connect(self.mVis.setFilter)

        self.actionRefreshPlot.triggered.connect(lambda: self.mVis.updatePlot())
        self.actionAddVisualization.triggered.connect(self.mVis.createVisualization)
        self.actionRemoveVisualization.triggered.connect(self.mVis.removeSelectedVisualizations)
        self.actionAcceptCandidate.triggered.connect(self.mVis.acceptCandidates)
        self.actionDeselect.triggered.connect(self.deselect)
        self.actionPanToSelected.triggered.connect(self.panToSelected)
        self.actionZoomToSelected.triggered.connect(self.zoomToSelected)
        self.actionShowAttributeTable.setEnabled(False)
        self.actionShowAttributeTable.triggered.connect(
            lambda: self.layerAttributeTableRequest.emit(self.mTreeView.selectedLayers()))
        self.onFeatureSelectionChanged(dict())
        self.actionShowSelectedProfileOnly.toggled.connect(self.mVis.setShowSelectedOnly)

        self.btnCancelTask.clicked.connect(self.mVis.cancelLoadingTask)

    def updateActions(self):

        self.mTreeView.selectedLayers()
        b = len(self.mTreeView.selectedLayers())
        self.actionShowAttributeTable.setEnabled(b)

    def onFeatureSelectionChanged(self, selected_features: dict):
        has_selected = len(selected_features) > 0
        self.actionPanToSelected.setEnabled(has_selected)
        self.actionZoomToSelected.setEnabled(has_selected)
        self.actionDeselect.setEnabled(has_selected)

    def deselect(self):
        for lid, fids in self.mVis.selectedFeatures().copy().items():
            lyr = self.project().mapLayer(lid)
            if isinstance(lyr, QgsVectorLayer):
                new_selection = [fid for fid in lyr.selectedFeatureIds() if fid not in fids]
                lyr.selectByIds(new_selection)

    def panToSelected(self):
        if isinstance(self.mVectorLayerTool, VectorLayerTools):
            selected = self.mVis.selectedFeatures()
            for lid, fids in selected.items():
                lyr = self.project().mapLayer(lid)
                if isinstance(lyr, QgsVectorLayer) and len(fids) > 0:
                    self.mVectorLayerTool.panToFeatures(lyr, fids)

    def zoomToSelected(self):
        if isinstance(self.mVectorLayerTool, VectorLayerTools):
            selected = self.mVis.selectedFeatures()
            for lid, fids in selected.items():
                lyr = self.project().mapLayer(lid)
                if isinstance(lyr, QgsVectorLayer) and len(fids) > 0:
                    self.mVectorLayerTool.zoomToFeatures(lyr, fids)

    def setProgress(self, progress: float):
        btnCancelTask: QToolButton = self.btnCancelTask
        pBar: QProgressBar = self.mProgressBar
        progress = int(progress)
        canCancel = 0 < progress < 100
        pBar.setValue(int(progress))
        btnCancelTask.setEnabled(canCancel)
        if progress == 100:
            pBar.setValue(0)

    def filterLineEdit(self) -> QgsFilterLineEdit:
        return self.mLineEdit

    def setProject(self, project: QgsProject):
        self.mVis.setProject(project)

    def project(self) -> QgsProject:
        return self.mVis.project()

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mVis.setTimeSeries(timeseries)

    def setMapDateRange(self, d0: QDateTime, d1: QDateTime):
        self.mVis.mPlotWidget.setMapDateRange(d0, d1)

    def setVectorLayerTools(self, vectorLayerTools: VectorLayerTools):
        self.mVectorLayerTool = vectorLayerTools

    def loadTemporalProfile(self, *args, **kwds):
        self.mVis.loadTemporalProfile(*args, **kwds)
