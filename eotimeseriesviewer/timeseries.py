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

import sys
import re
import collections
import traceback
import time
import json
import urllib
import types
import enum
import typing
import pickle
import json
import pathlib
import uuid
import bisect
from xml.etree import ElementTree

from qgis.PyQt.QtXml import QDomDocument


from qgis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *

from osgeo import osr, ogr, gdal, gdal_array
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.utils import relativePath

DEFAULT_WKT = QgsCoordinateReferenceSystem('EPSG:4326').toWkt()

LUT_WAVELENGTH_UNITS = {}
for siUnit in [r'nm', r'μm', r'mm', r'cm', r'dm']:
    LUT_WAVELENGTH_UNITS[siUnit] = siUnit
LUT_WAVELENGTH_UNITS[r'nanometers'] = r'nm'
LUT_WAVELENGTH_UNITS[r'micrometers'] = r'μm'
LUT_WAVELENGTH_UNITS[r'um'] = r'μm'
LUT_WAVELENGTH_UNITS[r'millimeters'] = r'mm'
LUT_WAVELENGTH_UNITS[r'centimeters'] = r'cm'
LUT_WAVELENGTH_UNITS[r'decimeters'] = r'dm'


from osgeo import gdal
from eotimeseriesviewer import LOG_MESSAGE_TAG
from eotimeseriesviewer.dateparser import DOYfromDatetime64
from eotimeseriesviewer.utils import SpatialExtent, loadUi, px2geo, geo2px, SpatialPoint

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


def getDS(pathOrDataset) -> gdal.Dataset:
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



def sensorID(nb:int, px_size_x:float, px_size_y:float, dt:int, wl:list, wlu:str, name:str) -> str:
    """
    Creates a sensor ID str
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

    if name != None:
        assert isinstance(name, str)
    jsonDict = {'nb': nb,
                'px_size_x': px_size_x,
                'px_size_y': px_size_y,
                'dt': dt,
                'wl': wl,
                'wlu': wlu,
                'name': name
                }
    return json.dumps(jsonDict)

def sensorIDtoProperties(idString:str) -> tuple:
    """
    Reads a sensor id string and returns the sensor properties. See sensorID().
    :param idString: str
    :return: (ns, px_size_x, px_size_y, [wl], wlu)
    """

    jsonDict = json.loads(idString)
    assert isinstance(jsonDict, dict)
    # must haves
    nb = jsonDict.get('nb')
    px_size_x = jsonDict.get('px_size_x')
    px_size_y = jsonDict.get('px_size_y')
    dt = jsonDict.get('dt')

    # can haves
    wl = jsonDict.get('wl', None)
    wlu = jsonDict.get('wlu', None)
    name = jsonDict.get('name', None)

    assert isinstance(dt, int) and dt >= 0
    assert isinstance(nb, int)
    assert isinstance(px_size_x, (int, float)) and px_size_x > 0
    assert isinstance(px_size_y, (int, float)) and px_size_y > 0
    if wl != None:
        assert isinstance(wl, list)
    if wlu != None:
        assert isinstance(wlu, str)
    if name != None:
        assert isinstance(name, str)
    return nb, px_size_x, px_size_y, dt, wl, wlu, name


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

    def __init__(self, sid:str, band_names:list = None):
        super(SensorInstrument, self).__init__()

        self.mId = sid
        self.nb:int
        self.px_size_x:float
        self.px_size_y:float
        self.dataType:int
        self.wl: list
        self.wlu: str
        self.nb, self.px_size_x, self.px_size_y, self.dataType, self.wl, self.wlu,  self.mNameOriginal = sensorIDtoProperties(self.mId)
        if self.mNameOriginal in [None, '']:
            self.mNameOriginal = '{}bands@{}m'.format(self.nb, self.px_size_x)

        self.mName = self.mNameOriginal
        import eotimeseriesviewer.settings
        storedName = eotimeseriesviewer.settings.sensorName(self.mId)
        if isinstance(storedName, str):
            self.mName = storedName

        if not isinstance(band_names, list):
            band_names = ['Band {}'.format(b+1) for b in range(self.nb)]

        assert len(band_names) == self.nb
        self.bandNames = band_names
        self.wlu = self.wlu
        if self.wl is None:
            self.wl = None
        else:
            self.wl = np.asarray(self.wl).tolist()

        self.hashvalue = hash(self.mId)

        from eotimeseriesviewer.tests import TestObjects
        import uuid
        path = '/vsimem/mockupImage.{}.bsq'.format(uuid.uuid4())
        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        self.mMockupDS = drv.Create(path, 2, 2, self.nb, eType=self.dataType)
        if self.wl is not None:
            self.mMockupDS.SetMetadataItem('wavelength', '{{{}}}'.format(','.join(str(wl) for wl in self.wl)))
        if self.wlu is not None:
            self.mMockupDS.SetMetadataItem('wavelength units', self.wlu)
        self.mMockupDS.FlushCache()
        s = ""

    def bandIndexClosestToWavelength(self, wl, wl_unit='nm') -> int:
        """
        Returns the band index closest to a certain wavelength
        :param wl: float | int
        :param wl_unit: str
        :return: int
        """
        from .utils import bandClosestToWavelength
        return bandClosestToWavelength(self.mMockupDS, wl, wl_unit=wl_unit)

    def proxyRasterLayer(self) -> QgsRasterLayer:
        """
        Creates an "empty" layer that can be used as proxy for band names, data types and render styles
        :return: QgsRasterLayer
        """
        lyr = SensorProxyLayer(self.mMockupDS.GetFileList()[0], name=self.name(), sensor=self)
        lyr.nameChanged.connect(lambda l=lyr: self.setName(l.name()))
        lyr.setCustomProperty('eotsv/sensorid', self.id())
        self.sigNameChanged.connect(lyr.setName)
        return lyr

    def id(self) -> str:
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
            assert isinstance(name, str)
            self.mName = name
            self.sigNameChanged.emit(self.name())

    def name(self) -> str:
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

    def description(self) -> str:
        """
        Returns a human-readable description
        :return: str
        """
        info = []
        info.append(self.name())
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tNAME\tWavelength')
        for b in range(self.nb):
            if self.wl is not None:
                wl = str(self.wl[b])
            else:
                wl = 'unknown'
            info.append('{}\t{}\t{}'.format(b + 1, self.bandNames[b], wl))

        return '\n'.join(info)


class SensorProxyLayer(QgsRasterLayer):

    def __init__(self, *args, sensor: SensorInstrument, **kwds):
        super(SensorProxyLayer, self).__init__(*args, **kwds)
        self.mSensor: SensorInstrument = sensor
        self.mTSS: TimeSeriesSource = None


    def sensor(self) -> SensorInstrument:
        """
        Returns the SensorInstrument this layer relates to
        :return: SensorInstrument
        """
        return self.mSensor

def verifyInputImage(datasource):
    """
    Checks if an image source can be uses as TimeSeriesDate, i.e. if it can be read by gdal.Open() and
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
    """Provides information on source images"""

    @classmethod
    def fromJson(cls, jsonData:str):
        """
        Returs a TimeSeriesSource from its JSON representation
        :param json:
        :return:
        """
        source = cls(None)
        state = json.loads(jsonData)
        source.__setstatedictionary(state)
        return source

    @classmethod
    def create(cls, source):
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
                s = ""
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
            s = ""

        elif isinstance(source, gdal.Dataset):
            ds = source

        if not isinstance(ds, gdal.Dataset):
            raise Exception('Unsupported source: {}'.format(source))

        srs = osr.SpatialReference()
        proj = ds.GetProjection()
        if proj in ['', None]:
            # try to find another SRS definition
            mdDict = ds.GetMetadata_Dict()
            if mdDict.get('lat#long_name') == 'latitude' and \
               mdDict.get('lon#long_name') == 'longitude':
                srs.ImportFromEPSG(4326)
                proj = srs.ExportToWkt()

        assert srs.ImportFromWkt(proj) == ogr.OGRERR_NONE, 'Can not read spatial reference from {}'.format(ds.GetDescription())

        return cls(ds)

    def __init__(self, dataset: gdal.Dataset = None):

        self.mIsVisible: bool = True
        self.mUri = None
        self.mDrv = None
        self.mWKT = None
        self.mCRS = None
        self.mWL = None
        self.mWLU = None
        self.nb: int = None
        self.ns: int = None
        self.nl: int = None
        self.mGeoTransform = None
        self.mGSD = None
        self.mDataType = None
        self.mSid = None
        self.mMetaData = None
        self.mUL = self.LR = None

        self.mSpatialExtent: SpatialExtent
        self.mSpatialExtent = None
        self.mTimeSeriesDate = None

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

            self.mWKT: str = dataset.GetProjection()
            if self.mWKT == '':
                # no CRS? try with QGIS API
                loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
                lyr = QgsRasterLayer(self.mUri, options=loptions)
                if lyr.crs().isValid():
                    self.mWKT = lyr.crs().toWkt()

            if self.mWKT == '':
                # default to WGS-84 lat lon
                self.mWKT = str(DEFAULT_WKT)

            self.mCRS = QgsCoordinateReferenceSystem(self.mWKT)

            px_x = float(abs(self.mGeoTransform[1]))
            px_y = float(abs(self.mGeoTransform[5]))
            self.mGSD = (px_x, px_y)
            self.mDataType = dataset.GetRasterBand(1).DataType

            sName = sensorName(dataset)
            self.mSidOriginal = self.mSid = sensorID(self.nb, px_x, px_y, self.mDataType, self.mWL, self.mWLU, sName)

            self.mUL = QgsPointXY(*px2geo(QPoint(0, 0), self.mGeoTransform, pxCenter=False))
            self.mLR = QgsPointXY(*px2geo(QPoint(self.ns, self.nl), self.mGeoTransform, pxCenter=False))

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
                elif name in ['mCRS', 'mTimeSeriesDate']:
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
        if not self.mCRS.isValid():
            srs = osr.SpatialReference()
            assert srs.ImportFromWkt(self.mCRS.toWkt()) == ogr.OGRERR_NONE, 'Unable to import spatial reference of {}'.format(self.mUri)
        self.mUL = QgsPointXY(QgsGeometry.fromWkt(self.mUL).asPoint())
        self.mLR = QgsPointXY(QgsGeometry.fromWkt(self.mLR).asPoint())
        self.mDate = np.datetime64(self.mDate)
        self.mSpatialExtent = None

    def __getstate__(self):

        dump = pickle.dumps(self.__statedictionary())
        return dump

    def __setstate__(self, state):
        d = pickle.loads(state)

        self.__setstatedictionary(d)

    def rasterUnitsPerPixelX(self) -> float:
        return abs(self.mGeoTransform[1])

    def rasterUnitsPerPixelY(self) -> float:
        return abs(self.mGeoTransform[5])

    def json(self) -> str:
        """
        Returns a JSON representation
        :return:
        """
        return json.dumps(self.__statedictionary())

    def name(self) -> str:
        """
        Returns a name for this data source
        :return:
        """
        bn = os.path.basename(self.uri())
        return '{} {}'.format(bn, self.date())


    def uri(self) -> str:
        """
        URI that can be used with GDAL to open a dataset
        :return: str
        """
        return self.mUri

    def qgsMimeDataUtilsUri(self) -> QgsMimeDataUtils.Uri:
        uri = QgsMimeDataUtils.Uri()
        uri.name = self.name()
        uri.providerKey = 'gdal'
        uri.uri = self.uri()
        uri.layerType = 'raster'
        return uri

    def asRasterLayer(self) -> QgsRasterLayer:
        lyr = QgsRasterLayer(self.uri(), self.name(), 'gdal')
        tprop: QgsRasterLayerTemporalProperties = lyr.temporalProperties()
        tprop.setMode(QgsRasterLayerTemporalProperties.ModeFixedTemporalRange)
        dtg = QDateTime(self.date().astype(object))
        tprop.setFixedTemporalRange(QgsDateTimeRange(dtg, dtg))
        return lyr

    def crsWkt(self) -> str:
        return self.mWKT

    def pixelCoordinate(self, geometry) -> QPoint:
        """

        :param QgsGeometry | QgsPoint | SpatialPoint:
        :return: QPoint, if coordinate interects with source raster, None else
        """

        if isinstance(geometry, QgsGeometry):
            geometry = geometry.asPoint()
        if isinstance(geometry, QgsPoint):
            geometry = QgsPointXY(geometry.x(), geometry.y())
        if isinstance(geometry, SpatialPoint):
            geometry = geometry.toCrs(self.crs())
        assert isinstance(geometry, QgsPointXY)
        px = geo2px(geometry, self.mGeoTransform)
        assert isinstance(px, QPoint)

        if px.x() < 0 or px.y() < 0 or px.x() >= self.ns or px.y() > self.nl:
            return None
        return px

    def sid(self) -> str:
        """
        Returns the sensor id
        :return: str
        """
        return self.mSid

    def timeSeriesDate(self):
        """
        Returns the parent TimeSeriesDate (if set)
        :return: TimeSeriesDate
        """
        return self.mTimeSeriesDate

    def setTimeSeriesDate(self, tsd):
        """
        Sets the parent TimeSeriesDate
        :param tsd: TimeSeriesDate
        """
        self.mTimeSeriesDate = tsd

    def date(self) -> np.datetime64:
        """
        Returns the date-time-group of the source image
        :return:
        :rtype:
        """
        return self.mDate

    def crs(self) -> QgsCoordinateReferenceSystem:
        """
        Returns the coordinate system as QgsCoordinateReferenceSystem
        :return:
        :rtype:
        """
        return self.mCRS

    def spatialExtent(self) -> SpatialExtent:
        """
        Returns the SpatialExtent
        :return:
        :rtype:
        """
        if not isinstance(self.mSpatialExtent, SpatialExtent):
            self.mSpatialExtent = SpatialExtent(self.mCRS, self.mUL, self.mLR)
        return self.mSpatialExtent

    def asDataset(self) -> gdal.Dataset:
        """
        Returns the source as gdal.Dataset
        :return:
        :rtype:
        """
        return gdal.Open(self.uri())

    def asArray(self) -> np.ndarray:
        """
        Returns the entire image as numpy array
        :return:
        :rtype:
        """
        return gdal_array.LoadFile(self.uri())

    def isVisible(self) -> bool:
        return self.mIsVisible

    def setIsVisible(self, b:bool):
        assert isinstance(b, bool)
        self.mIsVisible = b

    def __eq__(self, other):
        if not isinstance(other, TimeSeriesSource):
            return False
        return self.mUri == other.mUri

    def __lt__(self, other):
        assert isinstance(other, TimeSeriesSource)
        return self.date() < other.date()

    def __hash__(self):
        return hash(self.mUri)


class TimeSeriesDate(QAbstractTableModel):
    """
    A container to store all source images related to a single observation date and sensor.
    """
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
        super(TimeSeriesDate, self).__init__()
        
        assert isinstance(date, np.datetime64)
        assert isinstance(sensor, SensorInstrument)
        
        self.mSensor = sensor
        self.mDate = date
        self.mDOY = DOYfromDatetime64(self.mDate)
        self.mSources = []
        self.mMasks = []
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
        Adds an time series source to this TimeSeriesDate
        :param path: TimeSeriesSource or any argument accepted by TimeSeriesSource.create()
        :return: TimeSeriesSource, if added
        """

        if not isinstance(source, TimeSeriesSource):
            return self.addSource(TimeSeriesSource.create(source))
        else:
            assert isinstance(source, TimeSeriesSource)
            # assert self.mDate == source.date()
            assert self.mSensor.id() == source.sid()

            source.setTimeSeriesDate(self)

            if source not in self.mSources:
                i = len(self)
                self.beginInsertRows(QModelIndex(), i, i)
                self.mSources.append(source)
                self.endInsertRows()
                self.sigSourcesAdded.emit([source])
                return source
            else:
                return None

    def checkState(self) -> Qt.CheckState:
        """
        Returns the checkstate accorrding to the visibility of the TSDs TimeSeriesSources
        :return: Qt.CheckState
        """
        visible = [tss.isVisible() for tss in self]
        if all(visible):
            return Qt.Checked
        if any(visible):
            return Qt.PartiallyChecked
        return Qt.Unchecked


    def sensor(self) -> SensorInstrument:
        """
        Returns the SensorInstrument
        :return: SensorInsturment
        """
        return self.mSensor

    def sources(self) -> typing.List[TimeSeriesSource]:
        """
        Returns the source images
        :return: [list-of-TimeSeriesSource]
        """
        return self.mSources

    def sourceUris(self) -> typing.List[str]:
        """
        Returns all source URIs as list of strings-
        :return: [list-of-str]
        """
        return [tss.uri() for tss in self.sources()]

    def qgsMimeDataUtilsUris(self) -> list:
        """
        Returns all source URIs as list of QgsMimeDataUtils.Uri
        :return: [list-of-QgsMimedataUtils.Uris]
        """
        return [s.qgsMimeDataUtilsUri() for s in self.sources()]

    def date(self) -> np.datetime64:
        """
        Returns the observation date
        :return: numpy.datetime64
        """
        return np.datetime64(self.mDate)

    def decimalYear(self) -> float:
        """
        Returns the observation date as decimal year (year + doy / (366+1) )
        :return: float
        """

        return self.year() + self.doy() / (366+1)

    def year(self) -> int:
        """
        Returns the observation year
        :return: int
        """
        return self.mDate.astype(object).year

    def doy(self) -> int:
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

    def imageBorders(self) -> QgsGeometry:
        """
        Retunrs the exact border polygon
        :return: QgsGeometry
        """

        return None

    def __repr__(self) -> str:
        """
        String representation
        :return:
        """
        return 'TimeSeriesDate({},{})'.format(str(self.mDate), str(self.mSensor))

    def __eq__(self, other) -> bool:
        """
        Tow TimeSeriesDate instances are equal if they have the same date, sensor and sources.
        :param other: TimeSeriesDate
        :return: bool
        """
        if not isinstance(other, TimeSeriesDate):
            return False
        return self.id() == other.id() and self.mSources == other.mSources


    def __contains__(self, item):
        return item in self.mSources

    def __getitem__(self, slice):
        return self.mSources[slice]

    def __iter__(self) -> typing.Iterator[TimeSeriesSource]:
        """
        Iterator over all sources
        """
        return iter(self.mSources)

    def __len__(self) -> int:
        """
        Returns the number of source images.
        :return: int
        """
        return len(self.mSources)

    def __lt__(self, other) -> bool:
        """
        :param other: TimeSeriesDate
        :return: bool
        """
        assert isinstance(other, TimeSeriesDate)
        if self.date() < other.date():
            return True
        elif self.date() > other.date():
            return False
        else:
            return self.sensor().id() < other.sensor().id()
    
    def rowCount(self, parent: QModelIndex = QModelIndex()):
        
        return len(self)
    
    def columnCount(self, parent: QModelIndex):
        return len(TimeSeriesDate.ColumnNames)
    
    def flags(self, index: QModelIndex):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return TimeSeriesDate.ColumnNames[section]
        else:
            return None

    
    def data(self, index: QModelIndex, role: int ):
        
        if not index.isValid():
            return None
        
        tss = self.mSources[index.row()]
        assert isinstance(tss, TimeSeriesSource)
        
        cn = TimeSeriesDate.ColumnNames[index.column()]
        if role == Qt.UserRole:
            return tss
        
        if role == Qt.DisplayRole:
            if cn == TimeSeriesDate.cnNB:
                return tss.nb
            if cn == TimeSeriesDate.cnNS:
                return tss.ns
            if cn == TimeSeriesDate.cnNL:
                return tss.nl
            if cn == TimeSeriesDate.cnCRS:
                return tss.crs().description()
            if cn == TimeSeriesDate.cnUri:
                return tss.uri()
        
        return None   
            
        
    def id(self) -> tuple:
        """
        :return: tuple
        """
        return (self.mDate, self.mSensor.id())


    def mimeDataUris(self) -> list:
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

class SensorMatching(enum.Flag):
    """
    Describes when two different sources should be considered to be from the same sensor
    """


    PX_DIMS = enum.auto() #'Pixel Dimensions (GSD + Bands + Datatype)'
    WL = enum.auto()     #'Pixel Dims. + Wavelength'
    NAME = enum.auto()   #'Pixel Dims. + NAME'


    @staticmethod
    def name(flags) -> str:
        """
        Returns a description of the flag set
        :param flags:
        :type flags:
        :return:
        :rtype:
        """
        assert isinstance(flags, SensorMatching)
        parts = []
        if bool(flags & SensorMatching.PX_DIMS):
            parts.append('Pixel Dims.')
        if bool(flags & SensorMatching.WL):
            parts.append('Wavelength')
        if bool(flags & SensorMatching.NAME):
            parts.append('Name')

        if len(parts) == 0:
            return ''
        if len(parts) == 1 and bool(flags & SensorMatching.PX_DIMS):
            parts[0] = 'Pixel Dimensions (GSD + Bands + Datatype)'

        return ' + '.join(parts)

        assert isinstance(flags, SensorMatching)

    @staticmethod
    def tooltip(flags) -> str:
        """
        Returns a multi-line tooltip for the flag set
        :param flags:
        :type flags:
        :return:
        :rtype:
        """
        assert isinstance(flags, SensorMatching)
        parts = []
        if bool(flags & SensorMatching.PX_DIMS):
            parts.append('Source images of same sensor/product must have same ground sampling distance ("pixel size"), number of bands and data type.')
        if bool(flags & SensorMatching.WL):
            parts.append('Source images of same sensor/product must have same wavelength definition, e.g. nanometer value for each raster band.')
        if bool(flags & SensorMatching.NAME):
            parts.append('Source images of same sensor/product must have the same name, e.g. defined by a "sensor type = Landsat 8" metadata entry.')

        return '\n'.join(parts)


class TimeSeriesLoadingTask(QgsTask):

    sigFoundSources = pyqtSignal(list)
    sigMessage = pyqtSignal(str, bool)

    def __init__(self,
                 files: typing.List[str],
                 description: str = "Load Images",
                 callback = None,
                 block_size : int = 10):

        super().__init__(description=description)
        self.mFiles = files
        self.mSources = []
        self.mCallback = callback
        self.mResultBlockSize = block_size
        self.mInvalidSources = []

    def canCancel(self) -> bool:
        return True

    def run(self) -> bool:
        result_block = []
        n = len(self.mFiles)
        for i, path in enumerate(self.mFiles):
            assert isinstance(path, str)

            try:
                tss = TimeSeriesSource.create(path)
                assert isinstance(tss, TimeSeriesSource)
                self.mSources.append(tss)
                result_block.append(tss)
            except Exception as ex:
                self.mInvalidSources.append((path, ex))

            if len(result_block) >= self.mResultBlockSize:
                self.sigFoundSources.emit(result_block[:])
                result_block.clear()

            if self.isCanceled():
                return False

            self.setProgress(int(100 * (i+1) / n))

        if len(result_block) > 0:
            self.sigFoundSources.emit(result_block[:])
        return True

    def finished(self, result):
        if self.mCallback is not None:
            self.mCallback(result, self)

class TimeSeries(QAbstractItemModel):
    """
    The sorted list of data sources that specify the time series
    """

    sigTimeSeriesDatesAdded = pyqtSignal(list)
    sigTimeSeriesDatesRemoved = pyqtSignal(list)

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)

    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)

    sigVisibilityChanged = pyqtSignal()
    sigProgress = pyqtSignal(float)
    sigMessage = pyqtSignal(str, Qgis.MessageLevel)
    _sep = ';'

    def __init__(self, imageFiles=None):
        super(TimeSeries, self).__init__()
        self.mTSDs = list()
        self.mSensors = []
        self.mShape = None

        self.mDateTimePrecision = DateTimePrecision.Original
        self.mSensorMatchingFlags = SensorMatching.PX_DIMS

        self.mLUT_Path2TSD = {}
        self.mVisibleDate = []
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
        self.mTasks = dict()

        if imageFiles is not None:
            self.addSources(imageFiles)

    def setCurrentSpatialExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the spatial extent currently shown
        :param spatialExtent:
        """
        if isinstance(spatialExtent, SpatialExtent) and self.mCurrentSpatialExtent != spatialExtent:
            self.mCurrentSpatialExtent = spatialExtent

    def focusVisibilityToExtent(self, ext:SpatialExtent=None):
        """
        Changes TSDs visibility according to its intersection with a SpatialExtent
        :param ext: SpatialExtent
        """
        if ext is None:
            ext = self.currentSpatialExtent()
        if isinstance(ext, SpatialExtent):
            changed = False
            for tsd in self:
                assert isinstance(tsd, TimeSeriesDate)
                b = tsd.hasIntersectingSource(ext)
                if b != tsd.checkState():
                    changed = True
                tsd.setVisibility(b)

            if changed:
                ul = self.index(0, 0)
                lr = self.index(self.rowCount()-1, 0)
                self.dataChanged.emit(ul, lr, [Qt.CheckStateRole])
                self.sigVisibilityChanged.emit()

    def currentSpatialExtent(self) -> SpatialExtent:
        """
        Returns the current spatial extent
        :return: SpatialExtent
        """
        return self.mCurrentSpatialExtent

    def setVisibleDates(self, tsds:list):
        """
        Sets the TimeSeriesDates currently shown
        :param tsds: [list-of-TimeSeriesDate]
        """
        self.mVisibleDate.clear()
        self.mVisibleDate.extend(tsds)
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDate)
            if tsd in self:
                idx = self.tsdToIdx(tsd)
                # force reset of background color
                idx2 = self.index(idx.row(), self.columnCount()-1)
                self.dataChanged.emit(idx, idx2, [Qt.BackgroundColorRole])

    def findMatchingSensor(self, sensorID:str) -> SensorInstrument:
        if isinstance(sensorID, str):
            nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorIDtoProperties(sensorID)

        else:
            assert isinstance(sensorID, tuple) and len(sensorID) == 7
            nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorID

        PX_DIMS = (nb, px_size_y, px_size_x, dt)
        for sensor in self.sensors():
            PX_DIMS2 = (sensor.nb, sensor.px_size_y, sensor.px_size_x, sensor.dataType)

            samePxDims = PX_DIMS == PX_DIMS2
            sameName = sensor.mNameOriginal == name
            sameWL = wlu == sensor.wlu and np.array_equal(wl, sensor.wl)


            if bool(self.mSensorMatchingFlags & SensorMatching.PX_DIMS) and not samePxDims:
                continue

            if bool(self.mSensorMatchingFlags & SensorMatching.NAME) and not sameName:
                continue

            if bool(self.mSensorMatchingFlags & SensorMatching.WL) and not sameWL:
                continue

            return sensor

        return None

    def sensor(self, sensorID:str) -> SensorInstrument:
        """
        Returns the sensor with sid = sid
        :param sensorID: str, sensor id
        :return: SensorInstrument
        """
        assert isinstance(sensorID, str)

        nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorIDtoProperties(sensorID)

        refValues = (nb, px_size_y, px_size_x, dt, wl, wlu, name)
        for sensor in self.sensors():
            sValues = (sensor.nb, sensor.px_size_y, sensor.px_size_x, sensor.dataType, sensor.wl, sensor.wlu, sensor.mNameOriginal)
            if refValues == sValues:
                return sensor

        return None

    def sensors(self) -> typing.List[SensorInstrument]:
        """
        Returns the list of sensors derived from the TimeSeries data sources
        :return: [list-of-SensorInstruments]
        """
        return self.mSensors[:]

    def loadFromFile(self, path, n_max=None, runAsync:bool=True):
        """
        Loads a CSV file with source images of a TimeSeries
        :param path: str, Path of CSV file
        :param n_max: optional, maximum number of files to load
        """

        refDir = pathlib.Path(path).parent
        images = []
        masks = []
        with open(path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if re.match('^[ ]*[;#&]', line):
                    continue
                line = line.strip()
                path = pathlib.Path(line)
                if not path.is_absolute():
                    path = refDir / path

                images.append(path.as_posix())

        if n_max:
            n_max = min([len(images), n_max])
            images = images[0:n_max]

        self.addSources(images, runAsync=runAsync)

    def saveToFile(self, path, relative_path:bool = True):
        """
        Saves the TimeSeries sources into a CSV file
        :param path: str, path of CSV file
        :return: path of CSV file
        """
        if isinstance(path, str):
            path = pathlib.Path(path)
        assert isinstance(path, pathlib.Path)

        lines = []
        lines.append('#Time series definition file: {}'.format(np.datetime64('now').astype(str)))
        lines.append('#<image path>')
        for TSD in self:
            assert isinstance(TSD, TimeSeriesDate)
            for TSS in TSD:
                uri = TSS.uri()
                if relative_path:
                    uri = relativePath(uri, path.parent)
                lines.append(str(uri))

        with open(path, 'w', newline='\n', encoding='utf-8') as f:
            f.write('\n'.join(lines))
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


    def maxSpatialExtent(self, crs=None) -> SpatialExtent:
        """
        Returns the maximum SpatialExtent of all images of the TimeSeries
        :param crs: QgsCoordinateSystem to express the SpatialExtent coordinates.
        :return:
        """
        extent = None
        for i, tsd in enumerate(self.mTSDs):
            assert isinstance(tsd, TimeSeriesDate)
            ext = tsd.spatialExtent()
            if isinstance(extent, SpatialExtent):
                extent = extent.combineExtentWith(ext)
            else:
                extent = ext

        return extent

    def getTSD(self, pathOfInterest):
        """
        Returns the TimeSeriesDate related to an image source
        :param pathOfInterest: str, image source uri
        :return: TimeSeriesDate
        """
        tsd = self.mLUT_Path2TSD.get(pathOfInterest)
        if isinstance(tsd, TimeSeriesDate):
            return tsd
        else:
            for tsd in self.mTSDs:
                assert isinstance(tsd, TimeSeriesDate)
                if pathOfInterest in tsd.sourceUris():
                    return tsd
        return None

    def tsd(self, date: np.datetime64, sensor) -> TimeSeriesDate:
        """
        Returns the TimeSeriesDate identified by date and sensorID
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

    def insertTSD(self, tsd: TimeSeriesDate) -> TimeSeriesDate:
        """
        Inserts a TimeSeriesDate
        :param tsd: TimeSeriesDate
        """
        #insert sorted by time & sensor
        assert tsd not in self.mTSDs
        assert tsd.sensor() in self.mSensors

        tsd.mTimeSeries = self
        tsd.sigRemoveMe.connect(lambda tsd=tsd: self.removeTSDs([tsd]))

        tsd.rowsAboutToBeRemoved.connect(lambda p, first, last, tsd=tsd: self.beginRemoveRows(self.tsdToIdx(tsd), first, last))
        tsd.rowsRemoved.connect(self.endRemoveRows)
        tsd.rowsAboutToBeInserted.connect(lambda p, first, last, tsd=tsd: self.beginInsertRows(self.tsdToIdx(tsd), first, last))
        tsd.rowsInserted.connect(self.endInsertRows)
        tsd.sigSourcesAdded.connect(self.sigSourcesAdded)
        tsd.sigSourcesRemoved.connect(self.sigSourcesRemoved)

        row = bisect.bisect(self.mTSDs, tsd)
        self.beginInsertRows(self.mRootIndex, row, row)
        self.mTSDs.insert(row, tsd)
        self.endInsertRows()
        return tsd

    def showTSDs(self, tsds: list, b: bool = True):
        tsds = [t for t in tsds if t in self]

        col = 0
        idxMin = None
        idxMax = None
        for row, tsd in enumerate(self):
            assert isinstance(tsd, TimeSeriesDate)
            if tsd not in tsds:
                continue

            idx = self.index(row, col)
            if idxMin is None:
                idxMin = idxMax = idx
            else:
                idxMax = idx
            for source in tsd:
                source.setIsVisible(b)

        if isinstance(idxMin, QModelIndex):
            self.dataChanged.emit(idxMin, idxMax, [Qt.CheckStateRole])
            self.sigVisibilityChanged.emit()

    def hideTSDs(self, tsds):
        self.showTSDs(tsds, False)

    def removeTSDs(self, tsds):
        """
        Removes a list of TimeSeriesDate
        :param tsds: [list-of-TimeSeriesDate]
        """
        removed = list()
        toRemove = set()
        for t in tsds:
            if isinstance(t, TimeSeriesDate):
                toRemove.add(t)
            if isinstance(t, TimeSeriesSource):
                toRemove.add(t.timeSeriesDate())

        for tsd in list(sorted(list(toRemove), reverse=True)):

            assert isinstance(tsd, TimeSeriesDate)

            tsd.sigSourcesRemoved.disconnect()
            tsd.sigSourcesAdded.disconnect()
            tsd.sigRemoveMe.disconnect()

            row = self.mTSDs.index(tsd)
            self.beginRemoveRows(self.mRootIndex, row, row)
            self.mTSDs.remove(tsd)
            tsd.mTimeSeries = None
            removed.append(tsd)
            self.endRemoveRows()

        if len(removed) > 0:
            pathsToRemove = [path for path, tsd in self.mLUT_Path2TSD.items() if tsd in removed]
            for path in pathsToRemove:
                self.mLUT_Path2TSD.pop(path)

            self.checkSensorList()
            self.sigTimeSeriesDatesRemoved.emit(removed)

    def tsds(self, date:np.datetime64=None, sensor:SensorInstrument=None) -> typing.List[TimeSeriesDate]:

        """
        Returns a list of  TimeSeriesDate of the TimeSeries. By default all TimeSeriesDate will be returned.
        :param date: numpy.datetime64 to return the TimeSeriesDate for
        :param sensor: SensorInstrument of interest to return the [list-of-TimeSeriesDate] for.
        :return: [list-of-TimeSeriesDate]
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
        assert isinstance(sensor, SensorInstrument)
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

    def removeSensor(self, sensor:SensorInstrument) -> SensorInstrument:
        """
        Removes a sensor and all linked images
        :param sensor: SensorInstrument
        :return: SensorInstrument or none, if sensor was not defined in the TimeSeries
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            tsds = [tsd for tsd in self.mTSDs if tsd.sensor() == sensor]
            self.removeTSDs(tsds)
            if sensor in self.mSensors:
                self.mSensors.remove(sensor)
            self.sigSensorRemoved.emit(sensor)
            return sensor
        return None
    
    def addTimeSeriesSources(self, sources: typing.List[TimeSeriesSource]):
        assert isinstance(sources, list)

        addedDates = []
        for i, source in enumerate(sources):
            assert isinstance(source, TimeSeriesSource)
            newTSD = self.addTimeSeriesSource(source)
            if isinstance(newTSD, TimeSeriesDate):
                addedDates.append(newTSD)

        if len(addedDates) > 0:
            self.sigTimeSeriesDatesAdded.emit(addedDates)

    def addSources(self, sources:list, nWorkers:int = 1, runAsync:bool=True):
        """
        Adds source images to the TimeSeries
        :param sources: list of source images, e.g. a list of file paths
        :param nWorkers: not used yet
        :param runAsync: bool
        """
        sourcePaths = []
        for s in sources:
            path = None
            if isinstance(s, gdal.Dataset):
                path = s.GetDescription()
            elif isinstance(s, QgsRasterLayer):
                path = s.source()
            else:
                path = str(s)
            if path:
                sourcePaths.append(path)


        qgsTask = TimeSeriesLoadingTask(sourcePaths, callback=self.onTaskFinished)
        tid = id(qgsTask)
        self.mTasks[tid] = qgsTask
        qgsTask.taskCompleted.connect(lambda *args, tid=tid: self.onRemoveTask(tid))
        qgsTask.taskTerminated.connect(lambda *args, tid=tid: self.onRemoveTask(tid))
        qgsTask.sigFoundSources.connect(self.addTimeSeriesSources)
        qgsTask.progressChanged.connect(self.sigProgress.emit)

        if runAsync:
            tm = QgsApplication.taskManager()
            assert isinstance(tm, QgsTaskManager)
            tm.addTask(qgsTask)
        else:
            qgsTask.run()

    def onRemoveTask(self, key):
        if isinstance(key, QgsTask):
            key = id(key)
        self.mTasks.pop(key)

    def onTaskFinished(self, success, task:QgsTask):
        # print(':: onAddSourcesAsyncFinished')
        if isinstance(task, TimeSeriesLoadingTask):
            if len(task.mInvalidSources) > 0:
                info = ['Unable to load {} data source(s):'.format(len(task.mInvalidSources))]
                for (s, ex) in task.mInvalidSources:
                    info.append('Path="{}" Error="{}"'.format(str(s), str(ex).replace('\n', ' ')))
                info = '\n'.join(info)
                messageLog(info, Qgis.Critical)

    def addTimeSeriesSource(self, source:TimeSeriesSource) -> TimeSeriesDate:
        """
        :param source:
        :return: TimeSeriesDate (if new created)
        """
        if isinstance(source, TimeSeriesSource):
            tss = source
        else:
            tss = TimeSeriesSource.create(source)

        assert isinstance(tss, TimeSeriesSource)

        newTSD = None

        tsdDate = self.date2date(tss.date())
        sid = tss.sid()
        sensor = self.findMatchingSensor(sid)

        # if necessary, add a new sensor instance
        if not isinstance(sensor, SensorInstrument):
            sensor = self.addSensor(SensorInstrument(sid))
            assert isinstance(sensor, SensorInstrument)
        assert isinstance(sensor, SensorInstrument)
        tsd = self.tsd(tsdDate, sensor)

        # if necessary, add a new TimeSeriesDate instance
        if not isinstance(tsd, TimeSeriesDate):
            tsd = self.insertTSD(TimeSeriesDate(self, tsdDate, sensor))
            newTSD = tsd
            # addedDates.append(tsd)
        assert isinstance(tsd, TimeSeriesDate)

        # ensure that the source refers to the sensor ID of the linked sensor (which might be different from its orginal sensor id)
        tss.mSid = sensor.id()

        # add the source

        tsd.addSource(tss)
        self.mLUT_Path2TSD[tss.uri()] = tsd
        return newTSD

    def setDateTimePrecision(self, mode:DateTimePrecision):
        """
        Sets the precision with which the parsed DateTime information will be handled.
        :param mode: TimeSeriesViewer:DateTimePrecision
        :return:
        """
        self.mDateTimePrecision = mode

        #do we like to update existing sources?

    def setSensorMatching(self, flags:SensorMatching):
        """
        Sets the mode under which two source images can be considered as to be from the same sensor/product
        :param flags:
        :return:
        """
        assert isinstance(flags, SensorMatching)
        assert bool(flags & SensorMatching.PX_DIMS), 'SensorMatching flags PX_DIMS needs to be set'
        self.mSensorMatchingFlags = flags


    def date2date(self, date:np.datetime64) -> np.datetime64:
        """
        Converts a date of arbitrary precision into the date with precision according to the EOTSV settions.
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



    def sourceUris(self) -> list:
        """
        Returns the uris of all sources
        :return: [list-of-str]
        """
        uris = []
        for tsd in self:
            assert isinstance(tsd, TimeSeriesDate)
            uris.extend(tsd.sourceUris())
        return uris

    def __len__(self):
        return len(self.mTSDs)

    def __iter__(self) -> typing.Iterator[TimeSeriesDate]:
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

        if isinstance(node, TimeSeriesDate):
            return self.mRootIndex

        elif isinstance(node, TimeSeriesSource):
            tss = node
            tsd = node.timeSeriesDate()
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
        if isinstance(node, TimeSeriesDate):
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

    def tsdToIdx(self, tsd:TimeSeriesDate) -> QModelIndex:
        """
        Returns an QModelIndex pointing on a TimeSeriesDate of interest
        :param tsd: TimeSeriesDate
        :return: QModelIndex
        """
        row = self.mTSDs.index(tsd)
        return self.index(row, 0)

    def tsdFromIdx(self, index: QModelIndex) -> TimeSeriesDate:
        """
        Returns the TimeSeriesDate related to an QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if index.row() == -1 and index.column() == -1:
            return None
        elif not index.isValid():
            return None
        else:
            node = index.internalPointer()
            if isinstance(node, TimeSeriesDate):
                return node
            elif isinstance(node, TimeSeriesSource):
                return node.timeSeriesDate()

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
            tsd = node.timeSeriesDate()
            tss = node
        elif isinstance(node, TimeSeriesDate):
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
                if cName == self.cnSensor:
                    return tsd.sensor().name()

            if role == Qt.CheckStateRole and index.column() == 0:
                return Qt.Checked if node.isVisible() else Qt.Unchecked

            if role == Qt.DecorationRole and index.column() == 0:

                return None

                ext = tss.spatialExtent()
                if isinstance(self.mCurrentSpatialExtent, SpatialExtent) and isinstance(ext, SpatialExtent):
                    ext = ext.toCrs(self.mCurrentSpatialExtent.crs())

                    b = isinstance(ext, SpatialExtent) and ext.intersects(self.mCurrentSpatialExtent)
                    if b:
                        return QIcon(r':/eotimeseriesviewer/icons/mapview.svg')
                    else:
                        return QIcon(r':/eotimeseriesviewer/icons/mapviewHidden.svg')
                else:
                    print(ext)
                    return None

            if role == Qt.BackgroundColorRole and tsd in self.mVisibleDate:
                return QColor('yellow')

        if isinstance(node, TimeSeriesDate):
            if role in [Qt.DisplayRole]:
                if cName == self.cnSensor:
                    return tsd.sensor().name()
                if cName == self.cnImages:
                    return len(tsd)
                if cName == self.cnDate:
                    return str(tsd.date())

            if role == Qt.CheckStateRole and index.column() == 0:
                return node.checkState()

            if role == Qt.BackgroundColorRole and tsd in self.mVisibleDate:
                return QColor('yellow')

        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int):

        if not index.isValid():
            return False

        result = False
        bVisibilityChanged = False
        node = index.internalPointer()
        if isinstance(node, TimeSeriesDate):
            if role == Qt.CheckStateRole and index.column() == 0:
                # update all TSS
                tssVisible = value == Qt.Checked

                n = len(node)
                if n > 0:
                    for tss in node:
                        tss.setIsVisible(tssVisible)
                    self.dataChanged.emit(self.index(0, 0, index),
                                          self.index(self.rowCount(index) -1 , 0, index),
                                          [role])

                result = bVisibilityChanged = True

        if isinstance(node, TimeSeriesSource):
            if role == Qt.CheckStateRole and index.column() == 0:
                b = node.isVisible()
                node.setIsVisible(value == Qt.Checked)
                result = bVisibilityChanged = b != node.isVisible()

                if bVisibilityChanged:
                    # update parent TSD node
                    self.dataChanged.emit(index.parent(), index.parent(), [role])

        if result:
            self.dataChanged.emit(index, index, [role])

        if bVisibilityChanged:
            self.sigVisibilityChanged.emit()

        return result

    def findSource(self, tss: TimeSeriesSource) -> TimeSeriesSource:
        """
        Returns the first TimeSeriesSource instance that is equal to the TimeSeriesSource.
        """
        for tsd in self:
            for tssCandidate in tsd:
                if tssCandidate == tss:
                    return tssCandidate
        return None

    def findDate(self, date) -> TimeSeriesDate:
        """
        Returns a TimeSeriesDate closest to that in date
        :param date: numpy.datetime64 | str | TimeSeriesDate
        :return: TimeSeriesDate
        """
        if isinstance(date, str):
            date = np.datetime64(date)
        if isinstance(date, TimeSeriesDate):
            date = date.date()
        assert isinstance(date, np.datetime64)

        if len(self) == 0:
            return None
        dtAbs = np.abs(date - np.asarray([tsd.date() for tsd in self.mTSDs]))

        i = np.argmin(dtAbs)
        return self.mTSDs[i]

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            flags = flags | Qt.ItemIsUserCheckable
        return flags


class TimeSeriesTreeView(QTreeView):

    sigMoveToDateRequest = pyqtSignal(TimeSeriesDate)
    sigMoveToSource = pyqtSignal(TimeSeriesSource)
    sigSetMapCrs = pyqtSignal(QgsCoordinateReferenceSystem)

    def __init__(self, parent=None):
        super(TimeSeriesTreeView, self).__init__(parent)

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        idx = self.indexAt(event.pos())
        node = self.model().data(idx, role=Qt.UserRole)

        selectedTSDs = []
        selectedTSSs = []
        for idx in self.selectionModel().selectedRows():
            node = idx.data(Qt.UserRole)
            if isinstance(node, TimeSeriesDate):
                selectedTSDs.append(node)
                selectedTSSs.extend(node[:])
            if isinstance(node, TimeSeriesSource):
                selectedTSSs.append(node)
        selectedTSSs = sorted(set(selectedTSSs))

        menu = QMenu(self)

        a = menu.addAction('Copy path(s)')
        a.setEnabled(len(selectedTSSs) > 0)
        a.triggered.connect(lambda _, tss=selectedTSSs: self.setClipboardUris(tss))
        a.setToolTip('Copy path(s) to clipboard.')

        a = menu.addAction('Copy value(s)')
        a.triggered.connect(lambda: self.onCopyValues())

        menu.addSeparator()

        if isinstance(node, TimeSeriesDate):
            a = menu.addAction('Show map for {}'.format(node.date()))
            a.setToolTip('Shows the map related to this time series date.')
            a.triggered.connect(lambda *args, tsd=node: self.sigMoveToDateRequest.emit(tsd))
            menu.addSeparator()
        elif isinstance(node, TimeSeriesSource):
            a = menu.addAction('Show {}'.format(node.name()))
            a.setToolTip('Shows the map with {} and zooms to'.format(node.uri()))
            a.triggered.connect(lambda *args, tss=node: self.sigMoveToSource.emit(tss))
            menu.addSeparator()

            a = menu.addAction('Set Crs to maps')
            a.setToolTip(f'Sets the map projection to that of this image ({node.crs().description()})')
            a.triggered.connect(lambda *args, crs=node.crs(): self.sigSetMapCrs.emit(crs))

        a = menu.addAction('Set date(s) invisible')
        a.setToolTip('Hides the selected time series dates from being shown in a map.')
        a.triggered.connect(lambda *args, tsds=selectedTSDs: self.timeseries().showTSDs(tsds, False))
        a = menu.addAction('Set date(s) visible')
        a.setToolTip('Shows the selected time series dates in maps.')
        a.triggered.connect(lambda *args, tsds=selectedTSDs: self.timeseries().showTSDs(tsds, True))

        menu.addSeparator()

        a = menu.addAction('Open in QGIS')
        a.setToolTip('Adds the selected images to the QGIS map canvas')
        a.triggered.connect(lambda *args, tss=selectedTSSs: self.openInQGIS(tss))

        menu.popup(QCursor.pos())

    def openInQGIS(self, tssList: typing.List[TimeSeriesSource]):

        import qgis.utils
        iface = qgis.utils.iface
        if isinstance(iface, QgisInterface):
            layers = [tss.asRasterLayer() for tss in tssList]
            QgsProject.instance().addMapLayers(layers, True)

    def setClipboardUris(self, tssList: typing.List[TimeSeriesSource]):

        urls = []
        paths = []
        for tss in tssList:
            uri = tss.uri()
            if os.path.isfile(uri):
                url = QUrl.fromLocalFile(uri)
                paths.append(QDir.toNativeSeparators(uri))
            else:
                url = QUrl(uri)
                paths.append(uri)
            urls.append(url)
        md = QMimeData()
        md.setText('\n'.join(paths))
        md.setUrls(urls)

        QApplication.clipboard().setMimeData(md)

    def timeseries(self) -> TimeSeries:
        return self.model().sourceModel()

    def onSetCheckState(self, tsds: typing.List[TimeSeriesDate], checkState: Qt.CheckStateRole):
        """
        Sets a ChecState to all selected rows
        :param checkState: Qt.CheckState
        """


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


regSensorName = re.compile(r'(SATELLITEID|(sensor|product)[ _]?(type|name))', re.IGNORECASE)
def sensorName(dataset:gdal.Dataset) -> str:
    """
    Reads the sensor/product name. Returns None if a proper name can not be extracted.
    :param dataset: gdal.Dataset
    :return: str
    """
    assert isinstance(dataset, gdal.Dataset)
    domains = dataset.GetMetadataDomainList()
    if isinstance(domains, list):
        for domain in domains:
            md = dataset.GetMetadata_Dict(domain)
            if isinstance(md, dict):
                for key, value in md.items():
                    if regSensorName.search(key):
                        return str(value)

    for b in range(dataset.RasterCount):
        band = dataset.GetRasterBand(b+1)
        if isinstance(band, gdal.Band):
            domains = band.GetMetadataDomainList()
            if isinstance(domains, list):
                for domain in domains:
                    md = band.GetMetadata_Dict(domain)
                    if isinstance(md, dict):
                        for key, value in md.items():
                            if regSensorName.search(key):
                                return str(value)

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

def extractWavelengthsFromGDALMetaData(ds:gdal.Dataset) -> (list, str):
    """
    Reads the wavelength info from standard metadata strings
    :param ds: gdal.Dataset
    :return: (list, str)
    """

    regWLkey = re.compile('^(center )?wavelength[_ ]*$', re.I)
    regWLUkey = re.compile('^wavelength[_ ]*units?$', re.I)
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)", re.I)

    def findKey(d:dict, regex) -> str:
        for key in d.keys():
            if regex.search(key):
                return key

    # 1. try band level
    wlu = []
    wl = []
    for b in range(ds.RasterCount):
        band = ds.GetRasterBand(b + 1)
        assert isinstance(band, gdal.Band)
        domains = band.GetMetadataDomainList()
        if not isinstance(domains, list):
            continue
        for domain in domains:
            md = band.GetMetadata_Dict(domain)

            keyWLU = findKey(md, regWLUkey)
            keyWL = findKey(md, regWLkey)

            if isinstance(keyWL, str) and isinstance(keyWLU, str):

                valueWL = float(md[keyWL])
                valueWLU = str(md[keyWLU]).lower()

                if valueWL > 0:
                    wl.append(valueWL)

                if valueWLU in LUT_WAVELENGTH_UNITS.keys():
                    wlu.append(LUT_WAVELENGTH_UNITS[valueWLU])

                break

    if len(wlu) == len(wl) and len(wl) == ds.RasterCount:
        return wl, wlu[0]

    # 2. try data set level
    for domain in ds.GetMetadataDomainList():
        md = ds.GetMetadata_Dict(domain)

        keyWLU = findKey(md, regWLUkey)
        keyWL = findKey(md, regWLkey)

        if isinstance(keyWL, str) and isinstance(keyWLU, str):


            wlu = LUT_WAVELENGTH_UNITS[md[keyWLU].lower()]
            matches = regNumeric.findall(md[keyWL])
            wl = [float(n) for n in matches]



            if len(wl) == ds.RasterCount:
                return wl, wlu

    return None, None



def extractWavelengthsFromRapidEyeXML(ds:gdal.Dataset, dom:QDomDocument) -> (list, str):
    nodes = dom.elementsByTagName('re:bandSpecificMetadata')
    # see http://schemas.rapideye.de/products/re/4.0/RapidEye_ProductMetadata_GeocorrectedLevel.xsd
    # wavelength and units not given in the XML
    # -> use values from https://www.satimagingcorp.com/satellite-sensors/other-satellite-sensors/rapideye/
    if nodes.count() == ds.RasterCount and ds.RasterCount == 5:
        wlu = r'nm'
        wl = [0.5 * (440 + 510),
              0.5 * (520 + 590),
              0.5 * (630 + 685),
              0.5 * (760 + 850),
              0.5 * (760 + 850)
              ]
        return wl, wlu
    return None, None


def extractWavelengthsFromDIMAPXML(ds:gdal.Dataset, dom:QDomDocument) -> (list, str):
    """
    :param dom: QDomDocument | gdal.Dataset
    :return: (list of wavelengths, str wavelength unit)
    """
    # DIMAP XML metadata?
    assert isinstance(dom, QDomDocument)
    nodes = dom.elementsByTagName('Band_Spectral_Range')
    if nodes.count() > 0:
        candidates = []
        for element in [nodes.item(i).toElement() for i in range(nodes.count())]:
            _band = element.firstChildElement('BAND_ID').text()
            _wlu = element.firstChildElement('MEASURE_UNIT').text()
            wlMin = float(element.firstChildElement('MIN').text())
            wlMax = float(element.firstChildElement('MAX').text())
            _wl = 0.5 * wlMin + wlMax
            candidates.append((_band, _wl, _wlu))

        if len(candidates) == ds.RasterCount:
            candidates = sorted(candidates, key=lambda t: t[0])

            wlu = candidates[0][2]
            wlu = LUT_WAVELENGTH_UNITS[wlu]
            wl = [c[1] for c in candidates]
            return wl, wlu
    return None, None

def extractWavelengths(ds):
    """
    Returns the wavelength and wavelength units
    :param ds: gdal.Dataset
    :return: (float [list-of-wavelengths], str with wavelength unit)
    """

    if isinstance(ds, QgsRasterLayer):

        if ds.dataProvider().name() == 'gdal':
            uri = ds.source()
            return extractWavelengths(gdal.Open(uri))
        else:

            md = [l.split('=') for l in str(ds.metadata()).splitlines() if 'wavelength' in l.lower()]

            wl = wlu = None
            for kv in md:
                key, value = kv
                key = key.lower()
                value = value.strip()

                if key == 'wavelength':
                    tmp = re.findall(r'\d*\.\d+|\d+', value) #find floats
                    if len(tmp) == 0:
                        tmp = re.findall(r'\d+', value) #find integers
                    if len(tmp) == ds.bandCount():
                        wl = [float(w) for w in tmp]

                if key == 'wavelength units':
                    wlu = value
                    if wlu in LUT_WAVELENGTH_UNITS.keys():
                        wlu = LUT_WAVELENGTH_UNITS[wlu]

                if isinstance(wl, list) and isinstance(wlu, str):
                    return wl, wlu

    elif isinstance(ds, gdal.Dataset):

        def testWavelLengthInfo(wl, wlu) -> bool:
            return isinstance(wl, list) and len(wl) == ds.RasterCount and isinstance(wlu, str) and wlu in LUT_WAVELENGTH_UNITS.keys()

        # try band-specific metadata
        wl, wlu = extractWavelengthsFromGDALMetaData(ds)
        if testWavelLengthInfo(wl, wlu):
            return wl, wlu

        # try internal locations with XML info
        # SPOT DIMAP
        if 'xml:dimap' in ds.GetMetadataDomainList():
            md = ds.GetMetadata_Dict('xml:dimap')
            for key in md.keys():
                dom = QDomDocument()
                dom.setContent(key + '=' + md[key])
                wl, wlu = extractWavelengthsFromDIMAPXML(ds, dom)
                if testWavelLengthInfo(wl, wlu):
                    return wl, wlu

        # try separate XML files
        xmlReaders = [extractWavelengthsFromDIMAPXML, extractWavelengthsFromRapidEyeXML]
        for path in ds.GetFileList():
            if re.search(r'\.xml$', path, re.I) and not re.search(r'\.aux.xml$', path, re.I):
                dom = QDomDocument()
                with open(path, encoding='utf-8') as f:
                    dom.setContent(f.read())

                if dom.hasChildNodes():
                    for xmlReader in xmlReaders:
                        wl, wlu = xmlReader(ds, dom)
                        if testWavelLengthInfo(wl, wlu):
                            return wl, wlu

    return None, None


class TimeSeriesDock(QgsDockWidget):
    """
    QgsDockWidget that shows the TimeSeries
    """
    def __init__(self, parent=None):
        super(TimeSeriesDock, self).__init__(parent)
        
        loadUi(DIR_UI / 'timeseriesdock.ui', self)
        self.frameFilters.setVisible(False)

        self.timeSeriesTreeView: TimeSeriesTreeView
        self.mTimeSeries: TimeSeries = None
        self.mSelectionModel = None


    def initActions(self, parent):

        from eotimeseriesviewer.main import EOTimeSeriesViewerUI
        assert isinstance(parent, EOTimeSeriesViewerUI)
        self.btnAddTSD.setDefaultAction(parent.actionAddTSD)
        self.btnRemoveTSD.setDefaultAction(parent.actionRemoveTSD)
        self.btnLoadTS.setDefaultAction(parent.actionLoadTS)
        self.btnSaveTS.setDefaultAction(parent.actionSaveTS)
        self.btnClearTS.setDefaultAction(parent.actionClearTS)


    def showTSD(self, tsd:TimeSeriesDate):
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
                info = 'Empty TimeSeries. Please add source images.'
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
        Slot to react on user-driven changes of the selected TimeSeriesDate rows.
        """

        self.btnRemoveTSD.setEnabled(
            isinstance(self.mSelectionModel, QItemSelectionModel) and
            len(self.mSelectionModel.selectedRows()) > 0)

    def selectedTimeSeriesDates(self) -> list:
        """
        Returns the TimeSeriesDate selected by a user.
        :return: [list-of-TimeSeriesDate]
        """
        results = []
        if isinstance(self.mSelectionModel, QItemSelectionModel):
            for idx in self.mSelectionModel.selectedRows():
                tsd = self.mTSProxyModel.data(idx, Qt.UserRole)
                if isinstance(tsd, TimeSeriesSource):
                    tsd = tsd.timeSeriesDate()
                if isinstance(tsd, TimeSeriesDate) and tsd not in results:
                    results.append(tsd)
        return results

    def timeSeries(self) -> TimeSeries:
        """
        Returns the connected TimeSeries
        :return: TimeSeries
        """
        return self.mTimeSeries

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