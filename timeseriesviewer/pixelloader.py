import os, pickle
import sys
import datetime
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
import numpy as np
from utils import SpatialPoint, SpatialExtent, geo2px, px2geo
from osgeo import gdal
import multiprocessing as mp



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
        self.noDataValue = None
        self.exception = None
        self.info = None

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

def loadProfiles(paths, jobid, poolWorker, geom, q, cancelEvent):
    #geom = pickle.loads(geomDump)
    assert type(geom) in [SpatialPoint, SpatialExtent]
    crs = geom.crs()

    for i, path in enumerate(paths):
        if cancelEvent.is_set():
            return LOADING_CANCELED

        R = PixelLoaderResult(jobid, poolWorker, geom, path)

        try:
            ds = gdal.Open(path, gdal.GA_ReadOnly)
            gt = ds.GetGeoTransform()
            R.srcCrsWkt = ds.GetProjection()
            R.geoTransformation = gt
            crsSrc = QgsCoordinateReferenceSystem(ds.GetProjection())
            trans = QgsCoordinateTransform(crs, crsSrc)

            geo = trans.transform(geom)
            if isinstance(geo, QgsPoint):
                px = geo2px(geo, gt)
                if isOutOfImage(ds, px):
                    R.info = INFO_OUT_OF_IMAGE

                    q.put(R)
                    continue

                size_x = 1
                size_y = 1

            elif isinstance(geo, QgsRectangle):
                pt1 = QgsPoint(geo.xMinimum(), geo.yMaximum())
                pt2 = QgsPoint(geo.xMaximum(), geo.yMinimum())
                px = geo2px(pt1, gt)
                px2 = geo2px(pt2, gt)

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

            nb = ds.RasterCount
            values = ds.ReadAsArray(px.x(), px.y(), size_x, size_y)

            values = np.reshape(values, (nb, size_y, size_x))
            noData = [ds.GetRasterBand(b+1).GetNoDataValue() for b in range(nb)]
        except Exception as ex:
            R.exception = ex
            q.put(R)
            continue

        R.noDataValue = noData
        R.pxData = values
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
        self.APPLYRESULTS=[]
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

    def startLoading(self, pathList, theGeometry):
        assert isinstance(pathList, list)
        assert type(theGeometry) in [SpatialPoint, SpatialExtent]
        import pickle
        geomDump = pickle.dumps(theGeometry)

        self.jobid += 1
        self.sigLoadingStarted.emit(pathList[:])
        self.filesList.extend(pathList[:])

        l = len(pathList)
        self.nMax = l
        self.nFailed = 0

        #split number of files into list
        files = pathList[:]
        workPackages = list()
        i = 0
        while(len(files)) > 0:
            if len(workPackages) <= i:
                workPackages.append([])
            workPackages[i].append(files.pop(0))
            i = i + 1 if i < self.nProcesses - 1 else 0
        self.pool = mp.Pool(self.nProcesses)
        del self.APPLYRESULTS[:]
        self.queueChecker.start()
        for i, workPackage in enumerate(workPackages):
            args = (workPackage, self.jobid, i, theGeometry, self.resultQueue, self.cancelEvent)
            if False:
                r = self.pool.apply_async(loadProfiles, args=args, callback=self.checkQueue)
                self.APPLYRESULTS.append(r)
            else:
                self.checkQueue(loadProfiles(*args))
        self.pool.close()

    def cancelLoading(self):
        self.cancelEvent.set()



    def checkQueue(self, *args):

        while not self.resultQueue.empty():
            md = self.resultQueue.get()
            self.onPixelLoaded(md)

        if all([w.ready() for w in self.APPLYRESULTS]):
            print('All done')

            del self.APPLYRESULTS[:]
            self.queueChecker.stop()
            if not self.cancelEvent.is_set():
                self.sigLoadingFinished.emit()
        elif self.cancelEvent.is_set():
            self.queueChecker.stop()
            self.sigLoadingCanceled.emit()



if __name__ == '__main__':

    from sandbox import initQgisEnvironment
    qgsApp = initQgisEnvironment()
    from PyQt4.QtGui import *
    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfProcesses(1)

    import example.Images
    from timeseriesviewer import file_search
    dir = os.path.dirname(example.Images.__file__)
    files = file_search(dir, '*_BOA.tif')

    ext = SpatialExtent.fromRasterSource(files[0])
    pt = SpatialPoint(ext.crs(), ext.center())

    from multiprocessing import Pool

    def onPxLoaded(*args):
        n, nmax, plr = args
        assert isinstance(plr, PixelLoaderResult)

    PL = PixelLoader()
    def onDummy(*args):
        print(('dummy',args))

    def onTimer(*args):
        print(('TIMER',PL))

    PL.sigPixelLoaded.connect(onPxLoaded)
    PL.sigLoadingFinished.connect(lambda: onDummy('finished'))
    PL.sigLoadingCanceled.connect(lambda: onDummy('canceled'))
    PL.sigLoadingStarted.connect(lambda: onDummy('started'))
    PL.sigPixelLoaded.connect(lambda : onDummy('px loaded'))
    PL.startLoading(files, pt)

    QTimer.singleShot(2000, lambda : PL.cancelLoading())

    qgsApp.exec_()
    s = ""