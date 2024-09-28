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

        s = ""


if __name__ == '__main__':
    unittest.main()
