# coding=utf-8
"""Safe Translations Test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

from utilities import get_qgis_app
from timeseriesviewer.pixelloader import *
__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
import os, sys, pickle

from timeseriesviewer.utils import initQgisApplication
QGIS_APP = initQgisApplication()


class PixelLoaderTest(unittest.TestCase):
    """Test translations work."""

    @classmethod
    def setUpClass(cls):
        from timeseriesviewer import file_search, DIR_EXAMPLES
        cls.imgs = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        cls.img1 = cls.imgs[0]
        ds = gdal.Open(cls.img1)
        assert isinstance(ds, gdal.Dataset)
        nb, nl, ns = ds.RasterCount, ds.RasterYSize, ds.RasterXSize
        cls.img1Shape = (nb, nl, ns)
        cls.img1gt = ds.GetGeoTransform()
        cls.img1ProfileUL = ds.ReadAsArray(0, 0, 1, 1)
        cls.img1ProfileLR = ds.ReadAsArray(ns - 1, nl - 1, 1, 1)
        ds = None

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        """Runs before each test."""
        pass
    def tearDown(self):
        """Runs after each test."""
        pass


    def test_loadProfiles(self):

        from timeseriesviewer.utils import SpatialPoint, SpatialExtent, px2geo

        from multiprocessing import Queue, Event



        img1 = self.img1
        nb, nl, ns = self.img1Shape
        gt = self.img1gt

        ext = SpatialExtent.fromRasterSource(img1)

        ptUL = SpatialPoint(ext.crs(), *ext.upperLeft())
        ptLR = px2geo(QPoint(ns-1, nl-1), gt)
        ptLR = SpatialPoint(ext.crs(), ptLR)
        ptOutOfImage = SpatialPoint(ext.crs(), px2geo(QPoint(-1,-1), gt))

        resultQueue = Queue(50)
        cancelationEvent = Event()

        #simulate successful loading
        result = loadProfiles([(img1, None)],42,23,ptUL,resultQueue, cancelationEvent)
        self.assertEqual(result, LOADING_FINISHED)
        qresult = resultQueue.get()
        self.assertIsInstance(qresult, PixelLoaderTask)
        self.assertEqual(qresult.sourcePath, img1)
        self.assertIsInstance(qresult.resProfiles, np.ndarray)
        pxIndices = qresult.imagePixelIndices()
        self.assertIsInstance(pxIndices, tuple)
        self.assertIsInstance(pxIndices[0], np.ndarray)
        self.assertEqual(pxIndices[0][0], 0)
        self.assertEqual(pxIndices[1][0], 0)
        self.assertTrue(np.array_equal(qresult.resProfiles, self.img1ProfileUL))

        #test lower-left coordinate
        result = loadProfiles([(img1, None)], 42, 23, ptLR, resultQueue, cancelationEvent)
        self.assertEqual(result, LOADING_FINISHED)
        qresult = resultQueue.get()
        pxIndices = qresult.imagePixelIndices()
        self.assertEqual(pxIndices[0][0], nl-1)
        self.assertEqual(pxIndices[1][0], ns-1)
        self.assertTrue(np.array_equal(qresult.pxData, self.img1ProfileLR))

        #simulate out-of-image loading
        result = loadProfiles([(img1, None)], 42, 23, ptOutOfImage, resultQueue, cancelationEvent)
        self.assertEqual(result, LOADING_FINISHED)
        qresult = resultQueue.get()
        self.assertIsInstance(qresult, PixelLoaderTask)
        self.assertTrue(qresult.resProfiles is None)
        self.assertEqual(result, LOADING_FINISHED)


        #simulate cancellation event
        cancelationEvent.set()
        result = loadProfiles([(img1, None)], 42, 23, ptUL, resultQueue, cancelationEvent)
        self.assertEqual(result, LOADING_CANCELED)


    def test_pixelLoader(self):

        PL = PixelLoader()


if __name__ == "__main__":
    unittest.main()

