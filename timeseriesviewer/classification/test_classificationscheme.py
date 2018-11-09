# coding=utf-8
"""Resources test.

"""
__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
import tempfile
import enmapboxtestdata

from enmapbox.gui.utils import *
from .classificationscheme import *

SHOW_GUIS = True

QGIS_APP = initQgisApplication()



from unittest import TestCase
class TestsClassificationScheme(TestCase):

    def setUp(self):

        self.nameL1 = 'Level 1 (int)'
        self.nameL2 = 'Level 2 (str)'
    def createClassSchemeA(self)->ClassificationScheme:

        cs = ClassificationScheme()
        cs.insertClass(ClassInfo(name='unclassified', color=QColor('black')))
        cs.insertClass(ClassInfo(name='Forest', color=QColor('green')))
        cs.insertClass(ClassInfo(name='None-Forest', color=QColor('blue')))
        return cs

    def createClassSchemeB(self)->ClassificationScheme:

        cs = ClassificationScheme()
        cs.insertClass(ClassInfo(name='unclassified', color=QColor('black')))
        cs.insertClass(ClassInfo(name='Forest', color=QColor('green')))
        cs.insertClass(ClassInfo(name='Water', color=QColor('blue')))
        cs.insertClass(ClassInfo(name='Urban', color=QColor('red')))
        cs.insertClass(ClassInfo(name='Agriculture', color=QColor('red')))
        cs.insertClass(ClassInfo(name='unclassified', color=QColor('black')))
        cs.insertClass(ClassInfo(name='Class A', color=QColor('green')))
        cs.insertClass(ClassInfo(name='Class B', color=QColor('blue')))
        return cs

    def createRasterLayer(self)->QgsRasterLayer:

        rl = QgsRasterLayer(enmapboxtestdata.hires)

        renderer = QgsPalettedRasterRenderer(None, 1, {})
        assert isinstance(renderer, QgsPalettedRasterRenderer)
        rl.setRenderer(renderer)

        return rl

    def createVectorLayer(self)->QgsVectorLayer:
        # create layer
        vl = QgsVectorLayer("Point", "temporary_points", "memory")
        vl.startEditing()
        # add fields
        vl.addAttribute(QgsField("name", QVariant.String))
        nameL1 = self.nameL1
        nameL2 = self.nameL2
        vl.addAttribute(QgsField(nameL1, QVariant.Int))
        vl.addAttribute(QgsField(nameL2, QVariant.String))
        f = QgsFeature(vl.fields())
        f.setAttribute('name', 'an example')
        f.setAttribute(nameL1, 2)
        f.setAttribute(nameL2, 'Agriculture')
        vl.addFeature(f)

        f = QgsFeature(vl.fields())
        f.setAttribute('name', 'another example')
        f.setAttribute(nameL1, 1)
        f.setAttribute(nameL2, 'Forest')
        vl.addFeature(f)

        vl.commitChanges()


        confValuesL1 = {'classes': self.createClassSchemeA().json()}
        confValuesL2 = {'classes': self.createClassSchemeB().json()}
        vl.setEditorWidgetSetup(vl.fields().lookupField(nameL1), QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, confValuesL1))
        vl.setEditorWidgetSetup(vl.fields().lookupField(nameL2), QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, confValuesL2))



        return vl

    def testClassInfo(self):
        name = 'TestName'
        label = 2
        color = QColor('green')
        c = ClassInfo(name=name, label=label, color=color)
        self.assertEqual(c.name(), name)
        self.assertEqual(c.label(), label)
        self.assertEqual(c.color(), color)

        name2 = 'TestName2'
        label2 = 3
        color2 = QColor('red')
        c.setLabel(label2)
        c.setColor(color2)
        c.setName(name2)
        self.assertEqual(c.name(), name2)
        self.assertEqual(c.label(), label2)
        self.assertEqual(c.color(), color2)


    def test_ClassificationScheme(self):
        cs = ClassificationScheme.create(3)

        self.assertIsInstance(cs, ClassificationScheme)
        self.assertEqual(cs[0].color(), DEFAULT_UNCLASSIFIEDCOLOR)
        c = ClassInfo(label=1, name='New Class', color=QColor('red'))
        cs.insertClass(c)
        self.assertEqual(cs[3], c)
        cs._updateLabels()
        self.assertEqual(cs[3].label(), 3)

        self.assertEqual(cs.headerData(0, Qt.Horizontal, Qt.DisplayRole), 'Label')
        self.assertEqual(cs.headerData(1, Qt.Horizontal, Qt.DisplayRole), 'Name')
        self.assertEqual(cs.headerData(2, Qt.Horizontal, Qt.DisplayRole), 'Color')

        self.assertEqual(cs.data(cs.createIndex(0,0), Qt.DisplayRole), 0)
        self.assertEqual(cs.data(cs.createIndex(0,1), Qt.DisplayRole), cs[0].name())
        self.assertEqual(cs.data(cs.createIndex(0,2), Qt.DisplayRole), cs[0].color().name())
        self.assertEqual(cs.data(cs.createIndex(0,2), Qt.BackgroundColorRole), cs[0].color())

        self.assertIsInstance(cs.data(cs.createIndex(0,0), role=Qt.UserRole), ClassInfo)

        with self.assertRaises(AssertionError):
            cs.insertClass(c)

        c2 = ClassInfo(label=5, name='Class 2')
        cs.insertClass(c2)
        self.assertTrue(len(cs) == 5)


        mimeData = cs.mimeData(None)
        self.assertIsInstance(mimeData, QMimeData)

        for key in [MIMEDATA_KEY]:
            self.assertTrue(key in mimeData.formats())


    def test_json_pickle(self):
        cs = self.createClassSchemeA()

        j = cs.json()
        self.assertIsInstance(j, str)
        cs2 = ClassificationScheme.fromJson(j)
        self.assertIsInstance(cs2, ClassificationScheme)
        self.assertEqual(cs, cs2)

        p = cs.pickle()
        self.assertIsInstance(p, bytes)

        cs3 = ClassificationScheme.fromPickle(p)
        self.assertIsInstance(cs3, ClassificationScheme)
        self.assertEqual(cs3, cs)




    def test_ClassInfoComboBox(self):
        scheme = self.createClassSchemeA()


        w = ClassificationSchemeComboBox()
        w.show()
        w.setClassificationScheme(scheme)
        self.assertIsInstance(w.classificationScheme(), ClassificationScheme)
        w.setCurrentIndex(2)
        self.assertIsInstance(w.currentClassInfo(), ClassInfo)
        self.assertEqual(w.currentClassInfo(), scheme[2])

        if SHOW_GUIS:
            QGIS_APP.exec_()


    def test_ClassificationSchemeEditorWidgetFactory(self):

        # init some other requirements
        print('initialize EnMAP-Box editor widget factories')
        # register Editor widgets, if not done before

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()


        registerClassificationSchemeEditorWidget()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, ClassificationSchemeWidgetFactory)

        vl = self.createVectorLayer()



        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())
        dv = QgsDualView()
        dv.init(vl, c)
        dv.setView(QgsDualView.AttributeTable)
        dv.setAttributeTableConfig(vl.attributeTableConfig())
        dv.show()
        cb = QCheckBox()
        cb.setText('Show Editor')
        def onClicked(b:bool):
            if b:
                dv.setView(QgsDualView.AttributeEditor)
            else:
                dv.setView(QgsDualView.AttributeTable)
        cb.clicked.connect(onClicked)
        w.layout().addWidget(dv)
        w.layout().addWidget(cb)
        vl.startEditing()
        w.show()
        w.resize(QSize(300,250))
        print(vl.fields().names())
        look = vl.fields().lookupField

        self.assertTrue(factory.fieldScore(vl, look(self.nameL1)) == 20)
        self.assertTrue(factory.fieldScore(vl, look(self.nameL2)) == 20)

        parent = QWidget()
        configWidget = factory.configWidget(vl, look(self.nameL1), None)
        self.assertIsInstance(configWidget, ClassificationSchemeEditorConfigWidget)
        configWidget.show()

        self.assertIsInstance(factory.createSearchWidget(vl, 0, dv), QgsSearchWidgetWrapper)

        eww = factory.create(vl, 0, None, dv )
        self.assertIsInstance(eww, ClassificationSchemeEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), ClassificationSchemeComboBox)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))


        if SHOW_GUIS:
            QGIS_APP.exec_()


    def test_findMapLayerWithClassInfo(self):


        rr = self.createClassSchemeA().rasterRenderer()
        vr = self.createClassSchemeB().featureRenderer()
        vl = self.createVectorLayer()
        rl = self.createRasterLayer()
        self.assertIsInstance(vl, QgsVectorLayer)
        self.assertIsInstance(rl, QgsRasterLayer)
        self.assertIsInstance(rr, QgsRasterRenderer)
        self.assertIsInstance(vr, QgsFeatureRenderer)

        vl.setRenderer(vr)
        rl.setRenderer(rr)

        store = QgsMapLayerStore()
        from . import MAP_LAYER_STORES as ML_STORE
        ML_STORE.add(store)

        lyrs = findMapLayerWithClassInfo()
        self.assertIsInstance(lyrs, list)
        self.assertTrue(len(lyrs) == 0)

        store.addMapLayers([vl, rl])

        lyrs = findMapLayerWithClassInfo()
        self.assertIsInstance(lyrs, list)
        self.assertTrue(len(lyrs) == 2)
        self.assertTrue(vl in lyrs)
        self.assertTrue(rl in lyrs)

        if SHOW_GUIS:
            w = ClassificationSchemeWidget()
            w.show()
            w.onLoadClasses('layer')
            QGIS_APP.exec_()

    def test_ClassificationSchemeWidget(self):

        from . import MAP_LAYER_STORES as ML

        w = ClassificationSchemeWidget()
        self.assertIsInstance(w.classificationScheme(), ClassificationScheme)
        w.show()



        w.btnAddClasses.click()
        w.btnAddClasses.click()

        self.assertTrue(len(w.classificationScheme()) == 2)



        if SHOW_GUIS:
            QGIS_APP.exec_()


    def test_ClassificationSchemeComboBox(self):

        cs = self.createClassSchemeA()

        w = ClassificationSchemeComboBox(classification=cs)
        w.show()

        self.assertTrue(len(w.classificationScheme()) == 3)
        self.assertTrue(w.count() == 3)

        cs.removeClasses([cs[0]])
        self.assertTrue(w.count() == 2)

        newClasses = [ClassInfo(name='New 1'), ClassInfo(name='New 2')]
        cs.insertClasses(newClasses, index=0)
        self.assertTrue(w.count() == 4)
        self.assertTrue(w.itemData(0, Qt.UserRole) == newClasses[0])

        for i, classInfo in enumerate(w.classificationScheme()):
            self.assertTrue(classInfo.label() == i)

        newClasses2 = [ClassInfo(name='New 3'), ClassInfo(name='New 4')]
        cs.insertClasses(newClasses2, index=3)

        for i, classInfo in enumerate(w.classificationScheme()):
            self.assertIsInstance(classInfo, ClassInfo)
            self.assertTrue(classInfo.label() == i)
            text = w.itemData(i, role=Qt.DisplayRole)
            self.assertTrue(text.startswith('{}'.format(classInfo.label())))
        self.assertTrue(w.count() == 4+2)
        self.assertTrue(w.itemData(3, Qt.UserRole) == newClasses2[0])



        if SHOW_GUIS:
            QGIS_APP.exec_()


    def test_io_CSV(self):

        testDir = os.path.dirname(enmapboxtestdata.library)

        pathTmp = tempfile.mktemp(suffix='.csv')

        cs = self.createClassSchemeA()
        self.assertIsInstance(cs, ClassificationScheme)
        path = cs.saveToCsv(pathTmp)
        self.assertTrue(os.path.isfile(path))

        cs2 = ClassificationScheme.fromCsv(pathTmp)
        self.assertIsInstance(cs2, ClassificationScheme)
        self.assertEqual(cs, cs2)


    def test_io_RasterRenderer(self):


        cs = self.createClassSchemeA()
        self.assertIsInstance(cs, ClassificationScheme)

        r = cs.rasterRenderer()
        self.assertIsInstance(r, QgsPalettedRasterRenderer)



        cs2 = ClassificationScheme.fromRasterRenderer(r)
        self.assertIsInstance(cs2, ClassificationScheme)
        self.assertEqual(cs, cs2)

    def test_io_FeatureRenderer(self):


        cs = self.createClassSchemeA()
        self.assertIsInstance(cs, ClassificationScheme)

        r = cs.featureRenderer()
        self.assertIsInstance(r, QgsCategorizedSymbolRenderer)

        cs2 = ClassificationScheme.fromFeatureRenderer(r)
        self.assertIsInstance(cs2, ClassificationScheme)
        self.assertEqual(cs, cs2)


    def test_io_QML(self):

        testDir = os.path.dirname(enmapboxtestdata.library)
        qmFiles = file_search(testDir, 'LandCov_*.qml')

        pathTmp = tempfile.mktemp(suffix='.qml')
        for pathQML in qmFiles:
            # read from QML
            classScheme = ClassificationScheme.fromQml(pathQML)
            self.assertIsInstance(classScheme, ClassificationScheme)
            self.assertTrue(len(classScheme) > 0)

            # todo: other QML specific tests

            #write to QML
            classScheme.saveToQml(pathTmp)

            classScheme2 = ClassificationScheme.fromQml(pathTmp)
            self.assertIsInstance(classScheme2, ClassificationScheme)
            self.assertEqual(classScheme, classScheme2)





        s = ""

if __name__ == "__main__":

    SHOW_GUIS = False
    unittest.main()



