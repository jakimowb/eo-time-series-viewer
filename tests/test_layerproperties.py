# noinspection PyPep8Naming
import os, sys, re
from qgis.core import *
from qgis.gui import *
from eotimeseriesviewer.tests import initQgisApplication, testRasterFiles, TestObjects
import unittest, tempfile

from eotimeseriesviewer.layerproperties import *
from eotimeseriesviewer import DIR_REPO

resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = False and os.environ.get('CI') is None


QgsGui.editorWidgetRegistry().initEditors()


class TestLayerproperties(unittest.TestCase):

    def createVectorLayer(self) -> QgsVectorLayer:
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

    def test_LabelFieldModel(self):

        lyr = self.createVectorLayer()

        w = QTreeView()

        fm = LabelFieldModel(w)
        fm.setLayer(lyr)
        self.assertEqual(fm.layer(), lyr)

        newName = 'Layer Fields'
        fm.setHeaderData(0, Qt.Horizontal, newName, role=Qt.EditRole)
        self.assertEqual(newName, fm.headerData(0, Qt.Horizontal))

        w.setModel(fm)
        w.show()


        if SHOW_GUI:
            QGIS_APP.exec_()

    def test_FieldConfigEditorWidget(self):


        lyr = self.createVectorLayer()

        w = FieldConfigEditorWidget(None, lyr, 3)
        self.assertIsInstance(w, FieldConfigEditorWidget)
        w.show()

        conf1 = w.currentFieldConfig()
        self.assertEqual(conf1.config(), w.mInitialConf)
        self.assertEqual(conf1.factoryKey(), w.mInitialFactoryKey)
        w.setFactory('CheckBox')
        conf2 = w.currentFieldConfig()

        self.assertTrue(conf1 != conf2)
        self.assertTrue(w.changed())
        w.setFactory(conf1.factoryKey())

        conf3 = w.currentFieldConfig()
        self.assertEqual(conf3.factoryKey(), conf1.factoryKey())

        self.assertFalse(w.changed())

        if SHOW_GUI:
            QGIS_APP.exec_()



    def test_LayerFieldConfigEditorWidget(self):

        lyr = self.createVectorLayer()

        w = LayerFieldConfigEditorWidget(None)
        self.assertIsInstance(w, LayerFieldConfigEditorWidget)

        self.assertTrue(w.layer() == None)
        w.setLayer(lyr)
        self.assertTrue(w.layer() == lyr)
        w.setLayer(None)
        self.assertTrue(w.layer() == None)

        if SHOW_GUI:
            w.show()
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()

QGIS_APP.quit()
