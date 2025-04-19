import os
import re
import unittest

from osgeo import gdal

from eotimeseriesviewer import DIR_EXAMPLES
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource
from eotimeseriesviewer.timeseries.timeseries import TimeSeries

start_app()

DIR_SENTINEL = r''
DIR_PLEIADES = r'H:\Pleiades'
DIR_RAPIDEYE = r'Y:\RapidEye\3A'
DIR_LANDSAT = DIR_EXAMPLES / 'Images'
DIR_VRT = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'


class TestFileFormatLoading(EOTSVTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.TS = TimeSeries()

    def setUp(self):
        super().setUp()
        self.TS.clear()

    def tearDown(self):
        super().tearDown()
        self.TS.clear()

    def test_loadRapidEyeLocal(self):
        # load RapidEye
        searchDir = DIR_EXAMPLES / 'Images'
        if not os.path.isdir(searchDir):
            print('data directory undefined. skip test.')
            return
        files = list(file_search(searchDir, 're_*.tif', recursive=True))
        for file in files:
            tss = TimeSeriesSource.create(file)
            self.assertIsInstance(tss, TimeSeriesSource)
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS))

    def test_loadLandsat(self):
        searchDir = DIR_LANDSAT
        if not os.path.isdir(searchDir):
            print('DIR_LANDSAT undefined. skip test.')
            return
        files = list(file_search(searchDir, '*_L*_BOA.bsq'))[0:3]
        self.TS.addSources(files, runAsync=False)

        self.assertEqual(len(files), len(self.TS))
        s = ""

    def test_loadOSARIS_GRD(self):

        testDir = r'Q:\Processing_BJ\99_OSARIS_Testdata\Loibl-2019-OSARIS-Ala-Archa\Coherences'
        if os.path.isdir(testDir):
            files = file_search(testDir, re.compile(r'.*\.grd$'))
            for i, path in enumerate(files):
                tss = TimeSeriesSource.create(path)
                self.assertIsInstance(tss, TimeSeriesSource)
                self.assertTrue(tss.crs().isValid())
                self.TS.addSources([path], runAsync=False)
                self.assertEqual(len(self.TS), i + 1)

                tss = self.TS[0][0]
                self.assertIsInstance(tss, TimeSeriesSource)
                sensor = self.TS[0].sensor()
                self.assertIsInstance(sensor, SensorInstrument)

    def test_ForceLevel2(self):

        path = r'J:\diss_bj\level2\s-america\X0050_Y0025\20140601_LEVEL2_LND08_BOA.tif'
        path = r'J:\diss_bj\level2\s-america\X0049_Y0025\20140531_LEVEL2_LND07_BOA.tif'

        testData = r'J:\diss_bj\level2\s-america\X0049_Y0025'
        if os.path.isdir(testData):
            files = list(file_search(testData, '*IMP.tif'))
            if len(files) > 10:
                files = files[0:10]
            for i, path in enumerate(files):
                self.TS.addSources([path], runAsync=False)
                self.assertEqual(len(self.TS), i + 1)

                tss = self.TS[0][0]
                self.assertIsInstance(tss, TimeSeriesSource)
                sensor = self.TS[0].sensor()
                self.assertIsInstance(sensor, SensorInstrument)

            s = ""

    def test_badtimeformat(self):

        p = r'C:\Users\geo_beja\Desktop\23042014_LEVEL2_LND08_VZN.tif'

        if os.path.isfile(p):
            tss = TimeSeriesSource.create(p)
            s = ""

    def test_nestedVRTs(self):
        # load VRTs pointing to another VRT pointing to Landsat imagery
        searchDir = DIR_VRT
        if not os.path.isdir(searchDir):
            print('DIR_VRT undefined. skip test.')
            return
        files = list(file_search(searchDir, '*BOA.vrt', recursive=True))[0:3]
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS))

    def test_loadRapidEye(self):
        # load RapidEye
        searchDir = DIR_RAPIDEYE
        if not os.path.isdir(searchDir):
            print('DIR_RAPIDEYE undefined. skip test.')
            return
        files = file_search(searchDir, '*.tif', recursive=True)
        files = [f for f in files if not re.search(r'_(udm|browse)\.tif$', f)]
        if len(files) > 10:
            files = files[0:10]
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS.sourceUris()))

        tsd = self.TS[0]
        self.assertIsInstance(tsd, TimeSeriesDate)
        for wl in tsd.sensor().wl:
            self.assertTrue(wl > 0)
        tss = tsd[0]
        self.assertIsInstance(tss, TimeSeriesSource)

    def test_loadPleiades(self):
        # load Pleiades data
        searchDir = DIR_PLEIADES
        if not os.path.isdir(searchDir):
            print('DIR_PLEIADES undefined. skip test.')
            return
        # files = file_search(searchDir, 'DIM*.xml', recursive=True)
        files = list(file_search(searchDir, '*.jp2', recursive=True))[0:3]
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS))

    def test_loadSentinel2(self):
        # load Sentinel-2
        searchDir = DIR_SENTINEL
        if not os.path.isdir(searchDir):
            print('DIR_SENTINEL undefined. skip test.')
            return
        files = list(file_search(searchDir, '*MSIL1C.xml', recursive=True))
        self.TS.addSources(files, runAsync=False)

        # self.assertRegexpMatches(self.stderr.getvalue().strip(), 'Unable to add:')
        self.assertEqual(0, len(self.TS))  # do not add a containers
        subdatasets = []
        for file in files:
            subs = gdal.Open(file).GetSubDatasets()
            subdatasets.extend(s[0] for s in subs)
        self.TS.addSources(subdatasets, runAsync=False)
        self.assertEqual(len(subdatasets), len(self.TS))  # add subdatasets


if __name__ == '__main__':
    unittest.main(buffer=False)
