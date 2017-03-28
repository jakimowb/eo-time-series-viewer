# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HUB TimeSeriesViewer
                                 A QGIS based time series viewer
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

# Import the code for the dialog
import os, sys, re, fnmatch, collections, copy, traceback, six
import logging
logger = logging.getLogger(__name__)
from qgis.core import *

from timeseriesviewer.utils import *
from timeseriesviewer.ui import load


DEBUG = True

import numpy as np
import multiprocessing
#abbreviations
from timeseriesviewer import jp, mkdir, DIR_SITE_PACKAGES, file_search
from timeseriesviewer.timeseries import *




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
    Class to control interactions between TSV and a running QGIS instance
    """
    _instance = None


    @staticmethod
    def instance():
        return QgisTsvBridge._instance

    def __init__(self, iface, TSV):
        super(QgisTsvBridge, self).__init__()
        assert QgisTsvBridge._instance is None
        assert isinstance(TSV, TimeSeriesViewer)
        assert isinstance(iface, QgisInterface)
        self.iface = iface
        self.TSV = TSV
        self.ui = self.TSV.ui
        self.SpatTempVis = self
        self.syncBlocked = False

        from timeseriesviewer.ui.widgets import TimeSeriesViewerUI
        assert isinstance(self.ui, TimeSeriesViewerUI)

        self.cbQgsVectorLayer = self.ui.dockRendering.cbQgsVectorLayer
        self.gbQgsVectorLayer = self.ui.dockRendering.gbQgsVectorLayer
        self.cbQgsVectorLayer.setEnabled(True)
        self.gbQgsVectorLayer.setEnabled(True)
        self.qgsMapCanvas = self.iface.mapCanvas()
        assert isinstance(self.qgsMapCanvas, QgsMapCanvas)

        self.qgsMapCanvas.extentsChanged.connect(self.syncTsvWithQgs)
        self.qgsMapCanvas.destinationCrsChanged.connect(self.syncTsvWithQgs)


        assert isinstance(self.cbQgsVectorLayer, QgsMapLayerComboBox)
        assert isinstance(self.gbQgsVectorLayer, QgsCollapsibleGroupBox)

        self.TSV.spatialTemporalVis.sigSpatialExtentChanged.connect(self.syncQgsWithTsv)

        self.gbQgsVectorLayer.clicked.connect(self.onQgsVectorLayerChanged)
        self.cbQgsVectorLayer.layerChanged.connect(self.onQgsVectorLayerChanged)
        self.onQgsVectorLayerChanged(None)

    def syncTsvWithQgs(self, *args):
        if self.syncBlocked:
            return
        syncState = self.ui.dockNavigation.qgsSyncState()
        if any(syncState.values()):
            self.syncBlocked = True
            self.syncBlocked = True
            QTimer.singleShot(500, lambda: self.unblock())
            tsvExt = self.TSV.spatialTemporalVis.extent
            qgsExt = SpatialExtent.fromMapCanvas(self.qgsMapCanvas)
            newExtent = self.newExtent(tsvExt, syncState, qgsExt)
            self.TSV.spatialTemporalVis.setSpatialExtent(newExtent)
            self.syncBlocked = False

        pass


    def syncQgsWithTsv(self, spatialExtent):

        if self.syncBlocked:
            return


        syncState = self.ui.dockNavigation.qgsSyncState()
        if any(syncState.values()):
            self.syncBlocked = True
            QTimer.singleShot(500, lambda: self.unblock())
            tsvExt = self.TSV.spatialTemporalVis.extent
            qgsExt = SpatialExtent.fromMapCanvas(self.qgsMapCanvas)
            newExtent = self.newExtent(qgsExt, syncState, tsvExt)
            self.qgsMapCanvas.setDestinationCrs(newExtent.crs())
            self.qgsMapCanvas.setExtent(newExtent)
            self.syncBlocked = False

            QTimer.singleShot(1000, lambda : self.unblock())


    def unblock(self):
        self.syncBlocked = False

    def newExtent(self, oldExtent, syncState, newExtent):

        crs = newExtent.crs() if syncState['crs'] else oldExtent.crs()
        extent = oldExtent
        if syncState['extent']:
            extent = newExtent.toCrs(crs)
        elif syncState['center']:
            import copy
            extent = copy.copy(oldExtent)
            extent.setCenter(newExtent.center(), newExtent.crs())

        return extent


    def onQgsVectorLayerChanged(self, lyr):
        if self.gbQgsVectorLayer.isChecked() and \
           isinstance(self.cbQgsVectorLayer.currentLayer(), QgsVectorLayer):
            self.TSV.spatialTemporalVis.setVectorLayer(self.cbQgsVectorLayer.currentLayer())
        else:
            self.TSV.spatialTemporalVis.setVectorLayer(None)


    def extent(self):
        assert isinstance(self.qgsMapCanvas, QgsMapCanvas)
        return SpatialExtent.fromMapCanvas(self.qgsMapCanvas)


    def syncExtent(self, isChecked):
        if isChecked:
            self.cbSyncQgsMapCenter.setEnabled(False)
            self.cbSyncQgsMapCenter.blockSignals(True)
            self.cbSyncQgsMapCenter.setChecked(True)
            self.cbSyncQgsMapCenter.blockSignals(False)
        else:
            self.cbSyncQgsMapCenter.setEnabled(True)
        self.qgsSyncStateChanged()

    def qgsSyncState(self):
        return (self.cbSyncQgsMapCenter.isChecked(),
                self.cbSyncQgsMapExtent.isChecked(),
                self.cbSyncQgsCRS.isChecked())





class TimeSeriesViewerUI(QMainWindow,
                         load('timeseriesviewer.ui')):

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
        self.dockNavigation = addDockWidget(docks.NavigationDockUI(self))

        from timeseriesviewer.labeling import LabelingDockUI
        self.dockLabeling = addDockWidget(LabelingDockUI(self))
        #self.tabifyDockWidget(self.dockNavigation, self.dockRendering)
        #self.tabifyDockWidget(self.dockNavigation, self.dockLabeling)

        from timeseriesviewer.sensorvisualization import SensorDockUI
        self.dockSensors = addDockWidget(SensorDockUI(self))
        #area = Qt.RightDockWidgetArea


        area = Qt.BottomDockWidgetArea

        self.dockMapViews = addDockWidget(docks.MapViewDockUI(self))
        self.dockTimeSeries = addDockWidget(docks.TimeSeriesDockUI(self))
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
        self.dockNavigation.raise_()

        self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)


        #todo: move to QGS_TSV_Bridge
        self.dockRendering.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)

        #define subset-size behaviour

        self.restoreSettings()


    def restoreSettings(self):
        from timeseriesviewer import SETTINGS

        #set last CRS
        self.dockNavigation.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        s = ""


    def setQgsLinkWidgets(self):
        #enable/disable widgets that rely on QGIS instance interaction
        from timeseriesviewer import QGIS_TSV_BRIDGE
        from timeseriesviewer.main import QgisTsvBridge
        b = isinstance(QGIS_TSV_BRIDGE, QgisTsvBridge)
        self.dockNavigation.gbSyncQgs.setEnabled(b)
        self.dockRendering.gbQgsVectorLayer.setEnabled(b)

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



class TimeSeriesViewer:

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface

        self.ui = TimeSeriesViewerUI()

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

        from timeseriesviewer.mapvisualization import SpatialTemporalVisualization
        self.spatialTemporalVis = SpatialTemporalVisualization(self)
        self.spatialTemporalVis.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.spatialTemporalVis.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        self.spatialTemporalVis.sigShowProfiles.connect(self.spectralTemporalVis.loadCoordinate)

        self.spectralTemporalVis.sigMoveToTSD.connect(self.spatialTemporalVis.navigateToTSD)
        D.dockNavigation.sigSetSpatialExtent.connect(self.spatialTemporalVis.setSpatialExtent)
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

        D.actionAddTSD.triggered.connect(lambda : self.addTimeSeriesImages())
        D.actionRemoveTSD.triggered.connect(lambda: self.TS.removeDates(self.ui.dockTimeSeries.selectedTimeSeriesDates()))
        D.actionRefresh.triggered.connect(self.spatialTemporalVis.refresh)
        D.actionLoadTS.triggered.connect(self.loadTimeSeries)
        D.actionClearTS.triggered.connect(self.clearTimeSeries)
        D.actionSaveTS.triggered.connect(self.ua_saveTSFile)
        D.actionAddTSExample.triggered.connect(self.ua_loadExampleTS)

        D.actionShowCrosshair.toggled.connect(self.spatialTemporalVis.setShowCrosshair)

        #connect buttons with actions
        from timeseriesviewer.ui.widgets import AboutDialogUI, PropertyDialogUI
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

        if iface:
            import timeseriesviewer
            timeseriesviewer.QGIS_TSV_BRIDGE = QgisTsvBridge(iface, self)
            self.ui.setQgsLinkWidgets()


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
            QMessageBox.information(self.ui, 'File not found', '{} - this file describes an exemplary time series.'.format(PATH_EXAMPLE_TIMESERIES))
        else:
            self.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES)



    def ua_selectByRectangle(self):
        if self.RectangleMapTool is not None:
            self.qgsCanvas.setMapTool(self.RectangleMapTool)

    def ua_selectByCoordinate(self):
        if self.PointMapTool is not None:
            self.qgsCanvas.setMapTool(self.PointMapTool)



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

    def addTimeSeriesImages(self, files=None):
        if files is None:
            files = QFileDialog.getOpenFileNames()

            #collect sublayers, if existing


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


