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
from .timeseries import SensorInstrument, TimeSeriesDatum, TimeSeries, SensorProxyLayer
from .utils import loadUI
from .mapviewscrollarea import MapViewScrollArea
from .mapcanvas import MapCanvas, MapTools
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
        a.triggered.connect(lambda *args, canvas=centerCanvas, lyr=l:
                            showLayerPropertiesDialog(lyr, canvas))
        a.setEnabled(isinstance(centerCanvas, QgsMapCanvas))



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
    sigMapViewVisibility = pyqtSignal(bool)

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

        self.actionAddOgrLayer.triggered.connect(self.onAddOgrLayer)
        self.btnAddOgrLayer.setDefaultAction(self.actionAddOgrLayer)

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

    def visibleMapCanvases(self)->list:
        """
        Returns the currently visible mapcanvases
        :return: [list-of-MapCanvases]
        """
        return [m for m in self.mapCanvases() if m.isVisibleToViewport()]

    def onAddOgrLayer(self):

        from .externals.qps.utils import SelectMapLayersDialog

        d = SelectMapLayersDialog()
        d.setWindowTitle('Select Vector Layer')
        d.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)

        if d.exec() == QDialog.Accepted:
            for l in d.mapLayers():
                self.addLayer(l)
        else:
            s = ""
    def setCurrentLayer(self, layer):
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
            self.sigMapViewVisibility.emit(b)

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


    def registerMapCanvas(self, mapCanvas:MapCanvas):
        """
        Registers a new MapCanvas to this MapView
        :param sensor:
        :param mapCanvas:
        :return:
        """
        from eotimeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)

        mapCanvas.setMapView(self)
        mapCanvas.sigCrosshairVisibilityChanged.connect(self.setCrosshairVisibility)
        mapCanvas.sigCrosshairStyleChanged.connect(self.setCrosshairStyle)
        self.mMapCanvases.append(mapCanvas)
        self.sigMapViewVisibility.connect(mapCanvas.setEnabled)


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
            srcCanvas = self.sender()
            if isinstance(srcCanvas, MapCanvas):
                dstCanvases = [c for c in self.mapCanvases() if c != srcCanvas]
            else:
                dstCanvases = [c for c in self.mapCanvases()]

            for mapCanvas in dstCanvases:
                mapCanvas.setCrosshairVisibility(b, emitSignal=False)


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

class DatumViewUI(QFrame, loadUI('timeseriesdatumview.ui')):
    """
    Widget to host the MapCanvases of all map views that relate to a single Datum-Sensor combinbation.
    """
    def __init__(self, title='<#>', parent=None):
        super(DatumViewUI, self).__init__(parent)
        self.setupUi(self)

    def sizeHint(self):
        m = self.layout().contentsMargins()

        s = QSize(0, 0)

        map = None
        widgets = [self.layout().itemAt(i).widget() for i in range(self.layout().count())]
        widgets = [w for w in widgets if isinstance(w, QWidget)]

        maps = [w for w in widgets if isinstance(w, MapCanvas)]
        others = [w for w in widgets if not isinstance(w, MapCanvas)]

        s = self.layout().spacing()
        m = self.layout().contentsMargins()

        def totalHeight(widgetList):
            total = QSize(0,0)
            for w in widgetList:
                ws = w.size()
                if ws.width() == 0:
                    ws = w.sizeHint()
                if w.isVisible():
                    total.setWidth(max([total.width(), ws.width()]))
                    total.setHeight(total.height() +  ws.height())
            return total

        baseSize = totalHeight(widgets)
        if baseSize.width() == 0:
            for o in others:
                baseSize.setWidth(9999)
        s = QSize(baseSize.width() + m.left() + m.right(),
                  baseSize.height() + m.top() + m.bottom())
        #print(s)
        return s

"""
    def sizeHint(self):

        if not self.ui.isVisible():
            return QSize(0,0)
        else:
            #return self.ui.sizeHint()

            size = self.ui.sizeHint()
            s = self.ui.layout().spacing()
            m = self.ui.layout().contentsMargins()
            dx = m.left() + m.right() + s
            dy = self.ui.layout().spacing()

            n = len([m for m in self.mapCanvases.keys() if m.isVisible()])
            if n > 0:
                baseSize = self.mapCanvases.values()[0].size()
                size = QSize(baseSize.width()+ dx, \
                             size.height()+ (n+1)*(dy+2*s))
            else:
                s = ""
            return size


"""



class DatumView(QObject):

    sigRenderProgress = pyqtSignal(int,int)
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigVisibilityChanged = pyqtSignal(bool)

    def __init__(self, timeSeriesDatum:TimeSeriesDatum, stv, parent=None):
        assert isinstance(timeSeriesDatum, TimeSeriesDatum)
        assert isinstance(stv, SpatialTemporalVisualization)


        super(DatumView, self).__init__()
        self.ui = DatumViewUI(parent=parent)
        self.ui.create()
        self.showLoading(False)
        self.wOffset = self.ui.layout().count()-1
        self.minHeight = self.ui.height()
        #self.minWidth = 50
        self.renderProgress = dict()

        assert isinstance(stv, SpatialTemporalVisualization)
        self.STV = stv

        self.TSD = timeSeriesDatum
        self.scrollArea = stv.scrollArea
        self.mSensor = self.TSD.mSensor
        self.mSensor.sigNameChanged.connect(lambda :self.setColumnInfo())
        self.TSD.sigVisibilityChanged.connect(self.setVisibility)
        self.setColumnInfo()
        self.MVC = stv.MVC
        self.DVC = stv.DVC
        self.mMapCanvases = dict()
        self.mRenderState = dict()

    def setColumnInfo(self):

        labelTxt = '{}\n{}'.format(str(self.TSD.mDate), self.TSD.mSensor.name())
        tooltip = '\n'.join([tss.uri()for tss in self.TSD.sources()])

        self.ui.labelTitle.setText(labelTxt)
        self.ui.labelTitle.setToolTip(tooltip)

    def setVisibility(self, b):
        self.ui.setVisible(b)
        self.sigVisibilityChanged.emit(b)

    def setHighlighted(self, b=True, timeout=1000):
        styleOn = """.QFrame {
                    border: 4px solid red;
                    border-radius: 4px;
                }"""
        styleOff = """"""
        if b is True:
            self.ui.setStyleSheet(styleOn)
            if timeout > 0:
                QTimer.singleShot(timeout, lambda : self.setHighlighted(b=False))
        else:
            self.ui.setStyleSheet(styleOff)

    def removeMapView(self, mapView):
        canvas = self.mMapCanvases.pop(mapView)
        self.ui.layout().removeWidget(canvas)
        canvas.close()

    def mapCanvases(self)->list:
        """
        Retuns the MapCanvases of this DataView
        :return: [list-of-MapCanvases]
        """
        return self.mMapCanvases.values()

    def refresh(self):
        """
        Refreshes the MapCanvases in this DatumView, if they are not hidden behind a scroll area.
        """
        if self.ui.isVisible():
            for c in self.mapCanvases():
                if c.isVisible():
                    c.refresh()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)
        from eotimeseriesviewer.mapcanvas import MapCanvas

        mapCanvas = MapCanvas(self.ui)
        mapCanvas.setObjectName('MapCanvas {} {}'.format(mapView.title(), self.TSD.mDate))

        self.registerMapCanvas(mapView, mapCanvas)
        mapCanvas.setMapView(mapView)
        mapCanvas.setTSD(self.TSD)
        mapView.registerMapCanvas(mapCanvas)
        self.STV.registerMapCanvas(mapCanvas)
        mapCanvas.renderComplete.connect(lambda : self.onRenderingChange(False))
        mapCanvas.renderStarting.connect(lambda : self.onRenderingChange(True))

        #mapCanvas.sigMapRefreshed[float, float].connect(
        #    lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('Map {}'.format(self.mSensor.name()), dt))
        #mapCanvas.sigMapRefreshed.connect(
        #    lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('All Sensors', dt))

    def showLoading(self, b):
        if b:
            self.ui.progressBar.setRange(0, 0)
            self.ui.progressBar.setValue(-1)
        else:
            self.ui.progressBar.setRange(0,1)
            self.ui.progressBar.setValue(0)

    def onRenderingChange(self, b):
        mc = self.sender()
        #assert isinstance(mc, QgsMapCanvas)
        self.mRenderState[mc] = b
        self.showLoading(any(self.mRenderState.values()))

    def onRendering(self, *args):
        renderFlags = [m.renderFlag() for m in self.mMapCanvases.values()]
        drawFlags = [m.isDrawing() for m in self.mMapCanvases.values()]
#        print((renderFlags, drawFlags))
        isLoading = any(renderFlags)

        self.showLoading(isLoading)

        s = ""

    def registerMapCanvas(self, mapView, mapCanvas):

        from eotimeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        assert isinstance(mapView, MapView)
        self.mMapCanvases[mapView] = mapCanvas
        mapCanvas.setVisible(mapView.isVisible())


        #mapView.sigTitleChanged.connect(lambda title : mapCanvas.setSaveFileName('{}_{}'.format(self.TSD.date, title)))
        #mapCanvas.mapLayerModel().addMapLayerSources(self.TSD.qgsMimeDataUtilsUris())

        #self.ui.layout().insertWidget(self.wOffset + len(self.mapCanvases), mapCanvas)
        self.ui.layout().insertWidget(self.ui.layout().count() - 1, mapCanvas)
        self.ui.update()

        #register signals handled on (this) DV level
        mapCanvas.renderStarting.connect(lambda: self.sigLoadingStarted.emit(mapView, self.TSD))
        mapCanvas.mapCanvasRefreshed.connect(lambda: self.sigLoadingFinished.emit(mapView, self.TSD))
        #mapCanvas.sigShowProfiles.connect(lambda c, t : mapView.sigShowProfiles.emit(c,mapCanvas, t))
        #mapCanvas.sigChangeDVRequest.connect(self.onMapCanvasRequest)


    def __lt__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD < other.TSD

    def __eq__(self, other):
        """
        :param other:
        :return:
        """
        assert isinstance(other, DatumView)
        return self.TSD == other.TSD


class DateViewCollection(QObject):

    sigResizeRequired = pyqtSignal()
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigShowProfiles = pyqtSignal(SpatialPoint)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def __init__(self, STViz):
        assert isinstance(STViz, SpatialTemporalVisualization)
        super(DateViewCollection, self).__init__()
        #self.tsv = tsv
        #self.timeSeries = tsv.TS

        self.mViews = list()
        self.STV = STViz
        self.ui = self.STV.targetLayout.parentWidget()
        self.scrollArea = self.ui.parentWidget().parentWidget()
        #potentially there are many more dates than views.
        #therefore we implement the addinng/removing of mapviews here
        #we reduce the number of layout refresh calls by
        #suspending signals, adding the new map view canvases, and sending sigResizeRequired

        self.STV.MVC.sigMapViewAdded.connect(self.addMapView)
        self.STV.MVC.sigMapViewRemoved.connect(self.removeMapView)

        self.setFocusView(None)


    def tsdFromMapCanvas(self, mapCanvas):
        assert isinstance(mapCanvas, MapCanvas)
        for view in self.mViews:
            assert isinstance(view, DatumView)
            if mapCanvas in view.mMapCanvases.values():
                return view.TSD
        return None

    def tsdView(self, tsd):
        r = [v for v in self.mViews if v.TSD == tsd]
        if len(r) == 1:
            return r[0]
        else:
            raise Exception('TSD not in list')

    def addMapView(self, mapView):
        assert isinstance(mapView, MapView)
        w = self.ui
        #w.setUpdatesEnabled(False)
        #for tsdv in self.mViews:
        #    tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.mViews:
            tsdv.insertMapView(mapView)

        #for tsdv in self.mViews:
        #    tsdv.ui.setUpdatesEnabled(True)

        #mapView.sigSensorRendererChanged.connect(lambda *args : self.setRasterRenderer(mapView, *args))
        mapView.sigMapViewVisibility.connect(lambda: self.sigResizeRequired.emit())
        mapView.sigShowProfiles.connect(self.sigShowProfiles.emit)
        #w.setUpdatesEnabled(True)

        self.sigResizeRequired.emit()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        for tsdv in self.mViews:
            tsdv.removeMapView(mapView)
        self.sigResizeRequired.emit()


    def highlightDate(self, tsd):
        """
        Highlights a time series data for a specific time our
        :param tsd:
        :return:
        """
        tsdView = self.tsdView(tsd)
        if isinstance(tsdView, DatumView):
            tsdView.setHighlight(True)

    def setFocusView(self, tsd):
        self.focusView = tsd

    def orderedViews(self):
        #returns the
        if self.focusView is not None:
            assert isinstance(self.focusView, DatumView)
            return sorted(self.mViews, key=lambda v: np.abs(v.TSD.date - self.focusView.TSD.date))
        else:
            return self.mViews

    """
    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size

        for tsdView in self.orderedViews():
            tsdView.blockSignals(True)

        for tsdView in self.orderedViews():
            tsdView.setSubsetSize(size)

        for tsdView in self.orderedViews():
            tsdView.blockSignals(False)
    """


    def addDates(self, tsdList):
        """
        Create a new TSDView
        :param tsdList:
        :return:
        """
        for tsd in tsdList:
            assert isinstance(tsd, TimeSeriesDatum)
            DV = DatumView(tsd, self.STV, parent=self.ui)

            DV.sigLoadingStarted.connect(self.sigLoadingStarted.emit)
            DV.sigLoadingFinished.connect(self.sigLoadingFinished.emit)
            DV.sigVisibilityChanged.connect(lambda: self.STV.adjustScrollArea())

            for i, mapView in enumerate(self.STV.MVC):
                DV.insertMapView(mapView)

            bisect.insort(self.mViews, DV)
            i = self.mViews.index(DV)

            DV.ui.setParent(self.STV.targetLayout.parentWidget())
            self.STV.targetLayout.insertWidget(i, DV.ui)
            DV.ui.show()

        if len(tsdList) > 0:
            self.sigResizeRequired.emit()

    def removeDates(self, tsdList):
        toRemove = [v for v in self.mViews if v.TSD in tsdList]
        removedDates = []
        for DV in toRemove:
            self.mViews.remove(DV)

            for mapCanvas in DV.mMapCanvases.values():
                toRemove = mapCanvas.layers()
                mapCanvas.setLayers([])
                toRemove = [l for l in toRemove if isinstance(l, QgsRasterLayer)]
                if len(toRemove) > 0:
                    QgsProject.instance().removeMapLayers([l.id() for l in toRemove])

            DV.ui.parent().layout().removeWidget(DV.ui)
            DV.ui.hide()
            DV.ui.close()
            removedDates.append(DV.TSD)
            del DV

        if len(removedDates) > 0:
            self.sigResizeRequired.emit()

    def __len__(self):
        return len(self.mViews)

    def __iter__(self):
        return iter(self.mViews)

    def __getitem__(self, slice):
        return self.mViews[slice]

    def __delitem__(self, slice):
        self.removeDates(self.mViews[slice])


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

    def mapSize(self):
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


    def createMapView(self)->MapView:
        """
        Create a new MapView
        :return: MapView
        """

        mapView = MapView()

        n = len(self.mapViews()) + 1
        title = 'Map View {}'.format(n)
        while title in [m.title() for m in self.mapViews()]:
            n += 1
            title = 'Map View {}'.format(n)
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
        mapView.sigMapViewVisibility.connect(lambda *args, mv=mapView : self.onMapViewUpdated(mv))

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



class SpatialTemporalVisualization(QObject):
    """

    """
    sigLoadingStarted = pyqtSignal(DatumView, MapView)
    sigLoadingFinished = pyqtSignal(DatumView, MapView)
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
        self.mCRS = self.mSpatialExtent.crs()
        self.mSize = QSize(200, 200)
        self.mColor = Qt.black
        self.mMapCanvases = []
        self.ui = timeSeriesViewer.ui

        self.mVisibleDates = set()

        # map-tool handling
        self.mMapToolKey = MapTools.Pan
        self.mMapToolMode = None

        self.scrollArea = self.ui.scrollAreaSubsets
        assert isinstance(self.scrollArea, MapViewScrollArea)
        self.scrollArea.horizontalScrollBar().valueChanged.connect(self.onVisibleMapsChanged)
        self.scrollArea.horizontalScrollBar().rangeChanged.connect(self.onVisibleMapsChanged)
        # self.scrollArea.sigResized.connect(self.onVisibleMapsChanged)
        # self.scrollArea.sigResized.connect(self.refresh())
        # self.scrollArea.horizontalScrollBar().valueChanged.connect(self.mRefreshTimer.start)

        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.timeSeries()
        self.ui.dockMapViews.setTimeSeries(self.TS)
        self.targetLayout = self.ui.scrollAreaSubsetContent.layout()

        self.MVC = self.ui.dockMapViews
        assert isinstance(self.MVC, MapViewDock)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)
        self.MVC.sigMapViewAdded.connect(self.onMapViewAdded)
        self.MVC.sigMapViewAdded.connect(self.sigMapViewAdded.emit)
        self.MVC.sigMapViewRemoved.connect(self.sigMapViewRemoved.emit)
        self.vectorOverlay = None

        self.DVC = DateViewCollection(self)
        self.DVC.sigResizeRequired.connect(self.adjustScrollArea)

        self.TS.sigTimeSeriesDatesAdded.connect(self.DVC.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.DVC.removeDates)

        self.DVC.addDates(self.TS[:])
        if len(self.TS) > 0:
            self.setSpatialExtent(self.TS.maxSpatialExtent())
        #self.setSubsetSize(QSize(100,50))

        self.mMapRefreshTimer = QTimer(self)
        self.mMapRefreshTimer.timeout.connect(self.timedCanvasRefresh)
        self.mMapRefreshTimer.setInterval(500)
        self.mMapRefreshTimer.start()
        self.mNumberOfHiddenMapsToRefresh = 2
        self.mCurrentLayer = None

        self.mSyncLock = False

    def setMapTool(self, mapToolKey):


        mode = None

        if mapToolKey == MapTools.SelectFeature:
            if self.ui.optionSelectFeaturesRectangle.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectSimple
            elif self.ui.optionSelectFeaturesPolygon.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectPolygon
            elif self.ui.optionSelectFeaturesFreehand.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectFreehand
            elif self.ui.optionSelectFeaturesRadius.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectRadius
            else:
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectSimple

        self.mMapToolKey = mapToolKey
        self.mMapToolMode = mode


        from .mapcanvas import MapCanvas, MapCanvasMapTools

        for canvas in self.mapCanvases():

            if isinstance(canvas, MapCanvas):

                mapTools = canvas.mapTools()
                mapTools.activate(mapToolKey)

                mt = canvas.mapTool()
                if isinstance(mt, QgsMapToolSelect):
                    mt.setSelectionMode(mode)


    def setCurrentLayer(self, layer):

        assert layer is None or isinstance(layer, QgsMapLayer)
        self.mCurrentLayer = layer
        for canvas in self.mapCanvases():
            assert isinstance(canvas, QgsMapCanvas)
            canvas.setCurrentLayer(layer)

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

    def onVisibleMapsChanged(self, *args):

        visibleDates = set([m.tsd() for m in self.visibleMaps()])
        if visibleDates != self.mVisibleDates:
            self.mVisibleDates.clear()
            self.mVisibleDates.update(visibleDates)
            self.sigVisibleDatesChanged.emit(list(self.mVisibleDates))

    def timedCanvasRefresh(self, *args, force:bool=False):

        self.mSyncLock = False

        # do refresh maps
        assert isinstance(self.scrollArea, MapViewScrollArea)

        visibleMaps = self.visibleMaps()

        hiddenMaps = sorted([m for m in self.mapCanvases() if not m.isVisibleToViewport()],
                            key = lambda c : self.scrollArea.distanceToCenter(c) )

        n = 0
        # redraw all visible maps
        for c in visibleMaps:
            assert isinstance(c, MapCanvas)
            c.timedRefresh()
            n += 1

        if n < 10:
            # refresh up to mNumberOfHiddenMapsToRefresh maps which are not visible to the user
            i = 0
            for c in hiddenMaps:
                assert isinstance(c, MapCanvas)
                c.timedRefresh()
                i += 1
                if i >= self.mNumberOfHiddenMapsToRefresh and not force:
                    break

    def mapViewFromCanvas(self, mapCanvas:MapCanvas)->MapView:
        """
        Returns the MapView a mapCanvas belongs to
        :param mapCanvas: MapCanvas
        :return: MapView
        """
        for mapView in self.MVC:
            assert isinstance(mapView, MapView)
            if mapCanvas in mapView.mapCanvases():
                return mapView
        return None

    def onMapViewAdded(self, *args):
        self.adjustScrollArea()
        s = ""
    def createMapView(self)->MapView:
        """
        Create a new MapWiew
        :return: MapView
        """
        return self.MVC.createMapView()


    def registerMapCanvas(self, mapCanvas:MapCanvas):
        """
        Connects a MapCanvas and its signals
        :param mapCanvas: MapCanvas
        """
        from eotimeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)

        mapCanvas.setMapLayerStore(self.TSV.mMapLayerStore)
        mapCanvas.sigCrosshairPositionChanged.connect(lambda point, canvas=mapCanvas: self.TSV.setCurrentLocation(point, canvas))
        self.mMapCanvases.append(mapCanvas)


        # set general canvas properties
        mapCanvas.setFixedSize(self.mSize)
        mapCanvas.setDestinationCrs(self.mCRS)
        mapCanvas.setSpatialExtent(self.mSpatialExtent)

        mapCanvas.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        mapCanvas.sigCrosshairPositionChanged.connect(self.onCrosshairChanged)

        # activate the current map tool
        mapTools = mapCanvas.mapTools()
        mapTools.activate(self.mMapToolKey)

        mt = mapCanvas.mapTool()
        if isinstance(mt, QgsMapToolSelect):
            mt.setSelectionMode(self.mMapToolMode)

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
        self.MVC.setVectorLayer(lyr)



    def setMapSize(self, size):
        assert isinstance(size, QSize)
        self.mSize = size
        from eotimeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setFixedSize(size)
        self.sigMapSizeChanged.emit(self.mSize)
        self.adjustScrollArea()

    def mapSize(self)->QSize:
        """
        Returns the MapCanvas size
        :return: QSize
        """
        return QSize(self.mSize)


    def refresh(self):
        """
        Refreshes all visible MapCanvases
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            c.refresh()

        #self.mMapRefreshTimer.stop()

    def adjustScrollArea(self):
        """
        Adjusts the scroll area widget to fit all visible widgets
        """

        m = self.targetLayout.contentsMargins()
        nX = len(self.DVC)
        w = h = 0

        s = QSize()
        r = None
        tsdViews = [v for v in self.DVC if v.ui.isVisible()]
        mapViews = [v for v in self.MVC if v.isVisible()]
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
            if center != centerOld:
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
        return self.MVC

    def setMapBackgroundColor(self, color:QColor):
        """
        Sets the MapCanvas background color
        :param color: QColor
        """
        assert isinstance(self.MVC, MapViewDock)
        self.MVC.setMapBackgroundColor(color)



    def mapCanvases(self, mapView=None)->list:
        """
        Returns MapCanvases
        :param mapView: a MapView to return MapCanvases from only, defaults to None
        :return: [list-of-MapCanvas]
        """
        if isinstance(mapView, MapView):
            s = ""
        return self.mMapCanvases[:]

    def mapViews(self)->list:
        """
        Returns a list of all mapviews
        :return [list-of-MapViews]:
        """
        return self.MVC[:]

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if self.mCRS != crs:
            transform = QgsCoordinateTransform()
            transform.setSourceCrs(self.mCRS)
            transform.setDestinationCrs(crs)
            if transform.isValid() and not transform.isShortCircuited():
                self.mCRS = crs
                for mapCanvas in self.mapCanvases():
                    # print(('STV set CRS {} {}', str(mapCanvas), self.mCRS.description()))
                    mapCanvas.setDestinationCrs(QgsCoordinateReferenceSystem(crs))
                """
                from timeseriesviewer.utils import saveTransform
                if saveTransform(self.mSpatialExtent, self.mCRS, crs):
                    self.mCRS = crs
                    
                else:
                    pass
                """
                self.sigCRSChanged.emit(self.crs())


    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Returns the QgsCoordinateReferenceSystem
        :return: QgsCoordinateReferenceSystem
        """
        return self.mCRS

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the SpatialExtent
        :return: SpatialExtent
        """
        return self.mSpatialExtent



    def navigateToTSD(self, TSD:TimeSeriesDatum):
        """
        Changes the viewport of the scroll window to show the requested TimeSeriesDatum
        :param TSD: TimeSeriesDatum
        """
        assert isinstance(TSD, TimeSeriesDatum)
        #get widget related to TSD
        tsdv = self.DVC.tsdView(TSD)
        assert isinstance(self.scrollArea, QScrollArea)
        self.scrollArea.ensureWidgetVisible(tsdv.ui)

