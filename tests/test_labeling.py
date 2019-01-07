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
import os, sys, re
from timeseriesviewer.tests import initQgisApplication, testRasterFiles
import unittest, tempfile

from timeseriesviewer.labeling import *
from timeseriesviewer import DIR_REPO
from timeseriesviewer.mapcanvas import MapCanvas
from timeseriesviewer.tests import TestObjects
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True

class testclassLabelingTest(unittest.TestCase):

    def createVectorLayer(self)->QgsVectorLayer:


        lyr = TestObjects.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.featureCount() > 0)
        lyr.startEditing()
        lyr.addAttribute(QgsField('sensor', QVariant.String, 'varchar'))
        lyr.addAttribute(QgsField('date', QVariant.String, 'varchar'))
        lyr.addAttribute(QgsField('DOY', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('decyr', QVariant.Double, 'double'))
        lyr.addAttribute(QgsField('class1l', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('class1n', QVariant.String, 'varchar'))
        lyr.addAttribute(QgsField('class2l', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('class2n', QVariant.String, 'varchar'))
        assert lyr.commitChanges()
        names = lyr.fields().names()
        QgsProject.instance().addMapLayer(lyr)
        return lyr


    def test_menu(self):

        ts = TestObjects.createTimeSeries()

        lyr = self.createVectorLayer()
        model = LabelAttributeTableModel()
        model.setVectorLayer(lyr)

        model.setFieldShortCut('sensor', LabelShortCutType.Sensor)
        model.setFieldShortCut('date', LabelShortCutType.Date)
        model.setFieldShortCut('DOY', LabelShortCutType.DOY)
        model.setFieldShortCut('decyr', LabelShortCutType.Off)

        self.assertIsInstance(lyr, QgsVectorLayer)

        tsd = ts[10]
        #menu = model.menuForTSD(tsd)
        #self.assertIsInstance(menu, QMenu)

        canvas = MapCanvas()
        canvas.setTSD(tsd)
        canvas.setLabelingModel(model)
        menu = canvas.contextMenu()
        self.assertIsInstance(menu, QMenu)

        def findLabelAction(menu)->QAction:
            for a in menu.actions():
                if a.text().startswith('Label '):
                    return a
        m = findLabelAction(menu).menu()
        for a in m.actions():
            self.assertTrue(a.isEnabled() == False)
        lyr.selectByIds([1, 2, 3, 4, 5])
        menu = canvas.contextMenu()
        m = findLabelAction(menu).menu()
        for a in m.actions():
            self.assertTrue(a.isEnabled() == True)
            if a.text().startswith('Shortcuts'):
                a.trigger()

        for feature in lyr:
            assert isinstance(feature, QgsFeature)


        if SHOW_GUI:
            menu.exec_()



    def test_LabelingDock(self):

        dock = LabelingDock()
        self.assertIsInstance(dock, LabelingDock)
        lyr = self.createVectorLayer()

        self.assertIsInstance(dock.mVectorLayerComboBox, QgsMapLayerComboBox)
        dock.mVectorLayerComboBox.setCurrentIndex(1)
        self.assertTrue(dock.mVectorLayerComboBox.currentLayer() == lyr)

        model = dock.mLabelAttributeModel
        self.assertIsInstance(model, LabelAttributeTableModel)
        self.assertTrue(model.mVectorLayer == lyr)
        self.assertTrue(lyr.fields().count() == model.rowCount())

        dock.setFieldShortCut('sensor', LabelShortCutType.Sensor)
        dock.setFieldShortCut('date', LabelShortCutType.Date)
        dock.setFieldShortCut('DOY', LabelShortCutType.DOY)
        dock.setFieldShortCut('decyr', LabelShortCutType.Off)
        dock.setFieldShortCut('class1l', LabelShortCutType.Off)
        dock.setFieldShortCut('class1n', LabelShortCutType.Off)
        dock.setFieldShortCut('class2l', LabelShortCutType.Off)
        dock.setFieldShortCut('class2n', LabelShortCutType.Off)

        for name in lyr.fields().names():
            options = model.shortcuts(name)
            self.assertIsInstance(options, list)
            self.assertTrue(len(options) > 0)

        m = dock.mLabelAttributeModel
        self.assertIsInstance(m, LabelAttributeTableModel)
        self.assertTrue(m.data(m.createIndex(3, 0), Qt.DisplayRole) == 'sensor')

        v = m.data(m.createIndex(3, 0), Qt.UserRole)
        self.assertIsInstance(v, LabelShortCutType)
        self.assertTrue(v == LabelShortCutType.Sensor)


        lyr.selectByIds([1,2,3])
        lyr.startEditing()
        ts = TestObjects.createTimeSeries()
        tsd = ts[5]
        m.applyOnSelectedFeatures(tsd)

        if SHOW_GUI:
            dock.show()
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()
