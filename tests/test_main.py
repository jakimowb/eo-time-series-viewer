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


import unittest
import tempfile

from PyQt5.QtWidgets import QDialog
from qgis._core import QgsCoordinateReferenceSystem, QgsApplication, QgsProject
from qgis._gui import QgsMapCanvas

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, TestObjects


class TestMain(EOTSVTestCase):


    def test_TimeSeriesViewer(self):
        from qgis.utils import iface
        c = iface.mapCanvas()
        self.assertIsInstance(c, QgsMapCanvas)

        def onCRSChanged():
            print(f'QGIS MapCanvas CRS changed to {c.mapSettings().destinationCrs().description()}', flush=True)
        c.destinationCrsChanged.connect(onCRSChanged)

        crs = QgsCoordinateReferenceSystem('EPSG:32633')
        c.setDestinationCrs(crs)
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        TSV = EOTimeSeriesViewer()
        TSV.createMapView('True Color')
        TSV.createMapView('False Color')

        TSV.loadExampleTimeSeries(loadAsync=True)
        while QgsApplication.taskManager().countActiveTasks() > 0 or len(TSV.timeSeries().mTasks) > 0:
            QgsApplication.processEvents()

        if len(TSV.timeSeries()) > 0:
            tsd = TSV.timeSeries()[-1]
            TSV.setCurrentDate(tsd)
        from example import exampleEvents
        TSV.addVectorData(exampleEvents)
        # save and read settings
        path = self.createTestOutputDirectory() / 'test.qgz'
        QgsProject.instance().write(path.as_posix())
        self.assertTrue(QgsProject.instance().read(path.as_posix()))
        TSV.onReloadProject()

        self.showGui([TSV.ui])
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_TimeSeriesViewerNoSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        self.assertIsInstance(TSV, EOTimeSeriesViewer)
        self.showGui(TSV.ui)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_TimeSeriesViewerInvalidSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()
        images = ['not-existing-source']
        TSV.addTimeSeriesImages(images, loadAsync=False)

        self.showGui(TSV)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_TimeSeriesViewerMultiSource(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths, loadAsync=True)

        self.showGui(TSV.ui)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_AboutDialog(self):

        from eotimeseriesviewer.main import AboutDialogUI

        dialog = AboutDialogUI()

        self.assertIsInstance(dialog, QDialog)
        self.showGui([dialog])

    def test_exportMapsToImages(self):

        from eotimeseriesviewer.main import EOTimeSeriesViewer, SaveAllMapsDialog

        d = SaveAllMapsDialog()
        self.assertEqual(d.fileType(), 'PNG')

        dirTestOutput = self.createTestOutputDirectory() / 'test_screenshots'
        os.makedirs(dirTestOutput, exist_ok=True)
        pathTestOutput = dirTestOutput / 'canvas_shots.png'

        TSV = EOTimeSeriesViewer()

        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths, loadAsync=False)
        self.assertTrue(len(TSV.timeSeries()) > 0)
        TSV.exportMapsToImages(path=pathTestOutput)

        self.showGui(TSV)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_TimeSeriesViewerMassiveSources(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer

        TSV = EOTimeSeriesViewer()

        files = TestObjects.createArtificialTimeSeries(100)
        TSV.addTimeSeriesImages(files)

        self.showGui(TSV)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    print('\nRun 1 test in 5.373s\n\nFAILED (failures=1)', file=sys.stderr, flush=True)
    unittest.main(buffer=False)
    exit(0)

