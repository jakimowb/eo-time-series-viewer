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
import tracemalloc
import unittest
from time import time

from qgis._core import QgsRasterLayer

from eotimeseriesviewer.main import EOTimeSeriesViewer, SaveAllMapsDialog
from eotimeseriesviewer.tests import EOTSVTestCase, TestObjects, start_app, testRasterFiles
from qgis.core import QgsCoordinateReferenceSystem, QgsApplication, QgsProject
from qgis.gui import QgsMapCanvas

start_app()


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

        TSV.reloadProject()

        self.showGui([TSV.ui])
        TSV.close()
        QgsProject.instance().removeAllMapLayers()
        s = ""

    # @unittest.skip('test')
    def test_TimeSeriesViewerExampleSources(self):

        TSV = EOTimeSeriesViewer()
        TSV.loadExampleTimeSeries(loadAsync=False)

        self.showGui(TSV.ui)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('test')
    def test_TimeSeriesViewerNoSource(self):

        TSV = EOTimeSeriesViewer()

        self.assertIsInstance(TSV, EOTimeSeriesViewer)
        self.showGui(TSV.ui)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('test')
    def test_TimeSeriesViewerInvalidSource(self):

        TSV = EOTimeSeriesViewer()
        images = ['not-existing-source']
        TSV.addTimeSeriesImages(images, loadAsync=False)

        self.showGui(TSV)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('test')
    def test_TimeSeriesViewerMultiSource(self):

        TSV = EOTimeSeriesViewer()

        paths = TestObjects.createMultiSourceTimeSeries()
        TSV.addTimeSeriesImages(paths, loadAsync=True)

        self.showGui(TSV.ui)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_exportMapsToImages(self):

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

    # @unittest.skip('test')
    def test_TimeSeriesViewerMassiveSources(self):

        TSV = EOTimeSeriesViewer()

        files = TestObjects.createArtificialTimeSeries(100)
        TSV.addTimeSeriesImages(files)

        self.showGui(TSV)
        TSV.close()
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
