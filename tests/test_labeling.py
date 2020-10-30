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

import unittest
import re
import xmlrunner

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from qgis.core import QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsProject, \
    QgsFields
from qgis.gui import QgsDualView, QgsEditorConfigWidget, QgsMapLayerStyleManagerWidget, \
    QgsMapCanvas, QgsGui, QgsEditorWidgetRegistry, QgsEditorWidgetWrapper

from eotimeseriesviewer.docks import LabelDockWidget, SpectralLibraryDockWidget
from eotimeseriesviewer.labeling import LabelWidget, LabelConfigurationKey, LabelAttributeTableModel, shortcuts, \
    LabelShortcutEditorConfigWidget, quickLayerFieldSetup, quickLabelLayers, EDITOR_WIDGET_REGISTRY_KEY, \
    LabelShortcutType, LabelConfigurationKey, registerLabelShortcutEditorWidget, Option, OptionListModel, \
    LabelShortcutEditorWidgetWrapper, LabelShortcutWidgetFactory, createWidgetSetup, createWidgetConf
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapView
from eotimeseriesviewer.tests import TestObjects, EOTSVTestCase
import eotimeseriesviewer

class TestLabeling(EOTSVTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        print('## setUpClass')
        # app = qgis.testing.start_app(cleanup=True)

        print('## setUpClass - cleanup')
        for store in eotimeseriesviewer.MAP_LAYER_STORES:
            store.removeAllMapLayers()
        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()
        registerLabelShortcutEditorWidget()
        print('## setUpClass - done')

    def createVectorLayer(self) -> QgsVectorLayer:

        lyr = TestObjects.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.featureCount() > 0)
        lyr.startEditing()
        lyr.addAttribute(QgsField('sensor', QVariant.String, 'varchar'))
        lyr.addAttribute(QgsField('date', QVariant.Date, 'date'))
        lyr.addAttribute(QgsField('dateGrp1', QVariant.Date, 'date'))
        lyr.addAttribute(QgsField('dateGrp2', QVariant.Date, 'date'))
        lyr.addAttribute(QgsField('datetime', QVariant.DateTime, 'datetime'))
        lyr.addAttribute(QgsField('time', QVariant.Time, 'time'))
        lyr.addAttribute(QgsField('DOY', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('decyr', QVariant.Double, 'double'))
        lyr.addAttribute(QgsField('class1l', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('class1n', QVariant.String, 'varchar'))
        lyr.addAttribute(QgsField('class2l', QVariant.Int, 'int'))
        lyr.addAttribute(QgsField('class2n', QVariant.String, 'varchar'))
        assert lyr.commitChanges()
        names = lyr.fields().names()

        return lyr

    def test_optionModelCBox(self):
        m = QStandardItemModel()
        m.appendRow(QStandardItem('AA'))
        m.appendRow(QStandardItem('BB'))
        #m.addOptions(['AA', 'BB'])
        w = QWidget()
        cb = QComboBox()
        cb.setInsertPolicy(QComboBox.InsertAtTop)
        cb.setEditable(True)
        cb.setModel(m)
        w.setLayout(QVBoxLayout())
        w.layout().addWidget(QLabel('add values'))
        w.layout().addWidget(cb)

        self.showGui(w)

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
        # menu = model.menuForTSD(tsd)
        # self.assertIsInstance(menu, QMenu)

        canvas = MapCanvas()
        canvas.setTSD(tsd)
        canvas.setMapView(mv)
        pos = QPoint(int(canvas.width() * 0.5), int(canvas.height() * 0.5))
        menu = canvas.contextMenu(pos)
        self.assertIsInstance(menu, QMenu)

        def findLabelAction(menu) -> QAction:
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

    def test_LabelShortcutEditorConfigWidget(self):
        print('## test_LabelShortcutEditorConfigWidget')
        QgsProject.instance().clear()

        vl = self.createVectorLayer()
        vl.setName('TEST_LAYER_LABELING')
        self.setupEditWidgets(vl)

        self.assertIsInstance(vl, QgsVectorLayer)
        fields = vl.fields()
        i = fields.lookupField('class1l')
        field = fields.at(i)

        dirXML = self.createTestOutputDirectory()
        pathXML = dirXML / 'test.qgs'
        QgsProject.instance().addMapLayer(vl)
        QgsProject.instance().write(pathXML.as_posix())
        QgsProject.instance().clear()
        vl = None
        self.assertTrue(QgsProject.instance().read(pathXML.as_posix()))
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == 'TEST_LAYER_LABELING':
                vl = lyr
                break
        self.assertIsInstance(vl, QgsVectorLayer)
        self.assertTrue(vl in quickLabelLayers())

        s = ""
        factory: LabelShortcutWidgetFactory = LabelShortcutWidgetFactory.instance()
        self.assertIsInstance(factory, LabelShortcutWidgetFactory)

        parent = QWidget()

        parent.setWindowTitle('TEST')
        parent.setLayout(QVBoxLayout())
        model = OptionListModel()
        model.insertOptions(['Group1', 'Group2'])
        w = factory.configWidget(vl, i, parent)
        self.assertIsInstance(w, LabelShortcutEditorConfigWidget)
        w.setLayerGroupModel(model)
        parent.layout().addWidget(w)




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

        # randomly click into table cells
        vl.startEditing()

        size = dv.size()
        w = size.width()
        h = size.height()
        from random import randint
        for i in range(5):
            print('Test mouse press {}'.format(i + 1))
            x = randint(0, w - 1)
            y = randint(0, h - 1)
            localPos = QPointF(x, y)
            event = QMouseEvent(QEvent.MouseButtonPress, localPos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            dv.mousePressEvent(event)

        vl.selectByIds([1, 2, 3])
        ts = TestObjects.createTimeSeries()
        tsd = ts[5]

        if len(quickLabelLayers()) > 0:
            print('Found QuickLabelLayers:')
            for l in quickLabelLayers():
                print('{}={}'.format(l.name(), l.source()))


        self.showGui([dv, parent])
        self.assertTrue(vl.commitChanges())
        pass

    def setupEditWidgets(self, vl):
        from eotimeseriesviewer import ClassificationScheme
        classScheme1 = ClassificationScheme.create(5)
        classScheme1.setName('Schema1')
        classScheme2 = ClassificationScheme.create(3)
        classScheme2.setName('Schema2')

        vl.setEditorWidgetSetup(vl.fields().lookupField('sensor'), createWidgetSetup(LabelShortcutType.Sensor))
        vl.setEditorWidgetSetup(vl.fields().lookupField('date'), createWidgetSetup(LabelShortcutType.Date))

        vl.setEditorWidgetSetup(vl.fields().lookupField('dateGrp1'), createWidgetSetup(LabelShortcutType.Date, 'Group1'))
        vl.setEditorWidgetSetup(vl.fields().lookupField('dateGrp2'), createWidgetSetup(LabelShortcutType.Date, 'Group2'))

        vl.setEditorWidgetSetup(vl.fields().lookupField('datetime'), createWidgetSetup(LabelShortcutType.DateTime))

        vl.setEditorWidgetSetup(vl.fields().lookupField('time'), createWidgetSetup(LabelShortcutType.Time))

        vl.setEditorWidgetSetup(vl.fields().lookupField('DOY'), createWidgetSetup(LabelShortcutType.DOY))

        vl.setEditorWidgetSetup(vl.fields().lookupField('decyr'), createWidgetSetup(LabelShortcutType.DecimalYear))

        # set different types of classifications
        from eotimeseriesviewer.externals.qps.classification.classificationscheme import \
            EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
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
        size = canvas.size()
        pointCenter = QPointF(0.5 * size.width(), 0.5 * size.height())
        event = QMouseEvent(QEvent.MouseButtonPress, pointCenter, Qt.RightButton, Qt.RightButton, Qt.NoModifier)
        canvas.mousePressEvent(event)
        self.showGui(canvas)

    def test_LabelShortCutType(self):

        t = LabelShortcutType.Off

        self.assertIsInstance(t, LabelShortcutType)
        self.assertEqual(t.name, LabelShortcutType.Off.confValue())

        t = LabelShortcutType.Sensor
        self.assertEqual(t.value, LabelShortcutType.Sensor.value)
        self.assertEqual(t.value, LabelShortcutType(LabelShortcutType.Sensor).value)
        for t in LabelShortcutType:
            self.assertIsInstance(t, LabelShortcutType)
            self.assertEqual(t, t.fromConfValue(t.confValue()))

    def test_LabelingWidget2(self):
        lyr = TestObjects.createVectorLayer()
        lyr.setName('My Name')
        w = LabelWidget(lyr)
        lyr.setName('Changed Name')
        self.showGui(w)

    def test_addLabelDock(self):

        lyr = self.createVectorLayer()
        QgsProject.instance().addMapLayer(lyr)
        self.setupEditWidgets(lyr)
        EOTSV = EOTimeSeriesViewer()
        EOTSV.loadExampleTimeSeries(10, loadAsync=False)
        EOTSV.showAttributeTable(lyr)
        EOTSV.mapViews()[0].addLayer(lyr)
        EOTSV.onShowLayerProperties(lyr)

        self.assertEqual(1, len(EOTSV.ui.findChildren(LabelDockWidget)))

        dockWidgets = EOTSV.ui.findChildren(LabelDockWidget)
        self.assertEqual(1, len(dockWidgets))
        lyr.setName('Layer B')
        self.assertTrue('Layer B' in dockWidgets[0].windowTitle())

        self.showGui(EOTSV.ui)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
