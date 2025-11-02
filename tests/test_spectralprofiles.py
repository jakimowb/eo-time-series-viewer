from eotimeseriesviewer.dateparser import DateTimePrecision
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.sensors import has_sensor_id
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from qgis.core import QgsProject

start_app()


class TestSpectralProfiles(EOTSVTestCase):

    def test_load_spectral_profiles(self):
        n = 3
        EOTSV = EOTimeSeriesViewer()
        EOTSV.timeSeries().setDateTimePrecision(DateTimePrecision.Day)
        self.assertEqual(len(EOTSV.mapViews()), 0, msg=f'MapViews: {EOTSV.mapViews()}')
        EOTSV.loadExampleTimeSeries(n, filter_raster='20*_L*.tif', loadAsync=False)
        self.assertEqual(len(EOTSV.timeSeries()), n)
        self.assertEqual(len(EOTSV.mapViews()), 1, msg=f'MapViews: {EOTSV.mapViews()}')
        canvases = EOTSV.mapCanvases()
        self.assertEqual(len(canvases), n)
        c1: MapCanvas = EOTSV.mapCanvases()[0]
        pt: SpatialPoint = SpatialPoint.fromMapCanvasCenter(c1)
        self.assertIsInstance(pt, SpatialPoint)
        self.assertTrue(not pt.isEmpty())
        self.assertTrue(pt.crs().isValid())
        # EOTSV.createSpectralLibrary()
        EOTSV.mapWidget().timedRefresh(load_async=False)
        # self.taskManagerProcessEvents()

        sensorLayers = [lyr for lyr in c1.layers() if has_sensor_id(lyr)]
        self.assertTrue(len(sensorLayers) > 0)

        atdws = EOTSV.attributeTableDockWidgets()
        sldws = EOTSV.spectralLibraryDockWidgets()

        self.assertEqual(len(atdws), 0)
        self.assertEqual(len(sldws), 0)

        n = len(EOTSV.loadCurrentSpectralProfile(pt, c1))
        self.assertIsInstance(n, int)
        self.assertTrue(n > 0)

        atdws = EOTSV.attributeTableDockWidgets()
        sldws = EOTSV.spectralLibraryDockWidgets()

        self.assertEqual(len(atdws), 0)
        self.assertEqual(len(sldws), 1)

        self.showGui(EOTSV.ui)
        EOTSV.close()
        QgsProject.instance().removeAllMapLayers()
