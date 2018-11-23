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


import os, time
from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtXml import QDomDocument

from . import SETTINGS
from .utils import *
from .timeseries import TimeSeriesDatum
from .crosshair import CrosshairDialog, CrosshairStyle
from .maptools import *

class MapLayerInfo(object):
    """
    A minimum description of a QgsMapLayer source.
    """

    def __init__(self, srcOrMapLayer, isVisible, provider='gdal', renderer=None):

        self.mSrc = ''
        self.mLayer = None
        self.mProvider = None
        self.mRenderer = None
        self.setRenderer(renderer)
        if isinstance(srcOrMapLayer, QgsMapLayer):
            self.mSrc = srcOrMapLayer.source()
            self.mProvider = srcOrMapLayer.providerType()
            self.mLayer = srcOrMapLayer
            if isinstance(srcOrMapLayer, QgsVectorLayer):
                self.mRenderer = srcOrMapLayer.renderer()
            elif isinstance(srcOrMapLayer, QgsRasterLayer):
                self.mRenderer = srcOrMapLayer.renderer()

        else:
            self.mSrc = srcOrMapLayer
            assert provider in ['ogr','gdal','memory']
            self.mProvider = provider


        self.mIsVisible = isVisible


    def isSameSource(self, other):
        if not isinstance(other, MapLayerInfo):
            return False
        return self.mSrc == other.mSrc

    def initMapLayer(self):
        if self.mProvider == 'gdal':
            self.mLayer = QgsRasterLayer(self.mSrc)
        elif self.mProvider == 'ogr':
            self.mLayer = QgsVectorLayer(self.mSrc,os.path.basename(self.mSrc), 'ogr', True)

        self.setRenderer(self.mRenderer)

    def setRenderer(self, renderer):
        self.mRenderer = renderer
        if self.mProvider == 'ogr' and isinstance(renderer, QgsFeatureRenderer) or \
           self.mProvider == 'gdal' and isinstance(renderer, QgsRasterRenderer):
            self.mRenderer = renderer
            if self.isInitialized():
                from timeseriesviewer.mapvisualization import cloneRenderer
                copyRenderer(self.mRenderer, self.mLayer)

                #self.mLayer.repaintRequested.emit()

    def setIsVisible(self, b):
        self.mIsVisible = b

    def isVisible(self):
        return self.mIsVisible

    def layer(self):
        """returns a QgsMapLayer object related to the specified source.
            If not provided in the constructor, the QgsMapLayer will be initialized with first call of this method.
        """
        if not self.isInitialized():
            self.initMapLayer()
        return self.mLayer

    def isInitialized(self):
        return isinstance(self.mLayer, QgsMapLayer)

    def isRegistered(self):
        if not self.isInitialized():
            return None
        ref = QgsProject.instance().mapLayer(self.mLayer.layerId())

        return isinstance(ref, QgsMapLayer)


class MapCanvasLayerModel(QAbstractTableModel):
    """
    A model to save a list of QgsMapLayers and additional properties.
    """


    def __init__(self, parent=None):
        super(MapCanvasLayerModel, self).__init__(parent=parent)

        self.mColumnNames = ['layerID', 'isVisible', '']
        self.mLayerInfos = []


    def __len__(self):
        return len(self.mLayerInfos)

    def __iter__(self):
        return iter(self.mLayerInfos)

    def __repr__(self):
        info = 'MapLayerModel::'
        for li in self.mLayerInfos:
            if li.isVisible():
                info += '{}'.format(li.mSrc)
        return info

    def setRenderer(self, renderer):
        for li in self.mLayerInfos:
            assert isinstance(li, MapLayerInfo)
            li.setRenderer(renderer)

    def setVectorLayerSources(self, vectorSources, **kwds):
        self.removeLayerInfos(self.vectorLayerInfos())
        self.insertLayerInfos(0, vectorSources, provider='ogr', **kwds)

    def setVectorLayerVisibility(self, b):
        for li in self.vectorLayerInfos():
            li.setIsVisible(b)

    def setRasterLayerVisibility(self, b):
        for li in self.rasterLayerInfos():
            li.setIsVisible(b)


    def setRasterLayerSources(self, rasterSources, **kwds):
        self.removeLayerInfos(self.rasterLayerInfos())
        self.addLayerInfos(rasterSources, provider='gdal', **kwds)

    def vectorLayerInfos(self):
        return [li for li in self.mLayerInfos if li.mProvider in ['ogr', 'memory']]

    def rasterLayerInfos(self):
        return [li for li in self.mLayerInfos if li.mProvider == 'gdal']


    def addLayerInfo(self, mapLayer, **kwds):
        self.addLayerInfos([mapLayer], **kwds)

    def addLayerInfos(self, mapLayers, **kwds):
        self.insertLayerInfos(len(self), mapLayers, **kwds)

    def insertLayerInfo(self, i, mapLayer, **kwds):
        self.insertLayerInfo(i, [mapLayer], **kwds)

    def insertLayerInfos(self, i, mapLayers, isVisible=True, provider='gdal'):
        for mapLayer in mapLayers:
            li = None
            if isinstance(mapLayer, QgsRasterLayer) and provider != 'gdal':
                continue
            if isinstance(mapLayer, QgsVectorLayer) and provider not in ['ogr', 'memory']:
                continue
            if isinstance(mapLayer, QgsMapLayer):
                li = MapLayerInfo(mapLayer, isVisible=isVisible, provider=mapLayer.dataProvider().name())
            elif isinstance(mapLayer, QgsRasterLayer):
                li = MapLayerInfo(mapLayer, isVisible=isVisible, provider=mapLayer.dataProvider().name())
            elif isinstance(mapLayer, str):
                li = MapLayerInfo(mapLayer, isVisible=isVisible, provider=provider)

            if isinstance(li, MapLayerInfo):
                self.mLayerInfos.insert(i, li)
                i += 1

    def removeLayerInfo(self, mapLayer):
        self.removeLayerInfos([mapLayer])

    def removeLayerInfos(self, mapLayers):
        toRemove = []
        sourcesToRemove = []
        for ml in mapLayers:
            if isinstance(ml, QgsMapLayer):
                sourcesToRemove.append(ml.source())
            else:
                sourcesToRemove.append(ml)

        toRemove = [li for li in self.mLayerInfos if li in sourcesToRemove]

        for li in toRemove:
            self.mLayerInfos.remove(li)


    def layerSources(self):
        return [li.mSrc for li in self.mLayerInfos]

    def layers(self):
        return [li.layer() for li in self.mLayerInfos]

    def visibleLayers(self):
        return [li.layer() for li in self.mLayerInfos if li.isVisible()]

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.mLayers)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return self



class MapCanvas(QgsMapCanvas):

    saveFileDirectories = dict()
    sigShowProfiles = pyqtSignal(SpatialPoint, str)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigChangeDVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeMVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeSVRequest = pyqtSignal(QgsMapCanvas, QgsRasterRenderer)
    sigMapRefreshed = pyqtSignal([float, float],[float])

    sigCrosshairPositionChanged = pyqtSignal(SpatialPoint)
    sigCrosshairVisibilityChanged = pyqtSignal(bool)
    from .crosshair import CrosshairStyle
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)

        self.mLayerModel = MapCanvasLayerModel(parent=self)
        self.mTSD = self.mMapView = None
        #the canvas

        self.mIsRefreshing = False
        self.mRenderingFinished = True
        self.mRefreshStartTime = time.time()

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
        self.setCanvasColor(SETTINGS.value('CANVAS_BACKGROUND_COLOR', QColor(0, 0, 0)))
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        #refreshTimer.timeout.connect(self.onTimerRefresh)
        #self.extentsChanged.connect(lambda : self._setDataRefreshed())
        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))

        #self.mLazyRasterSources = []
        #self.mLazyVectorSources = []

        self.mRendererRaster = None
        self.mRendererVector = None



        self.mMapSummary = self.mapSummary()

        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.mCrosshairItem = CrosshairMapCanvasItem(self)

        self.mMapTools = dict()
        self.mMapTools['zoomOut'] = QgsMapToolZoom(self, True)
        self.mMapTools['zoomIn'] = QgsMapToolZoom(self, False)
        self.mMapTools['pan'] = QgsMapToolPan(self)

        from timeseriesviewer.maptools import CursorLocationMapTool
        mt = CursorLocationMapTool(self)
        mt.sigLocationRequest.connect(lambda c: self.sigShowProfiles.emit(c, 'identifyTemporalProfile'))
        self.mMapTools['identifyTemporalProfile'] = mt

        mt = CursorLocationMapTool(self)
        mt.sigLocationRequest.connect(lambda c : self.sigShowProfiles.emit(c, 'identifySpectralProfile'))
        self.mMapTools['identifySpectralProfile'] = mt

        mt = CursorLocationMapTool(self)
        #mt.sigLocationRequest.connect(self.sigShowProfiles.emit)
        mt.sigLocationRequest.connect(lambda c: self.sigShowProfiles.emit(c, 'identifyCursorLocationValues'))
        self.mMapTools['identifyCursorLocationValues'] = mt


        mt = CursorLocationMapTool(self)
        mt.sigLocationRequest.connect(lambda pt: self.setCenter(pt))
        self.mMapTools['moveCenter'] = mt


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
        scope = self.expressionContextScope()

    def setTSD(self, tsd):
        from timeseriesviewer.timeseries import TimeSeriesDatum

        assert isinstance(tsd, TimeSeriesDatum)
        self.mTSD = tsd

        scope = self.expressionContextScope()
        scope.setVariable('map_date', str(tsd.date), isStatic=True)
        scope.setVariable('map_doy', tsd.doy, isStatic=True)
        scope.setVariable('map_sensor', tsd.sensor.name(), isStatic=False)
        tsd.sensor.sigNameChanged.connect(lambda name : scope.setVariable('map_sensor', name))

        s = ""

    def setFixedSize(self, size):
        assert isinstance(size, QSize)
        if self.size() != size:
            super(MapCanvas, self).setFixedSize(size)

    def setCrs(self, crs:QgsCoordinateReferenceSystem):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if self.crs() != crs:
            self.setDestinationCrs(crs)

    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Shortcut to return self.mapSettings().destinationCrs()
        :return: QgsCoordinateReferenceSystem
        """
        return self.mapSettings().destinationCrs()


    def mapSummary(self):
        dom = QDomDocument()
        root = dom.createElement('renderer')
        dom.appendChild(root)
        if self.mRendererVector:
            self.mRendererVector.writeXML(dom, root)
        if self.mRendererRaster:
            self.mRendererRaster.writeXML(dom, root)
        xml = dom.toString()
        return (self.crs(), self.spatialExtent(), self.size(), self.mLayerModel.visibleLayers(), xml)


    def layerModel(self):
        return self.mLayerModel

    def setLayers(self, mapLayers):
        """
        Set the map layers and, if necessary, registers the in a QgsMapLayerStore
        :param mapLayers:
        """

        from .utils import MAP_LAYER_STORES
        if len(MAP_LAYER_STORES) > 0:
            store = MAP_LAYER_STORES[0]
            store.addMapLayers(mapLayers)
        else:
            print('MAPCANVAS without map layer store', file=sys.stderr)


        super(MapCanvas, self).setLayers(mapLayers)

        #self.refresh()

    def isRefreshing(self)->bool:
        return self.mIsRefreshing

    def isVisibleToViewport(self)->bool:
        return self.visibleRegion().boundingRect().isValid()

    def refresh(self, force=False):
        """
        low-level, only performed if MapCanvas is visible or force=True
        :param force: bool
        """

        mLyrs = self.layers()
        vLyrs = self.mLayerModel.visibleLayers()
        if mLyrs != vLyrs:
            self.setLayers(vLyrs)
            if (self.renderFlag() and not self.isDrawing()) or force:
                super(MapCanvas, self).refresh()
        else:
            s = ""

    def setLayers(self, layers, *args):
        self.mNeedsRefresh = True
        super(MapCanvas, self).setLayers(layers, *args)

    def refreshMap(self):
        self.mIsRefreshing = True
        self.mRefreshStartTime = time.time()


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



    def contextMenuEvent(self, event):
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
        action.triggered.connect(lambda: self.refresh(True))
        menu.addSeparator()

        action = menu.addAction('Change crosshair style')


        def onCrosshairChange(*args):

            style = CrosshairDialog.getCrosshairStyle(parent=self,
                                                  mapCanvas=self,
                                                  crosshairStyle=self.mCrosshairItem.crosshairStyle)

            if isinstance(style, CrosshairStyle):
                self.setCrosshairStyle(style)

        action.triggered.connect(onCrosshairChange)

        if self.mCrosshairItem.visibility():
            action = menu.addAction('Hide crosshair')
            action.triggered.connect(lambda : self.setCrosshairVisibility(False))
        else:
            action = menu.addAction('Show crosshair')
            action.triggered.connect(lambda: self.setCrosshairVisibility(True))

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
        action.triggered.connect(lambda: QApplication.clipboard().setText(center.wellKnownText()))

        action = m.addAction('Map Center')
        action.triggered.connect(lambda: QApplication.clipboard().setText(center.toString()))

        action = m.addAction('Map Extent (WKT)')
        action.triggered.connect(lambda: QApplication.clipboard().setText(ext.wellKnownText()))

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

    def stretchToExtent(self, spatialExtent, stretchType='linear_minmax', **stretchArgs):
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

                    if False:
                        vMin = min(ceR.minimumValue(), ceG.minimumValue(), ceB.minimumValue())
                        vMax = max(ceR.maximumValue(), ceG.maximumValue(), ceB.maximumValue())
                        for ce in [ceR, ceG, ceB]:
                            assert isinstance(ce, QgsContrastEnhancement)
                            ce.setMaximumValue(vMax)
                            ce.setMinimumValue(vMin)

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
        s = ""

    def activateMapTool(self, key):
        if key is None:
            self.setMapTool(None)
        elif key in self.mMapTools.keys():
            super(MapCanvas, self).setMapTool(self.mMapTools[key])
        else:
            s = ""
            #logger.error('unknown map tool key "{}"'.format(key))

    def saveMapImageDialog(self, fileType):
        lastDir = SETTINGS.value('CANVAS_SAVE_IMG_DIR', os.path.expanduser('~'))
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
            SETTINGS.setValue('CANVAS_SAVE_IMG_DIR', os.path.dirname(path))


    def setRenderer(self, renderer, refresh=True):

        success = self.layerModel().setRenderer(renderer)
        self.setRenderFlag(True)
        #self.refresh()


    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            b =  self.crs() != spatialExtent.crs()
            spatialExtent = spatialExtent.toCrs(self.crs())
            if spatialExtent:
                ext = QgsRectangle(spatialExtent)
                if b:
                    s = ""
                self.setCenter(ext.center())
                self.setExtent(ext)
                s = ""

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


    def spatialExtentHint(self):
        crs = self.crs()
        ext = SpatialExtent.world()
        for lyr in self.mLayerModel.layers() + self.layers():
            ext = SpatialExtent.fromLayer(lyr).toCrs(crs)
            break
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

