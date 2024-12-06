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
import random
import unittest
from typing import List

from PyQt5.QtCore import QSize
from qgis._core import QgsRectangle, QgsVectorLayer

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapvisualization import MapView, MapWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsTaskManager
from qgis.gui import QgsMapCanvas

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

    def assertEqualMapView(self, a: dict, b: dict):
        self.assertIsInstance(a, dict)
        self.assertIsInstance(b, dict)

        for k in self.getMKeys(MapView):
            self.assertTrue(k in a)
            self.assertTrue(k in b)

            v_a, v_b = a[k], b[k]
            if k == MapView.MKeySensorStyle:
                self.assertIsInstance(v_a, dict)
                self.assertIsInstance(v_b, dict)
                for sid in v_a.keys():
                    self.assertTrue(sid in v_b)
                    style_a, style_b = v_a[sid], v_b[sid]

                    self.assertEqual(style_a, style_b)
            else:
                self.assertEqual(v_a, v_b)

    def assertEqualSetting(self, a: dict, b: dict):

        self.assertValidSettings(a)
        self.assertValidSettings(b)

        self.assertEqual(a['TimeSeries'], b['TimeSeries'])

        mwA, mwB = a['MapWidget'], b['MapWidget']
        for k in self.getMKeys(MapWidget):
            v_a, v_b = mwA[k], mwB[k]
            if k == MapWidget.MKeyCurrentExtent:
                ext1, ext2 = QgsRectangle.fromWkt(v_a), QgsRectangle.fromWkt(v_b)
                self.assertEqual(ext1.center(), ext2.center())
                self.assertAlmostEqual(ext1.width(), ext2.width(), 5)
                self.assertAlmostEqual(ext1.height(), ext2.height(), 5)
            elif k == MapWidget.MKeyMapViews:
                self.assertEqual(len(v_a), len(v_b))

                for view_a, view_b in zip(v_a, v_b):
                    if view_a != view_b:
                        s = ""
                    self.assertEqualMapView(view_a, view_b)
            else:
                self.assertEqualElements(v_a, v_b)
                self.assertEqual(v_a, v_b, msg=f'Different values for key "{k}": {v_a} vs. {v_b}')

            if v_a != v_b:
                s = ""
        s = ""

    def assertEqualElements(self, a, b, msg: str = ''):
        self.assertEqual(type(a), type(b), msg=msg + 'Unequal types')

        if isinstance(a, dict):
            self.assertEqual(a.keys(), b.keys())
            for k in a.keys():
                self.assertEqualElements(a[k], b[k], msg=f'Key {k}:')
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b))
            for k1, k2 in zip(a, b):
                self.assertEqualElements(k1, k2)
        else:
            if a != b:
                s = ""
            self.assertEqual(a, b)

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
        TSV.createMapView('My 2nd View')
        map_views = TSV.mapViews()
        self.assertTrue(len(map_views) == 2)

        # read settings
        def getRedMinValues(tsv):
            tsv.mapWidget().timedRefresh()
            QgsApplication.processEvents()
            reds = []
            for mv in tsv.mapViews():
                for lyr in mv.sensorProxyLayers():
                    reds.append(lyr.renderer().redContrastEnhancement().minimumValue())
            return reds

        reds = getRedMinValues(TSV)

        ext = SpatialExtent.fromLayer(lyr)
        TSV.setCrs(ext.crs())
        self.assertEqual(TSV.crs(), ext.crs())
        TSV.setSpatialExtent(ext)
        self.taskManagerProcessEvents()

        settings2 = TSV.asMap()
        self.assertValidSettings(settings2)
        for mv, mvmap in zip(map_views, settings2['MapWidget'][MapWidget.MKeyMapViews]):
            self.assertEqual(mv.name(), mvmap[MapView.MKeyName])

        # self.assertEqual(ext, TSV.spatialExtent())
        TSV.mapWidget().timedRefresh()
        settings1 = TSV.asMap()

        # save settings
        path = self.createTestOutputDirectory() / 'test.qgs'
        QgsProject.instance().write(path.as_posix())
        TSV.mapWidget().timedRefresh()

        settings2 = TSV.asMap()
        self.assertEqualSetting(settings1, settings2)

        reds1_a = getRedMinValues(TSV)
        TSV.mapWidget().timedRefresh()
        QgsApplication.processEvents()
        reds1_b = getRedMinValues(TSV)

        self.assertTrue(QgsProject.instance().read(path.as_posix()))

        r2ba = TSV.mapWidget()._allReds()
        QgsApplication.processEvents()
        reds2_a = getRedMinValues(TSV)
        r2b = TSV.mapWidget()._allReds()
        TSV.mapWidget().timedRefresh()
        QgsApplication.processEvents()
        reds2_b = getRedMinValues(TSV)
        r2c = TSV.mapWidget()._allReds()
        QgsApplication.processEvents()
        settings2 = TSV.asMap()
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
