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

# Import the code for the dialog
import os, sys, re, fnmatch, collections, copy, traceback
from qgis.core import *
#os.environ['PATH'] += os.pathsep + r'C:\OSGeo4W64\bin'

from osgeo import gdal, ogr, osr, gdal_array

DEBUG = True

try:
    from qgis.gui import *
    import qgis
    import qgis_add_ins
    qgis_available = True
except:
    qgis_available = False

import numpy as np
import six
import multiprocessing
from PyQt4.QtCore import *
from PyQt4.QtGui import *


#abbreviations
mkdir = lambda p: os.makedirs(p, exist_ok=True)
jp = os.path.join

def expand_python_path(path):
    if path not in sys.path:
        sys.path.append(path)



#I don't know why, but this is required to run this in QGIS
path = os.path.abspath(jp(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

#ensure that required non-standard modules are available
PLUGIN_DIR = os.path.dirname(__file__)
LIB_DIR = jp(PLUGIN_DIR, 'libs')
expand_python_path(PLUGIN_DIR)
expand_python_path(LIB_DIR)
try:
    import pyqtgraph
except:
    expand_python_path(jp(LIB_DIR,'pyqtgraph'))

import pyqtgraph as pg

import tsv_widgets
from sensecarbon_tsv_gui import *



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
    columnames = ['date','sensor','ns','nl','nb','image','mask']

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
                return self.TS.getTSDs()[i]
        return None

    def getTimeSeriesDatumFromIndex(self, index):

        if index.isValid():
            i = index.row()
            if i >= 0 and i < len(self.TS):
                date = self.TS.getTSDs()[i]
                return self.TS.data[date]

        return None



    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None


        value = None
        ic_name = self.columnames[index.column()]
        TSD = self.getTimeSeriesDatumFromIndex(index)
        keys = list(TSD.__dict__.keys())
        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if ic_name == 'name':
                value = os.path.basename(TSD.pathImg)
            elif ic_name == 'sensor':
                if role == Qt.ToolTipRole:
                    value = TSD.sensor.getDescription()
                else:
                    value = str(TSD.sensor)
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
            value = TSD

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

LUT_SensorNames = {(6,30.,30.): 'L7 ETM+' \
                  ,(7,30.,30.): 'L8 OLI' \
                  ,(4,10.,10.): 'S2 MSI 10m' \
                  ,(6,20.,20.): 'S2 MSI 20m' \
                  ,(3,30.,30.): 'S2 MSI 60m' \
                  ,(3,30.,30.): 'S2 MSI 60m' \
                  ,(5,5.,5.): 'RE 5m' \
                  }


class BandView(object):
    def __init__(self, TS, recommended_bands=None):
        assert type(TS) is TimeSeries
        self.representation = collections.OrderedDict()
        self.TS = TS
        self.TS.sensorAdded.connect(self.checkSensors)
        self.TS.changed.connect(self.checkSensors)

        self.Sensors = self.TS.Sensors

        import copy
        for sensor in self.Sensors:
            self.initSensor(copy.deepcopy(sensor), recommended_bands=recommended_bands)



    def checkSensors(self):
        represented_sensors = set(self.representation.keys())
        ts_sensors = set(self.TS.Sensors.keys())

        to_add = ts_sensors - represented_sensors
        to_remove = represented_sensors - ts_sensors
        for S in to_remove:
            self.representation[S].close()
            self.representation.pop(S)
        for S in to_add:
            self.initSensor(S)


    def initSensor(self, sensor, recommended_bands=None):
        """

        :param sensor:
        :param recommended_bands:
        :return:
        """
        assert type(sensor) is SensorConfiguration
        if sensor not in self.representation.keys():
            #self.bandMappings[sensor] = ((0, 0, 5000), (1, 0, 5000), (2, 0, 5000))
            #x = imagechipviewsettings_widget.ImageChipViewSettings(sensor)
            #x = tsv_widgets.BandViewSettings(sensor)
            x = tsv_widgets.ImageChipViewSettings(sensor)

            if recommended_bands is not None:
                assert min(recommended_bands) > 0
                if max(recommended_bands) < sensor.nb:
                    x.setBands(recommended_bands)
            x.create()
            self.representation[sensor] = x


    def getSensorStats(self, sensor, bands):
        """

        :param sensor:
        :param bands:
        :return:
        """
        assert type(sensor) is SensorConfiguration
        dsRef = gdal.Open(self.Sensors[sensor][0])
        return [dsRef.GetRasterBand(b).ComputeRasterMinMax() for b in bands]


    def getRanges(self, sensor):
        return self.getWidget(sensor).getRGBSettings()[1]

    def getBands(self, sensor):
        return self.getWidget(sensor).getRGBSettings()[0]


    def getRGBSettings(self, sensor):
        return self.getWidget(sensor).getRGBSettings()

    def getWidget(self, sensor):
        assert type(sensor) is SensorConfiguration
        return self.representation[sensor]



    def useMaskValues(self):

        #todo:
        return False


class SensorConfiguration(object):
    """
    Describes a Sensor Configuration
    """

    def __init__(self,nb, px_size_x,px_size_y, band_names=None, wavelengths=None, sensor_name=None):

        assert nb >= 1

        self.TS = None
        self.nb = nb
        self.px_size_x = float(abs(px_size_x))
        self.px_size_y = float(abs(px_size_y))

        assert self.px_size_x > 0
        assert self.px_size_y > 0

        if band_names is not None:
            assert len(band_names) == nb
        else:
            band_names = ['Band {}'.format(b+1) for b in range(nb)]

        self.band_names = band_names

        if wavelengths is not None:
            assert len(wavelengths) == nb

        self.wavelengths = wavelengths

        if sensor_name is None:
            id = (self.nb, self.px_size_x, self.px_size_y)
            if id in LUT_SensorNames.keys():
                sensor_name = LUT_SensorNames[id]
            else:
                sensor_name = '{} b x {} m'.format(self.nb, self.px_size_x)


        self.sensor_name = sensor_name

        self.hashvalue = hash(','.join(self.band_names))

    def __eq__(self, other):
        return self.nb == other.nb and self.px_size_x == other.px_size_x and self.px_size_y == other.px_size_y

    def __hash__(self):
        return self.hashvalue

    def __repr__(self):
        return self.sensor_name

    def getDescription(self):
        info = []
        info.append(self.sensor_name)
        info.append('{} Bands'.format(self.nb))
        info.append('Band\tName\tWavelength')
        for b in range(self.nb):
            if self.wavelengths:
                wl = str(self.wavelengths[b])
            else:
                wl = 'unknown'
            info.append('{}\t{}\t{}'.format(b+1, self.band_names[b],wl))

        return '\n'.join(info)



class ImageChipLabel(QLabel):
    def __init__(self, parent=None, iface=None, TSD=None, bands=None):
        super(ImageChipLabel, self).__init__(parent)
        self.TSD = TSD
        self.bn = os.path.basename(self.TSD.pathImg)
        self.iface=iface
        self.bands=bands
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        tt = ['Date: {}'.format(TSD.date) \
             ,'Name: {}'.format(self.bn) \
             ,'RGB:  {}'.format(','.join([str(b) for b in bands]))]

        self.setToolTip(list2str(tt))


    def contextMenuEvent(self, event):
        menu = QMenu()
        #add general options
        action = menu.addAction('Copy to clipboard')
        action.triggered.connect(lambda : QApplication.clipboard().setPixmap(self.pixmap()))

        #add QGIS specific options
        if self.iface:
            action = menu.addAction('Add {} to QGIS layers'.format(self.bn))
            action.triggered.connect(lambda : qgis_add_ins.add_QgsRasterLayer(self.iface, self.TSD.pathImg, self.bands))

        menu.exec_(event.globalPos())



class TimeSeries(QObject):
    datumAdded = pyqtSignal(name='datumAdded')

    #fire when a new sensor configuration is added
    sensorAdded = pyqtSignal(object, name='sensorAdded')


    changed = pyqtSignal()
    progress = pyqtSignal(int,int,int, name='progress')
    chipLoaded = pyqtSignal(object, name='chiploaded')
    closed = pyqtSignal()
    error = pyqtSignal(object)

    def __init__(self, imageFiles=None, maskFiles=None):
        QObject.__init__(self)

        #define signals

        #fire when a new TSD is added


        self.data = collections.OrderedDict()

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


    def getSRS(self):
        if len(self.data) == 0:
            return 0
        else:
            TSD = self.data[self.getTSDs()[0]]
            return TSD.getSpatialReference()

    def getWKT(self):
        srs = self.getSRS()
        return srs.ExportToWkt()

    def getSceneCenter(self, srs=None):

        if srs is None:
            srs = self.getSRS()

        bbs = list()
        for S, TSDs in self.Sensors.items():
            x = []
            y = []
            for TSD in TSDs:
                bb = TSD.getBoundingBox(srs)
                x.extend([c[0] for c in bb])
                y.extend([c[1] for c in bb])

        return None
        pass

    def getMaxExtent(self, srs=None):

        x = []
        y = []

        if srs is None:
            srs = self.getSRS()

        for TSD in self.data.values():
            bb = TSD.getBoundingBox(srs)
            x.extend([c[0] for c in bb])
            y.extend([c[1] for c in bb])

        return (min(x), min(y), max(x), max(y))

    def getObservationDates(self):
        return [tsd.getDate() for tsd in self.data.keys()]

    def getTSDs(self, date_of_interest=None):
        if date_of_interest:
            tsds = [tsd for tsd in self.data.keys() if tsd.getDate() == date_of_interest]
        else:
            tsds = list(self.data.keys())
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
        self.data.clear()
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

        try:
            sensorAdded = False
            TSD = TimeSeriesDatum(pathImg, pathMsk=pathMsk)
            existingSensors = list(self.Sensors.keys())
            if TSD.sensor not in existingSensors:
                self.Sensors[TSD.sensor] = list()
                sensorAdded = True
            else:
                TSD.sensor = existingSensors[existingSensors.index(TSD.sensor)]

            if TSD in self.data.keys():
                six.print_('Time series datum already added: {}'.format(str(TSD)), file=sys.stderr)
            else:
                self.Sensors[TSD.sensor].append(TSD)
                self.data[TSD] = TSD

            if sensorAdded:
                self.sensorAdded.emit(TSD.sensor)

            if not _quiet:
                self._sortTimeSeriesData()
                self.changed.emit()
                self.datumAdded.emit()
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2)
            six.print_('Unable to add {}'.format(file), file=sys.stderr)
            pass



    def addFiles(self, files):
        assert isinstance(files, list)
        l = len(files)
        assert l > 0

        self.progress.emit(0,0,l)
        for i, file in enumerate(files):
            self.addFile(file, _quiet=True)
            self.progress.emit(0,i+1,l)

        self._sortTimeSeriesData()
        self.progress.emit(0,0,1)
        self.datumAdded.emit()
        self.changed.emit()



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
        return '\n'.join(info)

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


def getBoundingBoxPolygon(points, srs=None):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for point in points:
        ring.AddPoint(point[0], point[1])
    bb = ogr.Geometry(ogr.wkbPolygon)
    bb.AddGeometry(ring)
    if srs:
        bb.AssignSpatialReference(srs)
    return bb



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

        self.wavelength = None
        domains = dsImg.GetMetadataDomainList()
        if domains:
            for domain in domains:
                md = dsImg.GetMetadata_Dict(domain)
                if 'wavelength' in md.keys():
                    wl = md['wavelength']
                    wl = re.split('[;,{}]', wl)
                    wl = [float(w) for w in wl]
                    assert len(wl) == self.nb
                    self.wavelength = wl
                    break

        self.sensor = SensorConfiguration(self.nb, self.gt[1], self.gt[5], self.bandnames, self.wavelength)


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
            assert type(srs) is osr.SpatialReference
            my_srs = self.getSpatialReference()
            if not my_srs.IsSame(srs):
                #todo: consider srs differences
                trans = osr.CoordinateTransformation(my_srs, srs)
                ext = trans.TransformPoints(ext)
                ext = [(e[0], e[1]) for e in ext]

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
        return hash((self.date,self.sensor.sensor_name))


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

class VerticalLabel(QLabel):
    def __init__(self, text):
        super(self.__class__, self).__init__()
        self.text = text

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.black)
        painter.translate(20, 100)
        painter.rotate(-90)
        if self.text:
            painter.drawText(0, 0, self.text)
        painter.end()

    def minimumSizeHint(self):
        size = QLabel.minimumSizeHint(self)
        return QSize(size.height(), size.width())

    def sizeHint(self):
        size = QLabel.sizeHint(self)
        return QSize(size.height(), size.width())

class ImageChipBuffer(object):


    def __init__(self):
        self.data = dict()
        self.BBox = None
        self.SRS = None
        pass


    def hasDataCube(self, TSD):
        return TSD in self.data.keys()

    def getMissingBands(self, TSD, bands):

        missing = set(bands)
        if TSD in self.data.keys():
            missing = missing - set(self.data[TSD].keys())
        return missing

    def addDataCube(self, TSD, chipData):

        assert self.BBox is not None, 'Please initialize the bounding box first.'
        assert isinstance(chipData, dict)

        if TSD not in self.data.keys():
            self.data[TSD] = dict()
        self.data[TSD].update(chipData)

    def getDataCube(self, TSD):
        return self.data.get(TSD)

    def getChipArray(self, TSD, band_view, mode='rgb'):
        assert mode in ['rgb', 'bgr']
        bands = band_view.getBands(TSD.sensor)
        band_ranges = band_view.getRanges(TSD.sensor)
        nb = len(bands)
        assert nb == 3 and nb == len(band_ranges)
        assert TSD in self.data.keys(), 'Time Series Datum {} is not in buffer'.format(TSD.getDate())
        chipData = self.data[TSD]
        for b in bands:
            assert b in chipData.keys()



        nl, ns = chipData[bands[0]].shape

        dtype= 'uint8'
        array_data = np.ndarray((nl,ns, nb), dtype=dtype)

        if mode == 'rgb':
            ch_dst = [0,1,2]
        elif mode == 'bgr':
            # r -> dst channel 2
            # g -> dst channel 1
            # b -> dst channel 0
            ch_dst = [2,1,0]
        for i, i_dst in enumerate(ch_dst):

            offset = band_ranges[i][0]
            scale = 255./band_ranges[i][1]

            res = pg.rescaleData(chipData[bands[i]], scale, offset, dtype='float')
            np.clip(res, 0, 255, out=res)
            array_data[:,:,i_dst] = res

        return array_data


    def getChipRGB(self, TSD, band_view):
        bands = band_view.getBands(TSD.sensor)
        band_ranges = band_view.getRanges(TSD.sensor)
        assert len(bands) == 3 and len(bands) == len(band_ranges)
        assert TSD in self.data.keys(), 'Time Series Datum {} is not in buffer'.format(TSD.getDate())
        chipData = self.data[TSD]
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

        if band_view.useMaskValues():
            rgb = band_view.getMaskColor()
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


list2str = lambda ll : '\n'.join([str(l) for l in ll])

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


        #if isinstance(iface, QgsApplication):
        #self.iface = iface

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

        #init on empty time series
        self.TS = None
        self.init_TimeSeries()

        self.BAND_VIEWS = list()
        self.ImageChipBuffer = ImageChipBuffer()
        self.CHIPWIDGETS = collections.OrderedDict()

        self.ValidatorPxX = QIntValidator(0,99999)
        self.ValidatorPxY = QIntValidator(0,99999)
        D.btn_showPxCoordinate.clicked.connect(lambda: self.ua_showPxCoordinate_start())
        D.btn_selectByCoordinate.clicked.connect(self.ua_selectByCoordinate)
        D.btn_selectByRectangle.clicked.connect(self.ua_selectByRectangle)
        D.btn_addBandView.clicked.connect(lambda :self.ua_addBandView())

        D.btn_addTSImages.clicked.connect(lambda :self.ua_addTSImages())
        D.btn_addTSMasks.clicked.connect(lambda :self.ua_addTSMasks())
        D.btn_loadTSFile.clicked.connect(self.ua_loadTSFile)
        D.btn_saveTSFile.clicked.connect(self.ua_saveTSFile)
        D.btn_addTSExample.clicked.connect(self.ua_loadExampleTS)

        D.actionAdd_Images.triggered.connect(lambda :self.ua_addTSImages())
        D.actionAdd_Masks.triggered.connect(lambda :self.ua_addTSMasks())
        D.actionLoad_Time_Series.triggered.connect(self.ua_loadTSFile)
        D.actionSave_Time_Series.triggered.connect(self.ua_saveTSFile)
        D.actionLoad_Example_Time_Series.triggered.connect(self.ua_loadExampleTS)
        D.actionAbout.triggered.connect( \
            lambda: QMessageBox.about(self.dlg, 'SenseCarbon TimeSeriesViewer', 'A viewer to visualize raster time series data'))

        D.btn_removeTSD.clicked.connect(lambda : self.ua_removeTSD(None))
        D.btn_removeTS.clicked.connect(self.ua_clear_TS)


        D.spinBox_ncpu.setRange(0, multiprocessing.cpu_count())




        # Declare instance attributes
        self.actions = []
        #self.menu = self.tr(u'&EnMAP-Box')

        self.RectangleMapTool = None
        self.PointMapTool = None
        self.canvas_srs = osr.SpatialReference()

        if self.iface:
            self.canvas = self.iface.mapCanvas()
            self.menu = self.tr(u'&SenseCarbon TSV')
            self.toolbar = self.iface.addToolBar(u'SenseCarbon TSV')
            self.toolbar.setObjectName(u'SenseCarbon TSV')

            self.RectangleMapTool = qgis_add_ins.RectangleMapTool(self.canvas)
            self.RectangleMapTool.rectangleDrawed.connect(self.ua_selectBy_Response)
            self.PointMapTool = qgis_add_ins.PointMapTool(self.canvas)
            self.PointMapTool.coordinateSelected.connect(self.ua_selectBy_Response)
            #self.RectangleMapTool.connect(self.ua_selectByRectangle_Done)

        self.ICP = self.dlg.scrollArea_imageChip_content.layout()
        self.dlg.scrollArea_bandViews_content.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.BVP = self.dlg.scrollArea_bandViews_content.layout()

        self.check_enabled()
        s = ""

    def init_TimeSeries(self, TS=None):

        if TS is None:
            TS = TimeSeries()
        assert type(TS) is TimeSeries

        if self.TS is not None:
            disconnect_signal(self.TS.datumAdded)
            disconnect_signal(self.TS.progress)
            disconnect_signal(self.TS.chipLoaded)

        self.TS = TS
        self.TS.datumAdded.connect(self.ua_datumAdded)
        self.TS.progress.connect(self.ua_TSprogress)
        self.TS.chipLoaded.connect(self.ua_showPxCoordinate_addChips)

        TSM = TimeSeriesTableModel(self.TS)
        D = self.dlg
        D.tableView_TimeSeries.setModel(TSM)
        D.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        D.cb_doi.setModel(TSM)
        D.cb_doi.setModelColumn(0)
        D.cb_doi.currentIndexChanged.connect(self.scrollToDate)


    def ua_loadTSFile(self, path=None):
        if path is None or path is False:
            path = QFileDialog.getOpenFileName(self.dlg, 'Open Time Series file', '')

        if os.path.exists(path):


            M = self.dlg.tableView_TimeSeries.model()
            M.beginResetModel()
            self.ua_clear_TS()
            self.TS.loadFromFile(path)
            M.endResetModel()

            self.refreshBandViews()

        self.check_enabled()

    def ua_saveTSFile(self):
        path = QFileDialog.getSaveFileName(self.dlg, caption='Save Time Series file')
        if path is not None:
            self.TS.saveToFile(path)


    def ua_loadExampleTS(self):
        import sensecarbon_tsv
        path_example = file_search(os.path.dirname(sensecarbon_tsv.__file__), 'testdata.txt', recursive=True)
        if path_example is None or len(path_example) == 0:
            QMessageBox.information(self.dlg, 'File not found', 'testdata.txt - this file describes an exemplary time series.')
        else:
            self.ua_loadTSFile(path=path_example[0])


    def ua_selectByRectangle(self):
        if self.RectangleMapTool is not None:
            self.canvas.setMapTool(self.RectangleMapTool)

    def ua_selectByCoordinate(self):
        if self.PointMapTool is not None:
            self.canvas.setMapTool(self.PointMapTool)

    def setCanvasSRS(self,srs):
        if type(srs) is osr.SpatialReference:
            self.canvas_srs = srs
        else:
            self.canvas_srs.ImportFromWkt(srs)

        self.dlg.tb_bb_srs.setPlainText(self.canvas_srs.ExportToProj4())

    def ua_selectBy_Response(self, geometry, srs_wkt):
        D = self.dlg
        x = D.spinBox_coordinate_x.value()
        y = D.spinBox_coordinate_x.value()
        dx = D.doubleSpinBox_subset_size_x.value()
        dy = D.doubleSpinBox_subset_size_y.value()

        self.setCanvasSRS(osr.GetUserInputAsWKT(str(srs_wkt)))


        if type(geometry) is QgsRectangle:
            center = geometry.center()
            x = center.x()
            y = center.y()

            dx = geometry.xMaximum() - geometry.xMinimum()
            dy = geometry.yMaximum() - geometry.yMinimum()

        if type(geometry) is QgsPoint:
            x = geometry.x()
            y = geometry.y()

        """
        ref_srs = self.TS.getSRS()
        if ref_srs is not None and not ref_srs.IsSame(canvas_srs):
            print('Convert canvas coordinates to time series SRS')
            g = ogr.Geometry(ogr.wkbPoint)
            g.AddPoint(x,y)
            g.AssignSpatialReference(canvas_srs)
            g.TransformTo(ref_srs)
            x = g.GetX()
            y = g.GetY()
        """


        D.doubleSpinBox_subset_size_x.setValue(dx)
        D.doubleSpinBox_subset_size_y.setValue(dy)
        D.spinBox_coordinate_x.setValue(x)
        D.spinBox_coordinate_y.setValue(y)

    def qgs_handleMouseDown(self, pt, btn):
        pass



    def ua_TSprogress(self, v_min, v, v_max):
        assert v_min <= v and v <= v_max
        if v_min < v_max:
            P = self.dlg.progressBar
            if P.minimum() != v_min or P.maximum() != v_max:
                P.setRange(v_min, v_max)
            else:
                s = ""

            P.setValue(v)

    def ua_datumAdded(self):

        if len(self.TS) > 0:
            self.setCanvasSRS(self.TS.getSRS())
            if self.dlg.spinBox_coordinate_x.value() == 0.0 and \
               self.dlg.spinBox_coordinate_y.value() == 0.0:
                xmin, ymin, xmax, ymax = self.TS.getMaxExtent(srs=self.canvas_srs)
                self.dlg.spinBox_coordinate_x.setRange(xmin, xmax)
                self.dlg.spinBox_coordinate_y.setRange(ymin, ymax)
                #x, y = self.TS.getSceneCenter()
                self.dlg.spinBox_coordinate_x.setValue(0.5*(xmin+xmax))
                self.dlg.spinBox_coordinate_y.setValue(0.5*(ymin+ymax))
                s = ""
        self.dlg.cb_doi.setCurrentIndex(int(len(self.TS) / 2))
        self.dlg.tableView_TimeSeries.resizeColumnsToContents()

    def check_enabled(self):
        D = self.dlg
        hasTS = len(self.TS) > 0 or DEBUG
        hasTSV = len(self.BAND_VIEWS) > 0
        hasQGIS = qgis_available

        #D.tabWidget_viewsettings.setEnabled(hasTS)
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
        status_tip="SenseCarbon Time Series Viewer - a tool to visualize a time series of remote sensing imagery",
        whats_this="Open SenseCarbon Time Series Viewer",
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


    def ua_addTSD_to_QGIS(self, TSD, bands):

        s = ""

        pass


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



    def scrollToDate(self, date_of_interest):
        QApplication.processEvents()
        HBar = self.dlg.scrollArea_imageChips.horizontalScrollBar()
        TSDs = list(self.CHIPWIDGETS.keys())
        if len(TSDs) == 0:
            return

        #get date INDEX that is closest to requested date
        if type(date_of_interest) is str:
            date_of_interest = np.datetime64(date_of_interest)


        if type(date_of_interest) is np.datetime64:
            i_doi = TSDs.index(sorted(TSDs, key=lambda TSD: abs(date_of_interest - TSD.getDate()))[0])
        else:
            i_doi = date_of_interest

        step = int(float(HBar.maximum()) / (len(TSDs)+1))
        HBar.setSingleStep(step)
        HBar.setPageStep(step*5)
        HBar.setValue(i_doi * step)


    def ua_showPxCoordinate_start(self):

        if len(self.TS) == 0:
            return

        D = self.dlg
        dx = D.doubleSpinBox_subset_size_x.value() * 0.5
        dy = D.doubleSpinBox_subset_size_y.value() * 0.5

        cx = D.spinBox_coordinate_x.value()
        cy = D.spinBox_coordinate_y.value()

        pts = [(cx - dx, cy + dy), \
               (cx + dx, cy + dy), \
               (cx + dx, cy - dy), \
               (cx - dx, cy - dy)]

        bb = getBoundingBoxPolygon(pts, srs=self.canvas_srs)
        bbWkt = bb.ExportToWkt()
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

        #get the dates of interes
        dates_of_interest = list()
        doiTSD = D.cb_doi.itemData(D.cb_doi.currentIndex())
        if doiTSD is None:
            idx = int(len(self.TS)/2)
            doiTSD = D.cb_doi.itemData(idx)
            D.cb_doi.setCurrentIndex(idx)
        centerDate = doiTSD.getDate()
        allDates = self.TS.getObservationDates()
        i_doi = allDates.index(centerDate)

        if D.rb_showEntireTS.isChecked():
            dates_of_interest = allDates
        elif D.rb_showTimeWindow.isChecked():
            i0 = max([0, i_doi-D.sb_ndates_before.value()])
            ie = min([i_doi + D.sb_ndates_after.value(), len(allDates)-1])
            dates_of_interest = allDates[i0:ie+1]


        diff = set(dates_of_interest)
        diff = diff.symmetric_difference(self.CHIPWIDGETS.keys())

        self.clearLayoutWidgets(self.ICP)
        self.CHIPWIDGETS.clear()



        #initialize image labels

        cnt_chips = 0

        TSDs_of_interest = list()

        for date in dates_of_interest:

            #LV = QVBoxLayout()
            #LV.setSizeConstraint(QLayout.SetNoConstraint)

            for TSD in self.TS.getTSDs(date_of_interest=date):
                TSDs_of_interest.append(TSD)
                info_label_text = '{}\n{}'.format(TSD.date, TSD.sensor.sensor_name)
                textLabel = QLabel(info_label_text)
                tt = [TSD.date,TSD.pathImg, TSD.pathMsk]
                textLabel.setToolTip(list2str(tt))
                self.ICP.addWidget(textLabel, 0, cnt_chips)
                viewList = list()
                j = 1
                for view in self.BAND_VIEWS:
                    bands = view.getBands(TSD.sensor)
                    #imageLabel = QLabel()
                    #imv = pg.GraphicsView()
                    #imv = QGraphicsView(self.dlg.scrollArea_imageChip_content)
                    #imv = MyGraphicsView(self.dlg.scrollArea_imageChip_content, iface=self.iface, path=TSD.pathImg, bands=bands)
                    #imv = pg.ImageView(view=None)
                    imgLabel = ImageChipLabel(iface=self.iface, TSD=TSD, bands=bands)

                    imgLabel.setMinimumSize(size_x, size_y)
                    imgLabel.setMaximumSize(size_x, size_y)


                    viewList.append(imgLabel)
                    self.ICP.addWidget(imgLabel, j, cnt_chips)
                    j += 1

                textLabel = QLabel(info_label_text)
                textLabel.setToolTip(str(TSD))
                self.ICP.addWidget(textLabel, j, cnt_chips)

                self.CHIPWIDGETS[TSD] = viewList

                cnt_chips += 1

        self.dlg.scrollArea_imageChip_content.update()

        self.scrollToDate(centerDate)

        s = ""
        #ScrollArea.show()
        #ScrollArea.horizontalScrollBar().setValue()



        #fill image labels
        required_bands = dict()
        for j, view in enumerate(self.BAND_VIEWS):
                for S in view.Sensors.keys():
                    bands = set()
                    bands.update(view.getBands(S))
                    if len(bands) != 3:
                        s = ""
                    assert len(bands) == 3
                    if S not in required_bands.keys():
                        required_bands[S] = set()
                    required_bands[S] = required_bands[S].union(bands)

        missing = set()
        for TSD in TSDs_of_interest:
            missing_bands = self.ImageChipBuffer.getMissingBands(TSD, required_bands[TSD.sensor])
            if len(missing_bands) == 0:
                self.ua_showPxCoordinate_addChips(None, TSD=TSD)
            else:
                missing.add((TSD, tuple(missing_bands)))


        missing =list(missing)
        if len(missing) > 0:
            missing = sorted(missing, key=lambda d: abs(centerDate - d[0].getDate()))

            self.TS.getSpatialChips_parallel(bbWkt, srsWkt, TSD_band_list=missing)




    def ua_showPxCoordinate_addChips(self, results, TSD=None):

        if results is not None:
            TSD, chipData = results
            self.ImageChipBuffer.addDataCube(TSD, chipData)

        if TSD not in self.CHIPWIDGETS.keys():
            six.print_('TSD {} does not exist in CHIPBUFFER'.format(TSD), file=sys.stderr)
        else:
            for imgChipLabel, bandView in zip(self.CHIPWIDGETS[TSD], self.BAND_VIEWS):
                #imgView.clear()
                #imageLabel.setScaledContents(True)

                #rgb = self.ImageChipBuffer.getChipRGB(TSD, bandView)
                array = self.ImageChipBuffer.getChipArray(TSD, bandView, mode = 'bgr')
                qimg = pg.makeQImage(array, copy=True, transpose=False)

                #rgb2 = rgb.transpose([1,2,0]).copy('C')
                #qImg = qimage2ndarray.array2qimage(rgb2)
                #img = QImage(rgb2.data, nl, ns, QImage.Format_RGB888)

                pxMap = QPixmap.fromImage(qimg).scaled(imgChipLabel.size(), Qt.KeepAspectRatio)
                imgChipLabel.setPixmap(pxMap)
                imgChipLabel.update()
                #imgView.setPixmap(pxMap)
                #imageLabel.update()
                #imgView.adjustSize()
                #pxmap = QPixmap.fromImage(qimg)
                #

                """
                pxmapitem = QGraphicsPixmapItem(pxmap)
                if imgChipLabel.scene() is None:
                    imgChipLabel.setScene(QGraphicsScene())
                else:
                    imgChipLabel.scene().clear()

                scene = imgChipLabel.scene()
                scene.addItem(pxmapitem)

                imgChipLabel.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
                """

                pass
            self.ICP.layout().update()
            self.dlg.scrollArea_imageChip_content.update()
            s = ""

        pass

    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def ua_addTSImages(self, files=None):
        if files is None:
            files = QFileDialog.getOpenFileNames()

        if files:
            M = self.dlg.tableView_TimeSeries.model()
            M.beginResetModel()
            self.TS.addFiles(files)
            M.endResetModel()
            self.refreshBandViews()

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



    def ua_addBandView(self, band_recommendation = [3, 2, 1]):
        self.BAND_VIEWS.append(BandView(self.TS, recommended_bands=band_recommendation))
        self.refreshBandViews()


    def refreshBandViews(self):

        if len(self.BAND_VIEWS) == 0 and len(self.TS) > 0:
            self.ua_addBandView(band_recommendation=[3, 2, 1])
            self.ua_addBandView(band_recommendation=[4, 5, 3])


        self.clearLayoutWidgets(self.BVP)

        for i, BV in enumerate(self.BAND_VIEWS):
            W = QWidget()
            hl = QHBoxLayout()
            textLabel = VerticalLabel('View {}'.format(i+1))
            textLabel = QLabel('View {}'.format(i+1))
            textLabel.setToolTip('')
            textLabel.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            hl.addWidget(textLabel)

            for S in self.TS.Sensors.keys():
                w = BV.getWidget(S)

                w.setMaximumSize(w.size())
                #w.setMinimumSize(w.size())
                w.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.MinimumExpanding)
                #w.setBands(band_recommendation)
                hl.addWidget(w)
                s = ""

            hl.addItem(QSpacerItem(20,20,QSizePolicy.Expanding,QSizePolicy.Minimum))
            W.setLayout(hl)
            self.BVP.addWidget(W)
        self.check_enabled()



    def ua_removeBandView(self, w):
        self.BAND_VIEWS.remove(w)
        L = self.dlg.scrollArea_viewsWidget.layout()
        L.removeWidget(w)
        w.deleteLater()
        self.setViewNames()

    def ua_clear_TS(self):
        #remove views

        M = self.dlg.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.clear()
        M.endResetModel()
        self.check_enabled()

    def ua_removeTSD(self, TSDs=None):
        if TSDs is None:
            TSDs = self.getSelectedTSDs()
        assert isinstance(TSDs,list)

        M = self.dlg.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.removeDates(TSDs)
        M.endResetModel()
        self.check_enabled()



    def getSelectedTSDs(self):
        TV = self.dlg.tableView_TimeSeries
        TVM = TV.model()
        return [TVM.getTimeSeriesDatumFromIndex(idx) for idx in TV.selectionModel().selectedRows()]


def disconnect_signal(signal):
    while True:
        try:
            signal.disconnect()
        except TypeError:
            break


def showRGBData(data):
    from scipy.misc import toimage
    toimage(data).show()

def run_tests():

    if False:

        pathImg = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_BOA.vrt'
        pathMsk = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted\2014-07-26_LC82270652014207LGN00_Msk.vrt'

        if False:
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

        app  = QApplication([])
        main = PictureTest()
        main.show()

        range_r = [0,500]
        range_g = [0,500]
        range_b = [0,500]

        bands = [3,2,1]
        #chipData = TSD.readSpatialChip(bb,bands=bands )

        #main.addNumpy(getChip3d(chipData, bands, (range_r, range_g, range_b)))
        app.exec_()
        exit(0)

    if False:
        dirSrcLS = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
        filesImgLS = file_search(dirSrcLS, '2014*_BOA.vrt')
        filesMsk = file_search(dirSrcLS, '2014*_Msk.vrt')
        TS = TimeSeries(imageFiles=filesImgLS, maskFiles=filesMsk)

        print(TS)
        exit(0)


    if True:
        import PyQt4.Qt

        app=PyQt4.Qt.QApplication([])
        S = SenseCarbon_TSV(None)
        S.run()

        if True:
            dirSrcLS = r'\\141.20.140.107\NAS_Processing\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
            dirSrcRE = r'\\141.20.140.91\SAN_RSDBrazil\RapidEye\3A_VRTs'
            filesImgLS = file_search(dirSrcLS, '20*_BOA.vrt')
            filesImgRE = file_search(dirSrcRE, '*.vrt', recursive=True)
            #filesMsk = file_search(dirSrc, '2014*_Msk.vrt')
            S.ua_addTSImages(files=filesImgLS[0:2])
            S.ua_addTSImages(files=filesImgRE[0:2])
            #S.ua_addTSImages(files=filesImgLS)
            #S.ua_addTSImages(files=filesImgRE)
            #S.ua_loadExampleTS()


            #S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        app.exec_()

    if False:
        import qgis.core

        # supply path to where is your qgis installed

        #QgsApplication.setPrefixPath("/Applications/QGIS_2.12.app/Contents/MacOS/QGIS", True)

        # load providers
        QgsApplication.initQgis()

        a = QgsApplication([], True)

        S = SenseCarbon_TSV(a)
        S.run()

        if True:
            dirSrcLS = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\00_VRTs\02_Cutted'
            filesImgLS = file_search(dirSrcLS, '2014*_BOA.vrt')
            filesMsk = file_search(dirSrcLS, '2014*_Msk.vrt')
            S.ua_addTSImages(files=filesImgLS)
            S.ua_addTSMasks(files=filesMsk)

        #S.ua_addView(bands=[4,5,3])

        a.exec_()

    print('Tests done')
    exit(0)


if __name__ == '__main__':
    run_tests()
    print('Done')