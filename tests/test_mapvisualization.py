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
import os
import unittest
from pathlib import Path

import numpy as np
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QSpinBox, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomNode
from qgis.core import QgsFeatureRenderer, QgsHillshadeRenderer, QgsMultiBandColorRenderer, QgsPalettedRasterRenderer, \
    QgsProject, QgsRasterLayer, QgsRasterRenderer, QgsRasterShader, QgsSingleBandColorDataRenderer, \
    QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer, QgsVectorLayer, QgsVirtualLayerDefinition
from qgis.core import QgsMapLayer, QgsCoordinateTransform, QgsCoordinateReferenceSystem
from qgis.gui import QgsFontButton

from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.forceinputs import FindFORCEProductsTask
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapView, MapViewDock, MapWidget
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import rendererFromXml, rendererToXml
from eotimeseriesviewer.qgispluginsupport.qps.maptools import MapTools
from eotimeseriesviewer.qgispluginsupport.qps.utils import bandClosestToWavelength, file_search, parseWavelength, \
    SpatialExtent, UnitLookup
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.settings.settings import EOTSVSettingsManager
from eotimeseriesviewer.tests import EOTSVTestCase, example_raster_files, start_app, TestObjects
from eotimeseriesviewer.tests import FORCE_CUBE
from example.Images import Img_2014_05_07_LC82270652014127LGN00_BOA

start_app()


def getChildElements(node):
    assert isinstance(node, QDomNode)
    childs = node.childNodes()
    return [childs.at(i) for i in range(childs.count())]


def compareXML(element1, element2):
    assert isinstance(element1, QDomNode)
    assert isinstance(element2, QDomNode)

    tag1 = element1.nodeName()
    tag2 = element2.nodeName()
    if tag1 != tag2:
        return False

    elts1 = getChildElements(element1)
    elts2 = getChildElements(element2)

    if len(elts1) != len(elts2):
        return False

    if len(elts1) == 0:

        value1 = element1.nodeValue()
        value2 = element2.nodeValue()

        if value1 != value2:
            return False
        else:
            return True
    else:
        for e1, e2 in zip(elts1, elts2):
            if not compareXML(e1, e2):
                return False

        return True


# @unittest.skip('Not working yet')
class TestMapVisualization(EOTSVTestCase):
    """Test resources work."""

    def setUp(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        eotsv = EOTimeSeriesViewer.instance()
        if isinstance(eotsv, EOTimeSeriesViewer):
            eotsv.close()
            QApplication.processEvents()

    def test_FontButton(self):

        btn = QgsFontButton()
        # c = QgsMapCanvas()
        # c.setCanvasColor(QColor('black'))
        # c.show()
        # btn.setMapCanvas(c)
        tf = btn.textFormat()
        # tf.background().setFillColor(QColor('black'))
        # tf.background().setEnabled(True)
        tf.previewBackgroundColor = lambda: QColor('black')
        btn.setTextFormat(tf)
        btn.show()
        c = QColor('black')
        btn.setStyleSheet('background-color: rgb({}, {}, {});'.format(*c.getRgb()))

        def onChanged():
            tf = btn.textFormat()

            font = btn.font()

            s = ""

        btn.changed.connect(onChanged)
        self.showGui()

    def test_crs(self):

        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3035"),
                                           QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())

        self.assertTrue(transform.isValid())

    @unittest.skipIf(not isinstance(FORCE_CUBE, Path), 'FORCE_CUBE is undefined')
    def test_load_force_cube(self):
        eotsv = EOTimeSeriesViewer()
        eotsv.ui.show()
        eotsv.mapWidget().setMapsPerMapView(2, 1)
        tiles = [d.name for d in FORCEUtils.tileDirs(FORCE_CUBE)]
        if len(tiles) > 2:
            tiles = tiles[:1]
        task = FindFORCEProductsTask('BOA', FORCE_CUBE, tile_ids=tiles)
        task.run()
        files = task.files()[0:10]
        eotsv.addTimeSeriesImages(files)

        self.showGui(eotsv.ui)
        eotsv.close()
        QgsProject.instance().removeAllMapLayers()
        pass

    def test_load_layers_async(self):

        from example.Images import Img_2014_05_07_LC82270652014127LGN00_BOA, Img_2014_03_20_LC82270652014079LGN00_BOA, \
            re_2014_08_17
        from example import examplePoints, exampleNoDataImage
        from eotimeseriesviewer.mapvis.tasks import LoadMapCanvasLayers

        def onExecuted(bool, layers):
            s = ""

        raster_sources = {str(Img_2014_05_07_LC82270652014127LGN00_BOA): Img_2014_05_07_LC82270652014127LGN00_BOA,
                          str(Img_2014_03_20_LC82270652014079LGN00_BOA): None,
                          str(re_2014_08_17): {'type': QgsRasterLayer,
                                               'uri': re_2014_08_17,
                                               'providerType': 'gdal'},
                          'nonexistent': {},
                          }

        raster_sources = [
            {'uri': Img_2014_05_07_LC82270652014127LGN00_BOA,
             'legend_layer': 'foobar'},
            {'uri': Img_2014_03_20_LC82270652014079LGN00_BOA,
             'type': QgsRasterLayer,
             'providerType': 'gdal'},
            {'uri': 'does_not_exist'},
        ]

        other_sources = [
            {'uri': examplePoints},
            {'uri': exampleNoDataImage},
        ]

        task = LoadMapCanvasLayers(raster_sources)
        task.executed.connect(onExecuted)
        task.run_task_manager()

        for result in task.mResults:
            assert isinstance(result, dict)
            assert 'legend_layer' in result
            assert 'uri' in result
            self.assertIsInstance(result.get('layer'), QgsMapLayer)

        self.assertTrue(len(task.mErrors) == 1)
        self.assertTrue('does_not_exist' in str(task.mErrors))

        task = LoadMapCanvasLayers(other_sources)
        task.run()

        results = task.mResults
        self.assertEqual(len(results), 2)
        for result in results:
            lyr = result.get('layer')
            self.assertIsInstance(lyr, QgsMapLayer)
            self.assertTrue(lyr.isValid())

    def test_mapWidget(self):

        TS = TestObjects.createTimeSeries()
        w = MapWidget()
        w.setTimeSeries(TS)

        w.setMapTextFormat(EOTSVSettingsManager.settings().mapTextFormat)
        w.mMapViewColumns = 1
        w.show()

        controllW = QWidget()
        controllW.setLayout(QGridLayout())
        g = controllW.layout()
        assert isinstance(g, QGridLayout)

        def onNMapViews(n):
            mvs = w.mapViews()

            if n < 0:
                return

            if n < len(mvs):
                toRemove = mvs[n:]
                for mv in toRemove:
                    w.removeMapView(mv)
            elif n > len(mvs):
                while len(w.mapViews()) < n:
                    mv = MapView()
                    mv.optionShowSensorName.setChecked(True)
                    mv.optionShowMapViewName.setChecked(True)

                    mv.setTitle('MV {}'.format(len(w.mapViews())))
                    w.addMapView(mv)

        btnAMV = QPushButton('Add MapView')
        btnRMV = QPushButton('Remove MapView')
        btnAMV.clicked.connect(lambda: onNMapViews(len(w.mapViews()) + 1))
        btnRMV.clicked.connect(lambda: onNMapViews(len(w.mapViews()) - 1))

        sb = QSpinBox()
        sb.setMinimum(1)
        sb.setMaximum(100)
        sb.setValue(w.mMapViewColumns)
        sb.valueChanged.connect(lambda v: w.setMapsPerMapView(v))

        sbX = QSpinBox()
        sbX.setRange(50, 1000)
        sbX.setSingleStep(50)
        sbX.setValue(w.mMapSize.width())
        sbY = QSpinBox()
        sbY.setRange(50, 1000)
        sbY.setSingleStep(50)
        sbY.setValue(w.mMapSize.height())

        def onMapSizeChanged():

            s = QSize(sbX.value(), sbY.value())
            w.setMapSize(s)

        sbY.valueChanged.connect(onMapSizeChanged)
        sbX.valueChanged.connect(onMapSizeChanged)

        g.addWidget(QLabel('n dates'), 1, 0)
        g.addWidget(sb, 1, 1)
        g.addWidget(btnAMV, 2, 0)
        g.addWidget(btnRMV, 2, 1)

        g.addWidget(QLabel('Map Size'), 3, 0)
        g.addWidget(sbX, 3, 1)
        g.addWidget(sbY, 3, 2)
        controllW.show()

        mv1 = MapView(name='mv1')
        mv2 = MapView(name='mv2')
        mv3 = MapView(name='mv3')
        w.addMapView(mv1)

        if False:
            w.addMapView(mv2)

            self.assertEqual(w.mGrid.rowCount(), 2)
            w.addMapView(mv1)
            self.assertEqual(w.mGrid.rowCount(), 2)
            w.addMapView(mv3)
            self.assertEqual(w.mGrid.rowCount(), 3)
        # w.removeMapView(mv2)
        # self.assertEqual(w.mGrid.rowCount(), 2)
        # self.assertListEqual(w.mMapViews, [mv1, mv3])

        for mv in w.mapViews():
            self.assertIsInstance(mv, MapView)
            mv.setMapInfoExpression('@map_date')

        w.setCurrentDate(TS[0])

        for c in w.mapCanvases():
            c.update()
        self.showGui()
        TS.clear()

    def test_daterange(self):
        ts = TestObjects.createTimeSeries()
        MW = MapWidget()
        MW.setTimeSeries(ts)

        sigRange = None

        def onDateRangeChanged(*new_range):
            nonlocal sigRange
            sigRange = new_range

        MW.sigDateRangeChanged.connect(onDateRangeChanged)

        # show 3 maps
        MW.setMapsPerMapView(3, 1)
        view: MapView = MW.createMapView('mapview')

        tsd = ts[10]

        tsd0 = ts[9]
        tsd1 = ts[11]

        MW.setCurrentDate(tsd.dtg(), mode='center')
        visible = MW.visibleTSDs()

        d0, d1 = MW.currentDateRange()
        self.assertTrue(len(visible), 3)
        self.assertEqual(d0, tsd0.dtg())
        self.assertEqual(d1, tsd1.dtg())
        self.assertEqual(sigRange, (d0, d1))

        MW.setCurrentDate(tsd.dtg(), mode='start')
        d0, d1 = MW.currentDateRange()
        self.assertTrue(len(visible), 3)
        self.assertEqual(d0, tsd.dtg())
        self.assertEqual(sigRange, (d0, d1))

        MW.setCurrentDate(tsd.dtg(), mode='end')
        d0, d1 = MW.currentDateRange()
        self.assertTrue(len(visible), 3)
        self.assertEqual(d1, tsd.dtg())
        self.assertEqual(sigRange, (d0, d1))

        ts.clear()

    def test_mapview(self):
        TS = TestObjects.createTimeSeries()
        lyr = TestObjects.createVectorLayer()
        lyr.setName('Layer1 NAME')
        lyr2 = TestObjects.createVectorLayer()
        lyr2.setName('Layer2 name')

        QgsProject.instance().addMapLayers([lyr, lyr2])

        mapview = MapView()

        self.assertEqual([], mapview.sensors())

        for sensor in TS.sensors():
            self.assertIsInstance(sensor, SensorInstrument)
            mapview.addSensor(sensor)
        mapview.addLayer(lyr)
        mapview.addLayer(lyr2)
        self.assertEqual(TS.sensors(), mapview.sensors())

        MW = MapWidget()
        MW.setTimeSeries(TS)
        tsd = TS[0]
        MW.setMapsPerMapView(3, 2)
        MW.addMapView(mapview)
        MW.setCurrentDate(tsd)
        self.taskManagerProcessEvents()
        self.assertTrue(len(MW.mapCanvases()) == 6)

        canvas = MW.mapCanvases()[0]
        self.assertIsInstance(canvas, MapCanvas)
        self.assertEqual(canvas.tsd(), tsd)
        self.assertEqual(canvas.mapView(), mapview)

        self.assertEqual([], canvas.layers())
        canvas.timedRefresh()

        self.assertNotEqual([], canvas.layers())
        l = canvas.layers()[-1]
        MW.setCrs(l.crs())
        MW.setSpatialExtent(SpatialExtent.fromLayer(l))
        self.showGui()
        MW.close()
        QgsProject.instance().removeAllMapLayers()
        TS.clear()

    def test_mapViewDock(self):

        TS = TestObjects.createTimeSeries()
        mw = MapWidget()
        mw.setTimeSeries(TS)
        mw.setMapsPerMapView(1, 2)
        mw.setMapTool(MapTools.CursorLocation)
        dock = MapViewDock()
        self.assertIsInstance(dock, MapViewDock)
        # dock.setTimeSeries(TS)

        dock.setMapWidget(mw)

        tsd = TS[0]
        tss = tsd[0]

        mw.setCurrentDate(tsd)
        mw.setCrs(tss.crs())
        mw.setSpatialExtent(tss.spatialExtent())
        self.showGui([dock, mw])
        TS.clear()

    def test_mapcanvas(self):
        files = example_raster_files()
        lyr1 = QgsRasterLayer(files[0])
        m = MapCanvas()
        m.setLayers([])
        self.assertIsInstance(m, MapCanvas)
        m.show()

    def test_virtualLayers(self):
        lyr = TestObjects.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        VL = QgsVirtualLayerDefinition()

    def test_bandselection(self):
        lyr = QgsRasterLayer(Img_2014_05_07_LC82270652014127LGN00_BOA)

        wl, wlu = parseWavelength(lyr)
        self.assertIsInstance(wl, np.ndarray)
        self.assertIsInstance(wlu, str)
        wlu = UnitLookup.baseUnit(wlu)
        self.assertEqual(wlu, 'μm')
        refWL = [0.49, 0.56, 0.66, 0.84, 1.65, 2.2]

        self.assertEqual(len(wl), len(refWL))
        for wla, wlb in zip(wl, refWL):
            self.assertAlmostEqual(wla, wlb)

        self.assertEqual(0, bandClosestToWavelength(lyr, 'B'))

    def test_renderer(self):
        styleFiles = file_search(os.path.dirname(__file__), 'style*.txt')

        lyr = QgsRasterLayer(Img_2014_05_07_LC82270652014127LGN00_BOA)
        self.assertIsInstance(lyr, QgsRasterLayer)
        self.assertTrue(lyr.isValid())

        r0 = lyr.renderer()

        xml0 = rendererToXml(r0)
        r0b = rendererFromXml(xml0)
        self.assertTrue(type(r0), type(r0b))

        self.assertIsInstance(r0, QgsMultiBandColorRenderer)

        rasterRenderer = [QgsSingleBandGrayRenderer(r0, 0),
                          r0,
                          QgsPalettedRasterRenderer(r0, 0, [
                              QgsPalettedRasterRenderer.Class(0, QColor('black'), 'class1'),
                              QgsPalettedRasterRenderer.Class(1, QColor('green'), 'class2'),
                          ]),
                          QgsHillshadeRenderer(r0, 0, 0.0, 100.0),
                          QgsSingleBandPseudoColorRenderer(r0, 0, QgsRasterShader(0.0, 255.0)),
                          QgsSingleBandColorDataRenderer(r0, 0),
                          ]

        for r in rasterRenderer:
            r.setInput(lyr.dataProvider())
        vectorRenderer = []  # [QgsSingleSymbolRenderer(QgsLineSymbol()), QgsPointDistanceRenderer()]

        for r1 in rasterRenderer + vectorRenderer:
            print('Test {}'.format(r1.__class__.__name__))
            xml1 = rendererToXml(r1)
            self.assertIsInstance(xml1, QDomDocument)

            r1b = rendererFromXml(xml1)
            self.assertTrue(type(r1) is type(r1b), msg='Failed to reconstruct {r1.__class__.__name__}')

            if isinstance(r1, QgsRasterRenderer):
                self.assertIsInstance(r1b, QgsRasterRenderer)
            elif isinstance(r1, QgsFeatureRenderer):
                self.assertIsInstance(r1b, QgsFeatureRenderer)

            xml2 = rendererToXml(r1b)
            self.assertIsInstance(xml2, QDomDocument)
            self.assertTrue(xml1.toString() == xml2.toString())

            rClone = r1.clone()
            self.assertTrue(type(r1), type(rClone))
            xmlClone = rendererToXml(rClone)
            self.assertIsInstance(xmlClone, QDomDocument)

            similar = compareXML(xml1.firstChild(), xml2.firstChild())
            self.assertTrue(similar)
            del rClone, xmlClone

        print('Read style files')
        for path in styleFiles:
            with open(path, encoding='utf8') as f:
                print(path)
                xml = ''.join(f.readlines())
                renderer = rendererFromXml(xml)
                self.assertTrue(renderer is not None)
                self.assertIsInstance(renderer, (QgsRasterRenderer, QgsFeatureRenderer))
        print('Render tests finished')
        lyr.deleteLater()


if __name__ == '__main__':
    unittest.main(buffer=False)
