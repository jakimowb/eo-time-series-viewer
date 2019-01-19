# noinspection PyPep8Naming
import os, sys, re
from timeseriesviewer.tests import initQgisApplication, testRasterFiles
import unittest, tempfile

from timeseriesviewer.layerproperties import *
from timeseriesviewer import DIR_REPO
from timeseriesviewer.mapcanvas import MapCanvas
from timeseriesviewer.tests import TestObjects
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True


QgsGui.editorWidgetRegistry().initEditors()


class testclassLabelingTest(unittest.TestCase):

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



    def test_fieldModel(self):

        lyr = self.createVectorLayer()

        w = QTreeView()

        fm = LabelFieldModel(w)
        fm.setLayer(lyr)
        w.setModel(fm)
        w.show()


        if SHOW_GUI:
            QGIS_APP.exec_()


    def test_LayerFieldConfigEditorWidget(self):

        lyr = self.createVectorLayer()

        w = LayerFieldConfigEditorWidget(None)
        self.assertIsInstance(w, LayerFieldConfigEditorWidget)

        w.show()
        self.assertTrue(w.layer() == None)
        w.setLayer(lyr)
        self.assertTrue(w.layer() == lyr)


        if SHOW_GUI:

            QGIS_APP.exec_()