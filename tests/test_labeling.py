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

from eotimeseriesviewer.tests import initQgisApplication, testRasterFiles
import unittest, tempfile

from eotimeseriesviewer.labeling import *
from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.tests import TestObjects
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True and os.environ.get('CI') is None

reg = QgsGui.editorWidgetRegistry()
if len(reg.factories()) == 0:
    reg.initEditors()

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

        model.setFieldShortCut('sensor', LabelShortcutType.Sensor)
        model.setFieldShortCut('date', LabelShortcutType.Date)
        model.setFieldShortCut('DOY', LabelShortcutType.DOY)
        model.setFieldShortCut('decyr', LabelShortcutType.Off)

        self.assertIsInstance(lyr, QgsVectorLayer)

        tsd = ts[10]
        #menu = model.menuForTSD(tsd)
        #self.assertIsInstance(menu, QMenu)

        canvas = MapCanvas()
        canvas.setTSD(tsd)
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
                for t in list(LabelShortcutType):
                    self.assertTrue(t in possibleTypes)
            elif re.search('integer', field.typeName(), re.I):
                for t in [LabelShortcutType.Classification, LabelShortcutType.Off, LabelShortcutType.DOY]:
                    self.assertTrue(t in possibleTypes)
            elif re.search('real', field.typeName(), re.I):
                for t in [LabelShortcutType.Classification, LabelShortcutType.Off, LabelShortcutType.DOY]:
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

        reg = QgsGui.editorWidgetRegistry()
        reg.initEditors()
        registerLabelShortcutEditorWidget()

        classScheme1, classScheme2 = self.setupEditWidget(vl)

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
        #    applyShortcuts(lyr, tsd, [classScheme1[2], classScheme1[1]])

        if SHOW_GUI:
            dv.show()
            QGIS_APP.exec_()

        self.assertTrue(vl.commitChanges())
        pass

    def setupEditWidget(self, vl):
        from eotimeseriesviewer import ClassificationScheme
        classScheme1 = ClassificationScheme.create(5)
        classScheme1.setName('Schema1')
        classScheme2 = ClassificationScheme.create(3)
        classScheme2.setName('Schema2')

        vl.setEditorWidgetSetup(vl.fields().lookupField('sensor'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.Sensor}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('date'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.Date}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('DOY'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.DOY}))
        vl.setEditorWidgetSetup(vl.fields().lookupField('decyr'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.DecimalYear}))

        vl = vl
        vl.setEditorWidgetSetup(vl.fields().lookupField('class1l'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.Classification,
                                                      CONFKEY_CLASSIFICATIONSCHEME: classScheme1}))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class1n'),
                                QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                     {CONFKEY_LABELTYPE: LabelShortcutType.Classification,
                                                      CONFKEY_CLASSIFICATIONSCHEME: classScheme1}))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class2l'),
                                 QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                      {CONFKEY_LABELTYPE: LabelShortcutType.Classification,
                                                       CONFKEY_CLASSIFICATIONSCHEME: classScheme2}))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class2n'),
                                 QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY,
                                                      {CONFKEY_LABELTYPE: LabelShortcutType.Classification,
                                                       CONFKEY_CLASSIFICATIONSCHEME: classScheme2}))
        return classScheme1, classScheme2

    def test_LabelingDockActions(self):
        registerLabelShortcutEditorWidget()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())

        dock = LabelingDock()
        dock.show()
        self.assertIsInstance(dock, LabelingDock)
        lyr = self.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        lw = dock.labelingWidget()
        self.assertTrue(lw.mVectorLayerComboBox.currentLayer() is None)

        lyr1 = self.createVectorLayer()
        lyr1.setName('in editing mode')
        lyr1.startEditing()
        lyr2 = self.createVectorLayer()
        lyr2.setName('not in editing mode')

        QgsProject.instance().addMapLayers([lyr1, lyr2])

        lw.setCurrentVectorSource(lyr2)

        canvas = QgsMapCanvas()
        canvas.show()


        def setLayers():
            canvas.mapSettings().setDestinationCrs(dock.canvas().mapSettings().destinationCrs())
            canvas.setExtent(dock.canvas().extent())
            canvas.setLayers(dock.canvas().layers())

        lw.sigVectorLayerChanged.connect(setLayers)
        lw.sigMapCenterRequested.connect(setLayers)
        lw.sigMapExtentRequested.connect(setLayers)

        if SHOW_GUI:
            QGIS_APP.exec_()


    def test_LabelingDock(self):

        registerLabelShortcutEditorWidget()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())

        dock = LabelingDock()
        dock.show()
        lw = dock.labelingWidget()

        self.assertIsInstance(dock, LabelingDock)
        self.assertIsInstance(lw, LabelingWidget)
        lyr = self.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lw.mVectorLayerComboBox.currentLayer() is None)

        QgsProject.instance().addMapLayer(lyr)

        am = lyr.actions()
        self.assertIsInstance(am, QgsActionManager)

        # set a ClassificationScheme to each class-specific column

        classScheme1, classScheme2 = self.setupEditWidget(lyr)




        fids = [1, 2, 3]
        lyr.selectByIds(fids)
        lyr.startEditing()
        ts = TestObjects.createTimeSeries()
        tsd = ts[7]
        classInfo1 = classScheme1[2]
        classInfo2 = classScheme2[1]

        classInfoDict = {classScheme1.name():classInfo1,
                         classScheme2.name():classInfo2}

        applyShortcuts(lyr, tsd, classInfos=classInfoDict)

        for fid in fids:
            feature = lyr.getFeature(fid)
            self.assertIsInstance(feature, QgsFeature)
            self.assertEqual(feature.attribute('date'), str(tsd.date()))
            self.assertEqual(feature.attribute('sensor'), tsd.sensor().name())
            self.assertEqual(feature.attribute('class1l'), classInfo1.label())
            self.assertEqual(feature.attribute('class1n'), classInfo1.name())
            self.assertEqual(feature.attribute('class2l'), classInfo2.label())
            self.assertEqual(feature.attribute('class2n'), classInfo2.name())

        self.assertIsInstance(lw.mVectorLayerComboBox, QgsMapLayerComboBox)
        lw.mVectorLayerComboBox.setCurrentIndex(1)
        self.assertTrue(lw.mVectorLayerComboBox.currentLayer() == lyr)

        self.assertTrue(lyr.commitChanges())


        if SHOW_GUI:
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()

QGIS_APP.quit()
