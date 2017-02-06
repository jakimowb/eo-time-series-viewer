import sys, os
from qgis.core import *
from PyQt4.QtCore import *
from timeseriesviewer import *

import numpy as np
from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument

class ComboBoxDelegate(QItemDelegate):

    def __init__(self, parent=None):
        super(ComboBoxDelegate, self)

class PixelCollection(QObject):

    sigSensorSetChanged = pyqtSignal()
    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)

    def __init__(self, timeSeries):
        assert isinstance(timeSeries, TimeSeries)
        super(PixelCollection, self).__init__()

        self.TS = timeSeries
        self.sensors = []
        self.sensorPxLayers = dict()

    def addPixel(self, d):
        assert isinstance(d, dict)
        if len(d) > 0:
            tsd = self.TS.getTSD(d['path'])
            values = d['values']
            nb, nl, ns = values.shape
            assert nb >= 1

            assert isinstance(tsd, TimeSeriesDatum)
            if tsd.sensor not in self.sensorPxLayers.keys():
                #create new temp layer
                mem = QgsVectorLayer('point', 'Pixels_sensor_'+tsd.sensor.sensorName, 'memory')
                self.sensorPxLayers[tsd.sensor] = mem
                assert mem.startEditing()

                #standard field names, types, etc.
                fieldDefs = [('date',QVariant.String, 'char'),
                             ('doy', QVariant.Int, 'integer'),
                             ('geo_x', QVariant.Double, 'decimal'),
                             ('geo_y', QVariant.Double, 'decimal'),
                             ('px_x', QVariant.Int, 'integer'),
                             ('px_y', QVariant.Int, 'integer'),
                             ]
                for fieldDef in fieldDefs:
                    field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
                    mem.addAttribute(field)

                #add bands
                if values.dtype in [np.int8, np.int16, np.int32, np.int64,
                                    np.uint8, np.uint16, np.uint32, np.uint64]:
                    fType = QVariant.Int
                    fTypeName = 'integer'
                elif values.dtype in [np.float16, np.float32, np.float64]:
                    fType = QVariant.Double
                    fTypeName = 'decimal'
                else:
                    print('Unable to handle pixel data of type {}'.format(values.dtype))
                    raise NotImplementedError()

                for i in range(nb):
                    fName = 'b{}'.format(i+1)
                    mem.addAttribute(QgsField(fName, fType, fTypeName))
                assert mem.commitChanges()
                self.sigSensorSetChanged.emit()
                self.sigSensorAdded.emit(tsd.sensor)
                s = ""

            mem = self.sensorPxLayers[tsd.sensor]


            #insert each single pixel, line by line
            xres = d['xres']
            yres = d['yres']
            geo_ul_x = d['geo_ul_x']
            geo_ul_y = d['geo_ul_y']
            px_ul_x = d['px_ul_x']
            px_ul_y = d['px_ul_y']

            doy = tsd.doy
            for i in range(ns):
                geo_x = geo_ul_x + xres * i
                px_x = px_ul_x + i
                for j in range(nl):
                    geo_y = geo_ul_y + yres * j
                    px_y = px_ul_y + j
                    profile = values[:,j,i]
                    geometry = QgsPointV2(geo_x, geo_y)
                    feature = QgsFeature(mem.fields())

                    #fnames = [f.name() for f in mem.fields()]

                    feature.setGeometry(QgsGeometry(geometry))
                    feature.setAttribute('date', str(tsd.date))
                    feature.setAttribute('doy', doy)
                    feature.setAttribute('geo_x', geo_x)
                    feature.setAttribute('geo_y', geo_y)
                    feature.setAttribute('px_x', px_x)
                    feature.setAttribute('px_y', px_y)
                    for b in range(nb):
                        name ='b{}'.format(b+1)
                        #if mem.fieldNameIndex(name) == -1:
                        #    s = ""
                        feature.setAttribute('b{}'.format(b+1), profile[b])
                    mem.startEditing()
                    mem.addFeature(feature)
                    assert mem.commitChanges()


            #each pixel is a new feature
            s = ""

        pass



    def clear(self):
        for sensor in self.sensorPxLayers.keys():
            self.sigSensorRemoved.emit(sensor)
        self.sigSensorSetChanged.emit()


    def values(self, sensor, expression):
        if sensor not in self.sensorPxLayers.keys():
            return []
        mem = self.sensorPxLayers[sensor]
        exp = QgsExpression(expression)
        if exp.isValid():
            mem.selectAll()
            for feature in mem.selectedFeatures():
                exp.evaluate(feature)

                s = ""
        else:
            s = ""

        s =""
        return None



class PixelCollectionSensorExpressionModel(QAbstractTableModel):

    class SensorView(object):
        def __init__(self, sensor):
            assert isinstance(sensor, SensorInstrument)
            self.sensor = sensor
            self.expression = 'b1'
            self.isVisible = True

    columnames = ['sensor','nb','y-value']
    def __init__(self, pixelCollection, parent=None, *args):

        super(PixelCollectionSensorExpressionModel, self).__init__()
        assert isinstance(pixelCollection, PixelCollection)
        self.PX = pixelCollection
        self.PX.sigSensorAdded.connect(self.addSensor)
        self.PX.sigSensorRemoved.connect(self.removeSensor)

        self.items = []
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        for s in self.PX.sensorPxLayers.keys():
            self.addSensor(s)


    def addSensor(self, sensor):
        self.items.append(PixelCollectionSensorExpressionModel.SensorView(sensor))
        self.sort(self.sortColumnIndex, self.sortOrder)

    def removeSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        to_remove = [sv for sv in self.items if sv.sensor == sensor]
        for t in to_remove:
            self.items.remove(t)

    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        if colName == 'sensor':
            self.items.sort(key = lambda sv:sv.sensor.sensorName, reverse=r)
        elif colName == 'nb':
            self.items.sort(key=lambda sv: sv.sensor.nb, reverse=r)
        elif colName == 'y-value':
            self.items.sort(key=lambda sv: sv.expression, reverse=r)

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

        return self.createIndex([i for i, s in enumerate(self.items) if s.sensor == sensor],0)

    def getSensorExprFromIndex(self, index):
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

        sw = self.getSensorExprFromIndex(index)

        if role == Qt.DisplayRole:
            if columnName == 'sensor':
                value = sw.sensor.sensorName
            elif columnName == 'nb':
                value = str(sw.sensor.nb)
            elif columnName == 'y-value':
                value = sw.expression

        elif role == Qt.CheckStateRole:
            if columnName == 'sensor':
                value = Qt.Checked if sw.isVisible else Qt.Unchecked
        elif role == Qt.UserRole:
            value = sw
        return value


    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName == 'sensor':
                flags = flags | Qt.ItemIsUserCheckable

            if columnName in ['y-axis']: #allow check state
                flags = flags | Qt.ItemIsEditable
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
