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
import os.path
import unittest
import random
from typing import List

from PyQt5.QtCore import QSize
from qgis._core import QgsRectangle, QgsVectorLayer

from eotimeseriesviewer.mapvisualization import MapView, MapWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsTaskManager
from qgis.gui import QgsMapCanvas
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

# noinspection PyPep8Naming

start_app()


def onCRSChanged(c):
    print(f'QGIS MapCanvas CRS changed to {c.mapSettings().destinationCrs().description()}', flush=True)


class TestProjectIO(EOTSVTestCase):
    # @unittest.skip('N/A')

    def getMKeys(self, o: object) -> List[str]:
        return [v for k, v in o.__dict__.items() if k.startswith('MKey')]

    def assertValidSettings(self, a: dict):
        self.assertIsInstance(a, dict)
        for k in ['TimeSeries', 'MapWidget']:
            self.assertTrue(k in a)
            self.assertIsInstance(a[k], dict)

        for k in self.getMKeys(MapWidget):
            self.assertTrue(k in a['MapWidget'], msg=f'Missing MapWidget value "{k}"')
            for mv in a['MapWidget'][MapWidget.MKeyMapViews]:
                for k2 in self.getMKeys(MapView):
                    self.assertTrue(k2 in mv, msg=f'Missing MapView value "{k2}"')

        for k in ['sources']:
            self.assertTrue(k in a['TimeSeries'])

    def assertEqualSetting(self, a: dict, b: dict):

        self.assertValidSettings(a)
        self.assertValidSettings(b)

        self.assertEqual(a['TimeSeries'], b['TimeSeries'])

        mwA, mwB = a['MapWidget'], b['MapWidget']
        for k in self.getMKeys(MapWidget):
            v1, v2 = mwA[k], mwB[k]
            if k == MapWidget.MKeyCurrentExtent:
                ext1, ext2 = QgsRectangle.fromWkt(v1), QgsRectangle.fromWkt(v2)
                self.assertEqual(ext1.center(), ext2.center())
                self.assertAlmostEqual(ext1.width(), ext2.width(), 5)
                self.assertAlmostEqual(ext1.height(), ext2.height(), 5)
            else:
                self.assertEqual(v1, v2, msg=f'Different values for key "{k}": {v1} vs. {v2}')

        s = ""

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
        TSV.loadExampleTimeSeries(loadAsync=False)
        assert len(QgsProject.instance().mapLayers()) == 0

        self.taskManagerProcessEvents()

        if len(TSV.timeSeries()) > 0:
            tsd = TSV.timeSeries()[-1]
            TSV.setCurrentDate(tsd)

        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents)
        lyr.setName('MyTestLayer')
        TSV.addMapLayers([lyr])
        assert len(QgsProject.instance().mapLayers()) == 0

        ext = SpatialExtent.fromLayer(lyr)
        TSV.setCrs(ext.crs())
        self.assertEqual(TSV.crs(), ext.crs())
        TSV.setSpatialExtent(ext)
        settings2 = TSV.asMap()
        self.taskManagerProcessEvents()
        # self.assertEqual(ext, TSV.spatialExtent())

        settings1 = TSV.asMap()

        # save settings
        path = self.createTestOutputDirectory() / 'test.qgs'
        QgsProject.instance().write(path.as_posix())

        settings2 = TSV.asMap()
        self.assertEqualSetting(settings1, settings2)

        # read settings
        settings2 = TSV.asMap()
        self.assertTrue(QgsProject.instance().read(path.as_posix()))
        self.assertEqualSetting(settings1, settings2)

        # do some changes
        new_map_size = QSize(300, 250)
        new_maps_per_view = (2, 2)
        new_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        TSV.setMapSize(new_map_size)
        TSV.createMapView('My New MapView')
        TSV.setCrs(new_crs)

        new_map_view_names = [mv.name() for mv in TSV.mapViews()]

        new_tss_visibility = dict()
        for tss in TSV.timeSeries().timeSeriesSources():
            tss.setIsVisible(random.choice([True, False]))
            new_tss_visibility[tss.uri()] = tss.isVisible()

        TSV.mapWidget().setMapsPerMapView(*new_maps_per_view)

        self.assertEqual(new_crs, TSV.crs())

        settings3 = TSV.asMap()
        self.assertNotEqual(settings1, settings3)
        QgsProject.instance().write(path.as_posix())

        # reset all
        TSV.timeSeries().clear()
        TSV.mapWidget().removeAllMapViews()
        TSV.mapWidget().setMapsPerMapView(1, 1)
        crs = QgsCoordinateReferenceSystem('EPSG:32721')
        TSV.mapWidget().setCrs(crs)
        self.assertEqual(crs, TSV.crs())
        self.assertNotEqual(settings3, TSV.asMap())

        # reload project settings
        QgsProject.instance().read(path.as_posix())
        self.taskManagerProcessEvents()

        self.assertEqual(new_crs, TSV.crs())
        self.assertEqual(new_maps_per_view, TSV.mapWidget().mapsPerMapView())
        self.assertEqual(new_map_size, TSV.mapWidget().mapSize())
        self.assertEqual(new_map_view_names, [mv.name() for mv in TSV.mapViews()])

        self.assertEqualSetting(settings3, TSV.asMap())
        tss_vis = new_tss_visibility.copy()
        for tss in TSV.timeSeries().timeSeriesSources():
            self.assertTrue(tss.uri() in tss_vis)
            self.assertEqual(tss.isVisible(), tss_vis.pop(tss.uri()))
        self.assertTrue(len(tss_vis) == 0)

        self.showGui([TSV.ui])  #

        TSV.close()
        assert len(QgsProject.instance().mapLayers()) == 0
        assert len(TSV.mapLayerStore().mapLayers()) == 0
        QgsProject.instance().removeAllMapLayers()

        # QgsApplication.processEvents()

    PATH_Project = r'C:\Users\geo_beja\Desktop\ExampleEOTSV.qgz'

    @unittest.skipIf(not os.path.isfile((PATH_Project)), f'Project file does not exist {PATH_Project}')
    def test_load_project(self):

        p: QgsProject = QgsProject.instance()
        print(p.fileName())

        TSV = EOTimeSeriesViewer()
        p.read(self.PATH_Project)

        self.showGui(TSV.ui)
        TSV.close()


if __name__ == '__main__':
    unittest.main()
