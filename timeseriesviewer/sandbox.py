from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
import logging, io
logger = logging.getLogger(__name__)
from osgeo import gdal, ogr
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

    S.spatialTemporalVis.MVC.createMapView()
    import example.Images
    #imgs = file_search(jp(DIR_EXAMPLES,'Images'),'*.bsq')
    searchDir = jp(DIR_EXAMPLES, 'Images')

    #searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\01_UncutVRT'
    #searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
    imgs = file_search(searchDir, '*.bsq', recursive=True)[0:2]

    #imgs = [example.Images.Img_2014_07_10_LC82270652014191LGN00_BOA]
    S.addTimeSeriesImages(imgs)

    SP = SignalPrinter(S.spatialTemporalVis)


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
    import qgis.utils
    qgis.utils.iface = fakeQGIS

    S = TimeSeriesViewer(fakeQGIS)
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

class SignalPrinter(object):

    def __init__(self,  objs=None):

        self.signals = dict()
        if objs:
            self.addObject(objs)

    def addObject(self, obj):
        import inspect
        if isinstance(obj, list):
            for o in obj:
                self.addObject(o)
        elif isinstance(obj, QObject):
            t = QThread.currentThread()
            metaObject = obj.metaObject()
            for i in range(metaObject.methodCount()):
                method = metaObject.method(i)
                assert isinstance(method, QMetaMethod)
                if method.methodType() == QMetaMethod.Signal:
                    sigName = str(method.signature()).split('(')[0]
                    sig = getattr(obj, sigName)
                    if obj not in self.signals:
                        self.signals[obj] = []
                    self.signals[obj].append(sig)

            for sig in self.signals[obj]:
                sig.connect(lambda obj=obj, sig=sig, *args , **kwds : self.printSignal(obj, sig, *args, **kwds))
            s = ""

    def printSignal(self, o, sig, *args, **kwds):
        info = '{}'.format(sig.signal[1:])
        if len(args) > 0:
            info += ' {}'.format(str(args))
        if len(kwds) > 0:
            info += ' {}'.format(str(kwds))
        print(info)

def initQgisEnvironment():

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)
    # prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/Library/Frameworks/GDAL.framework/Versions/2.1/Resources/gdal'
        QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
        QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    gdal.SetConfigOption('VRT_SHARED_SOURCE', '0')  # !important. really. do not change this.
    #register resource files (all)
    import timeseriesviewer.ui
    dn = os.path.dirname(timeseriesviewer.ui.__file__)
    import timeseriesviewer.ui.qgis_icons_py2



    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()
    return qgsApp

def sandboxTestdata():
    from timeseriesviewer.main import TimeSeriesViewer

    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    S.spatialTemporalVis.MVC.createMapView()
    import example.Images
    searchDir = jp(DIR_EXAMPLES, 'Images')
    imgs = file_search(searchDir, '*.bsq', recursive=True)#[0:1]  # [0:5]

    S.addTimeSeriesImages(imgs)

def sandboxMultitemp2017(qgis=False):
    from timeseriesviewer.main import TimeSeriesViewer

    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES

    iface = None
    if qgis:
        iface = QgisFake()

    S = TimeSeriesViewer(iface)
    S.ui.show()
    S.run()

    S.spatialTemporalVis.MVC.createMapView()
    import example.Images

    if True:
        searchDir = r'O:\SenseCarbonProcessing\BJ_Multitemp2017\01_Data\Landsat'
        imgs = file_search(searchDir, 'LC8*.vrt', recursive=True)#[0:5]
        S.addTimeSeriesImages(imgs)

    if True:
        searchDir = r'O:\SenseCarbonProcessing\BJ_Multitemp2017\01_Data\CBERS'
        imgs = file_search(searchDir, 'CBERS*.vrt', recursive=True)#[0:1]
        S.addTimeSeriesImages(imgs)

        searchDir = r'O:\SenseCarbonProcessing\BJ_Multitemp2017\01_Data\RapidEye'
        imgs = file_search(searchDir, 're*.vrt', recursive=True)#[0:1]
        S.addTimeSeriesImages(imgs)


if __name__ == '__main__':
    import site, sys, pyqtgraph
    #add site-packages to sys.path as done by enmapboxplugin.py

    qgsApp = initQgisEnvironment()

    #run tests
    if False: gdal_qgis_benchmark()
    if True: sandboxQgisBridge()
    if False: sandboxGui()
    if False: sandboxTestdata()
    if False: sandboxMultitemp2017(qgis=True)

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
