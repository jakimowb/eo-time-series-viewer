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
import sys, os, re, collections
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

import pyqtgraph.opengl as gl
from pyqtgraph import functions as fn
from pyqtgraph.opengl import *
from OpenGL.GL import *

from timeseriesviewer.temporalprofiles2d import *

LABEL_EXPRESSION_3D = 'Scaling'

class AxisGrid3D(GLGridItem):
    def __init__(self, *args, **kwds):
        super(AxisGrid3D, self).__init__(*args, **kwds)

        self.mXYRange = np.asarray([[0, 1], [0, 1]])
        self.mColor = QColor('grey')

    def setColor(self, color):
        self.mColor = QColor(color)

    def setXRange(self, x0, x1):
        self.mXYRange[0, 0] = x0
        self.mXYRange[0, 1] = x1

    def setYRange(self, y0, y1):
        self.mXYRange[1, 0] = y0
        self.mXYRange[1, 1] = y1

    def paint(self):
        self.setupGLState()

        if self.antialias:
            glEnable(GL_LINE_SMOOTH)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        glBegin(GL_LINES)

        x0, x1 = self.mXYRange[0, :]
        y0, y1 = self.mXYRange[1, :]
        xs, ys, zs = self.spacing()
        rx = x1 - x0
        ry = y1 - y0
        xvals = np.arange(x0, x1, rx / 10)
        yvals = np.arange(y0, y1, ry / 10)
        # todo: nice line breaks
        # yvals = np.arange(-y / 2., y / 2. + ys * 0.001, ys)
        c = fn.glColor(self.mColor)
        glColor4f(*c)
        for x in xvals:
            glVertex3f(x, yvals[0], 0)
            glVertex3f(x, yvals[-1], 0)
        for y in yvals:
            glVertex3f(xvals[0], y, 0)
            glVertex3f(xvals[-1], y, 0)

        glEnd()


class ViewWidget3D(GLViewWidget):

    def __init__(self, parent=None):
        super(ViewWidget3D, self).__init__(parent)
        self.mousePos = QPoint(-1, -1)
        self.setBackgroundColor(QColor('black'))
        self.setMouseTracking(True)

        self.mDataMinRanges = [0, 0, 0]
        self.mDataMaxRanges = [1, 1, 1]
        self.mDataN = 0

        self.glAxes = Axis3D()

        self.glGridItemXY = AxisGrid3D()
        self.glGridItemXZ = AxisGrid3D()
        self.glGridItemYZ = AxisGrid3D()

        self.glGridItemXZ.setVisible(False)
        self.glGridItemYZ.setVisible(False)

        x, y, z = self.glAxes.size()

        self.glGridItemYZ.rotate(-90, 0, 1, 0)
        self.glGridItemXZ.rotate(90, 1, 0, 0)

        # self.glGridItemXY.scale(x/10,y/10, 1)
        # self.glGridItemXZ.scale(x/10,z/10, 1)
        # self.glGridItemYZ.scale(y/10,z/10, 1)

        self.mBasicItems = [self.glGridItemXY, self.glGridItemXZ, self.glGridItemYZ, self.glAxes]
        for item in self.mBasicItems:
            item.setDepthValue(-10)

            self.addItem(item)  # draw grid/axis after surfaces since they may be translucent

        self.initContextMenu()

    """
    def setDataRangeX(self, x0, x1):
        assert x0 < x1
        self.mDataMinRanges[0] = x0
        self.mDataMaxRanges[0] = x1

    def setDataRangeY(self, y0, y1):
        assert y0 < y1
        self.mDataMinRanges[0] = y0
        self.mDataMaxRanges[0] = y1

    def setDataRangeZ(self, z0, z1):
        assert z0 < z1
        self.mDataMinRanges[0] = z0
        self.mDataMaxRanges[0] = z1
    """

    def initContextMenu(self):

        menu = QMenu()

        # define grid options
        m = menu.addMenu('Grids')

        def visibilityAll(b):
            self.glGridItemXY.setVisible(b)
            self.glGridItemXZ.setVisible(b)
            self.glGridItemYZ.setVisible(b)

        a = m.addAction('Show All')
        a.setCheckable(False)
        a.triggered.connect(lambda: visibilityAll(True))

        a = m.addAction('Hide All')
        a.setCheckable(False)
        a.triggered.connect(lambda: visibilityAll(False))
        m.addSeparator()

        a = m.addAction('XY')
        a.setCheckable(True)
        a.setChecked(self.glGridItemXY.visible())
        a.toggled.connect(self.glGridItemXY.setVisible)

        a = m.addAction('XZ')
        a.setCheckable(True)
        a.setChecked(self.glGridItemXZ.visible())
        a.toggled.connect(self.glGridItemXZ.setVisible)

        a = m.addAction('YZ')
        a.setCheckable(True)
        a.setChecked(self.glGridItemYZ.visible())
        a.toggled.connect(self.glGridItemYZ.setVisible)

        m = menu.addMenu('Axes')

        frame = QFrame()
        l = QHBoxLayout()
        frame.setLayout(l)
        l.addWidget(QLabel('Color'))
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(frame)
        menu.addAction(wa)
        menu.insertMenu(wa, menu)

        self.btnAxisColor = QgsColorButton()

        a = m.addAction('X')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[0])
        a.toggled.connect(lambda b: self.glAxes.setX(visible=b))

        a = m.addAction('Y')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[1])
        a.toggled.connect(lambda b: self.glAxes.setX(visible=b))

        a = m.addAction('Z')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[2])
        a.toggled.connect(lambda b: self.glAxes.setX(visible=b))

        self.mMenu = menu

    def resetCamera(self):

        # self.mDataMinRanges
        self.setCameraPosition(self.mDataMinRanges, distance=5, elevation=10)

    def clearItems(self):
        for item in self.items:
            if item not in self.mBasicItems:
                self.removeItem(item)

    def paintGL(self, *args, **kwds):
        GLViewWidget.paintGL(self, *args, **kwds)
        self.qglColor(Qt.white)
        self.renderAnnotations()

    def zoomToFull(self):

        for item in self.items:
            if item not in self.mBasicItems:
                s = ""
        s = ""

    def updateDataRanges(self):
        x0 = x1 = y0 = y1 = z0 = z1 = n = None

        if hasattr(self, 'items'):
            for item in self.items:
                if item not in self.mBasicItems and hasattr(item, 'pos'):
                    pos = item.pos
                    if x0 is None:
                        n = pos.shape[0]
                        x0 = pos[:, 0].min()
                        y0 = pos[:, 1].min()
                        z0 = pos[:, 2].min()
                        x1 = pos[:, 0].max()
                        y1 = pos[:, 1].max()
                        z1 = pos[:, 2].max()
                    else:
                        n = max(n, pos.shape[0])
                        x0 = min(x0, pos[:, 0].min())
                        y0 = min(y0, pos[:, 1].min())
                        z0 = min(z0, pos[:, 2].min())
                        x1 = max(x1, pos[:, 0].max())
                        y1 = max(y1, pos[:, 1].max())
                        z1 = max(z1, pos[:, 2].max())
            if x1 is not None:
                self.mDataMinRanges = (x0, y0, z0)
                self.mDataMaxRanges = (x1, y1, z1)
                self.mDataN = n
                self.glAxes.setSize(x1, y1, z1)
                self.glGridItemXZ.setSize()

    def mouseMoveEvent(self, ev):
        assert isinstance(ev, QMouseEvent)
        """ Allow Shift to Move and Ctrl to Pan.
        Example taken from https://gist.github.com/blink1073/7406607
        """
        shift = ev.modifiers() & QtCore.Qt.ShiftModifier
        ctrl = ev.modifiers() & QtCore.Qt.ControlModifier
        if shift:
            y = ev.pos().y()
            if not hasattr(self, '_prev_zoom_pos') or not self._prev_zoom_pos:
                self._prev_zoom_pos = y
                return
            dy = y - self._prev_zoom_pos

            def delta():
                return -dy * 5

            ev.delta = delta
            self._prev_zoom_pos = y
            self.wheelEvent(ev)
        elif ctrl:
            pos = ev.pos().x(), ev.pos().y()
            if not hasattr(self, '_prev_pan_pos') or not self._prev_pan_pos:
                self._prev_pan_pos = pos
                return
            dx = pos[0] - self._prev_pan_pos[0]
            dy = pos[1] - self._prev_pan_pos[1]
            self.pan(dx, dy, 0, relative=True)
            self._prev_pan_pos = pos
        else:
            super(ViewWidget3D, self).mouseMoveEvent(ev)

        # items = self.itemsAt((pos.x(), pos.y(), 3, 3))

    def mousePressEvent(self, event):
        super(ViewWidget3D, self).mousePressEvent(event)
        self.mousePos = event.pos()
        if event.button() == 2:
            self.select = True
        else:
            self.select = False

        try:
            print(self.itemsAt((self.mousePos.x(), self.mousePos.y(), 3, 3)))
        except:
            pass

    def renderAnnotations(self):

        if self.glAxes.visible():
            x, y, z = self.glAxes.rangeMaxima()

            if x is not None:
                self.renderText(x, 0, 0, self.glAxes.mLabels[0])
                self.renderText(0, y, 0, self.glAxes.mLabels[1])
                self.renderText(0, 0, z, self.glAxes.mLabels[2])

        # self.renderText(0.8, 0.8, 0.8, 'text 3D')
        self.renderText(5, 10, 'text 2D fixed')

    def contextMenuEvent(self, event):
        assert isinstance(event, QContextMenuEvent)
        self.mMenu.exec_(self.mapToGlobal(event.pos()))


class Axis3D(GLAxisItem):

    def __init__(self, *args, **kwds):
        super(Axis3D, self).__init__(*args, **kwds)

        self.mRanges = np.asarray([[0, 1], [0, 1], [0, 1]])
        self.mColors = [QColor('white'), QColor('white'), QColor('white')]
        self.mVisibility = [True, True, True]
        self.mLabels = ['X', 'Y', 'Z']

    def rangeMinima(self):
        return self.mRanges[:, 0]

    def rangeMaxima(self):
        return self.mRanges[:, 1]

    def _set(self, ax, vMin=None, vMax=None, label=None, color=None, visible=None):
        i = ['x', 'y', 'z'].index(ax.lower())
        if vMin is not None:
            self.mRanges[i][0] = vMin
        if vMax is not None:
            self.mRanges[i][1] = vMax
        if color is not None:
            self.mColors[i] = color
        if label is not None:
            self.mLabels[i] = label
        if visible is not None:
            self.mVisibility[i] = visible

    def setX(self, **kwds):
        self._set('x', **kwds)

    def setY(self, **kwds):
        self._set('y', **kwds)

    def setZ(self, **kwds):
        self._set('z', **kwds)

    def paint(self):
        # glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        # glEnable( GL_BLEND )
        # glEnable( GL_ALPHA_TEST )
        self.setupGLState()

        if self.antialias:
            glEnable(GL_LINE_SMOOTH)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        x0, y0, z0 = self.rangeMinima()
        x1, y1, z1 = self.rangeMaxima()
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor4f(*fn.glColor(self.mColors[2]))

        glVertex3f(0, 0, z0)
        glVertex3f(0, 0, z1)

        glColor4f(*fn.glColor(self.mColors[1]))
        glVertex3f(0, y0, 0)
        glVertex3f(0, y1, 0)

        glColor4f(*fn.glColor(self.mColors[0]))
        glVertex3f(x0, 0, 0)
        glVertex3f(x1, 0, 0)

        glEnd()
        glLineWidth(1.0)



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
        super(QgsDialog, self).__init__(parent=parent , \
            buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
    ITEM_TYPES.addOption(Option('GLLinePlotItem', name= '3D Lines'))
    ITEM_TYPES.addOption(Option('GLScatterPlotItem', name='3D Scatter Plot'))
    ITEM_TYPES.addOption(Option('GLMeshItem', name='3D Mesh'))

    sigUpdated = pyqtSignal()
    sigExpressionUpdated = pyqtSignal()
    sigSensorChanged = pyqtSignal(SensorInstrument)

    def __init__(self, temporalProfile=None):
        super(TemporalProfile3DPlotStyle, self).__init__(temporalProfile=temporalProfile)
        #assert isinstance(temporalProfile, TemporalProfile)

        #TemporalProfilePlotStyleBase.__init__(self, None)

        # get some good defaults
        self.setExpression('b')
        self.mItemType = 'GLLinePlotItem'
        self.mIsVisible = True

        if OPENGL_AVAILABLE:
            from pyqtgraph.opengl import GLLinePlotItem
            pi = GLLinePlotItem()
            self.mGLItemKWDS = {'color': QColor(*[c*255 for c in pi.color]),
                                'width': pi.width,
                                'mode':  pi.mode,
                                'antialias':pi.antialias}
        else:

            self.mGLItemKWDS = {'color': QColor('green'),
                                'width': 2.0,
                                'mode':'lines',
                                'antialias':True}

    def setGLItemKwds(self, kwds):
        self.mGLItemKWDS = kwds

    def glItemKwds(self):
        return self.mGLItemKWDS.copy()


    def setItemType(self, itemType):
        assert itemType in TemporalProfile3DPlotStyle.ITEM_TYPES.optionValues()
        self.mItemType = itemType

    def itemType(self):
        return self.mItemType



    def copyFrom(self, plotStyle):
        super(TemporalProfile3DPlotStyle, self).copyFrom(plotStyle)
        assert isinstance(plotStyle, TemporalProfile3DPlotStyle)
        self.setItemType(plotStyle.itemType())
        self.setGLItemKwds(plotStyle.glItemKwds())
        s = ""


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

        kwds = self.mGLItemKWDS

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
        if self.mItemType == 'GLLinePlotItem':
            text = 'Lines'
        elif self.mItemType == 'GLMeshItem':
            text = 'Mesh'
        elif self.mItemType == 'GLScatterPlot':
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

    def createPlotItem(self, plotWidget):
        if not OPENGL_AVAILABLE:
            return None

        import pyqtgraph.opengl as gl
        sensor = self.sensor()
        tp = self.temporalProfile()
        if not isinstance(sensor, SensorInstrument) or not isinstance(tp, TemporalProfile):
            return None

        dataPos = []
        x0 = x1 = y0 = y1 = z0 = z1 = 0
        for iDate, tsd in enumerate(tp.mTimeSeries):
            data = tp.data(tsd)
            bandKeys = sorted([k for k in data.keys() if k.startswith('b') and data[k] != None],
                              key=lambda k: bandKey2bandIndex(k))
            if len(bandKeys) == 0:
                continue

            t = date2num(tsd.date)

            x = []
            y = []
            z = []

            for i, k in enumerate(bandKeys):
                x.append(i)
                y.append(t)
                z.append(data[k])
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
        for iPos, pos in enumerate(dataPos):
            x, y, z = pos
            arr = np.asarray((x, y, z), dtype=np.float64).transpose()

            #for i, m in enumerate(xyz):
            #    m0, m1 = m
            #    arr[:, i] = (arr[:, i] - m0) / (m1 - m0)

            if self.mItemType == 'GLLinePlotItem':
                plt = gl.GLLinePlotItem(pos=arr, **self.mGLItemKWDS)

            else:
                raise NotImplementedError(self.mItemType)

            return plt


class TemporalProfilePlotStyle3DWidget(QWidget, loadUI('plotstyle3Dwidget.ui')):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, title='<#>', parent=None):
        super(TemporalProfilePlotStyle3DWidget, self).__init__(parent)
        self.setupUi(self)
        if OPENGL_AVAILABLE:
            from pyqtgraph.opengl import GLViewWidget
            #todo assert isinstance(self.plotWidget, GLViewWidget)

        self.mBlockUpdates = False

        self.cbGLItemType.setModel(TemporalProfile3DPlotStyle.ITEM_TYPES)

        #connect signals

        #color buttons
        self.btnGLLinePlotItemColor.colorChanged.connect(self.refreshPreview)
        self.btnGLScatterPlotItemColor.colorChanged.connect(self.refreshPreview)

        #checkboxes
        self.cbGLItemType.currentIndexChanged.connect(self.refreshPreview)
        self.cbGLLinePlotItemMode.currentIndexChanged.connect(self.refreshPreview)

        #spin boxes
        self.sbGLLinePlotItemWidth.valueChanged.connect(self.refreshPreview)
        self.sbGLScatterPlotItemSize.valueChanged.connect(self.refreshPreview)

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
        from timeseriesviewer.models import setCurrentComboBoxValue

        itemType = style.mItemType
        model = self.cbGLItemType.model()
        assert isinstance(model, OptionListModel)
        setCurrentComboBoxValue(self.cbGLItemType, itemType)

        kwds = style.glItemKwds()

        def d(k, default):
            return kwds[k] if k in kwds.keys() else default

        self.cbAntialias.setChecked(d('antialias', True))
        DEF_COLOR = QColor('green')
        if itemType == 'GLLinePlotItem':

            self.btnGLLinePlotItemColor.setColor(d('color', DEF_COLOR))
            self.sbGLLinePlotItemWidth.setValue(d('width', 2.0))
            setCurrentComboBoxValue(self.cbGLLinePlotItemMode, d('mode', 'lines'))

        elif itemType == 'GLScatterPlotItem':
            self.btnGLScatterPlotItemColor.setColor(d('color', DEF_COLOR))
            self.sbGLScatterPlotItemSize.setValue(d('size', 2.0))
            setCurrentComboBoxValue(self.cbGLScatterPlotItemPxMode, d('pxMode', True))
        elif itemType == 'GLMeshItem':
            self.btnGLMeshItemColor.setColor(d('color', DEF_COLOR))
            self.btnGLMeshItemEdgeColor.setColor(d('edgeColor', DEF_COLOR))
            self.cbGLMeshItemDrawEdges.setChecked(d('drawEdges', False))
            self.cbGLMeshItemDrawFaces.setChecked(d('drawFaces', True))
            self.cbGLMeshItemSmooth.setChecked(d('smooth', True))
            self.cbGLMeshItemNormals.setChecked('normals', True)
        else:

            raise NotImplementedError()

        self.refreshPreview()


    def plotStyleIcon(self):
        icon = QIcon()
        #todo: get plot preview as 60x60 icon
        return icon

    def plotStyle(self):

        itemType = self.cbGLItemType.currentData(role=Qt.UserRole).value()
        style = TemporalProfile3DPlotStyle()
        style.setTemporalProfile(self.mLastPlotStyle.temporalProfile())
        style.setItemType(itemType)
        kwds = {'antialias':self.cbAntialias.isChecked()}

        if itemType == 'GLLinePlotItem':
            kwds['color'] = self.btnGLLinePlotItemColor.color()
            kwds['width'] = self.sbGLLinePlotItemWidth.value()
            kwds['mode'] = self.cbGLLinePlotItemMode.currentData(role=Qt.DisplayRole)
        elif itemType == 'GLScatterPlotItem':
            kwds['color'] = self.btnGLScatterPlotItemColor.color()
            kwds['size'] = self.sbGLScatterPlotItemSize.value()
            kwds['pxMode'] = self.cbGLScatterPlotItemPxMode.currentData(role=Qt.DisplayRole)
        elif itemType == 'GLMeshItem':
            kwds['color'] = self.btnGLMeshItemColor.color()
            kwds['edgeColor'] = self.btnGLMeshItemEdgeColor.color()
            kwds['drawEdges'] = self.cbGLMeshItemDrawEdges.isChecked()
            kwds['drawFaces'] = self.cbGLMeshItemDrawFaces.isChecked()
            kwds['smooth'] = self.cbGLMeshItemSmooth.isChecked()
            kwds['normals'] = self.cbGLMeshItemNormals.isChecked()
        else:

            raise NotImplementedError()

        style.setGLItemKwds(kwds)
        return style

