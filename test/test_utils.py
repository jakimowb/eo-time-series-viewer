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
from qgis import *
from PyQt5.QtGui import QIcon
from timeseriesviewer import file_search
from timeseriesviewer.utils import *
QGIS_APP = initQgisApplication()

class testclassUtilityTests(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass



    def test_spatialObjects(self):
        """Test we can click OK."""
        import example
        pathRE = file_search(os.path.dirname(example.__file__), 're*', recursive=True)[0]

        from example.inmemorydatasets import createInMemoryRaster
        dsMEM = createInMemoryRaster()
        se = SpatialExtent.fromRasterSource(dsMEM)
        self.assertIsInstance(se, SpatialExtent)

        pt1 = SpatialPoint.fromSpatialExtent(se)
        self.assertIsInstance(pt1, SpatialPoint)


        d = {}
        for t in [pt1, se]:
            try:
                d[t] = '{}'.format(t)
            except:
                self.fail('Unable to use {} as dictionary key.'.format(type(t)))


if __name__ == "__main__":
    unittest.main()



