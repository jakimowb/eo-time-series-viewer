# coding=utf-8
"""Safe Translations Test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""


from timeseriesviewer.pixelloader import *
__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
import os, sys, pickle

from timeseriesviewer.utils import initQgisApplication
import example.Images
from timeseriesviewer.utils import file_search

QGIS_APP = initQgisApplication()


def onDummy(*args):
    print(('dummy', args))


class PixelLoaderTest(unittest.TestCase):
    """Test translations work."""

    @classmethod
    def setUpClass(cls):
        from timeseriesviewer import DIR_EXAMPLES
        from timeseriesviewer.utils import file_search
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




    def test_pixelLoader(self):
        from timeseriesviewer.pixelloader import doLoaderTask, PixelLoaderTask, INFO_OUT_OF_IMAGE, INFO_NO_DATA
        from timeseriesviewer.utils import px2geo
        source = example.Images.Img_2014_05_15_LE72270652014135CUB00_BOA

        ext = SpatialExtent.fromRasterSource(source)
        ds = gdal.Open(source)

        gt = ds.GetGeoTransform()
        wkt = ds.GetProjection()
        ds = None
        ptNoData = px2geo(QgsPointXY(66,2), gt)

        pt = SpatialPoint.fromSpatialExtent(ext)
        x,y = pt.x(), pt.y()
        ptOutOfImage = SpatialExtent(ext.crs(), x + 10000, y, x + 12000, y + 70)  # out of image
        ptNoData     = SpatialPoint(ext.crs(), ptNoData)
        ptValid1      = SpatialPoint(ext.crs(), x, y)
        ptValid2 = SpatialPoint(ext.crs(), x+50, y+50)

        #test a valid pixels

        try:
            result = doLoaderTask(PixelLoaderTask(source, [ptValid1, ptValid2]))
        except Exception as ex:
            self.fail('Failed to return the pixels for two geometries')

        self.assertIsInstance(result, PixelLoaderTask)
        self.assertTrue(result.success())
        self.assertEqual(result.sourcePath, source)
        self.assertSequenceEqual(result.bandIndices, [0,1,2,3,4,5])
        self.assertIs(result.exception, None)



        self.assertEqual(result.resCrsWkt, wkt)
        self.assertEqual(result.resGeoTransformation, gt)
        self.assertEqual(result.resNoDataValues, None)
        self.assertIsInstance(result.resProfiles, list)
        self.assertEqual(len(result.resProfiles), 2, msg='did not return results for two geometries.')

        for i in range(len(result.resProfiles)):
            dn, stdDev = result.resProfiles[i]
            self.assertIsInstance(dn, np.ndarray)
            self.assertIsInstance(stdDev, np.ndarray)

            self.assertEqual(len(dn), len(stdDev))
            self.assertEqual(len(dn), 6)
            self.assertEqual(stdDev.max(), 0) #std deviation of a single pixel is always zero
            self.assertEqual(stdDev.min(), 0)



        #test a out-of-image geometry
        result = doLoaderTask(PixelLoaderTask(source, ptOutOfImage))
        self.assertTrue(result.success())
        self.assertEqual(result.resProfiles[0], INFO_OUT_OF_IMAGE)

        result = doLoaderTask(PixelLoaderTask(source, ptNoData))
        self.assertTrue(result.success())
        self.assertEqual(result.resProfiles[0], INFO_NO_DATA)

    def test_loadProfiles(self):

        from timeseriesviewer.utils import SpatialPoint, SpatialExtent, px2geo



        img1 = self.img1
        nb, nl, ns = self.img1Shape
        gt = self.img1gt

        ext = SpatialExtent.fromRasterSource(img1)

        ptUL = SpatialPoint(ext.crs(), *ext.upperLeft())
        ptLR = px2geo(QPoint(ns-1, nl-1), gt)
        ptLR = SpatialPoint(ext.crs(), ptLR)
        ptOutOfImage = SpatialPoint(ext.crs(), px2geo(QPoint(-1,-1), gt))

        dir = os.path.dirname(example.Images.__file__)
        # files = file_search(dir, '*.tif')
        files = [example.Images.Img_2014_05_07_LC82270652014127LGN00_BOA]
        files.append(example.Images.Img_2014_04_29_LE72270652014119CUB00_BOA)
        files.extend(file_search(dir, 're_*.tif'))
        for f in files: print(f)
        ext = SpatialExtent.fromRasterSource(files[0])
        x, y = ext.center()

        geoms1 = [
            # SpatialPoint(ext.crs(), 681151.214,-752388.476), #nodata in Img_2014_04_29_LE72270652014119CUB00_BOA
            SpatialExtent(ext.crs(), x + 10000, y, x + 12000, y + 70),  # out of image
            SpatialExtent(ext.crs(), x, y, x + 10000, y + 70),
            ]

        geoms2 = [SpatialPoint(ext.crs(), x, y),
                  SpatialPoint(ext.crs(), x + 250, y + 70)]

        from multiprocessing import Pool

        def onPxLoaded(*args):
            n, nmax, task = args
            assert isinstance(task, PixelLoaderTask)
            print(task)

        PL = PixelLoader()


        def onTimer(*args):
            print(('TIMER', PL))
            pass

        PL.sigPixelLoaded.connect(onPxLoaded)
        PL.sigLoadingFinished.connect(lambda: onDummy('finished'))
        PL.sigLoadingCanceled.connect(lambda: onDummy('canceled'))
        PL.sigLoadingStarted.connect(lambda: onDummy('started'))
        PL.sigPixelLoaded.connect(lambda: onDummy('px loaded'))

        tasks1 = []
        for i, f in enumerate(files):
            kwargs = {'myid': 'myID{}'.format(i)}
            tasks1.append(PixelLoaderTask(f, geoms1, bandIndices=None, **kwargs))

        tasks2 = []
        for i, f in enumerate(files):
            kwargs = {'myid': 'myID{}'.format(i)}
            tasks2.append(PixelLoaderTask(f, geoms2, bandIndices=None, **kwargs))

        for t in tasks1:
            result = doLoaderTask(t)
            s = ""

        PL.startLoading(tasks1)
        PL.startLoading(tasks2)

        print('DONE')




if __name__ == "__main__":
    unittest.main()

