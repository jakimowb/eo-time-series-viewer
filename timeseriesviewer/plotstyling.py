# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
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

import os

from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import numpy as np
from timeseriesviewer import *
from timeseriesviewer.utils import *
from timeseriesviewer.models import OptionListModel, Option, currentComboBoxValue, setCurrentComboBoxValue
import pyqtgraph as pg


MARKERSYMBOLS = [Option('o', u'Circle'),
                 Option('t',u'Triangle Down'),
                 Option('t1',u'Triangle Up'),
                 Option('t2',u'Triangle Right'),
                 Option('t3', u'Triangle Left'),
                 Option('p',u'Pentagon'),
                 Option('h', u'Hexagon'),
                 Option('s',u'Star'),
                 Option('+',u'Plus'),
                 Option('d',u'Diamond'),
                 Option(None, u'No Symbol')
                 ]

MARKERSYMBOLS2QGIS_SYMBOLS = dict()
for o in MARKERSYMBOLS:
    name = o.name()
    name = name.replace(' ','_')
    name = name.lower()
    MARKERSYMBOLS2QGIS_SYMBOLS[o.value()] = name

PENSTYLES = [Option(Qt.SolidLine, '___'),
             Option(Qt.DashLine, '_ _ _'),
             Option(Qt.DotLine, '. . .'),
             Option(Qt.DashDotLine, '_ .'),
             Option(Qt.DashDotDotLine, '_ . .'),
             Option(Qt.NoPen, 'No Pen')]

class PlotStyle(QObject):
    sigUpdated = pyqtSignal()
    def __init__(self, **kwds):
        plotStyle = kwds.get('plotStyle')
        if plotStyle: kwds.pop('plotStyle')
        super(PlotStyle,self).__init__()

        self.markerSymbol = MARKERSYMBOLS[0].mValue
        self.markerSize = 5
        self.markerBrush = QBrush()
        self.markerBrush.setColor(Qt.green)
        self.markerBrush.setStyle(Qt.SolidPattern)

        self.backgroundColor = Qt.black

        self.markerPen = QPen()
        self.markerPen.setCosmetic(True)
        self.markerPen.setStyle(Qt.NoPen)
        self.markerPen.setColor(Qt.white)
        self.markerPen.setWidthF(0)


        self.linePen = QPen()
        self.linePen.setCosmetic(True)
        self.linePen.setStyle(Qt.NoPen)
        self.linePen.setWidthF(0)
        self.linePen.setColor(QColor(74, 75, 75))

        self.mIsVisible = True

        if plotStyle:
            self.copyFrom(plotStyle)




    def setVisibility(self, b):
        assert isinstance(b, bool)
        old = self.mIsVisible
        self.mIsVisible = b

        if b != old:
            self.update()


    def update(self):
        self.sigUpdated.emit()


    def isVisible(self):
        return self.mIsVisible

    def copyFrom(self, plotStyle):
        assert isinstance(plotStyle, PlotStyle)

        self.markerSymbol = plotStyle.markerSymbol
        self.markerBrush = QBrush(plotStyle.markerBrush)
        self.markerPen = QPen(plotStyle.markerPen)
        self.markerSize = plotStyle.markerSize
        self.backgroundColor = QColor(plotStyle.backgroundColor)
        self.linePen = QPen(plotStyle.linePen)

        self.setVisibility(plotStyle.isVisible())

    def createIcon(self, size=None):

        if size is None:
            size = QSize(60,60)

        pm = QPixmap(size)
        pm.fill(self.backgroundColor)

        p = QPainter(pm)
        #draw the line
        p.setPen(self.linePen)
        p.drawLine(2, pm.height()-2, pm.width()-2, 2)
        p.translate(pm.width() / 2, pm.height() / 2)
        from pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol
        drawSymbol(p, self.markerSymbol, self.markerSize, self.markerPen, self.markerBrush)
        p.end()
        return QIcon(pm)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, PlotStyle):
            return False
        for k in self.__dict__.keys():
            if not self.__dict__[k] == other.__dict__[k]:
                return False
        return True

    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = self.__dict__.copy()

        ba = QByteArray()
        s = QDataStream(ba, QIODevice.WriteOnly)
        s.writeQVariant(self.linePen)
        s.writeQVariant(self.markerPen)
        s.writeQVariant(self.markerBrush)
        result['__pickleStateQByteArray__'] = ba
        result.pop('linePen')
        result.pop('markerPen')
        result.pop('markerBrush')

        return result

    def __setstate__(self, state):
        ba = state['__pickleStateQByteArray__']
        s = QDataStream(ba)
        state['linePen'] = s.readQVariant()
        state['markerPen'] = s.readQVariant()
        state['markerBrush'] = s.readQVariant()
        state.pop('__pickleStateQByteArray__')
        self.__dict__.update(state)

class PlotStyleWidget(QWidget, loadUI('plotstylewidget.ui')):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, title='<#>', parent=None):
        super(PlotStyleWidget, self).__init__(parent)
        self.setupUi(self)
        assert isinstance(self.plotWidget, pg.PlotWidget)

        self.mBlockUpdates = False
        #self.plotWidget.disableAutoRange()
        #self.plotWidget.setAspectLocked()
        self.plotWidget.setRange(xRange=[0,1], yRange=[0,1], update=True)
        self.plotWidget.setLimits(xMin=0, xMax=1, yMin=0, yMax=1)
        self.plotWidget.setMouseEnabled(x=False, y=False)

        for ax in self.plotWidget.plotItem.axes:
            self.plotWidget.plotItem.hideAxis(ax)
        #self.plotWidget.disableAutoRange()

        self.plotDataItem = self.plotWidget.plot(x=[0.1, 0.5, 0.9], y=[0.25, 0.9, 0.5])
        self.legend = pg.LegendItem((100,60), offset=(70,30))  # args are (size, offset)
        self.legend.setParentItem(self.plotDataItem.topLevelItem())   # Note we do NOT call plt.addItem in this case
        self.legend.hide()

        self.mMarkerSymbolModel = OptionListModel(options=MARKERSYMBOLS)
        self.cbMarkerSymbol.setModel(self.mMarkerSymbolModel)
        self.mPenAndLineStyleModel = OptionListModel(options=PENSTYLES)
        self.cbMarkerPenStyle.setModel(self.mPenAndLineStyleModel)
        self.cbLinePenStyle.setModel(self.mPenAndLineStyleModel)

        #connect signals
        self.btnMarkerBrushColor.colorChanged.connect(self.refreshPreview)
        self.btnMarkerPenColor.colorChanged.connect(self.refreshPreview)
        self.btnLinePenColor.colorChanged.connect(self.refreshPreview)

        self.cbMarkerSymbol.currentIndexChanged.connect(self.refreshPreview)
        self.cbMarkerPenStyle.currentIndexChanged.connect(self.refreshPreview)
        self.cbLinePenStyle.currentIndexChanged.connect(self.refreshPreview)

        self.sbMarkerSize.valueChanged.connect(self.refreshPreview)
        self.sbMarkerPenWidth.valueChanged.connect(self.refreshPreview)
        self.sbLinePenWidth.valueChanged.connect(self.refreshPreview)
        self.mLastPlotStyle = None

        self.setPlotStyle(PlotStyle())
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
        assert isinstance(style, PlotStyle)
        #set widget values
        self.mLastPlotStyle = style
        self.mBlockUpdates = True
        self.sbMarkerSize.setValue(style.markerSize)
        #self._setComboBoxToValue(self.cbMarkerSymbol, style.markerSymbol)
        setCurrentComboBoxValue(self.cbMarkerSymbol, style.markerSymbol)

        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)


        self.btnMarkerPenColor.setColor(style.markerPen.color())
        #self._setComboBoxToValue(self.cbMarkerPenStyle, style.markerPen.style())
        setCurrentComboBoxValue(self.cbMarkerPenStyle, style.markerPen.style())
        self.sbMarkerPenWidth.setValue(style.markerPen.width())
        self.btnMarkerBrushColor.setColor(style.markerBrush.color())

        self.btnLinePenColor.setColor(style.linePen.color())
        #self._setComboBoxToValue(self.cbLinePenStyle, style.linePen.style())
        setCurrentComboBoxValue(self.cbLinePenStyle, style.linePen.style())
        self.sbLinePenWidth.setValue(style.linePen.width())

        self.mBlockUpdates = False

        self.refreshPreview()


    def plotStyleIcon(self):
        icon = QIcon()
        #todo: get plot preview as 60x60 icon
        return icon

    def plotStyle(self):
        style = PlotStyle(plotStyle=self.mLastPlotStyle)

        #read plotstyle values from widgets
        style.markerSize = self.sbMarkerSize.value()
        symbol = currentComboBoxValue(self.cbMarkerSymbol)
        style.markerSymbol = symbol
        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)

        style.markerPen.setColor(self.btnMarkerPenColor.color())
        style.markerPen.setWidth(self.sbMarkerPenWidth.value())
        style.markerPen.setStyle(currentComboBoxValue(self.cbMarkerPenStyle))

        style.markerBrush.setColor(self.btnMarkerBrushColor.color())


        #style.linePen = pg.mkPen(color=self.btnLinePenColor.color(),
        #                         width=self.sbLinePenWidth.value(),
        #                         style=currentComboBoxValue(self.cbLinePenStyle))
        style.linePen.setColor(self.btnLinePenColor.color())
        style.linePen.setWidth(self.sbLinePenWidth.value())
        style.linePen.setStyle(currentComboBoxValue(self.cbLinePenStyle))

        return style


class PlotStyleButton(QPushButton):


    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, *args, **kwds):
        super(PlotStyleButton, self).__init__(*args, **kwds)
        self.mPlotStyle = PlotStyle()
        self.mInitialButtonSize = None
        self.setStyleSheet('* { padding: 0px; }')
        self.clicked.connect(self.showDialog)
        self.setPlotStyle(PlotStyle())


    def plotStyle(self):
        return PlotStyle(plotStyle=self.mPlotStyle)

    def setPlotStyle(self, plotStyle):
        if isinstance(plotStyle, PlotStyle):
            self.mPlotStyle.copyFrom(plotStyle)
            self._updateIcon()
            self.sigPlotStyleChanged.emit(self.mPlotStyle)
        else:
            s = ""


    def showDialog(self):
        #print(('A',self.mPlotStyle))
        style = PlotStyleDialog.getPlotStyle(plotStyle=self.mPlotStyle)

        if style:
            self.setPlotStyle(style)
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

class PlotStyleDialog(QgsDialog):

    @staticmethod
    def getPlotStyle(*args, **kwds):
        """
        Opens a CrosshairDialog.
        :param args:
        :param kwds:
        :return: specified PlotStyle if accepted, else None
        """
        d = PlotStyleDialog(*args, **kwds)
        d.exec_()

        if d.result() == QDialog.Accepted:
            return d.plotStyle()
        else:

            return None

    def __init__(self, parent=None, plotStyle=None, title='Specify Plot Style'):
        super(PlotStyleDialog, self).__init__(parent=parent , \
            buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = PlotStyleWidget(parent=self)
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


if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer.utils import initQgisApplication
    qgsApp = initQgisApplication()

    import pickle
    s1 = PlotStyle()
    s2 = pickle.loads(pickle.dumps(s1))
    assert isinstance(s2, PlotStyle)
    #btn = QgsSymbolButton()

    #btn = QgsSymbolButton()
    #btn.show()
    d  = PlotStyleDialog()
    d.exec_()

    #btn = PlotStyleButton()
    #btn.show()
    qgsApp.exec_()
    qgsApp.exitQgis()
