from unittest import TestCase

from osgeo import ogr

import example
from scripts.load_eotsv_profiles import main, read_profiles_from_files, points_info


class TestGDALProfileLoading(TestCase):

    def test_load_profiles(self):
        dir_rasters = example.dir_images
        path_vector = example.examplePoints

        ref = ogr.Open(path_vector)
        lyr = ref.GetLayer(0)

        ds2 = main(dir_rasters, path_vector)
        assert isinstance(ds2, ogr.DataSource)
        lyr2 = ds2.GetLayer(0)
        assert isinstance(lyr2, ogr.Layer)
        assert lyr2.GetFeatureCount() == lyr.GetFeatureCount()

    def test_read_profiles_from_files(self):
        files = [example.exampleLandsat8]

        path_vector = example.examplePoints
        ds = ogr.Open(path_vector)
        pts, srs_wkt = points_info(ds.GetLayer())

        results = read_profiles_from_files(files, pts, srs_wkt)

        self.assertIsInstance(results, dict)
