import os
import sys
import datetime
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
import numpy as np
from utils import SpatialPoint, SpatialExtent
from osgeo import gdal, gdal_array

class PixelLoadWorker(QObject):
    #qRegisterMetaType
    sigPixelLoaded = pyqtSignal(dict)

    sigWorkStarted = pyqtSignal(int)

    sigWorkFinished = pyqtSignal()

    def __init__(self, files, jobid, parent=None):
        super(PixelLoadWorker, self).__init__(parent)
        assert isinstance(files, list)
        self.files = files
        self.jobid = jobid
        self.mTerminate = False

    def info(self):
        return 'jobid:{} recent file: {}'.format(self.jobid, self.recentFile)

    @pyqtSlot()
    def terminate(self):
        self.mTerminate = True

    @pyqtSlot(str, str)
    def doWork(self, theGeometryWkt, theCrsDefinition):

        g = QgsGeometry.fromWkt(theGeometryWkt)
        if g.wkbType() == QgsWKBTypes.Point:
            g = g.asPoint()
        elif g.wkbType() == QgsWKBTypes.Polygon:
            g = g.asPolygon()
        else:
            raise NotImplementedError()

        if self.mTerminate: return

        crs = QgsCoordinateReferenceSystem(theCrsDefinition)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        paths = self.files
        self.sigWorkStarted.emit(len(paths))

        for i, path in enumerate(paths):
            if QThread.currentThread() is None or self.mTerminate:
                return

            self.recentFile = path

            lyr = QgsRasterLayer(path)
            if not lyr.isValid():
                #logger.debug('Layer not valid: {}'.format(path))
                continue
            dp = lyr.dataProvider()

            trans = QgsCoordinateTransform(crs, dp.crs())
            #todo: add with QGIS 3.0
            #if not trans.isValid():
            #    self.sigPixelLoaded.emit({})
            #    continue

            try:
                geo = trans.transform(g)
            except(QgsCsException):
                self.sigPixelLoaded.emit({})
                continue

            ns = dp.xSize()  # ns = number of samples = number of image columns
            nl = dp.ySize()  # nl = number of lines
            ex = dp.extent()

            xres = ex.width() / ns  # pixel size
            yres = ex.height() / nl

            if not ex.contains(geo):
                self.sigPixelLoaded.emit({})
                continue

            def geo2px(x, y):
                x = int(np.floor((x - ex.xMinimum()) / xres).astype(int))
                y = int(np.floor((ex.yMaximum() - y) / yres).astype(int))
                return x, y

            if isinstance(geo, QgsPoint):
                px_x, px_y = geo2px(geo.x(), geo.y())

                size_x = 1
                size_y = 1
                UL = geo
            elif isinstance(geo, QgsRectangle):

                px_x, px_y = geo2px(geo.xMinimum(), geo.yMaximum())
                px_x2, px_y2 = geo2px(geo.xMaximum(), geo.yMinimum())
                size_x = px_x2 - px_x
                size_y = px_y2 - px_y
                UL = QgsPoint(geo.xMinimum(), geo.yMaximum())

            ds = gdal.Open(path)
            if ds is None:
                self.sigPixelLoaded.emit({})
                continue
            nb = ds.RasterCount
            values = gdal_array.DatasetReadAsArray(ds, px_x, px_y, win_xsize=size_x, win_ysize=size_y)
            values = np.reshape(values, (nb, size_y, size_x))
            nodata = [ds.GetRasterBand(b+1).GetNoDataValue() for b in range(nb)]


            md = dict()
            md['_worker_'] = self.objectName()
            md['_thread_'] = QThread.currentThread().objectName()
            md['_jobid_'] = self.jobid
            md['_wkt_'] = theGeometryWkt
            md['path'] = path
            md['xres'] = xres
            md['yres'] = xres
            md['geo_ul_x'] = UL.x()
            md['geo_ul_y'] = UL.y()
            md['px_ul_x'] = px_x
            md['px_ul_y'] = px_y
            md['values'] = values
            md['nodata'] = nodata
            if QThread.currentThread() is None or self.mTerminate:
                return
            self.sigPixelLoaded.emit(md)
        self.recentFile = None
        self.sigWorkFinished.emit()




class PixelLoader(QObject):


    sigPixelLoaded = pyqtSignal(int, int, dict)
    sigLoadingStarted = pyqtSignal(list)
    sigLoadingFinished = pyqtSignal()
    sigLoadingCanceled = pyqtSignal()
    _sigStartThreadWorkers = pyqtSignal(str, str)
    _sigTerminateThreadWorkers = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)
        self.filesList = []
        self.jobid = -1
        self.nThreads = 1
        self.nMax = 0
        self.threadsAndWorkers = []

    @QtCore.pyqtSlot(dict)
    def onPixelLoaded(self, data):
        path = data.get('path')
        jobid = data.get('_jobid_')
        if jobid != self.jobid:
            #do not return results from previous jobs...
            #print('got thread results from {} but need {}...'.format(jobid, self.jobid))
            return
        elif path is not None and path in self.filesList:
            self.filesList.remove(path)
            self.sigPixelLoaded.emit(self.nMax - len(self.filesList), self.nMax, data)

            if len(self.filesList) == 0:
                self.sigLoadingFinished.emit()


    def setNumberOfThreads(self, nThreads):
        assert nThreads >= 1
        self.nThreads = nThreads

    def threadInfo(self):
        info = []
        info.append('done: {}/{}'.format(self.nDone, self.nMax))
        for i, t in enumerate(self.threads):
            info.append('{}: {}'.format(i, t.info() ))

        return '\n'.join(info)

    def cancelLoading(self):
        self._sigTerminateThreadWorkers.emit()
        threads = [t[0] for t in self.threadsAndWorkers]
        for thread in threads:
            self.finishThread(thread)
        assert len(self.threadsAndWorkers) == 0
        del self.filesList[:]
        self.nMax = 0
        self.sigLoadingCanceled.emit()


    def finishThread(self, thread):
        thread.quit()
        thread.wait()
        for t in self.threadsAndWorkers:
            th, worker = t
            if th == thread:
                worker.terminate()
                self.threadsAndWorkers.remove(t)
                break


    def startLoading(self, pathList, theGeometry):
        assert isinstance(pathList, list)
        assert type(theGeometry) in [SpatialPoint, SpatialExtent]

        self.cancelLoading()
        self.jobid += 1
        self.sigLoadingStarted.emit(pathList[:])


        crs = theGeometry.crs()
        if isinstance(theGeometry, SpatialPoint):
            theGeometry = QgsPointV2(theGeometry)
        elif isinstance(theGeometry, SpatialExtent):
            theGeometry = QgsPolygonV2(theGeometry.asWktPolygon())
        assert type(theGeometry) in [QgsPointV2, QgsPolygonV2]

        self.filesList.extend(pathList[:])

        l = len(pathList)
        self.nMax = l
        self.nFailed = 0


        files = pathList[:]
        workPackages = list()
        i = 0
        while(len(files)) > 0:
            if len(workPackages) <= i:
                workPackages.append([])
            workPackages[i].append(files.pop(0))
            i = i + 1 if i < self.nThreads - 1 else 0

        for i, workPackage in enumerate(workPackages):
            thread = QThread()
            thread.setObjectName('Thread {}'.format(i))
            #thread.finished.connect(lambda : self.removeFinishedThreads())
            #thread.finished.connect(thread.deleteLater)
            thread.finished.connect(lambda : self.finishThread(thread))
            thread.terminated.connect(lambda : self.finishThread(thread))

            worker = PixelLoadWorker(workPackage, self.jobid)
            self.threadsAndWorkers.append((thread, worker))
            worker.setObjectName('W {}'.format(i))
            worker.moveToThread(thread)
            worker.sigPixelLoaded.connect(self.onPixelLoaded)

            #worker.sigWorkFinished.connect(lambda : self.finishThread(thread))
            self._sigStartThreadWorkers.connect(worker.doWork)
            self._sigTerminateThreadWorkers.connect(worker.terminate)
            thread.start()


        #stark the workers
        self._sigStartThreadWorkers.emit(theGeometry.asWkt(50), str(crs.authid()))
        s = ""



if __name__ == '__main__':

    from sandbox import initQgisEnvironment
    qgsApp = initQgisEnvironment()
    from PyQt4.QtGui import *
    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfThreads(1)

    files = [r'D:\Repositories\QGIS_Plugins\hub-timeseriesviewer\example\Images\2012-04-23_LE72270652012114EDC00_BOA.bsq',
             r'D:\Repositories\QGIS_Plugins\hub-timeseriesviewer\example\Images\2012-05-25_LE72270652012146EDC00_BOA.bsq'
            ]

    lyr = QgsRasterLayer(files[0])
    coord = SpatialPoint(lyr.crs(),lyr.extent().center())


    l = QVBoxLayout()

    btnStart = QPushButton()
    btnStop = QPushButton()
    prog = QProgressBar()
    tboxResults = QPlainTextEdit()
    tboxResults.setMaximumHeight(300)
    tboxThreads = QPlainTextEdit()
    tboxThreads.setMaximumHeight(200)
    label = QLabel()
    label.setText('Progress')

    def showProgress(n,m,md):
        prog.setMinimum(0)
        prog.setMaximum(m)
        prog.setValue(n)

        info = []
        for k, v in md.items():
            info.append('{} = {}'.format(k,str(v)))
        tboxResults.setPlainText('\n'.join(info))
        #tboxThreads.setPlainText(PL.threadInfo())
        qgsApp.processEvents()

    PL.sigPixelLoaded.connect(showProgress)
    btnStart.setText('Start loading')
    btnStart.clicked.connect(lambda : PL.startLoading(files, coord))
    btnStop.setText('Cancel')
    btnStop.clicked.connect(lambda: PL.cancelLoading())
    lh = QHBoxLayout()
    lh.addWidget(btnStart)
    lh.addWidget(btnStop)
    l.addLayout(lh)
    l.addWidget(prog)
    l.addWidget(tboxThreads)
    l.addWidget(tboxResults)

    gb.setLayout(l)
    gb.show()
    #rs.setBackgroundStyle('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222, stop:1 #333);')
    #rs.handle.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #282, stop:1 #393);')
    qgsApp.exec_()
    qgsApp.exitQgis()
