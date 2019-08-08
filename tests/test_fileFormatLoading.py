
import os, re, io, importlib, uuid, unittest

import qgis.testing

from unittest import TestCase
from eotimeseriesviewer import *
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.timeseries import TimeSeries


DIR_SENTINEL = r''
DIR_PLEIADES = r'H:\Pleiades'
DIR_RAPIDEYE = jp(DIR_EXAMPLES, 'Images')
DIR_LANDSAT = jp(DIR_EXAMPLES, 'Images')
DIR_VRT = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'

class TestFileFormatLoading(TestCase):

    @classmethod
    def setUpClass(cls):

        cls.TS = TimeSeries()

        if False:
            cls.savedStdOut = sys.stdout
            cls.savedStdIn = sys.stdin

            cls.stdout = io.StringIO()
            cls.stderr = io.StringIO()
            sys.stdout = cls.stdout
            sys.stderr = cls.stderr

    @classmethod
    def tearDownClass(cls):
        pass
        #sys.stdout = cls.stdout
        #sys.stderr = cls.stderr

    def setUp(self):
        self.TS.clear()

    def tearDown(self):
        self.TS.clear()

    def test_loadRapidEyeLocal(self):
        # load RapidEye
        searchDir = jp(DIR_EXAMPLES, 'Images')
        if not os.path.isdir(searchDir):
            print('data directory undefined. skip test.')
            return
        files = list(file_search(searchDir, 're_*.bsq', recursive=True))
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
        searchDir =DIR_RAPIDEYE
        if not os.path.isdir(searchDir):
            print('DIR_RAPIDEYE undefined. skip test.')
            return
        files = file_search(searchDir, '*.tif', recursive=True)
        files = [f for f in files if not re.search(r'_(udm|browse)\.tif$', f)]
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS))



    def test_loadPleiades(self):
        #load Pleiades data
        searchDir = DIR_PLEIADES
        if not os.path.isdir(searchDir):
            print('DIR_PLEIADES undefined. skip test.')
            return
        #files = file_search(searchDir, 'DIM*.xml', recursive=True)
        files = list(file_search(searchDir, '*.jp2', recursive=True))[0:3]
        self.TS.addSources(files, runAsync=False)
        self.assertEqual(len(files), len(self.TS))

    def test_loadSentinel2(self):
        #load Sentinel-2
        searchDir = DIR_SENTINEL
        if not os.path.isdir(searchDir):
            print('DIR_SENTINEL undefined. skip test.')
            return
        files = list(file_search(searchDir, '*MSIL1C.xml', recursive=True))
        self.TS.addSources(files, runAsync=False)

        #self.assertRegexpMatches(self.stderr.getvalue().strip(), 'Unable to add:')
        self.assertEqual(0, len(self.TS))  # do not add a containers
        subdatasets = []
        for file in files:
            subs = gdal.Open(file).GetSubDatasets()
            subdatasets.extend(s[0] for s in subs)
        self.TS.addSources(subdatasets, runAsync=False)
        self.assertEqual(len(subdatasets), len(self.TS))  # add subdatasets



if __name__ == '__main__':
    unittest.main()
