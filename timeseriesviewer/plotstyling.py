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


class PlotStyle(object):
    def __init__(self, **kwds):

        self.symbol = 'o'
        self.symbolBrush = QColor('green')
        self.symbolPen = 'w'
        self.symbolSize = 8


class PlotStyleWidget(QWidget, load('plotstylewidget.ui')):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, title='<#>', parent=None):
        super(PlotStyleWidget, self).__init__(parent)
        self.setupUi(self)
        assert isinstance(self.plotWidget, pg.PlotWidget)


        self.plotWidget.disableAutoRange()
        self.plotWidget.setAspectLocked()
        self.plotWidget.setLimits(xMin=0, xMax=2, yMin=0, yMax=2)
        self.plotWidget.setMouseEnabled(x=False, y=False)
        self.plotWidget.disableAutoRange()

        self.plotItem = self.plotWidget.plot()
        self.plotItem.setData(x=[0.25, 0.5, 0.75], y=[0.25, 0.75, 0.5])
        #self.plotWidget.setCentralItem(self.plotItem)
        self.plotWidget.disableAutoRange()

        self.lastStyle = PlotStyle()
        self.setPlotStyle(self.lastStyle)
    def refreshPlotStylePreview(self, *args):
        style = self.plotStyle()
        #todo: set style to style preview


        self.sigPlotStyleChanged.emit(style)

    def setPlotStyle(self, style):
        assert isinstance(style, PlotStyle)

        self.plotItem.setData(symbol=style.symbol, symbolBrush=style.symbolBrush,
                              symbolPen=style.symbolPen, symbolSize=style.symbolSize)

        self.plotItem.update()
        self.plotWidget.update()

    def plotStyle(self):
        style = PlotStyle()
        #todo: read plotstyle values from widgets
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
            return d.crosshairStyle()
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
