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

from timeseriesviewer.utils import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest
from timeseriesviewer.utils import *
from timeseriesviewer.mapcanvas import *
from timeseriesviewer.mapvisualization import *
from example.Images import Img_2014_05_07_LC82270652014127LGN00_BOA
QGIS_APP = initQgisApplication()

def getChildElements(node):
    assert isinstance(node, QDomNode)
    childs = node.childNodes()
    return [childs.at(i) for i in range(childs.count())]

def compareXML(element1, element2 ):

    assert isinstance(element1, QDomNode)
    assert isinstance(element2, QDomNode)

    tag1 = element1.nodeName()
    tag2 = element2.nodeName()
    if tag1 != tag2:
        return False

    elts1 = getChildElements(element1);
    elts2 = getChildElements(element2);

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


class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass


    def test_mapcanvas(self):
        m = MapCanvas()
        self.assertIsInstance(m, QgsMapCanvas)
        m.show()


    def test_renderer(self):

        styleFiles = file_search(os.path.dirname(__file__), 'style*.txt')




        lyr = QgsRasterLayer(Img_2014_05_07_LC82270652014127LGN00_BOA)

        r0 = lyr.renderer()
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


            rClone = cloneRenderer(r1)
            self.assertTrue(type(r1), type(rClone))
            xmlClone =  rendererToXml(rClone)
            self.assertIsInstance(xmlClone, QDomDocument)

            similar = compareXML(xml1.firstChild(), xml2.firstChild())
            self.assertTrue(similar)






        for path in styleFiles:
            f = open(path, encoding='utf8')
            xml = ''.join(f.readlines())
            f.close()

            renderer = rendererFromXml(xml)
            self.assertTrue(renderer != None)
            #self.assertTrue(isinstance(renderer, QgsRasterRenderer) or isinstance(renderer, QgsFeatureRenderer), msg='Unable to read style from {}'.format(path))


        s = ""

    def test_maprendersettings(self):
        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA

        from timeseriesviewer.timeseries import TimeSeries
        TS = TimeSeries()
        TS.addFiles([Img_2014_01_15_LC82270652014015LGN00_BOA])
        sensor1 = TS.sensors()[0]
        w = MapViewRenderSettingsV2(sensor1)
        w.show()


        lyr = QgsRasterLayer(Img_2014_01_15_LC82270652014015LGN00_BOA)
        doc = QDomDocument()
        err = ''
        lyr.exportNamedStyle(doc, err)
        xml0 = doc.toString()
        self.assertEqual(err, '')

        xml = rendererToXml(lyr.renderer())
        self.assertIsInstance(xml, QDomDocument)
        xml = xml.toString()
        self.assertEqual(xml0, xml)


        r0 = lyr.renderer()
        r = w.rasterRenderer()

        self.assertIsInstance(r, QgsMultiBandColorRenderer)

        r2 = QgsSingleBandGrayRenderer(r, 2)
        w.setRasterRenderer(r2)
        self.assertIsInstance(w.currentRenderWidget(), QgsSingleBandGrayRendererWidget)
        r2b = w.rasterRenderer()
        self.assertIsInstance(r2b, QgsSingleBandGrayRenderer)
        xml2, xml2b = rendererToXml(r2).toString(), rendererToXml(r2b).toString()
        #self.assertEqual(xml2, xml2b)

        r3 = QgsSingleBandPseudoColorRenderer(r,0)
        r3.setClassificationMin(0)
        r3.setClassificationMax(100)
        w.setRasterRenderer(r3)
        self.assertIsInstance(w.currentRenderWidget(), QgsSingleBandPseudoColorRendererWidget)
        r3b = w.rasterRenderer()
        self.assertIsInstance(r3b, QgsSingleBandPseudoColorRenderer)
        xml3, xml3b = rendererToXml(r3).toString(), rendererToXml(r3b).toString()
        #self.assertEqual(xml3, xml3b)
        s = ""






if __name__ == "__main__":
    unittest.main()
