
import os, logging

logger = logging.getLogger(__name__)

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from timeseriesviewer import SETTINGS
from timeseriesviewer.utils import *
from timeseriesviewer.ui.widgets import TsvScrollArea

class TsvMapCanvas(QgsMapCanvas):
    from timeseriesviewer.main import SpatialExtent
    saveFileDirectories = dict()
    sigShowProfiles = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def __init__(self, tsdView, mapView, parent=None):
        super(TsvMapCanvas, self).__init__(parent=parent)
        from timeseriesviewer.main import TimeSeriesDatumView, MapView
        assert isinstance(tsdView, TimeSeriesDatumView)
        assert isinstance(mapView, MapView)

        #the canvas
        self.setCrsTransformEnabled(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCanvasColor(SETTINGS.value('CANVAS_BACKGROUND_COLOR', QColor(0, 0, 0)))
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))

        self.scrollArea = tsdView.scrollArea
        assert isinstance(self.scrollArea, TsvScrollArea)
        self.scrollArea.sigResized.connect(self.setRenderMe)
        self.scrollArea.horizontalScrollBar().valueChanged.connect(self.setRenderMe)

        self.tsdView = tsdView
        self.mapView = mapView

        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.crosshairItem = CrosshairMapCanvasItem(self)


        self.vectorLayer = None

        self.mapView.sigVectorLayerChanged.connect(self.refresh)
        self.mapView.sigVectorVisibility.connect(self.refresh)

        self.renderMe = False
        self.setRenderMe()

        self.sensorView = self.mapView.sensorViews[self.tsdView.Sensor]
        self.mapView.sigMapViewVisibility.connect(self.refresh)
        self.mapView.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        self.mapView.sigCrosshairStyleChanged.connect(self.setCrosshairStyle)
        self.referenceLayer = QgsRasterLayer(self.tsdView.TSD.pathImg)





        self.sensorView.sigSensorRendererChanged.connect(self.setRenderer)
        self.setRenderer(self.sensorView.layerRenderer())


        self.MAPTOOLS = dict()
        self.MAPTOOLS['zoomOut'] = QgsMapToolZoom(self, True)
        self.MAPTOOLS['zoomIn'] = QgsMapToolZoom(self, False)
        self.MAPTOOLS['pan'] = QgsMapToolPan(self)
        from timeseriesviewer.maptools import PointMapTool, PointLayersMapTool
        mt = PointMapTool(self)
        mt.sigCoordinateSelected.connect(self.sigShowProfiles.emit)
        self.MAPTOOLS['identifyProfile'] = mt

        self.refresh()


    def mapLayersToRender(self, *args):
        """Returns the map layers actually to be rendered"""
        mapLayers = []

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
        for l in mapLayers:
            reg.addMapLayer(l)
        super(TsvMapCanvas,self).setLayerSet([QgsMapCanvasLayer(l) for l in mapLayers])

    def refresh(self):
        self.setLayers(self.mapLayersToRender())
        self.setRenderMe()
        super(TsvMapCanvas, self).refresh()


    def setCrosshairStyle(self,crosshairStyle):
        from timeseriesviewer.crosshair import CrosshairStyle
        if crosshairStyle is None:
            self.crosshairItem.crosshairStyle.setShow(False)
            self.crosshairItem.update()
        else:
            assert isinstance(crosshairStyle, CrosshairStyle)
            self.crosshairItem.setCrosshairStyle(crosshairStyle)



    def setRenderMe(self):
        oldFlag = self.renderFlag()

        newFlag = self.visibleRegion().boundingRect().isValid() and self.isVisible() and self.tsdView.TSD.isVisible()
        if oldFlag != newFlag:
            self.setRenderFlag(newFlag)
        #print((self.tsdView.TSD, self.renderFlag()))
        #return b.isValid()

    def pixmap(self):
        """
        Returns the current map image as pixmap
        :return:
        """
        return QPixmap(self.map().contentImage().copy())

    def setShowCrosshair(self, b):
        assert isinstance(b, bool)
        self.crosshairItem.crosshairStyle.setShow(b)

    def contextMenuEvent(self, event):
        menu = QMenu()
        # add general options
        menu.addSeparator()
        action = menu.addAction('Stretch using current Extent')
        action.triggered.connect(self.stretchToCurrentExtent)
        action = menu.addAction('Zoom to Layer')
        action.triggered.connect(lambda : self.setExtent(SpatialExtent(self.referenceLayer.crs(),self.referenceLayer.extent())))
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
        action.triggered.connect(lambda: QApplication.clipboard().setText(self.tsdView.TSD.pathImg))
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
        TSD = self.tsdView.TSD
        action = menu.addAction('Hide date')
        action.triggered.connect(lambda : self.tsdView.TSD.setVisibility(False))
        action = menu.addAction('Remove date')
        action.triggered.connect(lambda: TSD.timeSeries.removeDates([TSD]))
        action = menu.addAction('Remove map view')
        action.triggered.connect(lambda: self.mapView.sigRemoveMapView.emit(self.mapView))
        action = menu.addAction('Hide map view')
        action.triggered.connect(lambda: self.mapView.sigHideMapView.emit())


        menu.exec_(event.globalPos())

    def stretchToCurrentExtent(self):
        results = dict()
        se = self.spatialExtent()

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
                        ce = QgsContrastEnhancement(ce)
                        ce.setMinimumValue(stats.minimumValue)
                        ce.setMaximumValue(stats.maximumValue)
                        return ce

                    newRenderer = QgsMultiBandColorRenderer(None,r.redBand(), r.greenBand(), r.blueBand())
                    newRenderer.setRedContrastEnhancement(getCE(r.redBand(), r.redContrastEnhancement()))
                    newRenderer.setGreenContrastEnhancement(getCE(r.greenBand(), r.greenContrastEnhancement()))
                    newRenderer.setBlueContrastEnhancement(getCE(r.blueBand(), r.blueContrastEnhancement()))

                    results[self.tsdView.TSD.sensor] = newRenderer
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
                    self.sensorView.setLayerRenderer(newRenderer)
        s = ""

    def activateMapTool(self, key):
        if key is None:
            self.setMapTool(None)
        elif key in self.MAPTOOLS.keys():
            self.setMapTool(self.MAPTOOLS[key])
        else:
            logger.error('unknown map tool key "{}"'.format(key))

    def saveMapImageDialog(self, fileType):
        lastDir = SETTINGS.value('CANVAS_SAVE_IMG_DIR', os.path.expanduser('~'))
        path = jp(lastDir, '{}.{}.{}'.format(self.tsdView.TSD.date, self.mapView.title(), fileType.lower()))

        path = QFileDialog.getSaveFileName(self, 'Save map as {}'.format(fileType), path)
        if len(path) > 0:
            self.saveAsImage(path, None, fileType)
            SETTINGS.setValue('CANVAS_SAVE_IMG_DIR', os.path.dirname(path))


    def setRenderer(self, renderer, targetLayerUri=None):
        if targetLayerUri is None:
            targetLayerUri = str(self.referenceLayer.source())

        lyrs = [l for l in self.mapLayersToRender() if str(l.source()) == targetLayerUri]
        assert len(lyrs) <= 1
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

        self.refresh()

    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            self.blockSignals(True)
            self.setDestinationCrs(spatialExtent.crs())
            self.setExtent(spatialExtent)
            self.blockSignals(False)
            self.refresh()


    def spatialExtent(self):
        return SpatialExtent.fromMapCanvas(self)
