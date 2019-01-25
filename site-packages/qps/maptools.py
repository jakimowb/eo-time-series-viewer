# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              maptools.py

                              -------------------
        begin                : 2019-01-20
        git sha              : $Format:%H$
        copyright            : (C) 2019 by benjamin jakimow
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
from qps.utils import *


def createCursor(resourcePath:str):
    """
    Creates a QCursor from a icon path
    :param resourcePath: str
    :return: QCursor
    """
    icon = QIcon(resourcePath)
    app = QgsApplication.instance()
    activeX = activeY = 13
    if icon.isNull():
        print('Unable to load icon from {}. Maybe resources not initialized?'.format(resourcePath))
    scale = Qgis.UI_SCALE_FACTOR * app.fontMetrics().height() / 32.
    size = QSize(scale * 32, scale * 32)
    cursor = QCursor(icon.pixmap(size), scale * activeX, scale * activeY)
    return cursor


class MapTools(object):
    """
    Static class to support handling of QgsMapTools.
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
    def create(mapToolKey:str, canvas, *args, activate=True, **kwds)->QgsMapTool:
        """
        Creates
        :param mapToolKey: str, identifies the requested QgsMapTool, e.g. 'ZOOM_IN'
        :param canvas: QgsMapCanvas to set the QgsMapTool on
        :param activate: bool, set True (default) to set the QgsMapTool to the QgsMapCanvas `canvas`
        :param args: optional arguments
        :param kwds: optional keywords
        :return: QgsMapTool
        """
        assert isinstance(mapToolKey, str)
        mapToolKey = mapToolKey.upper()
        assert mapToolKey in MapTools.mapToolKeys(), 'Unknown MapTool key "{}"'.format(mapToolKey)
        assert isinstance(canvas, QgsMapCanvas)

        mapTool = None
        if mapToolKey == MapTools.ZoomIn:
            mapTool = QgsMapToolZoom(canvas, False)
        elif mapToolKey == MapTools.ZoomOut:
            mapTool = QgsMapToolZoom(canvas, True)
        elif mapToolKey == MapTools.Pan:
            mapTool = QgsMapToolPan(canvas)
        elif mapToolKey == MapTools.ZoomPixelScale:
            mapTool = PixelScaleExtentMapTool(canvas)
        elif mapToolKey == MapTools.ZoomFull:
            mapTool = FullExtentMapTool(canvas)
        elif mapToolKey == MapTools.CursorLocation:
            mapTool = CursorLocationMapTool(canvas, *args, **kwds)
        elif mapToolKey == MapTools.MoveToCenter:
            mapTool = CursorLocationMapTool(canvas, *args, **kwds)
            mapTool.sigLocationRequest.connect(canvas.setCenter)
        elif mapToolKey == MapTools.SpectralProfile:
            mapTool = SpectralProfileMapTool(canvas, *args, **kwds)
        elif mapToolKey == MapTools.TemporalProfile:
            mapTool = TemporalProfileMapTool(canvas, *args, **kwds)
        else:
            raise NotImplementedError('mapToolKey {}'.format(mapToolKey))

        if activate:
            canvas.setMapTool(mapTool)

        return mapTool

    @staticmethod
    def mapToolKeys()->list:
        """
        Returns all keys which can be used to return a QgsMapTool with `MapTools.create(key:str, canvas:QgsMapCanvas, *args, **kwds)`.
        :return: [list-of-str]
        """
        return [MapTools.__dict__[k] for k in MapTools.__dict__.keys()
                if isinstance(MapTools.__dict__[k], str) and not k.startswith('_')]


class CursorLocationMapTool(QgsMapToolEmitPoint):
    """
    A QgsMapTool to collect SpatialPoints
    """
    sigLocationRequest = pyqtSignal([SpatialPoint], [SpatialPoint, QgsMapCanvas])

    def __init__(self, canvas:QgsMapCanvas, showCrosshair:bool=True):
        """
        :param canvas: QgsMapCanvas
        :param showCrosshair: bool, if True (default), a crosshair appears for some milliseconds to highlight
            the selected location
        """
        self.mShowCrosshair = showCrosshair

        self.mCrosshairTime = 250

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

    def setStyle(self, color=None, brushStyle=None, fillColor=None, lineStyle=None):
        """
        Sets the Croshsair style
        :param color:
        :param brushStyle:
        :param fillColor:
        :param lineStyle:
        :return:
        """
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

                # remove crosshair after a short while
                QTimer.singleShot(self.mCrosshairTime, self.hideRubberband)

            pt = SpatialPoint(crs, geoPoint)
            self.sigLocationRequest[SpatialPoint].emit(pt)
            self.sigLocationRequest[SpatialPoint, QgsMapCanvas].emit(pt, self.canvas())

    def hideRubberband(self):
        """
        Hides the rubberband
        """
        self.rubberband.reset()

class PixelScaleExtentMapTool(QgsMapTool):
    """
    A QgsMapTool to scale the QgsMapCanvas to the pixel resolution of a selected QgsRasterLayer pixel.
    """
    def __init__(self, canvas):
        super(PixelScaleExtentMapTool, self).__init__(canvas)
        #see defintion getThemePixmap(const QString &):QPixmap in qgsapplication.cpp
        self.mCursor = createCursor(':/qps/ui/icons/cursor_zoom_pixelscale.svg')
        self.setCursor(self.mCursor)
        canvas.setCursor(self.mCursor)

    def flags(self):
        return QgsMapTool.Transient

    def canvasReleaseEvent(self, mouseEvent):

        unitsPxX = []
        unitsPxY = []
        for lyr in self.canvas().layers():
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
            width = f * self.canvas().size().width() * unitsPxX #width in map units
            height = f * self.canvas().size().height() * unitsPxY #height in map units

            center = SpatialPoint.fromMapCanvasCenter(self.canvas())
            extent = SpatialExtent(center.crs(), 0, 0, width, height)
            extent.setCenter(center, center.crs())
            self.canvas().setExtent(extent)


class FullExtentMapTool(QgsMapTool):
    """
    A QgsMapTool to scale a QgsMapCanvas to the full extent of all available QgsMapLayers.
    """
    def __init__(self, canvas):
        super(FullExtentMapTool, self).__init__(canvas)
        self.mCursor = createCursor(':/qps/ui/icons/cursor_zoom_fullextent.svg')
        self.setCursor(self.mCursor)
        canvas.setCursor(self.mCursor)

    def canvasReleaseEvent(self, mouseEvent):
        self.canvas().zoomToFullExtent()

    def flags(self):
        return QgsMapTool.Transient


class PointLayersMapTool(CursorLocationMapTool):

    def __init__(self, canvas):
        super(PointLayersMapTool, self).__init__(self, canvas)
        self.layerType = QgsMapToolIdentify.AllLayers
        self.identifyMode = QgsMapToolIdentify.LayerSelection
        QgsMapToolIdentify.__init__(self, canvas)

class SpatialExtentMapTool(QgsMapToolEmitPoint):
    """
    A QgsMapTool to select a SpatialExtent
    """
    sigSpatialExtentSelected = pyqtSignal(SpatialExtent)

    def __init__(self, canvas:QgsMapCanvas):
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.rubberBand = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)
        self.setStyle(Qt.red, 1)
        self.reset()

    def setStyle(self, color:QColor, width:int):
        """
        Sets the style of the rectangle shows when selecting the SpatialExtent
        :param color: QColor
        :param width: int
        """
        self.rubberBand.setColor(color)
        self.rubberBand.setWidth(width)

    def reset(self):
        """
        Removes the drawn rectangle
        """
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

        crs = self.canvas().mapSettings().destinationCrs()
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


class RectangleMapTool(QgsMapToolEmitPoint):

    rectangleDrawed = pyqtSignal(QgsRectangle, object)


    def __init__(self, canvas):

        QgsMapToolEmitPoint.__init__(self, canvas)
        self.rubberBand = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)
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


        wkt = self.canvas().mapSettings().destinationCrs().toWkt()
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


class TemporalProfileMapTool(CursorLocationMapTool):
    def __init__(self, *args, **kwds):
        super(TemporalProfileMapTool, self).__init__(*args, **kwds)


class SpectralProfileMapTool(CursorLocationMapTool):
    def __init__(self, *args, **kwds):
        super(SpectralProfileMapTool, self).__init__(*args, **kwds)


