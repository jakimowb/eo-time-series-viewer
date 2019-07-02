# noinspection PyPep8Naming
import os, sys, re
from qgis.core import *
from qgis.gui import *
from eotimeseriesviewer.tests import initQgisApplication, testRasterFiles, TestObjects
import unittest, tempfile

from eotimeseriesviewer import DIR_REPO

resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True and os.environ.get('CI') is None


QgsGui.editorWidgetRegistry().initEditors()


class TestLayerproperties(unittest.TestCase):


    def test_selectSubLayers(self):

        from example import exampleGPKG
        vl = QgsVectorLayer(exampleGPKG)
        from eotimeseriesviewer.externals.qps.layerproperties import subLayerDefinitions


        sublayerDefs = subLayerDefinitions(vl)
        d = QgsSublayersDialog(QgsSublayersDialog.Ogr, "NAME")
        d.populateLayerTable(sublayerDefs)

        d.show()

        if SHOW_GUI:
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()

QGIS_APP.quit()
