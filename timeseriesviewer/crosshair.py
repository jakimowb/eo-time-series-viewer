
import os

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer import *
from timeseriesviewer.utils import *

from timeseriesviewer.ui.widgets import loadUIFormClass

load = lambda p : loadUIFormClass(jp(DIR_UI,p))

class CrosshairStyle(object):
    def __init__(self, **kwds):

        self.mColor = QColor.fromRgb(255,0,0, 125)
        self.mThickness = 1 #in px
        self.mSize = 1.0 #normalized
        self.mGap = 0.05 #normalized
        self.mShowDot = True
        self.mDotSize = 1 #in px
        self.mSizePixelBorder = 1
        self.mShow = True
        self.mShowPixelBorder = True


    def setColor(self, color):
        assert isinstance(color, QColor)
        self.mColor = color

    def setSize(self, size):
        self.mSize = self._normalize(size)

    def setDotSize(self, size):
        assert size >= 0
        self.mDotSize = size

    def setThickness(self, size):
        """
        Crosshair thickness in px
        :param size:
        :return:
        """
        assert size >= 0
        self.mThickness = size

    def setShowPixelBorder(self, b):
        assert isinstance(b, bool)
        self.mShowPixelBorder = b

    def setGap(self, gapSize):
        """
        Set gap size in % [0, 100] or normalized coordinates [0,1]
        :param gapSize:
        :return:
        """
        self.mGap = self._normalize(gapSize)

    def _normalize(self, size):
        assert size >= 0 and size <= 100
        size = float(size)
        if size > 1:
            size /= 100
        return size

    def setShowDot(self, b):
        assert isinstance(b, bool)
        self.mShowDot = b

    def setShow(self, b):
        assert isinstance(b, bool)
        self.mShow = b

    def rendererV2(self):
        """
        Returns the vector layer renderer
        :return:
        """
        registry = QgsSymbolLayerV2Registry.instance()
        lineMeta = registry.symbolLayerMetadata("SimpleLine")
        lineLayer = lineMeta.createSymbolLayer({})
        lineLayer.setColor(self.mColor)
        lineLayer.setPenStyle(Qt.SolidLine)

        lineLayer.setWidth(self.mThickness)
        lineLayer.setWidthUnit(2) #pixel
        #lineLayer.setWidth(self.mThickness)

        """
        lineLayer = lineMeta.createSymbolLayer(
            {'width': '0.26',
             'color': self.mColor,
             'offset': '0',
             'penstyle': 'solid',
             'use_custom_dash': '0'})
        """

        # Replace the default layer with our custom layer

        symbol = QgsLineSymbolV2([])
        symbol.deleteSymbolLayer(0)
        symbol.appendSymbolLayer(lineLayer)
        return QgsSingleSymbolRendererV2(symbol)

class CrosshairMapCanvasItem(QgsMapCanvasItem):

    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(CrosshairMapCanvasItem, self).__init__(mapCanvas)

        self.canvas = mapCanvas
        self.rasterGridLayer = None
        self.sizePixelBox = 0
        self.sizePixelBox = 1
        self.mShow = True
        self.crosshairStyle = CrosshairStyle()
        self.crosshairStyle.setShow(False)
        self.setCrosshairStyle(self.crosshairStyle)

    def setShow(self, b):
        assert isinstance(b, bool)
        self.mShow = b

    def connectRasterGrid(self, qgsRasterLayer):

        if isinstance(qgsRasterLayer):
            self.rasterGridLayer = qgsRasterLayer
        else:
            self.rasterGridLayer = None

    def setPixelBox(self, nPx):
        assert nPx >= 0
        assert nPx == 1 or nPx % 3 == 0, 'Size of pixel box must be an odd integer'
        self.sizePixelBox = nPx


    def setCrosshairStyle(self, crosshairStyle):
        assert isinstance(crosshairStyle, CrosshairStyle)
        self.crosshairStyle = crosshairStyle

        #apply style
        self.canvas.update()
        #self.updateCanvas()

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
        if self.mShow and self.crosshairStyle.mShow:
           #paint the crosshair
            size = self.canvas.size()
            centerGeo = self.canvas.center()
            centerPx = self.toCanvasCoordinates(self.canvas.center())

            x0 = centerPx.x() * (1.0 - self.crosshairStyle.mSize)
            y0 = centerPx.y() * (1.0 - self.crosshairStyle.mSize)
            x1 = size.width() - x0
            y1 = size.height() - y0
            gap = min([centerPx.x(), centerPx.y()]) * self.crosshairStyle.mGap

            #this is what we want to draw
            lines = []
            polygons = []

            lines.append(QLineF(x0, centerPx.y(), centerPx.x() - gap, centerPx.y()))
            lines.append(QLineF(x1, centerPx.y(), centerPx.x() + gap, centerPx.y()))
            lines.append(QLineF(centerPx.x(), y0, centerPx.x(), centerPx.y() - gap))
            lines.append(QLineF(centerPx.x(), y1, centerPx.x(), centerPx.y() + gap))

            if self.crosshairStyle.mShowDot:
                p = QRectF()

                d = int(round(max([1,self.crosshairStyle.mDotSize * 0.5])))

                p.setTopLeft(QPointF(centerPx.x() - d,
                                     centerPx.y() + d))
                p.setBottomRight(QPointF(centerPx.x() + d,
                                         centerPx.y() - d))

                p = QPolygonF(p)
                polygons.append(p)

            if self.crosshairStyle.mShowPixelBorder:
                rasterLayers = [l for l in self.canvas.layers() if isinstance(l, QgsRasterLayer)
                                and l.isValid()]

                if len(rasterLayers) > 0:

                    lyr = rasterLayers[0]

                    ns = lyr.width()  # ns = number of samples = number of image columns
                    nl = lyr.height()  # nl = number of lines
                    ex = lyr.extent()
                    xres = lyr.rasterUnitsPerPixelX()
                    yres = lyr.rasterUnitsPerPixelY()

                    ms = self.canvas.mapSettings()
                    centerPxLyr = ms.mapToLayerCoordinates(lyr, centerGeo)


                    m2p = self.canvas.mapSettings().mapToPixel()
                    #get center pixel pixel index
                    pxX = int(np.floor((centerPxLyr.x() - ex.xMinimum()) / xres).astype(int))
                    pxY = int(np.floor((ex.yMaximum() - centerPxLyr.y()) / yres).astype(int))


                    def px2LayerGeo(x, y):
                        x2 = ex.xMinimum() + (x * xres)
                        y2 = ex.yMaximum() - (y * yres)
                        return QgsPoint(x2,y2)
                    lyrCoord2CanvasPx = lambda x, y, : self.toCanvasCoordinates(
                        ms.layerToMapCoordinates(lyr,
                                                 px2LayerGeo(x, y)))
                    if pxX >= 0 and pxY >= 0 and \
                       pxX < ns and pxY < nl:
                        #get pixel edges in map canvas coordinates

                        lyrGeo = px2LayerGeo(pxX, pxY)
                        mapGeo = ms.layerToMapCoordinates(lyr, lyrGeo)
                        canCor = self.toCanvasCoordinates(mapGeo)

                        ul = lyrCoord2CanvasPx(pxX, pxY)
                        ur = lyrCoord2CanvasPx(pxX+1, pxY)
                        lr = lyrCoord2CanvasPx(pxX+1, pxY+1)
                        ll = lyrCoord2CanvasPx(pxX, pxY+1)

                        pixelBorder = QPolygonF()
                        pixelBorder.append(ul)
                        pixelBorder.append(ur)
                        pixelBorder.append(lr)
                        pixelBorder.append(ll)
                        pixelBorder.append(ul)

                        pen = QPen(Qt.SolidLine)
                        pen.setWidth(self.crosshairStyle.mSizePixelBorder)
                        pen.setColor(self.crosshairStyle.mColor)
                        pen.setBrush(self.crosshairStyle.mColor)
                        brush = QBrush(Qt.NoBrush)
                        brush.setColor(self.crosshairStyle.mColor)
                        painter.setBrush(brush)
                        painter.setPen(pen)
                        painter.drawPolygon(pixelBorder)

            pen = QPen(Qt.SolidLine)
            pen.setWidth(self.crosshairStyle.mThickness)
            pen.setColor(self.crosshairStyle.mColor)
            pen.setBrush(self.crosshairStyle.mColor)
            brush = QBrush(Qt.NoBrush)
            brush.setColor(self.crosshairStyle.mColor)
            painter.setBrush(brush)
            painter.setPen(pen)
            for p in polygons:
                painter.drawPolygon(p)
            for p in lines:
                painter.drawLine(p)





class CrosshairWidget(QWidget, load('crosshairwidget.ui')):
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, title='<#>', parent=None):
        super(CrosshairWidget, self).__init__(parent)
        self.setupUi(self)

        #self.crossHairReferenceLayer = CrosshairLayer()
        #self.crossHairReferenceLayer.connectCanvas(self.crossHairCanvas)

        self.mapCanvas.setExtent(QgsRectangle(0, 0, 1, 1))  #
        #QgsMapLayerRegistry.instance().addMapLayer(self.crossHairReferenceLayer)
        #self.crossHairCanvas.setLayerSet([QgsMapCanvasLayer(self.crossHairReferenceLayer)])

        #crs = QgsCoordinateReferenceSystem('EPSG:25832')
        #self.crossHairCanvas.mapSettings().setDestinationCrs(crs)

        self.mapCanvasItem = CrosshairMapCanvasItem(self.mapCanvas)

        self.btnCrosshairColor.colorChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairAlpha.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairThickness.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairGap.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxDotSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.cbCrosshairShowDot.toggled.connect(self.refreshCrosshairPreview)
        self.cbShowPixelBoundaries.toggled.connect(self.refreshCrosshairPreview)
        self.refreshCrosshairPreview()

    def setCanvasColor(self, color):
        self.mapCanvas.setBackgroundColor(color)
        self.btnMapCanvasColor.colorChanged.connect(self.onMapCanvasColorChanged)

    def onMapCanvasColorChanged(self, color):
        self.sigMapCanvasColorChanged.emit(color)
        self.refreshCrosshairPreview()

    def mapCanvasColor(self):
        return self.btnMapCanvasColor.color()

    def refreshCrosshairPreview(self, *args):
        style = self.crosshairStyle()
        self.mapCanvasItem.setCrosshairStyle(style)
        #self.crossHairReferenceLayer.setCrosshairStyle(style)
        #self.crossHairCanvas.refreshAllLayers()
        self.sigCrosshairStyleChanged.emit(style)

    def crosshairStyle(self):
        style = CrosshairStyle()
        c = self.btnCrosshairColor.color()
        c.setAlpha(self.spinBoxCrosshairAlpha.value())
        style.setColor(c)
        style.setThickness(self.spinBoxCrosshairThickness.value())
        style.setSize(self.spinBoxCrosshairSize.value())
        style.setGap(self.spinBoxCrosshairGap.value())
        style.setDotSize(self.spinBoxDotSize.value())
        style.setShowDot(self.cbCrosshairShowDot.isChecked())
        style.setShowPixelBorder(self.cbShowPixelBoundaries.isChecked())
        return style

class CrosshairDialog(QgsDialog):

    def __init__(self, parent=None, crosshairStyle=None, mapCanvas=None):
        super(CrosshairDialog, self).__init__(parent=parent , \
            buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = CrosshairWidget(parent=self)

        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cance')
        buttonBar = QHBoxLayout()
        #buttonBar.addWidget(self.btCancel)
        #buttonBar.addWidget(self.btOk)
        l = self.layout()
        l.addWidget(self.w)
        l.addLayout(buttonBar)
        #self.setLayout(l)

        if isinstance(mapCanvas, QgsMapCanvas):
            self.setMapCanvas(mapCanvas)

        if isinstance(crosshairStyle, CrosshairStyle):
            self.setCrosshairStyle(crosshairStyle)
        s = ""

    def crosshairStyle(self):
        return self.w.crosshairStyle()

    def setCrosshairStyle(self, crosshairStyle):
        assert isinstance(crosshairStyle, CrosshairStyle)
        self.w.setCrosshairStyle(crosshairStyle)

    def setMapCanvas(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        # copy layers
        canvas = self.w.mapCanvasItem.canvas
        lyrs = []
        for lyr in mapCanvas.layers():
            s = ""
        lyrs = mapCanvas.layers()
        canvas.setLayerSet([QgsMapCanvasLayer(l) for l in lyrs])
        canvas.mapSettings().setDestinationCrs(mapCanvas.mapSettings().destinationCrs())
        canvas.setExtent(mapCanvas.extent())
        canvas.setCenter(mapCanvas.center())
        canvas.refresh()
        canvas.updateMap()
        canvas.refreshAllLayers()

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    if False:
        c = QgsMapCanvas()
        c.setExtent(QgsRectangle(0,0,1,1))
        i = CrosshairMapCanvasItem(c)
        i.setShow(True)
        s = CrosshairStyle()
        s.setShow(True)
        i.setCrosshairStyle(s)
        c.show()


    import example.Images
    lyr = QgsRasterLayer(example.Images.Img_2012_05_09_LE72270652012130EDC00_BOA)
    QgsMapLayerRegistry.instance().addMapLayer(lyr)
    refCanvas = QgsMapCanvas()
    refCanvas.setLayerSet([QgsMapCanvasLayer(lyr)])
    refCanvas.setExtent(lyr.extent())
    refCanvas.show()
    d = CrosshairDialog(mapCanvas=refCanvas)
    d.exec_()

    qgsApp.exec_()
    qgsApp.exitQgis()
