# coding=utf-8
"""Tests QGIS plugin init."""

import os
import unittest
import example
import example.Images
from osgeo import gdal, ogr, osr
from timeseriesviewer.utils import file_search
from timeseriesviewer.timeseries import *

class TestInit(unittest.TestCase):


    def createTestDatasets(self):

        vsiDir = '/vsimem/tmp'
        from timeseriesviewer.temporalprofiles2d import date2num
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

    def test_timeseriesdatum(self):

        file = example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA

        tsd = TimeSeriesDatum.createFromPath(file)
        self.assertIsInstance(tsd, TimeSeriesDatum)
        self.assertEqual(tsd.nb, 6)



    def test_timeseries(self):

        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))

        addedDates = []

        TS = TimeSeries()
        TS.sigTimeSeriesDatesAdded.connect(lambda dates: addedDates.extend(dates))
        TS.sigTimeSeriesDatesRemoved.connect(lambda dates: [addedDates.remove(d) for d in dates])

        for file in files:
            TS.addFiles([file])

        self.assertEqual(len(files), len(TS))
        TS.removeDates(addedDates)
        self.assertEqual(len(addedDates), 0)

    def test_sensors(self):
        pathRE = list(file_search(os.path.dirname(example.__file__), 're*.tif', recursive=True))[0]
        pathLS = list(file_search(os.path.dirname(example.__file__), '*BOA.tif', recursive=True))[0]

        TS = TimeSeries()
        TS.addFiles(pathRE)
        TS.addFiles(pathLS)
        self.assertEqual(len(TS.Sensors), 2)

        dsRE = gdal.Open(pathRE)
        assert isinstance(dsRE, gdal.Dataset)

        tsdRE = TS.getTSD(pathRE)
        self.assertIsInstance(tsdRE, TimeSeriesDatum)
        sRE = tsdRE.sensor
        self.assertIsInstance(sRE, SensorInstrument)
        self.assertEqual(dsRE.RasterCount, sRE.nb)

    def test_datematching(self):
        pass



if __name__ == '__main__':
    unittest.main()
