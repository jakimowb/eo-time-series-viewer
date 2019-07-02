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

import sys, re, collections, traceback, time, json, urllib, types, enum, typing, pickle, json, uuid


import bisect

from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *


from osgeo import gdal
from eotimeseriesviewer.dateparser import DOYfromDatetime64
from eotimeseriesviewer.utils import SpatialExtent, loadUI, px2geo

gdal.SetConfigOption('VRT_SHARED_SOURCE', '0') #!important. really. do not change this.

import numpy as np

from eotimeseriesviewer import messageLog
from eotimeseriesviewer.dateparser import parseDateFromDataSet

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

    LUT_Wavelengths = dict({'B': 480,
                            'G': 570,
                            'R': 660,
                            'nIR': 850,
                            'swIR': 1650,
                            'swIR1': 1650,
                            'swIR2': 2150
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
            import eotimeseriesviewer.settings
            sensor_name = eotimeseriesviewer.settings.value(self._sensorSettingsKey(), sensor_name)
        self.mName = ''
        self.setName(sensor_name)

        self.hashvalue = hash(self.mId)

        from eotimeseriesviewer.tests import TestObjects
        import uuid
        path = '/vsimem/mockupImage.{}.bsq'.format(uuid.uuid4())
        self.mMockupDS = TestObjects.inMemoryImage(path=path, nb=self.nb, eType=self.dataType, ns=2, nl=2)

    def proxyLayer(self)->QgsRasterLayer:
        """
        Creates an "empty" layer that can be used as proxy for band names, data types and render styles
        :return: QgsRasterLayer
        """
        lyr = SensorProxyLayer(self.mMockupDS.GetFileList()[0], name=self.name(), sensor=self)
        lyr.nameChanged.connect(lambda l=lyr: self.setName(l.name()))
        lyr.setCustomProperty('eotsv/sensorid', self.id())
        self.sigNameChanged.connect(lyr.setName)
        return lyr

    def id(self)->str:
        """
        Returns the Sensor id
        :return: str
        """
        return self.mId

    def _sensorSettingsKey(self):
        return SensorInstrument.SensorNameSettingsPrefix+self.mId

    def setName(self, name: str):
        """
        Sets the sensor/product name
        :param name: str
        """
        if name != self.mName:
            self.mName = name
            import eotimeseriesviewer.settings
            eotimeseriesviewer.settings.setValue(self._sensorSettingsKey(), name)
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



class SensorProxyLayer(QgsRasterLayer):

    def __init__(self, *args, sensor:SensorInstrument, **kwds):
        super(SensorProxyLayer, self).__init__(*args, **kwds)
        self.mSensor = sensor

    def sensor(self)->SensorInstrument:
        """
        Returns the SensorInstrument this layer relates to
        :return: SensorInstrument
        """
        return self.mSensor

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

    from eotimeseriesviewer.dateparser import parseDateFromDataSet
    date = parseDateFromDataSet(datasource)
    if date is None:
        return False

    return True



class TimeSeriesSource(object):
    """Provides some information on source images"""

    @staticmethod
    def fromJson(jsonData:str):
        """
        Returs a TimeSeriesSource from its JSON representation
        :param json:
        :return:
        """
        source = TimeSeriesSource(None)
        state = json.loads(jsonData)
        source.__setstatedictionary(state)
        return source

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

    def __init__(self, dataset:gdal.Dataset=None):

        self.mUri = None
        self.mDrv = None
        self.mGT = None
        self.mWKT = None
        self.mCRS = None
        self.mWL = None
        self.mWLU = None
        self.nb = self.ns = self.nl = None
        self.mGeoTransform = None
        self.mGSD = None
        self.mDataType = None
        self.mSid = None
        self.mMetaData = None
        self.mUL = self.LR = None

        self.mTimeSeriesDatum = None

        if isinstance(dataset, gdal.Dataset):
            assert dataset.RasterCount > 0
            assert dataset.RasterYSize > 0
            assert dataset.RasterXSize > 0
            #self.mUri = dataset.GetFileList()[0]
            self.mUri = dataset.GetDescription()

            self.mDate = parseDateFromDataSet(dataset)
            assert self.mDate is not None, 'Unable to find acquisition date of {}'.format(self.mUri)

            self.mDrv = dataset.GetDriver().ShortName

            self.mWL, self.mWLU = extractWavelengths(dataset)


            self.nb, self.nl, self.ns = dataset.RasterCount, dataset.RasterYSize, dataset.RasterXSize
            self.mGeoTransform = dataset.GetGeoTransform()
            self.mMetaData = collections.OrderedDict()
            for domain in dataset.GetMetadataDomainList():
                self.mMetaData[domain] = dataset.GetMetadata_Dict(domain)

            self.mWKT = dataset.GetProjection()
            if self.mWKT == '':
                # no CRS? try with QGIS API
                lyr = QgsRasterLayer(self.mUri)
                if lyr.crs().isValid():
                    self.mWKT = lyr.crs().toWkt()

            self.mCRS = QgsCoordinateReferenceSystem(self.mWKT)

            px_x = float(abs(self.mGeoTransform[1]))
            px_y = float(abs(self.mGeoTransform[5]))
            self.mGSD = (px_x, px_y)
            self.mDataType = dataset.GetRasterBand(1).DataType
            self.mSid = sensorID(self.nb, px_x, px_y, self.mDataType, self.mWL, self.mWLU)


            self.mUL = QgsPointXY(*px2geo(QPoint(0, 0), self.mGeoTransform, pxCenter=False))
            self.mLR = QgsPointXY(*px2geo(QPoint(self.ns + 1, self.nl + 1), self.mGeoTransform, pxCenter=False))


    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __statedictionary(self):
        """
        Returns the internal state as serializable dictionary.

        :return: dict
        """
        state = dict()
        for name in dir(self):
            if re.search('^(n|m).+', name):
                value = getattr(self, name)
                if isinstance(value, (str, int, float, dict, list, tuple)):
                    state[name] = value
                elif isinstance(value, QgsPointXY):
                    state[name] = value.asWkt()
                elif isinstance(value, np.datetime64):
                    state[name] = str(value)
                elif name in ['mCRS', 'mTimeSeriesDatum']:
                    # will be derived from other variables
                    continue
                elif callable(value):
                    continue
                else:
                     s = ""
        return state

    def __setstatedictionary(self, state:dict):
        assert isinstance(state, dict)
        for k, v in state.items():
            self.__dict__[k] = v
        self.mCRS = QgsCoordinateReferenceSystem(self.mWKT)
        assert self.mCRS.isValid()
        self.mUL = QgsPointXY(QgsGeometry.fromWkt(self.mUL).asPoint())
        self.mLR = QgsPointXY(QgsGeometry.fromWkt(self.mLR).asPoint())
        self.mDate = np.datetime64(self.mDate)

    def __getstate__(self):

        dump = pickle.dumps(self.__statedictionary())
        return dump

    def __setstate__(self, state):
        d = pickle.loads(state)

        self.__setstatedictionary(d)

    def json(self)->str:
        """
        Returns a JSON representation
        :return:
        """
        return json.dumps(self.__statedictionary())

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

    def timeSeriesDatum(self):
        """
        Returns the parent TimeSeriesDatum (if set)
        :return: TimeSeriesDatum
        """
        return self.mTimeSeriesDatum

    def setTimeSeriesDatum(self, tsd):
        """
        Sets the parent TimeSeriesDatum
        :param tsd: TimeSeriesDatum
        """
        self.mTimeSeriesDatum = tsd

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


class TimeSeriesDatum(QAbstractTableModel):
    """
    A containe to store all image source related to a single observation date and sensor.
    """
    sigVisibilityChanged = pyqtSignal(bool)
    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)
    sigRemoveMe = pyqtSignal()
    
    
    cnUri = 'Source'
    cnNS = 'ns'
    cnNB = 'nb'
    cnNL = 'nl'
    cnCRS = 'crs'
    
    ColumnNames = [cnNB, cnNL, cnNS, cnCRS, cnUri]
    
    def __init__(self, timeSeries, date:np.datetime64, sensor:SensorInstrument):
        """
        Constructor
        :param timeSeries: TimeSeries, parent TimeSeries instance, optional
        :param date: np.datetime64,
        :param sensor: SensorInstrument
        """
        super(TimeSeriesDatum, self).__init__()
        
        assert isinstance(date, np.datetime64)
        assert isinstance(sensor, SensorInstrument)
        
        self.mSensor = sensor
        self.mDate = date
        self.mDOY = DOYfromDatetime64(self.mDate)
        self.mSources = []
        self.mMasks = []
        self.mVisibility = True
        self.mTimeSeries = timeSeries
    
    def removeSource(self, source:TimeSeriesSource):
        
        if source in self.mSources:
            i = self.mSources.index(source)
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mSources.remove(source)
            self.endRemoveRows()
            self.sigSourcesRemoved.emit([source])
        
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
            # assert self.mDate == source.date()
            assert self.mSensor.id() == source.sid()

            source.setTimeSeriesDatum(self)

            if source not in self.mSources:
                i = len(self)
                self.beginInsertRows(QModelIndex(), i, i)
                self.mSources.append(source)
                self.endInsertRows()
                self.sigSourcesAdded.emit([source])
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

    def decimalYear(self)->float:
        """
        Returns the observation date as decimal year (year + doy / (366+1) )
        :return: float
        """

        return self.year() + self.doy() / (366+1)

    def year(self)->int:
        """
        Returns the observation year
        :return: int
        """
        return self.mDate.astype(object).year

    def doy(self)->int:
        """
        Returns the day of Year (DOY)
        :return: int
        """
        return int(self.mDOY)

    def hasIntersectingSource(self, spatialExtent:SpatialExtent):
        for source in self:
            assert isinstance(source, TimeSeriesSource)
            ext = source.spatialExtent()
            if isinstance(ext, SpatialExtent):
                ext = ext.toCrs(spatialExtent.crs())
                if spatialExtent.intersects(ext):
                    return True
        return False


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

    def __repr__(self)->str:
        """
        String representation
        :return:
        """
        return 'TimeSeriesDatum({},{})'.format(str(self.mDate), str(self.mSensor))

    def __eq__(self, other)->bool:
        """
        Tow TimeSeriesDatum instances are equal if they have the same date, sensor and sources.
        :param other: TimeSeriesDatum
        :return: bool
        """
        if not isinstance(other, TimeSeriesDatum):
            return False
        return self.id() == other.id() and self.mSources == other.mSources


    def __contains__(self, item):
        return item in self.mSources

    def __getitem__(self, slice):
        return self.mSources[slice]

    def __iter__(self):
        """
        Iterator over all sources
        """
        return iter(self.mSources)

    def __len__(self)->int:
        """
        Returns the number of source images.
        :return: int
        """
        return len(self.mSources)

    def __lt__(self, other)->bool:
        """
        :param other: TimeSeriesDatum
        :return: bool
        """
        assert isinstance(other, TimeSeriesDatum)
        if self.date() < other.date():
            return True
        elif self.date() > other.date():
            return False
        else:
            return self.sensor().id() < other.sensor().id()
    
    def rowCount(self, parent: QModelIndex = QModelIndex()):
        
        return len(self)
    
    def columnCount(self, parent: QModelIndex):
        return len(TimeSeriesDatum.ColumnNames)
    
    def flags(self, index: QModelIndex):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return TimeSeriesDatum.ColumnNames[section]
        else:
            return None

    
    def data(self, index: QModelIndex, role: int ):
        
        if not index.isValid():
            return None
        
        tss = self.mSources[index.row()]
        assert isinstance(tss, TimeSeriesSource)
        
        cn = TimeSeriesDatum.ColumnNames[index.column()]
        if role == Qt.UserRole:
            return tss
        
        if role == Qt.DisplayRole:
            if cn == TimeSeriesDatum.cnNB:
                return tss.nb
            if cn == TimeSeriesDatum.cnNS:
                return tss.ns
            if cn == TimeSeriesDatum.cnNL:
                return tss.nl
            if cn == TimeSeriesDatum.cnCRS:
                return tss.crs().description()
            if cn == TimeSeriesDatum.cnUri:
                return tss.uri()
        
        return None   
            
        
    def id(self)->tuple:
        """
        :return: tuple
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


class TimeSeriesTreeView(QTreeView):

    sigMoveToDateRequest = pyqtSignal(TimeSeriesDatum)

    def __init__(self, parent=None):
        super(TimeSeriesTreeView, self).__init__(parent)

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        idx = self.indexAt(event.pos())
        tsd = self.model().data(idx, role=Qt.UserRole)

        menu = QMenu(self)
        a = menu.addAction('Copy value(s)')
        a.triggered.connect(lambda: self.onCopyValues())
        a = menu.addAction('Hide')
        a.setToolTip('Hides the selected dates.')
        a.triggered.connect(lambda: self.onSetCheckState(Qt.Checked))
        a = menu.addAction('Show')
        a.setToolTip('Shows the selected dates.')
        a.triggered.connect(lambda: self.onSetCheckState(Qt.Unchecked))
        if isinstance(tsd, TimeSeriesDatum):
            a = menu.addAction('Show {}'.format(tsd.date()))
            a.triggered.connect(lambda _, tsd=tsd: self.sigMoveToDateRequest.emit(tsd))

        menu.popup(QCursor.pos())

    def onSetCheckState(self, checkState):
        """
        Sets a ChecState to all selected rows
        :param checkState: Qt.CheckState
        """
        indices = self.selectionModel().selectedIndexes()
        rows = sorted(list(set([i.row() for i in indices])))
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            for r in rows:
                idx = model.index(r, 0)
                model.setData(idx, checkState, Qt.CheckStateRole)

    def onCopyValues(self, delimiter='\t'):
        """
        Copies selected cell values to the clipboard
        """
        indices = self.selectionModel().selectedIndexes()
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            from collections import OrderedDict
            R = OrderedDict()
            for idx in indices:
                if not idx.row() in R.keys():
                    R[idx.row()] = []
                R[idx.row()].append(model.data(idx, Qt.DisplayRole))
            info = []
            for k, values in R.items():
                info.append(delimiter.join([str(v) for v in values]))
            info = '\n'.join(info)
            QApplication.clipboard().setText(info)



class TimeSeriesTableView(QTableView):

    sigMoveToDateRequest = pyqtSignal(TimeSeriesDatum)

    def __init__(self, parent=None):
        super(TimeSeriesTableView, self).__init__(parent)

    def contextMenuEvent(self, event):
        """
        Creates and shows an QMenu
        :param event:
        """

        idx = self.indexAt(event.pos())
        tsd = self.model().data(idx, role=Qt.UserRole)


        menu = QMenu(self)
        a = menu.addAction('Copy value(s)')
        a.triggered.connect(lambda: self.onCopyValues())
        a = menu.addAction('Check')
        a.triggered.connect(lambda: self.onSetCheckState(Qt.Checked))
        a = menu.addAction('Uncheck')
        a.triggered.connect(lambda: self.onSetCheckState(Qt.Unchecked))
        if isinstance(tsd, TimeSeriesDatum):
            a = menu.addAction('Show {}'.format(tsd.date()))
            a.triggered.connect(lambda _, tsd=tsd: self.sigMoveToDateRequest.emit(tsd))

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
                idx = model.index(r, 0)
                model.setData(idx, checkState, Qt.CheckStateRole)

    def onCopyValues(self, delimiter='\t'):
        """
        Copies selected cell values to the clipboard
        """
        indices = self.selectionModel().selectedIndexes()
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            from collections import OrderedDict
            R = OrderedDict()
            for idx in indices:
                if not idx.row() in R.keys():
                    R[idx.row()] = []
                R[idx.row()].append(model.data(idx, Qt.DisplayRole))
            info = []
            for k, values in R.items():
                info.append(delimiter.join([str(v) for v in values]))
            info = '\n'.join(info)
            QApplication.clipboard().setText(info)
        s = ""



class DateTimePrecision(enum.Enum):
    """
    Describes the precision to pares DateTimeStamps.
    """

    Year = 'Y'
    Month = 'M'
    Week = 'W'
    Day = 'D'
    Hour = 'h'
    Minute = 'm'
    Second = 's'
    Milisecond = 'ms'
    Original = 0


def doLoadTimeSeriesSourcesTask(taskWrapper:QgsTask, dump):

    sources = pickle.loads(dump)
    assert isinstance(taskWrapper, QgsTask)

    results = []
    n = len(sources)
    for i, source in enumerate(sources):
        if taskWrapper.isCanceled():
            return pickle.dumps(results)
        s = TimeSeriesSource.create(source)
        if isinstance(s, TimeSeriesSource):
            results.append(s)

        taskWrapper.setProgress(float(i+1) / n * 100.0)
    return pickle.dumps(results)
    s = ""

class TimeSeries(QAbstractItemModel):
    """
    The sorted list of data sources that specify the time series
    """

    sigTimeSeriesDatesAdded = pyqtSignal(list)
    sigTimeSeriesDatesRemoved = pyqtSignal(list)
    sigLoadingProgress = pyqtSignal(int, int, str)


    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)

    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)



    _sep = ';'

    def __init__(self, imageFiles=None):
        super(TimeSeries, self).__init__()
        self.mTSDs = list()
        self.mSensors = []
        self.mShape = None
        self.mDateTimePrecision = DateTimePrecision.Original

        self.mCurrentDates = []
        self.mCurrentSpatialExtent = None

        self.cnDate = 'Date'
        self.cnSensor = 'Sensor'
        self.cnNS = 'ns'
        self.cnNL = 'nl'
        self.cnNB = 'nb'
        self.cnCRS = 'CRS'
        self.cnImages = 'Source Image(s)'
        self.mColumnNames = [self.cnDate, self.cnSensor,
                             self.cnNS, self.cnNL, self.cnNB,
                             self.cnCRS, self.cnImages]

        self.mRootIndex = QModelIndex()


        self.mTasks = list()

        if imageFiles is not None:
            self.addSources(imageFiles)

    def setCurrentSpatialExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the spatial extent currently shown
        :param spatialExtent:
        """
        if isinstance(spatialExtent, SpatialExtent) and self.mCurrentSpatialExtent != spatialExtent:
            self.mCurrentSpatialExtent = spatialExtent

            #
            #idx1 = self.index(0, 0)
            #idx2 = self.index(self.rowCount()-1, 0)
            #self.dataChanged.emit(idx1, idx2, [Qt.DecorationRole])

    def focusVisibilityToExtent(self):
        ext = self.currentSpatialExtent()
        if isinstance(ext, SpatialExtent):
            for tsd in self:
                assert isinstance(tsd, TimeSeriesDatum)
                b = tsd.hasIntersectingSource(ext)
                tsd.setVisibility(b)


    def currentSpatialExtent(self)->SpatialExtent:
        """
        Returns the current spatial extent
        :return: SpatialExtent
        """
        return self.mCurrentSpatialExtent

    def setCurrentDates(self, tsds:list):
        """
        Sets the TimeSeriesDates currently shown
        :param tsds: [list-of-TimeSeriesDatum]
        """


        self.mCurrentDates.clear()
        self.mCurrentDates.extend(tsds)
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDatum)
            if tsd in self:
                idx = self.tsdToIdx(tsd)
                # force reset of background color
                idx2 = self.index(idx.row(), self.columnCount()-1)
                self.dataChanged.emit(idx, idx2, [Qt.BackgroundColorRole])

    def sensor(self, sensorID:str)->SensorInstrument:
        """
        Returns the sensor with sid = sid
        :param sensorID: str, sensor id
        :return: SensorInstrument
        """
        assert isinstance(sensorID, str)
        for sensor in self.mSensors:
            assert isinstance(sensor, SensorInstrument)
            if sensor.id() == sensorID:
                return sensor
        return None


    def sensors(self)->list:
        """
        Returns the list of sensors derived from the TimeSeries data sources
        :return: [list-of-SensorInstruments]
        """
        return self.mSensors[:]

    def loadFromFile(self, path, n_max=None, progressDialog:QProgressDialog=None):
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
            self.addSourcesAsync(images[0:n_max], progressDialog=progressDialog)
        else:
            self.addSourcesAsync(images, progressDialog=progressDialog)
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
            assert isinstance(TSD, TimeSeriesDatum)
            for pathImg in TSD.sourceUris():
                lines.append(pathImg)

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
            if pathOfInterest in tsd.sourceUris():
                return tsd
        return None

    def tsd(self, date: np.datetime64, sensor)->TimeSeriesDatum:
        """
        Returns the TimeSeriesDatum identified by date and sensorID
        :param date: numpy.datetime64
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
        else:
            for tsd in self.mTSDs:
                if tsd.date() == date:
                    return tsd
        return None

    def insertTSD(self, tsd: TimeSeriesDatum)->TimeSeriesDatum:
        """
        Inserts a TimeSeriesDatum
        :param tsd: TimeSeriesDatum
        """
        #insert sorted by time & sensor
        assert tsd not in self.mTSDs
        assert tsd.sensor() in self.mSensors

        tsd.mTimeSeries = self
        tsd.sigRemoveMe.connect(lambda: self.removeTSDs([tsd]))
        tsd.rowsAboutToBeRemoved.connect(self.onSourcesAboutToBeRemoved)
        tsd.rowsRemoved.connect(self.onSourcesRemoved)
        tsd.rowsAboutToBeInserted.connect(self.onSourcesAboutToBeInserted)
        tsd.rowsInserted.connect(self.onSourcesInserted)
        tsd.sigSourcesAdded.connect(self.sigSourcesAdded)
        tsd.sigSourcesRemoved.connect(self.sigSourcesRemoved)

        row = bisect.bisect(self.mTSDs, tsd)
        self.beginInsertRows(self.mRootIndex, row, row)
        self.mTSDs.insert(row, tsd)
        self.endInsertRows()
        #self.rowsInserted()

        return tsd

    def onSourcesAboutToBeRemoved(self, parent, first, last):
        s = ""
        pass

    def onSourcesRemoved(self, parent, first, last):
        s = ""
    
    def onSourcesAboutToBeInserted(self, parent, first, last):
        s = ""
        
    def onSourcesInserted(self, parent, first, last):
        s = ""
        
  
    def removeTSDs(self, tsds):
        """
        Removes a list of TimeSeriesDatum
        :param tsds: [list-of-TimeSeriesDatum]
        """

        removed = list()
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDatum)
            row = self.mTSDs.index(tsd)
            self.beginRemoveRows(self.mRootIndex, row, row)
            self.mTSDs.remove(tsd)
            tsd.mTimeSeries = None
            removed.append(tsd)
            self.endRemoveRows()

        if len(removed) > 0:
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
            tsds = [tsd for tsd in tsds if tsd.sensor() == sensor]
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

    def addSourcesAsync(self, sources:list, nWorkers:int = 1, progressDialog:QProgressDialog=None):

        tm = QgsApplication.taskManager()
        assert isinstance(tm, QgsTaskManager)
        assert isinstance(nWorkers, int) and nWorkers >= 1


        # see https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
        def chunks(l, n):
            """Yield successive n-sized chunks from l."""
            for i in range(0, len(l), n):
                yield l[i:i + n]

        n = int(len(sources) / nWorkers)
        for subset in chunks(sources, 50):
        #for source in sources:
            #subset = [source]
            dump = pickle.dumps(subset)
            #taskDescription = 'Load EOTSV {} sources {}'.format(len(subset), uuid.uuid4())
            taskDescription = 'Load {} images'.format(len(subset))
            qgsTask = QgsTask.fromFunction(taskDescription, doLoadTimeSeriesSourcesTask, dump, on_finished=self.onAddSourcesAsyncFinished)
            self.mTasks.append(qgsTask)

            if False: # for debugging
                resultDump = doLoadTimeSeriesSourcesTask(qgsTask, dump)
                self.onAddSourcesAsyncFinished(None, resultDump)
            else:
                tm.addTask(qgsTask)

    def onAddSourcesAsyncFinished(self, *args):
        # print(':: onAddSourcesAsyncFinished')
        error = args[0]
        if error is None:
            try:
                addedDates = []
                dump = args[1]
                sources = pickle.loads(dump)
                for source in sources:
                    newTSD = self._addSource(source)
                    if isinstance(newTSD, TimeSeriesDatum):
                        addedDates.append(newTSD)

                if len(addedDates) > 0:
                    self.sigTimeSeriesDatesAdded.emit(addedDates)


            except Exception as ex:
                s = ""
        else:
            s = ""
        #self._cleanTasks()

    def _cleanTasks(self):
        toRemove = []
        for task in self.mTasks:
            if isinstance(task, QgsTask):
                if task.status() in [QgsTask.Complete, QgsTask.Terminated]:
                    toRemove.append(task)

        for t in toRemove:
            self.mTasks.remove(t)

    def addSources(self, sources:list, progressDialog:QProgressDialog=None):
        """
        Adds new data sources to the TimeSeries
        :param sources: [list-of-TimeSeriesSources]
        """
        assert isinstance(sources, list)

        nMax = len(sources)
        #self.sigTimeSeriesSourcesAboutToBeChanged.emit()

        self.sigLoadingProgress.emit(0, nMax, 'Start loading {} sources...'.format(nMax))
        
        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setRange(0, nMax)
            progressDialog.setLabelText('Load rasters...'.format(nMax))
        # 1. read sources
        # this could be excluded into a parallel process
        addedDates = []
        for i, source in enumerate(sources):
            newTSD = None
            msg = None
            if False: #debug
                newTSD = self._addSource(source)
            else:
                try:
                    newTSD = self._addSource(source)
                except Exception as ex:
                    msg = 'Unable to add: {}\n{}'.format(str(source), str(ex))
                    print(msg, file=sys.stderr)

            if isinstance(progressDialog, QProgressDialog):
                if progressDialog.wasCanceled():
                    break
                progressDialog.setValue(i)
                progressDialog.setLabelText('{}/{}'.format(i+1, nMax))

            if (i+1) % 10 == 0:
                self.sigLoadingProgress.emit(i+1, nMax, msg)

            if (i+1) % 50 == 0:
                QGuiApplication.processEvents()

            if isinstance(newTSD, TimeSeriesDatum):
                addedDates.append(newTSD)

        #if len(addedDates) > 0:

        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setLabelText('Create map widgets...')

        if len(addedDates) > 0:
            self.sigTimeSeriesDatesAdded.emit(addedDates)

    def _addSource(self, source:TimeSeriesSource)->TimeSeriesDatum:
        """
        :param source:
        :return: TimeSeriesDatum (if new created)
        """
        if isinstance(source, TimeSeriesSource):
            tss = source
        else:
            tss = TimeSeriesSource.create(source)

        assert isinstance(tss, TimeSeriesSource)

        newTSD = None

        tsdDate = self.date2date(tss.date())
        tssDate = tss.date()
        sid = tss.sid()
        sensor = self.sensor(sid)
        # if necessary, add a new sensor instance
        if not isinstance(sensor, SensorInstrument):
            sensor = self.addSensor(SensorInstrument(sid))
        assert isinstance(sensor, SensorInstrument)
        tsd = self.tsd(tsdDate, sensor)
        # if necessary, add a new TimeSeriesDatum instance
        if not isinstance(tsd, TimeSeriesDatum):
            tsd = self.insertTSD(TimeSeriesDatum(self, tsdDate, sensor))
            newTSD = tsd
            # addedDates.append(tsd)
        assert isinstance(tsd, TimeSeriesDatum)
        # add the source
        tsd.addSource(tss)
        return newTSD

    def setDateTimePrecision(self, mode:DateTimePrecision):
        """
        Sets the precision with which the parsed DateTime information will be handled.
        :param mode: TimeSeriesViewer:DateTimePrecision
        :return:
        """
        self.mDateTimePrecision = mode

        #do we like to update existing sources?




    def date2date(self, date:np.datetime64)->np.datetime64:
        """
        Converts a date of arbitrary precission into the date with precission according to the EOTSV settions.
        :param date: numpy.datetime64
        :return: numpy.datetime64
        """
        assert isinstance(date, np.datetime64)
        if self.mDateTimePrecision == DateTimePrecision.Original:
            return date
        else:
            date = np.datetime64(date, self.mDateTimePrecision.value)

        return date

    def sources(self) -> list:
        """
        Returns the input sources
        :return: iterator over [list-of-TimeSeriesSources]
        """

        for tsd in self:
            for source in tsd:
                yield source



    def sourceUris(self)->list:
        """
        Returns the uris of all sources
        :return: [list-of-str]
        """
        uris = []
        for tsd in self:
            assert isinstance(tsd, TimeSeriesDatum)
            uris.extend(tsd.sourceUris())
        return uris

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

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)

        if orientation == Qt.Horizontal and role == Qt.DisplayRole:

            if len(self.mColumnNames) > section:
                return self.mColumnNames[section]
            else:
                return ''

        else:
            return None

    def parent(self, index: QModelIndex) -> QModelIndex:
        """
        Returns the parent index of a QModelIndex `index`
        :param index: QModelIndex
        :return: QModelIndex
        """
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        tsd = None
        tss = None

        if isinstance(node, TimeSeriesDatum):
            return self.mRootIndex

        elif isinstance(node, TimeSeriesSource):
            tss = node
            tsd = node.timeSeriesDatum()
            return self.createIndex(self.mTSDs.index(tsd), 0, tsd)

    def rowCount(self, index: QModelIndex=None) -> int:
        """
        Return the row-count, i.e. number of child node for a TreeNode as index `index`.
        :param index: QModelIndex
        :return: int
        """
        if index is None:
            index = QModelIndex()

        if not index.isValid():
            return len(self)

        node = index.internalPointer()
        if isinstance(node, TimeSeriesDatum):
            return len(node)

        if isinstance(node, TimeSeriesSource):
            return 0


    def columnNames(self) -> list:
        """
        Returns the column names
        :return: [list-of-string]
        """
        return self.mColumnNames[:]

    def columnCount(self, index:QModelIndex = None) -> int:
        """
        Returns the number of columns
        :param index: QModelIndex
        :return:
        """

        return len(self.mColumnNames)


    def connectTreeView(self, treeView):
        self.mTreeView = treeView

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        if parent is None:
            parent = self.mRootIndex
        else:
            assert isinstance(parent, QModelIndex)

        if row < 0 or row >= len(self):
            return QModelIndex()
        if column < 0 or column >= len(self.mColumnNames):
            return QModelIndex()


        if parent == self.mRootIndex:
            # TSD node
            if row < 0 or row >= len(self):
                return QModelIndex()
            return self.createIndex(row, column, self[row])

        elif parent.parent() == self.mRootIndex:
            # TSS node
            tsd = self.tsdFromIdx(parent)
            if row < 0 or row >= len(tsd):
                return QModelIndex()
            return self.createIndex(row, column, tsd[row])

        return QModelIndex()

    def tsdToIdx(self, tsd:TimeSeriesDatum)->QModelIndex:
        """
        Returns an QModelIndex pointing on a TimeSeriesDatum of interest
        :param tsd: TimeSeriesDatum
        :return: QModelIndex
        """
        row = self.mTSDs.index(tsd)
        return self.index(row, 0)

    def tsdFromIdx(self, index: QModelIndex) -> TimeSeriesDatum:
        """
        Returns the TimeSeriesDatum related to an QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if index.row() == -1 and index.column() == -1:
            return None
        elif not index.isValid():
            return None
        else:
            node = index.internalPointer()
            if isinstance(node, TimeSeriesDatum):
                return node
            elif isinstance(node, TimeSeriesSource):
                return node.timeSeriesDatum()

        return None

    def data(self, index, role):
        """

        :param index: QModelIndex
        :param role: Qt.ItemRole
        :return: object
        """
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None

        node = index.internalPointer()
        tsd = None
        tss = None
        if isinstance(node, TimeSeriesSource):
            tsd = node.timeSeriesDatum()
            tss = node
        elif isinstance(node, TimeSeriesDatum):
            tsd = node

        if role == Qt.UserRole:
            return node

        cName = self.mColumnNames[index.column()]

        if isinstance(node, TimeSeriesSource):
            if role in [Qt.DisplayRole]:
                if cName == self.cnDate:
                    return str(tss.date())
                if cName == self.cnImages:
                    return tss.uri()
                if cName == self.cnNB:
                    return tss.nb
                if cName == self.cnNL:
                    return tss.nl
                if cName == self.cnNS:
                    return tss.ns
                if cName == self.cnCRS:
                    return tss.crs().description()

            if role == Qt.DecorationRole and index.column() == 0:

                return None

                ext = tss.spatialExtent()
                if isinstance(self.mCurrentSpatialExtent, SpatialExtent) and isinstance(ext, SpatialExtent):
                    ext = ext.toCrs(self.mCurrentSpatialExtent.crs())

                    b = isinstance(ext, SpatialExtent) and ext.intersects(self.mCurrentSpatialExtent)
                    if b:
                        return QIcon(r':/timeseriesviewer/icons/mapview.svg')
                    else:
                        return QIcon(r':/timeseriesviewer/icons/mapviewHidden.svg')
                else:
                    print(ext)
                    return None

            if role == Qt.BackgroundColorRole and tsd in self.mCurrentDates:
                return QColor('yellow')

        if isinstance(node, TimeSeriesDatum):
            if role in [Qt.DisplayRole]:
                if cName == self.cnSensor:
                    return tsd.sensor().name()
                if cName == self.cnImages:
                    return len(tsd)
                if cName == self.cnDate:
                    return str(tsd.date())

            if role == Qt.CheckStateRole and index.column() == 0:
                return Qt.Checked if tsd.isVisible() else Qt.Unchecked

            if role == Qt.BackgroundColorRole and tsd in self.mCurrentDates:
                return QColor('yellow')


        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int):

        if not index.isValid():
            return False

        result = False

        node = index.internalPointer()
        if isinstance(node, TimeSeriesDatum):
            if role == Qt.CheckStateRole and index.column() == 0:
                node.setVisibility(value == Qt.Checked)
                result = True

        if result == True:
            self.dataChanged.emit(index, index, [role])

        return result

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags
        #cName = self.mColumnNames.index(index.column())
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(index.internalPointer(), TimeSeriesDatum) and index.column() == 0:
            flags = flags | Qt.ItemIsUserCheckable
        return flags


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
        self.cnImages = 'Image(s)'
        self.mColumnNames = [self.cnDate, self.cnSensor,
                             self.cnNS, self.cnNL, self.cnNB,
                             self.cnCRS, self.cnImages]
        self.mTimeSeries = TS
        self.mSensors = set()
        self.mTimeSeries.sigTimeSeriesDatesRemoved.connect(self.removeTSDs)
        self.mTimeSeries.sigTimeSeriesDatesAdded.connect(self.addTSDs)

        self.items = []

        self.addTSDs([tsd for tsd in self.mTimeSeries])

    def timeSeries(self)->TimeSeries:
        """
        :return: TimeSeries
        """
        return self.mTimeSeries

    def removeTSDs(self, tsds:list):
        """
        Removes TimeSeriesDatum instances
        :param tsds: list
        """
        for tsd in tsds:
            if tsd in self.mTimeSeries:
                self.mTimeSeries.removeTSDs([tsd])
            elif tsd in self.items:
                idx = self.getIndexFromDate(tsd)
                self.removeRows(idx.row(), 1)

    def tsdChanged(self, tsd:TimeSeriesDatum):
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
            if columnName == self.cnSensor:
                if role == Qt.ToolTipRole:
                    value = TSD.sensor().description()
                else:
                    value = TSD.sensor().name()
            elif columnName == self.cnDate:
                value = '{}'.format(TSD.date())
            elif columnName == self.cnImages:
                value = '\n'.join(TSD.sourceUris())
            elif columnName == self.cnCRS:
                value = '\n'.join([tss.crs().description() for tss in tssList])
            elif columnName == self.cnNB:
                value = TSD.sensor().nb
            elif columnName == self.cnNL:
                value = '\n'.join([str(tss.nl) for tss in tssList])
            elif columnName == self.cnNS:
                value = '\n'.join([str(tss.ns) for tss in tssList])
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
            if columnName == self.cnDate: # allow check state
                flags = flags | Qt.ItemIsUserCheckable

            return flags
            # return item.qt_flags(index.column())
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



class TimeSeriesDockUI(QgsDockWidget, loadUI('timeseriesdock.ui')):
    """
    QgsDockWidget that shows the TimeSeries
    """
    def __init__(self, parent=None):
        super(TimeSeriesDockUI, self).__init__(parent)
        self.setupUi(self)

        #self.progressBar.setMinimum(0)
        #self.setProgressInfo(0, 100, 'Add images to fill time series')
        #self.progressBar.setValue(0)
        #self.progressInfo.setText(None)
        self.frameFilters.setVisible(False)

        self.mTimeSeries = None
        self.mSelectionModel = None


    def initActions(self, parent):

        from eotimeseriesviewer.main import TimeSeriesViewerUI
        assert isinstance(parent, TimeSeriesViewerUI)
        self.btnAddTSD.setDefaultAction(parent.actionAddTSD)
        self.btnRemoveTSD.setDefaultAction(parent.actionRemoveTSD)
        self.btnLoadTS.setDefaultAction(parent.actionLoadTS)
        self.btnSaveTS.setDefaultAction(parent.actionSaveTS)
        self.btnClearTS.setDefaultAction(parent.actionClearTS)


    def showTSD(self, tsd:TimeSeriesDatum):
        assert isinstance(self.timeSeriesTreeView, TimeSeriesTreeView)
        assert isinstance(self.mTSProxyModel, QSortFilterProxyModel)

        tsd.setVisibility(True)

        assert isinstance(self.mTimeSeries, TimeSeries)
        idxSrc = self.mTimeSeries.tsdToIdx(tsd)

        if isinstance(idxSrc, QModelIndex):
            idx2 = self.mTSProxyModel.mapFromSource(idxSrc)
            if isinstance(idx2, QModelIndex):
                self.timeSeriesTreeView.setCurrentIndex(idx2)
                self.timeSeriesTreeView.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

    def updateSummary(self):


        if isinstance(self.mTimeSeries, TimeSeries):
            if len(self.mTimeSeries) == 0:
                info = 'Empty Timeseries. Please add source images.'
            else:
                nDates = self.mTimeSeries.rowCount()
                nSensors = len(self.mTimeSeries.sensors())
                nImages = len(list(self.mTimeSeries.sources()))

                info = '{} dates, {} sensors, {} source images'.format(nDates, nSensors, nImages)
        else:
            info = ''
        self.summary.setText(info)

    def onSelectionChanged(self, *args):
        """
        Slot to react on user-driven changes of the selected TimeSeriesDatum rows.
        """

        self.btnRemoveTSD.setEnabled(
            isinstance(self.mSelectionModel, QItemSelectionModel) and
            len(self.mSelectionModel.selectedRows()) > 0)

    def selectedTimeSeriesDates(self)->list:
        """
        Returns the TimeSeriesDatum selected by a user.
        :return: [list-of-TimeSeriesDatum]
        """
        if isinstance(self.mSelectionModel, QItemSelectionModel):
            return [self.mTSProxyModel.data(idx, Qt.UserRole) for idx in self.mSelectionModel.selectedRows()]
        return []

    def setTimeSeries(self, TS:TimeSeries):
        """
        Sets the TimeSeries to be shown in the TimeSeriesDockUI
        :param TS: TimeSeries
        """
        from eotimeseriesviewer.timeseries import TimeSeries
        if isinstance(TS, TimeSeries):
            self.mTimeSeries = TS
            self.mTSProxyModel = QSortFilterProxyModel(self)
            self.mTSProxyModel.setSourceModel(self.mTimeSeries)
            self.mSelectionModel = QItemSelectionModel(self.mTSProxyModel)
            self.mSelectionModel.selectionChanged.connect(self.onSelectionChanged)


            self.timeSeriesTreeView.setModel(self.mTSProxyModel)
            self.timeSeriesTreeView.setSelectionModel(self.mSelectionModel)

            for c in range(self.mTSProxyModel.columnCount()):
                self.timeSeriesTreeView.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.mTimeSeries.rowsInserted.connect(self.updateSummary)
            #self.mTimeSeries.dataChanged.connect(self.updateSummary)
            self.mTimeSeries.rowsRemoved.connect(self.updateSummary)
            #TS.sigLoadingProgress.connect(self.setProgressInfo)

        self.onSelectionChanged()






if __name__ == '__main__':
    q = QApplication([])
    p = QProgressBar()
    p.setRange(0, 0)

    p.show()
    q.exec_()

    print(convertMetricUnit(100, 'cm', 'm'))
    print(convertMetricUnit(1, 'm', 'um'))