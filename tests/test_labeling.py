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
import json
import random
import re
import unittest

from qgis.core import edit, QgsEditorWidgetSetup, QgsExpression, QgsExpressionContext, QgsExpressionContextScope, \
    QgsFeature, QgsField, QgsFields, QgsGeometry, QgsMapLayer, QgsMarkerSymbol, QgsPointXY, QgsProject, QgsVectorLayer, \
    QgsWkbTypes
from qgis.PyQt.QtCore import NULL, QEvent, QMetaType, QPoint, QPointF, Qt
from qgis.PyQt.QtTest import QAbstractItemModelTester
from qgis.PyQt.QtWidgets import QAction, QComboBox, QLabel, QListView, QMenu, QVBoxLayout, QWidget
from qgis.gui import QgsDualView, QgsFieldComboBox, QgsMapCanvas, QgsMapLayerStyleManagerWidget
from qgis.PyQt.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
from eotimeseriesviewer.labeling.editorconfig import createWidgetSetup, LabelConfigurationKey, \
    LabelShortcutEditorConfigWidget, LabelShortcutType, LabelShortcutTypeModel, \
    LabelShortcutWidgetFactory, shortcuts
from eotimeseriesviewer.labeling.quicklabeling import addQuickLabelMenu, isQuickLabelField, isQuickLabelLayer, \
    quickLabelClassSchemes, quickLabelExpression, quickLabelExpressionContextScope, quickLabelLayers, setQuickClassInfo
from eotimeseriesviewer.labeling.attributetable import QuickLabelAttributeTableWidget
from eotimeseriesviewer import initAll
from eotimeseriesviewer.qgispluginsupport.qps.fieldvalueconverter import GenericPropertyTransformer
from eotimeseriesviewer.qgispluginsupport.qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, \
    QMETATYPE_QDATE, \
    QMETATYPE_QDATETIME, \
    QMETATYPE_QSTRING, \
    QMETATYPE_QTIME
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects
from eotimeseriesviewer.timeseries.source import TimeSeriesDate
from eotimeseriesviewer.docks import LabelDockWidget
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.mapcanvas import MapCanvas
from eotimeseriesviewer.mapvisualization import MapView
from eotimeseriesviewer.qgispluginsupport.qps.classification.classificationscheme import ClassificationScheme, \
    ClassInfo, classSchemeToConfig, EDITOR_WIDGET_REGISTRY_KEY as CS_KEY

start_app()
initAll()


class TestLabeling(EOTSVTestCase):

    def createVectorLayer(self, path=None) -> QgsVectorLayer:

        lyr = TestObjects.createVectorLayer(path=path, n_features=5)
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.featureCount() > 0)
        lyr.startEditing()
        lyr.addAttribute(QgsField('sensor', QMETATYPE_QSTRING, 'varchar'))
        lyr.addAttribute(QgsField('date', QMETATYPE_QDATE, 'date'))
        lyr.addAttribute(QgsField('dateGrp1', QMETATYPE_QDATE, 'date'))
        lyr.addAttribute(QgsField('dateGrp2', QMETATYPE_QDATE, 'date'))
        lyr.addAttribute(QgsField('datetime', QMETATYPE_QDATETIME, 'datetime'))
        lyr.addAttribute(QgsField('time', QMETATYPE_QTIME, 'time'))
        lyr.addAttribute(QgsField('DOY', QMETATYPE_INT, 'int'))
        lyr.addAttribute(QgsField('decyr', QMETATYPE_DOUBLE, 'double'))
        lyr.addAttribute(QgsField('class1l', QMETATYPE_INT, 'int'))
        lyr.addAttribute(QgsField('class1n', QMETATYPE_QSTRING, 'varchar'))
        lyr.addAttribute(QgsField('class2l', QMETATYPE_INT, 'int'))
        lyr.addAttribute(QgsField('class2n', QMETATYPE_QSTRING, 'varchar'))
        assert lyr.commitChanges()
        names = lyr.fields().names()

        return lyr

    def test_optionModelCBox(self):
        m = QStandardItemModel()
        m.appendRow(QStandardItem('AA'))
        m.appendRow(QStandardItem('BB'))
        # m.addOptions(['AA', 'BB'])
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

        ts = TestObjects.createTimeSeries()
        tss = list(ts.sources())[0]

        menu = QMenu('Main Menu')
        a = menu.addAction('Foobar')

        vl = self.createVectorLayer()
        fid = vl.allFeatureIds()[0]
        vl.selectByIds([fid])
        self.setupEditWidgets(vl)

        ql = addQuickLabelMenu(menu, [vl], tss)
        # menu.insertMenu(menu.actions()[0], ql)

        # self.showGui(menu)
        for a in menu.findChildren(QAction):
            a: QAction
            a.trigger()

        self.assertTrue(vl.isEditable())

        f: QgsFeature = vl.getFeature(fid)

        attr = f.attributeMap()
        for k, v in attr.items():
            self.assertTrue(v != NULL, msg=f'{k} = NULL')

        self.showGui(menu)

    def test_menu2(self):
        print('## test_menu')
        ts = TestObjects.createTimeSeries()

        mv = MapView()

        lyr = self.createVectorLayer()
        self.setupEditWidgets(lyr)

        lyr.selectByIds([lyr.allFeatureIds()[0]])

        tsd = ts[10]
        # menu = model.menuForTSD(tsd)
        # self.assertIsInstance(menu, QMenu)

        canvas = MapCanvas()

        canvas.setTSD(tsd)
        canvas.setLayers([lyr])
        canvas.setMapView(mv)
        pos = QPoint(int(canvas.width() * 0.5), int(canvas.height() * 0.5))
        menu = QMenu()
        canvas.populateContextMenu(menu, pos)

        def findLabelAction(menu) -> QAction:
            for a in menu.actions():
                if a.text().startswith('Quick Labels'):
                    return a

        m = findLabelAction(menu).menu()

        self.showGui(menu)

        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking UI')
    def test_shortcuts_eotsv(self):

        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)

        vl = TestObjects.createEmptyMemoryLayer(QgsFields(), wkbType=QgsWkbTypes.Point)
        vl.setName('My Labeling Layer')
        cs = ClassificationScheme()
        cs.insertClass(ClassInfo(label=1, name='classA', color='green'))
        cs.insertClass(ClassInfo(label=2, name='classB', color='blue'))
        cs.insertClass(ClassInfo(label=3, name='classC', color='orange'))

        with edit(vl):
            # setup different classification schemes
            # EOTSV QuickLayer Classification Scheme
            field = QgsField('my_class', QMetaType.QString)
            setup = createWidgetSetup(labelType=LabelShortcutType.Classification, classification=cs)
            field.setEditorWidgetSetup(setup)
            vl.addAttribute(field)
            vl.addAttribute(field)

            field = QgsField('my_date', QMetaType.QString, 'varchar')
            field.setEditorWidgetSetup(createWidgetSetup(LabelShortcutType.Date))
            vl.addAttribute(field)

            field = QgsField('my_datetime', QMetaType.QString, 'varchar')
            field.setEditorWidgetSetup(createWidgetSetup(LabelShortcutType.DateTime, group='grp2'))
            vl.addAttribute(field)

            # add 3 random features
            extent = eotsv.timeSeries()[0].spatialExtent().toCrs(vl.crs())

            for _ in range(3):
                x = random.uniform(extent.xMinimum(), extent.xMaximum())
                y = random.uniform(extent.yMinimum(), extent.yMaximum())

                point = QgsPointXY(x, y)
                geometry = QgsGeometry.fromPointXY(point)

                feature = QgsFeature(vl.fields())
                feature.setGeometry(geometry)
                assert vl.addFeature(feature)

        eotsv.addMapLayers([vl])
        eotsv.showAttributeTable(vl)
        assert vl.featureCount() > 0

        vl.selectByIds([vl.allFeatureIds()[0]])
        self.showGui(eotsv.ui)

        eotsv.close()

    def test_shortcuts(self):
        print('## test_shortcuts')
        vl = self.createVectorLayer()

        fields = vl.fields()
        self.assertIsInstance(fields, QgsFields)

        for name in fields.names():
            field = fields.at(fields.lookupField(name))
            self.assertIsInstance(field, QgsField)

            possibleTypes = shortcuts(field)
            self.assertIsInstance(possibleTypes, LabelShortcutType)

            if re.search('string', field.typeName(), re.I):
                assert LabelShortcutType.SourceImage in possibleTypes

            elif re.search('integer', field.typeName(), re.I):
                assert LabelShortcutType.DOY in possibleTypes

            elif re.search('real', field.typeName(), re.I):
                assert LabelShortcutType.DecimalYear in possibleTypes

        QgsProject.instance().removeAllMapLayers()

    def test_LabelShortcutEditorConfigWidget2(self):
        test_dir = self.createTestOutputDirectory()
        path = test_dir / 'layer_example.gpkg'
        vl = self.createVectorLayer(path=path)
        self.setupEditWidgets(vl)
        self.assertTrue(isQuickLabelLayer(vl))

        w = QWidget()
        w.setWindowTitle('LabelShortcutEditorTester')
        layout = QVBoxLayout()
        w.setLayout(layout)
        cb = QgsFieldComboBox()
        cb.setLayer(vl)
        layout.addWidget(cb)

        def onFieldChanged(name: str):
            i = cb.currentIndex()
            cw = LabelShortcutEditorConfigWidget(vl, i, w)
            # delete old widgets
            for j in reversed(range(layout.count())):
                _w = layout.itemAt(j).widget()
                if isinstance(_w, LabelShortcutEditorConfigWidget):
                    layout.removeWidget(_w)
                    _w.setParent(None)
            layout.addWidget(cw)

        cb.fieldChanged.connect(onFieldChanged)

        self.showGui(w)

    def test_LabelShortcutEditorConfigWidget3(self):

        vl = TestObjects.createVectorLayer()
        with edit(vl):
            vl.addAttribute(QgsField('mytext', QMetaType.QString))
            vl.addAttribute(QgsField('myint', QMetaType.Int))
            vl.addAttribute(QgsField('myfloat', QMetaType.Float))

        fields = vl.fields()
        i = fields.lookupField('mytext')
        cw = LabelShortcutEditorConfigWidget(vl, i, None)
        cw.setShortcutType(LabelShortcutType.Classification)

        if True:
            for i, labelType in enumerate(LabelShortcutType):
                # print(f'Test {i + 1} {labelType}')
                conf1 = {LabelConfigurationKey.LabelGroup: f'group_{i}',
                         LabelConfigurationKey.LabelType: labelType.name}

                cw.setConfig(conf1)
                conf2 = cw.config()
                dump = json.dumps(conf2)
                self.assertEqual(cw.shortcutType(), labelType)
                self.assertEqual(conf1, conf2)

        # set classification
        if True:
            cs = ClassificationScheme()
            cs.insertClass(ClassInfo(name='MyClass1', color='green'))
            cs.insertClass(ClassInfo(name='MyClass2', color='brown'))

            conf1 = {
                LabelConfigurationKey.LabelGroup: 'g2',
                LabelConfigurationKey.LabelType: LabelShortcutType.Classification.name,
                LabelConfigurationKey.LabelClassification: cs.asMap()
            }

            cw.setConfig(conf1)
            conf2 = cw.config()
            self.assertIsInstance(json.dumps(conf2), str)
            self.assertEqual(conf1, conf2)

        # set custom expression
        if True:
            conf1 = {
                LabelConfigurationKey.LabelType: LabelShortcutType.Customized.name,
                LabelConfigurationKey.LabelExpression: "foobar",
                LabelConfigurationKey.LabelGroup: 'g3',
            }
            cw.setConfig(conf1)
            conf2 = cw.config()
            self.assertIsInstance(json.dumps(conf2), str)
            self.assertEqual(conf1, conf2)

        self.showGui(cw)

    def test_LabelShortcutEditorConfigWidget(self):
        print('## test_LabelShortcutEditorConfigWidget')

        test_dir = self.createTestOutputDirectory()
        path = test_dir / 'layer_example.gpkg'
        vl = self.createVectorLayer(path=path)
        vl.setName('TEST_LAYER_LABELING')
        self.setupEditWidgets(vl)
        self.assertTrue(isQuickLabelLayer(vl))

        fields = vl.fields()
        i = fields.lookupField('class1l')
        field = fields.at(i)

        dirXML = self.createTestOutputDirectory()
        pathXML = dirXML / 'test.qgs'
        QgsProject.instance().addMapLayer(vl)
        QgsProject.instance().write(pathXML.as_posix())
        self.taskManagerProcessEvents()
        QgsProject.instance().removeAllMapLayers()
        vl = None
        self.assertTrue(QgsProject.instance().read(pathXML.as_posix()))
        self.taskManagerProcessEvents()
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == 'TEST_LAYER_LABELING':
                vl = lyr
                break
        self.assertIsInstance(vl, QgsVectorLayer)
        self.assertTrue(isQuickLabelLayer(vl))

        if vl not in quickLabelLayers():
            print(f'QuickLabelLayers: {len(quickLabelLayers())}')
            for l in quickLabelLayers():
                print(f'\t{l}')
            print(f'Project layers: {len(QgsProject.instance().mapLayers())}')
            for l in QgsProject.instance().mapLayers().values():
                if isinstance(l, QgsVectorLayer):
                    print(f'-> {l}')
                    for f in l.fields():
                        print(f'=> {f.name()}: {f.editorWidgetSetup().type()}, {isQuickLabelLayer(l)}, {vl == l}')

            print(f'Missed: {vl}')

        self.assertTrue(vl in quickLabelLayers())

        s = ""
        factory: LabelShortcutWidgetFactory = LabelShortcutWidgetFactory.instance()
        self.assertIsInstance(factory, LabelShortcutWidgetFactory)

        parent = QWidget()

        parent.setWindowTitle('TEST')
        parent.setLayout(QVBoxLayout())
        w = factory.configWidget(vl, i, parent)
        self.assertIsInstance(w, LabelShortcutEditorConfigWidget)

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
        QgsProject.instance().removeAllMapLayers()

    def setupEditWidgets(self, vl):
        classScheme1 = ClassificationScheme.create(5)
        classScheme1.setName('Schema1')
        classScheme2 = ClassificationScheme.create(3)
        classScheme2.setName('Schema2')

        with edit(vl):
            vl.setEditorWidgetSetup(vl.fields().lookupField('sensor'), createWidgetSetup(LabelShortcutType.Sensor))
            vl.setEditorWidgetSetup(vl.fields().lookupField('date'), createWidgetSetup(LabelShortcutType.Date))

            vl.setEditorWidgetSetup(vl.fields().lookupField('dateGrp1'),
                                    createWidgetSetup(LabelShortcutType.Date, 'Group1'))
            vl.setEditorWidgetSetup(vl.fields().lookupField('dateGrp2'),
                                    createWidgetSetup(LabelShortcutType.Date, 'Group2'))

            vl.setEditorWidgetSetup(vl.fields().lookupField('datetime'), createWidgetSetup(LabelShortcutType.DateTime))

            vl.setEditorWidgetSetup(vl.fields().lookupField('time'), createWidgetSetup(LabelShortcutType.Time))

            vl.setEditorWidgetSetup(vl.fields().lookupField('DOY'), createWidgetSetup(LabelShortcutType.DOY))

            vl.setEditorWidgetSetup(vl.fields().lookupField('decyr'), createWidgetSetup(LabelShortcutType.DecimalYear))

            # set different types of classifications
            vl.setEditorWidgetSetup(vl.fields().lookupField('class1l'),
                                    QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

            vl.setEditorWidgetSetup(vl.fields().lookupField('class1n'),
                                    QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

            vl.setEditorWidgetSetup(vl.fields().lookupField('class2l'),
                                    QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

            vl.setEditorWidgetSetup(vl.fields().lookupField('class2n'),
                                    QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(classScheme1)))

        self.assertTrue(vl.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories))
        self.assertTrue(isQuickLabelLayer(vl))
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
        QgsProject.instance().removeAllMapLayers()

    def test_label_shortcut_type_model(self):

        field = QgsField('myint', QMetaType.Int)
        model = LabelShortcutTypeModel(field)

        tester = QAbstractItemModelTester(model)

        if False:
            view = QListView()
            view.setModel(model)
            self.showGui(view)

        cb = QComboBox()
        cb.setModel(model)

        def onIndexChanged(index):
            ts = cb.currentData(Qt.UserRole)
            assert isinstance(ts, LabelShortcutType)
            print(f'Selected {ts}')

        cb.currentIndexChanged.connect(onIndexChanged)
        self.showGui(cb)

    def test_LabelingWidget2(self):
        lyr = TestObjects.createVectorLayer()
        lyr.setName('My Name')
        w = QuickLabelAttributeTableWidget(lyr)
        lyr.setName('Changed Name')
        self.showGui(w)

    def test_addLabelDock(self):

        lyr = self.createVectorLayer()
        QgsProject.instance().addMapLayer(lyr)
        self.setupEditWidgets(lyr)
        EOTSV = EOTimeSeriesViewer()
        EOTSV.mapWidget().setMapsPerMapView(5, 2)
        EOTSV.loadExampleTimeSeries(loadAsync=False)
        attrTable = EOTSV.showAttributeTable(lyr)
        EOTSV.mapViews()[0].addLayer(lyr)

        self.assertEqual(1, len(EOTSV.ui.findChildren(LabelDockWidget)))

        dockWidgets = EOTSV.ui.findChildren(LabelDockWidget)

        self.assertEqual(1, len(dockWidgets))
        self.assertEqual(dockWidgets[0], attrTable)
        lyr.setName('Layer B')
        self.assertTrue('Layer B' in dockWidgets[0].windowTitle())

        features = list(lyr.getFeatures())

        lyr.selectByIds([features[0].id()])
        attrTable.mLabelWidget.mActionZoomMapToSelectedRows.trigger()
        self.showGui(EOTSV.ui)

        EOTSV.close()
        QgsProject.instance().removeAllMapLayers()

    def test_doi_expression(self):

        context = QgsExpressionContext()
        scope = QgsExpressionContextScope()
        scope.setVariable('doi', 15)
        context.appendScope(scope)

        expression = QgsExpression('@doi')
        self.assertFalse(expression.hasParserError(), msg=expression.parserErrorString())

        value = expression.evaluate(context)
        self.assertFalse(expression.hasEvalError(), msg=expression.evalErrorString())

        self.assertEqual(15, value)

    def test_labelClassInfos(self):

        vl = TestObjects.createVectorLayer()

        cs = ClassificationScheme()
        cs.insertClass(ClassInfo(label=1, name='classA', color='green'))
        cs.insertClass(ClassInfo(label=2, name='classB', color='blue'))
        cs.insertClass(ClassInfo(label=3, name='classC', color='orange'))

        vl.setRenderer(cs.featureRenderer(QgsMarkerSymbol))

        with edit(vl):
            # setup different classification schemes
            # EOTSV QuickLayer Classification Scheme
            field = QgsField('cs_ql_str', QMetaType.QString)
            setup = createWidgetSetup(labelType=LabelShortcutType.Classification, classification=cs)
            field.setEditorWidgetSetup(setup)
            vl.addAttribute(field)

            field = QgsField('cs_ql_int', QMetaType.Int)
            setup = createWidgetSetup(labelType=LabelShortcutType.Classification, classification=cs)
            field.setEditorWidgetSetup(setup)
            vl.addAttribute(field)

            # Raster Classification Scheme
            field = QgsField('cs_cs_str', QMetaType.QString)
            field.setEditorWidgetSetup(QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(cs)))
            vl.addAttribute(field)

            field = QgsField('cs_cs_int', QMetaType.Int)
            field.setEditorWidgetSetup(QgsEditorWidgetSetup(CS_KEY, classSchemeToConfig(cs)))
            vl.addAttribute(field)

            # QGIS Classification
            field = QgsField('cs_qgis_str', QMetaType.QString)
            field.setEditorWidgetSetup(QgsEditorWidgetSetup('Classification', {}))
            vl.addAttribute(field)

            field = QgsField('cs_qgis_int', QMetaType.Int)
            field.setEditorWidgetSetup(QgsEditorWidgetSetup('Classification', {}))
            vl.addAttribute(field)

        vl.removeSelection()

        class_schemes = quickLabelClassSchemes(vl)
        self.assertEqual(len(class_schemes), 6)

        class_field_names = [f for f in vl.fields() if f.name().startswith('cs_')]

        with edit(vl):
            # no features selected -> no changes
            self.assertEqual(vl.selectedFeatureCount(), 0)
            for n in class_field_names:
                changed = setQuickClassInfo(vl, n, 1)
                self.assertEqual(changed, [])

            # select features and set class value
            id1 = vl.allFeatureIds()[0]
            vl.selectByIds([id1])
            self.assertEqual(vl.selectedFeatureCount(), 1)
            for n in class_field_names:
                # provide class label numer
                changed = setQuickClassInfo(vl, n, 1)
                self.assertEqual(changed, [id1])

                # provide class name
                changed = setQuickClassInfo(vl, n, 'classA')
                self.assertEqual(changed, [id1])

                # provide class info
                c = cs[2]
                self.assertIsInstance(c, ClassInfo)
                changed = setQuickClassInfo(vl, n, c)
                self.assertEqual(changed, [id1])

    def test_labelValues(self):

        vl = self.createVectorLayer()
        self.setupEditWidgets(vl)

        TS = TestObjects.createTimeSeries()

        tsd: TimeSeriesDate = TS[0]
        # tsd.setDTG(np.datetime64('2019-02-05T11:23:42.00'))
        tss = tsd[0]
        tss.mUri = '/path/to/image'
        tsd.sensor().setName('LND')

        context = QgsExpressionContext()

        context.appendScope(quickLabelExpressionContextScope(tsd))

        with edit(vl):
            for feature in vl.getFeatures():
                for field in vl.fields():
                    field: QgsField
                    fidx = vl.fields().lookupField(field.name())

                    if field.name() == 'DOY':
                        s = ""
                    transformer = GenericPropertyTransformer(field)
                    if isQuickLabelField(field):
                        self.assertIsInstance(field, QgsField)

                        ctx = QgsExpressionContext(context)
                        expr = QgsExpression(quickLabelExpression(field))

                        self.assertIsInstance(expr, QgsExpression)

                        self.assertFalse(expr.hasParserError(), msg=expr.parserErrorString())
                        self.assertTrue(expr.isValid())
                        value = expr.evaluate(ctx)

                        self.assertFalse(expr.hasEvalError(), msg=expr.evalErrorString())

                        if value is None:
                            print(
                                f'fid: {feature.id()}: {field.name()} ({field.typeName()}) value is None.\nExpression={expr}')
                            print(ctx.variablesToMap())
                            s = ""
                        else:
                            value2 = transformer.transform(ctx, value)
                            print(f'fid: {feature.id()}: Set {field.name()} ({field.typeName()}) = {value2}')
                            assert vl.changeAttributeValue(feature.id(), fidx, value2)
                    s = ""


if __name__ == "__main__":
    unittest.main(buffer=False)
