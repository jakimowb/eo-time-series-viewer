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
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *

import pyqtgraph.opengl as gl
from pyqtgraph import functions as fn
from OpenGL.GL import *
import OpenGL.GLUT
from pyqtgraph.opengl import *
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem
from pyqtgraph.Vector import Vector

from eotimeseriesviewer.temporalprofiles import *



DT_SELECTION = 200
class AxisGrid3D(GLGraphicsItem):

    def __init__(self, *args, **kwds):
        super(AxisGrid3D, self).__init__(*args, **kwds)
        self.antialias = True
        self.mRangesMin = np.asarray([0,0,0], dtype=np.float64)
        self.mRangesMax = np.asarray([1,1,1], dtype=np.float64)
        self.mSteps = np.asarray([10,10,10], dtype=np.int)
        self.mVisibility = np.ones((3), dtype=np.bool)
        self.mColor = QColor('grey')
        self.mDims = ['xy', 'xz', 'yz']
    def setColor(self, color):
        self.mColor = QColor(color)



    def set(self, dim, v0=None, v1=None, steps=None, visible=None, skipUpdate=False):
        assert isinstance(dim, str)
        dim = dim.lower()
        assert dim in self.mDims
        i = self.mDims.index(dim)
        if v0 is not None:
            self.mRangesMin[i] = v0

        if v1 is not None:
            self.mRangesMax[i] = v1

        if isinstance(steps, int):
            self.mSteps[i] = steps

        if isinstance(visible, bool):
            self.mVisibility[i] = visible

        if not skipUpdate:
            self.update()

    def setXY(self, **kwds):
        self.set('xy', **kwds)

    def setXZ(self, **kwds):
        self.set('xz', **kwds)

    def setYZ(self, **kwds):
        self.set('yz', **kwds)


    def setMinRanges(self, ranges):
        self.mRangesMin[:] = ranges

    def setMaxRanges(self, ranges):
        self.mRangesMax[:] = ranges


    def paint(self):
        self.setupGLState()

        if self.antialias:
            glEnable(GL_LINE_SMOOTH)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        glBegin(GL_LINES)

        #T = self.transform()

        #origin of axis values
        valMin = Vector(*self.mRangesMin)

        #max extent of axis values
        valMax = Vector(*self.mRangesMax)
        valRange = valMax - valMin
        if valRange.x() <= 0:
            valRange.setX(1)
        if valRange.y() <= 0:
            valRange.setY(1)
        if valRange.z() <= 0:
            valRange.setZ(1)
        stepSize = valRange / Vector(self.mSteps)

        valuesX = np.arange(valMin.x(), valMax.x()+1.00001*stepSize.x(), stepSize.x())
        valuesY = np.arange(valMin.y(), valMax.y()+1.00001*stepSize.y(), stepSize.y())
        valuesZ = np.arange(valMin.z(), valMax.z()+1.00001*stepSize.z(), stepSize.z())


        c = fn.glColor(self.mColor)
        glColor4f(*c)


        if self.mVisibility[0]: #show XY
            for x in valuesX:
                glVertex3f(x, valuesY[0], valMin.z())
                glVertex3f(x, valuesY[-1], valMin.z())
            for y in valuesY:
                glVertex3f(valuesX[0],  y, valMin.z())
                glVertex3f(valuesX[-1], y, valMin.z())

        if self.mVisibility[1]:  # show XZ
            for x in valuesX:
                glVertex3f(x, valMin.y(), valuesZ[0])
                glVertex3f(x, valMin.y(), valuesZ[-1])
            for z in valuesZ:
                glVertex3f(valuesX[0], valMin.y(), z)
                glVertex3f(valuesX[-1], valMin.y(), z)

        if self.mVisibility[2]:  # show YZ
            for y in valuesY:
                glVertex3f(valMin.x(), y, valuesZ[0])
                glVertex3f(valMin.x(), y, valuesZ[-1])
            for z in valuesZ:
                glVertex3f(valMin.x(), valuesY[0], z)
                glVertex3f(valMin.x(), valuesY[-1], z)


        glEnd()


class Label3D(GLGraphicsItem):

    def __init__(self, label='', *args, **kwds):
        super(Label3D, self).__init__(*args, **kwds)
        self.mLabel = label
        self.mIsVisible = True

        self.mPos =np.asarray([0,0,0], dtype=np.float)

    def setPos(self, x,y,z):
        self.mPos[0] = x
        self.mPos[1] = y
        self.mPos[2] = z


    def setText(self, text):
        assert isinstance(text, str)
        self.mLabel = text
    def text(self):
        return self.mLabel

    def setVisible(self, b):
        assert isinstance(b, bool)
        self.mIsVisible = b
        self.update()

    def isVisible(self):
        return self.mIsVisible

    def paint(self, *args, **kwds):

        s = ""

        if False:
            self.setupGLState()

            #glBegin(GL_LINES)
            glEnable(GL_LINE_SMOOTH)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

            #glBegin(GL_LINES)

            glPushMatrix()
            x,y,z= self.mPos
            glTranslatef(1,0,0)
            #glScale()
            from OpenGL.GLUT import glutStrokeCharacter,glutStrokeWidth, GLUT_STROKE_ROMAN
            w = 0
            text = self.mLabel.encode('utf-8')
            for c in text:
                w += glutStrokeWidth(GLUT_STROKE_ROMAN, c)
            glRotate(1,0,1,0)
            glScale(0.1,0.1,0.1)
            glTranslatef(-w / 2., -w/5., -w/2.)
            for c in text:
                glutStrokeCharacter(GLUT_STROKE_ROMAN, c)

            glPopMatrix()


            #glEnd()

class ViewWidget3D(GLViewWidget):

    def __init__(self, parent=None):
        super(ViewWidget3D, self).__init__(parent)
        self.mousePos = QPoint(-1, -1)
        self.setBackgroundColor(QColor('black'))
        self.setMouseTracking(True)

        self.mDataMinRanges = np.asarray([0, 0, 0])
        self.mDataMaxRanges = np.asarray([1, 1, 1])
        self.mDataSpan = self.mDataMaxRanges - self.mDataMinRanges

        self.mScale = np.asarray([1.,1.,1.])

        self.mDataN = 0

        self.glAxes = Axis3D()
        from pyqtgraph.Transform3D import Transform3D
        self.mItemTransformation = Transform3D()
        #self.glGridItemXY = AxisGrid3D()
        #self.glGridItemXZ = AxisGrid3D()
        #self.glGridItemYZ = AxisGrid3D()
        self.glGridItem = AxisGrid3D()
        #self.glGridItemXZ.setVisible(False)
        #self.glGridItemYZ.setVisible(False)

        x, y, z = self.glAxes.size()

        #self.glGridItemYZ.rotate(-90, 0, 1, 0)
        #self.glGridItemXZ.rotate( 90, 1, 0, 0)

        # self.glGridItemXY.scale(x/10,y/10, 1)
        # self.glGridItemXZ.scale(x/10,z/10, 1)
        # self.glGridItemYZ.scale(y/10,z/10, 1)

        #self.mBasicItems = [self.glGridItemXY, self.glGridItemXZ, self.glGridItemYZ, self.glAxes]
        self.mBasicItems = [self.glAxes, self.glGridItem]
        for item in self.mBasicItems:
            if item == self.glAxes:
                item.setDepthValue(-10)
            else:
                item.setDepthValue(0)

            self.addItem(item)  # draw grid/axis after surfaces since they may be translucent


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

    def setCameraPosition(self, pos=None, distance=None, elevation=None, azimuth=None):

        if distance is not None:
            self.opts['distance'] = distance
        if elevation is not None:
            self.opts['elevation'] = elevation
        if azimuth is not None:
            self.opts['azimuth'] = azimuth
        if pos is not None:
            if not isinstance(pos, QVector3D):
                pos = Vector(pos)
            self.opts['center'] = pos

    def resetCamera(self):

        # self.mDataMinRanges
        self.updateDataRanges()
        self.resetScaling()
        x,y,z = self.mDataMaxRanges
        self.setCameraPosition([1.,0.5,0.5], distance=10, elevation=10, azimuth=10)
        self.update()



    def clearItems(self):
        to_remove = [i for i in self.items if i not in self.mBasicItems]

        for i in to_remove:
            self.items.remove(i)
            i._setView(None)
        self.update()


    def paintGL(self, *args, **kwds):
        GLViewWidget.paintGL(self, *args, **kwds)
        self.qglColor(Qt.white)
        self.renderAnnotations()

    def zoomToFull(self):
        x = y = z = 0
        for item in self.items:
            if item not in self.mBasicItems:
                pos = item.pos
                #self.setCameraPosition(pos=pos, distance=10)
                break

        s = ""

    def updateDataRanges(self):
        """
        Re-calcuates the data ranges of the added plot items.
        Calls this before re-scaling the transformation matrix.
        """
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
                self.mDataMinRanges = np.asarray([x0, y0, z0])
                self.mDataMaxRanges = np.asarray([x1, y1, z1])
                self.mDataSpan = self.mDataMaxRanges - self.mDataMinRanges
                #avoid division by zero and provide a minimum range of 1/10000
                self.mDataSpan = np.where(self.mDataSpan == 0, np.ones((3), dtype=np.float64)/10000., self.mDataSpan)
                self.mDataMaxRanges = self.mDataMinRanges + self.mDataSpan
                self.mDataN = n

                self.glAxes.setMinRanges(self.mDataMinRanges)
                self.glAxes.setMaxRanges(self.mDataMaxRanges)
                self.glGridItem.setMinRanges(self.mDataMinRanges)
                self.glGridItem.setMaxRanges(self.mDataMaxRanges)


    def resetScaling(self):
        t = pg.Transform3D()
        scale = np.asarray([0.9, 1.0, 0.8]) / np.asarray(self.mDataSpan)  # scale to 0-1
        t.scale(*scale)
        t.translate(*(-1 * np.asarray(self.mDataMinRanges)))  # set axis origin to 0:0:0


        vMin = t*Vector(self.mDataMinRanges)
        vMax = t*Vector(self.mDataMaxRanges)
        #pos = (self.mDataMinRanges+self.mDataMaxRanges)*0.5
        #self.setCameraPosition(pos=Vector(*pos)*t)
        #self.setCameraPosition(pos=t*Vector(*pos))
        #self.setCameraPosition(pos=Vector(*pos))
        self.setItemTransform(t)
        #self.setCameraPosition(pos=Vector(0.5,0.5,0.5))

    def setItemTransform(self, transform):
        assert isinstance(transform, pg.Transform3D)
        self.mItemTransformation = transform
        for item in self.items:
            item.setTransform(transform)
    def itemTransformation(self):
        return self.mItemTransformation

    def addItems(self, items):
        """Adds a list of items to this plot"""
        for item in items:
            assert isinstance(item, GLGraphicsItem)
            if hasattr(item, 'initializeGL'):
                self.makeCurrent()
                try:
                    item.initializeGL()
                except:
                    self.checkOpenGLVersion('Error while adding item %s to GLViewWidget.' % str(item))
            item._setView(self)
        self.items.extend(items)
        self.updateDataRanges()
        self.update()

    def removeItems(self, items):

        for item in items:
            if item in self.items:
                self.items.remove(item)
                item._setView(None)
        self.updateDataRanges()
        self.update()


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
        if event.button() == Qt.RightButton:
            self.select = True

        else:
            self.select = False

        try:
            glColorSelected = fn.glColor(QColor('red'))
            for item in self.itemsAt((self.mousePos.x(), self.mousePos.y(), 3, 3)):



                if isinstance(item, GLLinePlotItem):
                    c = item.color
                    item.setData(color=glColorSelected)
                    QTimer.singleShot(DT_SELECTION, lambda item=item, c=c: item.setData(color=c))

        except:
            pass


    def renderAnnotations(self):

        if self.glAxes.visible():
            x0, y0, z0 = self.glAxes.rangeMinima()
            x1, y1, z1 = self.glAxes.rangeMaxima()
            dx, dy, dz = self.glAxes.rangeSpan()


            T = self.glAxes.transform()

            #transform
            d = 0.1

            V0 = T * Vector(*self.glAxes.rangeMinima())
            V1 = T * Vector(*self.glAxes.rangeMaxima())

            dx = V1.x() - V0.x()
            dy = V1.y() - V0.y()
            dz = V1.z() - V0.z()

            sx = V1.x() + 0.1*dx
            sy = V1.y() + 0.1*dy
            sz = V1.z() + 0.1*dz
            if x1 is not None:
                #self.renderText(x1 + d*dx, 0, 0, self.glAxes.mLabels[0])
                self.renderText(sx, 0, 0, self.glAxes.mLabels[0])
            if y1 is not None:
                #self.renderText(0, y1 + d*dy, 0, self.glAxes.mLabels[1])
                self.renderText(0, sy, 0, self.glAxes.mLabels[1])
            if z1 is not None:
                #self.renderText(0, 0, z1 + d*dz, self.glAxes.mLabels[2])
                self.renderText(0, 0, sz, self.glAxes.mLabels[2])

            if True: #set axes origin
                l = '{} {} {}'.format(x0,y0,z0)
                self.renderText(V0.x()-0.1*dx,V0.y()-0.1*dy, V0.z()-0.1*dz, l)


        # self.renderText(0.8, 0.8, 0.8, 'text 3D')
        # self.renderText(5, 10, 'text 2D fixed')

        self.qglColor(Qt.darkYellow)
        self.renderText(5, 10, '(3D Mode still experimental)')

    def contextMenuEvent(self, event):
        assert isinstance(event, QContextMenuEvent)

        menu = QMenu()

        a = menu.addAction('Reset Camera')
        a.triggered.connect(self.resetCamera)

        menu.addSeparator()

        # define grid options
        m = menu.addMenu('Grids')

        def gridVisibility(b):
            for d in ['XY','XZ','YZ']:
                self.glGridItem.set(d, visible=b)
            self.glGridItem.update()



        a = m.addAction('Show All')
        a.setCheckable(False)
        a.triggered.connect(lambda: gridVisibility(True))

        a = m.addAction('Hide All')
        a.setCheckable(False)
        a.triggered.connect(lambda: gridVisibility(False))

        m.addSeparator()

        for i, dim in enumerate(['XY','XZ','YZ']):
            a = m.addAction(dim)
            a.setCheckable(True)
            a.setChecked(self.glGridItem.mVisibility[i])
            a.toggled.connect(lambda b, dim=dim:self.glGridItem.set(dim,visible=b))



        m = menu.addMenu('Axes')

        a = m.addAction('Show All')
        a.setCheckable(False)
        a.triggered.connect(lambda : self.glAxes.setAxes('xyz', visible=True))

        a = m.addAction('Hide All')
        a.setCheckable(False)
        a.triggered.connect(lambda: self.glAxes.setAxes('xyz', visible=False))

        m.addSeparator()

        a = m.addAction('X')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[0])
        a.toggled.connect(lambda b: self.glAxes.setX(visible=b))

        a = m.addAction('Y')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[1])
        a.toggled.connect(lambda b: self.glAxes.setY(visible=b))

        a = m.addAction('Z')
        a.setCheckable(True)
        a.setChecked(self.glAxes.mVisibility[2])
        a.toggled.connect(lambda b: self.glAxes.setZ(visible=b))


        menuLabels = menu.addMenu('Labels')

        frame = QFrame()
        layout = QGridLayout()
        frame.setLayout(layout)

        names = ['X','Y','Z']
        for i, label in enumerate(self.glAxes.labels()):
            dim = names[i]
            layout.addWidget(QLabel(dim), i,0)
            tb = QLineEdit()
            tb.setText(label)
            tb.textChanged.connect(lambda t, dim=dim : self.glAxes.setAxes(dim, label=t))
            layout.addWidget(tb,i,1)
        layout.setSpacing(1)
        layout.setMargin(1)
        frame.setMinimumSize(layout.sizeHint())
        wa = QWidgetAction(menuLabels)
        wa.setDefaultWidget(frame)
        menuLabels.addAction(wa)


        menu.exec_(self.mapToGlobal(event.pos()))

class GLTextItem(GLGraphicsItem):
    def __init__(self, X=None, Y=None, Z=None, text=None):
        GLGraphicsItem.__init__(self)

        self.text = text
        self.X = X
        self.Y = Y
        self.Z = Z

    def setGLViewWidget(self, GLViewWidget):
        self.GLViewWidget = GLViewWidget

    def setText(self, text):
        self.text = text
        self.update()

    def setX(self, X):
        self.X = X
        self.update()

    def setY(self, Y):
        self.Y = Y
        self.update()

    def setZ(self, Z):
        self.Z = Z
        self.update()

    def paint(self):
        self.GLViewWidget.qglColor(Qt.white)
        self.GLViewWidget.renderText(self.X, self.Y, self.Z, self.text)

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

    def setMinRanges(self, ranges):
        self.mRanges[:,0] = ranges

    def setMaxRanges(self, ranges):
        self.mRanges[:,1] = ranges


    def rangeSpan(self):

        return self.mRanges[:,1] - self.mRanges[:,0]


    def setAxes(self, ax, vMin=None, vMax=None, label=None, color=None, visible=None):

        for c in ax:
            i = ['x', 'y', 'z'].index(c.lower())
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
        self.update()

    def setLabels(self, x,y,z):
        self.mLabels = [x,y,z]

    def labels(self):
        return self.mLabels[:]

    def setX(self, **kwds):
        self.setAxes('x', **kwds)

    def setY(self, **kwds):
        self.setAxes('y', **kwds)

    def setZ(self, **kwds):
        self.setAxes('z', **kwds)

    def paint(self):
        self.setupGLState()

        if self.antialias:
            glEnable(GL_LINE_SMOOTH)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        x0, y0, z0 = self.rangeMinima()
        x1, y1, z1 = self.rangeMaxima()


        #V0 = Vector(*self.rangeMinima())
        #V1 = Vector(*self.rangeMaxima())
        #T = self.transform()
        #V0 = V0*T
        #V1 = V1*T
        #x0,y0,z0 = V0.x(), V0.y(), V0.z()
        #x1, y1, z1 = V1.x(), V1.y(), V1.z()

        glLineWidth(3.0)
        glBegin(GL_LINES)

        if self.mVisibility[0]:
            glColor4f(*fn.glColor(self.mColors[0]))
            glVertex3f(x0, y0, z0)
            glVertex3f(x1, y0, z0)

        if self.mVisibility[1]:
            glColor4f(*fn.glColor(self.mColors[1]))
            glVertex3f(x0, y0, z0)
            glVertex3f(x0, y1, z0)

        if self.mVisibility[2]:
            glColor4f(*fn.glColor(self.mColors[2]))
            glVertex3f(x0, y0, z0)
            glVertex3f(x0, y0, z1)

        glEnd()
        glLineWidth(1.0)

