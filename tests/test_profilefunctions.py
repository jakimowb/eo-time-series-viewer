import json
import unittest

import numpy as np
from PyQt5.QtWidgets import QTableView
from qgis._core import QgsFeature

from eotimeseriesviewer.temporalprofile.spectralindices import SpectralIndexBandIdentifierModel, \
    SpectralIndexConstantModel
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects

start_app()


class ProfileFunctionTestCases(EOTSVTestCase):

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

    def test_sensorSpecs(self):

        ts = TestObjects.createTimeSeries()
        for sensor in ts.sensors():
            sid = sensor.id()
            spec = TemporalProfileUtils.sensorSpecs(sid)
            self.assertIsInstance(spec, dict)

            self.assertIn('nb', spec)
            self.assertIn('band_lookup', spec)
            self.assertIn('sid', spec)

    def test_bandOrIndex(self):

        lyr = TestObjects.createProfileLayer()
        for feature in lyr.getFeatures():
            tpData = feature.attribute('profile')
            sidx = np.asarray(tpData[TemporalProfileUtils.Sensor])
            all_band_values = tpData[TemporalProfileUtils.Values]

            for i, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
                is_sensor = np.where(sidx == i)[0]
                band_values = np.asarray([all_band_values[j] for j in is_sensor])
                if len(band_values) == 0:
                    continue

                specs = TemporalProfileUtils.sensorSpecs(sid)
                band_lookup = specs['band_lookup']

                n, nb = band_values.shape
                if specs['nb'] != nb:
                    s = ""
                self.assertEqual(nb, specs['nb'])

                # b(1) or b('1') -> return 1st band
                for expr in [1, '1']:
                    result = TemporalProfileUtils.bandOrIndex(expr, band_values, specs)
                    self.assertTrue(np.all(result == band_values[:, 0]))

                # b(999) or b('999') -> return 999th band
                for expr in [nb, f'{nb}']:
                    result = TemporalProfileUtils.bandOrIndex(expr, band_values, specs)
                    self.assertTrue(np.all(result == band_values[:, nb - 1]))

                # b('B') -> return band values by band acronym
                for band_acronym in ['R', 'G', 'B', 'N']:
                    result = TemporalProfileUtils.bandOrIndex(band_acronym, band_values, specs)
                    if band_acronym in band_lookup:
                        self.assertTrue(np.all(result == band_values[:, band_lookup[band_acronym]]))
                    else:
                        s = ""
                        self.assertTrue(np.all(np.isnan(result)))

                result = TemporalProfileUtils.bandOrIndex('NDVI', band_values, specs)

                if 'N' in band_lookup and 'R' in band_lookup:
                    ndvi = ((band_values[:, band_lookup['N']] - band_values[:, band_lookup['R']]) /
                            (band_values[:, band_lookup['N']] + band_values[:, band_lookup['R']]))
                    self.assertTrue(np.all(result == ndvi))
                else:
                    self.assertTrue(np.all(np.isnan(result)))

    def test_profile_python_function(self):

        tpData = TestObjects.createTemporalProfileDict()

        all_values = tpData[TemporalProfileUtils.Values]
        values_by_sid = {}
        for i, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
            values = []
            for j, s in enumerate(tpData[TemporalProfileUtils.Sensor]):
                if s == i:
                    values.append(tpData[TemporalProfileUtils.Values][j])

            values_by_sid[sid] = np.asarray(values)

        f = QgsFeature()
        expressions = {'*': 'b("NDVI")'}
        expressions = {k: TemporalProfileUtils.prepareBandExpression(v)[0] for k, v in expressions.items()}

        results = TemporalProfileUtils.applyExpressions(tpData, f, expressions)
        self.assertIsInstance(results, dict)
        x = results['x']
        y = results['y']
        n = results['n']
        sidx = results['sensor_indices']

        self.assertIsInstance(x, np.ndarray)
        self.assertIsInstance(y, np.ndarray)
        self.assertEqual(x.shape, y.shape)
        self.assertEqual(len(x), len(y))
        self.assertEqual(len(x), n)

        expressions = {}
        results = TemporalProfileUtils.applyExpressions(tpData, f, expressions)
        self.assertIsInstance(results, dict)
        self.assertEqual(results['n'], 0)

        sid1, sid2 = tpData[TemporalProfileUtils.SensorIDs]
        expressions = {sid1: 'b(4)',  # valid python expression, get values of band 4
                       sid2: 'foobar"',  # in-valid python expression
                       }

        results = TemporalProfileUtils.applyExpressions(tpData, f, expressions)
        self.assertIsInstance(results, dict)
        self.assertEqual(results['n'], 2)
        errors = results['errors']
        self.assertEqual(len(errors), 1)

        y = results['y']
        self.assertTrue(np.all(y == values_by_sid[sid1][:, 3]))

        sid1, sid2 = tpData[TemporalProfileUtils.SensorIDs]
        expressions = {sid1: 'b(1)',  # valid python expression, get values of band 4
                       sid2: None,  # exclude sid2
                       }

        results = TemporalProfileUtils.applyExpressions(tpData, f, expressions)
        self.assertIsInstance(results, dict)
        self.assertEqual(results['n'], 2)
        errors = results['errors']
        self.assertEqual(len(errors), 0)

        y = results['y']
        self.assertTrue(np.all(y == values_by_sid[sid1][:, 0]))
        s = ""


if __name__ == '__main__':
    unittest.main()
