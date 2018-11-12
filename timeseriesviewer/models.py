# -*- coding: utf-8 -*-
"""
***************************************************************************
    trees
    ---------------------
    Date                 : November 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
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


import os, pickle, copy

from collections import OrderedDict

from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from osgeo import gdal, osr


def currentComboBoxValue(comboBox):
    assert isinstance(comboBox, QComboBox)
    if isinstance(comboBox.model(), OptionListModel):
        o = comboBox.currentData(Qt.UserRole)
        assert isinstance(o, Option)
        return o.mValue
    else:
        return cb.currentData()

def setCurrentComboBoxValue(comboBox, value):
    """
    Sets a QComboBox to the value `value`, if it exists in the underlying item list
    :param comboBox: QComboBox
    :param value: any type
    :return: True | False
    """
    assert isinstance(comboBox, QComboBox)
    model = comboBox.model()
    if not isinstance(model, OptionListModel):
        i = comboBox.findData(value, role=Qt.DisplayRole)
        if i == -1:
            i = comboBox.findData(value, role=Qt.UserRole)

        if i != -1:
            comboBox.setCurrentIndex(i)
            return True
    else:
        if not isinstance(value, Option):
            value = Option(value)
        for i in range(comboBox.count()):
            option = comboBox.itemData(i, role=Qt.UserRole)
            if option == value:
                comboBox.setCurrentIndex(i)
                return True
    return False


class Option(object):

    def __init__(self, value, name=None, tooltip='', icon=None, **kwargs ):

        self.mValue = value
        if name is None:
            name = str(value)
        self.mName = name
        self.mTooltip = tooltip
        self.mIcon = icon

        for k, v in kwargs.items():
            assert k not in self.__dict__.keys()
            self.__dict__[k] = v

    def value(self):
        return self.mValue

    def name(self):
        return self.mName

    def tooltip(self):
        return self.mTooltip

    def icon(self):
        return self.mIcon

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

    def __iter__(self):
        return iter(self.mOptions)

    def __len__(self):
        return len(self.mOptions)


    def containsValue(self, value):
        return value in self.optionValues()

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


    def optionNames(self):
        return [o.mName for o in self.mOptions]

    def optionValues(self):
        return [o.mValue for o in self.mOptions]




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

