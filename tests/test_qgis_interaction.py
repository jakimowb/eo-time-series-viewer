# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

import os
import sys
import configparser
import xmlrunner
from eotimeseriesviewer.tests import start_app, testRasterFiles, EOTSVTestCase
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.core import *
from qgis.gui import *
import unittest
import tempfile

from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.tests import TestObjects



class TestQGISInteraction(EOTSVTestCase):
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """


    def test_syncExtents(self):


        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        TSV.loadExampleTimeSeries()
        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents)
        QgsProject.instance().addMapLayer(lyr)

        from qgis.utils import iface
        self.assertIsInstance(iface, QgisInterface)
        qgisCanvas = iface.mapCanvas()

        world = SpatialExtent.world()
        qgisCanvas.setDestinationCrs(world.crs())
        qgisCanvas.setExtent(world)

        qcenter1 = qgisCanvas.center()
        self.assertTrue(qgisCanvas.mapSettings().destinationCrs().isValid())
        self.assertIsInstance(qgisCanvas, QgsMapCanvas)
        TSV.ui.optionSyncMapCenter.setChecked(True)

        extent = TSV.spatialExtent()
        self.assertIsInstance(extent, SpatialExtent)
        center = extent.spatialCenter()
        self.assertIsInstance(center, SpatialPoint)

        self.showGui(TSV)




if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)

