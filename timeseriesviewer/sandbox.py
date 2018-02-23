# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import, unicode_literals
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


    searchDir = jp(DIR_EXAMPLES, 'Images')
    imgs = file_search(searchDir, '*.tif', recursive=True)[:]
    #searchDir = r'O:\SenseCarbonProcessing\09_testFolder\HLS-data-HUB-viewer\DE\L30\2016\33UUT'
    #imgs = file_search(searchDir, '*OLI.img')


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

    def legendInterface(self):
        QgsLegendInterface
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
    fakeQGIS.addVectorLayer(example.exampleEvents)
    fakeQGIS.addRasterLayer(example.Images.Img_2014_08_03_LE72270652014215CUB00_BOA)

    S.loadImageFiles([example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA])
    S.ui.resize(600,600)
    S.ui.dockRendering.gbQgsVectorLayer.setChecked(True)

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
    """
    A printer to print Qt Signals
    """

    def __init__(self,  objs=None):

        self.signals = dict()
        if objs:
            self.addObject(objs)

    def addObject(self, obj):
        """
        Adds an object to the printer. In case of QObjects, its QSignals will get connected to print emitted signals.
        :param obj:
        :return:
        """
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

def sandboxTestdata():
    from timeseriesviewer.main import TimeSeriesViewer

    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    S.spatialTemporalVis.MVC.createMapView()
    S.spatialTemporalVis.MVC.createMapView()

    import timeseriesviewer.profilevisualization
    timeseriesviewer.profilevisualization.DEBUG = True
    import example.Images
    if True:
        S.loadExampleTimeSeries()
    else:
        imgs = [example.Images.Img_2014_08_11_LC82270652014223LGN00_BOA,
                example.Images.re_2014_08_26]



        S.addTimeSeriesImages(imgs)

    from example import exampleEvents
    ml  = QgsVectorLayer(exampleEvents, 'labels', 'ogr', True)
    QgsMapLayerRegistry.instance().addMapLayer(ml)


if __name__ == '__main__':
    import site, sys, pyqtgraph
    # add site-packages to sys.path as done by enmapboxplugin.py
    from timeseriesviewer.utils import initQgisApplication
    qgsApp = initQgisApplication()
    import timeseriesviewer
    timeseriesviewer.DEBUG = True
    #run tests
    if False: gdal_qgis_benchmark()
    if False: sandboxQgisBridge()
    if False: sandboxGui()

    if True: sandboxTestdata()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
