import json
import unittest

from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget
from qgis._core import QgsProject

from eotimeseriesviewer.sensorvisualization import SensorDockUI
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.plotsettings import PlotSettingsTreeView, TPVisSensor
from eotimeseriesviewer.temporalprofile.visualization import TemporalProfileDock, TemporalProfileVisualization
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects
from eotimeseriesviewer import initResources
from eotimeseriesviewer.timeseries import SensorInstrument

start_app()
initResources()


class PlotSettingsTests(TestCase):

    def test_TemporalProfileVisualization(self):
        view = PlotSettingsTreeView()
        widget = DateTimePlotWidget()
        sensorDock = SensorDockUI()

        tpVis = TemporalProfileVisualization(view, widget)

        ts = TestObjects.createTimeSeries()
        tpVis.setTimeSeries(ts)
        sensorDock.setTimeSeries(ts)

        btnAddVis = QPushButton('Add Vis')
        btnAddVis.clicked.connect(tpVis.createVisualization)
        btnAddVis.click()
        l0 = QHBoxLayout()
        l0.addWidget(btnAddVis)

        l = QHBoxLayout()
        l.addWidget(view)
        l.addWidget(widget)
        l.addWidget(sensorDock)

        v = QVBoxLayout()
        v.addLayout(l0)
        v.addLayout(l)

        w = QWidget()
        w.setLayout(v)
        self.showGui(w)

    def assertIsJSONizable(self, value):
        text = json.dumps(value)
        self.assertIsInstance(text, str)
        value2 = json.loads(text)

        self.assertEqual(value, value2)

    def test_SensorItems(self):
        ts = TestObjects.createTimeSeries()

        tpSensor = TPVisSensor()
        data = tpSensor.settingsMap()
        self.assertIsInstance(data, dict)
        self.assertIsJSONizable(data)

        for sensor in ts.sensors():
            tpSensor.setSensor(sensor.id())
            data = tpSensor.settingsMap()
            self.assertIsInstance(data, dict)
            self.assertEqual(data['sensor_id'], sensor.id())

    def test_TemporalProfileDock(self):

        ts = TestObjects.createTimeSeries()

        for i, sensor in enumerate(ts.sensors()):
            sensor: SensorInstrument
            sensor.setName(f'Sensor {i + 1}')

        layer = TestObjects.createProfileLayer(ts)
        l2 = TestObjects.createVectorLayer()
        project = QgsProject()
        project.addMapLayers([layer, l2])
        dock = TemporalProfileDock()
        dock.setTimeSeries(ts)
        dock.setProject(project)

        panel = SensorDockUI()
        panel.setTimeSeries(ts)

        dock.mVis.updatePlot()

        l = QHBoxLayout()
        l.addWidget(dock)
        l.addWidget(panel)
        w = QWidget()
        w.setLayout(l)
        self.showGui(w)


if __name__ == "__main__":
    unittest.main(buffer=False)
