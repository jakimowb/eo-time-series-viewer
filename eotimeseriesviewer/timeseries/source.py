import json
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

from osgeo import gdal

from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent
from eotimeseriesviewer.sensors import create_sensor_id, SensorInstrument
from qgis.PyQt.QtCore import pyqtSignal, QAbstractTableModel, QDate, QDateTime, QMimeData, QModelIndex, Qt
from qgis.core import QgsCoordinateReferenceSystem, QgsDateTimeRange, QgsExpressionContextScope, QgsGeometry, \
    QgsMimeDataUtils, QgsRasterLayer, QgsRasterLayerTemporalProperties, QgsRectangle


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
        if isinstance(source, (str, Path)):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
            source = QgsRasterLayer(str(source), options=options)
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

    def __init__(self, layer: Union[QgsRasterLayer, str, Path], dtg: QDateTime):

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
