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
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum
from timeseriesviewer.temporalprofiles2d import *
from timeseriesviewer.profilevisualization import *
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

        lyr = TemporalProfileLayer(self.TS)
        tp = lyr.createTemporalProfiles(center)[0]


        self.assertIsInstance(tp, TemporalProfile)
        tp.loadMissingData(False)
        temporalProfiles = [tp]
        temporalProfiles.extend(lyr.createTemporalProfiles((SpatialPoint(center.crs(), center.x() - 50, center.y() + 50))))

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

    def test_temporalProfileLayer(self):

        col = TemporalProfileLayer(self.TS)

        extent = self.TS.getMaxSpatialExtent()
        center = extent.spatialCenter()

        point1 = SpatialPoint(center.crs(), center.x(), center.y() )
        point2 = SpatialPoint(center.crs(), center.x()+30, center.y()-30 )
        tps = col.createTemporalProfiles([point1, point1, point2])

        self.assertTrue(len(col) == 3)
        self.assertIsInstance(tps, list)
        self.assertTrue(len(tps) == 3)
        for tp in tps:
            self.assertIsInstance(tp, TemporalProfile)
        tp1, tp2, tp3 = tps


        self.assertIsInstance(tp1.geometry(), QgsGeometry)
        self.assertEqual(tp1.geometry().asWkb(), tp2.geometry().asWkb())
        self.assertNotEqual(tp1.geometry().asWkb(), tp3.geometry().asWkb())

        self.assertIsInstance(tp1.coordinate(), SpatialPoint)
        self.assertEqual(tp1.coordinate(), tp2.coordinate())
        col.removeTemporalProfiles([tp1])
        self.assertTrue(len(col) == 2)

        self.assertEqual(tp2, col[0])

        tp = col.fromSpatialPoint(tp2.coordinate())
        self.assertIsInstance(tp, TemporalProfile)
        self.assertEqual(tp, tp2)


        cb = QgsFeatureListComboBox()
        cb.setSourceLayer(col)
        cb.setIdentifierField(FN_ID)
        cb.setIdentifierValue(tp.id())
        cb.setDisplayExpression('to_string("id") + \'  \' + "name"')

        cb.show()
        s = ""
        QGIS_APP.exec_()

    def test_widgets(self):

        TS = self.TS
        layer = TemporalProfileLayer(self.TS)

        extent = self.TS.getMaxSpatialExtent()
        center = extent.spatialCenter()

        point1 = SpatialPoint(center.crs(), center.x(), center.y())
        point2 = SpatialPoint(center.crs(), center.x() + 30, center.y() - 30)
        point3 = SpatialPoint(center.crs(), center.x() + 30, center.y() + 30)
        points = [point1, point2, point3]
        n = len(points)
        #tps = layer.createTemporalProfiles([point1])
        tps = layer.createTemporalProfiles(points)
        self.assertIsInstance(tps, list)
        self.assertEqual(len(tps), n)
        model = TemporalProfileTableModel(layer)
        fmodel = TemporalProfileTableFilterModel(model)

        self.assertEqual(model.rowCount(), n)
        self.assertEqual(fmodel.rowCount(), n)
        tv = TemporalProfileTableView()
        tv.setModel(fmodel)
        tv.show()

        #i = ProfileViewDockUI()


        svis = SpectralTemporalVisualization(self.TS)
        svis.ui.show()
        svis.loadCoordinate(point3)
        svis.loadCoordinate(point2)
        s = ""
        QGIS_APP.exec_()


if __name__ == "__main__":
    unittest.main()



