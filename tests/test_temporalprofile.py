# coding=utf-8

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2024-09-08'
__copyright__ = 'Copyright 2024, Benjamin Jakimow'

import datetime
import os
import unittest

import numpy as np
from qgis.PyQt.QtWidgets import QComboBox
from qgis.core import edit, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsFields, QgsProject, QgsRasterLayer, \
    QgsVectorLayer

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, \
    TemporalProfileLayerFieldComboBox, TemporalProfileLayerProxyModel, TemporalProfileUtils
from eotimeseriesviewer.tests import EOTSVTestCase, FORCE_CUBE, start_app, TestObjects

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
        task = LoadTemporalProfileTask(files, points, crs=crs, info=info, n_threads=0)
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

    @unittest.skipIf(FORCE_CUBE is None, 'FORCE_CUBE is undefined')
    def test_load_profile_FORCE(self):

        def onProgress(progress):

            if progress < 100:
                print(f'\r{progress: 0.2f}', end='')
            else:
                print(f'\r{progress: 0.2f}')

        path_cube = FORCE_CUBE
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
            cache = task.mdCache
            profiles1 = task.profiles()
            for p in profiles1:
                self.assertTrue(TemporalProfileUtils.isProfileDict(p))
                success, err = TemporalProfileUtils.verifyProfile(p)
                self.assertTrue(success, msg=err)
            print(f'Run 1: tile {tileDir}: \nduration {task.loadingTime()}')
            nTotal = len(files)
            for k, v in task.mTimeIt.items():
                print(f'Avg {k}: {v}')

            task = LoadTemporalProfileTask(files, [pt], pt.crs(), mdCache=cache)
            task.progressChanged.connect(onProgress)
            task.run()
            profiles2 = task.profiles()
            print(f'Run 2: tile {tileDir} (cached layer infos): \nduration: {task.loadingTime()}')
            nTotal = len(files)
            for k, v in task.mTimeIt.items():
                print(f'Avg {k}: {v}')

            s = ""
        s = ""

    @unittest.skipIf(FORCE_CUBE is None, 'Missing FORCE_CUBE')
    def test_load_timeseries_profiledata_async(self):

        files = []
        for tileDir in FORCEUtils.tileDirs(FORCE_CUBE):
            files.extend(FORCEUtils.productFiles(tileDir, 'BOA'))
            break

        lyr = QgsRasterLayer(files[0].as_posix())
        self.assertTrue(lyr.isValid())
        points = [SpatialPoint.fromMapLayerCenter(lyr),
                  # SpatialPoint.fromPixelPosition(lyr, 50, 50),
                  # SpatialPoint.fromPixelPosition(lyr, -100, -200),  # out of image
                  ]

        # test without layer cache
        dtime = lambda t: datetime.datetime.now() - t
        now = datetime.datetime.now

        mdCache = dict()
        lyrCache = dict()

        n_threads = os.cpu_count()
        TEST_MATRIX = [
            # {'r': 3},
            # {'r': 3, 'mdCache': mdCache},
            # {'r': 3, 'lyrCache': lyrCache},
            # {'r': 3, 'n_threads': 1},
            # {'r': 3, 'n_threads': 2},
            # {'r': 3, 'n_threads': 4},
            {'r': 3, 'n_threads': 6},
            # {'r': 3, 'n_threads': 8},
            # {'r': 3, 'n_threads': 4, 'lyrCache': lyrCache},
            {'r': 3, 'n_threads': 6, 'lyrCache': lyrCache},
            # {'r': 3, 'n_threads': 8, 'lyrCache': lyrCache},

            # {'r': 3, 'n_threads': 10},
            # {'r': 3, 'n_threads': 1, 'lyrCache': lyrCache},
            # {'r': 3, 'n_threads': 5, 'lyrCache': lyrCache},
            # {'r': 3, 'n_threads': 10, 'lyrCache': lyrCache},
            # {'r': 3, 'n_threads': os.cpu_count()},
        ]
        files = files[0:100]
        for s, setting in enumerate(TEST_MATRIX):
            kwds = {k: v for k, v in setting.items() if k in ['mdCache', 'lyrCache', 'n_threads']}
            repetitions = setting.get('r', 1)
            print(f'# {s + 1}: Load from {len(files)} files: {kwds}')
            durations = []
            for r in range(repetitions):
                t = now()
                task = LoadTemporalProfileTask(files, points, lyr.crs(), **kwds)
                task.run()
                duration = dtime(t)
                durations.append(duration)
                print(f'{s + 1}-r{r + 1}: dt={duration}')
            t_avg = np.mean(np.asarray(durations).astype('timedelta64')).astype(object)
            print(f'{s + 1}-avg: {t_avg}')
            print(f'# {s + 1}: done : {kwds}')
        # test with layer cache

    # test with

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

    def test_temporalProfileLayerFieldModel(self):

        vl = TestObjects.createVectorLayer()
        vl.setName('Not to show')

        tl = TestObjects.createProfileLayer()
        tl.setName('TPLayer1')

        with edit(tl):
            field = TemporalProfileUtils.createProfileField('myProfiles2')
            tl.addAttribute(field)
        tl2 = TestObjects.createProfileLayer()
        tl2.setName('TPLayer12')

        # test without temporal profile layers
        project = QgsProject()
        cb = TemporalProfileLayerFieldComboBox(project=project)
        lyr, field = cb.layerField()
        self.assertTrue(lyr is None)
        self.assertTrue(field is None)

        self.assertFalse(cb.setLayerField('foo', 'bar'))

        # test with temporal profile layers
        project = QgsProject()
        project.addMapLayers([vl, tl, tl2])

        cb = TemporalProfileLayerFieldComboBox(project=project)

        self.assertTrue(cb.setLayerField(tl, 'myProfiles2'))
        self.assertTrue(cb.setLayerField(tl.id(), 'myProfiles2'))
        self.assertFalse(cb.setLayerField('foo', 'bar'))

        lyr, fn = cb.layerField()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertIsInstance(fn, QgsField)

        self.showGui(cb)

    def test_create_new_tp_layer(self):

        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)
        eotsv.createTemporalProfileLayer(skip_dialog=True)
        self.showGui(eotsv.ui)
        eotsv.close()


if __name__ == "__main__":
    unittest.main(buffer=False)
