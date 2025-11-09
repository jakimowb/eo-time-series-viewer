# -*- coding: utf-8 -*-
"""Tests QGIS plugin init."""
import json
import logging
import os
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal

import example
import example.Images
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.subdatasets import subLayerDetails
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialExtent, SpatialPoint
from eotimeseriesviewer.sensors import registerDataProvider, sensorID, SensorInstrument, SensorMockupDataProvider
from eotimeseriesviewer.tasks import EOTSVTask
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects, EOTSV_TIMESERIES_JSON
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource
from eotimeseriesviewer.timeseries.tasks import TimeSeriesFindOverlapSubTask, TimeSeriesFindOverlapTask, \
    TimeSeriesLoadingTask
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from eotimeseriesviewer.timeseries.widgets import TimeSeriesDock
from qgis.PyQt.QtCore import QAbstractItemModel, QDateTime, QMimeData, QPointF, \
    QSortFilterProxyModel, Qt, QUrl
from qgis.PyQt.QtGui import QDropEvent
from qgis.PyQt.QtWidgets import QTreeView
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsDateTimeRange, QgsMimeDataUtils, \
    QgsProject, QgsRasterLayer, QgsVector
from qgis.core import QgsGeometry, QgsFeature
from qgis.gui import QgsTaskManagerWidget

start_app()

logger = logging.getLogger(__name__)


class TestTimeSeries(EOTSVTestCase):

    @unittest.skipIf(EOTSVTestCase.runsInCI() or not EOTSV_TIMESERIES_JSON.is_file(),
                     'EOTSV_TIMESERIES_JSON is undefined')
    def test_add_thousands(self):

        with open(EOTSV_TIMESERIES_JSON, 'r') as f:
            data = json.load(f)

            for d in data['sources']:
                p = Path(d['source'])
                if not p.is_absolute():
                    p = EOTSV_TIMESERIES_JSON.parent / p
                    d['source'] = str(p)

        t0 = None

        def dt(msg: Optional[str] = None):
            nonlocal t0
            n = datetime.now()
            d = n - t0
            t0 = n
            logger.info(f'{msg}: {d}')
            return d

        # TS = TimeSeries()
        TSV = EOTimeSeriesViewer()
        TS = TSV.timeSeries()
        t0 = datetime.now()

        sources = [TimeSeriesSource.fromMap(d) for d in data['sources']]
        # sources = sources[0:10]
        n = len(sources)
        dt0 = dt(f'loading {n} TimeSeriesSources from json')
        TS.addSources(sources)
        dt2 = dt(f'adding {n} TimeSeriesSource to TimeSeries')

        self.showGui(TSV.ui)
        TSV.close()

    def test_loadfromfile_csv(self):
        ts = TimeSeries()
        import example
        files = [example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA,
                 example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                 example.Images.re_2014_06_25,
                 example.Images.re_2014_08_20]
        for f in files:
            self.assertTrue(os.path.isfile(f))
        ts.addSourceInputs(files, runAsync=False)
        self.assertTrue(len(ts) == len(files))

        # save time series, absolute paths
        pathTSFileAbs = self.createTestOutputDirectory() / 'timeseries_abs.txt'
        ts.saveToFile(pathTSFileAbs, relative_path=False)
        self.assertTrue(os.path.isfile(pathTSFileAbs))

        # save time series, relative paths
        pathTSFileRel = self.createTestOutputDirectory() / 'timeseries_rel.txt'
        ts.saveToFile(pathTSFileRel, relative_path=True)
        self.assertTrue(os.path.isfile(pathTSFileRel))

        # load time series
        tsAbs = TimeSeries()
        tsAbs.loadFromFile(pathTSFileAbs, runAsync=False)
        self.assertTrue(len(tsAbs) == len(files))

        tsRel = TimeSeries()
        tsRel.loadFromFile(pathTSFileAbs, runAsync=False)
        self.assertTrue(len(tsRel) == len(files))

    def test_loadfromfile_json(self):
        ts = TimeSeries()
        import example
        files = [example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA,
                 example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                 example.Images.re_2014_06_25,
                 example.Images.re_2014_08_20]
        for f in files:
            self.assertTrue(os.path.isfile(f))
        ts.addSourceInputs(files, runAsync=False)
        self.assertTrue(len(ts) == len(files))

        # save time series, absolute paths
        pathTSFileAbs = self.createTestOutputDirectory() / 'timeseries_abs.json'
        ts.saveToFile(pathTSFileAbs, relative_path=False)
        self.assertTrue(os.path.isfile(pathTSFileAbs))

        # save time series, relative paths
        pathTSFileRel = self.createTestOutputDirectory() / 'timeseries_rel.json'
        ts.saveToFile(pathTSFileRel, relative_path=True)
        self.assertTrue(os.path.isfile(pathTSFileRel))

        # load time series
        tsRel = TimeSeries()
        tsRel.loadFromFile(pathTSFileRel, runAsync=False)
        self.assertTrue(len(tsRel) == len(files))
        for tss in tsRel.sources():
            self.assertTrue(Path(tss.source()).is_file())

        tsAbs = TimeSeries()
        tsAbs.loadFromFile(pathTSFileAbs, runAsync=False)
        self.assertTrue(len(tsAbs) == len(files))
        for tss in tsAbs.sources():
            self.assertTrue(Path(tss.source()).is_file())

    @unittest.skipIf(os.environ.get('GITHUB_ACTIONS') == 'true', 'Skipping this test on GitHub Actions')
    def test_focus_visibility(self):

        ts = TestObjects.createTimeSeries()

        extentMax = ts.maxSpatialExtent()
        extent1 = extentMax + QgsVector(extentMax.width() + 1, extentMax.height() + 1)
        extent2 = extentMax.toCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        extent1 = SpatialExtent(extentMax.crs(), extent1)
        self.assertFalse(extentMax.intersects(extent1))

        doi = ts[25].dtg()

        ts.focusVisibility(extent1, date_of_interest=doi, runAsync=True)
        self.taskManagerProcessEvents()

        for tss in ts.sources():
            ext = tss.spatialExtent().toCrs(extent1.crs())
            self.assertFalse(ext.intersects(extent1))
            self.assertFalse(tss.isVisible())

        ts.focusVisibility(extent2, runAsync=True)
        self.taskManagerProcessEvents()
        for tss in ts.sources():
            ext = tss.spatialExtent().toCrs(extent2.crs())
            self.assertTrue(ext.intersects(extent2))
            self.assertTrue(tss.isVisible())

        ts.clear()

    def test_TimeSeriesFindOverlapSubTask(self):

        ts = TestObjects.createTimeSeries()
        sources = [str(example.exampleNoDataImage)] + ts.sourceUris()

        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        extent = ts.maxSpatialExtent().toCrs(crs)

        task = TimeSeriesFindOverlapSubTask(extent, crs, sources)
        self.assertTrue(task.run())

        for src in sources:
            self.assertTrue(src in task.intersections)

        ts.clear()

    def test_TimeSeriesFindOverlapTask(self):

        ts = TestObjects.createTimeSeries()

        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        extent = ts.maxSpatialExtent().toCrs(crs)
        doi = ts[25].dtg()

        all_overlaps = dict()

        n_calls = 0

        def onOverlapsFound(results: dict):
            nonlocal n_calls
            all_overlaps.update(results)
            n_calls += 1

        task = TimeSeriesFindOverlapTask(extent, ts.sources(), date_of_interest=doi)
        task.sigTimeSeriesSourceOverlap.connect(onOverlapsFound)
        task.run_task_manager()

        s = ""

        self.taskManagerProcessEvents()
        tss = TimeSeriesSource.create(example.exampleNoDataImage)
        self.assertIsInstance(tss, TimeSeriesSource)

        overlapped = []

        def onOverlapp(overlapp: dict):
            for tss, is_overlapp in overlapp.items():
                self.assertIsInstance(tss, str)
                self.assertTrue(is_overlapp in [True, False, None])

                overlapped.append(is_overlapp)

        def onFinished(success, results):
            self.assertTrue(success)
            self.assertIsInstance(results, EOTSVTask)

        ext_full = tss.spatialExtent()
        ext_nodata = SpatialExtent(ext_full.crs(),
                                   ext_full.xMinimum(),
                                   ext_full.yMinimum(),
                                   ext_full.xMinimum() + 4 * 30,
                                   ext_full.yMaximum())

        ext_outofbounds = SpatialExtent(ext_full.crs(),
                                        ext_full.xMinimum() - 100,
                                        ext_full.yMinimum(),
                                        ext_full.xMinimum() - 10,
                                        ext_full.yMaximum())

        for ext in [ext_full, ext_nodata, ext_outofbounds]:
            task = TimeSeriesFindOverlapTask(ext, [tss], sample_size=3)
            task.executed.connect(onFinished)
            task.sigTimeSeriesSourceOverlap.connect(onOverlapp)
            task.run_task_manager()
            self.assertEqual(task.errors(), [], msg=f'Task returned errors: {task.errors()}')

        self.assertListEqual(overlapped, [True, False, False])

        ts.clear()

    def test_find_overlap_memory_leak(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer
        EOTSV = EOTimeSeriesViewer()
        EOTSV.loadExampleTimeSeries(loadAsync=False)
        EOTSV.ui.show()

        TS: TimeSeries = EOTSV.timeSeries()
        ext: SpatialExtent = TS.maxSpatialExtent()
        center: SpatialPoint = ext.spatialCenter()

        self.showGui(EOTSV.ui)
        EOTSV.close()
        QgsProject.instance().removeAllMapLayers()
        s = ""

    def test_TimeSeriesDate(self):

        file = example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA

        tss = TimeSeriesSource.create(file)
        tss2 = TimeSeriesSource.create(example.Images.Img_2014_07_02_LE72270652014183CUB00_BOA)
        sensor = SensorInstrument(tss.sid())
        dtr = ImageDateUtils.dateRange(tss.dtg())

        tsd = TimeSeriesDate(dtr, sensor)
        tsd2 = TimeSeriesDate(dtr, sensor)

        self.assertIsInstance(tsd, TimeSeriesDate)
        self.assertEqual(tsd, tsd2)
        self.assertEqual(tsd.sensor(), sensor)
        self.assertEqual(len(tsd), 0)

        tsd.addSources(tss)
        tsd.addSources(tss)
        self.assertEqual(len(tsd), 1)

        self.assertTrue(tsd.year() == 2014)
        self.assertTrue(tsd.doy() == 79)
        self.assertIsInstance(tsd.decimalYear(), float)
        self.assertTrue(tsd.decimalYear() >= 2014 and tsd.decimalYear() < 2015)

    def test_tsd_daterange(self):

        ts = TestObjects.createTimeSeries(DateTimePrecision.Day)
        ts.setDateTimePrecision(DateTimePrecision.Day)
        for tsd in ts:

            t_range = tsd.dateTimeRange()
            self.assertIsInstance(t_range, QgsDateTimeRange)
            self.assertTrue(t_range.contains(tsd.dtg()))
            for tss in tsd:
                tss: TimeSeriesSource
                self.assertTrue(t_range.contains(tss.dtg()))

        ts.clear()

    def test_add_sources(self):

        d = {}
        dtg1 = QDateTime.fromString('2014-04-02', Qt.ISODate)
        dtg2 = QDateTime.fromString('2014-04-03', Qt.ISODate)
        dtr = QgsDateTimeRange(dtg1, dtg2)
        dtr2 = QgsDateTimeRange(dtg1, dtg2)

        sid = 'foobar'
        d[(dtr.begin(), sid)] = 'foo'

        assert (dtr2.begin(), sid) in d

        ts = TimeSeries()
        tss = TimeSeriesSource.fromGDALDataset(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA)

        self.assertIsInstance(tss, TimeSeriesSource)
        ts.addSources(tss)

    def test_TimeSeriesSource(self):

        sources = [example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                   gdal.Open(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA),
                   QgsRasterLayer(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA)
                   ]

        ref = None
        for src in sources:
            print('Test input source: {}'.format(src))
            tss = TimeSeriesSource.create(src)
            self.assertIsInstance(tss, TimeSeriesSource)
            self.assertIsInstance(tss.feature(), QgsFeature)
            self.assertIsInstance(tss.geometry(), QgsGeometry)
            extent = tss.spatialExtent(source_crs=False)
            self.assertIsInstance(extent, SpatialExtent)
            self.assertEqual(extent.crs(), QgsCoordinateReferenceSystem('EPSG:4326'))

            lyr = tss.asRasterLayer()
            self.assertIsInstance(lyr, QgsRasterLayer)
            self.assertTrue(lyr.isValid())

            extent = tss.spatialExtent()
            self.assertIsInstance(extent, SpatialExtent)
            self.assertEqual(extent.crs(), lyr.crs())

            self.assertIsInstance(tss.dtg(), QDateTime)

            if not isinstance(ref, TimeSeriesSource):
                ref = tss
            else:
                self.assertTrue(ref == tss)
                self.assertTrue(ref.sid() == tss.sid())

            mdui = tss.qgsMimeDataUtilsUri()
            self.assertIsInstance(mdui, QgsMimeDataUtils.Uri)

            lyr, b = mdui.rasterLayer('')
            self.assertTrue(b)
            self.assertIsInstance(lyr, QgsRasterLayer)
            self.assertTrue(lyr.isValid())
            self.assertEqual(lyr.width(), tss.ns())
            self.assertEqual(lyr.height(), tss.nl())
            ext1 = SpatialExtent.fromLayer(lyr)
            ext_ds = SpatialExtent.fromRasterSource(tss.asDataset())
            ext2 = tss.spatialExtent(source_crs=True)

            if ext1 != ext2:
                s = ""
            self.assertEqual(SpatialExtent.fromLayer(lyr), tss.spatialExtent())

            json = tss.json()
            self.assertIsInstance(json, str)
            tss3 = TimeSeriesSource.fromJson(json)
            self.assertIsInstance(tss3, TimeSeriesSource)
            self.assertEqual(tss, tss3)
            self.assertEqual(tss.dtg(), tss3.dtg())

    def test_datetimeprecision(self):

        img1 = TestObjects.createRasterDataset()
        img2 = TestObjects.createRasterDataset()
        self.assertIsInstance(img1, gdal.Dataset)
        self.assertIsInstance(img2, gdal.Dataset)
        t0 = np.datetime64('now')

        # different timestamps but, using the provided precision,
        # each TSS pair should be linked to the same TSD
        #
        pairs = [('2018-12-23T14:40:48', '2018-12-23T14:40:47', DateTimePrecision.Minute, 1),
                 ('2018-12-23T14:40', '2018-12-23T14:39', DateTimePrecision.Hour, 1),
                 ('2018-12-23T14:40:48', '2018-12-23T14:40:47', DateTimePrecision.Day, 1),
                 ('2018-12-23', '2018-12-22', DateTimePrecision.Week, 2),
                 ('2018-12-23', '2018-12-01', DateTimePrecision.Month, 2),
                 ('2018-12-23', '2018-11-01', DateTimePrecision.Year, 2),
                 ]
        for p in pairs:
            t1, t2, precision, n_tsd_default = p
            self.assertNotEqual(t1, t2)
            img1.SetMetadataItem('acquisition time', t1)
            img2.SetMetadataItem('acquisition time', t2)
            img1.FlushCache()
            img2.FlushCache()
            images = [img1, img2]
            image_dates = [
                QDateTime.fromString(t1, Qt.ISODateWithMs),
                QDateTime.fromString(t2, Qt.ISODateWithMs),
            ]

            for dt, img in zip(image_dates, images):
                lyr = QgsRasterLayer(img.GetDescription())
                dtg = ImageDateUtils.dateTimeFromLayer(lyr)
                self.assertIsInstance(dtg, QDateTime)
                self.assertEqual(dt, dtg)
                s = ""
            TS = TimeSeries()
            self.assertIsInstance(TS, TimeSeries)
            self.assertTrue(TS.mDateTimePrecision == DateTimePrecision.Day)

            TS.addSourceInputs(images, runAsync=False)
            sources = list(TS.sources())
            self.assertEqual(2, len(sources))

            for src in sources:
                self.assertTrue(src.dtg() in image_dates)
            self.assertEqual(n_tsd_default, len(TS))

            TS.setDateTimePrecision(precision)
            TS.addSourceInputs(images, runAsync=False)
            sources = list(TS.sources())
            self.assertEqual(2, len(sources))
            self.assertEqual(1, len(TS))

    def test_multisource_tanager(self):

        path = Path(r'/Users/jakimowb/Documents/Tanager')
        if not path.is_dir():
            return

        TSV = EOTimeSeriesViewer()
        TS = TSV.timeSeries()
        files = file_search(path, re.compile(r'.*\.h5$'), recursive=True)

        sr_details = []
        for file in files:
            for sl in subLayerDetails(file):
                if sl.name().endswith('surface_reflectance'):
                    sr_details.append(sl)
                    break

        for i, sl in enumerate(sr_details):
            TS.addSourceInputs([sl], runAsync=False)

        idx0 = TS.index(0, 0)
        idx0b = TS.tsdToIdx(TS.tsds()[0])

        n_tsds = TS.rowCount()
        for r in range(TS.rowCount()):
            idxTSD = TS.index(r, 0)

            tsd = TS.data(idxTSD, Qt.UserRole)
            assert isinstance(tsd, TimeSeriesDate)
            assert idxTSD == TS.tsdToIdx(tsd)
            assert tsd == idxTSD.internalPointer()

            n_tss = TS.rowCount(idxTSD)
            assert n_tss > 0
            for r_tss in range(TS.rowCount(idxTSD)):
                idxTSS = TS.index(r_tss, 0, idxTSD)
                tss = TS.data(idxTSS, Qt.UserRole)
                assert isinstance(tss, TimeSeriesSource)
                assert idxTSS.internalPointer() == tss
                assert tss in tsd

        self.showGui(TSV.ui)
        TSV.close()
        s = ""

    def test_multisource_tsd(self):

        p1 = TestObjects.createRasterDataset()
        p2 = TestObjects.createRasterDataset()

        sources = [p1, p2]
        for p in sources:
            p.SetMetadataItem('acquisition_date', '2014-04-01')
            p.FlushCache()
            s = ""

        TS = TimeSeries()
        self.assertEqual(len(TS), 0)

        TS.addSourceInputs(sources, runAsync=False)
        self.assertEqual(len(TS), 1)

        tsd = TS[0]
        self.assertIsInstance(tsd, TimeSeriesDate)
        self.assertEqual(len(tsd.sources()), 2)

        paths = TestObjects.createMultiSourceTimeSeries()

        TS = TimeSeries()
        TS.addSourceInputs(paths, runAsync=False)
        srcUris = TS.sourceUris()

        self.assertEqual(len(srcUris), len(paths))
        self.assertEqual(len(TS), 0.5 * len(paths))
        self.assertEqual(len(TS), 0.5 * len(srcUris))

    def test_timeseries_loadasync(self):

        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
        self.assertTrue(len(files) > 0)
        w = QgsTaskManagerWidget(QgsApplication.taskManager())

        task = TimeSeriesLoadingTask(files)
        runAsync = False
        TS = TimeSeries()
        TS.addSourceInputs(files, runAsync=runAsync)
        TS.addSourceInputs(files, runAsync=runAsync)
        TS.addSourceInputs(files, runAsync=runAsync)

        self.taskManagerProcessEvents()

        self.assertTrue(len(files) == len(TS))
        self.showGui(w)

    def test_blockremove(self):

        TS = TestObjects.createTimeSeries()

        to_remove = TS[0:2] + TS[-2:]
        TS.removeTSDs(to_remove)
        for tsd in to_remove:
            self.assertTrue(tsd not in TS)

        TS.clear()

    def test_timeseries(self):

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif', recursive=True))

        addedDates = []
        removedDates = []
        addedSensors = []
        removedSensors = []
        sourcesChanged = []

        TS = TimeSeries()
        self.assertIsInstance(TS, TimeSeries)
        self.assertIsInstance(TS, QAbstractItemModel)

        TS.sigTimeSeriesDatesAdded.connect(lambda dates: addedDates.extend(dates))
        TS.sigTimeSeriesDatesRemoved.connect(lambda dates: removedDates.extend(dates))
        # TS.sigSourcesChanged.connect(lambda tsd: sourcesChanged.append(tsd))
        TS.sigSensorAdded.connect(lambda sensor: addedSensors.append(sensor))
        TS.sigSensorRemoved.connect(lambda sensor: removedSensors.append(sensor))
        TS.addSourceInputs(files, runAsync=False)

        counts = dict()
        for i, tsd in enumerate(TS):
            self.assertIsInstance(tsd, TimeSeriesDate)
            sensor = tsd.sensor()
            counts[sensor] = counts.get(sensor, 0) + 1

        counts_total = sum(counts.values())
        self.assertEqual(counts_total, len(files))

        self.assertEqual(len(files), len(TS.sourceUris()))
        self.assertEqual(len(addedDates), len(TS))

        self.assertTrue(len(TS) > 0)
        self.assertEqual(TS.columnCount(), len(TS.mColumnNames))
        self.assertEqual(TS.rowCount(), len(TS))

        self.assertEqual(len(removedDates), 0)
        self.assertTrue(len(addedSensors) == 2)

        self.assertIsInstance(TS.maxSpatialExtent(), SpatialExtent)

        sensor = TS.sensors()[0]
        self.assertIsInstance(sensor, SensorInstrument)
        self.assertEqual(sensor, TS.sensor(sensor.id()))
        TS.removeSensor(sensor)
        self.assertEqual(counts[sensor], len(removedDates))

        extent = TS.maxSpatialExtent()
        self.assertIsInstance(extent, SpatialExtent)

    def test_get_tss_from_source(self):

        TS = TimeSeries()
        sources = self.exampleRasterFiles()
        TS.addSourceInputs(sources, runAsync=False)
        self.assertEqual(len(TS), len(sources))

    def test_SensorProxyLayerMockupDataProvider(self):

        registerDataProvider()
        nb = 7
        dx = 30
        dy = 30
        sid = sensorID(nb, dx, dy, dt=Qgis.DataType.Float32)
        self.assertIsInstance(sid, str)
        sensor = SensorInstrument(sid)
        self.assertIsInstance(sensor, SensorInstrument)
        self.assertIsInstance(sensor.dataType, Qgis.DataType)

        sensor2 = SensorInstrument(sid)
        self.assertEqual(sensor, sensor2)

        lyr = QgsRasterLayer(sid, 'TestLayer', SensorMockupDataProvider.providerKey())
        del lyr

        lyr = QgsRasterLayer(sid, 'TestLayer', SensorMockupDataProvider.providerKey())
        dp = lyr.dataProvider()
        self.assertIsInstance(dp, SensorMockupDataProvider)

        dp2 = dp.clone()
        self.assertIsInstance(dp2, SensorMockupDataProvider)
        self.assertNotEqual(id(dp), id(dp2))

        s = dp2.capabilities()
        self.assertEqual(nb, dp2.bandCount())

    def test_sensors(self):

        tss = TimeSeriesSource.create(example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA)
        self.assertIsInstance(tss, TimeSeriesSource)

        sensor = SensorInstrument(tss.sid())

        sensor2 = SensorInstrument(tss.sid())
        self.assertIsInstance(sensor, SensorInstrument)
        self.assertTrue(sensor == sensor2)
        sensor2.setName('foobar')
        self.assertTrue(sensor == sensor2)

        self.assertIsInstance(sensor2.id(), str)

        lyr = sensor.proxyRasterLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)

    def test_TimeSeriesTreeModel(self):

        TS: TimeSeries = TimeSeries()
        TS.setDateTimePrecision(DateTimePrecision.Day)
        self.assertIsInstance(TS, QAbstractItemModel)
        sources = TestObjects.createMultiSourceTimeSeries()
        n_sources = len(sources)

        s1 = sources[0]
        s2 = sources[1]

        ds1 = gdal.Open(s1)
        ds2 = gdal.Open(s2)
        dtg1 = ImageDateUtils.dateTimeFromGDALDataset(ds1)
        dtg2 = ImageDateUtils.dateTimeFromGDALDataset(ds2)

        self.assertNotEqual(dtg1, dtg2)
        self.assertEqual(dtg1.date(), dtg2.date())

        TS.addSourceInputs([s1, s2], runAsync=False)
        self.assertEqual(len(TS), 1)
        self.assertEqual(TS.rowCount(), 1)
        self.assertEqual(TS.rowCount(TS.index(0, 0)), 2)
        # 1. and 2.nd image should have the same date
        # -> 1 image group with 2 source images
        TS.addSourceInputs(sources[0:1], runAsync=False)
        self.assertEqual(len(TS), 1)
        TS.addSourceInputs(sources[1:2], runAsync=False)

        self.assertEqual(len(TS), 1)
        self.assertEqual(len(TS[0]), 2)

        self.assertTrue(len(TS) > 0)
        self.assertTrue(TS.rowCount(TS.index(0, 0)) == 2)

        TS.addSourceInputs(sources[2:], runAsync=False)

        self.assertEqual(set(sources), set(TS.sourceUris()))

        self.assertEqual(len(TS), TS.rowCount())
        M = QSortFilterProxyModel()
        M.setSourceModel(TS)
        TV = QTreeView()
        TV.setSortingEnabled(True)
        TV.setModel(M)

        self.showGui(TV)

    def test_TimeSeriesDock(self):

        TS = TimeSeries()
        TS.addSourceInputs(TestObjects.createMultiSourceTimeSeries())

        dock = TimeSeriesDock()
        dock.timeSeriesWidget().setTimeSeries(TS)
        dock.show()

        urls = [QUrl.fromLocalFile(example.Images.Img_2014_07_02_LE72270652014183CUB00_BOA),
                QUrl.fromLocalFile(example.Images.Img_2014_06_08_LC82270652014159LGN00_BOA),
                ]
        md = QMimeData()
        md.setUrls(urls)
        pos = QPointF()
        event = QDropEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
        dock.timeSeriesWidget().timeSeriesTreeView().dropEvent(event)
        self.taskManagerProcessEvents()
        self.showGui(dock)


if __name__ == '__main__':
    unittest.main(buffer=False, failfast=True)
