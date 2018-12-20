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

from timeseriesviewer.tests import initQgisApplication, testRasterFiles
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from timeseriesviewer.mapcanvas import *

resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True

class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_mapcanvas(self):
        m = MapCanvas()
        self.assertIsInstance(m, QgsMapCanvas)
        self.assertFalse(m.isVisible())
        self.assertFalse(m.isVisibleToViewport())

        files = testRasterFiles()
        lyr1 = QgsRasterLayer(files[0])


        m.setLazyLayers(files[0:2])

        self.assertTrue(len(m.layers()) == 0)
        m.timedRefresh()
        self.assertTrue(len(m.layers()) == 2)

        m.show()

        self.assertTrue(m.isVisible())
        self.assertTrue(m.isVisibleToViewport())

        m.timedRefresh()
        self.assertTrue(len(m.layers()) == 2)

        m.setLazyLayers([lyr1])



    def test_mapTools(self):

        m = MapCanvas()

        lastPos = None
        def onChanged(position:SpatialPoint):
            nonlocal lastPos
            lastPos = position
        m.sigCrosshairPositionChanged.connect(onChanged)

        center = SpatialPoint.fromMapCanvasCenter(m)
        import timeseriesviewer.maptools as mts
        m.setCrosshairVisibility(True)
        mt = mts.SpectralProfileMapTool(m)
        m.setMapTool(mt)
        self.assertTrue(m.crosshairPosition() == center)

        p2 = center.copy()
        p2.setX(p2.x()+100)
        m.setCrosshairPosition(p2)
        self.assertIsInstance(lastPos, SpatialPoint)
        self.assertTrue(lastPos == p2)


    def test_rendering_flags(self):
        #img = TestObjects.inMemoryImage(ns=10000,nl=10000, nb=3)
        #need a large image on file!
        from timeseriesviewer.main import TimeSeriesViewer
        from timeseriesviewer.mapvisualization import SpatialTemporalVisualization
        TSV = TimeSeriesViewer(None)
        self.assertIsInstance(TSV, TimeSeriesViewer)
        TSV.loadExampleTimeSeries()
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


if __name__ == "__main__":
    unittest.main()
