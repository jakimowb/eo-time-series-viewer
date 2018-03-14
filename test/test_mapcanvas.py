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

from timeseriesviewer.utils import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest
from timeseriesviewer.mapcanvas import *

QGIS_APP = initQgisApplication()


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




if __name__ == "__main__":
    unittest.main()
