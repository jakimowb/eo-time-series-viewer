import os, sys, re, fnmatch, collections, copy, traceback, six, bisect
import logging
logger = logging.getLogger(__name__)
from qgis.core import *
import numpy as np
from timeseriesviewer.utils import *
from timeseriesviewer.main import TimeSeriesViewer
from timeseriesviewer.timeseries import SensorInstrument, TimeSeriesDatum


class MapView(QObject):

    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibility = pyqtSignal(bool)
    sigVectorVisibility = pyqtSignal(bool)

    sigTitleChanged = pyqtSignal(str)
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)
    from timeseriesviewer.crosshair import CrosshairStyle
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)
    sigShowCrosshair = pyqtSignal(bool)
    sigVectorLayerChanged = pyqtSignal()

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

        self.vectorLayer = None
        self.setVectorLayer(None)

        #forward actions with reference to this band view
        self.spatialExtent = None
        self.ui.actionRemoveMapView.triggered.connect(lambda: self.sigRemoveMapView.emit(self))
        self.ui.actionApplyStyles.triggered.connect(self.applyStyles)
        self.ui.actionShowCrosshair.toggled.connect(self.setShowCrosshair)
        self.ui.sigShowMapView.connect(lambda: self.sigMapViewVisibility.emit(True))
        self.ui.sigHideMapView.connect(lambda: self.sigMapViewVisibility.emit(False))
        self.ui.sigVectorVisibility.connect(self.sigVectorVisibility.emit)
        self.sensorViews = collections.OrderedDict()

        self.mSpatialExtent = None

    def setVectorLayer(self, lyr):
        if isinstance(lyr, QgsVectorLayer):
            self.vectorLayer = lyr
            self.vectorLayer.rendererChanged.connect(self.sigVectorLayerChanged)
            self.ui.btnVectorOverlayVisibility.setEnabled(True)


        else:
            self.vectorLayer = None
            self.ui.btnVectorOverlayVisibility.setEnabled(False)

        self.sigVectorLayerChanged.emit()

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

    def visibleVectorOverlay(self):
        return isinstance(self.vectorLayer, QgsVectorLayer) and \
            self.ui.btnVectorOverlayVisibility.isChecked()



    def setTitle(self, title):
        self.mTitle = title
        #self.ui.setTitle('Map View' + title)
        self.sigTitleChanged.emit(self.mTitle)

    def title(self):
        return self.mTitle

    def setCrosshairStyle(self, crosshairStyle):
        self.sigCrosshairStyleChanged.emit(crosshairStyle)
    def setShowCrosshair(self, b):
        self.sigShowCrosshair.emit(b)

    def removeSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        if sensor in self.sensorViews.keys():
            w = self.sensorViews.pop(sensor)
            from timeseriesviewer.ui.widgets import MapViewSensorSettings
            assert isinstance(w, MapViewSensorSettings)
            l = self.ui.sensorList
            l.removeWidget(w.ui)
            w.ui.close()
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


    def getSensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.sensorViews[sensor]





class TimeSeriesDatumView(QObject):

    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
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

    def refresh(self):
        if self.ui.isVisible():
            for c in self.mapCanvases.values():
                if c.isVisible():
                    c.refreshAllLayers()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)

        i = self.MVC.index(mapView)

        from timeseriesviewer.mapcanvas import TsvMapCanvas
        canvas = TsvMapCanvas(self, mapView, parent=self.ui)

        canvas.setFixedSize(self.subsetSize)
        canvas.extentsChanged.connect(lambda : self.sigSpatialExtentChanged.emit(canvas.spatialExtent()))
        canvas.renderStarting.connect(lambda : self.sigLoadingStarted.emit(mapView, self.TSD))
        canvas.mapCanvasRefreshed.connect(lambda: self.sigLoadingFinished.emit(mapView, self.TSD))
        canvas.sigShowProfiles.connect(mapView.sigShowProfiles.emit)
        canvas.sigSpatialExtentChanged.connect(mapView.sigSpatialExtentChanged.emit)

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
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def __init__(self, timeSeriesViewer):
        assert isinstance(timeSeriesViewer, TimeSeriesViewer)
        super(SpatialTemporalVisualization, self).__init__()

        self.ui = timeSeriesViewer.ui
        self.scrollArea = self.ui.scrollAreaSubsets
        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.TS
        self.targetLayout = self.ui.scrollAreaSubsetContent.layout()
        self.dockMapViews = self.ui.dockMapViews
        self.MVC = MapViewCollection(self)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.vectorOverlay = None

        self.timeSeriesDateViewCollection = TimeSeriesDateViewCollection(self)
        self.timeSeriesDateViewCollection.sigResizeRequired.connect(self.adjustScrollArea)
        self.timeSeriesDateViewCollection.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.timeSeriesDateViewCollection.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        self.timeSeriesDateViewCollection.sigSpatialExtentChanged.connect(self.onSpatialExtentChanged)
        self.TS.sigTimeSeriesDatesAdded.connect(self.timeSeriesDateViewCollection.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.timeSeriesDateViewCollection.removeDates)
        #add dates, if already existing
        self.timeSeriesDateViewCollection.addDates(self.TS[:])

        self.setSpatialExtent(self.TS.getMaxSpatialExtent())
        self.setSubsetSize(QSize(100,50))

    def setCrosshairStyle(self, crosshairStyle):
        self.MVC.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        self.MVC.setShowCrosshair(b)

    def setVectorLayer(self, lyr):
        self.MVC.setVectorLayer(lyr)

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

    def refresh(self):
        for tsdView in self.timeSeriesDateViewCollection:
            tsdView.refresh()


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
        if extent:
            self.timeSeriesDateViewCollection.setSpatialExtent(extent)
            self.onSpatialExtentChanged(extent)

    def onSpatialExtentChanged(self, extent):
        self.extent = extent
        self.sigSpatialExtentChanged.emit(extent)

    def navigateToTSD(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        #get widget related to TSD
        tsdv = self.timeSeriesDateViewCollection.tsdView(TSD)
        assert isinstance(self.scrollArea, QScrollArea)
        self.scrollArea.ensureWidgetVisible(tsdv.ui)

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
    sigSpatialExtentChanged = pyqtSignal(QgsRectangle)

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


    def tsdView(self, tsd):
        r = [v for v in self.views if v.TSD == tsd]
        if len(r) == 1:
            return r[0]
        else:
            raise Exception('TSD not in list')

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

    def onSpatialExtentChanged(self, extent):
        for tsdview in self.orderedViews():
            tsdview.setSpatialExtent(extent)
        self.sigSpatialExtentChanged.emit(extent)

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
            tsdView.blockSignals(True)

        for tsdView in self.orderedViews():
            tsdView.setSubsetSize(size)

        for tsdView in self.orderedViews():
            tsdView.blockSignals(False)



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

            tsdView.sigSpatialExtentChanged.connect(self.onSpatialExtentChanged)
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
        self.STViz.TS.sigSensorRemoved.connect(self.removeSensor)
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

    def setCrosshairStyle(self, crosshairStyle):
        for mapView in self.mapViewsDefinitions:
            mapView.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        for mapView in self.mapViewsDefinitions:
            mapView.setShowCrosshair(b)

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

    def setVectorLayer(self, lyr):
        for mapView in self.mapViewsDefinitions:
            assert isinstance(mapView, MapView)
            mapView.setVectorLayer(lyr)

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



