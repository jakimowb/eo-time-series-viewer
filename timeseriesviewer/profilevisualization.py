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
import os, sys, pickle, datetime
from collections import OrderedDict
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.timeseries import *
from timeseriesviewer.utils import SpatialExtent, SpatialPoint, px2geo
from timeseriesviewer.ui.docks import TsvDockWidgetBase, loadUI
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleButton
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderTask
from timeseriesviewer.sensorvisualization import SensorListModel

import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph import AxisItem


import datetime

from osgeo import gdal, gdal_array
import numpy as np

DEBUG = False

def getTextColorWithContrast(c):
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')

class DateTimeAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(DateTimeAxis, self).__init__(*args, **kwds)

    def logTickStrings(self, values, scale, spacing):
        s = ""


    def tickStrings(self, values, scale, spacing):
        strns = []

        if len(values) == 0:
            return []
        #assert isinstance(values[0],
        values = [num2date(v) for v in values]
        rng = max(values)-min(values)
        ndays = rng.astype(int)

        strns = []

        for v in values:
            if ndays == 0:
                strns.append(v.astype(str))
            else:
                strns.append(v.astype(str))

        return strns

    def tickValues(self, minVal, maxVal, size):
        d = super(DateTimeAxis, self).tickValues(minVal, maxVal, size)

        return d





class _SensorPoints(pg.PlotDataItem):
    def __init__(self, *args, **kwds):
        super(_SensorPoints, self).__init__(*args, **kwds)
        # menu creation is deferred because it is expensive and often
        # the user will never see the menu anyway.
        self.menu = None

    def boundingRect(self):
        return super(SensorPoints,self).boundingRect()

    def paint(self, p, *args):
        super(SensorPoints, self).paint(p, *args)


    # On right-click, raise the context menu
    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def getContextMenus(self, event=None):
        if self.menu is None:
            self.menu = QMenu()
            self.menu.setTitle(self.name + " options..")

            green = QAction("Turn green", self.menu)
            green.triggered.connect(self.setGreen)
            self.menu.addAction(green)
            self.menu.green = green

            blue = QAction("Turn blue", self.menu)
            blue.triggered.connect(self.setBlue)
            self.menu.addAction(blue)
            self.menu.green = blue

            alpha = QWidgetAction(self.menu)
            alphaSlider = QSlider()
            alphaSlider.setOrientation(QtCore.Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu


class TemporalProfilePlotDataItem(pg.PlotDataItem):

    def __init__(self, plotStyle, parent=None):
        assert isinstance(plotStyle, TemporalProfilePlotStyle)


        super(TemporalProfilePlotDataItem, self).__init__([], [], parent=parent)
        self.mPlotStyle = plotStyle
        self.mPlotStyle.sigUpdated.connect(self.updateStyle)
        self.setClickable(True)
        self.updateData()
        self.updateStyle()

    def updateData(self):
        TP = self.mPlotStyle.temporalProfile()
        sensor = self.mPlotStyle.sensor()
        if isinstance(TP, TemporalProfile) and isinstance(sensor, SensorInstrument):
            x, y = TP.dataFromExpression(self.mPlotStyle.sensor(), self.mPlotStyle.expression())
            if len(y) > 0:
                self.setData(x=x, y=y)
            else:
                self.setData(x=None, y=None)
            self.update()

    def updateStyle(self):
        """
        Updates visibility properties
        """
        self.setVisible(self.mPlotStyle.isVisible())
        self.setPen(self.mPlotStyle.linePen)
        self.setBrush(self.mPlotStyle.markerBrush)

        #self.setFillBrush(self.mPlotStyle.)

    def setClickable(self, b, width=None):
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setColor(self, color):
        if not isinstance(color, QColor):

            color = QColor(color)
        self.setPen(color)

    def pen(self):

        return fn.mkPen(self.opts['pen'])

    def color(self):
        return self.pen().color()

        # On right-click, raise the context menu

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))
        return True

        # This method will be called when this item's _children_ want to raise
        # a context menu that includes their parents' menus.

    def getContextMenus(self, event=None):
        if self.menu is None:
            self.menu = QMenu()
            self.menu.setTitle(self.name + " options..")

            green = QAction("Turn green", self.menu)
            green.triggered.connect(self.setGreen)
            self.menu.addAction(green)
            self.menu.green = green

            blue = QAction("Turn blue", self.menu)
            blue.triggered.connect(self.setBlue)
            self.menu.addAction(blue)
            self.menu.green = blue

            alpha = QWidgetAction(self.menu)
            alphaSlider = QSlider()
            alphaSlider.setOrientation(QtCore.Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu

    def setLineWidth(self, width):
        pen = pg.mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)



class PlotSettingsWidgetDelegate(QStyledItemDelegate):
    """

    """
    def __init__(self, tableView, timeSeries, temporalProfileListModel, parent=None):

        super(PlotSettingsWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.tableView = tableView
        self.timeSeries = timeSeries
        self.temporalProfileListModel = temporalProfileListModel

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)
        model = tableView.model()

        assert isinstance(model, PlotSettingsModel)
        for c in [model.cnSensor, model.cnExpression, model.cnStyle,model.cnTemporalProfile]:
            i = model.columNames.index(c)
            tableView.setItemDelegateForColumn(i, self)

    def getColumnName(self, index):
        assert index.isValid()
        model = index.model()
        assert isinstance(model, PlotSettingsModel)
        return model.columNames[index.column()]
    """
    def sizeHint(self, options, index):
        s = super(ExpressionDelegate, self).sizeHint(options, index)
        exprString = self.tableView.model().data(index)
        l = QLabel()
        l.setText(exprString)
        x = l.sizeHint().width() + 100
        s = QSize(x, s.height())
        return self._preferedSize
    """

    def createEditor(self, parent, option, index):
        cname = self.getColumnName(index)
        model = self.tableView.model()
        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel):
            plotStyle = model.idx2plotStyle(index)
            if isinstance(plotStyle, TemporalProfilePlotStyle):
                if cname == model.cnExpression:
                    w = QgsFieldExpressionWidget(parent=parent)

                    #todo: w.setLayer(sv.memLyr)
                    w.setExpressionDialogTitle('Values')
                    w.setToolTip('Set an expression to calculate the plot y-values.')
                    w.fieldChanged.connect(lambda : self.checkData(w, w.expression()))

                elif cname == model.cnStyle:
                    w = PlotStyleButton(parent=parent)
                    w.setPlotStyle(plotStyle)
                    w.setToolTip('Set style.')
                    w.sigPlotStyleChanged.connect(lambda: self.checkData(w, w.plotStyle()))

                elif cname == model.cnSensor:
                    w = QComboBox(parent=parent)
                    m = SensorListModel(self.timeSeries)
                    w.setModel(m)

                elif cname == model.cnTemporalProfile:
                    w = QComboBox(parent=parent)
                    w.setModel(self.temporalProfileListModel)
                else:
                    raise NotImplementedError()
        return w

    def checkData(self, w, expression):
        if isinstance(w, QgsFieldExpressionWidget):
            assert expression == w.expression()
            assert w.isExpressionValid(expression) == w.isValidExpression()

            if w.isValidExpression():
                self.commitData.emit(w)
            else:
                s = ""
                #print(('Delegate commit failed',w.asExpression()))
        if isinstance(w, PlotStyleButton):

            self.commitData.emit(w)

    def setEditorData(self, editor, index):
        cname = self.getColumnName(index)
        model = self.tableView.model()

        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel):

            cname = self.getColumnName(index)
            if cname == model.cnExpression:
                lastExpr = index.model().data(index, Qt.DisplayRole)
                assert isinstance(editor, QgsFieldExpressionWidget)
                editor.setProperty('lastexpr', lastExpr)
                editor.setField(lastExpr)

            elif cname == model.cnStyle:
                style = index.data()
                assert isinstance(editor, PlotStyleButton)
                editor.setPlotStyle(style)

            elif cname == model.cnSensor:
                assert isinstance(editor, QComboBox)
                m = editor.model()
                assert isinstance(m, SensorListModel)
                sensor = index.data(role=Qt.UserRole)
                if isinstance(sensor, SensorInstrument):
                    idx = m.sensor2idx(sensor)
                    editor.setCurrentIndex(idx.row())
            elif cname == model.cnTemporalProfile:
                assert isinstance(editor, QComboBox)
                m = editor.model()
                assert isinstance(m, TemporalProfileCollectionListModel)
                TP = index.data(role=Qt.UserRole)
                if isinstance(TP, TemporalProfile):
                    idx = m.tp2idx(TP)
                    editor.setCurrentIndex(idx)
            else:
                raise NotImplementedError()

    def setModelData(self, w, model, index):
        cname = self.getColumnName(index)
        model = self.tableView.model()

        if index.isValid() and isinstance(model, PlotSettingsModel):
            if cname == model.cnExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression() and expr != exprLast:
                    model.setData(index, w.asExpression(), Qt.EditRole)

            elif cname == model.cnStyle:
                assert isinstance(w, PlotStyleButton)
                model.setData(index, w.plotStyle(), Qt.UserRole)

            elif cname == model.cnSensor:
                assert isinstance(w, QComboBox)
                sensor = w.itemData(w.currentIndex(), role=Qt.UserRole)
                assert isinstance(sensor, SensorInstrument)
                model.setData(index, sensor, Qt.EditRole)

            elif cname == model.cnTemporalProfile:
                assert isinstance(w, QComboBox)
                TP = w.itemData(w.currentIndex(), role=Qt.UserRole)
                assert isinstance(TP, TemporalProfile)
                model.setData(index, TP, Qt.EditRole)

            else:
                raise NotImplementedError()


class SensorPixelDataMemoryLayer(QgsVectorLayer):

    def __init__(self, sensor, crs=None):
        assert isinstance(sensor, SensorInstrument)
        if crs is None:
            crs = QgsCoordinateReferenceSystem('EPSG:4862')
        uri = 'Point?crs={}'.format(crs.authid())
        super(SensorPixelDataMemoryLayer, self).__init__(uri, 'Pixels_sensor_' + sensor.name(), 'memory', False)
        self.mSensor = sensor

        #initialize fields
        assert self.startEditing()
        # standard field names, types, etc.
        fieldDefs = [('pxid', QVariant.String, 'integer'),
                     ('date', QVariant.String, 'char'),
                     ('doy', QVariant.Int, 'integer'),
                     ('geo_x', QVariant.Double, 'decimal'),
                     ('geo_y', QVariant.Double, 'decimal'),
                     ('px_x', QVariant.Int, 'integer'),
                     ('px_y', QVariant.Int, 'integer'),
                     ]
        # one field for each band
        for b in range(sensor.nb):
            fName = 'b{}'.format(b + 1)
            fieldDefs.append((fName, QVariant.Double, 'decimal'))

        # initialize fields
        for fieldDef in fieldDefs:
            field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
            self.addAttribute(field)
        self.commitChanges()

    def sensor(self):
        return self.mSensor

    def nPixels(self):
        raise NotImplementedError()

    def dates(self):
        raise NotImplementedError()


class TemporalProfileCollectionListModel(QAbstractListModel):


    def __init__(self, temporalProfileCollection, *args, **kwds):

        super(TemporalProfileCollectionListModel, self).__init__(*args, **kwds)
        assert isinstance(temporalProfileCollection, TemporalProfileCollection)

        self.mTPColl = temporalProfileCollection
        self.mTPColl.rowsAboutToBeInserted.connect(self.rowsAboutToBeInserted)
        self.mTPColl.rowsInserted.connect(self.rowsInserted.emit)
        self.mTPColl.rowsAboutToBeRemoved.connect(self.rowsAboutToBeRemoved)
        self.mTPColl.rowsRemoved.connect(self.rowsRemoved.emit)

    def idx2tp(self, *args, **kwds):
        return self.mTPColl.idx2tp(*args, **kwds)

    def tp2idx(self, *args, **kwds):
        return self.mTPColl.tp2idx(*args, **kwds)

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            #return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def rowCount(self, *args, **kwds):
        return self.mTPColl.rowCount(*args, **kwds)


    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        TP = self.mTPColl.data(index, role=Qt.UserRole)
        value = None
        if isinstance(TP, TemporalProfile):
            if role == Qt.DisplayRole:
                value = '{}'.format(TP.name())
            elif role == Qt.ToolTipRole:
                value = '#{} "{}" {}'.format(TP.mID, TP.name(), TP.mCoordinate)
            elif role == Qt.UserRole:
                value = TP

        return value

class TemporalProfileCollection(QAbstractTableModel):
    """
    A collection to store the TemporalProfile data delivered by a PixelLoader
    """

    #sigSensorAdded = pyqtSignal(SensorInstrument)
    #sigSensorRemoved = pyqtSignal(SensorInstrument)
    #sigPixelAdded = pyqtSignal()
    #sigPixelRemoved = pyqtSignal()

    def __init__(self, ):
        super(TemporalProfileCollection, self).__init__()
        #self.sensorPxLayers = dict()
        #self.memLyrCrs = QgsCoordinateReferenceSystem('EPSG:4326')
        self.newDataFlag = False

        self.mcnID = 'id'
        self.mcnCoordinate = 'Coordinate'
        self.mcnLoaded = 'Loading'
        self.mcnName = 'Name'
        self.mColumNames = [self.mcnName, self.mcnLoaded, self.mcnCoordinate]

        crs = QgsCoordinateReferenceSystem('EPSG:4862')
        uri = 'Point?crs={}'.format(crs.authid())

        self.TS = None
        self.mLocations = QgsVectorLayer(uri, 'LOCATIONS', 'memory', False)
        self.mTemporalProfiles = []
        self.mTPLookupSpatialPoint = {}
        self.mTPLookupID = {}
        self.mCurrentTPID = 0
        self.mMaxProfiles = 10

        self.nextID = 0

    def __len__(self):
        return len(self.mTemporalProfiles)

    def __iter__(self):
        return iter(self.mTemporalProfiles)

    def __getitem__(self, slice):
        return self.mTemporalProfiles[slice]

    def __contains__(self, item):
        return item in self.mTemporalProfiles

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mTemporalProfiles)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.mColumNames)

    def idx2tp(self, index):
        if index.isValid():
            return self.mTemporalProfiles[index.row()]
        return None

    def tp2idx(self, temporalProfile):
        assert isinstance(temporalProfile, TemporalProfile)
        idx = self.createIndex(None, -1, 0)
        if temporalProfile in self.mTemporalProfiles:
            idx.setRow(self.mTemporalProfiles.index(temporalProfile))
        return idx

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumNames[index.column()]
        TP = self.idx2tp(index)
        if not isinstance(TP, TemporalProfile):
            return None
        #self.mColumNames = ['id','coordinate','loaded']
        if role == Qt.DisplayRole:
            if columnName == self.mcnID:
                value = TP.mID
            elif columnName == self.mcnName:
                value = TP.name()
            elif columnName == self.mcnCoordinate:
                value = '{}'.format(TP.mCoordinate)
            elif columnName == self.mcnLoaded:
                nIs, nMax = TP.loadingStatus()
                if nMax > 0:
                    value = '{}/{} ({:0.2f} %)'.format(nIs, nMax, float(nIs) / nMax * 100)
        elif role == Qt.EditRole:
            if columnName == self.mcnName:
                value = TP.name()
        elif role == Qt.ToolTipRole:
            if columnName == self.mcnID:
                value = 'ID Temporal Profile'
            elif columnName == self.mcnName:
                value = TP.name()
            elif columnName == self.mcnCoordinate:
                value = '{}'.format(TP.mCoordinate)
            elif columnName == self.mcnLoaded:
                nIs, nMax = TP.loadingStatus()
                value = '{}'.format(TP.mCoordinate)
        elif role == Qt.UserRole:
            value = TP

        return value

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            cName = self.mColumNames[index.column()]
            if cName == self.mcnName:
                flags = flags | Qt.ItemIsEditable

            return flags
            #return item.qt_flags(index.column())
        return None


    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        cName = self.mColumNames[index.column()]
        TP = self.idx2tp(index)
        if isinstance(TP, TemporalProfile):
            if role == Qt.EditRole and cName == self.mcnName:
                if len(value) == 0: #do not accept empty strings
                    return False
                else:
                    TP.setName(value)
                return True

        return False

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.mColumNames[col]
            elif orientation == Qt.Vertical:
                return col
        return None

    def insertTemporalProfiles(self, temporalProfiles, i=None):
        if isinstance(temporalProfiles, TemporalProfile):
            temporalProfiles = [temporalProfiles]

        assert isinstance(temporalProfiles, list)
        for temporalProfile in temporalProfiles:
            assert isinstance(temporalProfile, TemporalProfile)

        if i is None:
            i = len(self.mTemporalProfiles)

        self.beginInsertRows(QModelIndex(), i, i + len(temporalProfiles) - 1)
        for temporalProfile in temporalProfiles:
            assert isinstance(temporalProfile, TemporalProfile)
            id = self.nextID
            self.nextID += 1
            temporalProfile.mID = id
            self.mTemporalProfiles.insert(i, temporalProfile)
            self.mTPLookupID[id] = temporalProfile
            self.mTPLookupSpatialPoint[temporalProfile.mCoordinate] = temporalProfile
            i += 1
        self.endInsertRows()

    def temporalProfileFromGeometry(self, geometry):
        if geometry in self.mTPLookupSpatialPoint.keys():
            return self.mTPLookupSpatialPoint[geometry]
        else:
            return None

    def temporalProfileFromID(self, id):
        if id in self.mTPLookupID.keys():
            return self.mTPLookupID[id]
        else:
            return None

    def id(self, temporalProfile):
        """
        Returns the id of an TemporalProfile
        :param temporalProfile: TemporalProfile
        :return: id or None, inf temporalProfile is not part of this collections
        """

        for k, tp in self.mTPLookupID.items():
            if tp == temporalProfile:
                return k
        return None

    def fromID(self, id):
        if self.mTPLookupID.has_key(id):
            return self.mTPLookupID[id]
        else:
            return None

    def fromSpatialPoint(self, spatialPoint):
        if self.mTPLookupSpatialPoint.has_key(spatialPoint):
            return self.mTPLookupSpatialPoint[spatialPoint]
        else:
            return None

    def removeTemporalProfiles(self, temporalProfiles):
        """
        Removes temporal profiles from this collection
        :param temporalProfile: TemporalProfile
        """

        if isinstance(temporalProfiles, TemporalProfile):
            temporalProfiles = [temporalProfiles]
        assert isinstance(temporalProfiles, list)

        for temporalProfile in temporalProfiles:
            assert isinstance(p, TemporalProfile)
            if temporalProfile in self.mTemporalProfiles:

                idx = self.tp2idx(temporalProfile)
                row = idx.row()
                self.beginRemoveRows(QModelIndex(), row, row)
                self.mTemporalProfiles.remove(temporalProfile)
                self.mTPLookupSpatialPoint.__delitem__(temporalProfile)
                self.mTPLookupID.__delitem__(temporalProfile)
                self.endRemoveRows()

    def connectTimeSeries(self, timeSeries):
        self.clear()

        if isinstance(timeSeries, TimeSeries):
            self.TS = timeSeries
            #for sensor in self.TS.Sensors:
            #    self.addSensor(sensor)
            #self.TS.sigSensorAdded.connect(self.addSensor)
            #self.TS.sigSensorRemoved.connect(self.removeSensor)
        else:
            self.TS = None

    def setMaxProfiles(self, n):
        """
        Sets the maximum number of temporal profiles to be stored in this container.
        :param n: number of profiles, must be >= 1
        """
        assert n >= 1
        self.mMaxProfiles = n

        self.prune()

    def prune(self):
        """
        Reduces the number of temporal profile to the value n defined with .setMaxProfiles(n)
        :return: [list-of-removed-TemporalProfiles]
        """



    def getFieldDefn(self, name, values):
        if isinstance(values, np.ndarray):
            # add bands
            if values.dtype in [np.int8, np.int16, np.int32, np.int64,
                                np.uint8, np.uint16, np.uint32, np.uint64]:
                fType = QVariant.Int
                fTypeName = 'integer'
            elif values.dtype in [np.float16, np.float32, np.float64]:
                fType = QVariant.Double
                fTypeName = 'decimal'
        else:
            raise NotImplementedError()

        return QgsField(name, fType, fTypeName)

    def setFeatureAttribute(self, feature, name, value):
        assert isinstance(feature, QgsFeature)
        assert isinstance(name, str)
        i = feature.fieldNameIndex(name)
        assert i >= 0, 'Field "{}" does not exist'.format(name)
        field = feature.fields()[i]
        if field.isNumeric():
            if field.type() == QVariant.Int:
                value = int(value)
            elif field.type() == QVariant.Double:
                value = float(value)
            else:
                raise NotImplementedError()
        feature.setAttribute(i, value)

    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.mColumNames[col]
        r = order != Qt.AscendingOrder

        if colName == self.mcnName:
            self.items.sort(key = lambda TP:TP.name(), reverse=r)
        elif colName == self.mcnCoordinate:
            self.items.sort(key=lambda TP: str(TP.mCoordinate), reverse=r)
        elif colName == self.mcnID:
            self.items.sort(key=lambda TP: TP.mID, reverse=r)
        elif colName == self.mcnLoaded:
            self.items.sort(key=lambda TP: TP.loadingStatus(), reverse=r)
        self.layoutChanged.emit()


    def addPixelLoaderResult(self, d):
        assert isinstance(d, PixelLoaderTask)
        if d.success():

            for i, TPid in enumerate(d.temporalProfileIDs):

                TP = self.temporalProfileFromID(TPid)
                tsd = self.TS.getTSD(d.sourcePath)
                assert isinstance(tsd, TimeSeriesDatum)

                if isinstance(TP, TemporalProfile):
                    profileData = d.resProfiles[i]
                    vMean, vStd = profileData

                    values = {}
                    #1. add the pixel values per returned band
                    for iBand, bandIndex in enumerate(d.bandIndices):
                        key = 'b{}'.format(bandIndex + 1)
                        values[key] = vMean[iBand]
                        key = 'std{}'.format(bandIndex + 1)
                        values[key] = vStd[iBand]

                    #indicesY, indicesX = d.imagePixelIndices()
                    #values['px_x'] = indicesX
                    #values['px_y'] = indicesY

                    TP.updateData(tsd, values)

    def clear(self):
        #todo: remove TS Profiles
        #self.mTemporalProfiles.clear()
        #self.sensorPxLayers.clear()
        pass



class TemporalProfilePlotStyle(PlotStyle):

    sigUpdated = pyqtSignal()

    def __init__(self, temporalProfile):
        super(TemporalProfilePlotStyle, self).__init__()
        assert isinstance(temporalProfile, TemporalProfile)
        self.mSensor = None
        self.mTP = temporalProfile
        self.mExpression = u'"b1"'
        self.mPlotItems = []

        if isinstance(temporalProfile, TemporalProfile):
            self.setTemporalProfile(temporalProfile)

    def createPlotItem(self, plotWidget):
        pdi = TemporalProfilePlotDataItem(self)
        self.mPlotItems.append(pdi)
        return pdi

    def temporalProfile(self):
        return self.mTP

    def setTemporalProfile(self, temporalPofile):
        assert isinstance(temporalPofile, TemporalProfile)
        b = temporalPofile != self.mTP
        self.mTP = temporalPofile
        if b: self.sigUpdated.emit()

    def setSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        b = sensor != self.mSensor
        self.mSensor = sensor
        if b: self.sigUpdated.emit()



    def sensor(self):
        return self.mSensor


    def setExpression(self, exp):
        assert isinstance(exp, unicode)
        b = self.mExpression != exp
        self.mExpression = exp
        if b: self.sigUpdated.emit()

    def expression(self):
        return self.mExpression

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = super(TemporalProfilePlotStyle, self).__getstate__()
        #remove
        del result['mTP']
        del result['mSensor']

        return result




class DateTimeViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    sigMoveToDate = pyqtSignal(np.datetime64)
    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(DateTimeViewBox, self).__init__(parent)
        #self.menu = None # Override pyqtgraph ViewBoxMenu
        #self.menu = self.getMenu() # Create the menu
        #self.menu = None


    def raiseContextMenu(self, ev):

        pt = self.mapDeviceToView(ev.pos())
        print(pt.x(), pt.y())
        date = num2date(pt.x())
        menu = QMenu(None)
        a = menu.addAction('Move to {}'.format(date))
        a.setData(date)
        a.triggered.connect(lambda : self.sigMoveToDate.emit(date))
        self.scene().addParentContextMenus(self, menu, ev)
        menu.exec_(ev.screenPos().toPoint())




class DateTimePlotWidget(pg.PlotWidget):
    """
    Subclass of PlotWidget
    """
    def __init__(self, parent=None):
        """
        Constructor of the widget
        """
        super(DateTimePlotWidget, self).__init__(parent, viewBox=DateTimeViewBox())
        self.plotItem = pg.PlotItem(
            axisItems={'bottom':DateTimeAxis(orientation='bottom')},
            viewBox=DateTimeViewBox()
        )
        self.setCentralItem(self.plotItem)



class PlotSettingsModel(QAbstractTableModel):

    #sigSensorAdded = pyqtSignal(SensorPlotSettings)
    sigVisibilityChanged = pyqtSignal(TemporalProfilePlotStyle)
    sigDataChanged = pyqtSignal(TemporalProfilePlotStyle)

    regBandKey = re.compile("(?<!\w)b\d+(?!\w)", re.IGNORECASE)
    regBandKeyExact = re.compile('^' + regBandKey.pattern + '$', re.IGNORECASE)

    def __init__(self, temporalProfileCollection, plotWidget, parent=None, *args):

        #assert isinstance(tableView, QTableView)

        super(PlotSettingsModel, self).__init__(parent=parent)
        assert isinstance(temporalProfileCollection, TemporalProfileCollection)

        self.cnID = 'ID'
        self.cnSensor = 'sensor'
        self.cnExpression = 'y-value'
        self.cnStyle = 'style'
        self.cnTemporalProfile = 'px'
        self.columNames = [self.cnTemporalProfile, self.cnSensor, self.cnStyle, self.cnExpression]

        self.mPlotSettings = []
        self.mPlotDataItems = []
        #assert isinstance(plotWidget, DateTimePlotWidget)
        self.mPlotWidget = plotWidget
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        self.tpCollection = temporalProfileCollection

        assert isinstance(self.tpCollection.TS, TimeSeries)
        #self.tpCollection.TS.sigSensorAdded.connect(self.addPlotItem)
        #self.tpCollection.TS.sigSensorRemoved.connect(self.removeSensor)

        self.sort(0, Qt.AscendingOrder)
        self.dataChanged.connect(self.signaler)

    def __len__(self):
        return len(self.mPlotSettings)

    def __iter__(self):
        return iter(self.mPlotSettings)

    def __getitem__(self, slice):
        return self.mPlotSettings[slice]

    def __contains__(self, item):
        return item in self.mPlotSettings


    def testSlot(self, *args):
        print(('TESTSLOT', args))

    def columnIndex(self, name):
        return self.columNames.index(name)

    def signaler(self, idxUL, idxLR):
        if idxUL.isValid():

            plotStyle = self.idx2plotStyle(idxUL)
            cname = self.columNames[idxUL.column()]
            if cname in [self.cnSensor,self.cnStyle]:
                self.sigVisibilityChanged.emit(plotStyle)
            if cname in [self.cnExpression]:
                self.sigDataChanged.emit(plotStyle)


    @staticmethod
    def bandIndex2bandKey(i):
        assert isinstance(i, int)
        assert i >= 0
        return 'b{}'.format(i+1)

    @staticmethod
    def bandKey2bandIndex(key):
        match = PlotSettingsModel.regBandKeyExact.search(key)
        assert match
        idx = int(match.group()[1:])-1
        return idx

    def requiredBandsIndices(self, sensor):
        """
        Returns the band indices required to calculate the values for
        the different PlotStyle expressions making use of sensor
        :param sensor: SensorInstrument for which the band indices are to be returned.
        :return: [list-of-band-indices]
        """
        bandIndices = set()
        assert isinstance(sensor, SensorInstrument)
        for p in [p for p in self.mPlotSettings if p.sensor() == sensor]:
            assert isinstance(p, TemporalProfilePlotStyle)
            expression = p.expression()
            #remove leading & tailing "
            bandKeys = PlotSettingsModel.regBandKey.findall(expression)
            for bandIndex in [self.bandKey2bandIndex(key) for key in bandKeys]:
                bandIndices.add(bandIndex)

        return bandIndices


    def insertPlotStyles(self, plotStyles, i=None):
        """
        Inserts PlotStyle
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        :param i: index to insert, defaults to the last list position
        """
        if isinstance(plotStyles, TemporalProfilePlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)
        for plotStyle in plotStyles:
            assert isinstance(plotStyle, TemporalProfilePlotStyle)

        if i is None:
            i = len(self.mPlotSettings)

        self.beginInsertRows(QModelIndex(), i, i + len(plotStyles)-1)
        for j, plotStyle in enumerate(plotStyles):
            assert isinstance(plotStyle, TemporalProfilePlotStyle)

            self.mPlotSettings.insert(i+j, plotStyle)
        self.endInsertRows()

    def removePlotStyles(self, plotStyles):
        """
        Removes PlotStyle instances
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        """
        if isinstance(plotStyles, PlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)
        for plotStyle in plotStyles:
            assert isinstance(plotStyle, PlotStyle)
            if plotStyle in self.mPlotSettings:
                idx = self.plotStyle2idx(plotStyle)
                self.beginRemoveRows(QModelIndex(), idx.row(),idx.row())
                self.mPlotSettings.remove(plotStyle)
                self.endRemoveRows()

    def sort(self, col, order):
        if self.rowCount() == 0:
            return


        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        #self.beginMoveRows(idxSrc,

        if colName == self.cnSensor:
            self.mPlotSettings.sort(key = lambda sv:sv.sensor().name(), reverse=r)
        elif colName == self.cnExpression:
            self.mPlotSettings.sort(key=lambda sv: sv.expression(), reverse=r)
        elif colName == self.cnStyle:
            self.mPlotSettings.sort(key=lambda sv: sv.color, reverse=r)

    def rowCount(self, parent = QModelIndex()):
        return len(self.mPlotSettings)


    def removeRows(self, row, count , parent = QModelIndex()):

        self.beginRemoveRows(parent, row, row + count-1)

        toRemove = self.mPlotSettings[row:row + count]

        for tsd in toRemove:
            self.mPlotSettings.remove(tsd)

        self.endRemoveRows()

    def plotStyle2idx(self, plotStyle):

        assert isinstance(plotStyle, TemporalProfilePlotStyle)

        if plotStyle in self.mPlotSettings:
            i = self.mPlotSettings.index(plotStyle)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()

    def idx2plotStyle(self, index):

        if index.isValid() and index.row() < self.rowCount():
            return self.mPlotSettings[index.row()]

        return None

    def columnCount(self, parent = QModelIndex()):
        return len(self.columNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columNames[index.column()]
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfilePlotStyle):
            sensor = plotStyle.sensor()
            #print(('data', columnName, role))
            if role == Qt.DisplayRole:
                if columnName == self.cnSensor:
                    if isinstance(sensor, SensorInstrument):
                        value = sensor.name()
                    else:
                        value = '<Select Sensor>'
                elif columnName == self.cnExpression:
                    value = plotStyle.expression()
                elif columnName == self.cnTemporalProfile:
                    value = plotStyle.temporalProfile().name()

            #elif role == Qt.DecorationRole:
            #    if columnName == self.cnStyle:
            #        value = plotStyle.createIcon(QSize(96,96))

            elif role == Qt.CheckStateRole:
                if columnName == self.cnTemporalProfile:
                    value = Qt.Checked if plotStyle.isVisible() else Qt.Unchecked



            elif role == Qt.UserRole:
                value = plotStyle
                if columnName == self.cnSensor:
                    value = plotStyle.sensor()
                elif columnName == self.cnExpression:
                    value = plotStyle.expression()
                elif columnName == self.cnStyle:
                    value = plotStyle
                elif columnName == self.cnTemporalProfile:
                    value == plotStyle.temporalProfile()
                else:
                    value = plotStyle
        #print(('get data',value))
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return False
        #print(('Set data', index.row(), index.column(), value, role))
        columnName = self.columNames[index.column()]

        if value is None:
            return False

        result = False
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfilePlotStyle):
            if role in [Qt.DisplayRole, Qt.EditRole]:
                if columnName == self.cnExpression:
                    plotStyle.setExpression(value)
                    result = True
                elif columnName == self.cnStyle:
                    if isinstance(value, PlotStyle):
                        plotStyle.plotStyle.copyFrom(value)
                        result = True

            if role == Qt.CheckStateRole:
                if columnName == self.cnTemporalProfile:
                    plotStyle.setVisibility(value == Qt.Checked)
                    result = True

            if role == Qt.EditRole:
                if columnName == self.cnExpression:
                    plotStyle.setExpression(value)
                    result = True
                elif columnName == self.cnStyle:
                    plotStyle.copyFrom(value)
                    result = True
                elif columnName == self.cnSensor:
                    plotStyle.setSensor(value)
                    result = True
                elif columnName == self.cnTemporalProfile:
                    plotStyle.setTemporalProfile(value)
                    result = True

        if result:
            #save plot-style
            self.savePlotSettings(plotStyle, index='DEFAULT')
            self.dataChanged.emit(index, index)

        return result

    def savePlotSettings(self, sensorPlotSettings, index='DEFAULT'):
        return
        #todo
        assert isinstance(sensorPlotSettings, TemporalProfilePlotStyle)
        #todo: avoid dumps
        id = 'SPS.{}.{}'.format(index, sensorPlotSettings.sensor().id())
        d = pickle.dumps(sensorPlotSettings)
        SETTINGS.setValue(id, d)

    def restorePlotSettings(self, sensor, index='DEFAULT'):
        return None

        #todo
        assert isinstance(sensor, SensorInstrument)
        id = 'SPS.{}.{}'.format(index, sensor.id())
        sensorPlotSettings = SETTINGS.value(id)
        if sensorPlotSettings is not None:
            try:
                sensorPlotSettings = pickle.loads(sensorPlotSettings)
                s = ""
            except:
                sensorPlotSettings = None
                pass

        if isinstance(sensorPlotSettings, TemporalProfilePlotStyle):
            return sensorPlotSettings
        else:
            return None


    def flags(self, index):
        if index.isValid():
            columnName = self.columNames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in [self.cnTemporalProfile]:
                flags = flags | Qt.ItemIsUserCheckable
            if columnName in [self.cnTemporalProfile, self.cnSensor, self.cnExpression, self.cnStyle]: #allow check state
                flags = flags | Qt.ItemIsEditable
            return flags
            #return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None



class ProfileViewDockUI(QgsDockWidget, loadUI('profileviewdock.ui')):


    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)
        from timeseriesviewer import OPENGL_AVAILABLE, SETTINGS

        #TBD.
        #self.line.setVisible(False)
        #self.listWidget.setVisible(False)
        self.stackedWidget.setCurrentWidget(self.page2D)

        if OPENGL_AVAILABLE:
            l = self.page3D.layout()
            l.removeWidget(self.labelDummy3D)
            self.labelDummy3D.setVisible(False)
            from pyqtgraph.opengl import GLViewWidget
            self.plotWidget3D = GLViewWidget(parent=self.page3D)
            l.addWidget(self.plotWidget3D)
        else:
            self.plotWidget3D = None

        #pi = self.plotWidget2D.plotItem
        #ax = DateAxis(orientation='bottom', showValues=True)
        #pi.layout.addItem(ax, 3,2)

        self.baseTitle = self.windowTitle()
        self.TS = None

        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressInfo.setText('')
        self.pxViewModel2D = None
        self.pxViewModel3D = None

        self.tableView2DProfiles.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableView2DProfiles.setSortingEnabled(True)
        self.tableViewTemporalProfiles.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableViewTemporalProfiles.setSortingEnabled(True)

def date2num(d):
    d2 = d.astype(datetime.datetime)
    o = d2.toordinal()

    #assert d == num2date(o)

    return o

def num2date(n):
    n = int(np.round(n))
    if n < 1:
        n = 1
    d = datetime.datetime.fromordinal(n)
    d = d.date()

    return np.datetime64('{:04}-{:02}-{:02}'.format(d.year,d.month,d.day), 'D')

class TemporalProfile(QObject):

    _mNextID = 0
    @staticmethod
    def nextID():
        n = TemporalProfile._mNextID
        TemporalProfile._mNextID += 1
        return n

    def __init__(self, timeSeries, spatialPoint):
        super(TemporalProfile, self).__init__()
        assert isinstance(timeSeries, TimeSeries)
        assert isinstance(spatialPoint, SpatialPoint)

        self.mTimeSeries = timeSeries
        self.mCoordinate = spatialPoint
        self.mID = TemporalProfile.nextID()
        self.mData = {}
        self.mUpdated = False
        self.mName = '#{}'.format(self.mID)

        self.mLoaded = self.mLoadedMax = 0
        self.initMetadata()
        self.updateLoadingStatus()

    def initMetadata(self):
        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            meta = {'doy':tsd.doy,
                    'date':str(tsd.date)}
            self.updateData(tsd, meta)

    sigNameChanged = pyqtSignal(str)
    def setName(self, name):
        if name != self.mName:
            self.mName = name
            self.sigNameChanged.emit(self.mName)

    def name(self):
        return self.mName

    def updateData(self, tsd, values):
        assert isinstance(tsd, TimeSeriesDatum)
        assert isinstance(values, dict)

        if tsd not in self.mData.keys():
            self.mData[tsd] = {}

        self.mData[tsd].update(values)
        self.updateLoadingStatus()
        self.mUpdated = True


    def qgsFieldFromKeyValue(self, key, value):
        t = type(value)
        if t in [int, float]:

            fLen  = 0
            fPrec = 0
            fComm = ''
            fType = ''
            f = QgsField(key, QVariant.Double, 'double', 40, 5)
        else:
            f = QgsField(key, QVariant.String, 'text', 40, 5)
        return f

    def dataFromExpression(self, sensor, expression, dateType='date'):
        assert dateType in ['date','doy']
        x = []
        y = []
        if not isinstance(expression, QgsExpression):
            expression = QgsExpression(expression)
        assert isinstance(expression, QgsExpression)

        fields = QgsFields()
        f = QgsFeature()
        for i, tsd in enumerate(sorted([tsd for tsd in self.mData.keys() if tsd.sensor == sensor])):
            assert isinstance(tsd, TimeSeriesDatum)
            data = self.mData[tsd]


            if i == 0:
                #initialize the fields
                for k in data.keys():
                    field = self.qgsFieldFromKeyValue(k, data[k])
                    fields.append(field)

                f.setFields(fields)

            for k, v in data.items():
                f.setAttribute(k,v)

            value = expression.evaluate(f)
            if value is not None:
                if dateType == 'date':
                    x.append(date2num(tsd.date))
                elif dateType == 'doy':
                    x.append(tsd.doy)
                y.append(value)

        return np.asarray(x), np.asarray(y)

    def data(self, tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        if self.hasData(tsd):
            return self.mData[tsd]
        else:
            return {}


    def loadingStatus(self):
        """
        Returns the loading status in terms of single pixel values.
        nLoaded = sum of single band values
        nLoadedMax = potential maximum of band values that might be loaded
        :return: (nLoaded, nLoadedMax)
        """
        return self.mLoaded, self.mLoadedMax

    def updateLoadingStatus(self):
        """
        Calculates and the loading status in terms of single pixel values.
        nMax is the sum of all bands over each TimeSeriesDatum and Sensors
        """

        self.mLoaded = self.mLoadedMax

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            self.mLoadedMax += tsd.sensor.nb
            if self.hasData(tsd):
                self.mLoaded += len([k for k in self.mData[tsd].keys() if k.startswith('b')])


    def hasData(self,tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        return tsd in self.mData.keys()

    def __repr__(self):
        return 'TemporalProfile {}'.format(self.mCoordinate)



class SpectralTemporalVisualization(QObject):

    sigShowPixel = pyqtSignal(TimeSeriesDatum, QgsPoint, QgsCoordinateReferenceSystem)

    """
    Signalizes to move to specific date of interest
    """
    sigMoveToDate = pyqtSignal(np.datetime64)


    def __init__(self, ui):
        super(SpectralTemporalVisualization, self).__init__()
        #assert isinstance(timeSeries, TimeSeries)

        if not isinstance(ui, ProfileViewDockUI):
            print('UI : {}'.format(ui))

        assert isinstance(ui, ProfileViewDockUI), 'arg ui of type: {} {}'.format(type(ui), str(ui))
        self.ui = ui

        if DEBUG:
            import timeseriesviewer.pixelloader
            timeseriesviewer.pixelloader.DEBUG = True

        self.TS = None
        self.pixelLoader = PixelLoader()
        self.pixelLoader.sigPixelLoaded.connect(self.onPixelLoaded)
        self.pixelLoader.sigLoadingStarted.connect(lambda: self.ui.progressInfo.setText('Start loading...'))


        self.plot_initialized = False
        self.TV = ui.tableView2DProfiles
        self.TV.setSortingEnabled(False)
        self.plot2D = ui.plotWidget2D
        self.plot2D.plotItem.getViewBox().sigMoveToDate.connect(self.sigMoveToDate)
        self.plot3D = ui.plotWidget3D
        self.tpCollection = TemporalProfileCollection()
        self.tpCollectionListModel = TemporalProfileCollectionListModel(self.tpCollection)

        self.ui.tableViewTemporalProfiles.setModel(self.tpCollection)

        self.ui.cbTemporalProfile3D.setModel(self.tpCollectionListModel)
        #self.pxCollection.sigPixelAdded.connect(self.requestUpdate)
        #self.pxCollection.sigPixelRemoved.connect(self.clear)

        self.plotSettingsModel = None

        self.pixelLoader.sigLoadingStarted.connect(self.clear)
        self.pixelLoader.sigLoadingFinished.connect(lambda : self.plot2D.enableAutoRange('x', False))


        # self.VIEW.setItemDelegateForColumn(3, PointStyleDelegate(self.VIEW))
        self.plotData2D = dict()
        self.plotData3D = dict()

        self.updateRequested = True
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updatePlot)
        self.updateTimer.start(5000)

        self.sigMoveToDate.connect(self.onMoveToDate)

        self.initActions()

    def createNewPlotStyle(self):
        l = len(self.tpCollection)
        if l > 0:
            TP = self.tpCollection[0]
            PS = TemporalProfilePlotStyle(TP)
            sensors = self.TS.Sensors.keys()
            if len(sensors) > 0:
                PS.setSensor(sensors[0])
            self.plotSettingsModel.insertPlotStyles([PS])
            pdi = PS.createPlotItem(self.plot2D)
            plotItem = self.plot2D.getPlotItem()
            assert isinstance(plotItem, pg.PlotItem)
            plotItem.addItem(pdi)
            plotItem.update()
            #plotItem.addDataItem(pdi)
            plotItem.plot().sigPlotChanged.emit(plotItem)
            self.updatePlot()


    def initActions(self):

        self.ui.btnAddView.setDefaultAction(self.ui.actionAddView)
        self.ui.btnRemoveView.setDefaultAction(self.ui.actionRemoveView)
        self.ui.btnRefresh2D.setDefaultAction(self.ui.actionRefresh)
        self.ui.btnRefresh3D.setDefaultAction(self.ui.actionRefresh)
        self.ui.actionRefresh.triggered.connect(self.updatePlot)
        self.ui.actionAddView.triggered.connect(self.createNewPlotStyle)
        #todo: self.ui.actionRemoveView.triggered.connect(self.plotSettingsModel.createPlotStyle)


    def setTimeSeries(self, TS):

        assert isinstance(TS, TimeSeries)
        self.TS = TS

        self.tpCollection.connectTimeSeries(self.TS)



        self.plotSettingsModel = PlotSettingsModel(self.tpCollection, self.plot2D, parent=self)
        self.plotSettingsModel.sigVisibilityChanged.connect(self.setVisibility)
        self.plotSettingsModel.sigDataChanged.connect(self.requestUpdate)
        self.plotSettingsModel.rowsInserted.connect(self.onRowsInserted)
        # self.plotSettingsModel.modelReset.connect(self.updatePersistantWidgets)
        self.TV.setModel(self.plotSettingsModel)
        self.delegate = PlotSettingsWidgetDelegate(self.TV, self.TS, self.tpCollectionListModel)
        self.delegate.setItemDelegates(self.TV)


    sigMoveToTSD = pyqtSignal(TimeSeriesDatum)

    def onMoveToDate(self, date):
        dt = np.asarray([np.abs(tsd.date - date) for tsd in self.TS])
        i = np.argmin(dt)
        self.sigMoveToTSD.emit(self.TS[i])


    def onPixelLoaded(self, nDone, nMax, d):
        self.ui.progressBar.setValue(nDone)
        self.ui.progressBar.setMaximum(nMax)

        assert isinstance(d, PixelLoaderTask)

        bn = os.path.basename(d.sourcePath)
        if d.success():
            t = 'Last loaded from {}.'.format(bn)
            self.tpCollection.addPixelLoaderResult(d)
            self.updateRequested = True
        else:
            t = 'Failed loading from {}.'.format(bn)
            if d.info and d.info != '':
                t += '({})'.format(d.info)
        if DEBUG:
            print(t)
        # QgsApplication.processEvents()
        self.ui.progressInfo.setText(t)

    def requestUpdate(self, *args):
        self.updateRequested = True
        #next time

    def updatePersistentWidgets(self):
        model = self.TV.model()
        if isinstance(model, PlotSettingsModel):
            colExpression = model.columnIndex(model.cnExpression)
            colStyle = model.columnIndex(model.cnStyle)

            for row in range(model.rowCount()):
                idxExpr = model.createIndex(row, colExpression)
                idxStyle = model.createIndex(row, colStyle)

                #self.TV.openPersistentEditor(idxExpr)
                #self.TV.openPersistentEditor(idxStyle)

                #self.TV.openPersistentEditor(model.createIndex(start, colStyle))
            s = ""


    def onRowsInserted(self, parent, start, end):
        model = self.TV.model()
        if isinstance(model, PlotSettingsModel):
            colExpression = model.columnIndex(model.cnExpression)
            colStyle = model.columnIndex(model.cnStyle)
            while start <= end:
                idxExpr = model.createIndex(start, colExpression)
                idxStyle = model.createIndex(start, colStyle)
                self.TV.openPersistentEditor(idxExpr)
                self.TV.openPersistentEditor(idxStyle)
                start += 1
                #self.TV.openPersistentEditor(model.createIndex(start, colStyle))
            s = ""

    def onObservationClicked(self, plotDataItem, points):
        for p in points:
            tsd = p.data()
            #print(tsd)


    def clear(self):
        #first remove from pixelCollection
        self.tpCollection.prune()

        return

        self.plotData2D.clear()
        self.plotData3D.clear()

        pi = self.plot2D.getPlotItem()
        plotItems = pi.listDataItems()
        for p in plotItems:
            p.clear()
            p.update()

        if len(self.TS) > 0:
            rng = [self.TS[0].date, self.TS[-1].date]
            rng = [date2num(d) for d in rng]
            self.plot2D.getPlotItem().setRange(xRange=rng)
        #QApplication.processEvents()
        if self.plot3D:
            pass


    def loadCoordinate(self, spatialPoints=None):
        """
        Loads a temporal profile for a single or multiple geometries.
        :param spatialPoints: SpatialPoint | [list-of-SpatialPoints]
        """
        if not isinstance(self.plotSettingsModel, PlotSettingsModel):
            return False

        if not self.pixelLoader.isReadyToLoad():
            return False

        assert isinstance(self.TS, TimeSeries)

        #Get or create the TimeSeriesProfiles which will store the loaded values

        tasks = []
        TPs = []
        theGeometries = []
        LUT_bandIndices = dict()

        # Define a which (new) bands need to be loaded for each sensor
        for sensor in self.TS.Sensors:
            LUT_bandIndices[sensor] = self.plotSettingsModel.requiredBandsIndices(sensor)


        #update new / existing points
        if isinstance(spatialPoints, SpatialPoint):
            spatialPoints = [spatialPoints]

        for spatialPoint in spatialPoints:
            assert isinstance(spatialPoint, SpatialPoint)
            TP = self.tpCollection.fromSpatialPoint(spatialPoint)
            if not isinstance(TP, TemporalProfile):
                TP = TemporalProfile(self.TS, spatialPoint)
                self.tpCollection.insertTemporalProfiles(TP)
            TPs.append(TP)
            theGeometries.append(TP.mCoordinate)


        TP_ids = [TP.mID for TP in TPs]
        #each TSD is a Task
        #a Task defines which bands are to be loaded
        for tsd in self.TS:

            #do not load from invisible TSDs
            if not tsd.isVisible():
                continue

            #which bands do we need to load?
            requiredIndices = set(LUT_bandIndices[tsd.sensor])
            if len(requiredIndices) == 0:
                continue
            else:
                s = ""

            missingIndices = set()

            for TP in TPs:
                assert isinstance(TP, TemporalProfile)
                existingBandKeys = [k for k in TP.data(tsd).keys() if PlotSettingsModel.regBandKeyExact.search(k)]
                existingBandIndices = set([PlotSettingsModel.bandKey2bandIndex(k) for k in existingBandKeys])
                need2load = requiredIndices.difference(existingBandIndices)
                missingIndices = missingIndices.union(need2load)

            missingIndices = sorted(list(missingIndices))

            if len(missingIndices) > 0:
                task = PixelLoaderTask(tsd.pathImg, theGeometries,
                                       bandIndices=missingIndices,
                                       temporalProfileIDs=TP_ids)
                tasks.append(task)

        if len(tasks) > 0:
            aGoodDefault = 2 if len(self.TS) > 25 else 1

            self.pixelLoader.setNumberOfProcesses(SETTINGS.value('profileloader_threads', aGoodDefault))
            if DEBUG:
                print('Start loading for {} geometries from {} sources...'.format(
                    len(theGeometries), len(tasks)
                ))
            self.pixelLoader.startLoading(tasks)

        else:
            if DEBUG:
                print('Data for geometries already loaded')

    def setVisibility(self, sensorPlotStyle):
        assert isinstance(sensorPlotStyle, TemporalProfilePlotStyle)
        self.setVisibility2D(sensorPlotStyle)

    def setVisibility2D(self, sensorPlotStyle):

        self.plot2D.update()


    def addData(self, sensorView = None):

        if sensorView is None:
            for sv in self.plotSettingsModel.items:
                self.setData(sv)
        else:
            assert isinstance(sensorView, TemporalProfilePlotStyle)
            self.setData2D(sensorView)

    @QtCore.pyqtSlot()
    def updatePlot(self):
        if isinstance(self.plotSettingsModel, PlotSettingsModel):
            if DEBUG:
                print('Update plot...')



            pi = self.plot2D.getPlotItem()
            piDataItems = pi.listDataItems()
            locations = set()
            for plotSetting in self.plotSettingsModel:
                assert isinstance(plotSetting, TemporalProfilePlotStyle)
                locations.add(plotSetting.temporalProfile().mCoordinate)
                for pdi in plotSetting.mPlotItems:
                    assert isinstance(pdi, TemporalProfilePlotDataItem)
                    pdi.updateStyle()
                    pdi.updateData()



            #2. load pixel data
            self.loadCoordinate(list(locations))


            # https://github.com/pyqtgraph/pyqtgraph/blob/5195d9dd6308caee87e043e859e7e553b9887453/examples/customPlot.py
            return




def examplePixelLoader():

    # prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()


    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfThreads(2)

    if False:
        files = ['observationcloud/testdata/2014-07-26_LC82270652014207LGN00_BOA.bsq',
                 'observationcloud/testdata/2014-08-03_LE72270652014215CUB00_BOA.bsq'
                 ]
    else:
        from timeseriesviewer.utils import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = file_search(searchDir, '*227065*band4.img', recursive=True)
        #files = files[0:3]

    lyr = QgsRasterLayer(files[0])
    coord = lyr.extent().center()
    crs = lyr.crs()

    l = QVBoxLayout()

    btnStart = QPushButton()
    btnStop = QPushButton()
    prog = QProgressBar()
    tboxResults = QPlainTextEdit()
    tboxResults.setMaximumHeight(300)
    tboxThreads = QPlainTextEdit()
    tboxThreads.setMaximumHeight(200)
    label = QLabel()
    label.setText('Progress')

    def showProgress(n,m,md):
        prog.setMinimum(0)
        prog.setMaximum(m)
        prog.setValue(n)

        info = []
        for k, v in md.items():
            info.append('{} = {}'.format(k,str(v)))
        tboxResults.setPlainText('\n'.join(info))
        #tboxThreads.setPlainText(PL.threadInfo())
        qgsApp.processEvents()

    PL.sigPixelLoaded.connect(showProgress)
    btnStart.setText('Start loading')
    btnStart.clicked.connect(lambda : PL.startLoading(files, coord, crs))
    btnStop.setText('Cancel')
    btnStop.clicked.connect(lambda: PL.cancelLoading())
    lh = QHBoxLayout()
    lh.addWidget(btnStart)
    lh.addWidget(btnStop)
    l.addLayout(lh)
    l.addWidget(prog)
    l.addWidget(tboxThreads)
    l.addWidget(tboxResults)

    gb.setLayout(l)
    gb.show()
    #rs.setBackgroundStyle('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222, stop:1 #333);')
    #rs.handle.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #282, stop:1 #393);')
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    import site, sys
    from timeseriesviewer import utils
    qgsApp = utils.initQgisApplication()
    DEBUG = True

    for date in ['2012-01-01', '2017-12-23']:
        dt1 = np.datetime64(date)

        n = date2num(dt1)
        dt2 = num2date(n)

        assert dt1 == dt2

    ui = ProfileViewDockUI()
    ui.show()

    if True:
        TS = TimeSeries()
        STVis = SpectralTemporalVisualization(ui)
        STVis.setTimeSeries(TS)

        import example.Images
        from timeseriesviewer import file_search
        files = file_search(os.path.dirname(example.Images.__file__), '*.tif')
        TS.addFiles(files)
        ext = TS.getMaxSpatialExtent()
        cp1 = SpatialPoint(ext.crs(),ext.center())
        cp2 = SpatialPoint(ext.crs(), ext.center())
        cp3 = SpatialPoint(ext.crs(), ext.center().x()+500, ext.center().y()+250)

        STVis.loadCoordinate(cp1)
        STVis.loadCoordinate(cp2)
        STVis.loadCoordinate(cp3)
        STVis.createNewPlotStyle()
    qgsApp.exec_()
    qgsApp.exitQgis()

