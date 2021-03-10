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
import sys
import os
import re
import typing
import pathlib
import numpy as np
from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot, QObject, QFile, Qt, QSize, QCoreApplication, \
    QVariant, QDate, QDateTime, QTimer
from qgis.PyQt.QtGui import QCloseEvent, QColor, QIcon
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QMainWindow, \
    QToolButton, QAction, QLabel, QProgressBar, QApplication, QSizePolicy, \
    QMenu, QDialogButtonBox, QProgressDialog, QToolBar, QComboBox, QDialog, QFileDialog, QDockWidget
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsMessageOutput, QgsCoordinateReferenceSystem, \
    Qgis, QgsWkbTypes, QgsTask, QgsProviderRegistry, QgsMapLayerStore, QgsFeature, QgsField, \
    QgsTextFormat, QgsProject, QgsSingleSymbolRenderer, QgsGeometry, QgsApplication, QgsFillSymbol, \
    QgsProjectArchive, QgsZipUtils, QgsPointXY, QgsFields

from qgis.gui import QgsMapCanvas, QgsStatusBar, QgsFileWidget, \
    QgsMessageBar, QgsMessageViewer, QgsDockWidget, QgsTaskManagerWidget, QgisInterface
import qgis.utils
from eotimeseriesviewer import LOG_MESSAGE_TAG, DIR_UI, settings
from eotimeseriesviewer.utils import SpatialPoint, SpatialExtent, datetime64, fixMenuButtons, file_search, loadUi
from eotimeseriesviewer.timeseries import TimeSeries, TimeSeriesSource, TimeSeriesDate, TimeSeriesTreeView, \
    DateTimePrecision, SensorInstrument, SensorProxyLayer, SensorMatching, TimeSeriesFindOverlapTask, \
    TimeSeriesDock, TimeSeriesWidget
from eotimeseriesviewer.settings import Keys as SettingKeys, value as SettingValue
from eotimeseriesviewer.settings import defaultValues, setValue
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.docks import LabelDockWidget, SpectralLibraryDockWidget
from eotimeseriesviewer.profilevisualization import ProfileViewDock
from eotimeseriesviewer.temporalprofiles import TemporalProfileLayer
from eotimeseriesviewer.mapvisualization import MapView, MapWidget
from eotimeseriesviewer.vectorlayertools import EOTSVVectorLayerTools
import eotimeseriesviewer.settings as eotsvSettings
from .externals.qps.speclib.core import SpectralProfile, SpectralLibrary
from .externals.qps.speclib.gui import SpectralLibraryPanel, SpectralLibraryWidget
from .externals.qps.cursorlocationvalue import CursorLocationInfoModel, CursorLocationInfoDock
from .externals.qps.vectorlayertools import VectorLayerTools
from .externals.qps.maptools import MapTools
import eotimeseriesviewer.labeling
from eotimeseriesviewer import debugLog

DEBUG = False

SPECTRA_PROFILE_FIELDS = SpectralProfile().fields()
SPECTRA_PROFILE_FIELDS.append(QgsField('date', QVariant.Date, 'date'))
SPECTRA_PROFILE_FIELDS.append(QgsField('doy', QVariant.Int, 'int'))
SPECTRA_PROFILE_FIELDS.append(QgsField('sensor', QVariant.String, 'varchar'))


class AboutDialogUI(QDialog):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialogUI, self).__init__(parent)
        loadUi(DIR_UI / 'aboutdialog.ui', self)
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
        self.tbChanges.setHtml(readTextFile(PATH_CHANGELOG))
        self.tbLicense.setHtml(readTextFile(PATH_LICENSE))

    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)


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
        self.dockMapViews = self.addDockWidget(area, MapViewDock(self))

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

        from eotimeseriesviewer.profilevisualization import ProfileViewDock
        self.dockProfiles = self.addDockWidget(area, ProfileViewDock(self))

        area = Qt.LeftDockWidgetArea
        # self.dockAdvancedDigitizingDockWidget = self.addDockWidget(area,
        #   QgsAdvancedDigitizingDockWidget(self.dockLabeling.labelingWidget().canvas(), self))
        # self.dockAdvancedDigitizingDockWidget.setVisible(False)

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

        self.tabifyDockWidget(self.dockTaskManager, self.dockCursorLocation)
        self.tabifyDockWidget(self.dockTaskManager, self.dockSystemInfo)
        self.tabifyDockWidget(self.dockTaskManager, self.dockSensors)

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

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.mManager = QgsApplication.taskManager()
        self.setAutoRaise(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setLayout(QHBoxLayout())

        from eotimeseriesviewer.temporalprofiles import TemporalProfileLoaderTask
        from eotimeseriesviewer.timeseries import TimeSeriesLoadingTask, TimeSeriesFindOverlapTask

        self.mTrackedTasks = [
            TemporalProfileLoaderTask,
            TimeSeriesFindOverlapTask,
            TimeSeriesLoadingTask
        ]

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
        from eotimeseriesviewer.temporalprofiles import TemporalProfileLoaderTask
        from eotimeseriesviewer.timeseries import TimeSeriesLoadingTask

        if isinstance(task, (TemporalProfileLoaderTask, TimeSeriesFindOverlapTask, TimeSeriesLoadingTask)):
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

    def activeTasks(self) -> typing.List[QgsTask]:
        results = []
        for t in self.mManager.tasks():
            if isinstance(t, QgsTask):
                for taskType in self.mTrackedTasks:
                    if isinstance(t, taskType):
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
    _instance = None

    @staticmethod
    def instance():
        """
        Returns the TimeSeriesViewer instance
        :return:
        """
        return EOTimeSeriesViewer._instance

    sigCurrentDateChanged = pyqtSignal(TimeSeriesDate)
    sigCurrentLocationChanged = pyqtSignal([QgsCoordinateReferenceSystem, QgsPointXY],
                                           [QgsCoordinateReferenceSystem, QgsPointXY, QgsMapCanvas])

    sigCurrentSpectralProfilesChanged = pyqtSignal(list)
    sigCurrentTemporalProfilesChanged = pyqtSignal(list)
    currentLayerChanged = pyqtSignal(QgsMapLayer)

    def __init__(self):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        QObject.__init__(self)
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

        self.mTaskManagerButton = TaskManagerStatusButton(self.mStatusBar)
        self.mTaskManagerButton.setFont(statusBarFont)
        self.mStatusBar.addPermanentWidget(self.mTaskManagerButton, 10, QgsStatusBar.AnchorLeft)
        self.mTaskManagerButton.clicked.connect(lambda *args: self.ui.dockTaskManager.raise_())
        self.mMapLayerStore = self.mapWidget().mMapLayerStore

        import eotimeseriesviewer.utils
        eotimeseriesviewer.utils.MAP_LAYER_STORES.insert(0, self.mapLayerStore())
        from eotimeseriesviewer.timeseries import TimeSeriesDock
        from eotimeseriesviewer.mapvisualization import MapViewDock, MapWidget

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
        # Save reference to the QGIS interface

        # init empty time series
        self.mTimeSeries = TimeSeries()
        self.mTimeSeries.setDateTimePrecision(DateTimePrecision.Day)
        self.mSpatialMapExtentInitialized = False
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesChanged)
        self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self.onTimeSeriesChanged)
        self.mTimeSeries.sigSensorAdded.connect(self.onSensorAdded)

        # self.mTimeSeries.sigMessage.connect(self.setM)

        tswidget.setTimeSeries(self.mTimeSeries)
        self.ui.dockSensors.setTimeSeries(self.mTimeSeries)
        self.ui.dockProfiles.setTimeSeries(self.mTimeSeries)
        self.ui.dockProfiles.setVectorLayerTools(self.mVectorLayerTools)
        mw.setTimeSeries(self.mTimeSeries)
        mvd.setTimeSeries(self.mTimeSeries)
        mvd.setMapWidget(mw)

        self.profileDock: ProfileViewDock = self.ui.dockProfiles
        assert isinstance(self, EOTimeSeriesViewer)
        self.profileDock.sigMoveToDate.connect(self.setCurrentDate)

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
        self.ui.actionAddMapView.triggered.connect(mvd.createMapView)
        self.ui.actionAddTSD.triggered.connect(lambda: self.addTimeSeriesImages(None))
        self.ui.actionAddVectorData.triggered.connect(lambda: self.addVectorData())
        self.ui.actionCreateSpectralLibrary.triggered.connect(self.onCreateSpectralLibrary)
        self.ui.actionAddSubDatasets.triggered.connect(self.openAddSubdatasetsDialog)

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
        # self.ui.actionShowCrosshair.toggled.connect(mw.setCrosshairVisibility)
        self.ui.actionExportMapsToImages.triggered.connect(lambda: self.exportMapsToImages())

        self.ui.mActionLayerProperties.triggered.connect(self.onShowLayerProperties)

        from qgis.utils import iface
        self.ui.actionLoadProject.triggered.connect(iface.actionOpenProject().trigger)
        self.ui.actionReloadProject.triggered.connect(self.onReloadProject)
        self.ui.actionSaveProject.triggered.connect(iface.actionSaveProject().trigger)

        self.profileDock.actionLoadProfileRequest.triggered.connect(self.activateIdentifyTemporalProfileMapTool)

        # connect buttons with actions
        self.ui.actionAbout.triggered.connect(lambda: AboutDialogUI(self.ui).exec_())

        self.ui.actionSettings.triggered.connect(self.onShowSettingsDialog)
        import webbrowser
        from eotimeseriesviewer import DOCUMENTATION, SpectralLibrary, SpectralLibraryPanel, SpectralLibraryWidget
        self.ui.actionShowOnlineHelp.triggered.connect(lambda: webbrowser.open(DOCUMENTATION))

        # SLW: SpectralLibraryWidget = self.ui.dockSpectralLibrary.spectralLibraryWidget()
        # assert isinstance(SLW, SpectralLibraryWidget)
        # SLW.setVectorLayerTools(self.mVectorLayerTools)
        # add time-specific fields
        # sl = self.spectralLibrary()

        # self.mMapLayerStore.addMapLayer(sl)

        temporalProfileLayer = self.profileDock.temporalProfileLayer()
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

        QgsProject.instance().writeProject.connect(self.onWriteProject)
        QgsProject.instance().readProject.connect(self.onReadProject)

        if eotsvSettings.value(SettingKeys.StartupRestoreProjectSettings, False):
            self.onReloadProject()

    def onClose(self):
        debugLog(f'Close EOTSV')
        EOTimeSeriesViewer._instance = None
        self.mapWidget().onClose()

    def onWriteProject(self, dom: QDomDocument):

        node = dom.createElement('EOTSV')
        root = dom.documentElement()

        # save time series
        self.timeSeries().writeXml(node, dom)

        # save map views
        self.mapWidget().writeXml(node, dom)
        root.appendChild(node)

    def onReloadProject(self, *args):

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
        ids = []
        for l in layers:
            if isinstance(l, QgsMapLayer):
                ids.append(l.id())
            elif isinstance(l, str):
                ids.append(l)

        to_remove = []
        for d in self.ui.findChildren(SpectralLibraryDockWidget):
            assert isinstance(d, SpectralLibraryDockWidget)
            if d.speclib().id() in ids:
                to_remove.append(d)

        for d in self.ui.findChildren(LabelDockWidget):
            assert isinstance(d, LabelDockWidget)
            if d.vectorLayer().id() in ids:
                to_remove.append(d)

        for d in to_remove:
            self.ui.removeDockWidget(d)

    def onReadProject(self, doc: QDomDocument) -> bool:
        """
        Reads images and visualization settings from a QgsProject QDomDocument
        :param doc: QDomDocument
        :return: bool
        """
        if not isinstance(doc, QDomDocument):
            return False

        root = doc.documentElement()
        node = root.firstChildElement('EOTSV')
        if node.nodeName() == 'EOTSV':
            self.timeSeries().clear()

            mapviews = self.mapViews()
            for mv in mapviews:
                self.mapWidget().removeMapView(mv)

            self.mapWidget().readXml(node)

            mwNode = node.firstChildElement('MapWidget')
            if mwNode.nodeName() == 'MapWidget' and mwNode.hasAttribute('mapDate'):
                dt64 = datetime64(mwNode.attribute('mapDate'))
                if isinstance(dt64, np.datetime64):
                    self.mPostDataLoadingArgs['mapDate'] = dt64

            self.timeSeries().sigLoadingTaskFinished.connect(self.onPostDataLoading)
            self.timeSeries().readXml(node)

        return True

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

    def sensors(self) -> typing.List[SensorInstrument]:
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

    def exportMapsToImages(self, path=None, format='PNG'):
        """
        Exports the map canvases to local images.
        :param path: directory to save the images in
        :param format: raster format, e.g. 'PNG' or 'JPG'
        """
        import string

        if path is None:
            d = SaveAllMapsDialog()

            path = SettingValue(SettingKeys.MapImageExportDirectory, default=None)
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
            if not isinstance(tsd, TimeSeriesDate):
                continue
            mv = mapCanvas.mapView()
            assert isinstance(mv, MapView)
            mapCanvas.waitWhileRendering()
            imgPath = '{}.{}.{}'.format(tsd.date(), mv.title(), format)

            imgPath = ''.join(c for c in imgPath if c in valid_chars)
            imgPath = imgPath.replace(' ', '_')
            imgPath = os.path.join(path, imgPath)

            mapCanvas.saveAsImage(imgPath, None, format)
            progressDialog.setValue(i + 1)
            progressDialog.setLabelText('{}/{} maps saved'.format(i + 1, n))

            if progressDialog.wasCanceled():
                return

        setValue(SettingKeys.MapImageExportDirectory, path)

    def onMapViewAdded(self, mapView: MapView):
        """

        :param mapView:
        :return:
        """
        mapView.addLayer(self.profileDock.temporalProfileLayer())
        mapView.addSpectralProfileLayers()

        if len(self.mapViews()) == 1:
            mapView.setMapInfoExpression("@map_date + '\n' + @map_sensor")

    def temporalProfileLayer(self) -> TemporalProfileLayer:
        """
        Returns the TemporalProfileLayer
        :return:
        """
        return self.profileDock.temporalProfileLayer()

    def spectralLibraryWidgets(self) -> typing.List[SpectralLibraryWidget]:
        return [dw.spectralLibraryWidget() for dw in self.ui.findChildren(SpectralLibraryDockWidget)]

    def spectralLibraries(self) -> typing.List[SpectralLibrary]:
        """
        Returns the SpectraLibrary that are opened as the SpectralLibrary dock
        :return: SpectraLibrary
        """
        return [w.speclib() for w in self.spectralLibraryWidgets()]

    def openAddSubdatasetsDialog(self, *args,
                                 title: str = 'Open Subdatasets',
                                 filter: str = '*.*'):

        from .externals.qps.subdatasets import SubDatasetSelectionDialog

        d = SubDatasetSelectionDialog()
        d.setWindowTitle(title)
        d.setFileFilter(filter)
        d.exec_()
        if d.result() == QDialog.Accepted:
            files = d.selectedSubDatasets()
            if len(files) > 0:
                self.addTimeSeriesImages(files)

    def close(self):
        self.ui.close()

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
               geometry: typing.Union[SpatialPoint, SpatialExtent] = None):

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
        :param tsd:  TimeSeriesDate or numpy.datetime64
        """
        tsd = self.timeSeries().findDate(tsd)
        if isinstance(tsd, TimeSeriesDate):
            if show_if_hidden:
                self.mTimeSeries.showTSDs([tsd], b=True)
            self.ui.mMapWidget.setCurrentDate(tsd)

    def mapCanvases(self) -> typing.List[MapCanvas]:
        """
        Returns all MapCanvases of the spatial visualization
        :return: [list-of-MapCanvases]
        """
        return self.ui.mMapWidget.mapCanvases()

    def mapLayerStore(self) -> QgsMapLayerStore:
        """
        Returns the QgsMapLayerStore which is used to register QgsMapLayers
        :return: QgsMapLayerStore
        """
        return self.mMapLayerStore

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


    def onShowLayerProperties(self, lyr=None):
        if not isinstance(lyr, QgsMapLayer):
            lyr = self.currentLayer()

        if isinstance(lyr, (QgsVectorLayer, QgsRasterLayer)):
            from .externals.qps.layerproperties import showLayerPropertiesDialog
            showLayerPropertiesDialog(lyr, self, useQGISDialog=True)

    def onShowSettingsDialog(self):
        from eotimeseriesviewer.settings import SettingsDialog
        d = SettingsDialog(self.ui)
        r = d.exec_()

        if r == QDialog.Accepted:
            self.applySettings()
            s = ""
        else:
            pass
            s = ""

    def applySettings(self):
        """
        Reads the QSettings object and applies its values to related widget components
        """

        # the default values
        defaults = defaultValues()
        for key in list(SettingKeys):
            if SettingValue(key) == None and key in defaults.keys():
                setValue(key, defaults[key])

        v = SettingValue(SettingKeys.DateTimePrecision)
        if isinstance(v, DateTimePrecision):
            self.mTimeSeries.setDateTimePrecision(v)

        v = SettingValue(SettingKeys.SensorMatching)
        if isinstance(v, SensorMatching):
            self.mTimeSeries.setSensorMatching(v)

        v = SettingValue(SettingKeys.SensorSpecs)
        if isinstance(v, dict):
            sensors = dict()
            for s in self.sensors():
                sensors[s.id()] = s

            for sid, specs in v.items():
                assert isinstance(sid, str)
                assert isinstance(specs, dict)
                sensor = sensors.get(sid)
                if isinstance(sensor, SensorInstrument):
                    if 'name' in specs.keys():
                        sensor.setName(specs['name'])

        v = SettingValue(SettingKeys.MapUpdateInterval)
        if isinstance(v, int) and v > 0:
            self.ui.mMapWidget.mMapRefreshTimer.start(v)

        v = SettingValue(SettingKeys.MapBackgroundColor)
        if isinstance(v, QColor):
            self.ui.dockMapViews.setMapBackgroundColor(v)

        v = SettingValue(SettingKeys.MapTextFormat)
        if isinstance(v, QgsTextFormat):
            self.ui.dockMapViews.setMapTextFormat(v)

        v = SettingValue(SettingKeys.MapSize)
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

    def setSpatialExtent(self, spatialExtent: SpatialExtent):
        """
        Sets the map canvas extent
        :param spatialExtent: SpatialExtent
        """
        debugLog()
        self.mapWidget().setSpatialExtent(spatialExtent)

    def setSpatialCenter(self, spatialPoint: SpatialPoint):
        """
        Sets the center of map canvases
        :param spatialPoint: SpatialPoint
        """
        self.mapWidget().setSpatialCenter(spatialPoint)

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

        sensorLayers = [l for l in mapCanvas.layers() if isinstance(l, SensorProxyLayer)]
        currentSpectra = []

        for lyr in sensorLayers:
            assert isinstance(lyr, SensorProxyLayer)
            p = SpectralProfile.fromRasterLayer(lyr, spatialPoint)
            basename = os.path.basename(lyr.source())
            if isinstance(p, SpectralProfile):
                p = p.copyFieldSubset(SPECTRA_PROFILE_FIELDS)
                p.setName(f'{basename}')
                p.setAttribute('date', '{}'.format(tsd.date()))
                p.setAttribute('doy', int(tsd.doy()))
                p.setAttribute('sensor', tsd.sensor().name())
                currentSpectra.append(p)
                if self.mCurrentMapSpectraLoading == 'TOP':
                    break

        if len(currentSpectra) > 0:
            self.setCurrentSpectralProfiles(currentSpectra)

    def setCurrentSpectralProfiles(self, spectra: typing.List[SpectralProfile]):
        if not isinstance(spectra, list):
            spectra = [spectra]
        for s in spectra:
            assert isinstance(s, SpectralProfile)

        widgets: typing.List[SpectralLibraryWidget] = self.spectralLibraryWidgets()
        if len(widgets) == 0:
            self.onCreateSpectralLibrary()
            widgets = self.spectralLibraryWidgets()

        for w in widgets:
            w.setCurrentProfiles(spectra)

    @pyqtSlot(SpatialPoint)
    def loadCurrentTemporalProfile(self, spatialPoint: SpatialPoint):
        self.profileDock.loadCoordinate(spatialPoint)

    def onShowProfile(self, spatialPoint, mapCanvas, mapToolKey):

        assert mapToolKey in MapTools.mapToolValues()

        if mapToolKey == MapTools.TemporalProfile:

            self.profileDock.loadCoordinate(spatialPoint)

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
                                 files: typing.List[typing.Union[str, pathlib.Path]] = None,
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

    def currentLayer(self) -> QgsMapLayer:
        """
        Returns the current layer of the active (last clicked) map view
        :return: QgsMapLayer
        """
        return self.mapWidget().currentLayer()

    def createMapView(self, name: str = None) -> MapView:
        """
        Creates a new MapView.
        :return: MapView
        """
        return self.ui.dockMapViews.createMapView(name=name)

    def mapViews(self) -> typing.List[MapView]:
        """
        Returns all MapViews
        :return: [list-of-MapViews]
        """
        return self.ui.dockMapViews[:]

    def icon(self) -> QIcon:
        """
        Returns the EO Time Series Viewer icon
        :return: QIcon
        """
        import eotimeseriesviewer
        return eotimeseriesviewer.icon()

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

        knownName = eotsvSettings.sensorName(sensor.id())
        sensor.sigNameChanged.connect(lambda *args, s=sensor: self.onSensorNameChanged(sensor))

        if isinstance(knownName, str) and len(knownName) > 0:
            sensor.setName(knownName)
        else:
            self.onSensorNameChanged(sensor)  # save the sensor name to the settings

    def onSensorNameChanged(self, sensor: SensorInstrument):
        # save changed names to settings
        from eotimeseriesviewer.settings import saveSensorName
        if sensor in self.sensors():
            saveSensorName(sensor)

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

                if len(self.ui.dockMapViews) == 0:
                    self.ui.dockMapViews.createMapView()

        if len(self.mTimeSeries) == 0:
            self.mSpatialMapExtentInitialized = False

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

    def loadTimeSeriesStack(self):

        from eotimeseriesviewer.stackedbandinput import StackedBandInputDialog

        d = StackedBandInputDialog(parent=self.ui)
        if d.exec_() == QDialog.Accepted:
            writtenFiles = d.saveImages()
            self.addTimeSeriesImages(writtenFiles)

    def loadExampleTimeSeries(self, n: int = None, loadAsync=True):
        """
        Loads an example time series
        :param n: int, max. number of images to load. Useful for developer test-cases
        """

        import example.Images
        exampleDataDir = pathlib.Path(example.Images.__file__).parent
        rasterFiles = list(file_search(exampleDataDir, '*.tif', recursive=True))
        vectorFiles = list(file_search(exampleDataDir.parent, re.compile(r'.*\.(gpkg|shp)$'), recursive=True))
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
                    if lyr.geometryType() == QgsWkbTypes.PolygonGeometry and isinstance(renderer,
                                                                                        QgsSingleSymbolRenderer):
                        renderer = renderer.clone()
                        symbol = renderer.symbol()
                        if isinstance(symbol, QgsFillSymbol):
                            symbol.setOpacity(0.25)
                        lyr.setRenderer(renderer)
                    s = ""

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

    def focusTimeSeriesDateVisibility(self, *args, extent:SpatialExtent = None, date: TimeSeriesDate = None):
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

    def showAttributeTable(self, lyr: QgsVectorLayer, filterExpression: str = ""):
        assert isinstance(lyr, QgsVectorLayer)

        # 1. check if this layer is already opened as dock widget
        docks: typing.List[QgsDockWidget] = self.ui.findChildren(QgsDockWidget)
        vectorLayerDocks: typing.List[QgsDockWidget] = [d for d in docks if
                                                        isinstance(d, (LabelDockWidget, SpectralLibraryDockWidget))]

        for d in vectorLayerDocks:
            if isinstance(d, LabelDockWidget) and d.vectorLayer().id() == lyr.id() or \
                    isinstance(d, SpectralLibraryDockWidget) and d.speclib().id() == lyr.id():
                d.show()
                d.activateWindow()
                d.raise_()
                return

        # 2. create dock widget

        if isinstance(lyr, SpectralLibrary):
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

    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                # if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def addMapLayers(self, layers: typing.List[QgsMapLayer]) -> typing.List[QgsMapLayer]:
        """
        Adds QgsMapLayers
        :param layers:
        :return:
        """
        if isinstance(layers, QgsMapLayer):
            layers = [layers]

        layers = [l for l in layers if isinstance(l, QgsMapLayer) and not isinstance(l, SensorProxyLayer)]
        if len(layers) > 0:
            QgsProject.instance().addMapLayers(layers)
            for mapView in self.mapViews():
                assert isinstance(mapView, MapView)
                for l in layers:
                    mapView.addLayer(l)

                break  # add to first mapview only
        return layers

    def onCreateSpectralLibrary(self):
        speclib: SpectralLibrary = SpectralLibrary()
        speclib.startEditing()
        for field in SPECTRA_PROFILE_FIELDS:
            speclib.addAttribute(field)
        assert speclib.commitChanges()
        QgsProject.instance().addMapLayer(speclib)
        self.showAttributeTable(speclib)
        self.addMapLayers(speclib)

    def addVectorData(self, files=None) -> list:
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
            from eotimeseriesviewer.mapvisualization import MapView
            from .externals.qps.layerproperties import subLayers

            for f in files:
                vectorLayers.extend(subLayers(QgsVectorLayer(f)))

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
