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

import configparser
import unittest
import os
import xmlrunner
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsProject
from qgis.gui import QgsMapToolZoom, QgsMapToolPan
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.tests import EOTSVTestCase
from eotimeseriesviewer.externals.qps.maptools import MapTools, MapToolCenter, \
    FullExtentMapTool, PixelScaleExtentMapTool, QgsMapToolAddFeature, CursorLocationMapTool, QgsMapToolSelect


class TestMapTools(EOTSVTestCase):
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """

    def test_read_init(self):
        """Test that the plugin __init__ will validate on plugins.qgis.org."""

        # You should update this list according to the latest in
        # https://github.com/qgis/qgis-django/blob/master/qgis-app/plugins/validator.py

        required_metadata = [
            'name',
            'description',
            'version',
            'qgisMinimumVersion',
            'email',
            'author']

        file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), os.pardir,
            'metadata.txt'))

        metadata = []
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(file_path)
        message = 'Cannot find a section named "general" in %s' % file_path
        assert parser.has_section('general'), message
        metadata.extend(parser.items('general'))

        for expectation in required_metadata:
            message = ('Cannot find metadata "%s" in metadata source (%s).' % (
                expectation, file_path))

            self.assertIn(expectation, dict(metadata), message)

    def test_TimeSeriesViewer(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()
        TSV.show()
        TSV.loadExampleTimeSeries(loadAsync=False)
        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents)
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


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
