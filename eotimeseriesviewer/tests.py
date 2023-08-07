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

import os
import pathlib

import numpy as np
from osgeo import osr, gdal

from eotimeseriesviewer import DIR_EXAMPLES, DIR_UI, initAll
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.testing import TestCase, TestObjects as TObj, start_app
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search
from eotimeseriesviewer.timeseries import TimeSeries
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsApplication

start_app = start_app

osr.UseExceptions()
gdal.UseExceptions()


class EOTSVTestCase(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds):
        super().setUpClass(*args, *kwds)

        eotsv_resources = DIR_UI / 'eotsv_resources_rc.py'
        assert eotsv_resources.is_file(), \
            'eotsv_resources_rc.py not compiled. run python scripts/compile_resourcefiles.py first.'
        initAll()

    def tearDown(self):
        self.assertTrue(EOTimeSeriesViewer.instance() is None)
        super().tearDown()

    def closeBlockingWidget(self):
        """
        Closes the active blocking (modal) widget
        """
        w = QgsApplication.instance().activeModalWidget()
        if isinstance(w, QWidget):
            print('Close blocking {} "{}"'.format(w.__class__.__name__, w.windowTitle()))
            w.close()


def testRasterFiles() -> list:
    return list(file_search(DIR_EXAMPLES, '*.tif', recursive=True))


def createTimeSeries(self) -> TimeSeries:
    files = testRasterFiles()
    TS = TimeSeries()
    self.assertIsInstance(TS, TimeSeries)
    TS.addSources(files)
    self.assertTrue(len(TS) > 0)
    return TS


class TestObjects(TObj):
    """
    Creates objects to be used for testing. It is preferred to generate objects in-memory.
    """

    @staticmethod
    def createTimeSeries() -> TimeSeries:

        TS = TimeSeries()
        files = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        TS.addSources(list(files), runAsync=False)
        assert len(TS) > 0
        return TS

    @staticmethod
    def createArtificialTimeSeries(n=100) -> list:
        vsiDir = '/vsimem/tmp'
        d1 = np.datetime64('2000-01-01')
        print('Create in-memory test timeseries of length {}...'.format(n))
        files = testRasterFiles()

        paths = []
        i = 0
        import itertools
        drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)
        for file in itertools.cycle(files):
            if i >= n:
                break

            date = d1 + i
            path = os.path.join(vsiDir, 'file.{}.{}.tif'.format(i, date))
            dsDst = drv.CreateCopy(path, gdal.Open(file))
            assert isinstance(dsDst, gdal.Dataset)
            paths.append(path)

            i += 1

        print('Done!')

        return paths

    @staticmethod
    def createTimeSeriesStacks():
        vsiDir = '/vsimem/tmp'
        from eotimeseriesviewer.temporalprofiles import date2num
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
    def testImagePaths() -> list:
        import example
        path = pathlib.Path(example.__file__).parent / 'Images'
        files = list(file_search(path, '*.tif', recursive=True))
        assert len(files) > 0
        return files

    @staticmethod
    def createTestImageSeries(n=1) -> list:
        assert n > 0

        datasets = []
        for i in range(n):
            ds = TestObjects.inMemoryImage()
            datasets.append(ds)
        return datasets

    @staticmethod
    def createMultiSourceTimeSeries() -> list:

        # real files
        files = TestObjects.testImagePaths()
        movedFiles = []
        d = r'/vsimem/'
        for pathSrc in files:
            bn = os.path.basename(pathSrc)
            pathDst = d + 'shifted_' + bn + '.bsq'
            dsSrc = gdal.Open(pathSrc)
            tops = gdal.TranslateOptions(format='ENVI')
            gdal.Translate(pathDst, dsSrc, options=tops)
            dsDst = gdal.Open(pathDst, gdal.GA_Update)
            assert isinstance(dsDst, gdal.Dataset)
            gt = list(dsSrc.GetGeoTransform())
            ns, nl = dsDst.RasterXSize, dsDst.RasterYSize
            gt[0] = gt[0] + 0.5 * ns * gt[1]
            gt[3] = gt[3] + abs(0.5 * nl * gt[5])
            dsDst.SetGeoTransform(gt)
            dsDst.SetMetadata(dsSrc.GetMetadata(''), '')
            dsDst.FlushCache()

            dsDst = None
            dsDst = gdal.Open(pathDst)
            assert list(dsDst.GetGeoTransform()) == gt
            movedFiles.append(pathDst)

        final = []
        for f1, f2 in zip(files, movedFiles):
            final.append(f1)
            final.append(f2)
        return final
