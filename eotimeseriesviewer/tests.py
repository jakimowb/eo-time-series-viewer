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
import os
import pathlib
import uuid
from pathlib import Path
from typing import Any, Dict, List, Match, Pattern, Union

import numpy as np
from osgeo import gdal, osr
from qgis.core import edit, QgsApplication, QgsError, QgsFeature, QgsFields, QgsGeometry, QgsMapToPixel, QgsPointXY, \
    QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtWidgets import QWidget

from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from eotimeseriesviewer import DIR_EXAMPLES, DIR_UI, initAll
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.testing import start_app, TestCase, TestObjects as TObj
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, rasterLayerMapToPixel
from eotimeseriesviewer.timeseries.source import TimeSeriesSource
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.dateparser import DateTimePrecision

start_app = start_app

osr.UseExceptions()
gdal.UseExceptions()

DIR_LARGE_TIMESERIES = None

FORCE_CUBE = os.environ.get('FORCE_CUBE')
FORCE_CUBE = Path(FORCE_CUBE) if isinstance(FORCE_CUBE, str) and os.path.isdir(FORCE_CUBE) else None


class EOTSVTestCase(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds):
        super().setUpClass(*args, *kwds)

        eotsv_resources = DIR_UI / 'eotsv_resources_rc.py'
        assert eotsv_resources.is_file(), \
            'eotsv_resources_rc.py not compiled. run python scripts/compile_resourcefiles.py first.'
        initAll()

    @classmethod
    def tearDownClass(cls):
        cls.assertTrue(EOTimeSeriesViewer.instance() is None, 'EOTimeSeriesViewer instance was not closed')

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
        self.taskManagerProcessEvents()
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
    def createTemporalProfileDict() -> Dict[str, Any]:
        """
        Returns an exemplary temporal profile dictionary
        with a multi-sensor timeseries of 2 sensors.
        :return: dict
        """
        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
        from example.Images import re_2014_06_25

        tss1 = TimeSeriesSource.create(Img_2014_01_15_LC82270652014015LGN00_BOA)
        tss2 = TimeSeriesSource.create(re_2014_06_25)
        lyr1 = tss1.asRasterLayer()
        lyr2 = tss2.asRasterLayer()

        sensorIDs = []
        values = []
        sensors = []
        dates = []

        def addValues(lyr: QgsRasterLayer, datetime: str):
            sid = lyr.customProperty(SensorInstrument.PROPERTY_KEY)
            extent = lyr.extent()
            # random point within the extent
            x = np.random.uniform(extent.xMinimum(), extent.xMaximum())
            y = np.random.uniform(extent.yMinimum(), extent.yMaximum())
            point = QgsPointXY(x, y)
            val = TemporalProfileUtils.profileValues(lyr, point)
            values.append(val)
            if sid not in sensorIDs:
                sensorIDs.append(sid)
            sensors.append(sensorIDs.index(sid))
            dates.append(datetime)

            s = ""

        addValues(lyr1, '2024-01-01')
        addValues(lyr1, '2024-01-02')
        addValues(lyr2, '2024-01-03')
        addValues(lyr2, '2024-01-04')

        profileDict = {TemporalProfileUtils.SensorIDs: sensorIDs,
                       TemporalProfileUtils.Sensor: sensors,
                       TemporalProfileUtils.Date: dates,
                       TemporalProfileUtils.Values: values}
        assert TemporalProfileUtils.isProfileDict(profileDict)
        success, error = TemporalProfileUtils.verifyProfile(profileDict)
        assert success, error
        return profileDict

    @staticmethod
    def createTimeSeries(precision: DateTimePrecision = DateTimePrecision.Day) -> TimeSeries:

        TS = TimeSeries()
        TS.setDateTimePrecision(precision)
        # files = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        files = file_search(DIR_EXAMPLES / 'Images', '*.tif', recursive=True)
        TS.addSources(list(files), runAsync=False)
        assert len(TS) > 0
        return TS

    @staticmethod
    def createProfileLayer(timeseries: TimeSeries = None) -> QgsVectorLayer:

        if timeseries is None:
            timeseries = TestObjects.createTimeSeries()
        layer = TemporalProfileUtils.createProfileLayer()
        assert isinstance(layer, QgsVectorLayer)
        assert layer.isValid()

        tpFields = TemporalProfileUtils.temporalProfileFields(layer)
        assert isinstance(tpFields, QgsFields)
        assert tpFields.count() > 0

        sources = timeseries.sourceUris()
        l0 = QgsRasterLayer(sources[0])
        ns, nl = l0.width(), l0.height()
        m2p: QgsMapToPixel = rasterLayerMapToPixel(l0)
        points = [m2p.toMapCoordinates(0, 0),
                  m2p.toMapCoordinates(int(0.5 * ns), int(0.5 * nl)),
                  m2p.toMapCoordinates(ns - 1, nl - 1)]

        task = LoadTemporalProfileTask(sources, points, crs=l0.crs(), n_threads=os.cpu_count(),
                                       description='Load example temporal profiles')
        task.run_serial()

        new_features: List[QgsFeature] = list()
        for profile, point in zip(task.profiles(), task.profilePoints()):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(point.asWkt()))
            # profileJson = TemporalProfileUtils.profileJsonFromDict(profile)
            assert TemporalProfileUtils.verifyProfile(profile)
            f.setAttribute(tpFields[0].name(), profile)
            new_features.append(f)

        with edit(layer):
            if not layer.addFeatures(new_features):
                err = layer.error()
                if isinstance(err, QgsError):
                    raise err.message()

        layer.setDisplayExpression("format('Feature %1', $id)")
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
        uid = uuid.uuid4()
        for pathSrc in files[0:10]:
            bn = os.path.basename(pathSrc)
            pathDst = f'/vsimem/{uid}_shifted_{bn}.bsq'
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
            del dsDst
            dsDst = None
            dsDst = gdal.Open(pathDst)
            assert list(dsDst.GetGeoTransform()) == gt
            movedFiles.append(pathDst)

        final = []
        for f1, f2 in zip(files, movedFiles):
            final.append(f1)
            final.append(f2)
        return final
