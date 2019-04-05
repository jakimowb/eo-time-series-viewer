# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

from eotimeseriesviewer.tests import initQgisApplication, testRasterFiles, TestObjects
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile
from eotimeseriesviewer import SpatialPoint
from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.timeseries import *
QGIS_APP = initQgisApplication()
SHOW_GUI = False and os.environ.get('CI') is None

class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_basic_behaviour(self):

        files = TestObjects.testImagePaths()
        lyr1 = QgsRasterLayer(files[0])
        self.assertTrue(lyr1.isValid())
        QgsProject.instance().addMapLayer(lyr1)

        c = QgsMapCanvas()
        c.setWindowTitle('QgsMapCanvas test')
        self.assertIsInstance(c, QgsMapCanvas)


        bExtent = 0

        def onExtentChanged():
            nonlocal bExtent
            bExtent += 1

        c.extentsChanged.connect(onExtentChanged)
        c.setExtent(lyr1.extent())

        self.assertTrue(bExtent == 1)


        c.setLayers([lyr1])
        c.setDestinationCrs(lyr1.crs())
        c.setExtent(lyr1.extent())

        if SHOW_GUI:
            c.show()
            QGIS_APP.exec_()

    def test_mapcanvas(self):
        files = testRasterFiles()
        lyr1 = QgsRasterLayer(files[0])
        lyr2 = QgsRasterLayer(files[1])



        canvas = MapCanvas()
        canvas.setWindowTitle('timeseriesviewer.MapCanvas')
        canvas.setDestinationCrs(lyr1.crs())
        canvas.setExtent(lyr1.extent())

        self.assertIsInstance(canvas, QgsMapCanvas)
        self.assertFalse(canvas.isVisible())
        self.assertFalse(canvas.isVisibleToViewport())
        canvas.show()
        self.assertTrue(canvas.isVisible())
        self.assertTrue(canvas.isVisibleToViewport())


        if SHOW_GUI:
            canvas.setExtent(canvas.fullExtent())
            QGIS_APP.exec_()


    def test_mapTools(self):

        m = MapCanvas()

        lastPos = None
        def onChanged(position:SpatialPoint):
            nonlocal lastPos
            lastPos = position
        m.sigCrosshairPositionChanged.connect(onChanged)

        center = SpatialPoint.fromMapCanvasCenter(m)
        import eotimeseriesviewer.externals.qps.maptools as mts
        m.setCrosshairVisibility(True)
        mt = mts.SpectralProfileMapTool(m)
        m.setMapTool(mt)
        self.assertTrue(m.crosshairPosition() == center)

        p2 = SpatialPoint(center.crs(), center)
        p2.setX(p2.x()+100)
        m.setCrosshairPosition(p2)
        self.assertIsInstance(lastPos, SpatialPoint)
        self.assertTrue(lastPos == p2)


    def test_rendering_flags(self):
        #img = TestObjects.inMemoryImage(ns=10000,nl=10000, nb=3)
        #need a large image on file!
        from eotimeseriesviewer.main import TimeSeriesViewer
        from eotimeseriesviewer.mapvisualization import SpatialTemporalVisualization
        TSV = TimeSeriesViewer(None)
        self.assertIsInstance(TSV, TimeSeriesViewer)
        TSV.loadExampleTimeSeries()
        self.assertIsInstance(TSV.timeSeries(), TimeSeries)
        self.assertTrue(len(TSV.timeSeries()) > 0)
        TSV.show()
        QApplication.processEvents()

        stv = TSV.spatialTemporalVis
        self.assertIsInstance(stv, SpatialTemporalVisualization)

        maps = stv.mapCanvases()
        hidden = [m for m in maps if not m.isVisibleToViewport()]
        visible = [m for m in maps if m.isVisibleToViewport()]

        self.assertTrue(len(maps) == len(visible) + len(hidden))
        self.assertTrue(len(hidden) > 0)

        if SHOW_GUI:
            QGIS_APP.exec_()

    def test_mapCanvasLayerModel(self):

        M = MapCanvasLayerModel()
        self.assertIsInstance(M, MapCanvasLayerModel)
        files = TestObjects.testImagePaths()

        from eotimeseriesviewer.timeseries import TimeSeriesSource

        p0 = TimeSeriesSource.create(files[0]).qgsMimeDataUtilsUri()
        p1 = TimeSeriesSource.create(files[1]).qgsMimeDataUtilsUri()

        self.assertTrue(len(M) == 0)
        M.insertMapLayerSources(0, [p0, p1])
        self.assertTrue(len(M) == 2)

        lyr1 = QgsRasterLayer(files[3])
        lyr2 = QgsRasterLayer(files[4])
        M.insertMapLayerSources(0, [lyr1, lyr2])

        from qgis.PyQt.QtWidgets import QTableView
        TV = QTableView()
        TV.setModel(M)

        if SHOW_GUI:
            TV.show()
            QGIS_APP.exec_()




if __name__ == "__main__":

    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()

QGIS_APP.quit()