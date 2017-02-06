# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EnMAPBox
                                 A QGIS plugin
 EnMAP-Box V3
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by HU-Berlin
        email                : bj@geo.hu-berlin.de
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

# Import the code for the dialog
import os, sys, re, fnmatch, collections, copy, traceback, six
from qgis.core import *
#os.environ['PATH'] += os.pathsep + r'C:\OSGeo4W64\bin'

from osgeo import gdal, ogr, osr, gdal_array

DEBUG = True
import qgis.analysis
try:
    from qgis.gui import *
    import qgis
    import qgis_add_ins
    qgis_available = True

    #import console.console_output
    #console.show_console()
    #sys.stdout = console.console_output.writeOut()
    #sys.stderr = console.console_output.writeOut()

except:
    print('Can not find QGIS instance')
    qgis_available = False

import numpy as np

import sys, bisect, multiprocessing, site
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.uic.Compiler.qtproxies import QtGui, QtCore
import code
import codecs

#abbreviations
from timeseriesviewer import jp, mkdir, DIR_SITE_PACKAGES, file_search, dprint
from timeseriesviewer.timeseries import *

site.addsitedir(DIR_SITE_PACKAGES)


#I don't know why, but this is required to run this in QGIS
#todo: still required?
path = os.path.abspath(jp(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

#ensure that required non-standard modules are available

import pyqtgraph as pg




class SpatialExtent(QgsRectangle):
    """
    Object to keep QgsRectangle and QgsCoordinateReferenceSystem together
    """
    @staticmethod
    def fromMapCanvas(mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        extent = mapCanvas.extent()
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialExtent(crs, extent)

    def __init__(self, crs, *args):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialExtent, self).__init__(*args)
        self.mCrs = crs

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def toCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        box = QgsRectangle(self)
        if self.mCrs != crs:
            trans = QgsCoordinateTransform(self.mCrs, crs)
            box = trans.transformBoundingBox(box)
        return SpatialExtent(crs, box)

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

    def combineExtentWith(self, *args):
        if args is None:
            return
        elif isinstance(args[0], SpatialExtent):
            extent2 = args[0].toCrs(self.crs())
            self.combineExtentWith(QgsRectangle(extent2))
        else:
            super(SpatialExtent, self).combineExtentWith(*args)

    def setCenter(self, centerPoint, crs=None):

        if crs and crs != self.crs():
            trans = QgsCoordinateTransform(crs, self.crs())
            centerPoint = trans.transform(centerPoint)

        delta = centerPoint - self.center()
        self.setXMaximum(self.xMaximum() + delta.x())
        self.setXMinimum(self.xMinimum() + delta.x())
        self.setYMaximum(self.yMaximum() + delta.y())
        self.setYMinimum(self.yMinimum() + delta.y())


    def __cmp__(self, other):
        if other is None: return 1
        s = ""

    def __eq__(self, other):
        s = ""

    def __sub__(self, other):
        raise NotImplementedError()

    def __mul__(self, other):
        raise NotImplementedError()

    def upperLeft(self):
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self):
        return self.xMaximum(), self.yMinimum()

    def __repr__(self):

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())

class TsvMimeDataUtils(QObject):
    def __init__(self, mimeData):
        assert isinstance(mimeData, QMimeData)
        super(TsvMimeDataUtils, self).__init__()

        self.mimeData = mimeData

        self.xmlDoc = QDomDocument()

        if self.mimeData.hasText():
            self.xmlDoc.setContent(self.mimeData.text())
        self.xmlRoot = self.xmlDoc.documentElement()
        pass

    def hasRasterStyle(self):
        if self.xmlRoot.tagName() == 'qgis':
            elem = self.xmlRoot.elementsByTagName('rasterrenderer')
            return elem.count() != 0

        return False


    def rasterStyle(self, qgisDataType):

        elem = self.xmlRoot.elementsByTagName('rasterrenderer').item(0).toElement()
        type = str(elem.attribute('type'))
        from qgis.core import QGis, QgsContrastEnhancement

        def bandSettings(colorName):
            band = int(elem.attribute(colorName + 'Band'))
            ceNode = elem.elementsByTagName(colorName + 'ContrastEnhancement').item(0)
            vMin = float(ceNode.firstChildElement('minValue').firstChild().nodeValue())
            vMax = float(ceNode.firstChildElement('maxValue').firstChild().nodeValue())
            ceName = ceNode.firstChildElement('algorithm').firstChild().nodeValue()
            ceAlg = QgsContrastEnhancement.contrastEnhancementAlgorithmFromString(ceName)
            ce = QgsContrastEnhancement(qgisDataType)
            ce.setContrastEnhancementAlgorithm(ceAlg)
            ce.setMinimumValue(vMin)
            ce.setMaximumValue(vMax)
            return band, ce

        style = None
        if type == 'multibandcolor':
                A = int(elem.attribute('alphaBand'))
                O = int(elem.attribute('opacity'))
                R, ceR = bandSettings('red')
                G, ceG = bandSettings('green')
                B, ceB = bandSettings('blue')

                style = QgsMultiBandColorRenderer(None, R, G, B)
                style.setRedContrastEnhancement(ceR)
                style.setGreenContrastEnhancement(ceG)
                style.setBlueContrastEnhancement(ceB)

        elif type == 'singlebandgrey':

            pass

        return style

class QgisTsvBridge(QObject):
    """
    Class to control interactions between TSV and a running QGIS instance
    """
    _instance = None


    @staticmethod
    def instance():
        return QgisTsvBridge._instance

    def __init__(self, iface, TSV_UI):
        super(QgisTsvBridge, self).__init__()
        assert QgisTsvBridge._instance is None
        assert isinstance(iface, QgisInterface)
        self.iface = iface
        self.ui = TSV_UI
        self.cbVectorLayer = TSV_UI.cbQgsVectorLayer

    def extent(self):
        canvas = self.iface.mapCanvas()
        assert isinstance(canvas, QgsMapCanvas)
        crs = canvas.dest
        self.iface.mapCanvas().extent()
        s = ""

    def center(self):
        s = ""

    def crs(self):
        s = ""

    def getVectorLayerRepresentation(self):
        if self.ui.gbQgsVectorLayer.isChecked():
            lyr = self.cbVectorLayer.currentLayer()
            alpha = self.ui.sliderQgsVectorTransparency.value()
            return lyr
        else:
            return None


    def syncExtent(self, isChecked):
        if isChecked:
            self.dockRendering.cbSyncQgsMapCenter.setEnabled(False)
            self.dockRendering.cbSyncQgsMapCenter.blockSignals(True)
            self.dockRendering.cbSyncQgsMapCenter.setChecked(True)
            self.dockRendering.cbSyncQgsMapCenter.blockSignals(False)
        else:
            self.dockRendering.cbSyncQgsMapCenter.setEnabled(True)
        self.qgsSyncStateChanged()

    def qgsSyncState(self):
        return (self.cbSyncQgsMapCenter.isChecked(),
                self.cbSyncQgsMapExtent.isChecked(),
                self.cbSyncQgsCRS.isChecked())

    def qgsSyncStateChanged(self, *args):
        s = self.qgsSyncState()
        self.sigQgsSyncChanged.emit(s[0], s[1], s[2])






class MapView(QObject):

    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibility = pyqtSignal(bool)
    sigTitleChanged = pyqtSignal(str)
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigShowProfiles = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)

    def __init__(self, mapViewCollection, recommended_bands=None, parent=None):
        super(MapView, self).__init__()
        assert isinstance(mapViewCollection, MapViewCollection)
        self.MVC = mapViewCollection
        from timeseriesviewer.ui.widgets import MapViewDefinitionUI
        self.ui = MapViewDefinitionUI(self, parent=parent)
        self.ui.create()

        self.setVisibility(True)

        #forward actions with reference to this band view
        self.spatialExtent = None
        self.ui.actionRemoveMapView.triggered.connect(lambda: self.sigRemoveMapView.emit(self))
        self.ui.actionApplyStyles.triggered.connect(self.applyStyles)
        self.ui.sigShowMapView.connect(lambda: self.sigMapViewVisibility.emit(True))
        self.ui.sigHideMapView.connect(lambda: self.sigMapViewVisibility.emit(False))
        self.sensorViews = collections.OrderedDict()

        self.mSpatialExtent = None

    def applyStyles(self):
        for sensorView in self.sensorViews.values():
            sensorView.applyStyle()
        s = ""


    def setVisibility(self, isVisible):
        self.ui.setVisibility(isVisible)

    def setSpatialExtent(self, extent):
        assert isinstance(extent, SpatialExtent)
        self.mSpatialExtent = extent
        self.sigSpatialExtentChanged.emit(extent)

    def visibility(self):
        return self.ui.visibility()

    def setTitle(self, title):
        self.mTitle = title
        #self.ui.setTitle('Map View' + title)
        self.sigTitleChanged.emit(self.mTitle)

    def title(self):
        return self.mTitle


    def removeSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        if sensor in self.sensorViews.keys():
            self.sensorViews[sensor].close()
            self.sensorViews.pop(sensor)
            self.ui.adjustSize()
            return True
        else:
            return False

    def hasSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        return sensor in self.sensorViews.keys()

    def addSensor(self, sensor):
        """
        :param sensor:
        :return:
        """
        assert type(sensor) is SensorInstrument
        assert sensor not in self.sensorViews.keys()
        from timeseriesviewer.ui.widgets import MapViewSensorSettings
        w = MapViewSensorSettings(sensor)

        #w.showSensorName(False)
        self.sensorViews[sensor] = w
        l = self.ui.sensorList
        i = l.count()
        l.addWidget(w.ui)
        from timeseriesviewer.ui.widgets import maxWidgetSizes


        s = ""


    def getSensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.sensorViews[sensor]




class TimeSeriesDatumView(QObject):

    sigExtentsChanged = pyqtSignal(SpatialExtent)
    sigRenderProgress = pyqtSignal(int,int)
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigVisibilityChanged = pyqtSignal(bool)

    def __init__(self, TSD, timeSeriesDateViewCollection, mapViewCollection, parent=None):
        assert isinstance(TSD, TimeSeriesDatum)
        assert isinstance(timeSeriesDateViewCollection, TimeSeriesDateViewCollection)
        assert isinstance(mapViewCollection, MapViewCollection)

        super(TimeSeriesDatumView, self).__init__()
        from timeseriesviewer.ui.widgets import TimeSeriesDatumViewUI
        self.ui = TimeSeriesDatumViewUI(parent=parent)
        self.ui.create()

        self.L = self.ui.layout()
        self.wOffset = self.L.count()-1
        self.minHeight = self.ui.height()
        self.minWidth = 50
        self.renderProgress = dict()

        self.TSD = TSD
        self.scrollArea = timeSeriesDateViewCollection.scrollArea
        self.Sensor = self.TSD.sensor
        self.TSD.sigVisibilityChanged.connect(self.setVisibility)
        self.ui.labelTitle.setText(str(TSD.date))
        self.MVC = mapViewCollection
        self.TSDVC = timeSeriesDateViewCollection
        self.mapCanvases = dict()
        self.setSubsetSize(QSize(50, 50))

    def setVisibility(self, b):
        self.ui.setVisible(b)
        self.sigVisibilityChanged.emit(b)

    def activateMapTool(self, key):
        for c in self.mapCanvases.values():
            c.activateMapTool(key)

    def setMapViewVisibility(self, bandView, isVisible):
        self.mapCanvases[bandView].setVisible(isVisible)

    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)

        for c in self.mapCanvases.values():
            c.setSpatialExtent(spatialExtent)


    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        assert size.width() > 5 and size.height() > 5
        self.subsetSize = size


        self.ui.labelTitle.setFixedWidth(size.width())
        self.ui.line.setFixedWidth(size.width())

        #apply new subset size to existing canvases

        for canvas in self.mapCanvases.values():
            canvas.setFixedSize(size)
        self.adjustBaseMinSize()


    def adjustBaseMinSize(self):
        self.ui.setFixedSize(self.ui.sizeHint())

    def removeMapView(self, mapView):
        canvas = self.mapCanvases.pop(mapView)
        self.L.removeWidget(canvas)
        canvas.close()
        self.adjustBaseMinSize()

    def redraw(self):
        if self.ui.isVisible():
            for c in self.mapCanvases.values():
                if c.isVisible():
                    c.refreshAllLayers()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)

        i = self.MVC.index(mapView)

        from timeseriesviewer.ui.widgets import TsvMapCanvas
        canvas = TsvMapCanvas(self, mapView, parent=self.ui)

        canvas.setFixedSize(self.subsetSize)
        canvas.extentsChanged.connect(lambda : self.sigExtentsChanged.emit(canvas.spatialExtent()))
        canvas.renderStarting.connect(lambda : self.sigLoadingStarted.emit(mapView, self.TSD))
        canvas.mapCanvasRefreshed.connect(lambda: self.sigLoadingFinished.emit(mapView, self.TSD))
        canvas.sigShowProfiles.connect(mapView.sigShowProfiles.emit)

        self.mapCanvases[mapView] = canvas
        self.L.insertWidget(self.wOffset + i, canvas)
        canvas.refreshMap()
        self.adjustBaseMinSize()
        return canvas

    def __lt__(self, other):

        return self.TSD < other.TSD

    def __cmp__(self, other):
        return cmp(self.TSD, other.TSD)



class SpatialTemporalVisualization(QObject):
    """

    """
    sigLoadingStarted = pyqtSignal(TimeSeriesDatumView, MapView)
    sigLoadingFinished = pyqtSignal(TimeSeriesDatumView, MapView)
    sigShowProfiles = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)
    sigShowMapLayerInfo = pyqtSignal(dict)

    def __init__(self, timeSeriesViewer):
        assert isinstance(timeSeriesViewer, TimeSeriesViewer)
        super(SpatialTemporalVisualization, self).__init__()

        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.TS
        self.targetLayout = timeSeriesViewer.ui.scrollAreaSubsetContent.layout()
        self.dockMapViews = timeSeriesViewer.ui.dockMapViews
        self.MVC = MapViewCollection(self)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)
        self.timeSeriesDateViewCollection = TimeSeriesDateViewCollection(self)
        self.timeSeriesDateViewCollection.sigResizeRequired.connect(self.adjustScrollArea)
        self.timeSeriesDateViewCollection.sigLoadingStarted.connect(timeSeriesViewer.ui.dockRendering.addStartedWork)
        self.timeSeriesDateViewCollection.sigLoadingFinished.connect(timeSeriesViewer.ui.dockRendering.addFinishedWork)
        self.TS.sigTimeSeriesDatesAdded.connect(self.timeSeriesDateViewCollection.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.timeSeriesDateViewCollection.removeDates)
        #add dates, if already existing
        self.timeSeriesDateViewCollection.addDates(self.TS[:])

        self.setSpatialExtent(self.TS.getMaxSpatialExtent())
        self.setSubsetSize(QSize(100,50))

    def createMapView(self):
        self.MVC.createMapView()

    def activateMapTool(self, key):
        for tsdv in self.timeSeriesDateViewCollection:
            tsdv.activateMapTool(key)

    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size
        self.timeSeriesDateViewCollection.setSubsetSize(size)
        self.adjustScrollArea()

    def redraw(self):
        for tsdView in self.timeSeriesDateViewCollection:
            tsdView.redraw()


    def adjustScrollArea(self):
        #adjust scroll area widget to fit all visible widgets
        m = self.targetLayout.contentsMargins()
        n = len(self.timeSeriesDateViewCollection)
        w = h = 0

        s = QSize()
        r = None
        tmp = [v for v in self.timeSeriesDateViewCollection if not v.ui.isVisible()]
        for TSDView in [v for v in self.timeSeriesDateViewCollection if v.ui.isVisible()]:
            s = s + TSDView.ui.sizeHint()
            if r is None:
                r = TSDView.ui.sizeHint()
        if r:
            if isinstance(self.targetLayout, QHBoxLayout):

                s = QSize(s.width(), r.height())
            else:
                s = QSize(r.width(), s.height())

            s = s + QSize(m.left() + m.right(), m.top() + m.bottom())
            self.targetLayout.parentWidget().setFixedSize(s)



    def setMaxTSDViews(self, n=-1):
        self.nMaxTSDViews = n
        #todo: remove views

    def setSpatialExtent(self, extent):
        self.extent = extent
        if extent:
            self.timeSeriesDateViewCollection.setSpatialExtent(extent)


    def navToDOI(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        #get widget related to TSD
        tsdviews = [t for t in self.TSDViews if t.TSD == TSD]
        if len(tsdviews) > 0:
            i = self.TSDViews.index(tsdviews[0])+1.5
            n = len(self.TSDViews)

            scrollBar = self.TSV.ui.scrollAreaSubsets.horizontalScrollBar()
            smin = scrollBar.minimum()
            smax = scrollBar.maximum()
            v = smin + (smax - smin) * float(i) / n
            scrollBar.setValue(int(round(v)))

    def setMapViewVisibility(self, bandView, isVisible):
        assert isinstance(bandView, MapView)
        assert isinstance(isVisible, bool)

        for tsdv in self.TSDViews:
            tsdv.setMapViewVisibility(bandView, isVisible)






class TimeSeriesDateViewCollection(QObject):

    sigResizeRequired = pyqtSignal()
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigShowProfiles = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)

    def __init__(self, STViz):
        assert isinstance(STViz, SpatialTemporalVisualization)
        super(TimeSeriesDateViewCollection, self).__init__()
        #self.tsv = tsv
        #self.timeSeries = tsv.TS

        self.views = list()
        self.STViz = STViz
        self.ui = self.STViz.targetLayout.parentWidget()
        self.scrollArea = self.ui.parentWidget().parentWidget()
        #potentially there are many more dates than views.
        #therefore we implement the addinng/removing of mapviews here
        #we reduce the number of layout refresh calls by
        #suspending signals, adding the new map view canvases, and sending sigResizeRequired

        self.STViz.MVC.sigMapViewAdded.connect(self.addMapView)
        self.STViz.MVC.sigMapViewRemoved.connect(self.removeMapView)

        self.setFocusView(None)
        self.setSubsetSize(QSize(50,50))


    def addMapView(self, mapView):
        assert isinstance(mapView, MapView)
        w = self.ui
        w.setUpdatesEnabled(False)
        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.views:
            tsdv.insertMapView(mapView)

        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(True)

        #mapView.sigSensorRendererChanged.connect(lambda *args : self.setRasterRenderer(mapView, *args))
        w.setUpdatesEnabled(True)
        self.sigResizeRequired.emit()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        for tsdv in self.views:
            tsdv.removeMapView(mapView)
        self.sigResizeRequired.emit()


    def setFocusView(self, tsd):
        self.focusView = tsd

    def setSpatialExtent(self, extent):
        for tsdview in self.orderedViews():
            tsdview.setSpatialExtent(extent)

    def orderedViews(self):
        #returns the
        if self.focusView is not None:
            assert isinstance(self.focusView, TimeSeriesDatumView)
            return sorted(self.views,key=lambda v: np.abs(v.TSD.date - self.focusView.TSD.date))
        else:
            return self.views

    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size
        for tsdView in self.orderedViews():
            tsdView.setSubsetSize(size)



    def addDates(self, tsdList):
        """
        Create a new TSDView
        :param tsdList:
        :return:
        """
        for tsd in tsdList:
            assert isinstance(tsd, TimeSeriesDatum)
            tsdView = TimeSeriesDatumView(tsd, self, self.STViz.MVC, parent=self.ui)
            tsdView.setSubsetSize(self.subsetSize)

            tsdView.sigExtentsChanged.connect(self.setSpatialExtent)
            tsdView.sigLoadingStarted.connect(self.sigLoadingStarted.emit)
            tsdView.sigLoadingFinished.connect(self.sigLoadingFinished.emit)
            tsdView.sigVisibilityChanged.connect(lambda: self.STViz.adjustScrollArea())


            for i, mapView in enumerate(self.STViz.MVC):
                tsdView.insertMapView(mapView)

            bisect.insort(self.views, tsdView)
            tsdView.ui.setParent(self.STViz.targetLayout.parentWidget())
            self.STViz.targetLayout.addWidget(tsdView.ui)
            tsdView.ui.show()


        if len(tsdList) > 0:
            self.sigResizeRequired.emit()

    def removeDates(self, tsdList):
        toRemove = [v for v in self.views if v.TSD in tsdList]
        removedDates = []
        for tsdView in toRemove:

            self.views.remove(tsdView)

            tsdView.ui.parent().layout().removeWidget(tsdView.ui)
            tsdView.ui.hide()
            tsdView.ui.close()
            removedDates.append(tsdView.TSD)
            del tsdView

        if len(removedDates) > 0:
            self.sigResizeRequired.emit()

    def __len__(self):
        return len(self.views)

    def __iter__(self):
        return iter(self.views)

    def __getitem__(self, slice):
        return self.views[slice]

    def __delitem__(self, slice):
        self.removeDates(self.views[slice])

class MapViewCollection(QObject):

    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigSetMapViewVisibility = pyqtSignal(MapView, bool)
    sigShowProfiles = pyqtSignal(QgsPoint, QgsCoordinateReferenceSystem)

    def __init__(self, STViz):
        assert isinstance(STViz, SpatialTemporalVisualization)
        super(MapViewCollection, self).__init__()
        self.STViz = STViz
        self.STViz.dockMapViews.actionApplyStyles.triggered.connect(self.applyStyles)
        self.STViz.TS.sigSensorAdded.connect(self.addSensor)
        self.ui = STViz.dockMapViews
        self.btnList = STViz.dockMapViews.BVButtonList
        self.scrollArea = STViz.dockMapViews.scrollAreaMapViews
        self.scrollAreaContent = STViz.dockMapViews.scrollAreaMapsViewDockContent
        self.mapViewsDefinitions = []
        self.mapViewButtons = dict()
        self.adjustScrollArea()
    def applyStyles(self):
        for mapView in self.mapViewsDefinitions:
            mapView.applyStyles()

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViewsDefinitions.index(mapView)

    def adjustScrollArea(self):
        #adjust scroll area widget to fit all visible widgets
        l = self.scrollAreaContent.layout()
        from timeseriesviewer.ui.widgets import maxWidgetSizes
        newSize = maxWidgetSizes(l)
        #print(newSize)
        #newSize = self.scrollAreaContent.sizeHint()
        self.scrollAreaContent.setFixedSize(newSize)

    def addSensor(self, sensor):
        for mapView in self.mapViewsDefinitions:
            mapView.addSensor(sensor)
        self.adjustScrollArea()

    def removeSensor(self, sensor):
        for mapView in self.mapViewsDefinitions:
            mapView.removeSensor(sensor)

    def createMapView(self):

        btn = QToolButton(self.btnList)
        self.btnList.layout().insertWidget(self.btnList.layout().count() - 1, btn)

        mapView = MapView(self, parent=self.scrollArea)
        mapView.sigRemoveMapView.connect(self.removeMapView)
        mapView.sigShowProfiles.connect(self.sigShowProfiles.emit)

        for sensor in self.STViz.TS.Sensors:
            mapView.addSensor(sensor)

        self.mapViewButtons[mapView] = btn
        self.mapViewsDefinitions.append(mapView)


        btn.clicked.connect(lambda : self.showMapViewDefinition(mapView))
        self.refreshMapViewTitles()
        if len(self) == 1:
            self.showMapViewDefinition(mapView)
        self.sigMapViewAdded.emit(mapView)
        self.adjustScrollArea()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        btn = self.mapViewButtons[mapView]

        idx = self.mapViewsDefinitions.index(mapView)

        self.mapViewsDefinitions.remove(mapView)
        self.mapViewButtons.pop(mapView)

        mapView.ui.setVisible(False)
        btn.setVisible(False)
        self.btnList.layout().removeWidget(btn)
        l = self.scrollAreaContent.layout()

        for d in self.recentMapViewDefinitions():
            d.ui.setVisible(False)
            l.removeWidget(d.ui)
        l.removeWidget(mapView.ui)
        mapView.ui.close()
        btn.close()
        self.refreshMapViewTitles()
        self.sigMapViewRemoved.emit(mapView)
        if len(self) > 0:
            #show previous mapViewDefinition
            idxNext = max([idx-1, 0])
            self.showMapViewDefinition(self.mapViewsDefinitions[idxNext])

    def refreshMapViewTitles(self):

        for i, mapView in enumerate(self.mapViewsDefinitions):
            number = i+1
            title = '#{}'.format(number)
            mapView.setTitle(title)
            btn = self.mapViewButtons[mapView]
            btn.setText('{}'.format(number))
            btn.setToolTip('Show definition for map view {}'.format(number))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


    def setSpatialExtent(self, extent):
        for mv in self.mapViewsDefinitions:
            mv.setSpatialExtent(extent)

    def showMapViewDefinition(self, mapViewDefinition):
        assert mapViewDefinition in self.mapViewsDefinitions
        assert isinstance(mapViewDefinition, MapView)
        l = self.scrollAreaContent.layout()

        for d in self.recentMapViewDefinitions():
            d.ui.setVisible(False)
            l.removeWidget(d.ui)

        l.insertWidget(l.count() - 1, mapViewDefinition.ui)
        mapViewDefinition.ui.setVisible(True)
        self.ui.setWindowTitle(self.ui.baseTitle + '|'+mapViewDefinition.title())

    def recentMapViewDefinitions(self):
        parent = self.scrollAreaContent
        from timeseriesviewer.ui.widgets import MapViewDefinitionUI
        return [ui.mapViewDefinition() for ui in parent.findChildren(MapViewDefinitionUI)]


    def setMapViewVisibility(self, bandView, isVisible):
        assert isinstance(bandView, MapView)
        assert isinstance(isVisible, bool)





    def __len__(self):
        return len(self.mapViewsDefinitions)

    def __iter__(self):
        return iter(self.mapViewsDefinitions)

    def __getitem__(self, key):
        return self.mapViewsDefinitions[key]

    def __contains__(self, mapView):
        return mapView in self.mapViewsDefinitions


class TimeSeriesViewer:

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface

        from timeseriesviewer.ui.widgets import TimeSeriesViewerUI

        self.ui = TimeSeriesViewerUI(parent=iface)
        if iface:
            import timeseriesviewer
            timeseriesviewer.QGIS_TSV_BRIDGE = QgisTsvBridge(iface, self.ui)
            self.ui.setQgsLinkWidgets()

        #init empty time series
        self.TS = TimeSeries()
        self.hasInitialCenterPoint = False
        self.TS.sigTimeSeriesDatesAdded.connect(self.datesAdded)




        #init TS model

        D = self.ui
        #self.ICP = D.scrollAreaSubsetContent.layout()
        #D.scrollAreaMapViews.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #self.BVP = self.ui.scrollAreaMapViews.layout()
        D.dockNavigation.connectTimeSeries(self.TS)
        D.dockTimeSeries.connectTimeSeries(self.TS)
        D.dockSensors.connectTimeSeries(self.TS)
        D.dockProfiles.connectTimeSeries(self.TS)

        self.spectralTemporalVis = D.dockProfiles

        self.spatialTemporalVis = SpatialTemporalVisualization(self)
        self.spatialTemporalVis.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.spatialTemporalVis.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        #todo: self.spatialTemporalVis.sigShowMapLayerInfo

        self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)

        self.ValidatorPxX = QIntValidator(0,99999)
        self.ValidatorPxY = QIntValidator(0,99999)

        #connect actions with logic

        #D.btn_showPxCoordinate.clicked.connect(lambda: self.showSubsetsStart())
        #connect actions with logic

        D.actionSelectCenter.triggered.connect(lambda : self.spatialTemporalVis.activateMapTool('selectCenter'))
        #D.actionSelectArea.triggered.connect(lambda : self.spatialTemporalVis.activateMapTool('selectArea'))
        D.actionZoomMaxExtent.triggered.connect(lambda : self.zoomTo('maxExtent'))
        D.actionZoomPixelScale.triggered.connect(lambda: self.zoomTo('pixelScale'))
        D.actionZoomIn.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('zoomIn'))
        D.actionZoomOut.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('zoomOut'))
        D.actionPan.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('pan'))
        D.actionIdentifyTimeSeries.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyProfile'))
        D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
        D.actionAddMapView.triggered.connect(self.spatialTemporalVis.createMapView)

        D.actionAddTSD.triggered.connect(lambda : self.ua_addTSImages())
        D.actionRemoveTSD.triggered.connect(lambda: self.TS.removeDates(self.ui.dockTimeSeries.selectedTimeSeriesDates()))
        D.actionRedraw.triggered.connect(self.spatialTemporalVis.redraw)
        D.actionLoadTS.triggered.connect(self.loadTimeSeries)
        D.actionClearTS.triggered.connect(self.clearTimeSeries)
        D.actionSaveTS.triggered.connect(self.ua_saveTSFile)
        D.actionAddTSExample.triggered.connect(self.ua_loadExampleTS)


        #connect buttons with actions
        D.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())
        D.actionSettings.triggered.connect(lambda : PropertyDialogUI(self.ui).exec_())

        D.actionFirstTSD.triggered.connect(lambda: self.setDOISliderValue('first'))
        D.actionLastTSD.triggered.connect(lambda: self.setDOISliderValue('last'))
        D.actionNextTSD.triggered.connect(lambda: self.setDOISliderValue('next'))
        D.actionPreviousTSD.triggered.connect(lambda: self.setDOISliderValue('previous'))


        D.dockRendering.actionSetSubsetSize.triggered.connect(lambda : self.spatialTemporalVis.setSubsetSize(
                                                D.dockRendering.subsetSize()))
        D.actionSetExtent.triggered.connect(lambda: self.spatialTemporalVis.setSpatialExtent(self.ui.spatialExtent()))

        self.canvasCrs = QgsCoordinateReferenceSystem()


    def loadImageFiles(self, files):
        assert isinstance(files, list)
        self.TS.addFiles(files)


    def loadTimeSeries(self, path=None, n_max=None):
        if path is None or path is False:
            path = QFileDialog.getOpenFileName(self.ui, 'Open Time Series file', '')

        if os.path.exists(path):
            M = self.ui.dockTimeSeries.tableView_TimeSeries.model()
            M.beginResetModel()
            self.clearTimeSeries()
            self.TS.loadFromFile(path, n_max=n_max)
            M.endResetModel()


    def zoomTo(self, key):
        if key == 'maxExtent':
            ext = self.TS.getMaxSpatialExtent(self.ui.dockNavigation.crs())
            self.spatialTemporalVis.setSpatialExtent(ext)
        elif key == 'pixelScale':
            s = ""


    def icon(self):
        return TimeSeriesViewer.icon()

    def timeseriesChanged(self):

        if not self.hasInitialCenterPoint:
            if len(self.TS.data) > 0:
                extent = self.TS.getMaxSpatialExtent()
                self.spatialTemporalVis.setSubsetSize(self.ui.dockRendering.subsetSize())
                self.spatialTemporalVis.setSpatialExtent(extent)
                self.hasInitialCenterPoint = True

            if len(self.spatialTemporalVis.MVC) == 0:
                # add two empty band-views by default
                self.spatialTemporalVis.createMapView()
                self.spatialTemporalVis.createMapView()

        if len(self.TS.data) == 0:
            self.hasInitialCenterPoint = False



    def ua_saveTSFile(self):
        path = QFileDialog.getSaveFileName(self.ui, caption='Save Time Series file')
        if path is not None:
            self.TS.saveToFile(path)


    def ua_loadExampleTS(self):
        from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
        if not os.path.exists(PATH_EXAMPLE_TIMESERIES):
            QMessageBox.information(self.ui, 'File not found', '{} - this file describes an exemplary time series.'.format(path_example))
        else:
            self.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES)



    def ua_selectByRectangle(self):
        if self.RectangleMapTool is not None:
            self.qgsCanvas.setMapTool(self.RectangleMapTool)

    def ua_selectByCoordinate(self):
        if self.PointMapTool is not None:
            self.qgsCanvas.setMapTool(self.PointMapTool)

    #todo: define as qt slot
    def setSpatialSubset(self, spatialExtent):
        #keep specified CRS but translate extent
        oldExtent = self.ui.spatialExtent()
        self.ui.setSpatialExtent(extent)
        self.spatialTemporalVis.setSpatialExtent(extent)

    def qgs_handleMouseDown(self, pt, btn):
        pass



    def ua_TSprogress(self, v_min, v, v_max):
        assert v_min <= v and v <= v_max
        if v_min < v_max:
            P = self.ui.progressBar
            if P.minimum() != v_min or P.maximum() != v_max:
                P.setRange(v_min, v_max)
            else:
                s = ""

            P.setValue(v)

    def datesAdded(self, dates):
        assert isinstance(dates, list)
        self.ui.dockTimeSeries.tableView_TimeSeries.resizeColumnsToContents()
        self.timeseriesChanged()


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('EnMAPBox', message)





    def ua_addTSD_to_QGIS(self, TSD, bands):

        s = ""

        pass


    def unload(self):
        """Removes the plugin menu item and icon """
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.ui.show()



    def scrollToDate(self, date_of_interest):
        QApplication.processEvents()
        HBar = self.ui.scrollArea_imageChips.horizontalScrollBar()
        TSDs = list(self.CHIPWIDGETS.keys())
        if len(TSDs) == 0:
            return

        #get date INDEX that is closest to requested date
        if type(date_of_interest) is str:
            date_of_interest = np.datetime64(date_of_interest)


        if type(date_of_interest) is np.datetime64:
            i_doi = TSDs.index(sorted(TSDs, key=lambda TSD: abs(date_of_interest - TSD.getDate()))[0])
        else:
            i_doi = date_of_interest

        step = int(float(HBar.maximum()) / (len(TSDs)+1))
        HBar.setSingleStep(step)
        HBar.setPageStep(step*5)
        HBar.setValue(i_doi * step)


    def showSubset(self, renderJob, pixmap):

        assert isinstance(renderJob, RenderJob)
        chipLabel = self.CHIPWIDGETS[renderJob.TSD][renderJob.destinationId]
        chipLabel.setPixmap(pixmap)
        chipLabel.setFixedSize(pixmap.size())
        chipLabel.update()
        s = ""

    def ua_collect_date(self, ICL, event):
        if self.ui.rb_labeling_activate.isChecked():
            txt = self.ui.tb_labeling_text.toPlainText()
            reg = re.compile('\d{4}-\d{2}-\d{2}', re.I | re.MULTILINE)
            dates = set([np.datetime64(m) for m in reg.findall(txt)])
            doi = ICL.TSD.getDate()

            if event.button() == Qt.LeftButton:
                dates.add(doi)
            elif event.button() == Qt.MiddleButton and doi in dates:
                dates.remove(doi)

            dates = sorted(list(dates))
            txt = ' '.join([d.astype(str) for d in dates])
            self.ui.tb_labeling_text.setText(txt)


    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def ua_addTSImages(self, files=None):
        if files is None:
            files = QFileDialog.getOpenFileNames()

        if files:
            self.TS.addFiles(files)

    def clearTimeSeries(self):
        #remove views

        M = self.ui.dockTimeSeries.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.clear()
        M.endResetModel()

    def getSelectedTSDs(self):
        TV = self.ui.tableView_TimeSeries
        TVM = TV.model()
        return [TVM.getTimeSeriesDatumFromIndex(idx) for idx in TV.selectionModel().selectedRows()]


def disconnect_signal(signal):
    while True:
        try:
            signal.disconnect()
        except TypeError:
            break


def showRGBData(data):
    from scipy.misc import toimage
    toimage(data).show()

def run_tests():

    if False:

        pathImg = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_BOA.vrt'
        pathMsk = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_Msk.vrt'

        if False:
            TSD = TimeSeriesDatum(pathImg)
            TSD.setMask(pathMsk)

            c = [670949.883,-786288.771]

            w_x = w_y = 1000 #1km box
            srs = TSD.getSpatialReference()
            ring = ogr.Geometry(ogr.wkbLinearRing)
            import itertools
            for x,y in itertools.product([1000, -1000], repeat=2):
                ring.AddPoint(c[0]+x, c[1]+y)
            ring.AssignSpatialReference(srs)
            bb = ogr.Geometry(ogr.wkbPolygon)
            bb.AddGeometry(ring)
            bb.AssignSpatialReference(srs)




        def getChip3d_OLD(chips, r,g,b, range_r, range_g, range_b):

            nl, ns = chips[r].shape
            a3d = np.ndarray((3,nl,ns), dtype='float')

            rgb_idx = [r,g,b]
            ranges = [range_r, range_g, range_b]

            for i, rgb_i in enumerate(rgb_idx):
                range = ranges[i]
                data = chips[rgb_i].astype('float')
                data -= range[0]
                data *= 255./range[1]
                a3d[i,:] = data

            np.clip(a3d, 0, 255, out=a3d)

            return a3d.astype('uint8')

        app  = QApplication([])
        main = PictureTest()
        main.show()

        range_r = [0,500]
        range_g = [0,500]
        range_b = [0,500]

        bands = [3,2,1]
        #chipData = TSD.readSpatialChip(bb,bands=bands )

        #main.addNumpy(getChip3d(chipData, bands, (range_r, range_g, range_b)))
        app.exec_()
        exit(0)

    if False:
        dirSrcLS = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
        filesImgLS = file_search(dirSrcLS, '2014*_BOA.vrt')
        filesMsk = file_search(dirSrcLS, '2014*_Msk.vrt')
        TS = TimeSeries(imageFiles=filesImgLS, maskFiles=filesMsk)

        print(TS)
        exit(0)


    if True:
        import PyQt4.Qt

        app=PyQt4.Qt.QApplication([])
        S = TimeSeriesViewer(None)
        S.run()

        if True:
            dirSrcLS = r'\\141.20.140.107\NAS_Processing\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
            dirSrcRE = r'\\141.20.140.91\SAN_RSDBrazil\RapidEye\3A_VRTs'
            filesImgLS = file_search(dirSrcLS, '20*_BOA.vrt')
            filesImgRE = file_search(dirSrcRE, '*.vrt', recursive=True)
            #filesMsk = file_search(dirSrc, '2014*_Msk.vrt')
            S.ua_addTSImages(files=filesImgLS[0:2])
            S.ua_addTSImages(files=filesImgRE[0:2])
            #S.ua_addTSImages(files=filesImgLS)
            #S.ua_addTSImages(files=filesImgRE)
            #S.ua_loadExampleTS()


            #S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        app.exec_()

    if False:
        import qgis.core

        # supply path to where is your qgis installed

        #QgsApplication.setPrefixPath("/Applications/QGIS_2.12.app/Contents/MacOS/QGIS", True)

        # load providers
        QgsApplication.initQgis()

        a = QgsApplication([], True)

        S = TimeSeriesViewer(a)
        S.run()

        if True:
            dirSrcLS = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
            filesImgLS = file_search(dirSrcLS, '2014*_BOA.vrt')
            filesMsk = file_search(dirSrcLS, '2014*_Msk.vrt')
            S.ua_addTSImages(files=filesImgLS)
            S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        a.exec_()

    print('Tests done')
    exit(0)


if __name__ == '__main__':
    run_tests()
    print('Done')