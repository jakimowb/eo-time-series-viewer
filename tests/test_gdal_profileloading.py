import datetime
from unittest import TestCase

from osgeo import ogr, gdal

import example
from scripts.load_eotsv_profiles import main, read_profiles_from_files, points_info, SourceInfoCreator


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

    def test_read_sensorinfo(self):
        creator = SourceInfoCreator

        ds = creator.dataset(example.exampleLandsat8)
        self.assertIsInstance(ds, gdal.Dataset)

        wl, wlu = creator.wavelength_info(ds)

        self.assertIsInstance(wl, list)
        self.assertIsInstance(wlu, str)

        dtg = creator.datetime(ds)

        self.assertIsInstance(dtg, datetime.datetime)

    def test_datetimeFromString(self):
        examples = []

        s = ""
