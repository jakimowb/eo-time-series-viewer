from qgis._core import QgsApplication, QgsProcessingAlgorithm, QgsProcessingProvider, QgsProcessingRegistry, QgsProject, \
    QgsVectorLayer

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.processingalgorithms import AddTemporalProfileField, CreateEmptyTemporalProfileLayer, \
    EOTSVProcessingProvider, ReadTemporalProfiles
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects
from eotimeseriesviewer import initAll
from example import examplePoints

start_app()
initAll()


class ProcessingAlgorithmTests(TestCase):

    def test_provider(self):
        ID = EOTSVProcessingProvider.id()
        self.assertIsInstance(ID, str)

        from eotimeseriesviewer import registerProcessingProvider, unregisterProcessingProvider

        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
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
        self.assertTrue(EOTSVProcessingProvider.instance() is None)

    def test_create_temporal_profile_layer(self):
        alg = CreateEmptyTemporalProfileLayer()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        project = QgsProject()
        context, feedback = self.createProcessingContextFeedback()
        context.setProject(project)
        conf = {}
        alg.initAlgorithm(conf)

        TMP_DIR = self.createTestOutputDirectory()

        path = TMP_DIR / 'example.gpkg'
        parm = {alg.OUTPUT: path.as_posix()}

        self.assertTrue(alg.prepareAlgorithm(parm, context, feedback))
        results = alg.processAlgorithm(parm, context, feedback)

        lyr = QgsVectorLayer(results[alg.OUTPUT])
        self.assertTrue(lyr.isValid())
        self.assertEqual(lyr.featureCount(), 0)
        self.assertTrue(TemporalProfileUtils.isProfileLayer(lyr))

    def test_add_temporal_profiles(self):
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
                alg.FIELD_NAME: 'tp'
                }

        self.assertTrue(alg.prepareAlgorithm(parm, context, feedback))
        results = alg.processAlgorithm(parm, context, feedback)
        tplyr = results[alg.INPUT]
        self.assertEqual(tplyr, lyr)

        field = tplyr.fields().field('tp')
        self.assertTrue(TemporalProfileUtils.isProfileField(field))

    def test_read_temporal_profiles(self):
        lyr = QgsVectorLayer(examplePoints)

        tsv = EOTimeSeriesViewer()
        tsv.loadExampleTimeSeries(loadAsync=False)
        extent = tsv.timeSeries().maxSpatialExtent()

        self.assertFalse(TemporalProfileUtils.isProfileLayer(lyr))

        alg = ReadTemporalProfiles()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        context, feedback = self.createProcessingContextFeedback()
        project = QgsProject()
        context.setProject(project)

        conf = {}
        alg.initAlgorithm(conf)

        parm = {alg.INPUT: lyr,
                alg.FIELD_NAME: 'tp'
                }

        self.assertTrue(alg.prepareAlgorithm(parm, context, feedback))
        results = alg.processAlgorithm(parm, context, feedback)
        tplyr = results[alg.INPUT]
        self.assertEqual(tplyr, lyr)

        field = tplyr.fields().field('tp')
        self.assertTrue(TemporalProfileUtils.isProfileField(field))
