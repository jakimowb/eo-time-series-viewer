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

import unittest, tempfile, sys, os
from qgis import *
from qgis.gui import *
from PyQt5.QtGui import QIcon
import example.Images
from timeseriesviewer import file_search
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum
from timeseriesviewer.temporalprofiles2d import TemporalProfile, saveTemporalProfiles
from timeseriesviewer.utils import *
from osgeo import ogr, osr
QGIS_APP = initQgisApplication()

class testclassUtilityTests(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        self.TS = TimeSeries()

        files = file_search(os.path.dirname(example.Images.__file__), '*.tif')
        self.TS.addFiles(files)
        self.dirTmp = tempfile.mkdtemp(prefix='EOTSV_Test')


    def tearDown(self):
        """Runs after each test."""

        import shutil
        shutil.rmtree(self.dirTmp)


    def test_createTemporalProfile(self):

        center = self.TS.getMaxSpatialExtent().spatialCenter()


        tp = TemporalProfile(self.TS, center)
        self.assertIsInstance(tp, TemporalProfile)
        tp.setName('TestName')
        self.assertEqual(tp.name(), 'TestName')
        tp.loadMissingData(False)
        temporalProfiles = [tp]
        temporalProfiles.append(TemporalProfile(self.TS, SpatialPoint(center.crs(), center.x() - 50, center.y() + 50)))

        for tp in temporalProfiles:
            tp.loadMissingData()
            nd, nnd, total = tp.loadingStatus()
            self.assertEqual(total, nd+nnd)


        path = os.path.join(self.dirTmp, 'testsave.csv')
        saveTemporalProfiles(temporalProfiles,path, mode='all')

        self.assertTrue(os.path.isfile(path))
        file = open(path, 'r')
        lines = file.readlines()
        file.close()
        self.assertTrue(len(lines) > 2)


        path = os.path.join(self.dirTmp, 'testsave.shp')
        saveTemporalProfiles(temporalProfiles, path, mode='all')

        ds = ogr.Open(path)
        self.assertIsInstance(ds, ogr.DataSource)
        self.assertEqual(ds.GetDriver().GetDescription(), 'ESRI Shapefile')
        lyr = ds.GetLayer(0)
        self.assertIsInstance(lyr, ogr.Layer)
        #self.assertEqual(lyr.GetFeatureCount(), len(lines)-1)

if __name__ == "__main__":
    unittest.main()



