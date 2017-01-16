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


from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument


class TimeSeriesTableModel(QAbstractTableModel):
    columnames = ['date','sensor','ns','nl','nb','image','mask']

    def __init__(self, TS, parent=None, *args):
        super(QAbstractTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)
        self.TS = TS

    def rowCount(self, parent = QModelIndex()):
        return len(self.TS)

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self._data[row:row+count]
        for i in toRemove:
            self._data.remove(i)

        self.endRemoveRows()

    def getDateFromIndex(self, index):
        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.TS):
                return self.TS.getTSDs()[i]
        return None

    def getTimeSeriesDatumFromIndex(self, index):

        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.TS):
                return self.TS.data[i]

        return None



    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None


        value = None
        ic_name = self.columnames[index.column()]
        TSD = self.getTimeSeriesDatumFromIndex(index)
        keys = list(TSD.__dict__.keys())
        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if ic_name == 'name':
                value = os.path.basename(TSD.pathImg)
            elif ic_name == 'sensor':
                if role == Qt.ToolTipRole:
                    value = TSD.sensor.getDescription()
                else:
                    value = str(TSD.sensor)
            elif ic_name == 'date':
                value = '{}'.format(TSD.date)
            elif ic_name == 'image':
                value = TSD.pathImg
            elif ic_name == 'mask':
                value = TSD.pathMsk
            elif ic_name in keys:
                value = TSD.__dict__[ic_name]
            else:
                s = ""
        elif role == Qt.BackgroundColorRole:
            value = None
        elif role == Qt.UserRole:
            value = TSD

        return value

    #def flags(self, index):
    #    return Qt.ItemIsEnabled

    def flags(self, index):
        if index.isValid():
            item = self.getTimeSeriesDatumFromIndex(index)
            cname = self.columnames[index.column()]
            if cname.startswith('d'): #relative values can be edited
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
            else:
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

class TimeSeriesItemModel(QAbstractItemModel):

    def __init__(self, TS):
        QAbstractItemModel.__init__(self)
        #self.rootItem = TreeItem[]
        assert type(TS) is TimeSeries
        self.TS = TS

    def index(self, row, column, parent = QModelIndex()):
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def setData(self, index, value, role = Qt.EditRole):
        if role == Qt.EditRole:
            row = index.row()

            return False
        return False

    def data(self, index, role=Qt.DisplayRole):
        data = None
        if role == Qt.DisplayRole or role == Qt.EditRole:
            data = 'sampletext'


        return data

    def flags(self, QModelIndex):
        return Qt.ItemIsSelectable

    def rowCount(self, index=QModelIndex()):
        return len(self.TS)

    #---------------------------------------------------------------------------
    def columnCount(self, index=QModelIndex()):
        return 1


class TimeSeriesDateViewManager(QObject):

    def __init__(self, timeSeriesViewer):
        assert isinstance(timeSeriesViewer, TimeSeriesViewer)
        super(TimeSeriesDateViewManager, self).__init__()

        self.TSV = timeSeriesViewer
        self.TSDViews = list()

        self.mapViewManager = self.TSV.mapViewManager
        self.mapViewManager.sigMapViewAdded.connect(self.addMapView)
        self.mapViewManager.sigMapViewRemoved.connect(self.removeMapView)
        self.mapViewManager.sigMapViewVisibility.connect(self.setMapViewVisibility)

        self.setSpatialExtent(self.TSV.TS.getMaxSpatialExtent())
        self.setMaxTSDViews()
        self.initTimeSeries(self.TSV.TS)
        self.L = self.TSV.ui.scrollAreaSubsetContent.layout()
        self.setSubsetSize(QSize(100,50))


    def activateMapTool(self, key):
        for tsdv in self.TSDViews:
            tsdv.activateMapTool(key)


    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size
        for tsdv in self.TSDViews:
            tsdv.setSubsetSize(size)
        self.adjustScrollArea()

    def redraw(self):
        for tsdv in self.TSDViews:
            tsdv.redraw()


    def adjustScrollArea(self):

        m = self.L.contentsMargins()
        n = len(self.TSDViews)
        if n > 0:
            refTSDView = self.TSDViews[0]
            size = refTSDView.ui.size()

            w = n * size.width() + (n-1) * (m.left()+ m.right())
            h = max([refTSDView.ui.minimumHeight() + m.top() + m.bottom(),
                     self.TSV.ui.scrollAreaSubsets.height()-25])

            self.L.parentWidget().setFixedSize(w,h)


    def initTimeSeries(self, TS):
        assert isinstance(TS, TimeSeries)
        self.TS = TS
        self.TS.sigTimeSeriesDatesAdded.connect(self.createTSDViews)

    def setMaxTSDViews(self, n=-1):
        self.nMaxTSDViews = n
        #todo: remove views

    def setSpatialExtent(self, extent):
        self.extent = extent
        if extent:
            assert isinstance(extent, SpatialExtent)
            tsdviews = sorted(self.TSDViews, key=lambda t:t.TSD)
            for tsdview in tsdviews:
                tsdview.setSpatialExtent(extent)

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
        assert isinstance(bandView, MapViewDefinition)
        assert isinstance(isVisible, bool)

        for tsdv in self.TSDViews:
            tsdv.setMapViewVisibility(bandView, isVisible)


    def addMapView(self, bandView):
        assert isinstance(bandView, MapViewDefinition)

        w = self.L.parentWidget()
        w.setUpdatesEnabled(False)

        for tsdv in self.TSDViews:
            tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.TSDViews:
            tsdv.insertMapView(bandView)

        for tsdv in self.TSDViews:
            tsdv.ui.setUpdatesEnabled(True)

        w.setUpdatesEnabled(True)



    def removeMapView(self, bandView):
        assert isinstance(bandView, MapViewDefinition)
        for tsdv in self.TSDViews:
            tsdv.removeMapView(bandView)

    def createTSDViews(self, timeSeriesDates):
        for TSD in timeSeriesDates:
            assert isinstance(TSD, TimeSeriesDatum)
            tsdView = TimeSeriesDatumView(TSD)
            tsdView.setSubsetSize(self.subsetSize)
            tsdView.sigExtentsChanged.connect(self.setSpatialExtent)
            for i, bandView in enumerate(self.mapViewManager):
                tsdView.insertMapView(bandView)
            if self.extent:
                tsdView.setSpatialExtent(self.extent)
            self.addTSDView(tsdView)


    def removeTSD(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        tsdvs = [tsdv for tsdv in self.TSDViews if tsdv.TSD == TSD]
        assert len(tsdvs) == 1
        self.removeTSDView(tsdvs[0])

    def removeTSDView(self, TSDV):
        assert isinstance(TSDV, TimeSeriesDatumView)
        self.TSDViews.remove(TSDV)

    def addTSDView(self, TSDV):
        assert isinstance(TSDV, TimeSeriesDatumView)

        if len(self.TSDViews) < 10:
            pass

        bisect.insort(self.TSDViews, TSDV)

        TSDV.ui.setParent(self.L.parentWidget())
        self.L.addWidget(TSDV.ui)

        self.adjustScrollArea()
        #self.TSV.ui.scrollAreaSubsetContent.update()
        #self.TSV.ui.scrollAreaSubsets.update()
        s = ""




class MapViewDefinition(QObject):


    sigRemoveMapView = pyqtSignal(object)
    sigHideMapView = pyqtSignal()
    sigShowMapView = pyqtSignal()
    sigTitleChanged = pyqtSignal(str)

    def __init__(self, recommended_bands=None, parent=None, showSensorNames=True):
        super(MapViewDefinition, self).__init__()
        self.ui = MapViewDefinitionUI(self, parent=parent)
        self.ui.create()
        self.setVisibility(True)

        #forward actions with reference to this band view

        self.ui.actionRemoveMapView.triggered.connect(lambda: self.sigRemoveMapView.emit(self))
        self.ui.sigHideMapView.connect(lambda : self.sigHideMapView.emit())
        self.ui.sigShowMapView.connect(lambda: self.sigShowMapView.emit())
        self.sensorViews = collections.OrderedDict()
        self.mShowSensorNames = showSensorNames


    def setVisibility(self, isVisible):
        self.ui.setVisibility(isVisible)


    def visibility(self):
        return self.ui.visibility()

    def setTitle(self, title):
        self.mTitle = title
        self.ui.labelName.setText(title)
        self.sigTitleChanged.emit(self.mTitle)

    def title(self):
        return self.mTitle

    def showSensorNames(self, b):
        assert isinstance(b, bool)
        self.mShowSensorNames = b

        for s,w in self.sensorViews.items():
            w.showSensorName(b)


    def removeSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        if sensor in self.sensorViews.keys():
            self.sensorViews[sensor].close()
            self.sensorViews.pop(sensor)
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
        w = MapViewRenderSettings(sensor)
        #w.showSensorName(False)
        self.sensorViews[sensor] = w
        l = self.ui.sensorList
        i = l.count()
        l.addWidget(w.ui)


    def getSensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.sensorViews[sensor]





class MapViewManager(QObject):

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigMapViewAdded = pyqtSignal(MapViewDefinition)
    sigMapViewRemoved = pyqtSignal(MapViewDefinition)
    sigMapViewVisibility = pyqtSignal(MapViewDefinition, bool)

    def __init__(self, timeSeriesViewer):
        assert isinstance(timeSeriesViewer, TimeSeriesViewer)
        super(MapViewManager, self).__init__()

        self.TSV = timeSeriesViewer
        self.ui = self.TSV.ui
        self.mapViewsDefinitions = []
        self.mapViewButtons = dict()


    def removeSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)

        removed = False
        for view in self.mapViewsDefinitions:
            removed = removed and view.removeSensor(sensor)

        if removed:
            self.sigSensorRemoved(sensor)


    def createMapView(self):
        btnList = self.TSV.ui.dockMapViews.BVButtonList
        btn = QToolButton(btnList)
        btnList.layout().insertWidget(btnList.layout().count() - 1, btn)

        mapView = MapViewDefinition(parent=self.TSV.ui.dockMapViews.scrollAreaMapViews, showSensorNames=False)
        mapView.sigRemoveMapView.connect(self.removeMapView)
        mapView.sigShowMapView.connect(lambda : self.sigMapViewVisibility.emit(mapView, mapView.visibility()))
        mapView.sigHideMapView.connect(lambda: self.sigMapViewVisibility.emit(mapView, mapView.visibility()))
        #mapView.sigTitleChanged.connect(btn.setText)

        #bandView.setTitle('#{}'.format(len(self)))

        self.mapViewButtons[mapView] = btn
        self.mapViewsDefinitions.append(mapView)
        for sensor in self.TSV.TS.Sensors:
            mapView.addSensor(sensor)

        btn.clicked.connect(lambda : self.showMapViewDefinition(mapView))
        self.refreshMapViewTitles()
        self.sigMapViewAdded.emit(mapView)

        if len(self) == 1:
            self.showMapViewDefinition(mapView)

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapViewDefinition)
        btn = self.mapViewButtons[mapView]
        btnList = self.TSV.ui.dockMapViews.BVButtonList

        idx = self.mapViewsDefinitions.index(mapView)

        self.mapViewsDefinitions.remove(mapView)
        self.mapViewButtons.pop(mapView)

        mapView.ui.setVisible(False)
        btn.setVisible(False)
        btnList.layout().removeWidget(btn)
        l = self.ui.dockMapViews.scrollAreaMapsViewDockContent.layout()

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
            s = ""

    def showMapViewDefinition(self, mapViewDefinition):
        assert mapViewDefinition in self.mapViewsDefinitions
        assert isinstance(mapViewDefinition, MapViewDefinition)
        l = self.ui.dockMapViews.scrollAreaMapsViewDockContent.layout()

        for d in self.recentMapViewDefinitions():
            d.ui.setVisible(False)
            l.removeWidget(d.ui)

        l.insertWidget(l.count() - 1, mapViewDefinition.ui)
        mapViewDefinition.ui.setVisible(True)

    def recentMapViewDefinitions(self):
        parent = self.ui.dockMapViews.scrollAreaMapsViewDockContent
        return [ui.mapViewDefinition() for ui in parent.findChildren(MapViewDefinitionUI)]


    def setMapViewVisibility(self, bandView, isVisible):
        assert isinstance(bandView, MapViewDefinition)
        assert isinstance(isVisible, bool)





    def __len__(self):
        return len(self.mapViewsDefinitions)

    def __iter__(self):
        return iter(self.mapViewsDefinitions)

    def __getitem__(self, key):
        return self.mapViewsDefinitions[key]

    def __contains__(self, mapView):
        return mapView in self.mapViewsDefinitions


class TimeSeriesDatumView(QObject):

    sigExtentsChanged = pyqtSignal(SpatialExtent)

    def __init__(self, TSD, parent=None):

        super(TimeSeriesDatumView, self).__init__()
        self.ui = TimeSeriesDatumViewUI(parent)
        self.ui.create()

        self.TSD = None

        self.mapCanvases = dict()
        self.mapOrder = []
        self.setTimeSeriesDatum(TSD)
        self.L = self.ui.layout()
        self.wOffset = self.L.count()-1
        self.setSubsetSize(QSize(150,100))


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
        m = self.L.contentsMargins()

        self.ui.labelTitle.setFixedWidth(size.width())
        self.ui.line.setFixedWidth(size.width())

        #apply new subset size to existing canvases
        for c in self.mapCanvases.values():
            c.setFixedSize(size)

        self.ui.setFixedWidth(size.width() + 2*(m.left() + m.right()))
        n = len(self.mapCanvases)
        #todo: improve size forecast
        self.ui.setMinimumHeight((n+1) * size.height())


    def setTimeSeriesDatum(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        self.TSD = TSD
        self.ui.labelTitle.setText(str(TSD.date))

        for c in self.mapCanvases.values():
            c.setLayer(self.TSD.pathImg)

    def removeMapView(self, bandView):
        self.mapOrder.remove(bandView)
        canvas = self.mapCanvases.pop(bandView)
        self.L.removeWidget(canvas)
        canvas.close()

    def redraw(self):
        for c in self.mapCanvases.values():
            c.refreshAllLayers()

    def insertMapView(self, bandView, i=-1):
        assert isinstance(bandView, MapViewDefinition)
        assert bandView not in self.mapOrder
        if len(self.mapCanvases) != len(self.mapOrder):
            s = ""

        assert i >= -1 and i <= len(self.mapOrder)
        if i == -1:
            i = len(self.mapCanvases)

        canvas = MapViewMapCanvas(self.ui)
        canvas.setLayer(self.TSD.pathImg)
        canvas.setFixedSize(self.subsetSize)
        canvas.extentsChanged.connect(lambda : self.sigExtentsChanged.emit(canvas.spatialExtent()))


        self.mapCanvases[bandView] = canvas
        self.mapOrder.insert(i, bandView)
        self.L.insertWidget(self.wOffset + i, canvas)

    def __lt__(self, other):

        return self.TSD < other.TSD


class RenderJob(object):

    def __init__(self, TSD, renderer, destinationId=None):
        assert isinstance(TSD, TimeSeriesDatum)
        assert isinstance(renderer, QgsRasterRenderer)

        self.TSD = TSD
        self.renderer = renderer
        self.destinationId = destinationId

    def __eq__(self, other):
        if not isinstance(other, RenderJob):
            return False
        return self.TSD == other.TSD and \
               self.renderer == other.renderer and \
               self.destinationId == other.destinationId



list2str = lambda ll : '\n'.join([str(l) for l in ll])


class QgsInstanceInteraction(QObject):

    def __init__(self, iface, TSV_UI):
        super(QgsInstanceInteraction, self).__init__()

        self.iface = iface
        self.ui = TSV_UI
        self.cbVectorLayer = TSV_UI.cbQgsVectorLayer

    def extent(self):
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

        self.ui = TimeSeriesViewerUI()
        if iface:
            import timeseriesviewer
            timeseriesviewer.QGIS_TSV_BRIDGE = QgsInstanceInteraction(iface, self.ui)
            self.ui.setQgsLinkWidgets()

        #init empty time series
        self.TS = TimeSeries()
        self.hasInitialCenterPoint = False
        self.TS.sigTimeSeriesDatesAdded.connect(self.datesAdded)
        self.TS.sigProgress.connect(self.ua_TSprogress)

        #init TS model
        TSM = TimeSeriesTableModel(self.TS)
        D = self.ui
        #self.ICP = D.scrollAreaSubsetContent.layout()
        #D.scrollAreaMapViews.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #self.BVP = self.ui.scrollAreaMapViews.layout()

        D.tableView_TimeSeries.setModel(TSM)
        D.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)

        self.mapViewManager = MapViewManager(self)
        self.timeSeriesDateViewManager = TimeSeriesDateViewManager(self)

        self.ValidatorPxX = QIntValidator(0,99999)
        self.ValidatorPxY = QIntValidator(0,99999)

        #connect actions with logic

        #D.btn_showPxCoordinate.clicked.connect(lambda: self.showSubsetsStart())
        #connect actions with logic

        D.actionSelectCenter.triggered.connect(lambda : self.timeSeriesDateViewManager.activateMapTool('selectCenter'))
        D.actionSelectArea.triggered.connect(lambda : self.timeSeriesDateViewManager.activateMapTool('selectArea'))
        D.actionZoomMaxExtent.triggered.connect(lambda : self.zoomTo('maxExtent'))
        D.actionZoomPixelScale.triggered.connect(lambda: self.zoomTo('pixelScale'))
        D.actionZoomIn.triggered.connect(lambda: self.timeSeriesDateViewManager.activateMapTool('zoomIn'))
        D.actionZoomOut.triggered.connect(lambda: self.timeSeriesDateViewManager.activateMapTool('zoomOut'))
        D.actionPan.triggered.connect(lambda: self.timeSeriesDateViewManager.activateMapTool('pan'))

        D.actionAddMapView.triggered.connect(self.mapViewManager.createMapView)

        D.actionAddTSD.triggered.connect(self.ua_addTSImages)
        D.actionRemoveTSD.triggered.connect(self.removeTimeSeriesDates)
        D.actionRedraw.triggered.connect(self.timeSeriesDateViewManager.redraw)
        D.actionLoadTS.triggered.connect(self.loadTimeSeries)
        D.actionClearTS.triggered.connect(self.clearTimeSeries)
        D.actionSaveTS.triggered.connect(self.ua_saveTSFile)
        D.actionAddTSExample.triggered.connect(self.ua_loadExampleTS)


        #connect buttons with actions
        D.btnClearLabelList.clicked.connect(D.tbCollectedLabels.clear)
        D.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())
        D.actionSettings.triggered.connect(lambda : PropertyDialogUI(self.ui).exec_())

        D.actionFirstTSD.triggered.connect(lambda: self.setDOISliderValue('first'))
        D.actionLastTSD.triggered.connect(lambda: self.setDOISliderValue('last'))
        D.actionNextTSD.triggered.connect(lambda: self.setDOISliderValue('next'))
        D.actionPreviousTSD.triggered.connect(lambda: self.setDOISliderValue('previous'))


        D.sliderDOI.valueChanged.connect(self.setDOI)

        D.actionSetSubsetSize.triggered.connect(lambda : self.timeSeriesDateViewManager.setSubsetSize(
                                                self.ui.subsetSize()))
        D.actionSetExtent.triggered.connect(lambda: self.timeSeriesDateViewManager.setSpatialExtent(self.ui.spatialExtent()))

        self.canvasCrs = QgsCoordinateReferenceSystem()


    def zoomTo(self, key):
        if key == 'maxExtent':
            ext = self.TS.getMaxSpatialExtent(self.ui.crs())
            self.timeSeriesDateViewManager.setSpatialExtent(ext)
        elif key == 'pixelScale':
            s = ""


    def setDOISliderValue(self, key):
        ui = self.ui
        v = ui.sliderDOI.value()
        if key == 'first':
            v = ui.sliderDOI.minimum()
        elif key == 'last':
            v = ui.sliderDOI.maximum()
        elif key =='next':
            v = min([v+1,ui.sliderDOI.maximum()])
        elif key =='previous':
            v = max([v - 1, ui.sliderDOI.minimum()])
        ui.sliderDOI.setValue(v)

    def setDOI(self, i):

        TSD = None

        if len(self.TS) == 0:
            text = '<empty timeseries>'
        else:
            assert i <= len(self.TS)
            TSD = self.TS.data[i - 1]
            text = str(TSD.date)

        self.ui.labelDOIValue.setText(text)

        if TSD:
            self.timeSeriesDateViewManager.navToDOI(TSD)


    def icon(self):
        return TimeSeriesViewer.icon()

    def timeseriesChanged(self):
        D = self.ui
        D.sliderDOI.setMinimum(1)
        l = len(self.TS.data)
        D.sliderDOI.setMaximum(l)
        #get meaningfull tick intervall
        for tickInterval in [1,5,10,25,50,100,200]:
            if (D.sliderDOI.size().width() / float(l) * tickInterval) > 5:
                break
        D.sliderDOI.setTickInterval(tickInterval)

        if not self.hasInitialCenterPoint:
            if len(self.TS.data) > 0:
                extent = self.TS.getMaxSpatialExtent(self.canvasCrs)
                self.timeSeriesDateViewManager.setSubsetSize(self.ui.subsetSize())
                self.timeSeriesDateViewManager.setSpatialExtent(extent)
                self.ui.setSpatialExtent(extent)
                self.hasInitialCenterPoint = True

            if len(self.mapViewManager) == 0:
                # add two empty band-views by default
                self.mapViewManager.createMapView()
                self.mapViewManager.createMapView()

        if len(self.TS.data) == 0:
            self.hasInitialCenterPoint = False


    def loadTimeSeries(self, path=None, n_max=None):
        if path is None or path is False:
            path = QFileDialog.getOpenFileName(self.ui, 'Open Time Series file', '')

        if os.path.exists(path):


            M = self.ui.tableView_TimeSeries.model()
            M.beginResetModel()
            self.clearTimeSeries()
            self.TS.loadFromFile(path, n_max=n_max)
            M.endResetModel()

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
        self.timeSeriesDateViewManager.setSpatialExtent(extent)

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
        self.ui.tableView_TimeSeries.resizeColumnsToContents()
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
            M = self.ui.tableView_TimeSeries.model()
            M.beginResetModel()
            self.TS.addFiles(files)
            M.endResetModel()
            self.refreshMapViews()

        self.check_enabled()




    def clearTimeSeries(self):
        #remove views

        M = self.ui.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.clear()
        M.endResetModel()


    def removeTimeSeriesDates(self, TSDs=None):
        if TSDs is None:
            TSDs = self.getSelectedTSDs()
        assert isinstance(TSDs,list)

        M = self.ui.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.removeDates(TSDs)
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

            print(TSD)

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