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

class InputStackInfo(object):

    def __init__(self, dataset):
        if not isinstance(dataset, gdal.Dataset):
            dataset = gdal.Open(dataset)
        assert isinstance(dataset, gdal.Dataset)

        self.mMetadataDomains = dataset.GetMetadataDomainList()
        self.mMetaData = OrderedDict()
        for domain in self.mMetadataDomains:
            self.mMetaData[domain] = dataset.GetMetadata_Dict(domain)

        self.ns = dataset.RasterXSize
        self.nl = dataset.RasterYSize
        self.nb = dataset.RasterCount

        self.wkt = dataset.GetProjection()
        self.gt = dataset.GetGeoTransform()

        self.path = dataset.GetFileList()[0]

        self.bandName = os.path.splitext(os.path.basename(self.path))[0]

    def structure(self):
        return (self.ns, self.nl, self.nb, self.gt, self.wkt)

class InputStackTableModel(QAbstractTableModel):



    def __init__(self, parent=None):

        super(InputStackTableModel, self).__init__(parent)
        self.mStackImages = []

        self.cnFile = 'File'
        self.cn_fileproperties = 'Properties'
        self.cn_ns = 'Samples'
        self.cn_nl = 'Lines'
        self.cn_nb = 'Bands'
        self.cb_name = 'Band Name'
        self.cn_wl = 'Wavelength'
        self.mColumnNames = [self.cnFile, self.cn_fileproperties, self.cn_wl]

    def columnName(self, i):
        if isinstance(i, QModelIndex):
            i = i.column()
        return self.mColumnNames[i]

    def flags(self, index):
        if index.isValid():
            columnName = self.columnName(index)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in [self.cn_name, self.cn_wl]: #allow check state
                flags = flags | Qt.ItemIsUserCheckable

            return flags
            #return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None


    def rowCount(self, parent=None):
        return len(self.mStackImages)

    def columnCount(self, parent: QModelIndex):
        return len(self.mColumnNames)

    def insertSources(self, paths, i=None):

        if i == None:
            i = self.rowCount()

        if not isinstance(paths, list):
            paths = [paths]

        infos = []
        for p in paths:
            assert isinstance(p, str)
            ds = gdal.Open(p)
            if isinstance(ds, gdal.Dataset):
                info = InputStackInfo(ds)
                infos.append(info)

        if len(infos) > 0:

            self.beginInsertRows(QModelIndex(), i, i+len(infos)-1)
            for j, info in enumerate(infos):
                self.mStackImages.insert(i+j, info)
            self.endInsertRows()




    def isValid(self):
        l = len(self.mStackImages)
        if l == 0:
            return False
        ref = self.mStackImages[0]
        assert isinstance(ref, InputStackInfo)

        #all input stacks need to have the same characteristic
        for stackInfo in self.mStackImages[1:]:
            assert isinstance(stackInfo, InputStackInfo)
            if not ref.structure() == stackInfo.structure():
                return False
        return True


    def data(self, index: QModelIndex, role: int):


        if not index.isValid():
            return None

        info = self.mStackImages[index.column()]
        assert isinstance(info, InputStackInfo)
        cname = self.columnName(index)
        if role == Qt.DisplayRole:
            if cname == self.cnFile:
                return info.path
            elif cname == self.cn_fileproperties:
                return str(info.structure())
            elif cname == self.cn_wl:
                return str(info.structure())
            elif cname == self.cb_name:
                return info.bandName


        return None


class OutputImageModel(QAbstractTableModel):

    def __init__(self, parent=None):
        pass




    def outputVRTs(self):

        pass




class StackedBandInputDialog(QDialog, loadUI('stackedinputdatadialog.ui')):

    def __init__(self, parent=None):

        super(StackedBandInputDialog, self).__init__(parent=parent)
        self.setupUi(self)


        self.tableModelInputStacks = InputStackTableModel()
        self.tableViewSourceStacks.setModel(self.tableModelInputStacks)
        sm = self.tableViewSourceStacks.selectionModel()
        assert isinstance(sm, QItemSelectionModel)
        sm.selectionChanged.connect(self.onSourceStackSelectionChanged)

        self.initActions()

    def initActions(self):

        self.actionAddSourceStack.triggered.connect(self.onAddSource)
        self.actionRemoveSourceStack.triggered.connect(self.onRemoveSources)

        self.btnAddSourceStack.setDefaultAction(self.actionAddSourceStack)
        self.btnRemoveSourceStack.setDefaultAction(self.actionRemoveSourceStack)


    def onAddSource(self, *args):
        pass

    def addSources(self, paths):
        self.tableModelInputStacks.insertSources(paths)

    def onRemoveSources(self, *args):
        pass
    def onSourceStackSelectionChanged(self, selected, deselected):

        pass



    def validate(self):


        isValid = True



        self.buttonBox


