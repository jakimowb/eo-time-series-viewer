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
from qgis.core import *
from collections import OrderedDict
from qgis.gui import QgsDockWidget
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.utils import loadUi, SpatialExtent


class MapLayerRegistryModel(QAbstractTableModel):

        class LayerWrapper(object):
            def __init__(self, lyr):
                assert isinstance(lyr, QgsMapLayer)
                self.lyr = lyr

        def __init__(self, parent=None):
            super(MapLayerRegistryModel, self).__init__(parent)

            self.cID = '#'
            self.cName = 'Name'
            self.cSrc = 'Uri'
            self.cType= 'Type'

            self.REG = QgsMapLayerRegistry.instance()
            self.REG.layersAdded.connect(self.addLayers)
            self.REG.layersRemoved.connect(self.removeLayers)
            self.mLayers = list()

            s = ""

        def addLayers(self, lyrs):
            self.mLayers.extend(lyrs)
            self.layoutChanged.emit()

        def removeLayers(self, lyr):
            to_remove = [l for l in self.mLayers if l == lyr]
            for l in to_remove:
                self.mLayers.remove(l)
            self.layoutChanged.emit()

        def columnNames(self):
            return [self.cID, self.cName, self.cType, self.cSrc]

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
            assert isinstance(lyr, QgsMapLayer)
            if role == Qt.DisplayRole:
                if columnName == self.cID:
                    value = id(lyr)
                elif columnName == self.cName:
                    value = lyr.name()
                elif columnName == self.cSrc:
                    value = lyr.source()
                elif columnName in self.cType:
                    value = str(type(lyr))

            if role == Qt.UserRole:
                value = lyr

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

if __name__ == '__main__':
    import site, sys
    from timeseriesviewer import utils
    from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
    qgsApp = utils.initQgisApplication()

    REG = QgsMapLayerRegistry.instance()
    REG.addMapLayer(QgsRasterLayer(Img_2014_01_15_LC82270652014015LGN00_BOA))
    d = SystemInfoDock()
    d.show()

    qgsApp.exec_()