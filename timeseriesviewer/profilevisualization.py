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

import os, sys, pickle, datetime
from collections import OrderedDict
from qgis.gui import *
from qgis.core import *
from PyQt5.QtCore import *
from PyQt5.QtXml import *
from PyQt5.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.timeseries import *
from timeseriesviewer.utils import SpatialExtent, SpatialPoint, px2geo
from timeseriesviewer.ui.docks import TsvDockWidgetBase, loadUI
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleButton
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderTask
from timeseriesviewer.sensorvisualization import SensorListModel
from timeseriesviewer.temporalprofiles2d import *
from timeseriesviewer.temporalprofiles3d import *
from timeseriesviewer.temporalprofiles3d import LABEL_EXPRESSION_3D
import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph import AxisItem


import datetime

from osgeo import gdal, gdal_array
import numpy as np

DEBUG = False
OPENGL_AVAILABLE = False
MATPLOTLIB_AVAILABLE = False
try:
    import timeseriesviewer.temporalprofiles3dMPL
    MATPLOTLIB_AVAILABLE = True

except Exception as ex:
    print('unable to import matlotlib based 3d plotting:\n{}'.format(ex))

try:

    #import OpenGL
    OPENGL_AVAILABLE = True
    from timeseriesviewer.temporalprofiles3d import *

    #t = ViewWidget3D()
    #del t


except Exception as ex:
    print('unable to import OpenGL based packages:\n{}'.format(ex))



def getTextColorWithContrast(c):
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')

def selectedModelIndices(tableView):
    assert isinstance(tableView, QTableView)
    result = {}

    sm = tableView.selectionModel()
    m = tableView.model()
    if isinstance(sm, QItemSelectionModel) and isinstance(m, QAbstractItemModel):
        for idx in sm.selectedIndexes():
            assert isinstance(idx, QModelIndex)
            if idx.row() not in result.keys():
                result[idx.row()] = idx
    return result.values()



class _SensorPoints(pg.PlotDataItem):
    def __init__(self, *args, **kwds):
        super(_SensorPoints, self).__init__(*args, **kwds)
        # menu creation is deferred because it is expensive and often
        # the user will never see the menu anyway.
        self.menu = None

    def boundingRect(self):
        return super(_SensorPoints,self).boundingRect()

    def paint(self, p, *args):
        super(_SensorPoints, self).paint(p, *args)


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



class PlotSettingsModel2DWidgetDelegate(QStyledItemDelegate):
    """

    """
    def __init__(self, tableView, timeSeries, temporalProfileListModel, parent=None):
        assert isinstance(tableView, QTableView)
        assert isinstance(timeSeries, TimeSeries)
        assert isinstance(temporalProfileListModel, TemporalProfileCollectionListModel)
        super(PlotSettingsModel2DWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mTimeSeries = timeSeries
        self.mTemporalProfileListModel = temporalProfileListModel
        self.mSensorLayers = {}

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)
        model = tableView.model()

        assert isinstance(model, PlotSettingsModel2D)
        for c in [model.cnSensor, model.cnExpression, model.cnStyle, model.cnTemporalProfile]:
            i = model.columnNames.index(c)
            tableView.setItemDelegateForColumn(i, self)

    def getColumnName(self, index):
        assert index.isValid()
        model = index.model()
        assert isinstance(model, PlotSettingsModel2D)
        return model.columnNames[index.column()]
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
    def exampleLyr(self, sensor):
        assert isinstance(sensor, SensorInstrument)


        if sensor not in self.mSensorLayers.keys():

            crs = QgsCoordinateReferenceSystem('EPSG:4862')
            uri = 'Point?crs={}'.format(crs.authid())
            lyr = QgsVectorLayer(uri, 'LOCATIONS', 'memory')
            f = sensorExampleQgsFeature(sensor)
            assert isinstance(f, QgsFeature)
            assert lyr.startEditing()
            for field in f.fields():
                lyr.addAttribute(field)
            lyr.addFeature(f)
            lyr.commitChanges()
            self.mSensorLayers[sensor] = lyr
        return self.mSensorLayers[sensor]

    def createEditor(self, parent, option, index):
        cname = self.getColumnName(index)
        model = self.mTableView.model()
        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel2D):
            plotStyle = model.idx2plotStyle(index)

            if isinstance(plotStyle, TemporalProfile2DPlotStyle):
                if cname == model.cnExpression and isinstance(plotStyle.sensor(), SensorInstrument):
                    w = QgsFieldExpressionWidget(parent=parent)
                    w.setExpression(plotStyle.expression())
                    w.setLayer(self.exampleLyr(plotStyle.sensor()))
                    plotStyle.sigSensorChanged.connect(lambda s : w.setLayer(self.exampleLyr(s)))
                    w.setExpressionDialogTitle('Values')
                    w.setToolTip('Set an expression to specify the image band or calculate a spectral index.')
                    w.fieldChanged[str,bool].connect(lambda n, b : self.checkData(index, w, w.expression()))

                elif cname == model.cnStyle:
                    w = PlotStyleButton(parent=parent)
                    w.setPlotStyle(plotStyle)
                    w.setToolTip('Set style.')
                    w.sigPlotStyleChanged.connect(lambda: self.checkData(index, w, w.plotStyle()))

                elif cname == model.cnSensor:
                    w = QComboBox(parent=parent)
                    m = SensorListModel(self.mTimeSeries)
                    w.setModel(m)

                elif cname == model.cnTemporalProfile:
                    w = QComboBox(parent=parent)
                    w.setModel(self.mTemporalProfileListModel)
                else:
                    raise NotImplementedError()
        return w

    def checkData(self, index, w, value):
        assert isinstance(index, QModelIndex)
        model = self.mTableView.model()
        if index.isValid() and isinstance(model, PlotSettingsModel2D):
            plotStyle = model.idx2plotStyle(index)
            assert isinstance(plotStyle, TemporalProfile2DPlotStyle)
            if isinstance(w, QgsFieldExpressionWidget):
                assert value == w.expression()
                assert w.isExpressionValid(value) == w.isValidExpression()

                if w.isValidExpression():
                    self.commitData.emit(w)
                else:
                    s = ""
                    #print(('Delegate commit failed',w.asExpression()))
            if isinstance(w, PlotStyleButton):

                self.commitData.emit(w)

    def setEditorData(self, editor, index):
        cname = self.getColumnName(index)
        model = self.mTableView.model()

        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel2D):
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
        model = self.mTableView.model()

        if index.isValid() and isinstance(model, PlotSettingsModel2D):
            if cname == model.cnExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression() and expr != exprLast:
                    model.setData(index, w.asExpression(), Qt.EditRole)

            elif cname == model.cnStyle:
                assert isinstance(w, PlotStyleButton)
                model.setData(index, w.plotStyle(), Qt.EditRole)

            elif cname == model.cnSensor:
                assert isinstance(w, QComboBox)
                sensor = w.itemData(w.currentIndex(), role=Qt.UserRole)
                assert isinstance(sensor, SensorInstrument)
                model.setData(index, sensor, Qt.EditRole)

            elif cname == model.cnTemporalProfile:
                assert isinstance(w, QComboBox)
                TP = w.itemData(w.currentIndex(), role=Qt.UserRole)
                #assert isinstance(TP, TemporalProfile)
                model.setData(index, TP, Qt.EditRole)

            else:
                raise NotImplementedError()



class PlotSettingsModel3DWidgetDelegate(QStyledItemDelegate):
    """

    """
    def __init__(self, tableView, timeSeries, temporalProfileListModel, parent=None):
        assert isinstance(tableView, QTableView)
        assert isinstance(timeSeries, TimeSeries)
        assert isinstance(temporalProfileListModel, TemporalProfileCollectionListModel)
        super(PlotSettingsModel3DWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mTimeSeries = timeSeries
        self.mTemporalProfileListModel = temporalProfileListModel
        self.mSensorLayers = {}

        self.mTemporalProfileListModel.dataChanged.connect(self.updateComboBoxes)
        self.mTimeSeries.sigSensorRemoved.connect(self.updateComboBoxes)



    def updateComboBoxes(self):

        # assert isinstance(cb, QComboBox)

        s = ""




    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)
        model = tableView.model()
        assert isinstance(model, PlotSettingsModel3D)
        for c in [model.cnSensor, model.cnExpression, model.cnStyle, model.cnTemporalProfile]:
            i = model.columnNames.index(c)
            tableView.setItemDelegateForColumn(i, self)

    def getColumnName(self, index):
        assert index.isValid()
        model = index.model()
        assert isinstance(model, PlotSettingsModel3D)
        return model.columnNames[index.column()]
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
        model = self.mTableView.model()
        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel3D):
            plotStyle = model.idx2plotStyle(index)
            if isinstance(plotStyle, TemporalProfile3DPlotStyle):
                if cname == model.cnExpression:
                    w = QgsFieldExpressionWidget(parent=parent)
                    w.setExpression(plotStyle.expression())
                    w.setLayer(self.exampleLyr(plotStyle.sensor()))
                    def onSensorAdded(s):
                        w.setLayer(self.exampleLyr(s))
                    #plotStyle.sigSensorChanged.connect(lambda s : w.setLayer(self.exampleLyr(s)))
                    plotStyle.sigSensorChanged.connect(onSensorAdded)
                    w.setExpressionDialogTitle('Values')
                    w.setToolTip('Set an expression to specify the image band or calculate a spectral index.')
                    w.fieldChanged[str,bool].connect(lambda n, b : self.checkData(index, w, w.expression()))

                elif cname == model.cnStyle:
                    w = TemporalProfile3DPlotStyleButton(parent=parent)
                    w.setPlotStyle(plotStyle)
                    w.setToolTip('Set plot style')
                    w.sigPlotStyleChanged.connect(lambda: self.checkData(index, w, w.plotStyle()))

                elif cname == model.cnSensor:
                    w = QComboBox(parent=parent)
                    m = SensorListModel(self.mTimeSeries)
                    w.setModel(m)

                elif cname == model.cnTemporalProfile:
                    w = QComboBox(parent=parent)
                    w.setModel(self.mTemporalProfileListModel)
                else:
                    raise NotImplementedError()
        return w

    def exampleLyr(self, sensor):

        if sensor not in self.mSensorLayers.keys():
            crs = QgsCoordinateReferenceSystem('EPSG:4862')
            uri = 'Point?crs={}'.format(crs.authid())
            lyr = QgsVectorLayer(uri, 'LOCATIONS', 'memory')
            assert sensor is None or isinstance(sensor, SensorInstrument)

            f = sensorExampleQgsFeature(sensor, singleBandOnly=True)
            assert isinstance(f, QgsFeature)
            assert lyr.startEditing()
            for field in f.fields():
                lyr.addAttribute(field)
            lyr.addFeature(f)
            lyr.commitChanges()
            self.mSensorLayers[sensor] = lyr
        return self.mSensorLayers[sensor]

    def checkData(self, index, w, value):
        assert isinstance(index, QModelIndex)
        model = self.mTableView.model()
        if index.isValid() and isinstance(model, PlotSettingsModel3D):
            plotStyle = model.idx2plotStyle(index)
            assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
            if isinstance(w, QgsFieldExpressionWidget):
                assert value == w.expression()
                assert w.isExpressionValid(value) == w.isValidExpression()

                if w.isValidExpression():
                    self.commitData.emit(w)
                else:
                    s = ""
                    #print(('Delegate commit failed',w.asExpression()))
            if isinstance(w, PlotStyleButton):

                self.commitData.emit(w)

    def setEditorData(self, editor, index):
        cname = self.getColumnName(index)
        model = self.mTableView.model()

        w = None
        if index.isValid() and isinstance(model, PlotSettingsModel3D):
            cname = self.getColumnName(index)
            style = model.idx2plotStyle(index)

            if cname == model.cnExpression:
                lastExpr = index.model().data(index, Qt.DisplayRole)
                assert isinstance(editor, QgsFieldExpressionWidget)
                editor.setProperty('lastexpr', lastExpr)
                editor.setField(lastExpr)

            elif cname == model.cnStyle:
                assert isinstance(editor, TemporalProfile3DPlotStyleButton)
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
        model = self.mTableView.model()

        if index.isValid() and isinstance(model, PlotSettingsModel3D):
            if cname == model.cnExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression() and expr != exprLast:
                    model.setData(index, w.asExpression(), Qt.EditRole)

            elif cname == model.cnStyle:
                assert isinstance(w, TemporalProfile3DPlotStyleButton)
                model.setData(index, w.plotStyle(), Qt.EditRole)

            elif cname == model.cnSensor:
                assert isinstance(w, QComboBox)
                sensor = w.itemData(w.currentIndex(), role=Qt.UserRole)
                assert isinstance(sensor, SensorInstrument)
                model.setData(index, sensor, Qt.EditRole)

                s = ""

            elif cname == model.cnTemporalProfile:
                assert isinstance(w, QComboBox)
                TP = w.itemData(w.currentIndex(), role=Qt.UserRole)
                #assert isinstance(TP, TemporalProfile)
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




class PlotSettingsModel3D(QAbstractTableModel):

    #sigSensorAdded = pyqtSignal(SensorPlotSettings)
    sigVisibilityChanged = pyqtSignal(TemporalProfile2DPlotStyle)
    sigPlotStylesAdded = pyqtSignal(list)
    sigPlotStylesRemoved = pyqtSignal(list)

    def __init__(self, parent=None, *args):

        #assert isinstance(tableView, QTableView)

        super(PlotSettingsModel3D, self).__init__(parent=parent)
        self.mTimeSeries = None
        self.cnID = 'ID'
        self.cnExpression = LABEL_EXPRESSION_3D
        self.cnTemporalProfile = 'Coordinate'
        self.cnStyle = 'Style'
        self.cnSensor = 'Sensor'
        self.columnNames = [self.cnTemporalProfile, self.cnSensor, self.cnStyle, self.cnExpression]

        self.mPlotSettings = []
        #assert isinstance(plotWidget, DateTimePlotWidget)

        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder


        self.sort(0, Qt.AscendingOrder)

    def hasStyleForSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        for plotStyle in self.mPlotSettings:
            assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
            if plotStyle.sensor() == sensor:
                return True
        return False


    def createStyle(self, sensor):
        if not self.hasStyleForSensor(sensor):
            s = TemporalProfile3DPlotStyle()
            #use another color for the new sensor
            if len(self) > 0:
                color = self[-1].color()
                s.setColor(nextColor(color))
            self.insertPlotStyles([s])

    def onSensorRemoved(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        self.removePlotStyles([s for s in self.mPlotSettings if s.sensor() == sensor])



    def __len__(self):
        return len(self.mPlotSettings)

    def __iter__(self):
        return iter(self.mPlotSettings)

    def __getitem__(self, slice):
        return self.mPlotSettings[slice]

    def __contains__(self, item):
        return item in self.mPlotSettings


    def columnIndex(self, name):
        return self.columnNames.index(name)


    def insertPlotStyles(self, plotStyles, i=None):
        """
        Inserts PlotStyle
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        :param i: index to insert, defaults to the last list position
        """
        if isinstance(plotStyles, TemporalProfile3DPlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)
        for plotStyle in plotStyles:
            assert isinstance(plotStyle, TemporalProfile3DPlotStyle)

        if i is None:
            i = len(self.mPlotSettings)

        if len(plotStyles) > 0:
            self.beginInsertRows(QModelIndex(), i, i + len(plotStyles)-1)
            for j, plotStyle in enumerate(plotStyles):
                assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
                self.mPlotSettings.insert(i+j, plotStyle)
            self.endInsertRows()
            self.sigPlotStylesAdded.emit(plotStyles)

    def removePlotStyles(self, plotStyles):
        """
        Removes PlotStyle instances
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        """
        if isinstance(plotStyles, TemporalProfile3DPlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)

        if len(plotStyles) > 0:
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
                if plotStyle in self.mPlotSettings:
                    idx = self.plotStyle2idx(plotStyle)
                    self.beginRemoveRows(QModelIndex(), idx.row(),idx.row())
                    self.mPlotSettings.remove(plotStyle)
                    self.endRemoveRows()
            self.sigPlotStylesRemoved.emit(plotStyles)

    def sort(self, col, order):
        if self.rowCount() == 0:
            return


        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        #self.beginMoveRows(idxSrc,

        if colName == self.cnSensor:
            self.mPlotSettings.sort(key = lambda sv:sv.sensor().name(), reverse=r)

    def rowCount(self, parent = QModelIndex()):
        return len(self.mPlotSettings)


    def removeRows(self, row, count , parent = QModelIndex()):

        self.beginRemoveRows(parent, row, row + count-1)

        toRemove = self.mPlotSettings[row:row + count]

        for tsd in toRemove:
            self.mPlotSettings.remove(tsd)

        self.endRemoveRows()

    def plotStyle2idx(self, plotStyle):

        assert isinstance(plotStyle, TemporalProfile3DPlotStyle)

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
        return len(self.columnNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnNames[index.column()]
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfile3DPlotStyle):
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
                    tp = plotStyle.temporalProfile()
                    if isinstance(tp, TemporalProfile):
                        value = tp.name()
                    else:
                        value = 'undefined'

            elif role == Qt.EditRole:
                if columnName == self.cnExpression:
                    value = plotStyle.expression()

            elif role == Qt.CheckStateRole:
                if columnName == self.cnTemporalProfile:
                    value = Qt.Checked if plotStyle.isVisible() else Qt.Unchecked

            elif role == Qt.UserRole:
                value = plotStyle
                if columnName == self.cnSensor:
                    value = plotStyle.sensor()
                elif columnName == self.cnStyle:
                    value = plotStyle
                else:
                    value = plotStyle
        #print(('get data',value))
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return False
        #print(('Set data', index.row(), index.column(), value, role))
        columnName = self.columnNames[index.column()]

        if value is None:
            return False

        result = False
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfile3DPlotStyle):
            """
            if role in [Qt.DisplayRole]:
                if columnName == self.cnExpression and isinstance(value, str):
                    plotStyle.setExpression(value)
                    result = True
                elif columnName == self.cnStyle:
                    if isinstance(value, PlotStyle):
                        plotStyle.copyFrom(value)
                        result = True
            """

            if role == Qt.CheckStateRole:
                if columnName == self.cnTemporalProfile:
                    plotStyle.setVisibility(value == Qt.Checked)
                    result = True

            if role == Qt.EditRole:
                if columnName == self.cnSensor:
                    plotStyle.setSensor(value)
                    result = True
                elif columnName == self.cnExpression:
                    plotStyle.setExpression(value)
                    result = True
                elif columnName == self.cnTemporalProfile:
                    plotStyle.setTemporalProfile(value)
                    result = True
                elif columnName == self.cnStyle:
                    plotStyle.copyFrom(value)
                    result = True

        return result


    def flags(self, index):
        if index.isValid():
            stype = self.idx2plotStyle(index)
            columnName = self.columnNames[index.column()]
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
            return self.columnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None


class PlotSettingsModel2D(QAbstractTableModel):

    #sigSensorAdded = pyqtSignal(SensorPlotSettings)
    sigVisibilityChanged = pyqtSignal(TemporalProfile2DPlotStyle)
    sigDataChanged = pyqtSignal(TemporalProfile2DPlotStyle)
    sigPlotStylesAdded = pyqtSignal(list)
    sigPlotStylesRemoved = pyqtSignal(list)


    def __init__(self, parent=None, *args):

        #assert isinstance(tableView, QTableView)

        super(PlotSettingsModel2D, self).__init__(parent=parent)
        #assert isinstance(temporalProfileCollection, TemporalProfileCollection)

        self.cnID = 'ID'
        self.cnSensor = 'Sensor'
        self.cnExpression = LABEL_EXPRESSION_2D
        self.cnStyle = 'Style'
        self.cnTemporalProfile = 'Coordinate'
        self.columnNames = [self.cnTemporalProfile, self.cnSensor, self.cnStyle, self.cnExpression]

        self.mPlotSettings = []
        #assert isinstance(plotWidget, DateTimePlotWidget)
        #self.mPlotWidget = plotWidget
        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        #assert isinstance(self.tpCollection.TS, TimeSeries)
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
        return self.columnNames.index(name)

    def signaler(self, idxUL, idxLR):
        if idxUL.isValid():

            plotStyle = self.idx2plotStyle(idxUL)
            cname = self.columnNames[idxUL.column()]
            if cname in [self.cnSensor,self.cnStyle]:
                self.sigVisibilityChanged.emit(plotStyle)
            if cname in [self.cnExpression]:
                self.sigDataChanged.emit(plotStyle)




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
            assert isinstance(p, TemporalProfile2DPlotStyle)
            expression = p.expression()
            #remove leading & tailing "
            bandKeys = regBandKey.findall(expression)
            for bandIndex in [bandKey2bandIndex(key) for key in bandKeys]:
                bandIndices.add(bandIndex)

        return bandIndices


    def insertPlotStyles(self, plotStyles, i=None):
        """
        Inserts PlotStyle
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        :param i: index to insert, defaults to the last list position
        """
        if isinstance(plotStyles, TemporalProfile2DPlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)
        for plotStyle in plotStyles:
            assert isinstance(plotStyle, TemporalProfile2DPlotStyle)

        if i is None:
            i = len(self.mPlotSettings)

        if len(plotStyles) > 0:
            self.beginInsertRows(QModelIndex(), i, i + len(plotStyles)-1)
            for j, plotStyle in enumerate(plotStyles):
                assert isinstance(plotStyle, TemporalProfile2DPlotStyle)
                self.mPlotSettings.insert(i+j, plotStyle)
            self.endInsertRows()
            self.sigPlotStylesAdded.emit(plotStyles)

    def removePlotStyles(self, plotStyles):
        """
        Removes PlotStyle instances
        :param plotStyles: TemporalProfilePlotStyle | [list-of-TemporalProfilePlotStyle]
        """
        if isinstance(plotStyles, PlotStyle):
            plotStyles = [plotStyles]
        assert isinstance(plotStyles, list)

        if len(plotStyles) > 0:
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, PlotStyle)
                if plotStyle in self.mPlotSettings:
                    idx = self.plotStyle2idx(plotStyle)
                    self.beginRemoveRows(QModelIndex(), idx.row(),idx.row())
                    self.mPlotSettings.remove(plotStyle)
                    self.endRemoveRows()
            self.sigPlotStylesRemoved.emit(plotStyles)

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

        assert isinstance(plotStyle, TemporalProfile2DPlotStyle)

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
        return len(self.columnNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnNames[index.column()]
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfile2DPlotStyle):
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
                    tp = plotStyle.temporalProfile()
                    if isinstance(tp, TemporalProfile):
                        value = tp.name()
                    else:
                        value = 'undefined'

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
        columnName = self.columnNames[index.column()]


        result = False
        plotStyle = self.idx2plotStyle(index)
        if isinstance(plotStyle, TemporalProfile2DPlotStyle):
            if role in [Qt.DisplayRole]:
                if columnName == self.cnExpression:
                    plotStyle.setExpression(value)
                    result = True
                elif columnName == self.cnStyle:
                    if isinstance(value, PlotStyle):
                        plotStyle.copyFrom(value)
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
        assert isinstance(sensorPlotSettings, TemporalProfile2DPlotStyle)
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

        if isinstance(sensorPlotSettings, TemporalProfile2DPlotStyle):
            return sensorPlotSettings
        else:
            return None


    def flags(self, index):
        if index.isValid():
            columnName = self.columnNames[index.column()]
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
            return self.columnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None



class ProfileViewDockUI(QgsDockWidget, loadUI('profileviewdock.ui')):


    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)

        #TBD.
        #self.line.setVisible(False)
        #self.listWidget.setVisible(False)
        self.baseTitle = self.windowTitle()
        self.stackedWidget.currentChanged.connect(self.onStackPageChanged)
        self.stackedWidget.setCurrentWidget(self.page2D)

        self.plotWidget3D = None
        self.plotWidget3DMPL = None

        mode = 'No3D'
        if OPENGL_AVAILABLE:
            self.init3DWidgets('gl')
        elif MATPLOTLIB_AVAILABLE:
            self.init3DWidgets('mpl')


        #pi = self.plotWidget2D.plotItem
        #ax = DateAxis(orientation='bottom', showValues=True)
        #pi.layout.addItem(ax, 3,2)


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

        self.menuTPSaveOptions = QMenu()
        self.menuTPSaveOptions.addAction(self.actionSaveTPCoordinates)
        self.menuTPSaveOptions.addAction(self.actionSaveTPCSV)
        self.menuTPSaveOptions.addAction(self.actionSaveTPVector)
        self.btnSaveTemporalProfiles.setMenu(self.menuTPSaveOptions)

    def init3DWidgets(self, mode):
        assert mode in ['gl','mpl']
        l = self.frame3DPlot.layout()

        if True and OPENGL_AVAILABLE and mode == 'gl':

            from timeseriesviewer.temporalprofiles3dGL import ViewWidget3D
            self.plotWidget3D = ViewWidget3D(parent=self.frame3DPlot)
            self.plotWidget3D.setObjectName('plotWidget3D')

            size = self.labelDummy3D.size()
            l.addWidget(self.plotWidget3D)
            self.plotWidget3D.setSizePolicy(self.labelDummy3D.sizePolicy())
            self.labelDummy3D.setVisible(False)
            l.removeWidget(self.labelDummy3D)
            self.plotWidget3D.setBaseSize(size)
            self.splitter3D.setSizes([100, 100])

        elif MATPLOTLIB_AVAILABLE and mode == 'mpl':
            from timeseriesviewer.temporalprofiles3dMPL import MyMplCanvas3D
            self.plotWidget3DMPL = MyMplCanvas3D()
            self.plotWidget3DMPL.setObjectName('plotWidget3DMPL')
            size = self.labelDummy3D.size()
            l.addWidget(self.plotWidget3D)
            self.plotWidget3D.setSizePolicy(self.labelDummy3D.sizePolicy())
            self.labelDummy3D.setVisible(False)
            l.removeWidget(self.labelDummy3D)
            self.plotWidget3D.setBaseSize(size)
            self.splitter3D.setSizes([100, 100])

    def onStackPageChanged(self, i):
        w = self.stackedWidget.currentWidget()
        title = self.baseTitle
        if w == self.page2D:
            title = '{} | 2D'.format(title)
        elif w == self.page3D:
            title = '{} | 3D'.format(title)
        elif w == self.pagePixel:
            title = '{} | Coordinates'.format(title)
        self.setWindowTitle(title)

NEXT_COLOR_HUE_DELTA_CON = 10
NEXT_COLOR_HUE_DELTA_CAT = 100
def nextColor(color, mode='cat'):
    """
    Returns another color
    :param color: the previous color
    :param mode: 'cat' - for categorical color jump (next color looks pretty different to previous)
                 'con' - for continuous color jump (next color looks similar to previous)
    :return:
    """
    assert mode in ['cat','con']
    assert isinstance(color, QColor)
    hue, sat, value, alpha = color.getHsl()
    if mode == 'cat':
        hue += NEXT_COLOR_HUE_DELTA_CAT
    elif mode == 'con':
        hue += NEXT_COLOR_HUE_DELTA_CON
    if sat == 0:
        sat = 255
        value = 128
        alpha = 255
        s = ""
    while hue > 360:
        hue -= 360

    return QColor.fromHsl(hue, sat, value, alpha)




class SpectralTemporalVisualization(QObject):

    sigShowPixel = pyqtSignal(TimeSeriesDatum, QgsPoint, QgsCoordinateReferenceSystem)

    """
    Signalizes to move to specific date of interest
    """
    sigMoveToDate = pyqtSignal(np.datetime64)


    def __init__(self, ui):
        super(SpectralTemporalVisualization, self).__init__()

        assert isinstance(ui, ProfileViewDockUI), 'arg ui of type: {} {}'.format(type(ui), str(ui))
        self.ui = ui

        import timeseriesviewer.pixelloader
        if DEBUG:
            timeseriesviewer.pixelloader.DEBUG = True

        #the timeseries. will be set later
        self.TS = None
        self.plot_initialized = False

        self.plot2D = ui.plotWidget2D
        self.plot2D.getViewBox().sigMoveToDate.connect(self.sigMoveToDate)
        self.plot3D = ui.plotWidget3D

        # temporal profile collection to store loaded values
        self.tpCollection = TemporalProfileCollection()
        self.tpCollection.setMaxProfiles(self.ui.sbMaxTP.value())
        self.tpCollection.sigTemporalProfilesAdded.connect(self.onTemporalProfilesAdded)
        self.tpCollectionListModel = TemporalProfileCollectionListModel(self.tpCollection)
        self.ui.tableViewTemporalProfiles.setModel(self.tpCollection)
        self.ui.tableViewTemporalProfiles.selectionModel().selectionChanged.connect(self.onTemporalProfileSelectionChanged)
        self.ui.tableViewTemporalProfiles.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.ui.tableViewTemporalProfiles.contextMenuEvent = self.onTemporalProfilesContextMenu
        # pixel loader to load pixel values in parallel
        self.pixelLoader = PixelLoader()
        self.pixelLoader.sigPixelLoaded.connect(self.onPixelLoaded)
        self.pixelLoader.sigLoadingStarted.connect(lambda: self.ui.progressInfo.setText('Start loading...'))
        #self.pixelLoader.sigLoadingStarted.connect(self.tpCollection.prune)
        self.pixelLoader.sigLoadingFinished.connect(lambda : self.plot2D.enableAutoRange('x', False))

        #set the plot models for 2D
        self.plotSettingsModel2D = PlotSettingsModel2D()
        self.ui.tableView2DProfiles.setModel(self.plotSettingsModel2D)
        self.ui.tableView2DProfiles.setSortingEnabled(False)
        self.ui.tableView2DProfiles.selectionModel().selectionChanged.connect(self.onPlot2DSelectionChanged)
        self.ui.tableView2DProfiles.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.delegateTableView2D = None #wil be set with connecting the TimeSeries
        self.plotSettingsModel2D.sigDataChanged.connect(self.requestUpdate)
        self.plotSettingsModel2D.rowsInserted.connect(self.onRowsInserted2D)

        # set the plot models for 3D
        self.plotSettingsModel3D = PlotSettingsModel3D()
        self.ui.tableView3DProfiles.setModel(self.plotSettingsModel3D)
        self.ui.tableView3DProfiles.setSortingEnabled(False)
        self.ui.tableView2DProfiles.selectionModel().selectionChanged.connect(self.onPlot3DSelectionChanged)
        self.ui.tableView3DProfiles.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.plotSettingsModel3D.rowsInserted.connect(self.onRowsInserted3D)
        self.delegateTableView3D = None #will be set with connecting the TimeSeries

        self.reset3DCamera()

        def onTemporalProfilesRemoved(removedProfiles):
            #set to valid temporal profile

            affectedStyles2D = [p for p in self.plotSettingsModel2D if p.temporalProfile() in removedProfiles]
            affectedStyles3D = [p for p in self.plotSettingsModel3D if p.temporalProfile() in removedProfiles]
            alternativeProfile = self.tpCollection[-1] if len(self.tpCollection) > 0 else None
            for s in affectedStyles2D:
                assert isinstance(s, TemporalProfile2DPlotStyle)
                m = self.plotSettingsModel2D
                idx = m.plotStyle2idx(s)
                idx = m.createIndex(idx.row(), m.columnNames.index(m.cnTemporalProfile))
                m.setData(idx, alternativeProfile, Qt.EditRole)

            for s in affectedStyles3D:
                assert isinstance(s, TemporalProfile3DPlotStyle)
                m = self.plotSettingsModel3D
                idx = m.plotStyle2idx(s)
                idx = m.createIndex(idx.row(), m.columnNames.index(m.cnTemporalProfile))
                m.setData(idx, alternativeProfile, Qt.EditRole)

        self.tpCollection.sigTemporalProfilesRemoved.connect(onTemporalProfilesRemoved)

        # remove / add plot style
        def on2DPlotStyleRemoved(plotStyles):
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, PlotStyle)
                for pi in plotStyle.mPlotItems:
                    self.plot2D.getPlotItem().removeItem(pi)

        def on3DPlotStyleRemoved(plotStyles):
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
                for pi in plotStyle.mPlotItems:
                    self.plot3D.removeItem(pi)

        self.plotSettingsModel2D.sigPlotStylesRemoved.connect(on2DPlotStyleRemoved)


        #initialize the update loop
        self.updateRequested = True
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.onDataUpdate)
        self.updateTimer.start(2000)

        self.sigMoveToDate.connect(self.onMoveToDate)

        self.initActions()


    def onTemporalProfilesContextMenu(self, event):
        assert isinstance(event, QContextMenuEvent)
        tableView = self.ui.tableViewTemporalProfiles
        selectionModel = self.ui.tableViewTemporalProfiles.selectionModel()
        assert isinstance(selectionModel, QItemSelectionModel)
        idx = self.ui.tableViewTemporalProfiles.indexAt(event.pos())

        model = self.ui.tableViewTemporalProfiles.model()
        assert isinstance(model, TemporalProfileCollection)

        spatialPoints = []
        if idx.isValid():
            tp = model.idx2tp(idx)
            assert isinstance(tp, TemporalProfile)
            spatialPoints.append(tp.coordinate())
        else:
            #load for all
            for tp in model:
                assert isinstance(tp, TemporalProfile)
                spatialPoints.append(tp.coordinate())


        menu = QMenu()

        a = menu.addAction('Load missing')
        a.setToolTip('Loads missing band-pixels.')
        a.triggered.connect(lambda : self.loadCoordinate(spatialPoints=spatialPoints, mode='all'))
        s = ""

        a = menu.addAction('Reload')
        a.setToolTip('Reloads all band-pixels.')
        a.triggered.connect(lambda: self.loadCoordinate(spatialPoints=spatialPoints, mode='reload'))

        menu.popup(tableView.viewport().mapToGlobal(event.pos()))
        self.menu = menu

    def setTimeSeries(self, TS):

        assert isinstance(TS, TimeSeries)
        self.TS = TS
        self.tpCollection.connectTimeSeries(self.TS)

        self.delegateTableView2D = PlotSettingsModel2DWidgetDelegate(self.ui.tableView2DProfiles, self.TS, self.tpCollectionListModel)
        self.delegateTableView2D.setItemDelegates(self.ui.tableView2DProfiles)

        self.delegateTableView3D = PlotSettingsModel3DWidgetDelegate(self.ui.tableView3DProfiles, self.TS, self.tpCollectionListModel)
        self.delegateTableView3D.setItemDelegates(self.ui.tableView3DProfiles)

    def selected2DPlotStyles(self):
        result = []

        m = self.ui.tableView2DProfiles.model()
        for idx in selectedModelIndices(self.ui.tableView2DProfiles):
            result.append(m.idx2plotStyle(idx))
        return result

    def selectedTemporalProfiles(self):
        result = []
        m = self.ui.tableViewTemporalProfiles.model()
        for idx in selectedModelIndices(self.ui.tableViewTemporalProfiles):
            result.append(m.idx2tp(idx))
        return result

    def removePlotStyles2D(self, plotStyles):
        m = self.ui.tableView2DProfiles.model()
        if isinstance(m, PlotSettingsModel2D):
            m.removePlotStyles(plotStyles)




    def removeTemporalProfiles(self, temporalProfiles):
        m = self.ui.tableViewTemporalProfiles.model()
        if isinstance(m, TemporalProfileCollection):
            m.removeTemporalProfiles(temporalProfiles)

    def createNewPlotStyle2D(self):
        l = len(self.tpCollection)
        if l == 0:
            return

        plotStyle = TemporalProfile2DPlotStyle()
        plotStyle.sigExpressionUpdated.connect(self.updatePlot2D)

        sensors = list(self.TS.Sensors.keys())
        if len(sensors) > 0:
            plotStyle.setSensor(sensors[0])

        if len(self.tpCollection) > 0:
            temporalProfile = self.tpCollection[0]
            plotStyle.setTemporalProfile(temporalProfile)


        if len(self.plotSettingsModel2D) > 0:
            lastStyle = self.plotSettingsModel2D[0] #top style in list is the most-recent
            assert isinstance(lastStyle, TemporalProfile2DPlotStyle)
            markerColor = nextColor(lastStyle.markerBrush.color())
            plotStyle.markerBrush.setColor(markerColor)
        self.plotSettingsModel2D.insertPlotStyles([plotStyle], i=0)
        pdi = plotStyle.createPlotItem(self.plot2D)

        assert isinstance(pdi, TemporalProfilePlotDataItem)
        pdi.sigClicked.connect(self.onProfileClicked2D)
        pdi.sigPointsClicked.connect(self.onPointsClicked2D)
        self.plot2D.getPlotItem().addItem(pdi)
        #self.plot2D.getPlotItem().addItem(pg.PlotDataItem(x=[1, 2, 3], y=[1, 2, 3]))
        #plotItem.addDataItem(pdi)
        #plotItem.plot().sigPlotChanged.emit(plotItem)
        self.updatePlot2D()


    def createNewPlotStyle3D(self):
        if not OPENGL_AVAILABLE:
            return

        plotStyle = TemporalProfile3DPlotStyle()
        plotStyle.sigExpressionUpdated.connect(self.updatePlot3D)

        if len(self.tpCollection) > 0:
            temporalProfile = self.tpCollection[0]
            plotStyle.setTemporalProfile(temporalProfile)

        sensors = list(self.TS.Sensors.keys())
        if len(sensors) > 0:
            plotStyle.setSensor(sensors[0])

        self.plotSettingsModel3D.insertPlotStyles([plotStyle], i=0) # latest to the top
        self.updatePlot3D()

    def onProfileClicked2D(self, pdi):
        if isinstance(pdi, TemporalProfilePlotDataItem):
            sensor = pdi.mPlotStyle.sensor()
            tp = pdi.mPlotStyle.temporalProfile()
            if isinstance(tp, TemporalProfile) and isinstance(sensor, SensorInstrument):
                info = ['Sensor:{}'.format(sensor.name()),
                        'Coordinate:{}, {}'.format(tp.mCoordinate.x(), tp.mCoordinate.y())]
                self.ui.tbInfo2D.setPlainText('\n'.join(info))


    def onPointsClicked2D(self, pdi, spottedItems):
        if isinstance(pdi, TemporalProfilePlotDataItem) and isinstance(spottedItems, list):
            sensor = pdi.mPlotStyle.sensor()
            tp = pdi.mPlotStyle.temporalProfile()
            if isinstance(tp, TemporalProfile) and isinstance(sensor, SensorInstrument):

                info = ['Sensor: {}'.format(sensor.name()),
                        'Coordinate: {}, {}'.format(tp.mCoordinate.x(), tp.mCoordinate.y())]

                for item in spottedItems:
                    pos = item.pos()
                    x = pos.x()
                    y = pos.y()
                    date = num2date(x)
                    info.append('Date: {}\nValue: {}'.format(date, y))

                self.ui.tbInfo2D.setPlainText('\n'.join(info))

    def onTemporalProfilesAdded(self, profiles):
        self.tpCollection.prune()
        for plotStyle in self.plotSettingsModel3D:
            assert isinstance(plotStyle, TemporalProfilePlotStyleBase)
            if not isinstance(plotStyle.temporalProfile(), TemporalProfile):
                r = self.plotSettingsModel3D.plotStyle2idx(plotStyle).row()
                c = self.plotSettingsModel3D.columnIndex(self.plotSettingsModel3D.cnTemporalProfile)
                idx = self.plotSettingsModel3D.createIndex(r,c)
                self.plotSettingsModel3D.setData(idx, self.tpCollection[0])

    def onTemporalProfileSelectionChanged(self, selected, deselected):
        nSelected = len(selected)
        self.ui.actionRemoveTemporalProfile.setEnabled(nSelected > 0)
        self.ui.btnSaveTemporalProfiles.setEnabled(nSelected > 0)

    def onPlot2DSelectionChanged(self, selected, deselected):

        self.ui.actionRemoveStyle2D.setEnabled(len(selected) > 0)

    def onPlot3DSelectionChanged(self, selected, deselected):

        self.ui.actionRemoveStyle3D.setEnabled(len(selected) > 0)

    def initActions(self):

        self.ui.actionRemoveStyle2D.setEnabled(False)
        self.ui.actionRemoveTemporalProfile.setEnabled(False)

        self.ui.btnAddStyle2D.setDefaultAction(self.ui.actionAddStyle2D)
        self.ui.btnRemoveStyle2D.setDefaultAction(self.ui.actionRemoveStyle2D)


        self.ui.btnAddStyle3D.setDefaultAction(self.ui.actionAddStyle3D)
        self.ui.btnRemoveStyle3D.setDefaultAction(self.ui.actionRemoveStyle3D)

        self.ui.actionAddStyle2D.triggered.connect(self.createNewPlotStyle2D)
        self.ui.actionAddStyle3D.triggered.connect(self.createNewPlotStyle3D)

        self.ui.btnRefresh2D.setDefaultAction(self.ui.actionRefresh2D)
        self.ui.btnRefresh3D.setDefaultAction(self.ui.actionRefresh3D)
        self.ui.btnRemoveTemporalProfile.setDefaultAction(self.ui.actionRemoveTemporalProfile)
        self.ui.btnReset3DCamera.setDefaultAction(self.ui.actionReset3DCamera)

        self.ui.actionRefresh2D.triggered.connect(self.updatePlot2D)
        self.ui.actionRefresh3D.triggered.connect(self.updatePlot3D)

        self.ui.btnLoadProfile1.setDefaultAction(self.ui.actionLoadProfileRequest)
        self.ui.btnLoadProfile2.setDefaultAction(self.ui.actionLoadProfileRequest)
        self.ui.btnLoadProfile3.setDefaultAction(self.ui.actionLoadProfileRequest)



        self.ui.actionRemoveStyle2D.triggered.connect(lambda:self.removePlotStyles2D(self.selected2DPlotStyles()))
        self.ui.actionRemoveTemporalProfile.triggered.connect(lambda :self.removeTemporalProfiles(self.selectedTemporalProfiles()))
        self.ui.actionReset3DCamera.triggered.connect(self.reset3DCamera)
        self.tpCollection.sigMaxProfilesChanged.connect(self.ui.sbMaxTP.setValue)
        self.ui.sbMaxTP.valueChanged.connect(self.tpCollection.setMaxProfiles)


        from timeseriesviewer.temporalprofiles2d import saveTemporalProfiles
        DEF_PATH = None

        self.ui.actionSaveTPCoordinates.triggered.connect(
            lambda: saveTemporalProfiles(self.tpCollection[:],
                    QFileDialog.getSaveFileName(
                        self.ui, 'Save Temporal Profile Coordinates',
                        DEF_PATH, 'ESRI Shapefile (*.shp);;Geopackage (*.gpkg);;Textfile (*.csv *.txt)'
                    ), mode='coordinate'
            )
        )

        self.ui.actionSaveTPCSV.triggered.connect(
            lambda: saveTemporalProfiles(self.tpCollection[:],
                                         QFileDialog.getSaveFileName(
                                             self.ui, 'Save Temporal Profiles to Text File.',
                                             DEF_PATH,
                                             'Textfile (*.csv *.txt)'
                                         ), mode ='all'
                                         )
        )


        self.ui.actionSaveTPVector.triggered.connect(
            lambda: saveTemporalProfiles(self.tpCollection[:],
                                         QFileDialog.getSaveFileName(
                                             self.ui, 'Save Temporal Profiles to Vector File.',
                                             DEF_PATH,
                                             'ESRI Shapefile (*.shp);;Geopackage (*.gpkg)'
                                         ), mode = 'all'
                                         )
        )
        #todo: self.ui.actionRemoveStyle2D.triggered.connect(self.plotSettingsModel.createPlotStyle)

    def reset3DCamera(self, *args):

        if OPENGL_AVAILABLE:
            self.plot3D.resetCamera()



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

            t = 'Loaded {} pixel from {}.'.format(len(d.resProfiles), bn)
            self.tpCollection.addPixelLoaderResult(d)
            self.updateRequested = True
        else:
            t = 'Failed loading from {}.'.format(bn)
            if d.info and d.info != '':
                t += '({})'.format(d.info)

        # QgsApplication.processEvents()
        self.ui.progressInfo.setText(t)

    def requestUpdate(self, *args):
        self.updateRequested = True
        #next time

    def onRowsInserted2D(self, parent, start, end):
        model = self.ui.tableView2DProfiles.model()
        if isinstance(model, PlotSettingsModel2D):
            colExpression = model.columnIndex(model.cnExpression)
            colStyle = model.columnIndex(model.cnStyle)
            while start <= end:
                idxExpr = model.createIndex(start, colExpression)
                idxStyle = model.createIndex(start, colStyle)
                self.ui.tableView2DProfiles.openPersistentEditor(idxExpr)
                self.ui.tableView2DProfiles.openPersistentEditor(idxStyle)
                start += 1

    def onRowsInserted3D(self, parent, start, end):
        model = self.ui.tableView3DProfiles.model()
        if isinstance(model, PlotSettingsModel3D):
            colExpression = model.columnIndex(model.cnExpression)
            colStyle = model.columnIndex(model.cnStyle)
            while start <= end:
                idxStyle = model.createIndex(start, colStyle)
                idxExpr = model.createIndex(start, colExpression)
                self.ui.tableView3DProfiles.openPersistentEditor(idxStyle)
                self.ui.tableView3DProfiles.openPersistentEditor(idxExpr)
                start += 1

    def onObservationClicked(self, plotDataItem, points):
        for p in points:
            tsd = p.data()
            #print(tsd)




    LOADING_MODES = ['missing','reload','all']
    def loadCoordinate(self, spatialPoints=None, LUT_bandIndices=None, mode='missing'):
        """
        :param spatialPoints: [list-of-geometries] to load pixel values from
        :param LUT_bandIndices: dictionary {sensor:[indices]} with band indices to be loaded per sensor
        :param mode:
        :return:
        """
        """
        Loads a temporal profile for a single or multiple geometries.
        :param spatialPoints: SpatialPoint | [list-of-SpatialPoints]
        """
        assert mode in SpectralTemporalVisualization.LOADING_MODES

        if not isinstance(self.plotSettingsModel2D, PlotSettingsModel2D):
            return False

        #if not self.pixelLoader.isReadyToLoad():
        #    return False

        assert isinstance(self.TS, TimeSeries)

        #Get or create the TimeSeriesProfiles which will store the loaded values

        tasks = []
        TPs = []
        theGeometries = []


        # Define which (new) bands need to be loaded for each sensor
        if LUT_bandIndices is None:
            LUT_bandIndices = dict()
            for sensor in self.TS.Sensors:
                if mode in ['all','reload']:
                    LUT_bandIndices[sensor] = list(range(sensor.nb))
                else:
                    LUT_bandIndices[sensor] = self.plotSettingsModel2D.requiredBandsIndices(sensor)

        assert isinstance(LUT_bandIndices, dict)
        for sensor in self.TS.Sensors:
            assert sensor in LUT_bandIndices.keys()

        #update new / existing points
        if isinstance(spatialPoints, SpatialPoint):
            spatialPoints = [spatialPoints]

        for spatialPoint in spatialPoints:
            assert isinstance(spatialPoint, SpatialPoint)
            TP = self.tpCollection.fromSpatialPoint(spatialPoint)


            #if not TP exists for this point, create an empty one
            if not isinstance(TP, TemporalProfile):

                TP = TemporalProfile(self.TS, spatialPoint)

                #LIFO - last TP is the first
                self.tpCollection.insertTemporalProfiles(TP, i=0)

                if len(self.tpCollection) == 1:
                    if len(self.plotSettingsModel2D) == 0:
                        self.createNewPlotStyle2D()

                    if len(self.plotSettingsModel3D) == 0:
                        self.createNewPlotStyle3D()

            TPs.append(TP)
            theGeometries.append(TP.mCoordinate)


        TP_ids = [TP.mID for TP in TPs]
        #each TSD is a Task
        s = ""
        #a Task defines which bands are to be loaded
        for tsd in self.TS:

            #do not load from invisible TSDs
            if not tsd.isVisible():
                continue

            #which bands do we need to load?
            requiredIndices = set(LUT_bandIndices[tsd.sensor])
            if len(requiredIndices) == 0:
                continue

            if mode == 'missing':
                missingIndices = set()

                for TP in TPs:
                    assert isinstance(TP, TemporalProfile)
                    need2load = TP.missingBandIndices(tsd, requiredIndices=requiredIndices)
                    missingIndices = missingIndices.union(need2load)

                missingIndices = sorted(list(missingIndices))
            else:
                missingIndices = requiredIndices

            if len(missingIndices) > 0:
                task = PixelLoaderTask(tsd.pathImg, theGeometries,
                                       bandIndices=missingIndices,
                                       temporalProfileIDs=TP_ids)
                tasks.append(task)

        if len(tasks) > 0:
            aGoodDefault = 2 if len(self.TS) > 25 else 1

            #self.pixelLoader.setNumberOfProcesses(SETTINGS.value('profileloader_threads', aGoodDefault))
            if DEBUG:
                print('Start loading for {} geometries from {} sources...'.format(
                    len(theGeometries), len(tasks)
                ))
            self.pixelLoader.startLoading(tasks)

        else:
            if DEBUG:
                print('Data for geometries already loaded')

        s  =""

    def addData(self, sensorView = None):
        if sensorView is None:
            for sv in self.plotSettingsModel2D.items:
                self.setData(sv)
        else:
            assert isinstance(sensorView, TemporalProfile2DPlotStyle)
            self.setData2D(sensorView)


    @QtCore.pyqtSlot()
    def onDataUpdate(self):

        self.tpCollection.prune()

        for plotSetting in self.plotSettingsModel2D:
            assert isinstance(plotSetting, TemporalProfile2DPlotStyle)
            tp = plotSetting.temporalProfile()
            for pdi in plotSetting.mPlotItems:
                assert isinstance(pdi, TemporalProfilePlotDataItem)
                pdi.updateDataAndStyle()
            if isinstance(tp, TemporalProfile) and plotSetting.temporalProfile().updated():
                plotSetting.temporalProfile().resetUpdatedFlag()


        for i in self.plot2D.getPlotItem().dataItems:
            i.updateItems()


        notInit = [0, 1] == self.plot2D.getPlotItem().getAxis('bottom').range
        if notInit:
            x0 = x1 = None
            for plotSetting in self.plotSettingsModel2D:
                assert isinstance(plotSetting, TemporalProfile2DPlotStyle)
                for pdi in plotSetting.mPlotItems:
                    assert isinstance(pdi, TemporalProfilePlotDataItem)
                    if pdi.xData.ndim == 0 or pdi.xData.shape[0] == 0:
                        continue
                    if x0 is None:
                        x0 = pdi.xData.min()
                        x1 = pdi.xData.max()
                    else:
                        x0 = min(pdi.xData.min(), x0)
                        x1 = max(pdi.xData.max(), x1)

            if x0 is not None:
                self.plot2D.getPlotItem().setXRange(x0, x1)
                #self.plot2D.xAxisInitialized = True

    @QtCore.pyqtSlot()
    def updatePlot3D(self):
        if OPENGL_AVAILABLE:
            from pyqtgraph.opengl import GLViewWidget
            from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem
            import pyqtgraph.opengl as gl
            from timeseriesviewer.temporalprofiles3dGL import ViewWidget3D
            assert isinstance(self.plot3D, ViewWidget3D)

            # 1. ensure that data from all bands will be loaded
            #    new loaded values will be shown in the next updatePlot3D call
            coordinates = []
            for plotStyle3D in self.plotSettingsModel3D:
                assert isinstance(plotStyle3D, TemporalProfile3DPlotStyle)
                if plotStyle3D.isPlotable():
                    coordinates.append(plotStyle3D.temporalProfile().mCoordinate)

            if len(coordinates) > 0:
                self.loadCoordinate(coordinates, mode='all')

            # 2. remove old plot items
            self.plot3D.clearItems()

            # 3. add new plot items
            plotItems = []
            for plotStyle3D in self.plotSettingsModel3D:
                assert isinstance(plotStyle3D, TemporalProfile3DPlotStyle)
                if plotStyle3D.isPlotable():
                    items = plotStyle3D.createPlotItem(None)
                    plotItems.extend(items)

            self.plot3D.addItems(plotItems)
            self.plot3D.updateDataRanges()
            self.plot3D.resetScaling()
            #self.plot3D.resetCamera()

    @QtCore.pyqtSlot()
    def updatePlot2D(self):
        if isinstance(self.plotSettingsModel2D, PlotSettingsModel2D):
            if DEBUG:
                print('Update plot...')

            pi = self.plot2D.getPlotItem()

            locations = set()
            for plotStyle in self.plotSettingsModel2D:
                assert isinstance(plotStyle, TemporalProfile2DPlotStyle)
                if plotStyle.isPlotable():
                    locations.add(plotStyle.temporalProfile().mCoordinate)

                    for pdi in plotStyle.mPlotItems:
                        assert isinstance(pdi, TemporalProfilePlotDataItem)
                        pdi.updateDataAndStyle()

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
    qgsApp = utils.initQgisApplication(qgisDebug=True)
    DEBUG = False

    if False:
        f = QgsFeature()

        fields = QgsFields()
        field = QgsField('b', QVariant.Double, 'double', 40, 5)
        fields.append(field)
        f.setFields(fields)

        expr = QgsExpression('b')

        for n in [23, 42.24, None]:
            f.setAttribute('b', n)
            context = QgsExpressionContextUtils.createFeatureBasedContext(f, f.fields())
            r = expr.evaluate(context)
            print((n,r))
        s = ""


    if False: #the ultimative test for floating point division correctness, at least on a DOY-level
        date1 = np.datetime64('1960-12-31','D')
        assert date1 == num2date(date2num(date1))
        #1960 - 12 - 31
        for year in  range(1960, 2057):
            for doy in range(1, daysPerYear(year)+1):
                dt = datetime.timedelta(days=doy - 1)
                date1 = np.datetime64('{}-01-01'.format(year)) + np.timedelta64(doy-1,'D')
                date2 = datetime.date(year=year, month=1, day=1) + datetime.timedelta(days=doy-1)

                assert date1 == num2date(date2num(date1), dt64=True), 'date1: {}'.format(date1)
                assert date2 == num2date(date2num(date2), dt64=False), 'date2: {}'.format(date1)

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
        for tsd in TS:
            ext = tsd.spatialExtent()
            if ext.crs().description() != '':
                break
        cp1 = SpatialPoint(ext.crs(),ext.center())
        cpND = SpatialPoint(ext.crs(), 681151.214,-752388.476)
        cp2 = SpatialPoint(ext.crs(), ext.center())
        cp3 = SpatialPoint(ext.crs(), ext.center().x()+500, ext.center().y()+250)

        STVis.createNewPlotStyle2D()

        def addProfile():
            x0,y1 = ext.upperLeftPt()
            x1,y0 = ext.lowerRightPt()

            x = x0 + (x1 - x0) * np.random.sample()
            y = y0 + (y1 - y0) * np.random.sample()
            pt = SpatialPoint(ext.crs(), x, y)
            STVis.loadCoordinate(pt)


        btn = QPushButton('Add Profile')
        btn.clicked.connect(addProfile)
        btn.show()

        if False:
            for tp in STVis.tpCollection:
                assert isinstance(tp, TemporalProfile)
                tp.plot()
        #STVis.tpCollection.removeTemporalProfiles(STVis.tpCollection[-1])
        STVis.createNewPlotStyle3D()
        STVis.ui.listWidget.setCurrentRow(1)

        STVis.loadCoordinate(cpND)
        # STVis.loadCoordinate(cp2)
        # STVis.loadCoordinate(cp3)

    qgsApp.exec_()
    qgsApp.exitQgis()

