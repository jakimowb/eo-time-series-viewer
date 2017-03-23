
import os, re, io
from unittest import TestCase
from osgeo import gdal
from qgis import *
#from timeseriesviewer import *
from . import *
from timeseries import *

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



    def test_loadLandsat(self):
        searchDir = jp(DIR_EXAMPLES, 'Images')
        files = file_search(searchDir, '*_L*_BOA.bsq')[0:3]
        self.TS.addFiles(files)

        self.assertEqual(len(files), len(self.TS))
        s = ""

    def test_nestedVRTs(self):
        # load VRTs pointing to another VRT pointing to Landsat imagery
        searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
        files = file_search(searchDir, '*BOA.vrt', recursive=True)[0:3]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadRapidEye(self):
        # load RapidEye
        searchDir = r'H:\RapidEye\3A'
        files = file_search(searchDir, '*.tif', recursive=True)
        files = [f for f in files if not re.search('_(udm|browse)\.tif$', f)]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadPleiades(self):
        #load Pleiades data
        searchDir = r'H:\Pleiades'
        #files = file_search(searchDir, 'DIM*.xml', recursive=True)
        files = file_search(searchDir, '*.jp2', recursive=True)[0:3]
        self.TS.addFiles(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadSentinel2(self):
        #load Sentinel-2
        searchDir = r'H:\Sentinel2'
        files = file_search(searchDir, '*MSIL1C.xml', recursive=True)
        self.TS.addFiles(files)

        #self.assertRegexpMatches(self.stderr.getvalue().strip(), 'Unable to add:')
        self.assertEqual(0, len(self.TS))  # do not add a containers
        subdatasets = []
        for file in files:
            subs = gdal.Open(file).GetSubDatasets()
            subdatasets.extend(s[0] for s in subs)
        self.TS.addFiles(subdatasets)
        self.assertEqual(len(subdatasets), len(self.TS))  # add subdatasets