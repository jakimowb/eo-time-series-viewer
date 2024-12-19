from qgis.PyQt.QtCore import QPoint, Qt
from qgis.PyQt.QtGui import QColor, QPen
from qgis.PyQt.QtWidgets import QAction, QMenu, QSlider, QWidgetAction
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen
from eotimeseriesviewer.temporalprofile.plotstyle import TemporalProfilePlotStyle


class TemporalProfilePlotDataItem(pg.PlotDataItem):

    def __init__(self, plotStyle: TemporalProfilePlotStyle, parent=None):
        assert isinstance(plotStyle, TemporalProfilePlotStyle)

        super(TemporalProfilePlotDataItem, self).__init__([], [], parent=parent)
        self.menu: QMenu = None
        # self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.mPlotStyle: TemporalProfilePlotStyle = plotStyle
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.mPlotStyle.sigUpdated.connect(self.updateDataAndStyle)
        self.updateDataAndStyle()

    # On right-click, raise the context menu
    def mouseClickEvent(self, ev):
        if ev.button() == Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QPoint(pos.x(), pos.y()))
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
            alphaSlider.setOrientation(Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu

    def updateStyle(self):
        """
        Updates visibility properties
        """
        self.setVisible(self.mPlotStyle.isVisible())
        self.setSymbol(self.mPlotStyle.markerSymbol)
        self.setSymbolSize(self.mPlotStyle.markerSize)
        self.setSymbolBrush(self.mPlotStyle.markerBrush)
        self.setSymbolPen(self.mPlotStyle.markerPen)
        self.setPen(self.mPlotStyle.linePen)
        self.update()

    def setClickable(self, b, width=None):
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setColor(self, color):
        if not isinstance(color, QColor):
            color = QColor(color)
        self.setPen(color)

    def pen(self):
        return mkPen(self.opts['pen'])

    def color(self):
        return self.pen().color()

    def setLineWidth(self, width):
        pen = pg.mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)
