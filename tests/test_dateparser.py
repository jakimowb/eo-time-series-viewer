import datetime
import unittest

import numpy as np
from osgeo import gdal, gdal_array
from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QTime
from qgis.core import QgsDateTimeRange, QgsRasterLayer

from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from example import exampleLandsat8, exampleNoDataImage, exampleRapidEye

start_app()


class TestDateParser(EOTSVTestCase):

    def test_timestamp(self):

        inputs = [
            QDateTime.fromString('2014-06-08T12:24:30', Qt.ISODateWithMs),
            QDate.fromString('2014-06-08', Qt.ISODate),
            datetime.datetime(2014, 6, 8, 12, 24, 30),
            datetime.date(2014, 6, 8),
        ]

        for input in inputs:
            ts = ImageDateUtils.timestamp(input)
            self.assertIsInstance(ts, float)

    def test_imagedate_utils(self):

        expected = [
            '2014-06-08T12:24:30',
            '2014-06-08',
            '2014-01-01T00:00:00',
            '2014-12-31T23:59:59.999',

        ]

        for i, example in enumerate(expected):
            year = int(example[0:4])
            dt = QDateTime.fromString(example, Qt.ISODateWithMs)
            self.assertIsInstance(dt, QDateTime)
            self.assertTrue(dt.isValid())
            dyr = ImageDateUtils.decimalYear(dt)
            self.assertIsInstance(dyr, float)
            self.assertEqual(year, int(dyr))

    def test_date_extraction(self):

        pathTmp = '/vsimem/nothing.tif'
        ds0 = TestObjects.createRasterDataset(path=pathTmp, drv='GTiff')

        examples = [
            (pathTmp, None),
            (exampleNoDataImage, QDateTime.fromString('2014-01-08', Qt.ISODate)),
            (exampleRapidEye, QDateTime.fromString('2014-06-25', Qt.ISODate)),
            (exampleLandsat8, QDateTime.fromString('2014-01-15', Qt.ISODate)),
        ]

        for (uri, expected) in examples:
            ds = gdal.Open(str(uri))
            lyr = QgsRasterLayer(str(uri))

            dtg1 = ImageDateUtils.dateTimeFromGDALDataset(ds)
            dtg2 = ImageDateUtils.dateTimeFromLayer(lyr)

            self.assertEqual(dtg1, expected)
            self.assertEqual(dtg2, expected)

        dt1 = QDateTime(QDate(2022, 1, 1), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt1), 1)

        dt2 = QDateTime(QDate(2023, 12, 31), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 365)

        dt2 = QDateTime(QDate(2024, 12, 31), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 366)
        s = ""

    def test_gdal_domains(self):

        # see https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing
        path = '/vsimem/myimage.tif'
        arr = np.ones((2, 2))

        ds: gdal.Dataset = gdal_array.SaveArray(arr, path, format='GTiff')
        ds.SetMetadataItem('ACQUISITIONDATETIME', '2024-03-02', 'IMAGERY')
        ds.FlushCache()
        del ds

        dtg = ImageDateUtils.dateTimeFromLayer(path)
        self.assertIsInstance(dtg, QDateTime)
        self.assertEqual(dtg.date(), QDate(2024, 3, 2))

        # see https://www.nv5geospatialsoftware.com/docs/ENVIHeaderFiles.html
        path = '/vsimem/envi_image.bsq'
        arr = np.ones((2, 2))

        ds: gdal.Dataset = gdal_array.SaveArray(arr, path, format='ENVI')
        ds.SetMetadataItem('acquisition time', '2025-01-02', 'ENVI')
        ds.FlushCache()
        del ds

        dtg = ImageDateUtils.dateTimeFromLayer(path)
        self.assertIsInstance(dtg, QDateTime)
        self.assertEqual(dtg.date(), QDate(2025, 1, 2))

    def test_filenames(self):

        examples = [
            '/foo2024-04-01bar/image.tif',
            '/foo20240402bar/image.tif',
            '/data/foo2024-04-03bar.tif',
            '/data/foo20240404bar.tif',
        ]

        for path in examples:
            print(f'{path} -> {ImageDateUtils.dateTimeFromString(path).toString(Qt.ISODate)}')

        path = '/vsimem/myimage.tif'
        arr = np.ones((2, 2))

        ds: gdal.Dataset = gdal_array.SaveArray(arr, path, format='GTiff')
        ds.SetMetadataItem('ACQUISITIONDATETIME', '2024-03-02', 'IMAGERY')
        ds.FlushCache()
        del ds

        dtg = ImageDateUtils.dateTimeFromLayer(path)
        assert isinstance(dtg, QDateTime)
        print(dtg.toString(Qt.ISODate))

        self.assertIsInstance(dtg, QDateTime)
        print(dtg)

    def test_datetime(self):

        example = QDateTime(QDate(2023, 4, 3), QTime(0, 8, 15))
        inputs = [
            example,
            example.toString(Qt.ISODate),
            example.toPyDateTime(),
            str(example.toPyDateTime()),
            example.toPyDateTime().timestamp(),
            example.date(),
        ]

        for input in inputs:
            dt = ImageDateUtils.datetime(input)
            self.assertIsInstance(dt, QDateTime)
            if isinstance(input, QDate):
                self.assertEqual(dt, QDateTime(input, QTime()))
            else:
                self.assertEqual(dt, example)

        d = example.date().toPyDate()
        d2 = ImageDateUtils.datetime(d)
        self.assertIsInstance(d2, QDateTime)
        self.assertEqual(d2.date(), d)

    def test_date_precission(self):
        s = ""
        examples = [
            # date , expected begin / end of date range, precission
            ('2024-12-02T12:34:23', '2024-12-02T12:34:23.000', '2024-12-02T12:34:23.999', DateTimePrecision.Second),
            ('2024-12-02T12:34:23', '2024-12-02T12:34:00', '2024-12-02T12:34:59.999', DateTimePrecision.Minute),
            ('2024-12-02T12:34:23', '2024-12-02T12:00:00', '2024-12-02T12:59:59.999', DateTimePrecision.Hour),
            ('2024-12-02T12:34:23', '2024-12-02T00:00:00', '2024-12-02T23:59:59.999', DateTimePrecision.Day),
            ('2024-12-02T12:34:23', '2024-12-01T00:00:00', '2024-12-31T23:59:59.999', DateTimePrecision.Month),
            ('2024-12-01T12:34:23', '2024-01-01T00:00:00', '2024-12-31T23:59:59.999', DateTimePrecision.Year),
            ('2024-12-13T12:34:23', '2024-12-09T00:00:00.000', '2024-12-15T23:59:59.999', DateTimePrecision.Week),

        ]

        for i, (srcStr, exp0, exp1, prec) in enumerate(examples):
            dtSrc = QDateTime.fromString(srcStr, Qt.ISODate)
            date_range = ImageDateUtils.dateRange(dtSrc, prec)
            self.assertIsInstance(date_range, QgsDateTimeRange)
            self.assertFalse(date_range.isInfinite())
            self.assertTrue(date_range.contains(dtSrc))
            expected_d0 = QDateTime.fromString(exp0, Qt.ISODateWithMs)
            expected_d1 = QDateTime.fromString(exp1, Qt.ISODateWithMs)
            d0, d1 = date_range.begin(), date_range.end()
            self.assertEqual(expected_d0, d0, msg=f'Failed start "{prec}"')
            self.assertEqual(expected_d1, d1, msg=f'Failed end "{prec}"')

    def test_dateRangeString(self):

        dtg = QDateTime.fromString('2024-12-02T12:34:23.999', Qt.ISODateWithMs)
        assert dtg.isValid()

        examples = [
            # date , expected begin / end of date range, precission
            ('2024-049', DateTimePrecision.Week),
            ('2024-12-02T12:34:23.999', DateTimePrecision.Millisecond),
            ('2024-12-02T12:34:23', DateTimePrecision.Second),
            ('2024-12-02T12:34', DateTimePrecision.Minute),
            ('2024-12-02T12', DateTimePrecision.Hour),
            ('2024-12-02', DateTimePrecision.Day),
            ('2024-12', DateTimePrecision.Month),
            ('2024', DateTimePrecision.Year),

        ]

        for (expected, prec) in examples:
            txt = ImageDateUtils.dateString(dtg, prec)
            self.assertEqual(expected, txt)


if __name__ == '__main__':
    unittest.main()
