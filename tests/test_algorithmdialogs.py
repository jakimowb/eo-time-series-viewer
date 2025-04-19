import unittest

from qgis.core import QgsProcessingUtils, QgsVectorLayer

from eotimeseriesviewer.processing.algorithmdialog import AlgorithmDialog, BatchAlgorithmDialog
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.processing.processingalgorithms import ReadTemporalProfiles
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()


class AlgorithmDialogTests(EOTSVTestCase):

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_algorithmDialog(self):
        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)

        alg = ReadTemporalProfiles()
        conf = {}
        alg.initAlgorithm()

        context, feedback = self.createProcessingContextFeedback()

        # vl = TestObjects.createVectorLayer()
        # ts = TestObjects.createTimeSeries()
        context.setProject(eotsv.project())

        d = AlgorithmDialog(alg, context=context, iface=eotsv)
        d.exec_()

        results = d.results()
        layer = QgsProcessingUtils.mapLayerFromString(results[ReadTemporalProfiles.OUTPUT], context)
        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertTrue(layer.featureCount() > 0)
        for f in layer.getFeatures():
            s = ""

        s = ""

        self.showGui(eotsv.ui)
        eotsv.close()
        pass

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_batchDialog(self):
        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)
        # eotsv.loadTemporalProfilesForPoints()
        alg = ReadTemporalProfiles()
        conf = {}
        alg.initAlgorithm()

        context, feedback = self.createProcessingContextFeedback()

        # vl = TestObjects.createVectorLayer()
        # ts = TestObjects.createTimeSeries()
        context.setProject(eotsv.project())

        d = BatchAlgorithmDialog(alg, context=context, iface=eotsv)
        d.exec_()

        self.showGui(eotsv.ui)
        eotsv.close()

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_others(self):
        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)
        self.showGui(eotsv.ui)
        eotsv.close()
