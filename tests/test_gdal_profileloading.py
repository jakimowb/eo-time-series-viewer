import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Union

from osgeo import ogr, gdal

import example
from eotimeseriesviewer import initAll, DIR_REPO
from eotimeseriesviewer.qgispluginsupport.qps.testing import TestCase
from eotimeseriesviewer.tests import start_app
from scripts.load_eotsv_profiles import create_profile_layer, points_info, SourceInfoProvider, read_profiles

start_app()
initAll()


class TestGDALProfileLoading(TestCase):

    def assertIsProfileDictionary(self, data):
        self.assertIsInstance(data, dict)
        n = None

        values = data.get('values')
        sensor_ids = data.get('sensor_ids')
        sensor = data.get('sensor')
        date = data.get('date')
        self.assertIsInstance(values, list)
        self.assertIsInstance(sensor_ids, list)
        self.assertIsInstance(sensor, list)
        self.assertIsInstance(date, list)
        n = len(values)
        self.assertTrue(n > 0, msg='expected at least one profile')
        self.assertEqual(len(sensor), n, msg=f'expected {n} sensor ids, got {len(sensor)}')
        self.assertEqual(len(date), n, msg=f'expected {n} dates, got {len(date)}')

        sensor_ids = [json.loads(s) if isinstance(s, str) else s for s in sensor_ids]
        for s in sensor_ids:
            self.assertIsInstance(s, dict)

        for i, profile in enumerate(values):
            sid = sensor_ids[sensor[i]]
            self.assertEqual(len(profile), sid['nb'], msg=f'expected {sid["nb"]} bands, got {len(profile)}')
            d = date[i]
            d_iso = datetime.datetime.fromisoformat(d)

    def assertIsProfileLayer(self, source,
                             field: str = 'profiles',
                             layer: Union[str, int] = 0):
        if isinstance(source, (str, Path)):
            source: ogr.DataSource = ogr.Open(str(source))
            self.assertIsInstance(source, ogr.DataSource)

            if isinstance(layer, int):
                lyr = source.GetLayer(layer)
            elif isinstance(layer, str):
                lyr = source.GetLayerByName(layer)
            else:
                lyr = None
            self.assertIsInstance(lyr, ogr.Layer)
            self.assertTrue(lyr.GetFeatureCount() > 0)
            for f in lyr:
                self.assertIsInstance(f, ogr.Feature)
                dump = f.GetFieldAsString(field)
                if dump != '':
                    d = json.loads(dump)
                    self.assertIsProfileDictionary(d)

    def test_create_profile_layer(self):
        dir_rasters = example.dir_images
        path_vector = example.examplePoints

        test_outputs = self.createTestOutputDirectory()
        path_vector_out = test_outputs / 'test_vector.geojson'
        ref = ogr.Open(path_vector)
        lyr = ref.GetLayer(0)

        output_field = 'my_profiles42'
        ds2, tps = create_profile_layer(dir_rasters, path_vector,
                                        output_vector=path_vector_out,
                                        output_field=output_field)

        assert isinstance(ds2, gdal.Dataset)
        del ds2
        assert isinstance(tps, dict)

        ds2 = ogr.Open(str(path_vector_out))

        lyr2 = ds2.GetLayer(0)
        assert isinstance(lyr2, ogr.Layer)
        # assert lyr2.GetFeatureCount() == lyr.GetFeatureCount()

        field_names = [f.GetName() for f in lyr2.schema]
        i = field_names.index(output_field)
        n2 = 0
        for f in lyr2:
            f: ogr.Feature
            fid = f.GetFID()

            dataLyr = f.GetField(i)
            dataTps = tps.get(fid)

            if isinstance(dataLyr, str):
                dataLyr = json.loads(dataLyr)

            assert dataLyr == dataTps
            n2 += 1
        self.assertEqual(n2, lyr.GetFeatureCount())
        self.assertIsProfileLayer(path_vector_out, field='my_profiles42')

        # TSV = EOTimeSeriesViewer()
        # TSV.loadExampleTimeSeries(loadAsync=False)
        # TSV.addVectorData(path_vector_out)
        # self.showGui(TSV.ui)
        # TSV.close()

    def test_read_profiles_parallel(self):

        dir_rasters = example.dir_images
        path_vector = example.examplePoints

        test_outputs = self.createTestOutputDirectory()
        path_vector_out = test_outputs / 'test_vector_parallel.geojson'
        ref = ogr.Open(path_vector)
        lyr = ref.GetLayer(0)

        ds_out, profiles = create_profile_layer(
            rasters=str(dir_rasters),
            vector=str(path_vector),
            pattern='rx:.*\\.tif$',
            n_jobs=3,
            output_vector=str(path_vector_out),
            output_field='my_profiles12'
        )

        self.assertIsProfileLayer(path_vector_out, 'my_profiles12')

        if not TestCase.runsInCI():
            from eotimeseriesviewer.main import EOTimeSeriesViewer
            TSV = EOTimeSeriesViewer()
            TSV.loadExampleTimeSeries(loadAsync=False)
            TSV.addVectorData(path_vector_out)
            self.showGui(TSV.ui)
            TSV.close()

        s = ""
        pass

    def test_read_profiles(self):
        files = [example.exampleLandsat8]

        path_vector = example.examplePoints
        ds_vector = ogr.Open(path_vector)
        pts, srs_wkt = points_info(ds_vector.GetLayer())

        results, errors = read_profiles(files, pts, srs_wkt)

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

        # we need to be able to write the results to JSON
        path_json = self.createTestOutputDirectory() / 'test_profiles.json'
        with open(path_json, 'w') as f:
            json.dump(results, f, indent=4)

    def test_read_cli(self):

        dir_rasters = example.dir_images
        path_vector = example.examplePoints

        test_outputs = self.createTestOutputDirectory()
        path_vector_out = test_outputs / 'test_vector_parallel.geojson'

        cli_args = [f'-v {path_vector}',
                    f'-r {dir_rasters}',
                    f'--pattern *.tif',
                    f'--n_jobs 3',
                    f'--output_vector {path_vector_out}', ]

        script_path = DIR_REPO / 'scripts' / 'load_eotsv_profiles.py'
        cmd = [sys.executable, str(script_path), *cli_args]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # For debugging on failure
        err = f'{result.stderr}'
        if result.returncode != 0:
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", err)

        assert result.returncode == 0, err

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
