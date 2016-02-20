from qgis.core import *
from qgis.gui import *
import qgis
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import six


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



class PointMapTool(QgsMapToolEmitPoint):

    coordinateSelected = pyqtSignal(QgsPoint, object)


    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.marker = QgsVertexMarker(self.canvas)
        self.marker.setColor(Qt.red)
        self.marker.setIconSize(5)
        self.marker.setIconType(QgsVertexMarker.ICON_CROSS) # or ICON_CROSS, ICON_X
        self.marker.setPenWidth(3)


    def canvasPressEvent(self, e):
        point = self.toMapCoordinates(e.pos())

        self.marker.setCenter(point)
        self.marker.show()

    def canvasReleaseEvent(self, e):
        point = self.toMapCoordinates(e.pos())
        wkt = self.canvas.mapSettings().destinationCrs().toWkt()
        if wkt:
            self.coordinateSelected.emit(point, wkt)
            self.marker.setCenter(point)
            self.marker.hide()




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
