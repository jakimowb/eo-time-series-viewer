# coding=utf-8
"""Tests QGIS plugin init."""

import os
import unittest
import example
import example.Images
from osgeo import gdal, ogr, osr
from eotimeseriesviewer.utils import file_search
from eotimeseriesviewer.tests import TestObjects
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer.tests import initQgisApplication

QAPP = initQgisApplication()

class TestInit(unittest.TestCase):

    def createTestDatasets(self):

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
            p = '{}tmpstack{}.bsq'.format(vsiDir, i+1)

            ds = drv.Create(p, ns, nl, len(r), eType=gdal.GDT_Float32)
            assert isinstance(ds, gdal.Dataset)

            ds.SetProjection(crs.ExportToWkt())

            dateString = ','.join([str(d) for d in r])
            dateString = '{{{}}}'.format(dateString)
            ds.SetMetadataItem('wavelength', dateString, 'ENVI')

            for b, date in enumerate(r):
                decimalYear = date2num(date)

                band = ds.GetRasterBand(b+1)
                assert isinstance(band, gdal.Band)
                band.Fill(decimalYear)
            ds.FlushCache()
            datasets.append(p)





        return datasets


    def createTimeSeries(self)->TimeSeries:

        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
        TS = TimeSeries()
        self.assertIsInstance(TS, TimeSeries)
        TS.addSources(files)
        self.assertTrue(len(TS) > 0)
        return TS

    def test_sensorids(self):

        configs = [(6, 30, 30, gdal.GDT_Byte, [1, 2, 3, 4, 5, 6], None),
                   (6, 10, 20, gdal.GDT_CFloat32, [1, 2, 3, 4, 5, 6], 'index'),
                   (6, 30, 30, gdal.GDT_UInt32, [1, 2, 3, 323, 23., 3.4], 'Micrometers'),
                   (6, 30, 30, gdal.GDT_Int32, None, None),
        ]

        for conf in configs:
            #nb:int, px_size_x:float, px_size_y:float, dt:int, wl:list, wlu:str
            print(conf)
            self.assertIsInstance(sensorID(*conf), str, msg='Unable to create sensorID from "{}"'.format(str(conf)))
            sid = sensorID(*conf)

            c2 = sensorIDtoProperties(sid)
            self.assertListEqual(list(conf), list(c2))

    def test_TimeSeriesTableModel(self):

        TS = self.createTimeSeries()
        TM = TimeSeriesTableModel(TS)

        self.assertTrue(len(TS) > 0)
        self.assertIsInstance(TM, TimeSeriesTableModel)
        self.assertIsInstance(TM, QAbstractTableModel)

        self.assertTrue(TM.rowCount(None) == len(TS))

        tsd = TS[2]

        idx = TM.getIndexFromDate(tsd)
        self.assertIsInstance(idx, QModelIndex)

    def test_timeseriesdatum(self):

        file = example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA

        tss = TimeSeriesSource.create(file)
        sensor = SensorInstrument(tss.sid())

        tsd = TimeSeriesDatum(None, tss.date(), sensor)
        tsd2 = TimeSeriesDatum(None, tss.date(), sensor)
        self.assertIsInstance(tsd, TimeSeriesDatum)
        self.assertEqual(tsd, tsd2)
        self.assertEqual(tsd.sensor(), sensor)
        self.assertEqual(len(tsd), 0)
        tsd.addSource(tss)
        self.assertEqual(len(tsd), 1)

        self.assertTrue(tsd.year() == 2014)
        self.assertTrue(tsd.doy() == 79)
        self.assertIsInstance(tsd.decimalYear(), float)
        self.assertTrue(tsd.decimalYear() >= 2014 and tsd.decimalYear() < 2015)

    def test_timeseriessource(self):
        wcs = r'dpiMode=7&identifier=BGS_EMODNET_CentralMed-MCol&url=http://194.66.252.155/cgi-bin/BGS_EMODnet_bathymetry/ows?VERSION%3D1.1.0%26coverage%3DBGS_EMODNET_CentralMed-MCol'

        if False:
            webSources = [QgsRasterLayer(wcs, 'test', 'wcs')]

            for src in webSources:
                tss = TimeSeriesSource.create(src)
                self.assertIsInstance(tss, TimeSeriesSource)


        sources = [example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA,
                   gdal.Open(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA),
                   QgsRasterLayer(example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA)
                   ]

        ref = None
        for src in sources:

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


    def test_datetimeprecision(self):

        img1 = TestObjects.inMemoryImage()
        img2 = TestObjects.inMemoryImage()
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
            TS = TimeSeries()
            self.assertIsInstance(TS, TimeSeries)
            self.assertTrue(TS.mDateTimePrecision == DateTimePrecision.Original)
            TS.addSources([img1, img2])
            self.assertTrue(len(TS) == 2)

            TS = TimeSeries()
            TS.setDateTimePrecision(precision)
            TS.addSources([img1, img2])
            self.assertTrue(len(TS) == 1)

    def test_multisource_tsd(self):



        p1 = TestObjects.inMemoryImage()
        p2 = TestObjects.inMemoryImage()

        sources = [p1, p2]
        for p in sources:
            p.SetMetadataItem('acquisition_date', '2014-04-01')
            s = ""

        tssList = [TimeSeriesSource.create(p) for p in sources]

        TS = TimeSeries()
        self.assertTrue(len(TS) == 0)

        TS.addSources(tssList)
        self.assertTrue(len(TS) == 1)

        tsd = TS[0]
        self.assertIsInstance(tsd, TimeSeriesDatum)
        self.assertTrue(len(tsd.sources()) == 2)

        paths = TestObjects.createMultiSourceTimeSeries()
        TS = TimeSeries()
        TS.addSources(paths)
        srcUris = TS.sourceUris()
        self.assertTrue(len(srcUris) == len(paths))
        self.assertTrue(len(TS) == 0.5 * len(paths))
        self.assertTrue(len(TS) == 0.5 * len(srcUris))


    def test_timeseries(self):

        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))

        addedDates = []
        removedDates = []
        addedSensors = []
        removedSensors = []
        sourcesChanged = []

        TS = TimeSeries()
        self.assertIsInstance(TS, TimeSeries)
        TS.sigTimeSeriesDatesAdded.connect(lambda dates: addedDates.extend(dates))
        TS.sigTimeSeriesDatesRemoved.connect(lambda dates: removedDates.extend(dates))
        TS.sigSourcesChanged.connect(lambda tsd: sourcesChanged.append(tsd))
        TS.sigSensorAdded.connect(lambda sensor: addedSensors.append(sensor))
        TS.sigSensorRemoved.connect(lambda sensor:removedSensors.append(sensor))
        TS.addSources(files)

        counts = dict()
        for i, tsd in enumerate(TS):
            self.assertIsInstance(tsd, TimeSeriesDatum)
            sensor = tsd.sensor()
            if sensor not in counts.keys():
                counts[sensor] = 0
            counts[sensor] = counts[sensor] + 1

        self.assertEqual(len(files), len(TS))
        self.assertEqual(len(addedDates), len(TS))





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

        lyr = sensor.proxyLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)

    def test_datematching(self):
        pass



if __name__ == '__main__':
    unittest.main()

QAPP.quit()