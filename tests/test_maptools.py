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
import unittest

from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsMapToolPan, QgsMapToolZoom
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.maptools import CursorLocationMapTool, FullExtentMapTool, MapToolCenter, \
    MapTools, PixelScaleExtentMapTool, QgsMapToolAddFeature, QgsMapToolSelect
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()


class TestMapTools(EOTSVTestCase):
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """

    def test_TimeSeriesViewer(self):
        TSV = EOTimeSeriesViewer()
        TSV.show()
        TSV.loadExampleTimeSeries(loadAsync=False)
        from example import examplePoints
        lyr = QgsVectorLayer(examplePoints.as_posix())
        QgsProject.instance().addMapLayer(lyr)

        TSV.setMapTool(MapTools.ZoomIn)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), QgsMapToolZoom)

        TSV.setMapTool(MapTools.ZoomOut)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), QgsMapToolZoom)

        TSV.setMapTool(MapTools.ZoomFull)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), FullExtentMapTool)

        TSV.setMapTool(MapTools.Pan)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), QgsMapToolPan)

        TSV.setMapTool(MapTools.ZoomPixelScale)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), PixelScaleExtentMapTool)

        TSV.setMapTool(MapTools.CursorLocation)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), CursorLocationMapTool)

        # TSV.setMapTool(MapTools.SpectralProfile)
        # self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), SpectralProfileMapTool)

        # TSV.setMapTool(MapTools.TemporalProfile)
        # self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), TemporalProfileMapTool)

        TSV.setMapTool(MapTools.MoveToCenter)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), MapToolCenter)

        TSV.setMapTool(MapTools.AddFeature)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), QgsMapToolAddFeature)

        TSV.setMapTool(MapTools.SelectFeature)
        self.assertIsInstance(TSV.mapCanvases()[0].mapTool(), QgsMapToolSelect)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()
        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
