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
from typing import Dict, Iterator, List, Optional, Union

import numpy as np
from matplotlib.dates import date2num
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QFontMetrics, QIcon, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QStyle, QStyleOptionViewItem, QTreeView
from qgis._core import QgsFeatureRequest, QgsProperty, QgsPropertyDefinition
from qgis.gui import QgsDockWidget, QgsFieldExpressionWidget, QgsMapLayerComboBox
from qgis.core import QgsExpression, \
    QgsExpressionContext, QgsExpressionContextGenerator, QgsExpressionContextScope, QgsExpressionContextUtils, \
    QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QAbstractTableModel, QItemSelectionModel, \
    QModelIndex, QObject, QPoint, QPointF, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QCursor, QPainter, QPalette, QPen
from qgis.PyQt.QtWidgets import QAction, QDateEdit, QFrame, QGridLayout, QLabel, QMenu, \
    QRadioButton, QSlider, QStyledItemDelegate, QTableView, QWidget, QWidgetAction

from eotimeseriesviewer import DIR_UI
from .expression_functions import ProfileValueExpressionFunction
from ..dateparser import dateDOY, num2date
from ..qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle, PlotStyleButton, PlotStyleDialog
from ..qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from ..qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen, ScatterPlotItem
from ..qgispluginsupport.qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, ProfileColorPropertyItem, \
    PropertyItem, PropertyItemBase, PropertyItemGroup, QgsPropertyItem
from ..qgispluginsupport.qps.utils import loadUi, SpatialPoint
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


class TemporalProfilePlotStyle(PlotStyle):
    pass


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
        pi.getAxis('bottom').setLabel('Date')
        pi.getAxis('left').setLabel('Value')

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

        # self.mUpdateTimer = QTimer()
        # self.mUpdateTimer.setInterval(500)
        # self.mUpdateTimer.setSingleShot(False)
        # self.mUpdateTimer.timeout.connect(self.onPlotUpdateTimeOut)
        # self.mPlotSettingsModel: PlotSettingsModel = None

        # self.mPlotDataItems = dict()
        # self.mUpdatedProfileStyles = set()

    def onPlotSettingsChanged(self, idx0: QModelIndex, idxe: QModelIndex, roles: list):
        if not isinstance(self.mPlotSettingsModel, PlotSettingsTableModel):
            return None
        row = idx0.row()
        while row <= idxe.row():
            style = self.mPlotSettingsModel.index(row, 0).data(Qt.UserRole)
            assert isinstance(style, TemporalProfilePlotStyle)
            self.mUpdatedProfileStyles.add(style)
            row += 1

    def closeEvent(self, *args, **kwds):
        """
        Stop the time to avoid calls on freed / deleted C++ object references
        """
        self.mUpdateTimer.stop()
        super().closeEvent(*args, **kwds)

    def temporalProfilePlotDataItems(self) -> List[TemporalProfilePlotDataItem]:
        return [i for i in self.plotItem.items if isinstance(i, TemporalProfilePlotDataItem)]

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


class PlotSettingsTreeModel(QStandardItemModel):
    cName = 0
    cValue = 1

    sigProgressChanged = pyqtSignal(float)
    sigPlotWidgetStyleChanged = pyqtSignal()
    sigMaxProfilesExceeded = pyqtSignal()
    NOT_INITIALIZED = -1

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mModelItems: List[PropertyItemGroup] = []
        # # workaround https://github.com/qgis/QGIS/issues/45228

        hdr0 = QStandardItem('Setting')
        hdr0.setToolTip('Visualization setting')
        hdr1 = QStandardItem('Value')
        hdr1.setToolTip('Visualization setting value')
        self.setHorizontalHeaderItem(0, hdr0)
        self.setHorizontalHeaderItem(1, hdr1)

        self.mPlotWidget: DateTimePlotWidget = None
        self.mTimeSeries: TimeSeries = None
        self.mLayer: QgsVectorLayer = None
        self.mSensors: Dict[str, SensorInstrument] = dict()

        self.mVisualizations: List[TPVisGroup]

    def setPlotWidget(self, plotWidget: DateTimePlotWidget):
        self.mPlotWidget = plotWidget

    def setTimeSeries(self, timeSeries: TimeSeries):

        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensors)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensors)
        self.addSensors(timeSeries.sensors())

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mLayer, QgsVectorLayer):
            # disconnect signals
            pass

        self.mLayer = layer

    def addVisualization(self, vis: TPVisGroup):

        pass

    def addSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):
        """
        Create a new plotstyle for this sensor
        :param sensor:
        :return:
        """

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        for s in sensors:
            s: SensorInstrument
            if s.id() not in self.mSensors:
                self.mSensors[s.id()] = s

    def sensorIds(self) -> List[str]:
        """
        Returns the sensor ids for which plot styles exists
        :return:
        """
        return [s.sensor().id() for s in self.mPlotStyles]

    def removeSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        to_remove = []
        for sensor in sensors:
            sid = sensor.id()
            if sid in self.mSensors:
                self.mSensors.pop(sid)
                to_remove.append(sid)

    def plotWidget(self) -> DateTimePlotWidget:
        return self.mPlotWidget

    def updatePlot(self):

        pw = self.plotWidget()
        pw.plotItem.clear()

        request = QgsFeatureRequest()

        selected_fids = self.mLayer.selectedFeatureIds()

        for feature in self.mLayer.getFeatures(request):
            pass


class PlotSettingsTreeViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: QTreeView, parent=None):
        assert isinstance(treeView, QTreeView)
        super().__init__(parent=parent)
        self.mTreeView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: PropertyItem = index.data(Qt.UserRole)
        bc = QColor(self.plotControl().generalSettings().backgroundColor())
        total_h = self.mTreeView.rowHeight(index)
        total_w = self.mTreeView.columnWidth(index.column())
        style: QStyle = option.styleObject.style()
        margin = 3  # px
        if isinstance(item, PropertyItemBase):
            if item.hasPixmap():
                super().paint(painter, option, index)
                rect = option.rect
                size = QSize(rect.width(), rect.height())
                pixmap = item.previewPixmap(size)
                if isinstance(pixmap, QPixmap):
                    painter.drawPixmap(rect, pixmap)

            elif isinstance(item, PropertyItemGroup):
                # super().paint(painter, option, index)
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                h = option.rect.height()
                plot_style: PlotStyle = item.mPStyle.plotStyle()
                # add pixmap
                pm = plot_style.createPixmap(size=QSize(h, h), hline=True, bc=bc)
                to_paint.append(pm)
                if not item.isComplete():
                    to_paint.append(QIcon(r':/images/themes/default/mIconWarning.svg'))
                to_paint.append(item.data(Qt.DisplayRole))

                x0 = option.rect.x() + 1
                y0 = option.rect.y()
                for p in to_paint:
                    o: QStyleOptionViewItem = QStyleOptionViewItem(option)
                    self.initStyleOption(o, index)
                    o.styleObject = option.styleObject
                    o.palette = QPalette(option.palette)

                    if isinstance(p, Qt.CheckState):
                        # size = style.sizeFromContents(QStyle.PE_IndicatorCheckBox, o, QSize(), None)
                        o.rect = QRect(x0, y0, h, h)
                        o.state = {Qt.Unchecked: QStyle.State_Off,
                                   Qt.Checked: QStyle.State_On,
                                   Qt.PartiallyChecked: QStyle.State_NoChange}[p]
                        o.state = o.state | QStyle.State_Enabled

                        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, o, painter, self.mTreeView)

                    elif isinstance(p, QPixmap):
                        o.rect = QRect(x0, y0, h, h)
                        painter.drawPixmap(o.rect, p)

                    elif isinstance(p, QIcon):
                        o.rect = QRect(x0, y0, h, h)
                        p.paint(painter, o.rect)
                    elif isinstance(p, str):
                        font_metrics = QFontMetrics(self.mTreeView.font())
                        w = font_metrics.horizontalAdvance(p)
                        o.rect = QRect(x0 + margin, y0, x0 + margin + w, h)
                        palette = style.standardPalette()
                        enabled = True
                        textRole = QPalette.Foreground
                        style.drawItemText(painter, o.rect, Qt.AlignLeft, palette, enabled, p, textRole=textRole)

                    else:
                        raise NotImplementedError(f'Does not support painting of "{p}"')
                    x0 = o.rect.x() + margin + o.rect.width()

            elif isinstance(item, PlotStyleItem):
                # self.initStyleOption(option, index)
                plot_style: PlotStyle = item.plotStyle()

                if total_h > 0 and total_w > 0:
                    px = plot_style.createPixmap(size=QSize(total_w, total_h), bc=bc)
                    painter.drawPixmap(option.rect, px)
                else:
                    super().paint(painter, option, index)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def setItemDelegates(self, treeView: QTreeView):
        for c in range(treeView.model().columnCount()):
            treeView.setItemDelegateForColumn(c, self)

    def onRowsInserted(self, parent, idx0, idx1):
        nameStyleColumn = self.bridge().cnPlotStyle

        for c in range(self.mTreeView.model().columnCount()):
            cname = self.mTreeView.model().headerData(c, Qt.Horizontal, Qt.DisplayRole)
            if cname == nameStyleColumn:
                for r in range(idx0, idx1 + 1):
                    idx = self.mTreeView.model().index(r, c, parent=parent)
                    self.mTreeView.openPersistentEditor(idx)

    def plotControl(self) -> PlotSettingsTreeModel:
        return self.mTreeView.model().sourceModel()

    def createEditor(self, parent, option, index):
        w = None
        editor = None
        if index.isValid():
            item = index.data(Qt.UserRole)
            if isinstance(item, PropertyItem):
                editor = item.createEditor(parent)
        if isinstance(editor, QWidget):
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        if not index.isValid():
            return

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setEditorData(editor, index)
        else:
            super().setEditorData(editor, index)

        return

    def setModelData(self, w, model, index):

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setModelData(w, model, index)
        else:
            super().setModelData(w, model, index)


class PlotSettingsTreeView(QTreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class PlotSettingsProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class PlotSettingsTableModel(QAbstractTableModel):
    cSensor = 0
    cExpression = 1
    cStyle = 2
    cFilter = 3
    cLabel = 4

    def __init__(self, layer: QgsVectorLayer = None, timeSeries: TimeSeries = None, parent=None, *args):
        super(PlotSettingsTableModel, self).__init__(parent=parent)

        # self.mTemporalProfileLayer.featureAdded.connect(self.onTemporalProfilesAdded)
        # self.mTemporalProfileLayer.featuresDeleted.connect(self.onTemporalProfilesDeleted)
        # self.mTemporalProfileLayer.sigTemporalProfilesUpdated.connect(self.onTemporalProfilesUpdated)
        self.columnNames = {self.cSensor: 'Sensor',
                            self.cExpression: 'Expression',
                            self.cStyle: 'Style',
                            }

        self.mPlotStyles: List[TemporalProfilePlotStyle] = []
        self.mIconSize = QSize(25, 25)
        self.mTemporalProfileLayer: Optional[QgsVectorLayer] = None
        self.mTimeSeries: Optional[TimeSeries] = None

        if timeSeries:
            self.setTimeSeries(timeSeries)

        if layer:
            self.setLayer(layer)

        self.mPlotWidget: DateTimePlotWidget = None

    def profileStyles(self) -> List[TemporalProfilePlotStyle]:
        return [s for s in self.mPlotStyles if s.isVisible()]

    def setPlotWidget(self, plotWidget: DateTimePlotWidget):
        self.mPlotWidget = plotWidget

    def plotWidget(self) -> DateTimePlotWidget:
        return self.mPlotWidget

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mTemporalProfileLayer, QgsVectorLayer):
            # disconnect signals
            pass

        self.mTemporalProfileLayer = layer

    def updatePlot(self):

        pw = self.plotWidget()
        pw.plotItem.clear()

        style = self.multiSensorProfilePlotStyle()

        for feature in self.mModel.temporalProfileLayer().getFeatures():

            for style in styles:
                exp = QgsExpression(style.expression())

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

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        indices = self.selectionModel().selectedIndexes()

        if len(indices) > 0:
            refIndex = indices[0]
            assert isinstance(refIndex, QModelIndex)

            menu = QMenu(self)
            menu.setToolTipsVisible(True)

            menu.popup(QCursor.pos())

    def plotSettingsModel(self) -> PlotSettingsTableModel:
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


class TPVisSensor(PropertyItemGroup):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mZValue = 2
        self.setName('Visualization')
        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = False
        self.mSpeclib: QgsVectorLayer = None

        self.mPColor = ProfileColorPropertyItem('Color')
        self.mPColor.setDefinition(QgsPropertyDefinition(
            'Color', 'Color of spectral profile', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mPColor.setProperty(QgsProperty.fromValue(QColor('white')))


class TPVisGroup(PropertyItemGroup):
    MIME_TYPE = 'application/eotsv/temporalprofiles/PropertyItems'

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mZValue = 2
        self.setName('Temporal Profiles')
        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = True

        self.mPField = QgsPropertyItem('Field')
        self.mPField.setDefinition(QgsPropertyDefinition(
            'Field', 'Name of the field that stores the temporal profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPField.setProperty(QgsProperty.fromField('profiles', True))
        self.mPField.setIsProfileFieldProperty(True)

        self.mPStyle = PlotStyleItem('Style')
        self.mPStyle.setEditColors(False)
        self.mPLabel = QgsPropertyItem('Label')
        self.mPLabel.setDefinition(QgsPropertyDefinition(
            'Label', 'Text label to describe plotted temporal profiles.',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPLabel.setProperty(QgsProperty.fromExpression('$id'))

        self.mPFilter = QgsPropertyItem('Filter')
        self.mPFilter.setDefinition(QgsPropertyDefinition(
            'Filter', 'Filter feature', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPFilter.setProperty(QgsProperty.fromExpression(''))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLabel, self.mPFilter, self.mPStyle]:
            self.appendRow(pItem.propertyRow())

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        # connect requestPlotUpdate signal
        for propertyItem in self.propertyItems():
            propertyItem: PropertyItem
            propertyItem.signals().dataChanged.connect(self.signals().dataChanged.emit)
        self.signals().dataChanged.connect(self.update)
        # self.initBasicSettings()

    def addSensor(self, sid):

        s = ""

    def removeSensor(self, sid: str):

        s = ""


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

    def plotSettingsModel(self) -> PlotSettingsTableModel:

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

        for c in [PlotSettingsTableModel.cStyle, PlotSettingsTableModel.cExpression]:
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
            if c == PlotSettingsTableModel.cExpression:
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

            elif c == PlotSettingsTableModel.cStyle:
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
        if c == PlotSettingsTableModel.cExpression:
            lastExpr = index.data(Qt.DisplayRole)
            assert isinstance(editor, QgsFieldExpressionWidget)
            editor.setProperty('lastexpr', lastExpr)
            editor.setField(lastExpr)

        elif c == PlotSettingsTableModel.cStyle:
            assert isinstance(editor, PlotStyleButton)
            editor.setPlotStyle(style)

        else:
            raise NotImplementedError()

    def setModelData(self, w, model, index: QModelIndex):
        c = index.column()
        # model = self.plotSettingsModel()

        if index.isValid():
            if c == PlotSettingsTableModel.cExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression():
                    if expr != exprLast:
                        model.setData(index, w.asExpression(), Qt.EditRole)
                else:
                    w
            elif c == PlotSettingsTableModel.cStyle:
                if isinstance(w, PlotStyleButton):
                    style = w.plotStyle()
                    model.setData(index, style, Qt.EditRole)

            else:
                raise NotImplementedError()


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


class TemporalProfileDock(QgsDockWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        ui_path = DIR_UI / f'{self.__class__.__name__.lower()}.ui'
        loadUi(ui_path, self)

        self.mProject: QgsProject = QgsProject.instance()
        self.mMapLayerComboBox: QgsMapLayerComboBox
        self.mMapLayerComboBox.setProject(self.mProject)
        self.mPlotWidget: DateTimePlotWidget

        self.mTreeView: PlotSettingsTreeView
        self.mModel = PlotSettingsTreeModel()
        self.mModel.setPlotWidget(self.mPlotWidget)

        self.mProxyModel = PlotSettingsProxyModel()
        self.mProxyModel.setSourceModel(self.mModel)
        self.mTreeView.setModel(self.mProxyModel)
        self.mDelegate = PlotSettingsTreeViewDelegate(self.mTreeView)
        self.mTreeView.setItemDelegate(self.mDelegate)

    def plotWidget(self) -> DateTimePlotWidget:
        return self.mPlotWidget

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mModel.setTimeSeries(timeseries)

    def mapLayerComboBox(self) -> QgsMapLayerComboBox:
        return self.mMapLayerComboBox

    def project(self) -> QgsProject:
        return self.mProject

    def setProject(self, project: QgsProject):
        self.mProject = project
        self.mapLayerComboBox().setProject(project)

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        self.mModel.setLayer(layer)
        self.mModel.updatePlot()

    def layer(self) -> QgsVectorLayer:
        return self.mModel.temporalProfileLayer()
