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

from eotimeseriesviewer.tests import start_app, testRasterFiles
import unittest
import tempfile
import os
import qgis.testing
import xmlrunner

from eotimeseriesviewer.labeling import *
from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.tests import TestObjects, EOTSVTestCase
from eotimeseriesviewer.mapvisualization import MapView
from osgeo import ogr

class TestLabeling(EOTSVTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        print('## setUpClass')
        app = qgis.testing.start_app(cleanup=True)
        import eotimeseriesviewer.labeling
        print('## setUpClass - cleanup')
        for store in eotimeseriesviewer.MAP_LAYER_STORES:
            store.removeAllMapLayers()
        print('## setUpClass - done')

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
        print('## test_menu')
        ts = TestObjects.createTimeSeries()

        mv = MapView()

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
        canvas.setMapView(mv)
        pos = QPoint(int(canvas.width()*0.5), int(canvas.height()*0.5))
        menu = canvas.contextMenu(pos)
        self.assertIsInstance(menu, QMenu)

        def findLabelAction(menu)->QAction:
            for a in menu.actions():
                if a.text().startswith('Quick Labels'):
                    return a
        m = findLabelAction(menu).menu()

        self.showGui(menu)

    def test_shortcuts(self):
        print('## test_shortcuts')
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
                for t in [LabelShortcutType.Off, LabelShortcutType.DOY]:
                    self.assertTrue(t in possibleTypes)
            elif re.search('real', field.typeName(), re.I):
                for t in [LabelShortcutType.Off, LabelShortcutType.DOY]:
                    self.assertTrue(t in possibleTypes)
            else:
                self.fail('Unhandled QgsField typeName: {}'.format(field.typeName()))


    def test_LabelShortcutEditorConfigWidget(self):
        print('## test_LabelShortcutEditorConfigWidget')
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
        if len(reg.factories()) == 0:
            reg.initEditors()
        registerLabelShortcutEditorWidget()

        classScheme1, classScheme2 = self.setupEditWidgets(vl)

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



        #randomly click into table cells
        vl.startEditing()

        size = dv.size()
        w = size.width()
        h = size.height()
        from random import randint
        for i in range(5):
            print('Test mouse press {}'.format(i+1))
            x = randint(0, w-1)
            y = randint(0, h-1)
            localPos = QPointF(x, y)
            event = QMouseEvent(QEvent.MouseButtonPress, localPos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            dv.mousePressEvent(event)


        vl.selectByIds([1, 2, 3])
        ts = TestObjects.createTimeSeries()
        tsd = ts[5]

        if len(quickLabelLayers())> 0:
            print('Found QuickLabelLayers:')
            for l in quickLabelLayers():
                print('{}={}'.format(l.name(), l.source()))
        assert vl not in quickLabelLayers()
        n = len(quickLabelLayers())
        QgsProject.instance().addMapLayer(vl)

        self.assertTrue(len(quickLabelLayers()) == n + 1)
        for lyr in quickLabelLayers():
            assert isinstance(lyr, QgsVectorLayer)
        #    applyShortcuts(lyr, tsd, [classScheme1[2], classScheme1[1]])

        self.showGui([dv, parent])
        self.assertTrue(vl.commitChanges())
        pass

    def setupEditWidgets(self, vl):
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

        # set different types of classifications
        from eotimeseriesviewer.externals.qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
        from eotimeseriesviewer.externals.qps.classification.classificationscheme import classSchemeToConfig
        vl.setEditorWidgetSetup(vl.fields().lookupField('class1l'),
                                QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class1n'),
                                QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class2l'),
                                 QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

        vl.setEditorWidgetSetup(vl.fields().lookupField('class2n'),
                                 QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))


        return classScheme1, classScheme2

    def test_LabelingDockActions(self):
        print('## test_LabelingDockActions')
        registerLabelShortcutEditorWidget()
        reg = QgsGui.editorWidgetRegistry()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())

        dock = LabelingDock()

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


        def setLayers():
            canvas.mapSettings().setDestinationCrs(dock.canvas().mapSettings().destinationCrs())
            canvas.setExtent(dock.canvas().extent())
            canvas.setLayers(dock.canvas().layers())

        lw.sigVectorLayerChanged.connect(setLayers)
        lw.sigMapCenterRequested.connect(setLayers)
        lw.sigMapExtentRequested.connect(setLayers)

        self.showGui([dock, canvas])

    def test_canvasMenu(self):
        print('## test_canvasMenu')
        vl = self.createVectorLayer()
        c1, c2 = self.setupEditWidgets(vl)
        QgsProject.instance().addMapLayer(vl)

        self.assertIsInstance(vl, QgsVectorLayer)
        vl.startEditing()
        vl.selectByIds([0, 1, 2])
        ts = TestObjects.createTimeSeries()
        canvas = MapCanvas()
        canvas.setTSD(ts[0])

        self.showGui(canvas)

    def test_LabelingDock(self):
        print('## test_LabelingDock')
        registerLabelShortcutEditorWidget()
        reg = QgsGui.editorWidgetRegistry()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())

        dock = LabelingDock()

        lw = dock.labelingWidget()

        self.assertIsInstance(dock, LabelingDock)
        self.assertIsInstance(lw, LabelingWidget)
        lyr = self.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lw.currentVectorSource() is None)

        QgsProject.instance().addMapLayer(lyr)

        am = lyr.actions()
        self.assertIsInstance(am, QgsActionManager)

        # set a ClassificationScheme to each class-specific column

        classScheme1, classScheme2 = self.setupEditWidgets(lyr)




        fids = [1, 2, 3]
        lyr.selectByIds(fids)
        lyr.startEditing()
        ts = TestObjects.createTimeSeries()
        tsd = ts[7]
        classInfo1 = classScheme1[2]
        classInfo2 = classScheme2[1]



        setQuickTSDLabels(lyr, tsd, None)
        fields = lyr.fields()
        setQuickClassInfo(lyr, fields.lookupField('class1l'), classInfo1)
        setQuickClassInfo(lyr, fields.lookupField('class1n'), classInfo1)
        setQuickClassInfo(lyr, fields.lookupField('class2l'), classInfo2)
        setQuickClassInfo(lyr, fields.lookupField('class2n'), classInfo2)

        for fid in fids:
            feature = lyr.getFeature(fid)
            self.assertIsInstance(feature, QgsFeature)
            self.assertEqual(feature.attribute('date'), str(tsd.date()))
            self.assertEqual(feature.attribute('sensor'), tsd.sensor().name())
            self.assertEqual(feature.attribute('class1l'), classInfo1.label())
            self.assertEqual(feature.attribute('class1n'), classInfo1.name())
            self.assertEqual(feature.attribute('class2l'), classInfo2.label())
            self.assertEqual(feature.attribute('class2n'), classInfo2.name())

        lw.setCurrentVectorSource(lyr)
        self.assertTrue(lw.currentVectorSource() == lyr)

        self.assertTrue(lyr.commitChanges())

        self.showGui(dock)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
