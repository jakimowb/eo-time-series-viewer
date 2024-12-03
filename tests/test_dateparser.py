import datetime
import unittest

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from example import exampleLandsat8, exampleNoDataImage, exampleRapidEye
from qgis.core import QgsRasterLayer

start_app()


class TestDateParser(EOTSVTestCase):

    def test_date_extraction(self):
        lyr = QgsRasterLayer(exampleNoDataImage.as_posix())
        dtg = ImageDateUtils.datetimeFromLayer(lyr)
        self.assertIsInstance(dtg, datetime.datetime)

        dtg = ImageDateUtils.datetimeFromLayer(exampleRapidEye)
        # 2014-06-25
        self.assertEqual(dtg, datetime.datetime(2014, 6, 25))
        self.assertIsInstance(dtg, datetime.datetime)

        dtg = ImageDateUtils.datetimeFromLayer(exampleLandsat8)
        # 2014-01-15
        self.assertEqual(dtg, datetime.datetime(2014, 1, 15))

        pathTmp = '/vsimem/nothing.tif'
        ds = TestObjects.createRasterDataset(path=pathTmp, drv='GTiff')
        rl = QgsRasterLayer(pathTmp)
        self.assertTrue(rl.isValid())
        self.assertTrue(ImageDateUtils.datetimeFromLayer(pathTmp) is None)

        dt1 = datetime.datetime(2022, 1, 1)
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt1), 1)

        dt2 = datetime.datetime(2023, 12, 31)
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 365)

        dt2 = datetime.datetime(2024, 12, 31)
        self.assertTrue(ImageDateUtils.doiFromDateTime(dt2), 366)
        s = ""

    def test_date_precission(self):
        s = ""
        examples = [
            datetime.datetime(2024, 12, day=1),
            datetime.datetime(2024, 12, 31),
            datetime.datetime(2024, 12, 31, minute=24),
            datetime.datetime(2024, 12, 31, minute=24, second=12),
            datetime.datetime(2024, 12, 31, minute=24, second=12, microsecond=34),

        ]
        for i, dt in enumerate(examples):
            txt_iso = dt.isoformat()
            dt2 = datetime.datetime.fromisoformat(txt_iso)
            assert dt == dt2
            dt3 = ImageDateUtils.datetimeFromString(txt_iso)
            if dt != dt3:
                s = ""
            self.assertEqual(dt3, dt,
                             msg=f'Unable to reconstruct example {i + 1}:\nExpected {dt} from {txt_iso}, got {dt2}')


if __name__ == '__main__':
    unittest.main()
