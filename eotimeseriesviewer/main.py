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


r"""
File "D:\Programs\OSGeo4W\apps\Python27\lib\multiprocessing\managers.py", line
528, in start
self._address = reader.recv()
EOFError

see https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Multiprocessing
see https://github.com/CleanCut/green/issues/103 

"""
"""
path = os.path.abspath(os.path.join(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]
"""

import qgis.utils
from qgis.core import *
from qgis.gui import *
import qgis.utils
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer.profilevisualization import SpectralTemporalVisualization
from eotimeseriesviewer import SpectralProfile, SpectralLibrary, SpectralLibraryPanel
from eotimeseriesviewer.externals.qps.maptools import MapTools, CursorLocationMapTool, QgsMapToolSelect, QgsMapToolSelectionHandler
from eotimeseriesviewer.externals.qps.cursorlocationvalue import CursorLocationInfoModel, CursorLocationInfoDock
import eotimeseriesviewer.labeling

DEBUG = False

EXTRA_SPECLIB_FIELDS = [
    QgsField('date', QVariant.String, 'varchar'),
    QgsField('doy', QVariant.Int, 'int'),
    QgsField('sensor', QVariant.String, 'varchar')
]


class TimeSeriesViewerUI(QMainWindow,
                         loadUI('timeseriesviewer.ui')):

    def __init__(self, parent=None):
        """Constructor."""
        super(TimeSeriesViewerUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.addActions(self.findChildren(QAction))
        from eotimeseriesviewer import TITLE, icon, __version__

        self.mMapToolActions = []
        self.setWindowTitle('{} ({})'.format(TITLE, __version__))
        self.setWindowIcon(icon())
        if sys.platform == 'darwin':
            self.menuBar().setNativeMenuBar(False)

        # set button default actions -> this will show the action icons as well
        # I don't know why this is not possible in the QDesigner when QToolButtons are
        # placed outside a toolbar

        area = None

        def addDockWidget(dock):
            """
            shortcut to add a created dock and return it
            :param dock:
            :return:
            """
            self.addDockWidget(area, dock)
            return dock

        area = Qt.LeftDockWidgetArea

        # self.dockRendering = addDockWidget(docks.RenderingDockUI(self))

        if DEBUG:
            from eotimeseriesviewer.labeling import LabelingDock
            self.dockLabeling = addDockWidget(LabelingDock(self))
            self.dockLabeling.setHidden(True)

        from eotimeseriesviewer.sensorvisualization import SensorDockUI
        self.dockSensors = addDockWidget(SensorDockUI(self))

        from eotimeseriesviewer.mapvisualization import MapViewDock
        self.dockMapViews = addDockWidget(MapViewDock(self))

        self.dockCursorLocation = addDockWidget(CursorLocationInfoDock(self))

        # self.tabifyDockWidget(self.dockMapViews, self.dockRendering)
        self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)

        area = Qt.BottomDockWidgetArea
        # from timeseriesviewer.mapvisualization import MapViewDockUI
        # self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries = addDockWidget(TimeSeriesDockUI(self))
        self.dockTimeSeries.initActions(self)

        from eotimeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))
        from eotimeseriesviewer.labeling import LabelingDock
        self.dockLabeling = addDockWidget(LabelingDock(self))

        area = Qt.LeftDockWidgetArea
        self.dockAdvancedDigitizingDockWidget = addDockWidget(QgsAdvancedDigitizingDockWidget(self.dockLabeling.canvas(), self))
        self.dockAdvancedDigitizingDockWidget.setVisible(False)
        self.tabifyDockWidget(self.dockSensors, self.dockAdvancedDigitizingDockWidget)

        area = Qt.BottomDockWidgetArea
        panel = SpectralLibraryPanel(None)
        panel.setParent(self)
        self.dockSpectralLibrary = addDockWidget(panel)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockSpectralLibrary)

        #except Exception as ex:
        #    print('Unable to create SpectralLibrary panel', file=sys.stderr)
        #    print(ex, file=sys.stderr)
        #    self.dockSpectralLibrary = None
        #    self.dockSpectralLibrary = None

        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockLabeling)

        area = Qt.RightDockWidgetArea

        from eotimeseriesviewer.systeminfo import SystemInfoDock
        self.dockSystemInfo = addDockWidget(SystemInfoDock(self))
        self.dockSystemInfo.setVisible(False)

        for dock in self.findChildren(QDockWidget):

            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())

        self.dockTimeSeries.raise_()


    def registerMapToolAction(self, a:QAction):
        assert isinstance(a, QAction)
        if a not in self.mMapToolActions:
            self.mMapToolActions.append(a)
        a.setCheckable(True)
        a.toggled.connect(self.onMapToolActionToggled)

    def onMapToolActionToggled(self, b:bool):
        action = QApplication.instance().sender()
        assert isinstance(action, QAction)
        otherActions = [a for a in self.mMapToolActions if a != action]

        # enable / disable the other maptool actions
        if b is True:
            for a in otherActions:
                assert isinstance(a, QAction)
                a.setChecked(False)

        else:
            otherSelected = [a for a in otherActions if a.isChecked()]
            if len(otherSelected) == 0:
                action.setChecked(True)

        b = self.actionIdentify.isChecked()
        self.optionIdentifyCursorLocation.setEnabled(b)
        self.optionIdentifySpectralProfile.setEnabled(b)
        self.optionIdentifyTemporalProfile.setEnabled(b)
        self.optionMoveCenter.setEnabled(b)




LUT_MESSAGELOGLEVEL = {
                Qgis.Info: 'INFO',
                Qgis.Critical: 'INFO',
                Qgis.Warning: 'WARNING',
                Qgis.Success: 'SUCCESS',
                }


def showMessage(message, title, level):
    v = QgsMessageViewer()
    v.setTitle(title)
    #print('DEBUG MSG: {}'.format(message))
    v.setMessage(message, QgsMessageOutput.MessageHtml \
        if message.startswith('<html>')
    else QgsMessageOutput.MessageText)
    v.showMessage(True)



class TimeSeriesViewer(QgisInterface, QObject):

    _instance = None

    @staticmethod
    def instance():
        """
        Returns the TimeSeriesViewer instance
        :return:
        """
        return TimeSeriesViewer._instance

    sigCurrentLocationChanged = pyqtSignal([SpatialPoint],
                                           [SpatialPoint, QgsMapCanvas])

    sigCurrentSpectralProfilesChanged = pyqtSignal(list)
    sigCurrentTemporalProfilesChanged = pyqtSignal(list)


    def __init__(self):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """

        # assert TimeSeriesViewer.instance() is None

        QObject.__init__(self)
        QgisInterface.__init__(self)
        QApplication.processEvents()

        self.mMapLayerStore = QgsMapLayerStore()
        import eotimeseriesviewer.utils
        eotimeseriesviewer.utils.MAP_LAYER_STORES.insert(0, self.mapLayerStore())

        self.ui = TimeSeriesViewerUI()

        # Save reference to the QGIS interface
        import qgis.utils
        assert isinstance(qgis.utils.iface, QgisInterface)

        # init empty time series
        self.mTimeSeries = TimeSeries()
        self.mTimeSeries.setDateTimePrecision(DateTimePrecision.Day)
        self.mSpatialMapExtentInitialized = False
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)


        # map layer store

        # init other GUI components


        # self.ICP = D.scrollAreaSubsetContent.layout()
        # D.scrollAreaMapViews.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        # self.BVP = self.ui.scrollAreaMapViews.layout()
        # D.dockNavigation.connectTimeSeries(self.TS)
        self.ui.dockTimeSeries.setTimeSeries(self.mTimeSeries)
        self.ui.dockSensors.setTimeSeries(self.mTimeSeries)


        self.spectralTemporalVis = SpectralTemporalVisualization(self.mTimeSeries, self.ui.dockProfiles)
        self.spectralTemporalVis.pixelLoader.sigLoadingFinished.connect(
            lambda dt: self.ui.dockSystemInfo.addTimeDelta('Pixel Profile', dt))
        assert isinstance(self, TimeSeriesViewer)

        from eotimeseriesviewer.mapvisualization import SpatialTemporalVisualization
        self.spatialTemporalVis = SpatialTemporalVisualization(self)
        # self.spatialTemporalVis.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        # self.spatialTemporalVis.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        # self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)

        self.spatialTemporalVis.sigShowProfiles.connect(self.onShowProfile)
        self.ui.dockMapViews.sigCrsChanged.connect(self.spatialTemporalVis.setCrs)
        self.ui.dockMapViews.sigMapSizeChanged.connect(self.spatialTemporalVis.setMapSize)
        self.ui.dockMapViews.sigMapCanvasColorChanged.connect(self.spatialTemporalVis.setMapBackgroundColor)
        self.spatialTemporalVis.sigCRSChanged.connect(self.ui.dockMapViews.setCrs)
        self.spatialTemporalVis.sigMapSizeChanged.connect(self.ui.dockMapViews.setMapSize)
        self.spatialTemporalVis.sigVisibleDatesChanged.connect(self.timeSeries().setCurrentDates)
        self.spectralTemporalVis.sigMoveToTSD.connect(self.showTimeSeriesDatum)

        self.spectralTemporalVis.ui.actionLoadProfileRequest.triggered.connect(self.ui.actionIdentifyTemporalProfile.trigger)


        tstv = self.ui.dockTimeSeries.timeSeriesTreeView
        assert isinstance(tstv, TimeSeriesTreeView)
        tstv.sigMoveToDateRequest.connect(self.showTimeSeriesDatum)

        # init map tools
        self.mMapTools = []
        self.mCurrentMapLocation = None
        self.mCurrentMapSpectraLoading = 'TOP'

        def initMapToolAction(action, key):
            assert isinstance(action, QAction)
            assert isinstance(key, str)
            assert key in MapTools.mapToolKeys()
            action.triggered.connect(lambda: self.setMapTool(key))
            action.setProperty('eotsv/maptoolkey', key)
            self.ui.registerMapToolAction(action)



        initMapToolAction(self.ui.actionPan, MapTools.Pan)
        initMapToolAction(self.ui.actionZoomIn, MapTools.ZoomIn)
        initMapToolAction(self.ui.actionZoomOut, MapTools.ZoomOut)
        initMapToolAction(self.ui.actionZoomPixelScale, MapTools.ZoomPixelScale)
        initMapToolAction(self.ui.actionZoomFullExtent, MapTools.ZoomFull)
        initMapToolAction(self.ui.actionIdentify, MapTools.CursorLocation)

        initMapToolAction(self.ui.actionSelectFeatures, MapTools.SelectFeature)
        assert isinstance(self.ui.actionSelectFeatures, QAction)

        self.ui.optionSelectFeaturesRectangle.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesPolygon.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesFreehand.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesRadius.triggered.connect(self.onSelectFeatureOptionTriggered)

        m = QMenu()
        m.addAction(self.ui.optionSelectFeaturesRectangle)
        m.addAction(self.ui.optionSelectFeaturesPolygon)
        m.addAction(self.ui.optionSelectFeaturesFreehand)
        m.addAction(self.ui.optionSelectFeaturesRadius)

        self.ui.actionSelectFeatures.setMenu(m)

        # create edit toolbar
        tb = self.ui.toolBarEditing
        assert isinstance(tb, QToolBar)
        tb.addAction(self.ui.dockLabeling.actionToggleEditing())
        tb.addAction(self.ui.dockLabeling.actionSaveEdits())
        tb.addAction(self.ui.dockLabeling.actionAddFeature())
        self.ui.dockLabeling.sigMapExtentRequested.connect(self.setSpatialExtent)
        self.ui.dockLabeling.sigMapCenterRequested.connect(self.setSpatialCenter)

        initMapToolAction(self.ui.dockLabeling.actionAddFeature(), MapTools.AddFeature)


        self.ui.dockLabeling.sigVectorLayerChanged.connect(lambda : self.spatialTemporalVis.setCurrentLayer(self.ui.dockLabeling.currentVectorSource()))
        #initMapToolAction(self.ui.dockLabeling., MapTools.AddFeature)

        # set default map tool
        self.ui.actionPan.toggle()

        self.ui.dockCursorLocation.sigLocationRequest.connect(self.ui.actionIdentifyCursorLocationValues.trigger)

        self.ui.dockCursorLocation.mLocationInfoModel.setNodeExpansion(CursorLocationInfoModel.ALWAYS_EXPAND)

        # D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
        self.ui.actionAddMapView.triggered.connect(self.spatialTemporalVis.MVC.createMapView)

        self.ui.actionAddTSD.triggered.connect(lambda : self.addTimeSeriesImages(None))
        self.ui.actionAddVectorData.triggered.connect(lambda : self.addVectorData())
        self.ui.actionRemoveTSD.triggered.connect(lambda: self.mTimeSeries.removeTSDs(self.ui.dockTimeSeries.selectedTimeSeriesDates()))
        self.ui.actionRefresh.triggered.connect(self.spatialTemporalVis.refresh)
        self.ui.actionLoadTS.triggered.connect(self.loadTimeSeriesDefinition)
        self.ui.actionClearTS.triggered.connect(self.clearTimeSeries)
        self.ui.actionSaveTS.triggered.connect(self.saveTimeSeriesDefinition)
        self.ui.actionAddTSExample.triggered.connect(self.loadExampleTimeSeries)
        self.ui.actionLoadTimeSeriesStack.triggered.connect(self.loadTimeSeriesStack)
        self.ui.actionShowCrosshair.toggled.connect(self.spatialTemporalVis.setCrosshairVisibility)

        # connect buttons with actions
        from eotimeseriesviewer.widgets import AboutDialogUI
        self.ui.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())

        self.ui.actionSettings.triggered.connect(self.onShowSettingsDialog)
        import webbrowser
        from eotimeseriesviewer import DOCUMENTATION, SpectralLibrary, SpectralLibraryPanel, SpectralLibraryWidget
        self.ui.actionShowOnlineHelp.triggered.connect(lambda: webbrowser.open(DOCUMENTATION))

        SLW = self.ui.dockSpectralLibrary.spectralLibraryWidget()
        assert isinstance(SLW, SpectralLibraryWidget)
        SLW.sigLoadFromMapRequest.connect(self.ui.actionIdentifySpectralProfile.trigger)
        SLW.setMapInteraction(True)
        SLW.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
        SLW.sigMapExtentRequested.connect(self.setSpatialExtent)
        SLW.sigMapCenterRequested.connect(self.setSpatialCenter)

        # add the cadDock

        # add time-specific fields
        sl = self.spectralLibrary()

        assert isinstance(sl, SpectralLibrary)
        sl.setName('EOTS Spectral Library')
        sl.startEditing()
        for field in EXTRA_SPECLIB_FIELDS:
            sl.addAttribute(field)
        assert sl.commitChanges()

        self.mMapLayerStore.addMapLayer(sl)

        temporalProfileLayer = self.spectralTemporalVis.temporalProfileLayer()
        assert isinstance(temporalProfileLayer, QgsVectorLayer)
        temporalProfileLayer.setName('EOTS Temporal Profiles')
        self.mMapLayerStore.addMapLayer(temporalProfileLayer)

        self.spatialTemporalVis.sigMapViewAdded.connect(self.onMapViewAdded)
        #QgsProject.instance().addMapLayer(temporalProfileLayer)

        eotimeseriesviewer.labeling.MAP_LAYER_STORES.append(self.mMapLayerStore)
        eotimeseriesviewer.labeling.registerLabelShortcutEditorWidget()
        self.applySettings()

        TimeSeriesViewer._instance = self

        self.initQGISConnection()




    def onMapViewAdded(self, mapView):
        mapView.addLayer(self.spectralTemporalVis.temporalProfileLayer())
        mapView.addLayer(self.spectralLibrary())

    def temporalProfileLayer(self)->QgsVectorLayer:
        """
        Returns the TemporalProfileLayer
        :return:
        """
        from eotimeseriesviewer.profilevisualization import SpectralTemporalVisualization
        return self.spectralTemporalVis.temporalProfileLayer()


    def spectralLibrary(self)->SpectralLibrary:
        """
        Returns the SpectraLibrary of the SpectralLibrary dock
        :return: SpectraLibrary
        """
        from .externals.qps.speclib.spectrallibraries import SpectralLibraryPanel
        if isinstance(self.ui.dockSpectralLibrary, SpectralLibraryPanel):
            return self.ui.dockSpectralLibrary.SLW.speclib()
        else:
            return None



    def actionZoomActualSize(self):
        return self.ui.actionZoomPixelScale

    def actionZoomFullExtent(self):
        return self.ui.actionZoomFullExtent

    def actionZoomIn(self):
        return self.ui.actionZoomIn

    def actionZoomOut(self):
        return self.ui.actionZoomOut


    def showTimeSeriesDatum(self, tsd:TimeSeriesDatum):
        """
        Moves the viewport of the scroll window to a specific TimeSeriesDatum
        :param tsd:  TimeSeriesDatum
        """
        assert isinstance(tsd, TimeSeriesDatum)
        self.spatialTemporalVis.navigateToTSD(tsd)
        self.ui.dockTimeSeries.showTSD(tsd)
        # todo: move TableViews to as well


    def mapCanvases(self)->list:
        """
        Returns all MapCanvases of the spatial visualization
        :return: [list-of-MapCanvases]
        """
        return self.spatialTemporalVis.mapCanvases()

    def mapLayerStore(self)->QgsMapLayerStore:
        """
        Returns the QgsMapLayerStore which is used to register QgsMapLayers
        :return: QgsMapLayerStore
        """
        return self.mMapLayerStore

    def onMoveToFeature(self, layer:QgsMapLayer, feature:QgsFeature):
        """
        Move the spatial center of map visualization to `feature`.
        :param layer: QgsMapLayer
        :param feature: QgsFeature
        """
        g = feature.geometry()
        if isinstance(g, QgsGeometry):
            c = g.centroid()
            x, y = c.asPoint()
            crs = layer.crs()
            center = SpatialPoint(crs, x, y)
            self.spatialTemporalVis.setSpatialCenter(center)
            self.ui.actionRefresh.trigger()

    def onSelectFeatureOptionTriggered(self):

        a = self.sender()
        m = self.ui.actionSelectFeatures.menu()
        if isinstance(a, QAction) and isinstance(m, QMenu) and a in m.actions():
            for ca in m.actions():
                assert isinstance(ca, QAction)
                if ca == a:
                    self.ui.actionSelectFeatures.setIcon(a.icon())
                    self.ui.actionSelectFeatures.setToolTip(a.toolTip())
                ca.setChecked(ca == a)
        self.setMapTool(MapTools.SelectFeature)

    def onCrosshairPositionChanged(self, spatialPoint:SpatialPoint):
        """
        Synchronizes all crosshair positions. Takes care of CRS differences.
        :param spatialPoint: SpatialPoint of the new Crosshair position
        """
        sender = self.sender()
        from .mapcanvas import MapCanvas
        for mapCanvas in self.mapCanvases():
            if isinstance(mapCanvas, MapCanvas) and mapCanvas != sender:
                mapCanvas.setCrosshairPosition(spatialPoint, emitSignal=False)


    def initQGISConnection(self):
        """
        Initializes interactions between TimeSeriesViewer and the QGIS instances
        :return:
        """

        iface = qgis.utils.iface
        assert isinstance(iface, QgisInterface)

        self.ui.actionImportExtent.triggered.connect(lambda: self.spatialTemporalVis.setSpatialExtent(SpatialExtent.fromMapCanvas(iface.mapCanvas())))
        self.ui.actionExportExtent.triggered.connect(lambda: iface.mapCanvas().setExtent(self.spatialTemporalVis.spatialExtent().toCrs(iface.mapCanvas().mapSettings().destinationCrs())))
        self.ui.actionExportCenter.triggered.connect(lambda: iface.mapCanvas().setCenter(self.spatialTemporalVis.spatialExtent().spatialCenter()))
        self.ui.actionImportCenter.triggered.connect(lambda: self.spatialTemporalVis.setSpatialCenter(SpatialPoint.fromMapCanvasCenter(iface.mapCanvas())))


        self.spatialTemporalVis.sigSpatialExtentChanged.connect(lambda: self.spatialTemporalVis.syncQGISCanvasCenter(False))
        iface.mapCanvas().extentsChanged.connect(lambda: self.spatialTemporalVis.syncQGISCanvasCenter(True))



    def onShowSettingsDialog(self):
        from eotimeseriesviewer.settings import SettingsDialog
        d = SettingsDialog(self.ui)
        r = d.exec_()

        if r == QDialog.Accepted:
            self.applySettings()
            s = ""
        else:
            pass
            s  =""

    def applySettings(self):
        """
        Reads the QSettings object and applies its value to related widget components
        """


        from eotimeseriesviewer.settings import value, Keys, defaultValues, setValue

        # the default values
        defaults = defaultValues()
        for key in list(Keys):
            if value(key) == None:
                setValue(key, defaults[key])

        self.mTimeSeries.setDateTimePrecision(value(Keys.DateTimePrecision))
        self.spatialTemporalVis.mMapRefreshTimer.start(value(Keys.MapUpdateInterval))
        self.spatialTemporalVis.setMapBackgroundColor(value(Keys.MapBackgroundColor))
        self.spatialTemporalVis.setMapSize(value(Keys.MapSize))

    def setMapTool(self, mapToolKey, *args, **kwds):
        """
        Sets the active QgsMapTool for all canvases know to the EOTSV.
        :param mapToolKey: str, see MapTools documentation
        :param args:
        :param kwds:
        :return:
        """
        # disconnect previous map-tools?
        del self.mMapTools[:]

        kwds = {}

        if mapToolKey == MapTools.SelectFeature:
            if self.ui.optionSelectFeaturesRectangle.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectSimple
            elif self.ui.optionSelectFeaturesPolygon.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectPolygon
            elif self.ui.optionSelectFeaturesFreehand.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectFreehand
            elif self.ui.optionSelectFeaturesRadius.isChecked():
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectRadius
            else:
                mode = QgsMapToolSelectionHandler.SelectionMode.SelectSimple

        for canvas in self.mapCanvases():
            from .mapcanvas import MapCanvas, MapCanvasMapTools

            if isinstance(canvas, MapCanvas):

                mapTools = canvas.mapTools()
                mapTools.activate(mapToolKey)

                mt = canvas.mapTool()
                if isinstance(mt, QgsMapToolSelect):
                    mt.setSelectionMode(mode)


    def setSpatialExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the map canvas extent
        :param spatialExtent: SpatialExtent
        """
        self.spatialTemporalVis.setSpatialExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint:SpatialPoint):
        """
        Sets the center of map canvases
        :param spatialPoint: SpatialPoint
        """
        self.spatialTemporalVis.setSpatialCenter(spatialPoint)

    def spatialCenter(self)->SpatialPoint:
        return self.spatialTemporalVis.spatialCenter()

    def setCurrentLocation(self, spatialPoint:SpatialPoint, mapCanvas:QgsMapCanvas=None):
        """
        Sets the current "last selected" location, for which different properties might get derived,
        like cursor location values and SpectraProfiles.
        :param spatialPoint: SpatialPoint
        :param mapCanvas: QgsMapCanvas (optional), the canvas on which the location got selected
        """
        assert isinstance(spatialPoint, SpatialPoint)

        bCLV = self.ui.optionIdentifyCursorLocation.isChecked()
        bSP = self.ui.optionIdentifySpectralProfile.isChecked()
        bTP = self.ui.optionIdentifyTemporalProfile.isChecked()
        bCenter = self.ui.optionMoveCenter.isChecked()

        self.mCurrentMapLocation = spatialPoint

        if isinstance(mapCanvas, QgsMapCanvas):
            self.sigCurrentLocationChanged[SpatialPoint, QgsMapCanvas].emit(self.mCurrentMapLocation, mapCanvas)

            if bCLV:
                self.loadCursorLocationValueInfo(spatialPoint, mapCanvas)

            if bCenter:
                mapCanvas.setCenter(spatialPoint.toCrs(mapCanvas.mapSettings().destinationCrs()))

            if bSP:
                self.loadCurrentSpectralProfile(spatialPoint, mapCanvas)

        if bTP:
            self.loadCurrentTemporalProfile(spatialPoint)

        self.sigCurrentLocationChanged[SpatialPoint].emit(self.mCurrentMapLocation)

    @pyqtSlot(SpatialPoint, QgsMapCanvas)
    def loadCursorLocationValueInfo(self, spatialPoint:SpatialPoint, mapCanvas:QgsMapCanvas):
        self.ui.dockCursorLocation.loadCursorLocation(spatialPoint, mapCanvas)


    @pyqtSlot(SpatialPoint, QgsMapCanvas)
    def loadCurrentSpectralProfile(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas):
        """
        Loads SpectralProfiles from a location defined by `spatialPoint`
        :param spatialPoint: SpatialPoint
        :param mapCanvas: QgsMapCanvas
        """
        assert self.mCurrentMapSpectraLoading in ['TOP', 'ALL']
        assert isinstance(spatialPoint, SpatialPoint)
        from .mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        tsd = mapCanvas.tsd()

        sensorLayers   = [l for l in mapCanvas.layers() if isinstance(l, SensorProxyLayer)]
        currentSpectra = []


        sl = self.spectralLibrary()
        for lyr in sensorLayers:
            assert isinstance(lyr, SensorProxyLayer)
            p = SpectralProfile.fromRasterLayer(lyr, spatialPoint)
            if isinstance(p, SpectralProfile):
                p2 = p.copyFieldSubset(sl.fields())
                p2.setName('{} {}'.format(p.name(), tsd.date()))
                p2.setAttribute('date', '{}'.format(tsd.date()))
                p2.setAttribute('doy', int(tsd.doy()))
                p2.setAttribute('sensor', tsd.sensor().name())
                currentSpectra.append(p2)
                if self.mCurrentMapSpectraLoading == 'TOP':
                    break

        self.ui.dockSpectralLibrary.SLW.setCurrentSpectra(currentSpectra)

    @pyqtSlot(SpatialPoint)
    def loadCurrentTemporalProfile(self, spatialPoint: SpatialPoint):
        self.spectralTemporalVis.loadCoordinate(spatialPoint)

    def onShowProfile(self, spatialPoint, mapCanvas, mapToolKey):
        # self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)
        assert isinstance(spatialPoint, SpatialPoint)
        assert isinstance(mapCanvas, QgsMapCanvas)
        from eotimeseriesviewer.mapcanvas import MapTools
        assert mapToolKey in MapTools.mapToolKeys()

        if mapToolKey == MapTools.TemporalProfile:
            self.spectralTemporalVis.loadCoordinate(spatialPoint)
        elif mapToolKey == MapTools.SpectralProfile:

            tsd = self.spatialTemporalVis.DVC.tsdFromMapCanvas(mapCanvas)

            if not hasattr(self, 'cntSpectralProfile'):
                self.cntSpectralProfile = 0

            profiles = SpectralProfile.fromMapCanvas(mapCanvas, spatialPoint)

            # add metadata
            if isinstance(tsd, TimeSeriesDatum):
                profiles2 = []
                sl = self.spectralLibrary()
                if isinstance(sl, SpectralLibrary):
                    for p in profiles:
                        self.cntSpectralProfile += 1
                        assert isinstance(p, SpectralProfile)
                        p2 = p.copyFieldSubset(fields=sl.fields())
                        p2.setName('Profile {} {}'.format(self.cntSpectralProfile, tsd.mDate))
                        p2.setAttribute('date', '{}'.format(tsd.mDate))
                        p2.setAttribute('doy', int(tsd.mDOY))
                        p2.setAttribute('sensor', tsd.mSensor.name())
                        profiles2.append(p2)
                    self.ui.dockSpectralLibrary.SLW.setCurrentSpectra(profiles2)

        elif mapToolKey == MapTools.CursorLocation:

            self.ui.dockCursorLocation.loadCursorLocation(spatialPoint, mapCanvas)

        else:
            s = ""
        pass

    def messageBar(self)->QgsMessageBar:
        """
        Returns the QgsMessageBar that is used to show messages in the TimeSeriesViewer UI.
        :return: QgsMessageBar
        """
        return self.ui.messageBar

    def loadImageFiles(self, files:list):
        """
        Loads image files to the time series.
        :param files: [list-of-file-paths]
        """
        assert isinstance(files, list)

        progressDialog = QProgressDialog(parent=self.ui)
        progressDialog.setWindowTitle('Load data')
        progressDialog.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        progressDialog.show()
        QApplication.processEvents()
        self.mTimeSeries.addSources(files, progressDialog=progressDialog)

        progressDialog.hide()
        progressDialog.setParent(None)


    def loadTimeSeriesDefinition(self, path:str=None, n_max:int=None):
        """
        Loads a time series definition file
        :param path:
        :param n_max:
        :return:
        """
        s = settings()
        if not (isinstance(path, str) and os.path.isfile(path)):

            defFile = s.value('file_ts_definition')
            defDir = None
            if defFile is not None:
                defDir = os.path.dirname(defFile)

            filters = "CSV (*.csv *.txt);;" + \
                      "All files (*.*)"

            path, filter = QFileDialog.getOpenFileName(caption='Load Time Series definition', directory=defDir, filter=filters)

        if path is not None and os.path.exists(path):
            s.setValue('file_ts_definition', path)
            
            progressDialog = QProgressDialog(parent=self.ui)
            progressDialog.setWindowTitle('Load data')
            progressDialog.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
            progressDialog.show()

            self.clearTimeSeries()
            self.mTimeSeries.loadFromFile(path, n_max=n_max, progressDialog=progressDialog)
            progressDialog.hide()
            progressDialog.setParent(None)

    def createMapView(self):
        """
        Create a new MapView
        """
        self.spatialTemporalVis.createMapView()

    def mapViews(self)->list:
        """
        Returns all MapViews
        :return: [list-of-MapViews]
        """
        return self.spatialTemporalVis.MVC[:]

    def zoomTo(self, key):
        if key == 'zoomMaxExtent':
            ext = self.mTimeSeries.maxSpatialExtent(self.ui.dockRendering.crs())
        elif key == 'zoomPixelScale':

            extent = self.spatialTemporalVis.spatialExtent()
            #calculate in web-mercator for metric distances
            crs = self.spatialTemporalVis.crs()
            crsWMC = QgsCoordinateReferenceSystem('EPSG:3857')

            extentWMC = extent.toCrs(crsWMC)
            pxSize = max(self.mTimeSeries.pixelSizes(), key= lambda s :s.width())
            canvasSize = self.spatialTemporalVis.mapSize()
            f = 0.05
            width = f * canvasSize.width() * pxSize.width()  # width in map units
            height = f * canvasSize.height() * pxSize.height()
            ext = SpatialExtent(crsWMC, 0, 0, width, height)
            ext.setCenter(extentWMC.center())
            #return to original CRS
            ext = ext.toCrs(crs)
        else:
            raise NotImplementedError(key)
        self.spatialTemporalVis.setSpatialExtent(ext)


    def icon(self)->QIcon:
        """
        Returns the EO Time Series Viewer icon
        :return: QIcon
        """
        import eotimeseriesviewer
        return eotimeseriesviewer.icon()

    def logMessage(self, message, tag, level):
        m = message.split('\n')
        if '' in message.split('\n'):
            m = m[0:m.index('')]
        m = '\n'.join(m)
        if DEBUG: print(message)
        if not re.search('timeseriesviewer', m):
            return

        if level in [Qgis.Critical, Qgis.Warning]:

            self.ui.messageBar.pushMessage(tag, message, level=level)
            print(r'{}({}): {}'.format(tag, level, message))

    def onTimeSeriesChanged(self, *args):

        if not self.mSpatialMapExtentInitialized:
            if len(self.mTimeSeries) > 0:
                if len(self.spatialTemporalVis.MVC) == 0:
                    # add an empty MapView by default
                    self.spatialTemporalVis.createMapView()
                    #self.spatialTemporalVis.createMapView()

                extent = self.mTimeSeries.maxSpatialExtent()

                self.spatialTemporalVis.setCrs(extent.crs())
                self.spatialTemporalVis.setSpatialExtent(extent)
                self.mSpatialMapExtentInitialized = True



        if len(self.mTimeSeries) == 0:
            self.mSpatialMapExtentInitialized = False


    def saveTimeSeriesDefinition(self):
        s = settings()
        defFile = s.value('FILE_TS_DEFINITION')
        if defFile is not None:
            defFile = os.path.dirname(defFile)

        filters = "CSV (*.csv *.txt);;" + \
                  "All files (*.*)"
        path, filter = QFileDialog.getSaveFileName(caption='Save Time Series definition', filter=filters, directory=defFile)
        path = self.mTimeSeries.saveToFile(path)
        if path is not None:
            s.setValue('FILE_TS_DEFINITION', path)

    def loadTimeSeriesStack(self):

        from eotimeseriesviewer.stackedbandinput import StackedBandInputDialog

        d = StackedBandInputDialog(parent=self.ui)
        if d.exec_() == QDialog.Accepted:
            writtenFiles = d.saveImages()
            self.addTimeSeriesImages(writtenFiles)



    def loadExampleTimeSeries(self, n:int=None):
        """
        Loads an example time series
        :param n: int, max. number of images to load. Useful for developer test-cases
        """
        import example.Images
        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif'))

        if isinstance(n, bool) or not isinstance(n, int):
            n = len(files)

        # ensure valid inputs for n
        n = min(n, len(files))
        n = max(1, n)

        self.addTimeSeriesImages(files[0:n])


    def qgs_handleMouseDown(self, pt, btn):
        pass


    def timeSeries(self)->TimeSeries:
        """
        Returns the TimeSeries instance.
        :return: TimeSeries
        """
        return self.mTimeSeries

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
        return QCoreApplication.translate('HUBTSV', message)



    def unload(self):
        """Removes the plugin menu item and icon """
        self.iface.removeToolBarIcon(self.action)

    def show(self):
        self.ui.show()

    def run(self):
        #QApplication.processEvents()
        self.ui.show()


    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def addVectorData(self, files=None):

        if files is None:
            s = settings()
            defDir = s.value('DIR_FILESEARCH')
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('DIR_FILESEARCH', dn)

        if files:
            vectorLayers = []
            from eotimeseriesviewer.mapvisualization import MapView
            for f in files:
                for mapView in self.mapViews():
                    assert isinstance(mapView, MapView)
                    l = QgsVectorLayer(f, os.path.basename(f))
                    mapView.addLayer(l)
                    vectorLayers.append(l)
            QgsProject.instance().addMapLayers(vectorLayers)


    def addTimeSeriesImages(self, files: list):
        """
        Adds images to the time series
        :param files:
        """
        if files is None:
            s = settings()
            defDir = s.value('dir_datasources')

            filters = QgsProviderRegistry.instance().fileRasterFilters()
            files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('dir_datasources', dn)


        if files:
            self.mTimeSeries.addSources(files)

    def clearTimeSeries(self):

        self.mTimeSeries.beginResetModel()
        self.mTimeSeries.clear()
        self.mTimeSeries.endResetModel()


def disconnect_signal(signal):
    while True:
        try:
            signal.disconnect()
        except TypeError:
            break
