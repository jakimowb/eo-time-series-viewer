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
# noinspection PyPep8Naming


import os, time, types, enum
from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtXml import QDomDocument


from .utils import *
from .timeseries import TimeSeriesDatum
from .crosshair import CrosshairDialog, CrosshairStyle
from .maptools import *
from .labeling import LabelAttributeTableModel

class MapCanvasLayerModel(QAbstractTableModel):

    class LayerItem(object):

        def __init__(self, src):

            self.mLyr = None
            self.mUri = None
            self.mIsVisible = True
            self.mExternalControl = False

            if isinstance(src, QgsMimeDataUtils.Uri):
                self.mUri = src
                self.mExternalControl = False
            else:
                assert isinstance(src, QgsMapLayer)
                self.mLyr = src
                self.mUri = toQgsMimeDataUtilsUri(src)
                self.mExternalControl = True
                s  = ""
            assert isinstance(self.mUri, QgsMimeDataUtils.Uri)

        def name(self)->str:
            return self.mUri.name

        def source(self)->str:
            return self.mUri.uri

        def layerType(self)->str:
            return self.mUri.layerType

        def isVisible(self)->bool:
            return self.mIsVisible


        def hasMapLayerInstance(self)->bool:
            return isinstance(self.mLyr, QgsMapLayer)



    """
    A model to create QgsMapLayer instances and control its visibility.
    """
    def __init__(self, parent=None):

        super(MapCanvasLayerModel, self).__init__()
        self.cnName = 'Name'
        self.cnUri = 'Uri'
        self.cnLayerType = 'Type'

        self.mColumnNames = [self.cnName, self.cnLayerType, self.cnUri]

        self.mVectorsVisible = True
        self.mRastersVisible = True

        self.mDefaultRasterRenderer = None
        self.mDefaultVectorRenderer = None

        self.mItems = []

    def __iter__(self):
        return iter(self.mItems)

    def __len__(self)->int:
        return len(self.mItems)

    def setDefaultRasterRenderer(self, renderer:QgsRasterRenderer):
        if isinstance(renderer, QgsRasterRenderer):
            self.mDefaultRasterRenderer = renderer

            for item in self.mItems:
                assert isinstance(item, MapCanvasLayerModel.LayerItem)
                if not item.mExternalControl and isinstance(item.mLyr, QgsRasterLayer):
                    item.mLyr.setRenderer(renderer.clone())

    def setDefaultVectorRenderer(self, renderer:QgsFeatureRenderer):
        assert isinstance(renderer, QgsFeatureRenderer)
        self.mDefaultVectorRenderer = renderer

        for item in self.mItems:
            assert isinstance(item, MapCanvasLayerModel.LayerItem)
            if not item.mExternalControl and isinstance(item.mLyr, QgsVectorLayer):
                item.mLyr.setRenderer(renderer.clone())

    def setLayerVisibility(self, cls, b:bool):

        assert isinstance(b, bool)
        if isinstance(cls, int):
            item = self.mItems[cls]
            assert isinstance(item, MapCanvasLayerModel.LayerItem)
            item.mIsVisible = b

        elif cls == QgsRasterLayer:
            self.mRastersVisible = b
            for item in [i for i in self if i.layerType() == 'raster']:
                assert isinstance(item, MapCanvasLayerModel.LayerItem)
                item.mIsVisible = b

        elif cls == QgsVectorLayer:
            self.mVectorsVisible = b
            for item in [i for i in self if i.layerType() == 'vector']:
                assert isinstance(item, MapCanvasLayerModel.LayerItem)
                item.mIsVisible = b
        else:
            raise NotImplementedError()

    def clear(self):
        """
        Removes all layers
        """
        self.beginRemoveRows(QModelIndex(), 0, len(self)-1)
        self.mItems.clear()
        self.endRemoveRows()


    def addMapLayerSources(self, src):

        i = len(self.mItems)

        self.insertMapLayerSources(i, src)

    def insertMapLayerSources(self, index:int, mapLayerSources):
        assert isinstance(mapLayerSources, (list, types.GeneratorType))
        items = [MapCanvasLayerModel.LayerItem(src) for src in mapLayerSources]

        self.beginInsertRows(QModelIndex(), index, index + len(items) - 1)
        i = index
        for item in items:
            self.mItems.insert(i, item)
            i += 1
        self.endInsertRows()

    def visibleLayers(self, sorted=True)->list:
        """
        Returns the visible QgsMapLayer instances. Will create QgsMapLayer instances if necessary from uri's
        :return: [list-of-QgsMapLayers]
        """
        layers = []

        for item in self.mItems:
            assert isinstance(item, MapCanvasLayerModel.LayerItem)
            if not item.isVisible():
                continue

            if not item.hasMapLayerInstance():
                item.mLyr = toMapLayer(item.mUri)
                assert isinstance(item.mLyr, QgsMapLayer)

                if isinstance(self.mDefaultRasterRenderer, QgsRasterRenderer) and isinstance(item.mLyr, QgsRasterLayer):
                    item.mLyr.setRenderer(self.mDefaultRasterRenderer.clone())

                if isinstance(self.mDefaultVectorRenderer, QgsFeatureRenderer) and isinstance(item.mLyr, QgsVectorLayer):
                    item.mLyr.setRenderer(self.mDefaultRasterRenderer.clone())

            layers.append(item.mLyr)

        if sorted:
            layers = [l for l in layers if isinstance(l, QgsVectorLayer)] + \
                     [l for l in layers if isinstance(l, QgsRasterLayer)]
        return layers

    def rasterSources(self)->list:
        return [s for s in self if isinstance(s, MapCanvasLayerModel.LayerItem) and s.layerType() == 'raster']

    def vectorSources(self)->list:
        return [s for s in self if isinstance(s, MapCanvasLayerModel.LayerItem) and s.layerType() == 'vector']

    def removeMapLayerSources(self, mapLayerSources):
        assert isinstance(mapLayerSources, (list, types.GeneratorType))
        toRemove = []
        for src in mapLayerSources:
            uri = None
            if isinstance(src, MapCanvasLayerModel.LayerItem):
                uri = src.mUri.uri
            if isinstance(src, QgsRasterLayer):
                uri = src.source()
            elif isinstance(src, QgsMimeDataUtils.Uri):
                uri = src.uri
            elif isinstance(src, str):
                uri = src
            for item, item in enumerate(self.mItems):
                assert isinstance(item, MapCanvasLayerModel.LayerItem)
                if item.mUri.uri == uri:
                    toRemove.append(item)

        for item in toRemove:
            idx = self.item2index(item)
            self.beginRemoveRows(QModelIndex(), idx.row(), idx.row())
            self.mItems.remove(item)
            self.endRemoveRows()

    def item2index(self, item)->QModelIndex:
        assert isinstance(item, MapCanvasLayerModel.LayerItem)
        i = self.mItems.index(item)
        return self.createIndex(i,0,object=self.mItems[i])


    def rowCount(self, parent = QModelIndex())->int:

        return len(self.mItems)

    def columnCount(self, parent = QModelIndex())->int:
        return len(self.mColumnNames)

    def flags(self, index:QModelIndex):
        if index.isValid():
            columnName = self.mColumnNames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
            if columnName == self.cnName: #allow check state
                flags = flags | Qt.ItemIsUserCheckable
            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        item = self.mItems[index.row()]
        assert isinstance(item, MapCanvasLayerModel.LayerItem)
        cn = self.mColumnNames[index.column()]
        value = None
        if role == Qt.DisplayRole or role == Qt.ToolTipRole or role == Qt.EditRole:
            if cn == self.cnName:
                value = item.name()
            elif cn == self.cnUri:
                value = item.mUri.uri
            elif cn == self.cnLayerType:
                value = item.mUri.layerType

        elif role == Qt.CheckStateRole:
            if cn == self.cnName:
                value = Qt.Checked if item.isVisible() else Qt.Unchecked
        return value



    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        cn = self.mColumnNames[index.column()]
        item = self.mItems[index.row()]
        assert isinstance(item, MapCanvasLayerModel.LayerItem)
        changed = False

        if role == Qt.CheckStateRole and cn == self.cnName:
            item.mIsVisible = value == Qt.Checked
            changed = True

        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed

        return False



class MapCanvas(QgsMapCanvas):

    class Command(enum.Enum):

        RefreshRenderer = 1
        RefreshVisibility = 2
        Clear = 3
        RemoveRasters = 4
        HideRasters = 5
        ShowRasters = 6
        RemoveVectors = 7
        HideVectors = 8
        ShowVectors = 9



    saveFileDirectories = dict()
    sigShowProfiles = pyqtSignal(SpatialPoint, str)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigChangeDVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeMVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeSVRequest = pyqtSignal(QgsMapCanvas, QgsRasterRenderer)
    sigMapRefreshed = pyqtSignal([float, float], [float])

    sigCrosshairPositionChanged = pyqtSignal(SpatialPoint)
    sigCrosshairVisibilityChanged = pyqtSignal(bool)
    from .crosshair import CrosshairStyle
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)
        self.mMapLayerStore = QgsProject.instance()
        self.mMapLayers = []
        self.mMapLayerModel = MapCanvasLayerModel()
        self.mTimedRefreshPipeLine = dict()


        self.mTSD = self.mMapView = None
        self.mLabelingModel = None
        #the canvas
        self.mIsRefreshing = False
        self.mRenderingFinished = True
        self.mRefreshStartTime = time.time()
        self.mNeedsRefresh = False

        def onMapCanvasRefreshed(*args):
            self.mIsRefreshing = False
            self.mRenderingFinished = True
            self.mIsRefreshing = False
            t2 = time.time()
            dt = t2 - self.mRefreshStartTime

            self.sigMapRefreshed[float].emit(dt)
            self.sigMapRefreshed[float, float].emit(self.mRefreshStartTime, t2)

        self.mapCanvasRefreshed.connect(onMapCanvasRefreshed)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bg = timeseriesviewer.settings.value(timeseriesviewer.settings.Keys.MapBackgroundColor, default=QColor(0, 0, 0))
        self.setCanvasColor(bg)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        #refreshTimer.timeout.connect(self.onTimerRefresh)
        #self.extentsChanged.connect(lambda : self._setDataRefreshed())
        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))



        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.mCrosshairItem = CrosshairMapCanvasItem(self)

    def mapLayerModel(self)->MapCanvasLayerModel:
        """
        Returns the MapCanvasLayerModel which controls the layer visibility
        :return: MapCanvasLayerModel
        """
        return self.mMapLayerModel

    def setMapLayerStore(self, store):
        """
        Sets the QgsMapLayerStore or QgsProject instance that is used to register map layers
        :param store: QgsMapLayerStore | QgsProject
        """
        assert isinstance(store, (QgsMapLayerStore, QgsProject))
        self.mMapLayerStore = store

    def renderingFinished(self)->bool:
        """
        Returns whether the MapCanvas is processing a rendering task
        :return: bool
        """
        return self.mRenderingFinished

    def mousePressEvent(self, event:QMouseEvent):

        b = event.button() == Qt.LeftButton
        if b and isinstance(self.mapTool(), QgsMapTool):
            from timeseriesviewer.maptools import CursorLocationMapTool
            b = isinstance(self.mapTool(), (QgsMapToolIdentify,
                                            CursorLocationMapTool,
                                            SpectralProfileMapTool, TemporalProfileMapTool))

        super(MapCanvas, self).mousePressEvent(event)

        if b:
            ms = self.mapSettings()
            pointXY = ms.mapToPixel().toMapCoordinates(event.x(), event.y())
            spatialPoint = SpatialPoint(ms.destinationCrs(), pointXY)
            self.setCrosshairPosition(spatialPoint)

    def setMapView(self, mapView):
        from timeseriesviewer.mapvisualization import MapView

        assert isinstance(mapView, MapView)
        self.mMapView = mapView

    def setLabelingModel(self, model):
        assert isinstance(model, (LabelAttributeTableModel, None))
        self.mLabelingModel = model


    def setTSD(self, tsd:TimeSeriesDatum):
        """
        Sets the TimeSeriesDatum this map-canvas is linked to
        :param tsd:
        :return:
        """
        assert isinstance(tsd, TimeSeriesDatum)
        self.mTSD = tsd

        scope = self.expressionContextScope()
        scope.setVariable('map_date', str(tsd.date()), isStatic=True)
        scope.setVariable('map_doy', tsd.doy(), isStatic=True)
        scope.setVariable('map_sensor', tsd.sensor().name(), isStatic=False)
        tsd.sensor().sigNameChanged.connect(lambda name : scope.setVariable('map_sensor', name))
        tsd.sigSourcesChanged.connect(self.resetRasterSources)


        self.resetRasterSources()
        self.mapLayerModel().setDefaultRasterRenderer(self.defaultRasterRenderer())

    def resetRasterSources(self, *args):
        tsd = self.tsd()
        self.mapLayerModel().clear()
        if isinstance(tsd, TimeSeriesDatum):
            self.mapLayerModel().addMapLayerSources(tsd.qgsMimeDataUtilsUris())


    def tsd(self)->TimeSeriesDatum:
        """
        Returns the TimeSeriesDatum
        :return: TimeSeriesDatum
        """
        return self.mTSD

    def setSpatialExtent(self, extent:SpatialExtent):
        """
        Sets the spatial extent
        :param extent: SpatialExtent
        """
        assert isinstance(extent, SpatialExtent)
        extent = extent.toCrs(self.crs())
        self.setExtent(extent)

    def setSpatialCenter(self, center:SpatialPoint):
        """
        Sets the SpatialCenter
        :param center: SpatialPoint
        """
        assert isinstance(center, SpatialPoint)
        center = center.toCrs(self.crs())
        self.setCenter(center)

    def setFixedSize(self, size:QSize):
        """
        Changes the map-canvas size
        :param size: QSize
        """
        assert isinstance(size, QSize)
        if self.size() != size:
            super(MapCanvas, self).setFixedSize(size)

    def setCrs(self, crs:QgsCoordinateReferenceSystem):
        """
        Sets the
        :param crs:
        :return:
        """
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if self.crs() != crs:
            self.setDestinationCrs(crs)

    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Shortcut to return self.mapSettings().destinationCrs()
        :return: QgsCoordinateReferenceSystem
        """
        return self.mapSettings().destinationCrs()



    def setLayers(self, mapLayers):
        """
        Set the map layers and, if necessary, registers the in a QgsMapLayerStore
        :param mapLayers:
        """
        self.mMapLayerStore.addMapLayers(mapLayers)
        super(MapCanvas, self).setLayers(mapLayers)


    def isRefreshing(self)->bool:
        return self.mIsRefreshing

    def isVisibleToViewport(self)->bool:
        """
        Returns whether the MapCanvas is visible to a user and not hidden behind the invisible regions of a scroll area.
        :return: bool
        """
        return self.visibleRegion().boundingRect().isValid()

    def visibleLayers(self, sorted = True)->list:
        """
        Returns the QgsMapLayers to be shown in the map
        :return: [list-of-QgsMapLayers]
        """
        return self.mMapLayerModel.visibleLayers(sorted=sorted)

    def addToRefreshPipeLine(self, arguments: list):
        """
        Adds commands or other arguments to a pipeline which will be handled during the next timed refresh.
        :param arguments: argument | [list-of-arguments]
        """
        if not isinstance(arguments, list):
            arguments = [arguments]
        for a in arguments:
            if isinstance(a, (QgsMimeDataUtils.Uri, QgsMapLayer)):
                if not 'sources' in self.mTimedRefreshPipeLine.keys():
                    self.mTimedRefreshPipeLine['sources'] = []
                self.mTimedRefreshPipeLine['sources'].append(a)
            elif isinstance(a, QgsRasterRenderer):
                self.mTimedRefreshPipeLine[QgsFeatureRenderer] = a
            elif isinstance(a, QgsFeatureRenderer):
                self.mTimedRefreshPipeLine[QgsFeatureRenderer] = a
            elif isinstance(a, SpatialExtent):
                self.mTimedRefreshPipeLine[SpatialExtent] = a
            elif isinstance(a, SpatialPoint):
                self.mTimedRefreshPipeLine[SpatialExtent] = a
            elif isinstance(a, MapCanvas.Command):
                if not MapCanvas.Command in self.mTimedRefreshPipeLine.keys():
                    self.mTimedRefreshPipeLine[MapCanvas.Command] = []

                #append command, remove previous of same type
                while a in self.mTimedRefreshPipeLine[MapCanvas.Command]:
                    self.mTimedRefreshPipeLine[MapCanvas.Command].remove(a)
                self.mTimedRefreshPipeLine[MapCanvas.Command].append(a)
            else:
                raise NotImplementedError('Unsupported argument: {}'.format(str(a)))


    def timedRefresh(self):
        """
        Called to refresh the map canvas with all things needed to be done with lazy evaluation
        """
        if len(self.mTimedRefreshPipeLine) == 0 and self.layers() == self.mapLayerModel().visibleLayers():
            #there is nothing to do.
            return
        else:
            self.freeze(True)
            #look for new layers
            mlm = self.mapLayerModel()
            assert isinstance(mlm, MapCanvasLayerModel)

            #set sources first
            keys = self.mTimedRefreshPipeLine.keys()
            if 'sources' in keys:
                mlm.addMapLayerSources(self.mTimedRefreshPipeLine['sources'])

            #set renderers
            if QgsRasterRenderer in keys:
                self.mapLayerModel().setDefaultRasterRenderer(self.mTimedRefreshPipeLine[QgsRasterRenderer])

            if QgsFeatureRenderer in keys:
                self.mapLayerModel().setDefaultVectorRenderer(self.mTimedRefreshPipeLine[QgsFeatureRenderer])

            if QgsCoordinateReferenceSystem in keys:
                self.setDestinationCrs(self.mTimedRefreshPipeLine[QgsCoordinateReferenceSystem])

            if SpatialExtent in keys:
                self.setSpatialExtent(self.mTimedRefreshPipeLine[SpatialExtent])

            if SpatialPoint in keys:
                self.setSpatialExtent(self.mTimedRefreshPipeLine[SpatialPoint])

            if MapCanvas.Command in keys:
                commands = self.mTimedRefreshPipeLine[MapCanvas.Command]
                for command in commands:
                    assert isinstance(command, MapCanvas.Command)
                    if command == MapCanvas.Command.RefreshRenderer:
                        r = self.defaultRasterRenderer()
                        if isinstance(r, QgsRasterRenderer):
                            self.mapLayerModel().setDefaultRasterRenderer(r)

                    elif command == MapCanvas.Command.RefreshVisibility:
                        self.setLayers(self.visibleLayers())

                    elif command == MapCanvas.Command.RemoveRasters:
                        self.mMapLayerModel.removeMapLayerSources(self.mMapLayerModel.rasterSources())
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.RemoveVectors:
                        self.mMapLayerModel.removeMapLayerSources(self.mMapLayerModel.vectorSources())
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.ShowRasters:
                        self.mMapLayerModel.setLayerVisibility(QgsRasterLayer, True)
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.ShowVectors:
                        self.mMapLayerModel.setLayerVisibility(QgsVectorLayer, True)
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.HideRasters:
                        self.mMapLayerModel.setLayerVisibility(QgsRasterLayer, False)
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.HideVectors:
                        self.mMapLayerModel.setLayerVisibility(QgsVectorLayer, False)
                        self.setLayers(self.mMapLayerModel.visibleLayers())

                    elif command == MapCanvas.Command.Clear:
                        self.mMapLayerModel.clear()
                s = ""

            self.mTimedRefreshPipeLine.clear()

            lyrs = self.layers()
            visibleLayers = self.mapLayerModel().visibleLayers()
            if lyrs != visibleLayers:
                self.setLayers(visibleLayers)
            self.freeze(False)
            self.refresh()
            #is this really required?

            #if self.mNeedsRefresh or visibleLayers != lastLayers:
            #    self.mIsRefreshing = True
            #    self.mRefreshStartTime = time.time()
            #    self.setLayers(visibleLayers)
            #    self.refresh()
            #    self.mNeedsRefresh = False


    def setLayerVisibility(self, cls, isVisible:bool):
        """
        :param cls: type of layer, e.g. QgsRasterLayer to set visibility of all layers of same type
                    QgsMapLayer instance to the visibility of a specific layer
        :param isVisible: bool
        """
        self.mMapLayerModel.setLayerVisibility(cls, isVisible)
        self.addToRefreshPipeLine(MapCanvas.Command.RefreshVisibility)


    def setCrosshairStyle(self, crosshairStyle:CrosshairStyle, emitSignal=True):
        """
        Sets the CrosshairStyle
        :param crosshairStyle: CrosshairStyle
        :param emitSignal: Set to Fals to no emit a signal.
        """
        from timeseriesviewer.crosshair import CrosshairStyle
        if crosshairStyle is None:
            self.mCrosshairItem.crosshairStyle.setShow(False)
            self.mCrosshairItem.update()
        else:
            assert isinstance(crosshairStyle, CrosshairStyle)
            self.mCrosshairItem.setCrosshairStyle(crosshairStyle)

        if emitSignal:
            self.sigCrosshairStyleChanged.emit(self.mCrosshairItem.crosshairStyle)

    def crosshairStyle(self)->CrosshairStyle:
        """
        Returns the style of the Crosshair.
        :return: CrosshairStyle
        """
        return self.mCrosshairItem.crosshairStyle

    def setCrosshairPosition(self, spatialPoint:SpatialPoint, emitSignal=True):
        """
        Sets the position of the Crosshair.
        :param spatialPoint: SpatialPoint
        :param emitSignal: True (default). Set False to avoid emitting sigCrosshairPositionChanged
        :return:
        """
        point = spatialPoint.toCrs(self.mapSettings().destinationCrs())
        self.mCrosshairItem.setPosition(point)
        if emitSignal:
            self.sigCrosshairPositionChanged.emit(point)

    def crosshairPosition(self)->SpatialPoint:
        """Returns the last crosshair position"""
        return self.mCrosshairItem.mPosition


    def setCrosshairVisibility(self, b:bool, emitSignal=True):
        """
        Sets the Crosshair visbility
        :param b: bool
        """
        if b and self.mCrosshairItem.mPosition is None:
            self.mCrosshairItem.setPosition(self.spatialCenter())
            self.sigCrosshairPositionChanged.emit(self.spatialCenter())

        if b != self.mCrosshairItem.visibility():
            self.mCrosshairItem.setVisibility(b)
            if emitSignal:
                self.sigCrosshairVisibilityChanged.emit(b)

    def layerPaths(self):
        """
        :return: [list-of-str]
        """
        return [str(l.source()) for l in self.layers()]

    def pixmap(self):
        """
        Returns the current map image as pixmap
        :return: QPixmap
        """
        return self.grab()

    def contextMenu(self)->QMenu:
        """
        Create the MapCanvas context menu
        :return:
        """
        menu = QMenu()
        # add general options
        menu.addSeparator()
        m = menu.addMenu('Stretch to current extent...')
        action = m.addAction('Linear')
        action.triggered.connect(lambda : self.stretchToExtent(self.spatialExtent(), 'linear_minmax', p=0.0))

        action = m.addAction('Linear 5%')
        action.triggered.connect(lambda: self.stretchToExtent(self.spatialExtent(), 'linear_minmax', p=0.05))

        action = m.addAction('Gaussian')
        action.triggered.connect(lambda: self.stretchToExtent(self.spatialExtent(), 'gaussian', n=3))


        action = menu.addAction('Zoom to Layer')
        action.triggered.connect(lambda : self.setSpatialExtent(self.spatialExtentHint()))
        action = menu.addAction('Refresh')
        action.triggered.connect(lambda: self.refresh())
        menu.addSeparator()
        m = menu.addMenu('Crosshair...')
        action = m.addAction('Show')
        action.setCheckable(True)
        action.setChecked(self.mCrosshairItem.visibility())
        action.toggled.connect(self.setCrosshairVisibility)

        action = m.addAction('Style')
        def onCrosshairChange(*args):

            style = CrosshairDialog.getCrosshairStyle(parent=self,
                                                      mapCanvas=self,
                                                      crosshairStyle=self.mCrosshairItem.crosshairStyle)

            if isinstance(style, CrosshairStyle):
                self.setCrosshairStyle(style)

        action.triggered.connect(onCrosshairChange)

        menu.addSeparator()

        m = menu.addMenu('Copy...')
        action = m.addAction('Date')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_date'))
        action = m.addAction('Sensor')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_sensor'))
        action = m.addAction('Path')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_path'))
        action = m.addAction('Map')
        action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.pixmap()))

        m = menu.addMenu('Map Coordinates...')

        ext = self.spatialExtent()
        center = self.spatialExtent().spatialCenter()
        action = m.addAction('Extent (WKT Coordinates)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(ext.asWktCoordinates()))
        action = m.addAction('Extent (WKT Polygon)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(ext.asWktPolygon()))

        m.addSeparator()

        action = m.addAction('Map Center (WKT)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(center.asWkt()))

        action = m.addAction('Map Center')
        action.triggered.connect(lambda: QApplication.clipboard().setText(center.toString()))

        action = m.addAction('Map Extent (WKT)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(ext.asWktPolygon()))

        action = m.addAction('Map Extent')
        action.triggered.connect(lambda: QApplication.clipboard().setText(ext.toString()))

        m.addSeparator()

        action = m.addAction('CRS (EPSG)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(self.crs().authid()))
        action = m.addAction('CRS (WKT)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(self.crs().toWkt()))
        action = m.addAction('CRS (Proj4)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(self.crs().toProj4()))


        m = menu.addMenu('Save to...')
        action = m.addAction('PNG')
        action.triggered.connect(lambda : self.saveMapImageDialog('PNG'))
        action = m.addAction('JPEG')
        action.triggered.connect(lambda: self.saveMapImageDialog('JPG'))

        if isinstance(self.mLabelingModel, LabelAttributeTableModel) and isinstance(self.mTSD, TimeSeriesDatum):
            menu.addSeparator()
            m = self.mLabelingModel.contextMenuTSD(self.mTSD, menu)

        menu.addSeparator()

        from timeseriesviewer.utils import qgisInstance
        actionAddRaster2QGIS = menu.addAction('Add raster layers(s) to QGIS')
        actionAddRaster2QGIS.triggered.connect(lambda : self.addLayers2QGIS(
                [l for l in self.layers() if isinstance(l, QgsRasterLayer)]
            )
        )
        # QGIS 3: action.triggered.connect(lambda: QgsProject.instance().addMapLayers([l for l in self.layers() if isinstance(l, QgsRasterLayer)]))
        actionAddVector2QGIS = menu.addAction('Add vector layer(s) to QGIS')
        actionAddRaster2QGIS.triggered.connect(lambda : self.addLayers2QGIS(
            #QgsProject.instance().addMapLayers(
                [l for l in self.layers() if isinstance(l, QgsVectorLayer)]
            )
        )
        # QGIS 3: action.triggered.connect(lambda: QgsProject.instance().addMapLayers([l for l in self.layers() if isinstance(l, QgsVectorLayer)]))

        b = isinstance(qgisInstance(), QgisInterface)
        for a in [actionAddRaster2QGIS, actionAddVector2QGIS]:
            a.setEnabled(b)
        menu.addSeparator()

        action = menu.addAction('Hide date')
        action.triggered.connect(lambda : self.sigChangeDVRequest.emit(self, 'hide_date'))
        action = menu.addAction('Remove date')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'remove_date'))
        menu.addSeparator()
        action = menu.addAction('Hide map view')
        action.triggered.connect(lambda: self.sigChangeMVRequest.emit(self, 'hide_mapview'))
        action = menu.addAction('Remove map view')
        action.triggered.connect(lambda: self.sigChangeMVRequest.emit(self, 'remove_mapview'))

        return menu

    def contextMenuEvent(self, event):
        """
        Create and shows the MapCanvas context menu.
        :param event: QEvent
        """
        menu = self.contextMenu()
        menu.exec_(event.globalPos())

    def addLayers2QGIS(self, mapLayers):
        from timeseriesviewer.utils import qgisInstance
        iface = qgisInstance()
        if isinstance(iface, QgisInterface):
            grpNode= iface.layerTreeView().currentGroupNode()
            assert isinstance(grpNode, QgsLayerTreeGroup)
            for l in mapLayers:
                if isinstance(l, QgsRasterLayer):
                    lqgis = iface.addRasterLayer(l.source(), l.name())
                    lqgis.setRenderer(l.renderer().clone())

                if isinstance(l, QgsVectorLayer):
                    lqgis = iface.addVectorLayer(l.source(), l.name(), 'ogr')
                    lqgis.setRenderer(l.renderer().clone())

    def stretchToCurrentExtent(self):

        se = self.spatialExtent()
        self.stretchToExtent(se)

    def stretchToExtent(self, spatialExtent:SpatialExtent, stretchType='linear_minmax', **stretchArgs):
        """
        :param spatialExtent: rectangle to get the image statistics for
        :param stretchType: ['linear_minmax' (default), 'gaussian']
        :param stretchArgs:
            linear_minmax: 'p'  percentage from min/max, e.g. +- 5 %
            gaussian: 'n' mean +- n* standard deviations
        :return:
        """

        for l in self.layers():
            if isinstance(l, QgsRasterLayer):
                r = l.renderer()
                dp = l.dataProvider()
                newRenderer = None
                extent = spatialExtent.toCrs(l.crs())

                assert isinstance(dp, QgsRasterDataProvider)

                def getCE(band):
                    stats = dp.bandStatistics(band, QgsRasterBandStats.All, extent, 500)
                    # hist = dp.histogram(band,100, stats.minimumValue, stats.maximumValue, extent, 500, False)
                    ce = QgsContrastEnhancement(dp.dataType(band))
                    d = (stats.maximumValue - stats.minimumValue)
                    if stretchType == 'linear_minmax':
                        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                        ce.setMinimumValue(stats.minimumValue + d * stretchArgs.get('p', 0))
                        ce.setMaximumValue(stats.maximumValue - d * stretchArgs.get('p', 0))
                    elif stretchType == 'gaussian':
                        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                        ce.setMinimumValue(stats.mean - stats.stdDev * stretchArgs.get('n', 3))
                        ce.setMaximumValue(stats.mean + stats.stdDev * stretchArgs.get('n', 3))
                    else:
                        # stretchType == 'linear_minmax':
                        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                        ce.setMinimumValue(stats.minimumValue)
                        ce.setMaximumValue(stats.maximumValue)

                    return ce

                if isinstance(r, QgsMultiBandColorRenderer):

                    #newRenderer = QgsMultiBandColorRenderer(None, r.redBand(), r.greenBand(), r.blueBand())
                    newRenderer = cloneRenderer(r)

                    ceR = getCE(r.redBand())
                    ceG = getCE(r.greenBand())
                    ceB = getCE(r.blueBand())

                    newRenderer.setRedContrastEnhancement(ceR)
                    newRenderer.setGreenContrastEnhancement(ceG)
                    newRenderer.setBlueContrastEnhancement(ceB)

                elif isinstance(r, QgsSingleBandPseudoColorRenderer):
                    newRenderer = cloneRenderer(r)
                    ce = getCE(newRenderer.band())
                    #stats = dp.bandStatistics(newRenderer.band(), QgsRasterBandStats.All, extent, 500)

                    shader = newRenderer.shader()
                    newRenderer.setClassificationMax(ce.maximumValue())
                    newRenderer.setClassificationMin(ce.minimumValue())
                    shader.setMaximumValue(ce.maximumValue())
                    shader.setMinimumValue(ce.minimumValue())
                elif isinstance(r, QgsSingleBandGrayRenderer):
                    newRenderer = cloneRenderer(r)
                    s = ""
                elif isinstance(r, QgsPalettedRasterRenderer):
                    s = ""
                    #newRenderer = cloneRenderer(r)

                if newRenderer is not None:
                    self.sigChangeSVRequest.emit(self, newRenderer)
                    return
        s = ""


    def saveMapImageDialog(self, fileType):
        import timeseriesviewer.settings
        lastDir = timeseriesviewer.settings.value(timeseriesviewer.settings.Keys.ScreenShotDirectory, os.path.expanduser('~'))
        from timeseriesviewer.utils import saveFilePath
        from timeseriesviewer.mapvisualization import MapView
        if isinstance(self.mTSD, TimeSeriesDatum) and isinstance(self.mMapView, MapView):
            path = saveFilePath('{}.{}'.format(self.mTSD.date, self.mMapView.title()))
        else:
            path = 'mapcanvas'
        path = jp(lastDir, '{}.{}'.format(path, fileType.lower()))
        path, _ = QFileDialog.getSaveFileName(self, 'Save map as {}'.format(fileType), path)
        if len(path) > 0:
            self.saveAsImage(path, None, fileType)
            timeseriesviewer.settings.setValue(timeseriesviewer.settings.Keys.ScreenShotDirectory, os.path.dirname(path))

    def defaultRasterRenderer(self)->QgsRasterRenderer:
        """
        Returns the raster renderer in dependence of MapView and TimeSeriesDatum sensor
        :return: QgsRasterRenderer
        """
        from timeseriesviewer.mapvisualization import MapView
        if isinstance(self.mTSD, TimeSeriesDatum) and isinstance(self.mMapView, MapView):
            return self.mMapView.sensorWidget(self.mTSD.sensor()).rasterRenderer()
        else:
            return None

    def setSpatialExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the SpatialExtent to be shown.
        :param spatialExtent: SpatialExtent
        """
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            spatialExtent = spatialExtent.toCrs(self.crs())
            self.setExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint:SpatialPoint):
        """
        Sets the map center
        :param spatialPoint: SpatialPoint
        """
        center = spatialPoint.toCrs(self.crs())
        self.setCenter(center)

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the map extent as SpatialExtent (extent + CRS)
        :return: SpatialExtent
        """
        return SpatialExtent.fromMapCanvas(self)

    def spatialCenter(self)->SpatialPoint:
        """
        Returns the map center as SpatialPoint (QgsPointXY + CRS)
        :return: SpatialPoint
        """
        return SpatialPoint.fromMapCanvasCenter(self)


    def spatialExtentHint(self)->SpatialExtent:
        """
        Returns a hint for a SpatialExtent, derived from the first raster layer
        :return: SpatialExtent
        """
        crs = self.crs()

        layers = self.layers()
        if len(layers) > 0:
            e = self.fullExtent()
            ext = SpatialExtent(crs, e)
        else:
            ext = SpatialExtent.world()
        return ext


class CanvasBoundingBoxItem(QgsGeometryRubberBand):

    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(CanvasBoundingBoxItem, self).__init__(mapCanvas)

        self.canvas = mapCanvas
        self.mCanvasExtents = dict()
        self.mShow = True
        self.mShowTitles = True
        self.setIconType(QgsGeometryRubberBand.ICON_NONE)

    def connectCanvas(self, canvas):
        assert isinstance(canvas, QgsMapCanvas)
        assert canvas != self.canvas
        if canvas not in self.mCanvasExtents.keys():
            self.mCanvasExtents[canvas] = None
            canvas.extentsChanged.connect(lambda : self.onExtentsChanged(canvas))
            canvas.destroyed.connect(lambda : self.disconnectCanvas(canvas))
            self.onExtentsChanged(canvas)

    def disconnectCanvas(self, canvas):
            self.mCanvasExtents.pop(canvas)

    def onExtentsChanged(self, canvas):
        assert isinstance(canvas, QgsMapCanvas)

        ext = SpatialExtent.fromMapCanvas(canvas)
        ext = ext.toCrs(self.canvas.mapSettings().destinationCrs())

        geom = QgsPolygon()
        assert geom.fromWkt(ext.asWktPolygon())

        self.mCanvasExtents[canvas] = (ext, geom)
        self.refreshExtents()

    def refreshExtents(self):
        multi = QgsPolygon()
        if self.mShow:
            for canvas, t in self.mCanvasExtents.items():
                ext, geom = t
                multi.addGeometry(geom.clone())
        self.setGeometry(multi)

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
        super(CanvasBoundingBoxItem, self).paint(painter)

        if self.mShowTitles and self.mShow:
            painter.setPen(Qt.blue);
            painter.setFont(QFont("Arial", 30))

            for canvas, t in self.mCanvasExtents.items():
                ext, geom = t
                ULpx = self.toCanvasCoordinates(ext.center())
                txt = canvas.windowTitle()
                painter.drawLine(0, 0, 200, 200);
                painter.drawText(ULpx,  txt)


    def setShow(self, b):
        assert isinstance(b, bool)
        self.mShow = b

    def setShowTitles(self, b):
        assert isinstance(b, bool)
        self.mShowTitles = b

