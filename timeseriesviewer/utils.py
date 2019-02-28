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

import os, sys, math, re, io, fnmatch, uuid


from collections import defaultdict
from qgis.core import *
from qgis.gui import *
import qgis.utils
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtXml import QDomDocument
from PyQt5 import uic
from osgeo import gdal, ogr

from qps.utils import *

import weakref
import numpy as np

jp = os.path.join
dn = os.path.dirname

from timeseriesviewer import DIR_UI, DIR_REPO
from timeseriesviewer import messageLog
import timeseriesviewer
MAP_LAYER_STORES = [QgsProject.instance()]

def qgisInstance():
    """
    If existent, returns the QGIS Instance.
    :return: QgisInterface | None
    """

    from timeseriesviewer.main import TimeSeriesViewer
    if isinstance(qgis.utils.iface, QgisInterface) and \
        not isinstance(qgis.utils.iface, TimeSeriesViewer):
        return qgis.utils.iface
    else:
        return None



def settings():
    return QSettings('HU-Berlin', 'EO Time Series Viewer')


