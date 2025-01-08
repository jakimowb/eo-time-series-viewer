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
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QItemSelectionModel, QModelIndex, QObject, QPoint, Qt
from qgis.PyQt.QtWidgets import QAction, QMenu, QProgressBar, QSlider, QTableView, QToolButton, QWidgetAction
from qgis.core import edit, QgsApplication, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsFeature, \
    QgsFeatureRequest, QgsFields, QgsProject, QgsTaskManager, QgsVectorDataProvider, QgsVectorLayer
from qgis.gui import QgsDockWidget, QgsFilterLineEdit
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from eotimeseriesviewer import DIR_UI
from .datetimeplot import DateTimePlotWidget
from .plotsettings import PlotSettingsProxyModel, PlotSettingsTreeModel, PlotSettingsTreeView, \
    PlotSettingsTreeViewDelegate, TPVisGroup
from .temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from ..qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from ..qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from ..qgispluginsupport.qps.utils import loadUi, SpatialPoint
from ..qgispluginsupport.qps.vectorlayertools import VectorLayerTools
from ..timeseries import SensorInstrument, TimeSeries

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
            self.menu.setTitle(self.name + " options..")

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

    def __init__(self,
                 treeView: PlotSettingsTreeView,
                 plotWidget: DateTimePlotWidget,
                 *args, **kwds):
        super().__init__(*args, **kwds)

        self.mTreeView = treeView
        self.mPlotWidget = plotWidget

        self.mModel = PlotSettingsTreeModel()
        self.mModel.setPlotWidget(self.mPlotWidget)
        self.mModel.itemChanged.connect(self.onStyleChanged)

        self.mProxyModel = PlotSettingsProxyModel()
        self.mProxyModel.setSourceModel(self.mModel)
        self.mTreeView.setModel(self.mProxyModel)
        self.mDelegate = PlotSettingsTreeViewDelegate(self.mTreeView)
        self.mTreeView.setItemDelegate(self.mDelegate)

        self.mLastStyle: dict = dict()
        self.mTasks: List[LoadTemporalProfileTask] = list()
        self.mIsInitialized: bool = False

    def temporalProfileDestination(self) -> Tuple[Optional[QgsVectorLayer], Optional[str]]:
        """
        Returns the destination for new added temporal profiles
        :return: QgsVectorLayer, field name (str)
        """

        for vis in self.mModel.visualizations():
            lyr = vis.layer()
            field = vis.field()

            if TemporalProfileUtils.isProfileLayer(lyr) and field in lyr.fields().names():
                f = lyr.fields()[field]
                if TemporalProfileUtils.isProfileField(f):
                    return lyr, field

        return None, None

    def loadTemporalProfile(self, point: SpatialPoint, run_async: bool = True) -> bool:
        """
        Starts the loading of a new temporal profile
        :param point: SpatialPoint
        :param run_async:
        :return:
        """
        assert isinstance(point, SpatialPoint)

        ts: TimeSeries = self.timeSeries()
        if not isinstance(ts, TimeSeries):
            return False

        lyr, field = self.temporalProfileDestination()
        if isinstance(lyr, QgsVectorLayer):
            f = QgsFeature(lyr.fields())
            # todo: settings?
            with edit(lyr):
                dp: QgsVectorDataProvider = lyr.dataProvider()
                result = dp.addFeature(f)
                s = ""

        self.mModel.mSettingsNode

        # create a new feature in the target layer

        task = LoadTemporalProfileTask(ts.sourceUris(), points=[point], crs=point.crs(),
                                       callback=self.onTemporalProfileLoaded)
        task.progressChanged.connect(self.loadingProgress)
        self.mTasks.append(task)
        if True:
            tm: QgsTaskManager = QgsApplication.instance().taskManager()
            tm.addTask(task)
        else:
            task.finished(task.run())
            s = ""
        s = ""

    def onTemporalProfileLoaded(self, success, task: LoadTemporalProfileTask):

        if success:
            # where should we add the profiles to?
            taskInfo = task.info()

            layer: QgsVectorLayer

            for pt, profiles in zip(task.profilePoints(), task.profiles()):
                s = ""
        s = ""

    def setFilter(self, filter: str):
        self.mProxyModel.setFilterWildcard(filter)

    def treeView(self) -> PlotSettingsTreeView:
        self.mTreeView

    def initVisualization(self, vis: TPVisGroup):
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
        for task in self.mTasks:
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
            print(f'STYLE CHANGE {args} {id(args[0])}')
            self.updatePlot(settings)

    def updatePlot(self, settings: dict = None):

        if settings is None:
            settings = self.mModel.settingsMap()

        print('# Update plot')
        pw = self.mPlotWidget
        #

        new_plotitems = []
        project = self.project()

        # collects information required to calculate the x and y values for each sensor
        # using use-defined expressions
        SENSOR_SPECS: Dict[str, Dict] = dict()

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

            layers.append(lyr)

            # prepare/compile sensor expressions
            # compiles the expressions that are used to calculate the x and y values

            request = QgsFeatureRequest()
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.globalScope())
            context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
            context.appendScope(QgsExpressionContextUtils.layerScope(lyr))
            request.setExpressionContext(context)

            filter_expression = vis.get('filter')
            if filter_expression and filter_expression != '':
                print(f'# SET FEATURE FILTER {filter_expression}')
                request.setFilterExpression(filter_expression)

            layer_line_style: PlotStyle = PlotStyle.fromMap(vis['line_style'])

            # LUT_SENSOR = {s['sensor_id']: s for s in vis['sensors']}
            selected_fids: List[int] = lyr.selectedFeatureIds()

            BAND_EXPRESSIONS = dict()
            SENSOR_VISUALS = dict()

            LABEL_EXPRESSION = QgsExpression(vis.get('label', lyr.displayExpression()))
            s = ""

            for feature in lyr.getFeatures(request):
                feature: QgsFeature

                feature_context = QgsExpressionContext(context)
                feature_context.setFeature(feature)

                attributeMap: dict = feature.attributeMap()
                tpData = TemporalProfileUtils.profileDict(attributeMap.get(vis_field))
                if not isinstance(tpData, dict):
                    continue

                # collect for each sensor some specifications that we need to calculate the x and y values
                for i_sid, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
                    if sid not in SENSOR_SPECS:
                        spec = TemporalProfileUtils.sensorSpecs(sid)
                        SENSOR_SPECS[sid] = spec
                        match = self.timeSeries().findMatchingSensor(sid)
                        if isinstance(match, SensorInstrument):
                            if match.id() not in SENSOR_SPECS:
                                SENSOR_SPECS[match.id()] = spec
                        for vis_sensor in vis['sensors']:
                            vsid = vis_sensor['sensor_id']
                            if vsid in [match.id(), sid]:
                                if vis_sensor['show']:
                                    prepared_expr, error = TemporalProfileUtils.prepareBandExpression(
                                        vis_sensor['expression'])
                                else:
                                    # skip values of this sensor
                                    prepared_expr = None

                                BAND_EXPRESSIONS[sid] = prepared_expr
                                BAND_EXPRESSIONS[vsid] = prepared_expr
                                BAND_EXPRESSIONS[match.id()] = prepared_expr
                                SENSOR_VISUALS[sid] = SENSOR_VISUALS[vsid] = SENSOR_VISUALS[match.id()] = vis_sensor

                        # get the expressions to calculate the x and y values for each sensor

                # get the x and y values to show
                try:
                    results = TemporalProfileUtils.applyExpressions(tpData, feature, BAND_EXPRESSIONS, SENSOR_SPECS)
                except Exception as ex:
                    print(ex, file=sys.stderr)
                    break

                n = results['n']
                all_x = results['x']
                all_y = results['y']

                all_symbols = np.empty(n, dtype=object)
                all_symbol_pens = np.empty(n, dtype=object)
                all_symbol_brushes = np.empty(n, dtype=object)
                all_symbol_sizes = np.empty(n, dtype=int)

                line_pen = pg.mkPen(color='b', width=2)

                for sid, is_sensor in results['sensor_indices'].items():
                    vis_sensor = SENSOR_VISUALS[sid]
                    if vis_sensor['show']:
                        symbol_style: PlotStyle = PlotStyle.fromMap(vis_sensor['symbol_style'])

                        all_symbols[is_sensor] = symbol_style.markerSymbol
                        all_symbol_pens[is_sensor] = QPen(symbol_style.markerPen)
                        all_symbol_brushes[is_sensor] = QBrush(symbol_style.markerBrush)
                        all_symbol_sizes[is_sensor] = symbol_style.markerSize

                # data = {'x': timestamps,
                #        'y': all_y.astype(float)}
                if np.any(np.isfinite(all_y)):
                    feature_line_style = layer_line_style.clone()
                    if feature.id() in selected_fids:
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
                            name = result

                    pdi = pg.PlotDataItem(all_x, all_y,
                                          pen=feature_line_style.linePen,
                                          name=name,
                                          symbol=all_symbols,
                                          symbolSize=all_symbol_sizes,
                                          symbolPen=all_symbol_pens,
                                          symbolBrush=all_symbol_brushes)
                    # pdi = DateTimePlotDataItem(data)

                    # Create a new plot item that uses one line
                    # color but different symbols for each sensor

                    new_plotitems.append(pdi)

        self.mPlotWidget.plotItem.clear()
        for item in new_plotitems:
            self.mPlotWidget.plotItem.addItem(item)

    def initPlot(self):

        # create a visualization for each temporal profile layer
        for lyr in TemporalProfileUtils.profileLayers(self.project()):
            fields: QgsFields = TemporalProfileUtils.profileFields(lyr)
            exampleData = None
            for feature in lyr.getFeatures():
                for exampleField in fields:
                    dump = TemporalProfileUtils.profileDict(feature[exampleField.name()])
                    if dump:
                        exampleData = dump
                        break
                if exampleData:
                    break
            vis = TPVisGroup()
            vis.setLayer(lyr)
            vis.setField(exampleField)

            if exampleData:
                sensor_ids = exampleData[TemporalProfileUtils.SensorIDs]

                ts = self.timeSeries()
                if ts:
                    sensors = []
                    for sid in sensor_ids:
                        match = ts.findMatchingSensor(sid)
                        if match:
                            if match not in sensors:
                                sensors.append(match)
                        elif sid not in sensors:
                            sensors.append(sid)
                else:
                    sensors = sensor_ids

                vis.addSensors(sensors)

            self.mModel.addVisualizations(vis)

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mModel.setTimeSeries(timeseries)

    def timeSeries(self) -> TimeSeries:
        return self.mModel.timeSeries()

    def project(self) -> QgsProject:
        return self.mModel.project()

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)
        self.mTreeView.setProject(project)

        if not self.mIsInitialized:
            self.initPlot()


class TemporalProfileDock(QgsDockWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        ui_path = DIR_UI / f'{self.__class__.__name__.lower()}.ui'
        loadUi(ui_path, self)

        self.mProject: QgsProject = QgsProject.instance()
        self.mPlotWidget: DateTimePlotWidget
        self.mTreeView: PlotSettingsTreeView

        self.mVis = TemporalProfileVisualization(self.mTreeView, self.mPlotWidget)
        self.mVis.loadingProgress.connect(self.setProgress)
        self.mLineEdit: QgsFilterLineEdit
        self.mLineEdit.valueChanged.connect(self.mVis.setFilter)

        self.actionRefreshPlot.triggered.connect(lambda: self.mVis.updatePlot())
        self.actionAddVisualization.triggered.connect(self.mVis.createVisualization)
        self.actionRemoveVisualization.triggered.connect(self.mVis.removeSelectedVisualizations)

    def setProgress(self, progress: float):
        btnCancelTask: QToolButton = self.btnCancelTask
        pBar: QProgressBar = self.mProgressBar
        progress = int(progress)
        canCancel = 0 < progress < 100
        pBar.setValue(int(progress))
        btnCancelTask.setEnabled(canCancel)

    def filterLineEdit(self) -> QgsFilterLineEdit:
        return self.mLineEdit

    def setProject(self, project: QgsProject):
        self.mVis.setProject(project)

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mVis.setTimeSeries(timeseries)

    def setVectorLayerTools(self, vectorLayerTools: VectorLayerTools):
        pass

    def loadTemporalProfile(self, point: SpatialPoint, run_async: bool = True):
        self.mVis.loadTemporalProfile(point, run_async=run_async)
