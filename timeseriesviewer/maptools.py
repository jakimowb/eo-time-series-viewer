# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              maptools.py
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
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

import numpy as np
from timeseriesviewer.utils import *



class MapTools(object):
    """
    Static class to support handling of nQgsMapTools.
    """
    def __init__(self):
        raise Exception('This class is not for any instantiation')
    ZoomIn = 'ZOOM_IN'
    ZoomOut = 'ZOOM_OUT'
    ZoomFull = 'ZOOM_FULL'
    Pan = 'PAN'
    ZoomPixelScale = 'ZOOM_PIXEL_SCALE'
    CursorLocation = 'CURSOR_LOCATION'
    SpectralProfile = 'SPECTRAL_PROFILE'
    TemporalProfile = 'TEMPORAL_PROFILE'
    MoveToCenter = 'MOVE_CENTER'

    @staticmethod
    def copy(mapTool):
        assert isinstance(mapTool, QgsMapTool)
        s = ""


    @staticmethod
    def create(mapToolKey, canvas, *args, **kwds):
        assert mapToolKey in MapTools.mapToolKeys()

        assert isinstance(canvas, QgsMapCanvas)

        if mapToolKey == MapTools.ZoomIn:
            return QgsMapToolZoom(canvas, False)
        if mapToolKey == MapTools.ZoomOut:
            return QgsMapToolZoom(canvas, True)
        if mapToolKey == MapTools.Pan:
            return QgsMapToolPan(canvas)
        if mapToolKey == MapTools.ZoomPixelScale:
            return PixelScaleExtentMapTool(canvas)
        if mapToolKey == MapTools.ZoomFull:
            return FullExtentMapTool(canvas)
        if mapToolKey == MapTools.CursorLocation:
            return CursorLocationMapTool(canvas, *args, **kwds)
        if mapToolKey == MapTools.MoveToCenter:
            tool = CursorLocationMapTool(canvas, *args, **kwds)
            tool.sigLocationRequest.connect(canvas.setCenter)
            return tool
        if mapToolKey == MapTools.SpectralProfile:
            return SpectralProfileMapTool(canvas, *args, **kwds)
        if mapToolKey == MapTools.TemporalProfile:
            return TemporalProfileMapTool(canvas, *args, **kwds)

        raise Exception('Unknown mapToolKey {}'.format(mapToolKey))


    @staticmethod
    def mapToolKeys():
        return [MapTools.__dict__[k] for k in MapTools.__dict__.keys() if not k.startswith('_')]

"""
class CursorLocationMapTool(QgsMapToolEmitPoint):

    sigLocationRequest = pyqtSignal([SpatialPoint],[SpatialPoint, QgsMapCanvas])

    def __init__(self, canvas, showCrosshair=True, purpose=None):
        self.mShowCrosshair = showCrosshair
        self.mCanvas = canvas
        self.mPurpose = purpose
        QgsMapToolEmitPoint.__init__(self, self.mCanvas)

        self.mMarker = QgsVertexMarker(self.mCanvas)
        self.mRubberband = QgsRubberBand(self.mCanvas, QGis.Polygon)

        color = QColor('red')

        self.mRubberband.setLineStyle(Qt.SolidLine)
        self.mRubberband.setColor(color)
        self.mRubberband.setWidth(2)

        self.mMarker.setColor(color)
        self.mMarker.setPenWidth(3)
        self.mMarker.setIconSize(5)
        self.mMarker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X

    def canvasPressEvent(self, e):
        geoPoint = self.toMapCoordinates(e.pos())
        self.mMarker.setCenter(geoPoint)

    def setStyle(self, color=None, brushStyle=None, fillColor=None, lineStyle=None):
        if color:
            self.mRubberband.setColor(color)
        if brushStyle:
            self.mRubberband.setBrushStyle(brushStyle)
        if fillColor:
            self.mRubberband.setFillColor(fillColor)
        if lineStyle:
            self.mRubberband.setLineStyle(lineStyle)

    def canvasReleaseEvent(self, e):


        pixelPoint = e.pixelPoint()

        crs = self.mCanvas.mapSettings().destinationCrs()
        self.mMarker.hide()
        geoPoint = self.toMapCoordinates(pixelPoint)
        if self.mShowCrosshair:
            #show a temporary crosshair
            ext = SpatialExtent.fromMapCanvas(self.mCanvas)
            cen = geoPoint
            geom = QgsGeometry()
            geom.addPart([QgsPoint(ext.upperLeftPt().x(),cen.y()), QgsPoint(ext.lowerRightPt().x(), cen.y())],
                          QGis.Line)
            geom.addPart([QgsPoint(cen.x(), ext.upperLeftPt().y()), QgsPoint(cen.x(), ext.lowerRightPt().y())],
                          QGis.Line)
            self.mRubberband.addGeometry(geom, None)
            self.mRubberband.show()
            #remove crosshair after 0.25 sec
            QTimer.singleShot(250, self.hideRubberband)

        pt = SpatialPoint(crs, geoPoint)
        self.sigLocationRequest[SpatialPoint].emit(pt)
        self.sigLocationRequest[SpatialPoint, QgsMapCanvas].emit(pt, self.canvas())

    def hideRubberband(self):
        self.mRubberband.reset()
"""



class CursorLocationMapTool(QgsMapToolEmitPoint):

    sigLocationRequest = pyqtSignal([SpatialPoint],[SpatialPoint, QgsMapCanvas])

    def __init__(self, canvas, showCrosshair=True):
        self.mShowCrosshair = showCrosshair
        QgsMapToolEmitPoint.__init__(self, canvas)
        self.marker = QgsVertexMarker(self.canvas())
        self.rubberband = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)

        color = QColor('red')
        self.mButtons = [Qt.LeftButton]
        self.rubberband.setLineStyle(Qt.SolidLine)
        self.rubberband.setColor(color)
        self.rubberband.setWidth(2)

        self.marker.setColor(color)
        self.marker.setPenWidth(3)
        self.marker.setIconSize(5)
        self.marker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X
        self.hideRubberband()



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

            crs = self.canvas().mapSettings().destinationCrs()
            self.marker.hide()
            geoPoint = self.toMapCoordinates(pixelPoint)
            if self.mShowCrosshair:
                #show a temporary crosshair
                ext = SpatialExtent.fromMapCanvas(self.canvas())
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

            pt = SpatialPoint(crs, geoPoint)
            self.sigLocationRequest[SpatialPoint].emit(pt)
            self.sigLocationRequest[SpatialPoint, QgsMapCanvas].emit(pt, self.canvas())
    def hideRubberband(self):
        self.rubberband.reset()


class SpectralProfileMapTool(CursorLocationMapTool):

    def __init__(self, *args, **kwds):
        super(SpectralProfileMapTool, self).__init__(*args, **kwds)

class PixelScaleExtentMapTool(QgsMapTool):
    def __init__(self, canvas):
        super(PixelScaleExtentMapTool, self).__init__(canvas)
        self.canvas = canvas

    def flags(self):
        return QgsMapTool.Transient


    def canvasReleaseEvent(self, mouseEvent):
        layers = self.canvas.layers()

        unitsPxX = []
        unitsPxY = []
        for lyr in self.canvas.layers():
            if isinstance(lyr, QgsRasterLayer):
                unitsPxX.append(lyr.rasterUnitsPerPixelX())
                unitsPxY.append(lyr.rasterUnitsPerPixelY())

        if len(unitsPxX) > 0:
            unitsPxX = np.asarray(unitsPxX)
            unitsPxY = np.asarray(unitsPxY)
            if True:
                # zoom to largest pixel size
                i = np.nanargmax(unitsPxX)
            else:
                # zoom to smallest pixel size
                i = np.nanargmin(unitsPxX)
            unitsPxX = unitsPxX[i]
            unitsPxY = unitsPxY[i]
            f = 0.2
            width = f * self.canvas.size().width() * unitsPxX #width in map units
            height = f * self.canvas.size().height() * unitsPxY #height in map units


            center = SpatialPoint.fromMapCanvasCenter(self.canvas)
            extent = SpatialExtent(center.crs(), 0, 0, width, height)
            extent.setCenter(center, center.crs())
            self.canvas.setExtent(extent)
        s = ""


class FullExtentMapTool(QgsMapTool):
    def __init__(self, canvas):
        super(FullExtentMapTool, self).__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, mouseEvent):
        self.canvas.zoomToFullExtent()

    def flags(self):
        return QgsMapTool.Transient

class PointLayersMapTool(CursorLocationMapTool):

    def __init__(self, canvas):
        super(PointLayersMapTool, self).__init__(self, canvas)
        self.layerType = QgsMapToolIdentify.AllLayers
        self.identifyMode = QgsMapToolIdentify.LayerSelection
        QgsMapToolIdentify.__init__(self, canvas)

class SpatialExtentMapTool(QgsMapToolEmitPoint):
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



class TemporalProfileMapTool(CursorLocationMapTool):

    def __init__(self, *args, **kwds):
        super(TemporalProfileMapTool, self).__init__(*args, **kwds)

