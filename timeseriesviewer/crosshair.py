
import os

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from timeseriesviewer import *
from timeseriesviewer.utils import *

from timeseriesviewer.ui.widgets import loadUIFormClass
load = lambda p : loadUIFormClass(jp(DIR_UI,p))

class CrosshairWidget(QWidget, load('crosshairwidget.ui')):

    def __init__(self, title='<#>', parent=None):
        super(CrosshairWidget, self).__init__(parent)
        self.setupUi(self)


        self.crossHairReferenceLayer = CrosshairLayer()
        self.crossHairReferenceLayer.connectCanvas(self.crossHairCanvas)

        self.crossHairCanvas.setExtent(QgsRectangle(0, 0, 1, 1))#
        QgsMapLayerRegistry.instance().addMapLayer(self.crossHairReferenceLayer)
        self.crossHairCanvas.setLayerSet([QgsMapCanvasLayer(self.crossHairReferenceLayer)])



        crs = QgsCoordinateReferenceSystem('EPSG:25832')




        self.crossHairCanvas.mapSettings().setDestinationCrs(crs)



        self.btnCrosshairColor.colorChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairAlpha.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairThickness.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairGap.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxDotSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.cbCrosshairShowDot.toggled.connect(self.refreshCrosshairPreview)

        self.refreshCrosshairPreview()

    def setCanvasColor(self, color):
        self.crossHairCanvas.setBackgroundColor(color)
        self.btnMapCanvasColor.colorChanged.connect(self.onMapCanvasColorChanged)

    def onMapCanvasColorChanged(self, color):

        self.sigMapCanvasColorChanged.emit(color)
        self.refreshCrosshairPreview()

    def mapCanvasColor(self):
        return self.btnMapCanvasColor.color()

    def refreshCrosshairPreview(self, *args):

        style = self.crosshairStyle()
        self.crossHairReferenceLayer.setCrosshairStyle(style)
        self.crossHairCanvas.refreshAllLayers()


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
        return style


class CrosshairStyle(object):
    def __init__(self, **kwds):

        self.mColor = QColor.fromRgb(255,0,0, 125)
        self.mThickness = 1 #in px
        self.mSize = 1.0 #normalized
        self.mGap = 0.05 #normalized
        self.mShowDot = True
        self.mDotSize = 1 #in px
        self.mShow = True

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

class CrosshairLayer(QgsVectorLayer):

    def __init__(self):
        super(CrosshairLayer, self).__init__('LineString', 'Crosshair', 'memory')
        self.canvas = None
        self.rasterGridLayer = None
        self.sizePixelBox = 1

        self.crosshairStyle = None
        self.setCrosshairStyle(CrosshairStyle())


    def connectCanvas(self, canvas):

        if isinstance(canvas, QgsMapCanvas):
            self.canvas = canvas
            #react on changed extents etc.

            self.canvas.destinationCrsChanged.connect(self.updateCrosshairGeometry)
            self.canvas.extentsChanged.connect(self.updateCrosshairGeometry)
            self.setValid(True)
        else:
            self.canvas = None
            self.setValid(False)

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
        self.setRendererV2(crosshairStyle.rendererV2())
        if isinstance(self.canvas, QgsMapCanvas):
            self.updateCrosshairGeometry()

    def updateCrosshairGeometry(self):
        ext = self.canvas.extent()
        crs = self.canvas.mapSettings().destinationCrs()
        self.setCrs(crs)

        mu = self.canvas.mapUnitsPerPixel()

        #canvas bbox
        x0, x1 = ext.xMinimum(), ext.xMaximum()
        y0, y1 = ext.yMinimum(), ext.yMaximum()


        #canvas center
        cx = x0 + 0.5 * (x1 - x0)
        cy = y0 + 0.5 * (y1 - y0)

        #adjust length by size and gap values
        dMax = min([cx - x0, cy - y0])
        d1 = dMax * self.crosshairStyle.mSize#vert. distance from center to border
        d0 = dMax * self.crosshairStyle.mGap
        tMu = mu * self.crosshairStyle.mThickness

        def polygonFeature(xValues, yValues):
            points = []
            for x,y in zip(xValues, yValues):
                points.append(QgsPointV2(x, y))
            points.append(QgsPointV2(x[0], y[0])) #close ring
            return QgsGeometry.fromPolygon(points)

        def lineFeature(xValues, yValues):
            line = QgsLineStringV2()
            for x,y in zip(xValues, yValues):
                line.addVertex(QgsPointV2(x, y))

            feature = QgsFeature(self.fields())
            g = QgsGeometry(line)
            feature.setGeometry(g)
            feature.setValid(True)
            assert feature.isValid()
            return feature

        features = []
        #add lines
        for p in [-1,1]:
            features.append(lineFeature([cx + p * d1, cx + p * d0],[cy, cy]))
            features.append(lineFeature([cx, cx], [cy + p * d1, cy + p * d0]))

        if self.crosshairStyle.mShowDot:
            h = 0.5 * mu * self.crosshairStyle.mDotSize
            features.append(lineFeature(

                [cx - h, cx + h,cx + h,cx - h, cx - h],
                [cy - h, cy - h, cy + h, cy + h, cy - h]
            ))


        self.startEditing()
        self.selectAll()
        for feature in self.selectedFeatures():
            self.deleteFeature(feature.id())
        self.commitChanges()
        self.startEditing()
        for feature in features:
            assert feature.isValid()
            self.addFeature(feature)
            s = ""
        self.commitChanges()
        self.repaintRequested.emit()

    def setExtent(self, extent):
        raise NotImplementedError()

    def extent(self):
        return self.canvas.extent()



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()
    d = CrosshairWidget()
    d.show()
    qgsApp.exec_()
    qgsApp.exitQgis()
