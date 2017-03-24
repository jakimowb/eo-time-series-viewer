import os, time, datetime
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import PyQt4.QtWebKit

import sys, re, os, six


from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.ui import loadUIFormClass, DIR_UI

from timeseriesviewer.main import SpatialExtent
import pyqtgraph as pg

load = lambda p : loadUIFormClass(jp(DIR_UI,p))


class TsvDockWidgetBase(QgsDockWidget):

    def __init__(self, parent):
        super(TsvDockWidgetBase, self).__init__(parent)
        self.setupUi(self)

    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states



class RenderingDockUI(TsvDockWidgetBase, load('renderingdock.ui')):
    from timeseriesviewer.crosshair import CrosshairStyle

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    def __init__(self, parent=None):
        super(RenderingDockUI, self).__init__(parent)
        self.setupUi(self)
        self.progress = dict()
        self.spinBoxSubsetSizeX.valueChanged.connect(lambda: self.onSubsetValueChanged('X'))
        self.spinBoxSubsetSizeY.valueChanged.connect(lambda: self.onSubsetValueChanged('Y'))

        self.subsetRatio = None
        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()

        self.subsetSizeWidgets = [self.spinBoxSubsetSizeX, self.spinBoxSubsetSizeY]



    def subsetSize(self):
        return QSize(self.spinBoxSubsetSizeX.value(),
                     self.spinBoxSubsetSizeY.value())

    def onSubsetValueChanged(self, key):
        if self.checkBoxKeepSubsetAspectRatio.isChecked():

            if key == 'X':
                v_old = self.lastSubsetSizeX
                v_new = self.spinBoxSubsetSizeX.value()
                s = self.spinBoxSubsetSizeY
            elif key == 'Y':
                v_old = self.lastSubsetSizeY
                v_new = self.spinBoxSubsetSizeY.value()
                s = self.spinBoxSubsetSizeX

            oldState = s.blockSignals(True)
            s.setValue(int(round(float(v_new) / v_old * s.value())))
            s.blockSignals(oldState)

        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()

        self.actionSetSubsetSize.activate(QAction.Trigger)


    def addStartedWork(self, *args):
        self.progress[args] = False
        self.refreshProgressBar()


    def refreshProgressBar(self):
        self.progressBar.setMaximum(len(self.progress.keys()))
        p = len([v for v in self.progress.values() if v == True])
        self.progressBar.setValue(p)


    def addFinishedWork(self, *args):
        if args in self.progress.keys():
            self.progress[args] = True

        else:
            s = ""
        self.refreshProgressBar()

class NavigationDockUI(TsvDockWidgetBase, load('navigationdock.ui')):
    from timeseriesviewer.timeseries import TimeSeriesDatum

    sigNavToDOI = pyqtSignal(TimeSeriesDatum)

    def __init__(self, parent=None):
        super(NavigationDockUI, self).__init__(parent)
        self.setupUi(self)

        #default: disable QgsSync box
        self.gbSyncQgs.setEnabled(False)
        self.btnCrs.crsChanged.connect(self.sigSetCrs.emit)
        self.btnCrs.crsChanged.connect(self.onCrsUpdated)

        self.syncStateWidgets = [self.cbSyncQgsMapExtent, self.cbSyncQgsMapCenter, self.cbSyncQgsCRS]

        self.spatialExtentWidgets = [self.spinBoxExtentCenterX, self.spinBoxExtentCenterY,
                                     self.spinBoxExtentWidth, self.spinBoxExtentHeight]


        for sb in self.spatialExtentWidgets:
            sb.valueChanged.connect(self.onExtentDefinitionChanges)
        for cb in self.syncStateWidgets:
            cb.clicked.connect(self.onExtentDefinitionChanges)


        self.connectTimeSeries(None)

    def onExtentDefinitionChanges(self):
        if self.cbSyncQgsMapExtent.isChecked():
            self.cbSyncQgsMapCenter.setEnabled(False)
            self.cbSyncQgsMapCenter.setChecked(True)
        else:
            self.cbSyncQgsMapCenter.setEnabled(True)

        self.sigSetSpatialExtent.emit(self.spatialExtent())

    def connectTimeSeries(self, TS):
        self.TS = TS
        self.timeSeriesInitialized = False
        if TS is not None:
            TS.sigTimeSeriesDatesAdded.connect(self.updateFromTimeSeries)
        self.updateFromTimeSeries()


    def updateFromTimeSeries(self):
        if self.TS is None or len(self.TS) == 0:
            #reset
            self.timeSeriesInitialized = False
        else:
            if not self.timeSeriesInitialized:
                self.setSpatialExtent(self.TS.getMaxSpatialExtent(self.crs()))
                self.timeSeriesInitialized = True
                self.sigSetSpatialExtent.emit(self.spatialExtent())



    def qgsSyncState(self):
        return {'center':self.cbSyncQgsMapCenter.isChecked(),
                'extent':self.cbSyncQgsMapExtent.isChecked(),
                'crs':self.cbSyncQgsCRS.isChecked()}


    sigSetCrs = pyqtSignal(QgsCoordinateReferenceSystem)
    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.btnCrs.setCrs(crs)
        self.btnCrs.setLayerCrs(crs)
        self.onCrsUpdated(crs)

    def crs(self):
        return self.btnCrs.crs()

    def onCrsUpdated(self, crs):
        self.gbCrs.setTitle(crs.authid())
        self.textBoxCRSInfo.setPlainText(crs.toWkt())
        self.sigSetCrs.emit(self.crs())

    sigSetSpatialExtent = pyqtSignal(SpatialExtent)

    def spatialExtent(self):
        crs = self.crs()
        if not crs:
            return None
        width = QgsVector(self.spinBoxExtentWidth.value(), 0.0)
        height = QgsVector(0.0, self.spinBoxExtentHeight.value())

        Center = QgsPoint(self.spinBoxExtentCenterX.value(), self.spinBoxExtentCenterY.value())
        UL = Center - (width * 0.5) + (height * 0.5)
        LR = Center + (width * 0.5) - (height * 0.5)

        from timeseriesviewer.main import SpatialExtent
        return SpatialExtent(self.crs(), UL, LR)

    def setSpatialExtent(self, extent):
        old = self.spatialExtent()
        from timeseriesviewer.main import SpatialExtent
        assert isinstance(extent, SpatialExtent)
        center = extent.center()



        states = self._blockSignals(self.spatialExtentWidgets, True)

        self.spinBoxExtentCenterX.setValue(center.x())
        self.spinBoxExtentCenterY.setValue(center.y())
        self.spinBoxExtentWidth.setValue(extent.width())
        self.spinBoxExtentHeight.setValue(extent.height())
        self.setCrs(extent.crs())
        self._blockSignals(states)

        if extent != old:
            self.sigSetSpatialExtent.emit(extent)

    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states


class TimeSeriesDockUI(TsvDockWidgetBase, load('timeseriesdock.ui')):
    def __init__(self, parent=None):
        super(TimeSeriesDockUI, self).__init__(parent)
        #self.setupUi(self)
        self.btnAddTSD.setDefaultAction(parent.actionAddTSD)
        self.btnRemoveTSD.setDefaultAction(parent.actionRemoveTSD)
        self.btnLoadTS.setDefaultAction(parent.actionLoadTS)
        self.btnSaveTS.setDefaultAction(parent.actionSaveTS)
        self.btnClearTS.setDefaultAction(parent.actionClearTS)

        self.progressBar.setMinimum(0)
        self.setProgressInfo(0,100, 'Add images to fill time series')
        self.progressBar.setValue(0)
        self.progressInfo.setText(None)
        self.frameFilters.setVisible(False)

        self.connectTimeSeries(None)

    def setStatus(self):
        from timeseriesviewer.timeseries import TimeSeries
        if isinstance(self.TS, TimeSeries):
            ndates = len(self.TS)
            nsensors = len(set([tsd.sensor for tsd in self.TS]))
            msg = '{} scene(s) from {} sensor(s)'.format(ndates, nsensors)
            if ndates > 1:
                msg += ', {} to {}'.format(str(self.TS[0].date), str(self.TS[-1].date))
            self.progressInfo.setText(msg)


    def setProgressInfo(self, nDone, nMax, message=None):
        if self.progressBar.maximum() != nMax:
            self.progressBar.setMaximum(nMax)
        self.progressBar.setValue(nDone)
        self.progressInfo.setText(message)
        QgsApplication.processEvents()
        if nDone == nMax:
            QTimer.singleShot(3000, lambda: self.setStatus())


    def onSelectionChanged(self, *args):
        self.btnRemoveTSD.setEnabled(self.SM is not None and len(self.SM.selectedRows()) > 0)


        s = ""

    def selectedTimeSeriesDates(self):
        if self.SM is not None:
            return [self.TSM.data(idx, Qt.UserRole) for idx in self.SM.selectedRows()]
        return []

    def connectTimeSeries(self, TS):
        from timeseriesviewer.timeseries import TimeSeries
        self.TS = TS
        self.TSM = None
        self.SM = None
        self.timeSeriesInitialized = False

        if isinstance(TS, TimeSeries):
            from timeseriesviewer.viewmodels import TimeSeriesTableModel
            self.TSM = TimeSeriesTableModel(self.TS)
            self.tableView_TimeSeries.setModel(self.TSM)
            self.SM = QItemSelectionModel(self.TSM)
            self.tableView_TimeSeries.setSelectionModel(self.SM)
            self.SM.selectionChanged.connect(self.onSelectionChanged)
            self.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
            TS.sigLoadingProgress.connect(self.setProgressInfo)

        self.onSelectionChanged()

class MapViewDockUI(TsvDockWidgetBase, load('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.baseTitle = self.windowTitle()
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)

        #self.dockLocationChanged.connect(self.adjustLayouts)

    def toggleLayout(self, p):
        newLayout = None
        l = p.layout()
        print('toggle layout {}'.format(str(p.objectName())))
        tmp = QWidget()
        tmp.setLayout(l)
        sMax = p.maximumSize()
        sMax.transpose()
        sMin = p.minimumSize()
        sMin.transpose()
        p.setMaximumSize(sMax)
        p.setMinimumSize(sMin)
        if isinstance(l, QVBoxLayout):
            newLayout = QHBoxLayout()
        else:
            newLayout = QVBoxLayout()
        print(l, '->', newLayout)

        while l.count() > 0:
            item = l.itemAt(0)
            l.removeItem(item)

            newLayout.addItem(item)


        p.setLayout(newLayout)
        return newLayout

    def adjustLayouts(self, area):
        return
        lOld = self.scrollAreaMapsViewDockContent.layout()
        if area in [Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea] \
            and isinstance(lOld, QVBoxLayout) or \
        area in [Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea] \
                        and isinstance(lOld, QHBoxLayout):

            #self.toogleLayout(self.scrollAreaMapsViewDockContent)
            self.toggleLayout(self.BVButtonList)

class LabelingDockUI(TsvDockWidgetBase, load('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDockUI, self).__init__(parent)
        self.setupUi(self)

        self.btnClearLabelList.clicked.connect(self.tbCollectedLabels.clear)



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()
    d = RenderingDockUI()
    d.show()
    qgsApp.exec_()
    qgsApp.exitQgis()
