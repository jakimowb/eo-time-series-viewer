from qgis.core import *
from qgis.gui import QgsDockWidget
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.ui import loadUIFormClass, DIR_UI
from timeseriesviewer.main import SpatialExtent, SpatialPoint, QgisTsvBridge


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
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigQgisSyncStateChanged = pyqtSignal(QgisTsvBridge.SyncState)
    sigQgisInteractionRequest = pyqtSignal(str)

    def __init__(self, parent=None):
        super(RenderingDockUI, self).__init__(parent)
        self.setupUi(self)
        self.progress = dict()
        self.spinBoxMapSizeX.valueChanged.connect(lambda : self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda : self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()
        self.mSubsetRatio = None
        self.mResizeStop = False
        self.btnApplySizeChanges.setEnabled(False)
        self.btnApplySizeChanges.clicked.connect(lambda: self.onMapSizeChanged(None))
        self.btnMapCanvasColor.colorChanged.connect(self.sigMapCanvasColorChanged)
        self.btnCrs.crsChanged.connect(self.sigCrsChanged)

        #default: disable QgsSync box

        #todo: realt-time syncing?
        self.frameRTSync.setVisible(False)
        self.progressBar.setVisible(False)

        self.enableQgisSyncronization(False)

        self.mLastSyncState = self.qgsSyncState()
        self.cbSyncQgsMapExtent.stateChanged.connect(self.onSyncStateChanged)
        self.cbSyncQgsMapCenter.stateChanged.connect(self.onSyncStateChanged)
        self.cbSyncQgsCRS.stateChanged.connect(self.onSyncStateChanged)

        self.btnSetQGISCenter.clicked.connect(lambda : self.sigQgisInteractionRequest.emit('tsvCenter2qgsCenter'))
        self.btnSetQGISExtent.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('tsvExtent2qgsExtent'))
        self.btnGetQGISCenter.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('qgisCenter2tsvCenter'))
        self.btnGetQGISExtent.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('qgisExtent2tsvExtent'))

    def enableQgisSyncronization(self, b):

        self.gbSyncQgs.setEnabled(b)
        if b:
            self.gbSyncQgs.setTitle('QGIS')
        else:
            self.gbSyncQgs.setTitle('QGIS (not available)')
        #self.gbQgsVectorLayer.setEnabled(b)

    def onSyncStateChanged(self, *args):

        w = [self.cbSyncQgsMapCenter, self.cbSyncQgsMapExtent]
        self._blockSignals(w, True)
        if self.cbSyncQgsMapExtent.isChecked():
            self.cbSyncQgsMapCenter.setEnabled(False)
            self.cbSyncQgsMapCenter.setChecked(True)
        else:
            self.cbSyncQgsMapCenter.setEnabled(True)
        state = self.qgsSyncState()
        self._blockSignals(w, False)

        if self.mLastSyncState != state:
            self.mLastSyncState = state
            self.sigQgisSyncStateChanged.emit(state)


    def setQgisSyncState(self, syncState):
        assert isinstance(syncState, QgisTsvBridge.SyncState)

        self.cbSyncQgsCRS.setChecked(syncState.crs)
        self.cbSyncQgsMapExtent.setChecked(syncState.extent)
        self.cbSyncQgsMapCenter.setChecked(syncState.center)

    def qgsSyncState(self):
        s = QgisTsvBridge.SyncState()
        s.crs = self.cbSyncQgsCRS.isChecked()
        s.extent = self.cbSyncQgsMapExtent.isChecked()
        s.center = self.cbSyncQgsMapCenter.isChecked()
        return s


    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.btnCrs.setCrs(crs)
        self.btnCrs.setLayerCrs(crs)
        #self.sigCrsChanged.emit(self.crs())

    def crs(self):
        return self.btnCrs.crs()

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


    def setMapSize(self, size, blockWidgetSignals = True):
        assert isinstance(size, QSize)
        w = [self.spinBoxMapSizeX, self.spinBoxMapSizeY]

        if blockWidgetSignals:
            self._blockSignals(w, True)

        self.spinBoxMapSizeX.setValue(size.width()),
        self.spinBoxMapSizeY.setValue(size.height())
        self.mLastMapSize = QSize(size)
        if blockWidgetSignals:
            self._blockSignals(w, False)

    def mapSize(self):
        return QSize(self.spinBoxMapSizeX.value(),
                     self.spinBoxMapSizeY.value())

    def onMapSizeChanged(self, dim):
        newSize = self.mapSize()
        #1. set size of other dimension accordingly
        if dim is not None:
            if self.checkBoxKeepSubsetAspectRatio.isChecked():
                if dim == 'X':
                    vOld = self.mLastMapSize.width()
                    vNew = newSize.width()
                    targetSpinBox = self.spinBoxMapSizeY
                elif dim == 'Y':
                    vOld = self.mLastMapSize.height()
                    vNew = newSize.height()
                    targetSpinBox = self.spinBoxMapSizeX

                oldState = targetSpinBox.blockSignals(True)
                targetSpinBox.setValue(int(round(float(vNew) / vOld * targetSpinBox.value())))
                targetSpinBox.blockSignals(oldState)
                newSize = self.mapSize()
            if newSize != self.mLastMapSize:
                self.btnApplySizeChanges.setEnabled(True)
        else:
            self.sigMapSizeChanged.emit(self.mapSize())
            self.btnApplySizeChanges.setEnabled(False)
        self.setMapSize(newSize, True)

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


if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()
    d = RenderingDockUI()
    d.show()
    p = sandbox.SignalPrinter(d)

    qgsApp.exec_()
    qgsApp.exitQgis()
