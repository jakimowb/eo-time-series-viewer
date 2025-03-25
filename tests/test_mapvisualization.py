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

import numpy as np
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QGridLayout, QLabel, QSpinBox, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomNode

from eotimeseriesviewer.settings.settings import EOTSVSettingsManager
from eotimeseriesviewer.tests import EOTSVTestCase, example_raster_files, start_app, TestObjects

start_app()

from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapWidget, MapView, MapViewDock
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import rendererToXml, rendererFromXml
from eotimeseriesviewer.qgispluginsupport.qps.maptools import MapTools
from eotimeseriesviewer.qgispluginsupport.qps.utils import parseWavelength, bandClosestToWavelength, file_search, \
    UnitLookup, SpatialExtent
from eotimeseriesviewer.sensors import SensorInstrument
from example.Images import Img_2014_05_07_LC82270652014127LGN00_BOA
from qgis.PyQt.QtWidgets import QPushButton
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsMultiBandColorRenderer, QgsSingleBandGrayRenderer, \
    QgsPalettedRasterRenderer, QgsSingleBandPseudoColorRenderer, QgsRasterRenderer
from qgis.core import QgsFeatureRenderer, \
    QgsSingleBandColorDataRenderer, QgsHillshadeRenderer, \
    QgsRasterShader, \
    QgsVirtualLayerDefinition
from qgis.gui import QgsFontButton

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

        from eotimeseriesviewer.mapcanvas import MapCanvas
        MW = MapWidget()
        MW.setTimeSeries(TS)
        tsd = TS[0]

        MW.setMapsPerMapView(3, 2)
        MW.addMapView(mapview)
        MW.setCurrentDate(tsd)
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
            self.assertTrue(type(r1) == type(r1b), msg='Failed to reconstruct {r1.__class__.__name__}')

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
                self.assertTrue(renderer != None)
                self.assertIsInstance(renderer, (QgsRasterRenderer, QgsFeatureRenderer))
        print('Render tests finished')
        lyr.deleteLater()


if __name__ == '__main__':
    unittest.main(buffer=False)
