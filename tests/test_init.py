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

import os, sys, unittest, configparser
from eotimeseriesviewer.tests import initQgisApplication, TestObjects
APP = initQgisApplication()

from eotimeseriesviewer.main import *


SHOW_GUI = True and os.environ.get('CI') is None

class TestInit(unittest.TestCase):


    def test_loadexampledata(self):
        TSV = TimeSeriesViewer()
        TSV.show()
        TSV.loadExampleTimeSeries()

        if SHOW_GUI:
            APP.exec_()




if __name__ == '__main__':
    unittest.main()
