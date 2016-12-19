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
import os, sys, re, fnmatch, collections, copy, traceback, six
from qgis.core import *
#os.environ['PATH'] += os.pathsep + r'C:\OSGeo4W64\bin'

from osgeo import gdal, ogr, osr, gdal_array

DEBUG = True
import qgis.analysis
try:
    from qgis.gui import *
    import qgis
    import qgis_add_ins
    qgis_available = True

    #import console.console_output
    #console.show_console()
    #sys.stdout = console.console_output.writeOut()
    #sys.stderr = console.console_output.writeOut()

except:
    print('Can not find QGIS instance')
    qgis_available = False

import numpy as np

import multiprocessing, site
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.uic.Compiler.qtproxies import QtGui, QtCore
import sys
import code
import codecs

#abbreviations
from timeseriesviewer import jp, mkdir, DIR_SITE_PACKAGES, file_search, dprint

site.addsitedir(DIR_SITE_PACKAGES)
from timeseriesviewer.ui import widgets
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument


#I don't know why, but this is required to run this in QGIS
#todo: still required?
path = os.path.abspath(jp(sys.exec_prefix, '../../bin/pythonw.exe'))
if os.path.exists(path):
    multiprocessing.set_executable(path)
    sys.argv = [ None ]

#ensure that required non-standard modules are available

import pyqtgraph as pg


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
                return self.TS.data[i]

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



class BandView(QObject):

    removeView = pyqtSignal(object)

    def __init__(self, TS, recommended_bands=None):
        super(BandView, self).__init__()
        assert type(TS) is TimeSeries
        self.representation = collections.OrderedDict()
        self.TS = TS
        self.TS.sensorAdded.connect(self.checkSensors)
        self.TS.changed.connect(self.checkSensors)

        self.Sensors = self.TS.Sensors

        import copy
        for sensor in self.Sensors:
            self.initSensor(copy.deepcopy(sensor))



    def checkSensors(self):
        represented_sensors = set(self.representation.keys())
        ts_sensors = set(self.TS.Sensors.keys())

        to_add = ts_sensors - represented_sensors
        to_remove = represented_sensors - ts_sensors
        for S in to_remove:
            self.representation[S].getWidget().close()
            self.representation.pop(S)
        for S in to_add:
            self.initSensor(S)


    def initSensor(self, sensor):
        """
        :param sensor:
        :return:
        """
        assert type(sensor) is SensorInstrument
        if sensor not in self.representation.keys():
            x = widgets.ImageChipViewSettings(sensor)
            self.representation[sensor] = x


    def getWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.representation[sensor]

class RenderJob(object):

    def __init__(self, TSD, renderer, destinationId=None):
        assert isinstance(TSD, TimeSeriesDatum)
        assert isinstance(renderer, QgsRasterRenderer)

        self.TSD = TSD
        self.renderer = renderer
        self.destinationId = destinationId

    def __eq__(self, other):
        if not isinstance(other, RenderJob):
            return False
        return self.TSD == other.TSD and \
               self.renderer == other.renderer and \
               self.destinationId == other.destinationId



class PixmapBuffer(QObject):
    sigProgress = pyqtSignal(int, int)
    sigPixmapCreated = pyqtSignal(RenderJob, QPixmap)

    def __init__(self):
        super(PixmapBuffer, self).__init__()

        self.extent = None
        self.crs = None
        self.size = None
        self.nWorkersMax = 1
        self.Workers = []
        self.PIXMAPS = dict()
        self.JOBS = []
        self.nTotalJobs = -1
        self.nJobsDone = -1

    def addWorker(self):
        w = Worker()
        w.setCrsTransformEnabled(True)
        w.sigPixmapCreated.connect(self.newPixmapCreated)
        if self.isValid():
            self.setWorkerProperties(w)
        self.Workers.append(w)

    def setWorkerProperties(self, worker):
        assert isinstance(worker, Worker)
        worker.setFixedSize(self.size)
        worker.setDestinationCrs(self.crs)
        worker.setExtent(self.extent)
        worker.setCenter(self.extent.center())

    def newPixmapCreated(self, renderJob, pixmap):
        self.JOBS.remove(renderJob)
        self.nJobsDone += 1
        self.sigPixmapCreated.emit(renderJob, pixmap)
        self.sigProgress.emit(self.nJobsDone, self.nTotalJobs)

    def isValid(self):
        return self.extent != None and self.crs != None and self.size != None

    def setExtent(self, extent, crs, maxPx):
        self.stopRendering()
        assert isinstance(extent, QgsRectangle)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        assert isinstance(maxPx, int)
        ratio = extent.width() / extent.height()
        if ratio < 1:  # x is largest side
            size = QSize(maxPx, int(maxPx / ratio))
        else:  # y is largest
            size = QSize(int(maxPx * ratio), maxPx)

        self.crs = crs
        self.size = size
        self.extent = extent
        for w in self.Workers:
            self.setWorkerProperties(w)
        return size

    def stopRendering(self):
        for w in self.Workers:
            w.stopRendering()
            w.clear()
        while len(self.JOBS) > 0:
            self.JOBS.pop(0)
        self.sigProgress.emit(0, 0)

    def loadSubsets(self, jobs):
        for j in jobs:
            assert isinstance(j, RenderJob)

        self.stopRendering()

        self.JOBS.extend(jobs)
        self.nTotalJobs = len(self.JOBS)
        self.nJobsDone = 0
        self.sigProgress.emit(0, self.nTotalJobs)

        if len(self.Workers) == 0:
            self.addWorker()

        #split jobs to number of workers
        i = 0
        chunkSize = int(len(self.JOBS) / len(self.Workers))
        assert chunkSize > 0
        for i in range(0, len(self.Workers), chunkSize):
            worker = self.Workers[i]
            j = min(i+chunkSize, len(self.JOBS))
            worker.startLayerRendering(self.JOBS[i:j])

class Worker(QgsMapCanvas):

    sigPixmapCreated = pyqtSignal(RenderJob, QPixmap)


    def __init__(self, *args, **kwds):
        super(Worker,self).__init__(*args, **kwds)
        self.reg = QgsMapLayerRegistry.instance()
        self.painter = QPainter()
        self.renderJobs = list()
        self.mapCanvasRefreshed.connect(self.createPixmap)

    def isBusy(self):
        return len(self.renderJobs) != 0

    def createPixmap(self, *args):
        if len(self.renderJobs) > 0:
            pixmap = QPixmap(self.size())
            self.painter.begin(pixmap)
            self.map().paint(self.painter)
            self.painter.end()
            assert not pixmap.isNull()
            job = self.renderJobs.pop(0)
            self.sigPixmapCreated.emit(job, pixmap)
            self.startSingleLayerRendering()

    def stopLayerRendering(self):
        self.stopRendering()
        del self.renderJobs[:]
        assert self.isBusy() is False

    def startLayerRendering(self, renderJobs):
        assert isinstance(renderJobs, list)
        self.renderJobs.extend(renderJobs)
        self.startSingleLayerRendering()



    def startSingleLayerRendering(self):

        if len(self.renderJobs) > 0:
            renderJob = self.renderJobs[0]
            assert isinstance(renderJob, RenderJob)
            #mapLayer = QgsRasterLayer(renderJob.TSD.pathImg)
            mapLayer = renderJob.TSD.lyrImg
            mapLayer.setRenderer(renderJob.renderer)
            dprint('QgsMapLayerRegistry count: {}'.format(self.reg.count()))
            self.reg.addMapLayer(mapLayer)

            lyrSet = [QgsMapCanvasLayer(mapLayer)]
            self.setLayerSet(lyrSet)

            #todo: add crosshair
            self.refreshAllLayers()


class ImageChipLabel(QLabel):

    clicked = pyqtSignal(object, object)


    def __init__(self, time_series_viewer, TSD, renderer):
        assert isinstance(time_series_viewer, TimeSeriesViewer)
        assert isinstance(TSD, TimeSeriesDatum)
        assert isinstance(renderer, QgsRasterRenderer)

        super(ImageChipLabel, self).__init__(time_series_viewer.ui)
        self.TSV = time_series_viewer
        self.TSD = TSD
        self.bn = os.path.basename(self.TSD.pathImg)

        self.renderer = renderer
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        tt = ['Date: {}'.format(TSD.date) \
             ,'Name: {}'.format(self.bn) \
             ]

        self.setToolTip(list2str(tt))

    def mouseReleaseEvent(self, event):
	    self.clicked.emit(self, event)



    def contextMenuEvent(self, event):
        menu = QMenu()
        #add general options

        action = menu.addAction('Copy to clipboard')
        action.triggered.connect(lambda : QApplication.clipboard().setPixmap(self.pixmap()))


        #add QGIS specific options
        if self.TSV.iface:
            action = menu.addAction('Add {} to QGIS layers'.format(self.bn))
            action.triggered.connect(lambda : qgis_add_ins.add_QgsRasterLayer(self.iface, self.TSD.pathImg, self.bands))

        menu.exec_(event.globalPos())





def getBoundingBoxPolygon(points, srs=None):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for point in points:
        ring.AddPoint(point[0], point[1])
    bb = ogr.Geometry(ogr.wkbPolygon)
    bb.AddGeometry(ring)
    if isinstance(srs, QgsCoordinateReferenceSystem):

        _crs = osr.SpatialReference()
        _crs.ImportFromWkt(srs.toWkt())
        bb.AssignSpatialReference(_crs)
    return bb






def getDS(ds):
    if type(ds) is not gdal.Dataset:
        ds = gdal.Open(ds)
    return ds



def getBandNames(lyr):
    assert isinstance(lyr, QgsRasterLayer)
    dp = lyr.dataProvider()
    assert isinstance(dp, QgsRasterDataProvider)
    if str(dp.name()) == 'gdal':
        s = ""
    else:
        return lyr

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
        super(VerticalLabel, self).__init__(text)
        self.update()
        self.updateGeometry()


    def paintEvent(self, ev):
        p = QPainter(self)
        p.rotate(-90)
        rgn = QRect(-self.height(), 0, self.height(), self.width())
        align = self.alignment()
        self.hint = p.drawText(rgn, align, self.text())
        p.end()

        self.setMaximumWidth(self.hint.height())
        self.setMinimumWidth(0)
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(self.hint.width())

    def sizeHint(self):
        if hasattr(self, 'hint'):
            return QSize(self.hint.height(), self.hint.width())
        else:
            return QSize(19, 50)


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
            self.clear()
            self.BBox = BBox
            self.SRS = SRS

    def __repr__(self):
        info = ['Chipbuffer']
        info.append('Bounding Box: {}'.format(self.bbBoxWkt))
        info.append('Chips: {}'.format(len(self.data)))
        return '\n'.join(info)


list2str = lambda ll : '\n'.join([str(l) for l in ll])




class TimeSeriesViewer:
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
        if isinstance(self.iface, qgis.gui.QgisInterface):
            import console
            console.show_console()


        # Create the dialog (after translation) and keep reference
        from timeseriesviewer.ui.widgets import TimeSeriesViewerUI
        self.ui = TimeSeriesViewerUI()
        D = self.ui

        #init empty time series
        self.TS = TimeSeries()
        self.hasInitialCenterPoint = False
        self.TS.datumAdded.connect(self.ua_datumAdded)
        self.TS.changed.connect(self.timeseriesChanged)
        self.TS.progress.connect(self.ua_TSprogress)

        #init TS model
        TSM = TimeSeriesTableModel(self.TS)
        D = self.ui
        D.tableView_TimeSeries.setModel(TSM)
        D.tableView_TimeSeries.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)

        self.BAND_VIEWS = list()
        self.ImageChipBuffer = ImageChipBuffer()
        self.PIXMAPS = PixmapBuffer()
        self.PIXMAPS.sigPixmapCreated.connect(self.showSubset)
        self.CHIPWIDGETS = collections.OrderedDict()

        self.ValidatorPxX = QIntValidator(0,99999)
        self.ValidatorPxY = QIntValidator(0,99999)
        D.btn_showPxCoordinate.clicked.connect(lambda: self.showSubsetsStart())
        D.btn_selectByCoordinate.clicked.connect(self.ua_selectByCoordinate)
        D.btn_selectByRectangle.clicked.connect(self.ua_selectByRectangle)
        D.btn_addBandView.clicked.connect(lambda :self.ua_addBandView())

        D.btn_addTSImages.clicked.connect(lambda :self.ua_addTSImages())
        D.btn_addTSMasks.clicked.connect(lambda :self.ua_addTSMasks())
        D.btn_loadTSFile.clicked.connect(self.ua_loadTSFile)
        D.btn_saveTSFile.clicked.connect(self.ua_saveTSFile)
        D.btn_addTSExample.clicked.connect(self.ua_loadExampleTS)
        D.btn_labeling_clear.clicked.connect(D.tb_labeling_text.clear)
        D.actionAdd_Images.triggered.connect(lambda :self.ua_addTSImages())
        D.actionAdd_Masks.triggered.connect(lambda :self.ua_addTSMasks())
        D.actionLoad_Time_Series.triggered.connect(self.ua_loadTSFile)
        D.actionSave_Time_Series.triggered.connect(self.ua_saveTSFile)
        D.actionLoad_Example_Time_Series.triggered.connect(self.ua_loadExampleTS)
        D.actionAbout.triggered.connect( \
            lambda: QMessageBox.about(self.ui, 'SenseCarbon TimeSeriesViewer', 'A viewer to visualize raster time series data'))

        D.btn_removeTSD.clicked.connect(lambda : self.ua_removeTSD(None))
        D.btn_removeTS.clicked.connect(self.ua_clear_TS)

        D.sliderDOI.sliderMoved.connect(self.setDOILabel)
        D.spinBox_ncpu.setRange(0, multiprocessing.cpu_count())


        self.RectangleMapTool = None
        self.PointMapTool = None
        self.canvasCrs = QgsCoordinateReferenceSystem()

        if self.iface:
            self.canvas = self.iface.mapCanvas()

            self.RectangleMapTool = qgis_add_ins.RectangleMapTool(self.canvas)
            self.RectangleMapTool.rectangleDrawed.connect(self.setSpatialSubset)
            self.PointMapTool = qgis_add_ins.PointMapTool(self.canvas)
            self.PointMapTool.coordinateSelected.connect(self.setSpatialSubset)

            #self.RectangleMapTool.connect(self.ua_selectByRectangle_Done)

        self.ICP = self.ui.scrollArea_imageChip_content.layout()
        self.ui.scrollArea_bandViews_content.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.BVP = self.ui.scrollArea_bandViews_content.layout()

        self.check_enabled()
        s = ""

    def setDOILabel(self, i):
        TSD = self.TS.data[i-1]
        self.ui.labelDOI.setText(str(TSD.date))
        s = ""

    @staticmethod
    def icon():
        return QIcon(':/plugins/SenseCarbon/icon.png')

    def icon(self):
        return TimeSeriesViewer.icon()

    def timeseriesChanged(self):
        D = self.ui
        D.sliderDOI.setMinimum(1)
        D.sliderDOI.setMaximum(len(self.TS.data))
        if len(self.TS.data)>0 and not self.hasInitialCenterPoint:
            extent = self.TS.getMaxExtent(self.canvasCrs)
            self.setSpatialSubset(extent.center(), self.canvasCrs)
            self.hasInitialCenterPoint = True
        if len(self.TS.data) == 0:
            self.hasInitialCenterPoint = False

    def ua_loadTSFile(self, path=None):
        if path is None or path is False:
            path = QFileDialog.getOpenFileName(self.ui, 'Open Time Series file', '')

        if os.path.exists(path):


            M = self.ui.tableView_TimeSeries.model()
            M.beginResetModel()
            self.ua_clear_TS()
            self.TS.loadFromFile(path)
            M.endResetModel()

            self.refreshBandViews()

        self.check_enabled()

    def ua_saveTSFile(self):
        path = QFileDialog.getSaveFileName(self.ui, caption='Save Time Series file')
        if path is not None:
            self.TS.saveToFile(path)


    def ua_loadExampleTS(self):
        from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
        if not os.path.exists(PATH_EXAMPLE_TIMESERIES):
            QMessageBox.information(self.ui, 'File not found', '{} - this file describes an exemplary time series.'.format(path_example))
        else:
            self.ua_loadTSFile(path=PATH_EXAMPLE_TIMESERIES)



    def ua_selectByRectangle(self):
        if self.RectangleMapTool is not None:
            self.canvas.setMapTool(self.RectangleMapTool)

    def ua_selectByCoordinate(self):
        if self.PointMapTool is not None:
            self.canvas.setMapTool(self.PointMapTool)

    def setCanvasSRS(self,srs):
        assert isinstance(srs, QgsCoordinateReferenceSystem)
        #self.canvas_srs = srs
        self.canvasCrs = srs
        self.ui.tb_bb_srs.setPlainText(self.canvasCrs.toWkt())

    def setSpatialSubset(self, geometry, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        assert isinstance(geometry, QgsRectangle) or isinstance(geometry, QgsPoint)

        D = self.ui
        x = D.spinBox_coordinate_x.value()
        y = D.spinBox_coordinate_x.value()
        dx = D.doubleSpinBox_subset_size_x.value()
        dy = D.doubleSpinBox_subset_size_y.value()

        self.setCanvasSRS(crs)


        if type(geometry) is QgsRectangle:
            center = geometry.center()
            x = center.x()
            y = center.y()

            dx = geometry.xMaximum() - geometry.xMinimum()
            dy = geometry.yMaximum() - geometry.yMinimum()

        if type(geometry) is QgsPoint:
            x = geometry.x()
            y = geometry.y()

        D.doubleSpinBox_subset_size_x.setValue(dx)
        D.doubleSpinBox_subset_size_y.setValue(dy)
        D.spinBox_coordinate_x.setValue(x)
        D.spinBox_coordinate_y.setValue(y)

        if D.cb_loadSubsetDirectly.isChecked():
            self.showSubsetsStart()

    def qgs_handleMouseDown(self, pt, btn):
        pass



    def ua_TSprogress(self, v_min, v, v_max):
        assert v_min <= v and v <= v_max
        if v_min < v_max:
            P = self.ui.progressBar
            if P.minimum() != v_min or P.maximum() != v_max:
                P.setRange(v_min, v_max)
            else:
                s = ""

            P.setValue(v)

    def ua_datumAdded(self, TSD):

        if len(self.TS) == 1:
            self.setCanvasSRS(TSD.lyrImg.crs())
            if self.ui.spinBox_coordinate_x.value() == 0.0 and \
               self.ui.spinBox_coordinate_y.value() == 0.0:
                bbox = self.TS.getMaxExtent(srs=self.canvas_srs)

                self.ui.spinBox_coordinate_x.setRange(bbox.xMinimum(), bbox.xMaximum())
                self.ui.spinBox_coordinate_y.setRange(bbox.yMinimum(), bbox.yMaximum())
                #x, y = self.TS.getSceneCenter()
                c = bbox.center()
                self.ui.spinBox_coordinate_x.setValue(c.x())
                self.ui.spinBox_coordinate_y.setValue(c.y())
                s = ""
        #self.dlg.sliderDOI

        self.ui.tableView_TimeSeries.resizeColumnsToContents()

    def check_enabled(self):
        D = self.ui
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





    def ua_addTSD_to_QGIS(self, TSD, bands):

        s = ""

        pass


    def unload(self):
        """Removes the plugin menu item and icon """
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.ui.show()



    def scrollToDate(self, date_of_interest):
        QApplication.processEvents()
        HBar = self.ui.scrollArea_imageChips.horizontalScrollBar()
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


    def showSubsetsStart(self):

        if len(self.TS) == 0:
            return

        D = self.ui
        easting = QgsVector(D.doubleSpinBox_subset_size_x.value(), 0.0)
        northing = QgsVector(0.0, D.doubleSpinBox_subset_size_y.value())

        Center = QgsPoint(D.spinBox_coordinate_x.value(), D.spinBox_coordinate_y.value())
        UL = Center - (easting * 0.5) + (northing * 0.5)
        LR = Center + (easting * 0.5) - (northing * 0.5)
        extent = QgsRectangle(UL,LR)
        maxPx = int(D.spinBoxMaxPixmapSize.value())
        pxSize = self.PIXMAPS.setExtent(extent, self.canvasCrs, maxPx)

        #get the dates of interes
        dates_of_interest = list()

        doiTSD = self.TS.data[int(D.sliderDOI.value())-1]
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
                info_label_text = '{}\n{}'.format(TSD.date, TSD.sensor.sensorName)
                textLabel = QLabel(info_label_text)
                tt = [TSD.date,TSD.pathImg, TSD.pathMsk]
                textLabel.setToolTip(list2str(tt))
                self.ICP.addWidget(textLabel, 0, cnt_chips)
                viewList = list()
                j = 1
                for view in self.BAND_VIEWS:
                    viewWidget = view.getWidget(TSD.sensor)
                    layerRenderer = viewWidget.layerRenderer()

                    #imageLabel = QLabel()
                    #imv = pg.GraphicsView()
                    #imv = QGraphicsView(self.dlg.scrollArea_imageChip_content)
                    #imv = MyGraphicsView(self.dlg.scrollArea_imageChip_content, iface=self.iface, path=TSD.pathImg, bands=bands)
                    #imv = pg.ImageView(view=None)
                    imgLabel = ImageChipLabel(self, TSD, layerRenderer)

                    imgLabel.setMinimumSize(pxSize)
                    imgLabel.setMaximumSize(pxSize)
                    imgLabel.clicked.connect(self.ua_collect_date)


                    viewList.append(imgLabel)
                    self.ICP.addWidget(imgLabel, j, cnt_chips)
                    j += 1

                textLabel = QLabel(info_label_text)
                textLabel.setToolTip(str(TSD))
                self.ICP.addWidget(textLabel, j, cnt_chips)

                self.CHIPWIDGETS[TSD] = viewList

                cnt_chips += 1

        self.ui.scrollArea_imageChip_content.update()

        self.scrollToDate(centerDate)

        #todo: start pixmap loading
        #define render jobs
        #(TSD, [renderers] in order of views)

        LUT_RENDERER = {}
        for view in self.BAND_VIEWS:
            for sensor in view.Sensors.keys():
                if sensor not in LUT_RENDERER.keys():
                    LUT_RENDERER[sensor] = []
                LUT_RENDERER[sensor].append(
                    view.getWidget(sensor).layerRenderer()
                )


        jobs = []
        for TSD in TSDs_of_interest:
            for i, r in enumerate(LUT_RENDERER[TSD.sensor]):
                jobs.append(RenderJob(TSD, r.clone(), destinationId=i))

        #oder jobs by distance to DOI
        jobs = sorted(jobs, key = lambda j: abs(j.TSD.date - doiTSD.date))

        #todo: recycling to save loading time
        self.PIXMAPS.loadSubsets(jobs)

    def showSubset(self, renderJob, pixmap):

        assert isinstance(renderJob, RenderJob)
        chipLabel = self.CHIPWIDGETS[renderJob.TSD][renderJob.destinationId]
        chipLabel.setPixmap(pixmap)
        chipLabel.setFixedSize(pixmap.size())
        chipLabel.update()
        s = ""

    def ua_collect_date(self, ICL, event):
        if self.ui.rb_labeling_activate.isChecked():
            txt = self.ui.tb_labeling_text.toPlainText()
            reg = re.compile('\d{4}-\d{2}-\d{2}', re.I | re.MULTILINE)
            dates = set([np.datetime64(m) for m in reg.findall(txt)])
            doi = ICL.TSD.getDate()

            if event.button() == Qt.LeftButton:
                dates.add(doi)
            elif event.button() == Qt.MiddleButton and doi in dates:
                dates.remove(doi)

            dates = sorted(list(dates))
            txt = ' '.join([d.astype(str) for d in dates])
            self.ui.tb_labeling_text.setText(txt)


    def clearLayoutWidgets(self, L):
        if L is not None:
            while L.count():
                w = L.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
                #if w is not None:
                #    w.widget().deleteLater()
        QApplication.processEvents()

    def ua_addTSImages(self, files=None):
        if files is None:
            files = QFileDialog.getOpenFileNames()

        if files:
            M = self.ui.tableView_TimeSeries.model()
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
            M = self.ui.tableView_TimeSeries.model()
            M.beginResetModel()
            self.TS.addMasks(files, raise_errors=False)
            M.endResetModel()

        self.check_enabled()



    def ua_addBandView(self):
        bandView = BandView(self.TS)
        #bandView.removeView.connect(self.ua_removeBandView)
        self.BAND_VIEWS.append(bandView)
        self.refreshBandViews()


    def refreshBandViews(self):
        if len(self.BAND_VIEWS) == 0 and len(self.TS) > 0:
            self.ua_addBandView() # add two bandviews by default
            self.ua_addBandView()

        self.clearLayoutWidgets(self.BVP)

        for i, BV in enumerate(self.BAND_VIEWS):
            W = QWidget()

            hl = QHBoxLayout()
            hl.setSpacing(2)
            hl.setMargin(0)


            textLabel = VerticalLabel('View {}'.format(i+1))
            #textLabel = QLabel('View {}'.format(i+1))
            textLabel.setToolTip('')
            textLabel.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            hl.addWidget(textLabel)

            for S in self.TS.Sensors.keys():
                w = BV.getWidget(S).ui
                if i > 0:
                    w.setTitle(None) #show sensor name only on top
                w.setMaximumSize(w.size())
                #w.setMinimumSize(w.size())
                w.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.MinimumExpanding)
                #w.setBands(band_recommendation)
                hl.addWidget(w)
                s = ""

            hl.addItem(QSpacerItem(1,1))
            W.setLayout(hl)
            self.BVP.addWidget(W)
        self.BVP.addItem(QSpacerItem(1, 1))
        self.check_enabled()



    def ua_removeBandView(self, w):
        self.BAND_VIEWS.remove(w)
        self.refreshBandViews()

    def ua_clear_TS(self):
        #remove views

        M = self.ui.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.clear()
        M.endResetModel()
        self.check_enabled()

    def ua_removeTSD(self, TSDs=None):
        if TSDs is None:
            TSDs = self.getSelectedTSDs()
        assert isinstance(TSDs,list)

        M = self.ui.tableView_TimeSeries.model()
        M.beginResetModel()
        self.TS.removeDates(TSDs)
        M.endResetModel()
        self.check_enabled()



    def getSelectedTSDs(self):
        TV = self.ui.tableView_TimeSeries
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
        S = TimeSeriesViewer(None)
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

        S = TimeSeriesViewer(a)
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