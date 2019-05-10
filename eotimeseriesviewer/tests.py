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

import os, re, io, importlib, uuid
from qgis.core import *
import numpy as np
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import eotimeseriesviewer.externals.qps.testing
import eotimeseriesviewer.externals.qps
from eotimeseriesviewer.utils import file_search
from osgeo import ogr, osr, gdal, gdal_array
import example
from eotimeseriesviewer import DIR_EXAMPLES
from eotimeseriesviewer.timeseries import TimeSeries
SHOW_GUI = True

def initQgisApplication(*args, **kwds)->QgsApplication:
    """
    Initializes a QGIS Environment
    :return: QgsApplication instance of local QGIS installation
    """
    if isinstance(QgsApplication.instance(), QgsApplication):
        return QgsApplication.instance()
    else:

        import eotimeseriesviewer.externals.qps.testing
        app = eotimeseriesviewer.externals.qps.testing.initQgisApplication(*args, **kwds)

        import eotimeseriesviewer
        eotimeseriesviewer.initAll()
        return app

def testRasterFiles()->list:
    return list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))


def createTimeSeries(self) -> TimeSeries:
    files = testRasterFiles()
    TS = TimeSeries()
    self.assertIsInstance(TS, TimeSeries)
    TS.addSources(files)
    self.assertTrue(len(TS) > 0)
    return TS

class TestObjects(eotimeseriesviewer.externals.qps.testing.TestObjects):
    """
    Creates objects to be used for testing. It is preferred to generate objects in-memory.
    """
    @staticmethod
    def createTimeSeries():

        TS = TimeSeries()
        files = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        TS.addSources(list(files))
        assert len(TS) > 0
        return TS

    @staticmethod
    def createArtificialTimeSeries(n=100)->list:
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
        from eotimeseriesviewer.temporalprofiles2d import date2num
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
        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
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
        import example
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
        return files + movedFiles

