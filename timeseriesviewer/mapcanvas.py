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


import os
from qgis.core import *
from qgis.gui import *

from PyQt5.Qt import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtXml import QDomDocument

from timeseriesviewer import SETTINGS
from timeseriesviewer.utils import *
from timeseriesviewer.timeseries import TimeSeriesDatum
from timeseriesviewer.crosshair import CrosshairDialog

class MapTools(object):
    """
    Static class to support handling of nQgsMapTools.
    """
    def __init__(self):
        raise Exception('This class is not for any instantiation')
    ZoomIn = 'ZOOM_IN'
    ZoomOut = 'ZOOM_OUT'
    ZoomFull = 'ZOOM_FULL'
    Pan = 'PAN'
    ZoomPixelScale = 'ZOOM_PIXEL_SCALE'
    CursorLocation = 'CURSOR_LOCATION'
    SpectralProfile = 'SPECTRAL_PROFILE'
    TemporalProfile = 'TEMPORAL_PROFILE'
    MoveToCenter = 'MOVE_CENTER'

    @staticmethod
    def copy(mapTool):
        assert isinstance(mapTool, QgsMapTool)
        s = ""

    @staticmethod
    def create(mapToolKey, canvas, *args, **kwds):
        assert mapToolKey in MapTools.mapToolKeys()

        assert isinstance(canvas, QgsMapCanvas)

        if mapToolKey == MapTools.ZoomIn:
            return QgsMapToolZoom(canvas, False)
        if mapToolKey == MapTools.ZoomOut:
            return QgsMapToolZoom(canvas, True)
        if mapToolKey == MapTools.Pan:
            return QgsMapToolPan(canvas)
        if mapToolKey == MapTools.ZoomPixelScale:
            return PixelScaleExtentMapTool(canvas)
        if mapToolKey == MapTools.ZoomFull:
            return FullExtentMapTool(canvas)
        if mapToolKey == MapTools.CursorLocation:
            return CursorLocationMapTool(canvas, *args, **kwds)
        if mapToolKey == MapTools.MoveToCenter:
            tool = CursorLocationMapTool(canvas, *args, **kwds)
            tool.sigLocationRequest.connect(canvas.setCenter)
            return tool
        if mapToolKey == MapTools.SpectralProfile:
            return SpectralProfileMapTool(canvas, *args, **kwds)
        if mapToolKey == MapTools.TemporalProfile:
            return TemporalProfileMapTool(canvas, *args, **kwds)

        raise Exception('Unknown mapToolKey {}'.format(mapToolKey))


    @staticmethod
    def mapToolKeys():
        return [MapTools.__dict__[k] for k in MapTools.__dict__.keys() if not k.startswith('_')]



class CursorLocationMapTool(QgsMapToolEmitPoint):

    sigLocationRequest = pyqtSignal([SpatialPoint],[SpatialPoint, QgsMapCanvas])

    def __init__(self, canvas, showCrosshair=True, purpose=None):
        self.mShowCrosshair = showCrosshair
        self.mCanvas = canvas
        self.mPurpose = purpose
        QgsMapToolEmitPoint.__init__(self, self.mCanvas)

        self.mMarker = QgsVertexMarker(self.mCanvas)
        self.mRubberband = QgsRubberBand(self.mCanvas, QgsWkbTypes.PolygonGeometry)

        color = QColor('red')

        self.mRubberband.setLineStyle(Qt.SolidLine)
        self.mRubberband.setColor(color)
        self.mRubberband.setWidth(2)

        self.mMarker.setColor(color)
        self.mMarker.setPenWidth(3)
        self.mMarker.setIconSize(5)
        self.mMarker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X

    def canvasPressEvent(self, e):
        geoPoint = self.toMapCoordinates(e.pos())
        self.mMarker.setCenter(geoPoint)

    def setStyle(self, color=None, brushStyle=None, fillColor=None, lineStyle=None):
        if color:
            self.mRubberband.setColor(color)
        if brushStyle:
            self.mRubberband.setBrushStyle(brushStyle)
        if fillColor:
            self.mRubberband.setFillColor(fillColor)
        if lineStyle:
            self.mRubberband.setLineStyle(lineStyle)

    def canvasReleaseEvent(self, e):


        pixelPoint = e.pixelPoint()

        crs = self.mCanvas.mapSettings().destinationCrs()
        self.mMarker.hide()
        geoPoint = self.toMapCoordinates(pixelPoint)
        if self.mShowCrosshair:
            #show a temporary crosshair
            ext = SpatialExtent.fromMapCanvas(self.mCanvas)
            cen = geoPoint
            geom = QgsGeometry()

            lineV = QgsLineString([QgsPoint(ext.upperLeftPt().x(),cen.y()), QgsPoint(ext.lowerRightPt().x(), cen.y())])
            lineH = QgsLineString([QgsPoint(cen.x(), ext.upperLeftPt().y()), QgsPoint(cen.x(), ext.lowerRightPt().y())])
            geom.addPart(lineV, QgsWkbTypes.LineGeometry)
            geom.addPart(lineH, QgsWkbTypes.LineGeometry)
            self.mRubberband.addGeometry(geom, None)
            self.mRubberband.show()
            #remove crosshair after 0.25 sec
            QTimer.singleShot(250, self.hideRubberband)

        pt = SpatialPoint(crs, geoPoint)
        self.sigLocationRequest[SpatialPoint].emit(pt)
        self.sigLocationRequest[SpatialPoint, QgsMapCanvas].emit(pt, self.canvas())

    def hideRubberband(self):
        self.mRubberband.reset()


class SpectralProfileMapTool(CursorLocationMapTool):

    def __init__(self, *args, **kwds):
        super(SpectralProfileMapTool, self).__init__(*args, **kwds)


class TemporalProfileMapTool(CursorLocationMapTool):

    def __init__(self, *args, **kwds):
        super(TemporalProfileMapTool, self).__init__(*args, **kwds)


class FullExtentMapTool(QgsMapTool):
    def __init__(self, canvas):
        super(FullExtentMapTool, self).__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, mouseEvent):
        self.canvas.zoomToFullExtent()

    def flags(self):
        return QgsMapTool.Transient


class PixelScaleExtentMapTool(QgsMapTool):
    def __init__(self, canvas):
        super(PixelScaleExtentMapTool, self).__init__(canvas)
        self.canvas = canvas

    def flags(self):
        return QgsMapTool.Transient


    def canvasReleaseEvent(self, mouseEvent):
        layers = self.canvas.layers()

        unitsPxX = []
        unitsPxY = []
        for lyr in self.canvas.layers():
            if isinstance(lyr, QgsRasterLayer):
                unitsPxX.append(lyr.rasterUnitsPerPixelX())
                unitsPxY.append(lyr.rasterUnitsPerPixelY())

        if len(unitsPxX) > 0:
            unitsPxX = np.asarray(unitsPxX)
            unitsPxY = np.asarray(unitsPxY)
            if True:
                # zoom to largest pixel size
                i = np.nanargmax(unitsPxX)
            else:
                # zoom to smallest pixel size
                i = np.nanargmin(unitsPxX)
            unitsPxX = unitsPxX[i]
            unitsPxY = unitsPxY[i]
            f = 0.2
            width = f * self.canvas.size().width() * unitsPxX #width in map units
            height = f * self.canvas.size().height() * unitsPxY #height in map units


            center = SpatialPoint.fromMapCanvasCenter(self.canvas)
            extent = SpatialExtent(center.crs(), 0, 0, width, height)
            extent.setCenter(center, center.crs())
            self.canvas.setExtent(extent)
        s = ""


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
    sigDataLoadingFinished = pyqtSignal(np.timedelta64)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)

        self.mLayerModel = MapCanvasLayerModel(parent=self)
        self.mTSD = self.mMapView = None
        #the canvas
        self.mRefreshScheduled = False

        def resetRenderStartTime():
            self.mRenderStartTime = np.datetime64('now' ,'ms')
        resetRenderStartTime()

        def emitRenderTimeDelta(*args):
            dt = np.datetime64('now', 'ms') - self.mRenderStartTime
            self.sigDataLoadingFinished.emit(dt)

        self.renderStarting.connect(resetRenderStartTime)
        self.renderComplete.connect(emitRenderTimeDelta)

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


        self.mWasVisible = False
        self.mMapSummary = self.mapSummary()

        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.crosshairItem = CrosshairMapCanvasItem(self)

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

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if self.crs() != crs:
            self.setDestinationCrs(crs)

    def crs(self):
        return self.mapSettings().destinationCrs()

    def onVectorOverlayChange(self, *args):

        self.refresh()

    """
    def depr_mapLayersToRender(self, *args):
        
        if len(self.mLazyRasterSources) > 0:
            mls = [QgsRasterLayer(src) for src in self.mLazyRasterSources]
            QgsProject.instance().addMapLayers(mls, False)
            del self.mLazyRasterSources[:]
            self.mLayerModel.extend(mls)
            self.setRenderer(self.mRendererRaster, refresh=False)
        if len(self.mLazyVectorSources) > 0:
            for t in self.mLazyVectorSources:

                lyr, path, name, provider = t
                #lyr = QgsVectorLayer(path, name, provider, False)
                #lyr = t
                #add vector layers on top
                lyr.rendererChanged.connect(self.onVectorOverlayChange)
                self.mLayerModel.insert(0, lyr)
            del self.mLazyVectorSources[:]
            self.setRenderer(self.mRendererVector, refresh=False)

        return self.mLayerModel
        """

    #def setLazyRasterSources(self, sources):
    #    del self.mLazyRasterSources[:]
    #    assert isinstance(sources, list)
    #    self.mLazyRasterSources.extend(sources[:])

    #def setLazyVectorSources(self, sourceLayers):
    #    assert isinstance(sourceLayers, list)
    #    del self.mLazyVectorSources[:]
    #    for lyr in sourceLayers:
    #        assert isinstance(lyr, QgsVectorLayer)
    #        self.mLazyVectorSources.append((lyr, lyr.source(), lyr.name(), lyr.providerType()))

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

    def setLayerSet(self, *args):
        raise DeprecationWarning()

    def layerModel(self):
        return self.mLayerModel

    def setLayers(self, mapLayers):


        oldLayers = self.layers()
        newLayers = [l for l in mapLayers if l not in oldLayers]

        if len(newLayers) > 0:
            reg = QgsProject.instance()
            reg.addMapLayers(newLayers, False)

        super(MapCanvas, self).setLayers(mapLayers)

        #self.refresh()

    def refresh(self, force=False):
        #low-level, only performed if MapCanvas is visible

        isVisible = self.visibleRegion().boundingRect().isValid() and self.isVisible()

        if not isVisible:
            self.mRefreshScheduled = True
        else:
            mLyrs = self.layers()
            vLyrs = self.mLayerModel.visibleLayers()
            if mLyrs != vLyrs:
                self.setLayers(vLyrs)
            if self.renderFlag() or force:
                super(MapCanvas, self).refresh()



        ##self.checkRenderFlag()
        #if self.renderFlag() or force:
        #    self.setLayers(self.mLayerModel.visibleLayers())
        #    super(MapCanvas, self).refresh()

            #self.refreshAllLayers()


    def setCrosshairStyle(self,crosshairStyle):
        from timeseriesviewer.crosshair import CrosshairStyle
        if crosshairStyle is None:
            self.crosshairItem.crosshairStyle.setShow(False)
            self.crosshairItem.update()
        else:
            assert isinstance(crosshairStyle, CrosshairStyle)
            self.crosshairItem.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self,b):
        self.crosshairItem.setShow(b)


    def checkRenderFlag(self):
        """
        Controls the MapCanvas Render flag to decide if rendering is required
        :return:
        """
        wasVisible = self.mWasVisible
        isVisible = self.visibleRegion().boundingRect().isValid() \
                  and self.isVisible()
        if not isVisible:
            self.setRenderFlag(False)
            self.mWasVisible = False
            #will stop active render jobs

        else:
            #the canvas is visible, but is a new rendering required?
            lastSummary = self.mMapSummary
            self.mMapSummary = self.mapSummary()
            #isRequired = (wasVisible == False) or self.renderFlag() or self.mDataRefreshed
            #print(lastSummary)
            #print(self.mMapSummary)
            isRequired = lastSummary != self.mapSummary()
            self.mWasVisible = True
            if isRequired:
                self.setRenderFlag(True)
                #self.mMapSummary = self.mapSummary()
            else:
                self.setRenderFlag(False)


    def layerPaths(self):
        return [str(l.source()) for l in self.layers()]

    def pixmap(self):
        """
        Returns the current map image as pixmap
        :return: QPixmap
        """
        #return QPixmap(self.map().contentImage().copy())
        return QPixmap.grabWidget(self)



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

        action.triggered.connect(lambda : self.setCrosshairStyle(
                CrosshairDialog.getCrosshairStyle(parent=self,
                                                  mapCanvas=self,
                                                  crosshairStyle=self.crosshairItem.crosshairStyle)
                ))

        if self.crosshairItem.crosshairStyle.mShow:
            action = menu.addAction('Hide crosshair')
            action.triggered.connect(lambda : self.setShowCrosshair(False))
        else:
            action = menu.addAction('Show crosshair')
            action.triggered.connect(lambda: self.setShowCrosshair(True))

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
                    #lqgis = QgsRasterLayer(l.source(), l.name(), l.providerType(), False)
                    lqgis.setRenderer(l.renderer().clone())
                    #grpNode.addLayer(lqgis)
                if isinstance(l, QgsVectorLayer):
                    lqgis = iface.addVectorLayer(l.source(), l.name(), 'ogr')
                    #lqgis = QgsVectorLayer(l.source(), l.name(), 'ogr', False)
                    lqgis.setRendererV2(l.renderer().clone())
                    #grpNode.addLayer(lqgis)

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



    def spatialExtent(self):
        return SpatialExtent.fromMapCanvas(self)

    def spatialExtentHint(self):
        crs = self.crs()
        ext = SpatialExtent.world()
        for lyr in self.mLayerModel.layers()+ self.layers():
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


def exampleSyncedCanvases():
    global btnCrs, mapCanvases, lyrs, syncExtents
    import site, sys
    # add site-packages to sys.path as done by enmapboxplugin.py
    from timeseriesviewer import sandbox
    from timeseriesviewer.utils import SpatialExtent
    import example.Images
    qgsApp = sandbox.initQgisEnvironment()
    w = QWidget()
    hl1 = QHBoxLayout()
    hl2 = QHBoxLayout()
    btnCrs = QgsProjectionSelectionWidget(w)
    btnRefresh = QPushButton('Refresh', w)
    hl1.addWidget(btnCrs)
    hl1.addWidget(btnRefresh)
    vl = QVBoxLayout()
    vl.addLayout(hl1)
    vl.addLayout(hl2)
    w.setLayout(vl)
    files = [example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA,
             example.Images.Img_2013_05_20_LC82270652013140LGN01_BOA,
             example.Images.Img_2013_08_16_LE72270652013228CUB00_BOA]
    mapCanvases = []
    lyrs = []

    def onRefresh(*args):

        crs = btnCrs.crs()
        ext = SpatialExtent.fromLayer(lyrs[0]).toCrs(crs)
        for mapCanvas in mapCanvases:
            mapCanvas.setCrs(crs)
            mapCanvas.setSpatialExtent(ext)
            mapCanvas.refresh()
            mapCanvas.refreshAllLayers()

    def syncExtents(ext):

        for mapCanvas in mapCanvases:

            oldext = SpatialExtent.fromMapCanvas(mapCanvas)
            if oldext != ext:
                mapCanvas.blockSignals(True)
                #mapCanvas.setExtent(ext)
                mapCanvas.setSpatialExtent(ext)
                mapCanvas.blockSignals(False)
                mapCanvas.refreshAllLayers()

    def registerMapCanvas(mapCanvas):
        mapCanvas.extentsChanged.connect(lambda: syncExtents(SpatialExtent.fromMapCanvas(mapCanvas)))

    for i, f in enumerate(files):
        ml = QgsRasterLayer(f)
        #QgsProject.instance().addMapLayer(ml)
        lyrs.append(ml)

        #mapCanvas = QgsMapCanvas(w)
        mapCanvas = MapCanvas(w)

        registerMapCanvas(mapCanvas)
        hl2.addWidget(mapCanvas)
        #mapCanvas.setLayers([QgsMapCanvasLayer(ml)])
        mapCanvas.setLayers([ml])

        if i == 0:
            btnCrs.setCrs(ml.crs())
        mapCanvases.append(mapCanvas)

        btnCrs.crsChanged.connect(onRefresh)
        btnRefresh.clicked.connect(onRefresh)
    w.show()
    onRefresh()
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    from timeseriesviewer import utils
    from timeseriesviewer.mapcanvas import MapCanvas
    from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
    from example import  exampleEvents
    qgsApp = utils.initQgisApplication()



    def printTimeDelta(dt):
        print(dt)
    c = MapCanvas()
    #c.activateMapTool('identifySpectralProfile')
    #c.activateMapTool('identifyTemporalProfile')
    #c.activateMapTool('identifyCursorLocationValues')
    c.activateMapTool('moveCenter')

    c.sigDataLoadingFinished.connect(printTimeDelta)
    c.show()
    lyr1 = QgsRasterLayer(Img_2014_01_15_LC82270652014015LGN00_BOA)
    lyr2 = QgsVectorLayer(exampleEvents, 'events', 'ogr')

    c.layerModel().addLayerInfo(lyr2)
    c.layerModel().addLayerInfo(lyr1)

    for l in c.layerModel().visibleLayers():
        print(l)

    c.setDestinationCrs(lyr1.crs())
    c.setExtent(lyr1.extent())
    c.setCrs(QgsCoordinateReferenceSystem('EPSG:32632'))
    c.setExtent(c.spatialExtentHint())


    c.refresh()
    qgsApp.exec_()