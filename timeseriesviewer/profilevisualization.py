# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
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
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.timeseries import *
from timeseriesviewer.utils import SpatialExtent, SpatialPoint, px2geo, loadUI, nextColor
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleButton
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderTask
from timeseriesviewer.sensorvisualization import SensorListModel
from timeseriesviewer.temporalprofiles2d import LABEL_EXPRESSION_2D
from timeseriesviewer.temporalprofiles3d import LABEL_EXPRESSION_3D

import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph import AxisItem


import numpy as np

DEBUG = False
OPENGL_AVAILABLE = False
ENABLE_OPENGL = False

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
    def __init__(self, tableView, temporalProfileLayer, parent=None):
        assert isinstance(tableView, QTableView)
        assert isinstance(temporalProfileLayer, TemporalProfileLayer)
        super(PlotSettingsModel2DWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mTemporalProfileLayer = temporalProfileLayer
        self.mTimeSeries = temporalProfileLayer.timeSeries()

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
        #if isinstance(sensor, SensorInstrument):
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
                if cname == model.cnExpression:

                    w = QgsFieldExpressionWidget(parent=parent)
                    w.setExpressionDialogTitle('Values')
                    w.setToolTip('Set an expression to specify the image band or calculate a spectral index.')
                    w.fieldChanged[str, bool].connect(lambda n, b: self.checkData(index, w, w.expression()))
                    w.setExpression(plotStyle.expression())
                    plotStyle.sigSensorChanged.connect(lambda s: w.setLayer(self.exampleLyr(s)))
                    if isinstance(plotStyle.sensor(), SensorInstrument):
                        w.setLayer(self.exampleLyr(plotStyle.sensor()))




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
                    w = QgsFeatureListComboBox(parent=parent)
                    w.setSourceLayer(self.mTemporalProfileLayer)
                    w.setIdentifierField('id')
                    w.setDisplayExpression('to_string("id")+\'  \'+"name"')
                    w.setAllowNull(False)
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
                assert isinstance(editor, QgsFeatureListComboBox)
                value = editor.identifierValue()
                if value != QVariant():
                    plotStyle = index.data(role=Qt.UserRole)
                    TP = plotStyle.temporalProfile()
                    editor.setIdentifierValue(TP.id())
                else:
                    s  = ""
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
                if isinstance(w, PlotStyleButton):
                    model.setData(index, w.plotStyle(), Qt.EditRole)

            elif cname == model.cnSensor:
                assert isinstance(w, QComboBox)
                sensor = w.itemData(w.currentIndex(), role=Qt.UserRole)
                if isinstance(sensor, SensorInstrument):
                    model.setData(index, sensor, Qt.EditRole)

            elif cname == model.cnTemporalProfile:
                assert isinstance(w, QgsFeatureListComboBox)
                fid = w.identifierValue()
                if isinstance(fid, int):
                    TP = self.mTemporalProfileLayer.mProfiles.get(fid)
                    model.setData(index, TP, Qt.EditRole)

            else:
                raise NotImplementedError()



class PlotSettingsModel3DWidgetDelegate(QStyledItemDelegate):
    """

    """
    def __init__(self, tableView, temporalProfileLayer, parent=None):
        assert isinstance(tableView, QTableView)
        assert isinstance(temporalProfileLayer, TemporalProfileLayer)
        super(PlotSettingsModel3DWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mTimeSeries = temporalProfileLayer.timeSeries()
        self.mTemporalProfileLayer = temporalProfileLayer
        self.mSensorLayers = {}







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
                    w = QgsFeatureListComboBox(parent=parent)
                    w.setSourceLayer(self.mTemporalProfileLayer)
                    w.setIdentifierField('id')
                    w.setDisplayExpression('to_string("id")+\'  \'+"name"')
                    w.setAllowNull(False)
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
            if isinstance(w, TemporalProfile3DPlotStyleButton):

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
                assert isinstance(editor, QgsFeatureListComboBox)
                value = editor.identifierValue()
                if value != QVariant():
                    plotStyle = index.data(role=Qt.UserRole)
                    TP = plotStyle.temporalProfile()
                    editor.setIdentifierValue(TP.id())
                else:
                    s  = ""

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
                assert isinstance(w, QgsFeatureListComboBox)
                fid = w.identifierValue()
                if isinstance(fid, int):
                    TP = self.mTemporalProfileLayer.mProfiles.get(fid)
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
                    #set the style and trigger an update
                    lastItemType = plotStyle.itemType()
                    lastExpression = plotStyle.expression()
                    plotStyle.copyFrom(value)

                    if lastItemType != plotStyle.itemType() or \
                        lastExpression != plotStyle.expression():
                        plotStyle.updateDataProperties()
                    else:
                        plotStyle.updateStyleProperties()

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
                plotStyle.sigExpressionUpdated.connect(lambda s = plotStyle: self.onStyleUpdated(s))
                self.mPlotSettings.insert(i+j, plotStyle)
            self.endInsertRows()
            self.sigPlotStylesAdded.emit(plotStyles)

    def onStyleUpdated(self, style):

        idx = self.plotStyle2idx(style)
        r = idx.row()
        self.dataChanged.emit(self.createIndex(r, 0), self.createIndex(r, self.columnCount()))

        s = ""


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
                    plotStyle.updateDataProperties()
                    result = True
                elif columnName == self.cnStyle:
                    if isinstance(value, PlotStyle):
                        plotStyle.copyFrom(value)
                        plotStyle.updateStyleProperties()
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

        self.addActions(self.findChildren(QAction))

        self.mActions2D = [self.actionAddStyle2D, self.actionRemoveStyle2D, self.actionRefresh2D, self.actionReset2DPlot]
        self.mActions3D = [self.actionAddStyle3D, self.actionRemoveStyle3D, self.actionRefresh3D,
                           self.actionReset3DCamera]
        self.mActionsTP = [self.actionLoadTPFromOgr, self.actionSaveTemporalProfiles, self.actionToggleEditing,
                           self.actionRemoveTemporalProfile, self.actionLoadMissingValues]
        #TBD.
        #self.line.setVisible(False)
        #self.listWidget.setVisible(False)
        self.baseTitle = self.windowTitle()
        self.stackedWidget.currentChanged.connect(self.onStackPageChanged)


        self.plotWidget3D = None
        self.plotWidget3DMPL = None

        self.init3DWidgets('gl')


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

        self.tableView2DProfiles.horizontalHeader().setResizeMode(QHeaderView.Interactive)

    def init3DWidgets(self, mode='gl'):
        assert mode in ['gl']
        l = self.frame3DPlot.layout()

        if ENABLE_OPENGL and OPENGL_AVAILABLE and mode == 'gl':

            from timeseriesviewer.temporalprofiles3dGL import ViewWidget3D
            self.plotWidget3D = ViewWidget3D(parent=self.labelDummy3D.parent())
            self.plotWidget3D.setObjectName('plotWidget3D')

            size = self.labelDummy3D.size()
            l.addWidget(self.plotWidget3D)
            self.plotWidget3D.setSizePolicy(self.labelDummy3D.sizePolicy())
            self.labelDummy3D.setVisible(False)
            l.removeWidget(self.labelDummy3D)
            #self.plotWidget3D.setBaseSize(size)
            self.splitter3D.setSizes([100, 100])
            self.frameSettings3D.setEnabled(True)
        else:
            self.frameSettings3D.setEnabled(False)

    def onStackPageChanged(self, i):
        w = self.stackedWidget.currentWidget()
        title = self.baseTitle
        if w == self.page2D:
            title = '{} | 2D'.format(title)
            for a in self.mActions2D:
                a.setVisible(True)
            for a in self.mActions3D + self.mActionsTP:
                a.setVisible(False)
        elif w == self.page3D:
            title = '{} | 3D (experimental!)'.format(title)
            for a in self.mActions2D + self.mActionsTP:
                a.setVisible(False)
            for a in self.mActions3D:
                a.setVisible(True)
        elif w == self.pagePixel:
            title = '{} | Coordinates'.format(title)
            for a in self.mActions2D + self.mActions3D:
                a.setVisible(False)
            for a in self.mActionsTP:
                a.setVisible(True)

        w.update()
        self.setWindowTitle(title)


class SpectralTemporalVisualization(QObject):

    sigShowPixel = pyqtSignal(TimeSeriesDatum, QgsPoint, QgsCoordinateReferenceSystem)

    """
    Signalizes to move to specific date of interest
    """
    sigMoveToDate = pyqtSignal(np.datetime64)


    def __init__(self, timeSeries, profileDock):
        super(SpectralTemporalVisualization, self).__init__()

        assert isinstance(profileDock, ProfileViewDockUI)
        self.ui = profileDock

        import timeseriesviewer.pixelloader
        if DEBUG:
            timeseriesviewer.pixelloader.DEBUG = True

        #the timeseries. will be set later
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        self.plot_initialized = False

        self.plot2D = self.ui.plotWidget2D
        self.plot2D.getViewBox().sigMoveToDate.connect(self.sigMoveToDate)
        self.plot3D = self.ui.plotWidget3D

        # temporal profile collection to store loaded values
        self.mTemporalProfileLayer = TemporalProfileLayer(self.TS)
        self.mTemporalProfileLayer.sigTemporalProfilesAdded.connect(self.onTemporalProfilesAdded)
        self.mTemporalProfileLayer.startEditing()
        self.mTemporalProfileLayer.selectionChanged.connect(self.onTemporalProfileSelectionChanged)
        #self.tpCollectionListModel = TemporalProfileCollectionListModel(self.tpCollection)
        self.tpModel = TemporalProfileTableModel(self.mTemporalProfileLayer)
        self.tpFilterModel = TemporalProfileTableFilterModel(self.tpModel)

        self.ui.tableViewTemporalProfiles.setModel(self.tpFilterModel)
        #self.ui.tableViewTemporalProfiles.selectionModel().selectionChanged.connect(self.onTemporalProfileSelectionChanged)
        self.ui.tableViewTemporalProfiles.horizontalHeader().setResizeMode(QHeaderView.Interactive)
        self.ui.tableViewTemporalProfiles.setSortingEnabled(False)
        #self.ui.tableViewTemporalProfiles.contextMenuEvent = self.onTemporalProfilesContextMenu
        # pixel loader to load pixel values in parallel
        config = QgsAttributeTableConfig()
        config.update(self.mTemporalProfileLayer.fields())
        config.setActionWidgetVisible(True)

        hidden = [FN_ID]
        for i, columnConfig in enumerate(config.columns()):

            assert isinstance(columnConfig, QgsAttributeTableConfig.ColumnConfig)
            config.setColumnHidden(i, columnConfig.name in hidden)


        self.mTemporalProfilesTableConfig = config
        self.mTemporalProfileLayer.setAttributeTableConfig(self.mTemporalProfilesTableConfig)
        self.tpFilterModel.setAttributeTableConfig(self.mTemporalProfilesTableConfig)
        #self.ui.tableViewTemporalProfiles.setAttributeTable(self.mTemporalProfilesTableConfig)


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
        self.ui.tableView2DProfiles.horizontalHeader().setResizeMode(QHeaderView.Interactive)
        self.plotSettingsModel2D.sigDataChanged.connect(self.requestUpdate)
        self.plotSettingsModel2D.rowsInserted.connect(self.onRowsInserted2D)
        self.delegateTableView2D = PlotSettingsModel2DWidgetDelegate(self.ui.tableView2DProfiles, self.mTemporalProfileLayer)
        self.delegateTableView2D.setItemDelegates(self.ui.tableView2DProfiles)


        # set the plot models for 3D
        self.plotSettingsModel3D = PlotSettingsModel3D()
        self.ui.tableView3DProfiles.setModel(self.plotSettingsModel3D)
        self.ui.tableView3DProfiles.setSortingEnabled(False)
        self.ui.tableView2DProfiles.selectionModel().selectionChanged.connect(self.onPlot3DSelectionChanged)
        self.ui.tableView3DProfiles.horizontalHeader().setResizeMode(QHeaderView.Interactive)
        self.plotSettingsModel3D.rowsInserted.connect(self.onRowsInserted3D)
        self.delegateTableView3D = PlotSettingsModel3DWidgetDelegate(self.ui.tableView3DProfiles, self.mTemporalProfileLayer)
        self.delegateTableView3D.setItemDelegates(self.ui.tableView3DProfiles)

        if not ENABLE_OPENGL:
            self.ui.listWidget.item(1).setHidden(True)
            self.ui.page3D.setHidden(True)



        def onTemporalProfilesRemoved(removedProfiles):
            #set to valid temporal profile

            affectedStyles2D = [p for p in self.plotSettingsModel2D if p.temporalProfile() in removedProfiles]
            affectedStyles3D = [p for p in self.plotSettingsModel3D if p.temporalProfile() in removedProfiles]
            alternativeProfile = self.mTemporalProfileLayer[-1] if len(self.mTemporalProfileLayer) > 0 else None
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

        self.mTemporalProfileLayer.sigTemporalProfilesRemoved.connect(onTemporalProfilesRemoved)

        # remove / add plot style
        def on2DPlotStyleRemoved(plotStyles):
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, PlotStyle)
                for pi in plotStyle.mPlotItems:
                    self.plot2D.plotItem.removeItem(pi)

        def on3DPlotStyleRemoved(plotStyles):
            toRemove = []
            for plotStyle in plotStyles:
                assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
                toRemove.append(plotStyle.mPlotItems)
            self.plot3D.removeItems(toRemove)


        self.plotSettingsModel2D.sigPlotStylesRemoved.connect(on2DPlotStyleRemoved)
        self.plotSettingsModel3D.sigPlotStylesRemoved.connect(on3DPlotStyleRemoved)

        #initialize the update loop
        self.updateRequested = True
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.onDataUpdate)
        self.updateTimer.start(2000)

        self.sigMoveToDate.connect(self.onMoveToDate)

        self.initActions()
        #self.ui.stackedWidget.setCurrentPage(self.ui.pagePixel)
        self.ui.onStackPageChanged(self.ui.stackedWidget.currentIndex())

    def temporalProfileLayer(self):
        """
        Returns a QgsVectorLayer that is used to store profile coordinates.
        :return:
        """
        return self.mTemporalProfileLayer

    def onTemporalProfilesContextMenu(self, event):
        assert isinstance(event, QContextMenuEvent)
        tableView = self.ui.tableViewTemporalProfiles
        selectionModel = self.ui.tableViewTemporalProfiles.selectionModel()
        assert isinstance(selectionModel, QItemSelectionModel)

        model = self.ui.tableViewTemporalProfiles.model()
        assert isinstance(model, TemporalProfileLayer)

        temporalProfiles = []

        if len(selectionModel.selectedIndexes()) > 0:
            for idx in selectionModel.selectedIndexes():
                tp = model.idx2tp(idx)
                if isinstance(tp, TemporalProfile) and not tp in temporalProfiles:
                    temporalProfiles.append(tp)
        else:
            temporalProfiles = model[:]

        spatialPoints = [tp.coordinate() for tp in temporalProfiles]


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


    def selected2DPlotStyles(self):
        result = []

        m = self.ui.tableView2DProfiles.model()
        for idx in selectedModelIndices(self.ui.tableView2DProfiles):
            result.append(m.idx2plotStyle(idx))
        return result



    def removePlotStyles2D(self, plotStyles):
        m = self.ui.tableView2DProfiles.model()
        if isinstance(m, PlotSettingsModel2D):
            m.removePlotStyles(plotStyles)

    def removeTemporalProfiles(self, fids):

        self.mTemporalProfileLayer.selectByIds(fids)
        b = self.mTemporalProfileLayer.isEditable()
        self.mTemporalProfileLayer.startEditing()
        self.mTemporalProfileLayer.deleteSelectedFeatures()
        self.mTemporalProfileLayer.saveEdits(leaveEditable=b)

    def createNewPlotStyle2D(self):
        l = len(self.mTemporalProfileLayer)


        plotStyle = TemporalProfile2DPlotStyle()
        plotStyle.sigExpressionUpdated.connect(self.updatePlot2D)

        sensors = list(self.TS.Sensors.keys())
        if len(sensors) > 0:
            plotStyle.setSensor(sensors[0])

        if len(self.mTemporalProfileLayer) > 0:
            temporalProfile = self.mTemporalProfileLayer[0]
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
        self.plot2D.plotItem.addItem(pdi)
        #self.plot2D.getPlotItem().addItem(pg.PlotDataItem(x=[1, 2, 3], y=[1, 2, 3]))
        #plotItem.addDataItem(pdi)
        #plotItem.plot().sigPlotChanged.emit(plotItem)
        self.updatePlot2D()
        return plotStyle


    def createNewPlotStyle3D(self):
        if not (ENABLE_OPENGL and OPENGL_AVAILABLE):
            return


        plotStyle = TemporalProfile3DPlotStyle()
        plotStyle.sigExpressionUpdated.connect(self.updatePlot3D)

        if len(self.mTemporalProfileLayer) > 0:
            temporalProfile = self.mTemporalProfileLayer[0]
            plotStyle.setTemporalProfile(temporalProfile)
            if len(self.plotSettingsModel3D) > 0:
                color = self.plotSettingsModel3D[-1].color()
                plotStyle.setColor(nextColor(color))

        sensors = list(self.TS.Sensors.keys())
        if len(sensors) > 0:
            plotStyle.setSensor(sensors[0])


        self.plotSettingsModel3D.insertPlotStyles([plotStyle], i=0) # latest to the top
        plotItems = plotStyle.createPlotItem()
        self.plot3D.addItems(plotItems)
        #self.updatePlot3D()

    def onProfileClicked2D(self, pdi):
        if isinstance(pdi, TemporalProfilePlotDataItem):
            sensor = pdi.mPlotStyle.sensor()
            tp = pdi.mPlotStyle.temporalProfile()
            if isinstance(tp, TemporalProfile) and isinstance(sensor, SensorInstrument):
                c = tp.coordinate()
                info = ['Sensor:{}'.format(sensor.name()),
                        'Coordinate:{}, {}'.format(c.x(), c.y())]
                self.ui.tbInfo2D.setPlainText('\n'.join(info))


    def onPointsClicked2D(self, pdi, spottedItems):
        if isinstance(pdi, TemporalProfilePlotDataItem) and isinstance(spottedItems, list):
            sensor = pdi.mPlotStyle.sensor()
            tp = pdi.mPlotStyle.temporalProfile()
            if isinstance(tp, TemporalProfile) and isinstance(sensor, SensorInstrument):
                c = tp.coordinate()
                info = ['Sensor: {}'.format(sensor.name()),
                        'Coordinate: {}, {}'.format(c.x(), c.y())]

                for item in spottedItems:
                    pos = item.pos()
                    x = pos.x()
                    y = pos.y()
                    date = num2date(x)
                    info.append('Date: {}\nValue: {}'.format(date, y))

                self.ui.tbInfo2D.setPlainText('\n'.join(info))

    def onTemporalProfilesAdded(self, profiles):
        #self.mTemporalProfileLayer.prune()
        for plotStyle in self.plotSettingsModel3D:
            assert isinstance(plotStyle, TemporalProfilePlotStyleBase)
            if not isinstance(plotStyle.temporalProfile(), TemporalProfile):
                r = self.plotSettingsModel3D.plotStyle2idx(plotStyle).row()
                c = self.plotSettingsModel3D.columnIndex(self.plotSettingsModel3D.cnTemporalProfile)
                idx = self.plotSettingsModel3D.createIndex(r,c)
                self.plotSettingsModel3D.setData(idx, self.mTemporalProfileLayer[0])

    def onTemporalProfileSelectionChanged(self, selectedFIDs, deselectedFIDs):
        nSelected = len(selectedFIDs)

        self.ui.actionRemoveTemporalProfile.setEnabled(nSelected > 0)


    def onPlot2DSelectionChanged(self, selected, deselected):

        self.ui.actionRemoveStyle2D.setEnabled(len(selected) > 0)

    def onPlot3DSelectionChanged(self, selected, deselected):

        self.ui.actionRemoveStyle3D.setEnabled(len(selected) > 0)

    def initActions(self):

        self.ui.actionRemoveStyle2D.setEnabled(False)
        self.ui.actionRemoveTemporalProfile.setEnabled(False)
        self.ui.actionAddStyle2D.triggered.connect(self.createNewPlotStyle2D)
        self.ui.actionAddStyle3D.triggered.connect(self.createNewPlotStyle3D)
        self.ui.actionRefresh2D.triggered.connect(self.updatePlot2D)
        self.ui.actionRefresh3D.triggered.connect(self.updatePlot3D)
        self.ui.actionRemoveStyle2D.triggered.connect(lambda:self.removePlotStyles2D(self.selected2DPlotStyles()))
        self.ui.actionRemoveTemporalProfile.triggered.connect(lambda :self.removeTemporalProfiles(self.mTemporalProfileLayer.selectedFeatureIds()))
        self.ui.actionToggleEditing.triggered.connect(self.onToggleEditing)
        self.ui.actionReset2DPlot.triggered.connect(self.plot2D.resetViewBox)
        self.plot2D.resetTransform()
        self.ui.actionReset3DCamera.triggered.connect(self.reset3DCamera)
        self.ui.actionLoadTPFromOgr.triggered.connect(lambda : self.mTemporalProfileLayer.loadCoordinatesFromOgr(None))
        self.ui.actionLoadMissingValues.triggered.connect(lambda: self.loadMissingData())
        self.ui.actionSaveTemporalProfiles.triggered.connect(self.mTemporalProfileLayer.saveTemporalProfiles)
        #set actions to be shown in the TemporalProfileTableView context menu
        ma = [self.ui.actionSaveTemporalProfiles, self.ui.actionLoadMissingValues]
        self.ui.tableViewTemporalProfiles.setContextMenuActions(ma)

        self.onEditingToggled()

    def onSaveTemporalProfiles(self):

        s = ""

    def onToggleEditing(self, b):

        if self.mTemporalProfileLayer.isEditable():
            self.mTemporalProfileLayer.saveEdits(leaveEditable=False)
        else:
            self.mTemporalProfileLayer.startEditing()
        self.onEditingToggled()

    def onEditingToggled(self):
        lyr = self.mTemporalProfileLayer

        hasSelectedFeatures = lyr.selectedFeatureCount() > 0
        isEditable = lyr.isEditable()
        self.ui.actionToggleEditing.blockSignals(True)
        self.ui.actionToggleEditing.setChecked(isEditable)
        #self.actionSaveTemporalProfiles.setEnabled(isEditable)
        #self.actionReload.setEnabled(not isEditable)
        self.ui.actionToggleEditing.blockSignals(False)

        #self.actionAddAttribute.setEnabled(isEditable)
        #self.actionRemoveAttribute.setEnabled(isEditable)
        self.ui.actionRemoveTemporalProfile.setEnabled(isEditable and hasSelectedFeatures)
        #self.actionPasteFeatures.setEnabled(isEditable)
        self.ui.actionToggleEditing.setEnabled(not lyr.readOnly())




    def reset3DCamera(self, *args):

        if ENABLE_OPENGL and OPENGL_AVAILABLE:
            self.ui.actionReset3DCamera.trigger()



    sigMoveToTSD = pyqtSignal(TimeSeriesDatum)

    def onMoveToDate(self, date):
        dt = np.asarray([np.abs(tsd.date - date) for tsd in self.TS])
        i = np.argmin(dt)
        self.sigMoveToTSD.emit(self.TS[i])


    def onPixelLoaded(self, d):

        if isinstance(d, PixelLoaderTask):

            bn = os.path.basename(d.sourcePath)
            if d.success():

                t = 'Loaded {} pixel from {}.'.format(len(d.resProfiles), bn)
                self.mTemporalProfileLayer.addPixelLoaderResult(d)
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


    def loadMissingData(self, backgroundProcess=False):
        """
        Loads all band values of collected locations that have not been loaded until now
        """

        fids = self.mTemporalProfileLayer.selectedFeatureIds()
        if len(fids) == 0:
            fids = [f.id() for f in self.mTemporalProfileLayer.getFeatures()]

        tps = [self.mTemporalProfileLayer.mProfiles.get(fid) for fid in fids]
        spatialPoints = [tp.coordinate() for tp in tps if isinstance(tp, TemporalProfile)]
        self.loadCoordinate(spatialPoints=spatialPoints, mode='all', backgroundProcess=backgroundProcess)

    LOADING_MODES = ['missing','reload','all']
    def loadCoordinate(self, spatialPoints=None, LUT_bandIndices=None, mode='missing', backgroundProcess = True):
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
            TP = self.mTemporalProfileLayer.fromSpatialPoint(spatialPoint)
            #if not TP exists for this point, create an empty one
            if not isinstance(TP, TemporalProfile):
                TP = self.mTemporalProfileLayer.createTemporalProfiles(spatialPoint)[0]

                if len(self.mTemporalProfileLayer) == 1:
                    if len(self.plotSettingsModel2D) == 0:
                        self.createNewPlotStyle2D()

                    if len(self.plotSettingsModel3D) == 0:
                        self.createNewPlotStyle3D()

            TPs.append(TP)
            theGeometries.append(TP.coordinate())


        TP_ids = [TP.id() for TP in TPs]
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
            if backgroundProcess:
                self.pixelLoader.startLoading(tasks)
            else:
                import timeseriesviewer.pixelloader
                tasks = [PixelLoaderTask.fromDump(timeseriesviewer.pixelloader.doLoaderTask(None, task.toDump())) for task in tasks]
                l = len(tasks)
                for i, task in enumerate(tasks):
                    self.pixelLoader.sigPixelLoaded.emit(task)

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

        #self.mTemporalProfileLayer.prune()

        for plotSetting in self.plotSettingsModel2D:
            assert isinstance(plotSetting, TemporalProfile2DPlotStyle)
            tp = plotSetting.temporalProfile()
            for pdi in plotSetting.mPlotItems:
                assert isinstance(pdi, TemporalProfilePlotDataItem)
                pdi.updateDataAndStyle()
            if isinstance(tp, TemporalProfile) and plotSetting.temporalProfile().updated():
                plotSetting.temporalProfile().resetUpdatedFlag()


        for i in self.plot2D.plotItem.dataItems:
            i.updateItems()


        notInit = [0, 1] == self.plot2D.plotItem.getAxis('bottom').range
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
                self.plot2D.plotItem.setXRange(x0, x1)
                #self.plot2D.xAxisInitialized = True

    @QtCore.pyqtSlot()
    def updatePlot3D(self):
        if ENABLE_OPENGL and OPENGL_AVAILABLE:
            from pyqtgraph.opengl import GLViewWidget
            from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem
            import pyqtgraph.opengl as gl
            from timeseriesviewer.temporalprofiles3dGL import ViewWidget3D
            assert isinstance(self.plot3D, ViewWidget3D)

            # 1. ensure that data from all bands will be loaded
            #    new loaded values will be shown in the next updatePlot3D call
            coordinates = []
            allPlotItems = []
            for plotStyle3D in self.plotSettingsModel3D:
                assert isinstance(plotStyle3D, TemporalProfile3DPlotStyle)
                if plotStyle3D.isPlotable():
                    coordinates.append(plotStyle3D.temporalProfile().coordinate())

            if len(coordinates) > 0:
                self.loadCoordinate(coordinates, mode='all')

            toRemove = [item for item in self.plot3D.items if item not in allPlotItems]
            self.plot3D.removeItems(toRemove)
            toAdd = [item for item in allPlotItems if item not in self.plot3D.items]
            self.plot3D.addItems(toAdd)


            """
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
            """

    @QtCore.pyqtSlot()
    def updatePlot2D(self):
        if isinstance(self.plotSettingsModel2D, PlotSettingsModel2D):

            locations = set()
            for plotStyle in self.plotSettingsModel2D:
                assert isinstance(plotStyle, TemporalProfile2DPlotStyle)
                if plotStyle.isPlotable():
                    locations.add(plotStyle.temporalProfile().coordinate())

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


    if False:
        files = ['observationcloud/testdata/2014-07-26_LC82270652014207LGN00_BOA.bsq',
                 'observationcloud/testdata/2014-08-03_LE72270652014215CUB00_BOA.bsq'
                 ]
    else:
        from timeseriesviewer.utils import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = list(file_search(searchDir, '*227065*band4.img', recursive=True))
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
