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
import os

from qgis.core import QgsMapLayer, QgsProject, QgsRasterLayer, QgsRectangle
from qgis.gui import QgsMapCanvas

from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialExtent, SpatialPoint
from eotimeseriesviewer.utils import index_window, layerStyleString, setLayerStyleString
from example.Images import Img_2014_04_21_LC82270652014111LGN00_BOA
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects

start_app()


class TestUtils(EOTSVTestCase):

    def test_index_window(self):
        examples = [
            # n = 3 out of 2 -> return all available indices
            (2, 3, 'center', 1, [0, 1]),
            (2, 3, 'start', 1, [0, 1]),
            (2, 3, 'end', 1, [0, 1]),

            # special case: empty list
            (0, 3, 'center', 1, []),
            (0, 3, 'start', 1, []),
            (0, 3, 'end', 1, []),

            (10, 3, 'start', 9, [7, 8, 9]),
            (10, 3, 'start', 0, [0, 1, 2]),
            (10, 3, 'start', 1, [1, 2, 3]),
            (10, 3, 'start', 8, [7, 8, 9]),

            (10, 3, 'end', 0, [0, 1, 2]),
            (10, 3, 'end', 1, [0, 1, 2]),
            (10, 3, 'end', 2, [0, 1, 2]),
            (10, 3, 'end', 3, [1, 2, 3]),
            (10, 3, 'end', 9, [7, 8, 9]),

            # n_indices, window size, mode, target index, expected indices
            (10, 3, 'center', 0, [0, 1, 2]),
            (10, 3, 'center', 1, [0, 1, 2]),
            (10, 3, 'center', 2, [1, 2, 3]),
            (10, 3, 'center', 9, [7, 8, 9]),
            (10, 3, 'center', 8, [7, 8, 9]),
            (10, 3, 'center', 7, [6, 7, 8]),
            (10, 3, 'center', 9, [7, 8, 9]),
            # even window size? requested item is right-of-center (median)
            (10, 2, 'center', 0, [0, 1]),
            (10, 2, 'center', 1, [0, 1]),
            (10, 2, 'center', 2, [1, 2]),
            (10, 2, 'center', 3, [2, 3]),
            (10, 2, 'center', 8, [7, 8]),
            (10, 2, 'center', 9, [8, 9]),
        ]

        for i, conf in enumerate(examples):
            n, w, mode, t, expected = conf
            window = index_window(t, n, w, mode=mode)
            self.assertEqual(expected, window, msg=f'Failed for example {i + 1}: {conf}')

    def test_spatialExtent(self):
        canvas = QgsMapCanvas()

        lyr = QgsRasterLayer(Img_2014_04_21_LC82270652014111LGN00_BOA)
        QgsProject.instance().addMapLayer(lyr)
        canvas.setLayers([lyr])
        canvas.setExtent(lyr.extent())

        ext = SpatialExtent.fromMapCanvas(canvas)
        self.assertIsInstance(ext, SpatialExtent)
        self.assertIsInstance(ext, QgsRectangle)

        center = SpatialPoint.fromMapCanvasCenter(canvas)
        self.assertIsInstance(center, SpatialPoint)
        self.assertEqual(ext.spatialCenter(), center)
        QgsProject.instance().removeAllMapLayers()

    def test_file_search(self):
        import example

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.123'))
        self.assertTrue(len(files) == 0)

        files = list(file_search(os.path.dirname(example.Images.__file__), '*.tif', recursive=True))
        self.assertTrue(len(files) > 0)

    def test_copy_styles(self):
        lyr1 = TestObjects.createRasterLayer(nb=10)
        lyr1.renderer().setRedBand(1)
        lyr2 = lyr1.clone()
        lyr3 = lyr1.clone()

        lyr2.renderer().setRedBand(4)
        lyr2.setCustomProperty('myProp', 'myVal')

        xml1 = layerStyleString(lyr1, categories=QgsMapLayer.StyleCategory.Rendering)
        xml2 = layerStyleString(lyr2, categories=QgsMapLayer.StyleCategory.Rendering)
        xml3 = layerStyleString(lyr1, categories=QgsMapLayer.StyleCategory.Rendering)
        self.assertNotEqual(xml1, xml2)
        self.assertEqual(xml1, xml3)
        self.assertTrue('redBand="1"' in xml1)
        self.assertTrue('redBand="4"' in xml2)

        self.assertNotEqual(lyr1.renderer().redBand(), lyr2.renderer().redBand())
        setLayerStyleString(lyr2, xml1)
        self.assertEqual(lyr1.renderer().redBand(), lyr2.renderer().redBand())


if __name__ == "__main__":
    unittest.main(buffer=False)
