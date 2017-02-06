from qgis.core import *
from qgis.gui import *
import qgis
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtXml import *
from PyQt4.QtXmlPatterns import *
import six
import xml.etree
from qgis.core import *

from timeseriesviewer import SETTINGS
from timeseriesviewer.main import SpatialExtent


class CursorLocationValueMapTool(QgsMapTool):
    sigLocationIdentified = pyqtSignal(list)
    sigLocationRequest = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)
    def __init__(self, canvas):
        self.canvas = canvas
        self.layerType = QgsMapToolIdentify.AllLayers
        self.identifyMode = QgsMapToolIdentify.LayerSelection
        QgsMapToolIdentify.__init__(self, canvas)


    def canvasReleaseEvent(self, mouseEvent):
        x = mouseEvent.x()
        y = mouseEvent.y()
        point = self.canvas.getCoordinateTransform().toMapCoordinates(x,y)
        crs = self.canvas.mapRenderer().destinationCrs()
        self.sigLocationRequest.emit(point, crs)


def add_QgsRasterLayer(iface, path, rgb):
    if iface:

        fi = QFileInfo(path)
        layer = QgsRasterLayer(path, fi.baseName())
        if not layer.isValid():
            six.print_('Failed to load {}'.format(path))
        else:
            rasterLyr = iface.addRasterLayer(path, fi.baseName())


            renderer = rasterLyr.renderer()
            print(type(renderer))

            if type(renderer) is QgsMultiBandColorRenderer:
                renderer.setRedBand(rgb[0])
                renderer.setGreenBand(rgb[0])
                renderer.setBlueBand(rgb[0])

        if hasattr(layer, "triggerRepaint"):
            #layer.repaintRequested()
            layer.triggerRepaint()


    s = ""


paste_test = """
    <!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="2.12.3-Lyon">
 <pipe>
  <rasterrenderer opacity="1" alphaBand="-1" blueBand="1" greenBand="2" type="multibandcolor" redBand="3">
   <rasterTransparency/>
   <redContrastEnhancement>
    <minValue>2803.02</minValue>
    <maxValue>6072.21</maxValue>
    <algorithm>StretchToMinimumMaximum</algorithm>
   </redContrastEnhancement>
   <greenContrastEnhancement>
    <minValue>5103.86</minValue>
    <maxValue>7228.58</maxValue>
    <algorithm>StretchToMinimumMaximum</algorithm>
   </greenContrastEnhancement>
   <blueContrastEnhancement>
    <minValue>5992.32</minValue>
    <maxValue>7718.33</maxValue>
    <algorithm>StretchToMinimumMaximum</algorithm>
   </blueContrastEnhancement>
  </rasterrenderer>
  <brightnesscontrast brightness="0" contrast="0"/>
  <huesaturation colorizeGreen="128" colorizeOn="0" colorizeRed="255" colorizeBlue="128" grayscaleMode="0" saturation="0" colorizeStrength="100"/>
  <rasterresampler maxOversampling="2"/>
 </pipe>
 <blendMode>0</blendMode>
</qgis>
    """

def paste_band_settings(txt):

    result = None
    try:
        import xml.etree.ElementTree as ET
        tree = ET.fromstring(txt)

        renderer = tree.find('*/rasterrenderer')
        if renderer is not None:
            bands = list()
            ranges = list()
            for c in ['red','green','blue']:
                name = c + 'Band'
                if name not in renderer.attrib.keys():
                    return result

                bands.append(int(renderer.attrib[name]))
                v_min = float(renderer.find(c+'ContrastEnhancement/minValue').text)
                v_max = float(renderer.find(c+'ContrastEnhancement/maxValue').text)
                ranges.append((v_min, v_max))

            result = (bands, ranges)
    except:
        pass

    return result


class PointMapTool(QgsMapToolEmitPoint):

    sigCoordinateSelected = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)

    def __init__(self, canvas):

        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.marker = QgsVertexMarker(self.canvas)
        self.setStyle()

    def setStyle(self):
        color = QColor(SETTINGS.value('map_tool_color', Qt.red))
        penWidth = 3
        iconSize = 5
        iconType = QgsVertexMarker.ICON_CROSS
        self.marker.setColor(color)
        self.marker.setPenWidth(penWidth)
        self.marker.setIconSize(iconSize)
        self.marker.setIconType(iconType)  # or ICON_CROSS, ICON_X

    def canvasPressEvent(self, e):
        geoPoint = self.toMapCoordinates(e.pos())
        self.marker.setCenter(geoPoint)
        self.marker.show()

    def canvasReleaseEvent(self, e):


        pixelPoint = e.pixelPoint()
        _crs = self.canvas.mapRenderer().destinationCrs()
        crs = self.canvas.mapSettings().destinationCrs()
        self.marker.hide()
        if crs:

            geoPoint = self.toMapCoordinates(pixelPoint)
            self.marker.setCenter(geoPoint)
            self.sigCoordinateSelected.emit(geoPoint, crs)


class PointLayersMapTool(PointMapTool):

    def __init__(self, canvas):
        super(PointLayersMapTool, self).__init__(self, canvas)
        self.layerType = QgsMapToolIdentify.AllLayers
        self.identifyMode = QgsMapToolIdentify.LayerSelection
        QgsMapToolIdentify.__init__(self, canvas)

class SpatialExtentMapTool(QgsMapToolEmitPoint):
    from timeseriesviewer.main import SpatialExtent
    sigSpatialExtentSelected = pyqtSignal(SpatialExtent)


    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.rubberBand = QgsRubberBand(self.canvas, QGis.Polygon)
        self.setStyle(Qt.red, 1)
        self.reset()

    def setStyle(self, color, width):
        self.rubberBand.setColor(color)
        self.rubberBand.setWidth(width)

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QGis.Polygon)

    def canvasPressEvent(self, e):
        self.startPoint = self.toMapCoordinates(e.pos())
        self.endPoint = self.startPoint
        self.isEmittingPoint = True
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, e):
        self.isEmittingPoint = False

        crs = self.canvas.mapSettings().destinationCrs()
        rect = self.rectangle()

        self.reset()

        if crs is not None and rect is not None:
            extent = SpatialExtent(crs, rect)
            self.rectangleDrawed.emit(extent)


    def canvasMoveEvent(self, e):

        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(e.pos())
        self.showRect(self.startPoint, self.endPoint)

    def showRect(self, startPoint, endPoint):
        self.rubberBand.reset(QGis.Polygon)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPoint(startPoint.x(), startPoint.y())
        point2 = QgsPoint(startPoint.x(), endPoint.y())
        point3 = QgsPoint(endPoint.x(), endPoint.y())
        point4 = QgsPoint(endPoint.x(), startPoint.y())

        self.rubberBand.addPoint(point1, False)
        self.rubberBand.addPoint(point2, False)
        self.rubberBand.addPoint(point3, False)
        self.rubberBand.addPoint(point4, True)    # true to update canvas
        self.rubberBand.show()

    def rectangle(self):
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():

            return None

        return QgsRectangle(self.startPoint, self.endPoint)

    #def deactivate(self):
    #   super(RectangleMapTool, self).deactivate()
    #self.deactivated.emit()


class RectangleMapTool(QgsMapToolEmitPoint):

    rectangleDrawed = pyqtSignal(QgsRectangle, object)


    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.rubberBand = QgsRubberBand(self.canvas, QGis.Polygon)
        self.rubberBand.setColor(Qt.red)
        self.rubberBand.setWidth(1)
        self.reset()

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QGis.Polygon)

    def canvasPressEvent(self, e):
        self.startPoint = self.toMapCoordinates(e.pos())
        self.endPoint = self.startPoint
        self.isEmittingPoint = True
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, e):
        self.isEmittingPoint = False


        wkt = self.canvas.mapSettings().destinationCrs().toWkt()
        r = self.rectangle()
        self.reset()

        if wkt is not None and r is not None:
            self.rectangleDrawed.emit(r, wkt)


    def canvasMoveEvent(self, e):

        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(e.pos())
        self.showRect(self.startPoint, self.endPoint)

    def showRect(self, startPoint, endPoint):
        self.rubberBand.reset(QGis.Polygon)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPoint(startPoint.x(), startPoint.y())
        point2 = QgsPoint(startPoint.x(), endPoint.y())
        point3 = QgsPoint(endPoint.x(), endPoint.y())
        point4 = QgsPoint(endPoint.x(), startPoint.y())

        self.rubberBand.addPoint(point1, False)
        self.rubberBand.addPoint(point2, False)
        self.rubberBand.addPoint(point3, False)
        self.rubberBand.addPoint(point4, True)    # true to update canvas
        self.rubberBand.show()

    def rectangle(self):
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():

            return None

        return QgsRectangle(self.startPoint, self.endPoint)

    #def deactivate(self):
    #   super(RectangleMapTool, self).deactivate()
    #self.deactivated.emit()



def tests():

    print(paste_band_settings(paste_test))
    print(paste_band_settings('foo'))

if __name__ == '__main__':
    tests()
    print('Done')