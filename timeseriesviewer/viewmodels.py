import sys, os
from qgis.core import *
from PyQt4.QtCore import *
from timeseriesviewer import *

import numpy as np
import pyqtgraph as pg
from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument




class TimeSeriesTableModel(QAbstractTableModel):
    columnames = ['date', 'sensor', 'ns', 'nl', 'nb', 'image']

    def __init__(self, TS, parent=None, *args):

        super(TimeSeriesTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)
        self.TS = TS
        self.sensors = set()
        self.TS.sigTimeSeriesDatesRemoved.connect(self.removeTSDs)
        self.TS.sigTimeSeriesDatesAdded.connect(self.addTSDs)

        self.items = []
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        self.addTSDs([tsd for tsd in self.TS])

    def removeTSDs(self, tsds):
        #self.TS.removeDates(tsds)
        for tsd in tsds:
            if tsd in self.TS:
                #remove from TimeSeries first.
                self.TS.removeDates([tsd])
            elif tsd in self.items:
                idx = self.getIndexFromDate(tsd)
                self.removeRows(idx.row(), 1)

        #self.sort(self.sortColumnIndex, self.sortOrder)


    def addTSDs(self, tsds):
        self.items.extend(tsds)
        self.sort(self.sortColumnIndex, self.sortOrder)
        for sensor in set([tsd.sensor for tsd in tsds]):
            if sensor not in self.sensors:
                self.sensors.add(sensor)
                sensor.sigNameChanged.connect(lambda: self.reset())



    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        if colName in ['date','ns','nl','sensor']:
            self.items.sort(key = lambda d:d.__dict__[colName], reverse=r)

        self.layoutChanged.emit()
        s = ""


    def rowCount(self, parent = QModelIndex()):
        return len(self.items)


    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self.items[row:row+count]
        for tsd in toRemove:
            self.items.remove(tsd)
        self.endRemoveRows()

    def getIndexFromDate(self, tsd):
        return self.createIndex(self.items.index(tsd),0)

    def getDateFromIndex(self, index):
        if index.isValid():
            return self.items[index.row()]
        return None

    def getTimeSeriesDatumFromIndex(self, index):
        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.items):
                return self.items[i]

        return None

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnames[index.column()]

        TSD = self.getTimeSeriesDatumFromIndex(index)
        keys = list(TSD.__dict__.keys())


        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if columnName == 'name':
                value = os.path.basename(TSD.pathImg)
            elif columnName == 'sensor':
                if role == Qt.ToolTipRole:
                    value = TSD.sensor.getDescription()
                else:
                    value = TSD.sensor.name()
            elif columnName == 'date':
                value = '{}'.format(TSD.date)
            elif columnName == 'image':
                value = TSD.pathImg
            elif columnName in keys:
                value = TSD.__dict__[columnName]
            else:
                s = ""
        elif role == Qt.CheckStateRole:
            if columnName == 'date':
                value = Qt.Checked if TSD.isVisible() else Qt.Unchecked
        elif role == Qt.BackgroundColorRole:
            value = None
        elif role == Qt.UserRole:
            value = TSD

        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        if role is Qt.UserRole:

            s = ""

        columnName = self.columnames[index.column()]

        TSD = self.getTimeSeriesDatumFromIndex(index)
        if columnName == 'date' and role == Qt.CheckStateRole:
            TSD.setVisibility(value != Qt.Unchecked)
            return True
        else:
            return False

        return False

    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName == 'date': #allow check state
                flags = flags | Qt.ItemIsUserCheckable

            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None


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

    #add component tests here:



    pixelData = dict()
    pixelData['geo_x'] = 1000
    pixelData['geo_y'] = 2000

    px = PixelCollection()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
