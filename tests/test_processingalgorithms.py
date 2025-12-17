import unittest
from pathlib import Path
from typing import Optional

import processing.gui.ProcessingToolbox
import qgis.utils
from eotimeseriesviewer import initAll
from eotimeseriesviewer.forceinputs import FindFORCEProductsTask
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.processing.processingalgorithms import AddTemporalProfileField, CreateEmptyTemporalProfileLayer, \
    EOTSVProcessingProvider, ReadTemporalProfiles
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent, SpatialPoint
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils
from eotimeseriesviewer.tests import EOTSVTestCase, FORCE_CUBE, start_app, TestObjects
from example import examplePoints
from processing import AlgorithmDialog
from processing.gui.ProcessingToolbox import ProcessingToolbox
from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsRectangle
from qgis.core import edit, QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsProcessingAlgorithm, \
    QgsProcessingAlgRunnerTask, QgsProcessingParameterDefinition, QgsProcessingProvider, \
    QgsProcessingRegistry, QgsProcessingUtils, QgsProject, QgsRasterLayer, QgsTaskManager, QgsVectorLayer, \
    QgsMapLayer, QgsMapToPixel, QgsPointXY

start_app()
initAll()

processing.gui.ProcessingToolbox.iface = getattr(qgis.utils, 'iface')


class ProcessingAlgorithmTests(EOTSVTestCase):

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Runs in CI. Removing provider can fail other tests.')
    def test_provider(self):
        ID = EOTSVProcessingProvider.id()
        self.assertIsInstance(ID, str)

        from eotimeseriesviewer import registerProcessingProvider, unregisterProcessingProvider

        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()

        p = registry.providerById(EOTSVProcessingProvider.id())
        self.assertIsInstance(p, EOTSVProcessingProvider)

        alg = registry.createAlgorithmById(f'{EOTSVProcessingProvider.id()}:{AddTemporalProfileField.name()}', {})
        self.assertIsInstance(alg, AddTemporalProfileField)

        unregisterProcessingProvider()
        provider = EOTSVProcessingProvider.instance()
        self.assertIsInstance(provider, QgsProcessingProvider)
        self.assertTrue(registry.providerById(ID) is None)
        registerProcessingProvider()
        p = registry.providerById(ID)
        self.assertTrue(p is provider)

        algs = provider.algorithms()
        self.assertTrue(len(algs) > 0)

        unregisterProcessingProvider()
        self.assertTrue(registry.providerById(ID) is None)

    def test_create_temporal_profile_layer(self):
        alg = CreateEmptyTemporalProfileLayer()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        project = QgsProject()
        context, feedback = self.createProcessingContextFeedback()
        context.setProject(project)
        conf = {}
        alg.initAlgorithm(conf)

        # run with default parameters -> should produce a valid file
        parm = {}
        results, success = alg.run(parm, context, feedback)
        self.assertTrue(success)
        lyr = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
        self.assertTrue(lyr.isValid())
        self.assertEqual(lyr.featureCount(), 0)
        self.assertTrue(TemporalProfileUtils.isProfileLayer(lyr))

        # create with multiple fields
        parm = {alg.FIELD_NAMES: 'p1,p2 p3',
                alg.OTHER_FIELDS: [{'name': 'myInt', 'type': QMetaType.Int},
                                   {'name': 'myFloat', 'type': QMetaType.Double}]}
        results, success = alg.run(parm, context, feedback)
        self.assertTrue(success)
        lyr = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
        self.assertTrue(lyr.isValid())
        self.assertEqual(lyr.featureCount(), 0)

        profiles = []

        for f in ['p1', 'p2', 'p3']:
            self.assertTrue(TemporalProfileUtils.isProfileField(lyr.fields()[f]))

        for n, t in [('myInt', QMetaType.Int),
                     ('myFloat', QMetaType.Double)]:
            self.assertTrue(n in lyr.fields().names())
            field: QgsField = lyr.fields()[n]
            if field.type() != t:
                s = ""
            self.assertEqual(field.type(), t)

    def test_add_temporal_profile_field(self):
        lyr = TestObjects.createVectorLayer()

        self.assertFalse(TemporalProfileUtils.isProfileLayer(lyr))

        alg = AddTemporalProfileField()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        context, feedback = self.createProcessingContextFeedback()
        project = QgsProject()
        context.setProject(project)

        conf = {}
        alg.initAlgorithm(conf)

        parm = {alg.INPUT: lyr,
                alg.FIELD_NAME: 'tp',
                }

        results, success = alg.run(parm, context, feedback)
        self.assertTrue(success)
        lyr2 = results[alg.INPUT]
        self.assertEqual(lyr2, lyr)
        field = lyr2.fields().field('tp')
        self.assertTrue(TemporalProfileUtils.isProfileField(field))

    def test_read_temporal_profiles(self):
        lyr = QgsVectorLayer(examplePoints.as_posix())

        tsv = EOTimeSeriesViewer()
        tsv.loadExampleTimeSeries(loadAsync=False)

        sources = tsv.timeSeries().sourceUris()
        self.assertTrue(len(sources) > 0)
        extent = tsv.timeSeries().maxSpatialExtent()
        extentLyr = SpatialExtent.fromLayer(lyr).toCrs(extent.crs())
        self.assertTrue(extent.intersects(extentLyr))

        self.assertFalse(TemporalProfileUtils.isProfileLayer(lyr))

        dir_outputs = self.createTestOutputDirectory()
        path_out1 = dir_outputs / 'output_layer1.geojson'
        path_out2 = dir_outputs / 'output_layer2.geojson'

        alg = ReadTemporalProfiles()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        context, feedback = self.createProcessingContextFeedback()
        project = QgsProject()
        context.setProject(project)

        conf = {}
        alg.initAlgorithm(conf)
        parm = {alg.INPUT: lyr,
                alg.FIELD_NAME: 'tp',
                alg.OUTPUT: path_out1.as_posix()
                }

        r = alg.run(parm, context, feedback)

        results = success = None

        def onExecuted(task_success, task_results):
            nonlocal results, success
            results = task_results
            success = task_success

        parm[alg.OUTPUT] = path_out2.as_posix()

        alg = ReadTemporalProfiles()
        task = QgsProcessingAlgRunnerTask(alg, parm, context, feedback)
        self.assertTrue(task.canCancel())
        tm: QgsTaskManager = QgsApplication.taskManager()
        task.executed.connect(onExecuted)
        tm.addTask(task)

        self.taskManagerProcessEvents()

        self.assertTrue(success)

        tplyr: QgsVectorLayer = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
        field = tplyr.fields().field('tp')
        self.assertIsInstance(field, QgsField)
        self.assertTrue(TemporalProfileUtils.isProfileField(field))
        self.assertEqual(lyr.featureCount(), tplyr.featureCount())
        self.assertTrue(tplyr.featureCount() > 0)

        profiles = []
        points = []
        for (f1, f2) in zip(lyr.getFeatures(), tplyr.getFeatures()):
            f1: QgsFeature
            f2: QgsFeature

            self.assertGeometriesEqual(f1.geometry(), f2.geometry())

            d = TemporalProfileUtils.profileDict(f2.attribute(field.name()))
            wkt = f2.geometry().asWkt()
            self.assertTrue(wkt not in points)
            points.append(wkt)

            if d in profiles:
                s = ""

            self.assertTrue(d not in profiles)
            profiles.append(d)

            # self.assertTrue(TemporalProfileUtils.isProfileDict(d))

        tsv.close()

    def randomSampleLayer(self, path: Path, lyr: QgsMapLayer,
                          extent: Optional[QgsRectangle] = None,
                          n: int = 25,
                          distance: float = 100) -> QgsVectorLayer:

        if extent is None:
            extent = lyr.extent()
        # '13.847039328,14.093675662,52.429954232,52.666414474 [EPSG:4326]'
        par = {'EXTENT': extent,
               'POINTS_NUMBER': n, 'MIN_DISTANCE': distance,
               'TARGET_CRS': lyr.crs(), 'MAX_ATTEMPTS': 200,
               'OUTPUT': f'ogr:dbname=\'{path.as_posix()}\' table="output" (geom)'}

        context, feedback = self.createProcessingContextFeedback()
        project = QgsProject()
        context.setProject(project)
        alg = QgsApplication.processingRegistry().createAlgorithmById('native:randompointsinextent')
        assert isinstance(alg, QgsProcessingAlgorithm)
        results, success = alg.run(par, context=context, feedback=feedback)
        self.assertTrue(success)

        lyr = QgsVectorLayer(results['OUTPUT'])
        lyr.setName(path.stem)
        self.assertTrue(lyr.isValid())
        self.assertEqual(lyr.featureCount(), n)
        self.assertTrue(lyr.crs().isValid())
        return lyr

        s = ""

    @unittest.skipIf(FORCE_CUBE is None, 'FORCE_CUBE is undefined')
    def test_read_temporal_profiles_force(self):

        task = FindFORCEProductsTask('BOA', FORCE_CUBE)
        task.run()
        sources = [f.as_posix() for f in task.files()]

        n_max = 20
        if len(sources) > n_max:
            sources = sources[:n_max]

        lyr = QgsRasterLayer(sources[0])
        assert lyr.isValid()

        TEST_DIR = self.createTestOutputDirectory()

        if True:
            path = TEST_DIR / 'testsample.gpkg'
            ext = lyr.extent()
            ext2 = ext.scaled(1.05, ext.center())
            vLyr = self.randomSampleLayer(path, lyr, extent=ext2, n=25)
        else:

            crs = QgsCoordinateReferenceSystem('EPSG:4326')
            points = {}

            for x in range(-10, lyr.width() + 10, int(lyr.width() / 5)):
                for y in range(-10, lyr.height() + 10, int(lyr.height() / 5)):
                    in_extent = 0 <= x < lyr.width() and 0 <= y < lyr.height()
                    pt = SpatialPoint.fromPixelPosition(lyr, x, y).toCrs(crs)
                    points[(x, y, in_extent)] = pt

            uri = "point?crs=epsg:4326&field=id:integer"
            vLyr = QgsVectorLayer(uri, "Scratch point layer", "memory")
        with edit(vLyr):
            assert vLyr.addAttribute(QgsField('px_x', QMetaType.Int))
            assert vLyr.addAttribute(QgsField('px_y', QMetaType.Int))
            assert vLyr.addAttribute(QgsField('in_extent', QMetaType.Bool))

            mapUnitsPerPixel = lyr.rasterUnitsPerPixelX()
            extent = lyr.extent()
            center = extent.center()
            rotation = 0
            m2p = QgsMapToPixel(mapUnitsPerPixel,
                                center.x(),
                                center.y(),
                                lyr.width(),
                                lyr.height(),
                                rotation)

            for f in vLyr.getFeatures():
                g = f.geometry()
                gPt = g.asPoint()
                pxPt: QgsPointXY = m2p.transform(gPt)
                f.setAttribute('px_x', int(pxPt.x()))
                f.setAttribute('Px_y', int(pxPt.y()))
                in_extent = extent.contains(gPt)
                if in_extent is False:
                    s = ""
                assert vLyr.updateFeature(f)

        path = TEST_DIR / 'testsample_ogr.gpkg'
        if True:
            alg = ReadTemporalProfiles()
            context, feedback = self.createProcessingContextFeedback()
            project = QgsProject()
            context.setProject(project)
            conf = {}
            alg.initAlgorithm(conf)
            parm = {alg.INPUT: vLyr,
                    alg.TIMESERIES: sources,
                    alg.FIELD_NAME: 'tp',
                    alg.OUTPUT: f'ogr:dbname=\'{path.as_posix()}\' table="output" (geom)"'
                    }

            progress = None

            def onProgressChanged(p: float):
                nonlocal progress
                progress = p

            feedback.progressChanged.connect(onProgressChanged)

            results, success = alg.run(parm, context, feedback)

            self.assertTrue(success)
            self.assertEqual(100, progress)

            tpLyr = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
            self.assertIsInstance(tpLyr, QgsVectorLayer)
            self.assertTrue(tpLyr.isValid())
            field = tpLyr.fields().field('tp')
            self.assertTrue(TemporalProfileUtils.isProfileField(field))

        if True:
            alg = ReadTemporalProfiles()
            self.assertIsInstance(alg, QgsProcessingAlgorithm)

            context, feedback = self.createProcessingContextFeedback()
            project = QgsProject()
            context.setProject(project)
            conf = {}
            alg.initAlgorithm(conf)
            parm = {alg.INPUT: vLyr,
                    alg.TIMESERIES: sources,
                    alg.FIELD_NAME: 'tp'
                    }

            progress = None

            def onProgressChanged(p: float):
                nonlocal progress
                progress = p

            feedback.progressChanged.connect(onProgressChanged)

            results, success = alg.run(parm, context, feedback)

            self.assertEqual(100, progress)
            self.assertTrue(success)
            tpLyr = QgsProcessingUtils.mapLayerFromString(results[alg.OUTPUT], context)
            self.assertIsInstance(tpLyr, QgsVectorLayer)
            self.assertTrue(tpLyr.isValid())
            field = tpLyr.fields().field('tp')
            self.assertTrue(TemporalProfileUtils.isProfileField(field))

        if True:
            # test if we can cancel the process
            alg = ReadTemporalProfiles()
            context, feedback = self.createProcessingContextFeedback()
            project = QgsProject()
            context.setProject(project)
            conf = {}
            alg.initAlgorithm(conf)
            parm = {alg.INPUT: vLyr,
                    alg.TIMESERIES: sources,
                    alg.FIELD_NAME: 'tp'
                    }

            task = QgsProcessingAlgRunnerTask(alg, parm, context, feedback)
            self.assertTrue(task.canCancel())

            progress = 0

            def onProgressChanged(p):
                nonlocal progress
                progress = p
                if p > 0.0:
                    task.cancel()

            def onExecuted(success, results):
                self.assertFalse(success)
                self.assertEqual(results, {})

            task.progressChanged.connect(onProgressChanged)
            task.executed.connect(onExecuted)
            tm: QgsTaskManager = QgsApplication.taskManager()
            tm.addTask(task)

            while tm.count() > 0:
                QgsApplication.processEvents()

            self.assertTrue(0 < progress < 100.0)

    def test_processing_toolbox(self):

        def executeWithGui(aid, parent, in_place: bool, as_batch: bool):
            alg = QgsApplication.processingRegistry().algorithmById(aid)
            self.assertIsInstance(alg, QgsProcessingAlgorithm, msg=f'Algorithm {aid} is not a QgsProcessingAlgorithm')
            d = AlgorithmDialog(alg)
            d.exec_()
            d.close()

        w = ProcessingToolbox()
        w.executeWithGui.connect(executeWithGui)
        self.showGui(w)

    def test_algorithm_html_help(self):

        algs = [CreateEmptyTemporalProfileLayer(),
                ReadTemporalProfiles(),
                AddTemporalProfileField()]

        for a in algs:

            self.assertIsInstance(a, QgsProcessingAlgorithm)
            conf = {}
            a.initAlgorithm(conf)
            help = a.shortHelpString()
            self.assertIsInstance(help, str)
            self.assertTrue(len(help) > 0)

            for p in a.parameterDefinitions():
                self.assertIsInstance(p, QgsProcessingParameterDefinition)
                self.assertTrue(p.name() in help, msg=f'Parameter {p.name()} is missing in html help of {a.id()}')
