# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""
from __future__ import absolute_import
__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
from qgis import *
from PyQt4.QtGui import QIcon
from utilities import get_qgis_app
QGIS_APP = get_qgis_app()


class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_icon_png(self):
        """Test we can click OK."""
        from timeseriesviewer import  icon

        self.assertFalse(icon().isNull())

if __name__ == "__main__":
    suite = unittest.makeSuite(testclassResourcesTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


