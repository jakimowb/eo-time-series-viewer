import sys, os
from qgis.core import *
from PyQt4.QtCore import *
from timeseriesviewer import *

import numpy as np
import pyqtgraph as pg
from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument

from timeseriesviewer.ui.docks import loadUi, TsvDockWidgetBase

class SensorDockUI(TsvDockWidgetBase, loadUi('sensordock.ui')):
    def __init__(self, parent=None):
        super(SensorDockUI, self).__init__(parent)
        self.setupUi(self)

        self.TS = None

    def connectTimeSeries(self, timeSeries):
        from timeseriesviewer.timeseries import TimeSeries
        from timeseriesviewer.sensorvisualization import SensorTableModel
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        model = SensorTableModel(self.TS)
        self.sensorView.setModel(model)
        self.sensorView.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        s = ""


class SensorTableModel(QAbstractTableModel):
    columnames = ['name', 'nb', 'n images','wl','id']

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
            self.items.sort(key = lambda s:s.name(), reverse=r)
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
                value = sensor.name()
            elif columnName == 'nb':
                value = str(sensor.nb)
            elif columnName == 'n images':
                value = str(len(self.TS.getTSDs(sensorOfInterest=sensor)))
            elif columnName == 'id':
                value = sensor.id()
            elif columnName == 'wl':
                if sensor.wavelengths is None or sensor.wavelengths.ndim == 0:
                    value = 'undefined'
                else:
                    value = ','.join([str(w) for w in sensor.wavelengths])
                    if sensor.wavelengthUnits is not None:
                        value += '[{}]'.format(sensor.wavelengthUnits)

        elif role == Qt.CheckStateRole:
            if columnName == 'name':
                value = None
        elif role == Qt.UserRole:
            value = sensor
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        columnName = self.columnames[index.column()]

        sensor = self.getSensorFromIndex(index)
        assert isinstance(sensor, SensorInstrument)

        if role == Qt.EditRole and columnName == 'name':
            if len(value) == 0: #do not accept empty strings
                return False
            sensor.setName(str(value))
            return True

        return False

    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in ['name']: #allow check state
                flags = flags | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
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

