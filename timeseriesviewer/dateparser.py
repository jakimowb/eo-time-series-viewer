import os, re, logging
from osgeo import gdal
import numpy as np
from qgis import *
logger = logging.getLogger(__file__)

#regular expression. compile them only once

#thanks user "funkwurm" in
#http://stackoverflow.com/questions/28020805/regex-validate-correct-iso8601-date-string-with-time
regISODate = re.compile(r'(?:[1-9]\d{3}-(?:(?:0[1-9]|1[0-2])-(?:0[1-9]|1\d|2[0-8])|(?:0[13-9]|1[0-2])-(?:29|30)|(?:0[13578]|1[02])-31)|(?:[1-9]\d(?:0[48]|[2468][048]|[13579][26])|(?:[2468][048]|[13579][26])00)-02-29)T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:Z|[+-][01]\d:[0-5]\d)')
regISODate2 = re.compile(r'([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?')

#https://www.safaribooksonline.com/library/view/regular-expressions-cookbook/9781449327453/ch04s07.html

regYYYYMMDD = re.compile(r'(?P<year>[0-9]{4})(?P<hyphen>-?)(?P<month>1[0-2]|0[1-9])(?P=hyphen)(?P<day>3[01]|0[1-9]|[12][0-9])')
regMissingHypen = re.compile('^\d{8}')
regYYYYMM = re.compile(r'([0-9]{4})-(1[0-2]|0[1-9])')
regYYYYDOY = re.compile(r'(?P<year>[0-9]{4})-?(?P<day>36[0-6]|3[0-5][0-9]|[12][0-9]{2}|0[1-9][0-9]|00[1-9])')

def matchOrNone(regex, text):
    match = regex.search(text)
    if match:
        return match.group()
    else:
        return None

def extractDateTimeGroup(text):
    match = regISODate2.search(text)
    if match:
        matchedText = match.group()
        if regMissingHypen.search(matchedText):
            matchedText = '{}-{}-{}'.format(matchedText[0:4],matchedText[4:6],matchedText[6:])
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

    return None

def datetime64FromYYYYMMDD(yyyymmdd):

    return np.datetime64('{}-{}-{}'.format(yyyymmdd[0:4],yyyymmdd[4:6],yyyymmdd[6:8]))

def datetime64FromYYYYDOY(yyyydoy):
    return datetime64FromDOY(yyyydoy[0:4], yyyydoy[4:7])

def DOYfromDatetime64(dt):

    return (dt.astype('datetime64[D]') - dt.astype('datetime64[Y]')).astype(int)+1

def datetime64FromDOY(year, doy):
        if type(year) is str:
            year = int(year)
        if type(doy) is str:
            doy = int(doy)
        return np.datetime64('{:04d}-01-01'.format(year)) + np.timedelta64(doy-1, 'D')


class ImageDateReader(object):
    """
    Base class to extract numpy.datetime64 date-time-stamps
    """

    def __init__(self, dataSet):
        assert isinstance(dataSet, gdal.Dataset)
        self.dataSet = dataSet
        self.filePath = dataSet.GetFileList()[0]
        self.dirName = os.path.dirname(self.filePath)
        self.baseName, self.extension = os.path.splitext(os.path.basename(self.filePath))

    def readDTG(self):
        """
        :return: None in case date was not found, numpy.datetime64 else
        """
        raise NotImplementedError()
        return None

class ImageDateReaderDefault(ImageDateReader):
    def __init__(self, dataSet):
        super(ImageDateReaderDefault, self).__init__(dataSet)
        self.regDateKeys = re.compile('(acquisition[ ]*time|datetime)', re.IGNORECASE)

    def readDTG(self):
        # search metadata for datetime information
        # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for datetime format
        dtg = None
        for domain in self.dataSet.GetMetadataDomainList():
            md = self.dataSet.GetMetadata_Dict(domain)
            for key, value in md.items():
                if self.regDateKeys.search(key):
                    try:
                        dtg = np.datetime64(value)
                        return dtg
                    except:
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
    #see https://landsat.usgs.gov/what-are-naming-conventions-landsat-scene-identifiers
    regLandsatSceneID  = re.compile(r'L[COTEM][4578]\d{3}\d{3}\d{4}\d{3}[A-Z]{2}[A-Z1]\d{2}')
    regLandsatProductID = re.compile(r'L[COTEM]0[78]_(L1TP|L1GT|L1GS)_\d{3}\d{3}_\d{4}\d{2}\d{2}_\d{4}\d{2}\d{2}_0\d{1}_(RT|T1|T2)')

    def __init__(self, dataSet):
        super(ImageDateParserLandsat, self).__init__(dataSet)

    def readDTG(self):
        #search for LandsatSceneID (old) and Landsat Product IDs (new)
        sceneID = matchOrNone(ImageDateParserLandsat.regLandsatSceneID, self.baseName)
        if sceneID:
            return datetime64FromYYYYDOY(sceneID[9:16])

        productID = matchOrNone(ImageDateParserLandsat.regLandsatProductID, self.baseName)
        if productID:
            return np.datetim64(productID[17:25])
        return None



dateParserList = [c for c in ImageDateReader.__subclasses__()]
dateParserList.insert(0, dateParserList.pop(dateParserList.index(ImageDateReaderDefault))) #set to first position

def parseDateFromDataSet(dataSet):
    assert isinstance(dataSet, gdal.Dataset)
    for parser in dateParserList:
        dtg = parser(dataSet).readDTG()
        if dtg:
            return dtg
    return None


if __name__ == '__main__':

    p = r'E:\_EnMAP\temp\temp_bj\landsat\37S\EB\LE71720342015009SG100\LE71720342015009SG100_sr.tif'
    p = r'D:\Repositories\QGIS_Plugins\hub-timeseriesviewer\example\Images\2012-04-07_LE72270652012098EDC00_BOA.bsq'
    ds = gdal.Open(p)

    print(datetime64FromYYYYMMDD('20141212'))
    print(parseDateFromDataSet(ds))