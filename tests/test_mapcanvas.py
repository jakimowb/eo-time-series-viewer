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

from eotimeseriesviewer.mapcanvas import MapCanvas, MapCanvasInfoItem
from eotimeseriesviewer.qgispluginsupport.qps.maptools import SpectralProfileMapTool
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.tests import testRasterFiles, TestObjects, EOTSVTestCase, start_app
from qgis.PyQt.QtCore import QPoint
from qgis.PyQt.QtWidgets import QMenu
from qgis.core import QgsRasterLayer, QgsWkbTypes, QgsProject
from qgis.gui import QgsMapCanvas, QgsFontButton

start_app()


class TestMapCanvas(EOTSVTestCase):
    """Test resources work."""

    def test_basic_behaviour(self):

        files = TestObjects.testImagePaths()
        lyr1 = QgsRasterLayer(files[0])
        self.assertTrue(lyr1.isValid())
        QgsProject.instance().addMapLayer(lyr1)

        c = QgsMapCanvas()
        c.setWindowTitle('QgsMapCanvas test')
        self.assertIsInstance(c, QgsMapCanvas)

        bExtent = 0

        def onExtentChanged():
            nonlocal bExtent
            bExtent += 1

        c.extentsChanged.connect(onExtentChanged)
        c.setExtent(lyr1.extent())

        self.assertTrue(bExtent == 1)

        c.setLayers([lyr1])
        c.setDestinationCrs(lyr1.crs())
        c.setExtent(lyr1.extent())

        self.showGui(c)
        del c
        QgsProject.instance().removeAllMapLayers()

    def test_contextMenu(self):
        files = testRasterFiles()
        lyr1 = QgsRasterLayer(files[0])
        lyr2 = QgsRasterLayer(files[1])

        canvas = MapCanvas()
        canvas.setWindowTitle('timeseriesviewer.MapCanvas')
        canvas.setDestinationCrs(lyr1.crs())
        canvas.setExtent(lyr1.extent())

        pos = QPoint(int(canvas.width() * 0.5), int(canvas.height() * 0.5))
        menu = QMenu()
        canvas.populateContextMenu(menu, pos)
        self.assertIsInstance(menu, QMenu)
        self.showGui(menu)

        del canvas
        QgsProject.instance().removeAllMapLayers()

    def test_mapcanvasInfoItem(self):

        mc = MapCanvas()
        vl = TestObjects.createVectorLayer(QgsWkbTypes.Polygon)
        mc.setLayers([vl])
        mc.setDestinationCrs(vl.crs())
        mc.setExtent(mc.fullExtent())

        from eotimeseriesviewer.settings import Keys, defaultValues
        mc.mInfoItem.setTextFormat(defaultValues()[Keys.MapTextFormat])
        mc.mInfoItem.setUpperLeft('Upper\nLeft')
        if True:
            mc.mInfoItem.setMiddleLeft('Middle\nLeft')
            mc.mInfoItem.setLowerLeft('Lower\nLeft')

            mc.mInfoItem.setUpperCenter('Upper\nCenter')
            mc.mInfoItem.setMiddleCenter('Middle\nCenter')
            mc.mInfoItem.setLowerCenter('Lower\nCenter')

            mc.mInfoItem.setUpperRight('Upper\nRight')
            mc.mInfoItem.setMiddleRight('Middle\nRight')
            mc.mInfoItem.setLowerRight('Lower\nRight')

        if False:
            for k in mc.mInfoItem.mInfoText.keys():
                v = mc.mInfoItem.mInfoText[k]
                mc.mInfoItem.mInfoText[k] = v.replace('\n', ' ')

        item = mc.mInfoItem
        self.assertIsInstance(item, MapCanvasInfoItem)
        btn = QgsFontButton()
        btn.setMapCanvas(mc)
        btn.setTextFormat(item.textFormat())

        def onChanged():
            mc.mInfoItem.setTextFormat(btn.textFormat())
            mc.update()

        btn.changed.connect(onChanged)

        if False:
            w = QWidget()
            w.setLayout(QVBoxLayout())
            w.layout().addWidget(btn)
            w.layout().addWidget(mc)
            w.show()

        self.showGui([mc, btn])

        QgsProject.instance().removeAllMapLayers()

    def test_mapcanvas(self):
        files = testRasterFiles()
        lyr1 = QgsRasterLayer(files[0])
        lyr2 = QgsRasterLayer(files[1])

        canvas = MapCanvas()
        canvas.setWindowTitle('timeseriesviewer.MapCanvas')
        canvas.setDestinationCrs(lyr1.crs())
        canvas.setExtent(lyr1.extent())

        if False:
            self.assertIsInstance(canvas, QgsMapCanvas)
            self.assertFalse(canvas.checkState())
            self.assertFalse(canvas.isVisibleToViewport())

            self.assertTrue(canvas.checkState())
            self.assertTrue(canvas.isVisibleToViewport())

        canvas.setExtent(canvas.fullExtent())

        self.showGui([canvas])

    def test_mapTools(self):

        m = MapCanvas()

        lastPos = None

        def onChanged(position: SpatialPoint):
            nonlocal lastPos
            lastPos = position

        m.sigCrosshairPositionChanged.connect(onChanged)

        center = SpatialPoint.fromMapCanvasCenter(m)
        m.setCrosshairVisibility(True)
        mt = SpectralProfileMapTool(m)
        m.setMapTool(mt)
        self.assertTrue(m.crosshairPosition() == center)

        p2 = SpatialPoint(center.crs(), center)
        p2.setX(p2.x() + 100)
        m.setCrosshairPosition(p2)
        self.assertIsInstance(lastPos, SpatialPoint)
        self.assertTrue(lastPos == p2)


if __name__ == "__main__":
    unittest.main(buffer=False)
