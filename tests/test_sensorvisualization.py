# coding=utf-8
"""Tests QGIS plugin init."""

import os
import unittest
import example
import example.Images
from osgeo import gdal, ogr, osr
from eotimeseriesviewer.utils import file_search
from eotimeseriesviewer.tests import TestObjects
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer.tests import initQgisApplication
from eotimeseriesviewer.sensorvisualization import *
app = initQgisApplication()

class TestInit(unittest.TestCase):


    def createTestDatasets(self):

        vsiDir = '/vsimem/tmp'
        from eotimeseriesviewer.temporalprofiles import date2num
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

    def createTimeSeries(self)->TimeSeries:

        pathes = [example.Images.Img_2014_01_15_LC82270652014015LGN00_BOA,
                  example.Images.Img_2014_04_29_LE72270652014119CUB00_BOA,
                  example.Images.re_2014_06_25
                ]

        TS = TimeSeries()
        model = SensorListModel(TS)
        self.assertTrue(model.rowCount() == 0)

        TS.addSources(pathes, runAsync=False)
        self.assertTrue(len(TS) == len(pathes))

        self.assertTrue(model.rowCount() == 2)




if __name__ == '__main__':
    unittest.main()
