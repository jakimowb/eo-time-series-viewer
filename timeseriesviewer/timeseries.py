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

import sys, re, collections, traceback, time, json, urllib, types


import bisect

from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *


from osgeo import gdal
from timeseriesviewer.dateparser import DOYfromDatetime64
from timeseriesviewer.utils import SpatialExtent, loadUI, px2geo

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

GDAL_DATATYPES = {}
for var in vars(gdal):
    match = re.search(r'^GDT_(?P<type>.*)$', var)
    if match:
        number = getattr(gdal, var)
        GDAL_DATATYPES[match.group('type')] = number
        GDAL_DATATYPES[match.group()] = number


METRIC_EXPONENTS = {
    "nm": -9, "um": -6, "mm": -3, "cm": -2, "dm": -1, "m": 0, "hm": 2, "km": 3
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


def getDS(pathOrDataset)->gdal.Dataset:
    """
    Returns a gdal.Dataset
    :param pathOrDataset: str | gdal.Dataset | QgsRasterLayer
    :return:
    """
    if isinstance(pathOrDataset, QgsRasterLayer):
        return getDS(pathOrDataset.source())
    elif isinstance(pathOrDataset, gdal.Dataset):
        return pathOrDataset
    elif isinstance(pathOrDataset, str):
        ds = gdal.Open(pathOrDataset)
        assert isinstance(ds, gdal.Dataset)
        return ds



def sensorID(nb:int, px_size_x:float, px_size_y:float, dt:int, wl:list, wlu:str)->str:
    """
    Create a sensor ID
    :param nb: number of bands
    :param px_size_x: pixel size x
    :param px_size_y: pixel size y
    :param wl: list of wavelength
    :param wlu: str, wavelength unit
    :return: str
    """
    assert dt in GDAL_DATATYPES.values()
    assert isinstance(nb, int) and nb > 0
    assert isinstance(px_size_x, (int, float)) and px_size_x > 0
    assert isinstance(px_size_y, (int, float)) and px_size_y > 0

    if wl != None:
        assert isinstance(wl, list)
        assert len(wl) == nb

    if wlu != None:
        assert isinstance(wlu, str)

    return json.dumps((nb, px_size_x, px_size_y, dt, wl, wlu))

def sensorIDtoProperties(idString:str)->tuple:
    """
    Reads a sensor id string and returns the sensor properties. See sensorID().
    :param idString: str
    :return: (ns, px_size_x, px_size_y, [wl], wlu)
    """
    nb, px_size_x, px_size_y, dt, wl, wlu = json.loads(idString)
    assert isinstance(dt, int) and dt >= 0
    assert isinstance(nb, int)
    assert isinstance(px_size_x, (int,float)) and px_size_x > 0
    assert isinstance(px_size_y, (int, float)) and px_size_y > 0
    if wl != None:
        assert isinstance(wl, list)
    if wlu != None:
        assert isinstance(wlu, str)

    return nb, px_size_x, px_size_y, dt, wl, wlu



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

    def __init__(self, sid:str, sensor_name:str=None, band_names:list = None):
        super(SensorInstrument, self).__init__()

        self.mId = sid

        self.nb, self.px_size_x, self.px_size_y, self.dataType, self.wl, self.wlu = sensorIDtoProperties(self.mId)

        if not isinstance(band_names, list):
            band_names = ['Band {}'.format(b+1) for b in range(self.nb)]

        assert len(band_names) == self.nb
        self.bandNames = band_names
        self.wlu = self.wlu
        if self.wl is None:
            self.wl = None
        else:
            self.wl = np.asarray(self.wl)

        if sensor_name is None:
            sensor_name = '{}bands@{}m'.format(self.nb, self.px_size_x)
            sensor_name = SETTINGS.value(self._sensorSettingsKey(), sensor_name)
        self.mName = ''
        self.setName(sensor_name)

        self.hashvalue = hash(self.mId)

        from .utils import TestObjects
        import uuid
        path = '/vsimem/mockupImage.{}.bsq'.format(uuid.uuid4())
        self.mMockupDS = TestObjects.inMemoryImage(path=path, nb=self.nb, eType=self.dataType, ns=2, nl=2)
        self.mMockupLayer = QgsRasterLayer(self.mMockupDS.GetFileList()[0])


    def mockupLayer(self)->QgsRasterLayer:

        #create an in-memory data set
        return self.mMockupLayer

    def id(self)->str:
        return self.mId

    def _sensorSettingsKey(self):
        return SensorInstrument.SensorNameSettingsPrefix+self.mId

    def setName(self, name:str):
        """
        Sets the sensor/product name
        :param name: str
        """
        if name != self.mName:
            self.mName = name
            SETTINGS.setValue(self._sensorSettingsKey(), name)
            self.sigNameChanged.emit(self.name())

    def name(self)->str:
        """
        Returns the sensor name
        :return: str
        """
        return self.mName

    def __eq__(self, other):
        if not isinstance(other, SensorInstrument):
            return False
        return self.mId == other.mId

    def __hash__(self):
        return hash(self.id())

    def __repr__(self):
        return str(self.__class__) +' ' + self.name()

    def description(self)->str:
        """
        Returns a human-readable description
        :return: str
        """
        info = []
        info.append(self.name())
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tName\tWavelength')
        for b in range(self.nb):
            if self.wl is not None:
                wl = str(self.wl[b])
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



class TimeSeriesSource(object):
    """Provides some information on source images"""


    @staticmethod
    def create(source):
        """
        Reads the argument and returns a TimeSeriesSource
        :param source: gdal.Dataset, str, QgsRasterLayer
        :return: TimeSeriesSource
        """
        ds = None
        if isinstance(source, QgsRasterLayer):
            lyr = source
            provider = lyr.providerType()

            if provider == 'gdal':
                ds = gdal.Open(lyr.source())
            elif provider == 'wcs':
                parts = urllib.parse.parse_qs(lyr.source())
                url = re.search(r'^[^?]+', parts['url'][0]).group()
                identifier = re.search(r'^[^?]+', parts['identifier'][0]).group()

                uri2 = 'WCS:{}?coverage={}'.format(url, identifier)
                ds = gdal.Open(uri2)

                if not isinstance(ds, gdal.Dataset) or ds.RasterCount == 0:
                    dsGetCoverage = gdal.Open('WCS:{}'.format(url))
                    for subdatasetUrl, id in dsGetCoverage.GetSubDatasets():
                        if id == identifier:
                            ds = gdal.Open(subdatasetUrl)
                            break

            else:


                raise Exception('Unsupported raster data provider: {}'.format(provider))

        elif isinstance(source, str):
            ds = gdal.Open(source)

        elif isinstance(source, gdal.Dataset):
            ds = source

        else:
            raise Exception('Unsupported source: {}'.format(source))

        return TimeSeriesSource(ds)



    def __init__(self, dataset:gdal.Dataset):

        assert isinstance(dataset, gdal.Dataset)
        assert dataset.RasterCount > 0
        assert dataset.RasterYSize > 0
        assert dataset.RasterXSize > 0
        self.mUri = dataset.GetFileList()[0]

        self.mDate = parseDateFromDataSet(dataset)
        assert self.mDate is not None, 'Unable to find acquisition date of {}'.format(self.mUri)

        self.mDrv = dataset.GetDriver().ShortName
        self.mGT = dataset.GetGeoTransform()
        self.mWKT = dataset.GetProjection()
        self.mCRS = QgsCoordinateReferenceSystem(self.mWKT)

        self.mWL, self.mWLU = extractWavelengths(dataset)


        self.nb, self.nl, self.ns = dataset.RasterCount, dataset.RasterYSize, dataset.RasterXSize
        self.mGeoTransform = dataset.GetGeoTransform()
        px_x = float(abs(self.mGeoTransform[1]))
        px_y = float(abs(self.mGeoTransform[5]))
        self.mGSD = (px_x, px_y)
        self.mDataType = dataset.GetRasterBand(1).DataType
        self.mSid = sensorID(self.nb, px_x, px_y, self.mDataType, self.mWL, self.mWLU)

        self.mMetaData = collections.OrderedDict()
        for domain in dataset.GetMetadataDomainList():
            self.mMetaData[domain] = dataset.GetMetadata_Dict(domain)

        self.mUL = QgsPointXY(*px2geo(QPoint(0, 0), self.mGeoTransform, pxCenter=False))
        self.mLR = QgsPointXY(*px2geo(QPoint(self.ns + 1, self.nl + 1), self.mGeoTransform, pxCenter=False))


    def name(self)->str:
        """
        Returns a name for this data source
        :return:
        """
        bn = os.path.basename(self.uri())
        return '{} {}'.format(bn, self.date())


    def uri(self)->str:
        """
        URI that can be used with GDAL to open a dataset
        :return: str
        """
        return self.mUri

    def qgsMimeDataUtilsUri(self)->QgsMimeDataUtils.Uri:
        uri = QgsMimeDataUtils.Uri()
        uri.name = self.name()
        uri.providerKey = 'gdal'
        uri.uri = self.uri()
        uri.layerType = 'raster'
        return uri

    def sid(self)->str:
        """
        Returns the sensor id
        :return: str
        """
        return self.mSid

    def date(self)->np.datetime64:
        return self.mDate

    def crs(self)->QgsCoordinateReferenceSystem:
        return self.mCRS

    def spatialExtent(self)->SpatialExtent:
        return SpatialExtent(self.mCRS, self.mUL, self.mLR)

    def __eq__(self, other):
        if not isinstance(other, TimeSeriesSource):
            return False
        return self.mUri == other.mUri


class TimeSeriesDatum(QObject):

    sigVisibilityChanged = pyqtSignal(bool)
    sigRemoveMe = pyqtSignal()
    sigSourcesChanged = pyqtSignal()




    def __init__(self, timeSeries, date:np.datetime64, sensor:SensorInstrument):
        """
        Constructor
        :param timeSeries: TimeSeries, parent TimeSeries instance, optional
        :param date: np.datetime64,
        :param sensor: SensorInstrument
        """
        super(TimeSeriesDatum,self).__init__()
        assert isinstance(date, np.datetime64)
        assert isinstance(sensor, SensorInstrument)
        self.mSensor = sensor
        self.mDate = date
        self.mDOY = DOYfromDatetime64(self.mDate)
        self.mSources = []
        self.mMasks = []
        self.mVisibility = True
        self.mTimeSeries = timeSeries




    def addSource(self, source):
        """
        Adds an time series source to this TimeSeriesDatum
        :param path: TimeSeriesSource or any argument accepted by TimeSeriesSource.create()
        :return: TimeSeriesSource, if added
        """

        if not isinstance(source, TimeSeriesSource):
            return self.addSource(TimeSeriesSource.create(source))
        else:
            assert isinstance(source, TimeSeriesSource)
            assert self.mDate == source.date()
            assert self.mSensor.id() == source.sid()
            if source not in self.mSources:
                self.mSources.append(source)
                self.sigSourcesChanged.emit()
                return source
            else:
                return None



    def setVisibility(self, b:bool):
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

    def sensor(self)->SensorInstrument:
        """
        Returns the SensorInstrument
        :return: SensorInsturment
        """
        return self.mSensor

    def sources(self)->list:
        """
        Returns the source images
        :return: [list-of-TimeSeriesSource]
        """
        return self.mSources


    def sourceUris(self)->list:
        """
        Returns all source URIs  as list of strings-
        :return: [list-of-str]
        """
        return [tss.uri() for tss in self.sources()]

    def qgsMimeDataUtilsUris(self)->list:
        """
        Returns all source URIs as list of QgsMimeDataUtils.Uri
        :return: [list-of-QgsMimedataUtils.Uris]
        """
        return [s.qgsMimeDataUtilsUri() for s in self.sources()]

    def date(self)->np.datetime64:
        """
        Returns the observation date
        :return: numpy.datetime64
        """
        return np.datetime64(self.mDate)

    def doy(self)->int:
        """
        Returns the day of Year (DOY)
        :return: int
        """
        return int(self.mDOY)

    def spatialExtent(self):
        """
        Returns the SpatialExtent of all data sources
        :return: SpatialExtent
        """
        ext = None
        for i, tss in enumerate(self.sources()):
            assert isinstance(tss, TimeSeriesSource)
            if i == 0:
                ext = tss.spatialExtent()
            else:
                ext.combineExtentWith(tss.spatialExtent())
        return ext

    def imageBorders(self)->QgsGeometry:
        """
        Retunrs the exact border polygon
        :return: QgsGeometry
        """

        return None

    def __repr__(self):
        return 'TimeSeriesDatum({},{})'.format(self.mDate, str(self.mSensor))

    def __eq__(self, other):
        return self.mDate == other.date and self.mSensor.id() == other.sensor.id()

    def __len__(self):
        return len(self.mSources)



    def __lt__(self, other):
        assert isinstance(other, TimeSeriesDatum)
        if self.date() < other.date():
            return True
        elif self.date() > other.date():
            return False
        else:
            return self.sensor().id() < other.sensor().id()

    def id(self):
        """
        :return:
        """
        return (self.mDate, self.mSensor.id())


    def mimeDataUris(self)->list:
        """
        Returns the sources of this TSD as list of QgsMimeDataUtils.Uris
        :return: [list-of-QgsMimeDataUtils]
        """
        results = []
        for tss in self.sources():
            assert isinstance(tss, TimeSeriesSource)

        [tss.uri() for tss in self.sources()]

    def __hash__(self):
        return hash(self.id())


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
    sigSourcesChanged = pyqtSignal(TimeSeriesDatum)
    sigRuntimeStats = pyqtSignal(dict)

    def __init__(self, imageFiles=None, maskFiles=None):
        QObject.__init__(self)
        self.mTSDs = list()
        self.mSensors = []
        self.mShape = None

        if imageFiles is not None:
            self.addSources(imageFiles)
        if maskFiles is not None:
            self.addMasks(maskFiles)

    _sep = ';'

    def sensor(self, sid:str)->SensorInstrument:
        """
        Returns the sensor with sid = sid
        :param sid: str, sensor id
        :return: SensorInstrument
        """
        assert isinstance(sid, str)
        for sensor in self.mSensors:
            assert isinstance(sensor, SensorInstrument)
            if sensor.id() == sid:
                return sensor
        return None


    def sensors(self)->list:
        """
        Returns the list of sensors derived from the TimeSeries data sources
        :return: [list-of-SensorInstruments]
        """
        return self.mSensors[:]

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
            self.addSources(images[0:n_max])
        else:
            self.addSources(images)
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
        for TSD in self.mTSDs:

            line = TSD.pathImg
            lines.append(line)

        lines = [l+'\n' for l in lines]


        with open(path, 'w') as f:
            f.writelines(lines)
            messageLog('Time series source images written to {}'.format(path))

        return path

    def pixelSizes(self):
        """
        Returns the pixel sizes of all SensorInstruments
        :return: [list-of-QgsRectangles]
        """

        r = []
        for sensor in self.mSensors2TSDs.keys():
            r.append((QgsRectangle(sensor.px_size_x, sensor.px_size_y)))
        return r


    def maxSpatialExtent(self, crs=None)->SpatialExtent:
        """
        Returns the maximum SpatialExtent of all images of the TimeSeries
        :param crs: QgsCoordinateSystem to express the SpatialExtent coordinates.
        :return:
        """
        extent = None
        for i, tsd in enumerate(self.mTSDs):
            assert isinstance(tsd, TimeSeriesDatum)
            ext = tsd.spatialExtent()
            if isinstance(extent, SpatialExtent):
                extent = extent.combineExtentWith(ext)
            else:
                extent = ext

        return extent

    def getTSD(self, pathOfInterest):
        """
        Returns the TimeSeriesDatum related to an image source
        :param pathOfInterest: str, image source uri
        :return: TimeSeriesDatum
        """
        for tsd in self.mTSDs:
            assert isinstance(tsd, TimeSeriesDatum)
            if pathOfInterest in tsd.pathImg:
                return tsd
        return None

    def tsd(self, date:np.datetime64, sensor)->TimeSeriesDatum:
        """
        Returns the TimeSeriesDatum identified by ate nd sensorID
        :param date:
        :param sensor: SensorInstrument | str with sensor id
        :return:
        """
        assert isinstance(date, np.datetime64)
        if isinstance(sensor, str):
            sensor = self.sensor(sensor)
        if isinstance(sensor, SensorInstrument):
            for tsd in self.mTSDs:
                if tsd.date() == date and tsd.sensor() == sensor:
                    return tsd
        return None

    def insertTSD(self, tsd:TimeSeriesDatum)->TimeSeriesDatum:
        """
        Inserts a TimeSeriesDatum
        :param tsd: TimeSeriesDatum
        """
        #insert sorted by time & sensor
        assert tsd not in self.mTSDs
        assert tsd.sensor() in self.mSensors
        bisect.insort(self.mTSDs, tsd)
        tsd.mTimeSeries = self
        tsd.sigRemoveMe.connect(lambda: self.removeTSDs([tsd]))
        tsd.sigSourcesChanged.connect(lambda: self.sigSourcesChanged.emit(tsd))

        return tsd

    def removeTSDs(self, tsds):
        """
        Removes a list of TimeSeriesDatum
        :param tsds: [list-of-TimeSeriesDatum]
        """
        removed = list()
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDatum)
            assert tsd in self.mTSDs
            self.mTSDs.remove(tsd)
            tsd.mTimeSeries = None
            removed.append(tsd)
        self.sigTimeSeriesDatesRemoved.emit(removed)




    def tsds(self, date:np.datetime64=None, sensor:SensorInstrument=None)->list:

        """
        Returns a list of  TimeSeriesDatum of the TimeSeries. By default all TimeSeriesDatum will be returned.
        :param date: numpy.datetime64 to return the TimeSeriesDatum for
        :param sensor: SensorInstrument of interest to return the [list-of-TimeSeriesDatum] for.
        :return: [list-of-TimeSeriesDatum]
        """
        tsds = self.mTSDs[:]
        if date:
            tsds = [tsd for tsd in tsds if tsd.date() == date]
        if sensor:
            tsds = [tsd for tsd in tsds if tsd.sensor == sensor]
        return tsds

    def clear(self):
        """
        Removes all data sources from the TimeSeries (which will be empty after calling this routine).
        """
        self.removeTSDs(self[:])






    def addSensor(self, sensor:SensorInstrument):
        """
        Adds a Sensor
        :param sensor: SensorInstrument
        """

        if not sensor in self.mSensors:
            self.mSensors.append(sensor)
            self.sigSensorAdded.emit(sensor)
            return sensor
        else:
            return None

    def checkSensorList(self):
        """
        Removes sensors without linked TSD / no data
        """
        to_remove = []
        for sensor in self.sensors():
            tsds = [tsd for tsd in self.mTSDs if tsd.sensor() == sensor]
            if len(tsds) == 0:
                to_remove.append(sensor)
        for sensor in to_remove:
            self.removeSensor(sensor)

    def removeSensor(self, sensor:SensorInstrument)->SensorInstrument:
        """
        Removes a sensor and all linked images
        :param sensor: SensorInstrument
        :return: SensorInstrument or none, if sensor was not defined in the TimeSeries
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            tsds = [tsd for tsd in self.mTSDs if tsd.sensor() == sensor]
            self.removeTSDs(tsds)
            self.mSensors.remove(sensor)
            self.sigSensorRemoved.emit(sensor)
            return sensor
        return None


    def addSources(self, sources:list):
        """
        Adds new data sources to the TimeSeries
        :param sources: [list-of-TimeSeriesSources]
        """
        assert isinstance(sources, (list, types.GeneratorType))

        nMax = len(sources)

        self.sigLoadingProgress.emit(0, nMax, 'Start loading {} sources...'.format(nMax))

        # 1. read sources
        # this could be excluded into a parallel process
        addedDates = []
        for i, source in enumerate(sources):

            msg = None
            try:
                tss = None
                if not isinstance(source, TimeSeriesSource):
                    tss = TimeSeriesSource.create(source)
                else:
                    tss = source

                assert isinstance(tss, TimeSeriesSource)

                date = tss.date()
                sid = tss.sid()
                sensor = self.sensor(sid)

                #if necessary, add a new sensor instance
                if not isinstance(sensor, SensorInstrument):
                    sensor = self.addSensor(SensorInstrument(sid))
                assert isinstance(sensor, SensorInstrument)

                tsd = self.tsd(date, sensor)

                #if necessary, add a new TimeSeriesDatum instance
                if not isinstance(tsd, TimeSeriesDatum):
                    tsd = self.insertTSD(TimeSeriesDatum(self, date, sensor))
                    addedDates.append(tsd)
                assert isinstance(tsd, TimeSeriesDatum)

                #add the source
                tsd.addSource(tss)
                s = ""

            except Exception as ex:
                msg = 'Unable to add: {}\n{}'.format(str(source), str(ex))
                print(msg, file=sys.stderr)
            self.sigLoadingProgress.emit(i+1, nMax, msg)
        if len(addedDates) > 0:
            self.sigTimeSeriesDatesAdded.emit(addedDates)

    def __len__(self):
        return len(self.mTSDs)

    def __iter__(self):
        return iter(self.mTSDs)

    def __getitem__(self, slice):
        return self.mTSDs[slice]

    def __delitem__(self, slice):
        self.removeTSDs(slice)

    def __contains__(self, item):
        return item in self.mTSDs

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))


        return '\n'.join(info)



class TimeSeriesTableModel(QAbstractTableModel):

    def __init__(self, TS:TimeSeries, parent=None, *args):

        super(TimeSeriesTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)

        self.cnDate = 'Date'
        self.cnSensor = 'Sensor'
        self.cnNS = 'ns'
        self.cnNL = 'nl'
        self.cnNB = 'nb'
        self.cnCRS = 'CRS'
        self.cnImage = 'Images'
        self.mColumnNames = [self.cnDate, self.cnSensor, \
                            self.cnNS, self.cnNL, self.cnNB, \
                            self.cnCRS, self.cnImage]
        self.mTimeSeries = TS
        self.mSensors = set()
        self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self.removeTSDs)
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.addTSDs)


        self.items = []
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        self.addTSDs([tsd for tsd in self.mTimeSeries])

    def removeTSDs(self, tsds):
        #self.TS.removeDates(tsds)
        for tsd in tsds:
            if tsd in self.mTimeSeries:
                #remove from TimeSeries first.
                self.mTimeSeries.removeTSDs([tsd])
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

        for sensor in set([tsd.sensor() for tsd in tsds]):
            if sensor not in self.mSensors:
                self.mSensors.add(sensor)
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


    def rowCount(self, parent = QModelIndex())->int:
        return len(self.items)


    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self.items[row:row+count]
        for tsd in toRemove:
            self.items.remove(tsd)
        self.endRemoveRows()

    def getIndexFromDate(self, tsd:TimeSeriesDatum)->QModelIndex:
        assert isinstance(tsd, TimeSeriesDatum)
        return self.createIndex(self.items.index(tsd),0)

    def getDateFromIndex(self, index:QModelIndex)->TimeSeriesDatum:
        assert isinstance(index, QModelIndex)
        if index.isValid():
            return self.items[index.row()]
        return None

    def getTimeSeriesDatumFromIndex(self, index:QModelIndex)->TimeSeriesDatum:
        assert isinstance(index, QModelIndex)
        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.items):
                return self.items[i]

        return None

    def columnCount(self, parent = QModelIndex())->int:
        return len(self.mColumnNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumnNames[index.column()]

        TSD = self.getTimeSeriesDatumFromIndex(index)
        assert isinstance(TSD, TimeSeriesDatum)
        keys = list(TSD.__dict__.keys())
        tssList = TSD.sources()

        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if columnName == self.cnImage:
                value = [os.path.basename(tss.uri()) for tss in tssList]
            elif columnName == self.cnSensor:
                if role == Qt.ToolTipRole:
                    value = TSD.sensor().description()
                else:
                    value = TSD.sensor().name()
            elif columnName == self.cnDate:
                value = '{}'.format(TSD.date())
            elif columnName == self.cnImage:
                value = '\n'.join(TSD.sourceUris())
            elif columnName == self.cnCRS:
                value = '\n'.join([tss.crs().description() for tss in tssList])
            elif columnName == self.cnNB:
                value = TSD.sensor().nb
            elif columnName == self.cnNL:
                value = ','.join([str(tss.nl) for tss in tssList])
            elif columnName == self.cnNS:
                value = ','.join([str(tss.ns) for tss in tssList])
            elif columnName == self.cnSensor:
                value = TSD.sensor().name()

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











def extractWavelengths(ds):
    wl = None
    wlu = None

    # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
    regWLkey = re.compile('.*wavelength[_ ]*$', re.I)
    regWLUkey = re.compile('.*wavelength[_ ]*units?$', re.I)
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)", re.I)
    regWLU = re.compile('((micro|nano|centi)meters)|(um|nm|mm|cm|m|GHz|MHz)', re.I)

    if isinstance(ds, QgsRasterLayer):
        lyr = ds
        md = [l.split('=') for l in str(lyr.metadata()).splitlines() if 'wavelength' in l.lower()]
        #see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
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
    elif isinstance(ds, gdal.Dataset):

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


if __name__ == '__main__':
    q  = QApplication([])
    p = QProgressBar()
    p.setRange(0,0)

    p.show()
    q.exec_()

    print(convertMetricUnit(100, 'cm', 'm'))
    print(convertMetricUnit(1, 'm', 'um'))