        # -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import os, re, io


from unittest import TestCase
from timeseriesviewer import *
from timeseriesviewer.timeseries import *
from timeseriesviewer import DIR_EXAMPLES
from timeseriesviewer.utils import file_search
from osgeo import ogr, osr, gdal, gdal_array



class TestObjects():
    """
    Creates objects to be used for testing. It is prefered to generate objects in-memory.
    """

    @staticmethod
    def createTimeSeries():

        TS = TimeSeries()
        files = file_search(DIR_EXAMPLES, '*.bsq', recursive=True)
        TS.addSources(files)
        return TS

    @staticmethod
    def createTimeSeriesStacks():
        vsiDir = '/vsimem/tmp'
        from timeseriesviewer.temporalprofiles2d import date2num
        ns = 50
        nl = 100

        r1 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(16, 'D'), dtype=np.datetime64)
        r2 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(8, 'D'), dtype=np.datetime64)
        drv = gdal.GetDriverByName('ENVI')

        crs = osr.SpatialReference()
        crs.ImportFromEPSG(32633)

        assert isinstance(drv, gdal.Driver)
        datasets = []
        for i, r in enumerate([r1, r2]):
            p = '{}tmpstack{}.bsq'.format(vsiDir, i + 1)

            ds = drv.Create(p, ns, nl, len(r), eType=gdal.GDT_Float32)
            assert isinstance(ds, gdal.Dataset)

            ds.SetProjection(crs.ExportToWkt())

            dateString = ','.join([str(d) for d in r])
            dateString = '{{{}}}'.format(dateString)
            ds.SetMetadataItem('wavelength', dateString, 'ENVI')

            for b, date in enumerate(r):
                decimalYear = date2num(date)

                band = ds.GetRasterBand(b + 1)
                assert isinstance(band, gdal.Band)
                band.Fill(decimalYear)
            ds.FlushCache()
            datasets.append(p)

        return datasets

    @staticmethod
    def spectralProfiles(n):
        """
        Returns n random spectral profiles from the test data
        :return: lost of (N,3) array of floats specifying point locations.
        """

        files = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        results = []
        import random
        for file in random.choices(files, k=n):
            ds = gdal.Open(file)
            assert isinstance(ds, gdal.Dataset)
            b1 = ds.GetRasterBand(1)
            noData = b1.GetNoDataValue()
            assert isinstance(b1, gdal.Band)
            x = None
            y = None
            while x is None:
                x = random.randint(0, ds.RasterXSize-1)
                y = random.randint(0, ds.RasterYSize-1)

                if noData is not None:
                    v = b1.ReadAsArray(x,y,1,1)
                    if v == noData:
                        x = None
            profile = ds.ReadAsArray(x,y,1,1).flatten()
            results.append(profile)

        return results

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
        files = file_search(searchDir, 're_*.bsq', recursive=True)
        self.TS.addSources(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadLandsat(self):
        searchDir = jp(DIR_EXAMPLES, 'Images')
        files = file_search(searchDir, '*_L*_BOA.bsq')[0:3]
        self.TS.addSources(files)

        self.assertEqual(len(files), len(self.TS))
        s = ""

    def test_nestedVRTs(self):
        # load VRTs pointing to another VRT pointing to Landsat imagery
        searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\02_CuttedVRT'
        files = file_search(searchDir, '*BOA.vrt', recursive=True)[0:3]
        self.TS.addSources(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadRapidEye(self):
        # load RapidEye
        searchDir = r'H:\RapidEye\3A'
        files = file_search(searchDir, '*.tif', recursive=True)
        files = [f for f in files if not re.search('_(udm|browse)\.tif$', f)]
        self.TS.addSources(files)
        self.assertEqual(len(files), len(self.TS))



    def test_loadPleiades(self):
        #load Pleiades data
        searchDir = r'H:\Pleiades'
        #files = file_search(searchDir, 'DIM*.xml', recursive=True)
        files = file_search(searchDir, '*.jp2', recursive=True)[0:3]
        self.TS.addSources(files)
        self.assertEqual(len(files), len(self.TS))

    def test_loadSentinel2(self):
        #load Sentinel-2
        searchDir = r'H:\Sentinel2'
        files = file_search(searchDir, '*MSIL1C.xml', recursive=True)
        self.TS.addSources(files)

        #self.assertRegexpMatches(self.stderr.getvalue().strip(), 'Unable to add:')
        self.assertEqual(0, len(self.TS))  # do not add a containers
        subdatasets = []
        for file in files:
            subs = gdal.Open(file).GetSubDatasets()
            subdatasets.extend(s[0] for s in subs)
        self.TS.addSources(subdatasets)
        self.assertEqual(len(subdatasets), len(self.TS))  # add subdatasets
