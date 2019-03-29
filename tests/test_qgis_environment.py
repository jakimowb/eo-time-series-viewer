# coding=utf-8

import os
import unittest
from qgis import *
from qgis.core import *
from qgis.gui import *

from eotimeseriesviewer.tests import *
QGIS_APP = initQgisApplication()


class QGISTest(unittest.TestCase):
    """Test the QGIS Environment"""


    def test_qgis_environment(self):
        """QGIS environment has the expected providers"""

        r = QgsProviderRegistry.instance()
        self.assertIn('gdal', r.providerList())
        self.assertIn('ogr', r.providerList())
        self.assertIn('postgres', r.providerList())

    def test_projection(self):
        """Test that QGIS properly parses a wkt string.
        """
        crs = QgsCoordinateReferenceSystem()
        wkt = (
            'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
            'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
            'PRIMEM["Greenwich",0.0],UNIT["Degree",'
            '0.0174532925199433]]')
        crs.createFromWkt(wkt)
        auth_id = crs.authid()
        expected_auth_id = 'EPSG:4326'
        self.assertEqual(auth_id, expected_auth_id)


        from example.Images import Img_2014_08_11_LC82270652014223LGN00_BOA
        path = Img_2014_08_11_LC82270652014223LGN00_BOA
        title = 'TestRaster'
        layer = QgsRasterLayer(path, title)
        auth_id = layer.crs().authid()
        self.assertEqual(auth_id, 'EPSG:32621')

if __name__ == '__main__':
    unittest.main()
