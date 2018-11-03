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

import sys, re, collections, traceback


import bisect

from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *


from osgeo import gdal
from timeseriesviewer.utils import SpatialExtent, loadUI

gdal.SetConfigOption('VRT_SHARED_SOURCE', '0') #!important. really. do not change this.

import numpy as np

from timeseriesviewer import SETTINGS, messageLog
from timeseriesviewer.dateparser import parseDateFromDataSet

def transformGeometry(geom, crsSrc, crsDst, trans=None):
    if trans is None:
        assert isinstance(crsSrc, QgsCoordinateReferenceSystem)
        assert isinstance(crsDst, QgsCoordinateReferenceSystem)
        return transformGeometry(geom, None, None, trans=QgsCoordinateTransform(crsSrc, crsDst))
    else:
        assert isinstance(trans, QgsCoordinateTransform)
        return trans.transform(geom)

METRIC_EXPONENTS = {
    "nm":-9,"um": -6, "mm":-3, "cm":-2, "dm":-1, "m": 0,"hm":2, "km":3
}
#add synonyms
METRIC_EXPONENTS['nanometers'] = METRIC_EXPONENTS['nm']
METRIC_EXPONENTS['micrometers'] = METRIC_EXPONENTS['um']
METRIC_EXPONENTS['millimeters'] = METRIC_EXPONENTS['mm']
METRIC_EXPONENTS['centimeters'] = METRIC_EXPONENTS['cm']
METRIC_EXPONENTS['decimeters'] = METRIC_EXPONENTS['dm']
METRIC_EXPONENTS['meters'] = METRIC_EXPONENTS['m']
METRIC_EXPONENTS['hectometers'] = METRIC_EXPONENTS['hm']
METRIC_EXPONENTS['kilometers'] = METRIC_EXPONENTS['km']

def convertMetricUnit(value, u1, u2):
    assert u1 in METRIC_EXPONENTS.keys()
    assert u2 in METRIC_EXPONENTS.keys()

    e1 = METRIC_EXPONENTS[u1]
    e2 = METRIC_EXPONENTS[u2]

    return value * 10**(e1-e2)


def getDS(pathOrDataset):
    if isinstance(pathOrDataset, gdal.Dataset):
        return pathOrDataset
    else:
        ds = gdal.Open(pathOrDataset)
        assert isinstance(ds, gdal.Dataset)
        return ds




class SensorInstrument(QObject):
    """
    Describes a Sensor Configuration
    """
    SensorNameSettingsPrefix = 'SensorName.'
    sigNameChanged = pyqtSignal(str)

    LUT_Wavelengths = dict({'B':480,
                            'G':570,
                            'R':660,
                            'nIR':850,
                            'swIR':1650,
                            'swIR1':1650,
                            'swIR2':2150
                            })

    def __init__(self, pathImg, sensor_name=None):
        super(SensorInstrument, self).__init__()

        ds = getDS(pathImg)
        self.nb, nl, ns, crs, self.px_size_x, self.px_size_y = getSpatialPropertiesFromDataset(ds)

        self.bandDataType = ds.GetRasterBand(1).DataType
        self.pathImg = ds.GetFileList()[0]

        self.bandNames = [ds.GetRasterBand(b+1).GetDescription() for b in range(self.nb)]

        self.TS = None

        assert self.px_size_x > 0
        assert self.px_size_y > 0

        #find wavelength
        wl, wlu = parseWavelengthFromDataSet(ds)
        self.wavelengthUnits = wlu
        if wl is None:
            self.wavelengths = None
        else:
            self.wavelengths = np.asarray(wl)


        self.mId = '{}b{}m'.format(self.nb, self.px_size_x)
        if wl is not None:
            self.mId += ';'.join([str(w) for w in self.wavelengths]) + str(self.wavelengthUnits)


        if sensor_name is None:
            sensor_name = '{}bands@{}m'.format(self.nb, self.px_size_x)
            sensor_name = SETTINGS.value(self._sensorSettingsKey(), sensor_name)

        self.setName(sensor_name)

        self.hashvalue = hash(','.join(self.bandNames))


    def id(self):
        return self.mId

    def _sensorSettingsKey(self):
        return SensorInstrument.SensorNameSettingsPrefix+self.mId
    def setName(self, name):
        self._name = name

        SETTINGS.setValue(self._sensorSettingsKey(), name)
        self.sigNameChanged.emit(self.name())

    def name(self):
        return self._name

    def dataType(self, p_int):
        return self.bandDataType

    def bandClosestToWavelength(self, wl, wl_unit='nm'):
        """
        Returns the band index (>=0) of the band closest to wavelength wl
        :param wl:
        :param wl_unit:
        :return:
        """
        if not self.wavelengthsDefined():
            return None

        if wl in SensorInstrument.LUT_Wavelengths.keys():
            wl_unit = 'nm'
            wl = SensorInstrument.LUT_Wavelengths[wl]

        wl = float(wl)
        if self.wavelengthUnits != wl_unit:
            wl = convertMetricUnit(wl, wl_unit, self.wavelengthUnits)


        return np.argmin(np.abs(self.wavelengths - wl))




    def wavelengthsDefined(self):
        """
        Returns if wavelenght and wavelength units are defined
        :return: bool
        """
        return self.wavelengths is not None and \
                self.wavelengthUnits is not None

    def __eq__(self, other):
        if not isinstance(other, SensorInstrument):
            return False
        return self.nb == other.nb and \
               self.px_size_x == other.px_size_x and \
               self.px_size_y == other.px_size_y

    def __hash__(self):
        return hash(self.id())

    def __repr__(self):
        return str(self.__class__) +' ' + self.name()

    def getDescription(self):
        """
        Returns a human-readable description
        :return: str
        """
        info = []
        info.append(self.name())
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tName\tWavelength')
        for b in range(self.nb):
            if self.wavelengths is not None:
                wl = str(self.wavelengths[b])
            else:
                wl = 'unknown'
            info.append('{}\t{}\t{}'.format(b + 1, self.bandNames[b], wl))

        return '\n'.join(info)


def verifyInputImage(datasource):
    """
    Checks if an image source can be uses as TimeSeriesDatum, i.e. if it can be read by gdal.Open() and
    if we can extract an observation date as numpy.datetime64.
    :param datasource: str with data source uri or gdal.Dataset
    :return: bool
    """

    if datasource is None:
        return None
    if isinstance(datasource, str):
        datasource = gdal.Open(datasource)
    if not isinstance(datasource, gdal.Dataset):
        return False

    if datasource.RasterCount == 0 and len(datasource.GetSubDatasets()) > 0:
        #logger.error('Can not open container {}.\nPlease specify a subdataset'.format(path))
        return False

    if datasource.GetDriver().ShortName == 'VRT':
        files = datasource.GetFileList()
        if len(files) > 0:
            for f in files:
                subDS = gdal.Open(f)
                if not isinstance(subDS, gdal.Dataset):
                    return False

    from timeseriesviewer.dateparser import parseDateFromDataSet
    date = parseDateFromDataSet(datasource)
    if date is None:
        return False

    return True

class TimeSeriesDatum(QObject):
    """
    The core entity of a TimeSeries. Contains a data source, an observation date (numpy.datetime64) and
    the SensorInstrument the data source is linked to.
    """
    @staticmethod
    def createFromPath(path):
        """
        Creates a valid TSD or returns None if this is impossible
        :param path:
        :return:
        """

        tsd = None
        if verifyInputImage(path):

            try:
                tsd = TimeSeriesDatum(None, path)
            except :
                pass

        return tsd

    sigVisibilityChanged = pyqtSignal(bool)
    sigRemoveMe = pyqtSignal()



    def __init__(self, timeSeries, pathImg):
        super(TimeSeriesDatum,self).__init__()

        ds = getDS(pathImg)

        self.pathImg = ds.GetFileList()[0] if isinstance(pathImg, gdal.Dataset) else pathImg

        self.timeSeries = timeSeries
        self.nb, self.nl, self.ns, self.crs, px_x, px_y = getSpatialPropertiesFromDataset(ds)

        self.sensor = SensorInstrument(ds)

        self.date = parseDateFromDataSet(ds)
        assert self.date is not None, 'Unable to find acquisition date of {}'.format(pathImg)
        from timeseriesviewer.dateparser import DOYfromDatetime64
        self.doy = DOYfromDatetime64(self.date)


        gt = ds.GetGeoTransform()
        from timeseriesviewer.utils import px2geo
        UL = QgsPointXY(*px2geo(QPoint(0,0), gt, pxCenter=False))
        LR = QgsPointXY(*px2geo(QPoint(self.ns+1, self.nl+1), gt, pxCenter=False))
        self._spatialExtent = SpatialExtent(self.crs, UL, LR)

        self.srs_wkt = str(self.crs.toWkt())


        self.mVisibility = True


    def setVisibility(self, b):
        """
        Sets the visibility of the TimeSeriesDatum, i.e. whether linked MapCanvases will be shown to the user
        :param b: bool
        """
        old = self.mVisibility
        self.mVisibility = b
        if old != self.mVisibility:
            self.sigVisibilityChanged.emit(b)

    def isVisible(self):
        """
        Returns whether the TimeSeriesDatum is visible as MapCanvas
        :return: bool
        """
        return self.mVisibility


    def getDate(self):
        """
        Returns the observation date
        :return: numpy.datetime64
        """
        return np.datetime64(self.date)


    def getSpatialReference(self):
        """
        Returns the QgsCoordinateReferenceSystem of the data source.
        :return: QgsCoordinateReferenceSystem
        """
        return self.crs

    def spatialExtent(self):
        """
        Returns the SpatialExtent of the data source
        :return: SpatialExtent
        """
        return self._spatialExtent

    def __repr__(self):
        return 'TS Datum {} {}'.format(self.date, str(self.sensor))

    def __eq__(self, other):
        return self.date == other.date and self.sensor.id() == other.sensor.id()

    def __lt__(self, other):
        if self.date < other.date:
            return True
        elif self.date > other.date:
            return False
        else:
            return self.sensor.id() < other.sensor.id()

    def __hash__(self):
        return hash((self.date,self.sensor.id()))


class TimeSeriesTableView(QTableView):

    def __init__(self, parent=None):
        super(TimeSeriesTableView, self).__init__(parent)

    def contextMenuEvent(self, event):
        """
        Creates and shows an QMenu
        :param event:
        """
        menu = QMenu(self)
        a = menu.addAction('Copy value(s)')
        a.triggered.connect(self.onCopyValues)
        a = menu.addAction('Check')
        a.triggered.connect(lambda : self.onSetCheckState(Qt.Checked))
        a = menu.addAction('Uncheck')
        a.triggered.connect(lambda: self.onSetCheckState(Qt.Unchecked))
        menu.popup(QCursor.pos())

    def onSetCheckState(self, checkState):
        """
        Sets a ChecState to all selected rows
        :param checkState: Qt.CheckState
        """
        indices = self.selectionModel().selectedIndexes()
        rows = sorted(list(set([i.row() for i in indices])))
        model = self.model()
        if isinstance(model, TimeSeriesTableModel):
            for r in rows:
                idx = model.index(r,0)
                model.setData(idx, checkState, Qt.CheckStateRole)

    def onCopyValues(self):
        """
        Copies selected cell values to the clipboard
        """
        indices = self.selectionModel().selectedIndexes()
        model = self.model()
        if isinstance(model, TimeSeriesTableModel):
            from collections import OrderedDict
            R = OrderedDict()
            for idx in indices:
                if not idx.row() in R.keys():
                    R[idx.row()] = []
                R[idx.row()].append(model.data(idx, Qt.DisplayRole))
            info = []
            for k, values in R.items():
                info.append(';'.join([str(v) for v in values]))
            info = '\n'.join(info)
            QApplication.clipboard().setText(info)
        s = ""




class TimeSeriesDockUI(QgsDockWidget, loadUI('timeseriesdock.ui')):
    """
    QgsDockWidget that shows the TimeSeries
    """
    def __init__(self, parent=None):
        super(TimeSeriesDockUI, self).__init__(parent)
        self.setupUi(self)
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

        self.setTimeSeries(None)

    def setStatus(self):
        """
        Updates the status of the TimeSeries
        """
        from timeseriesviewer.timeseries import TimeSeries
        if isinstance(self.TS, TimeSeries):
            ndates = len(self.TS)
            nsensors = len(set([tsd.sensor for tsd in self.TS]))
            msg = '{} scene(s) from {} sensor(s)'.format(ndates, nsensors)
            if ndates > 1:
                msg += ', {} to {}'.format(str(self.TS[0].date), str(self.TS[-1].date))
            self.progressInfo.setText(msg)

    def setProgressInfo(self, nDone:int, nMax:int, message=None):
        """
        Sets the progress bar of the TimeSeriesDockUI
        :param nDone: number of added data sources
        :param nMax: total number of data source to be added
        :param message: error / other kind of info message
        """
        if self.progressBar.maximum() != nMax:
            self.progressBar.setMaximum(nMax)
        self.progressBar.setValue(nDone)
        self.progressInfo.setText(message)
        QgsApplication.processEvents()
        if nDone == nMax:
            QTimer.singleShot(3000, lambda: self.setStatus())

    def onSelectionChanged(self, *args):
        """
        Slot to react on user-driven changes of the selected TimeSeriesDatum rows.
        """
        self.btnRemoveTSD.setEnabled(self.SM is not None and len(self.SM.selectedRows()) > 0)

    def selectedTimeSeriesDates(self):
        """
        Returns the TimeSeriesDatum selected by a user.
        :return: [list-of-TimeSeriesDatum]
        """
        if self.SM is not None:
            return [self.TSM.data(idx, Qt.UserRole) for idx in self.SM.selectedRows()]
        return []

    def setTimeSeries(self, TS):
        """
        Sets the TimeSeries to be shown in the TimeSeriesDockUI
        :param TS: TimeSeries
        """
        from timeseriesviewer.timeseries import TimeSeries
        self.TS = TS
        self.TSM = None
        self.SM = None
        self.timeSeriesInitialized = False

        if isinstance(TS, TimeSeries):
            from timeseriesviewer.timeseries import TimeSeriesTableModel
            self.TSM = TimeSeriesTableModel(self.TS)
            self.tableView_TimeSeries.setModel(self.TSM)
            self.SM = QItemSelectionModel(self.TSM)
            self.tableView_TimeSeries.setSelectionModel(self.SM)
            self.SM.selectionChanged.connect(self.onSelectionChanged)
            self.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
            TS.sigLoadingProgress.connect(self.setProgressInfo)

        self.onSelectionChanged()


class TimeSeries(QObject):
    """
    The sorted list of data sources that specify the time series
    """

    sigTimeSeriesDatesAdded = pyqtSignal(list)
    sigTimeSeriesDatesRemoved = pyqtSignal(list)
    sigLoadingProgress = pyqtSignal(int, int, str)
    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigRuntimeStats = pyqtSignal(dict)

    def __init__(self, imageFiles=None, maskFiles=None):
        QObject.__init__(self)

        #define signals

        #fire when a new TSD is added


        #self.data = collections.OrderedDict()
        self.data = list()


        self.shape = None

        self.Sensors = collections.OrderedDict()

        self.Pool = None

        if imageFiles is not None:
            self.addFiles(imageFiles)
        if maskFiles is not None:
            self.addMasks(maskFiles)

    _sep = ';'

    def sensors(self):
        """
        Returns the list of sensors derived from the TimeSeries data soures
        :return: [list-of-SensorInstruments]
        """
        return list(self.Sensors.keys())

    def loadFromFile(self, path, n_max=None):
        """
        Loads a CSV file with source images of a TimeSeries
        :param path: str, Path of CSV file
        :param n_max: optional, maximum number of files to load
        """

        images = []
        masks = []
        with open(path, 'r') as f:
            lines = f.readlines()
            for l in lines:
                if re.match('^[ ]*[;#&]', l):
                    continue

                parts = re.split('[\n'+TimeSeries._sep+']', l)
                parts = [p for p in parts if p != '']
                images.append(parts[0])
                if len(parts) > 1:
                    masks.append(parts[1])

        if n_max:
            n_max = min([len(images), n_max])
            self.addFiles(images[0:n_max])
        else:
            self.addFiles(images)
        #self.addMasks(masks)


    def saveToFile(self, path):
        """
        Saves the TimeSeries sources into a CSV file
        :param path: str, path of CSV file
        :return: path of CSV file
        """
        if path is None or len(path) == 0:
            return None

        lines = []
        lines.append('#Time series definition file: {}'.format(np.datetime64('now').astype(str)))
        lines.append('#<image path>')
        for TSD in self.data:

            line = TSD.pathImg
            lines.append(line)

        lines = [l+'\n' for l in lines]


        with open(path, 'w') as f:
            f.writelines(lines)
            messageLog('Time series source images written to {}'.format(path))

        return path

    def getPixelSizes(self):
        """
        Returns the pixel sizes of all SensorInstruments
        :return: [list-of-QgsRectangles]
        """

        r = []
        for sensor in self.Sensors.keys():
            r.append((QgsRectangle(sensor.px_size_x, sensor.px_size_y)))
        return r

        return None

    def getMaxSpatialExtent(self, crs=None):
        """
        Returns the maximum SpatialExtent of all images of the TimeSeries
        :param crs: QgsCoordinateSystem to express the SpatialExtent coordinates.
        :return:
        """
        if len(self.data) == 0:
            return None

        extent = self.data[0].spatialExtent()
        assert isinstance(extent, SpatialExtent)
        if len(self.data) > 1:
            for TSD in self.data[1:]:
                extent.combineExtentWith(TSD.spatialExtent())
                x, y = extent.upperRight()
                if y > 0:
                    s =""
        if isinstance(crs, QgsCoordinateReferenceSystem):
            extent = extent.toCrs(crs)
        return extent

    def getObservationDates(self):
        """
        Returns the observations dates of ecach TimeSeries data source
        :return: [list-of-numpy.datetime64]
        """
        return [tsd.getDate() for tsd in self.data]

    def getTSD(self, pathOfInterest):
        """
        Returns the TimeSeriesDatum related to an image source
        :param pathOfInterest: str, image source uri
        :return: TimeSeriesDatum
        """
        for tsd in self.data:
            if tsd.pathImg == pathOfInterest:
                return tsd
        return None

    def getTSDs(self, dateOfInterest=None, sensorOfInterest=None):
        """
        Returns a list of  TimeSeriesDatum of the TimeSeries. By default all TimeSeriesDatum will be returned.
        :param dateOfInterest: numpy.datetime64 to return the TimeSeriesDatum for
        :param sensorOfInterest: SensorInstrument of interest to return the [list-of-TimeSeriesDatum] for.
        :return: [list-of-TimeSeriesDatum]
        """
        tsds = self.data[:]
        if dateOfInterest:
            tsds = [tsd for tsd in tsds if tsd.getDate() == dateOfInterest]
        if sensorOfInterest:
            tsds = [tsd for tsd in tsds if tsd.sensor == sensorOfInterest]
        return tsds

    def clear(self):
        """
        Removes all data sources from the TimeSeries (which will be empty after calling this routine).
        """
        self.removeDates(self[:])



    def removeDates(self, TSDs):
        """
        Removes a list of TimeSeriesDatum
        :param TSDs: [list-of-TimeSeriesDatum]
        """
        removed = list()
        for TSD in TSDs:
            assert type(TSD) is TimeSeriesDatum
            self.data.remove(TSD)
            TSD.createTimeSeries = None
            removed.append(TSD)

            S = TSD.sensor
            self.Sensors[S].remove(TSD)
            if len(self.Sensors[S]) == 0:
                self.Sensors.pop(S)
                self.sigSensorRemoved.emit(S)

        self.sigTimeSeriesDatesRemoved.emit(removed)


    def addTimeSeriesDates(self, timeSeriesDates):
        """
        Adds a list of TimeSeriesDatum
        :param timeSeriesDates: [list-of-TimeSeriesDatum]
        """
        assert isinstance(timeSeriesDates, list)
        added = list()
        for TSD in timeSeriesDates:
            assert isinstance(TSD, TimeSeriesDatum)
            try:
                sensorAdded = False
                existingSensors = list(self.Sensors.keys())
                if TSD.sensor not in existingSensors:
                    self.Sensors[TSD.sensor] = list()
                    sensorAdded = True
                else:
                    TSD.sensor = existingSensors[existingSensors.index(TSD.sensor)]

                if TSD in self.data:
                    print('Time series date-time already added ({} {}). \nPlease use VRTs to mosaic images with same acquisition date-time.'.format(str(TSD), TSD.pathImg), file=sys.stderr)
                else:
                    self.Sensors[TSD.sensor].append(TSD)
                    #insert sorted

                    bisect.insort(self.data, TSD)
                    TSD.timeSeries = self
                    TSD.sigRemoveMe.connect(lambda : self.removeDates([TSD]))
                    added.append(TSD)
                if sensorAdded:
                    self.sigSensorAdded.emit(TSD.sensor)

            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2)

                pass

        if len(added) > 0:
            self.sigTimeSeriesDatesAdded.emit(added)


    def addFiles(self, files):
        """
        Adds new data sources to the TimeSeries
        :param files: [list-of-str]
        """
        if isinstance(files, str):
            files = [files]
        assert isinstance(files, list)
        files = [f for f in files if f is not None]

        nMax = len(files)
        nDone = 0
        self.sigLoadingProgress.emit(0, nMax, 'Start loading {} files...'.format(nMax))

        for i, file in enumerate(files):
            t0 = np.datetime64('now')
            tsd = TimeSeriesDatum.createFromPath(file)
            if tsd is None:
                msg = 'Unable to add: {}'.format(os.path.basename(file))
                messageLog(msg)
            else:
                self.addTimeSeriesDates([tsd])
                msg = 'Added {}'.format(os.path.basename(file))
                self.sigRuntimeStats.emit({'dt_addTSD':np.datetime64('now')-t0})
            nDone += 1
            self.sigLoadingProgress.emit(nDone, nMax, msg)


    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, slice):
        return self.data[slice]

    def __delitem__(self, slice):
        self.removeDates(slice)

    def __contains__(self, item):
        return item in self.data

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))


        return '\n'.join(info)



class TimeSeriesTableModel(QAbstractTableModel):

    def __init__(self, TS, parent=None, *args):

        super(TimeSeriesTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)

        self.cnDate = 'Date'
        self.cnSensor = 'Sensor'
        self.cnNS = 'ns'
        self.cnNL = 'nl'
        self.cnNB = 'nb'
        self.cnCRS = 'CRS'
        self.cnImage = 'Image'
        self.mColumnNames = [self.cnDate, self.cnSensor, \
                            self.cnNS, self.cnNL, self.cnNB, \
                            self.cnCRS, self.cnImage]
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


    def tsdChanged(self, tsd):
        idx = self.getIndexFromDate(tsd)
        self.dataChanged.emit(idx, idx)

    def sensorsChanged(self, sensor):
        i = self.mColumnNames.index(self.cnSensor)
        idx0 = self.createIndex(0, i)
        idx1 = self.createIndex(self.rowCount(), i)
        self.dataChanged.emit(idx0, idx1)

    def addTSDs(self, tsds):

        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDatum)
            row = bisect.bisect_left(self.items, tsd)
            self.beginInsertRows(QModelIndex(), row, row)
            self.items.insert(row, tsd)
            self.endInsertRows()

            #self.sort(self.sortColumnIndex, self.sortOrder)

        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDatum)
            tsd.sigVisibilityChanged.connect(lambda: self.tsdChanged(tsd))

        for sensor in set([tsd.sensor for tsd in tsds]):
            if sensor not in self.sensors:
                self.sensors.add(sensor)
                sensor.sigNameChanged.connect(self.sensorsChanged)



    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.mColumnNames[col]
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
        return len(self.mColumnNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumnNames[index.column()]

        TSD = self.getTimeSeriesDatumFromIndex(index)
        assert isinstance(TSD, TimeSeriesDatum)
        keys = list(TSD.__dict__.keys())


        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if columnName == self.cnImage:
                value = os.path.basename(TSD.pathImg)
            elif columnName == self.cnSensor:
                if role == Qt.ToolTipRole:
                    value = TSD.sensor.getDescription()
                else:
                    value = TSD.sensor.name()
            elif columnName == self.cnDate:
                value = '{}'.format(TSD.date)
            elif columnName == self.cnImage:
                value = TSD.pathImg
            elif columnName == self.cnCRS:
                crs = TSD.crs
                assert isinstance(crs, QgsCoordinateReferenceSystem)
                value = crs.description()
            elif columnName in keys:
                value = TSD.__dict__[columnName]
            else:
                s = ""
        elif role == Qt.CheckStateRole:
            if columnName == self.cnDate:
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

        columnName = self.mColumnNames[index.column()]

        TSD = self.getTimeSeriesDatumFromIndex(index)
        if columnName == self.cnDate and role == Qt.CheckStateRole:
            TSD.setVisibility(value != Qt.Unchecked)
            return True
        else:
            return False

        return False

    def flags(self, index):
        if index.isValid():
            columnName = self.mColumnNames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName == self.cnDate: #allow check state
                flags = flags | Qt.ItemIsUserCheckable

            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None


def getSpatialPropertiesFromDataset(ds):
    assert isinstance(ds, gdal.Dataset)

    nb = ds.RasterCount
    nl = ds.RasterYSize
    ns = ds.RasterXSize
    proj = ds.GetGeoTransform()
    px_x = float(abs(proj[1]))
    px_y = float(abs(proj[5]))

    crs = QgsCoordinateReferenceSystem(ds.GetProjection())

    return nb, nl, ns, crs, px_x, px_y











def parseWavelengthFromDataSet(ds):
    assert isinstance(ds, gdal.Dataset)
    wl = None
    wlu = None

    #see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
    regWLkey = re.compile('.*wavelength[_ ]*$', re.I)
    regWLUkey = re.compile('.*wavelength[_ ]*units?$', re.I)
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)", re.I)
    regWLU = re.compile('((micro|nano|centi)meters)|(um|nm|mm|cm|m|GHz|MHz)', re.I)
    for domain in ds.GetMetadataDomainList():
        md = ds.GetMetadata_Dict(domain)
        for key, value in md.items():
            if wl is None and regWLkey.search(key):
                numbers = regNumeric.findall(value)
                if len(numbers) == ds.RasterCount:
                    wl = [float(n) for n in numbers]

            if wlu is None and regWLUkey.search(key):
                match = regWLU.search(value)
                if match:
                    wlu = match.group().lower()
                names = ['nanometers', 'micrometers', 'millimeters', 'centimeters', 'decimeters']
                si = ['nm', 'um', 'mm', 'cm', 'dm']
                if wlu in names:
                    wlu = si[names.index(wlu)]

    return wl, wlu



def parseWavelength(lyr):
    wl = None
    wlu = None
    assert isinstance(lyr, QgsRasterLayer)
    md = [l.split('=') for l in str(lyr.metadata()).splitlines() if 'wavelength' in l.lower()]
    #see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
    regWLU = re.compile('((micro|nano|centi)meters)|(um|nm|mm|cm|m|GHz|MHz)')
    for kv in md:
        key, value = kv
        key = key.lower()
        if key == 'center wavelength':
            tmp = re.findall(r'\d*\.\d+|\d+', value) #find floats
            if len(tmp) == 0:
                tmp = re.findall(r'\d+', value) #find integers
            if len(tmp) == lyr.bandCount():
                wl = [float(w) for w in tmp]

        if key == 'wavelength units':
            match = regWLU.search(value)
            if match:
                wlu = match.group()

            names = ['nanometers','micrometers','millimeters','centimeters','decimenters']
            si   = ['nm','um','mm','cm','dm']
            if wlu in names:
                wlu = si[names.index(wlu)]

    return wl, wlu

if __name__ == '__main__':
    q  = QApplication([])
    p = QProgressBar()
    p.setRange(0,0)

    p.show()
    q.exec_()

    print(convertMetricUnit(100, 'cm', 'm'))
    print(convertMetricUnit(1, 'm', 'um'))