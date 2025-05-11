from datetime import date, datetime, timedelta
import enum
import os
import re
from pathlib import Path
from typing import Optional, Union

from numpy import datetime64, int16, timedelta64
from osgeo import gdal

from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QTime
from qgis.core import Qgis, QgsDateTimeRange, QgsRasterDataProvider, QgsRasterLayer, QgsRasterLayerTemporalProperties

# regular expression. compile them only once

# thanks to user "funkwurm" in
# http://stackoverflow.com/questions/28020805/regex-validate-correct-iso8601-date-string-with-time
regISODate1 = re.compile(
    r'(?:[1-9]\d{3}-(?:(?:0[1-9]|1[0-2])-(?:0[1-9]|1\d|2[0-8])|(?:0[13-9]|1[0-2])-(?:29|30)|(?:0[13578]|1[02])-31)|(?:[1-9]\d(?:0[48]|[2468][048]|[13579][26])|(?:[2468][048]|[13579][26])00)-02-29)T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:Z|[+-][01]\d:[0-5]\d)')
regISODate3 = re.compile(
    r'([\\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\\:?00)([\\.,]\d+(?!:))?)?(\\17[0-5]\d([\\.,]\d+)?)?([zZ]|([\\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
regISODate2 = re.compile(
    r'(19|20|21\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\\:?00)([\\.,]\d+(?!:))?)?(\\17[0-5]\d([\\.,]\d+)?)?([zZ]|([\\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
# regISODate2 = re.compile(r'([12]\d{3}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
# https://www.safaribooksonline.com/library/view/regular-expressions-cookbook/9781449327453/ch04s07.html

regYYYYMMDD = re.compile(
    r'(?P<year>(19|20)\d\d)(?P<hyphen>-?)(?P<month>1[0-2]|0[1-9])(?P=hyphen)(?P<day>3[01]|0[1-9]|[12][0-9])')
regYYYY = re.compile(r'(?P<year>(19|20)\d\d)')
regMissingHypen = re.compile(r'^\d{8}')
regYYYYMM = re.compile(r'([0-9]{4})-(1[0-2]|0[1-9])')

regYYYYDOY = re.compile(r'(?P<year>(19|20)\d\d)-?(?P<day>36[0-6]|3[0-5][0-9]|[12][0-9]{2}|0[1-9][0-9]|00[1-9])')
regDecimalYear = re.compile(r'(?P<year>(19|20)\d\d)\.(?P<datefraction>\d\d\d)')


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
    Millisecond = 'ms'


def matchOrNone(regex, text):
    match = regex.search(text)
    if match:
        return match.group()
    else:
        return None


def dateDOY(date: date) -> int:
    """
    Returns the DOY
    :param date:
    :type date:
    :return:
    :rtype:
    """
    if isinstance(date, datetime64):
        date = date.astype(date)
    return date.timetuple().tm_yday


def daysPerYear(year) -> int:
    """Returns the days per year"""
    if isinstance(year, datetime64):
        year = year.astype(date)
    if isinstance(year, date):
        year = year.timetuple().tm_year

    return dateDOY(date(year=year, month=12, day=31))


def num2date(n, dt64: bool = True, qDate: bool = False):
    """
    Converts a decimal-year number into a date
    :param n: number
    :param dt64: Set True (default) to return the date as numpy.datetime64
    :param qDate: Set True to return a Qt QDate instead of numpy.datetime64
    :return: numpy.datetime64 (default) or QDate
    """
    n = float(n)
    if n < 1:
        n += 1

    year = int(n)
    fraction = n - year
    yearDuration = daysPerYear(year)
    yearElapsed = fraction * yearDuration

    doy = round(yearElapsed)
    if doy < 1:
        doy = 1
    d = date(year, 1, 1) + timedelta(days=doy - 1)
    if qDate:
        return QDate(d.year, d.month, d.day)
    if dt64:
        return datetime64(d)
    else:
        return d


def extractDateTimeGroup(text: str) -> Optional[datetime64]:
    """
    Extracts a date-time-group from a text string
    :param text: a string
    :return: numpy.datetime64 in case of success, or None
    """
    match = regISODate1.search(text)
    if match:
        matchedText = match.group()
        if regMissingHypen.search(matchedText):
            matchedText = '{}-{}-{}'.format(matchedText[0:4], matchedText[4:6], matchedText[6:])
        return datetime64(matchedText)

    match = regYYYYMMDD.search(text)
    if match:
        return datetime64FromYYYYMMDD(match.group())

    match = regYYYYDOY.search(text)
    if match:
        return datetime64FromYYYYDOY(match.group())

    match = regYYYYMM.search(text)
    if match:
        return datetime64(match.group())

    match = regDecimalYear.search(text)
    if match:
        year = float(match.group('year'))
        df = float(match.group('datefraction'))
        num = match.group()
        return num2date(num)

    match = regYYYY.search(text)
    if match:
        return datetime64(match.group('year'))
    return None


def datetime64FromYYYYMMDD(yyyymmdd):
    if re.search(r'^\d{8}$', yyyymmdd):
        # insert hyphens
        yyyymmdd = '{}-{}-{}'.format(yyyymmdd[0:4], yyyymmdd[4:6], yyyymmdd[6:8])
    return datetime64(yyyymmdd)


def datetime64FromYYYYDOY(yyyydoy):
    return datetime64FromDOY(yyyydoy[0:4], yyyydoy[4:7])


def DOYfromDatetime64(dt: datetime64):
    doy = dt.astype('datetime64[D]') - dt.astype('datetime64[Y]') + 1
    doy = doy.astype(int16)
    return doy


def datetime64FromDOY(year, doy):
    if type(year) is str:
        year = int(year)
    if type(doy) is str:
        doy = int(doy)
    return datetime64('{:04d}-01-01'.format(year)) + timedelta64(doy - 1, 'D')


class ImageDateReader(object):
    """
    Base class to extract numpy.datetime64 date-time-stamps
    """

    def __init__(self, dataSet):
        assert isinstance(dataSet, gdal.Dataset)
        self.dataSet = dataSet
        self.filePath = dataSet.GetDescription()
        self.dirName = os.path.dirname(self.filePath)
        self.baseName, self.extension = os.path.splitext(os.path.basename(self.filePath))

    def readDTG(self):
        """
        :return: None in case date was not found, numpy.datetime64 else
        """
        raise NotImplementedError()


class ImageReaderOWS(ImageDateReader):
    """Date reader for OGC web services"""

    def __init__(self, dataSet):
        super(ImageReaderOWS, self).__init__(dataSet)

    def readDTG(self):
        drv = self.dataSet.GetDriver()
        assert isinstance(drv, gdal.Driver)
        if drv.ShortName == 'WCS':
            text = self.dataSet.GetMetadataItem('WCS_GLOBAL#updateSequence', '')
            if isinstance(text, str):
                date = extractDateTimeGroup(text)
                if isinstance(date, datetime64):
                    return date

        return None


class ImageDateReaderDefault(ImageDateReader):
    """
    Default reader for dates in gdal.Datasets
    """

    def __init__(self, dataSet):
        super(ImageDateReaderDefault, self).__init__(dataSet)
        self.regDateKeys = re.compile('(acquisition[ _]*(time|date|datetime))', re.IGNORECASE)

    def readDTG(self):
        # search metadata for datetime information
        # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for datetime format
        dtg = None
        for domain in self.dataSet.GetMetadataDomainList():
            md = self.dataSet.GetMetadata_Dict(domain)
            for key, value in md.items():
                if self.regDateKeys.search(key):
                    try:
                        # remove timezone characters from end of string, e.g. 'Z' in '2013-03-25T13:45:03.0Z'
                        dtg = datetime64(re.sub(r'\D+$', '', value))
                        return dtg
                    except Exception as ex:
                        pass

        # search for ISO date in basename
        # search in basename
        dtg = extractDateTimeGroup(self.baseName)
        if dtg:
            return dtg
        dtg = extractDateTimeGroup(self.dirName)
        if dtg:
            return dtg
        return None


class ImageDateReaderPLEIADES(ImageDateReader):
    """
    Date reader for PLEIADES images
    """

    def __init__(self, dataSet):
        super(ImageDateReaderPLEIADES, self).__init__(dataSet)

    def readDTG(self):
        timeStamp = ''
        ext = self.extension.lower()

        if ext == '.xml':
            md = self.dataSet.GetMetadata_Dict()
            if 'IMAGING_DATE' in md.keys() and 'IMAGING_TIME' in md.keys():
                timeStamp = '{}T{}'.format(md.get('IMAGING_DATE', ''),
                                           md.get('IMAGING_TIME', ''))
        elif ext == '.jp2':
            timeStamp = self.dataSet.GetMetadataItem('ACQUISITIONDATETIME', 'IMAGERY')
        if len(timeStamp) > 0:
            return datetime64(timeStamp)
        return None


class ImageDateReaderSentinel2(ImageDateReader):
    def __init__(self, dataSet):
        super(ImageDateReaderSentinel2, self).__init__(dataSet)

    def readDTG(self):
        timeStamp = ''
        if self.extension.lower() == '.xml':
            md = self.dataSet.GetMetadata_Dict()
            timeStamp = md.get('DATATAKE_1_DATATAKE_SENSING_START', '')
        if len(timeStamp) > 0:
            return datetime64(timeStamp)
        return None


class ImageDateParserLandsat(ImageDateReader):
    """
    Reader for date in LANDSAT images
    #see https://landsat.usgs.gov/what-are-naming-conventions-landsat-scene-identifiers
    """

    regLandsatSceneID = re.compile(r'L[COTEM][4578]\d{3}\d{3}\d{4}\d{3}[A-Z]{2}[A-Z1]\d{2}')
    regLandsatProductID = re.compile(
        r'L[COTEM]0[78]_(L1TP|L1GT|L1GS)_\d{3}\d{3}_\d{4}\d{2}\d{2}_\d{4}\d{2}\d{2}_0\d{1}_(RT|T1|T2)')

    def __init__(self, dataSet):
        super(ImageDateParserLandsat, self).__init__(dataSet)

    def readDTG(self):
        # search for LandsatSceneID (old) and Landsat Product IDs (new)
        sceneID = matchOrNone(ImageDateParserLandsat.regLandsatSceneID, self.baseName)
        if sceneID:
            return datetime64FromYYYYDOY(sceneID[9:16])

        productID = matchOrNone(ImageDateParserLandsat.regLandsatProductID, self.baseName)
        if productID:
            return datetime64(productID[17:25])
        return None


# dateParserList = [c for c in ImageDateReader.__subclasses__()]
# dateParserList.insert(0, dateParserList.pop(dateParserList.index(ImageDateReaderDefault)))  # set to first position

dateParserList = [
    ImageDateReaderDefault,
    ImageDateParserLandsat,
    ImageDateReaderSentinel2,
    ImageDateReaderPLEIADES,
    ImageReaderOWS

]


def parseDateFromDataSet(dataSet: gdal.Dataset) -> Optional[datetime64]:
    assert isinstance(dataSet, gdal.Dataset)
    for parser in dateParserList:
        dtg = parser(dataSet).readDTG()
        if dtg:
            return dtg
    return None


rxLandsatSceneID = re.compile(r'L[COTEM][45789]\d{3}\d{3}(?P<dtg>\d{4}\d{3})[A-Z]{2}[A-Z1]\d{2}')

# date-time formats supported to read
# either as fmt = datetime.strptime format code, or
# or (fmt, rx), with rx being the regular expression to extract the part to be parsed with fmt
# regex needs to define a group called 'dtg' that can be extracted with match.group('dtg')
DATETIME_FORMATS = [
    # Landsat Scene ID
    ('%Y%j', rxLandsatSceneID),

    # RapidEye
    ('%Y%m%d', re.compile(r'(?P<dtg>\d{8})')),
    ('%Y-%m-%d', re.compile(r'(?P<dtg>\d{4}-\d{2}-\d{2})')),
    ('%Y/%m/%d', re.compile(r'(?P<dtg>\d{4}/\d{2}/\d{2})')),

    # FORCE outputs
    ('%Y%m%d', re.compile(r'(?P<dtg>\d{8})_LEVEL\d_.+_(BOA|QAI|DST|HOT|VZN)')),
]

GDAL_DATETIME_ITEMS = [
    # see https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing
    (re.compile(r'acquisition[_\- ]?datetime', re.I), ['IMAGERY', '']),

    (re.compile(r'acquisition[_\- ]?time', re.I), ['ENVI', '']),
]


class ImageDateUtils(object):
    PROPERTY_KEY = 'eotsv/dtg'

    rxDTGKey = re.compile(r'(acquisition|observation)[ _]*(time|date|datetime)', re.IGNORECASE)
    rxDTG = re.compile(r'((acquisition|observation)[ _]*(time|date|datetime)=(?P<dtg>[^<]+))', re.IGNORECASE)

    @classmethod
    def dateTimeFromString(cls, text: str) -> Optional[QDateTime]:
        if not isinstance(text, str):
            return None

        # try Qt Formats
        for fmt in [Qt.ISODateWithMs, Qt.ISODate, Qt.TextDate]:
            try:
                dtg: QDateTime = QDateTime.fromString(text, fmt)
                if dtg.isValid():
                    return dtg
            except Exception as ex:
                pass

        for fmt in DATETIME_FORMATS:
            try:
                if isinstance(fmt, str):
                    dtg = datetime.strptime(text, fmt)
                    return QDateTime(dtg)
                elif isinstance(fmt, tuple):
                    fmt, rx = fmt
                    match = rx.search(text)
                    if match:
                        dtg = datetime.strptime(match.group('dtg'), fmt)
                        return QDateTime(dtg)
            except Exception as ex:
                s = ""

        try:
            dt = datetime64(text).astype(object)
            dtg = None
            if isinstance(dt, date):
                dtg = QDateTime(QDate(dtg), QTime())
            elif isinstance(dt, datetime):
                dtg = QDateTime(dt)
            if isinstance(dtg, QDateTime) and dtg.isValid():
                return dtg
        except Exception as ex:
            pass

        return None

    @classmethod
    def dateTimeFromLayer(cls, layer: Union[Path, str, QgsRasterLayer, gdal.Dataset]) -> Optional[QDateTime]:
        if isinstance(layer, Path):
            return ImageDateUtils.dateTimeFromLayer(QgsRasterLayer(layer.as_posix()))
        elif isinstance(layer, str):
            return ImageDateUtils.dateTimeFromLayer(QgsRasterLayer(layer))
        elif isinstance(layer, gdal.Dataset):
            return ImageDateUtils.dateTimeFromLayer(layer.GetDescription())
        if not isinstance(layer, QgsRasterLayer) and layer.isValid():
            return None

        if ImageDateUtils.PROPERTY_KEY in layer.customPropertyKeys():
            dateString = layer.customProperty(ImageDateUtils.PROPERTY_KEY)
            return ImageDateUtils.dateTimeFromString(dateString)
        else:

            dtg = None
            filepath = Path(layer.source())

            # read from raster layer's temporal properties
            tprop: QgsRasterLayerTemporalProperties = layer.temporalProperties()

            if tprop.mode() == Qgis.RasterTemporalMode.FixedTemporalRange and not (
                    dateRange := tprop.fixedTemporalRange()).isInfinite():
                d = dateRange.begin()
                if d.isValid():
                    dtg = d

            if not dtg:

                for k in layer.customPropertyKeys():
                    if match := ImageDateUtils.rxDTGKey.match(k):
                        v = layer.customProperty(k)
                        d = QDateTime.fromString(v)
                        if d.isValid():
                            dtg = d
                            break

            if not dtg:
                # read from raster data provider
                dp: QgsRasterDataProvider = layer.dataProvider()
                tcap = dp.temporalCapabilities()
                dtg = ImageDateUtils.dateTimeFromDataProvider(dp)

            if not dtg:
                # read from file name
                dtg = ImageDateUtils.dateTimeFromString(filepath.name)

            if not dtg:
                # read from parent directory
                dtg = ImageDateUtils.dateTimeFromString(filepath.parent.name)

            if not dtg:
                # read from HTML metadata
                html = layer.htmlMetadata()
                if match := cls.rxDTG.search(html):
                    dtg = ImageDateUtils.dateTimeFromString(match.group('dtg'))

            if isinstance(dtg, QDateTime) and dtg.isValid():
                return dtg
            return None

    @classmethod
    def doiFromDateTime(cls, dtg: Union[QDateTime, QDate, datetime, date, str, float]) -> int:
        dtg = cls.datetime(dtg)
        return dtg.date().dayOfYear()

    @classmethod
    def datetime(cls, dtg: Union[QDateTime, QDate, datetime, date, str, float]) -> QDateTime:
        """
        Converts a time object into a QDateTime object
        :param dtg:
        :return:
        """
        if isinstance(dtg, float):
            return QDateTime(datetime.fromtimestamp(dtg))
        if isinstance(dtg, str):
            return cls.dateTimeFromString(dtg)
        if isinstance(dtg, (datetime, date)):
            return QDateTime(dtg)
        if isinstance(dtg, QDateTime):
            return dtg
        raise NotImplementedError(f'Unknown type: {type(dtg)}')

    @classmethod
    def timestamp(cls, dtg: Union[QDateTime, QDate, datetime, date]) -> float:
        """
        Converts a time object into a float string, to be used in plotting
        :param dtg:
        :return:
        """
        if isinstance(dtg, datetime):
            return dtg.timestamp()
        elif isinstance(dtg, QDateTime):
            return dtg.toPyDateTime().timestamp()
        elif isinstance(dtg, date):
            return cls.timestamp(datetime(dtg.year, dtg.month, dtg.day))
        elif isinstance(dtg, QDate):
            return cls.timestamp(QDateTime(dtg, QTime()))
        raise NotImplementedError(f'Unknown type: {type(dtg)}')

    @classmethod
    def decimalYear(cls, dateTime: QDateTime) -> float:
        """
        Returns the decimal year of a date-time
        <year>.<fraction of seconds to next year>
        :param dateTime:
        :return:
        """
        d: QDate = dateTime.date()
        d0 = QDateTime(QDate(d.year(), 1, 1))
        d1 = QDateTime(QDate(d.year() + 1, 1, 1))

        total_msecs = d1.toMSecsSinceEpoch() - d0.toMSecsSinceEpoch()
        msecs_since_d0 = dateTime.toMSecsSinceEpoch() - d0.toMSecsSinceEpoch()
        return d.year() + (msecs_since_d0 / total_msecs)

    @classmethod
    def dateTimeFromDataProvider(cls, dp: QgsRasterDataProvider) -> Optional[QDateTime]:
        if not isinstance(dp, QgsRasterDataProvider) and dp.isValid():
            return None

        if dp.name() == 'gdal':
            ds: gdal.Dataset = gdal.Open(dp.dataSourceUri())
            if isinstance(ds, gdal.Dataset):
                for (rx, domains) in GDAL_DATETIME_ITEMS:
                    for domain in domains:
                        md = ds.GetMetadata_Dict(domain)
                        if isinstance(md, dict):
                            for k, v in md.items():
                                if rx.match(k):
                                    dtg = QDateTime.fromString(v, Qt.ISODate)
                                    if dtg.isValid():
                                        return dtg

            s = ""

        tcap = dp.temporalCapabilities()
        if tcap.hasTemporalCapabilities():
            raise NotImplementedError()
        else:
            return None

    @classmethod
    def dateRange(cls,
                  dtg: QDateTime,
                  precision: DateTimePrecision = DateTimePrecision.Day) -> QgsDateTimeRange:
        """
        Returns the date-range a date-time-group belongs to, given a certain precission
        :param dtg:
        :param precision:
        :return:
        """
        assert isinstance(dtg, QDateTime)
        assert isinstance(precision, DateTimePrecision)
        d: QDate = dtg.date()
        t: QTime = dtg.time()
        if precision == DateTimePrecision.Millisecond:
            return QgsDateTimeRange(dtg, dtg)

        if precision == DateTimePrecision.Second:
            t0 = QTime(t.hour(), t.minute(), t.second())
            t1 = t0.addSecs(1).addMSecs(-1)
            result = QgsDateTimeRange(
                QDateTime(d, t0),
                QDateTime(d, t1),
            )

        elif precision == DateTimePrecision.Minute:
            t0 = QTime(t.hour(), t.minute(), 0)
            t1 = t0.addSecs(60).addMSecs(-1)
            result = QgsDateTimeRange(
                QDateTime(d, t0),
                QDateTime(d, t1),
            )
        elif precision == DateTimePrecision.Hour:
            t0 = QTime(t.hour(), 0, 0)
            t1 = t0.addSecs(60 * 60).addMSecs(-1)
            result = QgsDateTimeRange(
                QDateTime(d, t0),
                QDateTime(d, t1),
            )

        elif precision == DateTimePrecision.Day:
            d0 = QDateTime(QDate(d.year(), d.month(), d.day()))
            d1 = d0.addDays(1).addMSecs(-1)
            result = QgsDateTimeRange(d0, d1)

        elif precision == DateTimePrecision.Month:
            d0 = QDateTime(QDate(d.year(), d.month(), 1))
            d1 = d0.addMonths(1).addMSecs(-1)
            result = QgsDateTimeRange(d0, d1)

        elif precision == DateTimePrecision.Year:
            d0 = QDateTime(QDate(d.year(), 1, 1))
            d1 = d0.addYears(1).addMSecs(-1)
            result = QgsDateTimeRange(d0, d1)

        elif precision == DateTimePrecision.Week:
            day_of_week = d.dayOfWeek()
            d0 = d.addDays(- (day_of_week - 1))
            d1 = d.addDays(7 - day_of_week)

            result = QgsDateTimeRange(
                QDateTime(d0, QTime()),
                QDateTime(d1, QTime(23, 59, 59, 999)))

        else:
            raise NotImplementedError(f'Unknown precision: {precision}')

        return result

    @classmethod
    def dateString(cls,
                   dtg: QDateTime,
                   precision: DateTimePrecision = DateTimePrecision.Day) -> str:
        if not dtg.isValid():
            return ''
        if precision == DateTimePrecision.Millisecond:
            return dtg.toString(Qt.ISODateWithMs)
        if precision == DateTimePrecision.Second:
            return dtg.toString(Qt.ISODate)
        if precision == DateTimePrecision.Minute:
            return dtg.toString(Qt.ISODateWithMs)[0:-7]
        if precision == DateTimePrecision.Hour:
            return dtg.toString(Qt.ISODateWithMs)[0:-10]
        if precision == DateTimePrecision.Day:
            return dtg.toString(Qt.ISODateWithMs)[0:10]
        if precision == DateTimePrecision.Month:
            return dtg.toString(Qt.ISODateWithMs)[0:7]
        if precision == DateTimePrecision.Year:
            return dtg.toString(Qt.ISODateWithMs)[0:4]
        if precision == DateTimePrecision.Week:
            return '{1}-{0:03}'.format(*dtg.date().weekNumber())
        raise NotImplementedError(f'{precision}')
