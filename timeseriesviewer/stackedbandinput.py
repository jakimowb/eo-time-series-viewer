# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    stackedbandinput.py

    Sometimes time-series-data is written out as stacked band images, having one observation per band.
    This module helps to use such data as EOTS input.
    ---------------------
    Date                 : June 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import os, re, tempfile, pickle, copy, shutil, locale, uuid, csv, io
from collections import OrderedDict
from qgis.core import *
from qgis.gui import *
from qgis.utils import qgsfunction
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import QgsField, QgsFields, QgsFeature, QgsMapLayer, QgsVectorLayer, QgsConditionalStyle
from qgis.gui import QgsMapCanvas, QgsDockWidget
from pyqtgraph.widgets.PlotWidget import PlotWidget
from pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from pyqtgraph.graphicsItems.PlotItem import PlotItem
import pyqtgraph.functions as fn
import numpy as np
from osgeo import gdal, gdal_array

from timeseriesviewer.utils import *
#from timeseriesviewer.virtualrasters import *
from timeseriesviewer.models import *
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleDialog, MARKERSYMBOLS2QGIS_SYMBOLS
import timeseriesviewer.mimedata as mimedata

