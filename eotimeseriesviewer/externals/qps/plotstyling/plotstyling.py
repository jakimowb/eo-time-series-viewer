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

import os, json, sys

from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from ..externals.pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol
from ..externals.pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from ..utils import *
from ..models import OptionListModel, Option, currentComboBoxValue, setCurrentComboBoxValue
from ..externals import pyqtgraph as pg

DEBUG = False

MODULE_IMPORT_PATH = None

for name, module in sys.modules.items():
    if hasattr(module, '__file__') and module.__file__ == __file__:
        MODULE_IMPORT_PATH = name
        break


def log(msg: str):
    if DEBUG:
        QgsMessageLog.logMessage(msg, 'plotstyling.py')


MARKERSYMBOLS = [Option('o', u'Circle'),
                 Option('t', u'Triangle Down'),
                 Option('t1', u'Triangle Up'),
                 Option('t2', u'Triangle Right'),
                 Option('t3', u'Triangle Left'),
                 Option('p', u'Pentagon'),
                 Option('h', u'Hexagon'),
                 Option('s', u'Star'),
                 Option('+', u'Plus'),
                 Option('d', u'Diamond'),
                 Option(None, u'No Symbol')
                 ]

MARKERSYMBOLS2QGIS_SYMBOLS = dict()
for o in MARKERSYMBOLS:
    name = o.name()
    name = name.replace(' ', '_')
    name = name.lower()
    MARKERSYMBOLS2QGIS_SYMBOLS[o.value()] = name

PENSTYLES = [Option(Qt.SolidLine, '___'),
             Option(Qt.DashLine, '_ _ _'),
             Option(Qt.DotLine, '. . .'),
             Option(Qt.DashDotLine, '_ .'),
             Option(Qt.DashDotDotLine, '_ . .'),
             Option(Qt.NoPen, 'No Pen')]


def brush2tuple(brush: QBrush) -> tuple:
    return (
        QgsSymbolLayerUtils.encodeColor(brush.color()),
        # setMatrix
        QgsSymbolLayerUtils.encodeBrushStyle(brush.style())
        # texture
        # transform
    )


def tuple2brush(t: tuple) -> QBrush:
    # log('tuple2brush')
    assert len(t) == 2
    brush = QBrush()
    brush.setColor(QgsSymbolLayerUtils.decodeColor(t[0]))
    brush.setStyle(QgsSymbolLayerUtils.decodeBrushStyle(t[1]))
    return brush


def pen2tuple(pen: QPen) -> tuple:
    # log('pen2tuple')
    return (
        pen.width(),
        brush2tuple(pen.brush()),  # 1
        QgsSymbolLayerUtils.encodePenCapStyle(pen.capStyle()),
        QgsSymbolLayerUtils.encodeColor(pen.color()),
        pen.isCosmetic(),
        pen.dashOffset(),  # 5
        pen.dashPattern(),
        QgsSymbolLayerUtils.encodePenJoinStyle(pen.joinStyle()),
        pen.miterLimit(),
        QgsSymbolLayerUtils.encodePenStyle(pen.style())  # 9

    )


def tuple2pen(t: tuple) -> QPen:
    assert len(t) == 10
    pen = QPen()
    pen.setWidth(t[0])
    pen.setBrush(tuple2brush(t[1]))
    pen.setCapStyle(QgsSymbolLayerUtils.decodePenCapStyle(t[2]))
    pen.setColor(QgsSymbolLayerUtils.decodeColor(t[3]))
    pen.setCosmetic(t[4])
    pen.setDashOffset(t[5])
    pen.setDashPattern(t[6])
    pen.setJoinStyle(QgsSymbolLayerUtils.decodePenJoinStyle(t[7]))
    pen.setMiterLimit(t[8])
    pen.setStyle(QgsSymbolLayerUtils.decodePenStyle(t[9]))
    return pen


def runPlotStyleActionRoutine(layerID, styleField: str, id: int):
    """
    Is applied to a set of layer features to change the plotStyle JSON string stored in styleField
    :param layerID: QgsVectorLayer or vector id
    :param styleField: str, name of string field in layer.fields() to store the PlotStyle
    :param id: feature id of feature for which the QgsAction was called
    """

    layer = findMapLayer(layerID)
    if isinstance(layer, QgsVectorLayer):
        selectedFIDs = layer.selectedFeatureIds()
        if id in selectedFIDs:
            ids = selectedFIDs
        else:
            ids = [id]
        if len(ids) == 0:
            return

        fieldName = styleField
        fieldIndex = layer.fields().lookupField(fieldName)
        style = None
        features = [f for f in layer.getFeatures(ids)]

        for f in features:
            json = f.attribute(fieldName)
            style = PlotStyle.fromJSON(json)
            if isinstance(style, PlotStyle):
                style = PlotStyle.fromDialog(plotStyle=style)
                break
        if isinstance(style, PlotStyle):
            json = style.json()
            b = layer.isEditable()
            layer.startEditing()
            for f in features:
                f.setAttribute(fieldName, json)
                layer.changeAttributeValues(f.id(), {fieldIndex: json})
            if not b:
                layer.commitChanges()
    else:
        print('Unable to find layer "{}"'.format(layerID))


def createSetPlotStyleAction(field, mapLayerStore='QgsProject.instance()'):
    """
    Creates a QgsAction to set the style field of a QgsVectorLayer
    :param field: QgsField , the field to store the serialized PlotStyle
    :param mapLayerStore: str, code handle to access the relevant QgsMapLayer store
    :return: QgsAction
    """
    assert isinstance(field, QgsField)
    assert field.type() == QVariant.String

    iconPath = ':/qt-project.org/styles/commonstyle/images/standardbutton-clear-128.png'
    pythonCode = """
from {modulePath} import runPlotStyleActionRoutine
layerId = '[% @layer_id %]'
runPlotStyleActionRoutine(layerId, '{styleField}' , [% $id %])
""".format(modulePath=MODULE_IMPORT_PATH, mapLayerStore=mapLayerStore, styleField=field.name())

    return QgsAction(QgsAction.GenericPython, 'Set PlotStyle', pythonCode, iconPath, True,
                     notificationMessage='msgSetPlotStyle',
                     actionScopes={'Feature'})


class PlotStyle(QObject):
    """
    A class to store PyQtGraph specific plot settings
    """
    sigUpdated = pyqtSignal()

    @staticmethod
    def fromPlotDataItem( pdi:PlotDataItem):

        ps = PlotStyle()
        linePen = pg.mkPen(pdi.opts['pen'])

        ps.linePen = linePen
        ps.markerSymbol = pdi.opts['symbol']
        ps.markerBrush = pg.mkBrush(pdi.opts['symbolBrush'])
        ps.markerSize = pdi.opts['symbolSize']
        ps.markerPen = pg.mkPen(pdi.opts['symbolPen'])
        ps.mIsVisible = pdi.isVisible()

        return ps


    def __init__(self, **kwds):
        plotStyle = kwds.get('plotStyle')
        if plotStyle:
            kwds.pop('plotStyle')
        super(PlotStyle, self).__init__()

        self.markerSymbol = MARKERSYMBOLS[0].mValue
        self.markerSize = 5
        self.markerBrush = QBrush()
        self.markerBrush.setColor(Qt.green)
        self.markerBrush.setStyle(Qt.SolidPattern)

        self.backgroundColor = QColor(Qt.black)

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

    def lineWidth(self)->int:
        return self.linePen.width()

    def setLineWidth(self, width:int):
        self.linePen.setWidth(width)

    def lineColor(self)->QColor:
        return self.linePen.color()

    def setLineColor(self, color:QColor):
        if not isinstance(color, QColor):
            color = QColor(color)
        self.linePen.setColor(color)

    def apply(self, pdi:PlotDataItem, updateItem:bool=True):

        assert isinstance(pdi, PlotDataItem)

        pdi.opts['pen'] = pg.mkPen(self.linePen)
        pdi.opts['symbol'] = self.markerSymbol
        pdi.opts['symbolPen'] = pg.mkPen(self.markerPen)
        pdi.opts['symbolBrush'] = pg.mkBrush(self.markerBrush)
        pdi.opts['symbolSize'] = self.markerSize

        pdi.setVisible(self.mIsVisible)
        if updateItem:
            pdi.updateItems()





    @staticmethod
    def fromJSON(jsonString: str):
        """
        Takes a json string and returns a PlotStyle if any plot-style attribute was set
        see https://www.gdal.org/ogr_feature_style.html for details

        :param ogrFeatureStyle: str
        :return: [list-of-PlotStyles], usually of length = 1
        """
        # log('BEGIN fromJSON')
        if not isinstance(jsonString, str):
            return None
        try:
            obj = json.loads(jsonString)
        except Exception:
            return None

        plotStyle = PlotStyle()
        if 'markerPen' in obj.keys():
            plotStyle.markerPen = tuple2pen(obj['markerPen'])
        if 'markerBrush' in obj.keys():
            plotStyle.markerBrush = tuple2brush(obj['markerBrush'])
        if 'markerSymbol' in obj.keys():
            plotStyle.markerSymbol = obj['markerSymbol']
        if 'markerSize' in obj.keys():
            plotStyle.markerSize = obj['markerSize']
        if 'linePen' in obj.keys():
            plotStyle.linePen = tuple2pen(obj['linePen'])
        if 'isVisible' in obj.keys():
            plotStyle.setVisibility(obj['isVisible'])
        if 'backgroundColor' in obj.keys():
            plotStyle.backgroundColor = QgsSymbolLayerUtils.decodeColor(obj['backgroundColor'])
        # log('END fromJSON')
        return plotStyle

    @staticmethod
    def fromDialog(*args, **kwds):
        """
        Selects a PlotStyle from a user dialog
        :param self:
        :param args:
        :param kwds:
        :return: PlotStyle
        """

        return PlotStyleDialog.getPlotStyle(*args, **kwds)

    def json(self) -> str:
        """Returns a JSON representation of this plot style
        """
        # log('START json()')
        style = dict()
        style['markerPen'] = pen2tuple(self.markerPen)
        style['markerBrush'] = brush2tuple(self.markerBrush)
        style['markerSymbol'] = self.markerSymbol
        style['markerSize'] = self.markerSize
        style['linePen'] = pen2tuple(self.linePen)
        style['isVisible'] = self.mIsVisible
        style['backgroundColor'] = QgsSymbolLayerUtils.encodeColor(self.backgroundColor)
        dump = json.dumps(style, sort_keys=True, indent=0, separators=(',', ':'))
        # log('END json()')
        return dump

    def setVisibility(self, b):
        """
        Sets the visibility of a plot item
        :param b: bool
        """
        # log('setVisibility')
        b = bool(b)
        assert isinstance(b, bool)
        old = self.mIsVisible
        self.mIsVisible = b

        if b != old:
            self.update()

    def update(self):
        """
        Calls the sigUpdated signal
        :return:
        """
        self.sigUpdated.emit()

    def isVisible(self) -> bool:
        """
        Visibility of the plot item
        :return: bool
        """
        return self.mIsVisible

    def __copy__(self):
        style = PlotStyle()
        style.copyFrom(self)
        return style

    def clone(self):
        return copy.copy(self)

    def copyFrom(self, plotStyle):
        """
        Copy plot settings from another plot style
        :param plotStyle: PlotStyle
        """
        # log('copyFrom')
        assert isinstance(plotStyle, PlotStyle)

        self.markerSymbol = plotStyle.markerSymbol
        self.markerBrush = QBrush(plotStyle.markerBrush)
        self.markerPen = QPen(plotStyle.markerPen)
        self.markerSize = plotStyle.markerSize
        self.backgroundColor = QColor(plotStyle.backgroundColor)
        self.linePen = QPen(plotStyle.linePen)

        self.setVisibility(plotStyle.isVisible())

    def createIcon(self, size=None) -> QIcon:
        """
        Creates a QIcon to show this PlotStyle
        :param size: QSize
        :return: QIcon
        """
        return QIcon(self.createPixmap(size=size))

    def createPixmap(self, size=None) -> QPixmap:
        """
        Creates a QPixmap to show this PlotStyle
        :param size: QSize
        :return: QPixmap
        """

        if size is None:
            size = QSize(60, 60)

        pm = QPixmap(size)
        pm.fill(self.backgroundColor)

        p = QPainter(pm)
        # draw the line

        p.setPen(self.linePen)

        w, h = pm.width(), pm.height()

        hw, hh = int(w * 0.5), int(h * 0.5)
        w2, h2 = int(w * 0.75), int(h * 0.75)
        # p.drawLine(x1,y1,x2,y2)

        p.drawLine(2, h - 2, hw, hh)
        p.drawLine(hw, hh, w - 2, int(h * 0.3))

        p.translate(pm.width() / 2, pm.height() / 2)
        drawSymbol(p, self.markerSymbol, self.markerSize, self.markerPen, self.markerBrush)
        p.end()
        return pm

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, PlotStyle):
            return False
        for k in self.__dict__.keys():
            if not self.__dict__[k] == other.__dict__[k]:
                # bugfix if two pens are the same but pen1 != pen2
                if isinstance(self.__dict__[k], QPen):
                    p1, p2 = self.__dict__[k], other.__dict__[k]
                    assert isinstance(p1, QPen)
                    assert isinstance(p2, QPen)

                    if p1.brush() != p2.brush(): return False
                    if p1.capStyle() != p2.capStyle(): return False
                    if p1.color() != p2.color(): return False
                    if p1.dashPattern() != p2.dashPattern(): return False
                    if p1.dashOffset() != p2.dashOffset(): return False
                    if p1.isCosmetic() != p2.isCosmetic(): return False
                    if p1.isSolid() != p2.isSolid(): return False
                    if p1.joinStyle() != p2.joinStyle(): return False
                    if p1.miterLimit() != p2.miterLimit(): return False
                    if p1.style() != p2.style(): return False
                    if p1.width() != p2.width(): return False
                    if p1.widthF() != p2.widthF(): return False
                    s = ""

                else:

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

    def __init__(self, title='<#>', parent=None, x=None, y=None, plotStyle:PlotStyle=PlotStyle()):
        super(PlotStyleWidget, self).__init__(parent)
        self.setupUi(self)
        assert isinstance(self.plotWidget, pg.PlotWidget)

        self.mBlockUpdates = False
        # self.plotWidget.disableAutoRange()
        # self.plotWidget.setAspectLocked()
        self.plotWidget.setRange(xRange=[0, 1], yRange=[0, 1], update=True)
        self.plotWidget.setLimits(xMin=0, xMax=1, yMin=0, yMax=1)
        self.plotWidget.setMouseEnabled(x=False, y=False)

        for ax in self.plotWidget.plotItem.axes:
            self.plotWidget.plotItem.hideAxis(ax)
        # self.plotWidget.disableAutoRange()

        if x is None or y is None:
            # some arbitrary values
            x = [0.10, 0.5, 0.9]
            y = [0.25, 0.9, 0.5]
        assert len(x) == len(y), 'x and y need to be lists of same length.'

        self.plotDataItem = self.plotWidget.plot(x=x, y=y)
        self.legend = pg.LegendItem((100, 60), offset=(70, 30))  # args are (size, offset)
        self.legend.setParentItem(self.plotDataItem.topLevelItem())  # Note we do NOT call plt.addItem in this case
        self.legend.hide()

        self.mMarkerSymbolModel = OptionListModel(options=MARKERSYMBOLS)
        self.cbMarkerSymbol.setModel(self.mMarkerSymbolModel)
        self.mPenAndLineStyleModel = OptionListModel(options=PENSTYLES)
        self.cbMarkerPenStyle.setModel(self.mPenAndLineStyleModel)
        self.cbLinePenStyle.setModel(self.mPenAndLineStyleModel)

        # connect signals
        self.btnMarkerBrushColor.colorChanged.connect(self.refreshPreview)
        self.btnMarkerPenColor.colorChanged.connect(self.refreshPreview)
        self.btnLinePenColor.colorChanged.connect(self.refreshPreview)

        self.cbMarkerSymbol.currentIndexChanged.connect(self.refreshPreview)
        self.cbMarkerSymbol.currentIndexChanged.connect(
            lambda: self.toggleWidgetEnabled(self.cbMarkerSymbol, [self.btnMarkerBrushColor, self.sbMarkerSize]))
        self.cbMarkerPenStyle.currentIndexChanged.connect(self.refreshPreview)
        self.cbMarkerPenStyle.currentIndexChanged.connect(
            lambda: self.toggleWidgetEnabled(self.cbMarkerPenStyle, [self.btnMarkerPenColor, self.sbMarkerPenWidth]))
        self.cbLinePenStyle.currentIndexChanged.connect(self.refreshPreview)
        self.cbLinePenStyle.currentIndexChanged.connect(
            lambda: self.toggleWidgetEnabled(self.cbLinePenStyle, [self.btnLinePenColor, self.sbLinePenWidth]))

        self.sbMarkerSize.valueChanged.connect(self.refreshPreview)
        self.sbMarkerPenWidth.valueChanged.connect(self.refreshPreview)
        self.sbLinePenWidth.valueChanged.connect(self.refreshPreview)
        self.mLastPlotStyle = None
        self.cbIsVisible.toggled.connect(self.refreshPreview)
        self.setPlotStyle(plotStyle)
        self.refreshPreview()

    def toggleWidgetEnabled(self, cb: QComboBox, widgets: list):
        """
        Toggles if widgets are enabled according to the QComboBox text values
        :param cb: QComboBox
        :param widgets: [list-of-QWidgets]
        """
        text = cb.currentText()
        enabled = re.search(r'No (Pen|Symbol)', text) is None
        for w in widgets:
            assert isinstance(w, QWidget)
            w.setEnabled(enabled)

    def setPreviewVisible(self, b:bool):
        """
        Sets the visibility of the preview window.
        :param b:
        :type b:
        """
        assert isinstance(b, bool)
        self.plotWidget.setVisible(b)


    def refreshPreview(self, *args):
        if not self.mBlockUpdates:
            # log(': REFRESH NOW')
            style = self.plotStyle()

            # todo: set style to style preview
            pi = self.plotDataItem
            pi.setSymbol(style.markerSymbol)
            pi.setSymbolSize(style.markerSize)
            pi.setSymbolBrush(style.markerBrush)
            pi.setSymbolPen(style.markerPen)
            pi.setPen(style.linePen)
            pi.setVisible(style.isVisible())
            pi.update()
            self.plotWidget.update()

            self.sigPlotStyleChanged.emit(style)

    def setPlotStyle(self, style):
        assert isinstance(style, PlotStyle)
        # set widget values
        self.mLastPlotStyle = style
        self.mBlockUpdates = True
        self.sbMarkerSize.setValue(style.markerSize)
        # self._setComboBoxToValue(self.cbMarkerSymbol, style.markerSymbol)
        setCurrentComboBoxValue(self.cbMarkerSymbol, style.markerSymbol)

        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)

        self.btnMarkerPenColor.setColor(style.markerPen.color())
        # self._setComboBoxToValue(self.cbMarkerPenStyle, style.markerPen.style())
        setCurrentComboBoxValue(self.cbMarkerPenStyle, style.markerPen.style())
        self.sbMarkerPenWidth.setValue(style.markerPen.width())
        self.btnMarkerBrushColor.setColor(style.markerBrush.color())

        self.btnLinePenColor.setColor(style.linePen.color())
        # self._setComboBoxToValue(self.cbLinePenStyle, style.linePen.style())
        setCurrentComboBoxValue(self.cbLinePenStyle, style.linePen.style())
        self.sbLinePenWidth.setValue(style.linePen.width())
        self.cbIsVisible.setChecked(style.isVisible())
        self.mBlockUpdates = False

        self.refreshPreview()

    def plotStyleIcon(self):
        icon = QIcon()
        # todo: get plot preview as 60x60 icon
        return icon

    def plotStyle(self):
        style = PlotStyle(plotStyle=self.mLastPlotStyle)

        # read plotstyle values from widgets
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

        # style.linePen = pg.mkPen(plotStyle=self.btnLinePenColor.plotStyle(),
        #                         width=self.sbLinePenWidth.value(),
        #                         style=currentComboBoxValue(self.cbLinePenStyle))
        style.linePen.setColor(self.btnLinePenColor.color())
        style.linePen.setWidth(self.sbLinePenWidth.value())
        style.linePen.setStyle(currentComboBoxValue(self.cbLinePenStyle))
        style.setVisibility(self.cbIsVisible.isChecked())
        return style


class PlotStyleButton(QToolButton):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, *args, **kwds):
        super(PlotStyleButton, self).__init__(*args, **kwds)
        self.mPlotStyle = PlotStyle()

        self.mInitialButtonSize = None
        self.setStyleSheet('* { padding: 0px; }')
        # self.clicked.connect(self.showDialog)
        # self.setPlotStyle(PlotStyle())
        self._updateIcon()

        self.mMenu = QMenu()
        self.mMenu.triggered.connect(self.onAboutToShowMenu)
        # self.mWidget = PlotStyleWidget()
        self.mDialog = PlotStyleDialog()
        self.mDialog.setModal(False)
        self.mDialog.setPlotStyle(self.mPlotStyle)
        # self.mWidget.sigPlotStyleChanged.connect(self.setPlotStyle)
        self.mDialog.accepted.connect(self.onAccepted)
        self.mDialog.rejected.connect(self.onCanceled)
        self.mWA = QWidgetAction(self.mMenu)
        self.mWA.setDefaultWidget(self.mDialog)
        self.mMenu.addAction(self.mWA)
        self.mMenu.aboutToShow.connect(self.onAboutToShowMenu)
        self.setMenu(self.mMenu)
        self.setPopupMode(QToolButton.MenuButtonPopup)
        self.clicked.connect(lambda: self.activateWindow())
        # self.clicked.connect(self.onTest)

    def onAboutToShowMenu(self, *args):
        self.mWA.setVisible(True)
        self.mDialog.setVisible(True)
        self.mDialog.setPlotStyle(self.mPlotStyle)
        self.mDialog.activateWindow()

    def onAccepted(self, *args):
        if isinstance(self.mDialog, PlotStyleDialog):
            ps = self.mDialog.plotStyle()
            if ps != self.mPlotStyle:
                self.mPlotStyle = ps
                self._updateIcon()
                self.sigPlotStyleChanged.emit(ps)
        self.mWA.setVisible(False)

    def onCanceled(self, *args):
        self.mWA.setVisible(False)

    def plotStyle(self):
        return PlotStyle(plotStyle=self.mPlotStyle)

    def setPlotStyle(self, plotStyle):
        if isinstance(plotStyle, PlotStyle):
            log('setPlotStyle...')
            self.mPlotStyle.copyFrom(plotStyle)
            self.mDialog.setPlotStyle(plotStyle)
            self._updateIcon()
            self.sigPlotStyleChanged.emit(self.mPlotStyle)
        else:

            s = ""

    def resizeEvent(self, arg):
        self._updateIcon()

    def _updateIcon(self):
        if self.mInitialButtonSize is None:
            self.mInitialButtonSize = self.sizeHint()
            self.setIconSize(self.mInitialButtonSize)

        self.mInitialButtonSize = self.size()
        self.setIconSize(self.mInitialButtonSize)

        if self.mPlotStyle != None:
            s = self.mInitialButtonSize
            s = self.sizeHint()
            # s = QSize()
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

        if d.exec_() == QDialog.Accepted:
            return d.plotStyle()
        else:
            return None

    def __init__(self, parent=None, plotStyle=None, title='Specify Plot Style', **kwds):
        super(PlotStyleDialog, self).__init__(parent=parent, \
                                              buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                              **kwds)
        self.w = PlotStyleWidget(parent=self)
        self.setWindowTitle(title)
        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cancel')
        buttonBar = QHBoxLayout()
        # buttonBar.addWidget(self.btCancel)
        # buttonBar.addWidget(self.btOk)
        l = self.layout()
        l.addWidget(self.w)
        l.addLayout(buttonBar)
        if isinstance(plotStyle, PlotStyle):
            self.setPlotStyle(plotStyle)
        # self.setLayout(l)

    def plotStyle(self):
        return self.w.plotStyle()

    def setPlotStyle(self, plotStyle):
        assert isinstance(plotStyle, PlotStyle)
        self.w.setPlotStyle(plotStyle)


class PlotStyleEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(PlotStyleEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mEditorWidget = None
        self.mEditorButton = None
        self.mLabel = None
        self.mDefaultValue = None

    def createWidget(self, parent: QWidget):
        # log('createWidget')
        w = None
        if not self.isInTable(parent):
            w = PlotStyleWidget(parent=parent)
        else:
            # w = PlotStyleButton(parent)
            w = QLabel(parent)

        return w

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        if isinstance(editor, PlotStyleWidget):
            self.mEditorWidget = editor
            self.mEditorWidget.sigPlotStyleChanged.connect(self.onValueChanged)
            s = ""
        if isinstance(editor, PlotStyleButton):
            self.mEditorButton = editor
            self.mEditorButton.sigPlotStyleChanged.connect(self.onValueChanged)

        if isinstance(editor, QLabel):
            self.mLabel = editor
            self.mLabel.setToolTip('Use Form View to edit values')

    def setEnabled(self, enabled: bool):
        # log(' setEnabled={}'.format(enabled))

        if isinstance(self.mEditorWidget, PlotStyleWidget):
            self.mEditorWidget.setEnabled(enabled)
        if isinstance(self.mEditorButton, PlotStyleButton):
            self.mEditorButton.setEnabled(enabled)
        if isinstance(self.mLabel, QLabel):
            self.mLabel.setEnabled(enabled)

    def onValueChanged(self, *args):
        # log(' onValueChangedFORM')

        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs) -> bool:
        return any([isinstance(w, QWidget) for w in [self.mLabel, self.mEditorButton, self.mEditorWidget]])

    def value(self, *args, **kwargs):
        # log(' BEGIN value()')
        # value = self.defaultValue()
        value = self.mDefaultValue
        if isinstance(self.mEditorWidget, PlotStyleWidget):
            value = self.mEditorWidget.plotStyle()
        # if isinstance(self.mEditorButton, PlotStyleButton):
        # value = self.mEditorButton.plotStyle()
        if isinstance(value, PlotStyle):
            value = value.json()
        return value

    def setValue(self, value):

        # log(' setValue()')
        if not isinstance(value, str):
            style = PlotStyle()
        else:
            style = PlotStyle.fromJSON(value)

        if isinstance(style, PlotStyle):
            self.mDefaultValue = value
            if isinstance(self.mEditorWidget, PlotStyleWidget):
                self.mEditorWidget.setPlotStyle(style)
            # if isinstance(self.mEditorButton, PlotStyleButton):
            #    self.mEditorButton.setPlotStyle(style)
            if isinstance(self.mLabel, QLabel):
                self.mLabel.setPixmap(style.createPixmap(self.mLabel.size()))
        else:
            # log('STYLE IS NONE!')
            pass
        # log(' setValue() END')


class PlotStyleEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):
        super(PlotStyleEditorConfigWidget, self).__init__(vl, fieldIdx, parent)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(QLabel('Shows a dialog to specify a PlotStyle'))
        self.mConfig = {}

    def config(self, *args, **kwargs) -> dict:
        log(' config()')
        config = {}

        return config

    def setConfig(self, *args, **kwargs):
        log(' setConfig()')
        self.mConfig = {}


class PlotStyleEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name: str):

        super(PlotStyleEditorWidgetFactory, self).__init__(name)
        self._wrappers = []
        s = ""

    def configWidget(self, vl: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> QgsEditorConfigWidget:
        # print('configWidget()')
        w = PlotStyleEditorConfigWidget(vl, fieldIdx, parent)
        self._wrappers.append(w)
        return w

    def create(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> PlotStyleEditorWidgetWrapper:
        # log(': create(...)')
        w = PlotStyleEditorWidgetWrapper(vl, fieldIdx, editor, parent)
        self._wrappers.append(w)
        return w

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() == QVariant.String and field.length() > 400 and field.name().upper() == 'STYLE':
            return 20
        elif field.type() == QVariant.String:
            return 5
        else:
            return 0  # no support

    def createSearchWidget(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget) -> QgsSearchWidgetWrapper:
        log(' createSearchWidget()')
        return super(PlotStyleEditorWidgetFactory, self).createSearchWidget(vl, fieldIdx, parent)

    def writeConfig(self, config, configElement, doc, layer, fieldIdx):

        s = ""

    def readConfig(self, configElement, layer, fieldIdx):

        d = {}
        return d


EDITOR_WIDGET_REGISTRY_KEY = 'Plot Settings'


def registerPlotStyleEditorWidget():
    reg = QgsGui.editorWidgetRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        global PLOTSTYLE_EDITOR_WIDGET_FACTORY
        PLOTSTYLE_EDITOR_WIDGET_FACTORY = PlotStyleEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, PLOTSTYLE_EDITOR_WIDGET_FACTORY)
