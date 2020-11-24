
import unittest
import re
import xmlrunner
import datetime
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import numpy as np
from qgis.core import QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsProject, \
QgsFields
from qgis.gui import QgsDualView, QgsEditorConfigWidget, QgsMapLayerStyleManagerWidget, \
QgsMapCanvas, QgsGui, QgsEditorWidgetRegistry, QgsEditorWidgetWrapper

from eotimeseriesviewer.docks import LabelDockWidget, SpectralLibraryDockWidget
from eotimeseriesviewer.labeling import LabelWidget, LabelConfigurationKey, LabelAttributeTableModel, shortcuts, \
LabelShortcutEditorConfigWidget, quickLayerFieldSetup, quickLabelLayers, EDITOR_WIDGET_REGISTRY_KEY, \
LabelShortcutType, LabelConfigurationKey, registerLabelShortcutEditorWidget, Option, OptionListModel, \
LabelShortcutEditorWidgetWrapper, LabelShortcutWidgetFactory, createWidgetSetup, createWidgetConf, quickLabelValue
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapView
from eotimeseriesviewer.tests import TestObjects, EOTSVTestCase
from eotimeseriesviewer.externals.qps.utils import createQgsField
from eotimeseriesviewer.timeseries import TimeSeriesDate, TimeSeriesSource

import eotimeseriesviewer
EE_Available = False
try:
    import ee
    EE_Available = True
except ModuleNotFoundError:
    EE_Available = False
from eotimeseriesviewer.tests import TestObjects, EOTSVTestCase

@unittest.skipIf(EE_Available == False, 'GEE not available')
class TestLabeling(EOTSVTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ee.Initialize()
        import provider
        provider.register_data_provider()


    def test_access(self):
        s = ""
        l8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA')
        s = ""
        s = ""


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
