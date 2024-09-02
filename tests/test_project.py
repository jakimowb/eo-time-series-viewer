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

import unittest

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsTaskManager
from qgis.gui import QgsMapCanvas

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()


def onCRSChanged(c):
    print(f'QGIS MapCanvas CRS changed to {c.mapSettings().destinationCrs().description()}', flush=True)


class TestProjectIO(EOTSVTestCase):
    # @unittest.skip('N/A')
    def test_write_read(self):
        from qgis.utils import iface
        c = iface.mapCanvas()
        self.assertIsInstance(c, QgsMapCanvas)
        c.destinationCrsChanged.connect(lambda *args, ca=c: onCRSChanged(ca))

        crs = QgsCoordinateReferenceSystem('EPSG:32633')
        c.setDestinationCrs(crs)

        TSV = EOTimeSeriesViewer()
        TSV.createMapView('True Color')

        tm: QgsTaskManager = QgsApplication.taskManager()

        assert len(QgsProject.instance().mapLayers()) == 0
        TSV.loadExampleTimeSeries(loadAsync=True)
        assert len(QgsProject.instance().mapLayers()) == 0

        self.taskManagerProcessEvents()

        if len(TSV.timeSeries()) > 0:
            tsd = TSV.timeSeries()[-1]
            TSV.setCurrentDate(tsd)

        from example import exampleEvents
        TSV.addVectorData(exampleEvents)
        assert len(QgsProject.instance().mapLayers()) == 0

        # save and read settings
        path = self.createTestOutputDirectory() / 'test.qgz'
        QgsProject.instance().write(path.as_posix())
        self.assertTrue(QgsProject.instance().read(path.as_posix()))

        self.taskManagerProcessEvents()

        self.showGui([TSV.ui])  #

        TSV.close()
        assert len(QgsProject.instance().mapLayers()) == 0
        assert len(TSV.mapLayerStore().mapLayers()) == 0
        QgsProject.instance().removeAllMapLayers()

        # QgsApplication.processEvents()

    def test_TimeSeriesViewerExampleSources(self):
        # self.taskManagerProcessEvents()
        TSV = EOTimeSeriesViewer()

        # TSV.loadExampleTimeSeries(loadAsync=False)
        # self.taskManagerProcessEvents()

        # self.showGui(TSV.ui)
        TSV.close()
        # QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
