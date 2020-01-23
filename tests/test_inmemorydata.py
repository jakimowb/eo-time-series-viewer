# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

import os, sys, unittest, configparser

from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile
from eotimeseriesviewer.tests import TestCase

class TestInMemoryData(TestCase):
    """
    Tests for the GDAL/OGR VSI in-memory data
    """

    def test_vsimem_raster(self):

        from osgeo import gdal
        from eotimeseriesviewer.tests import TestObjects
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer
        TestObjects.inMemoryImage()
        # create an in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        self.assertIsInstance(driver, gdal.Driver)
        path = '/vsimem/inmemoryraster.tif'
        dataSet = driver.Create(path, 100, 50, bands=3, eType=gdal.GDT_Int16)
        self.assertIsInstance(dataSet, gdal.Dataset)
        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, \
                                 0, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        self.assertIsInstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        self.assertIsInstance(layer, QgsRasterLayer)
        self.assertTrue(layer.isValid())



    def test_vsimem_raster2(self):

        from osgeo import gdal
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

        # create an in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        assert isinstance(driver, gdal.Driver)
        path = '/vsimem/inmemoryraster.tif'

        dataSet = driver.Create(path, 100, 50, bands=3, eType=gdal.GDT_Int16)
        assert isinstance(dataSet, gdal.Dataset)
        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        assert isinstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        self.assertIsInstance(layer, QgsRasterLayer)
        self.assertTrue(layer.isValid())


if __name__ == '__main__':
    unittest.main()


