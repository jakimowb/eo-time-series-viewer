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

    def test_shortcuts(self):

        vl = self.createVectorLayer()

        fields = vl.fields()
        self.assertIsInstance(fields, QgsFields)

        for name in fields.names():
            field = fields.at(fields.lookupField(name))
            self.assertIsInstance(field, QgsField)

            possibleTypes = shortcuts(field)

            if re.search('string', field.typeName(), re.I):
                for t in list(LabelShortCutType):
                    self.assertTrue(t in possibleTypes)
            elif re.search('integer', field.typeName(), re.I):
                for t in [LabelShortCutType.Classification, LabelShortCutType.Off, LabelShortCutType.DOY]:
                    self.assertTrue(t in possibleTypes)
            elif re.search('real', field.typeName(), re.I):
                for t in [LabelShortCutType.Classification, LabelShortCutType.Off, LabelShortCutType.DOY]:
                    self.assertTrue(t in possibleTypes)
            else:
                self.fail('Unhandled QgsField typeName: {}'.format(field.typeName()))


    def test_LabelShortcutEditorConfigWidget(self):

        vl = self.createVectorLayer()

        self.assertIsInstance(vl, QgsVectorLayer)
        fields = vl.fields()
        i = fields.lookupField('class1l')
        field = fields.at(i)

        parent = QWidget()

        parent.setWindowTitle('TEST')
        parent.setLayout(QVBoxLayout())
        w = LabelShortcutEditorConfigWidget(vl, i, parent)
        self.assertIsInstance(w, LabelShortcutEditorConfigWidget)

        classScheme1 = ClassificationScheme.create(5)
        classScheme1.setName('Schema1')
        classScheme1 = ClassificationScheme.create(3)
        classScheme1.setName('Schema2')
        reg = QgsGui.editorWidgetRegistry()
        reg.initEditors()
        registerLabelShortcutEditorWidget()

        vl.setEditorWidgetSetup(vl.fields().lookupField('sensor'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {'labelType': LabelShortCutType.Sensor}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('date'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {'labelType': LabelShortCutType.Date}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('DOY'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {'labelType': LabelShortCutType.DOY}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('decyr'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {'labelType': LabelShortCutType.DecimalYear}))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class1l'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                    {'labelType': LabelShortCutType.Classification,
                                     'classificationScheme':classScheme1}))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class1n'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {'labelType': LabelShortCutType.Classification,
                                                      'classificationScheme': classScheme1}))

        for i in range(vl.fields().count()):
            setup = vl.editorWidgetSetup(i)
            self.assertIsInstance(setup, QgsEditorWidgetSetup)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                self.assertIsInstance(reg, QgsEditorWidgetRegistry)
                w2 = QWidget()

                confWidget = reg.createConfigWidget(EDITOR_WIDGET_REGISTRY_KEY, vl, i, parent)
                self.assertIsInstance(confWidget, QgsEditorConfigWidget)


                editorWidgetWrapper = reg.create(EDITOR_WIDGET_REGISTRY_KEY, vl, i, setup.config(), None, parent)
                self.assertIsInstance(editorWidgetWrapper, QgsEditorWidgetWrapper)



        canvas = QgsMapCanvas(parent)
        canvas.setVisible(False)

        dv = QgsDualView(parent)
        assert isinstance(dv, QgsDualView)
        dv.init(vl, canvas)  # , context=self.mAttributeEditorContext)
        dv.setView(QgsDualView.AttributeTable)


        panel = QgsMapLayerStyleManagerWidget(vl, canvas, parent)

        parent.layout().addWidget(w)
        parent.layout().addWidget(dv)
        parent.layout().addWidget(panel)

        parent.show()

        #randomly click into table cells
        vl.startEditing()

        size = dv.size()
        w = size.width()
        h = size.height()
        from random import randint
        for i in range(500):
            x = randint(0, w-1)
            y = randint(0, h-1)
            localPos = QPointF(x,y)
            event = QMouseEvent(QEvent.MouseButtonPress, localPos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            dv.mousePressEvent(event)
            s = ""

        vl.selectByIds([1, 2, 3])
        ts = TestObjects.createTimeSeries()
        tsd = ts[5]


        self.assertTrue(len(labelShortcutLayers()) == 0)
        QgsProject.instance().addMapLayer(vl)

        self.assertTrue(len(labelShortcutLayers()) == 1)
        for lyr in labelShortcutLayers():
            assert isinstance(lyr, QgsVectorLayer)
            applyShortcuts(lyr, tsd, [classScheme1[2], classScheme1[1]])

        if SHOW_GUI:
            dv.show()
            QGIS_APP.exec_()

        self.assertTrue(vl.commitChanges())
        pass


    def test_LabelingDock(self):

        dock = LabelingDock()
        self.assertIsInstance(dock, LabelingDock)
        lyr = self.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)


        from timeseriesviewer.classification.classificationscheme import registerClassificationSchemeEditorWidget
        from timeseriesviewer.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY
        registerClassificationSchemeEditorWidget()

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        am = lyr.actions()
        self.assertIsInstance(am, QgsActionManager)

        atc = lyr.attributeTableConfig()
        #set a ClassificationScheme to each class-specific column
        for name in lyr.fields().names():
            if name.startswith('class'):
                field = lyr.fields().lookupField(name)
                classScheme = {'foo':'bar'}
                lyr.setEditorWidgetSetup(field,
                                         QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, classScheme))

                setup = lyr.editorWidgetSetup(field)
                s = ""
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

        self.assertTrue(lyr.commitChanges())

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()
