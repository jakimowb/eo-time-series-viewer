import os

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer import *
from timeseriesviewer.utils import *

from timeseriesviewer.ui.widgets import loadUIFormClass
import pyqtgraph as pg
load = lambda p : loadUIFormClass(jp(DIR_UI,p))

MARKERSYMBOLS = [('o', u'Circle'),
                 ('t',u'Triangle Down'),
                 ('t1',u'Triangle Up'),
                 ('t2',u'Triangle Right'),
                 ('t3', u'Triangle Left'),
                 ('p',u'Pentagon'),
                 ('h', u'Hexagon'),
                 ('s',u'Star'),
                 ('+',u'Plus'),
                 ('d',u'Diamond'),
                 (None, u'No Symbol')
                 ]

PENSTYLES = [(Qt.SolidLine, '___'),
             (Qt.DashLine, '_ _ _'),
             (Qt.DotLine, '. . .'),
             (Qt.DashDotLine, '_ .'),
             (Qt.DashDotDotLine, '_ . .'),
             (Qt.NoPen, 'No Pen')]

class PlotStyle(object):
    def __init__(self, **kwds):

        self.markerSymbol = MARKERSYMBOLS[0][0]
        self.markerSize = 10
        self.markerBrush = QBrush()
        self.markerBrush.setColor(QColor(55,55,55))
        self.markerBrush.setStyle(Qt.SolidPattern)

        self.markerPen = QPen()
        self.markerPen.setStyle(Qt.SolidLine)
        self.markerPen.setColor(Qt.white)

        self.linePen = QPen()
        self.linePen.setStyle(Qt.SolidLine)
        self.linePen.setColor(QColor(74,75,75))



class PlotStyleWidget(QWidget, load('plotstylewidget.ui')):
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

        for t in MARKERSYMBOLS:
            self.cbMarkerSymbol.addItem(t[1], t[0])
        for t in PENSTYLES:
            self.cbMarkerPenStyle.addItem(t[1], t[0])
            self.cbLinePenStyle.addItem(t[1], t[0])

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


        self.setPlotStyle(PlotStyle())
        self.refreshPreview()

    def refreshPreview(self, *args):
        if not self.mBlockUpdates:
            print('DEBUG: REFRESH NOW')
            style = self.plotStyle()
            #todo: set style to style preview


            pi = self.plotDataItem
            pi.setData(x=[0.25, 0.5, 0.75], y=[0.25, 0.75, 0.5],
                       symbol=style.markerSymbol, symbolBrush=style.markerBrush,
                       symbolPen=style.markerPen, symbolSize=style.markerSize,
                       pen = style.linePen, width=style.linePen.width())
            #symbol='o', symbolBrush=sensorView.color, symbolPen='w', symbolSize=8
            pi.update()
            self.plotWidget.update()
            self.sigPlotStyleChanged.emit(style)

    def _setComboBoxToValue(self, cb, value):
        assert isinstance(cb, QComboBox)
        for i in range(cb.count()):
            v = cb.itemData(i)
            if type(value) in [str, unicode]:
                v = str(v)
            if v == value:
                cb.setCurrentIndex(i)
                break
        s = ""

    def setPlotStyle(self, style):
        assert isinstance(style, PlotStyle)
        #set widget values

        self.mBlockUpdates = True
        self.sbMarkerSize.setValue(style.markerSize)
        self._setComboBoxToValue(self.cbMarkerSymbol, style.markerSymbol)


        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)


        self.btnMarkerPenColor.setColor(style.markerPen.color())
        self._setComboBoxToValue(self.cbMarkerPenStyle, style.markerPen.style())
        self.sbMarkerPenWidth.setValue(style.markerPen.width())
        self.btnMarkerBrushColor.setColor(style.markerBrush.color())

        self.btnLinePenColor.setColor(style.linePen.color())
        self._setComboBoxToValue(self.cbLinePenStyle, style.linePen.style())

        self.sbLinePenWidth.setValue(style.linePen.width())

        self.mBlockUpdates = False

        self.refreshPreview()

    def plotStyle(self):
        style = PlotStyle()
        #read plotstyle values from widgets
        style.markerSize = self.sbMarkerSize.value()
        symbol = self.cbMarkerSymbol.itemData(self.cbMarkerSymbol.currentIndex())
        if isinstance(symbol, unicode):
            symbol = str(symbol)
        style.markerSymbol = symbol
        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)

        style.markerPen = pg.mkPen(color=self.btnMarkerPenColor.color(),
                                   width=self.sbMarkerPenWidth.value(),
                                   style=self.cbMarkerPenStyle.itemData(self.cbMarkerPenStyle.currentIndex()))


        style.markerBrush.setColor(self.btnMarkerBrushColor.color())
        style.markerBrush.setColor(self.btnMarkerBrushColor.color())

        style.linePen = pg.mkPen(color=self.btnLinePenColor.color(),
                                 width=self.sbLinePenWidth.value(),
                                 style=self.cbLinePenStyle.itemData(self.cbLinePenStyle.currentIndex()))

        return style

class PlotStyleDialog(QgsDialog):

    @staticmethod
    def getPlotStyle(*args, **kwds):
        """
        Opens a CrosshairDialog.
        :param args:
        :param kwds:
        :return: specified CrosshairStyle if accepted, else None
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
        #self.setLayout(l)


    def plotStyle(self):
        return self.w.plotStyle()

    def setPlotStyle(self, plotStyle):
        assert isinstance(plotStyle, PlotStyle)
        self.w.setPlotStyle(plotStyle)



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    style = PlotStyleDialog.getPlotStyle()
    print(style)
    qgsApp.exec_()
    qgsApp.exitQgis()
