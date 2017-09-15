# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
                              -------------------
        begin                : 2017-08-04
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
from __future__ import absolute_import
import sys, os, re
from qgis.core import *
from collections import OrderedDict
from qgis.gui import QgsDockWidget
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.utils import loadUi, SpatialExtent

PSUTIL_AVAILABLE = False
try:
    import psutil
    PSUTIL_AVAILABLE = True
except:
    pass


class MapLayerRegistryModel(QAbstractTableModel):

        class LayerWrapper(object):
            def __init__(self, lyr):
                assert isinstance(lyr, QgsMapLayer)
                self.lyr = lyr

        def __init__(self, parent=None):
            super(MapLayerRegistryModel, self).__init__(parent)

            self.cID = '#'
            self.cPID = 'PID'
            self.cName = 'Name'
            self.cSrc = 'Uri'
            self.cType= 'Type'

            self.mLayers = list()
            self.REG = QgsMapLayerRegistry.instance()
            self.REG.layersAdded.connect(self.addLayers)
            self.REG.layersWillBeRemoved .connect(self.removeLayers)
            self.addLayers(self.REG.mapLayers().values())


            s = ""

        def addLayers(self, lyrs):
            self.mLayers.extend(lyrs)
            self.layoutChanged.emit()

        @pyqtSlot(list)
        def removeLayers(self, lyrNames):
            to_remove = [self.REG.mapLayer(name) for name in lyrNames]

            for l in to_remove:
                if l in self.mLayers:
                    i = self.mLayers.index(l)
                    #self.beginRemoveRows(self.createIndex(0,0),i,i)
                    self.mLayers.remove(l)
                    #self.endRemoveRows()
            self.reset()

        def columnNames(self):
            return [self.cID, self.cPID, self.cName, self.cType, self.cSrc]

        def headerData(self, col, orientation, role):
            if orientation == Qt.Horizontal and role == Qt.DisplayRole:
                return self.columnNames()[col]
            elif orientation == Qt.Vertical and role == Qt.DisplayRole:
                return col
            return None

        def sort(self, col, order):
            """Sort table by given column number.
            """
            self.layoutAboutToBeChanged.emit()
            columnName = self.columnNames()[col]
            rev = order == Qt.DescendingOrder
            sortedLyers = None

            if columnName == self.cName:
                sortedLyers = sorted(self.mLayers, key=lambda l: l.name(), reverse=rev)
            elif columnName == self.cSrc:
                sortedLyers = sorted(self.mLayers, key=lambda l: l.source(), reverse=rev)
            elif columnName == self.cID:
                lyrs = self.REG.mapLayers().values()
                sortedLyers = sorted(self.mLayers, key=lambda l: lyrs.index(l), reverse=rev)
            elif columnName == self.cPID:
                sortedLyers = sorted(self.mLayers, key=lambda l: id(l), reverse=rev)
            elif columnName == self.cType:
                types = [QgsVectorLayer, QgsRasterLayer]
                sortedLyers = sorted(self.mLayers, key=lambda l: types.index(type(l)), reverse=rev)

            del self.mLayers[:]
            self.mLayers.extend(sortedLyers)
            self.layoutChanged.emit()

        def rowCount(self, parentIdx=None, *args, **kwargs):
            return len(self.mLayers)

        def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
            return len(self.columnNames())

        def lyr2idx(self, lyr):
            assert isinstance(lyr, QgsMapLayer)
            # return self.createIndex(self.mSpecLib.index(profile), 0)
            # pw = self.mProfileWrappers[profile]
            if not lyr in self.mLayers:
                return None
            return self.createIndex(self.mLayers.index(lyr), 0)

        def idx2lyr(self, index):
            assert isinstance(index, QModelIndex)
            if not index.isValid():
                return None
            return self.mLayers[index.row()]


        def idx2lyrs(self, indices):
            lyrs = [self.idx2lyr(i) for i in indices]
            return [l for l in lyrs if isinstance(l, QgsMapLayer)]

        def data(self, index, role=Qt.DisplayRole):
            if role is None or not index.isValid():
                return None

            columnName = self.columnNames()[index.column()]
            lyr = self.idx2lyr(index)
            value = None
            assert isinstance(lyr, QgsMapLayer)
            if role == Qt.DisplayRole:
                if columnName == self.cPID:
                    value = id(lyr)
                elif columnName == self.cID:
                    value = self.REG.mapLayers().values().index(lyr)
                elif columnName == self.cName:
                    value = lyr.name()
                elif columnName == self.cSrc:
                    value = lyr.source()
                elif columnName in self.cType:
                    value = re.sub('[\'<>]','',str(type(lyr))).split('.')[-1]

            if role == Qt.UserRole:
                value = lyr

            return value

        def flags(self, index):
            if index.isValid():
                columnName = self.columnNames()[index.column()]
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                return flags
            return None



class DataLoadingModel(QAbstractTableModel):

        def __init__(self, parent=None):
            super(DataLoadingModel, self).__init__(parent)

            self.cName = 'Type'
            self.cSamples = 'n'
            self.cAvgAll = u'mean \u0394t(all) [ms]'
            self.cMaxAll = u'max \u0394t(all) [ms]'
            self.cAvg10 = u'mean \u0394t(10) [ms]'
            self.cMax10 = u'max \u0394t(10) [ms]'
            self.cLast = u'last \u0394t [ms]'

            self.mCacheSize = 500
            self.mLoadingTimes = OrderedDict()

        def addTimeDelta(self, name, timedelta):
            assert isinstance(name, str)
            assert isinstance(timedelta, np.timedelta64)
            #if timedelta.astype(float) > 0:
            #print(timedelta)
            if name not in self.mLoadingTimes.keys():
                self.mLoadingTimes[name] = []
            to_remove = max(0,len(self.mLoadingTimes[name]) + 1 - self.mCacheSize)
            if to_remove > 0:
                del self.mLoadingTimes[name][0:to_remove]
            self.mLoadingTimes[name].append(timedelta)

            self.layoutChanged.emit()

        def columnNames(self):
            return [self.cName, self.cSamples, self.cLast, self.cMaxAll, self.cAvgAll, self.cMax10, self.cAvg10]

        def headerData(self, col, orientation, role):
            if orientation == Qt.Horizontal and role == Qt.DisplayRole:
                return self.columnNames()[col]
            elif orientation == Qt.Vertical and role == Qt.DisplayRole:
                return col
            return None

        def sort(self, col, order):
            """Sort table by given column number.
            """
            self.layoutAboutToBeChanged.emit()
            columnName = self.columnNames()[col]
            rev = order == Qt.DescendingOrder
            sortedNames = None
            if columnName == self.cName:
                sortedNames = sorted(self.mLoadingTimes.keys(), reverse=rev)
            elif columnName == self.cSamples:
                sortedNames = sorted(self.mLoadingTimes.keys(), key=lambda n: len(self.mLoadingTimes[n]), reverse=rev)
            elif columnName == self.cAvgAll:
                sortedNames = sorted(self.mLoadingTimes.keys(), key=lambda name:
                    np.asarray(self.mLoadingTimes[name]).mean(), reverse=rev)
            elif columnName == self.cAvg10:
                sortedNames = sorted(self.mLoadingTimes.keys(), key=lambda name:
                    np.asarray(self.mLoadingTimes[name][-10:]).mean(), reverse=rev)

            if sortedNames is not None:
                tmp = OrderedDict([(name, self.mLoadingTimes[name]) for name in sortedNames])
                self.mLoadingTimes.clear()
                self.mLoadingTimes.update(tmp)
                self.layoutChanged.emit()

        def rowCount(self, parentIdx=None, *args, **kwargs):
            return len(self.mLoadingTimes)

        def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
            return len(self.columnNames())

        def type2idx(self, type):
            assert isinstance(type, str)
            if type not in self.mLoadingTimes.keys():
                return None
            return self.createIndex(self.mLoadingTimes.keys().index(type), 0)

        def idx2type(self, index):
            assert isinstance(index, QModelIndex)
            if not index.isValid():
                return None
            return self.mLoadingTimes.keys()[index.row()]

        def data(self, index, role=Qt.DisplayRole):
            if role is None or not index.isValid():
                return None

            columnName = self.columnNames()[index.column()]
            name = self.idx2type(index)
            lTimes = self.mLoadingTimes[name]
            value = None
            if role == Qt.DisplayRole:
                if columnName == self.cName:
                    value = name
                elif columnName == self.cSamples:
                    value = len(lTimes)

                if len(lTimes) > 0:
                    if columnName == self.cAvg10:
                        value = float(np.asarray(lTimes[-10:]).mean().astype(float))
                    elif columnName == self.cAvgAll:
                        value = float(np.asarray(lTimes[:]).mean().astype(float))
                    elif columnName == self.cMax10:
                        value = float(np.asarray(lTimes[-10:]).max().astype(float))
                    elif columnName == self.cMaxAll:
                        value = float(np.asarray(lTimes[:]).max().astype(float))
                    elif columnName == self.cLast:
                        value = float(lTimes[-1].astype(float))

            if role == Qt.UserRole:
                value = lTimes

            return value

        def flags(self, index):
            if index.isValid():
                columnName = self.columnNames()[index.column()]
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                return flags
            return None



class SystemInfoDock(QgsDockWidget, loadUi('systeminfo.ui')):


    def __init__(self, parent=None):
        super(SystemInfoDock, self).__init__(parent)
        self.setupUi(self)

        self.lyrModel = MapLayerRegistryModel()
        self.tableViewMapLayerRegistry.setModel(self.lyrModel)

        self.dataLoadingModel = DataLoadingModel()
        def resetModel():
            self.dataLoadingModel.mLoadingTimes.clear()
            self.dataLoadingModel.layoutChanged.emit()

        self.tableViewDataLoading.setModel(self.dataLoadingModel)
        self.btnResetDataLoadingModel.clicked.connect(resetModel)

        self.labelPSUTIL.setVisible(PSUTIL_AVAILABLE == False)
        if PSUTIL_AVAILABLE:
            self.tableViewSystemParameters.setVisible(True)
            #self.systemInfoModel = SystemInfoModel()
            #self.tableViewSystemParameters.setModel(self.systemInfoModel)
        else:
            self.systemInfoModel = None

    def addTimeDelta(self, type, timedelta):
        self.dataLoadingModel.addTimeDelta(type, timedelta)


if __name__ == '__main__':
    import site, sys
    from timeseriesviewer import utils
    from timeseriesviewer.mapcanvas import MapCanvas
    from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
    qgsApp = utils.initQgisApplication()

    d = SystemInfoDock()
    d.show()
    c = MapCanvas()
    c.sigDataLoadingFinished.connect(lambda p : d.addTimeDelta('MAPCANVAS', p))
    c.show()
    lyr = QgsRasterLayer(Img_2014_01_15_LC82270652014015LGN00_BOA)
    c.setDestinationCrs(lyr.crs())
    c.setExtent(lyr.extent())
    c.setLayers([lyr])
    qgsApp.exec_()