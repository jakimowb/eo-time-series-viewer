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

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *


class MapViewScrollArea(QScrollArea):

    sigResized = pyqtSignal()
    def __init__(self, *args, **kwds):
        super(MapViewScrollArea, self).__init__(*args, **kwds)

    def resizeEvent(self, event):
        super(MapViewScrollArea, self).resizeEvent(event)
        self.sigResized.emit()

    def distanceToCenter(self, widget:QWidget)->int:
        # self.visibleRegion().boundingRect().isValid()
        halfSize = widget.size() * 0.5
        centerInParent = widget.mapToParent(QPoint(halfSize.width(), halfSize.height()))
        r = self.viewport().rect()
        centerViewPort = QPoint(int(r.x() + r.width() *0.5 ), int(r.y()+r.height()*0.5))

        diff = centerInParent - centerViewPort
        return diff.manhattanLength()