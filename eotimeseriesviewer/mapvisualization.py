# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
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
import enum
import logging
import math
import sys
import time
import traceback
from threading import Lock
from typing import Dict, Iterator, List, Optional, Tuple, Union

import qgis.utils
from qgis.PyQt.QtCore import pyqtSignal, QAbstractListModel, QDateTime, QMimeData, QModelIndex, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QGuiApplication, QIcon, QKeySequence, QMouseEvent
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QLineEdit, QMenu, QSlider, QSpinBox, QToolBox, \
    QWidget
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextGenerator, QgsExpressionContextScope, QgsExpressionContextUtils, QgsLayerTree, \
    QgsLayerTreeGroup, QgsLayerTreeLayer, QgsLayerTreeModel, QgsMapLayer, QgsMapLayerProxyModel, \
    QgsMultiBandColorRenderer, QgsPointXY, QgsProcessingFeedback, QgsProject, QgsRasterLayer, QgsRasterRenderer, \
    QgsRectangle, QgsTextFormat, QgsVector, QgsVectorLayer
from qgis.core import QgsLayerTreeNode
from qgis.gui import QgisInterface, QgsDockWidget, QgsExpressionBuilderDialog, QgsLayerTreeMapCanvasBridge, \
    QgsLayerTreeView, QgsLayerTreeViewMenuProvider, QgsMapCanvas, QgsMessageBar, QgsProjectionSelectionWidget

from eotimeseriesviewer import debugLog, DIR_UI
from eotimeseriesviewer.timeseries.source import TimeSeriesDate
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from eotimeseriesviewer.utils import copyMapLayerStyle, fixMenuButtons, index_window, layerStyleString, \
    setFontButtonPreviewBackgroundColor, setLayerStyleString
from .mapcanvas import KEY_LAST_CLICKED, MapCanvas, MapCanvasInfoItem, STYLE_CATEGORIES
from .maplayerproject import EOTimeSeriesViewerProject
from .qgispluginsupport.qps.crosshair.crosshair import CrosshairMapCanvasItem, CrosshairStyle, getCrosshairStyle
from .qgispluginsupport.qps.layerproperties import VectorLayerTools
from .qgispluginsupport.qps.maptools import MapTools
from .qgispluginsupport.qps.utils import loadUi, SignalBlocker, SpatialExtent, SpatialPoint
from .sensors import has_sensor_id, sensor_id, SensorInstrument, SensorMockupDataProvider
from .settings.settings import EOTSVSettingsManager

logger = logging.getLogger(__name__)

KEY_LOCKED_LAYER = 'eotsv/locked'
KEY_SENSOR_GROUP = 'eotsv/sensorgroup'


# KEY_SENSOR_LAYER = 'eotsv/sensorlayer'


def equalTextFormats(tf1: QgsTextFormat, tf2: QgsTextFormat) -> True:
    if not (isinstance(tf1, QgsTextFormat) and isinstance(tf2, QgsTextFormat)):
        return False
    return tf1.toMimeData().text() == tf2.toMimeData().text()


class MapViewLayerTreeModel(QgsLayerTreeModel):
    """
    Layer Tree as shown in a MapView
    """

    def __init__(self, rootNode, parent=None):
        super(MapViewLayerTreeModel, self).__init__(rootNode, parent=parent)

    def flags(self, index: QModelIndex):
        # return super().flags(index)
        flags = super().flags(index)
        node = self.index2node(index)
        if isinstance(node, QgsLayerTreeNode) and node.customProperty(KEY_LOCKED_LAYER):
            flags &= ~Qt.ItemIsDropEnabled
            flags &= ~Qt.ItemIsDragEnabled

        return flags

    # def supportedDragActions(self):
    #     return super().supportedDragActions()
    #     """
    #     """
    #     return Qt.CopyAction | Qt.MoveAction
    #
    # def supportedDropActions(self) -> Qt.DropActions:
    #     return super().supportedDropActions()
    #     """
    #     """
    #     return Qt.CopyAction | Qt.MoveAction
    #
    # def mimeTypes(self):
    #
    #     mt = super().mimeTypes()
    #     mt.append('text/uri-list')
    #     return mt
    #
    # def mimeData(self, index, parent):
    #     return super().mimeData(index, parent)
    #
    # def canDropMimeData(self, data: QMimeData, action, row: int, column: int, parent: QModelIndex):
    #
    #     parentNode = self.index2node(parent)
    #     if isinstance(parentNode, QgsLayerTreeGroup) and parentNode.customProperty(KEY_LOCKED_LAYER,
    #                                                                                defaultValue=False):
    #         return False
    #
    #     if data.hasUrls():
    #         return True
    #     if 'application/x-vnd.qgis.qgis.uri' in data.formats():
    #         return True
    #     else:
    #         return super().canDropMimeData(data, action, row, column, parent)
    #
    def dropMimeData(self, mimeData: QMimeData, action, row: int, column: int, parentIndex: QModelIndex):

        parentNode = self.index2node(parentIndex)
        if isinstance(parentNode, QgsLayerTreeGroup) and parentNode.customProperty(KEY_LOCKED_LAYER,
                                                                                   defaultValue=False):
            return False

        assert isinstance(mimeData, QMimeData)

        if not parentIndex.isValid():
            return False

        if mimeData.hasUrls():
            s = ""

        return super().dropMimeData(mimeData, action, row, column, parentIndex)


class MapViewExpressionContextGenerator(QgsExpressionContextGenerator):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mMapView: Optional[MapView] = None

    def setMapView(self, mapView):
        self.mMapView = mapView

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext([QgsExpressionContextUtils.projectScope(QgsProject.instance())])

        if False and isinstance(self.mMapView, MapView):
            canvas = self.mMapView.currentMapCanvas()
            context.appendScope(canvas.expressionContextScope())
        # self._context = context
        return context


class MapView(QFrame):
    """
    A MapView defines how a single map canvas visualizes sensor specific EOTS data plus additional vector overlays
    """
    # sigVisibilityChanged = pyqtSignal(bool)
    sigCanvasAppearanceChanged = pyqtSignal()
    sigCrosshairChanged = pyqtSignal()
    sigTitleChanged = pyqtSignal(str)
    sigCurrentLayerChanged = pyqtSignal(QgsMapLayer)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def __init__(self, name='Map View', parent=None):
        super(MapView, self).__init__(parent)
        loadUi(DIR_UI / 'mapview.ui', self)
        # self.setupUi(self)

        settings = EOTSVSettingsManager.settings()
        self.mMapBackgroundColor: QColor = settings.mapBackgroundColor
        self.mMapTextFormat: QgsTextFormat = QgsTextFormat(settings.mapTextFormat)
        self.mMapWidget = None

        # self.mLayerStyleInitialized: Dict[str, bool] = dict()

        self.mTimeSeries = None
        self.mSensorLayerList = list()
        self.mCrossHairStyle = CrosshairStyle()
        self.mCrossHairStyle.setVisibility(False)

        m = QMenu(self.btnToggleCrosshair)
        m.addAction(self.actionSetCrosshairStyle)

        self.btnToggleCrosshair.setMenu(m)
        self.btnToggleCrosshair.setDefaultAction(self.actionToggleCrosshairVisibility)
        self.btnToggleCrosshair.setChecked(self.crosshairStyle().mShow)
        self.btnToggleMapViewVisibility.setDefaultAction(self.actionToggleMapViewHidden)

        self.tbName.textChanged.connect(self.onTitleChanged)

        self.actionSetCrosshairStyle.triggered.connect(self.onChangeCrosshairStyle)
        self.actionToggleMapViewHidden.toggled.connect(self.sigCanvasAppearanceChanged)
        self.actionToggleCrosshairVisibility.toggled.connect(self.setCrosshairVisibility)

        self.actionAddMapLayer.triggered.connect(lambda *args: self.onAddMapLayer())
        self.actionAddVectorLayer.triggered.connect(lambda *args: self.onAddMapLayer(QgsMapLayerProxyModel.VectorLayer))
        self.actionAddRasterLayer.triggered.connect(lambda *args: self.onAddMapLayer(QgsMapLayerProxyModel.RasterLayer))
        self.btnAddLayer.setDefaultAction(self.actionAddMapLayer)
        m = QMenu()
        m.addAction(self.actionAddVectorLayer)
        m.addAction(self.actionAddRasterLayer)
        self.btnAddLayer.setMenu(m)

        self.btnHighlightMapView.setDefaultAction(self.actionHighlightMapView)
        self.actionHighlightMapView.triggered.connect(lambda: self.setHighlighted(True, timeout=500))

        assert isinstance(self.mLayerTreeView, QgsLayerTreeView)

        self.mDummyCanvas = QgsMapCanvas()  # dummy map canvas for dummy layers
        self.mDummyCanvas.setVisible(False)

        self.mLayerTree = QgsLayerTree()
        self.mLayerTreeMapCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mLayerTree, self.mDummyCanvas)

        # self.mLayerTreeModel = QgsLayerTreeModel(self.mLayerTree)
        self.mLayerTreeModel = MapViewLayerTreeModel(self.mLayerTree)

        self.mLayerTreeModel.setFlags(QgsLayerTreeModel.AllowNodeChangeVisibility
                                      | QgsLayerTreeModel.AllowNodeRename
                                      | QgsLayerTreeModel.AllowNodeReorder)

        self.mLayerTreeSensorNode: Optional[QgsLayerTreeGroup] = None
        self._createSensorNode()
        self.mLayerTreeView: QgsLayerTreeView
        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeView.currentLayerChanged.connect(self.sigCurrentLayerChanged.emit)
        self.mMapLayerTreeViewMenuProvider = MapViewLayerTreeViewMenuProvider(self, self.mLayerTreeView,
                                                                              self.mDummyCanvas)

        # register some actions that interact with other GUI elements
        # self.mMapLayerTreeViewMenuProvider.actionAddEOTSVSpectralProfiles.triggered.connect(self.addSpectralProfileLayer)
        # self.mMapLayerTreeViewMenuProvider.actionAddEOTSVTemporalProfiles.triggered.connect(self.addTemporalProfileLayer)

        self.mLayerTreeView.setMenuProvider(self.mMapLayerTreeViewMenuProvider)
        self.mLayerTreeView.currentLayerChanged.connect(self.setCurrentLayer)
        self.mLayerTree.removedChildren.connect(self.onChildNodesRemoved)

        self.mIsVisible = True
        self.setTitle(name)
        self.tbInfoExpression: QLineEdit
        self.mDefaultInfoExpressionToolTip: str = self.tbInfoExpression.toolTip()

        self.tbInfoExpression.textChanged.connect(self.onMapInfoExpressionChanged)
        self.btnShowInfoExpression.setDefaultAction(self.optionShowInfoExpression)
        self.optionShowInfoExpression.toggled.connect(self.tbInfoExpression.setEnabled)
        self.optionShowInfoExpression.toggled.connect(self.actionSetInfoExpression.setEnabled)
        self.btnSetInfoExpression.setDefaultAction(self.actionSetInfoExpression)
        self.actionSetInfoExpression.triggered.connect(self.onSetInfoExpression)

        self._fakeLyr: QgsVectorLayer = QgsVectorLayer("point?crs=epsg:4326", "Scratch point layer", "memory")

        # self.tbInfoExpression.setLayer(self.mLyr)

        # self.mExpressionContextGenerator = MapViewExpressionContextGenerator()
        # self.mExpressionContextGenerator.setMapView(self)

        self.tbInfoExpression.setEnabled(self.optionShowInfoExpression.isChecked())

        # self.tbInfoExpression.registerExpressionContextGenerator(self.mExpressionContextGenerator)
        self.optionShowInfoExpression.toggled.connect(self.sigCanvasAppearanceChanged)
        # self.tbInfoExpression.expressionChanged.connect(self.sigCanvasAppearanceChanged)
        for action in m.actions():
            action.toggled.connect(self.sigCanvasAppearanceChanged)

        fixMenuButtons(self)

    def setInfoExpressionError(self, error: str):

        if error in ['', None]:
            self.tbInfoExpression.setStyleSheet('')
            self.tbInfoExpression.setToolTip(self.mDefaultInfoExpressionToolTip)
        else:

            self.tbInfoExpression.setStyleSheet('QLineEdit#tbInfoExpression{color:red; border: 2px solid red;}')
            self.tbInfoExpression.setToolTip(f'<span style="color:red">{error}</span>')

    def onMapInfoExpressionChanged(self, text: str):

        self.sigCanvasAppearanceChanged.emit()
        s = ""

    def onSetInfoExpression(self, *args):

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self._fakeLyr))
        c = self.currentMapCanvas()
        if isinstance(c, MapCanvas):
            context.appendScope(QgsExpressionContextScope(c.expressionContextScope()))
        expression = self.tbInfoExpression.text()
        # taken from qgsfeaturefilterwidget.cpp : void QgsFeatureFilterWidget::filterExpressionBuilder()
        dlg = QgsExpressionBuilderDialog(self._fakeLyr, expression,
                                         self,
                                         'generic', context)
        dlg.setWindowTitle('Expression Based Filter')
        # myDa = QgsDistanceArea()
        # myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        # myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        # dlg.setGeomCalculator(myDa)

        if dlg.exec() == QDialog.Accepted:
            self.tbInfoExpression.setText(dlg.expressionText())

    def __iter__(self) -> Iterator[TimeSeriesDate]:
        return iter(self.mapCanvases())

    MKeyName = 'name'
    MKeyTextFormat = 'text_format'
    MKeyTextExpression = 'text_expression'
    MKeyBGColor = 'map_background_color'
    MKeyIsVisible = 'visible'
    MKeySensorStyle = 'sensor_styles'

    def asMap(self) -> dict:

        sensor_styles = dict()

        for lyr in self.sensorProxyLayers():
            sid = lyr.source()

            categories = QgsMapLayer.StyleCategory.Symbology
            if lyr.customProperty(SensorInstrument.PROPERTY_KEY_STYLE_INITIALIZED, defaultValue=False):
                categories = categories | QgsMapLayer.StyleCategory.Rendering

            sensor_styles[sid] = {
                'xml': layerStyleString(lyr, categories=categories),
                'initialized': lyr.customProperty(SensorInstrument.PROPERTY_KEY_STYLE_INITIALIZED)
            }

        d = {self.MKeyName: self.name(),
             self.MKeyTextFormat: self.mapTextFormat().toMimeData().text(),
             self.MKeyBGColor: self.mapBackgroundColor().name(),
             self.MKeyIsVisible: self.isVisible(),
             self.MKeyTextExpression: self.mapInfoExpression(),
             self.MKeySensorStyle: sensor_styles,
             }

        return d

    def fromMap(self, data: dict):

        if name := data.get(self.MKeyName):
            self.setName(name)

        if bg := data.get(self.MKeyBGColor):
            self.setMapBackgroundColor(QColor(bg))

        if expr := data.get(self.MKeyTextExpression):
            self.setMapInfoExpression(expr)

        if fmt := data.get(self.MKeyTextFormat):
            md = QMimeData()
            md.setText(fmt)
            textFormat, success = QgsTextFormat.fromMimeData(md)
            if success:
                self.setMapTextFormat(textFormat)

        if b := data.get(self.MKeyIsVisible):
            self.setVisibility(b)

        if sensor_styles := data.get(self.MKeySensorStyle):

            for sid, style_dict in sensor_styles.items():
                lyr = self.sensorProxyLayer(sid)
                if isinstance(lyr, QgsRasterLayer):
                    if styleXml := style_dict.get('xml', None):
                        setLayerStyleString(lyr, styleXml,
                                            categories=STYLE_CATEGORIES)

                    # the style (render settings etc.) was initialized on a map canvas
                    # if not, it will be stretched to the first map canvas
                    is_initialized = style_dict.get('initialized', False) is True
                    lyr.setCustomProperty(SensorInstrument.PROPERTY_KEY_STYLE_INITIALIZED, is_initialized)

    def setName(self, name: str):
        self.setTitle(name)

    def name(self) -> str:
        return self.title()

    def setMapInfoExpression(self, expression: str):
        self.tbInfoExpression.setText(expression)

    def mapInfoExpression(self) -> str:

        return f'{self.tbInfoExpression.text()}'.strip()

    def setMapTextFormat(self, textformat: QgsTextFormat) -> QgsTextFormat:
        if not equalTextFormats(self.mapTextFormat(), textformat):
            self.mMapTextFormat = textformat
            self.sigCanvasAppearanceChanged.emit()
        return self.mapTextFormat()

    def mapTextFormat(self) -> QgsTextFormat:
        return self.mMapTextFormat

    def mapBackgroundColor(self) -> QColor:
        """
        Returns the map background color
        :return: QColor
        """
        return self.mMapBackgroundColor

    def setMapBackgroundColor(self, color: QColor) -> QColor:
        """
        Sets the map background color
        :param color: QColor
        :return: QColor
        """
        if self.mMapBackgroundColor != color:
            self.mMapBackgroundColor = color
            self.sigCanvasAppearanceChanged.emit()
        return self.mMapBackgroundColor

    def onAddMapLayer(self, filter: QgsMapLayerProxyModel.Filter = QgsMapLayerProxyModel.All):
        """
        Slot that opens a SelectMapLayersDialog for any kind of layer
        """
        from .qgispluginsupport.qps.utils import SelectMapLayersDialog
        d = SelectMapLayersDialog()

        if filter == QgsMapLayerProxyModel.All:
            title = 'Select Layer'
            text = 'Layer'
        elif filter == QgsMapLayerProxyModel.RasterLayer:
            title = 'Select Raster Layer'
            text = 'Raster'
        elif filter == QgsMapLayerProxyModel.VectorLayer:
            title = 'Select Vector Layer'
            text = 'Vector'
        else:
            text = title = ''
        d.setWindowTitle(title)
        d.addLayerDescription(text, filter)
        if d.exec() == QDialog.Accepted:
            for lyr in d.mapLayers():
                self.addLayer(lyr)

    def setCurrentLayer(self, layer: QgsMapLayer):
        """
        Sets the QgsMapCanvas.currentLayer() that is used by some QgsMapTools
        :param layer: QgsMapLayer | None
        :return:
        """
        assert layer is None or isinstance(layer, QgsMapLayer)
        if layer in self.layers():
            self.mLayerTreeView.setCurrentLayer(layer)

            if layer not in self.mSensorLayerList:
                for c in self.mapCanvases():
                    c.setCurrentLayer(layer)
            return True

    def addSpectralProfileLayers(self):
        """Adds the EOTSV Spectral Profile Layers"""
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        tsv = EOTimeSeriesViewer.instance()
        if isinstance(tsv, EOTimeSeriesViewer):
            for lyr in tsv.spectralLibraries():
                if lyr not in self.layers():
                    self.addLayer(lyr)

    def addTemporalProfileLayer(self):
        """Adds the EOTSV Temporal Profile Layer"""
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        tsv = EOTimeSeriesViewer.instance()
        if isinstance(tsv, EOTimeSeriesViewer):
            lyr = tsv.temporalProfileLayer()
            if lyr not in self.layers():
                self.addLayer(lyr)

    def addLayer(self, layer: QgsMapLayer):
        """
        Add a QgsMapLayer to the MapView layer tree
        :param layer: QgsMapLayer
        """
        if isinstance(layer, QgsVectorLayer):
            self.mLayerTree.insertLayer(0, layer)
        else:
            self.mLayerTree.addLayer(layer)

    def _createSensorNode(self):
        self.mLayerTreeSensorNode = QgsLayerTreeGroup(name='Raster Time Series', checked=True)
        self.mLayerTreeSensorNode.setCustomProperty(KEY_LOCKED_LAYER, True)
        self.mLayerTreeSensorNode.setCustomProperty(KEY_SENSOR_GROUP, True)
        self.mLayerTree.addChildNode(self.mLayerTreeSensorNode)

    def _containsSensorNode(self, root: QgsLayerTreeGroup) -> bool:
        assert isinstance(root, QgsLayerTreeGroup)
        if root.customProperty(KEY_SENSOR_GROUP) in [True, 'true']:
            return True
        for grp in root.findGroups():
            if self._containsSensorNode(grp):
                return True
        return False

    def onChildNodesRemoved(self, node, idxFrom, idxTo):
        if not self._containsSensorNode(self.mLayerTreeModel.rootGroup()):
            self._createSensorNode()

    def onChangeCrosshairStyle(self):

        canvases = self.mapCanvases()
        if len(canvases) > 0:
            mapCanvas = canvases[0]
        else:
            mapCanvas = None

        style = getCrosshairStyle(parent=self, crosshairStyle=self.crosshairStyle(), mapCanvas=mapCanvas)
        if isinstance(style, CrosshairStyle):
            self.setCrosshairStyle(style)

    def setVisibility(self, b: bool):
        """
        Sets the map view visibility
        :param b: bool
        """
        assert isinstance(b, bool)

        changed = False

        if self.actionToggleMapViewHidden.isChecked() == b:
            self.actionToggleMapViewHidden.setChecked(not b)

        if changed:
            self.sigCanvasAppearanceChanged.emit()

    def isVisible(self) -> bool:
        """
        Returns the map view visibility
        :return: bool
        """
        return not self.actionToggleMapViewHidden.isChecked()

    def mapWidget(self):
        return self.mMapWidget

    def mapCanvases(self) -> List[MapCanvas]:
        """
        Returns the MapCanvases related to this map view. Requires that this mapview was added to a MapWidget
        :return: [list-of-MapCanvases]
        """

        if isinstance(self.mMapWidget, MapWidget):
            return self.mMapWidget.mapViewCanvases(self)
        else:
            return []

    def onTitleChanged(self, *args):

        self.setWindowTitle('Map View "{}"'.format(self.title()))
        self.sigTitleChanged.emit(self.title())
        self.sigCanvasAppearanceChanged.emit()

    def setMapWidget(self, w):
        if isinstance(w, MapWidget):
            self.mMapWidget = w
        else:
            self.mMapWidget = None

    def setTimeSeries(self, timeSeries: TimeSeries):
        """
        Conntects the MapView with a TimeSeries.
        :param timeSeries: TimeSeries
        """
        assert isinstance(timeSeries, TimeSeries)
        if self.mTimeSeries == timeSeries:
            return

        for s in self.sensors():
            self.removeSensor(s)

        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensor)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensor)
        for s in timeSeries.sensors():
            self.addSensor(s)

    def timeSeries(self) -> TimeSeries:
        """
        Returns the TimeSeries this mapview is connected with
        :return: TimeSeries
        """
        return self.mTimeSeries

    def setTitle(self, title: str):
        """
        Sets the widget title
        :param title: str
        """
        old = self.title()
        if old != title:
            self.tbName.setText(title)

    def visibleLayers(self) -> List[QgsMapLayer]:
        """
        Returns the visible layers, including proxy layer for time-series data
        :return: [list-of-QgsMapLayers]
        """
        return [l for l in self.mLayerTree.checkedLayers() if isinstance(l, QgsMapLayer)]

    def layers(self) -> List[QgsMapLayer]:
        """
        Returns all layers, including invisible or proxy layers for time-series data
        :return: [list-of-QgsMapLayers]
        """
        nodes = self.mLayerTree.findLayers()
        return [n.layer() for n in nodes if isinstance(n.layer(), QgsMapLayer)]

    def layerTree(self) -> QgsLayerTree:
        return self.mLayerTree

    def layerTreeView(self) -> QgsLayerTreeView:
        return self.mLayerTreeView

    def title(self, maskNewLines=True) -> str:
        """
        Returns the MapView title
        :return: str
        """
        if maskNewLines:
            return self.tbName.text().replace('\\n', ' ').strip()
        else:
            return self.tbName.text().strip()

    def setCrosshairStyle(self, crosshairStyle: CrosshairStyle) -> CrosshairStyle:
        """
        Seths the CrosshairStyle of this MapView
        :param crosshairStyle: CrosshairStyle
        """

        if self.mCrossHairStyle != crosshairStyle:
            self.mCrossHairStyle = crosshairStyle
            self.sigCrosshairChanged.emit()

        return self.mCrossHairStyle

    def setHighlighted(self, b=True, timeout: int = 1000):
        """
        Activates or deactivates a red-line border of the MapCanvases
        :param b: True | False to activate / deactivate the highlighted lines-
        :param timeout: int, milliseconds how long the highlighted frame should appear
        """
        styleOn = """.MapCanvas {
                    border: 4px solid red;
                    border-radius: 4px;
                }"""
        styleOff = """"""
        if b is True:
            for mapCanvas in self.mapCanvases():
                mapCanvas.setStyleSheet(styleOn)
            if timeout > 0:
                QTimer.singleShot(timeout, lambda: self.setHighlighted(False))
        else:
            for mapCanvas in self.mapCanvases():
                mapCanvas.setStyleSheet(styleOff)

    def currentMapCanvas(self) -> Optional[MapCanvas]:
        """
        Returns the MapCanvas that was clicked / used last
        :return: MapCanvas
        """
        if not isinstance(self.mMapWidget, MapWidget):
            return None
        canvases = sorted(self.mMapWidget.mapViewCanvases(self),
                          key=lambda c: c.property(KEY_LAST_CLICKED))
        if len(canvases) == 0:
            return None
        else:
            return canvases[-1]

    def currentLayer(self) -> QgsMapLayer:
        """
        Returns the current map layer, i.e. that selected in the map layer tree view.
        If this is a proxy layer, the MapView will try to return a "real" layer from a MapCanvas


        :return: QgsMapLayer
        """
        cl = self.mLayerTreeView.currentLayer()
        if sid := sensor_id(cl):
            canvases = [c for c in self.mapCanvases()
                        if isinstance(c.tsd(), TimeSeriesDate) and c.tsd().sensor().id() == sid]
            canvases = sorted(canvases, key=lambda c: c is not self.currentMapCanvas())
            for c in canvases:
                for lyr in c.layers():
                    if has_sensor_id(lyr):
                        return lyr
        return cl

    def crosshairStyle(self) -> CrosshairStyle:
        """
        Returns the CrosshairStyle
        :return: CrosshairStyle
        """
        return self.mCrossHairStyle

    def setCrosshairVisibility(self, b: bool):
        """
        Enables / diables the map canvas crosshair.
        :param b: bool
        """
        if b != self.actionToggleCrosshairVisibility.isChecked():
            self.actionToggleCrosshairVisibility.setChecked(b)
        else:
            self.mCrossHairStyle.setVisibility(b)
            self.sigCrosshairChanged.emit()

    def sensorProxyLayers(self) -> List[QgsRasterLayer]:
        layers = [n.layer() for n in self.mLayerTreeSensorNode.findLayers()]
        layers = [lyr for lyr in layers if
                  isinstance(lyr, QgsRasterLayer) and isinstance(lyr.dataProvider(), SensorMockupDataProvider)]
        for lyr in layers:
            assert lyr.customProperty(SensorInstrument.PROPERTY_KEY)
        return layers

    def sensorProxyLayer(self, sensor: Union[SensorInstrument, str]) -> Optional[QgsRasterLayer]:
        """
        Returns the proxy layer related to a SensorInstrument
        :param sensor: SensorInstrument
        :return: SensorLayer
        """
        if isinstance(sensor, SensorInstrument):
            sensor = sensor.id()
        for lyr in self.sensorProxyLayers():
            if lyr.customProperty(SensorInstrument.PROPERTY_KEY) == sensor:
                return lyr
        return None

    def sensorLayers(self, sensor_id: Optional[str] = None) -> List[QgsRasterLayer]:
        """
        :param sensor_id:
        :return:
        """
        layers = []
        for c in self.mapCanvases():
            layers.extend([lyr for lyr in c.layers() if has_sensor_id(lyr)])
        if sensor_id:
            layers = [lyr for lyr in layers if lyr.customProperty(SensorInstrument.PROPERTY_KEY) == sensor_id]
        return layers

    def sensors(self) -> List[SensorInstrument]:
        """
        Returns a list of SensorsInstruments
        :return: [list-of-SensorInstruments]
        """
        return [t[0] for t in self.mSensorLayerList]

    def addSensor(self, sensor: SensorInstrument):
        """
        Adds a SensorInstrument to be shown in this MapView. Each sensor will be represented as a Raster Layer in the
        Layer Tree Model.
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor not in self.sensors():
            sensor.sigNameChanged.connect(self.sigCanvasAppearanceChanged)

            masterLayer: QgsRasterLayer = sensor.proxyRasterLayer()
            if not (isinstance(masterLayer, QgsRasterLayer) and masterLayer.isValid()):
                s = ""
            assert isinstance(masterLayer, QgsRasterLayer) and masterLayer.isValid()
            assert isinstance(masterLayer.renderer(), QgsRasterRenderer)

            self.mSensorLayerList.append((sensor, masterLayer))
            masterLayer.styleChanged.connect(lambda *args, v=self, l=masterLayer: self.onMasterStyleChanged(l))
            masterLayer.nameChanged.connect(self.onMasterLyrNameChanged)
            layerTreeLayer: QgsLayerTreeLayer = self.mLayerTreeSensorNode.addLayer(masterLayer)
            layerTreeLayer.setCustomProperty(KEY_LOCKED_LAYER, True)
            # layerTreeLayer.setCustomProperty(KEY_SENSOR_LAYER, True)

            dummyLayers = self.mDummyCanvas.layers() + [masterLayer]
            self.mDummyCanvas.setLayers(dummyLayers)

            # self.mLayerStyleInitialized[sensor.id()] = False

    def onMasterLyrNameChanged(self, *args):
        lyr = self.sender()
        newname = lyr.name()
        ltn = self.mLayerTreeSensorNode.findLayer(lyr)
        # print(ltn.name())

    def onMasterStyleChanged(self, masterLayer: QgsRasterLayer):

        assert has_sensor_id(masterLayer)
        sid = sensor_id(masterLayer)

        if isinstance(sid, str):

            styleXml = layerStyleString(masterLayer,
                                        categories=STYLE_CATEGORIES)
            for lyr in self.sensorLayers(sid):
                copyMapLayerStyle(styleXml, lyr)

            # for c in self.sensorCanvases(sid):
            #    assert isinstance(c, MapCanvas)
            #    c.addToRefreshPipeLine(MapCanvas.Command.RefreshRenderer)

            # self.mLayerStyleInitialized[sid] = True

    def sensorCanvases(self, sensor: Union[str, SensorInstrument]) -> List[MapCanvas]:
        """
        Returns the MapCanvases that show a layer with data for the given ``sensor``
        :param sensor: SensorInstrument
        :return:
        """
        if isinstance(sensor, SensorInstrument):
            sensor = sensor.id()
        return [c for c in self.mapCanvases() if isinstance(c, MapCanvas)
                and isinstance(c.tsd(), TimeSeriesDate) and c.tsd().sensor().id() == sensor]

    def sensorLayer(self, sensor: SensorInstrument):
        """
        Returns the QgsRasterLayer that is used as proxy to specify the QgsRasterRenderer for a sensor
        :param sensor: SensorInstrument
        :return: QgsRasterLayer
        """
        assert isinstance(sensor, SensorInstrument)
        for t in self.mSensorLayerList:
            s, l = t
            assert isinstance(s, SensorInstrument)
            assert isinstance(l, QgsRasterLayer)
            if s == sensor:
                return l
        raise Exception('Sensor "{}" not registered to MapView "{}"'.format(sensor.name(), self.title()))

    def removeSensor(self, sensor: SensorInstrument):
        """
        Removes a sensor from this map view
        :param sensor:
        :return:
        """
        # if sensor in self.mLayerStyleInitialized.keys():
        #    self.mLayerStyleInitialized.pop(sensor)

        toRemove = []
        for t in self.mSensorLayerList:
            if t[0] == sensor:
                toRemove.append(t)

        for t in toRemove:
            sensor, sensorLayer = t
            sensorLayer.setDataSource('', '', 'gdal')
            self.mLayerTree.removeLayer(sensorLayer)
            self.mLayerTreeSensorNode.removeLayer(sensorLayer)
            self.mLayerTreeMapCanvasBridge.setCanvasLayers()
            self.mSensorLayerList.remove(t)

    def hasSensor(self, sensor: SensorInstrument) -> bool:
        """
        :param sensor:
        :return:
        """
        assert isinstance(sensor, SensorInstrument)
        return sensor in self.sensors()


class MapViewLayerTreeViewMenuProvider(QgsLayerTreeViewMenuProvider):

    def __init__(self, mapView, view: QgsLayerTreeView, canvas: QgsMapCanvas):
        super(MapViewLayerTreeViewMenuProvider, self).__init__()
        assert isinstance(view, QgsLayerTreeView)
        assert isinstance(canvas, QgsMapCanvas)
        self.mLayerTreeView: QgsLayerTreeView = view
        self.mDummyCanvas: QgsMapCanvas = canvas
        # self.mDefActions = QgsLayerTreeViewDefaultActions(self.mLayerTreeView)
        self.mMapView: MapView = mapView
        # self.actionAddGroup = self.mDefActions.actionAddGroup()
        # self.actionRename = self.mDefActions.actionRenameGroupOrLayer()
        # self.actionRemove = self.mDefActions.actionRemoveGroupOrLayer()
        # self.actionZoomToLayer = self.mDefActions.actionZoomToGroup(self.mDummyCanvas)
        # self.actionCheckAndAllChildren = self.mDefActions.actionCheckAndAllChildren()
        # self.actionShowFeatureCount = self.mDefActions.actionShowFeatureCount()
        # self.actionZoomToLayer = self.mDefActions.actionZoomToLayer(self.mDummyCanvas)
        # self.actionZoomToSelected = self.mDefActions.actionZoomToSelection(self.mDummyCanvas)
        # self.actionZoomToGroup = self.mDefActions.actionZoomToGroup(self.mDummyCanvas)
        # self.actionAddEOTSVSpectralProfiles = QAction('Add Spectral Profile Layer')
        # self.actionAddEOTSVTemporalProfiles = QAction('Add Temporal Profile Layer')

    def mapView(self) -> MapView:
        return self.mMapView

    def layerTreeView(self) -> QgsLayerTreeView:
        return self.mLayerTreeView

    def layerTree(self) -> QgsLayerTree:
        return self.layerTreeModel().rootGroup()

    def layerTreeModel(self) -> QgsLayerTreeModel:
        return self.layerTreeView().layerTreeModel()

    def onRemoveLayers(self):
        selected = self.layerTreeView().selectedLayers()
        for lyr in selected:
            if not has_sensor_id(lyr):
                self.mapView().mLayerTree.removeLayer(lyr)

    def onSetCanvasCRS(self):
        s = ""
        lyr = self.layerTreeView()

    def onZoomToLayer(self, layer: QgsMapLayer):
        extent = SpatialExtent.fromLayer(layer)
        if isinstance(extent, SpatialExtent):
            extent = extent.toCrs(self.mapView().mapWidget().crs())
            self.mapView().mapWidget().setSpatialExtent(extent)

    def onZoomActualSize(self):
        current = self.mapView().currentLayer()
        if isinstance(current, QgsRasterLayer):
            s = ""

    def onStretchToExtent(self):

        canvas = self.mapView().currentMapCanvas()
        if not isinstance(canvas, MapCanvas):
            return

        current = self.mapView().currentLayer()
        csid = sensor_id(current)
        if csid:
            for lyr in canvas.layers():
                sid = sensor_id(lyr)
                if sid == csid:
                    b = canvas.stretchToExtent(layer=lyr)
                    if not b:
                        s = ""
                    break

        elif isinstance(current, QgsRasterLayer):
            canvas.stretchToExtent(layer=current)

    def createContextMenu(self) -> QMenu:

        model = self.layerTreeModel()
        ltree = self.layerTree()
        view: QgsLayerTreeView = self.layerTreeView()
        currentGroup = view.currentGroupNode()
        currentLayer = view.currentLayer()
        currentIndex = view.currentIndex()

        currentCanvas = self.mapView().currentMapCanvas()
        isSensorGroup = isinstance(currentGroup, QgsLayerTreeGroup) and currentGroup.customProperty(
            KEY_SENSOR_GROUP) in [True, 'true']
        isSensorLayer = isinstance(sensor_id(currentLayer), str)
        mv: MapView = self.mapView()
        mw: MapWidget = mv.mapWidget()
        mw.setCurrentMapView(mv)
        if isSensorLayer:
            # the current layer is an "empty" proxy layer. use one from a visible map canvas instead
            pass

        from eotimeseriesviewer.main import EOTimeSeriesViewer
        eotsv = EOTimeSeriesViewer.instance()
        if not isinstance(eotsv, EOTimeSeriesViewer):
            return
        menu = QMenu(view)
        assert isinstance(mw, MapWidget)
        if isinstance(currentLayer, QgsMapLayer):
            a = menu.addAction('Rename')
            a.triggered.connect(lambda *args, cidx=currentIndex: view.edit(cidx))
            menu.addSeparator()

            # zoom to layer
            menu.addAction(eotsv.actionZoomToLayer())

            # rename layer
            #

            # zoom to native resolution
            # in this case not using a map tool but the current layer
            ref = eotsv.actionZoomActualSize()
            a = menu.addAction(ref.text())
            a.setIcon(ref.icon())
            a.triggered.connect(self.onZoomActualSize)

            if isinstance(currentLayer, QgsRasterLayer):
                a = menu.addAction('&Stretch Using Current Extent')
                a.triggered.connect(self.onStretchToExtent)

            # ----
            menu.addSeparator()
            a = menu.addAction('Add Spectral Library Layer')
            a.triggered.connect(self.mapView().addSpectralProfileLayers)

            a = menu.addAction('Add Temporal Profile Layer')
            a.triggered.connect(self.mapView().addTemporalProfileLayer)

            # ----
            menu.addSeparator()
            # duplicate layer
            # remove layer

            a = menu.addAction('Remove layer')
            a.setToolTip('Remove layer(s)')
            a.triggered.connect(self.onRemoveLayers)

            menu.addSeparator()
            if isinstance(currentLayer, QgsVectorLayer):
                menu.addAction(eotsv.actionOpenTable())
                menu.addAction(eotsv.actionToggleEditing())

            menu.addSeparator()
            # ----------
            # set CRS
            action = menu.addAction('Set layer CRS to map canvas')
            action.triggered.connect(self.onSetCanvasCRS)

            # ----
            # Export...
            # ------
            menu.addSeparator()
            # Styles...
            a: QAction = eotsv.actionPasteLayerStyle()

            menu.addAction(a)
            a: QAction = eotsv.actionCopyLayerStyle()
            menu.addAction(a)

            # Properties
            menu.addSeparator()
            menu.addAction(eotsv.actionLayerProperties())

        menu.addSeparator()
        return menu

    def vectorLayerTools(self) -> VectorLayerTools:

        from eotimeseriesviewer.main import EOTimeSeriesViewer
        return EOTimeSeriesViewer.instance().mVectorLayerTools

    def showAttributeTable(self, lyr: QgsVectorLayer):

        from eotimeseriesviewer.main import EOTimeSeriesViewer
        tsv = EOTimeSeriesViewer.instance()
        if isinstance(tsv, EOTimeSeriesViewer):
            tsv.showAttributeTable(lyr)
        s = ""

    def onSetLayerProperties(self, lyr: QgsRasterLayer, canvas: QgsMapCanvas):
        if isinstance(canvas, MapCanvas):
            canvas.onSetLayerProperties(lyr)


class MapViewListModel(QAbstractListModel):
    """
    A model to store a list of map views.

    """
    sigMapViewsAdded = pyqtSignal(list)
    sigMapViewsRemoved = pyqtSignal(list)

    def __init__(self, parent=None):
        super(MapViewListModel, self).__init__(parent)
        self.mMapViewList = []

    def addMapView(self, mapView):
        i = len(self.mMapViewList)
        self.insertMapView(i, mapView)

    def insertMapView(self, i, mapView):
        self.insertMapViews(i, [mapView])

    def insertMapViews(self, i, mapViews):
        assert isinstance(mapViews, list)
        assert i >= 0 and i <= len(self.mMapViewList)

        self.beginInsertRows(QModelIndex(), i, i + len(mapViews) - 1)

        for j in range(len(mapViews)):
            mapView = mapViews[j]
            assert isinstance(mapView, MapView)
            mapView.sigTitleChanged.connect(
                lambda: self.doRefresh([mapView])
            )
            self.mMapViewList.insert(i + j, mapView)
        self.endInsertRows()
        self.sigMapViewsAdded.emit(mapViews)

    def doRefresh(self, mapViews: List[MapView]):
        for mapView in mapViews:
            idx = self.mapView2idx(mapView)
            self.dataChanged.emit(idx, idx)

    def removeMapView(self, mapView: MapView):
        self.removeMapViews([mapView])

    def removeMapViews(self, mapViews: List[MapView]):
        assert isinstance(mapViews, list)
        for mv in mapViews:
            assert mv in self.mMapViewList
            idx = self.mapView2idx(mv)
            self.beginRemoveRows(idx.parent(), idx.row(), idx.row())
            self.mMapViewList.remove(mv)
            self.endRemoveRows()
        self.sigMapViewsRemoved.emit(mapViews)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mMapViewList)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1

    def idx2MapView(self, index):
        if isinstance(index, QModelIndex):
            if index.isValid():
                index = index.row()
            else:
                return None
        assert index >= 0 and index < len(self.mMapViewList)
        return self.mMapViewList[index]

    def mapView2idx(self, mapView):
        assert isinstance(mapView, MapView)
        row = self.mMapViewList.index(mapView)
        return self.createIndex(row, 0, mapView)

    def __len__(self):
        return len(self.mMapViewList)

    def __iter__(self):
        return iter(self.mMapViewList)

    def __getitem__(self, slice):
        return self.mMapViewList[slice]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mMapViewList)) or (index.row() < 0):
            return None

        mapView = self.idx2MapView(index)
        assert isinstance(mapView, MapView)

        value = None

        if role == Qt.DisplayRole:
            value = '{} {}'.format(index.row() + 1, mapView.title())
        # if role == Qt.DecorationRole:
        # value = classInfo.icon(QSize(20,20))
        if role == Qt.UserRole:
            value = mapView
        return value


def closest_index(tsd_target: TimeSeriesDate, tsds: List[TimeSeriesDate]) -> Optional[int]:
    """
    Returns the index of the TimeSeriesDate closest to a target date
    :param tsd_target:
    :type tsd_target:
    :param tsds:
    :type tsds:
    :return:
    :rtype:
    """
    if len(tsds) == 0:
        return None
    if tsd_target in tsds:
        return tsds.index(tsd_target)
    else:
        for i, tsd2 in enumerate(tsds):
            if tsd2 < tsd_target:
                continue
            else:
                break
        return i


class MapWidget(QFrame):
    """
    This widget contains all maps
    """

    class ViewMode(enum.Enum):

        MapViewByRows = 1,
        MapViewByCols = 2

    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrosshairPositionChanged = pyqtSignal([QgsCoordinateReferenceSystem, QgsPointXY],
                                             [QgsCoordinateReferenceSystem, QgsPointXY, MapCanvas])
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)

    sigMapBackgroundColorChanged = pyqtSignal(QColor)
    sigMapTextColorChanged = pyqtSignal(QColor)
    sigMapTextFormatChanged = pyqtSignal(QgsTextFormat)
    sigMapsPerMapViewChanged = pyqtSignal(int, int)
    sigMapViewsChanged = pyqtSignal()
    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigCurrentLayerChanged = pyqtSignal(QgsMapLayer)
    # sigCurrentCanvasChanged = pyqtSignal(MapCanvas)
    # sigCurrentMapViewChanged = pyqtSignal(MapView)
    sigDateRangeChanged = pyqtSignal(object, object)
    sigCurrentDateChanged = pyqtSignal(TimeSeriesDate)
    sigCurrentLocationChanged = pyqtSignal([QgsCoordinateReferenceSystem, QgsPointXY],
                                           [QgsCoordinateReferenceSystem, QgsPointXY, QgsMapCanvas])
    sigVisibleDatesChanged = pyqtSignal(list)
    sigViewModeChanged = pyqtSignal(ViewMode)

    def __init__(self, *args, **kwds):
        super(MapWidget, self).__init__(*args, **kwds)
        loadUi(DIR_UI / 'mapwidget.ui', self)

        self.setContentsMargins(1, 1, 1, 1)
        self.mGridFrame: QFrame
        self.mGrid: QGridLayout
        assert isinstance(self.mGrid, QGridLayout)

        self.mSyncLock = False
        self.mSyncQGISMapCanvasCenter: bool = False
        self.mLastQGISMapCanvasCenter: SpatialPoint = None
        self.mLastEOTSVMapCanvasCenter: SpatialPoint = None
        self.mMaxNumberOfCachedLayers = 0

        self.mMapLayerStore = EOTimeSeriesViewerProject()
        self.mMapLayerCache = dict()
        self.mCanvasCache = dict()

        self.tbSliderDate: QLabel

        # self.mCurrentMapView: MapView = None
        # self.mCurrentMapCanvas: MapCanvas = None

        self.mMapViews: List[MapView] = []
        self.mCanvases: Dict[MapView, List[MapCanvas]] = dict()
        self.mCanvasSignals = dict()
        self.mTimeSeries: Optional[TimeSeries] = None

        self.mMapToolKey: MapTools = MapTools.Pan

        self.mViewMode = MapWidget.ViewMode.MapViewByRows
        self.mMapViewColumns: int = 3
        self.mMapViewRows: int = 1

        self.mSpatialExtent: SpatialExtent = SpatialExtent.world()
        self.mCrsInitialized: bool = False

        self.mCurrentDate: Optional[TimeSeriesDate] = None
        self.mCurrentDateMode: str = 'center'

        self.mCrosshairPosition: Optional[SpatialPoint] = None

        self.mMapSize = QSize(200, 200)

        self.mMapTextFormat = EOTSVSettingsManager.settings().mapTextFormat
        self.mMapRefreshTimer = QTimer(self)
        self.mMapRefreshTimer.timeout.connect(self.timedRefresh)
        self.mMapRefreshTimer.setInterval(500)
        self.mMapRefreshTimer.start()
        self.mMapRefreshBlock: bool = False

        # define shortcuts
        self.actionForward.setShortcuts([QKeySequence(QKeySequence.MoveToNextChar)])
        self.actionBackward.setShortcuts([QKeySequence(QKeySequence.MoveToPreviousChar)])

        self.actionForwardFast.setShortcuts([QKeySequence(QKeySequence.MoveToNextWord),
                                             QKeySequence(Qt.Key_D)])
        self.actionBackwardFast.setShortcuts([QKeySequence(QKeySequence.MoveToPreviousWord),
                                              QKeySequence(Qt.Key_A)])

        self.actionLastDate.setShortcuts([QKeySequence(QKeySequence.MoveToEndOfLine),
                                          QKeySequence('Alt+D')])

        self.actionFirstDate.setShortcuts([QKeySequence(QKeySequence.MoveToStartOfLine),
                                           QKeySequence('Alt+A')])

        self.btnFirst.setDefaultAction(self.actionFirstDate)
        self.btnLast.setDefaultAction(self.actionLastDate)
        self.btnBackward.setDefaultAction(self.actionBackward)
        self.btnForward.setDefaultAction(self.actionForward)
        self.btnBackwardFast.setDefaultAction(self.actionBackwardFast)
        self.btnForwardFast.setDefaultAction(self.actionForwardFast)

        self.actionFirstDate.triggered.connect(self.moveToFirstTSD)
        self.actionLastDate.triggered.connect(self.moveToLastTSD)
        self.actionBackward.triggered.connect(self.moveToPreviousTSD)
        self.actionForward.triggered.connect(self.moveToNextTSD)
        self.actionBackwardFast.triggered.connect(self.moveToPreviousTSDFast)
        self.actionForwardFast.triggered.connect(self.moveToNextTSDFast)

        self.mTimeSlider.setTickInterval(0)
        self.mTimeSlider.setTracking(False)
        self.mTimeSlider.valueChanged.connect(self.onSliderValueChanged)
        self.mTimeSlider.sliderMoved.connect(self.onSliderMoved)

        self.mBlockExtentChange: bool = False

    def close(self):

        # for c in self.mapCanvases():
        #    c.setLayers([])
        #    c.blockSignals(True)

        while len(self.mapViews()) > 0:

            mapView: MapView = self.mapViews()[0]
            debugLog(f'Remove map view {mapView}')
            sensors = list(mapView.sensors())
            for s in sensors:
                mapView.removeSensor(s)
            for c in mapView.mapCanvases():
                c.setLayers([])
            self.removeMapView(mapView)

        self._freeUnusedMapLayers()
        self.mMapRefreshTimer.stop()

        QgsApplication.processEvents()
        import gc
        gc.collect()
        # SensorMockupDataProvider.ALL_INSTANCES
        SensorMockupDataProvider._release_sip_deleted()

        self.mMapLayerCache.clear()
        self.mMapLayerStore.removeAllMapLayers()

        super().close()

    def clearCanvasGrid(self):
        """
        Cleans the MapCanvas Grid
        :return:
        :rtype:
        """
        assert isinstance(self.mGrid, QGridLayout)
        while self.mGrid.count() > 0:
            item = self.mGrid.takeAt(0)
            widget = item.widget()
            if isinstance(widget, QWidget):
                if isinstance(widget, MapCanvas):
                    self._disconnectCanvasSignals(widget)
                widget.setParent(None)

    def messageBar(self) -> QgsMessageBar:
        """
        Returns the QgsMessageBar
        :return: QgsMessageBar
        """
        return self.mMessageBar

    def refresh(self):
        debugLog()
        canvases = self.mapCanvases()
        for c in canvases:
            c.refresh()

    def setMapTextFormat(self, textFormat: QgsTextFormat) -> QgsTextFormat:

        if not equalTextFormats(textFormat, self.mMapTextFormat):
            self.mMapTextFormat = textFormat
            for mapView in self.mapViews():
                assert isinstance(mapView, MapView)
                mapView.setMapTextFormat(textFormat)
            self.sigMapTextFormatChanged.emit(self.mapTextFormat())
        return self.mapTextFormat()

    def mapTextFormat(self) -> QgsTextFormat:
        return self.mMapTextFormat

    def setMapTool(self, mapToolKey: MapTools):

        if self.mMapToolKey != mapToolKey:
            self.mMapToolKey = mapToolKey

            for c in self.mapCanvases():
                assert isinstance(c, MapCanvas)
                mts = c.mapTools()
                mts.activate(self.mMapToolKey)

    def visibleTSDs(self) -> List[TimeSeriesDate]:
        """
        Returns the list of currently shown TimeSeriesDates.
        :return: [list-of-TimeSeriesDates]
        """
        for mv in self.mMapViews:
            tsds = []
            for c in self.mCanvases[mv]:
                if isinstance(c.tsd(), TimeSeriesDate):
                    tsds.append(c.tsd())

            return sorted(tsds)
        return []

    def spatialExtent(self) -> SpatialExtent:
        """
        Returns the current SpatialExtent
        :return: SpatialExtent
        """
        for c in self.mapCanvases():
            ext = SpatialExtent.fromMapCanvas(c)
            self.mSpatialExtent = ext
            return ext
        # backup: latest spatial extent stored
        return self.mSpatialExtent

    def setSpatialExtent(self, *args) -> SpatialExtent:
        """
        Sets a SpatialExtent to all MapCanvases.
        Arguments can be those to construct a SpatialExtent
        :param extent: SpatialExtent
        :return: SpatialExtent the current SpatialExtent
        """

        if len(args) == 1 and type(args[0]) is QgsRectangle:
            extent = SpatialExtent(self.crs(), args[0])
        else:
            if isinstance(args[0], SpatialExtent):
                extent = args[0]
            else:
                extent = SpatialExtent(*args)

        try:
            assert isinstance(extent, SpatialExtent), \
                'Expected SpatialExtent, but got {} {}'.format(type(extent), extent)
        except Exception as ex:
            traceback.print_exception(*sys.exc_info())
            raise ex

        if self.mBlockExtentChange:
            return self.mSpatialExtent

        ext = extent.toCrs(self.crs())
        if not isinstance(ext, SpatialExtent):
            s = ""
            # last resort: zoom to CRS boundaries

        if isinstance(ext, SpatialExtent) and ext != self.mSpatialExtent:

            with BlockExtentChange(self) as blocker:
                self.mSpatialExtent = ext
                debugLog(f'new extent: {self.mSpatialExtent}')
                for c in self.mapCanvases():
                    assert isinstance(c, MapCanvas)
                    c.setSpatialExtent(ext)
                    c.refresh()
                    # c.addToRefreshPipeLine(self.mSpatialExtent)
            self.sigSpatialExtentChanged.emit(ext.__copy__())

        return ext

    def setSpatialCenter(self, *args):
        """
        Sets the spatial center of all MapCanvases
        :param centerNew: SpatialPoint
        """
        centerNew = SpatialPoint(*args)
        assert isinstance(centerNew, SpatialPoint)
        extent = self.spatialExtent()

        if isinstance(extent, SpatialExtent):
            centerOld = extent.center()
            centerNew = centerNew.toCrs(extent.crs())
            if centerNew != centerOld and isinstance(centerNew, SpatialPoint):
                extent = extent.__copy__()
                extent.setCenter(centerNew)
                debugLog()
                self.setSpatialExtent(extent)

    def spatialCenter(self) -> SpatialPoint:
        """
        Return the center of all map canvas
        :return: SpatialPoint
        """
        return self.spatialExtent().spatialCenter()

    def setCrs(self, crs: QgsCoordinateReferenceSystem) -> QgsCoordinateReferenceSystem:
        """
        Sets the MapCanvas CRS.
        :param crs: QgsCoordinateReferenceSystem
        :return: QgsCoordinateReferenceSystem
        """
        crs = QgsCoordinateReferenceSystem(crs)

        if self.crs() == crs:
            return crs

        if self.mBlockExtentChange:
            return self.crs()

        with BlockExtentChange(self) as blocker:
            canvases = self.mapCanvases()
            if len(canvases) > 0:
                for i, c in enumerate(self.mapCanvases()):
                    c.setDestinationCrs(crs)
                    if i == 0:
                        self.mSpatialExtent = SpatialExtent.fromMapCanvas(c)
            else:
                new_extent = self.mSpatialExtent.toCrs(crs)
                if isinstance(new_extent, SpatialExtent):
                    self.mSpatialExtent = new_extent
                else:
                    self.mSpatialExtent = SpatialExtent(QgsCoordinateReferenceSystem('EPSG:4326'),
                                                        crs.bounds()).toCrs(crs)
        self.sigCrsChanged.emit(crs)

        return self.crs()

    def timedRefresh(self) -> bool:
        """
        Calls the timedRefresh() routine for all MapCanvases
        """
        if self.mMapRefreshBlock:
            return False

        with Lock() as lock:
            # print('# TIMED REFRESH')
            self.mMapRefreshBlock = True
            # with MapWidgetTimedRefreshBlocker(self):

            if self.mSyncQGISMapCanvasCenter:
                self.syncQGISCanvasCenter()

            canvases = self.mapCanvases()

            for c in canvases:
                c.timedRefresh()

            for mapView in self.mapViews():
                # test for initial raster stretches
                for proxyLayer in mapView.sensorProxyLayers():
                    if proxyLayer.customProperty(SensorInstrument.PROPERTY_KEY_STYLE_INITIALIZED, defaultValue=False):
                        continue

                    sid = proxyLayer.customProperty(SensorInstrument.PROPERTY_KEY)
                    for c in mapView.mapCanvases():
                        if isinstance(c.tsd(), TimeSeriesDate) and c.tsd().sensor().id() == sid:
                            for lyr in c.layers():
                                if sensor_id(lyr) == sid:
                                    t0 = datetime.datetime.now()
                                    c.stretchToCurrentExtent(layer=lyr)

                                    dt = datetime.datetime.now() - t0
                                    # print(f'# stretch time:{dt.total_seconds(): 0.2f}s')

                                    proxyLayer.setCustomProperty(SensorInstrument.PROPERTY_KEY_STYLE_INITIALIZED, True)
            self.mMapRefreshBlock = False
        return True

    def layers(self) -> List[QgsMapLayer]:
        """Returns all QgsMapLayers that are shown in all map view layer trees"""
        layers = []
        for mv in self.mapViews():
            for lyr in mv.layers():
                if lyr not in layers:
                    layers.append(lyr)
        return layers

    def currentLayer(self) -> Optional[QgsMapLayer]:
        mv = self.currentMapView()
        if isinstance(mv, MapView):
            return mv.currentLayer()
        return None

    def currentMapCanvas(self) -> MapCanvas:
        """
        Returns the active map canvas, i.e. the MapCanvas that was clicked last.
        :return: MapCanvas
        """
        canvases = sorted(self.mapCanvases(), key=lambda c: c.property(KEY_LAST_CLICKED), reverse=True)
        if len(canvases) > 0:
            return canvases[0]
        else:
            return None

    def setCurrentMapCanvas(self, mapCanvas: MapCanvas):
        assert isinstance(mapCanvas, MapCanvas)
        canvases = self.mapCanvases()
        assert mapCanvas in canvases
        mapCanvas.setProperty(KEY_LAST_CLICKED, time.time())

    def currentMapView(self) -> MapView:
        """
        Returns the last used map view, i.e. the last map view a canvas was clicked on or a layer was selected in
        :return:
        """
        return self.currentMapCanvas().mapView()

    def setCurrentMapView(self, mapView: MapView):
        assert isinstance(mapView, MapView)
        lastCurrentMapCanvas = self.currentMapCanvas()
        if not isinstance(lastCurrentMapCanvas, MapCanvas):
            return
        lastCurrentMapView = lastCurrentMapCanvas.mapView()

        if mapView != lastCurrentMapView:
            assert mapView in self.mapViews()

            position = 0
            for i, c in enumerate(lastCurrentMapView):
                if c == lastCurrentMapCanvas:
                    position = i
                    break

            canvases = mapView.mapCanvases()
            if len(canvases) > 0:
                position = min(position, len(canvases) - 1)
                self.setCurrentMapCanvas(canvases[position])

    MKeyMapSize = 'map_size'
    MKeyCrs = 'crs'
    MKeyMapsPerView = 'maps_per_view'
    MKeyMapViews = 'map_views'
    MKeyCurrentDate = 'current_date'
    MKeyCurrentExtent = 'extent'
    MKeyAuxMapLayers = '_aux_map_layers'

    def asMap(self) -> dict:
        """
        Returns the current visualisation settings as dict, to be serialized in a JSON dump.
        :return: dict
        """
        d = {self.MKeyMapSize: [self.mapSize().width(), self.mapSize().height()],
             self.MKeyCrs: self.crs().toWkt(),
             self.MKeyMapsPerView: self.mapsPerMapView(),
             self.MKeyMapViews: [mv.asMap() for mv in self.mapViews()],
             self.MKeyCurrentDate: str(self.currentDate().dtg().toString(Qt.ISODateWithMs)),
             self.MKeyCurrentExtent: self.spatialExtent().asWktPolygon(),
             }

        # basic storing of aux map layers. relates to https://github.com/jakimowb/eo-time-series-viewer/issues/12
        # to be replaced by proper layer-tree reconstruction
        aux_map_layers = {}
        aux_mapview_layers = []
        for mv in self.mapViews():
            mv_layer_info = []
            for lyr in mv.layers():
                if not has_sensor_id(lyr):
                    if lyr.id() not in aux_map_layers:
                        info_source = {
                            'id': lyr.id(),
                            'source': lyr.source(),
                            'provider': lyr.dataProvider().name(),
                            'class': lyr.__class__.__name__,
                            'name': lyr.name(),
                            'style': layerStyleString(lyr, QgsMapLayer.AllStyleCategories)}
                        aux_map_layers[lyr.id()] = info_source
                    mv_layer_info.append(lyr.id())
            aux_mapview_layers.append(mv_layer_info)

        d[self.MKeyAuxMapLayers] = {
            'sources': aux_map_layers,
            'map_views': aux_mapview_layers
        }
        return d

    def allProxyLayers(self) -> List[QgsRasterLayer]:
        """
        Returns all QgsRasterLayers that are used as SensorProxyLayer inside the layer trees.
        :return:
        """
        layers = []
        for mv in self.mapViews():
            layers.extend(mv.sensorProxyLayers())
        return layers

    def _allReds(self, skip_refresh: bool = False):
        """
        For debugging only. Returns all minimum values of red-band contrast enhancements.
        :return:
        """
        if not skip_refresh:
            QgsApplication.processEvents()
            self.timedRefresh()
            QgsApplication.processEvents()
            self.timedRefresh()
            QgsApplication.processEvents()

        reds = []
        for lyr in self.allProxyLayers():
            if isinstance(lyr.renderer(), QgsMultiBandColorRenderer):
                reds.append(lyr.renderer().redContrastEnhancement().minimumValue())
        reds = ['nan' if math.isnan(r) else r for r in reds]
        return reds

    def fromMap(self, data: dict, feedback: QgsProcessingFeedback = QgsProcessingFeedback()):

        self.removeAllMapViews()

        if self.MKeyMapSize in data:
            w, h = data.get(self.MKeyMapSize)
            self.setMapSize(QSize(w, h))

        if wkt := data.get(self.MKeyCrs):
            crs = QgsCoordinateReferenceSystem.fromWkt(wkt)
            if crs.isValid():
                self.setCrs(crs)

        if maps_per_view := data.get(self.MKeyMapsPerView):
            cols, rows = maps_per_view
            self.setMapsPerMapView(cols, rows)

        for mv in data.get(self.MKeyMapViews, []):
            mapView = MapView()
            mapView.setTimeSeries(self.timeSeries())
            mapView.fromMap(mv)

            self.addMapView(mapView)

        if current_date := data.get(self.MKeyCurrentDate):
            tsd = self.timeSeries().findDate(current_date)

            if isinstance(tsd, TimeSeriesDate):
                self.setCurrentDate(tsd)

        if extent := data.get(self.MKeyCurrentExtent):
            extent = QgsRectangle.fromWkt(extent)
            self.setSpatialExtent(SpatialExtent(self.crs(), extent))

        CLASS2INIT = {c.__name__: c for c in [QgsVectorLayer, QgsRasterLayer]}

        if aux_layers := data.get(self.MKeyAuxMapLayers):
            new_layers = dict()
            if sources := aux_layers.get('sources'):

                for oldId, sourceInfo in sources.items():
                    clsName = sourceInfo.get('class')
                    source = sourceInfo.get('source')
                    name = sourceInfo.get('name')
                    provider = sourceInfo.get('provider')

                    if not (source and name and provider):
                        continue

                    lyr = None
                    # check for layers that already exist, e.g. because we
                    # call load project within the same session
                    # check QGIS and internal layers
                    for store in [self.mMapLayerStore, QgsProject.instance()]:
                        if existingLayer := store.mapLayer(oldId):
                            if existingLayer.isValid():
                                lyr = existingLayer
                                break

                    if lyr is None:
                        if clsName == QgsVectorLayer.__name__:
                            lyr = QgsVectorLayer(source, name, providerLib=provider)
                        elif clsName == QgsRasterLayer.__name__:
                            lyr = QgsRasterLayer(source, name, providerType=provider)
                    if isinstance(lyr, QgsMapLayer) and lyr.isValid():
                        if styleXml := sourceInfo.get('style'):
                            setLayerStyleString(lyr, styleXml)

                            new_layers[oldId] = lyr

            self.mMapLayerStore.addMapLayers(new_layers.values())

            for i_mv, mv_layer_ids in enumerate(aux_layers.get('map_views', [])):
                if i_mv >= len(self.mapViews()):
                    break
                new_mv: MapView = self.mapViews()[i_mv]
                new_mv_layers = []
                for oldId in mv_layer_ids:
                    lyrNew = new_layers.get(oldId)
                    if isinstance(lyrNew, QgsMapLayer):
                        new_mv_layers.append(lyrNew)
                existing_layers = new_mv.layers()
                for lyr in reversed(new_mv_layers):
                    if lyr not in existing_layers:
                        new_mv.addLayer(lyr)

    def usedLayers(self) -> List[QgsMapLayer]:
        layers = set()
        for c in self.mapCanvases():
            layers = layers.union(set(c.layers()))
        return list(layers)

    def crs(self) -> QgsCoordinateReferenceSystem:
        # returns the used CRS
        for c in self.mapCanvases():
            return c.mapSettings().destinationCrs()

        # backup:
        return self.spatialExtent().crs()

    def setTimeSeries(self, ts: TimeSeries) -> TimeSeries:
        assert ts is None or isinstance(ts, TimeSeries)

        if isinstance(self.mTimeSeries, TimeSeries):
            self.mTimeSeries.sigVisibilityChanged.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesAdded.disconnect(self._updateSliderRange)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.disconnect(self._updateSliderRange)
            self.mTimeSeries.sigFindOverlapTaskFinished.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigSensorNameChanged.disconnect(self._updateCanvasAppearance)
            self.mTimeSeries.sigSensorAdded.disconnect(self.addSensor)
            self.mTimeSeries.sigSensorRemoved.disconnect(self.removeSensor)

        self.mTimeSeries = ts
        if isinstance(self.mTimeSeries, TimeSeries):
            self.mTimeSeries.sigVisibilityChanged.connect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self._updateCanvasDates)
            self.mTimeSeries.sigFindOverlapTaskFinished.connect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self._updateSliderRange)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self._updateSliderRange)
            self.mTimeSeries.sigSensorNameChanged.connect(self._updateCanvasAppearance)
            self.mTimeSeries.sigSensorAdded.connect(self.addSensor)
            self.mTimeSeries.sigSensorRemoved.connect(self.removeSensor)
            if len(self.mTimeSeries) > 0:
                # self.mCurrentDate = self.mTimeSeries[0]
                self.setCurrentDate(self.mTimeSeries[0], 'start')
            else:
                self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onSetInitialCurrentDate)
            self._updateSliderRange()

        return self.timeSeries()

    def addSensor(self, sensor: SensorInstrument):
        """
        Adds a new SensorInstrument
        :param sensor: SensorInstrument
        """
        for mapView in self.mapViews():
            mapView.addSensor(sensor)

    def removeSensor(self, sensor: SensorInstrument):
        """
        Removes a Sensor
        :param sensor: SensorInstrument
        """
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            mapView.removeSensor(sensor)

    def onSetInitialCurrentDate(self):
        if len(self.timeSeries()) > 0:
            self.setCurrentDate(self.timeSeries()[0])
            self.mTimeSeries.sigTimeSeriesDatesAdded.disconnect(self.onSetInitialCurrentDate)

    def _updateSliderRange(self):

        slider = self.timeSlider()
        assert isinstance(slider, QSlider)
        n = len(self.timeSeries())
        slider.setRange(0, n - 1)
        slider.setEnabled(n > 0)

        if n > 10:
            pageStep = int(n / 100) * 10
            slider.setTickInterval(pageStep)
        else:
            pageStep = 5
            slider.setTickInterval(0)

        slider.setPageStep(pageStep)

        if False and n > 0:
            tsd = self.currentDate()
            if isinstance(tsd, TimeSeriesDate) and tsd in self.timeSeries():
                i = self.timeSeries()[:].index(tsd)
                slider.setValue(i + 1)
        self._updateSliderDate()
        self._updateSliderCss()

    def _updateSliderCss(self):
        visible_dates = self.visibleTSDs()
        dateS = self.sliderDate()
        # css = self.mTimeSlider.styleSheet()
        px_width = self.mTimeSlider.width()
        n = len(self.timeSeries())
        if self.mTimeSlider.maximum() <= 0 or len(visible_dates) == 0 or not isinstance(dateS, TimeSeriesDate):
            px_start_left = 0
            px_start_right = 0
        else:

            iS = self.timeSeries().mTSDs.index(dateS)
            i0 = self.timeSeries().mTSDs.index(visible_dates[0])
            i1 = self.timeSeries().mTSDs.index(visible_dates[-1])

            px_per_date = px_width / self.mTimeSlider.maximum()
            px_dateS = int(self.mTimeSlider.value() * px_per_date)
            px_start_left = int(i0 * px_per_date)
            px_start_right = px_width - int(i1 * px_per_date)
        # handle_width = 12 if n < 1 else max(12, int(px_width * (len(visible_dates) / n)))
        css = """
QSlider::groove:horizontal {{
    border: 1px solid #999999;
    height: 8px; /* the groove expands to the size of the slider by default. by giving it a height, it has a fixed size */
    /* background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);*/
    /*
    position: absolute;
    left: 10px;
    right: 10px;
    */
    /*width: 25px 100;*/
    margin: 2px 0;
}}

QSlider::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
    border: 1px solid #5c5c5c;
    width: 24px;
    margin: -2px 0; /* handle is placed by default on the contents rect of the groove. Expand outside the groove */
    border-radius: 3px;
}}

QSlider::sub-page {{
    border: 1px solid lightgrey;
    border-right: none;
    background: yellow;
    margin: 0px 0 0 {};
}}

QSlider::add-page {{
    border: 1px solid lightgrey;
    border-left: none;
    background: yellow;
    margin: 0px {} 0 0;
}}
        """.format(px_start_left, px_start_right)
        self.mTimeSlider.setStyleSheet(css)

    def onSliderMoved(self, value: int):
        self._updateSliderDate(value)

    def _updateSliderDate(self, i=None):
        tsd = self.sliderDate(i)
        if isinstance(tsd, TimeSeriesDate):
            dtgString = tsd.dtg().toString(Qt.ISODate)
            dtgString = dtgString.replace('T00:00:00', '')
            self.tbSliderDate.setText('{}({:03})'.format(dtgString, tsd.doy()))
            # self.tbSliderDate.setToolTip(''{}({:03})'.format(tsd.date(), tsd.doy())')

    def onSliderValueChanged(self):
        tsd = self.sliderDate()
        if isinstance(tsd, TimeSeriesDate):
            self.setCurrentDate(tsd)

    def sliderDate(self, i: int = None) -> TimeSeriesDate:
        """
        Returns the TimeSeriesDate related to slider value i
        :param i: slider value
        :return: TimeSeriesDate
        """
        tsd = None
        if i is None:
            i = self.mTimeSlider.value()
        if isinstance(self.mTimeSeries, TimeSeries) and len(self.mTimeSeries) > 0:
            i = min(i, len(self.mTimeSeries) - 1)
            i = max(i, 0)
            tsd = self.mTimeSeries[i]
        return tsd

    def timeSeries(self) -> TimeSeries:
        return self.mTimeSeries

    def setMode(self, mode: ViewMode):

        if mode != self.mViewMode:
            self.mViewMode = mode
            self._updateGrid()
            self.sigViewModeChanged.emit(self.mViewMode)

    def setRowsPerMapView(self, n: int):
        assert n >= 1
        self.mMapViewRows = n

    def rowsPerMapView(self) -> int:
        return self.mMapViewRows

    def setMapsPerMapView(self, cols: int, rows: int) -> int:
        """
        Sets the number of maps per map viewe
        :param n: int
        :return: int, number of maps per map view
        """
        assert cols > 0
        assert rows > 0

        if self.mapsPerMapView() != (cols, rows):
            self.mMapViewColumns = cols
            self.mMapViewRows = rows
            self._updateGrid()
            self.timeSlider().setPageStep(max(1, cols * rows))
            self.sigMapsPerMapViewChanged.emit(self.mMapViewColumns, self.mMapViewRows)
        return self.mapsPerMapView()

    def mapsPerMapView(self) -> Tuple[int, int]:
        """
        Returns the number of maps per map view as tuple of columns x rows
        :return: (int, int)
        """
        return self.mMapViewColumns, self.mMapViewRows

    def setMapSize(self, size: QSize) -> QSize:
        """
        Sets the MapCanvas size
        :param size: QSite
        :return: QSize
        """

        if size != self.mMapSize:
            for canvas in self.mapCanvases():
                canvas.setFixedSize(size)

            self.mMapSize = size
            self._updateWidgetSize()
            self.sigMapSizeChanged.emit(size)

        return self.mMapSize

    def mapSize(self) -> QSize:
        """
        Returns the MapCanvas size
        :return: QSize
        """
        return self.mMapSize

    def mapCanvases(self) -> List[MapCanvas]:
        """
        Returns all MapCanvases
        :return: [list-of-MapCanvases]
        """
        return self.findChildren(MapCanvas)

    def mapViewCanvases(self, mapView: MapView) -> List[MapCanvas]:
        """
        Returns the MapCanvases related to a MapView, sorted in temporal order
        :param mapView: MapView
        :return: [list-of-MapCanvases]
        """
        A = []
        B = []
        for c in self.mCanvases.get(mapView, []):
            if isinstance(c.tsd(), TimeSeriesDate):
                A.append(c)
            else:
                B.append(c)

        return sorted(A, key=lambda c: c.tsd()) + B

    def moveToNextTSD(self):

        for tsd in self.timeSeries()[:]:
            assert isinstance(tsd, TimeSeriesDate)
            if tsd > self.currentDate() and tsd.checkState():
                self.setCurrentDate(tsd)
                return

    def moveToPreviousTSD(self):
        for tsd in reversed(self.timeSeries()[:]):
            if tsd < self.currentDate() and tsd.checkState():
                self.setCurrentDate(tsd)
                return

    def moveToNextTSDFast(self):
        visibleAll = self.timeSeries().visibleTSDs()
        visibleNow = self.visibleTSDs()
        n_maps = self.mMapViewColumns * self.mMapViewRows
        if len(visibleNow) > 0 and len(visibleAll) > 0:
            tsdLast = visibleNow[-1]
            i0 = closest_index(tsdLast, visibleAll)
            i = min(i0 + int(0.5 * n_maps), len(visibleAll) - 1)
            self.setCurrentDate(visibleAll[i])

    def moveToPreviousTSDFast(self):
        visibleAll = self.timeSeries().visibleTSDs()
        visibleNow = self.visibleTSDs()
        n_maps = self.mMapViewColumns * self.mMapViewRows
        if len(visibleNow) > 0 and len(visibleAll) > 0:
            tsdFirst = visibleNow[0]
            i0 = closest_index(tsdFirst, visibleAll)
            i = max(0, i0 - int(math.ceil(0.5 * n_maps)))
            self.setCurrentDate(visibleAll[i])

    def moveToFirstTSD(self):
        for tsd in self.timeSeries()[:]:
            if tsd.checkState():
                self.setCurrentDate(tsd)
                return
        s = ""

    def moveToLastTSD(self):
        for tsd in reversed(self.timeSeries()[:]):
            if tsd.checkState():
                self.setCurrentDate(tsd)
                return
        s = ""

    def setCurrentDate(self, tsd: Union[TimeSeriesDate, QDateTime],
                       mode: str = 'center') -> TimeSeriesDate:
        """
        Sets the current TimeSeriesDate, i.e. the "center" date of all dates to be shown
        :param tsd: TimeSeriesDate or QDateTime
        :param mode: where the tsd should be set in the row of map canvas. can be 'center', 'start' or 'end' of
                     map canvases.
        :return: TimeSeriesDate
        """
        assert mode in ['center', 'start', 'end']
        if not isinstance(tsd, TimeSeriesDate):
            tsd = self.timeSeries().findDate(tsd)

        assert isinstance(tsd, TimeSeriesDate)
        b = tsd != self.mCurrentDate or mode != self.mCurrentDateMode \
            or (len(self.mapCanvases()) > 0 and self.mapCanvases()[0].tsd() is None)

        self.mCurrentDate = tsd
        self.mCurrentDateMode = mode

        if b:
            self._updateCanvasDates()
            i = self.mTimeSeries[:].index(self.mCurrentDate)

            if self.mTimeSlider.value() != i:
                with SignalBlocker(self.mTimeSlider) as blocker:
                    self.mTimeSlider.setValue(i)

            self.sigCurrentDateChanged.emit(self.mCurrentDate)

        if isinstance(self.currentDate(), TimeSeriesDate):
            i = self.timeSeries()[:].index(self.currentDate())
            canForward = i < len(self.mTimeSeries) - 1
            canBackward = i > 0
        else:
            canForward = canBackward = False

        for a in [self.actionForward, self.actionForwardFast, self.actionLastDate]:
            a.setEnabled(canForward)

        for a in [self.actionBackward, self.actionBackwardFast, self.actionFirstDate]:
            a.setEnabled(canBackward)
        self._updateSliderCss()

        # update slider CSS
        # set CSS
        return self.mCurrentDate

    def timeSlider(self) -> QSlider:
        return self.mTimeSlider

    def currentDate(self) -> TimeSeriesDate:
        """
        Returns the current TimeSeriesDate
        :return: TimeSeriesDate
        """
        return self.mCurrentDate

    def currentDateRange(self) -> Tuple[Optional[QDateTime], Optional[QDateTime]]:
        """
        Returns the date range that is visualized by map canvases
        :return:
        """
        tsds = self.visibleTSDs()
        if len(tsds) > 0:
            return tsds[0].dtg(), tsds[-1].dtg()
        else:
            return None, None

    def createMapView(self, name: str = None) -> MapView:
        """
        Create a new MapView
        :return: MapView
        """
        mapView = MapView()

        n = len(self.mapViews()) + 1
        if isinstance(name, str) and len(name) > 0:
            title = name
        else:
            title = 'Map View {}'.format(n)
            while title in [m.title() for m in self.mapViews()]:
                n += 1
                title = 'Map View {}'.format(n)
        if n == 1:
            pass
            # mapView.optionShowDate.setChecked(True)
            # mapView.optionShowSensorName.setChecked(True)

        mapView.setTitle(title)
        self.addMapView(mapView)
        return mapView

    def addMapView(self, mapView: MapView) -> Optional[MapView]:
        """
        Adds a MapView
        :param mapView: MapView
        :return: MapView
        """
        assert isinstance(mapView, MapView)
        if mapView in self.mMapViews:
            return None
        mapView.setTimeSeries(self.timeSeries())
        self.mMapViews.append(mapView)

        mapView.setMapWidget(self)

        # connect signals
        # mapView.sigShowProfiles.connect(self.sigShowProfiles)
        mapView.sigCanvasAppearanceChanged.connect(self._updateCanvasAppearance)
        mapView.sigCrosshairChanged.connect(self._updateCrosshair)
        mapView.sigCurrentLayerChanged.connect(self.onCurrentMapViewLayerChanged)
        self._updateGrid()
        self._updateCrosshair(mapView=mapView)
        self.sigMapViewsChanged.emit()
        self.sigMapViewAdded.emit(mapView)
        if len(self.mapViews()) == 1:
            self.setCurrentMapView(mapView)

        return mapView

    def onCurrentMapViewLayerChanged(self, layer: QgsMapLayer):
        mapView = self.sender()
        if isinstance(mapView, MapView):
            self.setCurrentMapView(mapView)
        self.sigCurrentLayerChanged.emit(layer)

    def removeAllMapViews(self):

        to_remove = reversed(self.mMapViews)
        for mv in to_remove:
            self.removeMapView(mv)

    def removeMapView(self, mapView: MapView) -> Optional[MapView]:
        """
        Removes a MapView
        :param mapView: Mapview
        :return: MapView
        """
        if not isinstance(mapView, MapView):
            return None
        if mapView in self.mMapViews:
            self.mMapViews.remove(mapView)
            mapView.setMapWidget(None)
            # disconnect signals

            self._updateGrid()
            self.sigMapViewsChanged.emit()
            self.sigMapViewRemoved.emit(mapView)
        return mapView

    def mapLayerStore(self) -> EOTimeSeriesViewerProject:
        return self.mMapLayerStore

    def mapViews(self) -> List[MapView]:
        """
        Returns a list of all MapViews
        :return: [list-of-MapViews]
        """
        return self.mMapViews[:]

    def setSyncWithQGISMapCanvas(self, b: bool):
        assert isinstance(b, bool)
        self.mSyncQGISMapCanvasCenter = b

    def syncQGISCanvasCenter(self):
        if self.mSyncLock:
            return

        iface = qgis.utils.iface
        if not isinstance(iface, QgisInterface):
            return

        c = iface.mapCanvas()
        if not isinstance(c, QgsMapCanvas) or len(self.mapCanvases()) == 0:
            return

        def mapTolerance(canvas: QgsMapCanvas) -> QgsVector:
            m2p = canvas.mapSettings().mapToPixel()
            return m2p.toMapCoordinates(1, 1) - m2p.toMapCoordinates(0, 0)

        recentQGISCenter = SpatialPoint.fromMapCanvasCenter(c)
        recentEOTSVCenter = self.spatialCenter()
        if not (isinstance(recentQGISCenter, SpatialPoint) and isinstance(recentEOTSVCenter, SpatialPoint)):
            return

        if not isinstance(self.mLastQGISMapCanvasCenter, SpatialPoint):
            self.mLastQGISMapCanvasCenter = SpatialPoint.fromMapCanvasCenter(c)
        else:
            self.mLastEOTSVMapCanvasCenter = self.mLastEOTSVMapCanvasCenter.toCrs(c.mapSettings().destinationCrs())
        if not isinstance(self.mLastEOTSVMapCanvasCenter, SpatialPoint):
            self.mLastEOTSVMapCanvasCenter = self.spatialCenter()
        else:
            self.mLastEOTSVMapCanvasCenter = self.mLastEOTSVMapCanvasCenter.toCrs(self.crs())

        if not (isinstance(self.mLastEOTSVMapCanvasCenter, SpatialPoint)
                and isinstance(self.mLastQGISMapCanvasCenter, SpatialPoint)):
            return

        shiftQGIS = recentQGISCenter - self.mLastQGISMapCanvasCenter
        shiftEOTSV = recentEOTSVCenter - self.mLastEOTSVMapCanvasCenter
        tolQGIS = mapTolerance(c)
        tolEOTS = mapTolerance(self.mapCanvases()[0])

        shiftedQGIS = shiftQGIS.length() > tolQGIS.length()
        shiftedEOTSV = shiftEOTSV.length() > tolEOTS.length()

        if not (shiftedEOTSV or shiftedQGIS):
            return

        self.mSyncLock = True
        if shiftedQGIS:
            # apply change to EOTSV
            self.mLastQGISMapCanvasCenter = recentQGISCenter
            newCenterEOTSV = recentQGISCenter.toCrs(self.crs())
            self.mLastEOTSVMapCanvasCenter = newCenterEOTSV
            if isinstance(newCenterEOTSV, SpatialPoint):
                self.setSpatialCenter(newCenterEOTSV)

        elif shiftedEOTSV:
            # apply change to QGIS
            self.mLastEOTSVMapCanvasCenter = recentEOTSVCenter
            newCenterQGIS = recentEOTSVCenter.toCrs(c.mapSettings().destinationCrs())
            self.mLastQGISMapCanvasCenter = newCenterQGIS
            if isinstance(newCenterQGIS, SpatialPoint):
                c.setCenter(newCenterQGIS)

        self.mSyncLock = False

    def _createMapCanvas(self, parent=None) -> MapCanvas:
        mapCanvas = MapCanvas(parent)
        mapCanvas.setVisible(False)
        mapCanvas.setMapLayerStore(self.mMapLayerStore)
        mapCanvas.mInfoItem.setTextFormat(self.mapTextFormat())

        # set general canvas properties
        mapCanvas.setFixedSize(self.mMapSize)
        mapCanvas.setDestinationCrs(self.crs())
        mapCanvas.setSpatialExtent(self.spatialExtent())

        # activate the current map tool
        mapTools = mapCanvas.mapTools()
        mapTools.activate(self.mMapToolKey)

        # connect signals
        self._connectCanvasSignals(mapCanvas)
        return mapCanvas

    def _connectCanvasSignals(self, mapCanvas: MapCanvas):
        mapCanvas.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        # mapCanvas.sigDestinationCrsChanged.connect(self.setCrs)
        mapCanvas.sigCrosshairPositionChanged.connect(self.onCrosshairPositionChanged)
        mapCanvas.sigCanvasClicked.connect(self.onCanvasClicked)
        mapCanvas.mapTools().mtCursorLocation.sigLocationRequest.connect(
            lambda crs, pt, c=mapCanvas: self.onCanvasLocationRequest(c, crs, pt))

    def _disconnectCanvasSignals(self, mapCanvas: MapCanvas):
        mapCanvas.sigSpatialExtentChanged.disconnect(self.setSpatialExtent)
        # mapCanvas.sigDestinationCrsChanged.disconnect(self.setCrs)
        mapCanvas.sigCrosshairPositionChanged.disconnect(self.onCrosshairPositionChanged)
        mapCanvas.sigCanvasClicked.disconnect(self.onCanvasClicked)
        # mapCanvas.mapTools().mtCursorLocation.sigLocationRequest.disconnect(
        #    self.sigCurrentLocationChanged)

    def onCanvasLocationRequest(self, canvas: QgsMapCanvas, crs: QgsCoordinateReferenceSystem, pt: QgsPointXY):
        self.sigCurrentLocationChanged[QgsCoordinateReferenceSystem, QgsPointXY].emit(crs, pt)
        self.sigCurrentLocationChanged[QgsCoordinateReferenceSystem, QgsPointXY, QgsMapCanvas].emit(crs, pt, canvas)

    def onCanvasClicked(self, event: QMouseEvent):
        canvas = self.sender()
        if isinstance(canvas, MapCanvas):
            self.setCurrentMapCanvas(canvas)

    def onCrosshairPositionChanged(self, spatialPoint: SpatialPoint):
        canvas = self.sender()

        if self.mCrosshairPosition != spatialPoint:
            self.setCrosshairPosition(spatialPoint)
            self.sigCrosshairPositionChanged[QgsCoordinateReferenceSystem, QgsPointXY, MapCanvas].emit(
                self.mCrosshairPosition.crs(), self.mCrosshairPosition, canvas)

    def setCurrentLayer(self, layer: QgsMapLayer):

        for mapView in self.mapViews():
            mapView.setCurrentLayer(layer)

    def setCrosshairPosition(self, spatialPoint) -> SpatialPoint:
        spatialPoint = spatialPoint.toCrs(self.crs())
        if self.mCrosshairPosition != spatialPoint:
            self.mCrosshairPosition = spatialPoint

            for canvas in self.mapCanvases():
                assert isinstance(canvas, MapCanvas)
                canvas.setCrosshairPosition(spatialPoint)

            self.sigCrosshairPositionChanged[QgsCoordinateReferenceSystem, QgsPointXY].emit(
                self.mCrosshairPosition.crs(), self.mCrosshairPosition)
        return self.crosshairPosition()

    def crosshairPosition(self) -> SpatialPoint:
        return self.mCrosshairPosition

    def _updateGrid(self):
        self.mMapRefreshTimer.stop()
        for canvas in self.mGrid.findChildren(MapCanvas):
            self._disconnectCanvasSignals(canvas)
        self.mGrid.parentWidget().setVisible(False)
        self.clearCanvasGrid()

        nc = self.mMapViewColumns
        nr = len(self.mapViews()) * self.mMapViewRows

        for iMV, mv in enumerate(self.mMapViews):
            assert isinstance(mv, MapView)
            self.mCanvases[mv] = []
            visible = mv.isVisible()
            for row in range(self.mMapViewRows):
                for col in range(self.mMapViewColumns):
                    gridrow = (iMV * self.mMapViewRows) + row
                    gridcol = col
                    c: MapCanvas = self._createMapCanvas()
                    assert isinstance(c, MapCanvas)
                    c.setTSD(None)
                    c.setMapView(mv)
                    self.mGrid.addWidget(c, gridrow, gridcol)
                    c.setVisible(visible)
                    self.mCanvases[mv].append(c)
        self._updateCanvasDates()
        self._updateSliderCss()
        self.mGrid.parentWidget().setVisible(True)
        self.mMapRefreshTimer.start()

    def _updateWidgetSize(self):

        # self.mGrid.update()
        # self.resize(self.sizeHint())
        # self.setMaximumSize(self.sizeHint())
        # self.setFixedSize(self.sizeHint())
        # if False and self.parentWidget():
        if False:
            w = self
            assert isinstance(w, QWidget)

            rect = QGuiApplication.primaryScreen().geometry()

            maxw, maxh = 0.66 * rect.width(), 0.66 * rect.height()
            hint = self.sizeHint()
            minw, minh = min(hint.width(), maxw), min(hint.height(), maxh)

            w.setMinimumSize(minw, minh)
            # w.setFixedSize(self.sizeHint())
            w.layout().update()
            w.update()

    def _updateLayerCache(self) -> List[MapCanvas]:
        canvases = self.findChildren(MapCanvas)
        for c in canvases:
            assert isinstance(c, MapCanvas)
            self.mMapLayerCache[self._layerListKey(c)] = c.layers()
        return canvases

    def _layerListKey(self, canvas: MapCanvas) -> Tuple[MapView, TimeSeriesDate]:
        return canvas.mapView(), canvas.tsd()

    def _updateCanvasDates(self, updateLayerCache: bool = True):

        assert self.mCurrentDateMode in ['center', 'start', 'end']

        visibleBefore = self.visibleTSDs()
        dateRangeBefore = self.currentDateRange()

        bTSDChanged = False
        if updateLayerCache:
            self._updateLayerCache()
        if not (isinstance(self.mCurrentDate, TimeSeriesDate) and isinstance(self.timeSeries(), TimeSeries)):
            for c in self.findChildren(MapCanvas):
                assert isinstance(c, MapCanvas)
                c.setTSD(None)
            bTSDChanged = True
        else:

            visible = self.timeSeries().visibleTSDs()
            nCanvases = self.mMapViewColumns * self.mMapViewRows

            i_current_date = closest_index(self.mCurrentDate, visible)

            i_visible = index_window(i_current_date, len(visible), nCanvases, self.mCurrentDateMode)
            visible = sorted([visible[i] for i in i_visible])

            # set TSD of remaining canvases to None
            while len(visible) < nCanvases:
                visible.append(None)
            for mapView in self.mapViews():

                for tsd, canvas in zip(visible, self.mCanvases[mapView]):
                    assert isinstance(tsd, TimeSeriesDate) or tsd is None
                    assert isinstance(canvas, MapCanvas)
                    if canvas.tsd() != tsd:
                        canvas.setTSD(tsd)
                        key = self._layerListKey(canvas)
                        if key in self.mMapLayerCache.keys():
                            v = self.mMapLayerCache[key]
                            canvas.setLayers(self.mMapLayerCache.pop(key))
                        bTSDChanged = True

        if bTSDChanged:
            self._updateCanvasAppearance()

        visible2 = self.visibleTSDs()
        if visible2 != visibleBefore:
            self.sigVisibleDatesChanged.emit(visible2)

        dateRange2 = self.currentDateRange()
        if dateRange2 and dateRange2 != dateRangeBefore:
            self.sigDateRangeChanged.emit(*dateRange2)

    def _freeUnusedMapLayers(self):

        layers = [lyr for lyr in self.mMapLayerStore.mapLayers().values() if has_sensor_id(lyr)]
        needed = self.usedLayers()
        toRemove = [lyr for lyr in layers if has_sensor_id(lyr) and lyr not in needed]

        # remove layers from MapLayerCache and MapLayerStore
        for mv in self.mMapLayerCache.keys():
            layers = [lyr for lyr in self.mMapLayerCache[mv] if lyr not in toRemove]
            self.mMapLayerCache[mv] = layers
        self.mMapLayerStore.removeMapLayers(toRemove)

    def _updateCrosshair(self, mapView=None):

        if isinstance(mapView, MapView):
            mapViews = [mapView]
        else:
            mapViews = self.mapViews()

        for mapView in mapViews:
            assert isinstance(mapView, MapView)
            style = mapView.crosshairStyle()
            assert isinstance(style, CrosshairStyle)

            for canvas in self.mCanvases[mapView]:
                assert isinstance(canvas, MapCanvas)

                item = canvas.mCrosshairItem
                item.setVisibility(style.mShow)
                assert isinstance(item, CrosshairMapCanvasItem)
                item.setCrosshairStyle(style)
                # canvas.addToRefreshPipeLine(MapCanvas.Command.UpdateMapItems)

    def _updateCanvasAppearance(self, mapView: Optional[MapView] = None):

        if isinstance(mapView, MapView):
            mapViews = [mapView]
        else:
            mapViews = self.mapViews()

        for mapView in mapViews:
            assert isinstance(mapView, MapView)
            v = mapView.isVisible()
            bg = mapView.mapBackgroundColor()
            tf = mapView.mapTextFormat()

            infoItemVisible: bool = mapView.optionShowInfoExpression.isChecked()

            for canvas in self.mCanvases[mapView]:
                assert isinstance(canvas, MapCanvas)
                canvas.updateScope()
                # set overall visibility
                if canvas.isVisible() != v:
                    canvas.setVisible(v)

                infoItem: MapCanvasInfoItem = canvas.infoItem()
                infoItem.setTextFormat(tf)
                infoItem.setVisible(infoItemVisible)

                expr = QgsExpression(mapView.mapInfoExpression())

                errorText = ''
                infoText = None
                if isinstance(expr, QgsExpression) and expr.expression() != '':
                    # context = QgsExpressionContext([QgsExpressionContextScope(canvas.expressionContextScope())])
                    context: QgsExpressionContext = QgsExpressionContext()
                    context.appendScope(QgsExpressionContextUtils.globalScope())
                    context.appendScope(QgsExpressionContextScope(canvas.expressionContextScope()))

                    if expr.isValid():
                        expr2 = QgsExpression(expr)
                        infoText = expr2.evaluate(context)
                        if expr2.hasEvalError():
                            errorText += expr2.evalErrorString()
                    else:
                        errorText += expr.parserErrorString()

                infoItem.setInfoText(infoText)

                # canvas.addToRefreshPipeLine(MapCanvas.Command.UpdateMapItems)
                if canvas.canvasColor() != bg:
                    canvas.setCanvasColor(bg)
                    # canvas.addToRefreshPipeLine(mapView.mapBackgroundColor())

                canvas.refresh()
                if errorText != '':
                    logger.debug(errorText)

            mapView.setInfoExpressionError(errorText)


class BlockExtentChange(object):
    """
    Signal blocker for arbitrary number of QObjects
    """

    def __init__(self, mapWidget: MapWidget):
        assert isinstance(mapWidget, MapWidget)
        self.mMapWidget = mapWidget

    def __enter__(self):
        self.mMapWidget.mBlockExtentChange = True

    def __exit__(self, exc_type, exc_value, tb):
        self.mMapWidget.mBlockExtentChange = False


class MapViewDock(QgsDockWidget):
    # sigMapViewAdded = pyqtSignal(MapView)
    # sigMapViewRemoved = pyqtSignal(MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    sigMapCanvasTextFormatChanged = pyqtSignal(QgsTextFormat)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigMapsPerMapViewChanged = pyqtSignal(int, int)
    sigMapTextFormatChanged = pyqtSignal(QgsTextFormat)

    def __init__(self, parent=None):
        super(MapViewDock, self).__init__(parent)
        loadUi(DIR_UI / 'mapviewdock.ui', self)

        self.sbMapViewColumns: QSpinBox
        self.sbMapViewRows: QSpinBox
        self.baseTitle = self.windowTitle()

        self.btnAddMapView.setDefaultAction(self.actionAddMapView)
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnMutuallyExclusiveMapViews.setDefaultAction(self.optionMutuallyExclusiveMapViews)

        self.actionNextMapView.setShortcuts([QKeySequence(QKeySequence.MoveToNextPage),
                                             QKeySequence(Qt.ALT + Qt.Key_S)])

        self.actionPreviousMapView.setShortcuts([QKeySequence(QKeySequence.MoveToPreviousPage),
                                                 QKeySequence(Qt.ALT + Qt.Key_W)])

        self.actionNextMapView.triggered.connect(self.onNextMapView)
        self.actionPreviousMapView.triggered.connect(self.onPreviousMapView)

        self.btnNextMapView.setDefaultAction(self.actionNextMapView)
        self.btnPreviousMapView.setDefaultAction(self.actionPreviousMapView)

        self.btnCrs: QgsProjectionSelectionWidget
        self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.LayerCrs, True)
        self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.ProjectCrs, True)
        self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.CurrentCrs, True)
        self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.DefaultCrs, True)
        self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.RecentCrs, True)
        # self.btnCrs.setOptionVisible(QgsProjectionSelectionWidget.CrsNotSet, True)

        self.btnCrs.crsChanged.connect(self.sigCrsChanged)
        self.btnMapCanvasColor.colorChanged.connect(
            lambda c: setFontButtonPreviewBackgroundColor(c, self.btnTextFormat))
        self.btnMapCanvasColor.colorChanged.connect(self.sigMapCanvasColorChanged.emit)
        setFontButtonPreviewBackgroundColor(self.btnMapCanvasColor.color(), self.btnTextFormat)

        self.btnTextFormat.changed.connect(lambda *args: self.sigMapTextFormatChanged.emit(self.mapTextFormat()))
        self.btnApplySizeChanges.clicked.connect(self.onApplyButtonClicked)

        self.toolBox.currentChanged.connect(self.onToolboxIndexChanged)

        self.spinBoxMapSizeX.valueChanged.connect(lambda: self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda: self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()
        # self.mLastMapViewColumns: int = self.sbMapViewColumns.value()
        # self.mLastMapViewRows: int = self.sbMapViewRows.value()

        self.mMapWidget: Optional[MapWidget] = None

    def exclusiveMapViewVisibility(self) -> bool:
        return self.optionMutuallyExclusiveMapViews.isChecked()

    def onNextMapView(self):
        mapViews = self.toolBoxMapViews()
        if len(mapViews) > 1:
            current = self.currentMapView()
            i = mapViews.index(current) + 1
            if i >= len(mapViews):
                i = 0
            self.setCurrentMapView(mapViews[i])

    def onPreviousMapView(self):
        mapViews = self.toolBoxMapViews()
        if len(mapViews) > 1:
            current = self.currentMapView()
            i = mapViews.index(current) - 1
            if i < 0:
                i = len(mapViews) - 1
            self.setCurrentMapView(mapViews[i])

    def onApplyButtonClicked(self):
        self.sigMapSizeChanged.emit(QSize(self.spinBoxMapSizeX.value(), self.spinBoxMapSizeY.value()))
        self.sigMapsPerMapViewChanged.emit(self.sbMapViewColumns.value(), self.sbMapViewRows.value())

    def setMapWidget(self, mw: MapWidget) -> MapWidget:
        """
        Connects this MapViewDock with a MapWidget
        :param mw: MapWidget
        :return:
        """
        assert isinstance(mw, MapWidget)

        self.mMapWidget = mw

        self.btnCrs.setCrs(mw.crs())
        self.sigCrsChanged.connect(mw.setCrs)
        mw.sigCrsChanged.connect(self.setCrs)

        self.sigMapSizeChanged.connect(mw.setMapSize)
        mw.sigMapSizeChanged.connect(self.setMapSize)

        self.sigMapTextFormatChanged.connect(mw.setMapTextFormat)
        mw.sigMapTextFormatChanged.connect(self.setMapTextFormat)

        self.sigMapsPerMapViewChanged.connect(mw.setMapsPerMapView)
        mw.sigMapsPerMapViewChanged.connect(self.setMapsPerMapView)

        mw.sigMapViewAdded.connect(self.addMapView)
        mw.sigMapViewRemoved.connect(self.removeMapView)

        for mapView in mw.mapViews():
            self.addMapView(mapView)

        self.actionAddMapView.triggered.connect(mw.createMapView)
        self.actionRemoveMapView.triggered.connect(lambda *args, _mw=mw: _mw.removeMapView(self.currentMapView()))

        return self.mMapWidget

    def mapWidget(self) -> MapWidget:
        """
        Returns the connected MapWidget
        :return: MapWidget
        """
        return self.mMapWidget

    def toolBoxMapViews(self) -> List[MapView]:
        """
        Returns the defined MapViews that have been added to the toolBox
        :return: [list-of-MapViews]
        """
        assert isinstance(self.toolBox, QToolBox)
        mapViews = []
        for i in range(self.toolBox.count()):
            item = self.toolBox.widget(i)
            if isinstance(item, MapView):
                mapViews.append(item)
        return mapViews

    # def mapCanvases(self) -> list:
    #    """
    #    Returns all MapCanvases from all MapViews
    #    :return: [list-of-MapCanvases]
    #    """
    #
    #    maps = []
    #    for mapView in self.mapViews():
    #        assert isinstance(mapView, MapView)
    #        maps.extend(mapView.mapCanvases())
    #    return maps

    def setCrs(self, crs: QgsCoordinateReferenceSystem):
        if isinstance(crs, QgsCoordinateReferenceSystem):
            old = self.btnCrs.crs()
            if old != crs:
                self.btnCrs.setCrs(crs)
                self.btnCrs.setLayerCrs(crs)

    def setMapsPerMapView(self, cols: int, rows: int):
        assert cols > 0
        assert rows > 0

        if self.sbMapViewColumns.value() != cols:
            self.sbMapViewColumns.setValue(cols)
        if self.sbMapViewRows.value() != rows:
            self.sbMapViewRows.setValue(rows)

    def setMapTextFormat(self, textFormat: QgsTextFormat):
        if isinstance(textFormat, QgsTextFormat):
            textFormat = QgsTextFormat(textFormat)
            textFormat.setPreviewBackgroundColor(self.btnMapCanvasColor.color())
            if not equalTextFormats(textFormat, self.mapTextFormat()):
                self.btnTextFormat.setTextFormat(textFormat)

    def mapTextFormat(self) -> QgsTextFormat:
        return self.btnTextFormat.textFormat()

    def setMapSize(self, size):
        assert isinstance(size, QSize)
        ws = [self.spinBoxMapSizeX, self.spinBoxMapSizeY]
        oldSize = self.mapSize()
        b = oldSize != size
        for w in ws:
            w.blockSignals(True)

        self.spinBoxMapSizeX.setValue(size.width()),
        self.spinBoxMapSizeY.setValue(size.height())
        self.mLastMapSize = QSize(size)
        for w in ws:
            w.blockSignals(False)
        self.mLastMapSize = QSize(size)
        if b:
            self.sigMapSizeChanged.emit(size)

    def onMapSizeChanged(self, dim):
        newSize = self.mapSize()
        # 1. set size of other dimension accordingly
        if dim is not None:
            if self.checkBoxKeepSubsetAspectRatio.isChecked():
                if dim == 'X':
                    vOld = self.mLastMapSize.width()
                    vNew = newSize.width()
                    targetSpinBox = self.spinBoxMapSizeY
                elif dim == 'Y':
                    vOld = self.mLastMapSize.height()
                    vNew = newSize.height()
                    targetSpinBox = self.spinBoxMapSizeX

                oldState = targetSpinBox.blockSignals(True)
                targetSpinBox.setValue(int(round(float(vNew) / vOld * targetSpinBox.value())))
                targetSpinBox.blockSignals(oldState)
                newSize = self.mapSize()
            if newSize != self.mLastMapSize:
                self.btnApplySizeChanges.setEnabled(True)
        else:
            self.sigMapSizeChanged.emit(self.mapSize())
            self.btnApplySizeChanges.setEnabled(False)
        self.setMapSize(newSize)

    def mapSize(self) -> QSize:
        return QSize(self.spinBoxMapSizeX.value(),
                     self.spinBoxMapSizeY.value())

    def dummySlot(self):
        s = ""

    def onMapViewsRemoved(self, mapViews):

        for mapView in mapViews:
            idx = self.stackedWidget.indexOf(mapView.ui)
            if idx >= 0:
                self.stackedWidget.removeWidget(mapView.ui)
                mapView.ui.close()
            else:
                s = ""

        self.actionRemoveMapView.setEnabled(len(self.mMapViews) > 0)

    def mapBackgroundColor(self) -> QColor:
        """
        Returns the map canvas background color
        :return: QColor
        """
        return self.btnMapCanvasColor.color()

    def setMapBackgroundColor(self, color: QColor):
        """
        Sets the MapCanvas background color
        :param color: QColor
        """
        if color != self.mapBackgroundColor():
            self.btnMapCanvasColor.setColor(color)

    def setMapTextColor(self, color: QColor):
        """
        Sets the map text color
        :param color: QColor
        :return: QColor
        """
        if color != self.mapTextColor():
            self.btnMapTextColor.setColor(color)
        return self.mapTextColor()

    def mapTextColor(self) -> QColor:
        """
        Returns the map text color.
        :return: QColor
        """
        return self.btnMapTextColor.color()

    def onMapViewsAdded(self, mapViews):
        nextShown = None
        for mapView in mapViews:
            mapView.sigTitleChanged.connect(self.updateTitle)
            self.stackedWidget.addWidget(mapView.ui)
            if nextShown is None:
                nextShown = mapView

            contents = mapView.ui.scrollAreaWidgetContents
            size = contents.size()
            hint = contents.sizeHint()
            # mapView.ui.scrollArea.update()
            s = ""
            # setMinimumSize(mapView.ui.scrollAreaWidgetContents.sizeHint())
            # hint = contents.sizeHint()
            # contents.setMinimumSize(hint)
        if isinstance(nextShown, MapView):
            self.setCurrentMapView(nextShown)

        for mapView in mapViews:
            self.sigMapViewAdded.emit(mapView)

    def updateButtons(self, *args):
        b = len(self.mMapViews) > 0
        self.actionRemoveMapView.setEnabled(b)
        self.actionApplyStyles.setEnabled(b)
        self.actionHighlightMapView.setEnabled(b)

    def onInfoOptionToggled(self):

        self.sigMapInfoChanged.emit()
        s = ""

    def addMapView(self, mapView: MapView):
        """
        Adds a MapView
        :param mapView: MapView
        """
        assert isinstance(mapView, MapView)
        if mapView not in self.toolBoxMapViews():
            mapView.sigTitleChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            # mapView.sigVisibilityChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            mapView.sigCanvasAppearanceChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            self.sigMapCanvasColorChanged.connect(mapView.setMapBackgroundColor)
            self.sigMapCanvasTextFormatChanged.connect(mapView.setMapTextFormat)
            i = self.toolBox.addItem(mapView, mapView.windowIcon(), mapView.title())
            self.toolBox.setCurrentIndex(i)
            self.onMapViewUpdated(mapView)

            if len(self.toolBoxMapViews()) == 1:
                self.setMapTextFormat(mapView.mapTextFormat())

            # self.sigMapViewAdded.emit(mapView)

    def onToolboxIndexChanged(self):

        b = isinstance(self.toolBox.currentWidget(), MapView)
        self.actionRemoveMapView.setEnabled(b)

    def onMapViewUpdated(self, mapView: MapView):
        """
        Handles updates that react on MapView changes
        :param mapView: MapView to make the update for
        """
        numMV = 0
        for i in range(self.toolBox.count()):
            item = self.toolBox.widget(i)
            if isinstance(item, MapView):
                numMV += 1
            if item == mapView:

                if mapView.isVisible():
                    icon = QIcon(":/eotimeseriesviewer/icons/mapview.svg")
                else:
                    icon = QIcon(":/eotimeseriesviewer/icons/mapviewHidden.svg")

                self.toolBox.setItemIcon(i, icon)
                self.toolBox.setItemText(i, 'Map View {} "{}"'.format(numMV, mapView.title()))
                break

    def removeMapView(self, mapView: MapView) -> MapView:
        """
        Removes a MapView
        :param mapView: MapView
        :return: MapView
        """
        if mapView in self.toolBoxMapViews():
            for i in range(self.toolBox.count()):
                w = self.toolBox.widget(i)
                if isinstance(w, MapView) and w == mapView:
                    self.toolBox.removeItem(i)
                    mapView.close()
                    if self.toolBox.count() >= i:
                        self.toolBox.setCurrentIndex(min(i, self.toolBox.count() - 1))

            # self.sigMapViewRemoved.emit(mapView)
        return mapView

    def __len__(self) -> int:
        """
        Returns the number of MapViews
        :return: int
        """
        return len(self.toolBoxMapViews())

    def __iter__(self):
        """
        Provides an iterator over all MapViews
        :return:
        """
        return iter(self.toolBoxMapViews())

    def __getitem__(self, slice):
        return self.toolBoxMapViews()[slice]

    def __contains__(self, mapView):
        return mapView in self.toolBoxMapViews()

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.toolBoxMapViews().index(mapView)

    def applyStyles(self):
        for mapView in self.mMapViews:
            mapView.applyStyles()

    def setCrosshairStyle(self, crosshairStyle):
        for mapView in self.mMapViews:
            mapView.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        for mapView in self.mMapViews:
            mapView.setCrosshairVisibility(b)

    def setCurrentMapView(self, mapView):
        assert isinstance(mapView, MapView) and mapView in self.toolBoxMapViews()

        if self.exclusiveMapViewVisibility():
            for mv in self.toolBoxMapViews():
                mv.setVisibility(mv == mapView)
        self.toolBox.setCurrentWidget(mapView)
        self.updateTitle()

    def updateTitle(self, *args):
        # self.btnToggleMapViewVisibility.setChecked(mapView)
        mapView = self.currentMapView()
        if isinstance(mapView, MapView):
            title = '{} | {}'.format(self.baseTitle, mapView.title())
        else:
            title = self.baseTitle
        self.setWindowTitle(title)

    def currentMapView(self) -> Optional[MapView]:
        w = self.toolBox.currentWidget()
        if isinstance(w, MapView):
            return w
        else:
            # return first map view
            for mv in self.toolBoxMapViews():
                return mv
        return None
