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

from eotimeseriesviewer.tests import initQgisApplication, createTimeSeries, testRasterFiles, TestObjects
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, TimeSeriesSource
from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer.mapvisualization import *
from example.Images import Img_2014_05_07_LC82270652014127LGN00_BOA
QGIS_APP = initQgisApplication(loadProcessingFramework=False)

from eotimeseriesviewer import initResources
initResources()

SHOW_GUI = True and os.environ.get('CI') is None and not os.environ.get('CI')


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


class testclassMapVisualization(unittest.TestCase):
    """Test resources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_mapview(self):

        TS = TestObjects.createTimeSeries()
        lyr = TestObjects.createVectorLayer()
        lyr.setName('Layer1 Name')
        lyr.setTitle('Layer1 title')
        lyr2 = TestObjects.createVectorLayer()
        lyr2.setName('Layer2 name')

        mapview = MapView()

        self.assertEqual([], mapview.sensors())

        for sensor in TS.sensors():
            self.assertIsInstance(sensor, SensorInstrument)
            mapview.addSensor(sensor)
        mapview.addLayer(lyr)
        mapview.addLayer(lyr2)
        self.assertEqual(TS.sensors(), mapview.sensors())

        from eotimeseriesviewer.mapcanvas import MapCanvas
        canvas = MapCanvas()
        tsd = TS[0]
        canvas.setTSD(tsd)
        mapview.registerMapCanvas(canvas)

        self.assertTrue(canvas in mapview.mapCanvases())
        canvas.show()
        self.assertEqual([], canvas.layers())
        canvas.timedRefresh()
        self.assertNotEqual([], canvas.layers())
        l = canvas.layers()[-1]
        canvas.setCrs(l.crs())
        canvas.setExtent(l.extent())

        if SHOW_GUI:
            w = QWidget()
            w.setLayout(QHBoxLayout())
            w.layout().addWidget(mapview)
            w.layout().addWidget(canvas)
            w.show()

            timer = QTimer()
            timer.timeout.connect(canvas.timedRefresh)
            timer.setInterval(500)
            timer.start()
            QGIS_APP.exec_()

    def test_mapViewDock(self):

        TS = TestObjects.createTimeSeries()

        dock = MapViewDock()
        self.assertIsInstance(dock, MapViewDock)
        dock.setTimeSeries(TS)
        mapView = dock.createMapView()
        self.assertIsInstance(mapView, MapView)
        mapView.setTimeSeries(TS)
        canvas = MapCanvas()
        canvas.setTSD(TS[0])
        mapView.registerMapCanvas(canvas)
        tss = TS[0][0]
        self.assertIsInstance(tss, TimeSeriesSource)
        canvas.setCrs(tss.crs())
        canvas.setSpatialExtent(tss.spatialExtent())


        if SHOW_GUI:
            dock.show()
            canvas.show()

            timer = QTimer()
            timer.timeout.connect(canvas.timedRefresh)
            timer.setInterval(500)
            timer.start()

            QGIS_APP.exec_()



    def test_mapcanvas(self):

        files = testRasterFiles()

        lyr1 = QgsRasterLayer(files[0])


        m = MapCanvas()
        m.setLayers([])
        self.assertIsInstance(m, MapCanvas)
        m.show()




    def test_bandselection(self):

        lyr = QgsRasterLayer(Img_2014_05_07_LC82270652014127LGN00_BOA)

        wl, wlu = parseWavelength(lyr)
        self.assertIsInstance(wl, np.ndarray)
        self.assertIsInstance(wlu, str)
        self.assertEqual(wlu, 'um')
        refWL = [0.49,  0.56,  0.66,  0.84,  1.65,  2.2]

        self.assertEqual(len(wl), len(refWL))
        for wla, wlb in zip(wl, refWL):
            self.assertAlmostEqual(wla, wlb)

        self.assertEqual(0, bandClosestToWavelength(lyr, 'B'))
        s = ""

    def test_renderer(self):

        styleFiles = file_search(os.path.dirname(__file__), 'style*.txt')

        lyr = QgsRasterLayer(Img_2014_05_07_LC82270652014127LGN00_BOA)

        r0 = lyr.renderer()
        from eotimeseriesviewer.externals.qps.layerproperties import rendererFromXml, rendererToXml
        xml0 = rendererToXml(r0)
        r0b = rendererFromXml(xml0)
        self.assertTrue(type(r0), type(r0b))



        rasterRenderer = [QgsMultiBandColorRenderer(r0, 3,2,1, QgsContrastEnhancement(), QgsContrastEnhancement(), QgsContrastEnhancement()),
                          QgsPalettedRasterRenderer(r0,0, [
                              QgsPalettedRasterRenderer.Class(0, QColor('black'), 'class1'),
                              QgsPalettedRasterRenderer.Class(1, QColor('green'), 'class2'),
                          ] ),
                          QgsHillshadeRenderer(r0, 0, 0.0, 100.0),
                          QgsSingleBandPseudoColorRenderer(r0, 0, QgsRasterShader(0.0, 255.0)),
                          QgsSingleBandColorDataRenderer(r0, 0),
                          QgsSingleBandGrayRenderer(r0, 0)]

        vectorRenderer = []#[QgsSingleSymbolRenderer(QgsLineSymbol()), QgsPointDistanceRenderer()]

        for r1 in rasterRenderer + vectorRenderer:
            print('Test {}'.format(r1.__class__.__name__))
            xml1 = rendererToXml(r1)
            self.assertIsInstance(xml1, QDomDocument)


            r1b = rendererFromXml(xml1)
            self.assertTrue(type(r1), type(r1b))

            if isinstance(r1, QgsRasterRenderer):
                self.assertIsInstance(r1b, QgsRasterRenderer)
            elif isinstance(r1, QgsFeatureRenderer):
                self.assertIsInstance(r1b, QgsFeatureRenderer)

            xml2 = rendererToXml(r1b)
            self.assertIsInstance(xml2, QDomDocument)
            self.assertTrue(xml1.toString() == xml2.toString())


            rClone = r1.clone()
            self.assertTrue(type(r1), type(rClone))
            xmlClone =  rendererToXml(rClone)
            self.assertIsInstance(xmlClone, QDomDocument)

            similar = compareXML(xml1.firstChild(), xml2.firstChild())
            self.assertTrue(similar)






        for path in styleFiles:
            with open(path, encoding='utf8') as f:
                xml = ''.join(f.readlines())


                renderer = rendererFromXml(xml)
                self.assertTrue(renderer != None)

        s  =""




    def test_spatialTemporalVisualization(self):
        from eotimeseriesviewer.main import TimeSeriesViewer

        TSV = TimeSeriesViewer()
        TSV.loadExampleTimeSeries()
        TSV.show()

        SV = TSV.spatialTemporalVis
        self.assertIsInstance(SV, SpatialTemporalVisualization)
        QApplication.processEvents()
        # TSV.createMapView()

        import time
        time.sleep(5)

        SV.timedCanvasRefresh()


        visibleCanvases = []
        withLayers = []
        empty = []
        extent = None
        for mapCanvas in SV.mapCanvases():
            self.assertIsInstance(mapCanvas, MapCanvas)
            self.assertIsInstance(mapCanvas.spatialExtent(), SpatialExtent)

            if extent is None:
                extent = mapCanvas.spatialExtent()
            else:
                self.assertTrue(mapCanvas.spatialExtent() == extent)

            if len(mapCanvas.layers()) == 0:
                empty.append(mapCanvas)
            else:
                withLayers.append(mapCanvas)

        if True:
            QGIS_APP.exec_()

        self.assertTrue(len(withLayers) > 0)
        self.assertTrue(len(empty) > 0)

        # shift spatial extent
        extent2 = extent.setCenter(SpatialPoint(extent.crs(), extent.center().x()-100, extent.center().y()))
        SV.setSpatialExtent(extent2)
        SV.timedCanvasRefresh()
        for mapCanvas in SV.mapCanvases():
            self.assertIsInstance(mapCanvas, MapCanvas)
            if mapCanvas.isVisibleToViewport():
                self.assertTrue(mapCanvas.spatialExtent() == extent2)


        # shift spatial extent of single map canvas
        extent3 = extent.setCenter(SpatialPoint(extent.crs(), extent.center().x() + 100, extent.center().y()))
        canvas = SV.mapCanvases()[0]
        self.assertIsInstance(canvas, MapCanvas)
        canvas.setSpatialExtent(extent3)
        SV.timedCanvasRefresh()
        for mapCanvas in SV.mapCanvases():
            if mapCanvas.isVisibleToViewport():
                self.assertTrue(mapCanvas.spatialExtent() == extent3)

        # test map render changes
        for canvas in SV.mapCanvases():
            self.assertIsInstance(canvas, MapCanvas)
            menu = canvas.contextMenu()
            self.assertIsInstance(menu, QMenu)
            if canvas.isVisibleToViewport():

                for action in menu.findChildren(QAction):
                    self.assertIsInstance(action, QAction)
                    text = action.text()
                    if text in ['', 'Style', 'PNG', 'JPEG']:
                        # skip menu / blocking dialog options
                        continue
                    else:
                        print('Test QAction "{}"'.format(action.text()))
                        action.trigger()
                break
        s = ""



if __name__ == "__main__":
    unittest.main()
    print('Done')

QGIS_APP.quit()
exit(0)