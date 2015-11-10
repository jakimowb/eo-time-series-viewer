# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EnMAPBox
                                 A QGIS plugin
 EnMAP-Box V3
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by HU-Berlin
        email                : bj@geo.hu-berlin.de
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

try:
    from qgis.core import *
    from qgis.gui import *
    import qgis
    import qgis_add_ins
    qgis_available = True
except:
    qgis_available = False

# Import the code for the dialog
import os, sys, re, fnmatch, collections, copy
from osgeo import gdal, ogr, osr, gdal_array
import numpy as np
import pickle

import six
import multiprocessing


#I don't know why but this is required to run this in QGIS

path = os.path.abspath(os.path.join(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

pluginDir = os.path.dirname(__file__)
sys.path.append(pluginDir)
sys.path.append(os.path.join(pluginDir, 'qimage2ndarray'))

import qimage2ndarray

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from sensecarbon_tsv_gui import SenseCarbon_TSVGui

DEBUG = True

regLandsatSceneID = re.compile(r"L[EMCT][1234578]{1}[12]\d{12}[a-zA-Z]{3}\d{2}")



def file_search(rootdir, wildcard, recursive=False, ignoreCase=False):
    assert rootdir is not None
    if not os.path.isdir(rootdir):
        six.print_("Path is not a directory:{}".format(rootdir), file=sys.stderr)

    results = []

    for root, dirs, files in os.walk(rootdir):
        for file in files:
            if (ignoreCase and fnmatch.fnmatch(file.lower(), wildcard.lower())) \
                    or fnmatch.fnmatch(file, wildcard):
                results.append(os.path.join(root, file))
        if not recursive:
            break
    return results


class TimeSeriesTableModel(QAbstractTableModel):
    columnames = ['date','name','ns','nl','nb','image','mask']

    def __init__(self, TS, parent=None, *args):
        super(QAbstractTableModel, self).__init__()
        assert isinstance(TS, TimeSeries)
        self.TS = TS

    def rowCount(self, parent = QModelIndex()):
        return len(self.TS)

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self._data[row:row+count]
        for i in toRemove:
            self._data.remove(i)

        self.endRemoveRows()

    def getDateFromIndex(self, index):
        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.TS):
                return self.TS.getDates()[i]
        return None

    def getTimeSeriesDatumFromIndex(self, index):

        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.TS):
                date = self.TS.getDates()[i]
                return self.TS.data[date]

        return None



    def data(self, index, role = Qt.DisplayRole):
        if role is None or Qt is None or index.isValid() == False:
            return None


        value = None
        ic_name = self.columnames[index.column()]
        TSD = self.getTimeSeriesDatumFromIndex(index)
        keys = list(TSD.__dict__.keys())
        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if ic_name == 'name':
                value = os.path.basename(TSD.pathImg)
            elif ic_name == 'date':
                value = '{}'.format(TSD.date)
            elif ic_name == 'image':
                value = TSD.pathImg
            elif ic_name == 'mask':
                value = TSD.pathMsk
            elif ic_name in keys:
                value = TSD.__dict__[ic_name]
            else:
                s = ""
        elif role == Qt.BackgroundColorRole:
            value = None
        elif role == Qt.UserRole:
            value = self._data[index.row()]

        return value

    #def flags(self, index):
    #    return Qt.ItemIsEnabled

    def flags(self, index):
        if index.isValid():
            item = self.getTimeSeriesDatumFromIndex(index)
            cname = self.columnames[index.column()]
            if cname.startswith('d'): #relative values can be edited
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
            else:
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

class TimeSeriesItemModel(QAbstractItemModel):

    def __init__(self, TS):
        QAbstractItemModel.__init__(self)
        #self.rootItem = TreeItem[]
        assert type(TS) is TimeSeries
        self.TS = TS

    def index(self, row, column, parent = QModelIndex()):
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def setData(self, index, value, role = Qt.EditRole):
        if role == Qt.EditRole:
            row = index.row()

            return False
        return False

    def data(self, index, role=Qt.DisplayRole):
        data = None
        if role == Qt.DisplayRole or role == Qt.EditRole:
            data = 'sampletext'


        return data

    def flags(self, QModelIndex):
        return Qt.ItemIsSelectable

    def rowCount(self, index=QModelIndex()):
        return len(self.TS)

    #---------------------------------------------------------------------------
    def columnCount(self, index=QModelIndex()):
        return 1


class TimeSeries(QObject):

    #define signals
    datumAdded = pyqtSignal(list, name='datumAdded')
    changed = pyqtSignal()
    progress = pyqtSignal(int,int,int, name='progress')
    chipLoaded = pyqtSignal(object, name='chiploaded')
    closed = pyqtSignal()
    error = pyqtSignal(object)

    data = collections.OrderedDict()

    CHIP_BUFFER=dict()

    shape = None

    def __init__(self, imageFiles=None, maskFiles=None):
        QObject.__init__(self)

        self.Pool = None
        self.nb = None
        self.srs = None
        self.bandnames = list()


        if imageFiles is not None:
            self.addFiles(imageFiles)
        if maskFiles is not None:
            self.addMasks(maskFiles)



    def getMaxExtent(self):

        x = []
        y = []

        for TSD in self.data.values():
            bb = TSD.getBoundingBox(self.srs)
            x.extend([c[0] for c in bb])
            y.extend([c[1] for c in bb])

        return (min(x), min(y), max(x), max(y))

    def getDates(self):
        return list(self.data.keys())



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

    def getSpatialChips_parallel(self, bbWkt, srsWkt, dates=None, bands=[4,5,3], ncpu=1):
        assert type(bbWkt) is str and type(srsWkt) is str

        import multiprocessing
        if self.Pool is not None:
            self.Pool.terminate()

        self.Pool = multiprocessing.Pool(processes=ncpu)

        if dates is None:
            dates = self.getDates()

        self._callback_progress_max = len(dates)
        self._callback_progress_done = 0

        for date in dates:

            TSD = copy.deepcopy(self.data[date])
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
        assert l > 0

        self.progress.emit(0,0,l)
        for i, file in enumerate(files):

            try:
                self.addMask(file, raise_errors=raise_errors, mask_value=mask_value, exclude_mask_value=exclude_mask_value, _quiet=True)
            except:
                pass

            self.progress.emit(0,i+1,l)

        self.progress.emit(0,0,l)
        self.changed()

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
        dates = list(self.data.keys())
        for date in dates:
            self.removeDate(date, _quiet=True)
        self.changed.emit()


    def removeDates(self, dates):
        for date in dates:
            self.removeDate(date, _quiet=True)
        self.changed.emit()

    def removeDate(self, date, _quiet=False):

        assert type(date) is np.datetime64

        self.data.pop(date, None)
        if len(self.data) == 0:
            self.nb = None
            self.bandnames = None
            self.srs = None
        if not _quiet:
            self.changed.emit()


    def addFile(self, pathImg, pathMsk=None, _quiet=False):

        print(pathImg)
        print('Add image {}...'.format(pathImg))

        TSD = TimeSeriesDatum(pathImg, pathMsk=pathMsk)

        if self.nb is None:

            self.nb = TSD.nb
            self.bandnames = TSD.bandnames
            self.srs = TSD.getSpatialReference()

        else:

            assert self.nb == TSD.nb, 'TimeSeries initialized with {} bands but image {} has {} bands'.find(self.nb, pathImg, TSD.nb)

        self.data[TSD.getDate()] = TSD

        if not _quiet:
            self._sortTimeSeriesData()
            self.changed.emit()
            self.datumAdded.emit(self.bandnames[:])


    def addFiles(self, files):
        assert isinstance(files, list)
        l = len(files)
        assert l > 0

        self.progress.emit(0,0,l)
        for i, file in enumerate(files):
            try:
                self.addFile(file, _quiet=True)
            except:
                pass
            self.progress.emit(0,i+1,l)

        self._sortTimeSeriesData()
        self.progress.emit(0,0,l)
        self.datumAdded.emit(self.bandnames[:])



    def _sortTimeSeriesData(self):
        self.data = collections.OrderedDict(sorted(self.data.items(), key=lambda t:t[0]))

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))

        if l > 0:
            keys = list(self.data.keys())
            info.append('  Range: {} to {}'.format(keys[0], keys[-1]))
            info.append('  Bands: {} [{}]'.format(self.nb,','.join(self.bandnames)))
        return '\n'.join(info)

def PFunc_TimeSeries_getSpatialChip(TSD, bbWkt, srsWkt , bands=[4,5,3]):

    chipdata = TSD.readSpatialChip(bbWkt, srs=srsWkt, bands=bands)

    return TSD.getDate(), chipdata

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

def getDS(ds):
    if type(ds) is not gdal.Dataset:
        ds = gdal.Open(ds)
    return ds

def getImageDate(ds):
    if type(ds) is str:
        ds = gdal.Open(ds)

    path = ds.GetFileList()[0]
    to_check = [os.path.basename(path), os.path.dirname(path)]

    regAcqDate = re.compile(r'acquisition (time|date|day)', re.I)
    for key, value in ds.GetMetadata_Dict().items():
        if regAcqDate.search(key):
            to_check.insert(0, value)

    for text in to_check:
        date = parseAcquisitionDate(text)
        if date:
            return date

    raise Exception('Can not identify acquisition date of {}'.format(path))


class TimeSeriesDatum(object):

    def __init__(self, pathImg, pathMsk=None):
        self.pathImg = pathImg
        self.pathMsk = None

        dsImg = gdal.Open(pathImg)
        assert dsImg

        date = getImageDate(dsImg)
        assert date is not None
        self.date = date.astype(str)

        self.ns = dsImg.RasterXSize
        self.nl = dsImg.RasterYSize
        self.nb = dsImg.RasterCount

        self.srs_wkt = dsImg.GetProjection()
        self.gt = list(dsImg.GetGeoTransform())

        refBand = dsImg.GetRasterBand(1)
        self.etype = refBand.DataType

        self.nodata = refBand.GetNoDataValue()


        self.bandnames = list()
        for b in range(self.nb):
            name = dsImg.GetRasterBand(b+1).GetDescription()
            if name is None or name == '':
                name = 'Band {}'.format(b+1)
            self.bandnames.append(name)

        if pathMsk:
            self.setMask(pathMsk)

    def getdtype(self):
        return gdal_array.GDALTypeCodeToNumericTypeCode(self.etype)

    def getDate(self):
        return np.datetime64(self.date)

    def getSpatialReference(self):
        srs = osr.SpatialReference()
        srs.ImportFromWkt(self.srs_wkt)
        return srs

    def getBoundingBox(self, srs=None):
        ext = list()


        for px in [0,self.ns]:
            for py in [0, self.nl]:
                ext.append(px2Coordinate(self.gt, px, py))



        if srs is not None:
            my_srs = self.getSpatialReference()
            if not my_srs.IsSame(srs):
                #todo: consider srs differences
                raise Exception('differeng SRS in bounding box request')
                pass

        return ext


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
            g = geometry
            srs_bb = g.GetSpatialReference()
        else:
            assert srs is not None and type(srs) in [str, osr.SpatialReference]
            if type(srs) is str:
                srs_bb = osr.SpatialReference()
                srs_bb.ImportFromWkt(srs)
            else:
                srs_bb = srs.Clone()
            g = ogr.CreateGeometryFromWkt(geometry, srs_bb)

        assert srs_bb is not None and g is not None
        assert g.GetGeometryName() == 'POLYGON'

        if not srs_img.IsSame(srs_bb):
            g = g.Clone()
            g.TransformTo(srs_img)
        cx0,cx1,cy0,cy1 = g.GetEnvelope()

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
            six.print_('Selected image chip is out of raster image', file=sys.stderr)
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
        info = []
        info.append('TS Datum {}'.format(self.date))
        for key in ['pathImg', 'pathMsk']:
            info.append('  {}:{}'.format(key,self.__dict__[key]))
        return '\n'.join(info)

regYYYYDOY = re.compile(r'(19|20)\d{5}')
regYYYYMMDD = re.compile(r'(19|20)\d{2}-\d{2}-\d{2}')
regYYYY = re.compile(r'(19|20)\d{2}')
def parseAcquisitionDate(text):
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


class PictureTest(QMainWindow):

    def __init__(self, parent=None, qImage=None):
        super(PictureTest,self).__init__(parent)
        self.setWindowTitle("Show Image with pyqt")
        self.imageLabel=QLabel()
        self.imageLabel.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored)
        self.setCentralWidget(self.imageLabel)

        self.cv_img = None

        if qImage:
            self.addImage(qImage)

    def addImage(self, qImage):
        pxmap = QPixmap.fromImage(qImage)
        self.addPixmap(pxmap)

    def addPixmap(self, pixmap):
        pxmap = pixmap.scaled(self.imageLabel.size(), Qt.KeepAspectRatio)
        self.imageLabel.setPixmap(pxmap)
        self.imageLabel.adjustSize()
        self.imageLabel.update()

    def addNumpy(self, data):


        img = Array2Image(data)
        self.addImage(img)

        #self.resize(img.width(), img.height())

def getChip3d(chips, rgb_idx, ranges):
    assert len(rgb_idx) == 3 and len(rgb_idx) == len(ranges)
    for i in rgb_idx:
        assert i in chips.keys()

    nl, ns = chips[rgb_idx[0]].shape
    a3d = np.ndarray((3,nl,ns), dtype='float')

    for i, rgb_i in enumerate(rgb_idx):
        range = ranges[i]
        data = chips[rgb_i].astype('float')
        data -= range[0]
        data *= 255./range[1]
        a3d[i,:] = data

    np.clip(a3d, 0, 255, out=a3d)

    return a3d.astype('uint8')

def Array2Image(d3d):
    nb, nl, ns = d3d.shape
    byteperline = nb
    d3d = d3d.transpose([1,2,0]).copy()

    return QImage(d3d.data, ns, nl, QImage.Format_RGB888)



class ImageChipBuffer(object):

    data = dict()
    BBox = None
    SRS = None

    def __init__(self):

        pass

    def hasDataCube(self, date):
        return date in self.data.keys()

    def getMissingBands(self, date, bands):
        missing = set(bands)
        if date in self.data.keys():
            missing = missing - set(self.data[date].keys())

        return missing

    def addDataCube(self, date, chipData):
        assert self.BBox is not None, 'Please initialize the bounding box first.'

        assert type(date) == np.datetime64
        assert isinstance(chipData, dict)
        if date not in self.data.keys():
            self.data[date] = dict()
        self.data[date].update(chipData)

    def getDataCube(self, date):
        return self.data.get(date)

    def getChipRGB(self, date, view):
        bands = view.getBands()
        band_ranges = view.getRanges()
        assert len(bands) == 3 and len(bands) == len(band_ranges)
        assert date in self.data, 'Date {} is not in buffer'.format(date)
        chipData = self.data[date]
        for b in bands:
            assert b in chipData.keys()

        nl, ns = chipData[bands[0]].shape
        rgb_data = np.ndarray((3,nl,ns), dtype='float')

        for i, b in enumerate(bands):
            range = band_ranges[i]
            data = chipData[b].astype('float')
            data -= range[0]
            data *= 255./range[1]
            rgb_data[i,:] = data

        np.clip(rgb_data, 0, 255, out=rgb_data)
        rgb_data = rgb_data.astype('uint8')

        if view.useMaskValues():
            rgb = view.getMaskColor()
            is_masked = np.where(np.logical_not(chipData['mask']))
            for i, c in enumerate(rgb):
                rgb_data[i, is_masked[0], is_masked[1]] = c

        return  rgb_data

    def getChipImage(self, date, view):
        rgb = self.getChipRGB(date, view)
        nb, nl, ns = rgb.shape
        rgb = rgb.transpose([1,2,0]).copy('C')
        return QImage(rgb.data, ns, nl, QImage.Format_RGB888)

    def clear(self):
        self.data.clear()

    def setBoundingBox(self, BBox):
        assert type(BBox) is ogr.Geometry
        SRS = BBox.GetSpatialReference()
        assert SRS is not None
        if self.BBox is None or not self.BBox.Equals(BBox) or not self.SRS.IsSame(SRS):
            self.data.clear()
            self.BBox = BBox
            self.SRS = SRS

    def __repr__(self):
        info = ['Chipbuffer']
        info.append('Bounding Box: {}'.format(self.bbBoxWkt))
        info.append('Chips: {}'.format(len(self.data)))
        return '\n'.join(info)


class SenseCarbon_TSV:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = 'placeholder'
        #locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'EnMAPBox_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = SenseCarbon_TSVGui()
        D = self.dlg
        self.TS = TimeSeries()
        self.TS.datumAdded.connect(self.ua_datumAdded)
        self.TS.progress.connect(self.ua_TSprogress)
        self.TS.chipLoaded.connect(self.ua_showPxCoordinate_addChips)


        TSM = TimeSeriesTableModel(self.TS)
        D.tableView_TimeSeries.setModel(TSM)
        D.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        D.cb_timeWindow_doi.setModel(TSM)
        D.cb_timeWindow_doi.setModelColumn(0)

        self.VIEWS = list()
        self.ImageChipBuffer = ImageChipBuffer()
        self.CHIPWIDGETS = collections.OrderedDict()

        self.ValidatorPxX = QIntValidator(0,99999)
        self.ValidatorPxY = QIntValidator(0,99999)
        D.btn_showPxCoordinate.clicked.connect(lambda: self.ua_showPxCoordinate_start())
        D.btn_selectByCoordinate.clicked.connect(self.ua_selectByCoordinate)
        D.btn_selectByRectangle.clicked.connect(self.ua_selectByRectangle)
        D.btn_addBandView.clicked.connect(lambda :self.ua_addView())
        D.btn_addTSImages.clicked.connect(lambda :self.ua_addTSImages())
        D.btn_addTSMasks.clicked.connect(lambda :self.ua_addTSMasks())
        D.btn_removeTSD.clicked.connect(lambda : self.ua_removeTSD(None))
        D.btn_removeTS.clicked.connect(self.ua_removeTS)

        D.spinBox_ncpu.setRange(0, multiprocessing.cpu_count())

        # Declare instance attributes
        self.actions = []
        #self.menu = self.tr(u'&EnMAP-Box')
        # TODO: We are going to let the user set this up in a future iteration
        self.RectangleMapTool = None
        self.PointMapTool = None
        if self.iface:
            print('Init QGIS Interaction')
            self.canvas = self.iface.mapCanvas()
            self.menu = self.tr(u'&SenseCarbon TSV')
            self.toolbar = self.iface.addToolBar(u'SenseCarbon TSV')
            self.toolbar.setObjectName(u'SenseCarbon TSV')

            self.RectangleMapTool = qgis_add_ins.RectangleMapTool(self.canvas)
            self.RectangleMapTool.rectangleDrawed.connect(self.ua_selectBy_Response)
            self.PointMapTool = qgis_add_ins.PointMapTool(self.canvas)
            self.PointMapTool.coordinateSelected.connect(self.ua_selectBy_Response)
            #self.RectangleMapTool..connect(self.ua_selectByRectangle_Done)

        self.CPV = self.dlg.scrollAreaWidgetContents.layout()
        self.check_enabled()
        s = ""

    def ua_selectByRectangle(self):
        if self.RectangleMapTool is not None:
            self.canvas.setMapTool(self.RectangleMapTool)

    def ua_selectByCoordinate(self):
        if self.PointMapTool is not None:
            self.canvas.setMapTool(self.PointMapTool)

    def ua_selectBy_Response(self, geometry, authid):
        D = self.dlg
        x = D.spinBox_coordinate_x.value()
        y = D.spinBox_coordinate_x.value()
        dx = D.doubleSpinBox_subset_size_x.value()
        dy = D.doubleSpinBox_subset_size_y.value()

        canvas_srs = osr.SpatialReference()
        print(authid)
        print(type(authid))
        wkt = osr.GetUserInputAsWKT(str(authid))
        six.print_('{}'.format(wkt))
        canvas_srs.ImportFromWkt(wkt)

        if type(geometry) is QgsRectangle:
            center = geometry.center()
            x = center.x()
            y = center.y()

            dx = geometry.xMaximum() - geometry.xMinimum()
            dy = geometry.yMaximum() - geometry.yMinimum()

        if type(geometry) is QgsPoint:
            x = geometry.x()
            y = geometry.y()

        if self.TS.srs is not None and not self.TS.srs.IsSame(canvas_srs):
            print('Convert canvas coordinates to time series SRS')
            g = ogr.Geometry(ogr.wkbPoint)
            g.AddPoint(x,y)
            g.AssignSpatialReference(canvas_srs)
            g.TransformTo(self.TS.srs)
            x = g.GetX()
            y = g.GetY()



        D.doubleSpinBox_subset_size_x.setValue(dx)
        D.doubleSpinBox_subset_size_y.setValue(dy)
        D.spinBox_coordinate_x.setValue(x)
        D.spinBox_coordinate_y.setValue(y)

    def qgs_handleMouseDown(self, pt, btn):

        print('MOUSE DOWN')
        print(pt)
        print(btn)



    def ua_TSprogress(self, v_min, v, v_max):
        assert v_min <= v and v <= v_max
        P = self.dlg.progressBar
        if P.minimum() != v_min or P.maximum() != v_max:
            P.setRange(v_min, v_max)
        P.setValue(v)

    def ua_datumAdded(self):
        cb_centerdate = self.dlg.cb_centerdate
        cb_centerdate.clear()
        if len(self.TS) > 0:
            if self.dlg.spinBox_coordinate_x.value() == 0.0 and \
               self.dlg.spinBox_coordinate_y.value() == 0.0:
                xmin, ymin, xmax, ymax = self.TS.getMaxExtent()
                self.dlg.spinBox_coordinate_x.setRange(xmin, xmax)
                self.dlg.spinBox_coordinate_y.setRange(ymin, ymax)
                self.dlg.spinBox_coordinate_x.setValue(0.5*(xmin+xmax))
                self.dlg.spinBox_coordinate_y.setValue(0.5*(ymin+ymax))
                s =""

                for date in self.TS.getDates():
                    cb_centerdate.addItem(date.astype('str'), date)
            s = ""
        self.dlg.tableView_TimeSeries.resizeColumnsToContents()

    def check_enabled(self):
        D = self.dlg
        hasTS = len(self.TS) > 0 or DEBUG
        hasTSV = len(self.VIEWS) > 0
        hasQGIS = qgis_available

        D.tabWidget_viewsettings.setEnabled(hasTS)
        D.btn_showPxCoordinate.setEnabled(hasTS and hasTSV)
        D.btn_selectByCoordinate.setEnabled(hasQGIS)
        D.btn_selectByRectangle.setEnabled(hasQGIS)




    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('EnMAPBox', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        self.icon_path = ':/plugins/SenseCarbon/icon.png'
        self.add_action(
            self.icon_path,
            text=self.tr(u'SenseCarbon Time Series Viewer'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&SenseCarbon Time Series Viewer'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def run(self):
        """Run method that performs all the real work"""

        #self.dlg.setWindowIcon(QIcon(self.icon_path))
        # show the GUI
        self.dlg.show()

        if DEBUG:
            pass

    def ua_showPxCoordinate_start(self):

        if len(self.TS) == 0:
            return

        D = self.dlg
        dx = D.doubleSpinBox_subset_size_x.value() * 0.5
        dy = D.doubleSpinBox_subset_size_y.value() * 0.5

        cx = D.spinBox_coordinate_x.value()
        cy = D.spinBox_coordinate_y.value()



        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(cx - dx, cy + dy)
        ring.AddPoint(cx + dx, cy + dy)
        ring.AddPoint(cx + dx, cy - dy)
        ring.AddPoint(cx - dx, cy - dy)

        bb = ogr.Geometry(ogr.wkbPolygon)
        bb.AddGeometry(ring)
        bbWkt = bb.ExportToWkt()
        srsWkt = None
        if self.TS.srs:
            bb.AssignSpatialReference(self.TS.srs)

            srsWkt = bb.GetSpatialReference().ExportToWkt()


        self.ImageChipBuffer.setBoundingBox(bb)

        D = self.dlg
        ratio = dx / dy
        size_px = D.spinBox_chipsize_max.value()
        if ratio > 1: #x is largest side
            size_x = size_px
            size_y = int(size_px / ratio)
        else: #y is largest
            size_y = size_px
            size_x = int(size_px * ratio)
        #size_x = D.spinBox_chipsize_x.value()
        #size_y = D.spinBox_chipsize_y.value()

        ScrollArea = D.scrollArea
        #S.setWidgetResizable(False)
        #remove widgets

        #get the dates of interes
        dates_of_interest = list()
        if D.rb_showEntireTS.isChecked():
            dates_of_interest = self.TS.getDates()
        elif D.rb_showSelectedDates.isChecked():
            dates_of_interest = self.getSelectedDates()
        elif D.rb_showTimeWindow.isChecked():
            TSD = D.cb_timeWindow_doi.itemData(D.cb_timeWindow_doi.currentIndex())
            s = ""
            allDates = self.TS.getDates()
            i_doi = allDates.index(TSD)
            i0 = max([0, i_doi-D.sb_ndates_before.value()])
            ie = min([i_doi + D.sb_ndates_after.value(), len(allDates)])
            dates_of_interest = allDates[i0:ie]


        if self.CPV is None:
            ScrollArea.setLayout(QHBoxLayout())
            self.CPV = ScrollArea.layout()
        else:
            diff = set(dates_of_interest)
            diff = diff.symmetric_difference(self.CHIPWIDGETS.keys())

        self.clearLayoutWidgets(self.CPV)
        self.CHIPWIDGETS.clear()

        if False:
            if len(diff) != 0:
                self.clearLayoutWidgets(self.CPV)
                self.CHIPWIDGETS.clear()
            else:
                for date, viewList in self.CHIPWIDGETS.items():
                    for imageLabel in viewList:
                        imageLabel.clear()

        #initialize image labels

        for i, date in enumerate(dates_of_interest):

            #LV = QVBoxLayout()
            #LV.setSizeConstraint(QLayout.SetNoConstraint)
            TSD = self.TS.data[date]
            textLabel = QLabel('{}'.format(date.astype(str)))
            textLabel.setToolTip(str(TSD))
            #textLabel.setMinimumWidth(size_x)
            #textLabel.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            self.CPV.addWidget(textLabel, 0, i)
            viewList = list()
            for j, view in enumerate(self.VIEWS):
                imageLabel = QLabel()
                imageLabel.setFrameShape(QFrame.StyledPanel)
                imageLabel.setMinimumSize(size_x, size_y)
                imageLabel.setMaximumSize(size_x+1, size_y+1)
                imageLabel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                viewList.append(imageLabel)
                self.CPV.addWidget(imageLabel,j+1, i)
            self.CHIPWIDGETS[date] = viewList

        #LH.addSpacerItem(Spacer(size_x, size_y))
        ScrollArea.show()

        #fill image labels
        missing_dates = set()
        missing_bands = set()
        for i, date in enumerate(self.TS.getDates()):
            required_bands = set()
            for j, view in enumerate(self.VIEWS):
                required_bands = required_bands.union(set(view.getBands()))

            missing = self.ImageChipBuffer.getMissingBands(date, required_bands)
            if len(missing) == 0:
                self.ua_showPxCoordinate_addChips(None, date=date)
            else:
                missing_dates.add(date)
                missing_bands = missing_bands.union(missing)

        if len(missing_dates) > 0:
            self.TS.getSpatialChips_parallel(bbWkt, srsWkt, dates=list(missing_dates), bands=list(missing_bands))

    def ua_showPxCoordinate_addChips(self, results, date=None):

        if results is not None:
            date, chipData = results
            self.ImageChipBuffer.addDataCube(date, chipData)

        viewList = self.CHIPWIDGETS.get(date)

        if viewList:
            for j, view in enumerate(self.VIEWS):

                imageLabel = viewList[j]
                imageLabel.clear()
                #imageLabel.setScaledContents(True)

                rgb = self.ImageChipBuffer.getChipRGB(date, view)
                rgb2 = rgb.transpose([1,2,0]).copy('C')
                qImg = qimage2ndarray.array2qimage(rgb2)
                #img = QImage(rgb2.data, nl, ns, QImage.Format_RGB888)

                pxMap = QPixmap.fromImage(qImg)
                pxMap = pxMap.scaled(imageLabel.size(), Qt.KeepAspectRatio)

                imageLabel.setPixmap(pxMap)
                #imageLabel.update()
                imageLabel.adjustSize()

                s = ""
                pass
            self.CPV.layout().update()
        s = ""

        pass

    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()

    def ua_addTSImages(self, files=None):
        if files is None:
            files = QFileDialog.getOpenFileNames()

        if files:
            M = self.dlg.tableView_TimeSeries.model()
            M.beginResetModel()
            self.TS.addFiles(files)
            M.endResetModel()

            nb = self.TS.nb
            if len(self.VIEWS) == 0 and nb > 0:
                if nb < 3:
                    bands = [1,1,1]
                else:
                    self.ua_addView([3,2,1])
                    if nb >= 5:
                        self.ua_addView([4,5,3])


        self.check_enabled()


    def ua_addTSMasks(self, files=None):

        if files is None:
            files = QFileDialog.getOpenFileNames()

        l = len(files)
        if l > 0:
            M = self.dlg.tableView_TimeSeries.model()
            M.beginResetModel()
            self.TS.addMasks(files, raise_errors=False)
            M.endResetModel()

        self.check_enabled()


    def setViewNames(self):
        for i, w in enumerate(self.VIEWS):
            w.setTitle('View {}'.format(i+1))
        self.check_enabled()



    def ua_addView(self, bands = [3,2,1]):
        import imagechipviewsettings_widget

        if len(self.TS.bandnames) > 0:

            w = imagechipviewsettings_widget.ImageChipViewSettings(self.TS, parent=self.dlg)
            w.setMaximumSize(w.size())
            #w.setMinimumSize(w.size())
            w.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.MinimumExpanding)
            w.setBands(bands)
            w.removeView.connect(lambda : self.ua_removeView(w))

            L = self.dlg.scrollArea_viewsWidget.layout()
            L.addWidget(w)
            self.dlg.scrollArea_views.show()
            self.VIEWS.append(w)
            self.setViewNames()
            self.check_enabled()

    def ua_removeTS(self):
        #remove views

        M = self.dlg.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.clear()
        M.endResetModel()
        self.check_enabled()

    def ua_removeTSD(self, dates):
        if dates is None:
            dates = self.getSelectedDates()

        M = self.dlg.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.removeDates(dates)
        M.endResetModel()
        self.check_enabled()


    def ua_removeView(self,w):
        self.VIEWS.remove(w)
        L = self.dlg.scrollArea_viewsWidget.layout()
        L.removeWidget(w)
        w.deleteLater()
        self.setViewNames()
    def getSelectedDates(self):
        TV = self.dlg.tableView_TimeSeries
        TVM = TV.model()

        return [TVM.getTimeSeriesDatumFromIndex(idx).getDate() for idx in TV.selectionModel().selectedRows()]



def showRGBData(data):
    from scipy.misc import toimage
    toimage(data).show()

def run_tests():

    if False:

        pathImg = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_BOA.vrt'
        pathMsk = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_Msk.vrt'
        TSD = TimeSeriesDatum(pathImg)
        TSD.setMask(pathMsk)

        print(TSD)

        c = [670949.883,-786288.771]

        w_x = w_y = 1000 #1km box
        srs = TSD.getSpatialReference()
        ring = ogr.Geometry(ogr.wkbLinearRing)
        import itertools
        for x,y in itertools.product([1000, -1000], repeat=2):
            ring.AddPoint(c[0]+x, c[1]+y)
        ring.AssignSpatialReference(srs)
        bb = ogr.Geometry(ogr.wkbPolygon)
        bb.AddGeometry(ring)
        bb.AssignSpatialReference(srs)




        def getChip3d_OLD(chips, r,g,b, range_r, range_g, range_b):

            nl, ns = chips[r].shape
            a3d = np.ndarray((3,nl,ns), dtype='float')

            rgb_idx = [r,g,b]
            ranges = [range_r, range_g, range_b]

            for i, rgb_i in enumerate(rgb_idx):
                range = ranges[i]
                data = chips[rgb_i].astype('float')
                data -= range[0]
                data *= 255./range[1]
                a3d[i,:] = data

            np.clip(a3d, 0, 255, out=a3d)

            return a3d.astype('uint8')

        app=QApplication([])
        main=PictureTest()
        main.show()
        range_r = [0,500]
        range_g = [0,500]
        range_b = [0,500]

        bands = [3,2,1]
        chipData = TSD.readSpatialChip(bb,bands=bands )

        main.addNumpy(getChip3d(chipData, bands, (range_r, range_g, range_b)))
        app.exec_()
        exit(0)

    if False:
        dirSrc = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
        filesImg = file_search(dirSrc, '2014*_BOA.vrt')
        filesMsk = file_search(dirSrc, '2014*_Msk.vrt')
        TS = TimeSeries(imageFiles=filesImg, maskFiles=filesMsk)

        print(TS)
        exit(0)


    if True:
        import PyQt4.Qt
        a = PyQt4.Qt.QApplication([])

        S = SenseCarbon_TSV(None)
        S.run()

        if True:
            dirSrc = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
            filesImg = file_search(dirSrc, '2014*_BOA.vrt')
            #filesMsk = file_search(dirSrc, '2014*_Msk.vrt')
            #S.ua_addTSImages(files=filesImg[0:1])
            #S.ua_addTSImages(files=filesImg)
            #S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        a.exec_()

    if False:
        import qgis.core

        # supply path to where is your qgis installed

        QgsApplication.setPrefixPath("/Applications/QGIS_2.12.app/Contents/MacOS/QGIS", True)

        # load providers
        QgsApplication.initQgis()

        a = QgsApplication([], True)

        S = SenseCarbon_TSV(a)
        S.run()

        if True:
            dirSrc = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
            filesImg = file_search(dirSrc, '2014*_BOA.vrt')
            filesMsk = file_search(dirSrc, '2014*_Msk.vrt')
            S.ua_addTSImages(files=filesImg)
            #S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        a.exec_()

    print('Tests done')
    exit(0)

if __name__ == '__main__':

    run_tests()

    print('Done')