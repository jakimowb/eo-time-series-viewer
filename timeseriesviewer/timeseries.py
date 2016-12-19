from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect, time, traceback, copy
import bisect
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *

import numpy as np


def transformGeometry(geom, crsSrc, crsDst, trans=None):
    if trans is None:
        assert isinstance(crsSrc, QgsCoordinateReferenceSystem)
        assert isinstance(crsDst, QgsCoordinateReferenceSystem)
        return transformGeometry(geom, None, None, trans=QgsCoordinateTransform(crsSrc, crsDst))
    else:
        assert isinstance(trans, QgsCoordinateTransform)
        return trans.transform(geom)




class SensorInstrument(QObject):

    INSTRUMENTS = dict()
    INSTRUMENTS = {(6, 30., 30.): 'Landsat Legacy' \
                , (7, 30., 30.): 'L8 OLI' \
                , (4, 10., 10.): 'S2 MSI 10m' \
                , (6, 20., 20.): 'S2 MSI 20m' \
                , (3, 30., 30.): 'S2 MSI 60m' \
                , (3, 30., 30.): 'S2 MSI 60m' \
                , (5, 5., 5.): 'RE 5m' \
                    }

    """
    def fromGDALDataSet(self, ds):
        assert isinstance(ds, gdal.Dataset)
        nb = ds.RasterCount
    """

    """
    Describes a Sensor Configuration
    """
    def __init__(self, refLyr, sensor_name=None):
        super(SensorInstrument, self).__init__()
        assert isinstance(refLyr, QgsRasterLayer)
        #QgsMapLayerRegistry.instance().addMapLayer(refLyr)
        self.nb = refLyr.bandCount()
        self.bandDataType = refLyr.dataProvider().dataType(1)
        self.refUri = refLyr.dataProvider().dataSourceUri()
        r = refLyr.renderer()
        self.defaultRGB = [r.redBand(), r.greenBand(), r.blueBand()]
        s = ""
        """
        dom = QDomDocument()
        root = dom.createElement('root')
        refLyr.renderer().writeXML(dom, root)
        dom.appendChild(root)
        self.renderXML = dom.toString()
        """

        #todo: better band names
        self.bandNames = [refLyr.bandName(i) for i in range(1, self.nb + 1)]
        #self.refLyr = refLyr

        self.TS = None
        px_size_x = refLyr.rasterUnitsPerPixelX()
        px_size_y = refLyr.rasterUnitsPerPixelY()

        self.px_size_x = float(abs(px_size_x))
        self.px_size_y = float(abs(px_size_y))

        assert self.px_size_x > 0
        assert self.px_size_y > 0

        wavelengths = None
        #todo: find wavelength
        if wavelengths is not None:
            assert len(wavelengths) == self.nb

        self.wavelengths = wavelengths

        if sensor_name is None:
            id = (self.nb, self.px_size_x, self.px_size_y)
            sensor_name = SensorInstrument.INSTRUMENTS.get(
                id,
                '{}band@{}m'.format(self.nb, self.px_size_x))

        self.sensorName = sensor_name

        self.hashvalue = hash(','.join(self.bandNames))

    def __eq__(self, other):
        return self.nb == other.nb and \
               self.px_size_x == other.px_size_x and \
               self.px_size_y == other.px_size_y

    def __hash__(self):
        return self.hashvalue

    def __repr__(self):
        return self.sensorName

    def getDescription(self):
        info = []
        info.append(self.sensorName)
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tName\tWavelength')
        for b in range(self.nb):
            if self.wavelengths:
                wl = str(self.wavelengths[b])
            else:
                wl = 'unknown'
            info.append('{}\t{}\t{}'.format(b + 1, self.bandNames[b], wl))

        return '\n'.join(info)


class TSDLoaderSignals(QObject):

    sigRasterLayerLoaded = pyqtSignal(QgsRasterLayer)
    sigFinished = pyqtSignal()

class TSDLoader(QRunnable):
    """
    Runnable to load QgsRasterLayers from a parallel thread
    """
    def __init__(self, tsd_paths):
        super(TSDLoader, self).__init__()
        self.signals = TSDLoaderSignals()

        self.paths = list()
        for p in tsd_paths:
            if not (isinstance(p, tuple) or isinstance(p, list)):
                p = [p]
            self.paths.append(p)


    def run(self):
        lyrs = []
        for path in self.paths:
            TSD = TimeSeriesDatum(path)
            lyr = QgsRasterLayer(path)
            if lyr:
                lyrs.append(lyr)
                self.signals.sigRasterLayerLoaded.emit(lyr)
                dprint('{} loaded'.format(path))
            else:
                dprint('Failed to load {}'.format(path))
        self.signals.sigFinished.emit()
        #return lyrs


class TimeSeriesDatum(QObject):
    """
    Collects all data sets related to one sensor
    """

    def __init__(self, pathImg, pathMsk=None):
        super(TimeSeriesDatum,self).__init__()
        self.pathImg = pathImg
        self.pathMsk = None

        self.lyrImg = QgsRasterLayer(pathImg, os.path.basename(pathImg), False)
        self.uriImg = self.lyrImg.dataProvider().dataSourceUri()

        self.crs = self.lyrImg.dataProvider().crs()
        self.sensor = SensorInstrument(self.lyrImg)

        self.date = getImageDate2(self.lyrImg)
        assert self.date is not None, 'Unable to find acquisition date of {}'.format(pathImg)

        self.ns = self.lyrImg.width()
        self.nl = self.lyrImg.height()
        self.nb = self.lyrImg.bandCount()
        self.srs_wkt = str(self.crs.toWkt())


        if pathMsk:
            self.setMask(pathMsk)

    def getdtype(self):
        return gdal_array.GDALTypeCodeToNumericTypeCode(self.etype)

    def getDate(self):
        return np.datetime64(self.date)


    def getSpatialReference(self):
        return self.crs


    def getBoundingBox(self, srs=None):

        bbox = self.lyrImg.extent()
        if srs:
            assert isinstance(srs, QgsCoordinateReferenceSystem)
            bbox = transformGeometry(bbox, self.crs, srs)
        return bbox


    def setMask(self, pathMsk, raise_errors=True, mask_value=0, exclude_mask_value=True):
        dsMsk = gdal.Open(pathMsk)
        mskDate = getImageDate(dsMsk)


        errors = list()
        if mskDate and mskDate != self.getDate():
            errors.append('Mask date differs from image date')
        if self.ns != dsMsk.RasterXSize or self.nl != dsMsk.RasterYSize:
            errors.append('Spatial size differs')
        if dsMsk.RasterCount != 1:
            errors.append('Mask has > 1 bands')

        projImg = self.getSpatialReference()
        projMsk = osr.SpatialReference()
        projMsk.ImportFromWkt(dsMsk.GetProjection())

        if not projImg.IsSame(projMsk):
            errors.append('Spatial Reference differs from image')
        if self.gt != list(dsMsk.GetGeoTransform()):
            errors.append('Geotransformation differs from image')

        if len(errors) > 0:
            errors.insert(0, 'pathImg:{} \npathMsk:{}'.format(self.pathImg, pathMsk))
            errors = '\n'.join(errors)
            if raise_errors:
                raise Exception(errors)
            else:
                six.print_(errors, file=sys.stderr)
                return False
        else:
            self.pathMsk = pathMsk
            self.mask_value = mask_value
            self.exclude_mask_value = exclude_mask_value

            return True

    def readSpatialChip(self, geometry, srs=None, bands=[4,5,3]):

        srs_img = osr.SpatialReference()
        srs_img.ImportFromWkt(self.srs_wkt)


        if type(geometry) is ogr.Geometry:
            g_bb = geometry
            srs_bb = g_bb.GetSpatialReference()
        else:
            assert srs is not None and type(srs) in [str, osr.SpatialReference]
            if type(srs) is str:
                srs_bb = osr.SpatialReference()
                srs_bb.ImportFromWkt(srs)
            else:
                srs_bb = srs.Clone()
            g_bb = ogr.CreateGeometryFromWkt(geometry, srs_bb)

        assert srs_bb is not None and g_bb is not None
        assert g_bb.GetGeometryName() == 'POLYGON'

        if not srs_img.IsSame(srs_bb):
            g_bb = g_bb.Clone()
            g_bb.TransformTo(srs_img)

        cx0,cx1,cy0,cy1 = g_bb.GetEnvelope()

        ul_px = coordinate2px(self.gt, min([cx0, cx1]), max([cy0, cy1]))
        lr_px = coordinate2px(self.gt, max([cx0, cx1]), min([cy0, cy1]))
        lr_px = [c+1 for c in lr_px] #+1

        return self.readImageChip([ul_px[0], lr_px[0]], [ul_px[1], lr_px[1]], bands=bands)

    def readImageChip(self, px_x, px_y, bands=[4,5,3]):

        ds = gdal.Open(self.pathImg, gdal.GA_ReadOnly)

        assert len(px_x) == 2 and px_x[0] <= px_x[1]
        assert len(px_y) == 2 and px_y[0] <= px_y[1]

        ns = px_x[1]-px_x[0]+1
        nl = px_y[1]-px_y[0]+1
        assert ns >= 0
        assert nl >= 0

        src_ns = ds.RasterXSize
        src_nl = ds.RasterYSize


        chipdata = dict()



        #pixel indices in source image
        x0 = max([0, px_x[0]])
        y0 = max([0, px_y[0]])
        x1 = min([src_ns, px_x[1]])
        y1 = min([src_nl, px_y[1]])
        win_xsize = x1-x0+1
        win_ysize = y1-y0+1

        #pixel indices in image chip (ideally 0 and ns-1 or nl-1)
        i0 = x0 - px_x[0]
        i1 = i0 + win_xsize

        j0 = y0 - px_y[0]
        j1 = j0+ win_ysize




        templateImg = np.zeros((nl,ns))
        if self.nodata:
            templateImg *= self.nodata

        templateImg = templateImg.astype(self.getdtype())
        templateMsk = np.ones((nl,ns), dtype='bool')

        if win_xsize < 1 or win_ysize < 1:
            six.print_('Selected image chip is out of raster image {}'.format(self.pathImg), file=sys.stderr)
            for i, b in enumerate(bands):
                chipdata[b] = np.copy(templateImg)

        else:
            for i, b in enumerate(bands):
                band = ds.GetRasterBand(b)
                data = np.copy(templateImg)
                data[j0:j1,i0:i1] = band.ReadAsArray(xoff=x0, yoff=y0, win_xsize=win_xsize,win_ysize=win_ysize)
                chipdata[b] = data
                nodatavalue = band.GetNoDataValue()
                if nodatavalue is not None:
                    templateMsk[j0:j1,i0:i1] = np.logical_and(templateMsk[j0:j1,i0:i1], data[j0:j1,i0:i1] != nodatavalue)

            if self.pathMsk:
                ds = gdal.Open(self.pathMsk)
                tmp = ds.GetRasterBand(1).ReadAsArray(xoff=x0, yoff=y0, \
                            win_xsize=win_xsize,win_ysize=win_ysize) == 0

                templateMsk[j0:j1,i0:i1] = np.logical_and(templateMsk[j0:j1,i0:i1], tmp)

        chipdata['mask'] = templateMsk
        return chipdata

    def __repr__(self):
        return 'TS Datum {} {}'.format(self.date, str(self.sensor))

    def __cmp__(self, other):
        return cmp(str((self.date, self.sensor)), str((other.date, other.sensor)))

    def __eq__(self, other):
        return self.date == other.date and self.sensor == other.sensor

    def __hash__(self):
        return hash((self.date,self.sensor.sensorName))


class TimeSeries(QObject):
    datumAdded = pyqtSignal(TimeSeriesDatum)

    #fire when a new sensor configuration is added
    sensorAdded = pyqtSignal(SensorInstrument, name='sensorAdded')

    changed = pyqtSignal()
    progress = pyqtSignal(int,int,int, name='progress')
    closed = pyqtSignal()
    error = pyqtSignal(object)

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


    def loadFromFile(self, path):

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

        self.addFiles(images)
        self.addMasks(masks)


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



    def getMaxExtent(self, srs=None):
        if len(self.data) == 0:
            return None

        if srs is None:
            srs = self.data[0].crs()
        bb = None
        for TSD in self.data:
            if bb is None:
                bb = TSD.getBoundingBox(srs=srs)
            else:
                bb.unionRect(TSD.getBoundingBox(srs=srs))

        return bb

    def getObservationDates(self):
        return [tsd.getDate() for tsd in self.data]

    def getTSDs(self, date_of_interest=None):
        if date_of_interest:
            tsds = [tsd for tsd in self.data if tsd.getDate() == date_of_interest]
        else:
            tsds = self.data
        return tsds

    def _callback_error(self, error):
        six.print_(error, file=sys.stderr)
        self.error.emit(error)
        self._callback_progress()

    def _callback_spatialchips(self, results):
        self.chipLoaded.emit(results)
        self._callback_progress()

    def _callback_progress(self):
        self._callback_progress_done += 1
        self.progress.emit(0, self._callback_progress_done, self._callback_progress_max)

        if self._callback_progress_done >= self._callback_progress_max:
            self._callback_progress_done = 0
            self._callback_progress_max = 0
            self.progress.emit(0,0,1)

    def getSpatialChips_parallel(self, bbWkt, srsWkt, TSD_band_list, ncpu=1):
        assert type(bbWkt) is str and type(srsWkt) is str

        import multiprocessing
        if self.Pool is not None:
            self.Pool.terminate()

        self.Pool = multiprocessing.Pool(processes=ncpu)


        self._callback_progress_max = len(TSD_band_list)
        self._callback_progress_done = 0

        for T in TSD_band_list:

            TSD = copy.deepcopy(T[0])
            bands = T[1]
            #TSD = pickle.dumps(self.data[date])
            args = (TSD, bbWkt, srsWkt)
            kwds = {'bands':bands}

            if six.PY3:
                self.Pool.apply_async(PFunc_TimeSeries_getSpatialChip, \
                                 args=args, kwds=kwds, \
                                 callback=self._callback_spatialchips, error_callback=self._callback_error)
            else:
                self.Pool.apply_async(PFunc_TimeSeries_getSpatialChip, \
                                      args, kwds, self._callback_spatialchips)

        s = ""

        pass

    def getImageChips(self, xy, size=50, bands=[4,5,6], dates=None):
        chipCollection = collections.OrderedDict()

        if dates is None:
            dates = self.data.keys()
        for date in dates:
            TSD = self.data[date]
            chipCollection[date] = TSD.readImageChip(xy, size=size, bands=bands)

        return chipCollection

    def addMasks(self, files, raise_errors=True, mask_value=0, exclude_mask_value=True):
        assert isinstance(files, list)
        l = len(files)

        self.progress.emit(0,0,l)
        for i, file in enumerate(files):

            try:
                self.addMask(file, raise_errors=raise_errors, mask_value=mask_value, exclude_mask_value=exclude_mask_value, _quiet=True)
            except:
                pass

            self.progress.emit(0,i+1,l)

        self.progress.emit(0,0,1)
        self.changed.emit()

    def addMask(self, pathMsk, raise_errors=True, mask_value=0, exclude_mask_value=True, _quiet=False):
        print('Add mask {}...'.format(pathMsk))
        ds = getDS(pathMsk)
        date = getImageDate(ds)

        if date in self.data.keys():
            TSD = self.data[date]

            if not _quiet:
                self.changed.emit()

            return TSD.setMask(pathMsk, raise_errors=raise_errors, mask_value=mask_value, exclude_mask_value=exclude_mask_value)
        else:
            info = 'TimeSeries does not contain date {} {}'.format(date, pathMsk)
            if raise_errors:
                raise Exception(info)
            else:
                six.print_(info, file=sys.stderr)
            return False

    def removeAll(self):
        self.clear()

    def clear(self):
        self.Sensors.clear()
        del self.data[:]
        self.changed.emit()


    def removeDates(self, TSDs):
        for TSD in TSDs:
            self.removeTSD(TSD, _quiet=True)
        self.changed.emit()

    def removeTSD(self, TSD, _quiet=False):

        assert type(TSD) is TimeSeriesDatum
        S = TSD.sensor
        self.Sensors[S].remove(TSD)
        self.data.pop(TSD, None)
        if len(self.Sensors[S]) == 0:
            self.Sensors.pop(S)
        if not _quiet:
            self.changed.emit()



    def addFile(self, pathImg, pathMsk=None, _quiet=False):
        six.print_(pathImg)
        six.print_('Add image {}...'.format(pathImg))
        TSD = TimeSeriesDatum(pathImg, pathMsk=pathMsk)
        self.addTimeSeriesDatum(TSD)

    def addTimeSeriesDatum(self, TSD):

        try:
            sensorAdded = False
            existingSensors = list(self.Sensors.keys())
            if TSD.sensor not in existingSensors:
                self.Sensors[TSD.sensor] = list()
                sensorAdded = True
            else:
                TSD.sensor = existingSensors[existingSensors.index(TSD.sensor)]

            if TSD in self.data:
                six.print_('Time series datum already added: {}'.format(str(TSD)), file=sys.stderr)
            else:
                self.Sensors[TSD.sensor].append(TSD)

                #insert sorted
                bisect.insort(self.data, TSD)
                #self.data[TSD] = TSD
                self.datumAdded.emit(TSD)
            if sensorAdded:
                self.sensorAdded.emit(TSD.sensor)


        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2)
            six.print_('Unable to add {}'.format(file), file=sys.stderr)
            pass



    def addFilesAsync(self, files):
        assert isinstance(files, list)


    def addFiles(self, files):
        assert isinstance(files, list)
        l = len(files)
        assert l > 0

        self.progress.emit(0,0,l)
        for i, file in enumerate(files):
            self.addFile(file, _quiet=True)
            self.progress.emit(0,i+1,l)

        self.progress.emit(0,0,1)
        self.changed.emit()


    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, item):
        return item in self.data

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))

        if l > 0:
            keys = list(self.data.keys())
            info.append('  Range: {} to {}'.format(keys[0], keys[-1]))
        return '\n'.join(info)

regAcqDate = re.compile(r'acquisition[ ]*(time|date|day)', re.I)
regLandsatSceneID = re.compile(r"L[EMCT][1234578]{1}[12]\d{12}[a-zA-Z]{3}\d{2}")

def getImageDate2(lyr):
    assert isinstance(lyr, QgsRasterLayer)
    mdLines = str(lyr.metadata()).splitlines()
    date = None
    #find date in metadata
    for line in [l for l in mdLines if regAcqDate.search(l)]:
        date = parseAcquisitionDate(line)
        if date:
            return date
    #find date in filename
    dn, fn = os.path.split(str(lyr.dataProvider().dataSourceUri()))
    date = parseAcquisitionDate(fn)
    if date: return date

    #find date in file directory path
    date = parseAcquisitionDate(date)

    return date


def PFunc_TimeSeries_getSpatialChip(TSD, bbWkt, srsWkt , bands=[4,5,3]):

    chipdata = TSD.readSpatialChip(bbWkt, srs=srsWkt, bands=bands)

    return TSD, chipdata

def px2Coordinate(gt, pxX, pxY, upper_left=True):
    cx = gt[0] + pxX*gt[1] + pxY*gt[2]
    cy = gt[3] + pxX*gt[4] + pxY*gt[5]
    if not upper_left:
        cx += gt[1]*0.5
        cy += gt[5]*0.5
    return cx, cy

def coordinate2px(gt, cx, cy):
    px = int((cx - gt[0]) / gt[1])
    py = int((cy - gt[3]) / gt[5])
    return px, py


regYYYYDOY = re.compile(r'(19|20)\d{5}')
regYYYYMMDD = re.compile(r'(19|20)\d{2}-\d{2}-\d{2}')
regYYYY = re.compile(r'(19|20)\d{2}')

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
    return getDateTime64FromDOY(yyyydoy[0:4], yyyydoy[4:7])

def getDateTime64FromDOY(year, doy):
        if type(year) is str:
            year = int(year)
        if type(doy) is str:
            doy = int(doy)
        return np.datetime64('{:04d}-01-01'.format(year)) + np.timedelta64(doy-1, 'D')
