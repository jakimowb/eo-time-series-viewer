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
from qgis.core import QgsMapLayer, QgsVectorLayer, QgsRasterLayer, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsMapToPixel, QgsProject
from qgis.gui import QgsMapCanvas, QgisInterface
import unittest
import tempfile

from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.tests import TestObjects
from eotimeseriesviewer.main import EOTimeSeriesViewer


class TestQGISInteraction(EOTSVTestCase):
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """

    def setUp(self):

        eotsv = EOTimeSeriesViewer.instance()
        if isinstance(eotsv, EOTimeSeriesViewer):
            eotsv.close()
            QApplication.processEvents()

    def test_syncExtents(self):

        TSV = EOTimeSeriesViewer()
        TSV.loadExampleTimeSeries(loadAsync=False)
        QApplication.processEvents()

        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents)
        QgsProject.instance().addMapLayer(lyr)

        from qgis.utils import iface
        self.assertIsInstance(iface, QgisInterface)
        qgisCanvas = iface.mapCanvas()

        world = SpatialExtent.world()
        qgisCanvas.setDestinationCrs(world.crs())
        qgisCanvas.setExtent(world)


        def moveCanvasToCorner(canvas: QgsMapCanvas, pos:str) -> SpatialPoint:
            pos = pos.upper()
            assert pos in ['UL', 'LR', 'UR', 'LL']
            assert isinstance(canvas, QgsMapCanvas)
            m2p: QgsMapToPixel = canvas.mapSettings().mapToPixel()
            tol = m2p.toMapCoordinates(0,0) - m2p.toMapCoordinates(1,1)
            center = canvas.center()
            crs: QgsCoordinateReferenceSystem = canvas.mapSettings().destinationCrs()
            bounds : QgsRectangle = crs.bounds()
            w = canvas.width()
            h = canvas.height()
            if pos == 'UL':
                newCenter = m2p.toMapCoordinates(1, 1)
            elif pos == 'LR':
                newCenter = m2p.toMapCoordinates(w-1, h-1)
            elif pos == 'UR':
                newCenter = m2p.toMapCoordinates(w-1, 0)
            elif pos == 'LL':
                newCenter = m2p.toMapCoordinates(0, h-1)
            else:
                raise NotImplementedError()

            if newCenter.x() < bounds.xMinimum():
                newCenter.setX(bounds.xMinimum() + tol.x())
            elif newCenter.x() > bounds.xMaximum():
                newCenter.setX(bounds.xMaximum() - tol.x())

            if newCenter.y() < bounds.yMinimum():
                newCenter.setX(bounds.yMinimum() + tol.y())
            elif newCenter.y() > bounds.yMaximum():
                newCenter.setX(bounds.yMaximum() - tol.y())

            canvas.setCenter(newCenter)
            return SpatialPoint.fromMapCanvasCenter(canvas)

        TSV.ui.optionSyncMapCenter.setChecked(True)
        TSV.mapWidget().timedRefresh()
        # 1. move QGIS
        pt = moveCanvasToCorner(qgisCanvas, 'UL')
        self.assertTrue(qgisCanvas.mapSettings().destinationCrs().isValid())
        self.assertIsInstance(qgisCanvas, QgsMapCanvas)

        TSV.mapWidget().timedRefresh()
        pt2 = TSV.spatialCenter().toCrs(pt.crs())

        s = ""


        extent = TSV.spatialExtent()
        self.assertIsInstance(extent, SpatialExtent)
        center = extent.spatialCenter()
        self.assertIsInstance(center, SpatialPoint)

        self.showGui(TSV)

        TSV.close()


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)

