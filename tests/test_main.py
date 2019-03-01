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

import os, sys, unittest, configparser

from timeseriesviewer.tests import initQgisApplication, testRasterFiles
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from timeseriesviewer.mapcanvas import *
from timeseriesviewer.tests import TestObjects

QGIS_APP = initQgisApplication()
SHOW_GUI = True


class TestInit(unittest.TestCase):
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


        from timeseriesviewer.main import TimeSeriesViewer

        TSV = TimeSeriesViewer()
        TSV.show()
        TSV.loadExampleTimeSeries()

        if SHOW_GUI:
            QGIS_APP.exec_()

    def test_TimeSeriesViewerMultiSource(self):

        from timeseriesviewer.main import TimeSeriesViewer

        TSV = TimeSeriesViewer()
        TSV.show()
        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths)

        if SHOW_GUI:
            QGIS_APP.exec_()


    def test_TimeSeriesViewerNoSource(self):

        from timeseriesviewer.main import TimeSeriesViewer

        TSV = TimeSeriesViewer()
        TSV.show()
        #TSV.loadExampleTimeSeries(1)
        self.assertIsInstance(TSV, TimeSeriesViewer)
        if SHOW_GUI:
            QGIS_APP.exec_()


if __name__ == '__main__':
    unittest.main()
