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
# noinspection PyPep8Naming
import uuid
from eotimeseriesviewer.tests import start_app
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
import unittest
import tempfile
import xmlrunner

from qgis.core import QgsReadWriteContext, QgsTextFormat

from eotimeseriesviewer.tests import EOTSVTestCase

from eotimeseriesviewer.settings import *


class TestSettings(EOTSVTestCase):

    def test_Dialog(self):
        allValues = values()

        d = SettingsDialog()
        self.assertIsInstance(d, SettingsDialog)

        specs = value(Keys.SensorSpecs)
        defaults = defaultValues()
        self.assertIsInstance(defaults, dict)

        dialogValues = d.values()
        for k in Keys:
            a, b = allValues[k], dialogValues[k]
            if not a is None:
                if isinstance(a, QgsTextFormat):
                    self.assertIsInstance(b, QgsTextFormat)
                    a = a.toMimeData().text()
                    b = b.toMimeData().text()
                self.assertEqual(a, b, msg='Dialog returns {} instead {} for settings key {}'.format(a, b, k))

        defaultMapColor = dialogValues[Keys.MapBackgroundColor]
        dialogValues[Keys.MapBackgroundColor] = QColor('yellow')
        d.setValues(dialogValues)
        self.assertTrue(d.mCanvasColorButton.color() == QColor('yellow'))
        d.onAccept()

        d = SettingsDialog()
        dialogValues = d.values()
        self.assertTrue(dialogValues[Keys.MapBackgroundColor] == QColor('yellow'))
        dialogValues[Keys.MapBackgroundColor] = defaultMapColor
        setValues(dialogValues)

        d = SettingsDialog()
        dialogValues = d.values()
        self.assertTrue(dialogValues[Keys.MapBackgroundColor] == defaultMapColor)

        self.showGui(d)

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

    def test_MapTextFormat(self):

        key = Keys.MapTextFormat
        format0 = defaultValues()[key]
        format1 = defaultValues()[key]
        self.assertIsInstance(format1, QgsTextFormat)
        color1 = QColor('yellow')
        format1.setColor(color1)

        doc = QDomDocument()
        doc.appendChild(format1.writeXml(doc, QgsReadWriteContext()))
        docBA = doc.toByteArray()
        docStr = doc.toString()

        doc2 = QDomDocument()
        doc2.setContent(docBA)
        format2 = QgsTextFormat()
        format2.readXml(doc2.documentElement(), QgsReadWriteContext())
        color2 = format2.color()
        self.assertEqual(color1, color2)

        QS = QSettings('TEST')
        QS.setValue(key.value, doc.toByteArray())

        docBA3 = QS.value(key.value)
        self.assertIsInstance(docBA3, QByteArray)
        doc3 = QDomDocument()
        doc3.setContent(docBA3)
        format3 = QgsTextFormat()
        format3.readXml(doc3.documentElement(), QgsReadWriteContext())
        self.assertEqual(color1, format3.color())

        setValue(key, format1)
        self.assertEqual(format1.color(), value(key).color())

        s = ""

    def test_saveAndRestoreSensorNames(self):

        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
        from eotimeseriesviewer.timeseries import TimeSeriesSource, SensorInstrument, sensorIDtoProperties
        tss = TimeSeriesSource.create(Img_2014_01_15_LC82270652014015LGN00_BOA)
        self.assertIsInstance(tss, TimeSeriesSource)
        sensorID = tss.sid()

        jsonDict = json.loads(sensorID)
        assert isinstance(jsonDict, dict)

        for k in ['nb', 'px_size_x', 'px_size_y', 'dt', 'wl', 'wlu', 'name']:
            self.assertTrue(k in jsonDict.keys())

        # removed: should be done by project settings

if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
    exit(0)
