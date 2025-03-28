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
import unittest

from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsOptionsWidgetFactory
from qgis.PyQt.QtWidgets import QTableView

from eotimeseriesviewer.settings.widget import EOTSVSettingsWidget, EOTSVSettingsWidgetFactory, SensorSettingsTableModel
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from eotimeseriesviewer.sensors import SensorMatching
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer.timeseries.source import TimeSeriesSource

start_app()


class TestSettings(EOTSVTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_SettingsWidget(self):

        w = EOTSVSettingsWidget(None)

        # w.apply()
        # w.resetSettings()

        myPlotStyle = PlotStyle()
        myPlotStyle.setLineWidth(10)
        myPlotStyle.setLineColor(QColor('orange'))

        w.btnProfileAdded.setPlotStyle(myPlotStyle.clone())

        w.apply()

        w = EOTSVSettingsWidget(None)
        style2 = w.btnProfileAdded.plotStyle()
        self.assertIsInstance(style2, PlotStyle)
        if style2 != myPlotStyle:
            s1 = style2.map()
            s2 = myPlotStyle.map()
            self.assertEqual(s1, s2)
        self.assertEqual(myPlotStyle, style2)
        self.showGui(w)

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_init_factory(self):

        factory = EOTSVSettingsWidgetFactory.instance()
        self.assertIsInstance(factory, QgsOptionsWidgetFactory)
        from qgis.utils import iface
        # registerOptionsWidgetFactory()
        d = iface.showOptionsDialog(currentPage='')
        d.exec_()
        # unregisterOptionsWidgetFactory()

    def test_SensorMatching(self):

        f0 = SensorMatching.PX_DIMS

        self.assertTrue(bool(f0 & SensorMatching.PX_DIMS))
        self.assertFalse(bool(f0 & SensorMatching.WL))
        f1 = SensorMatching.PX_DIMS | SensorMatching.WL
        self.assertTrue(bool(f1 & SensorMatching.WL))
        self.assertFalse(bool(f1 & SensorMatching.NAME))

        for f in [f0, f1]:
            name = SensorMatching.name(f1)
            tooltip = SensorMatching.tooltip(f)
            self.assertIsInstance(name, str)
            self.assertIsInstance(tooltip, str)
            self.assertTrue(len(name) > 0)
            self.assertTrue(len(tooltip) > 0)

    def test_SensorModel(self):

        tb = QTableView()
        m = SensorSettingsTableModel()
        tb.setModel(m)
        tb.show()

        self.showGui(tb)

    def test_saveAndRestoreSensorNames(self):

        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA

        tss = TimeSeriesSource.create(Img_2014_01_15_LC82270652014015LGN00_BOA)
        self.assertIsInstance(tss, TimeSeriesSource)
        sensorID = tss.sid()

        jsonDict = json.loads(sensorID)
        assert isinstance(jsonDict, dict)

        for k in ['nb', 'px_size_x', 'px_size_y', 'dt', 'wl', 'wlu', 'name']:
            self.assertTrue(k in jsonDict.keys())

        # removed: should be done by project settings


if __name__ == "__main__":
    unittest.main(buffer=False)
