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
import re
import sys
import warnings
from typing import Dict, Iterator, List, Optional, Union

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot, QAbstractItemModel, QAbstractTableModel, QItemSelectionModel, \
    QModelIndex, QObject, QPoint, QPointF, QSize, QSortFilterProxyModel, Qt, QTimer
from qgis.core import edit, QgsAttributeTableConfig, QgsCoordinateReferenceSystem, QgsError, QgsExpression, \
    QgsExpressionContext, QgsExpressionContextGenerator, QgsExpressionContextScope, QgsExpressionContextUtils, \
    QgsFeature, QgsGeometry, QgsMapLayerProxyModel, QgsPoint, QgsVectorLayer
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QCursor, QPainter, QPalette, QPen
from qgis.PyQt.QtWidgets import QAction, QDateEdit, QDialog, QFrame, QGridLayout, QHeaderView, QLabel, QMenu, \
    QRadioButton, QSlider, QStyledItemDelegate, QTableView, QToolBar, QWidget, QWidgetAction
from qgis.gui import QgsDockWidget, QgsFieldExpressionWidget
from eotimeseriesviewer import DIR_UI
from .profilefunctions import ProfileValueExpressionFunction
from .qgispluginsupport.qps.layerproperties import AttributeTableWidget
from .qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle, PlotStyleButton, PlotStyleDialog
from .qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from .qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen, ScatterPlotItem, SpotItem
from .qgispluginsupport.qps.pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent
from .qgispluginsupport.qps.utils import loadUi, nextColor, SelectMapLayersDialog, SpatialPoint
from .qgispluginsupport.qps.vectorlayertools import VectorLayerTools
from .temporalprofiles import bandIndex2bandKey, bandKey2bandIndex, date2num, dateDOY, LABEL_EXPRESSION_2D, \
    LABEL_TIME, num2date, rxBandKey, TemporalProfile, TemporalProfileLayer
from .temporalprofileV2 import LoadTemporalProfileTask, TemporalProfileUtils
from .timeseries import SensorInstrument, TimeSeries, TimeSeriesDate

# noinspection PyPep8Naming

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


class TemporalProfilePlotStyle(PlotStyle):
    """
    Describes the PLotStyle for data of a single sensor.
    """
    sigStyleUpdated = pyqtSignal()

    def __init__(self, parent=None):
        super(TemporalProfilePlotStyle, self).__init__()
        self.mSensor: SensorInstrument = None
        self.mExpression: str = f'{ProfileValueExpressionFunction.NAME}(1)'
        self.mIsVisible: bool = True
        self.mShowLastLocation: bool = True

    def __hash__(self):
        return hash(id(self))

    def showLastLocation(self) -> bool:
        """
        """
        return self.mShowLastLocation

    def createPlotItem(self):
        raise NotImplementedError()

    def setSensor(self, sensor: SensorInstrument):
        assert sensor is None or isinstance(sensor, SensorInstrument)
        b = sensor != self.mSensor
        self.mSensor = sensor

    def sensor(self) -> SensorInstrument:
        return self.mSensor

    def setExpression(self, exp: str):
        assert isinstance(exp, str)
        b = self.mExpression != exp
        self.mExpression = exp

    def expression(self) -> str:
        return self.mExpression

    def expressionBandIndices(self) -> List[int]:
        return [bandKey2bandIndex(k) for k in self.expressionBandKeys()]

    def expressionBandKeys(self) -> List[str]:
        """
        Returns a list of image data bands
        """
        return sorted(set(rxBandKey.findall(self.expression())))

    def isVisible(self):
        return self.mIsVisible

    def setVisibility(self, b):
        assert isinstance(b, bool)
        old = self.isVisible()
        self.mIsVisible = b

    def copyFrom(self, plotStyle):
        if isinstance(plotStyle, PlotStyle):
            super(TemporalProfilePlotStyle, self).copyFrom(plotStyle)

        if isinstance(plotStyle, TemporalProfilePlotStyle):
            self.setExpression(plotStyle.expression())
            self.setSensor(plotStyle.sensor())


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


class TemporalProfilePlotDataItem(pg.PlotDataItem):

    def __init__(self, plotStyle: TemporalProfilePlotStyle, parent=None):
        assert isinstance(plotStyle, TemporalProfilePlotStyle)

        super(TemporalProfilePlotDataItem, self).__init__([], [], parent=parent)
        self.menu: QMenu = None
        # self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.mPlotStyle: TemporalProfilePlotStyle = plotStyle
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.mPlotStyle.sigUpdated.connect(self.updateDataAndStyle)
        self.updateDataAndStyle()

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

    def updateDataAndStyle(self):
        TP = self.mPlotStyle.temporalProfile()
        sensor = self.mPlotStyle.sensor()

        if isinstance(TP, TemporalProfile) and isinstance(sensor, SensorInstrument):
            x, y = TP.dataFromExpression(self.mPlotStyle.sensor(), self.mPlotStyle.expression(), dateType='date')

            if True:
                # handle failed removal of NaN
                # see https://github.com/pyqtgraph/pyqtgraph/issues/1057
                if not isinstance(y, np.ndarray):
                    y = np.asarray(y, dtype=float)
                if not isinstance(x, np.ndarray):
                    x = np.asarray(x)

                is_finite = np.isfinite(y)
                connected = np.logical_and(is_finite, np.roll(is_finite, -1))
                keep = is_finite + connected
                # y[np.logical_not(is_finite)] = np.nanmin(y)
                y = y[keep]
                x = x[keep]
                connected = connected[keep]
                self.setData(x=x, y=y, connect=connected)
            else:
                self.setData(x=x, y=y, connect='finite')

        else:
            self.setData(x=[], y=[])  # dummy for empty data
        self.updateStyle()

    def updateStyle(self):
        """
        Updates visibility properties
        """
        self.setVisible(self.mPlotStyle.isVisible())
        self.setSymbol(self.mPlotStyle.markerSymbol)
        self.setSymbolSize(self.mPlotStyle.markerSize)
        self.setSymbolBrush(self.mPlotStyle.markerBrush)
        self.setSymbolPen(self.mPlotStyle.markerPen)
        self.setPen(self.mPlotStyle.linePen)
        self.update()

    def setClickable(self, b, width=None):
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setColor(self, color):
        if not isinstance(color, QColor):
            color = QColor(color)
        self.setPen(color)

    def pen(self):
        return mkPen(self.opts['pen'])

    def color(self):
        return self.pen().color()

    def setLineWidth(self, width):
        pen = pg.mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)


class PlotSettingsModel(QAbstractTableModel):
    cSensor = 0
    cExpression = 1
    cStyle = 2

    def __init__(self, temporalProfileLayer: QgsVectorLayer, timeSeries: TimeSeries, parent=None, *args):
        assert isinstance(temporalProfileLayer, QgsVectorLayer)
        super(PlotSettingsModel, self).__init__(parent=parent)

        # self.mTemporalProfileLayer.featureAdded.connect(self.onTemporalProfilesAdded)
        # self.mTemporalProfileLayer.featuresDeleted.connect(self.onTemporalProfilesDeleted)
        # self.mTemporalProfileLayer.sigTemporalProfilesUpdated.connect(self.onTemporalProfilesUpdated)
        self.columnNames = {self.cSensor: 'Sensor',
                            self.cExpression: 'Expression',
                            self.cStyle: 'Style'}

        self.mPlotStyles: List[TemporalProfilePlotStyle] = []
        self.mIconSize = QSize(25, 25)
        self.mTemporalProfileLayer: Optional[QgsVectorLayer] = None
        self.mTimeSeries: Optional[TimeSeries] = None

        if timeSeries:
            self.setTimeSeries(timeSeries)

        if temporalProfileLayer:
            self.setTemporalProfileLayer(temporalProfileLayer)

    def setTemporalProfileLayer(self, layer: QgsVectorLayer):
        self.mTemporalProfileLayer = layer

    def setTimeSeries(self, timeSeries: TimeSeries):

        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensors)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensors)
        self.addSensors(timeSeries.sensors())

    def addSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):
        """
        Create a new plotstyle for this sensor
        :param sensor:
        :return:
        """

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        sensors = [s for s in sensors if s.id() not in self.sensorIds()]

        if len(sensors) == 0:
            return

        styles = [MultiSensorProfileStyle.defaultSensorStyle(s) for s in sensors]
        parent = QModelIndex()
        row0 = len(self.mPlotStyles)
        rowN = row0 + len(styles) - 1
        self.beginInsertRows(parent, row0, rowN)
        self.mPlotStyles.extend(styles)
        self.endInsertRows()

    def sensorIds(self) -> List[str]:
        """
        Returns the sensor ids for which plot styles exists
        :return:
        """
        return [s.sensor().id() for s in self.mPlotStyles]

    def removeSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        sensors = [s for s in sensors if s.id() in self.sensorIds()]
        for sensor in sensors:
            sid = sensor.id()
            while sid in (sids := self.sensorIds()):
                row = sids.index(sid)
                parent = QModelIndex()
                self.beginRemoveRows(parent, row, row)
                self.mTemporalProfileLayer.remove(row)
                self.endRemoveRows()

    def multiSensorProfilePlotStyle(self) -> MultiSensorProfileStyle:

        style = MultiSensorProfileStyle()
        for tp in self.temporalProfileStyles():
            style.setSensorStyle(tp.sensor().id(), tp)
        return style

    def timeSeries(self) -> TimeSeries:
        return self.mTimeSeries

    def temporalProfileLayer(self) -> QgsVectorLayer:
        return self.mTemporalProfileLayer

    def temporalProfileStyles(self) -> List[TemporalProfilePlotStyle]:
        return self.mPlotStyles[:]

    def __len__(self):
        return len(self.mPlotStyles)

    def __iter__(self) -> Iterator[TemporalProfilePlotStyle]:
        return iter(self.mPlotStyles)

    def __getitem__(self, slice):
        return self.mPlotStyles[slice]

    def __contains__(self, item):
        return item in self.mPlotStyles

    def columnIndex(self, name: str) -> int:
        return self.columnNames.index(name)

    def onStyleUpdated(self, style: TemporalProfilePlotStyle):

        idx = self.plotStyle2idx(style)
        r = idx.row()
        self.dataChanged.emit(self.createIndex(r, 0), self.createIndex(r, self.columnCount()))

    def depr_createNewPlotStyle2D(self) -> TemporalProfilePlotStyle:
        plotStyle = TemporalProfilePlotStyle()

        sensors = self.timeSeries().sensors()
        if len(sensors) > 0:
            plotStyle.setSensor(sensors[0])

        # if len(self.mTemporalProfileLayer) > 0:
        #    temporalProfile = self.mTemporalProfileLayer[0]
        #    plotStyle.setTemporalProfile(temporalProfile)

        if len(self) > 0:
            lastStyle = self[0]  # top style in list is the most-recent
            assert isinstance(lastStyle, TemporalProfilePlotStyle)
            markerColor = nextColor(lastStyle.markerBrush.color())
            plotStyle.markerBrush.setColor(markerColor)
        return plotStyle

    def rowCount(self, parent=QModelIndex()):
        return len(self.mPlotStyles)

    def plotStyle2idx(self, plotStyle):

        assert isinstance(plotStyle, TemporalProfilePlotStyle)

        if plotStyle in self.mPlotStyles:
            i = self.mPlotStyles.index(plotStyle)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()

    def idx2plotStyle(self, index) -> TemporalProfilePlotStyle:
        if index.isValid() and index.row() < self.rowCount():
            return self.mPlotStyles[index.row()]
        return None

    def columnCount(self, parent=QModelIndex()):
        return len(self.columnNames)

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        return self.createIndex(row, column, self.mPlotStyles[row])

    def data(self, index: QModelIndex, role: Qt.ItemDataRole):
        if not index.isValid():
            return None

        col = index.column()

        plotStyle: TemporalProfilePlotStyle = self.mPlotStyles[index.row()]

        if isinstance(plotStyle, TemporalProfilePlotStyle):
            sensor = plotStyle.sensor()

            if role == Qt.DisplayRole:
                if col == self.cSensor:
                    if isinstance(sensor, SensorInstrument):
                        return sensor.name()
                    else:
                        return '<Select Sensor>'
                elif col == self.cExpression:
                    return plotStyle.expression()

            elif role == Qt.CheckStateRole:
                if col == self.cSensor:
                    return Qt.Checked if plotStyle.isVisible() else Qt.Unchecked

            elif role == Qt.UserRole:
                return plotStyle
        return None

    def setData(self, index, value, role=None) -> bool:
        if not index.isValid():
            return False

        col = index.column()

        result = False
        plotStyle: TemporalProfilePlotStyle = index.data(Qt.UserRole)

        if isinstance(plotStyle, TemporalProfilePlotStyle):
            if role == Qt.CheckStateRole:
                if col == self.cSensor:
                    plotStyle.setVisibility(value == Qt.Checked)
                    result = True

            if role == Qt.EditRole:
                if col == self.cExpression:
                    plotStyle.setExpression(value)
                    result = True

                elif col == self.cStyle:
                    plotStyle.copyFrom(value)
                    result = True

                elif col == self.cSensor:
                    plotStyle.setSensor(value)
                    result = True

        if result:
            # self.savePlotSettings(plotStyle, index='DEFAULT')
            self.dataChanged.emit(index, index, [role, Qt.DisplayRole])

        return result

    def savePlotSettings(self, sensorPlotSettings, index='DEFAULT'):
        return

    def restorePlotSettings(self, sensor, index='DEFAULT'):
        return None

    def checkForRequiredDataUpdates(self, profileStyles: List[TemporalProfilePlotStyle]):
        if not isinstance(profileStyles, list):
            profileStyles = [profileStyles]

        if not isinstance(self.temporalProfileLayer(), TemporalProfileLayer):
            return

        SENSOR_BANDS = dict()
        temporal_profiles = set()
        for ps in profileStyles:
            assert isinstance(ps, TemporalProfilePlotStyle)
            sensor = ps.sensor()
            tp = ps.temporalProfile()
            band_indicies = ps.expressionBandIndices()
            band_indicies = [i for i in band_indicies if i >= 0 and i < sensor.nb]
            if isinstance(sensor, SensorInstrument) and isinstance(tp, TemporalProfile) and len(band_indicies) > 0:
                temporal_profiles.add(tp)
                if sensor not in SENSOR_BANDS.keys():
                    SENSOR_BANDS[sensor] = set()
                SENSOR_BANDS[sensor].update(band_indicies)

        self.temporalProfileLayer().loadMissingBandInfos(temporal_profiles, SENSOR_BANDS)

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if c in [self.cSensor]:
                flags = flags | Qt.ItemIsUserCheckable
            if c in [self.cExpression, self.cStyle]:  # allow check state
                flags = flags | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(col)
        return None


class PlotSettingsTableView(QTableView):

    def __init__(self, *args, **kwds):
        super(PlotSettingsTableView, self).__init__(*args, **kwds)

        pal = self.palette()
        cSelected = pal.color(QPalette.Active, QPalette.Highlight)
        pal.setColor(QPalette.Inactive, QPalette.Highlight, cSelected)
        self.setPalette(pal)

    def sensorHasWavelengths(self, sensor: SensorInstrument) -> bool:
        return isinstance(sensor, SensorInstrument) and \
            sensor.wl is not None and \
            len(sensor.wl) > 0

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        indices = self.selectionModel().selectedIndexes()

        if len(indices) > 0:
            refIndex = indices[0]
            assert isinstance(refIndex, QModelIndex)
            refPlotStyle = refIndex.data(Qt.UserRole)

            assert isinstance(refPlotStyle, TemporalProfilePlotStyle)
            refSensor = refPlotStyle.sensor()
            menu = QMenu(self)
            menu.setToolTipsVisible(True)

            a = menu.addAction('Set Style')
            a.triggered.connect(lambda *args, i=indices: self.onSetStyle(i))
            from .utils import LUT_WAVELENGTH

            has_wavelength = self.sensorHasWavelengths(refSensor)

            m = menu.addMenu('Set Band...')
            m.setEnabled(has_wavelength)

            a = m.addAction('Blue Band')
            a.setToolTip('Show values of blue band (band closest to {} nm'.format(LUT_WAVELENGTH['B']))
            a.triggered.connect(lambda *args, exp='<B>':
                                self.onSetExpression(exp))

            a = m.addAction('Green Band')
            a.setToolTip('Show values of green band (band closest to {} nm'.format(LUT_WAVELENGTH['G']))
            a.triggered.connect(lambda *args, exp='<G>':
                                self.onSetExpression(exp))

            a = m.addAction('Red Band')
            a.setToolTip('Show values of red band (band closest to {} nm'.format(LUT_WAVELENGTH['R']))
            a.triggered.connect(lambda *args, exp='<R>':
                                self.onSetExpression(exp))

            a = m.addAction('NIR Band')
            a.setToolTip('Show values of red band (band closest to {} nm'.format(LUT_WAVELENGTH['NIR']))
            a.setToolTip('Show values of Near Infrared (NIR) band')
            a.triggered.connect(lambda *args, exp='<NIR>':
                                self.onSetExpression(exp))

            a = m.addAction('SWIR1 Band')
            a.setToolTip('Show values of SWIR 1 band (band closest to {} nm'.format(LUT_WAVELENGTH['SWIR1']))
            a.triggered.connect(lambda *args, exp='<SWIR1>':
                                self.onSetExpression(exp))

            a = m.addAction('SWIR2 Band')
            a.setToolTip('Show values of SWIR 2 band (band closest to {} nm'.format(LUT_WAVELENGTH['SWIR2']))
            a.triggered.connect(lambda *args, exp='<SWIR2>':
                                self.onSetExpression(exp))

            m = menu.addMenu('Set Index...')

            a = m.addAction('NDVI')
            a.setToolTip('Calculate the Normalized Difference Vegetation Index (NDVI)')
            a.triggered.connect(lambda *args, exp='(<NIR>-<R>)/(<NIR>+<R>)': self.onSetExpression(exp))

            a = m.addAction('NDMI')
            a.setToolTip('Calculate the Normalized Difference Moisture Index (NDMI)')
            a.triggered.connect(lambda *args, exp='(<NIR>-<SWIR1>)/(<NIR>+<SWIR1>)':
                                self.onSetExpression(exp))

            a = m.addAction('NBR')
            a.setToolTip('Calculate the Normalized Burn Ratio (NBR)')
            a.triggered.connect(lambda *args, exp='(<NIR>-<SWIR2>)/(<NIR>+<SWIR2>)':
                                self.onSetExpression(exp))

            a = m.addAction('NBR 2')
            a.setToolTip('Calculate the Normalized Burn Ratio between two SWIR bands (NBR2)')
            a.triggered.connect(lambda *args, exp='(<SWIR1>-<SWIR2>)/(<SWIR1>+<SWIR2>)':
                                self.onSetExpression(exp))

            menu.popup(QCursor.pos())

    def onSetExpression(self, expr: str):
        rows = set()
        for idx in self.selectionModel().selectedIndexes():
            if idx.isValid():
                rows.add(idx.row())

        assert isinstance(expr, str)

        m = self.plotSettingsModel()
        for col in range(self.model().columnCount()):
            if self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole) == m.cnExpression:
                break

        for row in rows:
            idx = self.model().index(row, col)
            plotStyle = idx.data(Qt.UserRole)
            if not isinstance(plotStyle, TemporalProfilePlotStyle):
                continue

            sensor = plotStyle.sensor()
            if not (isinstance(sensor, SensorInstrument) and self.sensorHasWavelengths(sensor)):
                continue

            expr2 = expr[:]
            replacements = dict()
            for match in re.findall(r'<[^>]+>', expr2):
                s = ""
                wl = match[1:-1]
                bandKey = bandIndex2bandKey(sensor.bandIndexClosestToWavelength(wl))
                replacements[match] = '"{}"'.format(bandKey)
            for k, v in replacements.items():
                expr2 = expr2.replace(k, v)

            if '<' not in expr2:
                self.model().setData(idx, expr2, Qt.EditRole)

    def plotSettingsModel(self) -> PlotSettingsModel:
        return self.model().sourceModel()

    def onSetStyle(self, indices):

        m = self.plotSettingsModel()
        for col in range(self.model().columnCount()):
            if self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole) == m.cnStyle:
                break

        if len(indices) > 0:
            refStyle = indices[0].data(Qt.UserRole)
            assert isinstance(refStyle, TemporalProfilePlotStyle)
            newStyle = PlotStyleDialog.getPlotStyle(plotStyle=refStyle)
            if isinstance(newStyle, PlotStyle):
                for idx in indices:
                    assert isinstance(idx, QModelIndex)
                    idx2 = self.model().index(idx.row(), col)
                    self.model().setData(idx2, newStyle, role=Qt.EditRole)


class PlotSettingsContextGenerator(QgsExpressionContextGenerator):
    mFunc = ProfileValueExpressionFunction()
    QgsExpression.registerFunction(mFunc)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mLayer = None

    def setLayer(self, layer: QgsVectorLayer):
        self.mLayer = layer

    def setDate(self):
        pass

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()
        if isinstance(self.mLayer, QgsVectorLayer):
            context.appendScope(QgsExpressionContextUtils.layerScope(self.mLayer))

        dateScope = QgsExpressionContextScope('date')
        var = QgsExpressionContextScope.StaticVariable('date')
        var.value = 'today'
        dateScope.addVariable(var)
        dateScope.addFunction(self.mFunc.name(), self.mFunc.clone())
        context.appendScope(dateScope)
        return context


class PlotSettingsTableViewWidgetDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, tableView, parent=None):
        assert isinstance(tableView, PlotSettingsTableView)
        super(PlotSettingsTableViewWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mPlotSettingsContextGenerator = PlotSettingsContextGenerator()

    def plotSettingsModel(self) -> PlotSettingsModel:

        model = self.mTableView.model()

        while isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        return model

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QModelIndex):
        if index.column() == 2:
            style: TemporalProfilePlotStyle = index.data(Qt.UserRole)

            h = self.mTableView.verticalHeader().sectionSize(index.row())
            w = self.mTableView.horizontalHeader().sectionSize(index.column())

            if h > 0 and w > 0:
                px = style.createPixmap(size=QSize(w, h))
                label = QLabel()
                label.setPixmap(px)
                painter.drawPixmap(option.rect, px)
                # QApplication.style().drawControl(QStyle.CE_CustomBase, label, painter)
            else:
                super(PlotSettingsTableViewWidgetDelegate, self).paint(painter, option, index)
        else:
            super(PlotSettingsTableViewWidgetDelegate, self).paint(painter, option, index)

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)

        for c in [PlotSettingsModel.cStyle, PlotSettingsModel.cExpression]:
            tableView.setItemDelegateForColumn(c, self)

    """
    def sizeHint(self, options, index):
        s = super(ExpressionDelegate, self).sizeHint(options, index)
        exprString = self.tableView.model().data(index)
        l = QLabel()
        l.setText(exprString)
        x = l.sizeHint().width() + 100
        s = QSize(x, s.height())
        return self._preferedSize
    """

    def createEditor(self, parent, option, index: QModelIndex):

        if not index.isValid():
            return

        w = None
        c = index.column()
        plotStyle = index.data(Qt.UserRole)
        model = self.plotSettingsModel()
        self.mPlotSettingsContextGenerator.setLayer(model.temporalProfileLayer())
        if isinstance(plotStyle, TemporalProfilePlotStyle):
            if c == PlotSettingsModel.cExpression:
                w = QgsFieldExpressionWidget(parent=parent)
                w.setExpressionDialogTitle('Values')
                w.setToolTip('Set an expression to specify the image band or calculate a spectral index.')
                # w.fieldChanged[str, bool].connect(lambda n, b: self.checkData(index, w, w.expression()))

                w.registerExpressionContextGenerator(self.mPlotSettingsContextGenerator)

                model = self.plotSettingsModel()
                layer = model.temporalProfileLayer()
                if isinstance(layer, QgsVectorLayer):
                    w.setLayer(layer)
                # w.setRow(0)
                w.setExpression(plotStyle.expression())

            elif c == PlotSettingsModel.cStyle:
                w = PlotStyleButton(parent=parent)
                w.setPlotStyle(plotStyle)
                w.setToolTip('Set style.')
                # w.sigPlotStyleChanged.connect(lambda ps: self.checkData(index, w, ps))

            else:
                raise NotImplementedError()
        return w

    def checkData(self, index, w, value):
        assert isinstance(index, QModelIndex)
        if index.isValid():
            plotStyle = index.data(Qt.UserRole)
            assert isinstance(plotStyle, TemporalProfilePlotStyle)
            if isinstance(w, QgsFieldExpressionWidget):
                assert value == w.expression()
                assert w.isExpressionValid(value) == w.isValidExpression()

                if w.isValidExpression():
                    self.commitData.emit(w)
                else:
                    s = ""
                    # print(('Delegate commit failed',w.asExpression()))
            if isinstance(w, PlotStyleButton):
                self.commitData.emit(w)

    def setEditorData(self, editor, index: QModelIndex):
        if not index.isValid():
            return

        w = None
        style = index.data(Qt.UserRole)
        assert isinstance(style, TemporalProfilePlotStyle)
        c = index.column()
        if c == PlotSettingsModel.cExpression:
            lastExpr = index.data(Qt.DisplayRole)
            assert isinstance(editor, QgsFieldExpressionWidget)
            editor.setProperty('lastexpr', lastExpr)
            editor.setField(lastExpr)

        elif c == PlotSettingsModel.cStyle:
            assert isinstance(editor, PlotStyleButton)
            editor.setPlotStyle(style)

        else:
            raise NotImplementedError()

    def setModelData(self, w, model, index: QModelIndex):
        c = index.column()
        # model = self.plotSettingsModel()

        if index.isValid():
            if c == PlotSettingsModel.cExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression():
                    if expr != exprLast:
                        model.setData(index, w.asExpression(), Qt.EditRole)
                else:
                    w
            elif c == PlotSettingsModel.cStyle:
                if isinstance(w, PlotStyleButton):
                    style = w.plotStyle()
                    model.setData(index, style, Qt.EditRole)

            else:
                raise NotImplementedError()


class DateTimePlotWidget(pg.PlotWidget):
    """
    A plotwidget to visualize temporal profiles
    """

    def __init__(self, parent: QWidget = None):
        """
        Constructor of the widget
        """
        plotItem = pg.PlotItem(
            axisItems={'bottom': DateTimeAxis(orientation='bottom')},
            viewBox=DateTimeViewBox()
        )
        super(DateTimePlotWidget, self).__init__(parent, plotItem=plotItem)
        self.plotItem = plotItem
        # self.setCentralItem(self.plotItem)
        # self.xAxisInitialized = False

        pi = self.getPlotItem()
        pi.getAxis('bottom').setLabel(LABEL_TIME)
        pi.getAxis('left').setLabel(LABEL_EXPRESSION_2D)

        self.mInfoColor = QColor('yellow')
        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)
        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoLabelCursor.setColor(QColor('yellow'))

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())
        # self.plot2DLabel.setAnchor()
        # self.plot2DLabel.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(0, 0))
        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)

        assert isinstance(self.scene(), pg.GraphicsScene)
        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self.onMouseMoved2D)

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.setInterval(500)
        self.mUpdateTimer.setSingleShot(False)
        self.mUpdateTimer.timeout.connect(self.onPlotUpdateTimeOut)
        self.mPlotSettingsModel: PlotSettingsModel = None

        self.mPlotDataItems = dict()
        self.mUpdatedProfileStyles = set()

    def setPlotSettingsModel(self, plotSettingsModel: PlotSettingsModel):
        if self.mPlotSettingsModel == plotSettingsModel:
            return

        self.mUpdateTimer.stop()

        if isinstance(self.mPlotSettingsModel, PlotSettingsModel):
            # disconnect signals
            self.mPlotSettingsModel.dataChanged.disconnect(self.onPlotSettingsChanged)
            pass

        if isinstance(plotSettingsModel, PlotSettingsModel):
            # connect signals
            self.mPlotSettingsModel = plotSettingsModel
            self.mPlotSettingsModel.dataChanged.connect(self.onPlotSettingsChanged)
            self.mUpdateTimer.start()

    def onPlotSettingsChanged(self, idx0: QModelIndex, idxe: QModelIndex, roles: list):
        if not isinstance(self.mPlotSettingsModel, PlotSettingsModel):
            return None
        row = idx0.row()
        while row <= idxe.row():
            style = self.mPlotSettingsModel.index(row, 0).data(Qt.UserRole)
            assert isinstance(style, TemporalProfilePlotStyle)
            self.mUpdatedProfileStyles.add(style)
            row += 1

    def setUpdateInterval(self, msec: int):
        """
        Sets the update interval
        :param msec:
        :type msec:
        :return:
        :rtype:
        """
        self.mUpdateTimer.setInterval(msec)

    def closeEvent(self, *args, **kwds):
        """
        Stop the time to avoid calls on freed / deleted C++ object references
        """
        self.mUpdateTimer.stop()
        super().closeEvent(*args, **kwds)

    def onPlotUpdateTimeOut(self, *args):
        try:
            self.updateTemporalProfilePlotItems()
        except RuntimeError as ex1:
            print(ex1, file=sys.stderr)
        except NotImplementedError as ex2:
            print(ex2, file=sys.stderr)

    def temporalProfilePlotDataItems(self) -> List[TemporalProfilePlotDataItem]:
        return [i for i in self.plotItem.items if isinstance(i, TemporalProfilePlotDataItem)]

    def updateTemporalProfilePlotItems(self):
        if not isinstance(self.mPlotSettingsModel, PlotSettingsModel):
            return

        pi = self.getPlotItem()

        toBeVisualized = [ps for ps in self.mPlotSettingsModel if ps.isPlotable()]
        EXISTING = dict()
        for pdi in self.temporalProfilePlotDataItems():
            EXISTING[pdi.mPlotStyle] = pdi

        if len(toBeVisualized) == 0 and len(EXISTING) == 0:
            return

        toBeAdded = [ps for ps in toBeVisualized if ps not in EXISTING.keys()]
        toBeRemoved = [ps for ps in EXISTING.keys() if ps not in toBeVisualized]
        toBeUpdated = [ps for ps in toBeVisualized if ps not in toBeAdded and ps in self.mUpdatedProfileStyles]
        self.mUpdatedProfileStyles.clear()
        if len(toBeRemoved) > 0:
            for ps in toBeRemoved:
                pdi = EXISTING.pop(ps)
                self.plotItem.removeItem(pdi)
                pdi.setClickable(False)
                pdi.setVisible(False)

        if len(toBeAdded) > 0:
            added_pdis = []
            for profileStyle in toBeAdded:
                assert isinstance(profileStyle, TemporalProfilePlotStyle)
                pdi = TemporalProfilePlotDataItem(profileStyle)
                pdi.setClickable(True)
                pdi.setVisible(True)
                added_pdis.append(pdi)
                pi.addItem(pdi)
            if True:
                for pdi in added_pdis:
                    assert isinstance(pdi, TemporalProfilePlotDataItem)
                    assert pdi in self.temporalProfilePlotDataItems()
                    assert pdi.isVisible()
                    # assert len(pdi.xData) > 0
                    if pdi.xData is not None:
                        assert len(pdi.xData) == len(pdi.yData)

        if len(toBeUpdated) > 0:
            for ps in toBeUpdated:
                pdi = EXISTING[ps]
                assert isinstance(pdi, TemporalProfilePlotDataItem)
                pdi.updateDataAndStyle()

    def resetViewBox(self):
        self.plotItem.getViewBox().autoRange()

    def onMouseMoved2D(self, evt):
        pos = evt[0]  # using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()

        vb = plotItem.vb
        assert isinstance(vb, DateTimeViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()

            if x < 0:
                self.hideInfoItems()
                return
            nearest_item = None
            nearest_index = -1
            nearest_distance = sys.float_info.max

            date = num2date(x)
            doy = dateDOY(date)
            vb.updateCurrentDate(num2date(x, dt64=True))

            positionInfo = 'Value:{:0.5f}\nDate {}\nDOY {}'.format(mousePoint.y(), date, doy)
            self.mInfoLabelCursor.setText(positionInfo, color=self.mInfoColor)

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(vb.mActionShowCursorValues.isChecked())
            self.mInfoLabelCursor.setPos(pos)

            b = vb.mActionShowCrosshair.isChecked()
            self.mCrosshairLineH.setVisible(b)
            self.mCrosshairLineV.setVisible(b)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            self.hideInfoItems()

    def hideInfoItems(self):
        plotItem = self.getPlotItem()
        vb = plotItem.vb
        vb.setToolTip('')
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def onMouseMoved2D_BAK(self, evt):
        pos = evt[0]  # using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        if plotItem.sceneBoundingRect().contains(pos):
            vb = plotItem.vb
            assert isinstance(vb, DateTimeViewBox)
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            if x >= 0:
                y = mousePoint.y()
                date = num2date(x)
                doy = dateDOY(date)
                plotItem.vb.updateCurrentDate(num2date(x, dt64=True))
                self.mInfoLabelCursor.setText('DN {:0.2f}\nDate {}\nDOY {}'.format(
                    mousePoint.y(), date, doy),
                    color=self.mInfoColor)

                s = self.size()
                pos = QPointF(s.width(), 0)
                self.mInfoLabelCursor.setVisible(vb.mActionShowCursorValues.isChecked())
                self.mInfoLabelCursor.setPos(pos)

                b = vb.mActionShowCrosshair.isChecked()
                self.mCrosshairLineH.setVisible(b)
                self.mCrosshairLineV.setVisible(b)
                self.mCrosshairLineH.pen.setColor(self.mInfoColor)
                self.mCrosshairLineV.pen.setColor(self.mInfoColor)
                self.mCrosshairLineV.setPos(mousePoint.x())
                self.mCrosshairLineH.setPos(mousePoint.y())


class DateTimeAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(DateTimeAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(False)
        self.labelAngle = 0

    def logTickStrings(self, values, scale, spacing):
        s = ""

    def tickStrings(self, values, scale, spacing):
        strns = []

        if len(values) == 0:
            return []
        # assert isinstance(values[0],

        values = [num2date(v) if v > 0 else num2date(1) for v in values]
        rng = max(values) - min(values)
        ndays = rng.astype(int)

        strns = []

        for v in values:
            if ndays == 0:
                strns.append(v.astype(str))
            else:
                strns.append(v.astype(str))

        return strns

    def tickValues(self, minVal, maxVal, size):
        d = super(DateTimeAxis, self).tickValues(minVal, maxVal, size)

        return d

    def tickFont(self):
        return self.style.get('tickFont', None)

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):

        p.setRenderHint(p.Antialiasing, False)
        p.setRenderHint(p.TextAntialiasing, True)

        # draw long line along axis
        pen, p1, p2 = axisSpec
        p.setPen(pen)
        p.drawLine(p1, p2)
        p.translate(0.5, 0)  # resolves some damn pixel ambiguity

        # draw ticks
        for pen, p1, p2 in tickSpecs:
            p.setPen(pen)
            p.drawLine(p1, p2)

        # Draw all text
        if self.tickFont() is not None:
            p.setFont(self.tickFont())
        p.setPen(self.pen())

        # for rect, flags, text in textSpecs:
        #    p.drawText(rect, flags, text)
        #    # p.drawRect(rect)

        # see https://github.com/pyqtgraph/pyqtgraph/issues/322
        for rect, flags, text in textSpecs:
            p.save()  # save the painter state
            p.translate(rect.center())  # move coordinate system to center of text rect
            p.rotate(self.labelAngle)  # rotate text
            p.translate(-rect.center())  # revert coordinate system
            p.drawText(rect, flags, text)
            p.restore()  # restore the painter state


class DateTimeViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    sigMoveToDate = pyqtSignal(np.datetime64)
    sigMoveToLocation = pyqtSignal(SpatialPoint)

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(DateTimeViewBox, self).__init__(parent)
        # self.menu = None # Override pyqtgraph ViewBoxMenu
        # self.menu = self.getMenu() # Create the menu
        # self.menu = None
        self.mCurrentDate = np.datetime64('today')

        self.mXAxisUnit = 'date'
        xAction = [a for a in self.menu.actions() if re.search('X Axis', a.text(), re.IGNORECASE)][0]
        #  yAction = [a for a in self.menu.actions() if re.search('Y Axis', a.text(), re.IGNORECASE)][0]

        menuXAxis = self.menu.addMenu('X Axis')
        # define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()

        frame.setLayout(l)
        # l.addWidget(self, QWidget, int, int, alignment: Qt.Alignment = 0): not enough arguments
        self.rbXManualRange = QRadioButton('Manual')
        self.dateEditX0 = QDateEdit()
        self.dateEditX0.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('Start time')
        self.dateEditX0.setCalendarPopup(True)
        self.dateEditX0.dateChanged.connect(self.updateXRange)
        self.dateEditX1 = QDateEdit()
        self.dateEditX1.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('End time')
        self.dateEditX1.setCalendarPopup(True)
        self.dateEditX1.dateChanged.connect(self.updateXRange)

        self.rbXAutoRange = QRadioButton('Auto')
        self.rbXAutoRange.setChecked(True)
        self.rbXAutoRange.toggled.connect(self.updateXRange)

        l.addWidget(self.rbXManualRange, 0, 0)
        l.addWidget(self.dateEditX0, 0, 1)
        l.addWidget(self.dateEditX1, 0, 2)
        l.addWidget(self.rbXAutoRange, 1, 0)

        l.setContentsMargins(1, 1, 1, 1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuXAxis)
        wa.setDefaultWidget(frame)
        menuXAxis.addAction(wa)

        self.menu.insertMenu(xAction, menuXAxis)
        self.menu.removeAction(xAction)

        self.mActionMoveToDate = self.menu.addAction('Move to {}'.format(self.mCurrentDate))
        self.mActionMoveToDate.triggered.connect(lambda *args: self.sigMoveToDate.emit(self.mCurrentDate))

        # self.mActionMoveToProfile = self.menu.addAction('Move to profile location')
        # self.mActionMoveToProfile.triggered.connect(lambda *args: self.sigM.emit(self.mCurrentDate))

        self.mActionShowCrosshair = self.menu.addAction('Show Crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)
        self.mActionShowCursorValues = self.menu.addAction('Show Mouse values')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

    sigXAxisUnitChanged = pyqtSignal(str)

    def setXAxisUnit(self, unit):
        assert unit in ['date', 'doy']
        old = self.mXAxisUnit
        self.mXAxisUnit = unit
        if old != self.mXAxisUnit:
            self.sigXAxisUnitChanged.emit(self.mXAxisUnit)

    def xAxisUnit(self):
        return self.mXAxisUnit

    def updateXRange(self, *args):
        isAutoRange = self.rbXAutoRange.isChecked()
        self.enableAutoRange('x', isAutoRange)

        self.dateEditX0.setEnabled(not isAutoRange)
        self.dateEditX1.setEnabled(not isAutoRange)

        if not isAutoRange:
            t0 = date2num(self.dateEditX0.date())
            t1 = date2num(self.dateEditX1.date())
            t0 = min(t0, t1)
            t1 = max(t0, t1)

            self.setXRange(t0, t1)

    def updateCurrentDate(self, date):
        if isinstance(date, np.datetime64):
            self.mCurrentDate = date
            self.mActionMoveToDate.setData(date)
            self.mActionMoveToDate.setText('Move maps to {}'.format(date))

    def raiseContextMenu(self, ev):

        pt = self.mapDeviceToView(ev.pos())
        self.updateCurrentDate(num2date(pt.x(), dt64=True))

        plotDataItems = [item for item in self.scene().itemsNearEvent(ev) if
                         isinstance(item, ScatterPlotItem) and isinstance(item.parentItem(),
                                                                          TemporalProfilePlotDataItem)]

        xRange, yRange = self.viewRange()
        if min(xRange) > 0:
            t0 = num2date(xRange[0], qDate=True)
            t1 = num2date(xRange[1], qDate=True)
            self.dateEditX0.setDate(t0)
            self.dateEditX1.setDate(t1)

        menu = self.getMenu(ev)

        if len(plotDataItems) > 0:
            s = ""

        self.scene().addParentContextMenus(self, menu, ev)
        menu.exec_(ev.screenPos().toPoint())


class ProfileViewDock(QgsDockWidget):
    """
    Signalizes to move to specific date of interest
    """
    sigShowPixel = pyqtSignal(TimeSeriesDate, QgsPoint, QgsCoordinateReferenceSystem)
    sigMoveToDate = pyqtSignal(np.datetime64)
    sigMoveToTSD = pyqtSignal(TimeSeriesDate)

    def __init__(self, layer: QgsVectorLayer, parent=None):
        super(ProfileViewDock, self).__init__(parent)
        loadUi(DIR_UI / 'profileviewdock.ui', self)
        assert isinstance(layer, QgsVectorLayer)

        self.mActions2D = [self.actionAddStyle2D, self.actionRemoveStyle2D, self.actionRefresh2D]
        self.mActionsTP = [self.actionLoadProfileRequest, self.actionLoadTPFromOgr, self.actionSaveTemporalProfiles,
                           self.actionLoadMissingValues]

        self.baseTitle = self.windowTitle()
        self.stackedWidget.currentChanged.connect(self.updateTitle)

        self.mTimeSeries: TimeSeries = None
        self.pxViewModel2D = None

        self.tableView2DProfiles.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.mTasks = dict()

        self.plot_initialized = False

        # temporal profile collection to store loaded values
        self.mTemporalProfileLayer: QgsVectorLayer = layer
        self.mTemporalProfileLayer.selectionChanged.connect(self.onTemporalProfileSelectionChanged)

        self.pagePixel: AttributeTableWidget = AttributeTableWidget(self.mTemporalProfileLayer)
        self.stackedWidget.addWidget(self.pagePixel)
        self.addActions(self.findChildren(QAction))
        # organize toolbars
        self.mAttributeTableToolBar: QToolBar = self.pagePixel.mToolbar
        self.mAttributeTableToolBar.setWindowTitle('Attribute Table Toolbar')
        self.mAttributeTableToolBar.setMovable(False)

        before = self.pagePixel.mActionToggleEditing
        self.mAttributeTableToolBar.insertActions(before, self.mActionsTP)
        self.mAttributeTableToolBar.insertSeparator(before)

        self.mPlotToolBar.setMovable(False)
        # self.mPlotToolBar.addActions(self.mActions2D)
        # self.mPlotToolBar.addSeparator()
        # self.mPlotToolBar.addActions(self.mActionsTP)

        # self.pagePixel.addToolBar(self.mTemporalProfilesToolBar)

        # self.mTemporalProfilesToolBar.setMovable(False)

        config = QgsAttributeTableConfig()
        config.update(self.mTemporalProfileLayer.fields())
        config.setActionWidgetVisible(False)
        hidden = []
        for i, columnConfig in enumerate(config.columns()):
            assert isinstance(columnConfig, QgsAttributeTableConfig.ColumnConfig)
            config.setColumnHidden(i, columnConfig.name in hidden)
        self.mTemporalProfilesTableConfig = config
        self.mTemporalProfileLayer.setAttributeTableConfig(self.mTemporalProfilesTableConfig)

        # set the plot models for 2D

        self.plotSettingsModel2D = PlotSettingsModel(self.mTemporalProfileLayer, parent=self)
        self.plotSettingsModel2DProxy = QSortFilterProxyModel()
        self.plotSettingsModel2DProxy.setSourceModel(self.plotSettingsModel2D)
        self.tableView2DProfiles: PlotSettingsTableView
        self.tableView2DProfiles.setModel(self.plotSettingsModel2DProxy)
        self.tableView2DProfiles.setSortingEnabled(True)
        self.tableView2DProfiles.selectionModel().selectionChanged.connect(self.onPlot2DSelectionChanged)
        self.tableView2DProfiles.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.delegateTableView2D = PlotSettingsTableViewWidgetDelegate(self.tableView2DProfiles)

        self.plot2D: DateTimePlotWidget = self.plotWidget2D
        assert isinstance(self.plot2D, DateTimePlotWidget)
        self.plot2D.setPlotSettingsModel(self.plotSettingsModel2D)
        self.plot2D.getViewBox().sigMoveToDate.connect(self.sigMoveToDate)
        self.plot2D.getViewBox().scene().sigMouseClicked.connect(self.onPointsClicked2D)
        self.mLast2DMouseClickPosition = None

        self.sigMoveToDate.connect(self.onMoveToDate)
        self.initActions()
        self.updateTitle(self.stackedWidget.currentIndex())

    def updateTitle(self, i):
        w = self.stackedWidget.currentWidget()
        title = self.baseTitle
        if w == self.page2D:
            title = '{} | Visualization'.format(title)
        elif w == self.pagePixel:
            title = '{} | Coordinates'.format(title)
        w.update()
        self.setWindowTitle(title)

    def plotStyles(self):
        return self.plotSettingsModel2D[:]

    def temporalProfileLayer(self) -> TemporalProfileLayer:
        """
        Returns a QgsVectorLayer that is used to store profile coordinates.
        :return:
        """
        return self.mTemporalProfileLayer

    def setVectorLayerTools(self, vectorLayerTools: VectorLayerTools):
        self.pagePixel.setVectorLayerTools(vectorLayerTools)

    def vectorLayerTools(self) -> VectorLayerTools:
        return self.pagePixel.vectorLayerTools()

    def setTimeSeries(self, timeSeries: TimeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.mTimeSeries = timeSeries
        self.plotSettingsModel2D.setTimeSeries(timeSeries)

    def timeSeries(self) -> TimeSeries:
        return self.mTimeSeries

    def selected2DPlotStyles(self):
        result = []

        m = self.tableView2DProfiles.model()
        for idx in selectedModelIndices(self.tableView2DProfiles):
            result.append(m.data(idx, Qt.UserRole))
        return result

    def removePlotStyles2D(self, plotStyles):
        m = self.tableView2DProfiles.model()
        if isinstance(m.sourceModel(), PlotSettingsModel):
            m.sourceModel().removePlotStyles(plotStyles)

    def removeTemporalProfiles(self, fids):

        self.mTemporalProfileLayer.selectByIds(fids)
        b = self.mTemporalProfileLayer.isEditable()
        self.mTemporalProfileLayer.startEditing()
        self.mTemporalProfileLayer.deleteSelectedFeatures()
        self.mTemporalProfileLayer.saveEdits(leaveEditable=b)

    def onPointsClicked2D(self, event: MouseClickEvent):
        info = []
        assert isinstance(event, MouseClickEvent)
        for item in self.plot2D.scene().itemsNearEvent(event):

            if isinstance(item, ScatterPlotItem) and isinstance(item.parentItem(), TemporalProfilePlotDataItem):
                pdi = item.parentItem()
                assert isinstance(pdi, TemporalProfilePlotDataItem)
                tp = pdi.mPlotStyle.temporalProfile()
                assert isinstance(tp, TemporalProfile)
                c = tp.coordinate()

                spottedItems = item.pointsAt(event.pos())
                if len(spottedItems) > 0:
                    info.append('Sensor: {}'.format(pdi.mPlotStyle.sensor().name()))
                    info.append('Coordinate: {}, {}'.format(c.x(), c.y()))
                    for item in spottedItems:
                        if isinstance(item, SpotItem):
                            brush1 = item.brush()
                            brush2 = item.brush()
                            brush2.setColor(QColor('yellow'))
                            item.setBrush(brush2)
                            QTimer.singleShot(500, lambda *args, spotItem=item, brush=brush1: spotItem.setBrush(brush))

                            pos = item.pos()
                            self.mLast2DMouseClickPosition = pos
                            x = pos.x()
                            y = pos.y()
                            date = num2date(x)
                            info.append('{};{}'.format(date, y))

        self.tbInfo2D.setPlainText('\n'.join(info))

    def onTemporalProfileSelectionChanged(self, selectedFIDs, deselectedFIDs):
        pass

    def onPlot2DSelectionChanged(self, selected, deselected):

        self.actionRemoveStyle2D.setEnabled(len(selected) > 0)

        selectedProfilesIDs = set()
        selectedProfileStyles = set()
        for idx in selected.indexes():
            assert isinstance(idx, QModelIndex)
            profileStyle = idx.data(Qt.UserRole)
            if isinstance(profileStyle, TemporalProfilePlotStyle):
                selectedProfileStyles.add(profileStyle)
                tp = profileStyle.temporalProfile()
                if isinstance(tp, TemporalProfile):
                    selectedProfilesIDs.add(tp.id())
        selectedProfilesIDs = sorted(selectedProfilesIDs)
        lyr = self.temporalProfileLayer()
        if isinstance(lyr, QgsVectorLayer):
            lyr.selectByIds(selectedProfilesIDs)

        # todo: highlight selected profiles in plot

    def initActions(self):
        self.actionRemoveStyle2D.setEnabled(False)
        self.actionAddStyle2D.triggered.connect(self.createNewPlotStyle2D)
        self.actionRefresh2D.triggered.connect(self.updatePlot2D)
        self.actionRemoveStyle2D.triggered.connect(
            lambda: self.removePlotStyles2D(self.selected2DPlotStyles()))
        self.actionLoadTPFromOgr.triggered.connect(self.onLoadFromVector)
        self.actionLoadMissingValues.triggered.connect(
            lambda *args: self.mTemporalProfileLayer.loadMissingBandInfos())
        self.actionSaveTemporalProfiles.triggered.connect(
            lambda *args: self.mTemporalProfileLayer.saveTemporalProfiles(None))

    def createNewPlotStyle2D(self):
        style = self.plotSettingsModel2D.createNewPlotStyle2D()
        self.plotSettingsModel2D.insertPlotStyles([style], 0)

    def onLoadFromVector(self):

        d = SelectMapLayersDialog()
        d.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        d.setWindowTitle('Select Vector Layer')
        if d.exec() == QDialog.Accepted:
            for l in d.mapLayers():
                self.mTemporalProfileLayer.loadCoordinatesFromOgr(l.source())
                break

    def onToggleEditing(self, b):

        if self.mTemporalProfileLayer.isEditable():
            self.mTemporalProfileLayer.saveEdits(leaveEditable=False)
        else:
            self.mTemporalProfileLayer.startEditing()
        self.onEditingToggled()

    def onMoveToDate(self, date):
        dt = np.asarray([np.abs(tsd.date() - date) for tsd in self.timeSeries()])
        i = np.argmin(dt)
        self.sigMoveToTSD.emit(self.timeSeries()[i])

    def loadCoordinate(self, spatialPoints: List[SpatialPoint],
                       run_async: bool = True):
        """
        Create new point(s) in the TemporalProfileLayer and loads bands values for
        :param spatialPoints: SpatialPoint or [list-of-SpatialPoints]
        """
        if isinstance(spatialPoints, SpatialPoint):
            spatialPoints = [spatialPoints]

        assert isinstance(spatialPoints, list)
        if len(spatialPoints) == 0 or not isinstance(self.mTemporalProfileLayer, QgsVectorLayer):
            return

        for p in spatialPoints:
            assert isinstance(p, SpatialPoint)

        crs = self.mTemporalProfileLayer.crs()
        points = [pt.toCrs(crs) for pt in spatialPoints]

        info = {}
        files = self.timeSeries().sourceUris()
        task = LoadTemporalProfileTask(files, points, crs=crs, info=info)
        task.run()

        profiles = task.profiles()

        # add results
        tpFields = TemporalProfileUtils.temporalProfileFields(self.mTemporalProfileLayer)
        if len(tpFields) == 0:
            warnings.warn('vector layer misses temporal profile field')

        if len(profiles) > 0:
            new_features: List[QgsFeature] = list()
            for profile, point in zip(profiles, task.profilePoints()):
                f = QgsFeature(self.mTemporalProfileLayer.fields())
                f.setGeometry(QgsGeometry.fromWkt(point.asWkt()))
                profileJson = TemporalProfileUtils.profileJsonFromDict(profile)
                f.setAttribute(tpFields[0].name(), profileJson)
                new_features.append(f)

            with edit(self.mTemporalProfileLayer):
                if not self.mTemporalProfileLayer.addFeatures(new_features):
                    err = self.mTemporalProfileLayer.error()
                    if isinstance(err, QgsError):
                        warnings.warn(err.message())

        # create at least 1 plot style
        if self.mTemporalProfileLayer.featureCount() > 0 and len(self.plotSettingsModel2D) == 0:
            self.createNewPlotStyle2D()

    @pyqtSlot()
    def updatePlot2D(self):
        if isinstance(self.plotSettingsModel2D, PlotSettingsModel):
            self.plot2D.mUpdatedProfileStyles.update(self.plotSettingsModel2D[:])
            self.plot2D.updateTemporalProfilePlotItems()
