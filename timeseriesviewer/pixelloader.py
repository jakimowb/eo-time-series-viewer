# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
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
import multiprocessing, logging

import datetime
from qgis.gui import *
from qgis.core import *
from PyQt5.QtCore import *
import numpy as np
from timeseriesviewer.utils import SpatialPoint, SpatialExtent, geo2px, px2geo
from osgeo import gdal, gdal_array, osr

DEBUG = False

if DEBUG:
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(multiprocessing.SUBDEBUG)


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

    def __init__(self, source:str, geometries, bandIndices=None, **kwargs):

        if not isinstance(geometries, list):
            geometries = [geometries]
        assert isinstance(geometries, list)
        for geometry in geometries:
            assert type(geometry) in [SpatialExtent, SpatialPoint]


        self.mId = ''

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

    def setId(self, idStr:str):
        self.mId = idStr

    def id(self)->str:
        return self.mId

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





def doLoaderTask(taskWrapper:QgsTask, dump):

    #assert isinstance(taskWrapper, QgsTask)
    if isinstance(dump, PixelLoaderTask):
        task = dump
    else:
        task = PixelLoaderTask.fromDump(dump)
    assert isinstance(task, PixelLoaderTask)
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

        if geom.crs().isValid():
            crsRequest.ImportFromWkt(geom.crs().toWkt())
        else:
            crsRequest.ImportFromWkt(crsSrc.ExportToWkt())
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
    return task.toDump()



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
    Use QgsTaskManager interface in background
    """
    sigPixelLoaded = pyqtSignal(PixelLoaderTask)
    sigLoadingStarted = pyqtSignal()
    sigLoadingFinished = pyqtSignal()


    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)
        self.mTasks = {}


    def tasks(self)->list:
        """
        Returns the list of QgsTaskWrappers
        :return: list
        """

        return self.taskManager().tasks()

    def taskManager(self)->QgsTaskManager:
        return QgsApplication.taskManager()

    def startLoading(self, tasks):

        assert isinstance(tasks, list)

        tm = self.taskManager()

        #self.sigLoadingStarted.emit()

        #todo: create chuncks
        import uuid
        for plt in tasks:
            assert isinstance(plt, PixelLoaderTask)

            taskName = 'pltTask.{}'.format(uuid.uuid4())
            plt.setId(taskName)
            dump = plt.toDump()
            qgsTask = QgsTask.fromFunction(taskName, doLoaderTask, dump, on_finished=self.onLoadingFinished)
            tm.addTask(qgsTask)
            self.mTasks[taskName] = qgsTask


    def onLoadingFinished(self, *args, **kwds):

        error = args[0]
        if error is None:
            dump = args[1]
            plt = PixelLoaderTask.fromDump(dump)
            if isinstance(plt, PixelLoaderTask):
                self.mTasks.pop(plt.id())
                self.sigPixelLoaded.emit(plt)


    def status(self)->tuple:

        return None

    def cancelLoading(self):
        raise NotImplementedError


