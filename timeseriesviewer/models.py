# -*- coding: utf-8 -*-
"""
***************************************************************************
    models
    ---------------------
    Date                 : Februar 2018
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
# noinspection PyPep8Naming
from __future__ import unicode_literals, absolute_import

from qgis import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *




def currentComboBoxValue(comboBox, role=Qt.DisplayRole):
    assert isinstance(comboBox, QComboBox)
    i = comboBox.currentIndex()
    if i < 0:
        return None
    return comboBox.itemData(i, role=Qt.UserRole)

def setCurrentComboBoxValue(comboBox, value):
    pass

class Option(object):

    def __init__(self, value, name, tooltip=None, icon=None):

        self.mValue = value
        if name is None:
            name = str(value)
        self.mName = name
        self.mTooltip = tooltip
        self.mIcon = None

    def __eq__(self, other):
        if not isinstance(other, Option):
            return False
        else:
            return other.mValue == self.mValue


class OptionListModel(QAbstractListModel):
    def __init__(self, options=None, parent=None):
        super(OptionListModel, self).__init__(parent)

        self.mOptions = []

        self.insertOptions(options)


    def addOption(self, option):
        self.insertOptions([option])

    def addOptions(self, options):
        assert isinstance(options, list)
        self.insertOptions(options)

    sigOptionsInserted = pyqtSignal(list)
    def insertOptions(self, options, i=None):
        if options is None:
            return
        if not isinstance(options, list):
            options = [options]
        assert isinstance(options, list)

        options = [self.o2o(o) for o in options]
        options = [o for o in options if o not in self.mOptions]

        l = len(options)
        if l > 0:
            if i is None:
                i = len(self.mOptions)
            self.beginInsertRows(QModelIndex(), i, i + len(options) - 1)
            for o in options:
                self.mOptions.insert(i, o)
                i += 1
            self.endInsertRows()
            self.sigOptionsInserted.emit(options)


    def o2o(self,  value):
        if not isinstance(value, Option):
            value = Option(value, '{}'.format(value))
        return value

    sigOptionsRemoved = pyqtSignal(list)
    def removeOptions(self, options):
        options = [self.o2o(o) for o in options]
        options = [o for o in options if o in self.mOptions]
        removed = []
        for o in options:
            row = self.mOptions.index(o)
            self.beginRemoveRows(QModelIndex(), row, row)
            o2 = self.mOptions[row]
            self.mOptions.remove(o2)
            removed.append(o2)
            self.endRemoveRows()

        if len(removed) > 0:
            self.sigOptionsRemoved.emit(removed)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mOptions)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1

    def idx2option(self, index):
        if index.isValid():
            return self.mOptions[index.row()]
        return None

    def option2idx(self, option):
        if isinstance(option, Option):
            option = option.mValue

        idx = self.createIndex(None, -1, 0)
        for i, o in enumerate(self.mOptions):
            assert isinstance(o, Option)
            if o.mValue == option:
                idx.setRow(i)
                break
        return idx



    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mOptions)) or (index.row() < 0):
            return None
        option = self.idx2option(index)
        assert isinstance(option, Option)
        result = None
        if role == Qt.DisplayRole:
            result = '{}'.format(option.mName)
        elif role == Qt.ToolTipRole:
            result = '{}'.format(option.mName if option.mTooltip is None else option.mTooltip)
        elif role == Qt.DecorationRole:
            result = '{}'.format(option.mIcon)
        elif role == Qt.UserRole:
            return option
        return result


if __name__ == '__main__':
    import site, sys
    from timeseriesviewer.utils import initQgisApplication

    DEBUG = True
    qgsApp = initQgisApplication()
    m = OptionListModel()

    cb = QComboBox()
    cb.setModel(m)

    m.addOption(Option('v','value','tooltip'))
    m.addOption(Option('v2', 'value2', 'tooltip2'))
    cb.show()

    print(currentComboBoxValue(cb))
    qgsApp.exec_()
