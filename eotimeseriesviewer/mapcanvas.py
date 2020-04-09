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

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import QDomDocument



from .timeseries import TimeSeriesDate, TimeSeriesSource, SensorProxyLayer, SensorInstrument
from .externals.qps.crosshair.crosshair import CrosshairDialog, CrosshairStyle, CrosshairMapCanvasItem
from .externals.qps.maptools import *
from .labeling import quickLabelLayers, labelShortcutLayerClassificationSchemes, setQuickTSDLabelsForRegisteredLayers
from .externals.qps.classification.classificationscheme import ClassificationScheme, ClassInfo
from .externals.qps.utils import *
from .externals.qps.layerproperties import showLayerPropertiesDialog
import eotimeseriesviewer.settings

PROGRESS_TIMER = QTimer()
PROGRESS_TIMER.start(100)

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

class MapLoadingInfoItem(QgsMapCanvasItem):

    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(MapLoadingInfoItem, self).__init__(mapCanvas)
        self.mCanvas = mapCanvas
        self.mProgressConnection = None

        self.mCanvas.renderStarting.connect(lambda: self.showLoadingProgress(True))
        #self.mCanvas.renderComplete.connect(lambda: self.showLoadingProgress(False))

        PROGRESS_TIMER.timeout.connect(self.onProgressTimeOut)
        self.mShowProgress = False
        self.mIsVisible = True

    def showLoadingProgress(self, showProgress: bool):
        self.mShowProgress = showProgress
        self.update()

    def onProgressTimeOut(self):

        if self.mShowProgress:
            self.mCanvas.update()

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
            """
            Paints the crosshair
            :param painter:
            :param QStyleOptionGraphicsItem:
            :param QWidget_widget:
            :return:
            """
            if False and self.mShowProgress:

                if True:
                    options = QStyleOptionProgressBar()
                    options.rect = QRect(0, 0, painter.window().width(), 25)
                    options.textAlignment = Qt.AlignCenter
                    options.progress = 0
                    options.maximum = 0
                    options.minimum = 0
                    QApplication.style().drawControl(QStyle.CE_ProgressBar, options, painter)

class MapCanvasInfoItem(QgsMapCanvasItem):
    """
    A QgsMapCanvasItem to show text
    """
    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(MapCanvasInfoItem, self).__init__(mapCanvas)
        self.mCanvas = mapCanvas

        self.mText = dict()
        self.mWrapChar = '\n'
        self.mTextFormat = QgsTextFormat()
        self.mTextFormat.setSizeUnit(QgsUnitTypes.RenderPixels)
        self.mTextFormat.setFont(QFont('Helvetica', pointSize=10))
        self.mTextFormat.setColor(QColor('yellow'))

    def setWrapChar(self, c:str) -> str:
        """
        Sets a Wrap Character
        :param c:
        :return:
        """
        self.mWrapChar = c
        return self.wrapChar()

    def wrapChar(self) -> str:
        return self.mWrapChar

    def setText(self, text:str, alignment:Qt.Alignment=Qt.AlignTop | Qt.AlignHCenter):

        self.mText[alignment] = text


    def setTextFormat(self, format:QgsTextFormat):
        assert isinstance(format, QgsTextFormat)
        self.mTextFormat = format
        self.updateCanvas()

    def textFormat(self) -> QgsTextFormat:
        """
        Returns the text format.
        :return: QgsTextFormat
        """
        return self.mTextFormat

    def font(self) -> QFont:
        """
        Returns the font used to write text on the map canvas.
        :return: QFont
        """
        return self.mTextFormat.font()

    def setFont(self, font:QFont):
        self.mTextFormat.setFont(font)

    def setColor(self, color:QColor):
        """
        Sets the map info color
        :param color: QColor
        """
        self.mTextFormat.setColor(color)

    def color(self) -> QColor:
        """
        Returns the info text color
        :return: QColor
        """
        return self.mTextFormat.color()

    def paintText(self, painter, text:str, flags, rotation=0):
        padding = 5
        text = text.replace('\\n', '\n')
        text = text.split(self.wrapChar())

        nl = len(text)
        #text = text.split('\\n')
        r = QgsTextRenderer()

        painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing)

        context = QgsRenderContext()

        # taken from QGIS Repo src/core/qgspallabeling.cpp
        m2p = QgsMapToPixel(1, 0, 0, 0, 0, 0)
        context.setMapToPixel(m2p)
        context.setScaleFactor(QgsApplication.desktop().logicalDpiX() / 25.4)
        context.setUseAdvancedEffects(True)
        context.setPainter(painter)
        #context.setExtent(self.mCanvas.extent())
        #context.setExpressionContext(self.mCanvas.mapSettings().expressionContext())

        vp = QRectF(painter.viewport())
        #rect = self.mCanvas.extent().toRectF()

        textFormat = self.mTextFormat
        assert isinstance(textFormat, QgsTextFormat)
        th = r.textHeight(context, textFormat, text,  QgsTextRenderer.Rect)
        tw = r.textWidth(context, textFormat, text)

        # area to place the text inside
        rect = QRectF()
        x = 0.5*vp.width()
        y = 0.5*vp.height()
        hAlign = QgsTextRenderer.AlignCenter

        # horizontal position
        if bool(flags & Qt.AlignLeft):
            x = padding
            hAlign = QgsTextRenderer.AlignLeft

        elif bool(flags & Qt.AlignHCenter):
            x = 0.5 * vp.width()
            hAlign = QgsTextRenderer.AlignCenter

        elif bool(flags & Qt.AlignRight):
            x = vp.width() - padding
            hAlign = QgsTextRenderer.AlignRight

        # vertical position
        if bool(flags & Qt.AlignTop):
            y = padding + th - 0.5* (th / nl)

        elif bool(flags & Qt.AlignVCenter):
            y = 0.5 * (vp.height() + th)

        elif bool(flags & Qt.AlignBottom):
            y = vp.height() - padding #- th

        poo = QPointF(x, y)
        r.drawText(poo, rotation, hAlign, text, context, textFormat)

    def setUpperLeft(self, text:str):
        self.setText(text, Qt.AlignTop | Qt.AlignLeft)

    def setMiddleLeft(self, text: str):
        self.setText(text, Qt.AlignVCenter | Qt.AlignLeft)

    def setLowerLeft(self, text: str):
        self.setText(text, Qt.AlignBottom | Qt.AlignLeft)


    def setUpperCenter(self, text:str):
        self.setText(text, Qt.AlignTop | Qt.AlignHCenter)

    def setMiddleCenter(self, text: str):
        self.setText(text, Qt.AlignVCenter | Qt.AlignHCenter)

    def setLowerCenter(self, text: str):
        self.setText(text, Qt.AlignBottom | Qt.AlignHCenter)

    def setUpperRight(self, text:str):
        self.setText(text, Qt.AlignTop | Qt.AlignRight)

    def setMiddleRight(self, text: str):
        self.setText(text, Qt.AlignVCenter | Qt.AlignRight)

    def setLowerRight(self, text: str):
        self.setText(text, Qt.AlignBottom | Qt.AlignRight)

    def clearText(self):
        self.mText.clear()

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
            """
            Paints the crosshair
            :param painter:
            :param QStyleOptionGraphicsItem:
            :param QWidget_widget:
            :return:
            """
            for alignment, text in self.mText.items():
                if isinstance(text, str) and len(text) > 0:
                    self.paintText(painter, text, alignment)

class MapCanvasMapTools(QObject):


    def __init__(self, canvas:QgsMapCanvas, cadDock:QgsAdvancedDigitizingDockWidget):

        super(MapCanvasMapTools, self).__init__(canvas)
        self.mCanvas = canvas
        self.mCadDock = cadDock

        self.mtZoomIn = QgsMapToolZoom(canvas, False)
        self.mtZoomOut = QgsMapToolZoom(canvas, True)
        self.mtMoveToCenter = MapToolCenter(canvas)
        self.mtPan = QgsMapToolPan(canvas)
        self.mtPixelScaleExtent = PixelScaleExtentMapTool(canvas)
        self.mtFullExtentMapTool = FullExtentMapTool(canvas)
        self.mtCursorLocation = CursorLocationMapTool(canvas, True)

        self.mtAddFeature = QgsMapToolAddFeature(canvas, QgsMapToolCapture.CaptureNone, cadDock)
        self.mtSelectFeature = QgsMapToolSelect(canvas)

    def activate(self, mapToolKey, **kwds):
        from .externals.qps.maptools import MapTools

        if mapToolKey == MapTools.ZoomIn:
            self.mCanvas.setMapTool(self.mtZoomIn)
        elif mapToolKey == MapTools.ZoomOut:
            self.mCanvas.setMapTool(self.mtZoomOut)
        elif mapToolKey == MapTools.Pan:
            self.mCanvas.setMapTool(self.mtPan)
        elif mapToolKey == MapTools.ZoomFull:
            self.mCanvas.setMapTool(self.mtFullExtentMapTool)
        elif mapToolKey == MapTools.ZoomPixelScale:
            self.mCanvas.setMapTool(self.mtPixelScaleExtent)
        elif mapToolKey == MapTools.CursorLocation:
            self.mCanvas.setMapTool(self.mtCursorLocation)
        elif mapToolKey == MapTools.SpectralProfile:
            pass
        elif mapToolKey == MapTools.TemporalProfile:
            pass
        elif mapToolKey == MapTools.MoveToCenter:
            self.mCanvas.setMapTool(self.mtMoveToCenter)
        elif mapToolKey == MapTools.AddFeature:
            self.mCanvas.setMapTool(self.mtAddFeature)
        elif mapToolKey == MapTools.SelectFeature:
            self.mCanvas.setMapTool(self.mtSelectFeature)
            self.mtSelectFeature.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        elif mapToolKey == MapTools.SelectFeatureByPolygon:
            self.mCanvas.setMapTool(self.mtSelectFeature)
            self.mtSelectFeature.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectPolygon)
        elif mapToolKey == MapTools.SelectFeatureByFreehand:
            self.mCanvas.setMapTool(self.mtSelectFeature)
            self.mtSelectFeature.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectFreehand)
        elif mapToolKey == MapTools.SelectFeatureByRadius:
            self.mCanvas.setMapTool(self.mtSelectFeature)
            self.mtSelectFeature.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        else:
            print('Unknown MapTool key: {}'.format(mapToolKey))

        # if undefined, set a current vector layer
        if mapToolKey in [MapTools.SelectFeature, MapTools.SelectFeatureByPolygon, MapTools.SelectFeatureByRadius, MapTools.SelectFeatureByFreehand] \
                and self.mCanvas.currentLayer() is None:
            for vl in self.mCanvas.layers():
                if isinstance(vl, QgsVectorLayer):
                    self.mCanvas.setCurrentLayer(vl)
                    break


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
        UpdateMapItems = 5



    saveFileDirectories = dict()
    #sigShowProfiles = pyqtSignal(SpatialPoint, str)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    #sigChangeDVRequest = pyqtSignal(QgsMapCanvas, str)
    #sigChangeMVRequest = pyqtSignal(QgsMapCanvas, str)
    #sigChangeSVRequest = pyqtSignal(QgsMapCanvas, QgsRasterRenderer)
    sigMapRefreshed = pyqtSignal([float, float], [float])

    sigCrosshairPositionChanged = pyqtSignal(SpatialPoint)
    sigCrosshairVisibilityChanged = pyqtSignal(bool)
    sigDestinationCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)
        self.mMapLayerStore = QgsProject.instance()
        self.mMapLayers = []

        self.mMapTools = None
        self.initMapTools()

        self.mTimedRefreshPipeLine = dict()

        self.mCrosshairItem = CrosshairMapCanvasItem(self)
        self.mInfoItem = MapCanvasInfoItem(self)
        self.mProgressItem = MapLoadingInfoItem(self)

        self.mTSD = self.mMapView = None

        self.mUserInputWidget = QgsUserInputWidget(self)
        self.mUserInputWidget.setObjectName('UserInputDockWidget')
        self.mUserInputWidget.setAnchorWidget(self)
        self.mUserInputWidget.setAnchorWidgetPoint(QgsFloatingWidget.TopRight)
        self.mUserInputWidget.setAnchorPoint(QgsFloatingWidget.TopRight)

        #self.mProgressBar = QProgressBar()
        #self.mUserInputWidget.addUserInputWidget(self.mProgressBar)

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

        self.destinationCrsChanged.connect(lambda : self.sigDestinationCrsChanged.emit(self.crs()))

    def userInputWidget(self) -> QgsUserInputWidget:
        """
        Returns the mapcanvas QgsUserInputWidget
        :return: QgsUserInputWidget
        """
        return self.mUserInputWidget


    def infoItem(self) -> MapCanvasInfoItem:
        """
        Returns the MapCanvasInfoItem, e.g. to plot text on top of the map canvas
        :return: MapCanvasInfoItem
        """
        return self.mInfoItem

    def mapView(self):
        """
        Returns the MapView this MapCanvas is linked to
        :return:
        """
        return self.mMapView

    def mapTools(self) -> MapCanvasMapTools:
        """
        Returns the map tools of this MapCanvas
        :return: MapCanvasMapTools
        """
        return self.mMapTools

    def initMapTools(self):

        self.mCadDock = QgsAdvancedDigitizingDockWidget(self)
        self.mCadDock.setVisible(False)
        self.mMapTools = MapCanvasMapTools(self, self.mCadDock)

    def setMapLayerStore(self, store):
        """
        Sets the QgsMapLayerStore or QgsProject instance that is used to register map layers
        :param store: QgsMapLayerStore | QgsProject
        """
        assert isinstance(store, (QgsMapLayerStore, QgsProject))
        self.mMapLayerStore = store

    def renderingFinished(self) -> bool:
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
        """
        Sets the map canvas MapView
        :param mapView: MapView
        """
        from eotimeseriesviewer.mapvisualization import MapView

        assert isinstance(mapView, MapView)

        self.mMapView = mapView
        self.mInfoItem.setTextFormat(mapView.mapTextFormat())
        self.addToRefreshPipeLine(mapView.mapBackgroundColor())
        self.addToRefreshPipeLine(MapCanvas.Command.UpdateMapItems)

    def setTSD(self, tsd:TimeSeriesDate):
        """
        Sets the TimeSeriesDate this map-canvas is linked to
        :param tsd:
        :return:
        """
        if self.mTSD == tsd:
            return

        # disconnect old TSD
        if isinstance(self.mTSD, TimeSeriesDate):
            self.mTSD.sensor().sigNameChanged.disconnect(self.updateScope)

        self.mTSD = tsd

        if isinstance(tsd, TimeSeriesDate):
            self.mTSD.sensor().sigNameChanged.connect(self.updateScope)

        self.updateScope()


    def updateScope(self):
        """
        Updates map-canvas TSD variables
        """
        from .mapvisualization import MapView
        from .main import EOTimeSeriesViewer


        varMVNumber = None
        varMVName = None
        varDate = None
        varDOY = None
        varSensor = None


        tsd = self.tsd()
        if isinstance(tsd, TimeSeriesDate):
            varDate = str(tsd.date())
            varDOY = tsd.doy()
            varSensor = tsd.sensor().name()

        mv = self.mapView()
        if isinstance(mv, MapView):
            varMVName = mv.name()
            if isinstance(EOTimeSeriesViewer.instance(), EOTimeSeriesViewer):
                mapViews = EOTimeSeriesViewer.instance().mapViews()
                if mv in mapViews:
                    varMVNumber = mapViews.index(mv) + 1

        scope = self.expressionContextScope()
        scope.setVariable('map_view_num', varMVNumber, isStatic=False)
        scope.setVariable('map_view', varMVName, isStatic=False)
        scope.setVariable('map_date', varDate, isStatic=False)
        scope.setVariable('map_doy', varDOY, isStatic=False)
        scope.setVariable('map_sensor', varSensor, isStatic=False)

    def tsd(self) -> TimeSeriesDate:
        """
        Returns the TimeSeriesDate
        :return: TimeSeriesDate
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

    def crs(self) -> QgsCoordinateReferenceSystem:
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


    def isRefreshing(self) -> bool:
        return self.mIsRefreshing

    def isVisibleToViewport(self) -> bool:
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
                self.mTimedRefreshPipeLine[SpatialPoint] = a

            elif isinstance(a, QColor):
                self.mTimedRefreshPipeLine[QColor] = a

            elif isinstance(a, MapCanvas.Command):
                if not MapCanvas.Command in self.mTimedRefreshPipeLine.keys():
                    self.mTimedRefreshPipeLine[MapCanvas.Command] = []
                # remove previous commands of same type, append command to end
                while a in self.mTimedRefreshPipeLine[MapCanvas.Command]:
                    self.mTimedRefreshPipeLine[MapCanvas.Command].remove(a)
                self.mTimedRefreshPipeLine[MapCanvas.Command].append(a)

            else:
                print('Unsupported argument: {} {}'.format(type(a), str(a)), file=sys.stderr)

    def timedRefresh(self):
        """
        Called to refresh the map canvas with all things needed to be done with lazy evaluation
        """
        expected = []

        existing = self.layers()
        existingSources = [l.source() for l in existing]

        if self.mapView() is None or self.tsd() is None:
            self.setLayers([])
            self.mInfoItem.clearText()
            self.update()
            return

        for lyr in self.mMapView.layers():
            assert isinstance(lyr, QgsMapLayer)

            if isinstance(lyr, SensorProxyLayer):
                if self.tsd().sensor() == lyr.sensor():
                    for tss in self.tsd():
                        if not tss.isVisible():
                            continue
                        source = tss.uri()

                        if source in existingSources:
                            sourceLayer = existing[existingSources.index(source)]
                        else:
                            loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
                            sourceLayer = SensorProxyLayer(source, sensor=self.tsd().sensor(), options=loptions)
                            sourceLayer.setName(lyr.name())
                            sourceLayer.setCustomProperty('eotsv/sensorid', self.tsd().sensor().id())
                            try:
                                renderer = lyr.renderer()
                                if isinstance(renderer, QgsRasterRenderer):
                                    sourceLayer.setRenderer(renderer.clone())
                            except Exception as exR:
                                s = ""
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
                    self.setSpatialCenter(self.mTimedRefreshPipeLine[SpatialPoint])

                if QColor in keys:
                    self.setCanvasColor(self.mTimedRefreshPipeLine[QColor])

                if MapCanvas.Command in keys:
                    commands = self.mTimedRefreshPipeLine[MapCanvas.Command]
                    for command in commands:
                        assert isinstance(command, MapCanvas.Command)
                        if command == MapCanvas.Command.RefreshRenderer:
                            for px in [px for px in self.mMapView.layers() if isinstance(px, SensorProxyLayer)]:
                                for l in self.layers():
                                    if isinstance(l, SensorProxyLayer) and l.sensor() == px.sensor():
                                        try:
                                            renderer = px.renderer().clone()
                                            renderer.setInput(l.dataProvider())
                                            l.setRenderer(renderer)
                                        except Exception as ex:
                                            s = ""
                        if command == MapCanvas.Command.UpdateMapItems:
                            #self.update()
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

    def crosshairStyle(self) -> CrosshairStyle:
        """
        Returns the style of the Crosshair.
        :return: CrosshairStyle
        """
        return self.mCrosshairItem.crosshairStyle

    def setCrosshairPosition(self, spatialPoint:SpatialPoint):
        """
        Sets the position of the Crosshair.
        :param spatialPoint: SpatialPoint
        :param emitSignal: True (default). Set False to avoid emitting sigCrosshairPositionChanged
        :return:
        """

        point = spatialPoint.toCrs(self.mapSettings().destinationCrs())
        if self.mCrosshairItem.mPosition != point:
            self.mCrosshairItem.setPosition(point)
            self.sigCrosshairPositionChanged.emit(point)

    def crosshairPosition(self) -> SpatialPoint:
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

    def contextMenu(self, pos:QPoint) -> QMenu:
        """
        Creates the MapCanvas context menu with options relevant for pixel position ``pos``.
        :param pos: QPoint
        :return: QMenu
        """
        mapSettings = self.mapSettings()
        assert isinstance(mapSettings, QgsMapSettings)

        pointGeo = mapSettings.mapToPixel().toMapCoordinates(pos.x(), pos.y())
        assert isinstance(pointGeo, QgsPointXY)

        tsd = self.tsd()

        from .main import EOTimeSeriesViewer
        eotsv = EOTimeSeriesViewer.instance()

        viewPortMapLayers = [l for l in self.layers() if isinstance(l, QgsMapLayer)]

        viewPortRasterLayers = [l for l in viewPortMapLayers if isinstance(l, QgsRasterLayer) and SpatialExtent.fromLayer(l).toCrs(self.crs()).contains(pointGeo)]
        viewPortSensorLayers = [l for l in viewPortRasterLayers if isinstance(l, SensorProxyLayer)]
        viewPortVectorLayers = [l for l in viewPortMapLayers if isinstance(l, QgsVectorLayer)]

        refSensorLayer = None
        refRasterLayer = None

        if len(viewPortRasterLayers) > 0:
            refRasterLayer = viewPortRasterLayers[0]
        if len(viewPortSensorLayers) > 0:
            refSensorLayer = viewPortSensorLayers[0]

        menu = QMenu()

        if isinstance(self.tsd(), TimeSeriesDate):
            tss = None
            sourceUris = self.tsd().sourceUris()
            for sl in viewPortSensorLayers:
                if sl.source() in sourceUris:
                    tss = self.tsd()[sourceUris.index(sl.source())]
                    break

            lyrWithSelectedFeatures = [l for l in quickLabelLayers() if l.isEditable() and l.selectedFeatureCount() > 0]

            layerNames = ', '.join([l.name() for l in lyrWithSelectedFeatures])
            m = menu.addMenu('Quick Labels')
            m.setToolTipsVisible(True)
            nQuickLabelLayers = len(lyrWithSelectedFeatures)
            m.setEnabled(nQuickLabelLayers > 0)

            a = m.addAction('Set Date/Sensor attributes')
            a.setToolTip('Writes the dates and sensor quick labels of selected features in {}.'.format(layerNames))
            a.triggered.connect(lambda *args, tsd = self.tsd(), tss=tss: setQuickTSDLabelsForRegisteredLayers(tsd, tss))

            from .labeling import CONFKEY_CLASSIFICATIONSCHEME, layerClassSchemes, setQuickClassInfo
            if len(lyrWithSelectedFeatures) == 0:
                a = m.addAction('No features selected.')
                a.setToolTip('Select feature in the labeling panel to apply Quick label value on.')
                a.setEnabled(False)
            else:
                for layer in lyrWithSelectedFeatures:
                    assert isinstance(layer, QgsVectorLayer)

                    csf = layerClassSchemes(layer)
                    if len(csf) > 0:
                        m.addSection(layer.name())
                        for (cs, field) in csf:
                            assert isinstance(cs, ClassificationScheme)
                            assert isinstance(field, QgsField)

                            classMenu = m.addMenu('"{}" ({})'.format(field.name(), field.typeName()))
                            for classInfo in cs:
                                assert isinstance(classInfo, ClassInfo)
                                a = classMenu.addAction('{} "{}"'.format(classInfo.label(), classInfo.name()))
                                a.setIcon(classInfo.icon())
                                a.triggered.connect(lambda _, vl=layer, f=field, c=classInfo: setQuickClassInfo(vl, f, c))


        if isinstance(refSensorLayer, SensorProxyLayer):
            m = menu.addMenu('Raster stretch...')
            action = m.addAction('Linear')
            action.triggered.connect(lambda *args, lyr=refSensorLayer: self.stretchToExtent(self.spatialExtent(), 'linear_minmax', layer=lyr, p=0.0))

            action = m.addAction('Linear 5%')
            action.triggered.connect(lambda *args, lyr=refSensorLayer: self.stretchToExtent(self.spatialExtent(), 'linear_minmax', layer=lyr, p=0.05))

            action = m.addAction('Gaussian')
            action.triggered.connect(lambda *args, lyr=refSensorLayer: self.stretchToExtent(self.spatialExtent(), 'gaussian', layer=lyr, n=3))



        menu.addSeparator()

        from .externals.qps.layerproperties import pasteStyleFromClipboard, pasteStyleToClipboard

        b = isinstance(refRasterLayer, QgsRasterLayer)
        a = menu.addAction('Copy Style')
        a.setEnabled(b)
        a.setToolTip('Copy the current layer style to clipboard')
        a.triggered.connect(lambda *args, lyr=refRasterLayer: pasteStyleToClipboard(lyr))

        a = menu.addAction('Paste Style')


        a.setEnabled(False)
        clipBoardMime = QApplication.clipboard().mimeData()
        if isinstance(clipBoardMime, QMimeData) and 'application/qgis.style' in clipBoardMime.formats():
            a.setEnabled(True)

        a.triggered.connect(lambda *args, lyr=refRasterLayer: self.onPasteStyleFromClipboard(lyr))

        menu.addSeparator()

        m = menu.addMenu('Layers...')
        visibleLayers = viewPortRasterLayers + viewPortVectorLayers


        for mapLayer in visibleLayers:
            #sub = m.addMenu(mapLayer.name())
            if isinstance(mapLayer, SensorProxyLayer):
                name = os.path.basename(mapLayer.source())
            else:
                name = mapLayer.name()
            sub = m.addMenu(name)

            if isinstance(mapLayer, SensorProxyLayer):
                sub.setIcon(QIcon(':/eotimeseriesviewer/icons/icon.svg'))
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
            a.triggered.connect(lambda *args, lyr = mapLayer: self.onSetLayerProperties(lyr))


            a = sub.addAction('Zoom to Layer')
            a.setIcon(QIcon(':/images/themes/default/mActionZoomToLayer.svg'))
            a.triggered.connect(lambda *args, lyr=mapLayer: self.setSpatialExtent(SpatialExtent.fromLayer(lyr)))

            a = sub.addAction('Copy Style')
            a.setToolTip('Copy layer style to clipboard')
            a.triggered.connect(lambda *args, lyr=mapLayer: pasteStyleToClipboard(lyr))

            a = sub.addAction('Paste Style')
            a.setToolTip('Paster layer style from clipboard')
            a.setEnabled('application/qgis.style' in QApplication.clipboard().mimeData().formats())
            a.triggered.connect(lambda *args, lyr=mapLayer: self.onPasteStyleFromClipboard(lyr))

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

        action = m.addAction('Set Style')
        def onCrosshairChange(*args):

            style = CrosshairDialog.getCrosshairStyle(parent=self,
                                                      mapCanvas=self,
                                                      crosshair=self.mCrosshairItem.crosshairStyle)

            if isinstance(style, CrosshairStyle):
                self.setCrosshairStyle(style)

        action.triggered.connect(onCrosshairChange)

        if isinstance(tsd, TimeSeriesDate):
            menu.addSeparator()
            m = menu.addMenu('Copy...')
            action = m.addAction('Date')
            action.triggered.connect(lambda: QApplication.clipboard().setText(str(tsd.date())))
            action.setToolTip('Sends "{}" to the clipboard.'.format(str(tsd.date())))

            action = m.addAction('Sensor')
            action.triggered.connect(lambda: QApplication.clipboard().setText(tsd.sensor().name()))
            action.setToolTip('Sends "{}" to the clipboard.'.format(tsd.sensor().name()))

            action = m.addAction('Path')
            paths = [QDir.toNativeSeparators(p) for p in tsd.sourceUris()]
            action.triggered.connect(lambda _, paths=paths: QApplication.clipboard().setText('\n'.join(paths)))
            action.setToolTip('Sends {} source URI(s) to the clipboard.'.format(len(tsd)))

            extent = self.extent()
            assert isinstance(extent, QgsRectangle)
            action = m.addAction('Extent')
            action.triggered.connect(lambda _, extent=extent: QApplication.clipboard().setText(extent.toString()))
            action.setToolTip('Sends the map extent to the clipboard.')

            action = m.addAction('Map')
            action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.pixmap()))
            action.setToolTip('Copies this map into the clipboard.')

            from .utils import findParent
            from .mapvisualization import MapWidget
            mw = findParent(self, MapWidget)
            if isinstance(mw, MapWidget):
                action = m.addAction('All Maps')
                action.triggered.connect(lambda: QApplication.clipboard().setPixmap(mw.grab()))
                action.setToolTip('Copies all maps into the clipboard.')


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
        action.triggered.connect(lambda: self.saveMapImageDialog('PNG'))
        action = m.addAction('JPEG')
        action.triggered.connect(lambda: self.saveMapImageDialog('JPG'))

        menu.addSeparator()

        """
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
                    a.setToolTip('Write "{}" or "{}" to connected vector field attributes'.format(classInfo.name(), classInfo.label()))

                    a.triggered.connect(
                        lambda *args, tsd=self.tsd(), ci = classInfo:
                        applyShortcutsToRegisteredLayers(tsd, [ci]))
                classSchemes.append(classScheme)
        """


        if isinstance(self.tsd(), TimeSeriesDate) and isinstance(eotsv, EOTimeSeriesViewer):
            menu.addSeparator()

            ts = eotsv.timeSeries()

            action = menu.addAction('Focus on Spatial Extent')
            action.triggered.connect(ts.focusVisibilityToExtent)

            action = menu.addAction('Hide Date')
            action.triggered.connect(lambda *args: ts.hideTSDs([tsd]))

            action = menu.addAction('Remove Date')
            action.triggered.connect(lambda *args, : ts.removeTSDs([tsd]))

        return menu

    def onSetLayerProperties(self, lyr:QgsRasterLayer):
        # b = isinstance(mapLayer, SensorProxyLayer) == False:

        result = showLayerPropertiesDialog(lyr, self, useQGISDialog=True)

        if result == QDialog.Accepted and isinstance(lyr, SensorProxyLayer):
            r = lyr.renderer().clone()
            proxyLayer = self.mMapView.sensorProxyLayer(lyr.sensor())
            r.setInput(proxyLayer.dataProvider())
            proxyLayer.setRenderer(r)


    def onPasteStyleFromClipboard(self, lyr):
        from .externals.qps.layerproperties import pasteStyleFromClipboard
        pasteStyleFromClipboard(lyr)
        if isinstance(lyr, SensorProxyLayer):
            r = lyr.renderer().clone()
            proxyLayer = self.mMapView.sensorProxyLayer(lyr.sensor())
            r.setInput(proxyLayer.dataProvider())
            proxyLayer.setRenderer(r)


    def contextMenuEvent(self, event:QContextMenuEvent):
        """
        Create and shows the MapCanvas context menu.
        :param event: QEvent
        """
        assert isinstance(event, QContextMenuEvent)
        menu = self.contextMenu(event.pos())
        menu.exec_(event.globalPos())

    def addLayers2QGIS(self, mapLayers):
        import qgis.utils
        iface = qgis.utils.iface
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
        """
        Stretches the top-raster layer band to the current spatial extent
        """
        se = self.spatialExtent()
        self.stretchToExtent(se, stretchType='linear_minmax', p=0.05)

    def stretchToExtent(self, spatialExtent:SpatialExtent, stretchType='linear_minmax', layer:QgsRasterLayer=None, **stretchArgs):
        """
        :param spatialExtent: rectangle to get the image statistics for
        :param stretchType: ['linear_minmax' (default), 'gaussian']
        :param stretchArgs:
            linear_minmax: 'p'  percentage from min/max, e.g. +- 5 %
            gaussian: 'n' mean +- n* standard deviations
        :return:
        """
        if not isinstance(layer, QgsRasterLayer):
            layers = [l for l in self.layers() if isinstance(l, SensorProxyLayer)]
            if len(layers) > 0:
                layer = layers[0]
            else:
                layers = [l for l in self.layers() if isinstance(l, SensorProxyLayer)]
                if len(layers) > 0:
                    layer = layers[0]

        if not isinstance(layer, QgsRasterLayer):
            return

        if not isinstance(spatialExtent, SpatialExtent):
            spatialExtent = SpatialExtent.fromLayer(layer)

        r = layer.renderer()
        dp = layer.dataProvider()
        newRenderer = None
        extent = spatialExtent.toCrs(layer.crs())

        assert isinstance(dp, QgsRasterDataProvider)

        def getCE(band):
            stats = dp.bandStatistics(band, QgsRasterBandStats.All, extent, 256)

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

            if isinstance(layer, SensorProxyLayer):
                self.mMapView.sensorProxyLayer(layer.sensor()).setRenderer(newRenderer)
            elif isinstance(layer, QgsRasterLayer):
                layer.setRenderer(newRenderer)


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
        if isinstance(self.mTSD, TimeSeriesDate) and isinstance(self.mMapView, MapView):
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
            if isinstance(spatialExtent, SpatialExtent):
                self.setExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint: SpatialPoint):
        """
        Sets the map center
        :param spatialPoint: SpatialPoint
        """
        center = spatialPoint.toCrs(self.crs())
        if isinstance(center, SpatialPoint):
            self.setCenter(center)

    def spatialExtent(self) -> SpatialExtent:
        """
        Returns the map extent as SpatialExtent (extent + CRS)
        :return: SpatialExtent
        """
        return SpatialExtent.fromMapCanvas(self)

    def spatialCenter(self) -> SpatialPoint:
        """
        Returns the map center as SpatialPoint (QgsPointXY + CRS)
        :return: SpatialPoint
        """
        return SpatialPoint.fromMapCanvasCenter(self)


    def spatialExtentHint(self) -> SpatialExtent:
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

