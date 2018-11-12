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

from timeseriesviewertesting import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from timeseriesviewer.mapcanvas import *

resourceDir = os.path.join(DIR_REPO,'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)


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
        m.show()

        self.assertIsInstance(m.mLayerModel, MapCanvasLayerModel)


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





if __name__ == "__main__":
    unittest.main()
