# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
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

import enum
import math
import re
import sys
import time
import traceback
from typing import Dict, Iterator, List, Tuple

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import \
    Qt, QSize, pyqtSignal, QModelIndex, QTimer, QAbstractListModel
from qgis.PyQt.QtGui import \
    QColor, QIcon, QGuiApplication, QMouseEvent, QKeySequence
from qgis.PyQt.QtWidgets import \
    QWidget, QFrame, QLabel, QGridLayout, QSlider, QMenu, \
    QToolBox, QDialog, QSpinBox, QLineEdit
from qgis.PyQt.QtXml import \
    QDomDocument, QDomNode, QDomElement
from qgis.core import \
    QgsCoordinateReferenceSystem, QgsTextFormat, QgsProject, \
    QgsRectangle, QgsRasterRenderer, QgsMapLayerStore, QgsMapLayerStyle, \
    QgsLayerTreeModel, QgsLayerTreeGroup, QgsPointXY, \
    QgsLayerTree, QgsLayerTreeLayer, QgsReadWriteContext, QgsVector, \
    QgsRasterLayer, QgsVectorLayer, QgsMapLayer, QgsMapLayerProxyModel, QgsExpressionContextGenerator, \
    QgsExpressionContext, \
    QgsExpressionContextUtils, QgsExpression, QgsExpressionContextScope
from qgis.gui import \
    QgsDockWidget, QgsMapCanvas, QgsLayerTreeView, \
    QgisInterface, QgsLayerTreeViewMenuProvider, QgsLayerTreeMapCanvasBridge, \
    QgsProjectionSelectionWidget, QgsMessageBar, QgsExpressionBuilderDialog

from eotimeseriesviewer import DIR_UI, debugLog
from eotimeseriesviewer.utils import fixMenuButtons
from .mapcanvas import MapCanvas, MapCanvasInfoItem, KEY_LAST_CLICKED
from .qgispluginsupport.qps.crosshair.crosshair import getCrosshairStyle, CrosshairStyle, CrosshairMapCanvasItem
from .qgispluginsupport.qps.layerproperties import VectorLayerTools
from .qgispluginsupport.qps.maptools import MapTools
from .qgispluginsupport.qps.utils import SpatialPoint, SpatialExtent, loadUi, datetime64
from .timeseries import SensorInstrument, TimeSeriesDate, TimeSeries, SensorProxyLayer

KEY_LOCKED_LAYER = 'eotsv/locked'
KEY_SENSOR_GROUP = 'eotsv/sensorgroup'
KEY_SENSOR_LAYER = 'eotsv/sensorlayer'


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


class MapViewExpressionContextGenerator(QgsExpressionContextGenerator):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mMapView: MapView = None

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
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)
    sigCurrentLayerChanged = pyqtSignal(QgsMapLayer)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def __init__(self, name='Map View', parent=None):
        super(MapView, self).__init__(parent)
        loadUi(DIR_UI / 'mapview.ui', self)
        # self.setupUi(self)

        from eotimeseriesviewer.settings import Keys, defaultValues, value

        DEFAULT_VALUES = defaultValues()
        self.mMapBackgroundColor: QColor = value(Keys.MapBackgroundColor,
                                                 default=DEFAULT_VALUES.get(Keys.MapBackgroundColor, QColor('black')))
        self.mMapTextFormat: QgsTextFormat = value(Keys.MapTextFormat,
                                                   default=DEFAULT_VALUES.get(Keys.MapTextFormat, QgsTextFormat()))
        self.mMapWidget = None

        self.mLayerStyleInitialized: Dict[SensorInstrument, bool] = dict()

        self.mTimeSeries = None
        self.mSensorLayerList = list()
        self.mCrossHairStyle = CrosshairStyle()

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

    @staticmethod
    def readXml(node: QDomNode):
        if node.nodeName() == 'MapView':
            nodeMapView = node
        else:
            nodeMapView = node.firstChildElement('MapView')

        if nodeMapView.nodeName() != 'MapView':
            return None

        context = QgsReadWriteContext()
        mapView = MapView()

        def to_bool(value) -> bool:
            return str(value).lower() in ['1', 'true']

        mapView.setName(nodeMapView.attribute('name'))
        mapView.setMapBackgroundColor(QColor(nodeMapView.attribute('bg')))
        mapView.setVisibility(to_bool(nodeMapView.attribute('visible')))

        # mapView.optionShowDate.setChecked(to_bool(nodeMapView.attribute('showDate')))
        # mapView.optionShowSensorName.setChecked(to_bool(nodeMapView.attribute('showSensorName')))
        # mapView.optionShowMapViewName.setChecked(to_bool(nodeMapView.attribute('showMapViewName')))

        # nodeMapView.setAttribute('showDate', str(self.optionShowDate.checked()))
        # nodeMapView.setAttribute('showSensorName', str(self.optionShowSensorName.checked()))
        # nodeMapView.setAttribute('showMapViewName', str(self.optionShowMapViewName.checked()))

        textFormat = mapView.mapTextFormat()
        textFormat.readXml(nodeMapView, context)

        lyrTreeNode = node.firstChildElement('MapViewLayerTree').toElement()

        def copyLayerTree(parentSrc: QgsLayerTreeGroup, parentDst: QgsLayerTreeGroup):

            for child in parentSrc.children():
                if 'eotsv/locked' in child.customProperties():
                    continue
                if isinstance(child, QgsLayerTreeLayer):
                    lyr = child.layer()
                    if isinstance(lyr, QgsMapLayer) and lyr.isValid():
                        parentDst.addChildNode(child.clone())
                    s = ""
                elif isinstance(child, QgsLayerTreeGroup):
                    if 'eotsv/locked' in child.customProperties():
                        continue
                    grp = QgsLayerTreeGroup()
                    grp.setName(child.name())
                    grp.setIsMutuallyExclusive(child.isMutuallyExclusive())
                    parentDst.addChildNode(grp)
                    copyLayerTree(child, grp)

        if not lyrTreeNode.isNull():
            tree: QgsLayerTree = QgsLayerTree.readXml(lyrTreeNode, context)
            tree.resolveReferences(QgsProject.instance(), looseMatching=True)
            if len(tree.children()) > 0:
                copyLayerTree(tree.children()[0], mapView.mLayerTreeModel.rootGroup())
                # move sensor node to last position
                mapView.mLayerTree.removeChildNode(mapView.mLayerTreeSensorNode)
                # will be added again to the bottom
                # mapView.mLayerTree.addChildNode(mapView.mLayerTreeSensorNode)

        lyrNode = node.firstChildElement('MapViewProxyLayer').toElement()
        while lyrNode.nodeName() == 'MapViewProxyLayer':
            sid = lyrNode.attribute('sensor_id')
            styleNode = lyrNode.firstChildElement('LayerStyle')
            style = QgsMapLayerStyle()
            style.readXml(styleNode)
            sensor = SensorInstrument(sid)
            mapView.addSensor(sensor)
            lyr = mapView.sensorProxyLayer(sensor)
            lyr.setMapLayerStyle(style)

            lyrNode = lyrNode.nextSiblingElement()
        return mapView

    def writeXml(self, node: QDomNode, doc: QDomDocument):

        nodeMapView = doc.createElement('MapView')
        nodeMapView.setAttribute('name', self.name())
        nodeMapView.setAttribute('bg', self.mapBackgroundColor().name())
        nodeMapView.setAttribute('visible', str(self.isVisible()))
        nodeMapView.setAttribute('infoexpression', self.mapInfoExpression())

        context = QgsReadWriteContext()
        nodeTextStyle = self.mapTextFormat().writeXml(doc, context)
        nodeMapView.appendChild(nodeTextStyle)

        nodeLayerTree = doc.createElement('MapViewLayerTree')
        self.mLayerTree.writeXml(nodeLayerTree, context)
        nodeMapView.appendChild(nodeLayerTree)

        for sensor in self.sensors():
            lyr = self.sensorProxyLayer(sensor)
            if isinstance(lyr, SensorProxyLayer):
                sensorNode = doc.createElement('MapViewProxyLayer')
                sensorNode.setAttribute('sensor_id', sensor.id())
                style: QgsMapLayerStyle = lyr.mapLayerStyle()
                styleNode = doc.createElement('LayerStyle')
                style.writeXml(styleNode)
                sensorNode.appendChild(styleNode)
                nodeMapView.appendChild(sensorNode)
        node.appendChild(nodeMapView)

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

    def visibleMapCanvases(self) -> list:
        """
        Returns the currently visible mapcanvases
        :return: [list-of-MapCanvases]
        """
        return [m for m in self.mapCanvases() if m.isVisibleToViewport()]

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
        d.setWindowTitle(title)
        d.addLayerDescription(text, filter)
        if d.exec() == QDialog.Accepted:
            for l in d.mapLayers():
                self.addLayer(l)

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

    def setHighlighted(self, b=True, timeout=1000):
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

    def currentMapCanvas(self) -> MapCanvas:
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
        if isinstance(cl, SensorProxyLayer):
            sensor = cl.sensor()
            canvases = [c for c in self.mapCanvases() if c.tsd().sensor() == sensor]
            canvases = sorted(canvases, key=lambda c: c is not self.currentMapCanvas())
            for c in canvases:
                for l in c.layers():
                    if isinstance(l, SensorProxyLayer):
                        return l
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

    def sensorProxyLayers(self) -> List[SensorProxyLayer]:
        layers = [n.layer() for n in self.mLayerTreeSensorNode.findLayers()]
        return [l for l in layers if isinstance(l, SensorProxyLayer)]

    def sensorProxyLayer(self, sensor: SensorInstrument) -> SensorProxyLayer:
        """
        Returns the proxy layer related to a SensorInstrument
        :param sensor: SensorInstrument
        :return: SensorLayer
        """
        for l in self.sensorProxyLayers():
            if l.sensor() == sensor:
                return l
        return None

    def sensorLayers(self, sensor: SensorInstrument) -> List[SensorProxyLayer]:
        """
        :param sensor:
        :return:
        """
        layers = []
        for c in self.mapCanvases():
            for lyr in c.layers():
                if isinstance(lyr, SensorProxyLayer) and lyr.sensor() == sensor:
                    layers.append(lyr)
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
        Tree Model.
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor not in self.sensors():
            sensor.sigNameChanged.connect(self.sigCanvasAppearanceChanged)

            masterLayer: SensorProxyLayer = sensor.proxyRasterLayer()
            assert isinstance(masterLayer.renderer(), QgsRasterRenderer)

            self.mSensorLayerList.append((sensor, masterLayer))
            masterLayer.styleChanged.connect(lambda *args, v=self, l=masterLayer: self.onMasterStyleChanged(l))
            masterLayer.nameChanged.connect(self.onMasterLyrNameChanged)
            layerTreeLayer: QgsLayerTreeLayer = self.mLayerTreeSensorNode.addLayer(masterLayer)
            layerTreeLayer.setCustomProperty(KEY_LOCKED_LAYER, True)
            layerTreeLayer.setCustomProperty(KEY_SENSOR_LAYER, True)

            dummyLayers = self.mDummyCanvas.layers() + [masterLayer]
            self.mDummyCanvas.setLayers(dummyLayers)

            self.mLayerStyleInitialized[sensor] = False

    def onMasterLyrNameChanged(self, *args):
        lyr = self.sender()
        newname = lyr.name()
        ltn = self.mLayerTreeSensorNode.findLayer(lyr)
        # print(ltn.name())

    def onMasterStyleChanged(self, masterLayer: SensorProxyLayer):

        sensor: SensorInstrument = masterLayer.sensor()
        style: QgsMapLayerStyle = masterLayer.mapLayerStyle()
        # print('### MASTER-STYLE-CHANGED')
        # print(style.xmlData())
        for lyr in self.sensorLayers(sensor):
            lyr.setMapLayerStyle(style)

        for c in self.sensorCanvases(sensor):
            assert isinstance(c, MapCanvas)
            c.addToRefreshPipeLine(MapCanvas.Command.RefreshRenderer)

        self.mLayerStyleInitialized[sensor] = True

    def sensorCanvases(self, sensor: SensorInstrument) -> list:
        """
        Returns the MapCanvases that show a layer with data for the given ``sensor``
        :param sensor: SensorInstrument
        :return:
        """
        assert isinstance(sensor, SensorInstrument)
        return [c for c in self.mapCanvases() if isinstance(c, MapCanvas)
                and isinstance(c.tsd(), TimeSeriesDate) and c.tsd().sensor() == sensor]

    def sensorLayer(self, sensor: SensorInstrument):
        """
        Returns the QgsRasterLayer that is used a proxy to specify the QgsRasterRenderer for a sensor
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
        if sensor in self.mLayerStyleInitialized.keys():
            self.mLayerStyleInitialized.pop(sensor)

        toRemove = []
        for t in self.mSensorLayerList:
            if t[0] == sensor:
                toRemove.append(t)

        for t in toRemove:
            self.mLayerTreeSensorNode.removeLayer(t[1])
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
        for l in selected:
            if not isinstance(l, SensorProxyLayer):
                self.mapView().mLayerTree.removeLayer(l)

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
        current = self.mapView().currentLayer()
        canvas = self.mapView().currentMapCanvas()
        if not isinstance(canvas, MapCanvas):
            return
        if isinstance(current, SensorProxyLayer):

            for l in canvas.layers():
                if isinstance(l, SensorProxyLayer) and l.sensor() == current.sensor():
                    canvas.stretchToExtent(layer=current)
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
        isSensorLayer = isinstance(currentLayer, SensorProxyLayer)
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

            if isinstance(currentLayer, QgsRasterLayer) and not isinstance(currentLayer, SensorProxyLayer):
                pass

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
            menu.addAction(eotsv.actionPasteLayerStyle())
            menu.addAction(eotsv.actionCopyLayerStyle())

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


def closest_index(tsd_target: TimeSeriesDate, tsds: List[TimeSeriesDate]) -> int:
    """
    Returns the index of the TimeSeriesDate closest to tsd_target
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

        self.mMapLayerStore = QgsMapLayerStore(parent=self)
        self.mMapLayerCache = dict()
        self.mCanvasCache = dict()

        self.tbSliderDate: QLabel

        # self.mCurrentMapView: MapView = None
        # self.mCurrentMapCanvas: MapCanvas = None

        self.mMapViews: List[MapView] = []
        self.mCanvases: Dict[MapView, List[MapCanvas]] = dict()
        self.mCanvasSignals = dict()
        self.mTimeSeries: TimeSeries = None

        self.mMapToolKey: MapTools = MapTools.Pan

        self.mViewMode = MapWidget.ViewMode.MapViewByRows
        self.mMapViewColumns: int = 3
        self.mMapViewRows: int = 1

        self.mSpatialExtent: SpatialExtent = SpatialExtent.world()
        self.mCrs: QgsCoordinateReferenceSystem = self.mSpatialExtent.crs()
        self.mCrsInitialized: bool = False

        self.mCurrentDate: TimeSeriesDate = None
        self.mCrosshairPosition: SpatialPoint = None

        self.mMapSize = QSize(200, 200)
        from eotimeseriesviewer.settings import defaultValues, Keys

        DEFAULT_VALUES = defaultValues()
        self.mMapTextFormat = DEFAULT_VALUES[Keys.MapTextFormat]
        self.mMapRefreshTimer = QTimer(self)
        self.mMapRefreshTimer.timeout.connect(self.timedRefresh)
        self.mMapRefreshTimer.setInterval(500)
        self.mMapRefreshTimer.start()

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

    def close(self):
        self.mMapRefreshTimer.stop()
        self.mMapLayerStore.removeAllMapLayers()
        self.mMapLayerCache.clear()
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
        for c in self.mapCanvases():
            b = c.blockSignals(True)
            assert isinstance(c, MapCanvas)
            c.timedRefresh()
            c.blockSignals(b)

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
        return self.mSpatialExtent

    def setSpatialExtent(self, *args) -> SpatialExtent:
        """
        Sets a SpatialExtent to all MapCanvases.
        Arguments can be those to construct a SpatialExtent
        :param extent: SpatialExtent
        :return: SpatialExtent the current SpatialExtent
        """
        if len(args) == 1 and type(args[0]) == QgsRectangle:
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
        if self.mSpatialExtent == extent:
            return

        ext = extent.toCrs(self.crs())
        if not isinstance(ext, SpatialExtent):
            s = ""
            # last resort: zoom to CRS boundaries

        if isinstance(ext, SpatialExtent) and ext != self.spatialExtent():
            self.mSpatialExtent = ext
            debugLog(f'new extent: {self.mSpatialExtent}')
            for c in self.mapCanvases():
                assert isinstance(c, MapCanvas)
                c.addToRefreshPipeLine(self.mSpatialExtent)
            self.sigSpatialExtentChanged.emit(self.mSpatialExtent.__copy__())
        return self.spatialExtent()

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
        if self.mCrs == crs:
            return self.crs()

        self.mCrs = QgsCoordinateReferenceSystem(crs)
        for i, c in enumerate(self.mapCanvases()):
            wasBlocked = c.blockSignals(True)
            c.setDestinationCrs(self.mCrs)
            if i == 0:
                self.mSpatialExtent = SpatialExtent.fromMapCanvas(c)
            if not wasBlocked:
                c.blockSignals(False)
        self.sigCrsChanged.emit(self.crs())
        return self.crs()

    def timedRefresh(self):
        """
        Calls the timedRefresh() routine for all MapCanvases
        """
        if self.mSyncQGISMapCanvasCenter:
            self.syncQGISCanvasCenter()

        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            b = c.blockSignals(True)
            c.timedRefresh()
            c.blockSignals(b)

        for mapView in self.mapViews():
            # test for initial raster stretches
            for sensor in self.timeSeries().sensors():
                if not mapView.mLayerStyleInitialized.get(sensor, False):
                    for c in self.mapViewCanvases(mapView):
                        # find the first map canvas that contains  layer data of this sensor
                        # in its extent
                        if not isinstance(c.tsd(), TimeSeriesDate):
                            continue
                        if c.tsd().sensor() == sensor and c.stretchToCurrentExtent():
                            mapView.mLayerStyleInitialized[sensor] = True
                            break

    def currentLayer(self) -> QgsMapLayer:
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

    def writeXml(self, node: QDomElement, doc: QDomDocument) -> bool:
        """
        Writes the MapWidget settings to a QDomNode
        :param node:
        :param doc:
        :return:
        """
        context = QgsReadWriteContext()
        mwNode = doc.createElement('MapWidget')
        mapSize = self.mapSize()
        mwNode.setAttribute('mapsPerMapView', f'{self.mapsPerMapView()}')
        mwNode.setAttribute('mapWidth', f'{mapSize.width()}')
        mwNode.setAttribute('mapHeight', f'{mapSize.height()}')
        currentDate = self.currentDate()
        if isinstance(currentDate, TimeSeriesDate):
            mwNode.setAttribute('mapDate', f'{currentDate.date()}')
        crsNode = doc.createElement('MapExtent')
        self.spatialExtent().writeXml(crsNode, doc)
        mwNode.appendChild(crsNode)

        for mapView in self.mapViews():
            mapView.writeXml(mwNode, doc)
        node.appendChild(mwNode)
        return True

    def readXml(self, node: QDomNode):
        from .settings import setValue, Keys
        debugLog()
        if not node.nodeName() == 'MapWidget':
            node = node.firstChildElement('MapWidget')
        if node.isNull():
            return None

        if node.hasAttribute('mapsPerMapView'):
            v = node.attribute('mapsPerMapView')
            v = [int(v) for v in re.findall(r'\d+', v)]
            if len(v) >= 2:
                self.setMapsPerMapView(v[0], v[1])
        if node.hasAttribute('mapWidth') and node.hasAttribute('mapHeight'):
            mapSize = QSize(
                int(node.attribute('mapWidth')),
                int(node.attribute('mapHeight'))
            )

            self.setMapSize(mapSize)
            setValue(Keys.MapSize, mapSize)

        if node.hasAttribute('mapDate'):
            dt64 = datetime64(node.attribute('mapDate'))
            if isinstance(dt64, np.datetime64):
                tsd = self.timeSeries().tsd(dt64, None)
                if isinstance(tsd, TimeSeriesDate):
                    self.setCurrentDate(tsd)

        nodeExtent = node.firstChildElement('MapExtent')
        if nodeExtent.nodeName() == 'MapExtent':
            extent = SpatialExtent.readXml(nodeExtent)
            if isinstance(extent, SpatialExtent):
                self.setCrs(extent.crs())
                self.setSpatialExtent(extent)

        mvNode = node.firstChildElement('MapView').toElement()

        while mvNode.nodeName() == 'MapView':
            mapView = MapView.readXml(mvNode)
            if isinstance(mapView, MapView):
                setValue(Keys.MapTextFormat, mapView.mapTextFormat())
                setValue(Keys.MapBackgroundColor, mapView.mapBackgroundColor())

                for s in mapView.sensors():
                    self.timeSeries().addSensor(s)

                self.addMapView(mapView)

            mvNode = mvNode.nextSiblingElement()

    def usedLayers(self) -> List[QgsMapLayer]:
        layers = set()
        for c in self.mapCanvases():
            layers = layers.union(set(c.layers()))
        return list(layers)

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self.mCrs

    def setTimeSeries(self, ts: TimeSeries) -> TimeSeries:
        assert ts is None or isinstance(ts, TimeSeries)

        if isinstance(self.mTimeSeries, TimeSeries):
            self.mTimeSeries.sigVisibilityChanged.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesAdded.disconnect(self._updateSliderRange)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.disconnect(self._updateSliderRange)
            self.mTimeSeries.sigFindOverlapTaskFinished.disconnect(self._updateCanvasDates)
            self.mTimeSeries.sigSensorNameChanged.disconnect(self._updateCanvasAppearance)

        self.mTimeSeries = ts
        if isinstance(self.mTimeSeries, TimeSeries):
            self.mTimeSeries.sigVisibilityChanged.connect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self._updateCanvasDates)
            self.mTimeSeries.sigFindOverlapTaskFinished.connect(self._updateCanvasDates)
            self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self._updateSliderRange)
            self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self._updateSliderRange)
            self.mTimeSeries.sigSensorNameChanged.connect(self._updateCanvasAppearance)
            if len(self.mTimeSeries) > 0:
                self.mCurrentDate = self.mTimeSeries[0]
            else:
                self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onSetInitialCurrentDate)
            self._updateSliderRange()

        return self.timeSeries()

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

        if n > 0:
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
            self.tbSliderDate.setText('{}({:03})'.format(tsd.date(), tsd.doy()))
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
        s = ""

    def moveToPreviousTSD(self):
        for tsd in reversed(self.timeSeries()[:]):
            if tsd < self.currentDate() and tsd.checkState():
                self.setCurrentDate(tsd)
                return
        s = ""

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

    def setCurrentDate(self, tsd: TimeSeriesDate) -> TimeSeriesDate:
        """
        Sets the current TimeSeriesDate, i.e. the "center" date of all dates to be shown
        :param tsd: TimeSeriesDate
        :return: TimeSeriesDate
        """
        assert isinstance(tsd, TimeSeriesDate)

        b = tsd != self.mCurrentDate or (len(self.mapCanvases()) > 0 and self.mapCanvases()[0].tsd() is None)
        self.mCurrentDate = tsd

        if b:
            self._updateCanvasDates()

            i = self.mTimeSeries[:].index(self.mCurrentDate)

            if self.mTimeSlider.value() != i:
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

    def addMapView(self, mapView: MapView) -> MapView:
        """
        Adds a MapView
        :param mapView: MapView
        :return: MapView
        """
        assert isinstance(mapView, MapView)
        if mapView not in self.mMapViews:
            self.mMapViews.append(mapView)

            mapView.setMapWidget(self)

            # connect signals
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

    def removeMapView(self, mapView: MapView) -> MapView:
        """
        Removes a MapView
        :param mapView: Mapview
        :return: MapView
        """
        if mapView in self.mMapViews:
            self.mMapViews.remove(mapView)
            mapView.setMapWidget(None)
            # disconnect signals

            self._updateGrid()
            self.sigMapViewsChanged.emit()
            self.sigMapViewRemoved.emit(mapView)
        return mapView

    def mapLayerStore(self) -> QgsMapLayerStore:
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

    def onClose(self):
        """
        Removes all remaining mapviews and canvases etc.
        """
        for c in self.mapCanvases():
            c.blockSignals(True)

        while len(self.mapViews()) > 0:
            mapView: MapView = self.mapViews()[0]
            debugLog(f'Remove map view {mapView}')

            self.mMapViews.remove(mapView)
            mapView.setMapWidget(None)

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
        return (canvas.mapView(), canvas.tsd())

    def _updateCanvasDates(self, updateLayerCache: bool = True):

        visibleBefore = self.visibleTSDs()
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

            i_middle = closest_index(self.mCurrentDate, visible)
            i_visible = list(range(len(visible)))
            i_visible = sorted(i_visible, key=lambda i: abs(i - i_middle))
            i_visible = i_visible[0: min(len(i_visible), nCanvases)]

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
                            canvas.setLayers(self.mMapLayerCache.pop(key))
                        bTSDChanged = True

                    # canvas.setLayers()
        if bTSDChanged:
            self._updateCanvasAppearance()

        visible2 = self.visibleTSDs()
        if visible2 != visibleBefore:
            self.sigVisibleDatesChanged.emit(visible2)

        self._freeUnusedMapLayers()

    def _freeUnusedMapLayers(self):

        layers = [l for l in self.mMapLayerStore.mapLayers().values() if isinstance(l, SensorProxyLayer)]
        needed = self.usedLayers()
        toRemove = [l for l in layers if isinstance(l, SensorProxyLayer) and l not in needed]

        # todo: use a kind of caching

        # remove layers from MapLayerCache and MapLayerStore
        for mv in self.mMapLayerCache.keys():
            layers = [l for l in self.mMapLayerCache[mv] if l not in toRemove]
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

    def _updateCanvasAppearance(self, mapView=None):

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
            errorText = ''
            for canvas in self.mCanvases[mapView]:
                assert isinstance(canvas, MapCanvas)

                # set overall visibility
                if canvas.isVisible() != v:
                    canvas.setVisible(v)

                infoItem: MapCanvasInfoItem = canvas.infoItem()
                infoItem.setTextFormat(tf)
                infoItem.setVisible(infoItemVisible)

                expr = QgsExpression(mapView.mapInfoExpression())
                infoItem.setInfoText(None)
                if isinstance(expr, QgsExpression) and expr.expression() != '':
                    # context = QgsExpressionContext([QgsExpressionContextScope(canvas.expressionContextScope())])
                    context: QgsExpressionContext = QgsExpressionContext()
                    context.appendScope(QgsExpressionContextUtils.globalScope())
                    context.appendScope(QgsExpressionContextScope(canvas.expressionContextScope()))

                    if expr.isValid():
                        expr2 = QgsExpression(expr)

                        infoText = expr2.evaluate(context)
                        if not expr2.hasEvalError():
                            # print(infoText)
                            infoItem.setInfoText(str(infoText))
                        else:
                            if errorText == '':
                                errorText = expr2.evalErrorString()
                    else:
                        if errorText == '':
                            errorText = expr.parserErrorString()

                canvas.addToRefreshPipeLine(MapCanvas.Command.UpdateMapItems)
                if canvas.canvasColor() != bg:
                    canvas.addToRefreshPipeLine(mapView.mapBackgroundColor())

            mapView.setInfoExpressionError(errorText)


class MapViewDock(QgsDockWidget):
    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    sigMapCanvasTextFormatChanged = pyqtSignal(QgsTextFormat)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigMapsPerMapViewChanged = pyqtSignal(int, int)
    sigMapTextFormatChanged = pyqtSignal(QgsTextFormat)

    def setTimeSeries(self, timeSeries: TimeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensor)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensor)

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
        self.btnMapCanvasColor.colorChanged.connect(self.onMapCanvasColorChanged)
        self.onMapCanvasColorChanged(self.btnMapCanvasColor.color())
        self.btnTextFormat.changed.connect(lambda *args: self.sigMapTextFormatChanged.emit(self.mapTextFormat()))
        self.btnApplySizeChanges.clicked.connect(self.onApplyButtonClicked)

        self.actionAddMapView.triggered.connect(self.createMapView)
        self.actionRemoveMapView.triggered.connect(
            lambda: self.removeMapView(self.currentMapView()) if self.currentMapView() else None)

        self.toolBox.currentChanged.connect(self.onToolboxIndexChanged)

        self.spinBoxMapSizeX.valueChanged.connect(lambda: self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda: self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()
        # self.mLastMapViewColumns: int = self.sbMapViewColumns.value()
        # self.mLastMapViewRows: int = self.sbMapViewRows.value()

        self.mTimeSeries = None
        self.mMapWidget = None

    def exclusiveMapViewVisibility(self) -> bool:
        return self.optionMutuallyExclusiveMapViews.isChecked()

    def onNextMapView(self):
        mapViews = self.mapViews()
        if len(mapViews) > 1:
            current = self.currentMapView()
            i = mapViews.index(current) + 1
            if i >= len(mapViews):
                i = 0
            self.setCurrentMapView(mapViews[i])

    def onPreviousMapView(self):
        mapViews = self.mapViews()
        if len(mapViews) > 1:
            current = self.currentMapView()
            i = mapViews.index(current) - 1
            if i < 0:
                i = len(mapViews) - 1
            self.setCurrentMapView(mapViews[i])

    def onMapCanvasColorChanged(self, color: QColor):
        # todo: find a way to display the map canvas color in background
        css = f"QgsFontButton#btnTextFormat{{background-color:{color.name()}; }}"
        self.btnTextFormat.setStyleSheet(css)
        self.sigMapCanvasColorChanged.emit(color)

    def onApplyButtonClicked(self):
        self.sigMapSizeChanged.emit(QSize(self.spinBoxMapSizeX.value(), self.spinBoxMapSizeY.value()))
        self.sigMapsPerMapViewChanged.emit(self.sbMapViewColumns.value(), self.sbMapViewRows.value())

    def setMapWidget(self, mw) -> MapWidget:
        """
        Connects this MapViewDock with a MapWidget
        :param mw: MapWidget
        :return:
        """
        assert isinstance(mw, MapWidget)

        assert mw.timeSeries() == self.mTimeSeries, 'Set the time series first!'
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

        self.sigMapViewAdded.connect(mw.addMapView)
        self.sigMapViewRemoved.connect(mw.removeMapView)
        mw.sigMapViewAdded.connect(self.addMapView)
        mw.sigMapViewRemoved.connect(self.removeMapView)

        for mapView in mw.mapViews():
            self.addMapView(mapView)

        return self.mMapWidget

    def mapWidget(self) -> MapWidget:
        """
        Returns the connected MapWidget
        :return: MapWidget
        """
        return self.mMapWidget

    def mapViews(self) -> List[MapView]:
        """
        Returns the defined MapViews
        :return: [list-of-MapViews]
        """
        assert isinstance(self.toolBox, QToolBox)
        mapViews = []
        for i in range(self.toolBox.count()):
            item = self.toolBox.widget(i)
            if isinstance(item, MapView):
                mapViews.append(item)
        return mapViews

    def mapCanvases(self) -> list:
        """
        Returns all MapCanvases from all MapViews
        :return: [list-of-MapCanvases]
        """

        maps = []
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            maps.extend(mapView.mapCanvases())
        return maps

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
        mapView.sigShowProfiles.connect(self.sigShowProfiles)
        mapView.setTimeSeries(self.mTimeSeries)
        self.addMapView(mapView)
        return mapView

    def onInfoOptionToggled(self):

        self.sigMapInfoChanged.emit()
        s = ""

    def addMapView(self, mapView: MapView):
        """
        Adds a MapView
        :param mapView: MapView
        """
        assert isinstance(mapView, MapView)
        if mapView not in self:
            mapView.sigTitleChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            # mapView.sigVisibilityChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            mapView.sigCanvasAppearanceChanged.connect(lambda *args, mv=mapView: self.onMapViewUpdated(mv))
            self.sigMapCanvasColorChanged.connect(mapView.setMapBackgroundColor)
            self.sigMapCanvasTextFormatChanged.connect(mapView.setMapTextFormat)
            i = self.toolBox.addItem(mapView, mapView.windowIcon(), mapView.title())
            self.toolBox.setCurrentIndex(i)

            self.onMapViewUpdated(mapView)

            if len(self.mapViews()) == 1:
                self.setMapTextFormat(mapView.mapTextFormat())

            self.sigMapViewAdded.emit(mapView)

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
        if mapView in self.mapViews():
            for i in range(self.toolBox.count()):
                w = self.toolBox.widget(i)
                if isinstance(w, MapView) and w == mapView:
                    self.toolBox.removeItem(i)
                    mapView.close()
                    if self.toolBox.count() >= i:
                        self.toolBox.setCurrentIndex(min(i, self.toolBox.count() - 1))

            self.sigMapViewRemoved.emit(mapView)
        return mapView

    def __len__(self) -> int:
        """
        Returns the number of MapViews
        :return: int
        """
        return len(self.mapViews())

    def __iter__(self):
        """
        Provides an iterator over all MapViews
        :return:
        """
        return iter(self.mapViews())

    def __getitem__(self, slice):
        return self.mapViews()[slice]

    def __contains__(self, mapView):
        return mapView in self.mapViews()

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViews().index(mapView)

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
        assert isinstance(mapView, MapView) and mapView in self.mapViews()

        if self.exclusiveMapViewVisibility():
            for mv in self.mapViews():
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

    def currentMapView(self) -> MapView:
        w = self.toolBox.currentWidget()
        if isinstance(w, MapView):
            return w
        else:
            # return first map view
            views = self.mapViews()
            if len(views) > 0:
                return views[0]
        return None
