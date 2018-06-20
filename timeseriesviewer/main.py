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

from qgis.core import *
import os, sys, re, fnmatch, collections, copy, traceback, six, multiprocessing




r"""
File "D:\Programs\OSGeo4W\apps\Python27\lib\multiprocessing\managers.py", line
528, in start
self._address = reader.recv()
EOFError

see https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Multiprocessing
see https://github.com/CleanCut/green/issues/103 

"""

path = os.path.abspath(os.path.join(sys.exec_prefix, '../../bin/pythonw.exe'))

if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

import qgis.utils
from timeseriesviewer.utils import *
from timeseriesviewer import jp, mkdir, DIR_SITE_PACKAGES, messageLog
from timeseriesviewer.timeseries import *
from timeseriesviewer.profilevisualization import SpectralTemporalVisualization
import numpy as np



DEBUG = False

from timeseriesviewer.spectrallibraries import createQgsField, createStandardFields
import timeseriesviewer.spectrallibraries

fields = [f for f in createStandardFields()]
fields.insert(1, createQgsField('date', ''))
fields.insert(2, createQgsField('sensorname', ''))
standardFields = QgsFields()
for field in fields:
    standardFields.append(field)
timeseriesviewer.spectrallibraries.createStandardFields = lambda: standardFields

#ensure that required non-standard modules are available

import pyqtgraph as pg


"""
class QgisTsvBridge(QObject):
    #Class to control interactions between TSV and the running QGIS instance
    _instance = None

    @staticmethod
    def instance():
        if QgisTsvBridge._instance is None:
            QgisTsvBridge._instance = QgisTsvBridge()
        return QgisTsvBridge._instance

    @staticmethod
    def qgisInstance():
        if qgis.utils is not None and isinstance(qgis.utils.iface, QgisInterface):
            return qgis.utils.iface
        else:
            return None

    @staticmethod
    def addMapLayers(mapLayers, checkDuplicates=False):
        iface = QgisTsvBridge.qgisInstance()
        if iface:
            existingSources = [lyr.source() for lyr in iface.mapCanvas().layers()]

            for ml in mapLayers:
                assert isinstance(ml, QgsMapLayer)
                src = ml.source()
                if checkDuplicates and src in existingSources:
                    continue

                if isinstance(ml, QgsRasterLayer):
                    iface.addRasterLayer(src)
                if isinstance(ml, QgsVectorLayer):
                    iface.addVectorLayer(src, os.path.basename(src), ml.providerType())



    sigQgisProjectClosed = pyqtSignal()

    def __init__(self, parent=None):
        assert QgisTsvBridge._instance is None, 'Can not instantiate QgsTsvBridge twice'
        super(QgisTsvBridge, self).__init__(parent)
        self.TSV = None
        self.ui = None
        self.SpatTempVis = None
    def isValid(self):
        return isinstance(self.iface, QgisInterface) and isinstance(self.TSV, TimeSeriesViewer)

    def connect(self,TSV):
        # super(QgisTsvBridge, self).__init__(parent=TSV)
        iface = QgisTsvBridge.qgisInstance()
        if iface:
            self.iface = iface
            self.TSV = TSV
            self.ui = self.TSV.ui
            self.SpatTempVis = self



            from timeseriesviewer.ui.docks import RenderingDockUI
            assert isinstance(self.ui, TimeSeriesViewerUI)
            assert isinstance(self.ui.dockRendering, RenderingDockUI)

            self.ui.dockRendering.sigQgisInteractionRequest.connect(self.onQgisInteractionRequest)
            self.ui.dockRendering.enableQgisInteraction(True)

            #self.cbQgsVectorLayer = self.ui.dockRendering.cbQgsVectorLayer
            #self.gbQgsVectorLayer = self.ui.dockRendering.gbQgsVectorLayer

            self.qgsMapCanvas = self.iface.mapCanvas()
            assert isinstance(self.qgsMapCanvas, QgsMapCanvas)
            #assert isinstance(self.cbQgsVectorLayer, QgsMapLayerComboBox)
            #assert isinstance(self.gbQgsVectorLayer, QgsCollapsibleGroupBox)
            return True
        else:
            return False

    def addLayersToQGIS(self, mapLayers, noDuplicates=False):
        QgisTsvBridge.addMapLayers(mapLayers, checkDuplicates=noDuplicates)

    def onQgisInteractionRequest(self, request):
        if not self.isValid(): return
        assert isinstance(self.qgsMapCanvas, QgsMapCanvas)
        extQgs = SpatialExtent.fromMapCanvas(self.qgsMapCanvas)

        assert isinstance(self.TSV, TimeSeriesViewer)
        extTsv = self.TSV.spatialTemporalVis.spatialExtent()

        assert request in ['tsvCenter2qgsCenter',
                            'tsvExtent2qgsExtent',
                            'qgisCenter2tsvCenter',
                            'qgisExtent2tsvExtent']

        if request == 'tsvCenter2qgsCenter':
            center = SpatialPoint.fromSpatialExtent(extTsv)
            center = center.toCrs(extQgs.crs())
            if center:
                self.qgsMapCanvas.setCenter(center)
                self.qgsMapCanvas.refresh()

        if request == 'qgisCenter2tsvCenter':
            center = SpatialPoint.fromSpatialExtent(extQgs)
            center = center.toCrs(extTsv.crs())
            if center:
                self.TSV.spatialTemporalVis.setSpatialCenter(center)
                if self.ui.dockRendering.cbLoadCenterPixelProfile.isChecked():
                    self.TSV.spectralTemporalVis.loadCoordinate(center)

        if request == 'tsvExtent2qgsExtent':
            extent = extTsv.toCrs(extQgs.crs())
            if extent:
                self.qgsMapCanvas.setExtent(extent)
                self.qgsMapCanvas.refresh()

        if request == 'qgisExtent2tsvExtent':
            extent = extQgs.toCrs(extTsv.crs())
            if extent:
                self.TSV.spatialTemporalVis.setSpatialExtent(extent)
                if self.ui.dockRendering.cbLoadCenterPixelProfile.isChecked():
                    self.TSV.spectralTemporalVis.loadCoordinate(extent.spatialCenter())

"""

class TimeSeriesViewerUI(QMainWindow,
                         loadUI('timeseriesviewer.ui')):

    sigQgsSyncChanged = pyqtSignal(bool, bool, bool)

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
        from timeseriesviewer import TITLE, icon
        self.setWindowTitle(TITLE)

        self.setWindowIcon(icon())


        #set button default actions -> this will show the action icons as well
        #I don't know why this is not possible in the QDesigner when QToolButtons are
        #placed outside a toolbar

        import timeseriesviewer.ui.docks as docks

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

        #self.dockRendering = addDockWidget(docks.RenderingDockUI(self))

        if DEBUG:
            from timeseriesviewer.labeling import LabelingDockUI
            self.dockLabeling = addDockWidget(LabelingDockUI(self))
            self.dockLabeling.setHidden(True)

        from timeseriesviewer.sensorvisualization import SensorDockUI
        self.dockSensors = addDockWidget(SensorDockUI(self))

        from timeseriesviewer.mapvisualization import MapViewCollectionDock
        self.dockMapViews = addDockWidget(MapViewCollectionDock(self))

        from timeseriesviewer.cursorlocationvalue import CursorLocationInfoDock
        self.dockCursorLocation = addDockWidget(CursorLocationInfoDock(self))

        #self.tabifyDockWidget(self.dockMapViews, self.dockRendering)
        self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)


        area = Qt.BottomDockWidgetArea
        #from timeseriesviewer.mapvisualization import MapViewDockUI
        #self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries = addDockWidget(TimeSeriesDockUI(self))
        from timeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))

        from timeseriesviewer.spectrallibraries import SpectralLibraryPanel
        self.dockSpectralLibrary = addDockWidget(SpectralLibraryPanel(self))

        self.tabifyDockWidget(self.dockTimeSeries, self.dockSpectralLibrary)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)


        area = Qt.RightDockWidgetArea

        from timeseriesviewer.systeminfo import SystemInfoDock
        self.dockSystemInfo = addDockWidget(SystemInfoDock(self))
        self.dockSystemInfo.setVisible(False)


        for dock in self.findChildren(QDockWidget):
            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())




        self.dockTimeSeries.raise_()

        #self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)

        self.restoreSettings()


    def restoreSettings(self):
        from timeseriesviewer import SETTINGS

        #todo: restore settings
        s = ""



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
                Qgis.Info:'INFO',
                Qgis.Critical:'INFO',
                Qgis.Warning:'WARNING',
                Qgis.Success:'SUCCESS',
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
        return TimeSeriesViewer._instance



    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """

        assert TimeSeriesViewer.instance() is None

        QObject.__init__(self)
        QgisInterface.__init__(self)
        QApplication.processEvents()

        self.ui = TimeSeriesViewerUI()

        # Save reference to the QGIS interface

        if isinstance(iface, QgisInterface):
            self.iface = iface
            self.initQGISConnection()
        else:
            self.initQGISInterface()


        #


        #init empty time series
        self.TS = TimeSeries()
        self.mSpatialMapExtentInitialized = False
        self.TS.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)

        #init other GUI components


        #self.ICP = D.scrollAreaSubsetContent.layout()
        #D.scrollAreaMapViews.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #self.BVP = self.ui.scrollAreaMapViews.layout()
        #D.dockNavigation.connectTimeSeries(self.TS)
        self.ui.dockTimeSeries.setTimeSeries(self.TS)
        self.ui.dockSensors.setTimeSeries(self.TS)


        self.spectralTemporalVis = SpectralTemporalVisualization(self.TS, self.ui.dockProfiles)
        self.spectralTemporalVis.pixelLoader.sigLoadingFinished.connect(
            lambda dt: self.ui.dockSystemInfo.addTimeDelta('Pixel Profile', dt))
        assert isinstance(self, TimeSeriesViewer)

        from timeseriesviewer.mapvisualization import SpatialTemporalVisualization
        self.spatialTemporalVis = SpatialTemporalVisualization(self)
        #self.spatialTemporalVis.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        #self.spatialTemporalVis.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        #self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)

        self.spatialTemporalVis.sigShowProfiles.connect(self.onShowProfile)
        self.ui.dockMapViews.sigCrsChanged.connect(self.spatialTemporalVis.setCrs)
        self.ui.dockMapViews.sigMapSizeChanged.connect(self.spatialTemporalVis.setMapSize)
        self.ui.dockMapViews.sigMapCanvasColorChanged.connect(self.spatialTemporalVis.setBackgroundColor)
        self.spatialTemporalVis.sigCRSChanged.connect(self.ui.dockMapViews.setCrs)
        self.spatialTemporalVis.sigMapSizeChanged.connect(self.ui.dockMapViews.setMapSize)
        self.spectralTemporalVis.sigMoveToTSD.connect(self.spatialTemporalVis.navigateToTSD)

        self.spectralTemporalVis.ui.actionLoadProfileRequest.triggered.connect(self.ui.actionIdentifyTemporalProfile.trigger)
        from timeseriesviewer.mapcanvas import MapTools

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

        from timeseriesviewer.cursorlocationvalue import CursorLocationInfoModel
        self.ui.dockCursorLocation.mLocationInfoModel.setNodeExpansion(CursorLocationInfoModel.ALWAYS_EXPAND)
        #D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
        self.ui.actionAddMapView.triggered.connect(self.spatialTemporalVis.MVC.createMapView)

        self.ui.actionAddTSD.triggered.connect(lambda : self.addTimeSeriesImages())
        self.ui.actionAddVectorData.triggered.connect(lambda : self.addVectorData())
        self.ui.actionRemoveTSD.triggered.connect(lambda: self.TS.removeDates(self.ui.dockTimeSeries.selectedTimeSeriesDates()))
        self.ui.actionRefresh.triggered.connect(self.spatialTemporalVis.refresh)
        self.ui.actionLoadTS.triggered.connect(self.loadTimeSeriesDefinition)
        self.ui.actionClearTS.triggered.connect(self.clearTimeSeries)
        self.ui.actionSaveTS.triggered.connect(self.saveTimeSeriesDefinition)
        self.ui.actionAddTSExample.triggered.connect(self.loadExampleTimeSeries)
        self.ui.actionLoadTimeSeriesStack.triggered.connect(self.loadTimeSeriesStack)
        self.ui.actionShowCrosshair.toggled.connect(self.spatialTemporalVis.setShowCrosshair)

        #connect buttons with actions
        from timeseriesviewer.ui.widgets import AboutDialogUI, PropertyDialogUI
        self.ui.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())
        self.ui.actionSettings.triggered.connect(lambda : PropertyDialogUI(self.ui).exec_())
        import webbrowser
        from timeseriesviewer import URL_DOCUMENTATION
        self.ui.actionShowOnlineHelp.triggered.connect(lambda : webbrowser.open(URL_DOCUMENTATION))

        self.ui.dockSpectralLibrary.SLW.sigLoadFromMapRequest.connect(self.ui.actionIdentifySpectralProfile.trigger)
        self.ui.dockSpectralLibrary.SLW.setMapInteraction(True)


        QgsProject.instance().addMapLayer(self.ui.dockSpectralLibrary.speclib(), False)
        QgsProject.instance().addMapLayer(self.spectralTemporalVis.temporalProfileLayer(), False)

        moveToFeatureCenter = QgsMapLayerAction('Move to', self, QgsMapLayer.VectorLayer)
        moveToFeatureCenter.triggeredForFeature.connect(self.onMoveToFeature)

        reg = QgsGui.instance().mapLayerActionRegistry()
        assert isinstance(reg, QgsMapLayerActionRegistry)
        reg.addMapLayerAction(moveToFeatureCenter)
        reg.setDefaultActionForLayer(self.ui.dockSpectralLibrary.speclib(), moveToFeatureCenter)
        reg.setDefaultActionForLayer(self.spectralTemporalVis.temporalProfileLayer(), moveToFeatureCenter)

    def onMoveToFeature(self, layer:QgsMapLayer, feature:QgsFeature):
        g = feature.geometry()
        if isinstance(g, QgsGeometry):
            c = g.centroid()
            x, y = c.asPoint()
            crs = layer.crs()
            center = SpatialPoint(crs, x, y)
            self.spatialTemporalVis.setSpatialCenter(center)
            self.ui.actionRefresh.trigger()
            s = ""
    def initQGISConnection(self):

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


    def onShowProfile(self, spatialPoint, mapCanvas, mapToolKey):
        #self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)
        assert isinstance(spatialPoint, SpatialPoint)
        assert isinstance(mapCanvas, QgsMapCanvas)
        from timeseriesviewer.mapcanvas import MapTools
        assert mapToolKey in MapTools.mapToolKeys()

        if mapToolKey == MapTools.TemporalProfile:
            self.spectralTemporalVis.loadCoordinate(spatialPoint)
        elif mapToolKey == MapTools.SpectralProfile:
            from timeseriesviewer.spectrallibraries import SpectralProfile
            tsd = self.spatialTemporalVis.DVC.tsdFromMapCanvas(mapCanvas)

            if not hasattr(self, 'cntSpectralProfile'):
                self.cntSpectralProfile = 0

            profiles = SpectralProfile.fromMapCanvas(mapCanvas, spatialPoint)
            #add metadata
            if isinstance(tsd, TimeSeriesDatum):
                for p in profiles:
                    assert isinstance(p, SpectralProfile)
                    p.setName('Profile {} {}'.format(self.cntSpectralProfile, tsd.date))
                    p.setMetadata(u'date', u'{}'.format(tsd.date), addMissingFields=True)
                    p.setMetadata(u'sensorname', u'{}'.format(tsd.sensor.name()) , addMissingFields=True)
                    p.setMetadata(u'sensorid', u'{}'.format(tsd.sensor.id()), addMissingFields=True)

            self.cntSpectralProfile += 1
            self.ui.dockSpectralLibrary.SLW.setCurrentSpectra(profiles)

        elif mapToolKey == MapTools.CursorLocation:

            self.ui.dockCursorLocation.loadCursorLocation(spatialPoint, mapCanvas)

        else:
            s = ""
        pass

    def messageBar(self):
        return self.ui.messageBar

    def loadImageFiles(self, files):
        assert isinstance(files, list)
        self.TS.addFiles(files)


    def loadTimeSeriesDefinition(self, path=None, n_max=None):
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
            self.TS.loadFromFile(path, n_max=n_max)
            M.endResetModel()

    def createMapView(self):
        self.spatialTemporalVis.createMapView()

    def mapViews(self):
        return self.spatialTemporalVis.MVC[:]

    def zoomTo(self, key):
        if key == 'zoomMaxExtent':
            ext = self.TS.getMaxSpatialExtent(self.ui.dockRendering.crs())
        elif key == 'zoomPixelScale':

            extent = self.spatialTemporalVis.spatialExtent()
            #calculate in web-mercator for metric distances
            crs = self.spatialTemporalVis.crs()
            crsWMC = QgsCoordinateReferenceSystem('EPSG:3857')

            extentWMC = extent.toCrs(crsWMC)
            pxSize = max(self.TS.getPixelSizes(), key= lambda s :s.width())
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


    def icon(self):
        return TimeSeriesViewer.icon()


    def logMessage(self, message, tag, level):
        m = message.split('\n')
        if '' in message.split('\n'):
            m = m[0:m.index('')]
        m = '\n'.join(m)
        if DEBUG: print(message)
        if not re.search('timeseriesviewer', m):
            return

        if level in [Qgis.Critical, Qgis.Warning]:


            if False:
                widget = self.ui.messageBar.createMessage(tag, message)
                button = QPushButton(widget)
                button.setText("Show")
                button.pressed.connect(lambda: showMessage(message, '{}'.format(tag), level))
                widget.layout().addWidget(button)


                self.ui.messageBar.pushWidget(widget, level, SETTINGS.value('MESSAGE_TIMEOUT', 10))
            else:
                self.ui.messageBar.pushMessage(tag, message, level=level)
            #print on normal console
            print(u'{}({}): {}'.format(tag, level, message))

    def onTimeSeriesChanged(self, *args):

        if not self.mSpatialMapExtentInitialized:
            if len(self.TS.data) > 0:
                if len(self.spatialTemporalVis.MVC) == 0:
                    # add an empty MapView by default
                    self.spatialTemporalVis.createMapView()
                    #self.spatialTemporalVis.createMapView()

                extent = self.TS.getMaxSpatialExtent()

                self.spatialTemporalVis.setCrs(extent.crs())
                self.spatialTemporalVis.setSpatialExtent(extent)
                self.mSpatialMapExtentInitialized = True



        if len(self.TS.data) == 0:
            self.mSpatialMapExtentInitialized = False


    def saveTimeSeriesDefinition(self):
        s = settings()
        defFile = s.value('FILE_TS_DEFINITION')
        if defFile is not None:
            defFile = os.path.dirname(defFile)

        filters = "CSV (*.csv *.txt);;" + \
                  "All files (*.*)"
        path, filter = QFileDialog.getSaveFileName(caption='Save Time Series definition', filter=filters, directory=defFile)
        path = self.TS.saveToFile(path)
        if path is not None:
            s.setValue('FILE_TS_DEFINITION', path)

    def loadTimeSeriesStack(self):

        from timeseriesviewer.stackedbandinput import StackedBandInputDialog

        d = StackedBandInputDialog(parent=self.ui)
        if d.exec_() == QDialog.Accepted:
            writtenFiles = d.saveImages()
            self.addTimeSeriesImages(writtenFiles)



    def loadExampleTimeSeries(self):
        import example.Images
        files = file_search(os.path.dirname(example.Images.__file__), '*.tif')
        self.addTimeSeriesImages(files)


    def qgs_handleMouseDown(self, pt, btn):
        pass



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
            QgsProject.instance().addMapLayers(vectorLayers)


    def addTimeSeriesImages(self, files=None):
        if files is None:
            s = settings()
            defDir = s.value('dir_datasources')

            filters = QgsProviderRegistry.instance().fileRasterFilters()
            files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('dir_datasources', dn)


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


def main():
    # add site-packages to sys.path as done by enmapboxplugin.py
    from timeseriesviewer.utils import initQgisApplication
    qgsApp = initQgisApplication()
    ts = TimeSeriesViewer(None)
    ts.run()
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':

    import timeseriesviewer.__main__ as m
    m.run()