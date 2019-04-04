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
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer.profilevisualization import SpectralTemporalVisualization
from eotimeseriesviewer import SpectralProfile, SpectralLibrary

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

        from eotimeseriesviewer.mapvisualization import MapViewCollectionDock
        self.dockMapViews = addDockWidget(MapViewCollectionDock(self))

        from qps.cursorlocationvalue import CursorLocationInfoDock
        self.dockCursorLocation = addDockWidget(CursorLocationInfoDock(self))

        # self.tabifyDockWidget(self.dockMapViews, self.dockRendering)
        self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)


        area = Qt.BottomDockWidgetArea
        # from timeseriesviewer.mapvisualization import MapViewDockUI
        # self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries = addDockWidget(TimeSeriesDockUI(self))
        from eotimeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))
        from eotimeseriesviewer.labeling import LabelingDock
        self.dockLabeling = addDockWidget(LabelingDock(self))


        from qps.speclib.spectrallibraries import SpectralLibraryPanel

        try:

            panel = SpectralLibraryPanel(None)
            panel.setParent(self)
            self.dockSpectralLibrary = addDockWidget(panel)
            self.tabifyDockWidget(self.dockTimeSeries, self.dockSpectralLibrary)
        except Exception as ex:
            print('Unable to create SpectralLibrary panel', file=sys.stderr)
            print(ex, file=sys.stderr)
            self.dockSpectralLibrary = None




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

        # self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)


    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states



    sigSubsetSizeChanged = pyqtSignal(QSize)
    def setSubsetSize(self, size, blockSignal=False):
        old = self.subsetSize()
        w = [self.spinBoxSubsetSizeX, self.spinBoxSubsetSizeY]
        if blockSignal:
            states = self._blockSignals(w, True)

        self.spinBoxSubsetSizeX.setValue(size.width())
        self.spinBoxSubsetSizeY.setValue(size.height())
        self._setUpdateBehaviour()

        if blockSignal:
            self._blockSignals(states)
        elif old != size:
            self.sigSubsetSizeChanged(size)


    def setProgress(self, value, valueMax=None, valueMin=0):
        p = self.progressBar
        if valueMin is not None and valueMin != self.progessBar.minimum():
            p.setMinimum(valueMin)
        if valueMax is not None and valueMax != self.progessBar.maximum():
            p.setMaximum(valueMax)
        self.progressBar.setValue(value)



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



    def __init__(self, iface:QgisInterface=None):
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
        if isinstance(iface, QgisInterface):
            self.iface = iface
            self.initQGISConnection()
        else:
            self.initQGISInterface()

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
        self.ui.dockMapViews.sigMapCanvasColorChanged.connect(self.spatialTemporalVis.setBackgroundColor)
        self.spatialTemporalVis.sigCRSChanged.connect(self.ui.dockMapViews.setCrs)
        self.spatialTemporalVis.sigMapSizeChanged.connect(self.ui.dockMapViews.setMapSize)
        self.spectralTemporalVis.sigMoveToTSD.connect(self.showTimeSeriesDatum)

        self.spectralTemporalVis.ui.actionLoadProfileRequest.triggered.connect(self.ui.actionIdentifyTemporalProfile.trigger)


        tstv = self.ui.dockTimeSeries.tableView_TimeSeries
        assert isinstance(tstv, TimeSeriesTableView)
        tstv.sigMoveToDateRequest.connect(self.showTimeSeriesDatum)

        from eotimeseriesviewer.mapcanvas import MapTools

        self.ui.actionMoveCenter.triggered.connect(lambda : self.spatialTemporalVis.setMapTool(MapTools.MoveToCenter))
        #D.actionSelectArea.triggered.connect(lambda : self.spatialTemporalVis.activateMapTool('selectArea'))
        self.ui.actionZoomMaxExtent.triggered.connect(lambda : self.spatialTemporalVis.setMapTool(MapTools.ZoomFull))
        self.ui.actionZoomPixelScale.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.ZoomPixelScale))
        self.ui.actionZoomIn.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.ZoomIn))
        self.ui.actionZoomOut.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.ZoomOut))
        self.ui.actionPan.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.Pan))

        self.ui.actionIdentifyTemporalProfile.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.TemporalProfile))
        self.ui.actionIdentifySpectralProfile.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.SpectralProfile))

        self.ui.actionIdentifyCursorLocationValues.triggered.connect(lambda: self.spatialTemporalVis.setMapTool(MapTools.CursorLocation))
        self.ui.dockCursorLocation.sigLocationRequest.connect(self.ui.actionIdentifyCursorLocationValues.trigger)

        from qps.cursorlocationvalue import CursorLocationInfoModel
        self.ui.dockCursorLocation.mLocationInfoModel.setNodeExpansion(CursorLocationInfoModel.ALWAYS_EXPAND)
        #D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
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
        from eotimeseriesviewer import DOCUMENTATION, SpectralLibrary, SpectralLibraryPanel
        self.ui.actionShowOnlineHelp.triggered.connect(lambda: webbrowser.open(DOCUMENTATION))

        if isinstance(self.ui.dockSpectralLibrary, SpectralLibraryPanel):

            self.ui.dockSpectralLibrary.SLW.sigLoadFromMapRequest.connect(self.ui.actionIdentifySpectralProfile.trigger)
            self.ui.dockSpectralLibrary.SLW.setMapInteraction(True)

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
        QgsProject.instance().addMapLayer(temporalProfileLayer)

        # moveToFeatureCenter = QgsMapLayerAction('Move to', self, QgsMapLayer.VectorLayer)
        # moveToFeatureCenter.triggeredForFeature.connect(self.onMoveToFeature)

        # reg = QgsGui.instance().mapLayerActionRegistry()
        # assert isinstance(reg, QgsMapLayerActionRegistry)
        # reg.addMapLayerAction(moveToFeatureCenter)
        # reg.setDefaultActionForLayer(self.ui.dockSpectralLibrary.speclib(), moveToFeatureCenter)
        # reg.setDefaultActionForLayer(self.spectralTemporalVis.temporalProfileLayer(), moveToFeatureCenter)

        self.applySettings()

        TimeSeriesViewer._instance = self

    def spectralLibrary(self)->SpectralLibrary:
        """
        Returns the SpectraLibrary of the SpectralLibrary dock
        :return: SpectraLibrary
        """
        from qps.speclib.spectrallibraries import SpectralLibraryPanel
        if isinstance(self.ui.dockSpectralLibrary, SpectralLibraryPanel):
            return self.ui.dockSpectralLibrary.SLW.speclib()
        else:
            return None


    def showTimeSeriesDatum(self, tsd:TimeSeriesDatum):
        """
        Moves the viewport of the scroll window to a specific TimeSeriesDatum
        :param tsd:  TimeSeriesDatum
        """
        assert isinstance(tsd, TimeSeriesDatum)
        self.spatialTemporalVis.navigateToTSD(tsd)
        #todo: move TableViews to as well

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
        self.ui.actionImportExtent.triggered.connect(lambda: self.spatialTemporalVis.setSpatialExtent(SpatialExtent.fromMapCanvas(self.iface.mapCanvas())))
        self.ui.actionExportExtent.triggered.connect(lambda: self.iface.mapCanvas().setExtent(self.spatialTemporalVis.spatialExtent().toCrs(self.iface.mapCanvas().mapSettings().destinationCrs())))
        self.ui.actionExportCenter.triggered.connect(lambda: self.iface.mapCanvas().setCenter(self.spatialTemporalVis.spatialExtent().spatialCenter()))
        self.ui.actionImportCenter.triggered.connect(lambda: self.spatialTemporalVis.setSpatialCenter(SpatialPoint.fromMapCanvasCenter(self.iface.mapCanvas())))

    def initQGISInterface(self):
        """
        Initialize the QGIS Interface in case the EO TSV was not started from a QGIS GUI Instance
        """
        self.iface = self
        qgis.utils.iface = self

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
        self.spatialTemporalVis.setBackgroundColor(value(Keys.MapBackgroundColor))
        self.spatialTemporalVis.setMapSize(value(Keys.MapSize))

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

            #add metadata
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
        self.mTimeSeries.addSources(files)


    def loadTimeSeriesDefinition(self, path=None, n_max=None):
        """
        Loads a time series definition file
        :param path:
        :param n_max:
        :return:
        """
        s = settings()
        defFile = s.value('file_ts_definition')
        defDir = None
        if defFile is not None:
            defDir = os.path.dirname(defFile)

        filters = "CSV (*.csv *.txt);;" + \
                  "All files (*.*)"

        path, filter = QFileDialog.getOpenFileName(caption='Load Time Series definition', directory=defDir, filter=filters)
        if path is not None and os.path.exists(path):
            s.setValue('file_ts_definition', path)
            M = self.ui.dockTimeSeries.tableView_TimeSeries.model()
            M.beginResetModel()
            self.clearTimeSeries()
            self.mTimeSeries.loadFromFile(path, n_max=n_max)
            M.endResetModel()

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
            if len(self.mTimeSeries.mTSDs) > 0:
                if len(self.spatialTemporalVis.MVC) == 0:
                    # add an empty MapView by default
                    self.spatialTemporalVis.createMapView()
                    #self.spatialTemporalVis.createMapView()

                extent = self.mTimeSeries.maxSpatialExtent()

                self.spatialTemporalVis.setCrs(extent.crs())
                self.spatialTemporalVis.setSpatialExtent(extent)
                self.mSpatialMapExtentInitialized = True



        if len(self.mTimeSeries.mTSDs) == 0:
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
            for f in files:
                try:
                    l = QgsVectorLayer(f, os.path.basename(f))
                    vectorLayers.append(l)
                except Exception as ex:
                    pass
            #QgsProject.instance().addMapLayers(vectorLayers)
            self.mapLayerStore().addMapLayers(vectorLayers)

    def addTimeSeriesImages(self, files:list):
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
        #remove views

        M = self.ui.dockTimeSeries.tableView_TimeSeries.model()
        M.beginResetModel()
        self.mTimeSeries.clear()
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
