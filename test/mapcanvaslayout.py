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
from __future__ import absolute_import

from timeseriesviewer.utils import initQgisApplication
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from timeseriesviewer.mapcanvas import MapCanvas

app = initQgisApplication()

frame = QFrame()
frame.setLayout(QVBoxLayout())
frame.layout().addWidget(QProgressBar())
frame.layout().addWidget(QLabel('Info text'))
for i in range(2):
    m = MapCanvas(frame)
    m.setFixedSize(QSize(100,100))
    frame.layout().addWidget(m)
frame.sizeHint = lambda : m.size()
frame.show()

s = ""

app.exec_()