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

from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.timeseries import *
from timeseriesviewer.utils import SpatialExtent, SpatialPoint, px2geo
from timeseriesviewer.ui.docks import TsvDockWidgetBase, loadUi
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleButton
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderResult
import pyqtgraph as pg
from osgeo import gdal, gdal_array
import numpy as np

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



class SensorPoints(pg.PlotDataItem):
    def __init__(self, *args, **kwds):
        super(SensorPoints, self).__init__(*args, **kwds)
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


class PlotSettingsWidgetDelegate(QStyledItemDelegate):

    def __init__(self, tableView, parent=None):

        super(PlotSettingsWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.tableView = tableView

    def getColumnName(self, index):
        assert index.isValid()
        assert isinstance(index.model(), PlotSettingsModel)
        return index.model().columnames[index.column()]
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
        if cname == 'y-value':
            w = QgsFieldExpressionWidget(parent)
            sv = self.tableView.model().data(index, Qt.UserRole)
            w.setLayer(sv.memLyr)
            w.setExpressionDialogTitle('Values sensor {}'.format(sv.sensor().name()))
            w.setToolTip('Set values shown for sensor {}'.format(sv.sensor().name()))
            w.fieldChanged.connect(lambda : self.checkData(w, w.expression()))

        elif cname == 'style':
            sv = self.tableView.model().data(index, Qt.UserRole)


            w = PlotStyleButton(parent)
            w.setPlotStyle(sv)
            w.setToolTip('Set sensor style.')
            w.sigPlotStyleChanged.connect(lambda: self.checkData(w, w.plotStyle()))
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
        if cname == 'y-value':
            lastExpr = index.model().data(index, Qt.DisplayRole)
            assert isinstance(editor, QgsFieldExpressionWidget)
            editor.setProperty('lastexpr', lastExpr)
            editor.setField(lastExpr)

        elif cname == 'style':
            style = index.data()
            assert isinstance(editor, PlotStyleButton)
            editor.setPlotStyle(style)
        else:
            raise NotImplementedError()

    def setModelData(self, w, model, index):
        cname = self.getColumnName(index)
        if cname == 'y-value':
            assert isinstance(w, QgsFieldExpressionWidget)
            expr = w.asExpression()
            exprLast = model.data(index, Qt.DisplayRole)

            if w.isValidExpression() and expr != exprLast:
                model.setData(index, w.asExpression(), Qt.UserRole)
        elif cname == 'style':
            assert isinstance(w, PlotStyleButton)
            model.setData(index, w.plotStyle(), Qt.UserRole)

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



class PixelCollection(QObject):
    """
    Object to store pixel data delivered by PixelLoader
    """

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigPixelAdded = pyqtSignal()
    sigPixelRemoved = pyqtSignal()



    def __init__(self, ):
        super(PixelCollection, self).__init__()


        self.sensorPxLayers = dict()
        self.memLyrCrs = QgsCoordinateReferenceSystem('EPSG:4326')

    def connectTimeSeries(self, timeSeries):
        self.clear()

        if isinstance(timeSeries, TimeSeries):
            self.TS = timeSeries
            for sensor in self.TS.Sensors:
                self.addSensor(sensor)
            self.TS.sigSensorAdded.connect(self.addSensor)
            self.TS.sigSensorRemoved.connect(self.removeSensor)

        else:
            self.TS = None


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

    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        assert sensor not in self.sensorPxLayers.keys()

        mem = SensorPixelDataMemoryLayer(sensor, crs=self.memLyrCrs)
        self.sensorPxLayers[sensor] = mem
        self.sigSensorAdded.emit(sensor)

    def sensorData(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        assert sensor in self.sensorPxLayers.keys()
        return self.sensorPxLayers[sensor]

    def removeSensor(self, sensor):
        if sensor in self.sensorPxLayers.keys():
            del self.sensorPxLayers[sensor]

    def addPixel(self, d):
        assert isinstance(d, PixelLoaderResult)
        if d.success():
            tsd = self.TS.getTSD(d.source)
            values = d.pxData
            nodata = np.asarray(d.noDataValue)

            nb, nl, ns = values.shape
            assert nb >= 1

            assert isinstance(tsd, TimeSeriesDatum)

            mem = self.sensorData(tsd.sensor)

            #insert each single pixel, line by line
            indicesY, indicesX = d.imagePixelIndices()

            doy = tsd.doy
            gt = d.geoTransformation
            nb, nl, ns = d.pxData.shape
            srcCrs = d.imageCrs()
            for i in range(ns):
                for j in range(nl):
                    profile = d.pxData[:, j, i]
                    if np.any(np.any(profile == nodata)):
                        continue
                    geo = px2geo(QPoint(indicesX[i], indicesY[i]), gt)
                    geo = SpatialPoint(srcCrs, geo).toCrs(self.memLyrCrs)
                    if not isinstance(geo, SpatialPoint):
                        continue

                    geometry = QgsPointV2(geo.x(), geo.y())
                    feature = QgsFeature(mem.fields())

                    #fnames = [f.name() for f in mem.fields()]

                    feature.setGeometry(QgsGeometry(geometry))
                    feature.setAttribute('date', str(tsd.date))
                    feature.setAttribute('doy', doy)
                    feature.setAttribute('geo_x', geo.x())
                    feature.setAttribute('geo_y', geo.y())
                    feature.setAttribute('px_x', indicesX[i])
                    feature.setAttribute('px_y', indicesY[i])
                    for iBand, bandIndex in enumerate(d.pxBandIndices):
                        name ='b{}'.format(bandIndex+1)
                        if profile.ndim == 1:
                            self.setFeatureAttribute(feature, name, profile[iBand])
                        else:
                            self.setFeatureAttribute(feature, name, profile[iBand,:])
                    mem.startEditing()
                    assert mem.addFeature(feature)
                    assert mem.commitChanges()

            #each pixel is a new feature
            self.sigPixelAdded.emit()

        pass


    def clear(self):
        self.sensorPxLayers.clear()

    def clearPixels(self):
        sensors = self.sensorPxLayers.keys()
        n_deleted = 0
        for sensor in sensors:
            mem = self.sensorPxLayers[sensor]
            assert mem.startEditing()
            mem.selectAll()
            b, n = mem.deleteSelectedFeatures()
            n_deleted += n
            assert mem.commitChanges()

            #self.sigSensorRemoved.emit(sensor)

        if n_deleted > 0:
            self.sigPixelRemoved.emit()

    def dateValues(self, sensor, expression):
        mem = self.sensorData(sensor)
        dp = mem.dataProvider()
        exp = QgsExpression(expression)
        exp.prepare(dp.fields())

        possibleTsds = self.TS.getTSDs(sensorOfInterest=sensor)


        tsds = []
        values =  []

        if exp.isValid():
            mem.selectAll()
            for feature in mem.selectedFeatures():
                date = np.datetime64(feature.attribute('date'))
                y = exp.evaluatePrepared(feature)
                if y is not None:
                    tsd = next(tsd for tsd in possibleTsds if tsd.date == date)
                    tsds.append(tsd)
                    values.append(y)


        return tsds, values


class SensorPlotStyle(PlotStyle):

    def __init__(self):
        super(SensorPlotStyle, self).__init__()

        self.mSensor = None
        self.memLyr = None
        self.mExpression = u'"b1"'
        self.mIsVisible = True


    def connectSensor(self, sensor, memoryLayer):
        assert isinstance(sensor, SensorInstrument)
        assert isinstance(memoryLayer, QgsVectorLayer)

        self.memLyr = memoryLayer
        self.mSensor = sensor

    def isValid(self):
        """
        :return: True, if connected to a sensor and memoryLayer that contains pixel values
        """
        return isinstance(self.memLyr, QgsVectorLayer) and isinstance(self.mSensor, SensorInstrument)

    def sensor(self):
        return self.mSensor

    def setVisibility(self, b):
        self.mIsVisible
    def isVisible(self):
        return self.mIsVisible

    def setExpression(self, exp):
        self.mExpression = exp

    def expression(self):
        return self.mExpression

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = super(SensorPlotStyle, self).__getstate__()
        #remove
        del result['memLyr']
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
        self.plotItem = pg.PlotItem(axisItems={'bottom':DateTimeAxis(orientation='bottom')}, viewBox=DateTimeViewBox())
        self.setCentralItem(self.plotItem)


class PlotSettingsModel(QAbstractTableModel):

    #sigSensorAdded = pyqtSignal(SensorPlotSettings)
    sigVisibilityChanged = pyqtSignal(SensorPlotStyle)
    sigDataChanged = pyqtSignal(SensorPlotStyle)

    columnames = ['sensor','nb','style','y-value']
    def __init__(self, pixelCollection, parent=None, *args):

        #assert isinstance(tableView, QTableView)

        super(PlotSettingsModel, self).__init__(parent=parent)
        assert isinstance(pixelCollection, PixelCollection)

        self.mSensorPlotSettings = []

        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        self.pxCollection = pixelCollection

        self.pxCollection.sigSensorAdded.connect(self.addSensor)
        self.pxCollection.sigSensorRemoved.connect(self.removeSensor)

        for sensor in self.pxCollection.sensorPxLayers.keys():
            self.addSensor(sensor)

        self.sort(0, Qt.AscendingOrder)
        s = ""
        self.dataChanged.connect(self.signaler)

    def testSlot(self, *args):
        print('TESTSLOT')
        s = ""


    def signaler(self, idxUL, idxLR):
        if idxUL.isValid():
            sensorView = self.getSensorPlotSettingsFromIndex(idxUL)
            cname = self.columnames[idxUL.column()]
            if cname in ['sensor','style']:
                self.sigVisibilityChanged.emit(sensorView)
            if cname in ['y-value']:
                self.sigDataChanged.emit(sensorView)

    def requiredBands(self, sensor):
        """
        Returns the band indices required to calculate the values for this sensor
        :param sensor:
        :return: [list-of-band-indices]
        """
        idx = self.getIndexFromSensor(sensor)
        idx = self.createIndex(idx.row(),self.columnames.index('y-value'))

        equation = self.data(idx)
        plotSettings = self.data(idx, Qt.UserRole)
        assert isinstance(plotSettings, SensorPlotStyle)
        expression = plotSettings.expression()

        fields = plotSettings.memLyr.fields()

        bandNames = []
        bandIndices = []
        LUT_Field2Band = dict()
        for field in fields:
            assert isinstance(field, QgsField)
            LUT_Field2Band[field.name()] = field.name()
            if len(field.alias()) > 0:
                LUT_Field2Band[field.alias()] = field.name()


        for name, fieldName in LUT_Field2Band.items():
            if re.search(name+'($|[^\d])', expression):
                bandNames.append(fieldName)
                continue

        for bandName in bandNames:
            if re.search('b\d+', bandName):
                bandIndices.append(int(bandName[1:])-1)
        return bandIndices






    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        index = 'DEFAULT'

        sensorSettings = self.restorePlotSettings(sensor, index=index)
        if not isinstance(sensorSettings, SensorPlotStyle):
            sensorSettings = SensorPlotStyle()
        sensorSettings.connectSensor(sensor, self.pxCollection.sensorPxLayers[sensor])


        i = len(self.mSensorPlotSettings)

        self.beginInsertRows(QModelIndex(),i,i)
        self.mSensorPlotSettings.append(sensorSettings)
        self.endInsertRows()
        sensor.sigNameChanged.connect(self.onSensorNameChanged)

    def removeSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        toRemove = [s for s in self.mSensorPlotSettings if s.sensor() == sensor]
        for s in toRemove:

            idx = self.getIndexFromSensor(s.sensor())
            self.beginRemoveRows(QModelIndex(), idx.row(),idx.row())
            self.mSensorPlotSettings.remove(s)
            self.endRemoveRows()

    def onSensorNameChanged(self, name):
        self.beginResetModel()

        self.endResetModel()

    def sort(self, col, order):
        if self.rowCount() == 0:
            return


        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        #self.beginMoveRows(idxSrc,

        if colName == 'sensor':
            self.mSensorPlotSettings.sort(key = lambda sv:sv.sensor.name(), reverse=r)
        elif colName == 'nb':
            self.mSensorPlotSettings.sort(key=lambda sv: sv.sensor.nb, reverse=r)
        elif colName == 'y-value':
            self.mSensorPlotSettings.sort(key=lambda sv: sv.expression, reverse=r)
        elif colName == 'style':
            self.mSensorPlotSettings.sort(key=lambda sv: sv.color, reverse=r)





    def rowCount(self, parent = QModelIndex()):
        return len(self.mSensorPlotSettings)


    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self.mSensorPlotSettings[row:row + count]
        for tsd in toRemove:
            self.mSensorPlotSettings.remove(tsd)
        self.endRemoveRows()



    def getIndexFromSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        sensorViews = [i for i, s in enumerate(self.mSensorPlotSettings) if s.sensor() == sensor]
        assert len(sensorViews) == 1
        return self.createIndex(sensorViews[0],0)

    def getSensorPlotSettingsFromIndex(self, index):
        if index.isValid():
            return self.mSensorPlotSettings[index.row()]
        return None

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnames[index.column()]
        sw = self.getSensorPlotSettingsFromIndex(index)
        sensor = sw.sensor()
        #print(('data', columnName, role))
        if role == Qt.DisplayRole:
            if columnName == 'sensor':
                value = sensor.name()
            elif columnName == 'nb':
                value = str(sensor.nb)
            elif columnName == 'y-value':
                value = sw.expression()
        elif role == Qt.CheckStateRole:
            if columnName == 'sensor':
                value = Qt.Checked if sw.isVisible() else Qt.Unchecked
        elif role == Qt.UserRole:
            value = sw
        #print(('get data',value))
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return False
        #print(('Set data', index.row(), index.column(), value, role))
        columnName = self.columnames[index.column()]

        if value is None:
            return False
        result = False
        sw = self.getSensorPlotSettingsFromIndex(index)
        assert isinstance(sw, SensorPlotStyle)
        if role in [Qt.DisplayRole, Qt.EditRole]:
            if columnName == 'y-value':
                sw.setExpression(value)
                result = True
            elif columnName == 'style':
                if isinstance(value, PlotStyle):
                    sw.plotStyle.copyFrom(value)

                    result = True

        if role == Qt.CheckStateRole:
            if columnName == 'sensor':
                sw.setVisibility(value == Qt.Checked)
                result = True

        if role == Qt.UserRole:
            if columnName == 'y-value':
                sw.setExpression(value)
                result = True
            elif columnName == 'style':
                sw.copyFrom(value)
                result = True

        if result:
            #save plot-style
            self.savePlotSettings(sw, index='DEFAULT')
            self.dataChanged.emit(index, index)

        return result

    def savePlotSettings(self, sensorPlotSettings, index='DEFAULT'):
        assert isinstance(sensorPlotSettings, SensorPlotStyle)
        id = 'SPS.{}.{}'.format(index, sensorPlotSettings.sensor().id())
        d = pickle.dumps(sensorPlotSettings)
        SETTINGS.setValue(id, d)

    def restorePlotSettings(self, sensor, index='DEFAULT'):
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

        if isinstance(sensorPlotSettings, SensorPlotStyle):
            return sensorPlotSettings
        else:
            return None


    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName == 'sensor':
                flags = flags | Qt.ItemIsUserCheckable

            if columnName in ['y-value','style']: #allow check state
                flags = flags | Qt.ItemIsEditable
            return flags
            #return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None



class ProfileViewDockUI(TsvDockWidgetBase, loadUi('profileviewdock.ui')):


    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)
        from timeseriesviewer import OPENGL_AVAILABLE, SETTINGS

        #TBD.
        self.line.setVisible(False)
        self.listWidget.setVisible(False)
        self.stackedWidget.setCurrentWidget(self.page2D)

        if OPENGL_AVAILABLE:
            l = self.page3D.layout()
            l.removeWidget(self.labelDummy3D)
            from pyqtgraph.opengl import GLViewWidget
            self.plotWidget3D = GLViewWidget(self.page3D)
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

        self.tableView2DBands.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableView2DBands.setSortingEnabled(True)
        self.btnRefresh2D.setDefaultAction(self.actionRefresh2D)





def date2num(d):
    d2 = d.astype(datetime.datetime)
    o = d2.toordinal()

    #assert d == num2date(o)

    return o

def num2date(n):
    n = int(np.round(n))
    if n < 1:
        n = 1
    d = datetime.date.fromordinal(n)
    return np.datetime64(d, 'D')

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

        self.pixelLoader = PixelLoader()
        self.pixelLoader.sigPixelLoaded.connect(self.onPixelLoaded)
        self.pixelLoader.sigLoadingStarted.connect(lambda: self.ui.progressInfo.setText('Start loading...'))


        self.plot_initialized = False
        self.TV = ui.tableView2DBands
        self.TV.setSortingEnabled(False)
        self.plot2D = ui.plotWidget2D
        self.plot2D.plotItem.getViewBox().sigMoveToDate.connect(self.sigMoveToDate)

        self.plot3D = ui.plotWidget3D
        self.pxCollection = PixelCollection()
        self.pxCollection.sigPixelAdded.connect(self.requestUpdate)
        self.pxCollection.sigPixelRemoved.connect(self.clear)

        self.plotSettingsModel = None

        self.pixelLoader.sigLoadingStarted.connect(self.clear)
        self.pixelLoader.sigLoadingFinished.connect(lambda : self.plot2D.enableAutoRange('x', False))
        self.ui.actionRefresh2D.triggered.connect(lambda: self.setData())

        # self.VIEW.setItemDelegateForColumn(3, PointStyleDelegate(self.VIEW))
        self.plotData2D = dict()
        self.plotData3D = dict()

        self.updateRequested = True
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updatePlot)
        self.updateTimer.start(2000)

        self.sigMoveToDate.connect(self.onMoveToDate)

    def connectTimeSeries(self, TS):

        assert isinstance(TS, TimeSeries)
        self.TS = TS

        self.pxCollection.connectTimeSeries(self.TS)

        self.TS.sigSensorRemoved.connect(self.removeSensor)

        self.plotSettingsModel = PlotSettingsModel(self.pxCollection, parent=self)
        self.plotSettingsModel.sigVisibilityChanged.connect(self.setVisibility)
        self.plotSettingsModel.sigDataChanged.connect(self.requestUpdate)
        self.plotSettingsModel.rowsInserted.connect(self.onRowsInserted)
        # self.plotSettingsModel.modelReset.connect(self.updatePersistantWidgets)
        self.TV.setModel(self.plotSettingsModel)
        self.delegate = PlotSettingsWidgetDelegate(self.TV)
        self.TV.setItemDelegateForColumn(2, self.delegate)
        self.TV.setItemDelegateForColumn(3, self.delegate)
        # self.TV.setItemDelegateForColumn(3, PointStyleDelegate(self.TV))


    sigMoveToTSD = pyqtSignal(TimeSeriesDatum)

    def onMoveToDate(self, date):
        dt = np.asarray([np.abs(tsd.date - date) for tsd in self.TS])
        i = np.argmin(dt)
        self.sigMoveToTSD.emit(self.TS[i])


    def onPixelLoaded(self, nDone, nMax, d):
        self.ui.progressBar.setValue(nDone)
        self.ui.progressBar.setMaximum(nMax)

        assert isinstance(d, PixelLoaderResult)


        QgsApplication.processEvents()
        bn = os.path.basename(d.source)
        if d.success():

            t = 'Last loaded from {}.'.format(bn)
            self.pxCollection.addPixel(d)
        else:
            t = 'Failed loading from {}.'.format(bn)
            if d.info and d.info != '':
                t += '({})'.format(d.info)
        self.ui.progressInfo.setText(t)

    def requestUpdate(self, *args):
        self.updateRequested = True
        #next time

    def updatePersistentWidgets(self):
        model = self.TV.model()
        if model:
            colExpression = model.columnames.index('y-value')
            colStyle = model.columnames.index('style')
            for row in range(model.rowCount()):
                idxExpr = model.createIndex(row, colExpression)
                idxStyle = model.createIndex(row, colStyle)
                #self.TV.closePersistentEditor(idxExpr)
                #self.TV.closePersistentEditor(idxStyle)
                self.TV.openPersistentEditor(idxExpr)
                self.TV.openPersistentEditor(idxStyle)

                #self.TV.openPersistentEditor(model.createIndex(start, colStyle))
            s = ""


    def onRowsInserted(self, parent, start, end):
        model = self.TV.model()
        if model:
            colExpression = model.columnames.index('y-value')
            colStyle = model.columnames.index('style')
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

            print(tsd)
        s =""

    def clear(self):
        #first remove from pixelCollection
        self.pxCollection.clearPixels()
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
        QApplication.processEvents()
        if self.plot3D:
            pass


    def loadCoordinate(self, spatialPoint):
        if not isinstance(self.plotSettingsModel, PlotSettingsModel):
            return False

        if not self.pixelLoader.isReadyToLoad():
            return False

        assert isinstance(spatialPoint, SpatialPoint)
        assert isinstance(self.TS, TimeSeries)

        LUT_bandIndices = dict()
        for sensor in self.TS.Sensors:
            LUT_bandIndices[sensor] = self.plotSettingsModel.requiredBands(sensor)

        paths = []
        bandIndices = []
        for tsd in self.TS:
            if tsd.isVisible():
                paths.append(tsd.pathImg)
                bandIndices.append(LUT_bandIndices[tsd.sensor])

        aGoodDefault = 2 if len(self.TS) > 25 else 1
        self.pixelLoader.setNumberOfProcesses(SETTINGS.value('profileloader_threads', aGoodDefault))
        self.pixelLoader.startLoading(paths, spatialPoint, bandIndices=bandIndices)

        self.ui.setWindowTitle('{} | {} {}'.format(self.ui.baseTitle, str(spatialPoint.toString()), spatialPoint.crs().authid()))


    def setVisibility(self, sensorPlotStyle):
        assert isinstance(sensorPlotStyle, SensorPlotStyle)
        self.setVisibility2D(sensorPlotStyle)

    def setVisibility2D(self, sensorPlotStyle):
        assert isinstance(sensorPlotStyle, SensorPlotStyle)
        p = self.plotData2D[sensorPlotStyle.sensor()]

        p.setSymbol(sensorPlotStyle.markerSymbol)
        p.setSymbolSize(sensorPlotStyle.markerSize)
        p.setSymbolBrush(sensorPlotStyle.markerBrush)
        p.setSymbolPen(sensorPlotStyle.markerPen)

        p.setPen(sensorPlotStyle.linePen)

        p.setVisible(sensorPlotStyle.isVisible())
        p.update()
        self.plot2D.update()


    def addData(self, sensorView = None):

        if sensorView is None:
            for sv in self.plotSettingsModel.items:
                self.setData(sv)
        else:
            assert isinstance(sensorView, SensorPlotStyle)
            self.setData2D(sensorView)

    @QtCore.pyqtSlot()
    def updatePlot(self):
        if isinstance(self.plotSettingsModel, PlotSettingsModel) and self.updateRequested:
            self.setData()
            self.updateRequested = False

    def setData(self, sensorView = None):
        self.updateLock = True
        if sensorView is None:
            for sv in self.plotSettingsModel.mSensorPlotSettings:
                self.setData(sv)
        else:
            assert isinstance(sensorView, SensorPlotStyle)
            self.setData2D(sensorView)

        self.updateLock = False

    def removeSensor(self, sensor):
        s = ""
        self.plotSettingsModel.removeSensor(sensor)

        if sensor in self.plotData2D.keys():
            #remove from settings model
            self.plotSettingsModel.removeSensor(sensor)
            self.plotData2D.pop(sensor)
            self.pxCollection.removeSensor(sensor)
            # remove from px layer dictionary
            #self.sensorPxLayers.pop(sensor)
            #todo: remove from plot
            s = ""

    def setData2D(self, sensorView):
        assert isinstance(sensorView, SensorPlotStyle)

        if sensorView.sensor() not in self.plotData2D.keys():

            plotDataItem = self.plot2D.plot(name=sensorView.sensor().name(), pen=None, symbol='o', symbolPen=None)
            plotDataItem.sigPointsClicked.connect(self.onObservationClicked)

            self.plotData2D[sensorView.sensor()] = plotDataItem
            self.setVisibility2D(sensorView)

        plotDataItem = self.plotData2D[sensorView.sensor()]
        plotDataItem.setToolTip('Values {}'.format(sensorView.sensor().name()))


        #https://github.com/pyqtgraph/pyqtgraph/blob/5195d9dd6308caee87e043e859e7e553b9887453/examples/customPlot.py

        tsds, values = self.pxCollection.dateValues(sensorView.sensor(), sensorView.expression())
        if len(tsds) > 0:
            dates = np.asarray([date2num(tsd.date) for tsd in tsds])
            tsds = np.asarray(tsds)
            values = np.asarray(values)
            i = np.argsort(dates)
            plotDataItem.appendData()
            plotDataItem.setData(x=dates[i], y=values[i], data=tsds[i])

            self.setVisibility2D(sensorView)
            s = ""



    def setData3D(self, *arg):
        pass




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
    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    d1 = np.datetime64('2012-05-23')
    d2 = np.datetime64('2012-05-24')
    n1 = date2num(d1)
    n2 = date2num(d2)
    assert d1 == num2date(n1)
    assert d2 == num2date(n2)
    delta = n2-n1

    ui = ProfileViewDockUI()
    ui.show()

    if True:
        TS = TimeSeries()
        SViz = SpectralTemporalVisualization(ui)
        SViz.connectTimeSeries(TS)

        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
        TS.addFiles([Img_2014_01_15_LC82270652014015LGN00_BOA])
        ext = TS.getMaxSpatialExtent()
        cp = SpatialPoint(ext.crs(),ext.center())
        SViz.loadCoordinate(cp)

    qgsApp.exec_()
    qgsApp.exitQgis()

