import json
import re
import unittest
import random

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QSplitter, QVBoxLayout, QWidget
from qgis._core import QgsProject, QgsVectorLayer

from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialPoint
from eotimeseriesviewer.sensorvisualization import SensorDockUI
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.plotsettings import PlotSettingsTreeView, TPVisSensor
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileEditorWidgetFactory
from eotimeseriesviewer.temporalprofile.visualization import TemporalProfileDock, TemporalProfileVisualization
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects
from eotimeseriesviewer import initResources
from eotimeseriesviewer.timeseries import SensorInstrument, TimeSeries

start_app()
initResources()

TemporalProfileEditorWidgetFactory.register()
from eotimeseriesviewer.tests import FORCE_CUBE


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
        text = json.dumps(value, ensure_ascii=False)
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
            data = json.loads(json.dumps(data))
            self.assertEqual(data['sensor_id'], sensor.id())

    def test_TemporalProfileDock(self):

        if False and FORCE_CUBE and FORCE_CUBE.is_dir():
            files = file_search(FORCE_CUBE, re.compile('.*BOA.tif$'), recursive=True)
            ts = TimeSeries()
            files = list(files)[:50]
            ts.addSources(files, runAsync=False)
            s = ""
        else:
            ts = TestObjects.createTimeSeries()

        for i, sensor in enumerate(ts.sensors()):
            sensor: SensorInstrument
            sensor.setName(f'Sensor {i + 1}')

        btn = QPushButton('Add random profile')

        layer = TestObjects.createProfileLayer(ts)
        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertTrue(layer.isValid())
        l2 = TestObjects.createVectorLayer()
        project = QgsProject()
        project.addMapLayers([layer, l2])
        dock = TemporalProfileDock()
        dock.setTimeSeries(ts)
        dock.setProject(project)

        panel = SensorDockUI()
        panel.setTimeSeries(ts)

        dock.mVis.updatePlot()

        atd = AttributeTableWidget(layer)

        def onAddRandomProfile():
            ext = ts.maxSpatialExtent()
            x = random.uniform(ext.xMinimum(), ext.xMaximum())
            y = random.uniform(ext.yMinimum(), ext.yMaximum())
            pt = SpatialPoint(ext.crs(), x, y)
            dock.loadTemporalProfile(pt, run_async=False)

        def onMoveToDate(date):
            print(f'# Move to date: {date}')

        dock.sigMoveToDate.connect(onMoveToDate)

        btn.clicked.connect(onAddRandomProfile)

        # combine dock and panel with a splitter

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(dock)
        splitter.addWidget(panel)

        vl = QVBoxLayout()
        vl.addWidget(btn)
        vl.addWidget(splitter)
        vl.addWidget(atd)
        w = QWidget()
        w.setLayout(vl)
        w.resize(QSize(1200, 800))
        btn.click()
        self.showGui(w)


if __name__ == "__main__":
    unittest.main(buffer=False)
