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
from timeseriesviewer.crosshair import *
from timeseriesviewer.utils import *
resourceDir = os.path.join(DIR_REPO,'qgisresources')
QGIS_APP = initQgisApplication()

SHOW_GUI = True

class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass

    def test_CrosshairWidget(self):

        ds = TestObjects.inMemoryImage()

        lyr = QgsRasterLayer(ds.GetFileList()[0])
        c = QgsMapCanvas()
        store = QgsMapLayerStore()
        store.addMapLayer(lyr)
        c.setLayers([lyr])
        c.setDestinationCrs(lyr.crs())
        c.setExtent(lyr.extent())

        w = CrosshairWidget()
        self.assertIsInstance(w, CrosshairWidget)
        self.assertIsInstance(w.mapCanvas, QgsMapCanvas)
        self.assertEqual(len(w.mapCanvas.layers()), 0)

        w.copyCanvas(c)






        if SHOW_GUI:
            QGIS_APP.exec_()

    def test_CrosshairDialog(self):

        pass




if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()
