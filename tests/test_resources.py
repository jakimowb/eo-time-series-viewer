# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import os
import pathlib
import re
import unittest

from osgeo import gdal
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsRasterLayer, QgsVectorLayer

from eotimeseriesviewer import DIR_UI, icon as eotsvIcon
from eotimeseriesviewer.qgispluginsupport.qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from eotimeseriesviewer.qgispluginsupport.qps.speclib.core.spectralprofile import validateProfileValueDict
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, scanResources
from eotimeseriesviewer.tests import EOTSVTestCase, example_raster_files, start_app

start_app()


class TestResources(EOTSVTestCase):

    def test_icon(self):
        existing = list(scanResources())
        self.assertFalse(eotsvIcon().isNull())
        iconSVGs = file_search(os.path.join(DIR_UI, 'icons'), '*.svg')
        iconSVGs = [pathlib.Path(s).as_posix() for s in iconSVGs]
        iconSVGs = sorted([re.sub(r'^.*/eotimeseriesviewer/ui/icons/', ':/eotimeseriesviewer/icons/', s)
                           for s in iconSVGs])

        unusedSVGs = []
        for resource in iconSVGs:
            if resource not in existing:
                unusedSVGs.append(resource)
            else:
                icon = QIcon(resource)
                self.assertFalse(icon.isNull(), msg=f'unable to load icon {resource}')

        self.assertTrue(len(unusedSVGs) == 0, msg='Unused resources:\n{}'.format('\n'.join(sorted(unusedSVGs))))

    def test_example_images(self):

        for file in example_raster_files(pattern=re.compile(r'.*\.tif$')):
            ds: gdal.Dataset = gdal.Open(file)
            self.assertIsInstance(ds, gdal.Dataset)

            lyr = QgsRasterLayer(file)
            self.assertTrue(lyr.isValid())
            pDict = SpectralLibraryUtils.readProfileDict(lyr, lyr.extent().center())
            self.assertTrue(validateProfileValueDict(pDict))

    def test_example_vectors(self):

        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents)

        s = ""


if __name__ == "__main__":
    unittest.main(buffer=False)
