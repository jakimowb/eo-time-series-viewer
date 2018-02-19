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
import os, sys, pickle
import multiprocessing

import datetime
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
import numpy as np
from timeseriesviewer.utils import SpatialPoint, SpatialExtent, geo2px, px2geo
from osgeo import gdal, gdal_array, osr

DEBUG = False

def isOutOfImage(ds, px):
    """
    Evaluates if a pixel is inside and image or onot
    :param ds: gdal.Dataset
    :param px: QPoint
    :return: True | False
    """
    if px.x() < 0 or px.x() >= ds.RasterXSize:
        return True
    if px.y() < 0 or px.y() >= ds.RasterYSize:
        return True
    return False



class PixelLoaderTask(object):
    """
    An object to store the results of an loading from a single raster source.
    """
    def __init__(self, source, geometries, bandIndices=None, **kwargs):
        """

        :param jobId: jobId number as given by the calling PixelLoader
        :param processId: processId, as managed by the calling PixelLoader
        :param geometry: SpatialPoint that describes the pixels to be loaded
        :param source: file path to raster image.
        :param kwargs: additional stuff returned, e.g. to identify somethin
        """


        assert isinstance(geometries, list)
        for geometry in geometries:
            assert type(geometry) in [SpatialExtent, SpatialPoint]

        assert os.path.isfile(source)


        #assert isinstance(source, str) or isinstance(source, unicode)
        self.sourcePath = source
        self.geometries = geometries
        self.bandIndices = bandIndices

        #for internal use only
        self._jobId = None
        self._processId = None
        self._done = False

        #for returned data
        self.resCrsWkt = None
        self.resGeoTransformation = None
        self.resProfiles = None
        self.resNoDataValues = None
        self.exception = None
        self.info = None

        #other, free keywords
        for k in kwargs.keys():
            assert type(k) in [str, unicode]
            assert not k.startswith('_')
            if not k in self.__dict__.keys():
                self.__dict__[k] = kwargs[k]



    def imageCrs(self):
        return QgsCoordinateReferenceSystem(self.resCrsWkt)

    def depr_imagePixelIndices(self):
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
        if self.resGeoTransformation is None:
            return None
        p1 = px2geo(QPoint(0, 0), self.resGeoTransformation)
        p2 = px2geo(QPoint(1, 1), self.resGeoTransformation)

        xRes = abs(p2.x() - p1.x())
        yRes = abs(p2.y() - p1.y())
        return QSize(xRes, yRes)

    def success(self):
        """
        Returns True if the PixelLoaderTask has been finished well without exceptions.
        :return: True | False
        """
        """
        :return:
        """
        result = self._done and self.exception is None
        return result

    def __repr__(self):
        info = ['PixelLoaderTask:']
        if not self._done:
            info.append('not started...')
        else:
            if self.bandIndices:
                info.append('\tBandIndices {}:{}'.format(len(self.bandIndices), self.bandIndices))
            if self.resProfiles:
                info.append('\tProfileData: {}'.format(len(self.resProfiles)))
                for i, p in enumerate(self.resProfiles):
                    g = self.geometries[i]
                    d = self.resProfiles[i]
                    if d in [INFO_OUT_OF_IMAGE, NO_DATA]:
                        info.append('\t{}: {}:{}'.format(i + 1, g, d))
                    else:
                        vData = d[0]
                        vStd = d[1]
                        info.append('\t{}: {}:{} : {}'.format(i+1, g, vData.shape, vData))

        return '\n'.join(info)

LOADING_FINISHED = 'finished'
LOADING_CANCELED = 'canceled'
INFO_OUT_OF_IMAGE = 'out of image'
NO_DATA = 'no data values'

#def loadProfiles(pathsAndBandIndices, jobid, poolWorker, geom, q, cancelEvent, **kwargs):


def loadProfiles(taskList, queue, cancelEvent, **kwargs):

    for task in taskList:
        assert isinstance(task, PixelLoaderTask)
        if cancelEvent.is_set():
            return LOADING_CANCELED

        result = doLoaderTask(task)

        assert isinstance(result, PixelLoaderTask)

        queue.put(result)

    return LOADING_FINISHED

def transformPoint2Px(trans, pt, gt):
    x, y, _ = trans.TransformPoint(pt.x(), pt.y())
    return geo2px(QgsPoint(x, y), gt)

def doLoaderTask(task):

    assert isinstance(task, PixelLoaderTask)

    result = task

    ds = gdal.Open(task.sourcePath, gdal.GA_ReadOnly)
    nb, ns, nl = ds.RasterCount, ds.RasterXSize, ds.RasterYSize



    bandIndices = list(range(nb)) if task.bandIndices is None else list(task.bandIndices)

    gt = ds.GetGeoTransform()
    result.resGeoTransformation = gt
    result.resCrsWkt = ds.GetProjection()
    crsSrc = osr.SpatialReference(result.resCrsWkt)


    #convert Geometries into pixel indices to be extracted
    PX_SUBSETS = []



    for geom in task.geometries:

        crsRequest = osr.SpatialReference()
        crsRequest.ImportFromWkt(geom.crs().toWkt())
        trans = osr.CoordinateTransformation(crsRequest, crsSrc)

        if isinstance(geom, QgsPoint):
            ptUL = ptLR = QgsPoint(geom)
        elif isinstance(geom, QgsRectangle):
            TYPE = 'RECTANGLE'
            ptUL = QgsPoint(geom.xMinimum(), geom.yMaximum())
            ptLR = QgsPoint(geom.xMaximum(), geom.yMinimum())
        else:
            PX_SUBSETS.append(INFO_OUT_OF_IMAGE)

        pxUL = transformPoint2Px(trans, ptUL, gt)
        pxLR = transformPoint2Px(trans, ptLR, gt)

        bUL = isOutOfImage(ds, pxUL)
        bLR = isOutOfImage(ds, pxLR)

        if all([bUL, bLR]):
            PX_SUBSETS.append(INFO_OUT_OF_IMAGE)
            continue


        def shiftIntoImageBounds(pt, xMax, yMax):
            assert isinstance(pt, QPoint)
            if pt.x() < 0:
                pt.setX(0)
            elif pt.x() > xMax:
                pt.setX(xMax)
            if pt.y() < 0:
                pt.setY(0)
            elif pt.y() > yMax:
                pt.setY(yMax)


        shiftIntoImageBounds(pxUL, ds.RasterXSize, ds.RasterYSize)
        shiftIntoImageBounds(pxLR, ds.RasterXSize, ds.RasterYSize)

        if pxUL == pxLR:
            size_x = size_y = 1
        else:
            size_x = abs(pxUL.x() - pxLR.x())
            size_y = abs(pxUL.y() - pxLR.y())

        if size_x < 1: size_x = 1
        if size_y < 1: size_y = 1

        PX_SUBSETS.append((pxUL, pxUL, size_x, size_y))

    PROFILE_DATA = []

    if bandIndices == range(ds.RasterCount):
        #we have to extract all bands
        #in this case we use gdal.Dataset.ReadAsArray()
        noData = ds.GetRasterBand(1).GetNoDataValue()
        for px in PX_SUBSETS:
            if px == INFO_OUT_OF_IMAGE:
                PROFILE_DATA.append(INFO_OUT_OF_IMAGE)
                continue

            pxUL, pxUL, size_x, size_y = px

            bandData = ds.ReadAsArray(pxUL.x(), pxUL.y(), size_x, size_y).reshape((nb, size_x*size_y))
            if noData:
                isValid = np.ones(bandData.shape[1], dtype=np.bool)
                for b in range(bandData.shape[0]):
                    isValid *= bandData[b,:] != ds.GetRasterBand(b+1).GetNoDataValue()
                bandData = bandData[:, np.where(isValid)[0]]
            PROFILE_DATA.append(bandData)
    else:
        # access band values band-by-band
        # in this case we use gdal.Band.ReadAsArray()
        # and need to iterate over the requested band indices

        #save the returned band values for each geometry in a separate list
        #empty list == invalid geometry
        for i in range(len(PX_SUBSETS)):
            if PX_SUBSETS[i] == INFO_OUT_OF_IMAGE:
                PROFILE_DATA.append(INFO_OUT_OF_IMAGE)
            else:
                PROFILE_DATA.append([])


        for bandIndex in bandIndices:
            band = ds.GetRasterBand(bandIndex+1)
            noData = band.GetNoDataValue()
            assert isinstance(band, gdal.Band)

            for i, px in enumerate(PX_SUBSETS):
                if px == INFO_OUT_OF_IMAGE:
                    continue
                pxUL, pxUL, size_x, size_y = px
                bandData = band.ReadAsArray(pxUL.x(), pxUL.y(), size_x, size_y).flatten()
                if noData:
                    bandData = bandData[np.where(bandData != noData)[0]]
                PROFILE_DATA[i].append(bandData)

        for i in range(len(PX_SUBSETS)):
            pd = PROFILE_DATA[i]
            if len(pd) == 0:
                PROFILE_DATA[i] = INFO_OUT_OF_IMAGE
            else:
                #PROFILE_DATA[i] = np.dstack(pd).transpose(2,0,1)
                PROFILE_DATA[i] = np.vstack(pd)



    #finally, ensure that there is on 2D array only
    for i in range(len(PROFILE_DATA)):
        d = PROFILE_DATA[i]
        if d != INFO_OUT_OF_IMAGE:
            assert d.ndim == 2
            b, yx = d.shape
            assert b == len(bandIndices)

            _, _, size_x, size_y = PX_SUBSETS[i]
            if yx > 0:
                d = d.reshape((b, yx))
                vMean = d.mean(axis=1)
                vStd = d.std(axis=1)

                assert len(vMean) == len(bandIndices)
                assert len(vStd) == len(bandIndices)
            else:
                vMean = vStd = NO_DATA
            PROFILE_DATA[i] = (vMean, vStd)
            s = ""
    task.resProfiles = PROFILE_DATA
    task._done = True
    return task




class PixelLoader(QObject):
    """
    Loads pixel from raster images
    """

    sigPixelLoaded = pyqtSignal(int, int, PixelLoaderTask)
    sigLoadingStarted = pyqtSignal(list)
    sigLoadingFinished = pyqtSignal(np.timedelta64)
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
        self.mLoadingStartTime = np.datetime64('now','ms')
        self.queueChecker = QTimer()
        self.queueChecker.setInterval(3000)
        self.queueChecker.timeout.connect(self.checkQueue)

        self.pool = None

        self.MGR = multiprocessing.Manager()
        self.mAsyncResults = []
        self.resultQueue = self.MGR.Queue()
        self.cancelEvent = self.MGR.Event()


    @QtCore.pyqtSlot(PixelLoaderTask)
    def onPixelLoaded(self, data):
        assert isinstance(data, PixelLoaderTask)
        if data._jobId != self.jobid:
            #do not return results from previous jobs...
            #print('got thread results from {} but need {}...'.format(jobid, self.jobid))
            return
        else:
            self.filesList.remove(data.sourcePath)
            self.sigPixelLoaded.emit(self.nMax - len(self.filesList), self.nMax, data)

            if len(self.filesList) == 0:
                dt = np.datetime64('now', 'ms') - self.mLoadingStartTime
                self.sigLoadingFinished.emit(dt)


    def setNumberOfProcesses(self, nProcesses):
        assert nProcesses >= 1
        self.nProcesses = nProcesses

    def startLoading(self, tasks):

        assert isinstance(tasks, list)

        paths = []
        for t in tasks:
            assert isinstance(t, PixelLoaderTask)
            paths.append(t.sourcePath)

        self.mLoadingStartTime = np.datetime64('now', 'ms')
        self.jobid += 1
        self.sigLoadingStarted.emit(paths[:])
        self.filesList.extend(paths)

        l = len(paths)
        self.nMax = l
        self.nFailed = 0

        #split tasks into workpackages to be solve per parallel process
        workPackages = list()
        i = 0
        _tasks = tasks[:]
        while(len(_tasks)) > 0:
            if len(workPackages) <= i:
                workPackages.append([])
            task = _tasks.pop(0)
            task._jobId = self.jobid
            workPackages[i].append(task)
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
            #args = (workPackage, self.jobid, i, theGeometries, self.resultQueue, self.cancelEvent)
            # kwds = {'profileID':profileID}

            #set workpackage / thread-specific internal metdata
            for t in workPackage:
                assert isinstance(t, PixelLoaderTask)
                t.__processId = i


            args = (workPackage, self.resultQueue, self.cancelEvent)
            kwds = {}

            if DEBUG:
                self.checkQueue(loadProfiles(*args, **kwds))
            else:
                r = self.pool.apply_async(loadProfiles, args=args, callback=self.checkQueue, **kwds)
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
                pass

        elif self.cancelEvent.is_set():
            self.queueChecker.stop()
            self.sigLoadingCanceled.emit()



if __name__ == '__main__':

    from timeseriesviewer.utils import initQgisApplication
    qgsApp = initQgisApplication()
    from PyQt4.QtGui import *
    gb = QGroupBox()
    gb.setTitle('Sandbox')
    DEBUG = True
    PL = PixelLoader()
    PL.setNumberOfProcesses(1)

    import example.Images
    from timeseriesviewer import file_search
    dir = os.path.dirname(example.Images.__file__)
    #files = file_search(dir, '*.tif')
    files = [example.Images.Img_2014_05_07_LC82270652014127LGN00_BOA]
    files.append(example.Images.Img_2014_04_29_LE72270652014119CUB00_BOA)
    files.extend(file_search(dir, 're_*.tif'))
    for f in files: print(f)
    ext = SpatialExtent.fromRasterSource(files[0])

    from qgis.core import QgsPoint
    x,y = ext.center()

    geoms = [#SpatialPoint(ext.crs(), 681151.214,-752388.476), #nodata in Img_2014_04_29_LE72270652014119CUB00_BOA
             SpatialExtent(ext.crs(),x+10000,y,x+12000, y+70 ), #out of image
             SpatialExtent(ext.crs(),x,y,x+10000, y+70 ),
             SpatialPoint(ext.crs(), x,y),
             SpatialPoint(ext.crs(), x+250, y+70)]

    from multiprocessing import Pool

    def onPxLoaded(*args):
        n, nmax, task = args
        assert isinstance(task, PixelLoaderTask)
        print(task)

    PL = PixelLoader()
    def onDummy(*args):
        print(('dummy',args))

    def onTimer(*args):
        print(('TIMER',PL))
        pass
    PL.sigPixelLoaded.connect(onPxLoaded)
    PL.sigLoadingFinished.connect(lambda: onDummy('finished'))
    PL.sigLoadingCanceled.connect(lambda: onDummy('canceled'))
    PL.sigLoadingStarted.connect(lambda: onDummy('started'))
    PL.sigPixelLoaded.connect(lambda : onDummy('px loaded'))

    tasks = []
    for i, f in enumerate(files):
        kwargs = {'myid':'myID{}'.format(i)}
        tasks.append(PixelLoaderTask(f, geoms, bandIndices=None, **kwargs))

    PL.startLoading(tasks)

    #QTimer.singleShot(2000, lambda : PL.cancelLoading())

    qgsApp.exec_()
    s = ""