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
        #todo: do this delayed
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
        self.mCrs = None

        #default: disable QgsSync box
        self.gbSyncQgs.setEnabled(False)

        self.cbSyncQgsMapExtent.clicked.connect(self.qgsSyncStateChanged)
        self.cbSyncQgsMapCenter.clicked.connect(self.qgsSyncStateChanged)
        self.cbSyncQgsCRS.clicked.connect(self.qgsSyncStateChanged)

        self.spatialExtentWidgets = [self.spinBoxExtentCenterX, self.spinBoxExtentCenterY,
                                     self.spinBoxExtentWidth, self.spinBoxExtentHeight]

        for sb in self.spatialExtentWidgets:
            sb.valueChanged.connect(lambda: self.sigSpatialExtentChanged.emit(self.spatialExtent()))

        self.connectTimeSeries(None)

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
                self.sigSpatialExtentChanged.emit(self.spatialExtent())


    def qgsSyncStateChanged(self, *args):

        s = ""

    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        old = self.mCrs
        self.mCrs = crs
        self.textBoxCRSInfo.setPlainText(crs.toWkt())
        if self.mCrs != old:
            self.sigCrsChanged.emit(crs)

    def crs(self):
        return self.mCrs

    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

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
            self.sigSpatialExtentChanged.emit(extent)

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

        self.connectTimeSeries(None)


    def onSelectionChanged(self, *args):
        self.btnRemoveTSD.setEnabled(self.SM is not None and len(self.SM.selectedRows()) > 0)


        s = ""

    def selectedTimeSeriesDates(self):
        if self.SM is not None:
            return [self.TSM.data(idx, Qt.UserRole) for idx in self.SM.selectedRows()]
        return []

    def connectTimeSeries(self, TS):
        self.TS = TS
        self.TSM = None
        self.SM = None
        self.timeSeriesInitialized = False
        if TS is not None:
            from timeseriesviewer.viewmodels import TimeSeriesTableModel
            self.TSM = TimeSeriesTableModel(self.TS)
            self.tableView_TimeSeries.setModel(self.TSM)
            self.SM = QItemSelectionModel(self.TSM)
            self.tableView_TimeSeries.setSelectionModel(self.SM)
            self.SM.selectionChanged.connect(self.onSelectionChanged)
            self.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.onSelectionChanged()

class MapViewDockUI(TsvDockWidgetBase, load('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.baseTitle = self.windowTitle()
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)

        #self.dockLocationChanged.connect(self.adjustLayouts)

    def toogleLayout(self, p):
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
            self.toogleLayout(self.BVButtonList)

class LabelingDockUI(TsvDockWidgetBase, load('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDockUI, self).__init__(parent)
        self.setupUi(self)

        self.btnClearLabelList.clicked.connect(self.tbCollectedLabels.clear)



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()

    #run tests
    #d = AboutDialogUI()
    #d.show()

    from timeseriesviewer.tests import *

    TS = TestObjects.TimeSeries()
    ext = TS.getMaxSpatialExtent()

    d = ProfileViewDockUI()
    d.connectTimeSeries(TS)
    d.show()
    d.loadCoordinate(ext.center(), ext.crs())

    #close QGIS
    try:
        qgsApp.exec_()
    except:
        s = ""
    qgsApp.exitQgis()
