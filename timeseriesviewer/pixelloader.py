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

import os, sys
import pickle
import multiprocessing
from multiprocessing import Pool
import datetime
from qgis.gui import *
from qgis.core import *
from PyQt5.QtCore import *
import numpy as np
from timeseriesviewer.utils import SpatialPoint, SpatialExtent, geo2px, px2geo
from osgeo import gdal, gdal_array, osr

DEBUG = False


def dprint(msg):
    if DEBUG:
        print('PixelLoader: {}'.format(msg))

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

    @staticmethod
    def fromDump(byte_object):
        return pickle.loads(byte_object)

    def __init__(self, source, geometries, bandIndices=None, **kwargs):
        """

        :param jobId: jobId number as given by the calling PixelLoader
        :param processId: processId, as managed by the calling PixelLoader
        :param geometry: SpatialPoint that describes the pixels to be loaded
        :param source: file path to raster image.
        :param kwargs: additional stuff returned, e.g. to identify somethin
        """

        if not isinstance(geometries, list):
            geometries = [geometries]
        assert isinstance(geometries, list)
        for geometry in geometries:
            assert type(geometry) in [SpatialExtent, SpatialPoint]

        assert os.path.isfile(source)


        #assert isinstance(source, str) or isinstance(source, unicode)
        self.sourcePath = source
        self.geometries = geometries
        self.bandIndices = bandIndices

        #for internal use only
        self.mIsDone = False

        #for returned data
        self.resCrsWkt = None
        self.resGeoTransformation = None
        self.resProfiles = None
        self.resNoDataValues = None
        self.exception = None
        self.info = None

        #other, free keywords
        for k in kwargs.keys():
            assert isinstance(k, str)
            assert not k.startswith('_')
            if not k in self.__dict__.keys():
                self.__dict__[k] = kwargs[k]

    def toDump(self):
        return pickle.dumps(self)

    def validPixelValues(self, i):
        if not self.success():
            return False
        if i >= len(self.resProfiles):
            return False

        profileData = self.resProfiles[i]
        if profileData in [INFO_OUT_OF_IMAGE, INFO_NO_DATA]:
            return False
        else:
            return True


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
        result = self.mIsDone and self.exception is None
        return result

    def __repr__(self):
        info = ['PixelLoaderTask:']
        if not self.mIsDone:
            info.append('not started...')
        else:
            if self.bandIndices:
                info.append('\tBandIndices {}:{}'.format(len(self.bandIndices), self.bandIndices))
            if self.resProfiles:
                info.append('\tProfileData: {}'.format(len(self.resProfiles)))
                for i, p in enumerate(self.resProfiles):
                    g = self.geometries[i]
                    d = self.resProfiles[i]
                    if d in [INFO_OUT_OF_IMAGE, INFO_NO_DATA]:
                        info.append('\t{}: {}:{}'.format(i + 1, g, d))
                    else:
                        vData = d[0]
                        vStd = d[1]
                        try:
                            info.append('\t{}: {}:{} : {}'.format(i+1, g, vData.shape, vData))
                        except:
                            s  =""

        return '\n'.join(info)

LOADING_FINISHED = 'finished'
LOADING_CANCELED = 'canceled'
INFO_OUT_OF_IMAGE = 'out of image'
INFO_NO_DATA = 'no data values'

#def loadProfiles(pathsAndBandIndices, jobid, poolWorker, geom, q, cancelEvent, **kwargs):


def transformPoint2Px(trans, pt, gt):
    x, y, _ = trans.TransformPoint(pt.x(), pt.y())
    return geo2px(QgsPointXY(x, y), gt)

def doLoaderTask(task):

    #assert isinstance(task, PixelLoaderTask), '{}\n{}'.format(type(task), task)

    result = task

    ds = gdal.Open(task.sourcePath, gdal.GA_ReadOnly)
    nb, ns, nl = ds.RasterCount, ds.RasterXSize, ds.RasterYSize



    bandIndices = list(range(nb)) if task.bandIndices is None else list(task.bandIndices)
    #ensure to load valid indices only
    bandIndices = [i for i in bandIndices if i >= 0 and i < nb]

    task.bandIndices = bandIndices

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

        if isinstance(geom, QgsPointXY):
            ptUL = ptLR = QgsPointXY(geom)
        elif isinstance(geom, QgsRectangle):
            TYPE = 'RECTANGLE'
            ptUL = QgsPointXY(geom.xMinimum(), geom.yMaximum())
            ptLR = QgsPointXY(geom.xMaximum(), geom.yMinimum())
        else:
            raise NotImplementedError('Unsupported geometry {} {}'.format(type(geom), str(geom)))

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
            if isinstance(pd, list):
                if len(pd) == 0:
                    PROFILE_DATA[i] = INFO_OUT_OF_IMAGE
                else:
                    #PROFILE_DATA[i] = np.dstack(pd).transpose(2,0,1)
                    PROFILE_DATA[i] = np.vstack(pd)



    #finally, ensure that there is on 2D array only
    for i in range(len(PROFILE_DATA)):
        d = PROFILE_DATA[i]
        if isinstance(d, np.ndarray):
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
                PROFILE_DATA[i] = (vMean, vStd)
            else:
                PROFILE_DATA[i] = INFO_NO_DATA

            s = ""
    task.resProfiles = PROFILE_DATA
    task.mIsDone = True
    return task



def pixelLoadingLoop(inputQueue, resultQueue, cancelEvent, finishedEvent):
    import time
    from multiprocessing.queues import Queue
    from multiprocessing.synchronize import Event
    assert isinstance(inputQueue, Queue)
    assert isinstance(resultQueue, Queue)
    assert isinstance(cancelEvent, Event)
    assert isinstance(finishedEvent, Event)


    while not inputQueue.empty():
        if cancelEvent.is_set():
            dprint('Taskloop put CANCELED')
            break
        #if not inputQueue.empty():

        queueObj = inputQueue.get()
        if isinstance(queueObj, bytes):
            task = PixelLoaderTask.fromDump(queueObj)
            try:
                dprint('Taskloop {} doLoaderTask'.format(task.mJobId))
                task = doLoaderTask(task)
                dprint('Taskloop {} put task result back to queue'.format(task.mJobId))
                resultQueue.put(task.toDump())
            except Exception as ex:
                dprint('Taskloop {} EXCEPTION {} '.format(task.mJobId, ex))
                resultQueue.put(ex)
        elif isinstance(queueObj, str):
            if queueObj.startswith('LAST'):
                dprint('Taskloop put FINISHED')
                resultQueue.put('FINISHED')
                #finishedEvent.set()
                dprint('Taskloop FINISHED set')
        else:
            dprint('Taskloop put UNHANDLED')
            dprint('Unhandled {} {}'.format(str(queueObj), type(queueObj)))
            continue

    resultQueue.put('CANCELED')

class LoadingProgress(object):

    def __init__(self, id, nFiles):
        assert isinstance(nFiles, int)
        assert isinstance(id, int)
        self.mID = id
        self.mSuccess = 0
        self.mTotal = nFiles
        self.mFailed = 0

    def addResult(self, success=True):
        assert self.done() <= self.mTotal
        if success:
            self.mSuccess += 1
        else:
            self.mFailed += 1

    def id(self):
        return self.mID

    def failed(self):
        return self.mFailed


    def done(self):
        return self.mSuccess + self.mFailed

    def total(self):
        return self.mTotal



class PixelLoader(QObject):
    """
    Loads pixel from raster images
    """

    sigPixelLoaded = pyqtSignal(int, int, object)
    sigLoadingStarted = pyqtSignal(list)
    sigLoadingFinished = pyqtSignal(np.timedelta64)
    sigLoadingCanceled = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)
        #self.filesList = []
        self.jobId = -1
        self.jobProgress = {}
        self.nProcesses = 2
        self.nMax = 0
        self.nFailed = 0
        self.threadsAndWorkers = []
        self.mLoadingStartTime = np.datetime64('now','ms')

        #see https://gis.stackexchange.com/questions/35279/multiprocessing-error-in-qgis-with-python-on-windows
        #path = os.path.abspath(os.path.join(sys.exec_prefix, '../../bin/pythonw.exe'))
        #assert os.path.exists(path)
        #multiprocessing.set_executable(path)
        sys.argv = [__file__]

        self.mResultQueue = multiprocessing.Queue(maxsize=0)
        self.mTaskQueue = multiprocessing.Queue(maxsize=0)
        self.mCancelEvent = multiprocessing.Event()
        self.mKillEvent = multiprocessing.Event()
        self.mWorkerProcess = None

        self.queueCheckTimer = QTimer()  #
        #self.queueCheckTimer.setInterval(200)
        self.queueCheckTimer.timeout.connect(self.checkTaskResults)
        #self.queueCheckTimer.timeout.connect(self.dummySlot)
        self.queueCheckTimer.start(250)

    def initWorkerProcess(self):

        if not isinstance(self.mWorkerProcess, multiprocessing.Process) :
            self.mWorkerProcess = multiprocessing.Process(name='PixelLoaderWorkingProcess',
                                                          target=pixelLoadingLoop,
                                                          args=(self.mTaskQueue, self.mResultQueue, self.mCancelEvent, self.mKillEvent,))

            self.mWorkerProcess.daemon = False
            self.mWorkerProcess.start()

        else:
            if not self.mWorkerProcess.is_alive():
                self.mWorkerProcess.run()




    @QtCore.pyqtSlot(PixelLoaderTask)
    def onPixelLoaded(self, dataList):
        assert isinstance(dataList, list)
        for data in dataList:
            assert isinstance(data, PixelLoaderTask)

            if data.mJobId not in self.jobProgress.keys():
                return
            else:
                progressInfo = self.jobProgress[data.mJobId]

                assert isinstance(progressInfo, LoadingProgress)
                progressInfo.addResult(data.success())
                if progressInfo.done() == progressInfo.total():
                    self.jobProgress.pop(data.mJobId)

                self.sigPixelLoaded.emit(progressInfo.done(), progressInfo.total(), data)

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

        self.jobId += 1
        jobId = self.jobId

        self.jobProgress[jobId] = LoadingProgress(jobId, len(tasks))
        self.sigLoadingStarted.emit(paths[:])
        #self.mKillEvent.clear()
        self.initWorkerProcess()
        for t in tasks:
            assert isinstance(t, PixelLoaderTask)
            t.mJobId = self.jobId
            self.mTaskQueue.put(t.toDump())
        self.mTaskQueue.put('LAST_{}'.format(jobId))

    def cancelLoading(self):
        self.mCancelEvent.set()


    def isReadyToLoad(self):

        return self.mTaskQueue is None or (self.mTaskQueue.empty() and self.mResultQueue.empty())


    def checkTaskResults(self, *args):
        dataList = []
        finished = False
        canceled = False

        if isinstance(self.mWorkerProcess, multiprocessing.Process):
            while not self.mResultQueue.empty():
                data = self.mResultQueue.get()
                if isinstance(data, bytes):
                    task = PixelLoaderTask.fromDump(data)
                    dataList.append(task)
                    dprint('PixelLoader result pulled')
                elif isinstance(data, str):
                    if data == 'FINISHED':
                        finished = True
                    elif data == 'CANCELED':
                        canceled = True
                    else:
                        s = ""
                else:
                    raise Exception('Unhandled type returned {}'.format(data))
            if len(dataList) > 0:
                 self.onPixelLoaded(dataList)

            if finished:
                dt = np.datetime64('now', 'ms') - self.mLoadingStartTime
                self.sigLoadingFinished.emit(dt)


                if self.mTaskQueue.empty() and self.mResultQueue.empty():
                    pass
                    #self.mWorkerProcess.terminate()
                    #self.mWorkerProcess.join()






if __name__ == '__main__':

    from timeseriesviewer.utils import initQgisApplication
    import example.Images
    qgsApp = initQgisApplication()
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *

    from timeseriesviewer.pixelloader import doLoaderTask, PixelLoaderTask


    gb = QGroupBox()
    gb.setTitle('Sandbox')
    DEBUG = False

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


    def onPxLoaded(*args):
        n, nmax, task = args
        assert isinstance(task, PixelLoaderTask)
        print('Task {} Loaded'.format(task.mJobId))
        print(task)

    PL = PixelLoader()
    def onDummy(*args):
        print(('dummy',args))

    def onTimer(*args):
        print(('TIMER',PL))
        pass

    PL.sigPixelLoaded.connect(onPxLoaded)
    PL.sigLoadingFinished.connect(lambda: onDummy('finished'))
    #PL.sigLoadingFinished.connect(qgsApp.quit)
    PL.sigLoadingCanceled.connect(lambda: onDummy('canceled'))
    PL.sigLoadingStarted.connect(lambda: onDummy('started'))
    PL.sigPixelLoaded.connect(lambda : onDummy('px loaded'))

    tasks = []
    for i, f in enumerate(files):
        kwargs = {'myid':'myID{}'.format(i)}
        tasks.append(PixelLoaderTask(f, geoms, bandIndices=None, **kwargs))

    PL.startLoading(tasks)
    PL.startLoading(tasks)

    #QTimer.singleShot(2000, lambda : PL.cancelLoading())

    qgsApp.exec_()
    s = ""