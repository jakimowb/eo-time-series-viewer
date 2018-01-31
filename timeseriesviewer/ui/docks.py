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
from qgis.core import *
from qgis.gui import QgsDockWidget
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.utils import loadUi, SpatialExtent

class TsvDockWidgetBase(QgsDockWidget):

    def __init__(self, parent):
        super(TsvDockWidgetBase, self).__init__(parent)
        self.setupUi(self)

    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states



class RenderingDockUI(TsvDockWidgetBase, loadUi('renderingdock.ui')):
    from timeseriesviewer.crosshair import CrosshairStyle

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigQgisInteractionRequest = pyqtSignal(str)

    def __init__(self, parent=None):
        super(RenderingDockUI, self).__init__(parent)
        self.setupUi(self)
        self.progress = dict()
        self.spinBoxMapSizeX.valueChanged.connect(lambda : self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda : self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()
        self.mSubsetRatio = None
        self.mResizeStop = False
        self.btnApplySizeChanges.setEnabled(False)
        self.btnApplySizeChanges.clicked.connect(lambda: self.onMapSizeChanged(None))
        self.btnMapCanvasColor.colorChanged.connect(self.sigMapCanvasColorChanged)
        self.btnCrs.crsChanged.connect(self.sigCrsChanged)

        self.progressBar.setVisible(False)
        self.enableQgisInteraction(False)

        self.btnSetQGISCenter.clicked.connect(lambda : self.sigQgisInteractionRequest.emit('tsvCenter2qgsCenter'))
        self.btnSetQGISExtent.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('tsvExtent2qgsExtent'))
        self.btnGetQGISCenter.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('qgisCenter2tsvCenter'))
        self.btnGetQGISExtent.clicked.connect(lambda: self.sigQgisInteractionRequest.emit('qgisExtent2tsvExtent'))

    sigShowVectorOverlay = pyqtSignal(QgsVectorLayer)
    sigRemoveVectorOverlay = pyqtSignal()
    def onVectorOverlayerChanged(self, *args):

        b = self.gbQgsVectorLayer.isChecked()
        lyr = self.cbQgsVectorLayer.currentLayer()
        if b and isinstance(lyr, QgsVectorLayer):
            self.sigShowVectorOverlay.emit(lyr)
        else:
            self.sigRemoveVectorOverlay.emit()
        s = ""

    def enableQgisInteraction(self, b):

        self.gbSyncQgs.setEnabled(b)
        if b:
            self.gbSyncQgs.setTitle('QGIS')
        else:
            self.gbSyncQgs.setTitle('QGIS (not available)')




    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.btnCrs.setCrs(crs)
        self.btnCrs.setLayerCrs(crs)
        #self.sigCrsChanged.emit(self.crs())

    def crs(self):
        return self.btnCrs.crs()

    def spatialExtent(self):
        crs = self.crs()
        if not crs:
            return None
        width = QgsVector(self.spinBoxExtentWidth.value(), 0.0)
        height = QgsVector(0.0, self.spinBoxExtentHeight.value())

        Center = QgsPoint(self.spinBoxExtentCenterX.value(), self.spinBoxExtentCenterY.value())
        UL = Center - (width * 0.5) + (height * 0.5)
        LR = Center + (width * 0.5) - (height * 0.5)

        from timeseriesviewer.main import SpatialExtent
        return SpatialExtent(self.crs(), UL, LR)

    def setSpatialExtent(self, extent):
        old = self.spatialExtent()
        assert isinstance(extent, SpatialExtent)
        center = extent.center()



        states = self._blockSignals(self.spatialExtentWidgets, True)

        self.spinBoxExtentCenterX.setValue(center.x())
        self.spinBoxExtentCenterY.setValue(center.y())
        self.spinBoxExtentWidth.setValue(extent.width())
        self.spinBoxExtentHeight.setValue(extent.height())
        self.setCrs(extent.crs())
        self._blockSignals(states)

        if extent != old:
            self.sigSetSpatialExtent.emit(extent)

    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states


    def setMapSize(self, size, blockWidgetSignals = True):
        assert isinstance(size, QSize)
        w = [self.spinBoxMapSizeX, self.spinBoxMapSizeY]

        if blockWidgetSignals:
            self._blockSignals(w, True)

        self.spinBoxMapSizeX.setValue(size.width()),
        self.spinBoxMapSizeY.setValue(size.height())
        self.mLastMapSize = QSize(size)
        if blockWidgetSignals:
            self._blockSignals(w, False)

    def mapSize(self):
        return QSize(self.spinBoxMapSizeX.value(),
                     self.spinBoxMapSizeY.value())

    def onMapSizeChanged(self, dim):
        newSize = self.mapSize()
        #1. set size of other dimension accordingly
        if dim is not None:
            if self.checkBoxKeepSubsetAspectRatio.isChecked():
                if dim == 'X':
                    vOld = self.mLastMapSize.width()
                    vNew = newSize.width()
                    targetSpinBox = self.spinBoxMapSizeY
                elif dim == 'Y':
                    vOld = self.mLastMapSize.height()
                    vNew = newSize.height()
                    targetSpinBox = self.spinBoxMapSizeX

                oldState = targetSpinBox.blockSignals(True)
                targetSpinBox.setValue(int(round(float(vNew) / vOld * targetSpinBox.value())))
                targetSpinBox.blockSignals(oldState)
                newSize = self.mapSize()
            if newSize != self.mLastMapSize:
                self.btnApplySizeChanges.setEnabled(True)
        else:
            self.sigMapSizeChanged.emit(self.mapSize())
            self.btnApplySizeChanges.setEnabled(False)
        self.setMapSize(newSize, True)

    def addStartedWork(self, *args):
        self.progress[args] = False
        self.refreshProgressBar()


    def refreshProgressBar(self):
        self.progressBar.setMaximum(len(self.progress.keys()))
        p = len([v for v in self.progress.values() if v == True])
        self.progressBar.setValue(p)


    def addFinishedWork(self, *args):
        if args in self.progress.keys():
            self.progress[args] = True

        else:
            s = ""
        self.refreshProgressBar()




if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()
    d = RenderingDockUI()
    d.show()
    p = sandbox.SignalPrinter(d)

    qgsApp.exec_()
    qgsApp.exitQgis()
