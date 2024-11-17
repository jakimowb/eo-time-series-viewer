import json
import unittest

from PyQt5.QtWidgets import QTableView

from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
from eotimeseriesviewer.profilefunctions import ProfileValueExpressionFunction, spectral_index_scope, \
    SpectralIndexBandIdentifierModel, SpectralIndexConstantModel
from eotimeseriesviewer.temporalprofileV2 import TemporalProfileUtils
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects

start_app()


class ProfileFunctionTestCases(TestCase):

    def test_constantModel(self):

        model = SpectralIndexConstantModel()
        model.loadFromSpyndex()
        data1 = model.asMap()
        self.assertIsInstance(data1, dict)
        dump = json.dumps(data1)
        self.assertIsInstance(dump, str)
        data2 = json.loads(dump)

        model2 = SpectralIndexConstantModel()
        model2.loadFromMap(data2)

        for a1, a2 in zip(model.mConstantDefinitions.values(), model2.mConstantDefinitions.values()):
            self.assertEqual(a1, a2)

        view = QTableView()
        view.setModel(model)
        self.showGui(view)

    def test_BandAcronymModel(self):
        model = SpectralIndexBandIdentifierModel()
        # model.loadFromSpyndex('landsat8')
        model.loadFromSpyndex()

        data1 = model.asMap()

        dump = json.dumps(data1)
        self.assertIsInstance(dump, str)
        data2 = json.loads(dump)

        model2 = SpectralIndexBandIdentifierModel()
        model2.loadFromMap(data2)

        for a1, a2 in zip(model.mAcronyms, model2.mAcronyms):
            self.assertEqual(a1, a2)

        view = QTableView()
        view.setModel(model)
        self.showGui(view)

    def test_ProfileValueExpression(self):
        f = ProfileValueExpressionFunction()

        lyr = TestObjects.createProfileLayer()

        TemporalProfileUtils.temporalProfileFields(lyr)

        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(lyr))
        context.appendScope(spectral_index_scope())

        for feature in lyr.getFeatures():
            context.setFeature(feature)
            exp = QgsExpression(f'{f.name()}(\'NDVI\')')
            exp.prepare(context)
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
            ndvi_values = exp.evaluate(context)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertIsInstance(ndvi_values, list)

            # run QGIS Expression on each single data
            # this allows to user other QGIS functions
            context2 = QgsExpressionContext(context)
            for i, ndvi in enumerate(ndvi_values):
                context2.lastScope().setVariable('dates', i)
                exp = QgsExpression(f'({f.name()}(\'N\')-{f.name()}(\'R\')) / ({f.name()}(\'N\')+{f.name()}(\'R\'))')
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                ndvi_i = exp.evaluate(context2)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertEqual(ndvi_values[i], ndvi_i)


if __name__ == '__main__':
    unittest.main()
