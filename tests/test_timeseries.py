# -*- coding: utf-8 -*-
"""Tests QGIS plugin init."""
import os
import re
import unittest

import numpy as np
from osgeo import gdal, osr
from qgis._core import QgsDateTimeRange
from qgis.gui import QgsMapCanvas, QgsTaskManagerWidget
from qgis.core import Qgis, QgsApplication, QgsMimeDataUtils, QgsProject, QgsRasterLayer
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QAbstractItemModel, QAbstractTableModel, QMimeData, QPointF, QSortFilterProxyModel, Qt, \
    QUrl
from qgis.PyQt.QtGui import QDropEvent
from qgis.PyQt.QtWidgets import QTableView, QTreeView

import example
import example.Images
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialExtent, SpatialPoint
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from eotimeseriesviewer.timeseries import DateTimePrecision, registerDataProvider, sensorID, SensorInstrument, \
    SensorMatching, SensorMockupDataProvider, TimeSeries, TimeSeriesDate, TimeSeriesDock, TimeSeriesFindOverlapTask, \
    TimeSeriesSource

start_app()


class TestTimeSeries(EOTSVTestCase):

    def createTestDatasets(self):
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

    def createTimeSeries(self) -> TimeSeries:
        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
        TS = TimeSeries()
        self.assertIsInstance(TS, TimeSeries)
        TS.addSources(files)
        self.assertTrue(len(TS) > 0)
        return TS

    def test_loadfromfile(self):
        ts = TimeSeries()
        import example
        files = [example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA,
                 example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                 example.Images.re_2014_06_25,
                 example.Images.re_2014_08_20]
        for f in files:
            self.assertTrue(os.path.isfile(f))
        ts.addSources(files, runAsync=False)
        self.assertTrue(len(ts) == len(files))

        # save time series, absolute paths
        pathTSFileAbs = self.createTestOutputDirectory() / 'timeseries_abs.txt'
        ts.saveToFile(pathTSFileAbs, relative_path=False)
        self.assertTrue(os.path.isfile(pathTSFileAbs))

        # save time series, relative paths
        pathTSFileRel = self.createTestOutputDirectory() / 'timeseries_rel.txt'
        ts.saveToFile(pathTSFileRel, relative_path=False)
        self.assertTrue(os.path.isfile(pathTSFileRel))

        # load time series
        tsAbs = TimeSeries()
        tsAbs.loadFromFile(pathTSFileAbs, runAsync=False)
        self.assertTrue(len(tsAbs) == len(files))

        tsRel = TimeSeries()
        tsRel.loadFromFile(pathTSFileAbs, runAsync=False)
        self.assertTrue(len(tsRel) == len(files))

    def test_TimeSeriesFindOverlapTask(self):

        import example

        tss = TimeSeriesSource(example.exampleNoDataImage)
        self.assertIsInstance(tss, TimeSeriesSource)

        overlapped = []

        def onOverlapp(overlapp: dict):
            for tss, is_overlapp in overlapp.items():
                self.assertIsInstance(tss, str)
                self.assertTrue(is_overlapp in [True, False, None])

                overlapped.append(is_overlapp)

        def onFinished(success, task):
            self.assertIsInstance(task, TimeSeriesFindOverlapTask)

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
            task = TimeSeriesFindOverlapTask(ext, [tss], sample_size=3, callback=onFinished)
            task.sigTimeSeriesSourceOverlap.connect(onOverlapp)
            task.finished(task.run())
            self.assertTrue(task.mError is None, msg=f'Task returned error {task.mError}')

        self.assertListEqual(overlapped, [True, False, False])

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

        tsd = TimeSeriesDate(None, tss.date(), sensor)
        tsd2 = TimeSeriesDate(None, tss.date(), sensor)
        self.assertIsInstance(tsd, TimeSeriesDate)
        self.assertEqual(tsd, tsd2)
        self.assertEqual(tsd.sensor(), sensor)
        self.assertEqual(len(tsd), 0)
        tsd.addSource(tss)
        tsd.addSource(tss)
        self.assertEqual(len(tsd), 1)

        self.assertTrue(tsd.year() == 2014)
        self.assertTrue(tsd.doy() == 79)
        self.assertIsInstance(tsd.decimalYear(), float)
        self.assertTrue(tsd.decimalYear() >= 2014 and tsd.decimalYear() < 2015)

        self.assertIsInstance(tsd, QAbstractTableModel)
        for r in range(len(tsd)):
            for i in range(len(TimeSeriesDate.ColumnNames)):
                value = tsd.data(tsd.createIndex(r, i), role=Qt.DisplayRole)

        TV = QTableView()
        TV.setModel(tsd)
        self.showGui(TV)

    def test_tsd_daterange(self):

        ts = TestObjects.createTimeSeries(DateTimePrecision.Day)
        ts.setDateTimePrecision(DateTimePrecision.Day)
        for tsd in ts:

            date = tsd.date()
            t_range = tsd.temporalRange()
            self.assertIsInstance(t_range, QgsDateTimeRange)
            self.assertTrue(t_range.contains(tsd.qDateTime()))
            for tss in tsd:
                tss: TimeSeriesSource
                self.assertTrue(t_range.contains(tss.qDateTime()))

    def test_TimeSeriesSource(self):

        sources = [example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                   gdal.Open(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA),
                   QgsRasterLayer(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA)
                   ]

        ref = None
        for src in sources:
            print('Test input source: {}'.format(src))
            tss = TimeSeriesSource.create(src)
            self.assertIsInstance(tss.spatialExtent(), SpatialExtent)
            self.assertIsInstance(tss, TimeSeriesSource)

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
            self.assertEqual(lyr.width(), tss.ns)
            self.assertEqual(lyr.height(), tss.nl)
            ext1 = SpatialExtent.fromLayer(lyr)
            ext2 = tss.spatialExtent()
            if ext1 != ext2:
                s = ""
            self.assertEqual(SpatialExtent.fromLayer(lyr), tss.spatialExtent())

        import pickle

        dump = pickle.dumps(tss)
        tss2 = pickle.loads(dump)
        self.assertIsInstance(tss2, TimeSeriesSource)
        self.assertEqual(tss, tss2)

        json = tss.json()
        self.assertIsInstance(json, str)
        tss3 = TimeSeriesSource.fromJson(json)
        self.assertIsInstance(tss3, TimeSeriesSource)
        self.assertEqual(tss, tss3)

    def test_sensorMatching(self):

        testDir = r'Q:\Processing_BJ\99_EOTSV_RapidEye'
        if os.path.isdir(testDir):
            sensors = set()
            files = list(file_search(testDir, re.compile(r'.*RE.*\d+\.tif$'), recursive=True))
            tssList = []
            for file in files:
                tss = TimeSeriesSource.create(file)
                self.assertIsInstance(tss, TimeSeriesSource)
                sid = tss.sid()
                sensor = SensorInstrument(sid)
                self.assertIsInstance(sensor, SensorInstrument)
                sensors.add(sensor)
                tssList.append(tss)

            TS = TimeSeries()
            TS.setSensorMatching(SensorMatching.PX_DIMS)
            TS.addSources(files, runAsync=False)
            self.assertTrue(len(TS.sensors()) == 1)

            TS = TimeSeries()
            TS.setSensorMatching(SensorMatching.PX_DIMS | SensorMatching.NAME | SensorMatching.WL)
            TS.addSources(files, runAsync=False)
            self.assertTrue(len(TS.sensors()) == len(sensors))

            s = ""

    def test_datetimeprecision(self):

        img1 = TestObjects.createRasterDataset()
        img2 = TestObjects.createRasterDataset()
        self.assertIsInstance(img1, gdal.Dataset)
        self.assertIsInstance(img2, gdal.Dataset)
        t0 = np.datetime64('now')

        pairs = [('2018-12-23T14:40:48', '2018-12-23T14:40:47', DateTimePrecision.Minute),
                 ('2018-12-23T14:40', '2018-12-23T14:39', DateTimePrecision.Hour),
                 ('2018-12-23T14:40:48', '2018-12-23T14:40:47', DateTimePrecision.Day),
                 ('2018-12-23', '2018-12-22', DateTimePrecision.Week),
                 ('2018-12-23', '2018-12-01', DateTimePrecision.Month),
                 ('2018-12-23', '2018-11-01', DateTimePrecision.Year),
                 ]
        for p in pairs:
            t1, t2, precision = p
            img1.SetMetadataItem('acquisition time', t1)
            img2.SetMetadataItem('acquisition time', t2)
            img1.FlushCache()
            img2.FlushCache()

            TS = TimeSeries()
            self.assertIsInstance(TS, TimeSeries)
            self.assertTrue(TS.mDateTimePrecision == DateTimePrecision.Original)
            TS.addSources([img1, img2], runAsync=False)
            self.assertTrue(len(TS) == 2)

            TS = TimeSeries()
            TS.setDateTimePrecision(precision)
            TS.addSources([img1, img2], runAsync=False)
            self.assertTrue(len(TS) == 1)

    def test_multisource_tsd(self):

        p1 = TestObjects.createRasterDataset()
        p2 = TestObjects.createRasterDataset()

        sources = [p1, p2]
        for p in sources:
            p.SetMetadataItem('acquisition_date', '2014-04-01')
            p.FlushCache()
            s = ""

        TS = TimeSeries()
        self.assertTrue(len(TS) == 0)

        TS.addSources(sources, runAsync=False)
        self.assertEqual(len(TS), 1)

        tsd = TS[0]
        self.assertIsInstance(tsd, TimeSeriesDate)
        self.assertTrue(len(tsd.sources()) == 2)

        paths = TestObjects.createMultiSourceTimeSeries()
        TS = TimeSeries()
        TS.addSources(paths, runAsync=False)
        srcUris = TS.sourceUris()
        self.assertTrue(len(srcUris) == len(paths))
        self.assertTrue(len(TS) == 0.5 * len(paths))
        self.assertTrue(len(TS) == 0.5 * len(srcUris))

    def test_timeseries_loadasync(self):

        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
        self.assertTrue(len(files) > 0)
        w = QgsTaskManagerWidget(QgsApplication.taskManager())

        TS = TimeSeries()
        TS.addSources(files, runAsync=True)
        TS.addSources(files, runAsync=True)
        TS.addSources(files, runAsync=True)

        self.taskManagerProcessEvents()

        self.assertTrue(len(files) == len(TS))
        self.showGui(w)

    def test_blockremove(self):

        TS = TestObjects.createTimeSeries()

        to_remove = TS[0:2] + TS[-2:]
        TS.removeTSDs(to_remove)
        for tsd in to_remove:
            self.assertTrue(tsd not in TS)

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
        TS.addSources(files, runAsync=False)

        counts = dict()
        for i, tsd in enumerate(TS):
            self.assertIsInstance(tsd, TimeSeriesDate)
            sensor = tsd.sensor()
            if sensor not in counts.keys():
                counts[sensor] = 0
            counts[sensor] = counts[sensor] + 1

        self.assertEqual(len(files), len(TS))
        self.assertEqual(len(addedDates), len(TS))

        self.assertTrue(len(TS) > 0)
        self.assertEqual(TS.columnCount(), len(TS.mColumnNames))
        self.assertEqual(TS.rowCount(), len(TS))

        self.assertEqual(len(removedDates), 0)
        self.assertTrue(len(addedSensors) == 2)

        self.assertIsInstance(TS.maxSpatialExtent(), SpatialExtent)

        sensor = TS.sensors()[0]
        self.assertIsInstance(sensor, SensorInstrument)
        self.assertTrue(sensor == TS.sensor(sensor.id()))
        TS.removeSensor(sensor)
        self.assertEqual(counts[sensor], len(removedDates))

        extent = TS.maxSpatialExtent()
        self.assertIsInstance(extent, SpatialExtent)

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

        lyr = QgsRasterLayer(sid, 'TestLayer2', SensorMockupDataProvider.providerKey())

        canvas = QgsMapCanvas()
        canvas.show()
        canvas.setLayers([lyr])
        canvas.zoomToFullExtent()
        self.showGui(canvas)

    def test_sensor_proxy_layer_provider_footprint(self):
        registerDataProvider()

        def print_provider_references():
            print(' # : object id    : sip.isdeleted()')
            for i, (oid, p) in enumerate(SensorMockupDataProvider.ALL_INSTANCES.items()):
                print(f'{i:2} : {oid}: {sip.isdeleted(p)}')

        print('Before:')
        print_provider_references()
        sid = sensorID(100, 200, 300, Qgis.DataType.Float32)

        # create multiple layers with this data provider:
        layer = None
        keep_layers = []
        for i in range(10):
            layer = QgsRasterLayer(sid, 'test layer', SensorMockupDataProvider.providerKey())
            if i % 2 == 0:
                keep_layers.append(layer)
        # draw layers
        print('Before drawing layers:')
        print_provider_references()
        c = QgsMapCanvas()
        c.setLayers(keep_layers)
        c.mapSettings().setDestinationCrs(layer.crs())
        c.setExtent(layer.extent())

        print('After drawing layers:')
        print_provider_references()
        del keep_layers

        print('After deleting layers:')
        print_provider_references()

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

        TS = TimeSeries()
        self.assertIsInstance(TS, QAbstractItemModel)
        sources = TestObjects.createMultiSourceTimeSeries()

        # 1. and 2.nd image should have same date
        # -> 1 image group with 2 source images
        TS.addSources(sources[0:1], runAsync=False)
        self.assertTrue(len(TS) == 1)
        TS.addSources(sources[1:2], runAsync=False)
        self.assertTrue(len(TS) == 1)
        self.assertTrue(len(TS[0]) == 2)

        self.assertTrue(len(TS) > 0)
        self.assertTrue(TS.rowCount(TS.index(0, 0)) == 2)

        TS.addSources(sources[2:], runAsync=False)
        self.assertEqual(len(TS), TS.rowCount())
        M = QSortFilterProxyModel()
        M.setSourceModel(TS)
        TV = QTreeView()
        TV.setSortingEnabled(True)
        TV.setModel(M)

        self.showGui(TV)

    def test_TimeSeriesDock(self):

        TS = TimeSeries()
        TS.addSources(TestObjects.createMultiSourceTimeSeries())

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

        self.showGui(dock)


if __name__ == '__main__':
    unittest.main(buffer=False, failfast=True)
