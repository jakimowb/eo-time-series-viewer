# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 27.03.2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
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
import sys, os, re, collections, copy
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from eotimeseriesviewer.externals.qps.models import Option, OptionListModel


from eotimeseriesviewer.temporalprofiles import *

LABEL_EXPRESSION_3D = 'Scaling'


class TemporalProfile3DPlotStyleButton(QPushButton):

    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, *args, **kwds):
        super(TemporalProfile3DPlotStyleButton, self).__init__(*args, **kwds)
        self.mPlotStyle = TemporalProfile3DPlotStyle()
        self.mInitialButtonSize = None
        self.setStyleSheet('* { padding: 0px; }')
        self.clicked.connect(self.showDialog)
        self.setPlotStyle(PlotStyle())


    def plotStyle(self):
        return self.mPlotStyle

    def setPlotStyle(self, plotStyle):
        if isinstance(plotStyle, TemporalProfile3DPlotStyle):
            self.mPlotStyle.copyFrom(plotStyle)
            self._updateIcon()
            self.sigPlotStyleChanged.emit(self.mPlotStyle)
        else:
            s = ""


    def showDialog(self):
        #print(('A',self.mPlotStyle))
        style = TemporalProfile3DPlotStyleDialog.getPlotStyle(plotStyle=self.mPlotStyle)

        if style:
            self.setPlotStyle(style)
            s = ""
        #print(('B',self.mPlotStyle))
    def resizeEvent(self, arg):
        self._updateIcon()

    def _updateIcon(self):
        if self.mInitialButtonSize is None:
            self.mInitialButtonSize = self.sizeHint()
            self.setIconSize(self.mInitialButtonSize)

        if self.mPlotStyle != None:
            s = self.mInitialButtonSize
            s = self.sizeHint()
            #s = QSize()
            icon = self.mPlotStyle.createIcon(self.mInitialButtonSize)
            self.setIcon(icon)
        self.update()




        pass


class TemporalProfile3DPlotStyleDialog(QgsDialog):

    @staticmethod
    def getPlotStyle(*args, **kwds):
        """
        Opens a CrosshairDialog.
        :param args:
        :param kwds:
        :return: specified CrosshairStyle if accepted, else None
        """
        d = TemporalProfile3DPlotStyleDialog(*args, **kwds)
        d.exec_()

        if d.result() == QDialog.Accepted:
            return d.plotStyle()
        else:

            return None

    def __init__(self, parent=None, plotStyle=None, title='Specify 3D Plot Style'):
        super(QgsDialog, self).__init__(parent=parent , buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = TemporalProfilePlotStyle3DWidget(parent=self)
        self.setWindowTitle(title)
        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cancel')
        buttonBar = QHBoxLayout()
        #buttonBar.addWidget(self.btCancel)
        #buttonBar.addWidget(self.btOk)
        l = self.layout()
        l.addWidget(self.w)
        l.addLayout(buttonBar)
        if isinstance(plotStyle, PlotStyle):
            self.setPlotStyle(plotStyle)
        #self.setLayout(l)


    def plotStyle(self):
        return self.w.plotStyle()

    def setPlotStyle(self, plotStyle):
        assert isinstance(plotStyle, PlotStyle)
        self.w.setPlotStyle(plotStyle)


class TemporalProfile3DPlotStyle(TemporalProfilePlotStyleBase):

    ITEM_TYPES = OptionListModel()
    ITEM_TYPES.addOption(Option('LinePlotItem', name= '3D Lines'))
    ITEM_TYPES.addOption(Option('ScatterPlotItem', name='3D Scatter Plot'))
    ITEM_TYPES.addOption(Option('MeshItem', name='3D Mesh'))


    sigStyleUpdated = pyqtSignal()
    sigUpdated = pyqtSignal()
    sigExpressionUpdated = pyqtSignal()
    sigSensorChanged = pyqtSignal(SensorInstrument)

    def __init__(self, temporalProfile=None):
        super(TemporalProfile3DPlotStyle, self).__init__(temporalProfile=temporalProfile)
        #assert isinstance(temporalProfile, TemporalProfile)

        # get some good defaults
        self.setExpression('b')
        self.mItemType = 'LinePlotItem'
        self.mIsVisible = True

        self.m3DItemKWDS = {'color': QColor('green'),
                            'width': 2.0,
                            'mode':'line_strip',
                            'antialias':True}

    def setItemKwds(self, kwds):
        self.m3DItemKWDS = kwds
        #self.updateStyleProperties()

    def itemKwds(self):
        return self.m3DItemKWDS.copy()


    def updateStyleProperties(self):
        """
        Updates changes in coloring and visibility
        :return:
        """
        for pdi in self.mPlotItems:

            s = ""


    def updateDataProperties(self):
        """
        Updates changes in the underlying data or item type
        """
        plotDataItems = self.mPlotItems[:]
        for pdi in self.mPlotItems:
            s  = ""


    def setItemType(self, itemType):
        assert itemType in TemporalProfile3DPlotStyle.ITEM_TYPES.optionValues()
        self.mItemType = itemType
        self.sigDataUpdated.emit()
        #self.updateDataProperties()

    def itemType(self):
        return self.mItemType



    def copyFrom(self, plotStyle):
        super(TemporalProfile3DPlotStyle, self).copyFrom(plotStyle)
        assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
        self.setItemType(plotStyle.itemType())
        self.setItemKwds(plotStyle.itemKwds())

    def update(self):

        for pdi in self.mPlotItems:
            assert isinstance(pdi, TemporalProfilePlotDataItem)
            pdi.updateStyle()

    def createIcon(self, size=None):

        if size is None:
            size = QSize(100,60)

        pm = QPixmap(size)
        pm.fill(self.backgroundColor)
        p = QPainter(pm)

        kwds = self.m3DItemKWDS

        text = '3D'


        #brush = self.canvas.backgroundBrush()
        #c = brush.color()
        #c.setAlpha(170)
        #brush.setColor(c)
        #painter.setBrush(brush)
        #painter.setPen(Qt.NoPen)
        font = p.font()
        fm = QFontMetrics(font)
        backGroundSize = QSizeF(fm.size(Qt.TextSingleLine, text))
        backGroundSize = QSizeF(backGroundSize.width() + 3, -1 * (backGroundSize.height() + 3))
        #backGroundPos = QPointF(ptLabel.x() - 3, ptLabel.y() + 3)
        #background = QPolygonF(QRectF(backGroundPos, backGroundSize))
        #painter.drawPolygon(background)
        color = kwds.get('color')
        if color is None:
            color = QColor('green')
        if self.mItemType == 'LinePlotItem':
            text = 'Lines'
        elif self.mItemType == 'MeshItem':
            text = 'Mesh'
        elif self.mItemType == 'ScatterPlot':
            text = 'Scatter Plot'

        textPen = QPen(Qt.SolidLine)
        textPen.setWidth(1)
        textPen.setColor(color)
        textPos = QPoint(0, int(pm.size().height() * 0.7))
        p.setPen(textPen)
        p.drawText(textPos, text)

        p.end()
        icon = QIcon(pm)

        return icon

    def createPlotItem(self):
        """
        Returns the list of PlotItem related to the current settings
        :return: [list-of plotitems]
        """
        if not OPENGL_AVAILABLE:
            return None

        import pyqtgraph.opengl as gl

        plotItems = []

        sensor = self.sensor()
        tp = self.temporalProfile()
        expression = QgsExpression(self.expression())
        if not isinstance(sensor, SensorInstrument) \
                or not isinstance(tp, TemporalProfile) \
                or not expression.isValid():
            return plotItems

        feature = QgsFeature()
        fields = QgsFields()
        field = QgsField('b', QVariant.Double, 'double', 40, 5)
        fields.append(field)
        feature.setFields(fields)




        dataPos = []
        x0 = x1 = y0 = y1 = z0 = z1 = 0
        for iDate, tsd in enumerate(tp.mTimeSeries):
            assert isinstance(tsd, TimeSeriesDate)
            if tsd.mSensor != sensor:
                continue

            data = tp.data(tsd)
            bandKeys = sorted([k for k in data.keys() if k.startswith('b') and data[k] != None],
                              key=lambda k: bandKey2bandIndex(k))
            if len(bandKeys) == 0:
                continue

            t = date2num(tsd.mDate)

            x = []
            y = []
            z = []

            for i, k in enumerate(bandKeys):
                value = data[k]
                feature.setAttribute('b', float(value))
                context = QgsExpressionContextUtils.createFeatureBasedContext(feature, feature.fields())
                zValue = expression.evaluate(context)
                if zValue is not None:
                    x.append(i)
                    y.append(t)
                    z.append(zValue)
                else:
                    s = ""
            x = np.asarray(x)
            y = np.asarray(y)
            z = np.asarray(z)
            if iDate == 0:
                x0, x1 = (x.min(), x.max())
                y0, y1 = (y.min(), y.max())
                z0, z1 = (z.min(), z.max())
            else:
                x0, x1 = (min(x.min(), x0), max(x.max(), x1))
                y0, y1 = (min(y.min(), y0), max(y.max(), y1))
                z0, z1 = (min(z.min(), z0), max(z.max(), z1))
            dataPos.append((x, y, z))

        xyz = [(x0, x1), (y0, y1), (z0, z1)]
        l = len(dataPos)



        if self.mItemType == 'LinePlotItem':
            for iPos, pos in enumerate(dataPos):
                x, y, z = pos
                arr = np.asarray((x, y, z), dtype=np.float64).transpose()

                # for i, m in enumerate(xyz):
                #    m0, m1 = m
                #    arr[:, i] = (arr[:, i] - m0) / (m1 - m0)

                # degug pyqtgraph

                kwds = copy.copy(self.m3DItemKWDS)
                for k, v in list(kwds.items()):
                    if isinstance(v, QColor):
                        kwds[k] = fn.glColor(v)

                plt = gl.GLLinePlotItem(pos=arr, **kwds)
                plotItems.append(plt)
        else:

            raise NotImplementedError(self.mItemType)


        self.mPlotItems.append(plotItems)

        return plotItems


class TemporalProfilePlotStyle3DWidget(QWidget, loadUI('plotstyle3Dwidget.ui')):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, title='<#>', parent=None):
        super(TemporalProfilePlotStyle3DWidget, self).__init__(parent)
        self.setupUi(self)

        self.mBlockUpdates = False

        self.cb3DItemType.setModel(TemporalProfile3DPlotStyle.ITEM_TYPES)

        #connect signals

        #color buttons
        self.btn3DLinePlotItemColor.colorChanged.connect(self.refreshPreview)
        self.btn3DScatterPlotItemColor.colorChanged.connect(self.refreshPreview)

        #checkboxes
        self.cb3DItemType.currentIndexChanged.connect(self.refreshPreview)
        self.cb3DLinePlotItemMode.currentIndexChanged.connect(self.refreshPreview)

        #spin boxes
        self.sb3DLinePlotItemWidth.valueChanged.connect(self.refreshPreview)
        self.sb3DScatterPlotItemSize.valueChanged.connect(self.refreshPreview)

        self.setPlotStyle(TemporalProfile3DPlotStyle())
        self.refreshPreview()

    def refreshPreview(self, *args):
        if not self.mBlockUpdates:
            #print('DEBUG: REFRESH NOW')
            style = self.plotStyle()

            #todo: set style to style preview
            pi = self.plotDataItem
            pi.setSymbol(style.markerSymbol)
            pi.setSymbolSize(style.markerSize)
            pi.setSymbolBrush(style.markerBrush)
            pi.setSymbolPen(style.markerPen)
            pi.setPen(style.linePen)

            pi.update()
            self.plotWidget.update()
            self.sigPlotStyleChanged.emit(style)


    def setPlotStyle(self, style):
        assert isinstance(style, TemporalProfile3DPlotStyle)
        #set widget values
        self.mLastPlotStyle = style
        self.mBlockUpdates = True
        from eotimeseriesviewer.models import setCurrentComboBoxValue

        itemType = style.mItemType
        model = self.cb3DItemType.model()
        assert isinstance(model, OptionListModel)
        setCurrentComboBoxValue(self.cb3DItemType, itemType)

        kwds = style.itemKwds()

        def d(k, default):
            return kwds[k] if k in kwds.keys() else default

        self.cbAntialias.setChecked(d('antialias', True))
        DEF_COLOR = QColor('green')
        if itemType == 'LinePlotItem':

            self.btn3DLinePlotItemColor.setColor(d('color', DEF_COLOR))
            self.sb3DLinePlotItemWidth.setValue(d('width', 2.0))
            setCurrentComboBoxValue(self.cb3DLinePlotItemMode, d('mode', 'lines'))

        elif itemType == 'ScatterPlotItem':
            self.btn3DScatterPlotItemColor.setColor(d('color', DEF_COLOR))
            self.sb3DScatterPlotItemSize.setValue(d('size', 2.0))
            self.cb3DScatterPlotItemPxMode.setChecked(d('pxMode', True))
        elif itemType == 'MeshItem':
            self.btn3DMeshItemColor.setColor(d('color', DEF_COLOR))
            self.btn3DMeshItemEdgeColor.setColor(d('edgeColor', DEF_COLOR))
            self.cb3DMeshItemDrawEdges.setChecked(d('drawEdges', False))
            self.cb3DMeshItemDrawFaces.setChecked(d('drawFaces', True))
            self.cb3DMeshItemSmooth.setChecked(d('smooth', True))
            self.cb3DMeshItemNormals.setChecked(d('normals', True))
        else:

            raise NotImplementedError()

        self.refreshPreview()


    def plotStyleIcon(self):
        icon = QIcon()
        #todo: get plot preview as 60x60 icon
        return icon

    def plotStyle(self):

        itemType = self.cb3DItemType.currentData(role=Qt.UserRole).value()
        style = TemporalProfile3DPlotStyle()
        style.setTemporalProfile(self.mLastPlotStyle.temporalProfile())
        style.setItemType(itemType)
        kwds = {'antialias':self.cbAntialias.isChecked()}

        if itemType == 'LinePlotItem':
            kwds['color'] = self.btn3DLinePlotItemColor.color()
            kwds['width'] = self.sb3DLinePlotItemWidth.value()
            kwds['mode'] = self.cb3DLinePlotItemMode.currentData(role=Qt.DisplayRole)
        elif itemType == 'ScatterPlotItem':
            kwds['color'] = self.btn3DScatterPlotItemColor.color()
            kwds['size'] = self.sb3DScatterPlotItemSize.value()
            kwds['pxMode'] = self.cb3DScatterPlotItemPxMode.isChecked()
        elif itemType == 'MeshItem':
            kwds['color'] = self.btn3DMeshItemColor.color()
            kwds['edgeColor'] = self.btn3DMeshItemEdgeColor.color()
            kwds['drawEdges'] = self.cb3DMeshItemDrawEdges.isChecked()
            kwds['drawFaces'] = self.cb3DMeshItemDrawFaces.isChecked()
            kwds['smooth'] = self.cb3DMeshItemSmooth.isChecked()
            kwds['normals'] = self.cb3DMeshItemNormals.isChecked()
        else:

            raise NotImplementedError()

        style.setItemKwds(kwds)
        return style

