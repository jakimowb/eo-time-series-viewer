# coding=utf-8
"""Tests QGIS plugin init."""

import os
import unittest
import example
import example.Images
from osgeo import gdal
from timeseriesviewer.utils import file_search
from timeseriesviewer.timeseries import TimeSeries, SensorInstrument, TimeSeriesDatum

class TestInit(unittest.TestCase):

    def test_timeseriesdatum(self):

        file = example.Images.Img_2014_03_20_LC82270652014079LGN00_BOA

        tsd = TimeSeriesDatum.createFromPath(file)
        self.assertIsInstance(tsd, TimeSeriesDatum)
        self.assertEqual(tsd.nb, 6)

    def test_timeseries(self):

        files = file_search(os.path.dirname(example.__file__), '*.tif', recursive=True)

        addedDates = []

        TS = TimeSeries()
        TS.sigTimeSeriesDatesAdded.connect(lambda dates: addedDates.extend(dates))
        TS.sigTimeSeriesDatesRemoved.connect(lambda dates: [addedDates.remove(d) for d in dates])

        for file in files:
            TS.addFiles([file])

        self.assertEqual(len(files), len(TS))
        TS.removeDates(addedDates)
        self.assertEquals(len(addedDates), 0)

    def test_sensors(self):
        pathRE = file_search(os.path.dirname(example.__file__), 're*.tiff', recursive=True)[0]
        pathLS = file_search(os.path.dirname(example.__file__), '*BOA.tiff', recursive=True)[0]

        TS = TimeSeries()
        TS.addFiles(pathRE)
        TS.addFiles(pathLS)
        self.assertEqual(len(TS.Sensors), 2)

        dsRE = gdal.Open(pathRE)
        assert isinstance(dsRE, gdal.Dataset)

        tsdRE = TS.tsdFromPath(pathRE)
        self.assertIsInstance(tsdRE, TimeSeriesDatum)
        sRE = tsdRE.sensor
        self.assertIsInstance(sRE, SensorInstrument)
        self.assertEqual(dsRE.RasterCount, sRE.nb)

    def test_datematching(self):
        pass



if __name__ == '__main__':
    unittest.main()
