import json
import re
import unittest
import random

import numpy as np

from qgis.PyQt.QtGui import QAction, QIcon, QPen, QStandardItemModel
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotCurveItem
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.examples.ExampleApp import QColor
from qgis.PyQt.QtWidgets import QHBoxLayout, QMenu, QPushButton, QSplitter, QTreeView, QVBoxLayout, QWidget
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QSize, Qt
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, SpatialPoint
from eotimeseriesviewer.qgispluginsupport.qps.vectorlayertools import VectorLayerTools
from eotimeseriesviewer.sensorvisualization import SensorDockUI
from eotimeseriesviewer.temporalprofile.datetimeplot import copyProfiles, DateTimePlotDataItem, DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.plotsettings import PlotSettingsTreeView, PythonCodeItem, TPVisSensor, \
    TPVisSettings
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileEditorWidgetFactory, TemporalProfileUtils
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

    def test_settings(self):

        settings_item = TPVisSettings()

        action = QAction('My Action')
        action.setObjectName('MyAction')
        action.setChecked(True)
        action.setCheckable(True)
        action.setIcon(QIcon(r':/images/themes/default/mIconLineLayer.svg'))
        action.setToolTip('My Tooltip')

        def onToggled(b):
            print(f'Checked: {b}')

        action.toggled.connect(onToggled)

        settings_item.createActionItem(action)
        model = QStandardItemModel()

        model.insertRow(0, settings_item)

        view = QTreeView()
        view.setModel(model)
        self.showGui(view)

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

    def test_copy_profiles(self):

        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = np.asarray([ImageDateUtils.timestamp(d) for d in dates])
        pdi = DateTimePlotDataItem(x=x, y=ndvi_values, name='Profile A')

        pdi2 = DateTimePlotDataItem(x=x + 0.2, y=ndvi_values * 0.8, name='Profile B')

        copyProfiles([pdi, pdi2], 'json')
        md = QgsApplication.instance().clipboard().mimeData()
        data = json.loads(md.text())
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        if pdi.mTemporalProfile:
            copyProfiles([pdi, pdi2], 'tp_json')
            md = QgsApplication.instance().clipboard().mimeData()
            data = json.loads(md.text())
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)
            for i, d in enumerate(data):
                self.assertTrue(TemporalProfileUtils.isProfileDict(d))

        copyProfiles([pdi, pdi2], 'csv')
        md = QgsApplication.instance().clipboard().mimeData()
        data = md.text()
        self.assertIsInstance(data, str)
        lines = data.splitlines()
        self.assertEqual(lines[0], f'date,{pdi.name()},{pdi2.name()}')

    def test_DateTimePlotItem(self):

        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = np.asarray([ImageDateUtils.timestamp(d) for d in dates])
        pdi = DateTimePlotDataItem(x=x, y=ndvi_values, name='Profile A')
        pdi2 = DateTimePlotDataItem(x=x + 0.2, y=ndvi_values * 0.8, name='Profile B')

        selStyle = PlotStyle()
        selStyle.setLineWidth(5)
        selStyle.setLineColor('yellow')

        def func_selection(pdi: DateTimePlotDataItem):
            p = QPen(pdi.mDefaultStyle.linePen)
            p.setColor(QColor('yellow'))
            p.setWidth(p.width() + 3)
            pdi.setPen(p)

        pdi.setSelectedStyle(func_selection)
        pdi2.setSelectedStyle(func_selection)

        def onClicked(curve: PlotCurveItem):
            pdi = curve.parentItem()

            if not isinstance(pdi, DateTimePlotDataItem):
                return

        # pdi.setFlag(QGraphicsItem.ItemIsSelectable, True)
        # pdi.curve.setFlag(QGraphicsItem.ItemIsSelectable, True)
        coll = dict()
        coll[pdi] = 'foo'
        coll[pdi2] = 'bar'
        self.assertEqual(coll[pdi], 'foo')
        self.assertEqual(coll[pdi2], 'bar')

        w = DateTimePlotWidget()

        w.addItem(pdi)
        w.addItem(pdi2)

        self.showGui(w)

    def test_TemporalProfileDock(self):

        if FORCE_CUBE and FORCE_CUBE.is_dir():
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

        dock.setMapDateRange(ts[0].dtg(), ts[5].dtg())
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
