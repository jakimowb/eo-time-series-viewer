# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
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
# noinspection PyPep8Naming
from __future__ import absolute_import
import os, pickle
import sys
import datetime
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
import numpy as np
from timeseriesviewer.utils import SpatialPoint, SpatialExtent, geo2px, px2geo
from osgeo import gdal, gdal_array, osr
import multiprocessing as mp
#mp.freeze_support()
from timeseriesviewer.sandbox import initQgisEnvironment
DEBUG = False

def isOutOfImage(ds, px):
    if px.x() < 0 or px.x() >= ds.RasterXSize:
        return True
    if px.y() < 0 or px.y() >= ds.RasterYSize:
        return True
    return False

class PixelLoaderResult(object):
    """
    An object to store the results of an loading from a single raster source.
    """
    def __init__(self, jobId, processId, geometry, source):
        assert jobId is not None
        assert processId is not None
        assert type(geometry) in [SpatialExtent, SpatialPoint]
        assert isinstance(source, str) or isinstance(source, unicode)
        self.jobId = jobId
        self.processId = processId
        self.geometry = geometry
        self.pxUL = self.pxSubsetSize = None
        self.srcCrsWkt = None
        self.geoTransformation = None
        self.source = source
        self.pxData = None
        self.pxBandIndices = None
        self.noDataValue = None
        self.exception = None
        self.info = None

    def setValues(self, values, bandIndices = None, noDataValue=None):
        self.pxData = values
        self.noDataValue = noDataValue
        if bandIndices is None:
            self.pxBandIndices = np.arange(self.pxData.shape[0])
        else:
            self.pxBandIndices = bandIndices

    def imageCrs(self):
        return QgsCoordinateReferenceSystem(self.srcCrsWkt)

    def imagePixelIndices(self):
        """
        Returns the image pixel indices related to the extracted value subset
        :return: (numpy array y, numpy array x)
        """
        if self.pxUL is None:
            return None

        pxIdxX = np.arange(0, self.pxSubsetSize.width()) + self.pxUL.x()
        pxIdxY = np.arange(0, self.pxSubsetSize.height()) + self.pxUL.y()
        return (pxIdxY,pxIdxX)

    def pixelResolution(self):
        """
        Returns the spatial pixel resolution
        :return: QSize
        """
        if self.geoTransformation is None:
            return None
        p1 = px2geo(QPoint(0, 0), self.geoTransformation)
        p2 = px2geo(QPoint(1, 1), self.geoTransformation)

        xRes = abs(p2.x() - p1.x())
        yRes = abs(p2.y() - p1.y())
        return QSize(xRes, yRes)

    def success(self):
        return self.pxData is not None and self.exception is None

LOADING_FINISHED = 'finished'
LOADING_CANCELED = 'canceled'
INFO_OUT_OF_IMAGE = 'out of image'

def loadProfiles(pathsAndBandIndices, jobid, poolWorker, geom, q, cancelEvent):
    assert type(geom) in [SpatialPoint, SpatialExtent]

    #this routine might run in a parallel thread.
    crsRequest = osr.SpatialReference()
    crsRequest.ImportFromWkt(geom.crs().toWkt())

    ptUL = ptLR = None
    TYPE = None
    if isinstance(geom, QgsPoint):
        ptUL = QgsPoint(geom)
        TYPE = 'PIXEL'
    elif isinstance(geom, QgsRectangle):
        TYPE = 'RECTANGLE'
        ptUL = QgsPoint(geom.xMinimum(), geom.yMaximum())
        ptLR = QgsPoint(geom.xMaximum(), geom.yMinimum())
    else:
        raise NotImplementedError()

    for i, t in enumerate(pathsAndBandIndices):
        path, bandIndices = t

        if cancelEvent.is_set():
            return LOADING_CANCELED

        R = PixelLoaderResult(jobid, poolWorker, geom, path)

        try:
            ds = gdal.Open(path, gdal.GA_ReadOnly)
            gt = ds.GetGeoTransform()
            R.srcCrsWkt = ds.GetProjection()
            R.geoTransformation = gt
            crsSrc = osr.SpatialReference(R.srcCrsWkt)
            #print('SRC {} WKT:{}'.format(i, R.srcCrsWkt))
            trans = osr.CoordinateTransformation(crsRequest, crsSrc)

            def transformPoint2Px(trans, pt, gt):
                x,y,_ = trans.TransformPoint(pt.x(),pt.y())
                return geo2px(QgsPoint(x,y), gt)


            if TYPE == 'PIXEL':
                px = transformPoint2Px(trans, ptUL, gt)
                if isOutOfImage(ds, px):
                    R.info = INFO_OUT_OF_IMAGE
                    q.put(R)
                    continue

                size_x = 1
                size_y = 1

            elif TYPE == 'RECTANGLE':
                px = transformPoint2Px(trans, ptUL, gt)
                px2 = transformPoint2Px(trans, ptLR, gt)

                #todo: cut to existing pixel coordinates
                #if px2.x() > 0: px.setX(max([0, px.x()]))

                if isOutOfImage(ds, px) or \
                   isOutOfImage(ds, px2):
                        R.info = INFO_OUT_OF_IMAGE
                        q.put(R)
                        continue

                size_x = px2.x() - px.x()
                size_y = px.y() - px2.y()

            R.pxUL = px
            R.pxSubsetSize = QSize(size_x, size_y)

            values = None
            noData = None
            if bandIndices is None:
                values = ds.ReadAsArray(px.x(), px.y(), size_x, size_y)
                noData = [ds.GetRasterBand(b + 1).GetNoDataValue() for b in range(ds.RasterCount)]
            else:
                bandIndices = sorted(list(set(bandIndices)))
                noData = []
                for j, b in enumerate(bandIndices):
                    band = ds.GetRasterBand(b+1)
                    bandData = band.ReadAsArray(px.x(), px.y(), size_x, size_y)
                    if values is None:
                        values = np.empty((len(bandIndices), size_y, size_x), dtype=bandData.dtype)

                    noData.append(band.GetNoDataValue())
                    values[j,:] = bandData

            assert values.ndim == 3

        except Exception as ex:
            R.exception = ex
            q.put(R)
            continue

        R.setValues(values, bandIndices=bandIndices, noDataValue=noData)

        q.put(R)
    return LOADING_FINISHED



class PixelLoader(QObject):
    """
    Loads pixel from raster images
    """

    sigPixelLoaded = pyqtSignal(int, int, PixelLoaderResult)
    sigLoadingStarted = pyqtSignal(list)
    sigLoadingFinished = pyqtSignal()
    sigLoadingCanceled = pyqtSignal()
    _sigStartThreadWorkers = pyqtSignal(str)
    _sigTerminateThreadWorkers = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)
        self.filesList = []
        self.jobid = -1
        self.nProcesses = 2
        self.nMax = 0
        self.nFailed = 0
        self.threadsAndWorkers = []

        self.queueChecker = QTimer()
        self.queueChecker.setInterval(3000)
        self.queueChecker.timeout.connect(self.checkQueue)

        self.pool = None
        self.MGR = mp.Manager()
        self.mAsyncResults = []
        self.resultQueue = self.MGR.Queue()
        self.cancelEvent = self.MGR.Event()


    @QtCore.pyqtSlot(PixelLoaderResult)
    def onPixelLoaded(self, data):
        assert isinstance(data, PixelLoaderResult)
        if data.jobId != self.jobid:
            #do not return results from previous jobs...
            #print('got thread results from {} but need {}...'.format(jobid, self.jobid))
            return
        else:
            self.filesList.remove(data.source)
            self.sigPixelLoaded.emit(self.nMax - len(self.filesList), self.nMax, data)

            if len(self.filesList) == 0:
                self.sigLoadingFinished.emit()


    def setNumberOfProcesses(self, nProcesses):
        assert nProcesses >= 1
        self.nProcesses = nProcesses

    def startLoading(self, paths, theGeometry, bandIndices=None):
        assert isinstance(paths, list)
        if bandIndices is not None:
            assert len(bandIndices) == len(paths)
        else:
            bandIndices = [None for _ in paths]

        assert type(theGeometry) in [SpatialPoint, SpatialExtent]

        self.jobid += 1
        self.sigLoadingStarted.emit(paths[:])
        self.filesList.extend(paths)

        l = len(paths)
        self.nMax = l
        self.nFailed = 0

        #split number of files into list
        _pathsAndIndices = zip(paths, bandIndices)
        workPackages = list()
        i = 0
        while(len(_pathsAndIndices)) > 0:
            if len(workPackages) <= i:
                workPackages.append([])
            workPackages[i].append(_pathsAndIndices.pop(0))
            i = i + 1 if i < self.nProcesses - 1 else 0

        from multiprocessing.pool import Pool

        if not DEBUG:
            if isinstance(self.pool, Pool):
                self.pool.terminate()
                self.pool = None

            self.pool = Pool(self.nProcesses)
            del self.mAsyncResults[:]
            self.queueChecker.start()

        #print('theGeometryWKT: '+theGeometry.crs().toWkt())
        for i, workPackage in enumerate(workPackages):
            args = (workPackage, self.jobid, i, theGeometry, self.resultQueue, self.cancelEvent)
            if DEBUG:
                self.checkQueue(loadProfiles(*args))
            else:
                r = self.pool.apply_async(loadProfiles, args=args, callback=self.checkQueue)
                self.mAsyncResults.append(r)

        if not DEBUG:
            self.pool.close()

    def cancelLoading(self):
        self.cancelEvent.set()


    def isReadyToLoad(self):
        return len(self.mAsyncResults) == 0 and self.pool is None

    def checkQueue(self, *args):

        while not self.resultQueue.empty():
            md = self.resultQueue.get()
            self.onPixelLoaded(md)

        if all([w.ready() for w in self.mAsyncResults]):
            #print('All done')


            self.queueChecker.stop()
            del self.mAsyncResults[:]
            self.pool = None
            if not self.cancelEvent.is_set():
                self.sigLoadingFinished.emit()
        elif self.cancelEvent.is_set():
            self.queueChecker.stop()
            self.sigLoadingCanceled.emit()



if __name__ == '__main__':

    from timeseriesviewer.sandbox import initQgisEnvironment
    qgsApp = initQgisEnvironment()
    from PyQt4.QtGui import *
    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfProcesses(1)

    import example.Images
    from timeseriesviewer import file_search
    dir = os.path.dirname(example.Images.__file__)
    #files = file_search(dir, '*.tif')
    files = [example.Images.Img_2014_05_07_LC82270652014127LGN00_BOA]
    files.extend(file_search(dir, 're_*.tif'))
    ext = SpatialExtent.fromRasterSource(files[0])
    pt = SpatialPoint(ext.crs(), ext.center())

    from multiprocessing import Pool

    def onPxLoaded(*args):
        n, nmax, plr = args
        assert isinstance(plr, PixelLoaderResult)

    PL = PixelLoader()
    def onDummy(*args):
        print(('dummy',args))
        pass

    def onTimer(*args):
        print(('TIMER',PL))
        pass
    PL.sigPixelLoaded.connect(onPxLoaded)
    PL.sigLoadingFinished.connect(lambda: onDummy('finished'))
    PL.sigLoadingCanceled.connect(lambda: onDummy('canceled'))
    PL.sigLoadingStarted.connect(lambda: onDummy('started'))
    PL.sigPixelLoaded.connect(lambda : onDummy('px loaded'))
    PL.startLoading(files, pt)

    QTimer.singleShot(2000, lambda : PL.cancelLoading())

    qgsApp.exec_()
    s = ""