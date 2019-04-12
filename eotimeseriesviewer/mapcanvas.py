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
from eotimeseriesviewer import CursorLocationMapTool
from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtXml import QDomDocument



from .timeseries import TimeSeriesDatum, SensorProxyLayer, SensorInstrument
from .externals.qps.crosshair.crosshair import CrosshairDialog, CrosshairStyle, CrosshairMapCanvasItem
from .externals.qps.maptools import *
from .labeling import LabelAttributeTableModel, labelShortcutLayers, layerClassSchemes, applyShortcutsToRegisteredLayers
from .externals.qps.classification.classificationscheme import ClassificationScheme, ClassInfo
from .externals.qps.utils import *
from .externals.qps.layerproperties import showLayerPropertiesDialog
import eotimeseriesviewer.settings


def toQgsMimeDataUtilsUri(mapLayer:QgsMapLayer):

    uri = QgsMimeDataUtils.Uri()
    uri.name = mapLayer.name()
    uri.providerKey = mapLayer.dataProvider().name()
    uri.uri = mapLayer.source()
    if isinstance(mapLayer, QgsRasterLayer):
        uri.layerType = 'raster'
    elif isinstance(mapLayer, QgsVectorLayer):
        uri.layerType = 'vector'
    else:
        raise NotImplementedError()
    return uri

class MapCanvasInfoItem(QgsMapCanvasItem):

    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(MapCanvasInfoItem, self).__init__(mapCanvas)
        self.mCanvas = mapCanvas

        self.mULText = None
        self.mLRText = None
        self.mURText = None

        self.mVisibility = True

    def setVisibility(self, b:bool):
        """
        Sets the visibility of a Crosshair
        :param b:
        :return:
        """
        assert isinstance(b, bool)
        old = self.mShow
        self.mVisibility = b
        if old != b:
            self.mCanvas.update()

    def visibility(self)->bool:
        """Returns the Crosshair visibility"""
        return self.mVisibility

    def paintText(self, painter, text:str, position):
        pen = QPen(Qt.SolidLine)
        pen.setWidth(self.mCrosshairStyle.mThickness)
        pen.setColor(self.mCrosshairStyle.mColor)

        nLines = len(text.splitlines())

        font = QFont('Courier', pointSize=10)
        brush = self.mCanvas.backgroundBrush()
        c = brush.color()
        c.setAlpha(170)
        brush.setColor(c)
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)
        fm = QFontMetrics(font)
        #background = QPolygonF(QRectF(backGroundPos, backGroundSize))
        #painter.drawPolygon(background)
        painter.setPen(pen)
        painter.drawText(position, text)
        painter.setFont(QFont('Courier', pointSize=10))

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
            """
            Paints the crosshair
            :param painter:
            :param QStyleOptionGraphicsItem:
            :param QWidget_widget:
            :return:
            """
            if self.mLRText:
                self.paintText(painter, self.mLRText, QPoint(0, 0))


class MapCanvas(QgsMapCanvas):
    """
    A widget based on QgsMapCanvas to draw spatial data
    """
    class Command(enum.Enum):
        """
        Canvas specific commands
        """
        RefreshRenderer = 1
        Clear = 3
        UpdateLayers = 4


    saveFileDirectories = dict()
    sigShowProfiles = pyqtSignal(SpatialPoint, str)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigChangeDVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeMVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeSVRequest = pyqtSignal(QgsMapCanvas, QgsRasterRenderer)
    sigMapRefreshed = pyqtSignal([float, float], [float])

    sigCrosshairPositionChanged = pyqtSignal(SpatialPoint)
    sigCrosshairVisibilityChanged = pyqtSignal(bool)

    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)
        self.mMapLayerStore = QgsProject.instance()
        self.mMapLayers = []

        self.mTimedRefreshPipeLine = dict()

        self.mCrosshairItem = CrosshairMapCanvasItem(self)
        self.mInfoItem = MapCanvasInfoItem(self)

        self.mTSD = self.mMapView = None

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
        bg = eotimeseriesviewer.settings.value(eotimeseriesviewer.settings.Keys.MapBackgroundColor, default=QColor(0, 0, 0))
        self.setCanvasColor(bg)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))



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
        from eotimeseriesviewer.mapvisualization import MapView

        assert isinstance(mapView, MapView)
        self.mMapView = mapView

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
        tsd.sensor().sigNameChanged.connect(lambda name: scope.setVariable('map_sensor', name))


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


    def addToRefreshPipeLine(self, arguments: list):
        """
        Adds commands or other arguments to a pipeline which will be handled during the next timed refresh.
        :param arguments: argument | [list-of-arguments]
        """
        if not isinstance(arguments, list):
            arguments = [arguments]
        for a in arguments:
            if isinstance(a, SpatialExtent):
                self.mTimedRefreshPipeLine[SpatialExtent] = a
            elif isinstance(a, SpatialPoint):
                self.mTimedRefreshPipeLine[SpatialExtent] = a
            elif isinstance(a, MapCanvas.Command):
                if not MapCanvas.Command in self.mTimedRefreshPipeLine.keys():
                    self.mTimedRefreshPipeLine[MapCanvas.Command] = []
                # remove previous commands of same type, append command to end
                while a in self.mTimedRefreshPipeLine[MapCanvas.Command]:
                    self.mTimedRefreshPipeLine[MapCanvas.Command].remove(a)
                self.mTimedRefreshPipeLine[MapCanvas.Command].append(a)
            else:
                raise NotImplementedError('Unsupported argument: {}'.format(str(a)))


    def timedRefresh(self):
        """
        Called to refresh the map canvas with all things needed to be done with lazy evaluation
        """
        expected = []

        existing = self.layers()
        existingSources = [l.source() for l in existing]

        for lyr in self.mMapView.layers():
            assert isinstance(lyr, QgsMapLayer)

            if isinstance(lyr, SensorProxyLayer):
                if self.tsd().sensor() == lyr.sensor():
                    for source in self.tsd().sourceUris():
                        sourceLayer = None

                        if source in existingSources:
                            sourceLayer = existing[existingSources.index(source)]
                        else:
                            sourceLayer = SensorProxyLayer(source, sensor=self.tsd().sensor())
                            sourceLayer.setName(lyr.name())
                            sourceLayer.setCustomProperty('eotsv/sensorid', self.tsd().sensor().id())
                            renderer = lyr.renderer().clone()
                            sourceLayer.setRenderer(renderer)
                        assert isinstance(sourceLayer, QgsRasterLayer)
                        expected.append(sourceLayer)
                else:
                    # skip any other SensorProxyLayer that relates to another sensor
                    pass
            else:
                expected.append(lyr)

        if len(self.mTimedRefreshPipeLine) == 0 and self.layers() == expected:
            # there is nothing to do.
            return
        else:
            self.freeze(True)
            # look for new layers

            lyrs = self.layers()
            if lyrs != expected:
                self.setLayers(expected)

            if True:
                # set sources first
                keys = self.mTimedRefreshPipeLine.keys()

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
                            for px in [px for px in self.mMapView.layers() if isinstance(px, SensorProxyLayer)]:
                                for l in self.layers():
                                    if isinstance(l, SensorProxyLayer) and l.sensor() == px.sensor():
                                        renderer = px.renderer().clone()
                                        renderer.setInput(l.dataProvider())
                                        l.setRenderer(renderer)

                            pass


                self.mTimedRefreshPipeLine.clear()

            self.freeze(False)
            self.refresh()
            # is this really required?


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
        from eotimeseriesviewer import CrosshairStyle
        if crosshairStyle is None:
            self.mCrosshairItem.crosshairStyle.setShow(False)
            self.mCrosshairItem.update()
        else:
            assert isinstance(crosshairStyle, CrosshairStyle)
            self.mCrosshairItem.setCrosshairStyle(crosshairStyle)

        if emitSignal:
            self.sigCrosshairStyleChanged.emit(self.mCrosshairItem.crosshairStyle())

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

    def contextMenu(self, pos:QPoint)->QMenu:
        """
        Create the MapCanvas context menu with options relevant for pixel position ``pos``.
        :param pos: QPoint
        :return: QMenu
        """
        mapSettings = self.mapSettings()
        assert isinstance(mapSettings, QgsMapSettings)

        pointGeo = mapSettings.mapToPixel().toMapCoordinates(pos.x(), pos.y())
        assert isinstance(pointGeo, QgsPointXY)

        tsd = self.tsd()



        menu = QMenu()

        m = menu.addMenu('Optimize raster stretches...')
        action = m.addAction('Linear')
        action.triggered.connect(lambda: self.stretchToExtent(self.spatialExtent(), 'linear_minmax', p=0.0))

        action = m.addAction('Linear 5%')
        action.triggered.connect(lambda: self.stretchToExtent(self.spatialExtent(), 'linear_minmax', p=0.05))

        action = m.addAction('Gaussian')
        action.triggered.connect(lambda: self.stretchToExtent(self.spatialExtent(), 'gaussian', n=3))

        menu.addSeparator()

        m = menu.addMenu('Layers...')
        for mapLayer in self.layers():
            sub = m.addMenu(mapLayer.name())

            if isinstance(mapLayer, SensorProxyLayer):
                sub.setIcon(QIcon(':/timeseriesviewer/icons/icon.svg'))
            elif isinstance(mapLayer, QgsRasterLayer):
                sub.setIcon(QIcon(''))
            elif isinstance(mapLayer, QgsVectorLayer):
                wkbType = QgsWkbTypes.displayString(int(mapLayer.wkbType()))
                if re.search('polygon', wkbType, re.I):
                    sub.setIcon(QIcon(r':/images/themes/default/mIconPolygonLayer.svg'))
                elif re.search('line', wkbType, re.I):
                    sub.setIcon(QIcon(r':/images/themes/default/mIconLineLayer.svg'))
                elif re.search('point', wkbType, re.I):
                    sub.setIcon(QIcon(r':/images/themes/default/mIconPointLayer.svg'))

            a = sub.addAction('Properties...')
            a.triggered.connect(lambda *args, lyr=mapLayer: showLayerPropertiesDialog(lyr, self))

            a = sub.addAction('Zoom to Layer')
            a.setIcon(QIcon(':/images/themes/default/mActionZoomToLayer.svg'))
            a.triggered.connect(lambda *args, lyr=mapLayer: self.setSpatialExtent(SpatialExtent.fromLayer(lyr)))

        menu.addSeparator()

        action = menu.addAction('Zoom to full extent')
        action.setIcon(QIcon(':/images/themes/default/mActionZoomFullExtent.svg'))
        action.triggered.connect(lambda: self.setExtent(self.fullExtent()))

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

        menu.addSeparator()

        m = menu.addMenu('Label...')

        labelLayers = labelShortcutLayers()
        hasShortcutLayers = len(labelLayers) > 0
        lyrWithSelectedFeaturs = [l for l in labelLayers if len(l.selectedFeatureIds()) > 0]
        hasSelectedFeaturs = len(lyrWithSelectedFeaturs) > 0


        a = m.addAction('Time & sensor')
        a.setEnabled(hasShortcutLayers)
        if isinstance(self.tsd(), TimeSeriesDatum):
            a.setToolTip('Write time and sensor attribute related to {}.'.format(self.tsd().date()))

        classSchemes = []
        for layer in lyrWithSelectedFeaturs:
            for classScheme in layerClassSchemes(layer):
                assert isinstance(classScheme, ClassificationScheme)
                if classScheme in classSchemes:
                    continue

                classMenu = m.addMenu('Classification "{}"'.format(classScheme.name()))
                assert isinstance(classMenu, QMenu)
                for classInfo in classScheme:
                    assert isinstance(classInfo, ClassInfo)
                    a = classMenu.addAction(classInfo.name())
                    a.setIcon(classInfo.icon())
                    a.setToolTip('Write "{}" or "{}" to connected vector field attributes'.format(classInfo.name(), classInfo.value()))

                    a.triggered.connect(
                        lambda tsd=self.tsd(), ci = classInfo:
                        applyShortcutsToRegisteredLayers(tsd, [ci]))
                classSchemes.append(classScheme)

        """
            
            menu.addSeparator()
            
            from eotimeseriesviewer.utils import qgisInstance
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
            
        """

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

    def contextMenuEvent(self, event:QContextMenuEvent):
        """
        Create and shows the MapCanvas context menu.
        :param event: QEvent
        """
        assert isinstance(event, QContextMenuEvent)
        menu = self.contextMenu(event.pos())
        menu.exec_(event.globalPos())

    def addLayers2QGIS(self, mapLayers):
        from eotimeseriesviewer.utils import qgisInstance
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
            if isinstance(l, SensorProxyLayer):
                r = l.renderer()
                dp = l.dataProvider()
                newRenderer = None
                extent = spatialExtent.toCrs(l.crs())

                assert isinstance(dp, QgsRasterDataProvider)

                def getCE(band):
                    stats = dp.bandStatistics(band, QgsRasterBandStats.All, extent, 500)

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

                    newRenderer = r.clone()

                    ceR = getCE(r.redBand())
                    ceG = getCE(r.greenBand())
                    ceB = getCE(r.blueBand())

                    newRenderer.setRedContrastEnhancement(ceR)
                    newRenderer.setGreenContrastEnhancement(ceG)
                    newRenderer.setBlueContrastEnhancement(ceB)

                elif isinstance(r, QgsSingleBandPseudoColorRenderer):
                    newRenderer = r.clone()
                    ce = getCE(newRenderer.band())

                    # stats = dp.bandStatistics(newRenderer.band(), QgsRasterBandStats.All, extent, 500)

                    shader = newRenderer.shader()
                    newRenderer.setClassificationMax(ce.maximumValue())
                    newRenderer.setClassificationMin(ce.minimumValue())
                    shader.setMaximumValue(ce.maximumValue())
                    shader.setMinimumValue(ce.minimumValue())
                elif isinstance(r, QgsSingleBandGrayRenderer):
                    newRenderer = r.clone()
                    ce = getCE(newRenderer.grayBand())
                    newRenderer.setContrastEnhancement(ce)

                elif isinstance(r, QgsPalettedRasterRenderer):
                    newRenderer = r.clone()

                if newRenderer is not None:
                    self.mMapView.sensorProxyLayer(l.sensor()).setRenderer(newRenderer)

                    return
        s = ""


    def saveMapImageDialog(self, fileType):
        """
        Opens a dialog to save the map as local file
        :param fileType:
        :return:
        """
        import eotimeseriesviewer.settings
        lastDir = eotimeseriesviewer.settings.value(eotimeseriesviewer.settings.Keys.ScreenShotDirectory, os.path.expanduser('~'))
        from eotimeseriesviewer.utils import filenameFromString
        from eotimeseriesviewer.mapvisualization import MapView
        if isinstance(self.mTSD, TimeSeriesDatum) and isinstance(self.mMapView, MapView):
            path = filenameFromString('{}.{}'.format(self.mTSD.date(), self.mMapView.title()))
        else:
            path = 'mapcanvas'
        path = jp(lastDir, '{}.{}'.format(path, fileType.lower()))
        path, _ = QFileDialog.getSaveFileName(self, 'Save map as {}'.format(fileType), path)
        if len(path) > 0:
            self.saveAsImage(path, None, fileType)
            eotimeseriesviewer.settings.setValue(eotimeseriesviewer.settings.Keys.ScreenShotDirectory, os.path.dirname(path))

    def setSpatialExtent(self, spatialExtent: SpatialExtent):
        """
        Sets the SpatialExtent to be shown.
        :param spatialExtent: SpatialExtent
        """
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            spatialExtent = spatialExtent.toCrs(self.crs())
            self.setExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint: SpatialPoint):
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

