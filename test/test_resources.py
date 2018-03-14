# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
from qgis import *
from PyQt5.QtGui import QIcon
from timeseriesviewer import file_search
from timeseriesviewer.utils import initQgisApplication
QGIS_APP = initQgisApplication()


class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_icon(self):
        """Test we can click OK."""
        from timeseriesviewer import icon, DIR_UI
        self.assertFalse(icon().isNull())

        iconSVGs = file_search(os.path.join(DIR_UI, 'icons'), '*.svg')
        #:/timeseriesviewer/icons/IconTimeSeries.svg
        iconSVGs = [s.replace(DIR_UI,':').replace('\\','/') for s in iconSVGs]
        for resource in iconSVGs:
            icon = QIcon(resource)
            self.assertFalse(icon.isNull())



if __name__ == "__main__":
    unittest.main()



