# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import
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
        #self.extentsChanged.connect(lambda : self._setDataRefreshed())
        self.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(self.spatialExtent()))

        self.mLazyRasterSources = []
        self.mLazyVectorSources = []

        self.mRendererRaster = None
        self.mRendererVector = None

        #self.tsdView = tsdView
        #self.referenceLayer = QgsRasterLayer(self.tsdView.timeSeriesDatum.pathImg)

        self.mWasVisible = False
        self.mMapSummary = self.mapSummary()
        self.mLayers = []
        #self.mapView = mapView
        #self.spatTempVis = mapView.spatTempVis
        #assert isinstance(self.spatTempVis, SpatialTemporalVisualization)
        #self.sigSpatialExtentChanged.connect(self.spatTempVis.setSpatialExtent)

        from timeseriesviewer.crosshair import CrosshairMapCanvasItem
        self.crosshairItem = CrosshairMapCanvasItem(self)





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

    def crs(self):
        return self.mapSettings().destinationCrs()

    def onVectorOverlayChange(self, *args):

        self.refresh()

    def mapLayersToRender(self, *args):
        """Returns the map layers to be rendered"""
        if len(self.mLazyRasterSources) > 0:
            mls = [QgsRasterLayer(src) for src in self.mLazyRasterSources]
            QgsMapLayerRegistry.instance().addMapLayers(mls, False)
            del self.mLazyRasterSources[:]
            self.mLayers.extend(mls)
            self.setRenderer(self.mRendererRaster, refresh=False)
        if len(self.mLazyVectorSources) > 0:
            for t in self.mLazyVectorSources:

                lyr, path, name, provider = t
                #lyr = QgsVectorLayer(path, name, provider, False)
                #lyr = t
                #add vector layers on top
                lyr.rendererChanged.connect(self.onVectorOverlayChange)
                self.mLayers.insert(0, lyr)
            del self.mLazyVectorSources[:]
            self.setRenderer(self.mRendererVector, refresh=False)

        return self.mLayers

    def addLazyRasterSources(self, sources):
        assert isinstance(sources, list)
        self.mLazyRasterSources.extend(sources[:])

    def addLazyVectorSources(self, sourceLayers):
        assert isinstance(sourceLayers, list)
        for lyr in sourceLayers:
            assert isinstance(lyr, QgsVectorLayer)
            self.mLazyVectorSources.append((lyr, lyr.source(), lyr.name(), lyr.providerType()))


    def mapSummary(self):
        from PyQt4.QtXml import QDomDocument
        dom = QDomDocument()
        root = dom.createElement('renderer')
        dom.appendChild(root)
        if self.mRendererVector:
            self.mRendererVector.writeXML(dom, root)
        if self.mRendererRaster:
            self.mRendererRaster.writeXML(dom, root)
        xml = dom.toString()

        return (self.crs(), self.spatialExtent(), self.size(), str(self.layers()), str(self.mLazyVectorSources), str(self.mLazyRasterSources), xml)

    def setLayerSet(self, *args):
        raise DeprecationWarning()


    def setLayers(self, mapLayers):


        oldLayerSet = set(self.layers())
        newLayerSet = set(mapLayers)
        diffLayers = len(oldLayerSet.symmetric_difference(newLayerSet)) > 0
        if diffLayers:
            reg = QgsMapLayerRegistry.instance()
            reg.addMapLayers(mapLayers, False)
            self.mLayers = mapLayers[:]
            super(MapCanvas, self).setLayerSet([QgsMapCanvasLayer(l) for l in self.mLayers])

        #self.refresh()

    def refresh(self, force=False):
        #low-level, only performed if MapCanvas is visible

        self.checkRenderFlag()
        if self.renderFlag() or force:
            self.setLayers(self.mapLayersToRender())
            super(MapCanvas, self).refresh()
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

            #isRequired = (wasVisible == False) or self.renderFlag() or self.mDataRefreshed
            isRequired = lastSummary != self.mapSummary()
            self.mWasVisible = True
            if isRequired:
                self.setRenderFlag(True)
                self.mMapSummary = self.mapSummary()
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
        action = m.addAction('Date')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_date'))
        action = m.addAction('Sensor')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_sensor'))
        action = m.addAction('Path')
        action.triggered.connect(lambda: self.sigChangeDVRequest.emit(self, 'copy_path'))

        m = menu.addMenu('Save to...')
        action = m.addAction('PNG')
        action.triggered.connect(lambda : self.saveMapImageDialog('PNG'))
        action = m.addAction('JPEG')
        action.triggered.connect(lambda: self.saveMapImageDialog('JPG'))
        action = m.addAction('Clipboard')
        action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.pixmap()))
        from timeseriesviewer.main import QgisTsvBridge

        menu.addSeparator()
        action = menu.addAction('Add raster to QGIS')
        from PyQt4.QtCore import QThread

        import qgis.utils
        if qgis.utils is not None:
            action.triggered.connect(lambda: QgisTsvBridge.addMapLayers(self.layers()))
        else:
            action.setEnabled(False)

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


                    newRenderer = QgsMultiBandColorRenderer(None, r.redBand(), r.greenBand(), r.blueBand())
                    newRenderer.setRedContrastEnhancement(getCE(r.redBand()))
                    newRenderer.setGreenContrastEnhancement(getCE(r.greenBand()))
                    newRenderer.setBlueContrastEnhancement(getCE(r.blueBand()))

                elif isinstance(r, QgsSingleBandPseudoColorRenderer):
                    newRenderer = r.clone()
                    ce = getCE(newRenderer.band())
                    #stats = dp.bandStatistics(newRenderer.band(), QgsRasterBandStats.All, extent, 500)

                    shader = newRenderer.shader()
                    newRenderer.setClassificationMax(ce.maximumValue())
                    newRenderer.setClassificationMin(ce.minimumValue())
                    shader.setMaximumValue(ce.maximumValue())
                    shader.setMinimumValue(ce.minimumValue())
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


    def setRenderer(self, renderer, refresh=True):
        from timeseriesviewer.utils import copyRenderer
        if renderer is None:
            return
        if isinstance(renderer, QgsRasterRenderer):
            self.mRendererRaster = renderer
        elif isinstance(renderer, QgsFeatureRendererV2):
            self.mRendererVector = renderer

        success = [copyRenderer(renderer, lyr) for lyr in self.mLayers]
        if refresh and any(success):
            self.refresh()

    def depr_setVectorRenderer(self, renderer, refresh=True):
        self.mRendererVector = renderer
        lyrs = [l for l in self.mLayers if isinstance(l, QgsVectorLayer)]
        for lyr in lyrs:
            # todo: do we need to clone this?
            lyr.setRenderer(renderer)
        if refresh:
            self.refresh()

    def depr_setRasterRenderer(self, renderer, refresh=False):
        self.mRendererRaster = renderer
        lyrs = [l for l in self.mLayers if isinstance(l, QgsRasterLayer)]
        for lyr in lyrs:
            if isinstance(renderer, QgsMultiBandColorRenderer):
                r = renderer.clone()
                r.setInput(lyr.dataProvider())
            elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                r = renderer.clone()
                # r = QgsSingleBandPseudoColorRenderer(None, renderer.band(), None)
                r.setInput(lyr.dataProvider())
                cmin = renderer.classificationMin()
                cmax = renderer.classificationMax()
                r.setClassificationMin(cmin)
                r.setClassificationMax(cmax)
                # r.setShader(renderer.shader())
                s = ""
            else:
                raise NotImplementedError()
            lyr.setRenderer(r)
        if refresh:
            self.refresh()

    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            spatialExtent = spatialExtent.toCrs(self.crs())
            if spatialExtent:
                self.setExtent(spatialExtent)



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
