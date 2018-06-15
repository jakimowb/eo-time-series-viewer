# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 :
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
import unittest, tempfile

from timeseriesviewer.stackedbandinput import *
from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, Img_2014_05_07_LC82270652014127LGN00_BOA
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


    def test_dialog(self):
        d = StackedBandInputDialog()
        d.addSources([Img_2014_05_07_LC82270652014127LGN00_BOA, Img_2014_06_16_LE72270652014167CUB00_BOA])
        d.show()

        QGIS_APP.exec_()
        pass
if __name__ == "__main__":
    unittest.main()
