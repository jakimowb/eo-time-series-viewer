from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
import logging, io
logger = logging.getLogger(__name__)
from osgeo import gdal, ogr
from unittest import TestCase
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from timeseriesviewer import *
from timeseriesviewer.utils import *
from timeseriesviewer import file_search
from timeseriesviewer.timeseries import *

class SandboxObjects(object):

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


def sandboxGui():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    if False:
        files = [r'H:\\LandsatData\\Landsat_NovoProgresso\\LC82270652013140LGN01\\LC82270652013140LGN01_sr_band4.img']
        S.loadImageFiles(files)
        return
    if False:
        S.spatialTemporalVis.MVC.createMapView()
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=1)
        return
    if False:
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=100)
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

    def addVectorLayer(self, path, basename=None, providerkey=None):
        if basename is None:
            basename = os.path.basename(path)
        if providerkey is None:
            bn, ext = os.path.splitext(basename)

            providerkey = 'ogr'
        l = QgsVectorLayer(path, basename, providerkey)
        assert l.isValid()
        QgsMapLayerRegistry.instance().addMapLayer(l, True)
        self.rootNode.addLayer(l)
        self.bridge.setCanvasLayers()
        s = ""


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

def sandboxQgisBridge():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES

    fakeQGIS = QgisFake()

    S = TimeSeriesViewer(fakeQGIS)
    S.ui.show()
    S.run()

    fakeQGIS.ui.show()
    import example.Images
    fakeQGIS.addVectorLayer(example.exampleEvents)
    fakeQGIS.addRasterLayer(example.Images.Img_2014_08_03_LE72270652014215CUB00_BOA)

    S.loadImageFiles([example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA])
    S.ui.resize(600,600)
    s = ""


def gdal_qgis_benchmark():
    """Benchmark to compare loading times between GDAL a QGIS"""
    import numpy as np

    def load_via_gdal(path):
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        nb = ds.RasterCount
        ns = ds.RasterXSize
        nl = ds.RasterYSize
        wkt = ds.GetProjectionRef()
        crs = QgsCoordinateReferenceSystem(wkt)
        return crs, nb, nl, ns


    def load_via_qgis(path):
        lyr = QgsRasterLayer(path)
        nb = lyr.bandCount()
        ns = lyr.width()
        nl = lyr.height()
        crs = lyr.crs()
        return crs, nb, nl, ns

    t0 = None
    dtime = lambda t0 : np.datetime64('now') - t0

    root = r'E:\_EnMAP\temp\temp_bj\landsat\37S\EB'
    files = file_search(root, '*_sr.tif', recursive=True)
    #files = files[0:10]


    print('Load {} images with gdal...'.format(len(files)))
    t0 = np.datetime64('now')
    results_gdal = [load_via_gdal(p) for p in files]
    dt_gdal = dtime(t0)

    print('Load {} images with qgis...'.format(len(files)))
    t0 = np.datetime64('now')
    results_qgis = [load_via_qgis(p) for p in files]
    dt_qgis = dtime(t0)

    print('gdal: {} qgis: {}'.format(str(dt_gdal), str(dt_qgis)))
    for t in zip(results_gdal, results_qgis):
        assert t[0] == t[1]
        assert t[0][0].authid() == t[1][0].authid()
    print('Benchmark done')
    s =""


def initQgisEnvironment():
    global qgsApp
    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)
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



class TestFileFormatLoading(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.TS = TimeSeries()

        if False:
            cls.savedStdOut = sys.stdout
            cls.savedStdIn = sys.stdin

            cls.stdout = io.StringIO()
            cls.stderr = io.StringIO()
            sys.stdout = cls.stdout
            sys.stderr = cls.stderr

    @classmethod
    def tearDownClass(cls):
        pass
        #sys.stdout = cls.stdout
        #sys.stderr = cls.stderr

    def setUp(self):
        self.TS.clear()

    def tearDown(self):
        self.TS.clear()



    def test_loadLandsat(self):
        searchDir = jp(DIR_EXAMPLES, 'Images')
        files = file_search(searchDir, '*_L*_BOA.bsq')[0:3]
        self.TS.addFiles(files)

        self.assertEqual(len(files), len(self.TS))
        s = ""

    def test_nestedVRTs(self):
        # load VRTs pointing to another VRT pointing to Landsat imagery
        searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
        files = file_search(searchDir, '*BOA.vrt', recursive=True)[0:3]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadRapidEye(self):
        # load RapidEye
        searchDir = r'H:\RapidEye\3A'
        files = file_search(searchDir, '*.tif', recursive=True)
        files = [f for f in files if not re.search('_(udm|browse)\.tif$', f)]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadPleiades(self):
        #load Pleiades data
        searchDir = r'H:\Pleiades'
        #files = file_search(searchDir, 'DIM*.xml', recursive=True)
        files = file_search(searchDir, '*.jp2', recursive=True)[0:3]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadSentinel2(self):
        #load Sentinel-2
        searchDir = r'H:\Sentinel2'
        files = file_search(searchDir, '*MSIL1C.xml', recursive=True)
        self.TS.addFiles(files)

        #self.assertRegexpMatches(self.stderr.getvalue().strip(), 'Unable to add:')
        self.assertEqual(0, len(self.TS))  # do not add a containers
        subdatasets = []
        for file in files:
            subs = gdal.Open(file).GetSubDatasets()
            subdatasets.extend(s[0] for s in subs)
        self.TS.addFiles(subdatasets)
        self.assertEqual(len(subdatasets), len(self.TS))  # add subdatasets

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    initQgisEnvironment()

    #run tests
    if False: gdal_qgis_benchmark()
    if False: sandboxQgisBridge()
    if True: sandboxGui()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
