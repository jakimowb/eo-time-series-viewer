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
from typing import Dict, List

import numpy as np

from qgis.core import QgsExpressionContext, QgsExpressionContextUtils, QgsFeature, QgsFeatureRequest, QgsFields, \
    QgsProject, QgsVectorLayer
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QAbstractItemModel, QItemSelectionModel, \
    QModelIndex, QObject, QPoint, Qt
from qgis.PyQt.QtWidgets import QAction, QMenu, \
    QSlider, QTableView, QWidgetAction
from eotimeseriesviewer import DIR_UI
from .datetimeplot import DateTimePlotWidget
from .plotsettings import PlotSettingsProxyModel, PlotSettingsTreeModel, PlotSettingsTreeView, \
    PlotSettingsTreeViewDelegate, TPVisGroup
from .temporalprofile import TemporalProfileUtils
from ..qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from ..qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from ..qgispluginsupport.qps.utils import loadUi
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

        self.mProject = QgsProject.instance()
        self.mIsInitialized: bool = False

    def treeView(self) -> PlotSettingsTreeView:
        self.mTreeView

    def createVisualization(self, *args) -> TPVisGroup:

        v = TPVisGroup()

        # append missing sensors
        v.addSensors(self.timeSeries().sensors())
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

            layers.append(lyr)

            # prepare/compile sensor expressions
            # compiles the expressions that are used to calculate the x and y values

            request = QgsFeatureRequest()
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.layerScope(lyr))
            request.setExpressionContext(context)

            filter_expression = vis.get('filter')
            if filter_expression and filter_expression != '':
                print(f'# SET FEATURE FILTER {filter_expression}')
                request.setFilterExpression(filter_expression)
            vis_field = vis['field']

            layer_line_style: PlotStyle = PlotStyle.fromMap(vis['line_style'])

            # LUT_SENSOR = {s['sensor_id']: s for s in vis['sensors']}
            selected_fids: List[int] = lyr.selectedFeatureIds()

            BAND_EXPRESSIONS = dict()
            SENSOR_VISUALS = dict()

            for feature in lyr.getFeatures(request):
                feature: QgsFeature

                attributeMap = feature.attributeMap()
                tpData: dict = TemporalProfileUtils.profileDict(attributeMap[vis_field])

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

                    pdi = pg.PlotDataItem(all_x, all_y,
                                          pen=feature_line_style.linePen,
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
        for lyr in TemporalProfileUtils.profileLayers(self.mProject):
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
        return self.mProject

    def setProject(self, project: QgsProject):
        self.mProject = project
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

        self.actionRefreshPlot.triggered.connect(lambda: self.mVis.updatePlot())
        self.actionAddVisualization.triggered.connect(self.mVis.createVisualization)
        self.actionRemoveVisualization.triggered.connect(self.mVis.removeSelectedVisualizations)

    def setProject(self, project: QgsProject):
        self.mVis.setProject(project)

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mVis.setTimeSeries(timeseries)

    def setVectorLayerTools(self, vectorLayerTools: VectorLayerTools):
        pass
