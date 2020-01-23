# noinspection PyPep8Naming
import os, sys, re
from qgis.core import *
from qgis.gui import *
from eotimeseriesviewer.tests import TestCase
import unittest
os.environ['CI'] = 'True'



class TestLayerproperties(TestCase):


    def test_selectSubLayers(self):

        from example import exampleGPKG
        vl = QgsVectorLayer(exampleGPKG)
        from eotimeseriesviewer.externals.qps.layerproperties import subLayerDefinitions


        sublayerDefs = subLayerDefinitions(vl)
        d = QgsSublayersDialog(QgsSublayersDialog.Ogr, "NAME")
        d.populateLayerTable(sublayerDefs)

        self.showGui(d)

if __name__ == "__main__":

    unittest.main()

