import enum
import json
import re
from typing import Optional

import numpy as np
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsDataProvider, QgsMessageLog, QgsPointXY, \
    QgsProviderMetadata, QgsProviderRegistry, QgsRasterDataProvider, QgsRasterInterface, QgsRasterLayer, QgsRectangle
from qgis.PyQt.QtCore import pyqtSignal, QObject
from qgis.PyQt import sip
from osgeo import gdal

from eotimeseriesviewer.qgispluginsupport.qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from eotimeseriesviewer.qgispluginsupport.qps.unitmodel import UnitLookup
from eotimeseriesviewer.qgispluginsupport.qps.utils import LUT_WAVELENGTH

GDAL_DATATYPES = {}
for var in vars(gdal):
    match = re.search(r'^GDT_(?P<type>.*)$', var)
    if match:
        number = getattr(gdal, var)
        GDAL_DATATYPES[match.group('type')] = number
        GDAL_DATATYPES[match.group()] = number


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
