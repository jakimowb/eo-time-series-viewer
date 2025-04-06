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
from typing import List, Optional

from qgis.PyQt.QtCore import QSize
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapvisualization import MapView, MapWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource

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
            self.assertEqualElements(v_a, v_b)

    def assertEqualElements(self, a, b,
                            prefix: str = '',
                            sort_lists: bool = False,
                            excluded_prefixes: Optional[List[str]] = None):
        if excluded_prefixes is None:
            excluded_prefixes = []
        self.assertEqual(type(a), type(b),
                         msg=f'{prefix}\n\tUnequal types: {a} vs {b}'.strip())
        if prefix in excluded_prefixes:
            return

        if isinstance(a, dict):
            self.assertEqual(a.keys(), b.keys())
            for k in a.keys():
                if k.startswith('_'):
                    continue
                self.assertEqualElements(a[k], b[k],
                                         prefix=f'{prefix}["{k}"]'.strip(),
                                         sort_lists=sort_lists,
                                         excluded_prefixes=excluded_prefixes)
        elif isinstance(a, set):
            self.assertEqualElements(list(a), list(b),
                                     sort_lists=sort_lists,
                                     prefix=prefix,
                                     excluded_prefixes=excluded_prefixes)
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b),
                             msg=f'{prefix}:\n\tLists differ in number of elements: {len(a)} != {len(b)}'
                                 f'\n\tExpected: {a}\n\t  Actual: {b}')
            if sort_lists:
                a, b = sorted(a), sorted(b)

            for i, (k1, k2) in enumerate(zip(a, b)):
                self.assertEqualElements(k1, k2,
                                         prefix=f'{prefix}[{i}]'.strip(),
                                         excluded_prefixes=excluded_prefixes)
        else:
            self.assertEqual(a, b,
                             msg=f'{prefix}:\n\tUnequal elements: {a} vs. {b}'.strip())

    # @unittest.skipIf(True, 'TEST')
    def test_force(self):

        TSV = EOTimeSeriesViewer()
        TSV.loadExampleTimeSeries(loadAsync=False)

        for tsd in TSV.timeSeries():
            self.assertIsInstance(tsd, TimeSeriesDate)
            tsd_range = tsd.dateTimeRange()
            for tss in tsd:
                self.assertIsInstance(tss, TimeSeriesSource)
                self.assertTrue(tsd_range.contains(tss.dtg()))

                lyr = tss.asRasterLayer()
                lyr_range = lyr.temporalProperties().fixedTemporalRange()
                self.assertTrue(tsd_range.contains(lyr_range))

        TSV.setMapsPerMapView(5, 1)
        TSV.createMapView('View2')
        self.showGui(TSV.ui)
        TSV.close()

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Does not run in parallel.')
    def test_write_read(self):
        from qgis.utils import iface
        c = iface.mapCanvas()
        self.assertIsInstance(c, QgsMapCanvas)
        c.destinationCrsChanged.connect(lambda *args, ca=c: onCRSChanged(ca))

        crs = QgsCoordinateReferenceSystem('EPSG:32633')
        c.setDestinationCrs(crs)

        TSV = EOTimeSeriesViewer()
        # reds0a = TSV.mapWidget()._allReds()

        TSV.createMapView('True Color')
        reds0b = TSV.mapWidget()._allReds()
        assert len(QgsProject.instance().mapLayers()) == 0
        TSV.loadExampleTimeSeries(loadAsync=False)
        reds0c = TSV.mapWidget()._allReds()

        assert len(QgsProject.instance().mapLayers()) == 0
        self.taskManagerProcessEvents()
        if len(TSV.timeSeries()) > 0:
            tsd = TSV.timeSeries()[-1]
            TSV.setCurrentDate(tsd)

        from example import exampleEvents
        lyr = QgsVectorLayer(exampleEvents.as_posix())
        lyr.setName('MyTestLayer')
        TSV.mapViews()[0].setName('True Color')
        TSV.addMapLayers([lyr])
        assert len(QgsProject.instance().mapLayers()) == 0
        TSV.createMapView('My 2nd View')
        TSV.applyAllVisualChanges()

        stretched = []
        for tss in TSV.timeSeries().sources():
            sid = tss.sid()
            if sid not in stretched:
                TSV.setCurrentDate(tss.dtg())
                for mv in TSV.mapViews():
                    for c in mv.mapCanvases():
                        c.stretchToCurrentExtent()
                stretched.append(sid)

        TSV.applyAllVisualChanges()

        def mapViewNoneSensorLayers() -> dict:
            return {mv.name(): [lyr.name() for lyr in mv.layers() if isinstance(lyr, QgsVectorLayer)] for mv in
                    TSV.mapViews()}

        nslayers1 = mapViewNoneSensorLayers()
        self.assertTrue('MyTestLayer' in nslayers1['True Color'])

        map_views = TSV.mapViews()
        self.assertTrue(len(map_views) == 2)

        ext = SpatialExtent.fromLayer(lyr)
        TSV.setCrs(ext.crs())
        self.assertEqual(TSV.crs(), ext.crs())
        TSV.setSpatialExtent(ext)
        # TSV.ui.show()
        TSV.applyAllVisualChanges()

        settings2 = TSV.asMap()
        self.assertValidSettings(settings2)
        TSV.applyAllVisualChanges()

        settings1 = TSV.asMap()

        # save settings
        path = self.createTestOutputDirectory() / 'test.qgs'
        QgsProject.instance().write(path.as_posix())
        TSV.applyAllVisualChanges()

        # Ensure that writing does not change the configuration
        # This test is inspired by MS Word's PDF export, that modified my dissertation docx
        # several times without even telling me! (I know I should have used LaTeX and have been doing so since.)
        settings2 = TSV.asMap()

        excluded_prefixes = [
            '["MapWidget"]["map_views"][0]["sensor_styles"]["{"nb": 5, "px_size_x": 5.0, "px_size_y": 5.0, "dt": 2, "wl": null, "wlu": null, "name": null}"]',
            '["MapWidget"]["map_views"][1]["sensor_styles"]["{"nb": 5, "px_size_x": 5.0, "px_size_y": 5.0, "dt": 2, "wl": null, "wlu": null, "name": null}"]',
            '["MapWidget"]["map_views"][2]["sensor_styles"]["{"nb": 5, "px_size_x": 5.0, "px_size_y": 5.0, "dt": 2, "wl": null, "wlu": null, "name": null}"]',
        ]
        if os.name != 'nt':
            excluded_prefixes.append('["MainWindow"]["geometry"]')

        self.assertEqualElements(settings1, settings2, excluded_prefixes=excluded_prefixes)
        nslayers2 = mapViewNoneSensorLayers()
        self.assertEqualElements(nslayers1, nslayers2, excluded_prefixes=excluded_prefixes)

        self.assertTrue(QgsProject.instance().read(path.as_posix()))
        TSV.applyAllVisualChanges()

        settings2 = TSV.asMap()
        nslayers2 = mapViewNoneSensorLayers()

        self.assertEqualElements(settings1, settings2, excluded_prefixes=excluded_prefixes)

        self.assertEqualElements(nslayers1, nslayers2, sort_lists=True, excluded_prefixes=excluded_prefixes)

        # do some changes
        new_map_size = QSize(300, 250)
        new_maps_per_view = (2, 2)
        new_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        TSV.setMapSize(new_map_size)
        TSV.createMapView('My New MapView')
        TSV.setCrs(new_crs)
        new_ns_layers = mapViewNoneSensorLayers()
        new_map_view_names = [mv.name() for mv in TSV.mapViews()]
        QgsApplication.processEvents()
        new_tss_visibility = dict()
        for tss in TSV.timeSeries().timeSeriesSources():
            tss.setIsVisible(random.choice([True, False]))
            new_tss_visibility[tss.source()] = tss.isVisible()

        TSV.mapWidget().setMapsPerMapView(*new_maps_per_view)

        self.assertEqual(new_crs, TSV.crs())

        settings3 = TSV.asMap()
        self.assertNotEqual(settings1, settings3)
        QgsApplication.processEvents()
        QgsProject.instance().write(path.as_posix())
        QgsApplication.processEvents()

        # reset all
        TSV.timeSeries().clear()
        TSV.mapWidget().removeAllMapViews()
        TSV.mapWidget().setMapsPerMapView(1, 1)
        crs = QgsCoordinateReferenceSystem('EPSG:32721')
        TSV.mapWidget().setCrs(crs)
        self.assertEqual(crs, TSV.crs())
        self.assertNotEqual(settings3, TSV.asMap())
        QgsApplication.processEvents()
        # reload project settings
        QgsProject.instance().read(path.as_posix())
        QgsApplication.processEvents()
        self.taskManagerProcessEvents()

        self.assertEqual(new_crs, TSV.crs())
        self.assertEqual(new_maps_per_view, TSV.mapWidget().mapsPerMapView())
        self.assertEqual(new_map_size, TSV.mapWidget().mapSize())
        self.assertEqual(new_map_view_names, [mv.name() for mv in TSV.mapViews()])

        self.assertEqualElements(settings3, TSV.asMap(), excluded_prefixes=excluded_prefixes)
        tss_vis = new_tss_visibility.copy()
        for tss in TSV.timeSeries().timeSeriesSources():
            self.assertTrue(tss.source() in tss_vis)
            self.assertEqual(tss.isVisible(), tss_vis.pop(tss.source()))
        self.assertTrue(len(tss_vis) == 0)

        ns_layers3 = mapViewNoneSensorLayers()

        self.assertEqualElements(new_ns_layers, ns_layers3)

        TSV.setMapsPerMapView(5, 1)

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
