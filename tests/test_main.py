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
from eotimeseriesviewer.tests import start_app, testRasterFiles
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.core import *
from qgis.gui import *
from qgis.testing import TestCase
import unittest
import tempfile


from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.tests import TestObjects, EOTSVTestCase
from eotimeseriesviewer.main import *
class TestMain(EOTSVTestCase):


    def tearDown(self):
        eotsv = EOTimeSeriesViewer.instance()
        if isinstance(eotsv, EOTimeSeriesViewer):
            eotsv.close()
            QApplication.processEvents()
        super().tearDown()

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

    def test_TimeSeriesViewerNoSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        self.assertIsInstance(TSV, EOTimeSeriesViewer)
        self.showGui(TSV.ui)


    def test_TaskManagerStatusButton(self):

        bar = QgsStatusBar()
        w = TaskManagerStatusButton()
        bar.addPermanentWidget(w, 10, QgsStatusBar.AnchorLeft)
        bar.showMessage('my status')
        w.mInfoLabel.setText('emoty')
        self.showGui(bar)

    def test_TimeSeriesViewer(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        TSV = EOTimeSeriesViewer()
        TSV.createMapView('True Color')
        TSV.createMapView('Near Infrared')
        TSV.loadExampleTimeSeries()
        while QgsApplication.taskManager().countActiveTasks() > 0 or len(TSV.timeSeries().mTasks) > 0:
            QCoreApplication.processEvents()

        if len(TSV.timeSeries()) > 0:
            tsd = TSV.timeSeries()[-1]
            TSV.setCurrentDate(tsd)

        self.showGui([TSV.ui])

    def test_TimeSeriesViewerInvalidSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()
        images = ['not-existing-source']
        TSV.addTimeSeriesImages(images, loadAsync=False)

        self.showGui(TSV)

    def test_TimeSeriesViewerMultiSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths)

        self.showGui(TSV.ui)

    def test_AboutDialog(self):

        from eotimeseriesviewer.main import AboutDialogUI

        dialog = AboutDialogUI()

        self.assertIsInstance(dialog, QDialog)
        self.showGui([dialog])


    def test_exportMapsToImages(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer, SaveAllMapsDialog

        d = SaveAllMapsDialog()
        self.assertEqual(d.fileType(), 'PNG')

        pathTestOutput = tempfile.mkdtemp(prefix='EOTSTTestOutput')

        TSV = EOTimeSeriesViewer()

        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths)
        TSV.exportMapsToImages(path=pathTestOutput)

        self.showGui(TSV)

    def test_TimeSeriesViewerMassiveSources(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        files = TestObjects.createArtificialTimeSeries(100)
        TSV.addTimeSeriesImages(files)

        self.showGui(TSV)




if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)

