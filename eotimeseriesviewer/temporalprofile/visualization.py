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
import datetime
from typing import List

import numpy as np

from qgis.core import QgsFeature, QgsFeatureRequest, QgsFields, QgsProject, QgsVectorLayer
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QAbstractItemModel, QItemSelectionModel, \
    QModelIndex, QObject, QPoint, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMenu, \
    QSlider, QTableView, QWidgetAction
from eotimeseriesviewer import DIR_UI
from .datetimeplot import DateTimePlotDataItem, DateTimePlotWidget
from .plotsettings import PlotSettingsProxyModel, PlotSettingsTreeModel, PlotSettingsTreeView, \
    PlotSettingsTreeViewDelegate, TPVisGroup
from .temporalprofile import TemporalProfileUtils
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
            s = ""
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

        layers = []
        for i, vis in enumerate(settings['visualizations']):
            vis: dict
            if not vis.get('show', False):
                continue

            vis_layer = vis['layer']
            lyr = project.mapLayer(vis_layer['id'])
            if not isinstance(lyr, QgsVectorLayer):
                lyr = QgsVectorLayer(vis_layer['name'])

            if not isinstance(lyr, QgsVectorLayer):
                continue

            layers.append(lyr)

            request = QgsFeatureRequest()
            filter_expression = vis.get('filter')
            if filter_expression:
                request.setFilterExpression(filter_expression)
            vis_field = vis['field']

            LUT_SENSOR = {s['sensor_id']: s for s in vis['sensors']}

            for feature in lyr.getFeatures(request):
                feature: QgsFeature

                attributeMap = feature.attributeMap()
                tpData: dict = TemporalProfileUtils.profileDict(attributeMap[vis_field])

                n = len(tpData[TemporalProfileUtils.Values])

                y_values = []
                x_dates = tpData[TemporalProfileUtils.Date]
                colors = []
                markers = []

                all_sidx = np.asarray(tpData[TemporalProfileUtils.Sensor])
                all_value_list = tpData[TemporalProfileUtils.Values]
                all_dates = np.asarray(
                    [datetime.datetime.fromisoformat(d) for d in tpData[TemporalProfileUtils.Date]])
                # all_dates = np.asarray(range(n))

                all_show = np.ones((n,))

                all_x = all_dates.copy()
                all_y = np.empty(n, dtype=object)
                all_markers = np.empty(n, dtype=object)
                all_marker_pens = np.empty(n, dtype=object)

                # get the data to show
                for i_sid, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):

                    if sid not in LUT_SENSOR:
                        match = self.timeSeries().findMatchingSensor(sid)
                        if isinstance(match, SensorInstrument) and match.id() in LUT_SENSOR:
                            LUT_SENSOR[sid] = LUT_SENSOR[match.id()]

                    sensor_style = LUT_SENSOR.get(sid)
                    if not sensor_style:
                        # missing styling info. skip
                        continue

                    is_sensor = np.where(all_sidx == i_sid)[0]
                    if len(is_sensor) == 0:
                        continue

                    sensor_values = np.asarray([all_value_list[j] for j in is_sensor])
                    sensor_dates = all_dates[is_sensor]

                    sensor_expression = sensor_style.get('expression')
                    # todo: eval index expressions
                    # y = y * 3
                    # y = b('ndvi')
                    # y = b('ndvi') # return ndvi values
                    # y = b(1) # return values of 1st band
                    # x = x
                    sensor_y = sensor_values[:, 0]

                    all_x[is_sensor] = sensor_dates
                    all_y[is_sensor] = sensor_y

                timestamps = [d.timestamp() for d in all_x]
                data = {'x': timestamps,
                        'y': all_y.astype(float)}
                pdi = DateTimePlotDataItem(data)
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
