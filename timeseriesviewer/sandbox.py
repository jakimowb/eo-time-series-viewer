from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *


class HiddenCanvas(QgsMapCanvas):


    def __init__(self):
        super(HiddenCanvas,self).__init__(None, None)



class LayerLoaderR(QRunnable):

    layerReady = pyqtSignal(QgsRasterLayer)
    finished = pyqtSignal(list)
    def __init__(self):
        super(LayerLoader, self).__init__()

    def loadLayers(self, paths):
        lyrs = []
        for path in paths:
            print('Load '+path)
            lyr = QgsRasterLayer(path)
            if lyr:
                self.layerReady.emit(lyr)
                lyrs.append(lyr)

        self.finished.emit(lyrs)

class LayerLoader(QObject):

    layerReady = pyqtSignal(QgsRasterLayer)
    finished = pyqtSignal(list)
    def __init__(self):
        super(LayerLoader, self).__init__()

    def loadLayers(self, paths):
        lyrs = []
        for path in paths:
            print('Load '+path)
            lyr = QgsRasterLayer(path)
            if lyr:
                self.layerReady.emit(lyr)
                lyrs.append(lyr)

        self.finished.emit(lyrs)


def getLoadedLayer(layer):
    print('LAYER READY')
    print(layer)

def getLoadedLayers(layers):
    for lyr in layers:
        getLoadedLayer(lyr)


def loadingDone():
    print('DONE')

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
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

    from timeseriesviewer import file_search
    paths = file_search(r'C:\Users\geo_beja\Repositories\QGIS_Plugins\SenseCarbonTSViewer\example\Images',
                        '*.bsq')
    #run
    import numpy as np
    pool = QThreadPool()
    pool.maxThreadCount(3)

    pool.start()

    t0 = np.datetime64('now')
    #paths = []
    objThread = QThread()
    loader = LayerLoader()
    #loader.loadLayers(paths)
    loader.moveToThread(objThread)
    loader.finished.connect(objThread.quit)
    #loader.layerReady.connect(getLoadedLayer)
    objThread.started.connect(lambda:loader.loadLayers(paths))

    objThread.finished.connect(loadingDone)
    objThread.start()

    while not objThread.isFinished():


    print('DT: {}'.format(np.datetime64('now') - t0))

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
