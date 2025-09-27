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
from typing import Optional

from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.timeseries.source import TimeSeriesDate
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from qgis.PyQt.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from qgis.PyQt.QtWidgets import QHeaderView
from qgis.gui import QgsDockWidget


class SensorDockUI(QgsDockWidget):
    def __init__(self, parent=None):
        super(SensorDockUI, self).__init__(parent)
        loadUi(DIR_UI / 'sensordock.ui', self)

        self.TS = None
        self.mSensorModel: SensorTableModel = None
        self.mSortedModel: QSortFilterProxyModel = QSortFilterProxyModel()

    def setTimeSeries(self, timeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        self.mSensorModel = SensorTableModel(self.TS)
        self.mSortedModel.setSourceModel(self.mSensorModel)
        self.sensorView.setModel(self.mSortedModel)
        self.sensorView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)


class SensorTableModel(QAbstractTableModel):
    cName = 0
    cBands = 1
    cDates = 2
    cImages = 3
    cWL = 4
    cSID = 5

    def __init__(self, timeSeries: TimeSeries, parent=None, *args):

        super(SensorTableModel, self).__init__()
        assert isinstance(timeSeries, TimeSeries)

        # define column names
        self.mColumNames = {
            self.cName: "Name",
            self.cBands: "Bands",
            self.cDates: "Dates",
            self.cImages: "Images",
            self.cWL: "Wavelengths",
            self.cSID: "Sensor ID"
        }

        self.TS = timeSeries

        self.TS.sigSensorAdded.connect(self.addSensor)
        self.TS.sigSensorRemoved.connect(self.removeSensor)
        self.TS.sigTimeSeriesDatesAdded.connect(self.onTimeSeriesSourceChanges)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.onTimeSeriesSourceChanges)
        self.mSensors = []
        for s in self.TS.sensors():
            self.addSensor(s)

    def onTimeSeriesSourceChanges(self, timeSeriesDates: list):
        """
        Reaction on changes in the time series data sources
        :param timeSeriesDates: list
        """
        sensors = set()
        for tsd in timeSeriesDates:
            assert isinstance(tsd, TimeSeriesDate)
            sensors.add(tsd.sensor())

        for sensor in sensors:
            self.updateSensor(sensor)

    def addSensor(self, sensor: SensorInstrument):
        """
        Adds a sensor
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        i = self.rowCount()
        self.beginInsertRows(QModelIndex(), i, i)
        self.mSensors.append(sensor)
        sensor.sigNameChanged.connect(lambda *args, s=sensor: self.updateSensor(s))
        self.endInsertRows()

    def updateSensor(self, sensor: SensorInstrument):
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            tl = self.getIndexFromSensor(sensor)
            br = self.createIndex(tl.row(), self.columnCount() - 1)
            self.dataChanged.emit(tl, br)

    def removeSensor(self, sensor: SensorInstrument):
        """
        Removes a SensorInstrument
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            i = self.mSensors.index(sensor)
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mSensors.remove(sensor)
            self.endRemoveRows()

    def rowCount(self, parent=QModelIndex()):
        return len(self.mSensors)

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        toRemove = self.mSensors[row:row + count]
        for tsd in toRemove:
            self.mSensors.remove(tsd)
        self.endRemoveRows()

    def getIndexFromSensor(self, sensor) -> QModelIndex:
        return self.createIndex(self.mSensors.index(sensor), 0)

    def getSensorFromIndex(self, index) -> Optional[SensorInstrument]:
        if index.isValid():
            return self.mSensors[index.row()]
        return None

    def columnCount(self, parent=QModelIndex()):
        return len(self.mColumNames)

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        c = index.column()

        sensor = self.getSensorFromIndex(index)
        assert isinstance(sensor, SensorInstrument)

        if role in [Qt.DisplayRole, Qt.EditRole]:

            if c == self.cName:
                value = sensor.name()

            elif c == self.cBands:
                value = str(sensor.nb)

            elif c == self.cImages:
                n = 0
                for tsd in self.TS.tsds(sensor=sensor):
                    assert isinstance(tsd, TimeSeriesDate)
                    n += len(tsd.sources())
                value = n

            elif c == self.cDates:
                value = len(self.TS.tsds(sensor=sensor))

            elif c == self.cSID:
                value = sensor.id()

            elif c == self.cWL:
                if sensor.wl is None or len(sensor.wl) == 0:
                    value = 'undefined'
                else:
                    value = ','.join([str(w) for w in sensor.wl])
                    if sensor.wlu is not None:
                        value += '[{}]'.format(sensor.wlu)

        elif role == Qt.CheckStateRole:
            if c == self.cName:
                value = None

        elif role == Qt.UserRole:
            value = sensor

        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()

        sensor = self.getSensorFromIndex(index)
        assert isinstance(sensor, SensorInstrument)
        b = False
        if role == Qt.EditRole and c == self.cName:
            if len(value) == 0:  # do not accept empty strings
                b = False
            else:
                sensor.setName(str(value))
                b = True

        # data changed will be emitted via signal from sensor in updateSensor

        return b

    def index(self, row: int, col: int, parent: QModelIndex = None):
        return self.createIndex(row, col, self.mSensors[row])

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if index.column() in [self.cName]:  # allow check state
                flags = flags | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col + 1
        return None


class SensorListModel(QAbstractListModel):

    def __init__(self, timeSeries: TimeSeries, parent=None, *args):

        super(SensorListModel, self).__init__()
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        self.TS.sigSensorAdded.connect(self.insertSensor)
        self.TS.sigSensorRemoved.connect(self.removeSensor)

        self.mSensors = []
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        for s in self.TS.sensors():
            self.insertSensor(s)

    def insertSensor(self, sensor, i=None):
        assert isinstance(sensor, SensorInstrument)
        if i is None:
            i = len(self.mSensors)
            self.beginInsertRows(QModelIndex(), i, i)
            self.mSensors.insert(i, sensor)
            self.endInsertRows()

    def removeSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            i = self.mSensors.index(sensor)
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mSensors.remove(sensor)
            self.endRemoveRows()

    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        r = order != Qt.AscendingOrder
        self.mSensors.sort(key=lambda s: s.name(), reverse=r)
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self.mSensors)

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        toRemove = self.mSensors[row:row + count]
        for tsd in toRemove:
            self.mSensors.remove(tsd)
        self.endRemoveRows()

    def sensor2idx(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        return self.createIndex(self.mSensors.index(sensor), 0)

    def idx2sensor(self, index):
        assert isinstance(index, QModelIndex)
        if index.isValid():
            return self.mSensors[index.row()]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        sensor = self.idx2sensor(index)
        assert isinstance(sensor, SensorInstrument)

        if role == Qt.DisplayRole:
            value = sensor.name()
        elif role == Qt.UserRole:
            value = sensor
        return value

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None
