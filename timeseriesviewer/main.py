# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import
from qgis.core import *
import os, sys, re, fnmatch, collections, copy, traceback, six
import logging
logger = logging.getLogger(__name__)


import qgis.utils
from timeseriesviewer.utils import *



DEBUG = True

import numpy as np
import multiprocessing
#abbreviations
from timeseriesviewer import jp, mkdir, DIR_SITE_PACKAGES, file_search
from timeseriesviewer.timeseries import *
from timeseriesviewer.profilevisualization import SpectralTemporalVisualization



#I don't know why, but this is required to run this in QGIS
#todo: still required?
path = os.path.abspath(jp(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

#ensure that required non-standard modules are available

import pyqtgraph as pg


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
    Class to control interactions between TSV and the running QGIS instance
    """
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
            self.ui.dockRendering.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)
            self.ui.dockRendering.enableQgisInteraction(True)

            self.cbQgsVectorLayer = self.ui.dockRendering.cbQgsVectorLayer
            self.gbQgsVectorLayer = self.ui.dockRendering.gbQgsVectorLayer

            self.qgsMapCanvas = self.iface.mapCanvas()
            assert isinstance(self.qgsMapCanvas, QgsMapCanvas)
            assert isinstance(self.cbQgsVectorLayer, QgsMapLayerComboBox)
            assert isinstance(self.gbQgsVectorLayer, QgsCollapsibleGroupBox)
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


class TimeSeriesViewerUI(QMainWindow,
                         loadUi('timeseriesviewer.ui')):

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

        self.dockRendering = addDockWidget(docks.RenderingDockUI(self))

        from timeseriesviewer.labeling import LabelingDockUI
        self.dockLabeling = addDockWidget(LabelingDockUI(self))

        from timeseriesviewer.sensorvisualization import SensorDockUI
        self.dockSensors = addDockWidget(SensorDockUI(self))
        self.tabifyDockWidget(self.dockSensors, self.dockRendering)

        area = Qt.BottomDockWidgetArea
        from timeseriesviewer.mapvisualization import MapViewDockUI
        self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries = addDockWidget(TimeSeriesDockUI(self))
        from timeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))
        self.tabifyDockWidget(self.dockTimeSeries, self.dockMapViews)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)


        for dock in self.findChildren(QDockWidget):
            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())


        self.dockLabeling.setHidden(True)

        self.dockTimeSeries.raise_()

        self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)

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


_iface = None

class TimeSeriesViewer:

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        _iface = iface
        # initialize GUI
        self.ui = TimeSeriesViewerUI()

        #initialize QgisTsvBridge
        self.mQgisBridge = QgisTsvBridge.instance()

        #init empty time series
        self.TS = TimeSeries()
        self.mSpatialMapExtentInitialized = False
        self.TS.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)

        #init other GUI components

        D = self.ui
        #self.ICP = D.scrollAreaSubsetContent.layout()
        #D.scrollAreaMapViews.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #self.BVP = self.ui.scrollAreaMapViews.layout()
        #D.dockNavigation.connectTimeSeries(self.TS)
        D.dockTimeSeries.connectTimeSeries(self.TS)
        D.dockSensors.connectTimeSeries(self.TS)


        self.spectralTemporalVis = SpectralTemporalVisualization(D.dockProfiles)
        self.spectralTemporalVis.connectTimeSeries(self.TS)
        assert isinstance(self, TimeSeriesViewer)

        from timeseriesviewer.mapvisualization import SpatialTemporalVisualization
        self.spatialTemporalVis = SpatialTemporalVisualization(self)
        self.spatialTemporalVis.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.spatialTemporalVis.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)
        self.spectralTemporalVis.sigMoveToTSD.connect(self.spatialTemporalVis.navigateToTSD)

        D.actionMoveCenter.triggered.connect(lambda : self.spatialTemporalVis.activateMapTool('moveCenter'))
        #D.actionSelectArea.triggered.connect(lambda : self.spatialTemporalVis.activateMapTool('selectArea'))
        D.actionZoomMaxExtent.triggered.connect(lambda : self.zoomTo('zoomMaxExtent'))
        D.actionZoomPixelScale.triggered.connect(lambda: self.zoomTo('zoomPixelScale'))
        D.actionZoomIn.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('zoomIn'))
        D.actionZoomOut.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('zoomOut'))
        D.actionPan.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('pan'))
        D.actionIdentifyTimeSeries.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyProfile'))
        D.actionIdentifyMapLayers.triggered.connect(lambda: self.spatialTemporalVis.activateMapTool('identifyMapLayers'))
        D.actionAddMapView.triggered.connect(self.spatialTemporalVis.createMapView)

        D.actionAddTSD.triggered.connect(lambda : self.addTimeSeriesImages())
        D.actionRemoveTSD.triggered.connect(lambda: self.TS.removeDates(self.ui.dockTimeSeries.selectedTimeSeriesDates()))
        D.actionRefresh.triggered.connect(self.spatialTemporalVis.refresh)
        D.actionLoadTS.triggered.connect(self.loadTimeSeriesDefinition)
        D.actionClearTS.triggered.connect(self.clearTimeSeries)
        D.actionSaveTS.triggered.connect(self.saveTimeSeriesDefinition)
        D.actionAddTSExample.triggered.connect(self.loadExampleTimeSeries)

        D.actionShowCrosshair.toggled.connect(self.spatialTemporalVis.setShowCrosshair)

        #connect buttons with actions
        from timeseriesviewer.ui.widgets import AboutDialogUI, PropertyDialogUI
        D.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())
        D.actionSettings.triggered.connect(lambda : PropertyDialogUI(self.ui).exec_())

        D.dockRendering.sigMapSizeChanged.connect(self.spatialTemporalVis.setMapSize)
        D.dockRendering.sigCrsChanged.connect(self.spatialTemporalVis.setCrs)
        D.dockRendering.sigShowVectorOverlay.connect(self.spatialTemporalVis.setVectorLayer)
        D.dockRendering.sigRemoveVectorOverlay.connect(lambda: self.spatialTemporalVis.setVectorLayer(None))

        self.spatialTemporalVis.sigCRSChanged.connect(D.dockRendering.setCrs)
        D.dockRendering.sigSpatialExtentChanged.connect(self.spatialTemporalVis.setSpatialExtent)
        D.dockRendering.sigMapCanvasColorChanged.connect(self.spatialTemporalVis.setBackgroundColor)
        self.spatialTemporalVis.setMapSize(D.dockRendering.mapSize())


        if isinstance(iface, QgisInterface):
            self.mQgisBridge.connect(self)


    def loadImageFiles(self, files):
        assert isinstance(files, list)
        self.TS.addFiles(files)


    def loadTimeSeriesDefinition(self, path=None, n_max=None):
        s = settings()
        defFile = s.value('FILE_TS_DEFINITION')
        if defFile is not None:
            defFile = os.path.dirname(defFile)
        path = QFileDialog.getOpenFileName(caption='Load Time Series definition',
                                           directory=defFile)
        if path is not None and os.path.exists(path):
            s.setValue('FILE_TS_DEFINITION', path)
            M = self.ui.dockTimeSeries.tableView_TimeSeries.model()
            M.beginResetModel()
            self.clearTimeSeries()
            self.TS.loadFromFile(path, n_max=n_max)
            M.endResetModel()


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
            canvasSize = self.spatialTemporalVis.subsetSize()
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

    def onTimeSeriesChanged(self, *args):

        if not self.mSpatialMapExtentInitialized:
            if len(self.TS.data) > 0:
                if len(self.spatialTemporalVis.MVC) == 0:
                    # add two empty band-views by default
                    self.spatialTemporalVis.createMapView()
                    self.spatialTemporalVis.createMapView()

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
        path = QFileDialog.getSaveFileName(caption='Save Time Series definition',
                                           directory=defFile)
        path = self.TS.saveToFile(path)
        if path is not None:
            s.setValue('FILE_TS_DEFINITION', path)



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
        return QCoreApplication.translate('EnMAPBox', message)



    def unload(self):
        """Removes the plugin menu item and icon """
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        QApplication.processEvents()
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


    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def addTimeSeriesImages(self, files=None):
        if files is None:
            s = settings()
            defDir = s.value('DIR_FILESEARCH')
            files = QFileDialog.getOpenFileNames(directory=defDir)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('DIR_FILESEARCH', dn)


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
    from timeseriesviewer.sandbox import initQgisEnvironment, sandboxGui
    qgsApp = initQgisEnvironment()

    sandboxGui()

    # close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':

    main()