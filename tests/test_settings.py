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

from timeseriesviewer.tests import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from timeseriesviewer.mapcanvas import *
from timeseriesviewer.crosshair import *
from timeseriesviewer.utils import *
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication()

from timeseriesviewer.settings import *
SHOW_GUI = True

class testclassSettingsTest(unittest.TestCase):
    """Test resources work."""
    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass

    def test_Dialog(self):

        d = SettingsDialog()
        self.assertIsInstance(d, QDialog)
        r = d.exec_()

        self.assertTrue(r in [QDialog.Accepted, QDialog.Rejected])




if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()
