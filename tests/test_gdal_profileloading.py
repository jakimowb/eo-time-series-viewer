import datetime
import json
from pathlib import Path

from osgeo import ogr, gdal

import example
from eotimeseriesviewer.qgispluginsupport.qps.testing import TestCase
from eotimeseriesviewer.tests import start_app
from scripts.load_eotsv_profiles import main, points_info, SourceInfoProvider, read_profiles

start_app()


class TestGDALProfileLoading(TestCase):

    def test_main(self):
        dir_rasters = example.dir_images
        path_vector = example.examplePoints

        test_outputs = self.createTestOutputDirectory()
        path_vector_out = test_outputs / 'test_vector.gpkg'
        ref = ogr.Open(path_vector)
        lyr = ref.GetLayer(0)

        ds2, tps = main(dir_rasters, path_vector, output_vector=path_vector_out)

        assert isinstance(ds2, gdal.Dataset)
        assert isinstance(tps, dict)

        lyr2 = ds2.GetLayer(0)
        assert isinstance(lyr2, ogr.Layer)
        assert lyr2.GetFeatureCount() == lyr.GetFeatureCount()

        field_names = [f.GetName() for f in lyr2.schema]
        i = field_names.index('profiles')
        for f in lyr2:
            f: ogr.Feature
            fid = f.GetFID()

            dataLyr = f.GetField(i)
            dataTps = tps.get(fid)

            if isinstance(dataLyr, str):
                dataLyr = json.loads(dataLyr)

            assert dataLyr == dataTps

    def test_read_profiles_parallel(self):

        pass

    def test_read_profiles(self):
        files = [example.exampleLandsat8]

        path_vector = example.examplePoints
        ds_vector = ogr.Open(path_vector)
        pts, srs_wkt = points_info(ds_vector.GetLayer())

        results, errors = read_profiles(files, pts, srs_wkt)

        # we need to be able to write the results to JSON
        json.dumps(results, indent=4)

        self.assertIsInstance(results, list)
        for item in results:
            self.assertIsInstance(item, dict)

            ds_raster = gdal.Open(item.get('source'))
            self.assertIsInstance(ds_raster, gdal.Dataset)

            nodata = item.get('nodata')
            self.assertIsInstance(nodata, list)
            self.assertEqual(len(nodata), ds_raster.RasterCount)

            dtg = item.get('dtg')
            self.assertIsInstance(dtg, str)
            self.assertIsInstance(datetime.datetime.fromisoformat(dtg), datetime.datetime)

            sid = item.get('sid')
            self.assertIsInstance(sid, str)
            self.assertIsInstance(json.loads(sid), dict)

            profiles = item.get('profiles')
            self.assertIsInstance(profiles, dict)
            for fid, profile in profiles.items():
                assert fid in pts
                self.assertIsInstance(profile, list)
                self.assertEqual(len(profile), ds_raster.RasterCount)

    def test_read_sensorinfo(self):
        creator = SourceInfoProvider

        ds = creator.dataset(example.exampleLandsat8)
        self.assertIsInstance(ds, gdal.Dataset)

        wl, wlu = creator.wavelengths(ds)

        self.assertIsInstance(wl, list)
        self.assertIsInstance(wlu, str)

        dtg = creator.datetime(ds)

        self.assertIsInstance(dtg, datetime.datetime)

        sid = creator.wavelengths(ds)

        import eotimeseriesviewer.qgispluginsupport.qpstestdata.wavelength
        dir_images = Path(eotimeseriesviewer.qgispluginsupport.qpstestdata.wavelength.__path__[0])

        def test_wl_info(filename: str):
            path = dir_images / filename
            self.assertTrue(path.is_file(), msg=f'File not found: {path}')
            ds = creator.dataset(path)
            self.assertIsInstance(ds, gdal.Dataset, msg=f'Failed to load {path}')

            wl, wlu = creator.wavelengths(ds)
            self.assertIsInstance(wl, list)
            self.assertEqual(len(wl), ds.RasterCount)
            self.assertIsInstance(wlu, str)

        test_wl_info('envi_wl_implicit_nm.bsq')
        test_wl_info('envi_wl_fwhm.bsq')
        test_wl_info('gdal_wl_fwhm.tif')
        test_wl_info('gdal_wl_only.tif')
