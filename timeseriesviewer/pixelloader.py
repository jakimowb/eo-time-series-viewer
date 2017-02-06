import os
import sys

from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *


from osgeo import gdal, gdal_array
import numpy as np



class PixelLoadWorker(QObject):
    #qRegisterMetaType
    sigPixelLoaded = pyqtSignal(dict)

    sigWorkStarted = pyqtSignal(int)

    sigWorkFinished = pyqtSignal()

    def __init__(self, files, parent=None):
        super(PixelLoadWorker, self).__init__(parent)
        assert isinstance(files, list)
        self.files = files

    def info(self):
        return 'recent file {}'.format(self.recentFile)

    @pyqtSlot(str, str)
    def doWork(self, theGeometryWkt, theCrsDefinition):

        g = QgsGeometry.fromWkt(theGeometryWkt)
        if g.wkbType() == QgsWKBTypes.Point:
            g = g.asPoint()
        elif g.wkbType() == QgsWKBTypes.Polygon:
            g = g.asPolygon()
        else:
            raise NotImplementedError()



        crs = QgsCoordinateReferenceSystem(theCrsDefinition)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        paths = self.files
        self.sigWorkStarted.emit(len(paths))

        for i, path in enumerate(paths):
            self.recentFile = path

            lyr = QgsRasterLayer(path)
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

            nodata = [ds.GetRasterBand(b+1).GetNoDataValue() for b in range(nb)]


            md = dict()
            md['_worker_'] = self.objectName()
            md['_thread_'] = QThread.currentThread().objectName()
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

            self.sigPixelLoaded.emit(md)
        self.recentFile = None
        self.sigWorkFinished.emit()




class PixelLoader(QObject):


    sigPixelLoaded = pyqtSignal(int, int, dict)
    sigLoadingDone = pyqtSignal()
    sigLoadingFinished = pyqtSignal()
    sigLoadingCanceled = pyqtSignal()
    sigLoadCoordinate = pyqtSignal(str, str)

    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)

        self.nThreads = 1
        self.nMax = 0
        self.nDone = 0
        self.threadsAndWorkers = []

    @QtCore.pyqtSlot(dict)
    def onPixelLoaded(self, d):
        self.nDone += 1
        self.sigPixelLoaded.emit(self.nDone, self.nMax, d)

        if self.nDone == self.nMax:
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
        for t in self.threadsAndWorkers:
            thread, worker = t
            thread.quit()
        del self.threadsAndWorkers[:]

        for t,w in self.workerThreads.items():
            w.stop()
            t.quit()
            t.deleteLater()
            self.workerThreads.pop(t)
        self.nMax = self.nDone = None
        self.sigLoadingCanceled.emit()

    def removeFinishedThreads(self):

        toRemove = []
        for i, t in enumerate(self.threadsAndWorkers):
            thread, worker = t
            if thread.isFinished():
                thread.quit()
                toRemove.append(t)
        for t in toRemove:
            self.threadsAndWorkers.remove(t)

    def startLoading(self, pathList, theGeometry, crs):
        assert isinstance(pathList, list)

        if isinstance(theGeometry, QgsPoint):
            theGeometry = QgsPointV2(theGeometry)
        elif isinstance(theGeometry, QgsRectangle):
            theGeometry = QgsPolygonV2(theGeometry.asWktPolygon())
        assert type(theGeometry) in [QgsPointV2, QgsPolygonV2]


        wkt = theGeometry.asWkt(50)


        l = len(pathList)
        self.nMax = l
        self.nFailed = 0
        self.nDone = 0

        nThreads = self.nThreads
        filesPerThread = int(np.ceil(float(l) / nThreads))

        if True:
            worker = PixelLoadWorker(pathList[0:1])
            worker.doWork(wkt, str(crs.authid()))

        n = 0
        files = pathList[:]
        while len(files) > 0:
            n += 1

            i = min([filesPerThread, len(files)])
            thread = QThread()
            thread.setObjectName('Thread {}'.format(n))
            thread.finished.connect(self.removeFinishedThreads)
            thread.terminated.connect(self.removeFinishedThreads)

            worker = PixelLoadWorker(files[0:i])
            worker.setObjectName('W {}'.format(n))
            worker.moveToThread(thread)
            worker.sigPixelLoaded.connect(self.onPixelLoaded)
            worker.sigWorkFinished.connect(thread.quit)
            self.sigLoadCoordinate.connect(worker.doWork)
            thread.start()
            self.threadsAndWorkers.append((thread, worker))
            del files[0:i]

        #stark the workers

        self.sigLoadCoordinate.emit(theGeometry.asWkt(50), str(crs.authid()))




if __name__ == '__main__':

    # prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()


    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfThreads(1)

    if False:
        files = ['observationcloud/testdata/2014-07-26_LC82270652014207LGN00_BOA.bsq',
                 'observationcloud/testdata/2014-08-03_LE72270652014215CUB00_BOA.bsq'
                 ]
    else:
        from utils import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = file_search(searchDir, '*227065*band4.img', recursive=True)
        #files = files[0:3]

    lyr = QgsRasterLayer(files[0])
    coord = lyr.extent().center()
    crs = lyr.crs()

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
    btnStart.clicked.connect(lambda : PL.startLoading(files, coord, crs))
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

