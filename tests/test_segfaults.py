"""
Tests that create segfaults (and should not!), e.g. "interrupted by signal 11:SIGSEGV"
For example, due caused by garbage-collected references.
"""
from qgis.core import QgsVectorLayer, QgsProject

from eotimeseriesviewer import initAll
from eotimeseriesviewer.temporalprofile.visualization import TemporalProfileDock
from eotimeseriesviewer.tests import EOTSVTestCase, TestObjects, start_app

start_app()
initAll()


class PlotSettingsTests(EOTSVTestCase):
    # @unittest.skip("Needs to be rewritten / segfaults")
    def test_TemporalProfileDock(self):
        ts = TestObjects.createTimeSeries()

        layer = TestObjects.createProfileLayer(ts)
        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertTrue(layer.isValid())
        l2 = TestObjects.createVectorLayer()

        project = QgsProject()
        # project = QgsProject.instance()
        project.addMapLayers([layer, l2])

        dock = TemporalProfileDock()
        self.assertEqual(dock.project(), QgsProject.instance())
        dock.setTimeSeries(ts)
        dock.setProject(project)

        # dock.mVis.flushSignals()
        # QApplication.processEvents()

        # QgsApplication.instance().processEvents()
        # dock.mVis.mModel.removeAllVisualizations()
        # project.removeAllMapLayers()
        # dock.mVis.removeAllLayerConnections()
