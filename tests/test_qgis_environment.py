# coding=utf-8

import os
import unittest
from qgis import *
from qgis.core import *
from qgis.gui import *

from eotimeseriesviewer.tests import *
QGIS_APP = initQgisApplication()


class QGISTest(unittest.TestCase):
    """Test the QGIS Environment"""


    def test_mapcanvasbridge(self):

        from eotimeseriesviewer.tests import TestObjects
        layer = TestObjects.createVectorLayer()
        layer2 = TestObjects.createRasterLayer()
        QgsProject.instance().addMapLayers([layer, layer2])
        w = QWidget()
        w.setLayout(QHBoxLayout())

        c = QgsMapCanvas()
        c.setLayers([layer])
        c.setDestinationCrs(layer.crs())
        c.setExtent(c.fullExtent())

        ltree = QgsLayerTree()
        bridge = QgsLayerTreeMapCanvasBridge(ltree, c)
        model = QgsLayerTreeModel(ltree)

        model.setFlags(QgsLayerTreeModel.AllowNodeChangeVisibility |
                       QgsLayerTreeModel.AllowNodeRename |
                       QgsLayerTreeModel.AllowNodeReorder)

        ltree.addLayer(layer)
        ltree.addLayer(layer2)
        grp = ltree.addGroup('Name')
        grp.addLayer(layer)
        grp.addLayer(layer2)
        v = QgsLayerTreeView()
        v.setModel(model)
        w.layout().addWidget(v)
        w.layout().addWidget(c)


        if True:
            w.show()
            QGIS_APP.exec_()

    def test_qgis_environment(self):
        """QGIS environment has the expected providers"""

        r = QgsProviderRegistry.instance()
        self.assertIn('gdal', r.providerList())
        self.assertIn('ogr', r.providerList())
        self.assertIn('postgres', r.providerList())

    def test_projection(self):
        """Test that QGIS properly parses a wkt string.
        """
        crs = QgsCoordinateReferenceSystem()
        wkt = (
            'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
            'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
            'PRIMEM["Greenwich",0.0],UNIT["Degree",'
            '0.0174532925199433]]')
        crs.createFromWkt(wkt)
        auth_id = crs.authid()
        expected_auth_id = 'EPSG:4326'
        self.assertEqual(auth_id, expected_auth_id)


        from example.Images import Img_2014_08_11_LC82270652014223LGN00_BOA
        path = Img_2014_08_11_LC82270652014223LGN00_BOA
        title = 'TestRaster'
        layer = QgsRasterLayer(path, title)
        auth_id = layer.crs().authid()
        self.assertEqual(auth_id, 'EPSG:32621')

if __name__ == '__main__':
    unittest.main()
