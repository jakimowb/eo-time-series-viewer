from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotWidget, \
    SpectralProfilePlotItem, SpectralProfilePlotDataItem
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.tests import EOTSVTestCase
from qgis._core import QgsProject, QgsVectorLayer


class TestSpectralProfiles(EOTSVTestCase):


    def test_load_spectral_profiles(self):
        n = 3
        EOTSV = EOTimeSeriesViewer()
        self.assertEqual(len(EOTSV.mapViews()), 0, msg=f'MapViews: {EOTSV.mapViews()}')
        EOTSV.loadExampleTimeSeries(n, loadAsync=False)
        self.assertEqual(len(EOTSV.timeSeries()), n)
        self.assertEqual(len(EOTSV.mapViews()), 1, msg=f'MapViews: {EOTSV.mapViews()}')
        canvases = EOTSV.mapCanvases()
        self.assertEqual(len(canvases), n)
        c1: MapCanvas = EOTSV.mapCanvases()[0]
        pt = SpatialPoint.fromMapCanvasCenter(c1)
        EOTSV.createSpectralLibrary()
        EOTSV.loadCurrentSpectralProfile(pt, c1)

        for slw in EOTSV.spectralLibraryWidgets():
            speclib = slw.speclib()
            self.assertIsInstance(speclib, QgsVectorLayer)
            self.assertTrue(speclib.featureCount() == 1)
            pw: SpectralProfilePlotWidget = slw.plotWidget()
            pdis = [item for item in slw.plotControl().plotWidget().items()
                    if isinstance(item, SpectralProfilePlotDataItem)]
            self.assertEqual(len(pdis), 1)
        self.showGui(EOTSV.ui)
        EOTSV.close()
        QgsProject.instance().removeAllMapLayers()
