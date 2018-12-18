# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 10.01.2018
    Copyright            : (C) 2018 by Benjamin Jakimow
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
import os
from timeseriesviewer.tests import initQgisApplication

from qgis.core import QgsApplication
from qgis.gui import QgsCollapsibleGroupBox
from PyQt5.QtGui import *
from PyQt5.QtCore import *



app = initQgisApplication()
app.setPkgDataPath('D:/Repositories/QGIS')
p = app.getThemeIcon("/mIconCollapse.svg" )
gb = QgsCollapsibleGroupBox()
gb.setTitle('TEST')
gb.setWindowIconText('x')
gb.show()
s = ""

app.exec_()