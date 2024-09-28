import datetime
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal

from qgis.core import Qgis, QgsRasterDataProvider, QgsRasterLayer, QgsRasterLayerTemporalProperties
from qgis.PyQt.QtCore import QDate

# regular expression. compile them only once

# thanks to user "funkwurm" in
# http://stackoverflow.com/questions/28020805/regex-validate-correct-iso8601-date-string-with-time
regISODate1 = re.compile(
    r'(?:[1-9]\d{3}-(?:(?:0[1-9]|1[0-2])-(?:0[1-9]|1\d|2[0-8])|(?:0[13-9]|1[0-2])-(?:29|30)|(?:0[13578]|1[02])-31)|(?:[1-9]\d(?:0[48]|[2468][048]|[13579][26])|(?:[2468][048]|[13579][26])00)-02-29)T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:Z|[+-][01]\d:[0-5]\d)')
regISODate3 = re.compile(
    r'([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
regISODate2 = re.compile(
    r'(19|20|21\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
# regISODate2 = re.compile(r'([12]\d{3}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')
# https://www.safaribooksonline.com/library/view/regular-expressions-cookbook/9781449327453/ch04s07.html

regYYYYMMDD = re.compile(
    r'(?P<year>(19|20)\d\d)(?P<hyphen>-?)(?P<month>1[0-2]|0[1-9])(?P=hyphen)(?P<day>3[01]|0[1-9]|[12][0-9])')
regYYYY = re.compile(r'(?P<year>(19|20)\d\d)')
regMissingHypen = re.compile(r'^\d{8}')
regYYYYMM = re.compile(r'([0-9]{4})-(1[0-2]|0[1-9])')

regYYYYDOY = re.compile(r'(?P<year>(19|20)\d\d)-?(?P<day>36[0-6]|3[0-5][0-9]|[12][0-9]{2}|0[1-9][0-9]|00[1-9])')
regDecimalYear = re.compile(r'(?P<year>(19|20)\d\d)\.(?P<datefraction>\d\d\d)')


def matchOrNone(regex, text):
    match = regex.search(text)
    if match:
        return match.group()
    else:
        return None


def dateDOY(date: datetime.date) -> int:
    """
    Returns the DOY
    :param date:
    :type date:
    :return:
    :rtype:
    """
    if isinstance(date, np.datetime64):
        date = date.astype(datetime.date)
    return date.timetuple().tm_yday


def daysPerYear(year) -> int:
    """Returns the days per year"""
    if isinstance(year, np.datetime64):
        year = year.astype(datetime.date)
    if isinstance(year, datetime.date):
        year = year.timetuple().tm_year

    return dateDOY(datetime.date(year=year, month=12, day=31))


def num2date(n, dt64=True, qDate=False):
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
    try:
        date = datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
    except Exception:
        s = ""
    if qDate:
        return QDate(date.year, date.month, date.day)
    if dt64:
        return np.datetime64(date)
    else:
        return date


def extractDateTimeGroup(text: str) -> np.datetime64:
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
        return np.datetime64(matchedText)

    match = regYYYYMMDD.search(text)
    if match:
        return datetime64FromYYYYMMDD(match.group())

    match = regYYYYDOY.search(text)
    if match:
        return datetime64FromYYYYDOY(match.group())

    match = regYYYYMM.search(text)
    if match:
        return np.datetime64(match.group())

    match = regDecimalYear.search(text)
    if match:
        year = float(match.group('year'))
        df = float(match.group('datefraction'))
        num = match.group()
        return num2date(num)

    match = regYYYY.search(text)
    if match:
        return np.datetime64(match.group('year'))
    return None


def datetime64FromYYYYMMDD(yyyymmdd):
    if re.search(r'^\d{8}$', yyyymmdd):
        # insert hyphens
        yyyymmdd = '{}-{}-{}'.format(yyyymmdd[0:4], yyyymmdd[4:6], yyyymmdd[6:8])
    return np.datetime64(yyyymmdd)


def datetime64FromYYYYDOY(yyyydoy):
    return datetime64FromDOY(yyyydoy[0:4], yyyydoy[4:7])


def DOYfromDatetime64(dt):
    doy = dt.astype('datetime64[D]') - dt.astype('datetime64[Y]') + 1
    doy = doy.astype(np.int16)
    return doy

    return (dt.astype('datetime64[D]') - dt.astype('datetime64[Y]')).astype(int) + 1


def datetime64FromDOY(year, doy):
    if type(year) is str:
        year = int(year)
    if type(doy) is str:
        doy = int(doy)
    return np.datetime64('{:04d}-01-01'.format(year)) + np.timedelta64(doy - 1, 'D')


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
        return None


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
                if isinstance(date, np.datetime64):
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
                        dtg = np.datetime64(re.sub(r'\D+$', '', value))
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
            return np.datetime64(timeStamp)
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
            return np.datetime64(timeStamp)
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
            return np.datetim64(productID[17:25])
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


def parseDateFromDataSet(dataSet: gdal.Dataset) -> Optional[np.datetime64]:
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


class ImageDateUtils(object):
    PROPERTY_KEY = 'eotsv/dtg'

    @staticmethod
    def datetimeFromString(text: str) -> Optional[datetime.datetime]:
        if not isinstance(text, str):
            return None

        for fmt in DATETIME_FORMATS:
            try:
                if isinstance(fmt, str):
                    dtg = datetime.datetime.strptime(text, fmt)
                    return dtg
                elif isinstance(fmt, tuple):
                    fmt, rx = fmt
                    match = rx.search(text)
                    if match:
                        dtg = datetime.datetime.strptime(match.group('dtg'), fmt)
                        return dtg
            except Exception as ex:
                s = ""
        return None

    @staticmethod
    def datetimeFromLayer(layer: QgsRasterLayer) -> Optional[datetime.datetime]:
        if isinstance(layer, Path):
            return ImageDateUtils.datetimeFromLayer(QgsRasterLayer(layer.as_posix()))
        elif isinstance(layer, str):
            return ImageDateUtils.datetimeFromLayer(QgsRasterLayer(layer))
        if not isinstance(layer, QgsRasterLayer) and layer.isValid():
            return None
        if ImageDateUtils.PROPERTY_KEY in layer.customPropertyKeys():
            dateString = layer.customProperty(ImageDateUtils.PROPERTY_KEY)
            dtg = datetime.datetime.fromisoformat(dateString)
            return dtg
        else:

            dtg = None
            filepath = Path(layer.source())

            # read from raster layer's temporal properties
            tprop: QgsRasterLayerTemporalProperties = layer.temporalProperties()

            if tprop.mode() == Qgis.RasterTemporalMode.FixedTemporalRange and not (
                    dateRange := tprop.fixedTemporalRange()).isInfinite():
                t0 = dateRange.begin()

            if not dtg:
                # read from raster data provider
                dp: QgsRasterDataProvider = layer.dataProvider()
                tcap = dp.temporalCapabilities()
                dtg = ImageDateUtils.datetimeFromDataProvider(dp)

            if not dtg:
                # read from file name
                dtg = ImageDateUtils.datetimeFromString(filepath.name)

            if not dtg:
                # read from parent directory
                dtg = ImageDateUtils.datetimeFromString(filepath.parent.name)

            if isinstance(dtg, datetime.datetime):
                layer.setCustomProperty(ImageDateUtils.PROPERTY_KEY, dtg.isoformat())
            return dtg

    @staticmethod
    def datetimeFromDataProvider(dp: QgsRasterDataProvider) -> Optional[datetime.datetime]:
        if not isinstance(dp, QgsRasterDataProvider) and dp.isValid():
            return None
