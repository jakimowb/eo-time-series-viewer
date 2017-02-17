from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from timeseriesviewer import *

class TestObjects(object):

    @staticmethod
    def TimeSeries(nMax=10):
        files = file_search(jp(DIR_EXAMPLES,'Images'),'*.bsq')
        from timeseriesviewer.timeseries import TimeSeries
        ts = TimeSeries()
        n = len(files)
        if nMax:
            nMax = min([n, nMax])
            ts.addFiles(files[0:nMax])
        else:
            ts.addFiles(files[:])
        return ts


def test_gui():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    if False:
        from timeseriesviewer import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = file_search(searchDir, '*band4.img', recursive=True)

        #searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\01_UncutVRT'
        #files = file_search(searchDir, '*BOA.vrt', recursive=True)

        files = files[0:10]
        S.loadImageFiles(files)
        return
    if False:
        files = [r'H:\\LandsatData\\Landsat_NovoProgresso\\LC82270652013140LGN01\\LC82270652013140LGN01_sr_band4.img']
        S.loadImageFiles(files)
        return
    if False:
        S.spatialTemporalVis.MVC.createMapView()
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=1)
        return
    if True:
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=1)
        return
    pass

class QgisFake(QgisInterface):

    def __init__(self, *args):
        super(QgisFake, self).__init__(*args)

        self.canvas = QgsMapCanvas()
        self.canvas.blockSignals(False)
        print(self.canvas)
        self.canvas.setCrsTransformEnabled(True)
        self.canvas.setCanvasColor(Qt.black)
        self.canvas.extentsChanged.connect(self.testSlot)
        self.layerTreeView = QgsLayerTreeView()
        self.rootNode =QgsLayerTreeGroup()
        self.treeModel = QgsLayerTreeModel(self.rootNode)
        self.layerTreeView.setModel(self.treeModel)
        self.bridge = QgsLayerTreeMapCanvasBridge(self.rootNode, self.canvas)
        self.bridge.setAutoSetupOnFirstLayer(True)
        self.ui = QMainWindow()
        mainFrame = QFrame()

        self.ui.setCentralWidget(mainFrame)
        self.ui.setWindowTitle('Fake QGIS')
        l = QHBoxLayout()
        l.addWidget(self.layerTreeView)
        l.addWidget(self.canvas)
        mainFrame.setLayout(l)
        self.ui.setCentralWidget(mainFrame)
        self.lyrs = []
        self.createActions()

    def testSlot(self, *args):
        #print('--canvas changes--')
        s = ""

    def addVectorLayer(selfpath, basename, providerkey):
        pass

    def addRasterLayer(self, path, baseName=''):
        l = QgsRasterLayer(path, loadDefaultStyleFlag=True)
        self.lyrs.append(l)
        QgsMapLayerRegistry.instance().addMapLayer(l, True)
        self.rootNode.addLayer(l)
        self.bridge.setCanvasLayers()
        return

        cnt = len(self.canvas.layers())

        self.canvas.setLayerSet([QgsMapCanvasLayer(l)])
        l.dataProvider()
        if cnt == 0:
            self.canvas.mapSettings().setDestinationCrs(l.crs())
            self.canvas.setExtent(l.extent())
            from timeseriesviewer.main import SpatialExtent

            spatialExtent = SpatialExtent.fromMapLayer(l)
            #self.canvas.blockSignals(True)
            self.canvas.setDestinationCrs(spatialExtent.crs())
            self.canvas.setExtent(spatialExtent)
            #self.blockSignals(False)
            self.canvas.refresh()

        self.canvas.refresh()

    def createActions(self):
        m = self.ui.menuBar().addAction('Add Vector')
        m = self.ui.menuBar().addAction('Add Raster')

    def mapCanvas(self):
        return self.canvas

def test_qgisbridge():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES

    fakeQGIS = QgisFake()

    S = TimeSeriesViewer(fakeQGIS)
    S.ui.show()
    S.run()

    fakeQGIS.ui.show()
    import example.Images
    fakeQGIS.addRasterLayer(example.Images.Img_2014_08_03_LE72270652014215CUB00_BOA)
    S.loadImageFiles([example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA])
    s = ""



def test_component():

    pass

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

    #run tests
    if True: test_qgisbridge()
    if False: test_gui()
    if False: test_component()


    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
