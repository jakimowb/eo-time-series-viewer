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
from typing import Dict

from qgis._core import QgsFields

from qgis.gui import QgsDockWidget
from qgis.core import QgsProject
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QItemSelectionModel, \
    QModelIndex, QObject, QPoint, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMenu, \
    QSlider, QTableView, QWidgetAction
from eotimeseriesviewer import DIR_UI
from .datetimeplot import DateTimePlotWidget
from .plotsettings import PlotSettingsProxyModel, PlotSettingsTreeModel, PlotSettingsTreeView, \
    TPVisGroup
from .plotstyle import TemporalProfilePlotStyle
from .temporalprofile import TemporalProfileUtils
from ..qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from ..qgispluginsupport.qps.utils import loadUi
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


class MultiSensorProfileStyle(QObject):
    """
    PlotStyle for a multi-sensor temporal profile
    Allows to define different PlotStyles for each sensor.
    """
    sigStyleUpdated = pyqtSignal()

    @staticmethod
    def defaultSensorStyle(sensor: SensorInstrument) -> TemporalProfilePlotStyle:
        style = TemporalProfilePlotStyle()
        style.setSensor(sensor)
        # todo: use last settings
        return style

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mSensorStyles: Dict[str, TemporalProfilePlotStyle] = dict()

    def setSensorStyle(self,
                       sensorID: str,
                       style=None,
                       expression: str = '@b1'):
        if style is None:
            style = self.defaultSensorStyle()

        self.mSensorStyles[sensorID] = style


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

        self.mProxyModel = PlotSettingsProxyModel()
        self.mProxyModel.setSourceModel(self.mModel)
        self.mTreeView.setModel(self.mProxyModel)
        # self.mDelegate = PlotSettingsTreeViewDelegate(self.mTreeView)
        # self.mTreeView.setItemDelegate(self.mDelegate)

        self.mProject = QgsProject.instance()
        self.mIsInitialized: bool = False
        self.mTimeSeries: TimeSeries = None

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
                sensors = exampleData[TemporalProfileUtils.SensorIDs]
                vis.addSensors(sensors)

            self.mModel.addVisualization(vis)

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mTimeSeries = timeseries

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

    def setProject(self, project: QgsProject):
        self.mVis.setProject(project)

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mVis.setTimeSeries(timeseries)
