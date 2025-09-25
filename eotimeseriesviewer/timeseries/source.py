import json
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

from osgeo import gdal
from qgis.PyQt.QtCore import QMetaType, QPoint
from qgis.PyQt.QtCore import pyqtSignal, QAbstractTableModel, QDate, QDateTime, QMimeData, QModelIndex, Qt
from qgis.core import QgsCoordinateReferenceSystem, QgsDateTimeRange, QgsExpressionContextScope, QgsGeometry, \
    QgsMimeDataUtils, QgsRasterLayer, QgsRasterLayerTemporalProperties, QgsRectangle
from qgis.core import QgsFeature, QgsFields, QgsField, QgsCoordinateTransform, QgsProject, Qgis

from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent, px2geo
from eotimeseriesviewer.sensors import create_sensor_id, SensorInstrument


class TimeSeriesException(Exception):
    pass


def datasetExtent(ds: gdal.Dataset) -> Tuple[QgsCoordinateReferenceSystem, QgsGeometry]:
    """
    Returns the CRS and the extent as QgsGeometry of a gdal.Dataset
    :param ds:
    :return:
    """
    assert isinstance(ds, gdal.Dataset)

    gt = ds.GetGeoTransform()
    ul = px2geo(QPoint(0, 0), gt, pxCenter=False)
    ur = px2geo(QPoint(ds.RasterXSize, 0), gt, pxCenter=False)
    lr = px2geo(QPoint(ds.RasterXSize, ds.RasterYSize), gt, pxCenter=False)
    ll = px2geo(QPoint(0, ds.RasterYSize), gt, pxCenter=False)
    crs = QgsCoordinateReferenceSystem(ds.GetProjectionRef())
    extent = QgsGeometry.fromPolygonXY([[ul, ur, lr, ll, ul]])
    return crs, extent


class TimeSeriesSource(object):
    """Provides information on source images"""

    MIMEDATA_FORMATS = ['text/uri-list']

    MKeyDateTime = 'datetime'
    MKeySource = 'source'
    MKeyProvider = 'provider'
    MKeyName = 'name'
    MKeySensor = 'sid'
    MKeyDimensions = 'dims'
    MKeyCrs = 'crs'
    MKeyExtent = 'extent'
    MKeyIsVisible = 'visible'

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

        data = json.loads(jsonData)

        return cls.fromMap(data)

    @classmethod
    def fromMap(cls, d: dict) -> 'TimeSeriesSource':
        provider = d[TimeSeriesSource.MKeyProvider]
        source = d[TimeSeriesSource.MKeySource]
        name = d.get(TimeSeriesSource.MKeyName, '')
        sid = d[TimeSeriesSource.MKeySensor]
        dtg = d[TimeSeriesSource.MKeyDateTime]
        crs = d[TimeSeriesSource.MKeyCrs]
        extent = d[TimeSeriesSource.MKeyExtent]
        dims = d[TimeSeriesSource.MKeyDimensions]

        #             source=ds.GetDescription(),
        #             dtg=dtg,
        #             sid=sid,
        #             dims=dims,
        #             crs=crs,
        #             extent=extent,
        #             provider='gdal',
        #             name=name

        return TimeSeriesSource(source, dtg, sid, dims, crs, extent, provider, name=name)

        if provider == 'gdal':
            ds = gdal.Open(d[TimeSeriesSource.MKeySource])
            return TimeSeriesSource.fromGDALDataset(ds,
                                                    name=d.get(TimeSeriesSource.MKeyName))
        else:
            layer = QgsRasterLayer(d[TimeSeriesSource.MKeySource],
                                   name=d.get(TimeSeriesSource.MKeyName),
                                   providerType=d.get(TimeSeriesSource.MKeyProvider))
            dtg = QDateTime.fromString(d[TimeSeriesSource.MKeyDateTime], Qt.ISODateWithMs)
            return TimeSeriesSource(layer, dtg)

    def qgsMimeDataUtilsUri(self) -> QgsMimeDataUtils.Uri:

        uri = QgsMimeDataUtils.Uri(self.asRasterLayer())
        return uri

    @classmethod
    def px2geo(cls, x, y, gt) -> Tuple[float, float]:
        return gt[0] + x * gt[1] + y * gt[2], \
               gt[3] + x * gt[4] + y * gt[5]

    @classmethod
    def fromGDALDataset(cls,
                        ds: Union[str, Path, gdal.Dataset],
                        dtg: Optional[QDateTime] = None,
                        name: Optional[str] = None) -> 'TimeSeriesSource':

        if isinstance(ds, (str, Path)):
            ds = gdal.Open(str(ds))

        assert isinstance(ds, gdal.Dataset), f'Unable to open {ds} as gdal.Dataset'

        crs, extent = datasetExtent(ds)
        assert crs.isValid()

        if dtg is None:
            dtg = ImageDateUtils.dateTimeFromGDALDataset(ds)
        assert isinstance(dtg, QDateTime) and dtg.isValid()

        if not isinstance(name, str):
            name = Path(ds.GetDescription()).name

        sid = create_sensor_id(ds)
        dims = [ds.RasterCount, ds.RasterYSize, ds.RasterXSize]
        tss = TimeSeriesSource(
            source=ds.GetDescription(),
            dtg=dtg,
            sid=sid,
            dims=dims,
            crs=crs,
            extent=extent,
            provider='gdal',
            name=name
        )
        return tss

    @classmethod
    def fromQgsRasterLayer(cls,
                           layer: QgsRasterLayer,
                           dtg: Optional[QDateTime] = None,
                           name: Optional[str] = None):

        assert isinstance(layer, QgsRasterLayer) and layer.isValid()
        if dtg is None:
            dtg = ImageDateUtils.dateTimeFromLayer(layer)
        assert isinstance(dtg, QDateTime) and dtg.isValid()
        if name is None:
            name = layer.name()
            if name == '':
                name = Path(layer.source()).name
        assert isinstance(name, str) and len(name) > 0

        sid = create_sensor_id(layer)
        dims = [layer.bandCount(), layer.height(), layer.width()]
        tss = TimeSeriesSource(
            source=layer.source(),
            dtg=dtg,
            sid=sid,
            dims=dims,
            crs=layer.crs(),
            extent=QgsGeometry.fromRect(layer.extent()),
            provider='gdal',
            name=name
        )
        return tss

    @classmethod
    def create(cls, source: Union[QgsRasterLayer, str, Path]) -> 'TimeSeriesSource':
        """
        Reads the argument and returns a TimeSeriesSource
        :param source: gdal.Dataset, str or QgsRasterLayer
        :return: TimeSeriesSource
        """
        if isinstance(source, QgsRasterLayer):
            return cls.fromQgsRasterLayer(source)
        else:
            return cls.fromGDALDataset(source)

    FIELDS = QgsFields()
    FIELDS.append(QgsField(MKeySource, QMetaType.QString))
    FIELDS.append(QgsField(MKeyName, QMetaType.QString))
    FIELDS.append(QgsField(MKeyProvider, QMetaType.QString))
    FIELDS.append(QgsField(MKeySensor, QMetaType.QString))
    FIELDS.append(QgsField(MKeyDateTime, QMetaType.QDateTime))

    CRS = QgsCoordinateReferenceSystem('EPSG:4326')

    def __init__(self,
                 source: str,
                 dtg: Union[str, QDateTime],
                 sid: str,
                 dims: List[int],
                 crs: Union[str, QgsCoordinateReferenceSystem],
                 extent: Union[str, QgsGeometry],
                 provider: str = 'gdal',
                 name: Optional[str] = None):
        """
        :param source: path to source
        :param dtg: date-time of observation
        :param sid: sensor id
        :param dims: source dimensions (nb, nl, ns)
        :param crs: source native coordinate reference system
        :param extent: the raster extent in source CRS. Should be as precise as possible.
        :param provider: QgsRasterLayer provider, defaults to 'gdal'
        :param name: name of source
        """

        dtg = ImageDateUtils.datetime(dtg)
        if isinstance(crs, str):
            crs = QgsCoordinateReferenceSystem(crs)
        if isinstance(extent, str):
            extent = QgsGeometry.fromWkt(extent)

        assert isinstance(source, str) and len(source) > 0
        assert isinstance(dtg, QDateTime) and dtg.isValid()
        assert isinstance(crs, QgsCoordinateReferenceSystem) and crs.isValid()
        assert isinstance(extent, QgsGeometry)

        assert isinstance(dims, (list, tuple)) and len(dims) == 3
        for d in dims:
            assert isinstance(d, int) and d > 0

        if isinstance(extent, QgsRectangle):
            extent = QgsGeometry.fromRect(extent)

        assert isinstance(extent, QgsGeometry) and extent.isSimple()
        fields = QgsFields()
        # super().__init__(fields, hash(source))
        self.mFeature = QgsFeature(fields, hash(source))
        # set feature geometry in EPSG:4326
        transform = QgsCoordinateTransform(crs, self.CRS, QgsProject.instance().transformContext())
        g = QgsGeometry(extent)
        assert g.transform(transform) == Qgis.GeometryOperationResult.Success
        self.mFeature.setGeometry(g)
        self.mFeature.setAttributes([source, name, provider, sid, dtg])

        self.mIsVisible: bool = True
        self.mCrs: QgsCoordinateReferenceSystem = crs
        self.mSource: str = source
        self.mSourceExtent: Optional[SpatialExtent] = None
        self.mName: str = name
        self.mProvider: str = provider
        self.mSid: str = sid
        self.mDims = dims
        self.mIsVisible: bool = True
        self.mDTG: QDateTime = dtg

        # will be set later
        self.mTimeSeriesDate: Optional[TimeSeriesDate] = None

    def geometry(self) -> QgsGeometry:
        return self.mFeature.geometry()

    def provider(self) -> str:
        return self.mProvider

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
             self.MKeyDateTime: self.mDTG.toString(Qt.ISODate),
             self.MKeyExtent: self.mFeature.geometry().asWkt(),
             self.MKeyDimensions: self.mDims,
             self.MKeyCrs: self.mCrs.toWkt(),
             self.MKeyIsVisible: self.mIsVisible,
             }

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

    def asRasterLayer(self, loadDefaultStyle: bool = False) -> QgsRasterLayer:
        loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=loadDefaultStyle)
        lyr = QgsRasterLayer(self.mSource, self.mName, self.mProvider, options=loptions)
        tprop: QgsRasterLayerTemporalProperties = lyr.temporalProperties()
        tprop.setIsActive(True)
        tprop.setMode(QgsRasterLayerTemporalProperties.ModeFixedTemporalRange)
        lyr.setCustomProperty(ImageDateUtils.PROPERTY_KEY, self.dtg().toString(Qt.ISODate))
        lyr.setCustomProperty(SensorInstrument.PROPERTY_KEY, self.sid())
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

    def spatialExtent(self, source_crs: bool = True) -> SpatialExtent:
        """
        Returns the source bounding box
        :param source_crs: if True (default) the extent is returned in the source CRS, otherwise in EPSG 4326.
        :return: SpatialExtent
        """
        if source_crs:
            if self.mSourceExtent is None:
                self.mSourceExtent = SpatialExtent.fromRasterSource(self.mSource)
            return self.mSourceExtent
        else:
            return SpatialExtent(self.CRS, self.geometry().boundingBox())

    def asDataset(self) -> gdal.Dataset:
        """
        Returns the source as gdal.Dataset
        :return:
        :rtype:
        """
        return gdal.Open(self.mSource)

    def feature(self) -> QgsFeature:
        return self.mFeature

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
        self.mTimeSeries: Optional['TimeSeries'] = None

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

    def dtgString(self) -> str:

        prec = self.mTimeSeries.dateTimePrecision() if self.mTimeSeries else DateTimePrecision.Day
        return ImageDateUtils.dateString(self.dtg(), prec)

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
