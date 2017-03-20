import os, re, logging
from osgeo import gdal
import numpy as np

logger = logging.getLogger('hub-tsv')

#regular expression. compile them only once

#thanks user "funkwurm" in
#http://stackoverflow.com/questions/28020805/regex-validate-correct-iso8601-date-string-with-time
regISODate = re.compile(r'^(?:[1-9]\d{3}-(?:(?:0[1-9]|1[0-2])-(?:0[1-9]|1\d|2[0-8])|(?:0[13-9]|1[0-2])-(?:29|30)|(?:0[13578]|1[02])-31)|(?:[1-9]\d(?:0[48]|[2468][048]|[13579][26])|(?:[2468][048]|[13579][26])00)-02-29)T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:Z|[+-][01]\d:[0-5]\d)$')


def matchOrNone(regex, text):
    match = regex.search(text)
    if match:
        return match.group()
    else:
        return None

def extractDateTimeGroup(regex, text):

    match = regex.search(text)
    if match is not None:
        return np.datetime64(match.group())
    else:
        return None


def getDateTime64FromYYYYDOY(yyyydoy):
    return getDatetime64FromDOY(yyyydoy[0:4], yyyydoy[4:7])

def getDOYfromDatetime64(dt):

    return (dt.astype('datetime64[D]') - dt.astype('datetime64[Y]')).astype(int)+1

def getDatetime64FromDOY(year, doy):
        if type(year) is str:
            year = int(year)
        if type(doy) is str:
            doy = int(doy)
        return np.datetime64('{:04d}-01-01'.format(year)) + np.timedelta64(doy-1, 'D')



from timeseriesviewer.utils import KeepRefs

class ImageDateParser(object):
    """
    Base class to extract numpy.datetime64 date-time-stamps
    """

    def __init__(self, dataSet):
        assert isinstance(dataSet, gdal.Dataset)
        self.dataSet = dataSet
        self.filePath = dataSet.GetFileList()[0]
        self.dirName = os.path.dirname(self.filePath)
        self.baseName, self.extension = os.path.splitext(os.path.basename(self.filePath))

    def parseDate(self):
        """
        :return: None in case date was not found, numpy.datetime64 else
        """
        raise NotImplementedError()
        return None

class ImageDateParserGeneric(ImageDateParser):
    def __init__(self, dataSet):
        super(ImageDateParserGeneric, self).__init__(dataSet)
        self.regDateKeys = re.compile('(acquisition[ ]*time|datetime)', re.IGNORECASE)

    def parseDate(self):
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
        dtg = extractDateTimeGroup(regISODate, self.baseName)
        if dtg: return dtg

        # search for ISO date in file directory path
        dtg = extractDateTimeGroup(regISODate, self.dirName)
        return dtg


class ImageDateParserPLEIADES(ImageDateParser):
    def __init__(self, dataSet):
        super(ImageDateParserPLEIADES, self).__init__(dataSet)

    def parseDate(self):
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


class ImageDateParserSentinel2(ImageDateParser):
    def __init__(self, dataSet):
        super(ImageDateParserSentinel2, self).__init__(dataSet)

    def parseDate(self):
        timeStamp = ''
        ext = self.extension.lower()

        if ext == '.xml':
            md = self.dataSet.GetMetadata_Dict()
            timeStamp = md.get('DATATAKE_1_DATATAKE_SENSING_START', '')
        if len(timeStamp) > 0:
            return np.datetime64(timeStamp)
        return None

class ImageDateParserLandsat(ImageDateParser):
    #see https://landsat.usgs.gov/what-are-naming-conventions-landsat-scene-identifiers
    regLandsatSceneID  = re.compile(r'L[COTEM][4578]\d{3}\d{3}\d{4}\d{3}[A-Z]{2}[A-Z1]\d{2}')
    regLandsatProductID = re.compile(r'L[COTEM]0[78]_(L1TP|L1GT|L1GS)_\d{3}\d{3}_\d{4}\d{2}\d{2}_\d{4}\d{2}\d{2}_0\d{1}_(RT|T1|T2)')

    def __init__(self, dataSet):
        super(ImageDateParserLandsat, self).__init__(dataSet)

    def parseDate(self):
        #search for LandsatSceneID (old) and Landsat Product IDs (new)
        sceneID = matchOrNone(ImageDateParserLandsat.regLandsatSceneID, self.baseName)
        if sceneID:
            return getDateTime64FromYYYYDOY(sceneID[9:16])

        productID = matchOrNone(ImageDateParserLandsat.regLandsatProductID, self.baseName)
        if productID:
            return np.datetim64(productID[17:25])
        return None



dateParserList = [c for c in ImageDateParser.__subclasses__()]
dateParserList.insert(0, dateParserList.pop(dateParserList.index(ImageDateParserGeneric))) #set to first position

def parseDateFromDataSet(dataSet):
    assert isinstance(dataSet, gdal.Dataset)
    for parser in dateParserList:
        dtg = parser(dataSet).parseDate()
        if dtg:
            return dtg
    return None


if __name__ == '__main__':

    p = r'E:\_EnMAP\temp\temp_bj\landsat\37S\EB\LE71720342015009SG100\LE71720342015009SG100_sr.tif'

    ds = gdal.Open(p)
    parseDateFromDataSet(ds)
    s = ""