from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect, time, traceback, copy

import bisect, datetime
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *

import numpy as np

from timeseriesviewer import DIR_REPO, DIR_EXAMPLES, dprint, jp, findAbsolutePath

def transformGeometry(geom, crsSrc, crsDst, trans=None):
    if trans is None:
        assert isinstance(crsSrc, QgsCoordinateReferenceSystem)
        assert isinstance(crsDst, QgsCoordinateReferenceSystem)
        return transformGeometry(geom, None, None, trans=QgsCoordinateTransform(crsSrc, crsDst))
    else:
        assert isinstance(trans, QgsCoordinateTransform)
        return trans.transform(geom)

METRIC_EXPONENTS = {
    "nm":-9,"um": -6, "mm":-3, "cm":-2, "dm":-1, "m": 0,"hm":2, "km":3
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

def verifyVRT(pathVRT):

    ds = gdal.Open(pathVRT)
    if ds is None:
        return False
    s = ""

    return True


def getDS(pathOrDataset):
    if isinstance(pathOrDataset, gdal.Dataset):
        return pathOrDataset
    else:
        ds = gdal.Open(pathOrDataset)
        assert isinstance(ds, gdal.Dataset)
        return ds

class SensorInstrument(QObject):

    sigNameChanged = pyqtSignal(str)

    LUT_Wavelengths = dict({'B':480,
                            'G':570,
                            'R':660,
                            'nIR':850,
                            'swIR':1650,
                            'swIR1':1650,
                            'swIR2':2150
                            })
    """
    Describes a Sensor Configuration
    """
    def __init__(self, pathImg, sensor_name=None):
        super(SensorInstrument, self).__init__()

        ds = getDS(pathImg)
        self.nb, nl, ns, crs, self.px_size_x, self.px_size_y = getSpatialPropertiesFromDataset(ds)

        self.bandDataType = ds.GetRasterBand(1).DataType
        self.pathImg = ds.GetFileList()[0]

        #todo: better band names
        self.bandNames = [ds.GetRasterBand(b+1).GetDescription() for b in range(self.nb)]

        self.TS = None

        assert self.px_size_x > 0
        assert self.px_size_y > 0

        #find wavelength
        wl, wlu = parseWavelengthFromDataSet(ds)
        self.wavelengths = np.asarray(wl)
        self.wavelengthUnits = wlu

        self._id = '{}b{}m'.format(self.nb, self.px_size_x)
        if wl is not None:
            self._id += ';'.join([str(w) for w in self.wavelengths])+ wlu
        if sensor_name is None:

            sensor_name = '{}bands@{}m'.format(self.nb, self.px_size_x)
        self.setName(sensor_name)

        self.hashvalue = hash(','.join(self.bandNames))

    def id(self):
        return self._id

    def setName(self, name):
        self._name = name
        self.sigNameChanged.emit(self.name())

    def name(self):
        return self._name

    def dataType(self, p_int):
        return self.bandDataType

    def bandClosestToWavelength(self, wl, wl_unit='nm'):
        """
        Returns the band index (>=0) of the band closest to wavelength wl
        :param wl:
        :param wl_unit:
        :return:
        """
        if not self.wavelengthsDefined():
            return None

        if wl in SensorInstrument.LUT_Wavelengths.keys():
            wl_unit = 'nm'
            wl = SensorInstrument.LUT_Wavelengths[wl]

        wl = float(wl)
        if self.wavelengthUnits != wl_unit:
            wl = convertMetricUnit(wl, wl_unit, self.wavelengthUnits)


        return np.argmin(np.abs(self.wavelengths - wl))




    def wavelengthsDefined(self):
        return self.wavelengths is not None and \
                self.wavelengthUnits is not None

    def __eq__(self, other):
        return self.nb == other.nb and \
               self.px_size_x == other.px_size_x and \
               self.px_size_y == other.px_size_y

    def __hash__(self):
        return hash(self.id())

    def __repr__(self):
        return str(self.__class__) +' ' + self.name()

    def getDescription(self):
        info = []
        info.append(self.name())
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tName\tWavelength')
        for b in range(self.nb):
            if self.wavelengths is not None:
                wl = str(self.wavelengths[b])
            else:
                wl = 'unknown'
            info.append('{}\t{}\t{}'.format(b + 1, self.bandNames[b], wl))

        return '\n'.join(info)


def verifyInputImage(path, vrtInspection=''):

    if not os.path.exists(path):
        print('{}Image does not exist: '.format(vrtInspection, path))
        return False
    ds = gdal.Open(path)
    if not ds:
        print('{}GDAL unable to open: '.format(vrtInspection, path))
        return False
    if ds.GetDriver().ShortName == 'VRT':
        vrtInspection = 'VRT Inspection {}\n'.format(path)
        validSrc = [verifyInputImage(p, vrtInspection=vrtInspection) for p in set(ds.GetFileList()) - set([path])]
        return all(validSrc)
    else:
        return True

def pixel2coord(gt, x, y):
    """Returns global coordinates from pixel x, y coords"""
    """https://scriptndebug.wordpress.com/2014/11/24/latitudelongitude-of-each-pixel-using-python-and-gdal/"""
    xoff, a, b, yoff, d, e = gt
    xp = a * x + b * y + xoff
    yp = d * x + e * y + yoff
    return (xp, yp)

class TimeSeriesDatum(QObject):
    @staticmethod
    def createFromPath(path):
        """
        Creates a valid TSD or returns None if this is impossible
        :param path:
        :return:
        """
        p = findAbsolutePath(path)
        if verifyInputImage(p):
            return TimeSeriesDatum(None, p)
        else:
            return None



    """
    Collects all data sets related to one sensor
    """
    sigVisibilityChanged = pyqtSignal(bool)
    sigRemoveMe = pyqtSignal()



    def __init__(self, timeSeries, pathImg):
        super(TimeSeriesDatum,self).__init__()

        ds = getDS(pathImg)

        self.pathImg = ds.GetFileList()[0]

        self.timeSeries = timeSeries
        self.nb, self.nl, self.ns, self.crs, px_x, px_y = getSpatialPropertiesFromDataset(ds)

        self.sensor = SensorInstrument(ds)

        self.date = getImageDateFromDataset(ds)
        self.doy = getDOYfromDate(self.date)
        assert self.date is not None, 'Unable to find acquisition date of {}'.format(pathImg)

        gt = ds.GetGeoTransform()

        UL = QgsPoint(*pixel2coord(gt, 0, 0))
        LR = QgsPoint(*pixel2coord(gt, self.ns, self.nl))
        from timeseriesviewer.main import SpatialExtent
        self._spatialExtent = SpatialExtent(self.crs, UL, LR)

        self.srs_wkt = str(self.crs.toWkt())


        self.mVisibility = True


    def rank(self):
        return self.timeSeries.index(self)

    def setVisibility(self, b):
        old = self.mVisibility
        self.mVisibility = b
        if old != self.mVisibility:
            self.sigVisibilityChanged.emit(b)

    def isVisible(self):
        return self.mVisibility


    def getDate(self):
        return np.datetime64(self.date)


    def getSpatialReference(self):
        return self.crs

    def spatialExtent(self):
        return self._spatialExtent

    def __repr__(self):
        return 'TS Datum {} {}'.format(self.date, str(self.sensor))

    def __cmp__(self, other):
        return cmp(str((self.date, self.sensor)), str((other.date, other.sensor)))

    #def __eq__(self, other):
    #    return self.date == other.date and self.sensor == other.sensor

    def __lt__(self, other):
        if self.date < other.date:
            return True
        else:
            return self.sensor.id() < other.sensor.id()

    def __hash__(self):
        return hash((self.date,self.sensor.id()))


class TimeSeries(QObject):

    sigTimeSeriesDatesAdded = pyqtSignal(list)
    sigTimeSeriesDatesRemoved = pyqtSignal(list)
    sigLoadingProgress = pyqtSignal(int, int, str)
    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigRuntimeStats = pyqtSignal(dict)

    def __init__(self, imageFiles=None, maskFiles=None):
        QObject.__init__(self)

        #define signals

        #fire when a new TSD is added


        #self.data = collections.OrderedDict()
        self.data = list()

        self.CHIP_BUFFER=dict()

        self.shape = None

        self.Sensors = collections.OrderedDict()

        self.Pool = None

        if imageFiles is not None:
            self.addFiles(imageFiles)
        if maskFiles is not None:
            self.addMasks(maskFiles)

    _sep = ';'


    def loadFromFile(self, path, n_max=None):

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
            self.addFiles(images[0:n_max])
        else:
            self.addFiles(images)
        #self.addMasks(masks)


    def saveToFile(self, path):
        if path is None or len(path) == 0:
            return

        lines = []
        lines.append('#Time series definition file: {}'.format(np.datetime64('now').astype(str)))
        lines.append('#<image path>[;<mask path>]')
        for TSD in self.data.values():

            line = TSD.pathImg
            if TSD.pathMsk is not None:
                line += TimeSeries._sep + TSD.pathMsk

            lines.append(line)

        lines = [l+'\n' for l in lines]

        print('Write {}'.format(path))
        with open(path, 'w') as f:
            f.writelines(lines)

    def getMaxSpatialExtent(self, crs=None):
        if len(self.data) == 0:
            return None

        extent = self.data[0].spatialExtent()
        if len(self.data) > 1:
            for TSD in self.data[1:]:
                extent.combineExtentWith(TSD.spatialExtent())

        return extent


    def tsdFromPath(self, path):
        for tsd in self.data:
            if tsd.pathImg == path:
                return tsd
        return False

    def getObservationDates(self):
        return [tsd.getDate() for tsd in self.data]

    def getTSD(self, pathOfInterest):
        for tsd in self.data:
            if tsd.pathImg == pathOfInterest:
                return tsd
        return None

    def getTSDs(self, dateOfInterest=None, sensorOfInterest=None):
        tsds = self.data[:]
        if dateOfInterest:
            tsds = [tsd for tsd in tsds if tsd.getDate() == dateOfInterest]
        if sensorOfInterest:
            tsds = [tsd for tsd in tsds if tsd.sensor == sensorOfInterest]
        return tsds

    def clear(self):
        self.removeDates(self[:])


    def removeDates(self, TSDs):
        removed = list()
        for TSD in TSDs:
            assert type(TSD) is TimeSeriesDatum
            self.data.remove(TSD)
            TSD.timeSeries = None
            removed.append(TSD)

            S = TSD.sensor
            self.Sensors[S].remove(TSD)
            if len(self.Sensors[S]) == 0:
                self.Sensors.pop(S)
                self.sigSensorRemoved.emit(S)

        self.sigTimeSeriesDatesRemoved.emit(removed)


    def addTimeSeriesDates(self, timeSeriesDates):
        assert isinstance(timeSeriesDates, list)
        added = list()
        for TSD in timeSeriesDates:
            try:
                sensorAdded = False
                existingSensors = list(self.Sensors.keys())
                if TSD.sensor not in existingSensors:
                    self.Sensors[TSD.sensor] = list()
                    sensorAdded = True
                else:
                    TSD.sensor = existingSensors[existingSensors.index(TSD.sensor)]

                if TSD in self.data:
                    six.print_('Time series datum already added: {} {}'.format(str(TSD), TSD.pathImg), file=sys.stderr)
                else:
                    self.Sensors[TSD.sensor].append(TSD)
                    #insert sorted

                    bisect.insort(self.data, TSD)
                    TSD.timeSeries = self
                    TSD.sigRemoveMe.connect(lambda : self.removeDates([TSD]))
                    added.append(TSD)
                if sensorAdded:
                    self.sigSensorAdded.emit(TSD.sensor)

            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2)
                six.print_('Unable to add {}'.format(file), file=sys.stderr)
                pass

        if len(added) > 0:
            self.sigTimeSeriesDatesAdded.emit(added)


    def addFiles(self, files):
        assert isinstance(files, list)
        nMax = len(files)
        nDone = 0
        self.sigLoadingProgress.emit(0,nMax, 'Start loading {} files...'.format(nMax))

        for i, file in enumerate(files):
            t0 = np.datetime64('now')
            tsd = TimeSeriesDatum.createFromPath(file)
            if tsd is None:
                msg = 'Unable to add: {}'.format(os.path.basename(file))
                dprint(msg, file=sys.stderr)
            else:
                self.addTimeSeriesDates([tsd])
                msg = 'Added {}'.format(os.path.basename(file))
                self.sigRuntimeStats.emit({'dt_addTSD':np.datetime64('now')-t0})
            nDone += 1
            self.sigLoadingProgress.emit(nDone, nMax, msg)


    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, slice):
        return self.data[slice]

    def __delitem__(self, slice):
        self.removeDates(slice)

    def __contains__(self, item):
        return item in self.data

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))


        return '\n'.join(info)

regAcqDate = re.compile(r'acquisition[ ]*(time|date|day)', re.I)
regLandsatSceneID = re.compile(r"L[EMCT][1234578]{1}[12]\d{12}[a-zA-Z]{3}\d{2}")

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

def getImageDateFromDataset(ds):
    assert isinstance(ds, gdal.Dataset)



    #search metadata for datetime information
    # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for datetime format

    regDateKeys = re.compile('(acquisition[ ]*time|date)')

    for domain in ds.GetMetadataDomainList():
        md = ds.GetMetadata_Dict(domain)
        for key, value in md.items():
            if regDateKeys.search(key):
                return np.datetime64(value)

    #extract from file basename
    path = ds.GetFileList()[0]
    bn = os.path.basename(path)
    path_dir = os.path.dirname(path)

    #search in basename
    date = parseAcquisitionDate(bn)
    if date: return date

    #find date in file directory path
    date = parseAcquisitionDate(path_dir)
    return date



regYYYYDOY = re.compile(r'(19|20)\d{5}')
regYYYYMMDD = re.compile(r'(19|20)\d{2}-\d{2}-\d{2}')
regYYYY = re.compile(r'(19|20)\d{2}')

def parseWavelengthFromDataSet(ds):
    assert isinstance(ds, gdal.Dataset)
    wl = None
    wlu = None

    #see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
    regWLkey = re.compile('.*wavelength[_ ]*$')
    regWLUkey = re.compile('.*wavelength[_ ]*units?$')
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)")
    regWLU = re.compile('((micro|nano|centi)meters)|(um|nm|mm|cm|m|GHz|MHz)')
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
                    wlu = match.group()
                names = ['nanometers', 'micrometers', 'millimeters', 'centimeters', 'decimeters']
                si = ['nm', 'um', 'mm', 'cm', 'dm']
                if wlu in names:
                    wlu = si[names.index(wlu)]

    return wl, wlu



def parseWavelength(lyr):
    wl = None
    wlu = None
    assert isinstance(lyr, QgsRasterLayer)
    md = [l.split('=') for l in str(lyr.metadata()).splitlines() if 'wavelength' in l.lower()]
    #see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
    regWLU = re.compile('((micro|nano|centi)meters)|(um|nm|mm|cm|m|GHz|MHz)')
    for kv in md:
        key, value = kv
        key = key.lower()
        if key == 'center wavelength':
            tmp = re.findall('\d*\.\d+|\d+', value) #find floats
            if len(tmp) == 0:
                tmp = re.findall('\d+', value) #find integers
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

    return wl, wlu



def parseAcquisitionDate(text):
    match = regLandsatSceneID.search(text)
    if match:
        id = match.group()
        return getDateTime64FromYYYYDOY(id[9:16])
    match = regYYYYMMDD.search(text)
    if match:
        return np.datetime64(match.group())
    match = regYYYYDOY.search(text)
    if match:
        return getDateTime64FromYYYYDOY(match.group())
    match = regYYYY.search(text)
    if match:
        return np.datetime64(match.group())
    return None



def getDateTime64FromYYYYDOY(yyyydoy):
    return getDateFromDOY(yyyydoy[0:4], yyyydoy[4:7])

def getDOYfromDate(dt):

    return (dt.astype('datetime64[D]') - dt.astype('datetime64[Y]')).astype(int)+1

def getDateFromDOY(year, doy):
        if type(year) is str:
            year = int(year)
        if type(doy) is str:
            doy = int(doy)
        return np.datetime64('{:04d}-01-01'.format(year)) + np.timedelta64(doy-1, 'D')


if __name__ == '__main__':

    assert getDOYfromDate(np.datetime64('2014-01-01')) == 1
    assert getDOYfromDate(np.datetime64('2017-12-31')) == 365

    print convertMetricUnit(100, 'cm', 'm')
    print convertMetricUnit(1, 'm', 'um')