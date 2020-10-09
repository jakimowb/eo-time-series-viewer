# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/searchfiledialog.py

    A dialog to search multiple files, fast.
    ---------------------
    Beginning            : 2020-08-17
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import os
import sys
import importlib
import re
import fnmatch
import io
import zipfile
import pathlib
import warnings
import collections
import copy
import shutil
import typing
import gc
import sip
import traceback
import calendar
import datetime
from qgis.core import *
from qgis.core import QgsField, QgsVectorLayer, QgsRasterLayer, QgsRasterDataProvider, QgsMapLayer, QgsMapLayerStore, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsRectangle, QgsPointXY, QgsProject, \
    QgsMapLayerProxyModel, QgsRasterRenderer, QgsMessageOutput, QgsFeature, QgsTask, Qgis, QgsGeometry
from qgis.gui import *
from qgis.gui import QgisInterface, QgsDialog, QgsMessageViewer, QgsMapLayerComboBox, QgsMapCanvas

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import *
from qgis.core import *
from qgis.gui import *
from qgis.gui import QgsFileWidget
from osgeo import gdal, ogr, osr, gdal_array
import numpy as np
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QDialogButtonBox, QLabel, QGridLayout, QMainWindow
from . import DIR_UI_FILES
from .utils import loadUi


class SearchFilesDialog(QDialog):
    """
    A dialog to select multiple files, fast
    """
    sigFilesFound = pyqtSignal(list)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(DIR_UI_FILES / 'searchfilesdialog.ui', self)

        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)
        self.btnRecursive.setDefaultAction(self.optionRecursive)
        self.btnReload.setDefaultAction(self.actionReload)

        self.fileWidget: QgsFileWidget
        #self.fileWidget.setReadOnly(True)
        self.fileWidget.setStorageMode(QgsFileWidget.GetDirectory)
        self.fileWidget.fileChanged.connect(self.reloadFiles)

        s = ""

    def validate(self):
        s = ""

    def reloadFiles(self, *args):
        print('#RELOAD FILES')

