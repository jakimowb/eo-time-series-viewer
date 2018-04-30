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

from qgis import *
from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtXml import *
from PyQt5.QtXmlPatterns import *
import six
import xml.etree
from qgis.core import *

from timeseriesviewer import SETTINGS
from timeseriesviewer.main import SpatialExtent, SpatialPoint



class CursorLocationMapTool(QgsMapToolEmitPoint):

    sigLocationRequest = pyqtSignal(SpatialPoint)

    def __init__(self, canvas, showCrosshair=True):
        self.mShowCrosshair = showCrosshair
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.marker = QgsVertexMarker(self.canvas)
        self.rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)

        color = QColor('red')
        self.mButtons = [Qt.LeftButton]
        self.rubberband.setLineStyle(Qt.SolidLine)
        self.rubberband.setColor(color)
        self.rubberband.setWidth(2)



        self.marker.setColor(color)
        self.marker.setPenWidth(3)
        self.marker.setIconSize(5)
        self.marker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X

    def setMouseButtons(self, listOfButtons):
        assert isinstance(listOfButtons)
        self.mButtons = listOfButtons

    def canvasPressEvent(self, e):
        assert isinstance(e, QgsMapMouseEvent)
        if e.button() in self.mButtons:
            geoPoint = self.toMapCoordinates(e.pos())
            self.marker.setCenter(geoPoint)
        #self.marker.show()

    def setStyle(self, color=None, brushStyle=None, fillColor=None, lineStyle=None):
        if color:
            self.rubberband.setColor(color)
        if brushStyle:
            self.rubberband.setBrushStyle(brushStyle)
        if fillColor:
            self.rubberband.setFillColor(fillColor)
        if lineStyle:
            self.rubberband.setLineStyle(lineStyle)
    def canvasReleaseEvent(self, e):
        if e.button() in self.mButtons:

            pixelPoint = e.pixelPoint()

            crs = self.canvas.mapSettings().destinationCrs()
            self.marker.hide()
            geoPoint = self.toMapCoordinates(pixelPoint)
            if self.mShowCrosshair:
                #show a temporary crosshair
                ext = SpatialExtent.fromMapCanvas(self.canvas)
                cen = geoPoint
                geom = QgsGeometry()
                lineH = QgsLineString([QgsPoint(ext.upperLeftPt().x(),cen.y()), QgsPoint(ext.lowerRightPt().x(), cen.y())])
                lineV = QgsLineString([QgsPoint(cen.x(), ext.upperLeftPt().y()), QgsPoint(cen.x(), ext.lowerRightPt().y())])

                geom.addPart(lineH, QgsWkbTypes.LineGeometry)
                geom.addPart(lineV, QgsWkbTypes.LineGeometry)
                self.rubberband.addGeometry(geom, None)
                self.rubberband.show()
                #remove crosshair after 0.25 sec
                QTimer.singleShot(250, self.hideRubberband)

            self.sigLocationRequest.emit(SpatialPoint(crs, geoPoint))

    def hideRubberband(self):
        self.rubberband.reset()

class PointLayersMapTool(CursorLocationMapTool):

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
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.setStyle(Qt.red, 1)
        self.reset()

    def setStyle(self, color, width):
        self.rubberBand.setColor(color)
        self.rubberBand.setWidth(width)

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)

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
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(startPoint.x(), endPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(endPoint.x(), startPoint.y())

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
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(Qt.red)
        self.rubberBand.setWidth(1)
        self.reset()

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)

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
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(startPoint.x(), endPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(endPoint.x(), startPoint.y())

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



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    import example.Images
    lyr1 = QgsRasterLayer(example.Images.Img_2012_05_09_LE72270652012130EDC00_BOA)
    lyr2 = QgsRasterLayer(example.Images.Img_2012_05_09_LE72270652012130EDC00_BOA)
    lyr3 = QgsRasterLayer(example.Images.Img_2012_05_09_LE72270652012130EDC00_BOA)

    QgsProject.instance().addMapLayers([lyr1, lyr2, lyr3])

    w = QWidget()
    l = QHBoxLayout()
    canvas1 = QgsMapCanvas()
    canvas1.setWindowTitle('Canvas1')
    canvas1.setLayerSet([QgsMapCanvasLayer(lyr1)])
    canvas1.setExtent(lyr1.extent())
    mt = CursorLocationMapTool(canvas1)
    canvas1.setMapTool(mt)
    canvas2 = QgsMapCanvas()
    canvas2.setWindowTitle('Canvas2')
    canvas2.setLayerSet([QgsMapCanvasLayer(lyr2)])
    canvas2.setExtent(lyr2.extent())
    canvas3 = QgsMapCanvas()
    canvas3.setWindowTitle('Canvas3')
    #canvas3.setLayerSet([QgsMapCanvasLayer(lyr3)])
    #canvas3.setExtent(lyr3.extent())

    l.addWidget(canvas1)
    l.addWidget(canvas2)
    l.addWidget(canvas3)
    w.setLayout(l)

    w.show()

    qgsApp.exec_()
    qgsApp.exitQgis()
