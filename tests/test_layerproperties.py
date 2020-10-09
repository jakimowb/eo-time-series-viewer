# noinspection PyPep8Naming
import os
import sys
import re
import xmlrunner
from qgis.core import QgsVectorLayer
from qgis.gui import QgsSublayersDialog
from eotimeseriesviewer.tests import EOTSVTestCase
import unittest


class TestLayerProperties(EOTSVTestCase):

    def test_selectSubLayers(self):
        from example import exampleGPKG
        vl = QgsVectorLayer(exampleGPKG)
        from eotimeseriesviewer.externals.qps.layerproperties import subLayerDefinitions

        sublayerDefs = subLayerDefinitions(vl)
        d = QgsSublayersDialog(QgsSublayersDialog.Ogr, "NAME")
        d.populateLayerTable(sublayerDefs)

        self.showGui(d)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
