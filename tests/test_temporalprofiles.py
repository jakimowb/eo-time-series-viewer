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
import tempfile
import sys
import os
import xmlrunner
from qgis import *
from qgis.gui import *
from qgis.PyQt.QtGui import QIcon
import example.Images
from eotimeseriesviewer.timeseries import TimeSeries, TimeSeriesDate
from eotimeseriesviewer.temporalprofiles import *
from eotimeseriesviewer.profilevisualization import *
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.tests import EOTSVTestCase, TestObjects
from osgeo import ogr, osr



class TestTemporalProfiles(EOTSVTestCase):
    """Test temporal profiles"""

    def setUp(self):
        """Runs before each test."""
        super().setUp()
        self.TS = TimeSeries()

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif'))
        self.TS.addSources(files, runAsync=False)
        self.assertTrue(len(self.TS) > 0)
        self.dirTmp = tempfile.mkdtemp(prefix='EOTSV_Test')

    def tearDown(self):
        """Runs after each test."""

        import shutil
        shutil.rmtree(self.dirTmp)

    def createTemporalProfiles(self):

        center = self.TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(self.TS)
        results = []
        results.extend(lyr.createTemporalProfiles(center))
        results.extend(lyr.createTemporalProfiles(SpatialPoint(center.crs(), center.x() + 40, center.y() + 50)))
        for p in results:
            self.assertIsInstance(p, TemporalProfile)
        return results

    def test_temporalprofileloadertaskinfo(self):

        timeSeries = TestObjects.createTimeSeries()
        self.assertIsInstance(timeSeries, TimeSeries)
        center = timeSeries.maxSpatialExtent().spatialCenter()
        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(timeSeries)
        tp1 = lyr.createTemporalProfiles(center)[0]
        self.assertIsInstance(tp1, TemporalProfile)

        tss = timeSeries[0][0]
        self.assertIsInstance(tss, TimeSeriesSource)


    def test_geometryToPixel(self):

        timeSeries = TestObjects.createTimeSeries()
        tss = timeSeries[0][0]
        self.assertIsInstance(tss, TimeSeriesSource)
        extent = tss.spatialExtent()
        polygon = QgsGeometry.fromWkt(extent.asWktPolygon())
        center = extent.spatialCenter()

        ds = tss.asDataset()

        px_size_x, px_size_y = tss.rasterUnitsPerPixelX(), tss.rasterUnitsPerPixelY()
        # convert points to pixel coordinates
        px, py = geometryToPixel(ds, center)
        self.assertEqual(len(px), len(py))
        self.assertEqual(px, [int(0.5 * ds.RasterXSize)])
        self.assertEqual(py, [int(0.5 * ds.RasterYSize)])

        # no pixel-coordinate for out of bounds points :

        oobPoints = [
            QgsPointXY(extent.xMinimum() - 0.5 * px_size_x, center.y()),
            QgsPointXY(center.x(), extent.yMaximum() + 0.5 * px_size_y),
            QgsPointXY(center.x(), extent.yMinimum() - 0.5 * px_size_y),
            QgsPointXY(extent.xMaximum() + 0.5 * px_size_x, center.y())
        ]

        for oobPt in oobPoints:
            px, py = geometryToPixel(ds, oobPt)
            self.assertEqual(len(px), len(py))
            self.assertEqual(px, [])
            self.assertEqual(py, [])

        # return pixel coordinate for pixels covered by polygons:
        # A: extent -> return each pixel
        for geom in [polygon, extent]:
            px, py = geometryToPixel(ds, geom)
            self.assertEqual(len(px), len(py))
            self.assertEqual(min(px), 0)
            self.assertEqual(min(py), 0)
            self.assertEqual(max(px), ds.RasterXSize-1)
            self.assertEqual(max(py), ds.RasterYSize-1)
            self.assertEqual(len(px), tss.nl * tss.ns)

    def test_createTemporalProfile(self):

        center = self.TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(self.TS)
        tp = lyr.createTemporalProfiles(center)[0]

        self.assertIsInstance(tp, TemporalProfile)
        tp.loadMissingData()
        temporalProfiles = [tp]
        temporalProfiles.extend(lyr.createTemporalProfiles((SpatialPoint(center.crs(), center.x() - 50, center.y() + 50))))

        for tp in temporalProfiles:
            tp.loadMissingData()
            nd, nnd, total = tp.loadingStatus()
            self.assertEqual(total, nd+nnd)

    def test_temporalProfileLayer(self):

        lyr1 = TemporalProfileLayer()
        lyr1.setTimeSeries(self.TS)

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

        def onLoaded(results):
            self.assertIsInstance(results, list)
            for r in results:
                self.assertIsInstance(r, TemporalProfileLoaderTaskResult)
                self.assertTrue(r.mTSD in lyr1.timeSeries())
                s = ""

        def onUpdated(profiles, sensor):
            self.assertIsInstance(sensor, SensorInstrument)
            self.assertTrue(sensor in lyr1.timeSeries().sensors())
            for p in profiles:
                self.assertIsInstance(p, TemporalProfile)
                self.assertTrue(p in lyr1)
        # load data
        lyr1.sigTemporalProfilesUpdated.connect(onUpdated)
        task = TemporalProfileLoaderTask(lyr1)
        task.sigProfilesLoaded.connect(onLoaded)
        task.run()

        lyr1.loadMissingBandInfos(run_async=False)

        updated_sensors = set()
        updated_profiles = set()

        def onUpdated(profiles, sensor):
            self.assertIsInstance(profiles, list)
            self.assertIsInstance(sensor, SensorInstrument)
            for p in profiles:
                self.assertIsInstance(p, TemporalProfile)
                self.assertTrue(p in lyr1.mProfiles.values())
            updated_profiles.update(profiles)
            updated_sensors.update([sensor])

        lyr1.sigTemporalProfilesUpdated.connect(onUpdated)
        lyr1.loadMissingBandInfos(run_async=False)

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
                    x, y = tp.dataFromExpression(sensor, expression)
                    self.assertIsInstance(x, list)
                    self.assertIsInstance(y, list)
                    self.assertEqual(len(x), len(y))
                    #self.assertTrue(len(x) > 0)



    def test_plotstyltable(self):

        btn = PlotStyleButton()
        style = btn.plotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        btn.setPlotStyle(style)
        self.showGui(btn)


    def test_profilesettings(self):

        from eotimeseriesviewer.profilevisualization import PlotSettingsTableView

        tv = PlotSettingsTableView()
        self.assertIsInstance(tv, QTableView)
        self.showGui(tv)

    def test_profiledock(self):

        ts = TestObjects.createTimeSeries()
        w = ProfileViewDock()
        w.setTimeSeries(ts)

        lyr = w.temporalProfileLayer()
        self.assertIsInstance(lyr, TemporalProfileLayer)

        extent = ts.maxSpatialExtent()
        center = extent.spatialCenter()

        point1 = SpatialPoint(center.crs(), center.x(), center.y())
        point2 = SpatialPoint(center.crs(), center.x() + 30, center.y() - 30)
        point3 = SpatialPoint(center.crs(), center.x() + 30, center.y() + 30)
        points = [point1, point2, point3]
        w.loadCoordinate(points)

        timer = QTimer()
        timer.timeout.connect(self.closeBlockingWidget)
        timer.start(1000)
        # test actions
        for a in w.mActionsTP:
            a.trigger()


        self.showGui(w)

    def test_profiledock2(self):

        TS = self.TS
        layer = TemporalProfileLayer()
        layer.setTimeSeries(self.TS)
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


        self.assertEqual(model.rowCount(), n)

        pd = ProfileViewDock()
        pd.setTimeSeries(self.TS)
        QgsProject.instance().addMapLayer(pd.temporalProfileLayer())
        reg = QgsGui.instance().mapLayerActionRegistry()

        moveToFeatureCenter = QgsMapLayerAction('Move to', pd, QgsMapLayer.VectorLayer)

        assert isinstance(reg, QgsMapLayerActionRegistry)
        reg.setDefaultActionForLayer(pd.temporalProfileLayer(), moveToFeatureCenter)
        pd.loadCoordinate(point3)
        pd.loadCoordinate(point2)

        #from eotimeseriesviewer.externals.qps.resources import ResourceBrowser
        #browser = ResourceBrowser()

        self.showGui([pd])


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)

