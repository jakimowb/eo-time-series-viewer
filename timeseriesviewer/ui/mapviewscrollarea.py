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
from __future__ import absolute_import

from PyQt4.QtCore import pyqtSignal
from PyQt4.QtGui import QScrollArea

class MapViewScrollArea(QScrollArea):

    sigResized = pyqtSignal()
    def __init__(self, *args, **kwds):
        super(MapViewScrollArea, self).__init__(*args, **kwds)

    def resizeEvent(self, event):
        super(MapViewScrollArea, self).resizeEvent(event)
        self.sigResized.emit()
