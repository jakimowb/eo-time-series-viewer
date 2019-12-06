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

        d = SettingsDialog()
        self.assertIsInstance(d, SettingsDialog)

        defaults = defaultValues()
        self.assertIsInstance(defaults, dict)

        values = d.values()

        defaultMapColor = values[Keys.MapBackgroundColor]
        values[Keys.MapBackgroundColor] = QColor('yellow')
        d.setValues(values)
        self.assertTrue(d.mCanvasColorButton.color() == QColor('yellow'))
        d.onAccept()

        d = SettingsDialog()
        values = d.values()
        self.assertTrue(values[Keys.MapBackgroundColor] == QColor('yellow'))
        values[Keys.MapBackgroundColor] = defaultMapColor
        setValues(values)

        d = SettingsDialog()
        values = d.values()
        self.assertTrue(values[Keys.MapBackgroundColor] == defaultMapColor)

        if SHOW_GUI:
            r = d.exec_()

            self.assertTrue(r in [QDialog.Accepted, QDialog.Rejected])

            if r == QDialog.Accepted:
                defaults = d.values()
                self.assertIsInstance(defaults, dict)


    def test_SensorModel(self):

        tb = QTableView()
        m = SensorSettingsTableModel()
        tb.setModel(m)
        tb.show()

        if SHOW_GUI:
            QGIS_APP.exec_()


if __name__ == "__main__":
    SHOW_GUI = False and os.environ.get('CI') is None
    unittest.main()
