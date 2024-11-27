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
from typing import List, Match, Pattern, Union

import numpy as np
from osgeo import gdal, osr

from qgis.core import edit, QgsApplication, QgsError, QgsFeature, QgsGeometry, QgsMapToPixel, QgsRasterLayer, \
    QgsVectorLayer
from eotimeseriesviewer import DIR_EXAMPLES, DIR_UI, initAll
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.testing import start_app, TestCase, TestObjects as TObj
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, rasterLayerMapToPixel
from eotimeseriesviewer.temporalprofileV2 import LoadTemporalProfileTask, TemporalProfileUtils
from eotimeseriesviewer.timeseries import TimeSeries
from qgis.PyQt.QtWidgets import QWidget

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

    @staticmethod
    def taskManagerProcessEvents() -> bool:
        tm = QgsApplication.taskManager()
        has_active_tasks = False
        while any(tm.activeTasks()):
            if not has_active_tasks:
                print('Wait for QgsTaskManager tasks to be finished...\r', flush=True)
                has_active_tasks = True
            QgsApplication.processEvents()
        print('\rfinished.', flush=True)
        return has_active_tasks

    def tearDown(self):
        self.assertTrue(EOTimeSeriesViewer.instance() is None)
        super().tearDown()

    @staticmethod
    def closeBlockingWidget():
        """
        Closes the active blocking (modal) widget
        """
        w = QgsApplication.instance().activeModalWidget()
        if isinstance(w, QWidget):
            print('Close blocking {} "{}"'.format(w.__class__.__name__, w.windowTitle()))
            w.close()

    @classmethod
    def exampleRasterFiles(cls) -> List[str]:
        return example_raster_files()


def example_raster_files(pattern: Union[str, Pattern, Match] = '*.tif') -> List[str]:
    return list(file_search(DIR_EXAMPLES, pattern, recursive=True))


def createTimeSeries(self) -> TimeSeries:
    files = example_raster_files()
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
        files = file_search(DIR_EXAMPLES / 'Images', '*.tif', recursive=True)
        TS.addSources(list(files), runAsync=False)
        assert len(TS) > 0
        return TS

    @staticmethod
    def createProfileLayer(timeseries: TimeSeries = None) -> QgsVectorLayer:

        if timeseries is None:
            timeseries = TestObjects.createTimeSeries()
        layer = TemporalProfileUtils.createProfileLayer()
        tpFields = TemporalProfileUtils.temporalProfileFields(layer)

        sources = timeseries.sourceUris()
        l0 = QgsRasterLayer(sources[0])
        ns, nl = l0.width(), l0.height()
        m2p: QgsMapToPixel = rasterLayerMapToPixel(l0)
        points = [m2p.toMapCoordinates(0, 0),
                  m2p.toMapCoordinates(int(0.5 * ns), int(0.5 * nl)),
                  m2p.toMapCoordinates(ns - 1, nl - 1)]

        task = LoadTemporalProfileTask(sources, points, crs=l0.crs())
        task.run()

        profiles = task.profiles()
        new_features: List[QgsFeature] = list()
        for profile, point in zip(profiles, task.profilePoints()):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(point.asWkt()))
            profileJson = TemporalProfileUtils.profileJsonFromDict(profile)
            f.setAttribute(tpFields[0].name(), profile)
            new_features.append(f)

        with edit(layer):
            if not layer.addFeatures(new_features):
                err = layer.error()
                if isinstance(err, QgsError):
                    raise err.message()
        return layer

    @staticmethod
    def createArtificialTimeSeries(n=100) -> List[str]:
        vsiDir = '/vsimem/tmp'
        d1 = np.datetime64('2000-01-01')
        print('Create in-memory test timeseries of length {}...'.format(n))
        files = example_raster_files()

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
    def exampleImagePaths() -> list:
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
        files = TestObjects.exampleImagePaths()
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
