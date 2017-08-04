# coding=utf-8
"""Safe Translations Test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""
from __future__ import absolute_import
from utilities import get_qgis_app

__author__ = 'ismailsunni@yahoo.co.id'
__date__ = '12/10/2011'
__copyright__ = ('Copyright 2012, Australia Indonesia Facility for '
                 'Disaster Reduction')
import unittest
import os

QGIS_APP = get_qgis_app()

from timeseriesviewer.plotstyling import *


class TestPlotStyling(unittest.TestCase):
    """Test translations work."""


    def test_plotstyles(self):
        #qgsApp = QGIS_APP()

        import pickle
        s1 = PlotStyle()
        s2 = pickle.loads(pickle.dumps(s1))
        self.assertEqual(s1,s2)



if __name__ == "__main__":
    suite = unittest.makeSuite(TestPlotStyling)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
