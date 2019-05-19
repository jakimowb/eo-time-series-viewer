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

import os, sys, configparser

from eotimeseriesviewer.tests import initQgisApplication, testRasterFiles
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.core import *
from qgis.gui import *
from qgis.testing import TestCase
import unittest, tempfile

import eotimeseriesviewer
eotimeseriesviewer.initResources()
from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.tests import TestObjects

QGIS_APP = initQgisApplication()
SHOW_GUI = True and os.environ.get('CI') is None



class TestInit(TestCase):
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """


    def test_syncExtents(self):


        from eotimeseriesviewer.main import TimeSeriesViewer

        TSV = TimeSeriesViewer()
        TSV.show()
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

        extent = TSV.spatialTemporalVis.spatialExtent()
        self.assertIsInstance(extent, SpatialExtent)
        center = extent.spatialCenter()
        self.assertIsInstance(center, SpatialPoint)
        center2 = SpatialPoint(center.crs(), center.x() + 100, center.y() + 100)
        TSV.spatialTemporalVis.mSyncLock = False
        TSV.setSpatialCenter(center2)
        self.assertEqual(TSV.spatialCenter(), center2)

        qcenter2 = qgisCanvas.center()
        self.assertNotEqual(qcenter1, qcenter2)
        TSV.ui.optionSyncMapCenter.setChecked(False)
        TSV.spatialTemporalVis.mSyncLock = False
        TSV.setSpatialCenter(center)
        self.assertNotEqual(qcenter2, qgisCanvas.center())




        if SHOW_GUI:
            QGIS_APP.exec_()


if __name__ == '__main__':
    unittest.main()

