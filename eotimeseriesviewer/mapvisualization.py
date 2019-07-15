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


import os, sys, re, fnmatch, collections, copy, traceback, bisect
from qgis.core import *
from qgis.core import QgsContrastEnhancement, QgsRasterShader, QgsColorRampShader,  QgsProject, QgsCoordinateReferenceSystem, \
    QgsRasterLayer, QgsVectorLayer, QgsMapLayer, QgsMapLayerProxyModel, QgsColorRamp, QgsSingleBandPseudoColorRenderer

from qgis.gui import *
from qgis.gui import QgsDockWidget, QgsMapCanvas, QgsMapTool, QgsCollapsibleGroupBox
from PyQt5.QtXml import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import numpy as np
from .utils import *
from .import Option, OptionListModel
from .timeseries import SensorInstrument, TimeSeriesDate, TimeSeries, SensorProxyLayer
from .utils import loadUI
from .mapviewscrollarea import MapViewScrollArea
from .mapcanvas import MapCanvas, MapTools, MapCanvasInfoItem, MapCanvasMapTools
from .externals.qps.crosshair.crosshair import getCrosshairStyle, CrosshairStyle
from .externals.qps.layerproperties import showLayerPropertiesDialog
from .externals.qps.maptools import *

#assert os.path.isfile(dummyPath)
#lyr = QgsRasterLayer(dummyPath)
#assert lyr.isValid()
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)

KEY_LOCKED_LAYER = 'eotsv/locked'
KEY_SENSOR_GROUP = 'eotsv/sensorgroup'
KEY_SENSOR_LAYER = 'eotsv/sensorlayer'



class MapViewLayerTreeViewMenuProvider(QgsLayerTreeViewMenuProvider):

    def __init__(self, mapView, view: QgsLayerTreeView, canvas: QgsMapCanvas):
        super(MapViewLayerTreeViewMenuProvider, self).__init__()
        assert isinstance(view, QgsLayerTreeView)
        assert isinstance(canvas, QgsMapCanvas)
        self.mLayerTreeView = view
        self.mDummyCanvas = canvas
        self.mDefActions = QgsLayerTreeViewDefaultActions(self.mLayerTreeView)
        self.mMapView = mapView

        self.actionAddGroup = self.mDefActions.actionAddGroup()
        self.actionRename = self.mDefActions.actionRenameGroupOrLayer()
        self.actionRemove = self.mDefActions.actionRemoveGroupOrLayer()
        #self.actionZoomToLayer = self.mDefActions.actionZoomToGroup(self.mDummyCanvas)
        self.actionCheckAndAllChildren = self.mDefActions.actionCheckAndAllChildren()
        self.actionShowFeatureCount = self.mDefActions.actionShowFeatureCount()
        #self.actionZoomToLayer = self.mDefActions.actionZoomToLayer(self.mDummyCanvas)
        #self.actionZoomToSelected = self.mDefActions.actionZoomToSelection(self.mDummyCanvas)
        #self.actionZoomToGroup = self.mDefActions.actionZoomToGroup(self.mDummyCanvas)
        self.actionAddEOTSVSpectralProfiles = QAction('Add Spectral Profile Layer')

        self.actionAddEOTSVTemporalProfiles = QAction('Add Temporal Profile Layer')

    def mapView(self):
        return self.mMapView

    def layerTreeView(self)->QgsLayerTreeView:
        return self.mLayerTreeView

    def layerTree(self)->QgsLayerTree:
        return self.layerTreeModel().rootGroup()

    def layerTreeModel(self)->QgsLayerTreeModel:
        return self.layerTreeView().model()

    def createContextMenu(self)->QMenu:

        model = self.layerTreeModel()
        ltree = self.layerTree()
        view = self.layerTreeView()
        g = view.currentGroupNode()
        l = view.currentLayer()
        i = view.currentIndex()
        #fixedNodes = len([l for l in view.selectedLayersRecursive() if l.property(KEY_LOCKED_LAYER) == True]) > 0 or \
        #             isinstance(g, QgsLayerTreeGroup) and g.property(KEY_LOCKED_LAYER) == True

        # disable actions
        #self.actionRemove.setEnabled(fixedNodes == False)

        menu = QMenu(view)
        isSensorGroup = isinstance(g, QgsLayerTreeGroup) and g.customProperty(KEY_SENSOR_GROUP) in [True, 'true']
        isSensorLayer = isinstance(l, QgsRasterLayer) and l.customProperty(KEY_SENSOR_LAYER) in [True, 'true']
        self.actionRemove.setEnabled(not (isSensorGroup or isSensorLayer))
        self.actionAddGroup.setEnabled(not (isSensorGroup or isSensorLayer))
        menu.addAction(self.actionAddGroup)
        menu.addAction(self.actionRename)
        menu.addAction(self.actionRemove)

        #menu.addAction(self.actionZoomToGroup)
        #menu.addAction(self.actionZoomToLayer)
        #menu.addAction(self.actionZoomToSelected)

        menu.addSeparator()

        menu.addAction(self.actionAddEOTSVSpectralProfiles)
        menu.addAction(self.actionAddEOTSVTemporalProfiles)

        menu.addSeparator()

        centerCanvas = None
        if isinstance(self.mapView(), MapView):
            visibleCanvases = self.mapView().visibleMapCanvases()
            if len(visibleCanvases) > 0:
                i = int(len(visibleCanvases) / 2)
                centerCanvas = visibleCanvases[i]

        a = menu.addAction('Set Properties')

        a.triggered.connect(lambda *args,
                                   canvas = centerCanvas,
                                   lyr = l,
                                   b = not isinstance(l, SensorProxyLayer):
                            showLayerPropertiesDialog(lyr, canvas, useQGISDialog=b))

        a.setEnabled(isinstance(centerCanvas, QgsMapCanvas))

        from .externals.qps.layerproperties import pasteStyleFromClipboard, pasteStyleToClipboard
        a = menu.addAction('Copy Style')
        a.setToolTip('Copy the current layer style to clipboard')
        a.triggered.connect(lambda *args, lyr=l: pasteStyleToClipboard(lyr))

        a = menu.addAction('Paste Style')
        a.setEnabled('application/qgis.style' in QApplication.clipboard().mimeData().formats())
        a.triggered.connect(lambda *args, lyr=l: pasteStyleFromClipboard(lyr))

        #a = menu.addAction('Settings')
        #from qps.layerproperties import showLayerPropertiesDialog
        #a.triggered.connect(lambda *args, lyr=l:showLayerPropertiesDialog(lyr, self._canvas))

        return menu

class MapViewLayerTreeModel(QgsLayerTreeModel):
    """
    Layer Tree as shown in a MapView
    """
    def __init__(self, rootNode, parent=None):
        super(MapViewLayerTreeModel, self).__init__(rootNode, parent=parent)

    def dataXXX(self, index:QModelIndex, role=Qt.DisplayRole):
        node = self.index2node(index)
        # if node.name() == 'testlayer':
        #     s = ""

        if True:
            if isinstance(node, QgsLayerTreeGroup) and node.customProperty(KEY_SENSOR_GROUP) in ['true', True]:
                if role == Qt.FontRole:
                    f = super(MapViewLayerTreeModel, self).data(index, role=role)
                    f.setBold(True)
                    return f
            if isinstance(node, QgsLayerTreeLayer) and node.customProperty(KEY_SENSOR_LAYER) in ['true', True]:

                if role == Qt.FontRole:
                    f = super(MapViewLayerTreeModel, self).data(index, role=role)
                    assert isinstance(f, QFont)
                    f.setItalic(True)
                    return f

                if role == Qt.DecorationRole:
                    return QIcon(':/timeseriesviewer/icons/icon.svg')

        return super(MapViewLayerTreeModel, self).data(index, role=role)

    def flagsXXX(self, index:QModelIndex):

        f = super(MapViewLayerTreeModel, self).flags(index)

        node = self.index2node(index)
        if isinstance(node, QgsLayerTreeNode) and ( \
                node.customProperty(KEY_SENSOR_LAYER) in ['true', True] or \
                node.customProperty(KEY_SENSOR_GROUP) in ['true', True]):
            f = f ^ Qt.ItemIsDragEnabled
            f = f ^ Qt.ItemIsDropEnabled

        return f


class MapView(QFrame, loadUIFormClass(jp(DIR_UI, 'mapview.ui'))):
    """
    A MapView defines how a single map canvas visualizes sensor specific EOTS data plus additional vector overlays
    """
    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibilityChanged = pyqtSignal(bool)
    sigCrosshairVisibilityChanged = pyqtSignal(bool)

    sigTitleChanged = pyqtSignal(str)
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)

    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def __init__(self, name='Map View', parent=None):
        super(MapView, self).__init__(parent)
        self.setupUi(self)

        m = QMenu(self.btnToggleCrosshair)
        m.addAction(self.actionSetCrosshairStyle)

        self.btnToggleCrosshair.setMenu(m)
        self.btnToggleCrosshair.setDefaultAction(self.actionToggleCrosshairVisibility)
        self.btnToggleMapViewVisibility.setDefaultAction(self.actionToggleMapViewHidden)
        self.tbName.textChanged.connect(self.onTitleChanged)
        self.actionSetCrosshairStyle.triggered.connect(self.onChangeCrosshairStyle)
        self.actionToggleMapViewHidden.toggled.connect(lambda isHidden: self.setVisibility(not isHidden))
        self.actionToggleCrosshairVisibility.toggled.connect(self.setCrosshairVisibility)

        self.actionAddVectorLayer.triggered.connect(self.onAddVectorLayer)
        self.actionAddRasterLayer.triggered.connect(self.onAddRasterLayer)
        self.btnAddVectorLayer.setDefaultAction(self.actionAddVectorLayer)
        self.btnAddRasterLayer.setDefaultAction(self.actionAddRasterLayer)

        self.btnHighlightMapView.setDefaultAction(self.actionHighlightMapView)
        self.actionHighlightMapView.triggered.connect(lambda: self.setHighlighted(True, timeout=500))

        self.mCurrentLayer = None

        self.mTimeSeries = None
        self.mSensorLayerList = list()
        self.mMapCanvases = list()
        assert isinstance(self.mLayerTreeView, QgsLayerTreeView)

        self.mDummyCanvas = QgsMapCanvas() # dummy map canvas for dummy layers
        self.mDummyCanvas.setVisible(False)

        self.mLayerTree = QgsLayerTree()
        self.mLayerTreeMapCanvasBridget = QgsLayerTreeMapCanvasBridge(self.mLayerTree, self.mDummyCanvas)

        # self.mLayerTreeModel = QgsLayerTreeModel(self.mLayerTree)
        self.mLayerTreeModel = MapViewLayerTreeModel(self.mLayerTree)

        self.mLayerTreeModel.setFlags(QgsLayerTreeModel.AllowNodeChangeVisibility |
                                      QgsLayerTreeModel.AllowNodeRename |
                                      QgsLayerTreeModel.AllowNodeReorder)

        self._createSensorNode()

        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mMapLayerTreeViewMenuProvider = MapViewLayerTreeViewMenuProvider(self, self.mLayerTreeView, self.mDummyCanvas)

        # register some actions that interact with other GUI elements
        self.mMapLayerTreeViewMenuProvider.actionAddEOTSVSpectralProfiles.triggered.connect(self.addSpectralProfileLayer)
        self.mMapLayerTreeViewMenuProvider.actionAddEOTSVTemporalProfiles.triggered.connect(self.addTemporalProfileLayer)

        self.mLayerTreeView.setMenuProvider(self.mMapLayerTreeViewMenuProvider)
        self.mLayerTreeView.currentLayerChanged.connect(self.setCurrentLayer)
        self.mLayerTree.removedChildren.connect(self.onChildNodesRemoved)

        self.mIsVisible = True
        self.setTitle(name)

        m = QMenu()
        m.addAction(self.optionShowDate)
        m.addAction(self.optionShowSensorName)
        m.addAction(self.optionShowMapViewName)
        self.btnInfoOptions.setMenu(m)

        fixMenuButtons(self)


    def setName(self, name:str):
        self.setTitle(name)

    def name(self)->str:
        return self.title()

    def visibleMapCanvases(self)->list:
        """
        Returns the currently visible mapcanvases
        :return: [list-of-MapCanvases]
        """
        return [m for m in self.mapCanvases() if m.isVisibleToViewport()]

    def onAddVectorLayer(self):
        """
        Slot that opens a SelectMapLayersDialog to add a vector layer
        """
        from .externals.qps.utils import SelectMapLayersDialog
        d = SelectMapLayersDialog()
        d.setWindowTitle('Select Vector Layer')
        d.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        if d.exec() == QDialog.Accepted:
            for l in d.mapLayers():
                self.addLayer(l)

    def onAddRasterLayer(self):
        """
        Slot that opens a SelectMapLayersDialog to add a vector layer
        """
        from .externals.qps.utils import SelectMapLayersDialog
        d = SelectMapLayersDialog()
        d.setWindowTitle('Select Raster Layer')
        d.addLayerDescription('Raster Layer', QgsMapLayerProxyModel.RasterLayer)
        if d.exec() == QDialog.Accepted:
            for l in d.mapLayers():
                self.addLayer(l)


    def setCurrentLayer(self, layer:QgsMapLayer):
        """
        Sets the QgsMapCanvas.currentLayer() that is used by some QgsMapTools
        :param layer: QgsMapLayer | None
        :return:
        """
        assert layer is None or isinstance(layer, QgsMapLayer)

        self.mCurrentLayer = layer

        if layer not in self.mSensorLayerList:
            for c in self.mapCanvases():
                c.setCurrentLayer(layer)
        else:
            s = ""



    def addSpectralProfileLayer(self):
        """Adds the EOTSV Spectral Profile Layer"""
        from eotimeseriesviewer.main import TimeSeriesViewer
        tsv = TimeSeriesViewer.instance()
        if isinstance(tsv, TimeSeriesViewer):
            lyr = tsv.spectralLibrary()
            if lyr not in self.layers():
                self.addLayer(lyr)

    def addTemporalProfileLayer(self):
        """Adds the EOTSV Temporal Profile Layer"""
        from eotimeseriesviewer.main import TimeSeriesViewer
        tsv = TimeSeriesViewer.instance()
        if isinstance(tsv, TimeSeriesViewer):
            lyr = tsv.temporalProfileLayer()
            if lyr not in self.layers():
                self.addLayer(lyr)


    def addLayer(self, layer:QgsMapLayer):
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

    def _containsSensorNode(self, root:QgsLayerTreeGroup)->bool:
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
        style = getCrosshairStyle(parent=self, crosshairStyle=self.crosshairStyle())
        if isinstance(style, CrosshairStyle):
            self.setCrosshairStyle(style)

    def setVisibility(self, b: bool):
        """
        Sets the map view visibility
        :param b: bool
        """
        assert isinstance(b, bool)

        changed = False

        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            if not mapCanvas.isVisible() == b:
                changed = True
                mapCanvas.setVisible(b)

        if self.actionToggleMapViewHidden.isChecked() == b:
            self.actionToggleMapViewHidden.setChecked(not b)

        if changed:
            self.sigMapViewVisibilityChanged.emit(b)

    def isVisible(self)->bool:
        """
        Returns the map view visibility
        :return: bool
        """
        return not self.actionToggleMapViewHidden.isChecked()

    def mapCanvases(self)->list:
        """
        Returns the MapCanvases related to this map view
        :return: [list-of-MapCanvases]
        """
        return self.mMapCanvases[:]

    def onTitleChanged(self, *args):
        self.setWindowTitle('Map View "{}"'.format(self.title()))
        self.sigTitleChanged.emit(self.title())

    def setTimeSeries(self, timeSeries:TimeSeries):
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

    def timeSeries(self)->TimeSeries:
        """
        Returns the TimeSeries this mapview is connected with
        :return: TimeSeries
        """
        return self.mTimeSeries

    def setTitle(self, title:str):
        """
        Sets the widget title
        :param title: str
        """
        old = self.title()
        if old != title:
            self.tbName.setText(title)


    def layers(self)->list:
        """
        Returns the visible layers, including proxy layer for time-series data
        :return: [list-of-QgsMapLayers]
        """
        return [l for l in self.mLayerTree.checkedLayers() if isinstance(l, QgsMapLayer)]

    def title(self)->str:
        """
        Returns the MapView title
        :return: str
        """
        return self.tbName.text()

    def refreshMapView(self, sensor=None):
        for mapCanvas in self.mapCanvases():
            if isinstance(mapCanvas, MapCanvas):
                mapCanvas.refresh()

    def setCrosshairStyle(self, crosshairStyle:CrosshairStyle):
        """
        Seths the CrosshairStyle of this MapView
        :param crosshairStyle: CrosshairStyle
        """
        from eotimeseriesviewer import CrosshairStyle
        assert isinstance(crosshairStyle, CrosshairStyle)
        srcCanvas = self.sender()
        if isinstance(srcCanvas, MapCanvas):
            dstCanvases = [c for c in self.mapCanvases() if c != srcCanvas]
        else:
            dstCanvases = [c for c in self.mapCanvases()]

        for mapCanvas in dstCanvases:
            mapCanvas.setCrosshairStyle(crosshairStyle, emitSignal=False)


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
                QTimer.singleShot(timeout, lambda : self.setHighlighted(False))
        else:
            for mapCanvas in self.mapCanvases():
                mapCanvas.setStyleSheet(styleOff)

    def crosshairStyle(self)->CrosshairStyle:
        """
        Returns the CrosshairStyle
        :return:
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            style = c.crosshairStyle()
            if isinstance(style, CrosshairStyle):
                return style
        return None

    def setCrosshairVisibility(self, b:bool):
        """
        Enables / diables the map canvas crosshair.
        :param b: bool
        """
        # set the action checked state first
        if self.actionToggleCrosshairVisibility.isChecked() != b:
            self.actionToggleCrosshairVisibility.setChecked(b)
        else:
            self.sigCrosshairVisibilityChanged.emit(b)

    def sensorProxyLayers(self)->list:
        layers = [n.layer() for n in self.mLayerTreeSensorNode.findLayers()]
        return [l for l in layers if isinstance(l, SensorProxyLayer)]

    def sensorProxyLayer(self, sensor:SensorInstrument)->SensorProxyLayer:
        """
        Returns the proxy layer related to a SensorInstrument
        :param sensor: SensorInstrument
        :return: SensorLayer
        """
        for l in self.sensorProxyLayers():
            if l.sensor() == sensor:
                return l
        return None

    def sensors(self)->list:
        """
        Returns a list of SensorsInstruments
        :return: [list-of-SensorInstruments]
        """

        return [t[0] for t in self.mSensorLayerList]

    def addSensor(self, sensor:SensorInstrument):
        """
        Adds a SensorInstrument to be shown in this MapView. Each sensor will be represented as a Raster Layer in the
        Tree Model.
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor not in self.sensors():
            dummyLayer = sensor.proxyLayer()
            assert isinstance(dummyLayer.renderer(), QgsRasterRenderer)
            dummyLayer.rendererChanged.connect(lambda sensor=sensor: self.onSensorRendererChanged(sensor))

            #QgsProject.instance().addMapLayer(dummyLayer)

            layerTreeLayer = self.mLayerTreeSensorNode.addLayer(dummyLayer)
            assert isinstance(layerTreeLayer, QgsLayerTreeLayer)
            layerTreeLayer.setCustomProperty(KEY_LOCKED_LAYER, True)
            layerTreeLayer.setCustomProperty(KEY_SENSOR_LAYER, True)
            self.mSensorLayerList.append((sensor, dummyLayer))

    def onSensorRendererChanged(self, sensor:SensorInstrument):
        for c in self.sensorCanvases(sensor):
            assert isinstance(c, MapCanvas)
            c.addToRefreshPipeLine(MapCanvas.Command.RefreshRenderer)

    def sensorCanvases(self, sensor:SensorInstrument)->list:
        """
        Returns the MapCanvases that show a layer with data for the given ``sensor``
        :param sensor: SensorInstrument
        :return:
        """
        assert isinstance(sensor, SensorInstrument)
        return [c for c in self.mapCanvases() if isinstance(c, MapCanvas) and c.tsd().sensor() == sensor]


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

    def removeSensor(self, sensor:SensorInstrument):
        """
        Removes a sensor from this map view
        :param sensor:
        :return:
        """
        pair = None
        for i, t in enumerate(self.mSensorLayerList):
            if t[0] == sensor:
                pair = t
                break
        assert pair is not None, 'Sensor "{}" not found'.format(sensor.name())
        self.mLayerTreeSensorNode.removeLayer(pair[1])
        self.mSensorLayerList.remove(pair)


    def hasSensor(self, sensor)->bool:
        """
        :param sensor:
        :return:
        """
        assert isinstance(sensor, SensorInstrument)
        return sensor in self.sensors()

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
                lambda : self.doRefresh([mapView])
            )
            self.mMapViewList.insert(i + j, mapView)
        self.endInsertRows()
        self.sigMapViewsAdded.emit(mapViews)


    def doRefresh(self, mapViews):
        for mapView in mapViews:
            idx = self.mapView2idx(mapView)
            self.dataChanged.emit(idx, idx)

    def removeMapView(self, mapView):
        self.removeMapViews([mapView])

    def removeMapViews(self, mapViews):
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
            value = '{} {}'.format(index.row() +1 , mapView.title())
        #if role == Qt.DecorationRole:
            #value = classInfo.icon(QSize(20,20))
        if role == Qt.UserRole:
            value = mapView
        return value

class MapViewDock(QgsDockWidget, loadUI('mapviewdock.ui')):

    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigMapsPerMapViewChanged = pyqtSignal(int)

    def setTimeSeries(self, timeSeries:TimeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensor)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensor)

    def __init__(self, parent=None):
        super(MapViewDock, self).__init__(parent)
        self.setupUi(self)

        self.baseTitle = self.windowTitle()

        self.btnAddMapView.setDefaultAction(self.actionAddMapView)
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)

        self.btnCrs.crsChanged.connect(self.sigCrsChanged)
        self.btnMapCanvasColor.colorChanged.connect(self.onMapCanvasBackgroundColorChanged)
        self.btnApplySizeChanges.clicked.connect(lambda : self.sigMapSizeChanged.emit(QSize(self.spinBoxMapSizeX.value(),self.spinBoxMapSizeY.value())))

        self.actionAddMapView.triggered.connect(self.createMapView)
        self.actionRemoveMapView.triggered.connect(lambda : self.removeMapView(self.currentMapView()) if self.currentMapView() else None)
        self.actionApplyStyles.triggered.connect(self.refreshCurrentMapView)

        self.toolBox.currentChanged.connect(self.onToolboxIndexChanged)

        self.spinBoxMapSizeX.valueChanged.connect(lambda: self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda: self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()

        self.sbMpMV.valueChanged.connect(self.sigMapsPerMapViewChanged)
        self.mTimeSeries = None




    def mapViews(self)->list:
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

    def mapCanvases(self)->list:
        """
        Returns all MapCanvases from all MapViews
        :return: [list-of-MapCanvases]
        """

        maps = []
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            maps.extend(mapView.mapCanvases())
        return maps

    def setCrs(self, crs):
        if isinstance(crs, QgsCoordinateReferenceSystem):
            old = self.btnCrs.crs()
            if old != crs:
                self.btnCrs.setCrs(crs)
                self.btnCrs.setLayerCrs(crs)

    def mapsPerMapView(self)->int:
        return self.sbMpMV.value()

    def setMapsPerMapView(self, n:int):
        assert n > 0
        self.sbMpMV.setValue(n)


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
        #1. set size of other dimension accordingly
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

    def mapSize(self)->QSize:
        return QSize(self.spinBoxMapSizeX.value(),
                     self.spinBoxMapSizeY.value())


    def refreshCurrentMapView(self, *args):
        mv = self.currentMapView()
        if isinstance(mv, MapView):
            mv.refreshMapView()
        else:
            s  =""


    def dummySlot(self):
        s  =""

    def onMapViewsRemoved(self, mapViews):

        for mapView in mapViews:
            idx = self.stackedWidget.indexOf(mapView.ui)
            if idx >= 0:
                self.stackedWidget.removeWidget(mapView.ui)
                mapView.ui.close()
            else:
                s = ""


        self.actionRemoveMapView.setEnabled(len(self.mMapViews) > 0)


    def mapBackgroundColor(self)->QColor:
        """
        Returns the map canvas background color
        :return: QColor
        """
        return self.btnMapCanvasColor.color()


    def setMapBackgroundColor(self, color:QColor):
        """
        Sets the MapCanvas background color
        :param color: QColor
        """
        if color != self.mapBackgroundColor():
            self.btnMapCanvasColor.setColor(color)


    def onMapCanvasBackgroundColorChanged(self, color:QColor):
        """
        Reacts on a changes map color
        :param color: QColor
        """
        assert isinstance(color, QColor)
        self.mColor = color
        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.addToRefreshPipeLine(color)

        self.sigMapCanvasColorChanged.emit(color)


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
            #mapView.ui.scrollArea.update()
            s = ""
            #setMinimumSize(mapView.ui.scrollAreaWidgetContents.sizeHint())
            #hint = contents.sizeHint()
            #contents.setMinimumSize(hint)
        if isinstance(nextShown, MapView):
            self.setCurrentMapView(nextShown)

        for mapView in mapViews:
            self.sigMapViewAdded.emit(mapView)

    def updateButtons(self, *args):
        b = len(self.mMapViews) > 0
        self.actionRemoveMapView.setEnabled(b)
        self.actionApplyStyles.setEnabled(b)
        self.actionHighlightMapView.setEnabled(b)


    def createMapView(self, name:str=None)->MapView:
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
            mapView.optionShowDate.setChecked(True)
            mapView.optionShowSensorName.setChecked(True)

        mapView.setTitle(title)
        mapView.sigShowProfiles.connect(self.sigShowProfiles)
        mapView.setTimeSeries(self.mTimeSeries)
        self.addMapView(mapView)
        return mapView



    def addMapView(self, mapView:MapView):
        """
        Adds a MapView
        :param mapView: MapView
        """
        assert isinstance(mapView, MapView)
        mapView.sigTitleChanged.connect(lambda *args, mv=mapView : self.onMapViewUpdated(mv))
        mapView.sigMapViewVisibilityChanged.connect(lambda *args, mv=mapView : self.onMapViewUpdated(mv))

        i = self.toolBox.addItem(mapView, mapView.windowIcon(), mapView.title())
        self.toolBox.setCurrentIndex(i)
        self.onMapViewUpdated(mapView)
        self.sigMapViewAdded.emit(mapView)

    def onToolboxIndexChanged(self):

        b = isinstance(self.toolBox.currentWidget(), MapView)
        self.actionRemoveMapView.setEnabled(b)

    def onMapViewUpdated(self, mapView:MapView):
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
                    icon = QIcon(":/timeseriesviewer/icons/mapview.svg")
                else:
                    icon = QIcon(":/timeseriesviewer/icons/mapviewHidden.svg")

                self.toolBox.setItemIcon(i, icon)
                self.toolBox.setItemText(i, 'Map View {} "{}"'.format(numMV, mapView.title()))
                break

    def removeMapView(self, mapView:MapView)->MapView:
        """
        Removes a MapView
        :param mapView: MapView
        :return: MapView
        """
        assert mapView in self.mapViews()
        for i in range(self.toolBox.count()):
            w = self.toolBox.widget(i)
            if isinstance(w, MapView) and w == mapView:
                self.toolBox.removeItem(i)
                mapView.close()
                if self.toolBox.count() >= i:
                    self.toolBox.setCurrentIndex(min(i, self.toolBox.count()-1))

        self.sigMapViewRemoved.emit(mapView)
        return mapView



    def __len__(self)->int:
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

    def addSensor(self, sensor:SensorInstrument):
        """
        Adds a new SensorInstrument
        :param sensor: SensorInstrument
        """
        for mapView in self.mapViews():
            mapView.addSensor(sensor)


    def removeSensor(self, sensor:SensorInstrument):
        """
        Removes a Sensor
        :param sensor: SensorInstrument
        """
        for mapView in self.mMapViews:
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

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViewsDefinitions.index(mapView)


    def setCurrentMapView(self, mapView):
        assert isinstance(mapView, MapView) and mapView in self.mapViews()
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

    def currentMapView(self):
        w = self.toolBox.currentWidget()
        if isinstance(w, MapView):
            return w
        return None


class MapWidget(QWidget, loadUIFormClass(jp(DIR_UI, 'mapwidget.ui'))):
    """
    This widget contains all maps
    """

    class ViewMode(enum.Enum):

        MapViewByRows = 1,
        MapViewByCols = 2


    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCRSChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigMapsPerMapViewChanged = pyqtSignal(int)
    sigMapViewsChanged = pyqtSignal()
    sigCurrentDateChanged = pyqtSignal(TimeSeriesDate)
    sigViewModeChanged = pyqtSignal(ViewMode)

    def __init__(self, *args, **kwds):
        super(MapWidget, self).__init__(*args, **kwds)
        self.setupUi(self)
        self.setContentsMargins(1,1,1,1)
        self.mGrid = QGridLayout()
        self.setLayout(self.mGrid)
        self.mGrid.setSpacing(0)
        self.mGrid.setContentsMargins(0,0,0,0)

        self.mMapLayerStore = QgsMapLayerStore()
        self.mMapViews = []
        self.mCanvases = dict()
        self.mTimeSeries = None

        self.mMapToolKey = MapTools.Pan
        self.mMapToolMode = None

        self.mViewMode = MapWidget.ViewMode.MapViewByRows
        self.mMpMV = 3

        self.mSpatialExtent = SpatialExtent.world()
        self.mCrs = self.mSpatialExtent.crs()
        self.mCurrentDate = None
        self.mMapSize = QSize(200, 200)

        self.mMapRefreshTimer = QTimer(self)
        self.mMapRefreshTimer.timeout.connect(self.timedRefresh)
        self.mMapRefreshTimer.setInterval(500)
        self.mMapRefreshTimer.start()

        #self.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))

    def setMapTool(self, mapToolKey:MapTools, mode):

        if self.mMapToolKey != mapToolKey or mode != self.mMapToolMode:
            self.mMapToolKey = mapToolKey
            self.mMapToolMode = mode

            for c in self.mapCanvases():
                assert isinstance(c, MapCanvas)
                mts = c.mapTools()
                mts.setSelectionMode()

    def visibleTSDs(self):

        for mv in self.mMapViews:
            tsds = []
            for c in self.mCanvases[mv]:
                if isinstance(c.tsd(), TimeSeriesDate):
                    tsds.append(c.tsd())

            return tsds
        return []

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the current SpatialExtent
        :return: SpatialExtent
        """
        return self.mSpatialExtent

    def setSpatialExtent(self, extent:SpatialExtent)->SpatialExtent:
        """
        Sets a SpatialExtent to all MapCanvases.
        :param extent: SpatialExtent
        :return: SpatialExtent the current SpatialExtent
        """

        if self.mSpatialExtent != extent:
            self.mSpatialExtent = extent

            for c in self.mapCanvases():
                assert isinstance(c, MapCanvas)
                c.addToRefreshPipeLine(extent)

            self.sigSpatialExtentChanged.emit(self.mSpatialExtent.__copy__())
        return self.spatialExtent()

    def setCrs(self, crs:QgsCoordinateReferenceSystem):
        """
        Sets the MapCanvas CRS.
        :param crs: QgsCoordinateReferenceSystem
        :return: QgsCoordinateReferenceSystem
        """

        self.mCrs = crs
        if isinstance(crs, QgsCoordinateReferenceSystem):
            for c in self.mapCanvases():
                c.setCrs(crs)

        return self.crs()

    def timedRefresh(self):
        """
        Calls the timedRefresh() routine for all MapCanvases
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            c.timedRefresh()

    def crs(self)->QgsCoordinateReferenceSystem:
        return self.mCrs

    def setTimeSeries(self, ts:TimeSeries)->TimeSeries:
        assert ts == None or isinstance(ts, TimeSeries)
        self.mTimeSeries = ts
        return self.timeSeries()

    def timeSeries(self)->TimeSeries:
        return self.mTimeSeries

    def setMode(self, mode:ViewMode):

        if mode != self.mViewMode:
            self.mViewMode = mode
            self._updateGrid()
            self.sigViewModeChanged.emit(self.mViewMode)

    def setMapsPerMapView(self, n:int):
        assert n > 0

        if n != self.mMpMV:
            self.mMpMV = n
            self._updateGrid()
            self.sigMapsPerMapViewChanged.emit(n)

    def setMapSize(self, size:QSize):

        if size != self.mMapSize:
            for canvas in self.mapCanvases():
                canvas.setFixedSize(size)

            self.mMapSize = size
            self._updateGridSize()
            self.sigMapSizeChanged.emit(size)


    def mapSize(self)->QSize:
        return self.mMapSize

    def mapCanvases(self)->list:
        return self.findChildren(MapCanvas)

    def mapViewCanvases(self, mapView:MapView):
        return self.mCanvases[mapView]

    def setCurrentDate(self, tsd:TimeSeriesDate):
        assert isinstance(tsd, TimeSeriesDate)

        b = tsd != self.mCurrentDate
        self.mCurrentDate = tsd

        if b:
            self._updateCanvasDates()


    def currentDate(self)->TimeSeriesDate:
        return self.mCurrentDate


    def addMapView(self, mapView:MapView):
        assert isinstance(mapView, MapView)
        if mapView not in self.mMapViews:

            self.mMapViews.append(mapView)

            # connect signals
            mapView.sigMapViewVisibilityChanged
            mapView.sigCrosshairVisibilityChanged

            self._updateGrid()
            self.sigMapViewsChanged.emit()


    def removeMapView(self, mapView:MapView):
        if mapView in self.mMapViews:
            self.mMapViews.remove(mapView)

            # disconnect signals


            self._updateGrid()
            self.sigMapViewsChanged.emit()




    def mapViews(self)->list:
        return self.mMapViews[:]


    def _cropGrid(self):
        if self.mViewMode == MapWidget.ViewMode.MapViewByRows:

            nc = self.mMpMV
            nr = len(self.mapViews())
        else:
            raise NotImplementedError()

        toRemove = []
        for row in range(nr, self.mGrid.rowCount()):
            for col in range(self.mGrid.columnCount()):
                item = self.mGrid.itemAtPosition(row, col)
                if isinstance(item, QLayoutItem) and isinstance(item.widget(), QWidget):
                    toRemove.append(item.widget())

        for col in range(nc, self.mGrid.columnCount()):
            for row in range(self.mGrid.rowCount()):
                item = self.mGrid.itemAtPosition(row, col)
                if isinstance(item, QLayoutItem) and isinstance(item.widget(), QWidget):
                    toRemove.append(item.widget())

        for w in toRemove:
            self.mGrid.removeWidget(w)
            w.setParent(None)
            w.setVisible(False)

    def _createMapCanvas(self)->MapCanvas:
        mapCanvas = MapCanvas()
        mapCanvas.setMapLayerStore(self.mMapLayerStore)

        # set general canvas properties
        mapCanvas.setFixedSize(self.mMapSize)
        mapCanvas.setDestinationCrs(self.mCrs)
        mapCanvas.setSpatialExtent(self.mSpatialExtent)

        # activate the current map tool
        mapTools = mapCanvas.mapTools()
        mapTools.activate(self.mMapToolKey)

        mt = mapCanvas.mapTool()
        if isinstance(mt, QgsMapToolSelect):
            mt.setSelectionMode(self.mMapToolMode)

        # connect signals
        self._connectCanvasSignals(mapCanvas)
        return mapCanvas

    def _connectCanvasSignals(self, mapCanvas:MapCanvas):
        mapCanvas.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        mapCanvas.sigDestinationCrsChanged.connect(self.setCrs)
        mapCanvas.sigCrosshairPositionChanged.connect(self.onCrosshairPositionChanged)

    def _disconnectCanvasSignals(self, mapCanvas:MapCanvas):
        mapCanvas.sigSpatialExtentChanged.disconnect(self.setSpatialExtent)
        mapCanvas.sigDestinationCrsChanged.disconnect(self.setCrs)
        mapCanvas.sigCrosshairPositionChanged.disconnect(self.onCrosshairPositionChanged)

    def onCrosshairPositionChanged(self, spatialPoint:SpatialPoint):
        self.TSV.setCurrentLocation(point, canvas)
        # lambda point, canvas=mapCanvas: self.TSV.setCurrentLocation(point, canvas))


    def _updateGrid(self):

        self._cropGrid() #remove canvases that we do not need

        oldCanvases = self.findChildren(MapCanvas)

        usedCanvases = []
        self.mCanvases.clear()

        if self.mViewMode == MapWidget.ViewMode.MapViewByRows:
            for row, mv in enumerate(self.mMapViews):
                assert isinstance(mv, MapView)
                self.mCanvases[mv] = []
                for col in range(self.mMpMV):
                    item = self.mGrid.itemAtPosition(row, col)
                    if isinstance(item, QLayoutItem) and isinstance(item.widget(), MapCanvas):
                        c = item.widget()
                    else:
                        c = self._createMapCanvas()
                        self.mGrid.addWidget(c, row, col)
                    assert isinstance(c, MapCanvas)
                    c.setFixedSize(self.mMapSize)
                    c.setTSD(None)
                    c.setMapView(mv)
                    usedCanvases.append(c)
                    self.mCanvases[mv].append(c)
        else:
            raise NotImplementedError()
        self._updateGridSize()
        self._updateCanvasDates()

        # remove old canvases
        for c in oldCanvases:
            if c not in usedCanvases:
                self._disconnectCanvasSignals(c)




    def _updateGridSize(self):

        self.mGrid.update()
        # self.resize(self.sizeHint())
        # self.setMaximumSize(self.sizeHint())
        self.setFixedSize(self.sizeHint())
        if self.parentWidget():
            w = self.parentWidget()
            assert isinstance(w, QWidget)
            w.setFixedSize(self.sizeHint())
            w.layout().update()
            w.update()


    def sizeHint(self):
        if True:
            w, h = self.mMapSize.width(), self.mMapSize.height()

            nx = self.mMpMV
            ny = len(self.mMapViews)

            m = self.contentsMargins()
            s = self.layout().spacing()

            w = w * nx + m.right() + m.left() + nx * s
            h = h * ny + m.top() + m.bottom() + ny * s
            return QSize(w, h)
        sh = super(MapWidget, self).sizeHint()
        return sh


    def _updateCanvasDates(self):
        if not (isinstance(self.mCurrentDate, TimeSeriesDate) and isinstance(self.timeSeries(), TimeSeries)):
            for c in self.findChildren(MapCanvas):
                assert isinstance(c, MapCanvas)
                c.setTSD(None)
        else:

            visible = [tsd for tsd in self.timeSeries() if tsd.isVisible()]
            if len(visible) == 0:
                return

            t = self.mCurrentDate.date()
            visible = sorted(visible, key=lambda tsd: abs(tsd.date() - t))
            visible = visible[0:min(len(visible), self.mMpMV)]
            visible = sorted(visible)

            for mapView in self.mapViews():
                for tsd, canvas in zip(visible, self.mCanvases[mapView]):
                    assert isinstance(tsd, TimeSeriesDate)
                    assert isinstance(canvas, MapCanvas)
                    canvas.setTSD(tsd)

                    #canvas.setLayers()
        self._updateCanvasInfo()


    def _updateCanvasInfo(self):
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            for canvas in self.mCanvases[mapView]:
                assert isinstance(canvas, MapCanvas)
                tsd = canvas.tsd()
                info = canvas.infoItem()
                assert isinstance(info, MapCanvasInfoItem)
                uc = []
                lc = []
                if isinstance(tsd, TimeSeriesDate):
                    if mapView.optionShowDate.isChecked():
                        uc += ['{}'.format(tsd.date())]
                    if mapView.optionShowMapViewName.isChecked():
                        lc += ['{}'.format(mapView.title())]
                    if mapView.optionShowSensorName.isChecked():
                        uc += ['{}'.format(tsd.sensor().name())]

                info.mUCText = ':'.join(uc)
                info.mLCText = ':'.join(lc)

class SpatialTemporalVisualization(QObject):
    """

    """
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)
    sigShowMapLayerInfo = pyqtSignal(dict)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigCRSChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigActivateMapTool = pyqtSignal(str)
    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)

    sigVisibleDatesChanged = pyqtSignal(list)

    def __init__(self, timeSeriesViewer):
        super(SpatialTemporalVisualization, self).__init__()
        # assert isinstance(timeSeriesViewer, TimeSeriesViewer), timeSeriesViewer

        # default map settings
        self.mSpatialExtent = SpatialExtent.world()
        #self.mCRS = self.mSpatialExtent.crs()
        self.ui = timeSeriesViewer.ui
        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.timeSeries()

        self.mMapWidget = self.ui.mapWidget
        assert isinstance(self.mMapWidget, MapWidget)
        self.mMapWidget.mMapLayerStore = self.TSV.mapLayerStore()
        self.mMapViewDock = self.ui.dockMapViews
        assert isinstance(self.mMapViewDock, MapViewDock)

        self.mMapViewDock.setTimeSeries(self.TS)
        self.mMapWidget.setTimeSeries(self.TS)
        self.mMapWidget.setMapSize(self.mapSize())

        # map-tool handling
        self.mMapToolKey = MapTools.Pan
        self.mMapToolMode = None

        for mv in self.mMapViewDock:
            self.mMapWidget.addMapView(mv)

        self.mMapViewDock.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.mMapViewDock.sigMapViewAdded.connect(self.mMapWidget.addMapView)
        self.mMapViewDock.sigMapViewRemoved.connect(self.mMapWidget.removeMapView)
        self.mMapViewDock.sigMapViewAdded.connect(self.sigMapViewAdded.emit)
        self.mMapViewDock.sigMapViewRemoved.connect(self.sigMapViewRemoved.emit)
        self.mMapViewDock.sigMapsPerMapViewChanged.connect(self.mMapWidget.setMapsPerMapView)
        self.mMapViewDock.sigCrsChanged.connect(self.mMapWidget.setCrs)

        self.vectorOverlay = None

        if len(self.TS) > 0:
            self.setSpatialExtent(self.TS.maxSpatialExtent())


        self.mNumberOfHiddenMapsToRefresh = 2
        self.mCurrentLayer = None

        self.mSyncLock = False

    def setMapTool(self, mapToolKey, mode):
        self.mMapWidget.setMapTool(mapToolKey, mode)



    def setCurrentLayer(self, layer:QgsMapLayer):
        """
        Sets the current map layer some map tools can operate on
        :param layer: QgsMapLayer
        """
        assert layer is None or isinstance(layer, QgsMapLayer)
        self.mCurrentLayer = layer
        for mapView in self.mapViews():
            mapView.setCurrentLayer(self.mCurrentLayer)

    def syncQGISCanvasCenter(self, qgisChanged:bool):

        if self.mSyncLock:
            return

        iface = qgis.utils.iface
        assert isinstance(iface, QgisInterface)

        c = iface.mapCanvas()
        if not isinstance(c, QgsMapCanvas):
            return

        tsvCenter = self.spatialExtent().spatialCenter()
        qgsCenter = SpatialExtent.fromMapCanvas(c).spatialCenter()

        if qgisChanged:
            # change EOTSV
            if tsvCenter.crs().isValid():
                self.mSyncLock = True
                qgsCenter = qgsCenter.toCrs(tsvCenter.crs())
                if isinstance(qgsCenter, SpatialPoint):
                    self.setSpatialCenter(qgsCenter)
        else:
            # change QGIS
            if qgsCenter.crs().isValid():
                self.mSyncLock = True
                tsvCenter = tsvCenter.toCrs(qgsCenter.crs())
                if isinstance(tsvCenter, SpatialPoint):
                    c.setCenter(tsvCenter)
            else:
                pass

    def visibleMaps(self)->list:
        """
        Returns a list of mapcanvas visible to the user
        :return: [list-of-MapCanvases
        """
        return [m for m in self.mapCanvases() if m.isVisibleToViewport()]

    def visibleTSDs(self):
        """
        Returns an ordered list of visible time series dates.
        :return: [list-of-TimeSeriesDates]
        """

        return self.mMapWidget.visibleTSDs()

    def timedCanvasRefresh(self, *args, force:bool=False):
        self.mMapWidget.timedRefresh()


    def createMapView(self, name:str=None)->MapView:
        """
        Create a new MapWiew
        :return: MapView
        """
        return self.mMapViewDock.createMapView(name=name)


    def onCrosshairChanged(self, spatialPoint:SpatialPoint):
        """
        Synchronizes all crosshair positions. Takes care of CRS differences.
        :param spatialPoint: SpatialPoint of new Crosshair position
        """
        from eotimeseriesviewer import CrosshairStyle

        srcCanvas = self.sender()
        if isinstance(srcCanvas, MapCanvas):
            dstCanvases = [c for c in self.mapCanvases() if c != srcCanvas]
        else:
            dstCanvases = [c for c in self.mapCanvases()]

        if isinstance(spatialPoint, SpatialPoint):
            for mapCanvas in dstCanvases:
                mapCanvas.setCrosshairPosition(spatialPoint, emitSignal=False)


    def setCrosshairStyle(self, crosshairStyle:CrosshairStyle):
        """
        Sets a crosshair style to all map canvas
        :param crosshairStyle: CrosshairStyle

        """
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            mapView.setCrosshairStyle(crosshairStyle)


    def setCrosshairVisibility(self, b:bool):
        """
        Sets the Crosshair visiblity
        :param b: bool
        """
        assert isinstance(b, bool)
        self.onCrosshairChanged(b)


    def setVectorLayer(self, lyr:QgsVectorLayer):
        """
        Sets a QgsVectorLaye to be shown on top of raster images
        :param lyr: QgsVectorLayer
        """
        self.mMapViewDock.setVectorLayer(lyr)


    def setMapSize(self, size:QSize):
        """
        Sets the MapCanvas size.
        :param size: QSize
        """
        self.mMapWidget.setMapSize(size)


    def mapSize(self)->QSize:
        """
        Returns the MapCanvas size
        :return: QSize
        """
        return self.mMapViewDock.mapSize()


    def refresh(self):
        """
        Refreshes all visible MapCanvases
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            c.refresh()

        #self.mMapRefreshTimer.stop()

    def doAdjustScrollArea(self):
        m = self.targetLayout.contentsMargins()
        nX = len(self.DVC)
        w = h = 0

        s = QSize()
        r = None
        tsdViews = [v for v in self.DVC if v.ui.isVisible()]
        mapViews = [v for v in self.mMapViewDock if v.isVisible()]
        nX = len(tsdViews)
        nY = len(mapViews)
        spacing = self.targetLayout.spacing()
        margins = self.targetLayout.contentsMargins()

        sizeX = 1
        sizeY = 50
        if nX > 0:
            s = tsdViews[0].ui.sizeHint().width()
            s = nX * (s + spacing) + margins.left() + margins.right()
            sizeX = s
        if nY > 0 and nX > 0:
                s = tsdViews[0].ui.sizeHint().height()
                s = s + margins.top() + margins.bottom()
                sizeY = s

            #s = tsdViews[0].ui.sizeHint()
            #s = QSize(nX * (s.width() + spacing) + margins.left() + margins.right(),
            #          s.height() + margins.top() + margins.bottom())

        #print(sizeX, sizeY)
        self.targetLayout.parentWidget().resize(QSize(sizeX, sizeY))

    def onLocationRequest(self, pt:SpatialPoint, canvas:QgsMapCanvas):

        self.sigShowProfiles.emit(pt, canvas, "")

    def setSpatialCenter(self, center:SpatialPoint, mapCanvas0=None):
        """
        Sets the spatial center of all MapCanvases
        :param center: SpatialPoint
        :param mapCanvas0:
        """
        assert isinstance(center, SpatialPoint)

        extent = self.spatialExtent()

        if isinstance(extent, SpatialExtent):
            centerOld = extent.center()
            center = center.toCrs(extent.crs())
            if center != centerOld and isinstance(center, SpatialPoint):
                extent = extent.__copy__()
                extent.setCenter(center)
                self.setSpatialExtent(extent)


    def spatialCenter(self)->SpatialPoint:
        return self.spatialExtent().spatialCenter()


    def setSpatialExtent(self, extent, mapCanvas0=None):
        """
        Sets the spatial extent of all MapCanvases
        :param extent: SpatialExtent
        :param mapCanvas0:
        :return:
        """
        lastExtent = self.spatialExtent()

        assert isinstance(extent, SpatialExtent)
        extent = extent.toCrs(self.crs())
        if not isinstance(extent, SpatialExtent) \
            or extent.isEmpty() or not extent.isFinite() \
            or extent.width() <= 0 \
            or extent.height() <= 0 \
            or extent == self.mSpatialExtent:
            return

        if self.mSpatialExtent == extent:
            return

        self.mSpatialExtent = extent
        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.addToRefreshPipeLine(extent)

        if lastExtent != extent:
            self.sigSpatialExtentChanged.emit(extent)


    def mapViewDock(self)->MapViewDock:
        """
        Returns the MapViewDock that controls all MapViews
        :return: MapViewDock
        """
        return self.mMapViewDock

    def setMapBackgroundColor(self, color:QColor):
        """
        Sets the MapCanvas background color
        :param color: QColor
        """
        assert isinstance(self.mMapViewDock, MapViewDock)
        self.mMapViewDock.setMapBackgroundColor(color)

    def mapCanvases(self, mapView=None)->list:
        """
        Returns MapCanvases
        :param mapView: a MapView to return MapCanvases from only, defaults to None
        :return: [list-of-MapCanvas]
        """
        return self.mMapWidget.mapCanvases()

    def mapViews(self)->list:
        """
        Returns a list of all mapviews
        :return [list-of-MapViews]:
        """
        return self.mMapViewDock[:]

    def setCrs(self, crs):
        self.mMapWidget.setCrs(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if self.mMapWidget.crs() != crs:
            self.mMapWidget.setCrs(crs)
            self.sigCRSChanged.emit(self.crs())


    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Returns the QgsCoordinateReferenceSystem
        :return: QgsCoordinateReferenceSystem
        """
        return self.mMapWidget.crs()

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the SpatialExtent
        :return: SpatialExtent
        """
        return self.mMapWidget.spatialExtent()



    def navigateToTSD(self, tsd:TimeSeriesDate):
        """
        Changes the viewport of the scroll window to show the requested TimeSeriesDate
        :param TSD: TimeSeriesDate
        """
        self.mMapWidget.setCurrentDate(tsd)

