import unittest

from PyQt5.QtCore import QTime
from qgis._core import QgsDateTimeRange

from qgis.PyQt.QtCore import QDate, QDateTime, Qt
from qgis.core import QgsRasterLayer
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from example import exampleLandsat8, exampleNoDataImage, exampleRapidEye

start_app()


class TestDateParser(EOTSVTestCase):

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
        lyr = QgsRasterLayer(exampleNoDataImage.as_posix())
        dtg = ImageDateUtils.dateTimeFromLayer(lyr)
        self.assertIsInstance(dtg, QDateTime)

        dtg = ImageDateUtils.dateTimeFromLayer(exampleRapidEye)
        # 2014-06-25
        self.assertIsInstance(dtg, QDateTime)
        self.assertTrue(dtg.isValid())
        self.assertEqual(dtg, QDateTime.fromString('2014-06-25', Qt.ISODate))

        dtg = ImageDateUtils.dateTimeFromLayer(exampleLandsat8)
        # 2014-01-15
        self.assertEqual(dtg, QDateTime(QDate(2014, 1, 15), QTime()))

        pathTmp = '/vsimem/nothing.tif'
        ds = TestObjects.createRasterDataset(path=pathTmp, drv='GTiff')
        rl = QgsRasterLayer(pathTmp)
        self.assertTrue(rl.isValid())
        self.assertTrue(ImageDateUtils.dateTimeFromLayer(pathTmp) is None)

        dt1 = QDateTime(QDate(2022, 1, 1), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt1), 1)

        dt2 = QDateTime(QDate(2023, 12, 31), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 365)

        dt2 = QDateTime(QDate(2024, 12, 31), QTime())
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 366)
        s = ""

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