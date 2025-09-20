# coding=utf-8

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2024-09-08'
__copyright__ = 'Copyright 2024, Benjamin Jakimow'

import datetime
import unittest

from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, \
    TemporalProfileLayerFieldComboBox, TemporalProfileLayerProxyModel, TemporalProfileUtils
from eotimeseriesviewer.tests import EOTSVTestCase, FORCE_CUBE, start_app, TestObjects
from qgis.PyQt.QtWidgets import QComboBox
from qgis.core import edit, QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsFields, QgsProject, \
    QgsRasterLayer, QgsTaskManager, QgsVectorLayer

start_app()


class TestTemporalProfilesV2(EOTSVTestCase):
    """Test temporal profiles"""

    def test_load_timeseries_profiledata_tm(self):
        files = self.exampleRasterFiles()[1:]

        lyr1 = QgsRasterLayer(files[0])
        self.assertTrue(lyr1.isValid())
        pt = SpatialPoint.fromMapLayerCenter(lyr1)

        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        pt = pt.toCrs(crs)
        points = [pt]

        nFiles = len(files)
        info = dict(id=1)

        def onExecuted(success, results):
            s = ""

        def onProgress(progress):
            print(f'Progress {progress}')

        task = LoadTemporalProfileTask(files, points, crs=crs, info=info)
        task.executed.connect(onExecuted)
        task.progressChanged.connect(onProgress)
        tm: QgsTaskManager = QgsApplication.instance().taskManager()
        tm.addTask(task)

        while tm.count() > 0:
            QgsApplication.processEvents()

        s = ""

    def test_load_timeseries_profiledata(self):
        files = self.exampleRasterFiles()[1:]

        lyr1 = QgsRasterLayer(files[0])
        self.assertTrue(lyr1.isValid())

        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        points = [(-3, -3),  # out of image pixel
                  (4, 4),
                  (10, 10)]
        points = [SpatialPoint.fromPixelPosition(lyr1, *px).toCrs(crs) for px in points]

        nFiles = len(files)
        info = dict(id=1)
        task = LoadTemporalProfileTask(['does_not_exists.tif'] + files, points, crs=crs, info=info, save_sources=True)

        tm: QgsTaskManager = QgsApplication.instance().taskManager()
        tm.addTask(task)

        while tm.count() > 0:
            QgsApplication.processEvents()

        profiles = task.profiles()

        self.assertEqual(len(profiles), len(points))
        for i, profile in enumerate(profiles):
            if i == 0:
                self.assertTrue(profile is None)
                continue

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

    def allFORCEFiles(self, product='BOA'):
        all_files = []

        for tileDir in FORCEUtils.tileDirs(FORCE_CUBE):
            all_files.extend(FORCEUtils.productFiles(tileDir, product))

        return all_files

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

            t0 = datetime.datetime.now()
            task.run_task_manager()
            loadingTime = datetime.datetime.now() - t0

            profiles1 = task.profiles()
            for p in profiles1:
                self.assertTrue(TemporalProfileUtils.isProfileDict(p))
                success, err = TemporalProfileUtils.verifyProfile(p)
                self.assertTrue(success, msg=err)
            print(f'Run: tile {tileDir}: \nduration {loadingTime}')

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
        eotsv.ui.show()
        while eotsv.mapCanvas() is None:
            QgsApplication.processEvents()
        pt = SpatialPoint.fromMapCanvasCenter(eotsv.mapCanvas())
        eotsv.loadCurrentTemporalProfile(pt)
        self.showGui(eotsv.ui)
        eotsv.close()
        del eotsv

    @unittest.skipIf(FORCE_CUBE is None, 'FORCE_CUBE is undefined')
    def test_FORCE2(self):

        files = self.allFORCEFiles()
        # files = files[0:10]
        lyr = QgsRasterLayer(files[0].as_posix())
        pixels = [(100, 50),
                  (-10, -20),
                  (25, 75),
                  (-20, -5),
                  ]
        points = [SpatialPoint.fromPixelPosition(lyr, *px) for px in pixels]

        def onExecuted(success, r):
            self.assertTrue(success)
            self.assertIsInstance(r, list)

        def onProgress(progress):
            print(f'Progress {progress}')

        # files = files[0:10]

        runs = [
            {'loader': 'gdal', 'n_threads': 4},
            {'loader': 'qgis', 'n_threads': 4},
            {'loader': 'qgis', 'n_threads': 1},
            {'loader': 'gdal', 'n_threads': 1},
        ]

        results = []
        for run in runs:
            n_threads = run['n_threads']
            loader = run['loader']
            task = LoadTemporalProfileTask(files[0:100], points, lyr.crs(),
                                           loader=loader, n_threads=n_threads)
            task.executed.connect(onExecuted)
            task.progressChanged.connect(onProgress)
            if False:
                task.run_serial()
            else:
                task.run_task_manager()
            result = run.copy()
            result['profiles'] = task.profiles()
            result['points'] = task.mPoints
            result['duration'] = datetime.datetime.now() - task.mInitTime
            results.append(result)

        profiles = None
        print(f'Load {len(points)} points from {len(files)} files:')
        for i, result in enumerate(results):
            p = result['profiles']
            if i == 0:
                profiles = p
            else:
                self.assertEqual(profiles, p)
            print(f'{result['loader']} {result['n_threads']} {result['duration']}')

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Live testing only')
    def test_temp_profile_loading(self):

        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)
        eotsv.activateIdentifyTemporalProfileMapTool()
        eotsv.loadCurrentTemporalProfile(eotsv.spatialCenter())
        self.showGui(eotsv.ui)

        eotsv.close()
        QgsProject.instance().removeAllMapLayers()


if __name__ == "__main__":
    unittest.main(buffer=False)
