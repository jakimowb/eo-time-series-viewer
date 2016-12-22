# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'imagechipviewsettings_widget_base.ui'
#
# Created: Mon Oct 26 16:10:40 2015
#      by: PyQt4 UI code generator 4.10.2
#
# WARNING! All changes made in this file will be lost!

'''
/***************************************************************************
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 ***************************************************************************/
'''

import os
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import sys, re, os, six

from timeseriesviewer import jp
from timeseriesviewer.ui import loadUIFormClass, DIR_UI

PATH_MAIN_UI = jp(DIR_UI, 'timseriesviewer.ui')
PATH_BANDVIEWSETTINGS_UI = jp(DIR_UI, 'bandviewsettings.ui')
PATH_IMAGECHIPVIEWSETTINGS_UI = jp(DIR_UI, 'imagechipviewsettings.ui')
PATH_BANDVIEW_UI = jp(DIR_UI, 'bandview.ui')
PATH_TSDVIEW_UI = jp(DIR_UI, 'timeseriesdatumview.ui')

class TimeSeriesViewerUI(QMainWindow,
                         loadUIFormClass(PATH_MAIN_UI)):

    def __init__(self, parent=None):
        """Constructor."""
        super(TimeSeriesViewerUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.mCrs = None

        #set button default actions -> this will show the action icons as well
        #I don't know why this is not possible in the QDesigner when QToolButtons are
        #placed outside a toolbar
        self.btnSelectArea.setDefaultAction(self.actionSelectArea)
        self.btnSelectCenterCoordinate.setDefaultAction(self.actionSelectCenter)

        self.btnNavToFirstTSD.setDefaultAction(self.actionFirstTSD)
        self.btnNavToLastTSD.setDefaultAction(self.actionLastTSD)
        self.btnNavToPreviousTSD.setDefaultAction(self.actionPreviousTSD)
        self.btnNavToNextTSD.setDefaultAction(self.actionNextTSD)

        self.btnAddTSD.setDefaultAction(self.actionAddTSD)
        self.btnRemoveTSD.setDefaultAction(self.actionRemoveTSD)
        self.btnLoadTS.setDefaultAction(self.actionLoadTS)
        self.btnSaveTS.setDefaultAction(self.actionSaveTS)
        self.btnClearTS.setDefaultAction(self.actionClearTS)

        #define subset-size behaviour
        self.spinBoxSubsetSizeX.valueChanged.connect(lambda: self.onSubsetValueChanged('X'))
        self.spinBoxSubsetSizeY.valueChanged.connect(lambda: self.onSubsetValueChanged('Y'))
        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()


    def crs(self):
        return self.mCrs
        pass

    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        old = self.mCrs
        self.mCrs = crs
        self.textBoxCRSInfo.setText(crs.toWkt())
        if self.mCrs != old:
            self.sigCrsChanged.emit(crs)


    def extent(self):
        width = QgsVector(self.spinBoxExtentWidth.value(), 0.0)
        height = QgsVector(0.0, self.spinBoxExtentHeight.value())

        Center = QgsPoint(self.spinBoxExtentCenterX.value(), self.spinBoxExtentCenterY.value())
        UL = Center - (width * 0.5) + (height * 0.5)
        LR = Center + (width * 0.5) - (height * 0.5)
        return QgsRectangle(UL, LR)

    sigExtentChanged = pyqtSignal(QgsRectangle)
    def setExtent(self, extent):
        old = self.extent()
        assert isinstance(extent, QgsRectangle)
        center = extent.center()
        self.spinBoxExtentCenterX.setValue(center.x())
        self.spinBoxExtentCenterY.setValue(center.y())
        self.spinBoxExtentWidth.setValue(extent.width())
        self.spinBoxExtentHeight.setValue(extent.height())

        if old != extent:
            self.sigExtentChanged.emit(extent)

    sigSubsetSizeChanged = pyqtSignal(QSize)

    def setSubsetSize(self, size):
        old = self.subsetSize()
        self.spinBoxSubsetSizeX.setValue(size.width())
        self.spinBoxSubsetSizeY.setValue(size.height())

        if old != size:
            self.sigSubsetSizeChanged(size)

    def subsetSize(self):
        return QSize(self.spinBoxSubsetSizeX.value(),
                     self.spinBoxSubsetSizeY.value())


    def setProgress(self, value, valueMax=None, valueMin=0):
        p = self.progressBar
        if valueMin is not None and valueMin != self.progessBar.minimum():
            p.setMinimum(valueMin)
        if valueMax is not None and valueMax != self.progessBar.maximum():
            p.setMaximum(valueMax)
        self.progressBar.setValue(value)


    def onSubsetValueChanged(self, key):
        if self.checkBoxLockSubsetAspect.isChecked():

            if key == 'X':
                v_old = self.lastSubsetSizeX
                v_new = self.spinBoxSubsetSizeX.value()
                s = self.spinBoxSubsetSizeY
            elif key == 'Y':
                v_old = self.lastSubsetSizeY
                v_new = self.spinBoxSubsetSizeY.value()
                s = self.spinBoxSubsetSizeX

            oldState = s.blockSignals(True)
            s.setValue(int(round(float(v_new) / v_old * s.value())))
            s.blockSignals(oldState)

        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()

        self.actionSetSubsetSize.activate(QAction.Trigger)

class VerticalLabel(QLabel):
    def __init__(self, text, orientation='vertical', forceWidth=True):
        QLabel.__init__(self, text)
        self.forceWidth = forceWidth
        self.orientation = None
        self.setOrientation(orientation)

    def setOrientation(self, o):
        if self.orientation == o:
            return
        self.orientation = o
        self.update()
        self.updateGeometry()

    def paintEvent(self, ev):
        p = QPainter(self)
        # p.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 200)))
        # p.setPen(QtGui.QPen(QtGui.QColor(50, 50, 100)))
        # p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))

        if self.orientation == 'vertical':
            p.rotate(-90)
            rgn = QRect(-self.height(), 0, self.height(), self.width())
        else:
            rgn = self.contentsRect()
        align = self.alignment()
        # align  = QtCore.Qt.AlignTop|QtCore.Qt.AlignHCenter

        self.hint = p.drawText(rgn, align, self.text())
        p.end()

        if self.orientation == 'vertical':
            self.setMaximumWidth(self.hint.height())
            self.setMinimumWidth(0)
            self.setMaximumHeight(16777215)
            if self.forceWidth:
                self.setMinimumHeight(self.hint.width())
            else:
                self.setMinimumHeight(0)
        else:
            self.setMaximumHeight(self.hint.height())
            self.setMinimumHeight(0)
            self.setMaximumWidth(16777215)
            if self.forceWidth:
                self.setMinimumWidth(self.hint.width())
            else:
                self.setMinimumWidth(0)

    def sizeHint(self):
        if self.orientation == 'vertical':
            if hasattr(self, 'hint'):
                return QSize(self.hint.height(), self.hint.width())
            else:
                return QSize(19, 50)
        else:
            if hasattr(self, 'hint'):
                return QSize(self.hint.width(), self.hint.height())
            else:
                return QSize(50, 19)

class BandViewUI(QFrame, loadUIFormClass(PATH_BANDVIEW_UI)):

    def __init__(self, title='View',parent=None):
        super(BandViewUI, self).__init__(parent)

        self.setupUi(self)
        self.btnRemoveBandView.setDefaultAction(self.actionRemoveBandView)
        self.btnAddBandView.setDefaultAction(self.actionAddBandView)


class TimeSeriesDatumViewUI(QFrame, loadUIFormClass(PATH_TSDVIEW_UI)):
    def __init__(self, title='<#>', parent=None):
        super(TimeSeriesDatumViewUI, self).__init__(parent)

        self.emptyHeight = self.height()
        self.setupUi(self)

    def sizeHint(self):

        w = self.minimumWidth()
        canvases = self.findChildren(BandViewMapCanvas)
        h = self.emptyHeight + len(canvases) * w
        return QSize(w,h)

class LineWidget(QFrame):

    def __init__(self, parent=None, orientation='horizontal'):
        super(LineWidget, self).__init__(parent)

        self.setFrameShadow(QFrame.Sunken)
        self.setFixedHeight(3)
        self.setStyleSheet("background-color: #c0c0c0;")
        self.orientation = orientation
        if self.orientation == 'horizontal':
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

class ImageChipViewSettingsUI(QGroupBox,
                             loadUIFormClass(PATH_IMAGECHIPVIEWSETTINGS_UI)):

    def __init__(self, parent=None):
        """Constructor."""
        super(ImageChipViewSettingsUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect

        self.setupUi(self)

        self.btnDefault.setDefaultAction(self.actionSetDefault)
        self.btnTrueColor.setDefaultAction(self.actionSetTrueColor)
        self.btnCIR.setDefaultAction(self.actionSetCIR)
        self.btn453.setDefaultAction(self.actionSet453)


class BandViewMapCanvas(QgsMapCanvas):

    def __init__(self, parent=None):
        super(BandViewMapCanvas, self).__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lyr = None
        self.renderer = None
        self.registry = QgsMapLayerRegistry.instance()

    def setLayer(self, uri):
        assert isinstance(uri, str)

        self.setLayerSet([])
        if self.lyr is not None:
            #de-register layer
            self.registry.removeMapLayer(self.lyr)

        self.lyr = QgsRasterLayer(uri)
        self.lyr.setRenderer(self.renderer)
        self.registry.addMapLayer(self.lyr, False)

        lset = [QgsMapCanvasLayer(self.lyr)]
        self.setLayerSet(lset)

    def setRenderer(self, renderer):
        s = ""
        self.renderer = renderer.clone()




class ImageChipViewSettings(QObject):

    #define signals


    sigRendererChanged = pyqtSignal(QgsRasterRenderer)
    sigRemoveView = pyqtSignal()

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(ImageChipViewSettings, self).__init__(parent)

        self.ui = ImageChipViewSettingsUI(parent)
        self.ui.create()


        self.ui.setTitle(sensor.sensorName)
        self.ui.bandNames = sensor.bandNames
        self.minValues = [self.ui.tbRedMin, self.ui.tbGreenMin, self.ui.tbBlueMin]
        self.maxValues = [self.ui.tbRedMax, self.ui.tbGreenMax, self.ui.tbBlueMax]
        self.sliders = [self.ui.sliderRed, self.ui.sliderGreen, self.ui.sliderBlue]

        for tb in self.minValues + self.maxValues:
            tb.setValidator(QDoubleValidator())
        for sl in self.sliders:
            sl.setMinimum(1)
            sl.setMaximum(sensor.nb)
            sl.valueChanged.connect(self.layerRendererChanged)

        self.ceAlgs = [("No enhancement", QgsContrastEnhancement.NoEnhancement),
                       ("Stretch to MinMax", QgsContrastEnhancement.StretchToMinimumMaximum),
                       ("Stretch and clip to MinMax",QgsContrastEnhancement.StretchAndClipToMinimumMaximum),
                       ("Clip to MinMax", QgsContrastEnhancement.ClipToMinimumMaximum)]
        for item in self.ceAlgs:
            self.ui.comboBoxContrastEnhancement.addItem(item[0], item[1])


        from timeseriesviewer.timeseries import SensorInstrument
        assert isinstance(sensor, SensorInstrument)
        self.sensor = sensor

        lyr = QgsRasterLayer(self.sensor.refUri)
        renderer = lyr.renderer()
        self.setLayerRenderer(renderer)

        #provide default min max
        self.defaultRGB = [renderer.redBand(), renderer.greenBand(), renderer.blueBand()]
        self.ui.actionSetDefault.triggered.connect(lambda : self.setBandSelection('default'))
        self.ui.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('TrueColor'))
        self.ui.actionSetCIR.triggered.connect(lambda: self.setBandSelection('CIR'))
        self.ui.actionSet453.triggered.connect(lambda: self.setBandSelection('453'))

        if not self.sensor.wavelengthsDefined():
            self.ui.btnTrueColor.setEnabled(False)
            self.ui.btnCIR.setEnabled(False)
            self.ui.btn453.setEnabled(False)
        s = ""

    def showSensorName(self, b):
        if b:
            self.ui.setTitle(self.sensor.sensorName)
        else:
            self.ui.setTitle(None)

    def setBandSelection(self, key):

        if key == 'default':
            bands = self.defaultRGB
        else:
            if key == 'TrueColor':
                colors = ['R','G','B']
            elif key == 'CIR':
                colors = ['nIR', 'R', 'G']
            elif key == '453':
                colors = ['nIR','swIR', 'R']
            bands = [self.sensor.bandClosestToWavelength(c) for c in colors]

        for i, b in enumerate(bands):
            self.sliders[i].setValue(b)
            #slider value change emits signal -> no emit required here

    def rgb(self):
        return [self.ui.sliderRed.value(),
               self.ui.sliderGreen.value(),
               self.ui.sliderBlue.value()]

    def setRenderInfo(self, *args):
        rgb = self.rgb()

        text = 'RGB {}-{}-{}'.format(*rgb)
        if self.sensor.wavelengthsDefined():
            text += ' ({} {})'.format(
                ','.join(['{:0.2f}'.format(self.sensor.wavelengths[b-1]) for b in rgb]),
                self.sensor.wavelengthUnits)
        self.ui.labelBands.setText(text)

    def setLayerRenderer(self, renderer):
        ui = self.ui
        assert isinstance(renderer, QgsRasterRenderer)

        if isinstance(renderer, QgsMultiBandColorRenderer):
            ui.sliderRed.setValue(renderer.redBand())
            ui.sliderGreen.setValue(renderer.greenBand())
            ui.sliderBlue.setValue(renderer.blueBand())

            ceRed = renderer.redContrastEnhancement()
            ceGreen = renderer.greenContrastEnhancement()
            ceBlue = renderer.blueContrastEnhancement()

            algs = [i[1] for i in self.ceAlgs]
            ui.comboBoxContrastEnhancement.setCurrentIndex(algs.index(ceRed.contrastEnhancementAlgorithm()))
            self.layerRendererChanged()

    def layerRendererChanged(self):
        self.setRenderInfo()
        self.sigRendererChanged.emit(self.layerRenderer())

    def layerRenderer(self):
        ui = self.ui
        r = QgsMultiBandColorRenderer(None,
            ui.sliderRed.value(), ui.sliderGreen.value(), ui.sliderBlue.value())

        i = self.ui.comboBoxContrastEnhancement.currentIndex()
        alg = self.ui.comboBoxContrastEnhancement.itemData(i)

        if alg == QgsContrastEnhancement.NoEnhancement:
            r.setRedContrastEnhancement(None)
            r.setGreenContrastEnhancement(None)
            r.setBlueContrastEnhancement(None)
        else:
            rgbEnhancements = []
            for i in range(3):
                e = QgsContrastEnhancement(self.sensor.bandDataType)
                e.setMinimumValue(float(self.minValues[i].text()))
                e.setMaximumValue(float(self.maxValues[i].text()))
                e.setContrastEnhancementAlgorithm(alg)
                rgbEnhancements.append(e)
            r.setRedContrastEnhancement(rgbEnhancements[0])
            r.setGreenContrastEnhancement(rgbEnhancements[1])
            r.setBlueContrastEnhancement(rgbEnhancements[2])
        return r


        s = ""

    def contextMenuEvent(self, event):
        menu = QMenu()

        #add general options
        action = menu.addAction('Remove Band View')
        action.setToolTip('Removes this band view')
        action.triggered.connect(lambda : self.sigRemoveView.emit())
        #add QGIS specific options
        txt = QApplication.clipboard().text()
        if re.search('<!DOCTYPE(.|\n)*rasterrenderer.*type="multibandcolor"', txt) is not None:
            import qgis_add_ins
            action = menu.addAction('Paste style')
            action.setToolTip('Uses the QGIS raster layer style to specify band selection and band value ranges.')
            action.triggered.connect(lambda : self.setLayerRenderer(qgis_add_ins.paste_band_settings(txt)))


        menu.exec_(event.globalPos())


