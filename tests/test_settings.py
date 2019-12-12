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
from eotimeseriesviewer.tests import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from eotimeseriesviewer.mapcanvas import *
from eotimeseriesviewer import *
from eotimeseriesviewer.utils import *
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication()

from eotimeseriesviewer.settings import *
SHOW_GUI = True and os.environ.get('CI') is None

class testclassSettingsTest(unittest.TestCase):
    """Test resources work."""
    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass

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

        if SHOW_GUI:
            r = d.exec_()

            self.assertTrue(r in [QDialog.Accepted, QDialog.Rejected])

            if r == QDialog.Accepted:
                defaults = d.values()
                self.assertIsInstance(defaults, dict)


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

        if SHOW_GUI:
            QGIS_APP.exec_()

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

        oldname0 = sensorName(sensorID)
        sensor = SensorInstrument(sensorID)
        oldname = sensor.name()
        if oldname0 is not None:
            self.assertEqual(oldname0, oldname, )

        self.assertIsInstance(oldname, str)
        self.assertIsInstance(sensor, SensorInstrument)
        name1 = 'S1'+str(uuid.uuid4())
        sensor.setName(name1)

        savedName = sensorName(sensorID)
        self.assertIsInstance(savedName, str)
        self.assertEqual(savedName, name1)


        #sensor.setName(oldname)
        #name2 = sensorName(sensorID)
        #self.assertEqual(oldname, name2)





if __name__ == "__main__":
    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()
