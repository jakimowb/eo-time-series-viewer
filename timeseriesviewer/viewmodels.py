# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import sys, os
from qgis.core import *
from PyQt5.QtCore import *
from timeseriesviewer import *

import numpy as np
import pyqtgraph as pg
from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument






if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from tests import initQgisApplication
    qapp = initQgisApplication()

    import example

    vl = QgsVectorLayer(example.exampleEvents)

    store = QgsMapLayerStore()
    store.addMapLayer(vl)



    box = QgsMapLayerComboBox()
    box.model().sourceModel().addLayers([vl])
    box.show()
    qapp.exec_()
