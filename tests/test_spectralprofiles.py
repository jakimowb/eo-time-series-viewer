from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer.timeseries import has_sensor_id

start_app()

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotWidget, \
    SpectralProfilePlotDataItem
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from qgis.core import QgsProject, QgsVectorLayer


class TestSpectralProfiles(EOTSVTestCase):

    def test_load_spectral_profiles(self):
        n = 3
        EOTSV = EOTimeSeriesViewer()
        self.assertEqual(len(EOTSV.mapViews()), 0, msg=f'MapViews: {EOTSV.mapViews()}')
        EOTSV.loadExampleTimeSeries(n, filter_raster='re_*.tif', loadAsync=False)
        self.assertEqual(len(EOTSV.timeSeries()), n)
        self.assertEqual(len(EOTSV.mapViews()), 1, msg=f'MapViews: {EOTSV.mapViews()}')
        canvases = EOTSV.mapCanvases()
        self.assertEqual(len(canvases), n)
        c1: MapCanvas = EOTSV.mapCanvases()[0]
        pt: SpatialPoint = SpatialPoint.fromMapCanvasCenter(c1)
        self.assertIsInstance(pt, SpatialPoint)
        self.assertTrue(not pt.isEmpty())
        self.assertTrue(pt.crs().isValid())
        EOTSV.createSpectralLibrary()

        sensorLayers = [lyr for lyr in c1.layers() if has_sensor_id(lyr)]
        self.assertTrue(len(sensorLayers) > 0)

        n = len(EOTSV.loadCurrentSpectralProfile(pt, c1))
        self.assertIsInstance(n, int)
        self.assertTrue(n > 0)

        for slw in EOTSV.spectralLibraryWidgets():
            speclib = slw.speclib()
            self.assertIsInstance(speclib, QgsVectorLayer)
            self.assertTrue(speclib.featureCount() == 1, msg=f'Got {speclib.featureCount()} profiles instead of 1')
            pw: SpectralProfilePlotWidget = slw.plotWidget()
            pdis = [item for item in slw.plotControl().plotWidget().items()
                    if isinstance(item, SpectralProfilePlotDataItem)]
            self.assertEqual(len(pdis), 1)
        self.showGui(EOTSV.ui)
        EOTSV.close()
        QgsProject.instance().removeAllMapLayers()
