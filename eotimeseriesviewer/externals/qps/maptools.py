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

import enum, math
from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

import numpy as np
from .utils import *


def tr(t:str)->str:
    return t


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
    size = QSize(int(scale * 32), int(scale * 32))
    cursor = QCursor(icon.pixmap(size), int(scale * activeX), int(scale * activeY))
    return cursor


def createQgsMapCanvasUserInputWidget(canvas:QgsMapCanvas)->QgsUserInputWidget:
    """
    Create a QgsUserInputWidget that is linked to the top-right QgsMapCanvas corner (as in the QGIS Desktop main canvas).
    :param canvas: QgsMapCanvas
    :return: QgsUserInputWidget
    """
    assert isinstance(canvas, QgsMapCanvas)
    mUserInputWidget = canvas.findChild(QgsUserInputWidget)
    if not isinstance(mUserInputWidget, QgsUserInputWidget):
        mUserInputWidget = QgsUserInputWidget(canvas)
        mUserInputWidget.setObjectName('UserInputDockWidget')
        mUserInputWidget.setAnchorWidget(canvas)
        mUserInputWidget.setAnchorWidgetPoint(QgsFloatingWidget.TopRight)
        mUserInputWidget.setAnchorPoint(QgsFloatingWidget.TopRight)
    return mUserInputWidget

class MapTools(enum.Enum):
    """
    Static class to support the creation of QgsMapTools.
    """
    #def __init__(self):
    #    raise Exception('This class is not for any instantiation')
    ZoomIn = 'ZOOM_IN'
    ZoomOut = 'ZOOM_OUT'
    ZoomFull = 'ZOOM_FULL'
    Pan = 'PAN'
    ZoomPixelScale = 'ZOOM_PIXEL_SCALE'
    CursorLocation = 'CURSOR_LOCATION'
    SpectralProfile = 'SPECTRAL_PROFILE'
    TemporalProfile = 'TEMPORAL_PROFILE'
    MoveToCenter = 'MOVE_CENTER'
    AddFeature = 'ADD_FEATURE'
    SelectFeature = 'SELECT_FEATURE'
    SelectFeatureByPolygon = 'SELECT_FEATURE_POLYGON'
    SelectFeatureByFreehand = 'SELECT_FEATURE_FREEHAND'
    SelectFeatureByRadius = 'SELECT_FEATURE_RADIUS'

    @staticmethod
    def toMapToolEnum(arg):
        if isinstance(arg, str):
            names = MapTools.mapToolNames()
            values = MapTools.mapToolValues()
            if arg in names:
                arg = MapTools.__members__.get(arg)
            elif arg in values:
                arg = MapTools.__members__.get(names[values.index(arg)])
        assert isinstance(arg, MapTools)
        return arg

    @staticmethod
    def create(mapToolEnum, canvas, *args, activate=True, **kwds)->QgsMapTool:
        """
        Creates
        :param mapToolEnum: str, identifies the requested QgsMapTool, e.g. 'ZOOM_IN'
        :param canvas: QgsMapCanvas to set the QgsMapTool on
        :param activate: bool, set True (default) to set the QgsMapTool to the QgsMapCanvas `canvas`
        :param args: optional arguments
        :param kwds: optional keywords
        :return: QgsMapTool
        """

        mapToolEnum = MapTools.toMapToolEnum(mapToolEnum)

        assert isinstance(mapToolEnum, MapTools)
        assert isinstance(canvas, QgsMapCanvas)

        mapTool = None
        if mapToolEnum == MapTools.ZoomIn:
            mapTool = QgsMapToolZoom(canvas, False)
        elif mapToolEnum == MapTools.ZoomOut:
            mapTool = QgsMapToolZoom(canvas, True)
        elif mapToolEnum == MapTools.Pan:
            mapTool = QgsMapToolPan(canvas)
        elif mapToolEnum == MapTools.ZoomPixelScale:
            mapTool = PixelScaleExtentMapTool(canvas)
        elif mapToolEnum == MapTools.ZoomFull:
            mapTool = FullExtentMapTool(canvas)
        elif mapToolEnum == MapTools.CursorLocation:
            mapTool = CursorLocationMapTool(canvas, *args, **kwds)
        elif mapToolEnum == MapTools.MoveToCenter:
            mapTool = CursorLocationMapTool(canvas, *args, **kwds)
            mapTool.sigLocationRequest.connect(canvas.setCenter)
        elif mapToolEnum == MapTools.SpectralProfile:
            mapTool = SpectralProfileMapTool(canvas, *args, **kwds)
        elif mapToolEnum == MapTools.TemporalProfile:
            mapTool = TemporalProfileMapTool(canvas, *args, **kwds)
        elif mapToolEnum == MapTools.AddFeature:
            mapTool = QgsMapToolAddFeature(canvas, *args, **kwds)
        elif mapToolEnum == MapTools.SelectFeature:
            mapTool = QgsMapToolSelect(canvas)
            mapTool.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        elif mapToolEnum == MapTools.SelectFeatureByFreehand:
            mapTool = QgsMapToolSelect(canvas)
            mapTool.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectFreehand)
        elif mapToolEnum == MapTools.SelectFeatureByPolygon:
            mapTool = QgsMapToolSelect(canvas)
            mapTool.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectPolygon)
        elif mapToolEnum == MapTools.SelectFeatureByRadius:
            mapTool = QgsMapToolSelect(canvas)
            mapTool.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        else:
            raise NotImplementedError('Unknown MapTool "{}"'.format(mapToolEnum))

        if activate:
            canvas.setMapTool(mapTool)

        return mapTool

    @staticmethod
    def mapToolKeys()->list:
        import warnings
        warnings.warn('Deprecated. use .mapToolValues() instead', DeprecationWarning)
        return MapTools.mapToolValues()

    @staticmethod
    def mapToolNames() -> list:
        return [k.name for k in list(MapTools)]

    @staticmethod
    def mapToolValues()->list:
        return [k.value for k in list(MapTools)]

    @staticmethod
    def mapToolEnums()->list:
        return list(MapTools.__members__.values())

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


class MapToolCenter(CursorLocationMapTool):
    """This maptool centers a QgsMapCanvas on the clicked position"""

    def __init__(self, canvas:QgsMapCanvas):
        super(MapToolCenter, self).__init__(canvas)
        self.sigLocationRequest.connect(lambda point: self.canvas().setCenter(point))

class PixelScaleExtentMapTool(QgsMapTool):
    """
    A QgsMapTool to scale the QgsMapCanvas to the pixel resolution of a selected QgsRasterLayer pixel.
    """
    def __init__(self, canvas):
        super(PixelScaleExtentMapTool, self).__init__(canvas)

        self.mCursor = createCursor(':/qps/ui/icons/cursor_zoom_pixelscale.svg')
        self.setCursor(self.mCursor)
        canvas.setCursor(self.mCursor)

    def flags(self):
        """

        :return:
        """
        return QgsMapTool.Transient

    def canvasReleaseEvent(self, mouseEvent:QgsMapMouseEvent):
        """

        :param mouseEvent:
        :return:
        """
        crs = self.canvas().mapSettings().destinationCrs()
        pt = SpatialPoint(crs, mouseEvent.mapPoint())
        center = SpatialPoint.fromMapCanvasCenter(self.canvas())

        unitsPxX = None
        unitsPxY = None


        for lyr in self.canvas().layers():
            if isinstance(lyr, QgsRasterLayer) and lyr.extent().contains(pt.toCrs(lyr.crs())):
                unitsPxX = lyr.rasterUnitsPerPixelX()
                unitsPxY = lyr.rasterUnitsPerPixelY()
                break

        if isinstance(unitsPxX, (int, float)) and unitsPxX > 0:
            width = self.canvas().size().width() * unitsPxX #width in map units
            height = self.canvas().size().height() * unitsPxY #height in map units
            extent = SpatialExtent(crs, 0, 0, width, height)
            extent.setCenter(center, crs=crs)
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
        super(SpatialExtentMapTool, self).__init__(canvas)
        self.isEmittingPoint = False
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
            self.sigSpatialExtentSelected.emit(extent)


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


class QgsFeatureAction(QAction):
    """
    This is a python copy of the qgis/app/QgsFeatureAction.cpp
    """
    from weakref import WeakKeyDictionary
    sLastUsedValues = WeakKeyDictionary()

    def __init__(self, name:str, f:QgsFeature, layer:QgsVectorLayer, actionID:id, defaultAttr:int, parent:QObject=None):


        super(QgsFeatureAction, self).__init__(name, parent)
        
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.mFeature = f
        self.mActionId = actionID
        self.mIdx = defaultAttr
        self.mFeatureSaved = False
        self.mForceSuppressFormPopup = False


    def execute(self):
        self.mLayer.actions().doAction(self.mActionId, self.mFeature, self.mIdx)



    def newDialog(self, cloneFeatures:bool)->QgsAttributeDialog:
        """
        Creates a new dialog
        :param cloneFeatures: bool
        :return: QgsAttributeDialog
        """
        f = QgsFeature(self.mFeature) if cloneFeatures else self.mFeature

        context = QgsAttributeEditorContext()

        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())

        context.setDistanceArea(myDa)
        #context.setVectorLayerTools()
        #context.setMapCanvas()
        context.setFormMode(QgsAttributeEditorContext.StandaloneDialog)

        dialog = QgsAttributeDialog(self.mLayer, f, cloneFeatures, self.parentWidget(), True, context)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.Tool)
        dialog.setObjectName('featureaction {} {}'.format(self.mLayer.id(), f.id()))


        actions = self.mLayer.actions().actions("Feature")
        if len(actions) == 0:
            dialog.setContextMenuPolicy(Qt.ActionsContextMenu)

        a = QAction(tr("Run Actions"), dialog)
        a.setEnabled(False)
        dialog.addAction(a)

        for action in actions:
            assert isinstance(action, QgsAction)
            if not action.runable():
                continue

            if not self.mLayer.isEditable() and action.isEnabledOnlyWhenEditable():
                continue

            feat = dialog.feature()
            a = QgsFeatureAction(action.name(), feat, self.mLayer, action.id(), -1, dialog)
            dialog.addAction(a)
            a.triggered.connect(a.execute)

            pb = dialog.findChild(QAbstractButton, action.name())
            if isinstance(pb, QAbstractButton):
                pb.clicked.connect(a.execute)

        return dialog

    def viewFeatureForm(self, h:QgsHighlight)->bool:
    
        if not self.mLayer or not self.mFeature:
            return False

        name = "featureactiondlg:{}:{}".format(self.mLayer.id(), self.mFeature.id() )
        
        
        #QgsAttributeDialog * dialog = QgisApp::instance()->findChild < QgsAttributeDialog * > (name);
        #if (dialog)
        #    {
        #        delete
        #    h;
        #    dialog->raise ();
        #    dialog->activateWindow();
        #    return true;
        #    }

        dialog = self.newDialog(True)
        dialog.setHighlight(h)
        #// delete the dialog when it is closed
        dialog.setAttribute(Qt.WA_DeleteOnClose )
        dialog.show()

        return True




    def editFeature(self, showModal:bool)->bool:

        if not self.mLayer:
            return False

        if showModal:

            dialog = self.newDialog( False)

            if not self.mFeature.isValid():
                dialog.setMode( QgsAttributeEditorContext.AddFeatureMode )

            rv = dialog.exec()
            self.mFeature.setAttributes( dialog.feature().attributes())
            return rv

        else:

            name = "featureactiondlg:{}:{}".format(self.mLayer.id(), self.mFeatureid() )

            #QgsAttributeDialog *dialog = QgisApp::instance()->findChild<QgsAttributeDialog *>( name );
            #if ( dialog )
            #{
            #  dialog->raise();
            #  return true;
            #}

            dialog = self.newDialog( False)

            if not self.mFeature.isValid():
                dialog.setMode(QgsAttributeEditorContext.AddFeatureMode )

            #// delete the dialog when it is closed
            dialog.setAttribute( Qt.WA_DeleteOnClose )
            dialog.show()


        return True



    def addFeature(self, defaultAttributes:dict, showModal:bool, scope:QgsExpressionContextScope):

        if not (isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable()):
            return

        reuseLastValues = bool(QgsSettings().value('qgis/digitizing/reuseLastValues', False))

        fields = self.mLayer.fields()
        initialAttributeValues = dict()


        context = self.mLayer.createExpressionContext()
        if scope:
            context.appendScope(scope)

        newFeature = QgsVectorLayerUtils.createFeature(self.mLayer, self.mFeature.geometry(), initialAttributeValues, context)


        self.mFeature = newFeature

        isDisabledAttributesValueDlg = bool(QgsSettings().value('qgis/digitizing/disable_enter_attribute_values_dialog', False))
        if not self.mLayer.isSpatial():
            isDisabledAttributesValueDlg = False

        if fields.count() == 0:
            isDisabledAttributesValueDlg = True

        opt = self.mLayer.editFormConfig().suppress()
        if opt == QgsEditFormConfig.SuppressOn:
            isDisabledAttributesValueDlg = True
        elif opt == QgsEditFormConfig.SuppressOff:
            isDisabledAttributesValueDlg = False

        if self.mForceSuppressFormPopup:
            isDisabledAttributesValueDlg = True

        if isDisabledAttributesValueDlg:
            self.mLayer.beginEditCommand(self.text())
            self.mFeatureSaved = self.mLayer.addFeature(self.mFeature)
            if self.mFeatureSaved:
                self.mLayer.endEditCommand()
                self.mLayer.triggerRepaint()
            else:
                self.mLayer.destroyEditComand()
        else:

            dialog = self.newDialog(False)
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.setMode(QgsAttributeEditorContext.AddFeatureMode)
            dialog.setEditCommandMessage(self.text())
            dialog.attributeForm().featureSaved.connect(self.onFeatureSaved)

            if not showModal:
                self.setParent(dialog)
                dialog.show()
                self.mFeature = None
                return True

            dialog.exec_()


        return self.mFeatureSaved


    def setForceSuppressFormPopup(self, force:bool):
        self.mForceSuppressFormPopup = force



    def onFeatureSaved(self, feature:QgsFeature):
        form = self.sender()
        if not isinstance(form, QgsAttributeForm):
            return


        #// Assign provider generated values
        if self.mFeature:
           self.mFeature = feature

        self.mFeatureSaved = True

        settings = QgsSettings()

        reuseLastValues = bool(settings.value("qgis/digitizing/reuseLastValues", False))
        #QgsDebugMsg(QStringLiteral("reuseLastValues: %1").arg(reuseLastValues));

        if reuseLastValues:
            fields = self.mLayer.fields()
            for idx in range(fields.count()):

                newValues = feature.attributes();
                origValues = self.sLastUsedValues[self.mLayer]

                if origValues[idx] != newValues.at(idx):

                    #QgsDebugMsg( QStringLiteral( "saving %1 for %2" ).arg( sLastUsedValues[mLayer][idx].toString() ).arg( idx ) );
                    self.sLastUsedValues[self.mLayer][idx] = newValues.at( idx )




class QgsMapToolDigitizeFeature(QgsMapToolCapture):

    digitizingCompleted = pyqtSignal(QgsFeature)
    digitizingFinished = pyqtSignal()



    def __init__(self, canvas:QgsMapCanvas, layer:QgsMapLayer, mode, cadDockWidget:QgsAdvancedDigitizingDockWidget):

        super(QgsMapToolDigitizeFeature, self).__init__(canvas, cadDockWidget, mode)

        self.mCheckGeometryType = True
        self.mLayer = layer
        self.mCurrentLayer = None
        #mToolName = tr( "Digitize feature" );
        #connect( QgisApp::instance(), &QgisApp::newProject, this, &QgsMapToolDigitizeFeature::stopCapturing );
        #connect( QgisApp::instance(), &QgisApp::projectRead, this, &QgsMapToolDigitizeFeature::stopCapturing );


    def digitized(self, f:QgsFeature):
        self.digitizingCompleted.emit(f)


    def activate(self):
        vlayer = self.mLayer
        if not isinstance(self.mLayer, QgsVectorLayer):
            vlayer = self.currentVectorLayer()

        if isinstance(vlayer, QgsVectorLayer) and vlayer.geometryType() == QgsWkbTypes.NullGeometry:
            f = QgsFeature()
            self.digitized(f)
            return


        if self.mLayer:
            # //remember current layer
            self.mCurrentLayer = self.canvas().currentLayer()
            #//set the layer with the given
            self.canvas().setCurrentLayer(self.mLayer)


        super(QgsMapToolDigitizeFeature, self).activate()

    def deactivate(self):
        super(QgsMapToolDigitizeFeature, self).deactivate()

        if self.mCurrentLayer:
            #//set the layer back to the one remembered
            self.canvas().setCurrentLayer(self.mCurrentLayer)
            self.digitizingFinished.emit()

    def checkGeometryType(self)->bool:
        return self.mCheckGeometryType


    def setCheckGeometryType(self, checkGeometryType:bool):

        self.mCheckGeometryType = checkGeometryType

    def cadCanvasReleaseEvent(self, e:QgsMapMouseEvent):

        vlayer = self.mLayer
        if not isinstance(vlayer, QgsVectorLayer):
            #//if no given layer take the current from canvas
            vlayer = self.currentVectorLayer()

        if not isinstance(vlayer, QgsVectorLayer):

            self.notifyNotVectorLayer()
            return

        layerWKBType = vlayer.wkbType()
        provider = vlayer.dataProvider()

        if not (provider.capabilities() & QgsVectorDataProvider.AddFeatures ):

            self.messageEmitted.emit("The data provider for this layer does not support the addition of features.", Qgis.Warning)

            return


        if not vlayer.isEditable():

            self.notifyNotEditableLayer()
            return


        #// POINT CAPTURING
        if self.mode() == self.CapturePoint:

            if e.button() != Qt.LeftButton:
                return

            #//check we only use this tool for point/multipoint layers
            if vlayer.geometryType() != QgsWkbTypes.PointGeometry and self.mCheckGeometryType:

                self.messageEmitted.emit("Wrong editing tool, cannot apply the 'capture point' tool on this vector layer", Qgis.Warning)
                return


            savePoint = None #; //point in layer coordinates
            isMatchPointZ = False
            try:

                fetchPoint = QgsPoint()
                res = self.fetchLayerPoint( e.mapPointMatch(), fetchPoint)
                if QgsWkbTypes.hasZ(fetchPoint.wkbType()):
                    isMatchPointZ = True

                if res == 0:

                    if isMatchPointZ:
                        savePoint = fetchPoint
                    else:
                        savePoint = QgsPoint(fetchPoint.x(), fetchPoint.y())

                else:

                    layerPoint = self.toLayerCoordinates( vlayer, e.mapPoint() )
                    if isMatchPointZ:
                        savePoint = QgsPoint(QgsWkbTypes.PointZ, layerPoint.x(), layerPoint.y(), fetchPoint.z() )
                    else:
                        savePoint = QgsPoint(layerPoint.x(), layerPoint.y())
            except QgsCsException as cse:
                self.messageEmitted.emit("Cannot transform the point to the layers coordinate system", Qgis.Warning )
                return


            #//only do the rest for provider with feature addition support
            #//note that for the grass provider, this will return false since
            #//grass provider has its own mechanism of feature addition
            if provider.capabilities() & QgsVectorDataProvider.AddFeatures:

                f = QgsFeature(vlayer.fields(), 0 )

                g = None
                if layerWKBType == QgsWkbTypes.Point:
                    g = QgsGeometry(savePoint )
                elif not QgsWkbTypes.isMultiType(layerWKBType) and QgsWkbTypes.hasZ( layerWKBType ):
                    g = QgsGeometry(QgsPoint(savePoint.x(), savePoint.y(), savePoint.z() if isMatchPointZ else self.defaultZValue() ) )
                elif QgsWkbTypes.isMultiType(layerWKBType) and not QgsWkbTypes.hasZ( layerWKBType ):
                    #g = QgsGeometry::fromMultiPointXY( QgsMultiPointXY() << savePoint );
                    g = QgsGeometry.fromMultiPointXY(savePoint)

                elif QgsWkbTypes.isMultiType(layerWKBType) and QgsWkbTypes.hasZ(layerWKBType):

                    mp = QgsMultiPoint()
                    mp.addGeometry(QgsPoint(QgsWkbTypes.PointZ, savePoint.x(), savePoint.y(), savePoint.z() if isMatchPointZ else self.defaultZValue() ) )
                    g = QgsGeometry()
                    g.set( mp )
                else:
                    #// if layer supports more types (mCheckGeometryType is false)
                    g = QgsGeometry(QgsPoint(savePoint))

                if QgsWkbTypes.hasM( layerWKBType ):
                    g.get().addMValue()


                f.setGeometry( g )
                f.setValid( True)

                self.digitized( f )

                #// we are done with digitizing for now so instruct advanced digitizing dock to reset its CAD points
                self.cadDockWidget().clearPoints()



        #// LINE AND POLYGON CAPTURING
        elif self.mode() == self.CaptureLine or self.mode() == self.CapturePolygon:

            #//check we only use the line tool for line/multiline layers
            if self.mode() == self.CaptureLine and vlayer.geometryType() != QgsWkbTypes.LineGeometry and self.mCheckGeometryType:

                self.messageEmitted.emit(tr("Wrong editing tool, cannot apply the 'capture line' tool on this vector layer"), Qgis.Warning )
                return


            #//check we only use the polygon tool for polygon/multipolygon layers
            if self.mode() == self.CapturePolygon and vlayer.geometryType() != QgsWkbTypes.PolygonGeometry and self.mCheckGeometryType:

              self.messageEmitted.emit( tr( "Wrong editing tool, cannot apply the 'capture polygon' tool on this vector layer" ), Qgis.Warning)
              return


            #//add point to list and to rubber band
            if e.button() == Qt.LeftButton:

                error = self.addVertex(e.mapPoint(), e.mapPointMatch() )
                if error == 1 :
                    #//current layer is not a vector layer
                    return

                elif error == 2:

                    #//problem with coordinate transformation
                    self.messageEmitted.emit( tr( "Cannot transform the point to the layers coordinate system" ), Qgis.Warning )
                    return

                self.startCapturing();

            elif e.button() == Qt.RightButton:

                #// End of string
                self.deleteTempRubberBand()

                #//lines: bail out if there are not at least two vertices
                if self.mode() == self.CaptureLine and self.size() < 2:

                    self.stopCapturing()
                    return


                #//polygons: bail out if there are not at least two vertices
                if self.mode() == self.CapturePolygon and self.size() < 3:

                    self.stopCapturing()
                    return;


                if self.mode() == self.CapturePolygon:
                    self.closePolygon()


                #//create QgsFeature with wkb representation
                f = QgsFeature(vlayer.fields(), 0 )

                #//does compoundcurve contain circular strings?
                #//does provider support circular strings?
                hasCurvedSegments = self.captureCurve().hasCurvedSegments()
                providerSupportsCurvedSegments = vlayer.dataProvider().capabilities() & QgsVectorDataProvider.CircularGeometries

                snappingMatchesList = []
                curveToAdd = None
                if hasCurvedSegments and providerSupportsCurvedSegments:

                    curveToAdd = self.captureCurve().clone()

                else:

                    curveToAdd = self.captureCurve().curveToLine()
                    snappingMatchesList = self.snappingMatches()


                if self.mode() == self.CaptureLine:

                    g = QgsGeometry(curveToAdd)
                    f.setGeometry( g )

                else:
                    poly = None
                    if hasCurvedSegments and providerSupportsCurvedSegments:
                        poly = QgsCurvePolygon()
                    else:
                        poly = QgsPolygon()

                    poly.setExteriorRing( curveToAdd )
                    g = QgsGeometry( poly )
                    f.setGeometry( g )

                    featGeom = f.geometry()
                    avoidIntersectionsReturn = featGeom.avoidIntersections( QgsProject.instance().avoidIntersectionsLayers() )
                    f.setGeometry( featGeom )
                    if avoidIntersectionsReturn == 1:
                        #//not a polygon type. Impossible to get there
                        pass

                    if f.geometry().isEmpty(): # //avoid intersection might have removed the whole geometry

                        self.messageEmitted.emit(tr( "The feature cannot be added because it's geometry collapsed due to intersection avoidance" ), Qgis.Critical )
                        self.stopCapturing()
                        return


                f.setValid(True)

                self.digitized(f)

                self.stopCapturing()





class QgsMapToolAddFeature(QgsMapToolDigitizeFeature):

    def __init__(self, canvas:QgsMapCanvas, mode, cadDockWidget:QgsAdvancedDigitizingDockWidget):
        super(QgsMapToolAddFeature, self).__init__(canvas, canvas.currentLayer(), mode, cadDockWidget)

        self.setCheckGeometryType(True)
        #mToolName = tr( "Add feature" );
        #connect( QgisApp::instance(), &QgisApp::newProject, this, &QgsMapToolAddFeature::stopCapturing );
        #connect( QgisApp::instance(), &QgisApp::projectRead, this, &QgsMapToolAddFeature::stopCapturing );
        QgsProject.instance().cleared.connect(self.stopCapturing)

    def addFeature(self, vlayer:QgsVectorLayer, f:QgsFeature, showModal:bool )->bool:

        scope = QgsExpressionContextUtils.mapToolCaptureScope(self.snappingMatches() )
        action = QgsFeatureAction("add feature", f, vlayer, '', -1, self)
        res = action.addFeature({}, showModal, scope )
        if showModal:
            del action
        return res


    def digitized(self, f:QgsFeature):

        vlayer = self.currentVectorLayer()
        res = self.addFeature( vlayer, f, False)

        if res and (self.mode() == self.CaptureLine or self.mode() == self.CapturePolygon):

            #//add points to other features to keep topology up-to-date
            topologicalEditing = QgsProject.instance().topologicalEditing()

            #//use always topological editing for avoidIntersection.
            #//Otherwise, no way to guarantee the geometries don't have a small gap in between.
            intersectionLayers = QgsProject.instance().avoidIntersectionsLayers()
            avoidIntersection = len(intersectionLayers) > 0
            if avoidIntersection:# //try to add topological points also to background layers

                for vl in intersectionLayers:

                    #//can only add topological points if background layer is editable...
                    if vl.geometryType() == QgsWkbTypes.PolygonGeometry and vl.isEditable():

                        vl.addTopologicalPoints( f.geometry() )



            elif topologicalEditing:

                vlayer.addTopologicalPoints( f.geometry() )


class QgsDistanceWidget(QWidget):
    distanceChanged = pyqtSignal(float)
    distanceEditingCanceled = pyqtSignal()
    distanceEditingFinished = pyqtSignal(float, Qt.KeyboardModifiers)
    distanceEditingCanceled = pyqtSignal()

    def __init__(self, label:str, parent:QWidget=None):

        super(QgsDistanceWidget, self).__init__(parent)

        self.mLayout = QHBoxLayout(self)
        self.mLayout.setContentsMargins( 0, 0, 0, 0 )
        self.mLayout.setAlignment(Qt.AlignLeft)
        self.setLayout(self.mLayout)


        if label:

            lbl = QLabel( label, self)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignCenter)
            self.mLayout.addWidget( lbl )


        self.mDistanceSpinBox = QgsDoubleSpinBox( self)
        self.mDistanceSpinBox.setSingleStep( 1 )
        self.mDistanceSpinBox.setValue( 0 )
        self.mDistanceSpinBox.setMinimum( 0 )
        self.mDistanceSpinBox.setMaximum( 1000000000 )
        self.mDistanceSpinBox.setDecimals( 6 )
        self.mDistanceSpinBox.setShowClearButton( False)
        self.mDistanceSpinBox.setSizePolicy( QSizePolicy.MinimumExpanding, QSizePolicy.Preferred )
        self.mLayout.addWidget(self.mDistanceSpinBox )

        # connect signals
        self.mDistanceSpinBox.installEventFilter(self)
        self.mDistanceSpinBox.valueChanged.connect(self.distanceChanged)

        # config focus
        self.setFocusProxy(self.mDistanceSpinBox )



    def setDistance(self, distance:float):

        self.mDistanceSpinBox.setValue(distance)
        self.mDistanceSpinBox.selectAll()


    def distance(self)->float:
        return self.mDistanceSpinBox.value()

    def eventFilter(self, obj:QObject, ev:QEvent )->bool:

        if ( obj == self.mDistanceSpinBox and ev.type() == QEvent.KeyPress ):

            event = QKeyEvent(ev)
            if event.key() == Qt.Key_Escape:

              self.distanceEditingCanceled.emit()
              return False

            if event.key() == Qt.Key_Enter or event.key() == Qt.Key_Return:

              self.distanceEditingFinished.emit(self.distance(), event.modifiers() )
              return True;



        return False


class QgsMapToolSelectUtils(object):
    """
    Mimics the QgsMapToolSelectUtils C++ implementation from the not-python-accessible QGIS app code
    """
    @staticmethod
    def getCurrentVectorLayer(canvas:QgsMapCanvas):

        vlayer = canvas.currentLayer()

        if not isinstance(vlayer, QgsVectorLayer):
            print("No active vector layer", file=sys.stderr)

        return vlayer

    @staticmethod
    def setRubberBand( canvas:QgsMapCanvas, selectRect:QRect, rubberBand:QgsRubberBand):

        transform = canvas.getCoordinateTransform()
        ll = transform.toMapCoordinates(selectRect.left(), selectRect.bottom() )
        lr = transform.toMapCoordinates( selectRect.right(), selectRect.bottom() )
        ul = transform.toMapCoordinates( selectRect.left(), selectRect.top() )
        ur = transform.toMapCoordinates( selectRect.right(), selectRect.top() )

        if isinstance(rubberBand, QgsRubberBand):

            rubberBand.reset(QgsWkbTypes.PolygonGeometry )
            rubberBand.addPoint( ll, False )
            rubberBand.addPoint( lr, False )
            rubberBand.addPoint( ur, False )
            rubberBand.addPoint( ul, True )

    @staticmethod
    def expandSelectRectangle( mapPoint:QgsPointXY, canvas:QgsMapCanvas, vlayer:QgsVectorLayer):

        boxSize = 0
        if ( not vlayer or vlayer.geometryType() != QgsWkbTypes.PolygonGeometry ):

            #if point or line use an artificial bounding box of 10x10 pixels
            #to aid the user to click on a feature accurately
            boxSize = 5

        else:
            #otherwise just use the click point for polys
            boxSize = 1


        transform = canvas.getCoordinateTransform()
        point = transform.transform( mapPoint )
        ll = transform.toMapCoordinates( int( point.x() - boxSize ), int( point.y() + boxSize ) )
        ur = transform.toMapCoordinates( int( point.x() + boxSize ), int( point.y() - boxSize ) )
        return QgsRectangle( ll, ur )

    @staticmethod
    def selectMultipleFeatures( canvas:QgsMapCanvas, selectGeometry:QgsGeometry, modifiers:Qt.KeyboardModifiers):

        behavior = QgsVectorLayer.SetSelection
        if ( modifiers & Qt.ShiftModifier and modifiers & Qt.ControlModifier ):
            behavior = QgsVectorLayer.IntersectSelection
        elif ( modifiers & Qt.ShiftModifier ):
            behavior = QgsVectorLayer.AddToSelection
        elif ( modifiers & Qt.ControlModifier ):
            behavior = QgsVectorLayer.RemoveFromSelection

        doContains = modifiers & Qt.AltModifier
        QgsMapToolSelectUtils.setSelectedFeatures( canvas, selectGeometry, behavior, doContains )

    @staticmethod
    def selectSingleFeature(canvas:QgsMapCanvas, selectGeometry:QgsGeometry, modifiers:Qt.KeyboardModifiers  ):

        vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer( canvas )
        if not isinstance(vlayer, QgsVectorLayer):
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)

        selectedFeatures = QgsMapToolSelectUtils.getMatchingFeatures( canvas, selectGeometry, False, True )
        if len(selectedFeatures) == 0:

            if ( not( modifiers & Qt.ShiftModifier or modifiers & Qt.ControlModifier ) ):
                # if no modifiers then clicking outside features clears the selection
                # but if there's a shift or ctrl modifier, then it's likely the user was trying
                # to modify an existing selection by adding or subtracting features and just
                # missed the feature
                vlayer.removeSelection()

            QApplication.restoreOverrideCursor()
            return


        behavior = QgsVectorLayer.SetSelection

        # either shift or control modifier switches to "toggle" selection mode
        if ( modifiers & Qt.ShiftModifier or modifiers & Qt.ControlModifier ) and not Qt.AltModifier:

            selectId = selectedFeatures[0]
            layerSelectedFeatures = vlayer.selectedFeatureIds()
            if selectId in layerSelectedFeatures:
                behavior = QgsVectorLayer.RemoveFromSelection
            else:
                behavior = QgsVectorLayer.AddToSelection


        vlayer.selectByIds( selectedFeatures, behavior )

        QApplication.restoreOverrideCursor()

    @staticmethod
    def setSelectedFeatures( canvas:QgsMapCanvas, selectGeometry:QgsGeometry, \
                             selectBehavior:QgsVectorLayer.SelectBehavior,  \
                             doContains:bool=True, \
                             singleSelect:bool=False ):

        vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer( canvas )
        if not isinstance(vlayer, QgsVectorLayer):
            return

        QApplication.setOverrideCursor( Qt.WaitCursor )

        selectedFeatures = QgsMapToolSelectUtils.getMatchingFeatures( canvas, selectGeometry, doContains, singleSelect )
        vlayer.selectByIds( selectedFeatures, selectBehavior )

        QApplication.restoreOverrideCursor()


    @staticmethod
    def getMatchingFeatures( canvas:QgsMapCanvas, selectGeometry:QgsGeometry, doContains:bool , singleSelect:bool )->list:

        newSelectedFeatures = []

        if ( selectGeometry.type() != QgsWkbTypes.PolygonGeometry ):
            return newSelectedFeatures

        vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer( canvas )
        if not isinstance(vlayer, QgsVectorLayer):
            return newSelectedFeatures

        # toLayerCoordinates will throw an exception for any 'invalid' points in
        # the rubber band.
        # For example, if you project a world map onto a globe using EPSG 2163
        # and then click somewhere off the globe, an exception will be thrown.
        selectGeomTrans = selectGeometry

        try:
            ct = QgsCoordinateTransform()
            ct.setSourceCrs(canvas.mapSettings().destinationCrs())
            ct.setDestinationCrs(vlayer.crs())
            ct.setContext(QgsProject.instance().transformContext())
            #QgsCoordinateTransform ct( canvas->mapSettings().destinationCrs(), vlayer->crs(), QgsProject::instance() );

            # todo: ...

            selectGeomTrans.transform( ct )

        except QgsCsException as cse:
            # catch exception for 'invalid' point and leave existing selection unchanged
            return newSelectedFeatures

        context = QgsRenderContext.fromMapSettings(canvas.mapSettings())
        context.expressionContext().appendScope(QgsExpressionContextUtils.layerScope(vlayer))
        r = None
        if ( vlayer.renderer()):
            r = vlayer.renderer().clone()
            r.startRender( context, vlayer.fields() )


        request = QgsFeatureRequest()
        request.setFilterRect(selectGeomTrans.boundingBox())
        request.setFlags( QgsFeatureRequest.ExactIntersect )
        if ( r ):
            request.setSubsetOfAttributes( r.usedAttributes(context), vlayer.fields() )
        else:
            request.setNoAttributes()

        fit = vlayer.getFeatures(request)
        assert isinstance(fit, QgsFeatureIterator)

        f = QgsFeature()
        closestFeatureId = 0
        foundSingleFeature = False
        #double closestFeatureDist = std::numeric_limits<double>::max();
        closestFeatureDist = sys.float_info.max
        while ( fit.nextFeature( f ) ):
            context.expressionContext().setFeature( f )
            #// make sure to only use features that are visible
            if ( r and not r.willRenderFeature( f, context ) ):
                continue

            g = f.geometry()
            if ( doContains ):
                if ( not selectGeomTrans.contains( g ) ):
                    continue
            else:
              if ( not selectGeomTrans.intersects( g ) ):
                    continue

            if ( singleSelect ):

                foundSingleFeature = True
                distance = g.distance( selectGeomTrans )
                if ( distance <= closestFeatureDist ):
                    closestFeatureDist = distance
                    closestFeatureId = f.id()


            else:

                newSelectedFeatures.append(f.id())


        if ( singleSelect and foundSingleFeature ):

            newSelectedFeatures.append(closestFeatureId)


        if ( r ):
            r.stopRender( context )


        return newSelectedFeatures




class QgsMapToolSelectionHandler(QObject):
    """
    Mimics the QgsMapToolSelectionHandler C++ implementation
    """

    class SelectionMode(enum.Enum):
        SelectSimple = 0
        SelectPolygon = 1
        SelectFreehand = 2
        SelectRadius = 3

    geometryChanged = pyqtSignal(Qt.KeyboardModifiers)

    def __init__(self, canvas:QgsMapCanvas, selectionMode):
        super(QgsMapToolSelectionHandler, self).__init__()
        assert isinstance(selectionMode, QgsMapToolSelectionHandler.SelectionMode)
        self.mCanvas = canvas
        assert isinstance(canvas, QgsMapCanvas)

        self.mSelectionMode = selectionMode
        self.mSnapIndicator = QgsSnapIndicator(canvas)
        self.mIdentifyMenu = QgsIdentifyMenu(canvas)
        self.mIdentifyMenu.setAllowMultipleReturn(False)
        self.mIdentifyMenu.setExecWithSingleResult(True)
        self.mSelectionActive = False

        self.mDistanceWidget = None

        # create own user-input widget or use the first that is child to the map canvas
        self.mUserInputWidget = createQgsMapCanvasUserInputWidget(self.mCanvas)
        self.mSelectionRubberBand = None
        self.mInitDragPos = None
        self.mRadiusCenter = None
        self.mFillColor = QColor( 254, 178, 76, 63 )
        self.mStrokeColor = QColor( 254, 58, 29, 100 )

    def canvasReleaseEvent(self, e:QgsMapMouseEvent):
        if self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectSimple:
            self.selectFeaturesReleaseEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectPolygon:
            pass
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectFreehand:
            self.selectFreehandReleaseEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectRadius:
            self.selectRadiusReleaseEvent( e )

    def canvasMoveEvent(self, e:QgsMapMouseEvent):
        if self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectSimple:
            self.selectFeaturesMoveEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectPolygon:
            self.selectPolygonMoveEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectFreehand:
            self.selectFreehandMoveEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectRadius:
            self.selectRadiusMoveEvent( e )

    def canvasPressEvent(self, e:QgsMapMouseEvent):
        if self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectSimple:
            self.selectFeaturesPressEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectPolygon:
            self.selectPolygonPressEvent( e )
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectFreehand:
            pass
        elif self.mSelectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectRadius:
            pass

    def keyReleaseEvent(self, e:QKeyEvent)->bool:
        if self.mSelectionActive and e.key() == Qt.Key_Escape:
            self.cancel()
            return True
        else:
            return False

    def deactivate(self):
        self.cancel()

    def selectFeaturesPressEvent(self, e:QgsMapMouseEvent):
        if not self.mSelectionRubberBand:
            self.initRubberBand()
        self.mInitDragPos = e.pos()

    def selectFeaturesMoveEvent(self, e:QgsMapMouseEvent):

        if e.buttons() != Qt.LeftButton:
            return


        if not self.mSelectionActive:
            self.mSelectionActive = True
            rect = QRect(e.pos(), e.pos())
        else:
            rect = QRect(e.pos(), self.mInitDragPos)

        if isinstance(self.mSelectionRubberBand, QgsRubberBand):

            self.mSelectionRubberBand.setToCanvasRectangle(rect)

    def selectFeaturesReleaseEvent(self, e:QgsMapMouseEvent):

        point = e.pos() - self.mInitDragPos

        if not self.mSelectionActive or ( point.manhattanLength() < QApplication.startDragDistance() ):

            self.mSelectionActive = False
            self.setSelectedGeometry( QgsGeometry.fromPointXY(self.toMapCoordinates( e.pos() ) ), e.modifiers() )


        if self.mSelectionRubberBand and self.mSelectionActive:

            self.setSelectedGeometry(self.mSelectionRubberBand.asGeometry(), e.modifiers() )
            self.mSelectionRubberBand.reset()


        self.mSelectionActive = False


    def toMapCoordinates(self, point:QPoint)->QgsPointXY:
        return self.mCanvas.getCoordinateTransform().toMapCoordinates( point )


    def selectPolygonMoveEvent(self, e:QgsMapMouseEvent):
        if not isinstance(self.mSelectionRubberBand, QgsRubberBand):
            return

        if self.mSelectionRubberBand.numberOfVertices() > 0:
            self.mSelectionRubberBand.movePoint(self.toMapCoordinates( e.pos() ) )

    def selectPolygonPressEvent(self, e:QgsMapMouseEvent):

        #// Handle immediate right-click on feature to show context menu
        if not self.mSelectionRubberBand and e.button() == Qt.RightButton:


            # QList<QgsMapToolIdentify::IdentifyResult> results;
            #QMap< QString, QString > derivedAttributes;

            results = []
            derivedAttributes = dict()

            mapPoint = self.toMapCoordinates(e.pos())
            x = mapPoint.x()
            y = mapPoint.y()
            sr = QgsMapTool.searchRadiusMU(self.mCanvas)

            #const QList<QgsMapLayer *> layers = mCanvas->layers();
            layers = self.mCanvas.layers()

            for vectorLayer in layers:
                if isinstance(vectorLayer, QgsVectorLayer):
                    if vectorLayer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        fit = vectorLayer.getFeatures( QgsFeatureRequest()
                                                   .setDestinationCrs(self.mCanvas.mapSettings().destinationCrs(),
                                                                      self.mCanvas.mapSettings().transformContext())
                                                   .setFilterRect( QgsRectangle( x - sr, y - sr, x + sr, y + sr ) )
                                                   .setFlags( QgsFeatureRequest.ExactIntersect ) )
                        f = None
                        while fit.nextFeature( f ):
                            results.append(QgsMapToolIdentify.IdentifyResult(vectorLayer, f, derivedAttributes ))


            globalPos = self.mCanvas.mapToGlobal( QPoint( e.pos().x() + 5, e.pos().y() + 5 ) )
            selectedFeatures = self.mIdentifyMenu.exec(results, globalPos )
            if not selectedFeatures.empty() and selectedFeatures[0].mFeature.hasGeometry():
                self.setSelectedGeometry(selectedFeatures[0].mFeature.geometry(), e.modifiers() )
            return 


        #// Handle definition of polygon by clicking points on cancas
        if not self.mSelectionRubberBand:
            self.initRubberBand()

        if e.button() == Qt.LeftButton:
            self.mSelectionRubberBand.addPoint(self.toMapCoordinates( e.pos() ) )
            self.mSelectionActive = True
        else:
            if self.mSelectionRubberBand.numberOfVertices() > 2:
                self.setSelectedGeometry(self.mSelectionRubberBand.asGeometry(), e.modifiers() )

            self.mSelectionRubberBand.reset()
            self.mSelectionActive = False

    def selectFreehandMoveEvent(self, e:QgsMapMouseEvent):

        if not (self.mSelectionActive or self.mSelectionRubberBand):
            return

        self.mSelectionRubberBand.addPoint(self.toMapCoordinates( e.pos() ) )


    def selectFreehandReleaseEvent(self, e:QgsMapMouseEvent):

        if self.mSelectionActive:
            if e.button() != Qt.LeftButton:
                return

            if not self.mSelectionRubberBand:
                self.initRubberBand()

            self.mSelectionRubberBand.addPoint(self.toMapCoordinates( e.pos() ) )
            self.mSelectionActive = True

        else:
            if e.button() == Qt.LeftButton:
                if self.mSelectionRubberBand and self.mSelectionRubberBand.numberOfVertices() > 2:
                    self.setSelectedGeometry(self.mSelectionRubberBand.asGeometry(), e.modifiers() )

            self.mSelectionRubberBand.reset()
            self.mSelectionActive = False


    def selectRadiusMoveEvent(self, e:QgsMapMouseEvent):

        radiusEdge = e.snapPoint()

        self.mSnapIndicator.setMatch(e.mapPointMatch() )

        if not self.mSelectionActive:
            return


        if not self.mSelectionRubberBand:

            self.initRubberBand()

        self.updateRadiusFromEdge( radiusEdge )


    def selectRadiusReleaseEvent(self, e:QgsMapMouseEvent):

        if e.button() == Qt.RightButton:
            self.cancel()
            return

        if e.button() != Qt.LeftButton:
            return

        if not self.mSelectionActive:

            self.mSelectionActive = True
            self.mRadiusCenter = e.snapPoint()
            self.createDistanceWidget()
        else:
            if isinstance(self.mSelectionRubberBand, QgsRubberBand):
                self.setSelectedGeometry(self.mSelectionRubberBand.asGeometry(), e.modifiers() )

            self.cancel()


    def initRubberBand(self):

        self.mSelectionRubberBand = QgsRubberBand(self.mCanvas, QgsWkbTypes.PolygonGeometry)
        self.mSelectionRubberBand.setFillColor(self.mFillColor )
        self.mSelectionRubberBand.setStrokeColor(self.mStrokeColor)


    def createDistanceWidget(self):
        if not isinstance(self.mCanvas, QgsMapCanvas):
            return

        self.deleteDistanceWidget()

        self.mDistanceWidget = QgsDistanceWidget("Selection radius:")
        # emulate
        # QgisApp::instance()->addUserInputWidget( mDistanceWidget );
        # by adding the distance widget to the MapTool's QgsMapCanvas directly
        self.mUserInputWidget.addUserInputWidget(self.mDistanceWidget)

        self.mDistanceWidget.setFocus(Qt.TabFocusReason)
        self.mDistanceWidget.distanceChanged.connect(self.updateRadiusRubberband)
        self.mDistanceWidget.distanceEditingFinished.connect(self.radiusValueEntered)
        self.mDistanceWidget.distanceEditingCanceled.connect(self.cancel)
        #connect( mDistanceWidget, &QgsDistanceWidget::distanceEditingFinished, this, &QgsMapToolSelectionHandler::radiusValueEntered );
        #connect( mDistanceWidget, &QgsDistanceWidget::distanceEditingCanceled, this, &QgsMapToolSelectionHandler::cancel );


    def deleteDistanceWidget(self):
        if isinstance(self.mDistanceWidget, QWidget):
            self.mDistanceWidget.releaseKeyboard()
            self.mDistanceWidget.deleteLater()

        self.mDistanceWidget = None


    def radiusValueEntered(self, radius:float, modifiers:Qt.KeyboardModifiers):

        if not isinstance(self.mSelectionRubberBand, QgsRubberBand):
            return

        self.updateRadiusRubberband( radius );
        self.setSelectedGeometry(self.mSelectionRubberBand.asGeometry(), modifiers )
        self.cancel();


    def cancel(self):

        self.deleteDistanceWidget()
        self.mSnapIndicator.setMatch( QgsPointLocator.Match() )
        if isinstance(self.mSelectionRubberBand, QgsRubberBand):
            self.mSelectionRubberBand.reset()
        self.mSelectionActive = False


    def updateRadiusRubberband(self, radius:float):

        if not isinstance(self.mSelectionRubberBand, QgsRubberBand):
            self.initRubberBand()

        RADIUS_SEGMENTS = 80
        self.mSelectionRubberBand.reset(QgsWkbTypes.PolygonGeometry)
        for i in range(RADIUS_SEGMENTS):

            theta = i * ( 2.0 * math.pi / RADIUS_SEGMENTS )
            radiusPoint = QgsPointXY(self.mRadiusCenter.x() + radius * math.cos( theta ),
                                     self.mRadiusCenter.y() + radius * math.sin( theta ) )
            self.mSelectionRubberBand.addPoint( radiusPoint, False)

        self.mSelectionRubberBand.closePoints(True)


    def updateRadiusFromEdge(self, radiusEdge:QgsPointXY):
        radius = math.sqrt(self.mRadiusCenter.sqrDist( radiusEdge ) )
        if self.mDistanceWidget:
            self.mDistanceWidget.setDistance( radius )
            self.mDistanceWidget.setFocus( Qt.TabFocusReason )

        else:
            self.updateRadiusRubberband( radius )

    def selectedGeometry(self)->QgsGeometry:
        return self.mSelectionGeometry

    def setSelectedGeometry(self, geometry:QgsGeometry, modifiers:Qt.KeyboardModifiers):

        self.mSelectionGeometry = geometry
        self.geometryChanged.emit(modifiers)

    def setSelectionMode(self, mode):
        assert isinstance(mode, QgsMapToolSelectionHandler.SelectionMode)
        self.mSelectionMode = mode

    def selectionMode(self):
        return self.mSelectionMode


class QgsMapToolSelect(QgsMapTool):

    def __init__(self, canvas:QgsMapCanvas):
        super(QgsMapToolSelect, self).__init__(canvas)

        self.mSelectionHandler = QgsMapToolSelectionHandler(canvas, QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        self.mSelectionHandler.geometryChanged.connect(self.selectFeatures)
        self.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)


    def setSelectionMode(self, selectionMode:QgsMapToolSelectionHandler.SelectionMode):
        self.mSelectionHandler.setSelectionMode(selectionMode)
        if selectionMode == QgsMapToolSelectionHandler.SelectionMode.SelectSimple:
            self.setCursor(QgsApplication.getThemeCursor(QgsApplication.Select))
        else:
            self.setCursor(Qt.ArrowCursor)

    def canvasPressEvent(self, e:QgsMapMouseEvent):
        self.mSelectionHandler.canvasPressEvent(e)


    def canvasMoveEvent(self, e:QgsMapMouseEvent):
        self.mSelectionHandler.canvasMoveEvent(e)


    def canvasReleaseEvent(self, e:QgsMapMouseEvent):
        self.mSelectionHandler.canvasReleaseEvent(e)


    def keyReleaseEvent(self, e:QKeyEvent):
        if (self.mSelectionHandler.keyReleaseEvent(e)):
            return

        super(QgsMapToolSelect, self).keyPressEvent(e)


    def deactivate(self):
        self.mSelectionHandler.deactivate()
        super(QgsMapToolSelect, self).deactivate()



    def selectFeatures(self, modifiers:Qt.KeyboardModifiers):

        if self.mSelectionHandler.selectionMode() == QgsMapToolSelectionHandler.SelectionMode.SelectSimple \
            and self.mSelectionHandler.selectedGeometry().type() == QgsWkbTypes.PointGeometry:

            vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer(self.canvas())
            r = QgsMapToolSelectUtils.expandSelectRectangle(self.mSelectionHandler.selectedGeometry().asPoint(),
                                                            self.canvas(),
                                                            vlayer )
            QgsMapToolSelectUtils.selectSingleFeature(self.canvas(), QgsGeometry.fromRect(r), modifiers )

        else:
            QgsMapToolSelectUtils.selectMultipleFeatures(self.canvas(), self.mSelectionHandler.selectedGeometry(),
                                                         modifiers )



