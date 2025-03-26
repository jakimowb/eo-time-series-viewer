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
import json
import os
import pathlib
import re
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Match, Optional, Pattern, Tuple, Union

from qgis.core import edit, Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, \
    QgsExpressionContext, QgsFeature, QgsField, QgsFields, QgsFillSymbol, QgsGeometry, QgsMapLayer, QgsMessageOutput, \
    QgsPointXY, QgsProcessingContext, QgsProcessingFeedback, QgsProcessingMultiStepFeedback, QgsProcessingUtils, \
    QgsProject, QgsProjectArchive, QgsProviderRegistry, QgsRasterLayer, QgsSingleSymbolRenderer, QgsTask, \
    QgsTaskManager, QgsVectorLayer, QgsWkbTypes, QgsZipUtils
from processing import AlgorithmDialog
from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot, QCoreApplication, QDateTime, QFile, QObject, QRect, QSize, Qt, QTimer
import qgis.utils
from qgis.PyQt.QtGui import QCloseEvent, QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog, \
    QHBoxLayout, QLabel, QMainWindow, QMenu, QProgressBar, QProgressDialog, QSizePolicy, QToolBar, QToolButton, QWidget
from qgis.PyQt.QtXml import QDomCDATASection, QDomDocument, QDomElement
from qgis.gui import QgisInterface, QgsDockWidget, QgsFileWidget, QgsMapCanvas, QgsMessageBar, QgsMessageViewer, \
    QgsStatusBar, QgsTaskManagerWidget
import eotimeseriesviewer
from eotimeseriesviewer import debugLog, DIR_UI, DOCUMENTATION, LOG_MESSAGE_TAG, settings
from eotimeseriesviewer.docks import LabelDockWidget, SpectralLibraryDockWidget
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapView, MapViewDock, MapWidget
from eotimeseriesviewer.timeseries import TimeSeries, \
    TimeSeriesDate, TimeSeriesDock, TimeSeriesSource, TimeSeriesTreeView, \
    TimeSeriesWidget
from .sensors import has_sensor_id, SensorInstrument, SensorMockupDataProvider
from .dateparser import DateTimePrecision
from eotimeseriesviewer.vectorlayertools import EOTSVVectorLayerTools
from .about import AboutDialogUI
from .forceinputs import FindFORCEProductsTask, FORCEProductImportDialog
from .maplayerproject import EOTimeSeriesViewerProject
from .qgispluginsupport.qps.cursorlocationvalue import CursorLocationInfoDock
from .qgispluginsupport.qps.layerproperties import showLayerPropertiesDialog
from .qgispluginsupport.qps.maptools import MapTools
from .qgispluginsupport.qps.qgisenums import QMETATYPE_INT, QMETATYPE_QDATE, QMETATYPE_QSTRING
from .qgispluginsupport.qps.speclib.core import create_profile_field, is_spectral_library, profile_field_list
from .qgispluginsupport.qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from .qgispluginsupport.qps.speclib.core.spectralprofile import encodeProfileValueDict
from .qgispluginsupport.qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from .qgispluginsupport.qps.speclib.gui.spectralprofilesources import StandardLayerProfileSource
from .qgispluginsupport.qps.subdatasets import subLayers
from .qgispluginsupport.qps.utils import file_search, loadUi, SpatialExtent, SpatialPoint
from .settings.settings import EOTSVSettingsManager
from .settings.widget import EOTSVSettingsWidgetFactory
from .tasks import EOTSVTask
from .temporalprofile.temporalprofile import TemporalProfileUtils
from .temporalprofile.visualization import TemporalProfileDock
from .utils import fixMenuButtons

DEBUG = False

SPECTRA_PROFILE_FIELDS = QgsFields()
SPECTRA_PROFILE_FIELDS.append(create_profile_field('profiles'))
SPECTRA_PROFILE_FIELDS.append(QgsField('date', QMETATYPE_QDATE))
SPECTRA_PROFILE_FIELDS.append(QgsField('doy', QMETATYPE_INT))
SPECTRA_PROFILE_FIELDS.append(QgsField('sensor', QMETATYPE_QSTRING))


class EOTimeSeriesViewerUI(QMainWindow):
    sigAboutToBeClosed = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(EOTimeSeriesViewerUI, self).__init__(parent)
        loadUi(DIR_UI / 'timeseriesviewer.ui', self)

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

        area = Qt.LeftDockWidgetArea

        # self.dockRendering = addDockWidget(docks.RenderingDockUI(self))

        from eotimeseriesviewer.mapvisualization import MapViewDock
        self.dockMapViews: MapViewDock = self.addDockWidget(area, MapViewDock(self))
        # self.dockProcessingToolbox = self.addDockWidget(area, processing.gui.ProcessingToolbox.ProcessingToolbox())
        # self.tabifyDockWidget(self.dockMapViews, self.dockProcessingToolbox)
        self.dockMapViews.raise_()

        # self.tabifyDockWidget(self.dockMapViews, self.dockRendering)
        # self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)

        area = Qt.BottomDockWidgetArea
        # from timeseriesviewer.mapvisualization import MapViewDockUI
        # self.dockMapViews = addDockWidget(MapViewDockUI(self))

        self.dockTimeSeries: TimeSeriesDock = self.addDockWidget(area, TimeSeriesDock(self))

        tbar: QToolBar = self.dockTimeSeries.timeSeriesWidget().toolBar()
        tbar.addSeparator()
        tbar.addAction(self.actionAddTSD)
        tbar.addAction(self.actionRemoveTSD)
        tbar.addAction(self.actionLoadTS)
        tbar.addAction(self.actionSaveTS)
        tbar.addSeparator()
        tbar.addAction(self.actionClearTS)
        self.dockTimeSeries.timeSeriesWidget().sigTimeSeriesDatesSelected.connect(self.actionRemoveTSD.setEnabled)

        self.dockProfiles = self.addDockWidget(area, TemporalProfileDock(self))

        area = Qt.BottomDockWidgetArea
        # panel = SpectralLibraryPanel(self)

        # self.dockSpectralLibrary = self.addDockWidget(area, panel)

        # self.tabifyDockWidget(self.dockTimeSeries, self.dockSpectralLibrary)
        # self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)
        # self.tabifyDockWidget(self.dockTimeSeries, self.dockLabeling)

        area = Qt.RightDockWidgetArea

        self.dockTaskManager = QgsDockWidget('Task Manager')
        self.dockTaskManager.setWidget(QgsTaskManagerWidget(QgsApplication.taskManager()))
        self.dockTaskManager.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.dockTaskManager = self.addDockWidget(area, self.dockTaskManager)

        from eotimeseriesviewer.systeminfo import SystemInfoDock
        from eotimeseriesviewer.sensorvisualization import SensorDockUI

        self.dockSystemInfo = self.addDockWidget(area, SystemInfoDock(self))
        self.dockSystemInfo.setVisible(False)

        self.dockSensors = self.addDockWidget(area, SensorDockUI(self))
        self.dockCursorLocation = self.addDockWidget(area, CursorLocationInfoDock(self))

        self.tabifyDockWidget(self.dockSensors, self.dockCursorLocation)
        self.tabifyDockWidget(self.dockSensors, self.dockSystemInfo)
        self.tabifyDockWidget(self.dockSensors, self.dockTaskManager)
        self.dockSensors.raise_()

        for dock in self.findChildren(QDockWidget):

            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())

        self.dockTimeSeries.raise_()

    def addDockWidget(self, area: Qt.DockWidgetArea, dock: QDockWidget) -> QDockWidget:
        """
        shortcut to add a created dock and return it
        :param dock:
        :return:
        """
        dock.setParent(self)
        super().addDockWidget(area, dock)
        return dock

    def registerMapToolAction(self, a: QAction) -> QAction:
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

    def onMapToolActionToggled(self, b: bool, action: QAction):
        """
        Reacts on toggling a map tool
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

    def closeEvent(self, a0: QCloseEvent):
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
    if message.startswith('<html>'):
        v.setMessage(message, QgsMessageOutput.MessageHtml)
    else:
        v.setMessage(message, QgsMessageOutput.MessageText)
    v.showMessage(True)


class TaskManagerStatusButton(QToolButton):

    def __init__(self, taskManager: QgsTaskManager, parent: QWidget = None):
        super().__init__(parent)

        self.mManager: QgsTaskManager = taskManager
        self.setAutoRaise(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setLayout(QHBoxLayout())

        self.mInfoLabel = QLabel('', parent=self)
        # self.setStyleSheet('background-color:yellow')
        # self.mInfoLabel.setStyleSheet('background-color:#234521;')
        # self.mInfoLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.mInfoLabel.setWordWrap(False)
        self.mProgressBar = QProgressBar(parent=self)
        self.mProgressBar.setMinimum(0)
        self.mProgressBar.setMaximum(100)
        self.mProgressBar.setMaximumWidth(100)
        self.mProgressBar.setMaximumHeight(18)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.mProgressBar)
        self.layout().addWidget(self.mInfoLabel)
        #        self.layout().setStretchFactor(self.mInfoLabel, 2)
        # self.layout().addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        # self.clicked.connect(self.toggleDisplay)
        """
        self.mFloatingWidget = QgsTaskManagerFloatingWidget( manager, parent ? parent->window() : nullptr );
        self.mFloatingWidget.setAnchorWidget( this );
        self.mFloatingWidget.setAnchorPoint( QgsFloatingWidget::BottomMiddle );
        self.mFloatingWidget.setAnchorWidgetPoint( QgsFloatingWidget::TopMiddle );
        self.mFloatingWidget.hide();
        """
        # self.hide()

        self.mManager.taskAdded.connect(self.onTaskAdded)
        # self.mManager.allTasksFinished.connect(self.allFinished)
        # self.mManager.finalTaskProgressChanged.connect(self.overallProgressChanged)
        # self.mManager.countActiveTasksChanged.connect(self.countActiveTasksChanged)

    def onTaskAdded(self, taskID):
        task = self.mManager.task(taskID)

        if isinstance(task, EOTSVTask):
            task.progressChanged.connect(self.updateTaskInfo)
            task.taskCompleted.connect(self.updateTaskInfo)
            task.taskTerminated.connect(self.updateTaskInfo)

    def sizeHint(self):
        m = self.fontMetrics()
        txt = self.mInfoLabel.text()
        if hasattr(m, 'horizontalAdvance'):
            width = m.horizontalAdvance('X')
        else:
            width = m.width('X')
        width = int(width * 50 * Qgis.UI_SCALE_FACTOR)
        # width = super().sizeHint().width()
        # width = width + self.mInfoLabel.sizeHint().width()
        height = super().sizeHint().height() - 5
        return QSize(width, height)

    def activeTasks(self) -> List[QgsTask]:
        results = []
        for t in self.mManager.tasks():
            if isinstance(t, EOTSVTask):
                results.append(t)
                break
        return results

    def updateTaskInfo(self, *args):
        n = 0
        p = 0.0
        activeTasks = self.activeTasks()
        activeTasks = self.activeTasks()
        for t in activeTasks:
            n += 1
            p += t.progress()

        if n == 0:
            p = 0
            self.mInfoLabel.setText('')
        else:
            self.mInfoLabel.setText(activeTasks[-1].description())
            p = int(round(p / n))
        self.mProgressBar.setValue(p)
        self.setVisible(n > 0)


class EOTimeSeriesViewer(QgisInterface, QObject):
    sigCurrentDateChanged = pyqtSignal(TimeSeriesDate)
    sigCurrentLocationChanged = pyqtSignal([QgsCoordinateReferenceSystem, QgsPointXY],
                                           [QgsCoordinateReferenceSystem, QgsPointXY, QgsMapCanvas])

    sigCurrentSpectralProfilesChanged = pyqtSignal(list)
    sigCurrentTemporalProfilesChanged = pyqtSignal(list)
    currentLayerChanged = pyqtSignal(QgsMapLayer)

    _instance = None

    @staticmethod
    def instance() -> Optional['EOTimeSeriesViewer']:
        """
        Returns the TimeSeriesViewer instance
        :return:
        """
        return EOTimeSeriesViewer._instance

    def __init__(self):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # QObject.__init__(self)
        QgisInterface.__init__(self)
        # QApplication.processEvents()

        assert EOTimeSeriesViewer.instance() is None, 'EOTimeSeriesViewer instance already exists.'
        EOTimeSeriesViewer._instance = self
        self.ui = EOTimeSeriesViewerUI()

        # create status bar
        self.ui.statusBar().setStyleSheet("QStatusBar::item {border: none;}")

        # Drop the font size in the status bar by a couple of points
        statusBarFont = self.ui.font()
        fontSize = statusBarFont.pointSize()
        if os.name == 'windows':
            fontSize = max(fontSize - 1, 8)  # bit less on windows, due to poor rendering of small point sizes
        else:
            fontSize = max(fontSize - 2, 6)
        statusBarFont.setPointSize(fontSize)

        self.mStatusBar = QgsStatusBar()
        self.mStatusBar.setParentStatusBar(self.ui.statusBar())
        self.mStatusBar.setFont(statusBarFont)

        self.ui.statusBar().setFont(statusBarFont)
        self.ui.statusBar().addPermanentWidget(self.mStatusBar, 1)

        self.mTaskManager = QgsApplication.taskManager()
        self.mTaskManagerButton = TaskManagerStatusButton(self.mTaskManager, parent=self.mStatusBar, )
        self.mTaskManagerButton.setFont(statusBarFont)
        self.mStatusBar.addPermanentWidget(self.mTaskManagerButton, 10, QgsStatusBar.AnchorLeft)
        self.mTaskManagerButton.clicked.connect(lambda *args: self.ui.dockTaskManager.raise_())
        self.mMapLayerStore: EOTimeSeriesViewerProject = self.mapWidget().mapLayerStore()

        mvd: MapViewDock = self.ui.dockMapViews
        tswidget: TimeSeriesWidget = self.ui.dockTimeSeries.timeSeriesWidget()
        mw: MapWidget = self.ui.mMapWidget

        assert isinstance(mvd, MapViewDock)
        assert isinstance(mw, MapWidget)
        assert isinstance(tswidget, TimeSeriesWidget)

        self.ui.sigAboutToBeClosed.connect(self.onClose)

        import qgis.utils
        assert isinstance(qgis.utils.iface, QgisInterface)
        QgsProject.instance().layersWillBeRemoved.connect(self.onLayersWillBeRemoved)
        QgsApplication.instance().messageLog().messageReceived.connect(self.logMessage)

        # self.mapLayerStore().addMapLayer(self.ui.dockSpectralLibrary.speclib())

        self.mPostDataLoadingArgs: dict = dict()

        self.mVectorLayerTools: EOTSVVectorLayerTools = EOTSVVectorLayerTools()
        self.mVectorLayerTools.sigMessage.connect(lambda msg, level: self.logMessage(msg, LOG_MESSAGE_TAG, level))
        self.mVectorLayerTools.sigPanRequest.connect(self.setSpatialCenter)
        self.mVectorLayerTools.sigZoomRequest.connect(self.setSpatialExtent)
        self.mVectorLayerTools.sigEditingStarted.connect(self.updateCurrentLayerActions)
        self.mVectorLayerTools.sigFocusVisibility.connect(self.focusTimeSeriesDateVisibility)
        self.mVectorLayerTools.sigFlashFeatureRequest.connect(self.flashFeatures)
        # Save reference to the QGIS interface

        # init empty time series
        self.mTimeSeries = TimeSeries()
        self.mTimeSeries.setDateTimePrecision(DateTimePrecision.Day)
        self.mSpatialMapExtentInitialized = False
        self.mTemporalProfileLayerInitialized = False
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)
        self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self.onTimeSeriesChanged)
        self.mTimeSeries.sigSensorAdded.connect(self.onSensorAdded)

        # self.mTimeSeries.sigMessage.connect(self.setM)

        tswidget.setTimeSeries(self.mTimeSeries)
        self.ui.dockSensors.setTimeSeries(self.mTimeSeries)
        self.ui.dockProfiles.setTimeSeries(self.mTimeSeries)
        self.ui.dockProfiles.setVectorLayerTools(self.mVectorLayerTools)
        mw.setTimeSeries(self.mTimeSeries)
        # mvd.setTimeSeries(self.mTimeSeries)
        mvd.setMapWidget(mw)

        self.profileDock: TemporalProfileDock = self.ui.dockProfiles
        self.profileDock.sigMoveToDate.connect(self.setCurrentDate)
        self.profileDock.setProject(self.mapLayerStore())

        # mw.sigSpatialExtentChanged.connect(self.timeSeries().setCurrentSpatialExtent)
        mw.sigVisibleDatesChanged.connect(self.timeSeries().setVisibleDates)
        mw.sigMapViewAdded.connect(self.onMapViewAdded)
        mw.sigCurrentLocationChanged[QgsCoordinateReferenceSystem, QgsPointXY].connect(
            lambda crs, pt, canvas=mw: self.setCurrentLocation(SpatialPoint(crs, pt),
                                                               mapCanvas=mw.currentMapCanvas()))
        mw.sigCurrentLayerChanged.connect(self.updateCurrentLayerActions)
        mw.sigCurrentDateChanged.connect(self.sigCurrentDateChanged)
        mw.sigCurrentDateChanged.connect(tswidget.setCurrentDate)

        self.ui.optionSyncMapCenter.toggled.connect(self.mapWidget().setSyncWithQGISMapCanvas)
        tb = self.ui.toolBarTimeControl
        assert isinstance(tb, QToolBar)
        tb.addAction(mw.actionFirstDate)
        tb.addAction(mw.actionBackwardFast)
        tb.addAction(mw.actionBackward)
        tb.addAction(mw.actionForward)
        tb.addAction(mw.actionForwardFast)
        tb.addAction(mw.actionLastDate)

        tstv: TimeSeriesTreeView = tswidget.timeSeriesTreeView()
        assert isinstance(tstv, TimeSeriesTreeView)
        tstv.sigMoveToDate.connect(self.setCurrentDate)
        tstv.sigMoveToSource.connect(self.setCurrentSource)
        tstv.sigMoveToExtent.connect(self.setSpatialExtent)
        tstv.sigSetMapCrs.connect(self.setCrs)
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

        initMapToolAction(self.ui.mActionSelectFeatures, MapTools.SelectFeature)
        assert isinstance(self.ui.mActionSelectFeatures, QAction)
        initMapToolAction(self.ui.mActionAddFeature, MapTools.AddFeature)

        self.ui.mActionZoomToLayer.triggered.connect(self.onZoomToLayer)
        self.ui.mActionOpenTable.triggered.connect(self.onOpenTable)

        self.ui.optionSelectFeaturesRectangle.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesPolygon.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesFreehand.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.optionSelectFeaturesRadius.triggered.connect(self.onSelectFeatureOptionTriggered)
        self.ui.mActionDeselectFeatures.triggered.connect(self.deselectFeatures)

        m = QMenu()
        m.addAction(self.ui.optionSelectFeaturesRectangle)
        m.addAction(self.ui.optionSelectFeaturesPolygon)
        m.addAction(self.ui.optionSelectFeaturesFreehand)
        m.addAction(self.ui.optionSelectFeaturesRadius)

        self.ui.mActionSelectFeatures.setMenu(m)

        def onEditingToggled(b: bool):
            l = self.currentLayer()
            if b:
                self.mVectorLayerTools.startEditing(l)
            else:
                self.mVectorLayerTools.stopEditing(l, True)

        self.ui.mActionToggleEditing.toggled.connect(onEditingToggled)

        # create edit toolbar
        tb = self.ui.toolBarVectorFeatures
        assert isinstance(tb, QToolBar)

        # set default map tool
        self.ui.actionPan.toggle()
        self.ui.dockCursorLocation.sigLocationRequest.connect(self.ui.actionIdentifyCursorLocationValues.trigger)
        # self.ui.dockCursorLocation.mLocationInfoModel.setNodeExpansion(CursorLocationInfoModel.ALWAYS_EXPAND)
        self.ui.actionAddMapView.triggered.connect(mw.createMapView)
        self.ui.actionAddTSD.triggered.connect(lambda: self.addTimeSeriesImages(None))
        self.ui.actionAddVectorData.triggered.connect(lambda: self.addVectorData())
        self.ui.actionCreateSpectralLibrary.triggered.connect(self.createSpectralLibrary)
        self.ui.actionAddSubDatasets.triggered.connect(self.openAddSubdatasetsDialog)
        self.ui.actionCreateTemporalProfileLayer.triggered.connect(self.createTemporalProfileLayer)

        # see https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi/data-formats/xsd
        self.ui.actionAddSentinel2.triggered.connect(
            lambda: self.openAddSubdatasetsDialog(
                title='Open Sentinel-2 Datasets', filter='MTD_MSIL*.xml'))

        self.ui.actionRemoveTSD.triggered.connect(
            lambda: self.mTimeSeries.removeTSDs(tswidget.selectedTimeSeriesDates()))
        self.ui.actionRefresh.triggered.connect(mw.refresh)
        self.ui.actionLoadTS.triggered.connect(self.loadTimeSeriesDefinition)
        self.ui.actionClearTS.triggered.connect(self.clearTimeSeries)
        self.ui.actionSaveTS.triggered.connect(self.saveTimeSeriesDefinition)
        self.ui.actionAddTSExample.triggered.connect(lambda: self.loadExampleTimeSeries(loadAsync=True))
        self.ui.actionLoadTimeSeriesStack.triggered.connect(self.loadTimeSeriesStack)
        self.ui.actionAddFORCEProducts.triggered.connect(self.loadFORCEProducts)
        # self.ui.actionShowCrosshair.toggled.connect(mw.setCrosshairVisibility)
        self.ui.actionExportMapsToImages.triggered.connect(lambda: self.exportMapsToImages())

        self.ui.mActionLayerProperties.triggered.connect(self.onShowLayerProperties)
        from qgis.utils import iface
        self.ui.actionLoadProject.triggered.connect(iface.actionOpenProject().trigger)
        self.ui.actionReloadProject.triggered.connect(self.reloadProject)
        self.ui.actionSaveProject.triggered.connect(iface.actionSaveProject().trigger)

        # self.profileDock.actionLoadProfileRequest.triggered.connect(self.activateIdentifyTemporalProfileMapTool)

        # connect buttons with actions
        self.ui.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())

        self.ui.actionSettings.triggered.connect(self.showSettingsDialog)

        self.ui.actionShowOnlineHelp.triggered.connect(lambda: webbrowser.open(DOCUMENTATION))

        # self.processingToolbox().executeWithGui.connect(self.executeAlgorithm)

        # SLW: SpectralLibraryWidget = self.ui.dockSpectralLibrary.spectralLibraryWidget()
        # assert isinstance(SLW, SpectralLibraryWidget)
        # SLW.setVectorLayerTools(self.mVectorLayerTools)
        # add time-specific fields
        # sl = self.spectralLibrary()

        # self.mMapLayerStore.addMapLayer(sl)

        # temporalProfileLayer = self.profileDock.temporalProfileLayer()
        # assert isinstance(temporalProfileLayer, QgsVectorLayer)
        # temporalProfileLayer.setName('EOTS Temporal Profiles')
        # self.mapLayerStore().addMapLayer(temporalProfileLayer)

        eotimeseriesviewer.labeling.MAP_LAYER_STORES.append(self.mapLayerStore())
        eotimeseriesviewer.labeling.registerLabelShortcutEditorWidget()
        self.applySettings()

        self.initQGISConnection()

        for toolBar in self.ui.findChildren(QToolBar):
            fixMenuButtons(toolBar)

        self.ui.dockTimeSeries.setFloating(True)
        self.ui.dockTimeSeries.setFloating(False)

        QgsProject.instance().writeProject.connect(self.onWriteProject)
        QgsProject.instance().readProject.connect(self.onReadProject)

    def mapCanvas(self) -> Optional[MapCanvas]:
        """
        Returns the 1st shown map canvas
        :return:
        """
        for c in self.mapWidget().mapCanvases():
            return c
        return None

    def executeAlgorithm(self, alg_id):
        # processingPlugin = qgis.utils.plugins.get('processing', ProcessingPlugin(iface))

        # processingPlugin.executeAlgorithm(alg_id, parent, in_place=in_place, as_batch=as_batch)
        config = {}
        alg = QgsApplication.instance().processingRegistry().createAlgorithmById(alg_id, config)

        return None
        if alg is not None:

            ok, message = alg.canExecute()
            if not ok:
                dlg = MessageDialog()
                dlg.setTitle(self.tr('Error executing algorithm'))
                dlg.setMessage(
                    self.tr('<h3>This algorithm cannot '
                            'be run :-( </h3>\n{0}').format(message))
                dlg.exec()
                return

    def taskManager(self) -> QgsTaskManager:
        return self.mTaskManager

    def onClose(self):
        debugLog('Close EOTSV')

        EOTimeSeriesViewer._instance = None
        self.mapWidget().onClose()

    def applyAllVisualChanges(self):
        tm = QgsApplication.taskManager()
        while any(tm.activeTasks()):
            print('Wait for QgsTaskManager to finish all tasks...\r', flush=True)
            QgsApplication.processEvents()
        QApplication.processEvents()
        while self.mapWidget().mMapRefreshBlock:
            QApplication.processEvents()
        self.mapWidget().timedRefresh()
        while any(tm.activeTasks()):
            print('Wait for QgsTaskManager to finish all tasks...\r', flush=True)
            QgsApplication.processEvents()
        QApplication.processEvents()

    def asMap(self) -> dict:

        dockInfos = dict()
        for dock in self.ui.findChildren(QDockWidget):
            dock: QDockWidget
            n = dock.windowTitle()
            dockInfos[n] = {
                'floating': dock.isFloating(),
                'visible': dock.isVisibleTo(dock.parent()),
                'size': [dock.width(), dock.height()]
            }

        g: QRect = self.ui.geometry()
        mainWindow = {
            'geometry': [g.x(), g.y(), g.width(), g.height()],
            'docks': dockInfos,
        }

        d = {'MainWindow': mainWindow,
             'TimeSeries': self.timeSeries().asMap(),
             'MapWidget': self.mapWidget().asMap()}

        return d

    def fromMap(self, map_data: dict, feedback: QgsProcessingFeedback = QgsProcessingFeedback()):

        multistep = QgsProcessingMultiStepFeedback(2, feedback)
        multistep.setCurrentStep(1)

        self.timeSeries().fromMap(map_data.get('TimeSeries'), feedback=multistep)
        multistep.setCurrentStep(2)
        self.mapWidget().fromMap(map_data.get('MapWidget'), feedback=multistep)

        if mainWindow := map_data.get('MainWindow'):

            if dockInfos := mainWindow.get('docks'):
                dockInfos: Dict[str, dict]
                for dock in self.ui.findChildren(QDockWidget):
                    dock: QDockWidget
                    dockTitle = dock.windowTitle()
                    if dockInfo := dockInfos.get(dockTitle):

                        dock.setFloating(dockInfo.get('floating', dock.isFloating()))
                        dock.setVisible(dockInfo.get('visible', dock.isVisible()))
                        if bSize := dockInfo.get('size'):
                            dock.resize(*bSize)
                        # dock.set(dockInfo.get('isFloating', dock.isFloating()))

            if g := mainWindow.get('geometry'):
                self.ui.setGeometry(QRect(*g))
                QApplication.processEvents()
                assert self.ui.height() == g[-1]

    def asJson(self) -> str:
        return json.dumps(self.asMap(), ensure_ascii=False)

    def fromJson(self, jsonText: str, feedback: QgsProcessingFeedback = None):

        data = json.loads(jsonText)

        if isinstance(data, dict):
            self.fromMap(data, feedback=feedback)

    def onWriteProject(self, dom: QDomDocument):

        node: QDomElement = dom.createElement('EOTSV')
        root = dom.documentElement()
        cdata: QDomCDATASection = dom.createCDATASection(self.asJson())
        jsonNode = dom.createElement('jsonSettings')
        jsonNode.appendChild(cdata)
        node.appendChild(jsonNode)
        root.appendChild(node)

    def onReadProject(self, doc: QDomDocument) -> bool:
        """
        Reads images and visualization settings from a QgsProject QDomDocument
        :param doc: QDomDocument
        :return: bool
        """
        if not isinstance(doc, QDomDocument):
            return False

        sender = self.sender()

        root = doc.documentElement()
        node = root.firstChildElement('EOTSV')

        # if isinstance(sender, QgsProject):
        #    print(f'# READ_PROJECT: {id(sender)} {sender.fileName()}')
        #    print(f'# READ_PROJECT: {id(sender)} {sender.fileName()}')
        debugLog()
        if node.nodeName() == 'EOTSV':

            class MyProgress(QgsProcessingFeedback):

                textChanged = pyqtSignal(str)

                def __init__(self, *args, **kwds):
                    super().__init__(*args, **kwds)

                def setProgressText(self, text):
                    super().setProgressText(text)
                    self.textChanged.emit(text)

            dialog = self._createProgressDialog(title='Load Project')
            dialog.setMinimumDuration(1)
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setRange(0, 100)
            dialog.setValue(0)
            feedback = MyProgress()

            def onProgress(v):
                dialog.setValue(int(v))

            feedback.progressChanged.connect(onProgress)
            feedback.textChanged.connect(dialog.setLabelText)
            dialog.canceled.connect(feedback.cancel)

            try:
                self.timeSeries().clear()

                mapviews = self.mapViews()

                for mv in mapviews:
                    self.mapWidget().removeMapView(mv)
                dialog.setValue(35)
                jsonText = node.firstChildElement('jsonSettings').text()
                self.fromJson(jsonText, feedback=feedback)
            except Exception as ex:
                if True:
                    raise ex
                print(ex, file=sys.stderr)

            dialog.setValue(100)
            dialog.close()

        return True

    def reloadProject(self, *args):

        proj: QgsProject = QgsProject.instance()
        path = proj.fileName()
        if os.path.isfile(path):
            archive = None
            if QgsZipUtils.isZipFile(path):
                archive = QgsProjectArchive()
                archive.unzip(path)
                path = archive.projectFile()

            file = QFile(path)

            doc = QDomDocument('qgis')
            doc.setContent(file)
            self.onReadProject(doc)

            if isinstance(archive, QgsProjectArchive):
                archive.clearProjectFile()

    def onLayersWillBeRemoved(self, layers):
        ids: List[str] = []
        for lyr in layers:
            if isinstance(lyr, QgsMapLayer):
                ids.append(lyr.id())
            elif isinstance(lyr, str):
                ids.append(lyr)

        to_remove = []
        for d in self.ui.findChildren(SpectralLibraryDockWidget):
            assert isinstance(d, SpectralLibraryDockWidget)
            if isinstance(d.speclib(), QgsVectorLayer) and d.speclib().id() in ids:
                to_remove.append(d)

        for d in self.ui.findChildren(LabelDockWidget):
            assert isinstance(d, LabelDockWidget)
            if isinstance(d.vectorLayer(), QgsVectorLayer) and d.vectorLayer().id() in ids:
                to_remove.append(d)

        for d in to_remove:
            self.ui.removeDockWidget(d)

    def onPostDataLoading(self):
        """
        Handles actions that can be applied on a filled time series only, i.e. after sigLoadingTaskFinished was called.
        """
        if 'mapDate' in self.mPostDataLoadingArgs.keys():
            mapDate = self.mPostDataLoadingArgs.pop('mapDate')
            tsd = self.timeSeries().tsd(mapDate, None)
            if isinstance(tsd, TimeSeriesDate):
                self.setCurrentDate(tsd)

        self.timeSeries().sigLoadingTaskFinished.disconnect(self.onPostDataLoading)

    def lockCentralWidgetSize(self, b: bool):
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

    def sensors(self) -> List[SensorInstrument]:
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

    def _createProgressDialog(self, title='Load Data') -> QProgressDialog:
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

    def deselectFeatures(self):
        """
        Removes all feature selections (across all map canvases)
        """
        for canvas in self.mapCanvases():
            assert isinstance(canvas, QgsMapCanvas)
            for vl in [l for l in canvas.layers() if isinstance(l, QgsVectorLayer)]:
                assert isinstance(vl, QgsVectorLayer)
                vl.removeSelection()

    def exportMapsToImages(self,
                           path: Union[None, str, Path] = None,
                           format: str = 'PNG'):
        """
        Exports the map canvases to local images.
        :param path: directory to save the images in
        :param format: raster format, e.g. 'PNG' or 'JPG'
        """
        import string

        if path is None:
            d = SaveAllMapsDialog()

            path = EOTSVSettingsManager.settings().dirScreenShots
            if isinstance(path, str):
                d.setDirectory(path)

            if d.exec() != QDialog.Accepted:
                s = ""
                return

            format = d.fileType().lower()
            path = d.directory()

        else:
            format = format.lower()

        path = Path(path)

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
            if not isinstance(tsd, TimeSeriesDate):
                continue
            mv = mapCanvas.mapView()
            assert isinstance(mv, MapView)
            mapCanvas.waitWhileRendering()
            imgPath = '{}.{}.{}'.format(tsd.dtg(), mv.title(), format)

            imgPath = ''.join(c for c in imgPath if c in valid_chars)
            imgPath = imgPath.replace(' ', '_')
            imgPath = os.path.join(path, imgPath)

            mapCanvas.saveAsImage(imgPath, None, format)
            progressDialog.setValue(i + 1)
            progressDialog.setLabelText('{}/{} maps saved'.format(i + 1, n))

            if progressDialog.wasCanceled():
                return

        settings = EOTSVSettingsManager.settings()
        if settings.dirScreenShots != path:
            settings.dirScreenShots = path
            EOTSVSettingsManager.saveSettings(settings)

    def onMapViewAdded(self, mapView: MapView):
        """

        :param mapView:
        :return:
        """
        # mapView.addLayer(self.profileDock.temporalProfileLayer())
        mapView.addSpectralProfileLayers()

        if len(self.mapViews()) == 1:
            mapView.setMapInfoExpression("@map_date + '\n' + @map_sensor")

    def temporalProfileLayers(self) -> List[QgsVectorLayer]:
        """
        Returns known layers with temporal profiles
        :return:
        """

        return self.profileDock.temporalProfileLayer()

    def spectralLibraryWidgets(self) -> List[SpectralLibraryWidget]:
        return [dw.spectralLibraryWidget() for dw in self.ui.findChildren(SpectralLibraryDockWidget)]

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        """
        Returns the SpectraLibrary that are opened as the SpectralLibrary dock
        :return: SpectraLibrary
        """
        return [w.speclib() for w in self.spectralLibraryWidgets()]

    def openAddSubdatasetsDialog(self, *args,
                                 title: str = 'Open Subdatasets',
                                 filter: str = '*.*'):

        from .qgispluginsupport.qps.subdatasets import SubDatasetSelectionDialog

        d = SubDatasetSelectionDialog()
        d.setWindowTitle(title)
        d.setFileFilter(filter)
        d.exec_()
        if d.result() == QDialog.Accepted:
            files = d.selectedSubDatasets()
            if len(files) > 0:
                self.addTimeSeriesImages(files)

    def close(self):
        self._stopTasks()
        self.mapWidget().close()
        self.mapLayerStore().removeAllMapLayers()
        self.ui.close()
        EOTimeSeriesViewer._instance = None

    def _stopTasks(self):

        tm: QgsTaskManager = QgsApplication.taskManager()
        while (tm.count()) > 0:

            for task in tm.tasks():
                if isinstance(task, EOTSVTask):
                    task.cancel()
            QgsApplication.instance().processEvents()
        s = ""

    def actionCopyLayerStyle(self) -> QAction:
        return self.ui.mActionCopyLayerStyle

    def actionOpenTable(self) -> QAction:
        return self.ui.mActionOpenTable

    def actionZoomActualSize(self) -> QAction:
        return self.ui.actionZoomPixelScale

    def actionZoomFullExtent(self) -> QAction:
        return self.ui.actionZoomFullExtent

    def actionZoomToLayer(self) -> QAction:
        return self.ui.mActionZoomToLayer

    def actionZoomIn(self) -> QAction:
        return self.ui.actionZoomIn

    def actionZoomOut(self) -> QAction:
        return self.ui.actionZoomOut

    def actionPasteLayerStyle(self) -> QAction:
        return self.ui.mActionPasteLayerStyle

    def actionLayerProperties(self) -> QAction:
        return self.ui.mActionLayerProperties

    def actionToggleEditing(self) -> QAction:
        return self.ui.mActionToggleEditing

    def setCurrentLayer(self, layer: QgsMapLayer):
        self.mapWidget().setCurrentLayer(layer)
        self.updateCurrentLayerActions()

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self.mapWidget().crs()

    def setCurrentSource(self, tss: TimeSeriesSource):
        """
        Moves the map view to a TimeSeriesSource
        """
        debugLog('EOTImeSeriesViewersetCurrentSource')
        tss = self.timeSeries().findSource(tss)
        if isinstance(tss, TimeSeriesSource):
            self.ui.mMapWidget.setCurrentDate(tss.timeSeriesDate())

            ext = tss.spatialExtent().toCrs(self.crs())
            # set to new extent, but do not change the EOTSV CRS
            if isinstance(ext, SpatialExtent):
                self.setSpatialExtent(ext)
            else:
                # we cannot transform the coordinate. Try to set the EOTSV center only
                center = tss.spatialExtent().spatialCenter().toCrs(self.crs())
                if isinstance(center, SpatialPoint):
                    self.setSpatialCenter(center)
                else:
                    # last resort: we need to change the EOTSV Projection
                    self.setSpatialExtent(tss.spatialExtent())

    def moveTo(self, date: QDateTime = None,
               geometry: Union[SpatialPoint, SpatialExtent] = None):

        # set geometry first, e.g. on zoom operations
        if isinstance(geometry, SpatialPoint):
            self.setSpatialCenter(geometry)
        elif isinstance(geometry, SpatialExtent):
            self.setSpatialExtent(geometry)
        elif geometry is not None:
            print('Unsupported moveTo action')

        # set temporal subset, i.e. current date
        if date:
            self.setCurrentDate(date)

    def setCurrentDate(self, tsd: TimeSeriesDate, show_if_hidden: bool = True):
        """
        Moves the viewport of the scroll window to a specific TimeSeriesDate
        :param show_if_hidden:
        :param tsd:  TimeSeriesDate or numpy.datetime64
        """
        tsd = self.timeSeries().findDate(tsd)
        if isinstance(tsd, TimeSeriesDate):
            if show_if_hidden:
                self.mTimeSeries.showTSDs([tsd], b=True)
            self.ui.mMapWidget.setCurrentDate(tsd)

    def mapCanvases(self) -> List[MapCanvas]:
        """
        Returns all MapCanvases of the spatial visualization
        :return: [list-of-MapCanvases]
        """
        return self.ui.mMapWidget.mapCanvases()

    def project(self) -> QgsProject:
        return self.mapWidget().mapLayerStore()

    def mapLayerStore(self) -> EOTimeSeriesViewerProject:
        """
        Returns the QgsMapLayerStore which is used to register QgsMapLayers
        :return: QgsMapLayerStore
        """
        return self.mapWidget().mapLayerStore()

    def onOpenTable(self):
        c = self.currentLayer()
        if isinstance(c, QgsVectorLayer):
            self.showAttributeTable(c)

    def onZoomToLayer(self):

        c = self.currentLayer()
        if isinstance(c, QgsMapLayer):
            self.setSpatialExtent(SpatialExtent.fromLayer(c))

    def onMoveToFeature(self, layer: QgsMapLayer, feature: QgsFeature):
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
        m = self.ui.mActionSelectFeatures.menu()
        if isinstance(a, QAction) and isinstance(m, QMenu) and a in m.actions():
            for ca in m.actions():
                assert isinstance(ca, QAction)
                if ca == a:
                    self.ui.mActionSelectFeatures.setIcon(a.icon())
                    self.ui.mActionSelectFeatures.setToolTip(a.toolTip())
                ca.setChecked(ca == a)
        self.setMapTool(MapTools.SelectFeature)

    def onSelectFeatureTriggered(self):
        self.setMapTool(MapTools.SelectFeature)

    def initQGISConnection(self):
        """
        Initializes interactions between TimeSeriesViewer and the QGIS instances
        :return:
        """
        iface = qgis.utils.iface
        assert isinstance(iface, QgisInterface)

        self.ui.actionImportExtent.triggered.connect(
            lambda: self.setSpatialExtent(SpatialExtent.fromMapCanvas(iface.mapCanvas())))
        self.ui.actionImportCenter.triggered.connect(
            lambda: self.setSpatialCenter(SpatialPoint.fromMapCanvasCenter(iface.mapCanvas())))

        def setQGISCenter(*args):
            c = iface.mapCanvas()
            if isinstance(c, QgsMapCanvas):
                c.setCenter(self.spatialCenter().toCrs(c.mapSettings().destinationCrs()))
                c.refresh()

        def setQGISExtent(*args):
            c = iface.mapCanvas()
            if isinstance(c, QgsMapCanvas):
                c.setExtent(self.spatialExtent().toCrs(c.mapSettings().destinationCrs()))
                c.refresh()

        self.ui.actionExportExtent.triggered.connect(setQGISExtent)
        self.ui.actionExportCenter.triggered.connect(setQGISCenter)

        self.mapWidget().setCrs(iface.mapCanvas().mapSettings().destinationCrs())

    def onShowLayerProperties(self,
                              lyr: Optional[QgsMapLayer] = None,
                              canvas: Optional[QgsMapCanvas] = None):

        if not isinstance(lyr, QgsMapLayer):
            lyr = self.currentLayer()
            canvas = self.currentMapCanvas()

        # in any case, replace a mockup layer with a real layer instance
        # to let the properties dialog make image stats calculations on real images
        if (isinstance(lyr, QgsRasterLayer) and lyr.isValid()
                and lyr.dataProvider().name() == SensorMockupDataProvider.__name__):
            sid = lyr.source()

            newLyr = None
            for mv in self.mapViews():
                if lyr not in mv.sensorProxyLayers():
                    continue
                for sLyr in mv.sensorLayers(sid):
                    newLyr = sLyr
                    break
            if newLyr is None:
                # find
                for tsd in self.timeSeries():
                    if tsd.sensor().id() == sid:
                        for tss in tsd.sources():
                            newLyr = tss.asRasterLayer(True)
                            break
                    if newLyr:
                        break
            if newLyr:
                lyr = newLyr

        if isinstance(lyr, QgsMapLayer):
            if not isinstance(canvas, QgsMapCanvas) or lyr not in canvas.layers():
                canvas = QgsMapCanvas()
                canvas.setDestinationCrs(lyr.crs())
                canvas.setExtent(lyr.extent())
                canvas.setLayers([lyr])

            showLayerPropertiesDialog(lyr,
                                      canvas=canvas,
                                      messageBar=self.messageBar(),
                                      useQGISDialog=False, modal=True)

    def showSettingsDialog(self):
        from qgis.utils import iface
        d = iface.showOptionsDialog(currentPage=EOTSVSettingsWidgetFactory.defaultObjectName)
        if isinstance(d, QDialog):
            d.exec_()

    def applySettings(self):
        """
        Reads the EOTSVSettings object and applies its values to related widgets
        """

        # the default values
        settings = EOTSVSettingsManager.settings()
        self.mTimeSeries.setDateTimePrecision(settings.dateTimePrecision)
        self.mTimeSeries.setSensorMatching(settings.sensorMatching)

        sensorSpecs = settings.sensorSpecifications
        sensors = dict()
        for s in self.sensors():
            sensors[s.id()] = s

        for sid, specs in sensorSpecs.items():
            assert isinstance(sid, str)
            assert isinstance(specs, dict)
            sensor = sensors.get(sid)
            if isinstance(sensor, SensorInstrument):
                if 'name' in specs.keys():
                    sensor.setName(specs['name'])

        if settings.mapUpdateInterval > 0:
            self.ui.mMapWidget.mMapRefreshTimer.start(settings.mapUpdateInterval)

    # def processingToolbox(self) -> processing.gui.ProcessingToolbox.ProcessingToolbox:
    #    return self.ui.dockProcessingToolbox

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
            self.ui.mActionSelectFeatures.setChecked(True)
        else:
            self.ui.mActionSelectFeatures.setChecked(False)

        self.ui.mMapWidget.setMapTool(mapToolKey, *args)
        kwds = {}

    def setMapsPerMapView(self, cols: int, rows: int):
        """
        Sets the number of map canvases that is shown per map view
        :param n: int
        """
        self.mapWidget().setMapsPerMapView(cols, rows)

    def setMapSize(self, size: QSize):
        """
        Sets the MapCanvas size.
        :param size: QSize
        """
        self.mapWidget().setMapSize(size)

    def setCrs(self, crs: QgsCoordinateReferenceSystem):
        self.mapWidget().setCrs(crs)

    def setSpatialExtent(self, *args):
        """
        Sets the map canvas extent
        :param spatialExtent: SpatialExtent
        """
        debugLog()
        self.mapWidget().setSpatialExtent(*args)

    def setSpatialCenter(self, *args):
        """
        Sets the center of map canvases
        :param spatialPoint: SpatialPoint
        """
        self.mapWidget().setSpatialCenter(*args)

    def spatialExtent(self) -> SpatialExtent:
        """
        Returns the map extent
        :return: SpatialExtent
        """
        return self.mapWidget().spatialExtent()

    def spatialCenter(self) -> SpatialPoint:
        """
        Returns the map center
        :return: SpatialPoint
        """
        return self.mapWidget().spatialCenter()

    def setCurrentLocation(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas = None):
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
            self.sigCurrentLocationChanged[QgsCoordinateReferenceSystem, QgsPointXY, QgsMapCanvas].emit(
                self.mCurrentMapLocation.crs(), self.mCurrentMapLocation, mapCanvas)

            if bCLV:
                self.loadCursorLocationValueInfo(spatialPoint, mapCanvas)

            if bCenter:
                mapCanvas.setCenter(spatialPoint.toCrs(mapCanvas.mapSettings().destinationCrs()))

            if bSP:
                self.loadCurrentSpectralProfile(spatialPoint, mapCanvas)

        if bTP:
            self.loadCurrentTemporalProfile(spatialPoint)

        self.sigCurrentLocationChanged[QgsCoordinateReferenceSystem, QgsPointXY].emit(
            self.mCurrentMapLocation.crs(),
            self.mCurrentMapLocation)

    @pyqtSlot(SpatialPoint, QgsMapCanvas)
    def loadCursorLocationValueInfo(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas):
        self.ui.dockCursorLocation.loadCursorLocation(spatialPoint, mapCanvas)

    @pyqtSlot(SpatialPoint, QgsMapCanvas)
    def loadCurrentSpectralProfile(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        """
        Loads SpectralProfiles from a location defined by `spatialPoint`
        :param spatialPoint: SpatialPoint
        :param mapCanvas: QgsMapCanvas
        """
        assert self.mCurrentMapSpectraLoading in ['TOP', 'ALL']
        assert isinstance(spatialPoint, SpatialPoint)
        from .mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        tsd: TimeSeriesDate = mapCanvas.tsd()

        sensorLayers = [lyr for lyr in mapCanvas.layers() if has_sensor_id(lyr)]

        profilesAndContext = []

        for lyr in sensorLayers:

            source = StandardLayerProfileSource(lyr)
            results = source.collectProfiles(spatialPoint, kernel_size=QSize(1, 1), snap=False)

            if len(results) > 0:
                profilesAndContext.extend(results)

            if self.mCurrentMapSpectraLoading == 'TOP':
                break

        if len(profilesAndContext) > 0:
            self.setCurrentSpectralProfiles(profilesAndContext)

        return profilesAndContext

    def setCurrentSpectralProfiles(self, spectra: List[Tuple[Dict, QgsExpressionContext]]):

        widgets: List[SpectralLibraryWidget] = self.spectralLibraryWidgets()
        if len(widgets) == 0:
            self.createSpectralLibrary()
            widgets = self.spectralLibraryWidgets()

        style = EOTSVSettingsManager.settings().profileStyleCurrent

        for w in widgets:

            sl: QgsVectorLayer = w.speclib()

            pfields = profile_field_list(sl)
            if len(pfields) > 0:

                currentStyles = dict()
                new_features: List[QgsFeature] = []
                pfield: QgsField = pfields[0]
                fid = 0
                g: QgsGeometry = None
                for (profileDict, context) in spectra:
                    fid += 1

                    feature = QgsFeature(sl.fields())
                    feature.setId(fid)

                    # set spectral profile values
                    dump = encodeProfileValueDict(profileDict, encoding=pfield)
                    feature.setAttribute(pfield.name(), dump)

                    if g is None and context.hasGeometry():
                        # use the geometry related to the origin of the 1. profile field as
                        # feature geometry
                        _g = QgsGeometry(context.geometry())
                        crs = context.variable('_source_crs')
                        if sl.crs().isValid() and isinstance(crs, QgsCoordinateReferenceSystem) and crs.isValid():
                            trans = QgsCoordinateTransform()
                            trans.setSourceCrs(crs)
                            trans.setDestinationCrs(sl.crs())
                            if _g.transform(trans) == Qgis.GeometryOperationResult.Success:
                                g = _g

                        del crs
                    if isinstance(g, QgsGeometry):
                        feature.setGeometry(QgsGeometry(g))

                    varnames = [n for n in sl.fields().names() if n in n in context.variableNames()]
                    for n in varnames:
                        vfield: QgsField = sl.fields()[n]

                        try:
                            newValue = vfield.convertCompatible(context.variable(n))
                            feature.setAttribute(n, newValue)
                        except ValueError as ex:
                            print(ex, file=sys.stderr)
                    new_features.append(feature)
                    currentStyles[(fid, pfield.name())] = style

                w.setCurrentProfiles(new_features, make_permanent=False, currentProfileStyles=currentStyles)

    @pyqtSlot(SpatialPoint)
    def loadCurrentTemporalProfile(self, spatialPoint: SpatialPoint):
        if not self.mTemporalProfileLayerInitialized:
            self.initTemporalProfileLayer()

        layer = fieldname = None
        tp_layer = self.currentLayer()
        if TemporalProfileUtils.isProfileLayer(tp_layer):
            for field in TemporalProfileUtils.profileFields(tp_layer):
                fieldname = field.name()
                layer = tp_layer
                break
            self.profileDock.loadTemporalProfile(spatialPoint, layer=layer, field=fieldname)

    def initTemporalProfileLayer(self):
        """
        Create a new temporal profile layer, just in case none exists.
        """
        has_tl_lyr = False
        for lid, lyr in self.mapLayerStore().mapLayers().items():
            if TemporalProfileUtils.isProfileLayer(lyr):
                has_tl_lyr = True
                break
        if not has_tl_lyr:
            lyr = self.createTemporalProfileLayer(skip_dialog=True)
            if isinstance(lyr, QgsVectorLayer):
                lyr.setName('Temporal Profiles')
                with edit(lyr):
                    lyr.addAttribute(QgsField('notes', QMETATYPE_QSTRING))
                self.addMapLayers([lyr])
                self.mTemporalProfileLayerInitialized = True
        else:
            self.mTemporalProfileLayerInitialized = True

    def onShowProfile(self, spatialPoint, mapCanvas, mapToolKey):

        assert mapToolKey in MapTools.mapToolValues()

        if mapToolKey == MapTools.TemporalProfile:

            self.profileDock.loadTemporalProfile(spatialPoint)

        elif mapToolKey == MapTools.SpectralProfile:
            tsd = None
            from .mapcanvas import MapCanvas
            if isinstance(mapCanvas, MapCanvas):
                tsd = mapCanvas.tsd()

            if not hasattr(self, 'cntSpectralProfile'):
                self.cntSpectralProfile = 0

            profiles = [SpectralLibraryUtils.readProfileDict(lyr, spatialPoint)
                        for lyr in mapCanvas.layers() if isinstance(lyr, QgsRasterLayer)]

            # add metadata
            if isinstance(tsd, TimeSeriesDate):
                profiles2 = []
                sl = self.spectralLibrary()
                if is_spectral_library(sl):
                    for p in profiles:
                        self.cntSpectralProfile += 1
                        assert isinstance(p, QgsFeature)
                        p2 = p.copyFieldSubset(fields=sl.fields())
                        p2.setName('Profile {} {}'.format(self.cntSpectralProfile, tsd.mDTR))
                        p2.setAttribute('date', '{}'.format(tsd.mDTR))
                        p2.setAttribute('doy', int(tsd.mDOY))
                        p2.setAttribute('sensor', tsd.mSensor.name())
                        profiles2.append(p2)
                    self.ui.dockSpectralLibrary.SLW.setCurrentSpectralProfiles(profiles2)

        elif mapToolKey == MapTools.CursorLocation:

            self.ui.dockCursorLocation.loadCursorLocation(spatialPoint, mapCanvas)

        else:
            s = ""
        pass

    def messageBar(self) -> QgsMessageBar:
        """
        Returns the QgsMessageBar that is used to show messages in the TimeSeriesViewer UI.
        :return: QgsMessageBar
        """
        return self.ui.mMapWidget.messageBar()

    def loadTimeSeriesDefinition(self,
                                 files: List[Union[str, pathlib.Path]] = None,
                                 n_max: int = None,
                                 runAsync=True):
        """
        Loads a time series definition file
        :param files:
        :param n_max:
        :return:
        """
        if isinstance(files, bool):
            files = None

        if isinstance(files, (str, pathlib.Path)):
            files = [files]
        s = settings.settings()
        if files is None:

            defFile = s.value('file_ts_definition')
            defDir = None
            if defFile is not None:
                defDir = os.path.dirname(defFile)

            filters = "CSV (*.csv *.txt);;" + \
                      "All files (*.*)"

            files, filter = QFileDialog.getOpenFileNames(caption='Load Time Series definition', directory=defDir,
                                                         filter=filters)

        if isinstance(files, list):
            # self.clearTimeSeries()
            for file in sorted(files):
                s.setValue('file_ts_definition', file)
                self.mTimeSeries.loadFromFile(file, n_max=n_max, runAsync=runAsync)

    def currentMapCanvas(self) -> MapCanvas:
        return self.mapWidget().currentMapCanvas()

    def currentLayer(self) -> QgsMapLayer:
        """
        Returns the current layer of the active (last clicked) map view
        :return: QgsMapLayer
        """
        return self.mapWidget().currentLayer()

    def createMapView(self, *args, **kwds) -> MapView:
        """
        Creates a new MapView.
        :return: MapView
        """
        return self.mapWidget().createMapView(*args, **kwds)

    def mapViews(self) -> List[MapView]:
        """
        Returns all MapViews
        :return: [list-of-MapViews]
        """
        return self.mapWidget().mapViews()

    def icon(self) -> QIcon:
        """
        Returns the EO Time Series Viewer icon
        :return: QIcon
        """
        import eotimeseriesviewer
        return eotimeseriesviewer.icon()

    def temporalProfileDock(self) -> TemporalProfileDock:
        return self.profileDock

    def temporalProfiles(self) -> list:
        """
        Returns collected temporal profiles
        :return: [list-of-TemporalProfiles]
        """
        return self.profileDock.temporalProfileLayer()[:]

    def logMessage(self, message: str, tag: str, level):
        """

        """
        if level == Qgis.Critical:
            duration = 200
        else:
            duration = 50
        if tag == LOG_MESSAGE_TAG and level in [Qgis.Critical, Qgis.Warning]:
            lines = message.splitlines()
            self.messageBar().pushMessage(tag, lines[0], message, level, duration)

    def onSensorAdded(self, sensor: SensorInstrument):
        sensor.sigNameChanged.connect(lambda *args, s=sensor: self.onSensorNameChanged(sensor))

        knownName = EOTSVSettingsManager.sensorName(sensor)
        if isinstance(knownName, str) and len(knownName) > 0:
            sensor.setName(knownName)
        else:
            self.onSensorNameChanged(sensor)  # save the sensor name to the settings

    def onSensorNameChanged(self, sensor: SensorInstrument):
        # save changed names to settings

        if sensor in self.sensors():
            EOTSVSettingsManager.saveSensorName(sensor)

    def onTimeSeriesChanged(self, *args):
        if not self.mSpatialMapExtentInitialized:
            if len(self.mTimeSeries) > 0:
                extent = self.timeSeries().maxSpatialExtent()
                if isinstance(extent, SpatialExtent):
                    debugLog('Extent changed')
                    self.mapWidget().setCrs(extent.crs())
                    self.mapWidget().setSpatialExtent(extent)
                    self.mSpatialMapExtentInitialized = True
                else:
                    self.mSpatialMapExtentInitialized = False
                    print('Failed to calculate max. spatial extent of TimeSeries with length {}'.format(
                        len(self.timeSeries())))
                lastDate = self.ui.mMapWidget.currentDate()
                if lastDate:
                    tsd = self.timeSeries().findDate(lastDate)
                else:
                    tsd = self.timeSeries()[0]
                self.setCurrentDate(tsd)

                if len(self.mapViews()) == 0:
                    self.createMapView()

        self.mSpatialMapExtentInitialized = len(self.mTimeSeries) > 0

    def mapWidget(self) -> MapWidget:
        """
        Returns the MapWidget that contains all map canvases.
        :return: MapWidget
        """
        return self.ui.mMapWidget

    def saveTimeSeriesDefinition(self):
        s = settings.settings()
        defFile = s.value('FILE_TS_DEFINITION')
        if defFile is not None:
            defFile = os.path.dirname(defFile)

        filters = "CSV (*.csv *.txt);;" + \
                  "All files (*.*)"
        path, filter = QFileDialog.getSaveFileName(caption='Save Time Series definition', filter=filters,
                                                   directory=defFile)
        if path not in [None, '']:
            path = self.mTimeSeries.saveToFile(path)
            s.setValue('FILE_TS_DEFINITION', path)

    def loadFORCEProducts(self):

        settings = EOTSVSettingsManager.settings()

        d = FORCEProductImportDialog(parent=self.ui)
        if force_root := settings.forceRootDir:
            d.setRootFolder(force_root)
        if force_product := settings.forceProduct:
            d.setProductType(force_product)

        if d.exec_() == QDialog.Accepted:
            settings = EOTSVSettingsManager.settings()

            settings.forceRootDir = Path(d.rootFolder())
            settings.forceProduct = d.productType()
            EOTSVSettingsManager.saveSettings(settings)

            search_results = d.files()
            if not isinstance(search_results, list):
                task = FindFORCEProductsTask(d.productType(), d.rootFolder())

                def onCompleted(t: FindFORCEProductsTask):
                    files = t.files()
                    self.addTimeSeriesImages(files)
                    s = ""

                task.taskCompleted.connect(lambda *args, t=task: onCompleted(task))
                self.taskManager().addTask(task)
            else:
                self.addTimeSeriesImages(search_results)

    def loadTimeSeriesStack(self):

        from eotimeseriesviewer.stackedbandinput import StackedBandInputDialog

        d = StackedBandInputDialog(parent=self.ui)
        if d.exec_() == QDialog.Accepted:
            writtenFiles = d.saveImages()
            self.addTimeSeriesImages(writtenFiles)

    def loadExampleTimeSeries(self,
                              n: int = None,
                              loadAsync: bool = True,
                              filter_raster: Union[str, Pattern, Match] = re.compile(r'.*\.tif$'),
                              filter_vector: Union[str, Pattern, Match] = re.compile(r'.*\.(gpkg|shp)$')):
        """
        Loads an example time series
        :param filter_vector:
        :param filter_raster:
        :param loadAsync: object
        :param n: int, max. number of images to load. Useful for developer test-cases
        """

        import example.Images
        exampleDataDir = pathlib.Path(example.Images.__file__).parent
        rasterFiles = sorted(list(file_search(exampleDataDir, filter_raster, recursive=True)))
        vectorFiles = sorted(list(file_search(exampleDataDir.parent, filter_vector, recursive=True)))

        if isinstance(n, bool) or not isinstance(n, int):
            n = len(rasterFiles)

        # ensure valid inputs for n
        n = min(n, len(rasterFiles))
        n = max(1, n)

        self.addTimeSeriesImages(rasterFiles[0:n], loadAsync=loadAsync)

        if len(vectorFiles) > 0:

            # make polygons transparent

            added_vector_layers = self.addVectorData(vectorFiles)

            for lyr in added_vector_layers:
                if isinstance(lyr, QgsVectorLayer):
                    renderer = lyr.renderer()
                    if lyr.geometryType() == QgsWkbTypes.PolygonGeometry and isinstance(renderer,
                                                                                        QgsSingleSymbolRenderer):
                        renderer = renderer.clone()
                        symbol = renderer.symbol()
                        if isinstance(symbol, QgsFillSymbol):
                            symbol.setOpacity(0.25)
                        lyr.setRenderer(renderer)
                    s = ""
        if not loadAsync:
            self.mapWidget().timedRefresh()

    def timeSeries(self) -> TimeSeries:
        """
        Returns the TimeSeries instance.
        :return: TimeSeries
        """
        return self.mTimeSeries

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

    def flashFeatures(self, layer: QgsVectorLayer, featuresIDs: List[int]):

        for c in self.mapCanvases():
            c.flashFeatureIds(layer, featuresIDs)

    def focusTimeSeriesDateVisibility(self, *args, extent: SpatialExtent = None, date: TimeSeriesDate = None):
        """
        Adjusts the visibility of TimeSeriesDates to the presence of data in a spatial extent.
        :param args:
        :type args:
        :param extent:
        :type extent:
        :param date:
        :type date:
        :return:
        :rtype:
        """

        if extent is None:
            extent = self.mapWidget().spatialExtent()

        if date is None:
            date = self.mapWidget().currentDate()

        self.timeSeries().focusVisibility(extent, date_of_interest=date)

    def updateCurrentLayerActions(self, *args):
        """
        Enables/disables actions and buttons that relate to the current layer and its current state
        """

        layer = self.currentLayer()
        debugLog('updateCurrentLayerActions: {}'.format(str(layer)))
        isVector = isinstance(layer, QgsVectorLayer)
        hasSelectedFeatures = False
        for mv in self.mapViews():
            for l in mv.layers():
                if isinstance(l, QgsVectorLayer) and l.selectedFeatureCount() > 0:
                    hasSelectedFeatures = True
                    break
        isVector and layer.selectedFeatureCount() > 0

        self.ui.mActionDeselectFeatures.setEnabled(hasSelectedFeatures)
        self.ui.mActionSelectFeatures.setEnabled(isVector)

        self.ui.mActionToggleEditing.setEnabled(isVector)
        self.ui.mActionToggleEditing.setChecked(isVector and layer.isEditable())

        self.ui.mActionAddFeature.setEnabled(isVector and layer.isEditable())

        if isVector:
            if layer.geometryType() == QgsWkbTypes.PointGeometry:
                icon = QIcon(':/images/themes/default/mActionCapturePoint.svg')
            elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                icon = QIcon(':/images/themes/default/mActionCaptureLine.svg')
            elif layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                icon = QIcon(':/images/themes/default/mActionCapturePolygon.svg')
            else:
                icon = QIcon(':/images/themes/default/mActionCapturePolygon.svg')
            self.ui.mActionAddFeature.setIcon(icon)

        self.ui.mActionSaveEdits.setEnabled(isVector and layer.isEditable())

        if isinstance(layer, (QgsRasterLayer, QgsVectorLayer)):
            self.currentLayerChanged.emit(layer)

    def vectorLayerTools(self) -> EOTSVVectorLayerTools:
        return self.mVectorLayerTools

    def show(self):
        self.ui.show()

    def showAttributeTable(self, lyr: QgsVectorLayer, filterExpression: str = "") -> QgsDockWidget:
        assert isinstance(lyr, QgsVectorLayer)

        # 1. check if this layer is already opened as dock widget
        docks: List[QgsDockWidget] = self.ui.findChildren(QgsDockWidget)
        vectorLayerDocks: List[QgsDockWidget] = [d for d in docks if
                                                 isinstance(d, (LabelDockWidget, SpectralLibraryDockWidget))]

        for d in vectorLayerDocks:
            if isinstance(d, LabelDockWidget) and d.vectorLayer().id() == lyr.id() or \
                    isinstance(d, SpectralLibraryDockWidget) and d.speclib().id() == lyr.id():
                d.show()
                d.activateWindow()
                d.raise_()
                return

        # 2. create dock widget

        if is_spectral_library(lyr):
            dock = SpectralLibraryDockWidget(speclib=lyr)
            dock.setObjectName(f'SpectralLibraryDockWidget{id(dock)}')
            dock.setVectorLayerTools(self.vectorLayerTools())
            dock.SLW.actionSelectProfilesFromMap.setVisible(True)
            dock.SLW.sigLoadFromMapRequest.connect(lambda *args: self.setMapTool(MapTools.SpectralProfile))
            # dock.SLW.actionSelectProfilesFromMap.triggered.connect(self.activateIdentifySpectralProfileMapTool)
        else:
            dock = LabelDockWidget(lyr)
            dock.mLabelWidget.sigMoveTo[QDateTime].connect(self.setCurrentDate)
            dock.mLabelWidget.sigMoveTo[QDateTime, object].connect(self.moveTo)
            dock.setObjectName(f'LabelDockWidget{id(dock)}')
            dock.setVectorLayerTools(self.vectorLayerTools())

        self.ui.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.ui.menuPanels.addAction(dock.toggleViewAction())
        self.ui.tabifyDockWidget(self.ui.dockProfiles, dock)
        dock.activateWindow()
        QTimer.singleShot(10, lambda d=dock: d.raise_())
        return dock

    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                # if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def addMapLayers(self, layers: List[QgsMapLayer]) -> List[QgsMapLayer]:
        """
        Adds QgsMapLayers
        :param layers:
        :return:
        """
        if isinstance(layers, QgsMapLayer):
            layers = [layers]

        layers = [lyr for lyr in layers if not has_sensor_id(lyr)]
        if len(layers) > 0:
            self.mapLayerStore().addMapLayers(layers)
            for mapView in self.mapViews():
                assert isinstance(mapView, MapView)
                for lyr in layers:
                    mapView.addLayer(lyr)

                break  # add to first mapview only

        return layers

    def createTemporalProfileLayer(self, skip_dialog: bool = False) -> Optional[QgsVectorLayer]:
        """
        Create a new temporal profile layer
        :return:
        """

        from eotimeseriesviewer.processingalgorithms import CreateEmptyTemporalProfileLayer

        alg = CreateEmptyTemporalProfileLayer()
        conf = {}
        alg.initAlgorithm(conf)

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)
        context.setProject(self.mapLayerStore())

        layer = None

        if skip_dialog:
            param = {}
            results, success = alg.run(param, context, context.feedback())
            if success:
                layer = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
                s = ""
        else:
            d = AlgorithmDialog(alg)
            d.context = context

            def onExecuted(success, results):
                nonlocal layer
                if success and alg.OUTPUT in results:
                    layer = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], d.processingContext())
                    s = ""
                d.close()

            d.algorithmFinished.connect(onExecuted)
            d.exec_()

        if isinstance(layer, QgsVectorLayer) and TemporalProfileUtils.isProfileLayer(layer):
            self.addMapLayers([layer])
            return layer
        return None

    def createSpectralLibrary(self) -> SpectralLibraryWidget:
        """
        Create a spectral library
        """

        speclib: QgsVectorLayer = SpectralLibraryUtils.createSpectralLibrary()
        speclib.startEditing()
        for field in SPECTRA_PROFILE_FIELDS:
            speclib.addAttribute(field)
        assert speclib.commitChanges()
        # QgsProject.instance().addMapLayer(speclib)
        self.mapLayerStore().addMapLayer(speclib)
        self.showAttributeTable(speclib)
        self.addMapLayers(speclib)

    def addVectorData(self, files=None) -> List[QgsVectorLayer]:
        """
        Adds vector data
        :param files: vector layer sources
        :return: [list-of-QgsVectorLayers]
        """
        vectorLayers = []
        if files is None:
            s = settings.settings()
            defDir = s.value('DIR_FILESEARCH')
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

            if len(files) > 0 and os.path.exists(files[0]):
                dn = os.path.dirname(files[0])
                s.setValue('DIR_FILESEARCH', dn)

        if not isinstance(files, list):
            files = [files]
        if files:

            for f in files:
                vectorLayers.extend(subLayers(f))

            if len(vectorLayers) > 0:
                self.addMapLayers(vectorLayers)

        return vectorLayers

    def addTimeSeriesImages(self, image_sources: list, loadAsync: bool = True):
        """
        Adds images to the time series
        :param image_sources:
        """
        if image_sources is None:
            s = settings.settings()
            defDir = s.value('dir_datasources')

            filters = QgsProviderRegistry.instance().fileRasterFilters()

            image_sources, filter = QFileDialog.getOpenFileNames(
                directory=defDir,
                filter=filters,
                parent=self.ui,
                # options=QFileDialog.DontUseNativeDialog #none-native is too slow
            )

            if len(image_sources) > 0 and os.path.exists(image_sources[0]):
                dn = os.path.dirname(image_sources[0])
                s.setValue('dir_datasources', dn)

        if image_sources:
            self.mTimeSeries.addSources(image_sources, runAsync=loadAsync)

    def clearTimeSeries(self):

        self.mTimeSeries.beginResetModel()
        self.mTimeSeries.clear()
        self.mTimeSeries.endResetModel()


class SaveAllMapsDialog(QDialog):

    def __init__(self, parent=None):
        super(SaveAllMapsDialog, self).__init__(parent)
        loadUi(DIR_UI / 'saveallmapsdialog.ui', self)
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

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(lambda: self.setResult(QDialog.Accepted))
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(lambda: self.setResult(QDialog.Rejected))
        self.validate()

    def validate(self, *args):
        b = os.path.isdir(self.directory())
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(b)

    def setDirectory(self, path: str):
        assert os.path.isdir(path)
        self.fileWidget.setFilePath(path)

    def directory(self) -> str:
        """
        Returns the selected directory
        :return: str
        """
        return self.fileWidget.filePath()

    def fileType(self) -> str:
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
