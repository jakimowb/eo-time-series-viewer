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
import bisect
import copy
import datetime
import enum
import json
# noinspection PyPep8Naming
import os
import pathlib
import re
import warnings
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

import numpy as np
from osgeo import gdal

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDataProvider, \
    QgsDateTimeRange, QgsExpressionContextScope, QgsGeometry, QgsMessageLog, QgsMimeDataUtils, QgsPointXY, \
    QgsProcessingFeedback, QgsProcessingMultiStepFeedback, QgsProject, QgsProviderMetadata, QgsProviderRegistry, \
    QgsRasterBandStats, QgsRasterDataProvider, QgsRasterInterface, QgsRasterLayer, QgsRasterLayerTemporalProperties, \
    QgsRectangle, QgsTask, QgsTaskManager
from qgis.PyQt import sip
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QAbstractTableModel, QDate, QDateTime, QDir, \
    QItemSelectionModel, QMimeData, QModelIndex, QObject, QRegExp, QSortFilterProxyModel, Qt, QUrl
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from qgis.PyQt.QtWidgets import QAbstractItemView, QAction, QHeaderView, QMainWindow, QMenu, QToolBar, QTreeView
from qgis.gui import QgisInterface, QgsDockWidget
from qgis.PyQt.QtXml import QDomDocument
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer import DIR_UI, messageLog
from .qgispluginsupport.qps.unitmodel import UnitLookup
from .qgispluginsupport.qps.utils import loadUi, LUT_WAVELENGTH, relativePath, SpatialExtent
from .qgispluginsupport.qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from .tasks import EOTSVTask

gdal.SetConfigOption('VRT_SHARED_SOURCE', '0')  # !important. really. do not change this.

DEFAULT_CRS = 'EPSG:4326'

LUT_WAVELENGTH_UNITS = {}
for siUnit in [r'nm', r'μm', r'mm', r'cm', r'dm']:
    LUT_WAVELENGTH_UNITS[siUnit] = siUnit
LUT_WAVELENGTH_UNITS[r'nanometers'] = r'nm'
LUT_WAVELENGTH_UNITS[r'micrometers'] = r'μm'
LUT_WAVELENGTH_UNITS[r'um'] = r'μm'
LUT_WAVELENGTH_UNITS[r'millimeters'] = r'mm'
LUT_WAVELENGTH_UNITS[r'centimeters'] = r'cm'
LUT_WAVELENGTH_UNITS[r'decimeters'] = r'dm'


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
# add synonyms
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

    return value * 10 ** (e1 - e2)


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


def create_sensor_id(lyr: QgsRasterLayer) -> Optional[str]:
    """
    Creates a unique sensor_id
    :param lyr:
    :return:
    """
    assert isinstance(lyr, QgsRasterLayer) and lyr.isValid()

    nb = lyr.bandCount()
    dp: QgsRasterDataProvider = lyr.dataProvider()
    px_size_x = lyr.rasterUnitsPerPixelX()
    px_size_y = lyr.rasterUnitsPerPixelY()
    dt = dp.dataType(1)

    name = sensorName(lyr)
    wl = wlu = None
    spectralProperties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
    if spectralProperties:
        wl = spectralProperties.wavelengths()
        wlu = spectralProperties.wavelengthUnits()
        if isinstance(wlu, list):
            wlu = wlu[0]

    return sensorID(nb, px_size_x, px_size_y, dt, wl, wlu, name)


def sensorID(nb: int,
             px_size_x: float,
             px_size_y: float,
             dt: Qgis.DataType,
             wl: list = None,
             wlu: str = None,
             name: str = None) -> str:
    """
    Creates a sensor ID str
    :param name:
    :param dt:
    :param nb: number of bands
    :param px_size_x: pixel size x
    :param px_size_y: pixel size y
    :param wl: list of wavelength
    :param wlu: str, wavelength unit
    :return: str
    """
    assert dt in GDAL_DATATYPES.values()
    assert isinstance(dt, Qgis.DataType)
    assert isinstance(nb, int) and nb > 0
    assert isinstance(px_size_x, (int, float)) and px_size_x > 0
    assert isinstance(px_size_y, (int, float)) and px_size_y > 0

    if wl is not None:
        assert isinstance(wl, list)
        assert len(wl) == nb

        if all([w is None for w in wl]):
            wl = None

    if wlu is not None:
        assert isinstance(wlu, str)

    if name is not None:
        assert isinstance(name, str)

    jsonDict = {'nb': nb,
                'px_size_x': px_size_x,
                'px_size_y': px_size_y,
                'dt': int(dt),
                'wl': wl,
                'wlu': wlu,
                'name': name
                }
    return json.dumps(jsonDict, ensure_ascii=False)


def sensorIDtoProperties(idString: str) -> tuple:
    """
    Reads a sensor id string and returns the sensor properties. See sensorID().
    :param idString: str
    :return: (ns, px_size_x, px_size_y, dt, wl, wlu, name)
    """

    jsonDict = json.loads(idString)
    assert isinstance(jsonDict, dict)
    # must haves
    nb = jsonDict.get('nb')
    px_size_x = jsonDict.get('px_size_x')
    px_size_y = jsonDict.get('px_size_y')
    dt = Qgis.DataType(jsonDict.get('dt'))

    # can haves
    wl = jsonDict.get('wl', None)
    wlu = jsonDict.get('wlu', None)
    name = jsonDict.get('name', None)

    assert isinstance(dt, Qgis.DataType)
    assert isinstance(nb, int)
    assert isinstance(px_size_x, (int, float)) and px_size_x > 0
    assert isinstance(px_size_y, (int, float)) and px_size_y > 0
    if wl is not None:
        assert isinstance(wl, list)
    if wlu is not None:
        assert isinstance(wlu, str)
    if name is not None:
        assert isinstance(name, str)
    return nb, px_size_x, px_size_y, dt, wl, wlu, name


class SensorInstrument(QObject):
    """
    Describes a Sensor Configuration
    """
    SensorNameSettingsPrefix = 'SensorName.'
    sigNameChanged = pyqtSignal(str)

    PROPERTY_KEY = 'eotsv/sensor'
    PROPERTY_KEY_STYLE_INITIALIZED = 'eotsv/style_initialized'

    def __init__(self, sid: str, band_names: list = None):
        super(SensorInstrument, self).__init__()

        self.mId = sid
        self.nb: int
        self.px_size_x: float
        self.px_size_y: float
        self.dataType: int
        self.wl: list
        self.wlu: str
        self.nb, self.px_size_x, self.px_size_y, self.dataType, self.wl, self.wlu, self.mNameOriginal \
            = sensorIDtoProperties(self.mId)

        # self.mMockupLayer = QgsRasterLayer('')

        if self.mNameOriginal in [None, '']:
            self.mName = '{}bands@{}m'.format(self.nb, self.px_size_x)
        else:
            self.mName = self.mNameOriginal

        # import eotimeseriesviewer.settings
        # storedName = eotimeseriesviewer.settings.sensorName(self.mId)
        # if isinstance(storedName, str):
        #    self.mName = storedName

        if not isinstance(band_names, list):
            band_names = ['Band {}'.format(b + 1) for b in range(self.nb)]

        assert len(band_names) == self.nb
        self.bandNames = band_names
        self.wlu = self.wlu
        if self.wl is None:
            self.wl = None
        else:
            self.wl = np.asarray(self.wl).tolist()

        self.hashvalue = hash(self.mId)

    def bandIndexClosestToWavelength(self, wl, wl_unit='nm') -> int:
        """
        Returns the band index closest to a certain wavelength
        :param wl: float | int
        :param wl_unit: str
        :return: int
        """
        if isinstance(wl, str):
            if wl in LUT_WAVELENGTH:
                wl = LUT_WAVELENGTH[wl]

        if self.wlu != wl_unit:
            wl = UnitLookup.convertLengthUnit(wl, wl_unit, self.wlu)

        return int(np.argmin(np.abs(np.asarray(self.wl) - wl)))

    def proxyRasterLayer(self) -> QgsRasterLayer:
        """
        Creates an "empty" in-memory layer that can be used as proxy for band names, data types and render styles
        :return: QgsRasterLayer
        """
        lyr = QgsRasterLayer(self.mId, name=self.name(), providerType=SensorMockupDataProvider.providerKey())
        lyr.nameChanged.connect(lambda *args, l=lyr: self.setName(l.name()))
        lyr.setCustomProperty(self.PROPERTY_KEY, self.id())
        lyr.setCustomProperty(self.PROPERTY_KEY_STYLE_INITIALIZED, False)

        self.sigNameChanged.connect(lyr.setName)
        return lyr

    def id(self) -> str:
        """
        Returns the Sensor id
        :return: str
        """
        return self.mId

    def _sensorSettingsKey(self):
        return SensorInstrument.SensorNameSettingsPrefix + self.mId

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
        return str(self.__class__) + ' ' + self.name()

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


class SensorMockupDataProvider(QgsRasterDataProvider):
    ALL_INSTANCES = dict()

    @staticmethod
    def _release_sip_deleted():
        to_delete = {k for k, o in SensorMockupDataProvider.ALL_INSTANCES.items()
                     if sip.isdeleted(o)}
        for k in to_delete:
            SensorMockupDataProvider.ALL_INSTANCES.pop(k)

    def __init__(self,
                 sid: str,
                 providerOptions: QgsDataProvider.ProviderOptions,
                 flags: QgsDataProvider.ReadFlags, **kwds):
        super().__init__(sid, providerOptions, flags, **kwds)

        self.mSid = sid
        self.mProviderOptions = providerOptions
        self.mFlags = flags
        sensor = SensorInstrument(sid)
        self.mSensor: SensorInstrument = sensor
        self.mCrs = QgsCoordinateReferenceSystem('EPSG:4326')

    def setSensor(self, sensor: SensorInstrument):
        assert isinstance(sensor, SensorInstrument)
        self.mSensor = sensor

    def sensor(self) -> SensorInstrument:
        return self.mSensor

    def capabilities(self):
        caps = QgsRasterInterface.Size | QgsRasterInterface.Identify | QgsRasterInterface.IdentifyValue
        if Qgis.versionInt() >= 33800:
            return Qgis.RasterInterfaceCapabilities(caps)
        else:
            return QgsRasterDataProvider.ProviderCapabilities(caps)

    def crs(self):
        return self.mCrs

    def extent(self):
        return QgsRectangle(QgsPointXY(0, 0), QgsPointXY(1, 1))

    def isValid(self) -> bool:
        return isinstance(self.mSensor, SensorInstrument)

    def name(self):
        return self.__class__.__name__

    def dataType(self, bandNo: int):
        return self.mSensor.dataType

    def bandCount(self):
        return self.mSensor.nb

    def sourceDataType(self, bandNo: int):
        return self.dataType(bandNo)

    @classmethod
    def providerKey(cls) -> str:
        return 'sensormockup'

    @classmethod
    def description(cls) -> str:
        return 'SensorMockupDataProvider'

    @classmethod
    def createProvider(cls, uri, providerOptions, flags=None):
        # compatibility with Qgis < 3.16, ReadFlags only available since 3.16
        flags = QgsDataProvider.ReadFlags()
        provider = SensorMockupDataProvider(uri, providerOptions, flags)

        # keep a python reference on the new provider instance
        cls.ALL_INSTANCES[id(provider)] = provider
        cls._release_sip_deleted()
        return provider

    def clone(self):
        return self.createProvider(self.mSid, self.mProviderOptions, self.mFlags)


def registerDataProvider():
    metadata = QgsProviderMetadata(
        SensorMockupDataProvider.providerKey(),
        SensorMockupDataProvider.description(),
        SensorMockupDataProvider.createProvider,
    )
    registry = QgsProviderRegistry.instance()
    successs = registry.registerProvider(metadata)
    if not successs:
        s = ""
    QgsMessageLog.logMessage('EOTSV SensorMockupDataProvider registered', level=Qgis.MessageLevel.Info)


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
        # logger.error('Can not open container {}.\nPlease specify a subdataset'.format(path))
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

    MIMEDATA_FORMATS = ['text/uri-list']

    MKeyDateTime = 'datetime'
    MKeySource = 'source'
    MKeyProvider = 'provider'
    MKeyName = 'name'
    MKeySensor = 'sid'

    @classmethod
    def fromMimeData(cls, mimeData: QMimeData) -> List['TimeSeriesSource']:
        sources = []
        if mimeData.hasUrls():
            for url in mimeData.urls():
                try:
                    print(url)
                    tss = TimeSeriesSource.create(url)
                    if isinstance(tss, TimeSeriesSource):
                        sources.append(tss)
                except Exception:
                    pass
        return sources

    @classmethod
    def fromJson(cls, jsonData: str) -> 'TimeSeriesSource':
        """
        Returns a TimeSeriesSource from its JSON representation
        :param jsonData:
        :return:
        """

        d = json.loads(jsonData)
        layer = QgsRasterLayer(d[TimeSeriesSource.MKeySource],
                               name=d.get(TimeSeriesSource.MKeyName),
                               providerType=d.get(TimeSeriesSource.MKeyProvider))
        dtg = QDateTime.fromString(d[TimeSeriesSource.MKeyDateTime], Qt.ISODateWithMs)
        return TimeSeriesSource(layer, dtg)

    def qgsMimeDataUtilsUri(self) -> QgsMimeDataUtils.Uri:

        uri = QgsMimeDataUtils.Uri(self.asRasterLayer())
        return uri

    @classmethod
    def create(cls, source: Union[QgsRasterLayer, str, Path]) -> 'TimeSeriesSource':
        """
        Reads the argument and returns a TimeSeriesSource
        :param source: gdal.Dataset, str or QgsRasterLayer
        :return: TimeSeriesSource
        """

        if isinstance(source, str):
            source = QgsRasterLayer(source)
        elif isinstance(source, Path):
            source = QgsRasterLayer(source.as_posix())
        elif isinstance(source, gdal.Dataset):
            source = QgsRasterLayer(source.GetDescription(), providerType='gdal')

        if isinstance(source, QgsRasterLayer) and source.isValid():
            date = ImageDateUtils.dateTimeFromLayer(source)
            if isinstance(date, QDateTime):
                return TimeSeriesSource(source, date)
            else:
                raise Exception(f'Unable to read observation date for {source.source()}')
        else:
            raise Exception(f'Unable to open {source} as QgsRasterLayer')

    def __init__(self, layer: QgsRasterLayer, dtg: QDateTime):

        if isinstance(layer, (Path, str)):
            layer = QgsRasterLayer(Path(layer).as_posix())

        assert isinstance(layer, QgsRasterLayer) and layer.isValid()
        assert isinstance(dtg, QDateTime)

        self.mIsVisible: bool = True
        self.mCrs: QgsCoordinateReferenceSystem = layer.crs()
        self.mExtent: QgsRectangle = layer.extent()
        self.mSource: str = layer.source()
        self.mName: str = layer.name()
        self.mProvider: str = layer.dataProvider().name()
        self.mSid: str = create_sensor_id(layer)
        self.mDims = [layer.bandCount(), layer.height(), layer.width()]
        self.mIsVisible: bool = True
        self.mDTG: QDateTime = dtg

        self.mLayer: QgsRasterLayer = layer
        self.mTimeSeriesDate: Optional[TimeSeriesDate] = None

    def nb(self) -> int:
        """
        Returns the number of bands.
        :return: int
        """
        return self.mDims[0]

    def nl(self) -> int:
        """
        Returns the number of lines.
        :return: int
        """
        return self.mDims[1]

    def ns(self) -> int:
        """
        Returns the number of samples.
        :return: int
        """
        return self.mDims[2]

    def source(self) -> str:
        """
        Returns the source uri.
        :return: str
        """
        return self.mSource

    def clone(self):
        return TimeSeriesSource(self.asRasterLayer(False), self.mDTG)

    def asMap(self) -> dict:

        d = {self.MKeySource: self.mSource,
             self.MKeyName: self.mName,
             self.MKeyProvider: self.mProvider,
             self.MKeySensor: self.mSid,
             self.MKeyDateTime: self.mDTG.toString(Qt.ISODate)}

        return d

    def json(self) -> str:
        """
        JSON representation of this for fast restore
        :return:
        """
        return json.dumps(self.asMap(), ensure_ascii=False)

    def name(self) -> str:
        """
        Returns a name for this data source
        :return:
        """
        return self.mName
        # bn = os.path.basename(self.mSource)
        # return '{} {}'.format(bn, self.dtg())

    def asRasterLayer(self, loadDefaultStyle: bool = False) -> QgsRasterLayer:
        loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=loadDefaultStyle)
        lyr = QgsRasterLayer(self.mSource, self.mName, self.mProvider, options=loptions)
        tprop: QgsRasterLayerTemporalProperties = lyr.temporalProperties()
        tprop.setIsActive(True)
        tprop.setMode(QgsRasterLayerTemporalProperties.ModeFixedTemporalRange)
        lyr.setCustomProperty('eotsv/dtg', self.dtg().toString(Qt.ISODate))
        tprop.setFixedTemporalRange(QgsDateTimeRange(self.dtg(), self.dtg()))
        return lyr

    def crsWkt(self) -> str:
        return self.crs().toWkt()

    def sid(self) -> str:
        """
        Returns the sensor id
        :return: str
        """
        return self.mSid

    def setTimeSeriesDate(self, tsd: 'TimeSeriesDate'):
        """
        Sets the parent TimeSeriesDate
        :param tsd: TimeSeriesDate
        """
        assert isinstance(tsd, TimeSeriesDate)
        self.mTimeSeriesDate = tsd

    def timeSeriesDate(self) -> 'TimeSeriesDate':
        return self.mTimeSeriesDate

    def dtg(self) -> QDateTime:
        """
        Returns the Date-Time-Group this observation is related to
        :return: QDateTime
        """
        return self.mDTG

    def crs(self) -> QgsCoordinateReferenceSystem:
        """
        Returns the coordinate system as QgsCoordinateReferenceSystem
        :return:
        :rtype:
        """
        return self.mCrs

    def spatialExtent(self) -> SpatialExtent:
        """
        Returns the SpatialExtent
        :return:
        :rtype:
        """
        return SpatialExtent(self.mCrs, self.mExtent)

    def asDataset(self) -> gdal.Dataset:
        """
        Returns the source as gdal.Dataset
        :return:
        :rtype:
        """
        return gdal.Open(self.mSource)

    def isVisible(self) -> bool:
        return self.mIsVisible

    def setIsVisible(self, b: bool):
        assert isinstance(b, bool)
        self.mIsVisible = b

    def __eq__(self, other):
        if not isinstance(other, TimeSeriesSource):
            return False
        return self.mSource == other.mSource

    def __lt__(self, other):
        assert isinstance(other, TimeSeriesSource)
        return self.dtg() < other.dtg()

    def __hash__(self):
        return hash(self.mSource)


class TimeSeriesDate(QAbstractTableModel):
    """
    A container to store all source images related to a single observation date (range) and sensor.
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

    def __init__(self, dtr: QgsDateTimeRange, sensor: SensorInstrument):
        """
        Constructor
        :param dtr: np.datetime64,
        :param sensor: SensorInstrument
        """
        super(TimeSeriesDate, self).__init__()

        assert isinstance(dtr, QgsDateTimeRange)
        assert isinstance(sensor, SensorInstrument)

        self.mSensor: SensorInstrument = sensor
        self.mDTR: QgsDateTimeRange = dtr

        self.mSources: List[TimeSeriesSource] = []
        self.mMasks = []
        self.mTimeSeries: Optional[TimeSeries] = None

    def removeSource(self, source: TimeSeriesSource):

        if source in self.mSources:
            i = self.mSources.index(source)
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mSources.remove(source)
            self.endRemoveRows()
            self.sigSourcesRemoved.emit([source])

    def dateTimeRange(self) -> QgsDateTimeRange:
        return QgsDateTimeRange(self.mDTR.begin(), self.mDTR.end())

    def scope(self) -> QgsExpressionContextScope:

        scope = QgsExpressionContextScope(self.__class__.__name__)
        dtg0: QDateTime = self.dateTimeRange().begin()
        d0: QDate = dtg0.date()

        scope.setVariable('date', dtg0.toString(Qt.ISODate))
        scope.setVariable('doy', ImageDateUtils.doiFromDateTime(dtg0))
        scope.setVariable('decimalYear', ImageDateUtils.decimalYear(dtg0))
        scope.setVariable('sensor', self.sensor().name())
        scope.setVariable('sensor_id', self.sensor().id())

        return scope

    def addSource(self, source: TimeSeriesSource):
        """
        Adds an time series source to this TimeSeriesDate
        :param path: TimeSeriesSource or any argument accepted by TimeSeriesSource.create()
        :return: TimeSeriesSource, if added
        """

        assert isinstance(source, TimeSeriesSource)
        # assert self.mDate == source.date()
        # assert self.mSensor.id() == source.sid()

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
        Returns the checkstate according to the visibility of the TSDs TimeSeriesSources
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
        :return: SensorInstrument
        """
        return self.mSensor

    def sources(self) -> List[TimeSeriesSource]:
        """
        Returns the source images
        :return: [list-of-TimeSeriesSource]
        """
        return self.mSources

    def sourceUris(self) -> List[str]:
        """
        Returns all source URIs as list of strings-
        :return: [list-of-str]
        """
        return [tss.source() for tss in self.sources()]

    def qgsMimeDataUtilsUris(self) -> list:
        """
        Returns all source URIs as list of QgsMimeDataUtils.Uri
        :return: [list-of-QgsMimedataUtils.Uris]
        """
        return [s.qgsMimeDataUtilsUri() for s in self.sources()]

    def dtg(self) -> QDateTime:
        """
        Returns the beginning date-time group (DTG) of the described date-time-range.
        :return: QDateTime
        """
        return self.mDTR.begin()

    def dateString(self) -> str:

        if isinstance(self.mTimeSeries, TimeSeries):
            prec = self.mTimeSeries.dateTimePrecision()
            return ImageDateUtils.dateTimeString(self.dtg(), prec)
        else:
            return self.dtg().toString(Qt.ISODate)

    def decimalYear(self) -> float:
        """
        Returns the observation date as decimal year (year + doy / (366+1) )
        :return: float
        """

        return ImageDateUtils.decimalYear(self.dtg())

    def year(self) -> int:
        """
        Returns the observation year
        :return: int
        """
        return self.dtg().date().year()

    def doy(self) -> int:
        """
        Returns the day of Year (DOY)
        :return: int
        """
        return ImageDateUtils.doiFromDateTime(self.dtg())

    def hasIntersectingSource(self, spatialExtent: SpatialExtent):
        for source in self:
            assert isinstance(source, TimeSeriesSource)
            ext = source.spatialExtent()
            if isinstance(ext, SpatialExtent):
                ext = ext.toCrs(spatialExtent.crs())
                if spatialExtent.intersects(ext):
                    return True
        return False

    def spatialExtent(self, crs: Optional[QgsCoordinateReferenceSystem] = None):
        """
        Returns the SpatialExtent of all data sources
        :return: SpatialExtent
        """
        ext = None
        for i, tss in enumerate(self.sources()):
            assert isinstance(tss, TimeSeriesSource)
            if i == 0:
                ext = tss.spatialExtent()
                if crs is None:
                    crs = ext.crs()
                else:
                    ext = ext.toCrs(crs)
            else:
                ext.combineExtentWith(tss.spatialExtent().toCrs(crs))
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
        return 'TimeSeriesDate({},{})'.format(str(self.mDTR), str(self.mSensor))

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

    def __iter__(self) -> Iterator[TimeSeriesSource]:
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
        if self.dtg() < other.dtg():
            return True
        elif self.dtg() > other.dtg():
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

    def data(self, index: QModelIndex, role: int):

        if not index.isValid():
            return None

        tss = self.mSources[index.row()]
        assert isinstance(tss, TimeSeriesSource)

        cn = TimeSeriesDate.ColumnNames[index.column()]
        if role == Qt.UserRole:
            return tss

        if role == Qt.DisplayRole:
            if cn == TimeSeriesDate.cnNB:
                return tss.nb()
            if cn == TimeSeriesDate.cnNS:
                return tss.ns()
            if cn == TimeSeriesDate.cnNL:
                return tss.nl()
            if cn == TimeSeriesDate.cnCRS:
                return tss.crs().description()
            if cn == TimeSeriesDate.cnUri:
                return tss.source()

        return None

    def id(self) -> Tuple[QgsDateTimeRange, str]:
        """
        :return: tuple
        """
        return self.mDTR, self.mSensor.id()

    def __hash__(self):
        return hash(str(self.id()))


class SensorMatching(enum.Flag):
    """
    Describes when two different sources should be considered to be from the same sensor
    """

    PX_DIMS = enum.auto()  # 'Pixel Dimensions (GSD + Bands + Datatype)'
    WL = enum.auto()  # 'Pixel Dims. + Wavelength'
    NAME = enum.auto()  # 'Pixel Dims. + NAME'

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
            parts.append(
                'Source images of same sensor/product must have same ground sampling distance ("pixel size"), '
                'number of bands and data type.')
        if bool(flags & SensorMatching.WL):
            parts.append(
                r'Source images of same sensor/product must have same wavelength definition, '
                r'e.g. nanometer value for each raster band.')
        if bool(flags & SensorMatching.NAME):
            parts.append(
                r'Source images of same sensor/product must have the same name, e.g. defined by '
                r'a "sensor type = Landsat 8" metadata entry.')

        return '\n'.join(parts)


class TimeSeriesFindOverlapTask(EOTSVTask):
    sigTimeSeriesSourceOverlap = pyqtSignal(dict)

    def __init__(self,
                 extent: SpatialExtent,
                 time_series_sources: List[TimeSeriesSource],
                 date_of_interest: QDateTime = None,
                 max_forward: int = -1,
                 max_backward: int = -1,
                 callback=None,
                 description: str = None,
                 sample_size: int = 16,
                 progress_interval: int = 2):
        """

        :param extent:
        :param time_series_sources:
        :param date_of_interest: date of interest from which to start searching. "pivot" date
        :param max_forward: max. number of intersecting dates to search into the past of date_of_interest
            defaults to -1 = search for all dates < date_of_interest
        :param max_backward: max. number of intersecting dates to search into the future of date_of_interest
            defaults to -1 = search for all dates > date_of_interest
        :param callback:
        :param description:
        :param sample_size: number of samples in x and y direction
        :param progress_interval:
        """
        if description is None:
            if date_of_interest is not None and (max_forward != -1 or max_backward != -1):
                description = f'Find image overlap ({str(date_of_interest)})'
            else:
                description = 'Find image overlap (all dates)'

        super().__init__(description=description,
                         flags=QgsTask.CanCancel | QgsTask.CancelWithoutPrompt | QgsTask.Silent)
        assert sample_size >= 1
        assert progress_interval >= 1
        assert isinstance(extent, SpatialExtent)
        self.mTimeSeriesSources: List[TimeSeriesSource] = [tss.clone() for tss in time_series_sources]

        self.mDates = set([tss.dtg() for tss in self.mTimeSeriesSources])

        if not isinstance(date_of_interest, QDateTime):
            self.mDOI = list(self.mDates)[0]
        else:
            self.mDOI = date_of_interest

        if max_forward == -1:
            self.m_max_forward = len(self.mTimeSeriesSources)
        else:
            self.m_max_forward = max_forward

        if max_backward == -1:
            self.m_max_backward = len(self.mTimeSeriesSources)
        else:
            self.m_max_backward = max_backward

        self.mCallback = callback
        self.mTargetExtent = extent.__copy__()
        self.mSampleSize = sample_size
        self.mProgressInterval = datetime.timedelta(seconds=progress_interval)
        self.mIntersections: Dict[str, bool] = dict()
        self.mError = None

        emptyStats: QgsRasterBandStats = QgsRasterBandStats()
        emptyMin = emptyStats.minimumValue
        emptyMax = emptyStats.maximumValue
        self.mEmptyMinMax = (emptyMin, emptyMax)

        targetCRS: QgsCoordinateReferenceSystem = self.mTargetExtent.crs()
        self.mExtentLookup: Dict[str, SpatialExtent] = dict()
        self.mExtentLookup[targetCRS.toWkt()] = self.mTargetExtent

    def testTSS(self, tss: TimeSeriesSource) -> bool:

        wkt = tss.crsWkt()
        if wkt not in self.mExtentLookup.keys():
            self.mExtentLookup[wkt] = self.mTargetExtent.toCrs(tss.crs())

        targetExtent2 = self.mExtentLookup.get(wkt)
        if not isinstance(targetExtent2, SpatialExtent):
            return False

        if not targetExtent2.intersects(tss.spatialExtent()):
            return False

        lyr: QgsRasterLayer = tss.asRasterLayer()
        if not isinstance(lyr, QgsRasterLayer):
            return False

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=DeprecationWarning)
            stats: QgsRasterBandStats = lyr.dataProvider().bandStatistics(1,
                                                                          stats=Qgis.RasterBandStatistic.Range,
                                                                          extent=targetExtent2,
                                                                          sampleSize=self.mSampleSize)

        if not isinstance(stats, QgsRasterBandStats):
            return False
        return (stats.minimumValue, stats.maximumValue) != self.mEmptyMinMax

    def run(self):
        """
        Start the Task and returns the results.
        :return:
        """

        # try:
        if True:
            # for tssUri in self.mTSS:
            #    self.mIntersections[tssUri] = False

            n = len(self.mTimeSeriesSources)

            t0 = datetime.datetime.now()

            sources = sorted(self.mTimeSeriesSources, key=lambda tss: abs(tss.dtg().secsTo(self.mDOI)))

            dates_before = set()
            dates_after = set()

            smallest = min(self.mDates)
            highest = max(self.mDates)

            for i, tss in enumerate(sources):

                obs_date: QDateTime = tss.dtg()

                if obs_date < smallest or obs_date > highest:
                    continue

                is_intersection: bool = self.testTSS(tss)
                self.mIntersections[tss.source()] = is_intersection

                if is_intersection:
                    if obs_date < self.mDOI:
                        dates_before.add(obs_date)
                        if len(dates_before) >= self.m_max_backward:
                            smallest = min(dates_before)
                    elif obs_date > self.mDOI:
                        dates_after.add(obs_date)
                        if len(dates_after) >= self.m_max_forward:
                            highest = max(dates_after)

                dt = datetime.datetime.now() - t0
                if dt > self.mProgressInterval:
                    if self.isCanceled():
                        return False
                    self.sigTimeSeriesSourceOverlap.emit(self.mIntersections.copy())
                    self.mIntersections.clear()
                    progress = int(100 * (i + 1) / n)
                    self.setProgress(progress)
                    t0 = datetime.datetime.now()

        # except Exception as ex:
        #    self.mError = ex
        #    return False

        if len(self.mIntersections) > 0:
            self.sigTimeSeriesSourceOverlap.emit(self.mIntersections.copy())
        self.mIntersections.clear()
        self.setProgress(100)

        return True

    def canCancel(self) -> bool:
        return True

    def finished(self, result):
        if self.mCallback is not None:
            self.mCallback(result, self)


class TimeSeriesLoadingTask(EOTSVTask):
    sigFoundSources = pyqtSignal(list)
    sigMessage = pyqtSignal(str, bool)

    def __init__(self,
                 files: List[str],
                 visibility: List[bool] = None,
                 description: str = "Load Images",
                 callback=None,
                 progress_interval: int = 5):

        super().__init__(description=description,
                         flags=QgsTask.Silent | QgsTask.CanCancel | QgsTask.CancelWithoutPrompt)

        assert progress_interval >= 1

        self.mFiles: List[str] = copy.deepcopy(files)
        if visibility:
            assert isinstance(visibility, list) and len(visibility) == len(files)
            self.mVisibility: List[bool] = [b is True for b in visibility]
        else:
            self.mVisibility: List[bool] = [True for _ in files]
        # self.mSources: List[TimeSeriesSource] = []
        self.mProgressInterval = datetime.timedelta(seconds=progress_interval)
        self.mCallback = callback
        self.mInvalidSources: List[Tuple[str, Exception]] = []
        self.mError: Exception = None

    def canCancel(self) -> bool:
        return True

    def run(self) -> bool:
        result_block: List[TimeSeriesSource] = []
        n = len(self.mFiles)

        t0 = datetime.datetime.now()

        try:
            for i, path in enumerate(self.mFiles):
                assert isinstance(path, str)

                try:
                    tss = TimeSeriesSource.create(path)
                    assert isinstance(tss, TimeSeriesSource), f'Unable to open {path} as TimeSeriesSource'
                    tss.setIsVisible(self.mVisibility[i])
                    # self.mSources.append(tss)
                    result_block.append(tss)
                    del tss
                except Exception as ex:
                    self.mInvalidSources.append((path, ex))

                dt = datetime.datetime.now() - t0

                if dt > self.mProgressInterval:
                    if self.isCanceled():
                        return False
                    progress = int(100 * (i + 1) / n)
                    self.setProgress(progress)
                    # self.sigFoundSources.emit(cloneAndClear())
                    self.sigFoundSources.emit([tss.clone() for tss in result_block])
                    result_block.clear()

            if len(result_block) > 0:
                # self.sigFoundSources.emit(cloneAndClear())
                self.sigFoundSources.emit([tss.clone() for tss in result_block])
                result_block.clear()
        except Exception as ex:
            self.mError = ex
            return False

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

    sigLoadingTaskFinished = pyqtSignal()
    sigFindOverlapTaskFinished = pyqtSignal()

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigSensorNameChanged = pyqtSignal(SensorInstrument)

    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)

    sigVisibilityChanged = pyqtSignal()
    sigProgress = pyqtSignal(float)
    sigMessage = pyqtSignal(str, Qgis.MessageLevel)
    _sep = ';'

    cDate = 0
    cSensor = 1
    cNS = 2
    cNL = 3
    cNB = 4
    cCRS = 5
    cImages = 6

    def __init__(self, imageFiles=None):
        super(TimeSeries, self).__init__()
        self.mTSDs: List[TimeSeriesDate] = list()
        self.mSensors: List[SensorInstrument] = []
        self.mShape = None
        self.mTreeView: QTreeView = None
        self.mDateTimePrecision = DateTimePrecision.Day
        self.mSensorMatchingFlags = SensorMatching.PX_DIMS

        self.mLUT_Path2TSD = {}
        self.mVisibleDates: Set[TimeSeriesDate] = set()

        self.mColumnNames = {
            self.cDate: 'Date',
            self.cSensor: 'Sensor',
            self.cNS: 'ns',
            self.cNB: 'nb',
            self.cNL: 'nl',
            self.cCRS: 'CRS',
            self.cImages: 'Source Image(s)'
        }

        self.mRootIndex = QModelIndex()
        self.mTasks = dict()

        if imageFiles is not None:
            self.addSources(imageFiles)

    def focusVisibility(self,
                        ext: SpatialExtent,
                        runAsync: bool = None,
                        date_of_interest: np.datetime64 = None,
                        max_before: int = -1,
                        max_after: int = -1):
        """
        Changes TSDs visibility according to its intersection with a SpatialExtent
        :param date_of_interest:
        :type date_of_interest:
        :param max_after:
        :type max_after:
        :param max_before:
        :type max_before:
        :param runAsync: if True (default), the visibility check is run in a parallel task
        :param ext: SpatialExtent
        """
        assert isinstance(ext, SpatialExtent)

        if runAsync is None:
            from eotimeseriesviewer.settings import value, Keys
            runAsync = value(Keys.QgsTaskAsync, True)

        tssToTest: List[TimeSeriesSource] = []
        if isinstance(ext, SpatialExtent):
            changed = False
            for tsd in self:
                assert isinstance(tsd, TimeSeriesDate)
                tssToTest.extend(tsd[:])
                # for tss in tsd[:]:
                #    assert isinstance(tss, TimeSeriesSource)
                #    tssToTest.(tss)

        if len(tssToTest) > 0:
            from eotimeseriesviewer.settings import value, Keys

            qgsTask = TimeSeriesFindOverlapTask(ext,
                                                tssToTest,
                                                date_of_interest=date_of_interest,
                                                max_backward=max_before,
                                                max_forward=max_after,
                                                sample_size=value(Keys.RasterOverlapSampleSize),
                                                callback=self.onTaskFinished)

            qgsTask.sigTimeSeriesSourceOverlap.connect(self.onFoundOverlap)
            qgsTask.progressChanged.connect(self.sigProgress.emit)

            if True and runAsync:
                tm = QgsApplication.taskManager()
                assert isinstance(tm, QgsTaskManager)
                # stop previous tasks, allow to run one only
                for t in tm.tasks():
                    if isinstance(t, TimeSeriesFindOverlapTask):
                        t.cancel()
                tm.addTask(qgsTask)
            else:
                qgsTask.finished(qgsTask.run())

    def onFoundOverlap(self, results: dict):

        URI2TSS = dict()
        for tsd in self:
            for tss in tsd:
                URI2TSS[tss.uri()] = tss

        affectedTSDs = set()
        for tssUri, b in results.items():
            assert isinstance(tssUri, str)
            tss = URI2TSS.get(tssUri, None)
            if isinstance(tss, TimeSeriesSource):
                tss.setIsVisible(b)
                tsd = tss.timeSeriesDate()
                if isinstance(tsd, TimeSeriesDate):
                    affectedTSDs.add(tsd)
        if len(affectedTSDs) == 0:
            return

        affectedTSDs = sorted(affectedTSDs)

        rowMin = rowMax = None
        for i, tsd in enumerate(affectedTSDs):
            idx = self.tsdToIdx(tsd)
            if i == 0:
                rowMin = rowMax = idx.row()
            else:
                rowMin = min(rowMin, idx.row())
                rowMax = max(rowMax, idx.row())

        idx0 = self.index(rowMin, 0)
        idx1 = self.index(rowMax, 0)
        self.dataChanged.emit(idx0, idx1, [Qt.CheckStateRole])

    def setVisibleDates(self, tsds: list):
        """
        Sets the TimeSeriesDates currently shown
        :param tsds: [list-of-TimeSeriesDate]
        """
        self.mVisibleDates.clear()
        self.mVisibleDates.update(tsds)
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDate)
            if tsd in self:
                idx = self.tsdToIdx(tsd)
                # force reset of background color
                idx2 = self.index(idx.row(), self.columnCount() - 1)
                self.dataChanged.emit(idx, idx2, [Qt.BackgroundColorRole])

    def findMatchingSensor(self, sensorID: str) -> SensorInstrument:
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

    def sensor(self, sensor_id: str) -> SensorInstrument:
        """
        Returns the sensor with sid = sid
        :param sensor_id: str, sensor id
        :return: SensorInstrument
        """
        assert isinstance(sensor_id, str)

        nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorIDtoProperties(sensor_id)

        refValues = (nb, px_size_y, px_size_x, dt, wl, wlu, name)
        for sensor in self.sensors():
            sValues = (
                sensor.nb, sensor.px_size_y, sensor.px_size_x, sensor.dataType, sensor.wl, sensor.wlu,
                sensor.mNameOriginal)
            if refValues == sValues:
                return sensor

        return None

    def sensors(self) -> List[SensorInstrument]:
        """
        Returns the list of sensors derived from the TimeSeries data sources
        :return: [list-of-SensorInstruments]
        """
        return self.mSensors[:]

    def loadFromFile(self, path: Union[str, pathlib.Path], n_max=None, runAsync: bool = None):
        """
        Loads a CSV file with source images of a TimeSeries
        :param path: str, Path of CSV file
        :param n_max: optional, maximum number of files to load
        :param runAsync: optional,
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

    def saveToFile(self, path, relative_path: bool = True):
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
                uri = TSS.source()
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

    def maxSpatialExtent(self, crs: QgsCoordinateReferenceSystem = None) -> SpatialExtent:
        """
        Returns the maximum SpatialExtent of all images of the TimeSeries
        :param crs: QgsCoordinateSystem to express the SpatialExtent coordinates.
        :return:
        """
        extent = None
        for i, tsd in enumerate(self.mTSDs):
            assert isinstance(tsd, TimeSeriesDate)
            ext = tsd.spatialExtent(crs=crs)
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

    def tsd(self, dtr: QgsDateTimeRange, sensor: Union[SensorInstrument, str]) -> Optional[TimeSeriesDate]:
        """
        Returns the TimeSeriesDate identified by date-time-range and sensorID
        :param dtr: numpy.datetime64
        :param sensor: SensorInstrument | str with sensor id
        :return:
        """
        assert isinstance(dtr, QgsDateTimeRange)
        if isinstance(sensor, str):
            sensor = self.sensor(sensor)

        if isinstance(sensor, SensorInstrument):
            for tsd in self.mTSDs:
                if tsd.dateTimeRange() == dtr and tsd.sensor() == sensor:
                    return tsd
        else:
            for tsd in self.mTSDs:
                if tsd.dateTimeRange() == dtr:
                    return tsd
        return None

    def insertTSD(self, tsd: TimeSeriesDate) -> TimeSeriesDate:
        """
        Inserts a TimeSeriesDate
        :param tsd: TimeSeriesDate
        """
        # insert sorted by time & sensor
        assert tsd not in self.mTSDs
        assert tsd.sensor() in self.mSensors

        tsd.mTimeSeries = self
        tsd.sigRemoveMe.connect(lambda t=tsd: self.removeTSDs([t]))

        tsd.rowsAboutToBeRemoved.connect(
            lambda p, first, last, t=tsd: self.beginRemoveRows(self.tsdToIdx(t), first, last))
        tsd.rowsRemoved.connect(self.endRemoveRows)
        tsd.rowsAboutToBeInserted.connect(
            lambda p, first, last, t=tsd: self.beginInsertRows(self.tsdToIdx(t), first, last))
        tsd.rowsInserted.connect(self.endInsertRows)

        tsd.sigSourcesAdded.connect(self.sigSourcesAdded)
        tsd.sigSourcesRemoved.connect(self.sigSourcesRemoved)

        row = bisect.bisect(self.mTSDs, tsd)
        self.beginInsertRows(self.mRootIndex, row, row)
        self.mTSDs.insert(row, tsd)
        self.endInsertRows()
        return tsd

    def showTSDs(self, tsds: list, b: bool = True):
        tsds = sorted(set([t for t in tsds if t in self]))
        if len(tsds) == 0:
            return

        idx0 = self.tsdToIdx(tsds[0])
        idx1 = self.tsdToIdx(tsds[-1])

        for i, tsd in enumerate(tsds):
            assert isinstance(tsd, TimeSeriesDate)
            for tss in tsd:
                tss.setIsVisible(b)

        self.dataChanged.emit(idx0, idx1, [Qt.CheckStateRole])
        self.sigVisibilityChanged.emit()

    def hideTSDs(self, tsds):
        self.showTSDs(tsds, False)

    def removeTSDs(self, tsds: List[TimeSeriesDate]):
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
        toRemove = sorted(list(toRemove))
        removed = []
        while len(toRemove) > 0:
            block: List[TimeSeriesDate] = [toRemove.pop(0)]

            r0 = r1 = self.tsdToIdx(block[0]).row()
            while len(toRemove) > 0:
                if self.index(r1 + 1, 0).data(Qt.UserRole) != toRemove[0]:
                    break
                else:
                    block.append(toRemove.pop(0))
                    r1 += 1

            self.beginRemoveRows(self.mRootIndex, r0, r1)
            for tsd in block:
                self.mTSDs.remove(tsd)
                tsd.mTimeSeries = None
                tsd.sigSourcesAdded.disconnect(self.sigSourcesAdded)
                tsd.sigSourcesRemoved.disconnect(self.sigSourcesRemoved)

                removed.append(tsd)
            self.endRemoveRows()

        if len(removed) > 0:
            pathsToRemove = [path for path, tsd in self.mLUT_Path2TSD.items() if tsd in removed]
            for path in pathsToRemove:
                self.mLUT_Path2TSD.pop(path)

            self.checkSensorList()
            self.sigTimeSeriesDatesRemoved.emit(removed)

    def timeSeriesSources(self,
                          copy: Optional[bool] = False,
                          sensor: Optional[SensorInstrument] = None) -> List[TimeSeriesSource]:
        """
        Returns a flat list of all sources
        :param copy:
        :return:
        """
        if isinstance(sensor, SensorInstrument):
            tsds = self.tsds(None, sensor)
        else:
            tsds = self[:]

        for tsd in tsds:
            for tss in tsd:
                if copy:
                    tss = tss.clone()
                yield tss

    def tsds(self, date: np.datetime64 = None, sensor: SensorInstrument = None) -> List[TimeSeriesDate]:

        """
        Returns a list of  TimeSeriesDate of the TimeSeries. By default all TimeSeriesDate will be returned.
        :param date: numpy.datetime64 to return the TimeSeriesDate for
        :param sensor: SensorInstrument of interest to return the [list-of-TimeSeriesDate] for.
        :return: [list-of-TimeSeriesDate]
        """
        tsds = self.mTSDs[:]
        if date:
            tsds = [tsd for tsd in tsds if tsd.dtg() == date]
        if sensor:
            tsds = [tsd for tsd in tsds if tsd.sensor() == sensor]
        return tsds

    def clear(self):
        """
        Removes all data sources from the TimeSeries (which will be empty after calling this routine).
        """
        self.removeTSDs(self[:])

    def addSensor(self, sensor: SensorInstrument):
        """
        Adds a Sensor
        :param sensor: SensorInstrument
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor not in self.mSensors:
            sensor.sigNameChanged.connect(self.onSensorNameChanged)
            self.mSensors.append(sensor)
            self.sigSensorAdded.emit(sensor)
            return sensor
        else:
            return None

    def onSensorNameChanged(self, name: str):
        sensor = self.sender()

        if isinstance(sensor, SensorInstrument) and sensor in self.sensors():
            idx0 = self.index(0, self.cSensor)
            idx1 = self.index(self.rowCount() - 1, self.cSensor)
            self.dataChanged.emit(idx0, idx1)
            self.sigSensorNameChanged.emit(sensor)
        s = ""

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

    def removeSensor(self, sensor: SensorInstrument) -> SensorInstrument:
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

    def addTimeSeriesSources(self, sources: List[TimeSeriesSource]):
        """
        Adds a list of time series sources to the time series
        :param sources:  list-of-TimeSeriesSources
        """
        assert isinstance(sources, list)
        # print('Add TSS...', flush=True)
        addedDates = []
        for i, source in enumerate(sources):
            assert isinstance(source, TimeSeriesSource)
            newTSD = self.addTimeSeriesSource(source)
            if isinstance(newTSD, TimeSeriesDate):
                addedDates.append(newTSD)

        if len(addedDates) > 0:
            self.sigTimeSeriesDatesAdded.emit(addedDates)

    def addSources(self,
                   sources: list,
                   visibility: List[bool] = None,
                   runAsync: bool = None):
        """
        Adds source images to the TimeSeries
        :param visibility:
        :param sources: list of source images, e.g. a list of file paths
        :param runAsync: bool
        """
        from eotimeseriesviewer.settings import value, Keys

        if runAsync is None:
            runAsync = value(Keys.QgsTaskAsync, True)

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

        qgsTask = TimeSeriesLoadingTask(sourcePaths,
                                        visibility=visibility,
                                        callback=self.onTaskFinished,
                                        )

        # tid = id(qgsTask)
        # self.mTasks[tid] = qgsTask
        # qgsTask.taskCompleted.connect(lambda *args, tid=tid: self.onRemoveTask(tid))
        # qgsTask.taskTerminated.connect(lambda *args, tid=tid: self.onRemoveTask(tid))
        qgsTask.sigFoundSources.connect(self.addTimeSeriesSources)
        qgsTask.progressChanged.connect(self.sigProgress.emit)

        self.mTasks[id(qgsTask)] = qgsTask

        if runAsync:
            tm: QgsTaskManager = QgsApplication.taskManager()
            assert isinstance(tm, QgsTaskManager)
            tm.addTask(qgsTask)
        else:
            qgsTask.finished(qgsTask.run())

    def onRemoveTask(self, key):
        # print(f'remove {key}', flush=True)
        if isinstance(key, QgsTask):
            key = id(key)
        if key in self.mTasks.keys():
            self.mTasks.pop(key)

    def onTaskFinished(self, success, task: QgsTask):
        # print(':: onAddSourcesAsyncFinished')
        if isinstance(task, TimeSeriesLoadingTask):
            if len(task.mInvalidSources) > 0:
                info = ['Unable to load {} data source(s):'.format(len(task.mInvalidSources))]
                for (s, ex) in task.mInvalidSources:
                    info.append('Path="{}"\nError="{}"'.format(str(s), str(ex).replace('\n', ' ')))
                info = '\n'.join(info)
                messageLog(info, Qgis.Critical)

            self.sigLoadingTaskFinished.emit()

        elif isinstance(task, TimeSeriesFindOverlapTask):
            if success:
                if len(task.mIntersections) > 0:
                    self.onFoundOverlap(task.mIntersections)
            self.sigFindOverlapTaskFinished.emit()
        tm: QgsTaskManager = QgsApplication.taskManager()

        self.onRemoveTask(task)

    def addTimeSeriesSource(self, tss: TimeSeriesSource) -> TimeSeriesDate:
        """
        :param source:
        :return: TimeSeriesDate (if new created)
        """
        assert isinstance(tss, TimeSeriesSource)

        newTSD = None

        tsr: QgsDateTimeRange = ImageDateUtils.dateRange(tss.dtg(), self.mDateTimePrecision)

        sid = tss.sid()
        sensor = self.findMatchingSensor(sid)

        # if necessary, add a new sensor instance
        if not isinstance(sensor, SensorInstrument):
            sensor = SensorInstrument(sid)
            sensor = self.addSensor(sensor)
            assert isinstance(sensor, SensorInstrument)
        assert isinstance(sensor, SensorInstrument)
        tsd = self.tsd(tsr, sensor)

        # if necessary, add a new TimeSeriesDate instance
        if not isinstance(tsd, TimeSeriesDate):
            tsd = TimeSeriesDate(tsr, sensor)
            tsd.mTimeSeries = self
            newTSD = self.insertTSD(tsd)
            assert tsd == newTSD
            # addedDates.append(tsd)
        assert isinstance(tsd, TimeSeriesDate)

        # add the source

        tsd.addSource(tss)
        self.mLUT_Path2TSD[tss.source()] = tsd
        return newTSD

    def dateTimePrecision(self) -> DateTimePrecision:
        return self.mDateTimePrecision

    def setDateTimePrecision(self, mode: DateTimePrecision):
        """
        Sets the precision with which the parsed DateTime information will be handled.
        :param mode: TimeSeriesViewer:DateTimePrecision
        :return:
        """
        assert isinstance(mode, DateTimePrecision)
        all_sources = list(self.timeSeriesSources())
        self.beginResetModel()
        self.clear()
        self.mDateTimePrecision = mode
        self.addTimeSeriesSources(all_sources)
        self.endResetModel()
        # do we like to update existing sources?

    def setSensorMatching(self, flags: SensorMatching):
        """
        Sets the mode under which two source images can be considered as to be from the same sensor/product
        :param flags:
        :return:
        """
        assert isinstance(flags, SensorMatching)
        assert bool(flags & SensorMatching.PX_DIMS), 'SensorMatching flags PX_DIMS needs to be set'
        self.mSensorMatchingFlags = flags

    def sources(self) -> List[TimeSeriesSource]:
        """
        Returns the input sources
        :return: iterator over [list-of-TimeSeriesSources]
        """

        for tsd in self:
            for source in tsd:
                yield source

    def sourceUris(self) -> List[str]:
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

    def __iter__(self) -> Iterator[TimeSeriesDate]:
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

    def rowCount(self, index: QModelIndex = None) -> int:
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

    def columnCount(self, index: QModelIndex = None) -> int:
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

    def tsdToIdx(self, tsd: TimeSeriesDate) -> QModelIndex:
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

    def visibleTSDs(self) -> List[TimeSeriesDate]:
        """
        Returns the visible TSDs (which have TimeSeriesSource to be shown)
        :return:
        :rtype:
        """
        return [tsd for tsd in self if not tsd.checkState() == Qt.Unchecked]

    def asMap(self) -> dict:

        d = {}
        sources = []
        for tss in self.timeSeriesSources():
            tss: TimeSeriesSource
            sources.append({
                'uri': tss.mUri,
                'visible': tss.isVisible()
            })
        d['sources'] = sources
        return d

    def fromMap(self, data: dict, feedback: QgsProcessingFeedback = QgsProcessingFeedback()):

        multistep = QgsProcessingMultiStepFeedback(4, feedback)
        multistep.setCurrentStep(1)
        multistep.setProgressText('Clean')
        self.clear()

        uri_vis = dict()

        multistep.setCurrentStep(2)
        multistep.setProgressText('Read Sources')
        sources = []

        for d in data.get('sources', []):
            uri = d.get('uri')

            if uri:
                tss = TimeSeriesSource.create(uri)
                uri_vis[tss.uri()] = d.get('visible', True)
                if isinstance(tss, TimeSeriesSource):
                    sources.append(tss)

        multistep.setCurrentStep(3)
        multistep.setProgressText('Add Sources')

        if len(sources) > 0:
            self.addTimeSeriesSources(sources)

        for tss in self.timeSeriesSources():
            tss.setIsVisible(uri_vis.get(tss.uri(), tss.isVisible()))

    def data(self, index: QModelIndex, role: Qt.DisplayRole):
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

        c = index.column()

        if isinstance(node, TimeSeriesSource):
            if role in [Qt.DisplayRole]:
                if c == self.cDate:
                    return tss.dtg().toString(Qt.ISODate)
                if c == self.cImages:
                    return tss.source()
                if c == self.cNB:
                    return tss.nb
                if c == self.cNL:
                    return tss.nl
                if c == self.cNS:
                    return tss.ns
                if c == self.cCRS:
                    return tss.crs().description()
                if c == self.cSensor:
                    return tsd.sensor().name()

            if role == Qt.CheckStateRole and c == 0:
                return Qt.Checked if node.isVisible() else Qt.Unchecked

            if role == Qt.DecorationRole and c == 0:
                return None

            if role == Qt.BackgroundColorRole and tsd in self.mVisibleDates:
                return QColor('yellow')

        if isinstance(node, TimeSeriesDate):
            if role in [Qt.DisplayRole]:
                if c == self.cSensor:
                    return tsd.sensor().name()
                if c == self.cImages:
                    return len(tsd)
                if c == self.cDate:
                    return self.dateRangeString(tsd.dateTimeRange())

            if role == Qt.CheckStateRole and index.column() == 0:
                return node.checkState()

            if role == Qt.BackgroundColorRole and tsd in self.mVisibleDates:
                return QColor('yellow')

        return None

    def dateRangeString(self, dateTimeRange: QgsDateTimeRange):

        return dateTimeRange.begin().toString(Qt.ISODate)

    def setData(self, index: QModelIndex, value: Any, role: int):

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
                                          self.index(self.rowCount(index) - 1, 0, index),
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

    def findDate(self, date) -> Optional[TimeSeriesDate]:
        """
        Returns a TimeSeriesDate closest to that in date
        :param date: QDateTime | str | TimeSeriesDate
        :return: TimeSeriesDate
        """
        if isinstance(date, TimeSeriesDate):
            date = date.dtg()
        elif isinstance(date, str):
            date = QDateTime.fromString(date, Qt.ISODateWithMs)

        assert isinstance(date, QDateTime)

        if len(self) == 0:
            return None

        secs2date = [date.secsTo(tsd.dtg()) for tsd in self.mTSDs]
        i = np.argmin(np.abs(np.asarray(secs2date)))
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
    sigMoveToDate = pyqtSignal(TimeSeriesDate)
    sigMoveToSource = pyqtSignal(TimeSeriesSource)
    sigMoveToExtent = pyqtSignal(SpatialExtent)
    sigSetMapCrs = pyqtSignal(QgsCoordinateReferenceSystem)

    def __init__(self, parent=None):
        super(TimeSeriesTreeView, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        md: QMimeData = event.mimeData()
        for format in TimeSeriesSource.MIMEDATA_FORMATS:
            if format in md.formats():
                event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        md: QMimeData = event.mimeData()
        local_files = []
        local_ts_lists = []
        if md.hasUrls():
            for url in md.urls():
                url: QUrl
                if url.isLocalFile():
                    path = pathlib.Path(url.toLocalFile())
                    if re.search(r'\.(txt|csv)$', path.name):
                        local_ts_lists.append(path)
                    else:
                        local_files.append(path)
        event.acceptProposedAction()
        if len(local_files) > 0:
            self.timeseries().addSources(local_files)
        if len(local_ts_lists) > 0:
            for file in local_ts_lists:
                self.timeseries().loadFromFile(file)

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
            a = menu.addAction('Move to date {}'.format(node.dtg()))
            a.setToolTip(f'Sets the current map date to {node.dtg()}.')
            a.triggered.connect(lambda *args, tsd=node: self.sigMoveToDate.emit(tsd))

            a = menu.addAction('Move to extent {}'.format(node.dtg()))
            a.setToolTip('Sets the current map extent')
            a.triggered.connect(lambda *args, tsd=node: self.onMoveToExtent(tsd.spatialExtent()))

            menu.addSeparator()

        elif isinstance(node, TimeSeriesSource):

            a = menu.addAction('Show {}'.format(node.name()))
            a.setToolTip(f'Sets the current map date to {node.dtg()} and zooms\nto the spatial extent of {node.uri()}')
            a.triggered.connect(lambda *args, tss=node: self.sigMoveToSource.emit(tss))

            a = menu.addAction(f'Set map CRS from {node.name()}')
            a.setToolTip(f'Sets the map projection to {node.crs().description()}')
            a.triggered.connect(lambda *args, crs=node.crs(): self.sigSetMapCrs.emit(crs))

            menu.addSeparator()

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

    def onMoveToExtent(self, extent: SpatialExtent):
        if isinstance(extent, SpatialExtent):
            self.sigMoveToExtent.emit(extent)

    def openInQGIS(self, tssList: List[TimeSeriesSource]):
        import qgis.utils
        iface = qgis.utils.iface
        if isinstance(iface, QgisInterface):
            layers = [tss.asRasterLayer() for tss in tssList]
            QgsProject.instance().addMapLayers(layers, True)

    def setClipboardUris(self, tssList: List[TimeSeriesSource]):
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

        QgsApplication.clipboard().setMimeData(md)

    def timeseries(self) -> TimeSeries:
        return self.model().sourceModel()

    def onSetCheckState(self, tsds: List[TimeSeriesDate], checkState: Qt.CheckStateRole):
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
            QgsApplication.clipboard().setText(info)


regSensorName = re.compile(r'(SATELLITEID|(sensor|product)[ _]?(type|name))', re.IGNORECASE)

rxSensorName = re.compile(r'<li>(SATELLITEID|(sensor|product)[ _]?(type|name))=(?P<name>[^<]+)</li>', re.I)


def sensorName(layer: QgsRasterLayer) -> Optional[str]:
    """
    Reads the sensor/product name. Returns None if a proper name can not be extracted.
    :param dataset: gdal.Dataset
    :return: str
    """
    assert isinstance(layer, QgsRasterLayer) and layer.isValid()

    html = layer.htmlMetadata()
    match = rxSensorName.search(html)
    if match:
        return match.group('name')
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


def extractWavelengthsFromGDALMetaData(ds: gdal.Dataset) -> (list, str):
    """
    Reads the wavelength info from standard metadata strings
    :param ds: gdal.Dataset
    :return: (list, str)
    """

    regWLkey = re.compile('^(center )?wavelength[_ ]*$', re.I)
    regWLUkey = re.compile('^wavelength[_ ]*units?$', re.I)
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)", re.I)

    def findKey(d: dict, regex) -> str:
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


def extractWavelengthsFromRapidEyeXML(ds: gdal.Dataset, dom: QDomDocument) -> (list, str):
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


def extractWavelengthsFromDIMAPXML(ds: gdal.Dataset, dom: QDomDocument) -> (list, str):
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
                    tmp = re.findall(r'\d*\.\d+|\d+', value)  # find floats
                    if len(tmp) == 0:
                        tmp = re.findall(r'\d+', value)  # find integers
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
            return isinstance(wl, list) and len(wl) == ds.RasterCount and isinstance(wlu,
                                                                                     str) and wlu in LUT_WAVELENGTH_UNITS.keys()

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


class TimeSeriesFilterModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setRecursiveFilteringEnabled(True)
        # self.setSortRole(Qt.EditRole)
        # self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        reg = self.filterRegExp()
        if reg.isEmpty():
            return True

        for c in range(self.sourceModel().columnCount()):
            idx = self.sourceModel().index(sourceRow, c, parent=sourceParent)
            value = idx.data(Qt.DisplayRole)
            value = str(value)
            if reg.indexIn(value) >= 0:
                return True

        return False


class TimeSeriesWidget(QMainWindow):
    sigTimeSeriesDatesSelected = pyqtSignal(bool)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(DIR_UI / 'timeserieswidget.ui', self)

        self.mTimeSeriesTreeView: TimeSeriesTreeView
        assert isinstance(self.mTimeSeriesTreeView, TimeSeriesTreeView)
        self.mTimeSeries: TimeSeries = None
        self.mTSProxyModel: TimeSeriesFilterModel = TimeSeriesFilterModel()
        self.mSelectionModel = None
        self.mLastDate: TimeSeriesDate = None
        self.optionFollowCurrentDate: QAction
        self.optionFollowCurrentDate.toggled.connect(lambda: self.setCurrentDate(self.mLastDate))
        self.optionUseRegex: QAction
        self.optionCaseSensitive: QAction
        self.btnUseRegex.setDefaultAction(self.optionUseRegex)
        self.btnCaseSensitive.setDefaultAction(self.optionCaseSensitive)
        self.optionCaseSensitive.toggled.connect(self.onFilterExpressionChanged)
        self.optionUseRegex.toggled.connect(self.onFilterExpressionChanged)
        self.tbFilterExpression.textChanged.connect(self.onFilterExpressionChanged)

    def onFilterExpressionChanged(self, *args):
        expression: str = self.tbFilterExpression.text()

        useRegex: bool = self.optionUseRegex.isChecked()

        if self.optionCaseSensitive.isChecked():
            sensitivity = Qt.CaseSensitive
        else:
            sensitivity = Qt.CaseInsensitive
        self.mTSProxyModel.setFilterCaseSensitivity(sensitivity)
        if useRegex:
            rx = QRegExp(expression, sensitivity)
            self.mTSProxyModel.setFilterRegExp(rx)
        else:
            self.mTSProxyModel.setFilterWildcard(expression)

    def toolBar(self) -> QToolBar:
        return self.mToolBar

    def setCurrentDate(self, tsd: TimeSeriesDate):
        """
        Checks if optionFollowCurrentDate is checked. If True, will call setTSD to focus on the TimeSeriesDate
        :param tsd: TimeSeriesDate
        :type tsd:
        :return:
        :rtype:
        """
        self.mLastDate = tsd
        if not isinstance(tsd, TimeSeriesDate):
            return
        if self.optionFollowCurrentDate.isChecked():
            self.moveToDate(tsd)

    def moveToDate(self, tsd: TimeSeriesDate):
        tstv = self.timeSeriesTreeView()
        assert isinstance(tstv, TimeSeriesTreeView)
        assert isinstance(self.mTSProxyModel, QSortFilterProxyModel)

        assert isinstance(self.mTimeSeries, TimeSeries)
        idxSrc = self.mTimeSeries.tsdToIdx(tsd)

        if isinstance(idxSrc, QModelIndex):
            idx2 = self.mTSProxyModel.mapFromSource(idxSrc)
            if isinstance(idx2, QModelIndex):
                tstv.setCurrentIndex(idx2)
                tstv.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

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
        self.mStatusBar.showMessage(info, 0)

    def onSelectionChanged(self, *args):
        """
        Slot to react on user-driven changes of the selected TimeSeriesDate rows.
        """
        b = isinstance(self.mSelectionModel, QItemSelectionModel) and len(self.mSelectionModel.selectedRows()) > 0

        self.sigTimeSeriesDatesSelected.emit(b)

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

    def setTimeSeries(self, TS: TimeSeries):
        """
        Sets the TimeSeries to be shown in the TimeSeriesDockUI
        :param TS: TimeSeries
        """
        from eotimeseriesviewer.timeseries import TimeSeries

        if isinstance(TS, TimeSeries):
            self.mTimeSeries = TS
            self.mTSProxyModel.setSourceModel(self.mTimeSeries)
            self.mSelectionModel = QItemSelectionModel(self.mTSProxyModel)
            self.mSelectionModel.selectionChanged.connect(self.onSelectionChanged)

            tstv = self.timeSeriesTreeView()
            tstv.setModel(self.mTSProxyModel)
            tstv.setSelectionModel(self.mSelectionModel)
            tstv.sortByColumn(0, Qt.AscendingOrder)

            for c in range(self.mTSProxyModel.columnCount()):
                self.timeSeriesTreeView().header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.mTimeSeries.rowsInserted.connect(self.updateSummary)
            # self.mTimeSeries.dataChanged.connect(self.updateSummary)
            self.mTimeSeries.rowsRemoved.connect(self.updateSummary)
            # TS.sigLoadingProgress.connect(self.setProgressInfo)

        self.onSelectionChanged()

    def timeSeriesTreeView(self) -> TimeSeriesTreeView:
        return self.mTimeSeriesTreeView


class TimeSeriesDock(QgsDockWidget):
    """
    QgsDockWidget that wraps the TimeSeriesWidget
    """

    def __init__(self, parent=None):
        super(TimeSeriesDock, self).__init__(parent)
        self.setWindowTitle('Time Series')
        self.mTimeSeriesWidget = TimeSeriesWidget()
        self.setWidget(self.mTimeSeriesWidget)

    def timeSeriesWidget(self) -> TimeSeriesWidget:
        return self.mTimeSeriesWidget


def has_sensor_id(layer) -> bool:
    return sensor_id(layer) is not None


def sensor_id(layer) -> Optional[str]:
    if isinstance(layer, QgsRasterLayer):

        if SensorInstrument.PROPERTY_KEY in layer.customPropertyKeys():
            return layer.customProperty(SensorInstrument.PROPERTY_KEY)
        else:
            # retries key and add to layer:
            sid = create_sensor_id(layer)
            layer.setCustomProperty(SensorInstrument.PROPERTY_KEY, sid)
            return sid
    else:
        return None
