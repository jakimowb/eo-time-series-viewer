# coding=utf-8

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2024-09-08'
__copyright__ = 'Copyright 2024, Benjamin Jakimow'

import os
import unittest
from pathlib import Path

from PyQt5.QtWidgets import QComboBox
from qgis._core import QgsFeature, QgsProject

from qgis.core import QgsCoordinateReferenceSystem, QgsField, QgsFields, QgsRasterLayer, QgsVectorLayer
from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.temporalprofile.visualization import TemporalProfileDock
from eotimeseriesviewer.temporalprofile.tableview import PlotSettingsTableModel, PlotSettingsTableView, \
    PlotSettingsTableViewWidgetDelegate
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, TemporalProfileLayerProxyModel, \
    TemporalProfileUtils
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects

start_app()


class TestTemporalProfilesV2(EOTSVTestCase):
    """Test temporal profiles"""

    def test_load_timeseries_profiledata(self):
        files = self.exampleRasterFiles()[1:]

        lyr1 = QgsRasterLayer(files[0])
        self.assertTrue(lyr1.isValid())
        pt = SpatialPoint.fromMapLayerCenter(lyr1)

        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        pt = pt.toCrs(crs)
        points = [pt]

        nFiles = len(files)
        info = dict(id=1)
        task = LoadTemporalProfileTask(files, points, crs=crs, info=info)
        task.run()

        profiles = task.profiles()

        self.assertEqual(len(profiles), len(points))
        for profile in profiles:
            self.assertIsInstance(profile, dict)

            sources = profile[TemporalProfileUtils.Source]
            values = profile[TemporalProfileUtils.Values]
            for src, val in zip(sources, values):
                lyr = QgsRasterLayer(src)
                self.assertTrue(lyr.isValid())
                self.assertEqual((len(val)), lyr.bandCount())
                self.assertTrue(None not in val)
            profileJson = TemporalProfileUtils.profileJsonFromDict(profile)
            profile2 = TemporalProfileUtils.profileDictFromJson(profileJson)

            self.assertEqual(profile, profile2)

    @unittest.skipIf('FORCE_CUBE' not in os.environ, 'FORCE_CUBE is undefined')
    def test_load_profile_FORCE(self):

        def onProgress(progress):

            if progress < 100:
                print(f'\r{progress: 0.2f}', end='')
            else:
                print(f'\r{progress: 0.2f}')

        path_cube = Path(os.environ['FORCE_CUBE'])
        assert path_cube.is_dir()
        for tileDir in FORCEUtils.tileDirs(path_cube):
            files = FORCEUtils.productFiles(tileDir, 'BOA')
            lyr = QgsRasterLayer(files[0].as_posix())
            self.assertTrue(lyr.isValid())
            pt = SpatialPoint.fromMapLayerCenter(lyr)
            files = files[0:5]
            task = LoadTemporalProfileTask(files, [pt], pt.crs())
            task.progressChanged.connect(onProgress)
            task.run()
            cache = task.mCache
            profiles1 = task.profiles()
            for p in profiles1:
                self.assertTrue(TemporalProfileUtils.isProfileDict(p))
                success, err = TemporalProfileUtils.verifyProfile(p)
                self.assertTrue(success, msg=err)
            print(f'Run 1: tile {tileDir}: \nduration {task.loadingTime()}')
            nTotal = len(files)
            for k, v in task.mTimeIt.items():
                print(f'Avg {k}: {v}')

            task = LoadTemporalProfileTask(files, [pt], pt.crs(), cache=cache)
            task.progressChanged.connect(onProgress)
            task.run()
            profiles2 = task.profiles()
            print(f'Run 2: tile {tileDir} (cached layer infos): \nduration: {task.loadingTime()}')
            nTotal = len(files)
            for k, v in task.mTimeIt.items():
                print(f'Avg {k}: {v}')

            s = ""
        s = ""

    def test_load_timeseries_profiledata_async(self):

        pass

    def test_calc_indices(self):

        pass

    def test_plotSettinsTableModel(self):

        timeSeries = TestObjects.createTimeSeries()
        layer = TestObjects.createProfileLayer(timeSeries)
        model = PlotSettingsTableModel(layer, timeSeries)
        view = PlotSettingsTableView()
        delegate = PlotSettingsTableViewWidgetDelegate(view)
        view.setItemDelegate(delegate)
        view.setModel(model)

        self.showGui(view)

    def test_temporal_profile_field(self):

        field = TemporalProfileUtils.createProfileField('myProfiles')
        self.assertIsInstance(field, QgsField)
        self.assertTrue(TemporalProfileUtils.isProfileField(field))

    def test_create_temporal_profile_layer(self):

        lyr = TemporalProfileUtils.createProfileLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        self.assertEqual(lyr.featureCount(), 0)

        tpFields = TemporalProfileUtils.temporalProfileFields(lyr.fields())
        self.assertIsInstance(tpFields, QgsFields)
        self.assertTrue(tpFields.count() > 0)
        for field in tpFields:
            self.assertTrue(TemporalProfileUtils.isProfileField(field))

    def test_TemporalProfileUtils(self):

        lyr = TestObjects.createProfileLayer()

        project = QgsProject()
        project.addMapLayer(lyr)

        layers = TemporalProfileUtils.profileLayers(project)
        self.assertIsInstance(layers, list)
        self.assertTrue(len(layers) == 1 and layers[0] == lyr)

        self.assertTrue(lyr.featureCount() > 0)
        self.assertTrue(TemporalProfileUtils.isProfileLayer(lyr))

        fields = TemporalProfileUtils.profileFields(lyr)
        self.assertTrue(fields.count() == 1)
        for field in fields:
            self.assertTrue(TemporalProfileUtils.isProfileField(field))

            for f in lyr.getFeatures():
                f: QgsFeature
                dump = TemporalProfileUtils.profileDict(f.attribute(field.name()))
                self.assertTrue(TemporalProfileUtils.isProfileDict(dump))

    def test_TemporalProfileLayerProxyModel(self):

        layers = [
            TestObjects.createProfileLayer(),
            TestObjects.createVectorLayer(),
            TestObjects.createRasterLayer()
        ]
        project = QgsProject()
        project.addMapLayers(layers)

        model = TemporalProfileLayerProxyModel()
        model.setProject(project)

        self.assertTrue(model.rowCount() == 1)

        lyr = TestObjects.createProfileLayer()
        lyr.setName('Layer 2')
        project.addMapLayer(lyr)
        self.assertTrue(model.rowCount() == 2)

        cb = QComboBox()
        cb.setModel(model)

        self.showGui(cb)

    def test_TemporalProfileDock(self):

        ts = TestObjects.createTimeSeries()
        layer = TestObjects.createProfileLayer(ts)
        l2 = TestObjects.createVectorLayer()
        project = QgsProject()
        project.addMapLayers([layer, l2])
        dock = TemporalProfileDock()
        dock.setTimeSeries(ts)
        dock.setProject(project)

        self.showGui(dock)


if __name__ == "__main__":
    unittest.main(buffer=False)
