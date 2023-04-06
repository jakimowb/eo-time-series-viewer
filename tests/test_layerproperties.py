# noinspection PyPep8Naming
import os
import sys
import re

from qgis.core import QgsVectorLayer
from qgis.gui import QgsSublayersDialog

from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import subLayerDefinitions
from eotimeseriesviewer.tests import EOTSVTestCase
import unittest


class TestLayerProperties(EOTSVTestCase):

    def test_selectSubLayers(self):
        from example import exampleGPKG
        vl = QgsVectorLayer(exampleGPKG)

        sublayerDefs = subLayerDefinitions(vl)
        d = QgsSublayersDialog(QgsSublayersDialog.Ogr, "NAME")
        d.populateLayerTable(sublayerDefs)

        self.showGui(d)


if __name__ == "__main__":
    unittest.main(buffer=False)
    exit(0)
