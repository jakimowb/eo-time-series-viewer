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

import unittest


from qgis.core import QgsProject, QgsRectangle, QgsRasterLayer
from qgis.gui import QgsMapCanvas
from example.Images import Img_2014_04_21_LC82270652014111LGN00_BOA
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.tests import EOTSVTestCase


class TestUtils(EOTSVTestCase):

    def test_spatialExtent(self):
        canvas = QgsMapCanvas()

        l = QgsRasterLayer(Img_2014_04_21_LC82270652014111LGN00_BOA)
        QgsProject.instance().addMapLayer(l)
        canvas.setLayers([l])
        canvas.setExtent(l.extent())

        ext = SpatialExtent.fromMapCanvas(canvas)
        self.assertIsInstance(ext, SpatialExtent)
        self.assertIsInstance(ext, QgsRectangle)

        center = SpatialPoint.fromMapCanvasCenter(canvas)
        self.assertIsInstance(center, SpatialPoint)
        self.assertEqual(ext.spatialCenter(), center)

    def test_file_search(self):
        import example

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.123'))
        self.assertTrue(len(files) == 0)

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif', recursive=True))
        self.assertTrue(len(files) > 0)


if __name__ == "__main__":
    unittest.main(buffer=False)
    exit(0)
