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
from eotimeseriesviewer.mapvisualization import MapView, MapWidget
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


class AboutDialogUI(QDialog, loadUI('aboutdialog.ui')):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialogUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.init()

    def init(self):
        self.mTitle = self.windowTitle()
        self.listWidget.currentItemChanged.connect(lambda: self.setAboutTitle())
        self.setAboutTitle()

        # page About
        from eotimeseriesviewer import PATH_LICENSE, __version__, PATH_CHANGELOG, PATH_ABOUT
        self.labelVersion.setText('{}'.format(__version__))

        def readTextFile(path):
            if os.path.isfile(path):
                f = open(path, encoding='utf-8')
                txt = f.read()
                f.close()
            else:
                txt = 'unable to read {}'.format(path)
            return txt

        # page Changed
        self.tbAbout.setHtml(readTextFile(PATH_ABOUT))
        self.tbChanges.setHtml(readTextFile(PATH_CHANGELOG + '.html'))
        self.tbLicense.setHtml(readTextFile(os.path.splitext(PATH_LICENSE)[0] + '.html'))


    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)





class TimeSeriesViewerUI(QMainWindow,
                         loadUI('timeseriesviewer.ui')):

    sigAboutToBeClosed = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(TimeSeriesViewerUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.setCentralWidget(self.mMapWidget)

        self.addActions(self.findChildren(QAction))
        from eotimeseriesviewer import TITLE, icon, __version__

        self.mInitResized = False
        self.mMapToolActions = []
        self.setWindowTitle('{} ({})'.format(TITLE, __version__))
        self.setWindowIcon(icon())
        if sys.platform == 'darwin':
            self.menuBar().setNativeMenuBar(False)

        # set button default actions -> this will show the action icons as well
        # I don't know why this is not possible in the QDesigner when QToolButtons are
        # placed outside a toolbar

        area = None

        def addDockWidget(dock:QDockWidget):
            """
            shortcut to add a created dock and return it
            :param dock:
            :return:
            """
            dock.setParent(self)
            self.addDockWidget(area, dock)
            return dock

        area = Qt.LeftDockWidgetArea

        # self.dockRendering = addDockWidget(docks.RenderingDockUI(self))



        from eotimeseriesviewer.mapvisualization import MapViewDock
        self.dockMapViews = addDockWidget(MapViewDock(self))

        # self.tabifyDockWidget(self.dockMapViews, self.dockRendering)
        # self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)

        area = Qt.BottomDockWidgetArea
        # from timeseriesviewer.mapvisualization import MapViewDockUI
        # self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries = addDockWidget(TimeSeriesDock(self))
        self.dockTimeSeries.initActions(self)

        from eotimeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))
        from eotimeseriesviewer.labeling import LabelingDock
        self.dockLabeling = addDockWidget(LabelingDock(self))

        area = Qt.LeftDockWidgetArea
        self.dockAdvancedDigitizingDockWidget = addDockWidget(QgsAdvancedDigitizingDockWidget(self.dockLabeling.labelingWidget().canvas(), self))
        self.dockAdvancedDigitizingDockWidget.setVisible(False)


        area = Qt.BottomDockWidgetArea
        panel = SpectralLibraryPanel(self)

        self.dockSpectralLibrary = addDockWidget(panel)

        self.tabifyDockWidget(self.dockTimeSeries, self.dockSpectralLibrary)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockLabeling)

        area = Qt.RightDockWidgetArea


        self.dockTaskManager = QgsDockWidget('Task Manager')
        self.dockTaskManager.setWidget(QgsTaskManagerWidget(QgsApplication.taskManager()))
        self.dockTaskManager.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.dockTaskManager = addDockWidget(self.dockTaskManager)



        from eotimeseriesviewer.systeminfo import SystemInfoDock
        from eotimeseriesviewer.sensorvisualization import SensorDockUI

        self.dockSystemInfo = addDockWidget(SystemInfoDock(self))
        self.dockSystemInfo.setVisible(False)

        self.dockSensors = addDockWidget(SensorDockUI(self))
        self.dockCursorLocation = addDockWidget(CursorLocationInfoDock(self))

        self.tabifyDockWidget(self.dockTaskManager, self.dockCursorLocation)
        self.tabifyDockWidget(self.dockTaskManager, self.dockSystemInfo)
        self.tabifyDockWidget(self.dockTaskManager, self.dockSensors)




        for dock in self.findChildren(QDockWidget):

            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())

        self.dockTimeSeries.raise_()


    def registerMapToolAction(self, a:QAction)->QAction:
        """
        Registers this action as map tools action. If triggered, all other mapt tool actions with be set unchecked
        :param a: QAction
        :return: QAction
        """

        assert isinstance(a, QAction)
        if a not in self.mMapToolActions:
            self.mMapToolActions.append(a)
        a.setCheckable(True)
        a.toggled.connect(lambda b, action=a: self.onMapToolActionToggled(b, action))
        return a

    def onMapToolActionToggled(self, b:bool, action:QAction):
        """
        Reacts on togglinga map tool
        :param b:
        :param action:
        """
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

    def closeEvent(self, a0:QCloseEvent):
        self.sigAboutToBeClosed.emit()

    """
    def resizeEvent(self, event:QResizeEvent):

        super(TimeSeriesViewerUI, self).resizeEvent(event)

        if False and not self.mInitResized:
            pass
        w = 0.5
        minH = int(self.size().height() * w)
        print(minH)
        #self.mCentralWidget.setMinimumHeight(minH)
        for d in self.findChildren(QDockWidget):
            w = d.widget()
            assert isinstance(d, QDockWidget)
            print((d.objectName(), d.minimumHeight(), d.sizePolicy().verticalPolicy()))
            d.setMinimumHeight(0)
            s = ""
        #self.mCentralWidget.setMinimumWidth(int(self.size().width() * w))
            #self.mInitResized = True
    """
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
    sigCloses = pyqtSignal()

    def __init__(self):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        QObject.__init__(self)
        QgisInterface.__init__(self)
        QApplication.processEvents()

        self.mMapLayerStore = QgsMapLayerStore()
        import eotimeseriesviewer.utils
        eotimeseriesviewer.utils.MAP_LAYER_STORES.insert(0, self.mapLayerStore())

        TimeSeriesViewer._instance = self
        self.ui = TimeSeriesViewerUI()

        mvd = self.ui.dockMapViews
        dts = self.ui.dockTimeSeries
        mw = self.ui.mMapWidget
        from eotimeseriesviewer.timeseries import TimeSeriesDock
        from eotimeseriesviewer.mapvisualization import MapViewDock, MapWidget
        assert isinstance(mvd, MapViewDock)
        assert isinstance(mw, MapWidget)
        assert isinstance(dts, TimeSeriesDock)

        def onClosed():
            TimeSeriesViewer._instance = None
        self.ui.sigAboutToBeClosed.connect(onClosed)


        # Save reference to the QGIS interface
        import qgis.utils
        assert isinstance(qgis.utils.iface, QgisInterface)

        # init empty time series
        self.mTimeSeries = TimeSeries()
        self.mTimeSeries.setDateTimePrecision(DateTimePrecision.Day)
        self.mSpatialMapExtentInitialized = False
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)

        dts.setTimeSeries(self.mTimeSeries)
        self.ui.dockSensors.setTimeSeries(self.mTimeSeries)
        mw.setTimeSeries(self.mTimeSeries)
        mvd.setTimeSeries(self.mTimeSeries)
        mvd.setMapWidget(mw)


        self.spectralTemporalVis = SpectralTemporalVisualization(self.mTimeSeries, self.ui.dockProfiles)
        self.spectralTemporalVis.pixelLoader.sigLoadingFinished.connect(
            lambda dt: self.ui.dockSystemInfo.addTimeDelta('Pixel Profile', dt))
        assert isinstance(self, TimeSeriesViewer)

        mw.sigSpatialExtentChanged.connect(self.timeSeries().setCurrentSpatialExtent)
        mw.sigVisibleDatesChanged.connect(self.timeSeries().setVisibleDates)
        mw.sigMapViewAdded.connect(self.onMapViewAdded)
        mw.sigCurrentLocationChanged.connect(self.setCurrentLocation)

        tb = self.ui.toolBarTimeControl
        assert isinstance(tb, QToolBar)
        tb.addAction(mw.actionFirstDate)
        tb.addAction(mw.actionBackwardFast)
        tb.addAction(mw.actionBackward)
        tb.addAction(mw.actionForward)
        tb.addAction(mw.actionForwardFast)
        tb.addAction(mw.actionLastDate)

        tstv = self.ui.dockTimeSeries.timeSeriesTreeView
        assert isinstance(tstv, TimeSeriesTreeView)
        tstv.sigMoveToDateRequest.connect(self.setCurrentDate)

        self.mCurrentMapLocation = None
        self.mCurrentMapSpectraLoading = 'TOP'

        self.ui.actionLockMapPanelSize.toggled.connect(self.lockCentralWidgetSize)

        def initMapToolAction(action, key):
            assert isinstance(action, QAction)
            assert isinstance(key, MapTools)

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
        tb = self.ui.toolBarVectorFeatures
        assert isinstance(tb, QToolBar)
        tb.addAction(self.ui.dockLabeling.labelingWidget().actionToggleEditing())
        tb.addAction(self.ui.dockLabeling.labelingWidget().actionSaveEdits())
        tb.addAction(self.ui.dockLabeling.labelingWidget().actionAddFeature())
        labelingWidget = self.ui.dockLabeling.labelingWidget()
        from .labeling import LabelingWidget
        assert isinstance(labelingWidget, LabelingWidget)
        labelingWidget.sigMapExtentRequested.connect(self.setSpatialExtent)
        labelingWidget.sigMapCenterRequested.connect(self.setSpatialCenter)
        labelingWidget.sigVectorLayerChanged.connect(
            lambda: self.mapWidget().setCurrentLayer(
                self.ui.dockLabeling.labelingWidget().currentVectorSource()))

        initMapToolAction(self.ui.dockLabeling.labelingWidget().actionAddFeature(), MapTools.AddFeature)




        # set default map tool
        self.ui.actionPan.toggle()

        self.ui.dockCursorLocation.sigLocationRequest.connect(self.ui.actionIdentifyCursorLocationValues.trigger)

        self.ui.dockCursorLocation.mLocationInfoModel.setNodeExpansion(CursorLocationInfoModel.ALWAYS_EXPAND)

        # D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
        self.ui.actionAddMapView.triggered.connect(mvd.createMapView)

        self.ui.actionAddTSD.triggered.connect(lambda: self.addTimeSeriesImages(None))
        self.ui.actionAddVectorData.triggered.connect(lambda: self.addVectorData())
        self.ui.actionRemoveTSD.triggered.connect(lambda: self.mTimeSeries.removeTSDs(dts.selectedTimeSeriesDates()))
        self.ui.actionRefresh.triggered.connect(mw.refresh)
        self.ui.actionLoadTS.triggered.connect(self.loadTimeSeriesDefinition)
        self.ui.actionClearTS.triggered.connect(self.clearTimeSeries)
        self.ui.actionSaveTS.triggered.connect(self.saveTimeSeriesDefinition)
        self.ui.actionAddTSExample.triggered.connect(lambda: self.loadExampleTimeSeries(loadAsync=False))
        self.ui.actionLoadTimeSeriesStack.triggered.connect(self.loadTimeSeriesStack)
        #self.ui.actionShowCrosshair.toggled.connect(mw.setCrosshairVisibility)
        self.ui.actionExportMapsToImages.triggered.connect(lambda: self.exportMapsToImages())

        self.spectralTemporalVis.ui.actionLoadProfileRequest.triggered.connect(self.activateIdentifyTemporalProfileMapTool)
        self.ui.dockSpectralLibrary.SLW.actionSelectProfilesFromMap.triggered.connect(self.activateIdentifySpectralProfileMapTool)

        # connect buttons with actions
        self.ui.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())

        self.ui.actionSettings.triggered.connect(self.onShowSettingsDialog)
        import webbrowser
        from eotimeseriesviewer import DOCUMENTATION, SpectralLibrary, SpectralLibraryPanel, SpectralLibraryWidget
        self.ui.actionShowOnlineHelp.triggered.connect(lambda: webbrowser.open(DOCUMENTATION))

        SLW = self.ui.dockSpectralLibrary.spectralLibraryWidget()
        assert isinstance(SLW, SpectralLibraryWidget)

        SLW.setMapInteraction(True)
        SLW.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
        SLW.sigMapExtentRequested.connect(self.setSpatialExtent)
        SLW.sigMapCenterRequested.connect(self.setSpatialCenter)

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



        eotimeseriesviewer.labeling.MAP_LAYER_STORES.append(self.mMapLayerStore)
        eotimeseriesviewer.labeling.registerLabelShortcutEditorWidget()
        self.applySettings()



        self.initQGISConnection()


        for toolBar in self.ui.findChildren(QToolBar):
            fixMenuButtons(toolBar)


        self.ui.dockTimeSeries.setFloating(True)
        self.ui.dockTimeSeries.setFloating(False)

    def lockCentralWidgetSize(self, b:bool):
        """
        Locks or release the current central widget size
        :param b:
        """
        w = self.ui.centralWidget()

        size = w.size()
        if b:
            w.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
            w.setMinimumSize(size)
        else:
            w.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))
            w.setMinimumSize(0, 0)

    def sensors(self)->list:
        """
        Returns the list of Sensors
        :return: [list-of-Sensors]
        """
        return self.mTimeSeries.sensors()


    def activateIdentifyTemporalProfileMapTool(self, *args):
        """
        Activates the collection of temporal profiles
        """
        self.ui.actionIdentify.trigger()
        self.ui.optionIdentifyTemporalProfile.setChecked(True)

    def activateIdentifySpectralProfileMapTool(self, *args):
        """
        Activates the collection of spectral profiles
        """
        self.ui.actionIdentify.trigger()
        self.ui.optionIdentifySpectralProfile.setChecked(True)

    def _createProgressDialog(self, title='Load Data')->QProgressDialog:
        """
        Creates a QProgressDialog to load image data
        :return: QProgressDialog
        """
        progressDialog = QProgressDialog(self.ui)
        progressDialog.setWindowTitle(title)
        progressDialog.setMinimumDuration(500)
        progressDialog.setValue(0)
        progressDialog.setWindowFlags(progressDialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        return progressDialog

    def exportMapsToImages(self, path=None, format='PNG'):
        """
        Exports the map canvases to local images.
        :param path: directory to save the images in
        :param format: rastr format, e.g. 'PNG' or 'JPG'
        """
        from .mapcanvas import MapCanvas
        from .mapvisualization import MapView
        from .settings import Keys, setValue, value
        import string


        if path is None:
            d = SaveAllMapsDialog()

            path = value(Keys.MapImageExportDirectory, default=None)
            if isinstance(path, str):
                d.setDirectory(path)

            if d.exec() != QDialog.Accepted:
                s = ""
                return

            format = d.fileType().lower()
            path = d.directory()



        else:
            format = format.lower()

        mapCanvases = self.mapCanvases()
        n = len(mapCanvases)
        progressDialog = self._createProgressDialog(title='Save Map Images...')
        progressDialog.setRange(0, n)

        valid_chars = "-_.() {}{}".format(string.ascii_letters, string.digits)

        for i, mapCanvas in enumerate(mapCanvases):
            if progressDialog.wasCanceled():
                return

            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.timedRefresh()
            tsd = mapCanvas.tsd()
            mv = mapCanvas.mapView()
            assert isinstance(mv, MapView)
            mapCanvas.waitWhileRendering()
            imgPath = '{}.{}.{}'.format(tsd.date(), mv.title(), format)

            imgPath = ''.join(c for c in imgPath if c in valid_chars)
            imgPath = imgPath.replace(' ', '_')
            imgPath = os.path.join(path, imgPath)

            mapCanvas.saveAsImage(imgPath, None, format)
            progressDialog.setValue(i + 1)
            progressDialog.setLabelText('{}/{} maps saved'.format(i+1, n))

            if progressDialog.wasCanceled():
                return

        setValue(Keys.MapImageExportDirectory, path)


    def onMapViewAdded(self, mapView:MapView):
        """

        :param mapView:
        :return:
        """
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


    def setCurrentDate(self, tsd:TimeSeriesDate):
        """
        Moves the viewport of the scroll window to a specific TimeSeriesDate
        :param tsd:  TimeSeriesDate
        """
        self.ui.mMapWidget.setCurrentDate(tsd)


    def mapCanvases(self)->list:
        """
        Returns all MapCanvases of the spatial visualization
        :return: [list-of-MapCanvases]
        """
        return self.ui.mMapWidget.mapCanvases()

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
            self.ui.mMapWidget.setSpatialCenter(center)
            self.ui.actionRefresh.trigger()

    def onSelectFeatureOptionTriggered(self):

        a = self.sender()
        m = self.ui.actionSelectFeatures.menu()

        if isinstance(a, QAction) and isinstance(m, QMenu) and a in m.actions():
            for option in m.actions():
                assert isinstance(option, QAction)
                if option == a:
                    self.ui.actionSelectFeatures.setIcon(a.icon())
                    self.ui.actionSelectFeatures.setToolTip(a.toolTip())
                option.setChecked(option == a)
        self.onSelectFeatureTriggered()

    def onSelectFeatureTriggered(self):

        self.setMapTool(MapTools.SelectFeature)


    def initQGISConnection(self):
        """
        Initializes interactions between TimeSeriesViewer and the QGIS instances
        :return:
        """

        iface = qgis.utils.iface
        assert isinstance(iface, QgisInterface)

        self.ui.actionImportExtent.triggered.connect(lambda: self.setSpatialExtent(SpatialExtent.fromMapCanvas(iface.mapCanvas())))
        self.ui.actionExportExtent.triggered.connect(lambda: iface.mapCanvas().setExtent(self.spatialExtent().toCrs(iface.mapCanvas().mapSettings().destinationCrs())))
        self.ui.actionExportCenter.triggered.connect(lambda: iface.mapCanvas().setCenter(self.spatialCenter().toCrs(iface.mapCanvas().mapSettings().destinationCrs())))
        self.ui.actionImportCenter.triggered.connect(lambda: self.setSpatialCenter(SpatialPoint.fromMapCanvasCenter(iface.mapCanvas())))

        def onSyncRequest(qgisChanged:bool):
            if self.ui.optionSyncMapCenter.isChecked():
                self.ui.mMapWidget.syncQGISCanvasCenter(qgisChanged)

        self.ui.mMapWidget.sigSpatialExtentChanged.connect(lambda: onSyncRequest(False))
        iface.mapCanvas().extentsChanged.connect(lambda: onSyncRequest(True))


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
        Reads the QSettings object and applies its values to related widget components
        """


        from eotimeseriesviewer.settings import value, Keys, defaultValues, setValue

        # the default values
        defaults = defaultValues()
        for key in list(Keys):
            if value(key) == None and key in defaults.keys():
                setValue(key, defaults[key])

        v = value(Keys.DateTimePrecision)
        if isinstance(v, DateTimePrecision):
            self.mTimeSeries.setDateTimePrecision(v)

        v = value(Keys.MapUpdateInterval)
        if isinstance(v, int) and v > 0:
            self.ui.mMapWidget.mMapRefreshTimer.start(v)

        v = value(Keys.MapBackgroundColor)
        if isinstance(v, QColor):
            self.ui.dockMapViews.setMapBackgroundColor(v)

        v = value(Keys.MapTextFormat)
        if isinstance(v, QgsTextFormat):
            self.ui.dockMapViews.setMapTextFormat(v)

        v = value(Keys.MapSize)
        if isinstance(v, QSize):
            self.ui.mMapWidget.setMapSize(v)



    def setMapTool(self, mapToolKey, *args, **kwds):
        """
        Sets the active QgsMapTool for all canvases know to the EOTSV.
        :param mapToolKey: str, see MapTools documentation
        :param args:
        :param kwds:
        :return:
        """

        if mapToolKey == MapTools.SelectFeature:
            if self.ui.optionSelectFeaturesRectangle.isChecked():
                mapToolKey = MapTools.SelectFeature
            elif self.ui.optionSelectFeaturesPolygon.isChecked():
                mapToolKey = MapTools.SelectFeatureByPolygon
            elif self.ui.optionSelectFeaturesFreehand.isChecked():
                mapToolKey = MapTools.SelectFeatureByFreehand
            elif self.ui.optionSelectFeaturesRadius.isChecked():
                mapToolKey = MapTools.SelectFeatureByRadius

        self.ui.mMapWidget.setMapTool(mapToolKey, *args)
        kwds = {}

    def setMapsPerMapView(self, n:int):
        """
        Sets the number of map canvases that is shown per map view
        :param n: int
        """
        self.mapWidget().setMapsPerMapView(n)

    def setMapSize(self, size:QSize):
        """
        Sets the MapCanvas size.
        :param size: QSize
        """
        self.mapWidget().setMapSize(size)

    def setSpatialExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the map canvas extent
        :param spatialExtent: SpatialExtent
        """
        self.mapWidget().setSpatialExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint:SpatialPoint):
        """
        Sets the center of map canvases
        :param spatialPoint: SpatialPoint
        """
        self.mapWidget().setSpatialCenter(spatialPoint)

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the map extent
        :return: SpatialExtent
        """
        return self.mapWidget().spatialExtent()

    def spatialCenter(self)->SpatialPoint:
        """
        Returns the map center
        :return: SpatialPoint
        """
        return self.mapWidget().spatialCenter()

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

        assert isinstance(spatialPoint, SpatialPoint)
        assert isinstance(mapCanvas, QgsMapCanvas)
        from eotimeseriesviewer.mapcanvas import MapTools
        assert mapToolKey in MapTools.mapToolKeys()

        if mapToolKey == MapTools.TemporalProfile:
            self.spectralTemporalVis.loadCoordinate(spatialPoint)
        elif mapToolKey == MapTools.SpectralProfile:

            tsd = None
            from .mapcanvas import MapCanvas
            if isinstance(mapCanvas, MapCanvas):
                tsd = mapCanvas.tsd()

            if not hasattr(self, 'cntSpectralProfile'):
                self.cntSpectralProfile = 0

            profiles = SpectralProfile.fromMapCanvas(mapCanvas, spatialPoint)

            # add metadata
            if isinstance(tsd, TimeSeriesDate):
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
        return self.ui.mMapWidget.messageBar()


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
            self.clearTimeSeries()
            progressDialog = self._createProgressDialog()
            self.mTimeSeries.loadFromFile(path, n_max=n_max, progressDialog=progressDialog)


    def createMapView(self, name:str=None):
        """
        Creates a new MapView.
        :return: MapView
        """
        return self.ui.dockMapViews.createMapView(name=name)

    def mapViews(self)->list:
        """
        Returns all MapViews
        :return: [list-of-MapViews]
        """
        return self.ui.dockMapViews[:]


    def icon(self)->QIcon:
        """
        Returns the EO Time Series Viewer icon
        :return: QIcon
        """
        import eotimeseriesviewer
        return eotimeseriesviewer.icon()

    def temporalProfiles(self)->list:
        """
        Returns collected temporal profiles
        :return: [list-of-TemporalProfiles]
        """
        return self.spectralTemporalVis.temporalProfileLayer()[:]

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
                if len(self.ui.dockMapViews) == 0:
                    self.ui.dockMapViews.createMapView()

                extent = self.mTimeSeries.maxSpatialExtent()

                self.ui.mMapWidget.setCrs(extent.crs())
                self.ui.mMapWidget.setSpatialExtent(extent)
                self.mSpatialMapExtentInitialized = True



        if len(self.mTimeSeries) == 0:
            self.mSpatialMapExtentInitialized = False

    def mapWidget(self)->MapWidget:
        """
        Returns the MapWidget that contains all map canvases.
        :return: MapWidget
        """
        return self.ui.mMapWidget

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



    def loadExampleTimeSeries(self, n:int=None, loadAsync=True):
        """
        Loads an example time series
        :param n: int, max. number of images to load. Useful for developer test-cases
        """
        import example.Images
        exampleDataDir = os.path.dirname(example.__file__)
        rasterFiles = list(file_search(exampleDataDir, '*.tif', recursive=True))
        vectorFiles = list(file_search(exampleDataDir, re.compile(r'.*\.(gpkg|shp)$'), recursive=True))
        if isinstance(n, bool) or not isinstance(n, int):
            n = len(rasterFiles)

        # ensure valid inputs for n
        n = min(n, len(rasterFiles))
        n = max(1, n)

        self.addTimeSeriesImages(rasterFiles[0:n], loadAsync=loadAsync)

        if len(vectorFiles) > 0:

            # make polygons transparent

            self.addVectorData(vectorFiles)

            for lyr in QgsProject.instance().mapLayers().values():
                if isinstance(lyr, QgsVectorLayer) and lyr.source() in vectorFiles:
                    renderer = lyr.renderer()
                    if lyr.geometryType() == QgsWkbTypes.PolygonGeometry and isinstance(renderer, QgsSingleSymbolRenderer):
                        renderer = renderer.clone()
                        symbol = renderer.symbol()
                        if isinstance(symbol, QgsFillSymbol):
                            symbol.setOpacity(0.25)
                        lyr.setRenderer(renderer)
                    s = ""


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

    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def addVectorData(self, files=None)->list:
        """
        Adds vector data
        :param files: vector layer sources
        :return: [list-of-QgsVectorLayers]
        """
        vectorLayers = []
        if files is None:
            s = settings()
            defDir = s.value('DIR_FILESEARCH')
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('DIR_FILESEARCH', dn)

        if files:
            from eotimeseriesviewer.mapvisualization import MapView
            from .externals.qps.layerproperties import subLayers

            for f in files:
                vectorLayers.extend(subLayers(QgsVectorLayer(f)))

            if len(vectorLayers) > 0:
                QgsProject.instance().addMapLayers(vectorLayers)
                for mapView in self.mapViews():
                    assert isinstance(mapView, MapView)
                    for l in vectorLayers:
                        mapView.addLayer(l)

                    break # add to first mapview only

        return vectorLayers



    def addTimeSeriesImages(self, files: list, loadAsync=True):
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
            progressDialog = self._createProgressDialog()
            progressDialog.setRange(0, len(files))
            progressDialog.setLabelText('Start loading {} images....'.format(len(files)))

            if loadAsync:
                self.mTimeSeries.addSourcesAsync(files, progressDialog=progressDialog)
            else:
                self.mTimeSeries.addSources(files, progressDialog=progressDialog)



            #QCoreApplication.processEvents()
            #self.mTimeSeries.addSources(files)

    def clearTimeSeries(self):

        self.mTimeSeries.beginResetModel()
        self.mTimeSeries.clear()
        self.mTimeSeries.endResetModel()



class SaveAllMapsDialog(QDialog, loadUI('saveallmapsdialog.ui')):


    def __init__(self, parent=None):

        super(SaveAllMapsDialog, self).__init__(parent)
        self.setupUi(self)
        self.setWindowTitle('Save Maps')
        assert isinstance(self.fileWidget, QgsFileWidget)
        assert isinstance(self.cbFileType, QComboBox)

        self.fileWidget.setStorageMode(QgsFileWidget.GetDirectory)

        formats = [('Portable Network Graphics (*.png)', 'PNG'),
                   ('Joint Photographic Experts Group (*.jpg)', 'JPG'),
                   ('Windows Bitmap (*.bmp)', 'BMP'),
                   ('Portable Bitmap (*.pbm)', 'PBM'),
                   ('Portable Graymap (*.pgm)', 'PGM'),
                   ('Portable Pixmap (*.ppm)', 'PPM'),
                   ('X11 Bitmap (*.xbm)', 'XBM'),
                   ('X11 Pixmap (*.xpm)', 'XPM'),
                   ]



        for t in formats:
            self.cbFileType.addItem(t[0], userData=t[1])

        self.fileWidget.fileChanged.connect(self.validate)

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(lambda : self.setResult(QDialog.Accepted))
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(lambda : self.setResult(QDialog.Rejected))
        self.validate()

    def validate(self, *args):

        b = os.path.isdir(self.directory())
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(b)


    def setDirectory(self, path:str):
        assert os.path.isdir(path)
        self.fileWidget.setFilePath(path)


    def directory(self)->str:
        """
        Returns the selected directory
        :return: str
        """
        return self.fileWidget.filePath()

    def fileType(self)->str:
        """
        Returns the selected file type
        :return:
        """
        return self.cbFileType.currentData(Qt.UserRole)



def disconnect_signal(signal):
    while True:
        try:
            signal.disconnect()
        except TypeError:
            break



