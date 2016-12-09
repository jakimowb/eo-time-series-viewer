from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect, time
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from timeseriesviewer import DIR_EXAMPLES, jp, dprint

class HiddenCanvas(QgsMapCanvas):


    def __init__(self):
        super(HiddenCanvas,self).__init__(None, None)



def getLoadedLayer(layer):
    print('LAYER READY')
    print(layer)

def getLoadedLayers(layers):
    for lyr in layers:
        getLoadedLayer(lyr)


def loadingDone():
    print('DONE')


from itertools import izip_longest

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(*args, fillvalue=fillvalue)

def waitForThreads():
    print "Waiting for thread pool"
    pool.waitForDone()
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


    #close QGIS

    qgsApp.aboutToQuit.connect(waitForThreads)
    qgsApp.exec_()
    qgsApp.exitQgis()
