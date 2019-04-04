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
from eotimeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum
from eotimeseriesviewer.temporalprofiles2d import *
from eotimeseriesviewer.profilevisualization import *
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.tests import initQgisApplication
from osgeo import ogr, osr
QGIS_APP = initQgisApplication()
SHOW_GUI = False and os.environ.get('CI') is None and not os.environ.get('CI')

class testclassUtilityTests(unittest.TestCase):
    """Test temporal profiles"""

    def setUp(self):
        """Runs before each test."""
        self.TS = TimeSeries()

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif'))
        self.TS.addSources(files)
        self.dirTmp = tempfile.mkdtemp(prefix='EOTSV_Test')

    def tearDown(self):
        """Runs after each test."""

        import shutil
        shutil.rmtree(self.dirTmp)

    def createTemporalProfiles(self):

        center = self.TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer(self.TS)

        results = []
        results.extend(lyr.createTemporalProfiles(center))
        results.extend(lyr.createTemporalProfiles(SpatialPoint(center.crs(), center.x() + 40, center.y() + 50)))
        for p in results:
            self.assertIsInstance(p, TemporalProfile)
        return results

    def test_createTemporalProfile(self):

        center = self.TS.maxSpatialExtent().spatialCenter()

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



    def test_temporalProfileLayer(self):

        lyr1 = TemporalProfileLayer(self.TS)



        extent = self.TS.maxSpatialExtent()
        center = extent.spatialCenter()

        point1 = SpatialPoint(center.crs(), center.x(), center.y() )
        point2 = SpatialPoint(center.crs(), center.x()+30, center.y()-30 )
        tps = lyr1.createTemporalProfiles([point1, point1, point2])



        self.assertTrue(len(lyr1) == 3)
        self.assertIsInstance(tps, list)
        self.assertTrue(len(tps) == 3)
        for tp in tps:
            self.assertIsInstance(tp, TemporalProfile)
        tp1, tp2, tp3 = tps
        self.assertTrue(len(list(lyr1.getFeatures())) == lyr1.featureCount())

        lyr2 = TemporalProfileLayer(self.TS)
        self.assertTrue(len(list(lyr1.getFeatures())) == lyr1.featureCount(), msg='Creation of other Temporal Profile Layers failed')

        self.assertIsInstance(tp1.geometry(), QgsGeometry)
        self.assertEqual(tp1.geometry().asWkb(), tp2.geometry().asWkb())
        self.assertNotEqual(tp1.geometry().asWkb(), tp3.geometry().asWkb())

        self.assertIsInstance(tp1.coordinate(), SpatialPoint)
        self.assertEqual(tp1.coordinate(), tp2.coordinate())
        lyr1.removeTemporalProfiles([tp1])
        self.assertTrue(len(lyr1) == 2)

        self.assertEqual(tp2, lyr1[0])

        tp = lyr1.fromSpatialPoint(tp2.coordinate())
        self.assertIsInstance(tp, TemporalProfile)
        self.assertEqual(tp, tp2)

        p = tempfile.mktemp('.shp', 'testtemporalprofiles')
        writtenFiles = lyr1.saveTemporalProfiles(p, loadMissingValues=True)
        self.assertTrue(len(writtenFiles) == 2)
        for f in writtenFiles:
            self.assertTrue(os.path.isfile(f))

        if SHOW_GUI:
            # test save-file-dialog
            writtenFiles = lyr1.saveTemporalProfiles(None)
            self.assertTrue(len(writtenFiles) == 2)
            for f in writtenFiles:
                self.assertTrue(os.path.isfile(f))

        lyr2 = TemporalProfileLayer(self.TS)


        path = os.path.join(self.dirTmp, 'testsave.shp')
        writtenFiles = lyr1.saveTemporalProfiles(path)
        self.assertTrue(len(writtenFiles) == 2)
        for p in writtenFiles:
            self.assertTrue(os.path.isfile(p))
        with open(writtenFiles[1], 'r', encoding='utf-8') as f:
            lines = f.readlines()

            self.assertTrue(len(lines) > 2)


        cb = QgsFeatureListComboBox()
        cb.setSourceLayer(lyr1)
        cb.setIdentifierField(FN_ID)
        cb.setIdentifierValue(tp.id())
        cb.setDisplayExpression('to_string("id") + \'  \' + "name"')

        cb.show()
        s = ""
        if SHOW_GUI:
            QGIS_APP.exec_()


    def test_expressions(self):
        s = ""
        tps = self.createTemporalProfiles()
        expressions = ['b1 + b2']

        for tp in tps:
            self.assertIsInstance(tp, TemporalProfile)
            tp.loadMissingData()
            tsdKeys = list(tp.mData.keys())
            for tsd in self.TS:
                self.assertIn(tsd, tsdKeys)
                s = ""

            for sensor in self.TS.sensors():
                self.assertIsInstance(sensor, SensorInstrument)
                for expression in expressions:
                    x , y = tp.dataFromExpression(sensor, expression)
                    self.assertIsInstance(x, list)
                    self.assertIsInstance(y, list)
                    self.assertEqual(len(x), len(y))
                    #self.assertTrue(len(x) > 0)

        styles = PlotStyle()


    def test_widgets(self):

        TS = self.TS
        layer = TemporalProfileLayer(self.TS)

        extent = self.TS.maxSpatialExtent()
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

        pd = ProfileViewDockUI()


        svis = SpectralTemporalVisualization(self.TS, pd)


        QgsProject.instance().addMapLayer(svis.temporalProfileLayer())
        reg = QgsGui.instance().mapLayerActionRegistry()

        moveToFeatureCenter = QgsMapLayerAction('Move to', svis.ui, QgsMapLayer.VectorLayer)

        assert isinstance(reg, QgsMapLayerActionRegistry)
        reg.setDefaultActionForLayer(svis.temporalProfileLayer(), moveToFeatureCenter)


        svis.loadCoordinate(point3)
        svis.loadCoordinate(point2)
        svis.ui.show()

        if SHOW_GUI:
            QGIS_APP.exec_()


if __name__ == "__main__":


    unittest.main()



QGIS_APP.quit()