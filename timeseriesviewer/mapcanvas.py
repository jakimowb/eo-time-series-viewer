
import os, logging

logger = logging.getLogger(__name__)

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from timeseriesviewer import SETTINGS
from timeseriesviewer.utils import *
from timeseriesviewer.ui.widgets import TsvScrollArea

class MapCanvas(QgsMapCanvas):



    from timeseriesviewer.main import SpatialExtent, SpatialPoint
    saveFileDirectories = dict()
    sigShowProfiles = pyqtSignal(SpatialPoint)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigChangeDVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeMVRequest = pyqtSignal(QgsMapCanvas, str)
    sigChangeSVRequest = pyqtSignal(QgsMapCanvas, QgsRasterRenderer)

    def __init__(self, parent=None):
        super(MapCanvas, self).__init__(parent=parent)
        from timeseriesviewer.mapvisualization import DatumView, MapView, SpatialTemporalVisualization

        #the canvas
        self.setCrsTransformEnabled(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCanvasColor(SETTINGS.value('CANVAS_BACKGROUND_COLOR', QColor(0, 0, 0)))
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        #refreshTimer.timeout.connect(self.onTimerRefresh)
        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))


        #self.tsdView = tsdView
        #self.referenceLayer = QgsRasterLayer(self.tsdView.timeSeriesDatum.pathImg)

        self.mLayers = []
        #self.mapView = mapView
        #self.spatTempVis = mapView.spatTempVis
        #assert isinstance(self.spatTempVis, SpatialTemporalVisualization)
        #self.sigSpatialExtentChanged.connect(self.spatTempVis.setSpatialExtent)

        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.crosshairItem = CrosshairMapCanvasItem(self)



        self.mDataRefreshRequired = False



        self.mMapTools = dict()
        self.mMapTools['zoomOut'] = QgsMapToolZoom(self, True)
        self.mMapTools['zoomIn'] = QgsMapToolZoom(self, False)
        self.mMapTools['pan'] = QgsMapToolPan(self)

        from timeseriesviewer.maptools import CursorLocationMapTool
        mt = CursorLocationMapTool(self)
        mt.sigLocationRequest.connect(self.sigShowProfiles.emit)
        self.mMapTools['identifyProfile'] = mt
        mt = CursorLocationMapTool(self)
        mt.sigLocationRequest.connect(lambda pt: self.setCenter(pt))
        self.mMapTools['moveCenter'] = mt


    def setFixedSize(self, size):
        assert isinstance(size, QSize)
        if self.size() != size:
            super(MapCanvas, self).setFixedSize(size)

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if self.crs() != crs:
            self.setDestinationCrs(crs)
            self.mDataRefreshRequired = True
    def crs(self):
        return self.mapSettings().destinationCrs()


    def _depr_onExtentsChanged(self, *args):
        if not self.mBlockExtentsChangedSignal:
            self.mBlockExtentsChangedSignal = True
            print('set STV extent')
            self.spatTempVis.setSpatialExtent(self.spatialExtent())
            self.mBlockExtentsChangedSignal = False

    def mapLayersToRender(self, *args):
        """Returns the map layers actually to be rendered"""
        return self.mLayers

        mapLayers = []
        self.mLayers
        if self.mapView.visibleVectorOverlay():
            #if necessary, register new vector layer
            refLyr = self.mapView.vectorLayer
            refUri = refLyr.dataProvider().dataSourceUri()

            if self.vectorLayer is None or self.vectorLayer.dataProvider().dataSourceUri() != refUri:
                providerKey = refLyr.dataProvider().name()
                baseName = os.path.basename(refUri)
                self.vectorLayer = QgsVectorLayer(refUri, baseName, providerKey)

            #update layer style
            self.vectorLayer.setRendererV2(refLyr.rendererV2().clone())
            mapLayers.append(self.vectorLayer)

        if self.referenceLayer:
            mapLayers.append(self.referenceLayer)

        return mapLayers



    def setLayerSet(self, *args):
        raise DeprecationWarning()

    def setLayers(self, mapLayers):
        reg = QgsMapLayerRegistry.instance()
        reg.addMapLayers(mapLayers, False)

        self.mLayers = mapLayers[:]
        self.mDataRefreshRequired = True
        super(MapCanvas, self).setLayerSet([QgsMapCanvasLayer(l) for l in self.mLayers])

        #self.refresh()

    def refresh(self):
        #low-level, only performed if MapCanvas is visible
        self.checkRenderFlag()
        if self.renderFlag():
            print('REFRESH {}'.format(self.objectName()))
            self.setLayers(self.mapLayersToRender())
            #super(MapCanvas, self).refresh()
            self.refreshAllLayers()


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

    def onTimerRefresh(self):
        self.checkRenderFlag()
        self.refresh()

    def checkRenderFlag(self):
        isVisible = self.visibleRegion().boundingRect().isValid() \
                  and self.isVisible()
        if not isVisible:
            self.setRenderFlag(False)
        else:
            isRequired = self.renderFlag() or self.mDataRefreshRequired and not self.signalsBlocked()
            self.setRenderFlag(isRequired)

    def layerPaths(self):
        return [str(l.source()) for l in self.layers()]

    def pixmap(self):
        """
        Returns the current map image as pixmap
        :return:
        """
        return QPixmap(self.map().contentImage().copy())



    def contextMenuEvent(self, event):
        menu = QMenu()
        # add general options
        menu.addSeparator()
        action = menu.addAction('Stretch using current Extent')
        action.triggered.connect(self.stretchToCurrentExtent)
        action = menu.addAction('Zoom to Layer')
        action.triggered.connect(lambda : self.setSpatialExtent(self.spatialExtentHint()))
        menu.addSeparator()

        action = menu.addAction('Change crosshair style')
        from timeseriesviewer.crosshair import CrosshairDialog
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
        action = m.addAction('Map to Clipboard')
        action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.pixmap()))
        action = m.addAction('Image Path')
        action.triggered.connect(lambda: QApplication.clipboard().setText('\n'.join(self.layerPaths())))
        action = m.addAction('Image Style')
        #action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.tsdView.TSD.pathImg))

        m = menu.addMenu('Save as...')
        action = m.addAction('PNG')
        action.triggered.connect(lambda : self.saveMapImageDialog('PNG'))
        action = m.addAction('JPEG')
        action.triggered.connect(lambda: self.saveMapImageDialog('JPG'))

        from timeseriesviewer.main import QgisTsvBridge
        bridge = QgisTsvBridge.instance()
        if bridge:
            assert isinstance(bridge, QgisTsvBridge)
            action = m.addAction('Add layer to QGIS')
            action = m.addAction('Import extent from QGIS')
            action = m.addAction('Export extent to QGIS')
            s = ""




        menu.addSeparator()

        action = menu.addAction('Hide date')
        action.triggered.connect(lambda : self.sigChangeDVRequest.emit(self, 'hide_date'))
        action = menu.addAction('Remove date')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'remove_date'))
        action = menu.addAction('Remove map view')
        action.triggered.connect(lambda: self.sigChangeMVRequest.emit(self, 'remove_mapview'))
        action = menu.addAction('Hide map view')
        action.triggered.connect(lambda: self.sigChangeMVRequest.emit(self, 'hide_mapview'))


        menu.exec_(event.globalPos())

    def stretchToCurrentExtent(self):

        se = self.spatialExtent()
        ceAlg = QgsContrastEnhancement.StretchToMinimumMaximum
        for l in self.layers():
            if isinstance(l, QgsRasterLayer):
                r = l.renderer()
                dp = l.dataProvider()
                newRenderer = None
                extent = se.toCrs(l.crs())

                assert isinstance(dp, QgsRasterDataProvider)
                bands = None
                if isinstance(r, QgsMultiBandColorRenderer):

                    def getCE(band, ce):
                        stats = dp.bandStatistics(band, QgsRasterBandStats.All, extent, 500)
                        if stats.maximumValue is None:
                            s = ""
                        ce = QgsContrastEnhancement(dp.dataType(band))
                        ce.setContrastEnhancementAlgorithm(ceAlg)
                        ce.setMinimumValue(stats.minimumValue)
                        ce.setMaximumValue(stats.maximumValue)
                        return ce

                    newRenderer = QgsMultiBandColorRenderer(None,r.redBand(), r.greenBand(), r.blueBand())
                    newRenderer.setRedContrastEnhancement(getCE(r.redBand(), r.redContrastEnhancement()))
                    newRenderer.setGreenContrastEnhancement(getCE(r.greenBand(), r.greenContrastEnhancement()))
                    newRenderer.setBlueContrastEnhancement(getCE(r.blueBand(), r.blueContrastEnhancement()))

                elif isinstance(r, QgsSingleBandPseudoColorRenderer):
                    newRenderer = r.clone()
                    stats = dp.bandStatistics(newRenderer.band(), QgsRasterBandStats.All, extent, 500)
                    shader = newRenderer.shader()
                    newRenderer.setClassificationMax(stats.maximumValue)
                    newRenderer.setClassificationMin(stats.minimumValue)
                    shader.setMaximumValue(stats.maximumValue)
                    shader.setMinimumValue(stats.minimumValue)
                    s = ""

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
        path = jp(lastDir, '{}.{}.{}'.format(self.tsdView.TSD.date, self.mapView.title(), fileType.lower()))

        path = QFileDialog.getSaveFileName(self, 'Save map as {}'.format(fileType), path)
        if len(path) > 0:
            self.saveAsImage(path, None, fileType)
            SETTINGS.setValue('CANVAS_SAVE_IMG_DIR', os.path.dirname(path))




    def setRenderer(self, renderer):

        #lyrs = [l for l in self.mapLayersToRender() if str(l.source()) == targetLayerUri]
        isRasterRenderer = isinstance(renderer, QgsRasterRenderer)
        if isRasterRenderer:
            lyrs = [l for l in self.mLayers if isinstance(l, QgsRasterLayer)]
            for lyr in lyrs:
                if isinstance(renderer, QgsMultiBandColorRenderer):
                    r = renderer.clone()
                    r.setInput(lyr.dataProvider())
                elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                    r = renderer.clone()
                    #r = QgsSingleBandPseudoColorRenderer(None, renderer.band(), None)
                    r.setInput(lyr.dataProvider())
                    cmin = renderer.classificationMin()
                    cmax = renderer.classificationMax()
                    r.setClassificationMin(cmin)
                    r.setClassificationMax(cmax)
                    #r.setShader(renderer.shader())
                    s = ""
                else:
                    raise NotImplementedError()
                lyr.setRenderer(r)
        else:
            lyrs = [l for l in self.mLayers if isinstance(l, QgsVectorLayer)]
            for lyr in lyrs:
                lyr.setRenderer(renderer)

        self.refresh()

    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            spatialExtent = spatialExtent.toCrs(self.crs())
            if spatialExtent:
                self.setExtent(spatialExtent)
                self.mDataRefreshRequired = True


    def spatialExtent(self):
        return SpatialExtent.fromMapCanvas(self)

    def spatialExtentHint(self):
        crs = self.crs()
        ext = SpatialExtent.world()
        for lyr in self.mLayers + self.layers():
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

        geom = QgsPolygonV2()
        assert geom.fromWkt(ext.asWktPolygon())

        self.mCanvasExtents[canvas] = (ext, geom)
        self.refreshExtents()

    def refreshExtents(self):
        multi = QgsMultiPolygonV2()
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
        #QgsMapLayerRegistry.instance().addMapLayer(ml)
        lyrs.append(ml)

        #mapCanvas = QgsMapCanvas(w)
        mapCanvas = MapCanvas(w)
        mapCanvas.setCrsTransformEnabled(True)
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
    exampleSyncedCanvases()
