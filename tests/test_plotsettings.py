import json
import re
import unittest
import random

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QMenu, QPushButton, QSplitter, QVBoxLayout, QWidget
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtGui import QAction
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialPoint
from eotimeseriesviewer.qgispluginsupport.qps.vectorlayertools import VectorLayerTools
from eotimeseriesviewer.sensorvisualization import SensorDockUI
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.plotsettings import PlotSettingsTreeView, PythonCodeItem, TPVisSensor
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileEditorWidgetFactory
from eotimeseriesviewer.temporalprofile.visualization import TemporalProfileDock, TemporalProfileVisualization
from eotimeseriesviewer.tests import EOTSVTestCase, FORCE_CUBE, start_app, TestObjects
from eotimeseriesviewer import initResources
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.timeseries.timeseries import TimeSeries

start_app()
initResources()

TemporalProfileEditorWidgetFactory.register()


class PlotSettingsTests(EOTSVTestCase):

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

    def test_bandIndexMenu(self):

        m = QMenu()
        item = PythonCodeItem('Band')
        view = PlotSettingsTreeView()
        menu = view.addSpectralIndexMenu(m, [item])

        self.assertIsInstance(menu, QMenu)
        for a in menu.findChildren(QAction):
            a: QAction

            if a.data():
                index = a.data()
                a.trigger()
                self.assertEqual(item.mPythonExpression, index)
            s = ""
            print(a.text())
        self.showGui(m)

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

    def test_TemporalProfileDock_pan_zoom(self):

        ts = TestObjects.createTimeSeries()

        lyr = TestObjects.createProfileLayer(ts)

        project = QgsProject()
        project.addMapLayer(lyr)
        dock = TemporalProfileDock()
        dock.setTimeSeries(ts)
        dock.setProject(project)

        canvas = QgsMapCanvas()

        cntPan = 0
        cntZoom = 0

        def onPan(*args, **kwds):
            nonlocal cntPan
            cntPan += 1

        def onZoom(*args, **kwargs):
            nonlocal cntZoom
            cntZoom += 1

        lyrTools = VectorLayerTools()
        lyrTools.sigPanRequest.connect(onPan)
        lyrTools.sigZoomRequest.connect(onZoom)

        dock.setVectorLayerTools(lyrTools)

        fids = lyr.allFeatureIds()
        fid = random.choice(fids)

        aPan: QAction = dock.actionPanToSelected
        aZoom: QAction = dock.actionZoomToSelected

        lyr.selectByIds([fid])

        self.assertTrue(aPan.isEnabled())
        self.assertTrue(aZoom.isEnabled())
        lyr.selectByIds([])
        self.assertFalse(aPan.isEnabled())
        self.assertFalse(aZoom.isEnabled())
        lyr.selectByIds([fid])
        self.assertTrue(aPan.isEnabled())
        self.assertTrue(aZoom.isEnabled())

        aPan.trigger()
        self.assertEqual(cntPan, 1)
        aZoom.trigger()
        self.assertEqual(cntZoom, 1)

    def test_TemporalProfileDock(self):

        if False and FORCE_CUBE and FORCE_CUBE.is_dir():
            files = file_search(FORCE_CUBE, re.compile('.*BOA.tif$'), recursive=True)
            ts = TimeSeries()
            files = list(files)[:25]
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
