import sys, os
from qgis.core import *
from PyQt4.QtCore import *
from timeseriesviewer import *


from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument

class SensorTableModel(QAbstractTableModel):
    columnames = ['name', 'nb', 'n images']

    def __init__(self, TS, parent=None, *args):

        super(SensorTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)
        self.TS = TS

        self.TS.sigSensorAdded.connect(self.addSensor)
        self.TS.sigSensorRemoved.connect(self.removeSensor)

        self.items = []
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        for s in self.TS.Sensors:
            self.addSensor(s)


    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)

        self.items.append(sensor)
        self.sort(self.sortColumnIndex, self.sortOrder)

    def removeSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.items:
            self.items.remove(sensor)

    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        if colName == 'name':
            self.items.sort(key = lambda s:s.sensorName, reverse=r)
        elif colName == 'nb':
            self.items.sort(key=lambda s: s.nb, reverse=r)

        self.layoutChanged.emit()


    def rowCount(self, parent = QModelIndex()):
        return len(self.items)


    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self.items[row:row+count]
        for tsd in toRemove:
            self.items.remove(tsd)
        self.endRemoveRows()

    def getIndexFromSensor(self, sensor):
        return self.createIndex(self.items.index(sensor),0)

    def getSensorFromIndex(self, index):
        if index.isValid():
            return self.items[index.row()]
        return None

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnames[index.column()]

        sensor = self.getSensorFromIndex(index)
        assert isinstance(sensor, SensorInstrument)

        if role == Qt.DisplayRole:
            if columnName == 'name':
                value = sensor.sensorName
            elif columnName == 'nb':
                value = str(sensor.nb)
            elif columnName == 'n images':
                value = str(len(self.TS.getTSDs(sensorOfInterest=sensor)))

        elif role == Qt.CheckStateRole:
            if columnName == 'name':
                value = None
        elif role == Qt.UserRole:
            value = sensor
        return value


    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in ['name']: #allow check state
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




class TimeSeriesTableModel(QAbstractTableModel):
    columnames = ['date', 'sensor', 'ns', 'nl', 'nb', 'image', 'mask']

    def __init__(self, TS, parent=None, *args):

        super(TimeSeriesTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)
        self.TS = TS

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
                    value = str(TSD.sensor)
            elif columnName == 'date':
                value = '{}'.format(TSD.date)
            elif columnName == 'image':
                value = TSD.pathImg
            elif columnName == 'mask':
                value = TSD.pathMsk
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

