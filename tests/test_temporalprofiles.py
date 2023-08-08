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
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QTableView

import example.Images
from eotimeseriesviewer.profilevisualization import ProfileViewDock
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyleButton
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialPoint
from eotimeseriesviewer.temporalprofiles import TemporalProfileLayer, TemporalProfile, geometryToPixel, \
    TemporalProfileLoaderTask, TemporalProfileTableModel
from eotimeseriesviewer.tests import EOTSVTestCase, TestObjects
from eotimeseriesviewer.tests import start_app
from eotimeseriesviewer.timeseries import TimeSeries, TimeSeriesSource, SensorInstrument
from qgis._core import QgsGeometry, QgsPointXY, QgsTask
from qgis.core import QgsMapLayer, QgsProject
from qgis.gui import QgsGui, QgsMapLayerAction, QgsMapLayerActionRegistry

start_app()
class TestTemporalProfiles(EOTSVTestCase):
    """Test temporal profiles"""

    def setUp(self):
        """Runs before each test."""
        super().setUp()
        self.TS = TimeSeries()

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif'))
        self.TS.addSources(files, runAsync=False)
        self.assertTrue(len(self.TS) > 0)


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
            self.assertEqual(max(px), ds.RasterXSize - 1)
            self.assertEqual(max(py), ds.RasterYSize - 1)
            self.assertEqual(len(px), tss.nl * tss.ns)

    def test_createTemporalProfile(self):

        center = self.TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(self.TS)
        tp = lyr.createTemporalProfiles(center)[0]

        self.assertIsInstance(tp, TemporalProfile)
        tp.loadMissingData()
        temporalProfiles = [tp]
        temporalProfiles.extend(lyr.createTemporalProfiles((
            SpatialPoint(center.crs(), center.x() - 50, center.y() + 50))))

        for tp in temporalProfiles:
            tp.loadMissingData()
            nd, nnd, total = tp.loadingStatus()
            self.assertEqual(total, nd + nnd)

    def test_temporalProfileLayer(self):

        lyr1 = TemporalProfileLayer()
        self.assertTrue(lyr1.crs().isValid())
        lyr1.setTimeSeries(self.TS)

        extent = self.TS.maxSpatialExtent()
        center = extent.spatialCenter()

        point1 = SpatialPoint(center.crs(), center.x(), center.y())
        point2 = SpatialPoint(center.crs(), center.x() + 30, center.y() - 30)
        tps = lyr1.createTemporalProfiles([point1, point1, point2])

        self.assertTrue(len(lyr1) == 3)
        self.assertIsInstance(tps, list)
        self.assertTrue(len(tps) == 3)
        for tp in tps:
            self.assertIsInstance(tp, TemporalProfile)
        tp1, tp2, tp3 = tps
        self.assertTrue(len(list(lyr1.getFeatures())) == lyr1.featureCount())

        def onLoaded(results, task):
            self.assertIsInstance(results, bool)
            self.assertIsInstance(task, QgsTask)

        def onUpdated(profiles):
            self.assertIsInstance(profiles, list)
            for p in profiles:
                self.assertIsInstance(p, TemporalProfile)
                self.assertTrue(p in lyr1)

        # load data
        lyr1.sigTemporalProfilesUpdated.connect(onUpdated)
        task = TemporalProfileLoaderTask(lyr1, callback=onLoaded)
        task.finished(task.run())

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
                    # self.assertTrue(len(x) > 0)

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
        tv.close()
        QgsProject.instance().removeAllMapLayers()

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
        # tps = layer.createTemporalProfiles([point1])
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

        self.showGui([pd])
        QgsProject.instance().removeAllMapLayers()


if __name__ == "__main__":
    unittest.main(buffer=False)
    exit(0)
