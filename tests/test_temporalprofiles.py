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

import os
import re
import unittest
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QTableView
from qgis.core import QgsGeometry, QgsMapLayer, QgsPointXY, QgsProject, QgsTask
from qgis.gui import QgsGui, QgsMapLayerAction, QgsMapLayerActionRegistry
from eotimeseriesviewer.profilevisualization import ProfileViewDock
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyleButton
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialPoint
from eotimeseriesviewer.temporalprofiles import geometryToPixel, TemporalProfile, TemporalProfileLayer, \
    TemporalProfileLoaderTask, TemporalProfileTableModel
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from eotimeseriesviewer.timeseries import SensorInstrument, TimeSeries, TimeSeriesSource

start_app()


class TestTemporalProfiles(EOTSVTestCase):
    """Test temporal profiles"""

    def setUp(self):
        """Runs before each test."""
        super().setUp()

    def createTemporalProfiles(self):
        TS = TestObjects.createTimeSeries()
        center = TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(TS)
        results = []
        results.extend(lyr.createTemporalProfiles(center))
        results.extend(lyr.createTemporalProfiles(SpatialPoint(center.crs(), center.x() + 40, center.y() + 50)))
        for p in results:
            self.assertIsInstance(p, TemporalProfile)
        return results

    def test_temporalprofileloadertaskinfo1(self):

        timeSeries = TestObjects.createTimeSeries()
        self.assertIsInstance(timeSeries, TimeSeries)
        center = timeSeries.maxSpatialExtent().spatialCenter()
        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(timeSeries)
        tp1 = lyr.createTemporalProfiles(center)[0]
        self.assertIsInstance(tp1, TemporalProfile)

        tss = timeSeries[0][0]
        self.assertIsInstance(tss, TimeSeriesSource)

    DIR_FORCE = Path('D:\EOTSV\FORCE_CUBE')

    @unittest.skipIf(DIR_FORCE.is_dir(), f'Missing FORCE dir: {DIR_FORCE}')
    def test_temporalprofileloadertaskinfo2(self):

        if not os.path.isdir(self.DIR_FORCE):
            return

        timeSeries = TimeSeries()

        files = file_search(self.DIR_FORCE, re.compile(r'.*_BOA.tif$'), recursive=True)
        timeSeries.addSources(files, runAsync=False)

        self.assertIsInstance(timeSeries, TimeSeries)
        center = timeSeries.maxSpatialExtent().spatialCenter()
        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(timeSeries)
        tp1: TemporalProfile = lyr.createTemporalProfiles(center)[0]
        self.assertIsInstance(tp1, TemporalProfile)
        tp1.loadMissingData()

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
        TS = TestObjects.createTimeSeries()
        center = TS.maxSpatialExtent().spatialCenter()

        lyr = TemporalProfileLayer()
        lyr.setTimeSeries(TS)
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
        TS = TestObjects.createTimeSeries()
        lyr1 = TemporalProfileLayer()
        self.assertTrue(lyr1.crs().isValid())
        lyr1.setTimeSeries(TS)

        extent = TS.maxSpatialExtent()
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
        TS = TestObjects.createTimeSeries()
        tps = self.createTemporalProfiles()
        expressions = ['b1 + b2']

        for tp in tps:
            self.assertIsInstance(tp, TemporalProfile)
            tp.loadMissingData()
            tsdKeys = list(tp.mData.keys())
            for tsd in TS:
                self.assertIn(tsd, tsdKeys)
                s = ""

            for sensor in TS.sensors():
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

        TS = TestObjects.createTimeSeries()
        layer = TemporalProfileLayer()
        layer.setTimeSeries(TS)
        extent = TS.maxSpatialExtent()
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
        pd.setTimeSeries(TS)
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
