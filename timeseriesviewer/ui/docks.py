import os
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


load = lambda p : loadUIFormClass(jp(DIR_UI,p))

class TsvDockWidgetBase(QgsDockWidget):


    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states


class ProfileViewDockUI(TsvDockWidgetBase, load('profileviewdock.ui')):
    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)

class SensorDockUI(TsvDockWidgetBase, load('sensordock.ui')):
    def __init__(self, parent=None):
        super(SensorDockUI, self).__init__(parent)
        self.setupUi(self)



class RenderingDockUI(TsvDockWidgetBase, load('renderingdock.ui')):
    def __init__(self, parent=None):
        super(RenderingDockUI, self).__init__(parent)
        self.setupUi(self)

    def subsetSize(self):
        return QSize(self.spinBoxSubsetSizeX.value(),
                     self.spinBoxSubsetSizeY.value())


class NavigationDockUI(TsvDockWidgetBase, load('navigationdock.ui')):
    from timeseriesviewer.timeseries import TimeSeriesDatum

    sigNavToDOI = pyqtSignal(TimeSeriesDatum)

    def __init__(self, parent=None):
        super(NavigationDockUI, self).__init__(parent)
        self.setupUi(self)
        self.mCrs = None

        self.btnNavToFirstTSD.setDefaultAction(parent.actionFirstTSD)
        self.btnNavToLastTSD.setDefaultAction(parent.actionLastTSD)
        self.btnNavToPreviousTSD.setDefaultAction(parent.actionPreviousTSD)
        self.btnNavToNextTSD.setDefaultAction(parent.actionNextTSD)

        #default: disable QgsSync box
        self.gbSyncQgs.setEnabled(False)

        self.cbSyncQgsMapExtent.clicked.connect(self.qgsSyncStateChanged)
        self.cbSyncQgsMapCenter.clicked.connect(self.qgsSyncStateChanged)
        self.cbSyncQgsCRS.clicked.connect(self.qgsSyncStateChanged)

        self.spatialExtentWidgets = [self.spinBoxExtentCenterX, self.spinBoxExtentCenterY,
                                     self.spinBoxExtentWidth, self.spinBoxExtentHeight]

        self.sliderDOI.valueChanged.connect(self.onSliderDOIChanged)


        self.connectTimeSeries(None)

    def connectTimeSeries(self, TS):
        self.TS = TS
        self.timeSeriesInitialized = False
        if TS is not None:
            TS.sigTimeSeriesDatesAdded.connect(self.updateFromTimeSeries)

        self.updateFromTimeSeries()


    def updateFromTimeSeries(self):
        self.sliderDOI.setMinimum(1)
        if self.TS is None or len(self.TS) == 0:
            #reset
            self.timeSeriesInitialized = False
            self.labelDOIValue.setText('Time series is empty')
            self.sliderDOI.setMaximum(1)
        else:
            l = len(self.TS)
            self.sliderDOI.setMaximum(l)
            # get meaningfull tick intervall
            for tickInterval in [1, 5, 10, 25, 50, 100, 200]:
                if (self.sliderDOI.size().width() / float(l) * tickInterval) > 5:
                    break
            self.sliderDOI.setTickInterval(tickInterval)

            if not self.timeSeriesInitialized:
                self.setSpatialExtent(self.TS.getMaxSpatialExtent(self.crs()))
                self.timeSeriesInitialized = True

    def setDOISliderValue(self, key):
        ui = self.ui
        v = ui.sliderDOI.value()
        if key == 'first':
            v = ui.sliderDOI.minimum()
        elif key == 'last':
            v = ui.sliderDOI.maximum()
        elif key == 'next':
            v = min([v + 1, ui.sliderDOI.maximum()])
        elif key == 'previous':
            v = max([v - 1, ui.sliderDOI.minimum()])
        ui.sliderDOI.setValue(v)


    def onSliderDOIChanged(self, i):

        if self.TS is None or len(self.TS) == 0:
            self.labelDOIValue.setText('<empty timeseries>')
        else:
            assert i <= len(self.TS)
            TSD = self.TS.data[i - 1]
            self.labelDOIValue.setText(str(TSD.date))
            self.sigNavToDOI.emit(TSD)

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
        self.setupUi(self)

class MapViewDockUI(TsvDockWidgetBase, load('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.dockLocationChanged.connect(self.adjustLayouts)

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

    d = ProfileDockUI()
    d.show()
    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
