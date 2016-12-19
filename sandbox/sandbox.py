from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect, time
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from timeseriesviewer import DIR_EXAMPLES, jp, dprint
DIR_SANDBOX = os.path.dirname(__file__)

from itertools import izip_longest

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(*args, fillvalue=fillvalue)



class HiddenMapCanvas(QgsMapCanvas):

    sigPixmapCreated = pyqtSignal(QgsRasterLayer, QPixmap)


    def __init__(self, *args, **kwds):
        super(HiddenMapCanvas,self).__init__(*args, **kwds)
        self.reg = QgsMapLayerRegistry.instance()
        self.painter = QPainter()
        self.layerQueue = list()
        self.mapCanvasRefreshed.connect(self.createPixmap)

    def isBusy(self):
        return len(self.layerQueue) != 0

    def createPixmap(self, *args):
        assert len(self.layerQueue) > 0

        pixmap = QPixmap(self.size())
        self.painter.begin(pixmap)
        self.map().paint(self.painter)
        self.painter.end()
        assert not pixmap.isNull()
        lyr = self.layerQueue.pop(0)

        assert lyr.extent().intersects(self.extent())
        self.sigPixmapCreated.emit(lyr, pixmap)
        self.startSingleLayerRendering()


    def startLayerRendering(self, layers):
        assert isinstance(layers, list)
        self.layerQueue.extend(layers)
        self.startSingleLayerRendering()



    def startSingleLayerRendering(self):

        if len(self.layerQueue) > 0:
            mapLayer = self.layerQueue[0]
            self.reg.addMapLayer(mapLayer)
            lyrSet = [QgsMapCanvasLayer(mapLayer)]
            self.setLayerSet(lyrSet)

            #todo: add crosshair
            self.refreshAllLayers()



n_PX = 0
def newPixmap(layer, pixmap):
    global n_PX
    pathPNG = jp(DIR_SANDBOX, 'mapimage{}.png'.format(n_PX))
    n_PX += 1
    # .saveAsImage(pathPNG)
    # pm = C.layerToPixmap(lyrRef, QSize(600,600))
    print('Write ' + pathPNG)
    pixmap.toImage().save(pathPNG)

    s = ""


if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        #os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()

    from timeseriesviewer import file_search, PATH_EXAMPLE_TIMESERIES
    from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum
    pathTestTS = jp(DIR_EXAMPLES, 'ExampleTimeSeries.csv')
    TS = TimeSeries()
    if False or not os.path.exists(pathTestTS):
        paths = file_search(jp(DIR_EXAMPLES, 'Images'), '*.bsq')

        TS.addFiles(paths)
        TS.saveToFile(PATH_EXAMPLE_TIMESERIES)
    else:
        TS.loadFromFile(PATH_EXAMPLE_TIMESERIES)





    C = HiddenMapCanvas()
    C.setAutoFillBackground(True)
    C.setCanvasColor(Qt.green)
    #C.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    #l = QHBoxLayout()
    #l.addWidget(C)
    #w.layout().addWidget(C)
    #w.show()


    #C.setFixedSize(QSize(300,400))
    lyrRef = TS.data[24].lyrImg
    layers = [TS.data[i].lyrImg for i in [23,12,16]]
    QgsMapLayerRegistry.instance().addMapLayer(lyrRef, False)
    C.setDestinationCrs(lyrRef.crs())
    C.setExtent(lyrRef.extent())
    C.setFixedSize(QSize(600, 600))
    C.sigPixmapCreated.connect(newPixmap)


    C.startLayerRendering(layers)
    #w.show()
    qgsApp.exec_()

    pathPNG = jp(DIR_SANDBOX, 'mapimage.png')
    #.saveAsImage(pathPNG)
    #pm = C.layerToPixmap(lyrRef, QSize(600,600))
    #pm.toImage().save(pathPNG)


    #qgsApp.exitQgis()
    s = ""

    if False:
        drvMEM = gdal.GetDriverByName('MEM')
        ds = gdal.Open(TS.data[0].pathImg)
        ds = drvMEM.CreateCopy('',ds)

        lyr = QgsRasterLayer(paths[0])
        finalLayerList = []
        def callback(result):
            assert isinstance(result, QgsRasterLayer)
            print(result)
            finalLayerList.append(result)
            s =  ""
        cnt = 0
        def callbackFin():
            cnt-=1

        #run
        #LL = LayerLoaderR(paths)
        #LL.signales.sigLayerLoaded.connect(callback)
        #r = LL.run()

        import numpy as np
        #pool = QThreadPool()
        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(4)
        for files in grouper(paths, 3):

            LL = TSDLoader([f for f in files if f is not None])
            cnt += 1
            LL.signals.sigRasterLayerLoaded.connect(callback)
            LL.signals.sigFinished.connect(callbackFin)
            pool.start(LL)

        t0 = np.datetime64('now')
        pool.waitForDone()


    s = ""