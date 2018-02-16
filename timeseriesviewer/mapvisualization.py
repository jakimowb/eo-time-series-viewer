# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import, unicode_literals
import os, sys, re, fnmatch, collections, copy, traceback, six, bisect
import logging
logger = logging.getLogger(__name__)
from qgis.core import *
from PyQt4.QtXml import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer.utils import *

from timeseriesviewer.timeseries import SensorInstrument, TimeSeriesDatum, TimeSeries
from timeseriesviewer.ui.docks import TsvDockWidgetBase, loadUI
from timeseriesviewer.main import TsvMimeDataUtils
from timeseriesviewer.ui.mapviewscrollarea import MapViewScrollArea
from timeseriesviewer.mapcanvas import MapCanvas
from timeseriesviewer.crosshair import CrosshairStyle


class MapViewUI(QFrame, loadUI('mapviewdefinition.ui')):


    def __init__(self, parent=None):
        super(MapViewUI, self).__init__(parent)
        self.setupUi(self)
        self.mSensors = collections.OrderedDict()

        m = QMenu(self.btnToggleCrosshair)
        m.addAction(self.actionSetCrosshairStyle)
        #a = m.addAction('Set Crosshair Style')

        self.btnToggleCrosshair.setMenu(m)

        #connect the QActions with the QgsCollapsibleGroupBoxes
        self.gbVectorRendering.toggled.connect(self.actionToggleVectorVisibility.toggle)
        self.gbRasterRendering.toggled.connect(self.actionToggleRasterVisibility.toggle)

        self.actionToggleVectorVisibility.toggled.connect(self.gbVectorRendering.setChecked)
        self.actionToggleRasterVisibility.toggled.connect(self.gbRasterRendering.setChecked)
        #self.actionToggleRasterVisibility.toggled.connect(self.dummy)

        self.btnToggleCrosshair.setDefaultAction(self.actionToggleCrosshairVisibility)
        self.btnToggleMapViewVisibility.setDefaultAction(self.actionToggleMapViewVisibility)

    def dummy(self, *args):
        print((self.sender(), args))
        print(args)

    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)

        w = MapViewSensorSettings(sensor)
        #sizePolicy = QSizePolicy(QSize)
        #w.ui.
        l = self.renderSettingsLayout
        assert sensor not in self.mSensors.keys()

        lastWidgetIndex = l.count()-1
        l.insertWidget(lastWidgetIndex, w.ui)
        self.mSensors[sensor] = w
        #self.resize(self.sizeHint())

        return w


    def removeSensor(self, sensor):

        assert isinstance(sensor, SensorInstrument)
        sensorSettings = self.mSensors.pop(sensor)
        assert isinstance(sensorSettings, MapViewSensorSettings)

        l = self.renderSettingsLayout
        l.removeWidget(sensorSettings.ui)
        sensorSettings.ui.close()
        #self.resize(self.sizeHint())


class MapView(QObject):

    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibility = pyqtSignal(bool)
    #sigVectorVisibility = pyqtSignal(bool)
    #sigRasterVisibility = pyqtSignal(bool)

    sigTitleChanged = pyqtSignal([str],[unicode])
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)

    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)
    sigShowCrosshair = pyqtSignal(bool)
    sigVectorLayerChanged = pyqtSignal()

    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def __init__(self, mapViewCollection, name='Map View', recommended_bands=None, parent=None):
        super(MapView, self).__init__()
        assert isinstance(mapViewCollection, MapViewCollectionDock)

        self.ui = MapViewUI(mapViewCollection.stackedWidget)
        self.ui.show()
        self.ui.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.ui.cbQgsVectorLayer.layerChanged.connect(self.setVectorLayer)
        self.ui.tbName.textChanged.connect(self.sigTitleChanged)
        from timeseriesviewer.crosshair import getCrosshairStyle
        self.ui.actionSetCrosshairStyle.triggered.connect(
            lambda : self.setCrosshairStyle(getCrosshairStyle(
                parent=self.ui,
                crosshairStyle=self.mCrosshairStyle))
        )

        self.mapViewCollection = mapViewCollection
        self.sensorViews = collections.OrderedDict()

        self.mVectorLayer = None
        self.setVectorLayer(None)

        self.mCrosshairStyle = CrosshairStyle()
        self.mShowCrosshair = True

        self.mIsVisible = True
        self.mVectorsVisible = True
        self.mRastersVisible = True

        self.ui.actionToggleVectorVisibility.setChecked(True)
        self.ui.actionToggleVectorVisibility.toggled.connect(self.setVectorVisibility)

        self.ui.actionToggleRasterVisibility.setChecked(True)
        self.ui.actionToggleRasterVisibility.toggled.connect(self.setRasterVisibility)

        self.ui.actionToggleCrosshairVisibility.toggled.connect(self.setShowCrosshair)
        self.ui.actionToggleMapViewVisibility.toggled.connect(lambda b: self.setIsVisible(not b))



        self.ui.actionToggleVectorVisibility.setChecked(True)
        self.ui.actionToggleRasterVisibility.setChecked(True)

        self.setTitle(name)
        #forward actions with reference to this band view
    def dummy(self, *args):
        print(args)
    def setIsVisible(self, b):
        assert isinstance(b, bool)
        changed = b != self.mIsVisible

        self.mIsVisible = b

        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setVisible(b)
        if changed:
            self.sigMapViewVisibility.emit(b)


    def isVisible(self):
        return self.mIsVisible

    def mapCanvases(self):
        m = []
        for sensor, sensorView in self.sensorViews.items():
            m.extend(sensorView.mapCanvases())
        return m

    def vectorLayerRenderer(self):
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.rendererV2()
        return None

    def setVectorLayerRenderer(self, renderer):
        if isinstance(renderer, QgsFeatureRendererV2) and \
            isinstance(self.mVectorLayer, QgsVectorLayer):
            self.mVectorLayer.setRendererV2(renderer)

    def setVectorLayer(self, lyr):

        if isinstance(lyr, QgsVectorLayer):

            #add vector layer
            self.mVectorLayer = lyr
            self.mVectorLayer.rendererChanged.connect(self.sigVectorLayerChanged)

            for mapCanvas in self.mapCanvases():
                assert isinstance(mapCanvas, MapCanvas)
                mapCanvas.layerModel().setVectorLayerSources([self.mVectorLayer])
                #mapCanvas.setLayers([l for l in mapCanvas.layers() if isinstance(l, QgsRasterLayer)])
                #mapCanvas.setLazyVectorSources([lyr])
                mapCanvas.refresh()

        else:
            #remove vector layers
            self.mVectorLayer = None
            for mapCanvas in self.mapCanvases():
                mapCanvas.layerModel().setVectorLayerSources([])
                #mapCanvas.setLayers([l for l in mapCanvas.mLayers if not isinstance(l, QgsVectorLayer)])
                mapCanvas.refresh()

        self.sigVectorLayerChanged.emit()

    def applyStyles(self):
        for sensorView in self.sensorViews.values():
            sensorView.applyStyle()

    def setTitle(self, title):
        old = self.title()
        if old != title:
            self.ui.tbName.setText(title)

    def title(self):
        return self.ui.tbName.text()

    def refreshMapView(self, *args):
        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.refresh()

    def setCrosshairStyle(self, crosshairStyle):
        if isinstance(crosshairStyle, CrosshairStyle):
            old = self.mCrosshairStyle
            self.mCrosshairStyle = crosshairStyle
            if old != self.mCrosshairStyle:
                self.sigCrosshairStyleChanged.emit(self.mCrosshairStyle)

    def setHighlighted(self, b=True, timeout=1000):
        styleOn = """.MapCanvas {
                    border: 4px solid red;
                    border-radius: 4px;
                }"""
        styleOff = """"""
        if b is True:
            for mapCanvas in self.mapCanvases():
                mapCanvas.setStyleSheet(styleOn)
            if timeout > 0:
                QTimer.singleShot(timeout, lambda : self.setHighlighted(False))
        else:
            for mapCanvas in self.mapCanvases():
                mapCanvas.setStyleSheet(styleOff)


    def setShowCrosshair(self, b):
        assert isinstance(b, bool)
        self.mShowCrosshair = b
        self.sigShowCrosshair.emit(b)

    def showCrosshair(self):
        return self.mShowCrosshair and self.mCrosshairStyle is not None


    def rasterVisibility(self):
        return self.mRastersVisible

    def vectorVisibility(self):
        return self.mVectorsVisible

    def setRasterVisibility(self, b):
        assert isinstance(b, bool)
        if self.rasterVisibility() != b:
            self.mRastersVisible = b
            self.ui.actionToggleRasterVisibility.setChecked(b)

            for mapCanvas in self.mapCanvases():
                assert isinstance(mapCanvas, MapCanvas)
                mapCanvas.layerModel().setRasterLayerVisibility(b)
                mapCanvas.refresh()

            #self.sigRasterVisibility.emit(b)

    def setVectorVisibility(self, b):
        assert isinstance(b, bool)
        if self.vectorVisibility() != b:
            self.mVectorsVisible = b
            self.ui.actionToggleVectorVisibility.setChecked(b)

            for mapCanvas in self.mapCanvases():
                assert isinstance(mapCanvas, MapCanvas)
                mapCanvas.layerModel().setVectorLayerVisibility(b)
                mapCanvas.refresh()

    def removeSensor(self, sensor):
        assert sensor in self.sensorViews.keys()
        self.sensorViews.pop(sensor)
        self.ui.removeSensor(sensor)
        return True

    def hasSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        return sensor in self.sensorViews.keys()

    def registerMapCanvas(self, sensor, mapCanvas):
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        assert isinstance(sensor, SensorInstrument)

        sensorView = self.sensorViews[sensor]
        assert isinstance(sensorView, MapViewSensorSettings)
        sensorView.registerMapCanvas(mapCanvas)

        #register signals sensor specific signals
        mapCanvas.setRenderer(sensorView.rasterLayerRenderer())
        mapCanvas.setRenderer(self.vectorLayerRenderer())

        #register non-sensor specific signals for this mpa view
        self.sigMapViewVisibility.connect(mapCanvas.refresh)
        self.sigCrosshairStyleChanged.connect(mapCanvas.setCrosshairStyle)
        self.sigShowCrosshair.connect(mapCanvas.setShowCrosshair)
        self.sigVectorLayerChanged.connect(mapCanvas.refresh)
#        self.sigVectorVisibility.connect(mapCanvas.refresh)




    def addSensor(self, sensor):
        """
        :param sensor:
        :return:
        """
        assert type(sensor) is SensorInstrument
        assert sensor not in self.sensorViews.keys()

        #w.showSensorName(False)
        w = self.ui.addSensor(sensor)
        #w.sigSensorRendererChanged.connect(self.onSensorRenderingChanged)
        self.sensorViews[sensor] = w
        s  =""

    """
    def onSensorRenderingChanged(self, renderer):
        sensorSettings = self.sender()
        assert isinstance(sensorSettings, MapViewSensorSettings)
        for mapCanvas in sensorSettings.mapCanvases():
            mapCanvas.setRenderer(renderer)
            #mapCanvas.refresh()
    """
    def getSensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.sensorViews[sensor]



class MapViewRenderSettingsUI(QgsCollapsibleGroupBox, loadUI('mapviewrendersettings.ui')):

    def __init__(self, parent=None):
        """Constructor."""
        super(MapViewRenderSettingsUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect

        self.setupUi(self)

        self.btnDefaultMB.setDefaultAction(self.actionSetDefaultMB)
        self.btnTrueColor.setDefaultAction(self.actionSetTrueColor)
        self.btnCIR.setDefaultAction(self.actionSetCIR)
        self.btn453.setDefaultAction(self.actionSet453)

        self.btnSingleBandDef.setDefaultAction(self.actionSetDefaultSB)
        self.btnSingleBandBlue.setDefaultAction(self.actionSetB)
        self.btnSingleBandGreen.setDefaultAction(self.actionSetG)
        self.btnSingleBandRed.setDefaultAction(self.actionSetR)
        self.btnSingleBandNIR.setDefaultAction(self.actionSetNIR)
        self.btnSingleBandSWIR.setDefaultAction(self.actionSetSWIR)

        self.btnPasteStyle.setDefaultAction(self.actionPasteStyle)
        self.btnCopyStyle.setDefaultAction(self.actionCopyStyle)
        self.btnApplyStyle.setDefaultAction(self.actionApplyStyle)



class MapViewSensorSettings(QObject):
    """
    Describes the rendering of images of one Sensor
    """

    sigSensorRendererChanged = pyqtSignal(QgsRasterRenderer)

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(MapViewSensorSettings, self).__init__(parent)
        from timeseriesviewer.timeseries import SensorInstrument
        assert isinstance(sensor, SensorInstrument)
        self.sensor = sensor

        self.ui = MapViewRenderSettingsUI(parent)
        self.ui.create()
        self.ui.stackedWidget.currentChanged.connect(self.updateUi)
        self.sensor.sigNameChanged.connect(self.onSensorNameChanged)
        self.onSensorNameChanged(self.sensor.name())
        self.mMapCanvases = []
        self.ui.bandNames = sensor.bandNames

        self.multiBandMinValues = [self.ui.tbRedMin, self.ui.tbGreenMin, self.ui.tbBlueMin]
        self.multiBandMaxValues = [self.ui.tbRedMax, self.ui.tbGreenMax, self.ui.tbBlueMax]
        self.multiBandSliders = [self.ui.sliderRed, self.ui.sliderGreen, self.ui.sliderBlue]



        for tb in self.multiBandMinValues + self.multiBandMaxValues + [self.ui.tbSingleBandMin, self.ui.tbSingleBandMax]:
            assert isinstance(tb, QLineEdit)

            tb.setValidator(QDoubleValidator())
            tb.textChanged.connect(self.onValuesChanged)

        for sl in self.multiBandSliders + [self.ui.sliderSingleBand]:
            sl.setMinimum(1)
            sl.setMaximum(sensor.nb)
            sl.valueChanged.connect(self.updateUi)




        self.ceAlgs = collections.OrderedDict()

        self.ceAlgs["No enhancement"] = QgsContrastEnhancement.NoEnhancement
        self.ceAlgs["Stretch to MinMax"] = QgsContrastEnhancement.StretchToMinimumMaximum
        self.ceAlgs["Stretch and clip to MinMax"] = QgsContrastEnhancement.StretchAndClipToMinimumMaximum
        self.ceAlgs["Clip to MinMax"] = QgsContrastEnhancement.ClipToMinimumMaximum

        self.colorRampType = collections.OrderedDict()
        self.colorRampType['Interpolated'] = QgsColorRampShader.INTERPOLATED
        self.colorRampType['Discrete'] = QgsColorRampShader.DISCRETE
        self.colorRampType['Exact'] = QgsColorRampShader.EXACT

        self.colorRampClassificationMode = collections.OrderedDict()
        self.colorRampClassificationMode['Continuous'] = 1
        self.colorRampClassificationMode['Equal Interval'] = 2
        self.colorRampClassificationMode['Quantile'] = 3

        def populateCombobox(cb, d):
            for key, value in d.items():
                cb.addItem(key, value)
            cb.setCurrentIndex(0)

        populateCombobox(self.ui.comboBoxContrastEnhancement, self.ceAlgs)
        populateCombobox(self.ui.cbSingleBandColorRampType, self.colorRampType)
        populateCombobox(self.ui.cbSingleBandMode, self.colorRampClassificationMode)

        self.ui.cbSingleBandColorRamp.populate(QgsStyleV2.defaultStyle())


        nb = self.sensor.nb
        lyr = QgsRasterLayer(self.sensor.pathImg)

        #define default renderers:
        bands = [min([b,nb-1]) for b in range(3)]
        extent = lyr.extent()

        bandStats = [lyr.dataProvider().bandStatistics(b, QgsRasterBandStats.All, extent, 500) for b in range(nb)]

        def createEnhancement(bandIndex):
            bandIndex = min([nb - 1, bandIndex])
            e = QgsContrastEnhancement(self.sensor.bandDataType)
            e.setMinimumValue(bandStats[bandIndex].Min)
            e.setMaximumValue(bandStats[bandIndex].Max)
            e.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            return e

        self.defaultMB = QgsMultiBandColorRenderer(lyr.dataProvider(), bands[0], bands[1], bands[2])
        self.defaultMB.setRedContrastEnhancement(createEnhancement(bands[0]))
        self.defaultMB.setGreenContrastEnhancement(createEnhancement(bands[1]))
        self.defaultMB.setBlueContrastEnhancement(createEnhancement(bands[2]))

        self.defaultSB = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 0, None)

        colorRamp = self.ui.cbSingleBandColorRamp.currentColorRamp()

        #fix: QGIS 3.0 constructor
        shaderFunc = QgsColorRampShader(bandStats[0].Min, bandStats[0].Max)
        shaderFunc.setColorRampType(QgsColorRampShader.INTERPOLATED)
        shaderFunc.setClip(True)
        nSteps = 5
        colorRampItems = []
        diff = bandStats[0].Max - bandStats[0].Min
        for  i in range(nSteps+1):
            f = float(i) / nSteps
            color = colorRamp.color(f)
            value = bandStats[0].Min + diff * f
            colorRampItems.append(QgsColorRampShader.ColorRampItem(value, color))
        shaderFunc.setColorRampItemList(colorRampItems)
        shader = QgsRasterShader()
        shader.setMaximumValue(bandStats[0].Max)
        shader.setMinimumValue(bandStats[0].Min)
        shader.setRasterShaderFunction(shaderFunc)
        self.defaultSB.setShader(shader)
        self.defaultSB.setClassificationMin(shader.minimumValue())
        self.defaultSB.setClassificationMax(shader.maximumValue())
        #init connect signals
        self.ui.actionSetDefaultMB.triggered.connect(lambda : self.setBandSelection('defaultMB'))
        self.ui.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('TrueColor'))
        self.ui.actionSetCIR.triggered.connect(lambda: self.setBandSelection('CIR'))
        self.ui.actionSet453.triggered.connect(lambda: self.setBandSelection('453'))

        self.ui.actionSetDefaultSB.triggered.connect(lambda: self.setBandSelection('defaultSB'))
        self.ui.actionSetB.triggered.connect(lambda: self.setBandSelection('B'))
        self.ui.actionSetG.triggered.connect(lambda: self.setBandSelection('G'))
        self.ui.actionSetR.triggered.connect(lambda: self.setBandSelection('R'))
        self.ui.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
        self.ui.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))

        self.ui.actionApplyStyle.triggered.connect(self.applyStyle)
        self.ui.actionCopyStyle.triggered.connect(lambda : QApplication.clipboard().setMimeData(self.mimeDataStyle()))
        self.ui.actionPasteStyle.triggered.connect(lambda : self.pasteStyleFromClipboard())

        #self.ui.stackedWidget

        if not self.sensor.wavelengthsDefined():
            self.ui.btnTrueColor.setEnabled(False)
            self.ui.btnCIR.setEnabled(False)
            self.ui.btn453.setEnabled(False)

            self.ui.btnSingleBandBlue.setEnabled(False)
            self.ui.btnSingleBandGreen.setEnabled(False)
            self.ui.btnSingleBandRed.setEnabled(False)
            self.ui.btnSingleBandNIR.setEnabled(False)
            self.ui.btnSingleBandSWIR.setEnabled(False)

        #apply recent or default renderer
        renderer = lyr.renderer()

        #set defaults
        self.setLayerRenderer(self.defaultSB)
        self.setLayerRenderer(self.defaultMB)

        self.mLastRenderer = renderer
        if type(renderer) in [QgsMultiBandColorRenderer, QgsSingleBandPseudoColorRenderer]:
            self.setLayerRenderer(renderer)


        QApplication.clipboard().dataChanged.connect(self.onClipboardChange)
        self.onClipboardChange()

    def mapCanvases(self):
        return self.mMapCanvases[:]

    def registerMapCanvas(self, mapCanvas):

        assert isinstance(mapCanvas, MapCanvas)
        self.mMapCanvases.append(mapCanvas)
        mapCanvas.sigChangeSVRequest.connect(self.onMapCanvasRendererChangeRequest)


    def onSensorNameChanged(self, newName):

        self.ui.setTitle(self.sensor.name())
        self.ui.actionApplyStyle.setToolTip('Apply style to all map view images from "{}"'.format(self.sensor.name()))

    def pasteStyleFromClipboard(self):
        utils = TsvMimeDataUtils(QApplication.clipboard().mimeData())
        if utils.hasRasterStyle():
            renderer = utils.rasterStyle(self.sensor.bandDataType)
            if renderer is not None:
                self.setLayerRenderer(renderer)

    def applyStyle(self, *args):
        r = self.rasterLayerRenderer()
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.layerModel().setRenderer(r)
            mapCanvas.refresh()

    def onClipboardChange(self):
        utils = TsvMimeDataUtils(QApplication.clipboard().mimeData())
        self.ui.btnPasteStyle.setEnabled(utils.hasRasterStyle())

    def onMapCanvasRendererChangeRequest(self, mapCanvas, renderer):
        self.setLayerRenderer(renderer)

    def setBandSelection(self, key):


        if key == 'defaultMB':
            bands = [self.defaultMB.redBand(), self.defaultMB.greenBand(), self.defaultMB.blueBand()]
        elif key == 'defaultSB':
            bands = [self.defaultSB.band()]

        else:
            if key in ['R','G','B','nIR','swIR']:
                colors = [key]
            elif key == 'TrueColor':
                colors = ['R','G','B']
            elif key == 'CIR':
                colors = ['nIR', 'R', 'G']
            elif key == '453':
                colors = ['nIR','swIR', 'R']
            bands = [self.sensor.bandClosestToWavelength(c) for c in colors]

        if len(bands) == 1:
            self.ui.sliderSingleBand.setValue(bands[0]+1)
        elif len(bands) == 3:
            for i, b in enumerate(bands):
                self.multiBandSliders[i].setValue(b+1)




    SignalizeImmediately = True

    def onValuesChanged(self, text):
        styleValid = ""
        styleInValid = """.QLineEdit {border-color:red;
                           border-style: outset;
                           border-width: 2px;
                           background-color: yellow }
                        """
        w = self.sender()
        if isinstance(w, QLineEdit):
            validator = w.validator()
            assert isinstance(validator, QDoubleValidator)
            res = validator.validate(text, 0)
            if res[0] == QDoubleValidator.Acceptable:
                w.setStyleSheet(styleValid)
            else:
                w.setStyleSheet(styleInValid)

    def updateUi(self, *args):

        cw = self.ui.stackedWidget.currentWidget()
        text = ''
        if cw == self.ui.pageMultiBand:
            text = 'Multiband({} {} {})'.format(
                self.ui.sliderRed.value(),
                self.ui.sliderGreen.value(),
                self.ui.sliderBlue.value()
            )
        elif cw == self.ui.pageSingleBand:
            text = 'Singleband({})'.format(self.ui.sliderSingleBand.value())

        text = '{} - {}'.format(self.sensor.name(), text)
        self.ui.setTitle(text)


    def setLayerRenderer(self, renderer):
        ui = self.ui
        assert isinstance(renderer, QgsRasterRenderer)
        from timeseriesviewer.utils import niceNumberString
        updated = False
        if isinstance(renderer, QgsMultiBandColorRenderer):
            self.ui.cbRenderType.setCurrentIndex(0)
            #self.ui.stackedWidget.setcurrentWidget(self.ui.pageMultiBand)

            for s in self.multiBandSliders:
                s.blockSignals(True)
            ui.sliderRed.setValue(renderer.redBand())
            ui.sliderGreen.setValue(renderer.greenBand())
            ui.sliderBlue.setValue(renderer.blueBand())
            for s in self.multiBandSliders:
                s.blockSignals(False)


            ceRed = renderer.redContrastEnhancement()
            ceGreen = renderer.greenContrastEnhancement()
            ceBlue = renderer.blueContrastEnhancement()

            if ceRed is None:
                ceRed = ceGreen = ceBlue = QgsContrastEnhancement(self.sensor.bandDataType)
                s = ""
            for i, ce in enumerate([ceRed, ceGreen, ceBlue]):
                vMin = ce.minimumValue()
                vMax = ce.maximumValue()
                self.multiBandMinValues[i].setText(niceNumberString(vMin))
                self.multiBandMaxValues[i].setText(niceNumberString(vMax))

            idx = self.ceAlgs.values().index(ceRed.contrastEnhancementAlgorithm())
            ui.comboBoxContrastEnhancement.setCurrentIndex(idx)


            updated = True

        if isinstance(renderer, QgsSingleBandPseudoColorRenderer):
            self.ui.cbRenderType.setCurrentIndex(1)
            #self.ui.stackedWidget.setCurrentWidget(self.ui.pageSingleBand)

            self.ui.sliderSingleBand.setValue(renderer.band())
            shader = renderer.shader()
            cmin = shader.minimumValue()
            cmax = shader.maximumValue()
            self.ui.tbSingleBandMin.setText(str(cmin))
            self.ui.tbSingleBandMax.setText(str(cmax))

            shaderFunc = shader.rasterShaderFunction()
            self.ui.cbSingleBandColorRampType.setCurrentIndex(shaderFunc.colorRampType())
            updated = True

        self.updateUi()
        if updated:
            self.mLastRenderer = self.rasterLayerRenderer()

        if updated and MapViewSensorSettings.SignalizeImmediately:
            self.sigSensorRendererChanged.emit(renderer.clone())
            self.applyStyle()

    def mimeDataStyle(self):
        mimeData = QMimeData()
        r = self.rasterLayerRenderer()
        if isinstance(r, QgsRasterRenderer):
            doc = QDomDocument()
            lyr = QgsRasterLayer(self.sensor.pathImg)
            lyr.setRenderer(self.rasterLayerRenderer())
            err = ''
            lyr.exportNamedStyle(doc, err)
            if len(err) == 0:
                mimeData.setData('application/qgis.style', doc.toByteArray())
                mimeData.setText(doc.toString())
        return mimeData



        return mimeData

    def currentComboBoxItem(self, cb):
        d = cb.itemData(cb.currentIndex(), Qt.UserRole)
        return d

    def rasterLayerRenderer(self):
        ui = self.ui
        r = None
        if ui.stackedWidget.currentWidget() == ui.pageMultiBand:
            r = self.rasterRendererMultiBand(ui)

        if ui.stackedWidget.currentWidget() == ui.pageSingleBand:
            r = self.rasterRendererSingleBand(ui)
        return r

    def rasterRendererMultiBand(self, ui):
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
                minmax = [float(self.multiBandMinValues[i].text()), float(self.multiBandMaxValues[i].text())]
                cmin = min(minmax)
                cmax = max(minmax)
                e.setMinimumValue(cmin)
                e.setMaximumValue(cmax)
                e.setContrastEnhancementAlgorithm(alg)
                rgbEnhancements.append(e)
            r.setRedContrastEnhancement(rgbEnhancements[0])
            r.setGreenContrastEnhancement(rgbEnhancements[1])
            r.setBlueContrastEnhancement(rgbEnhancements[2])
        return r

    def rasterRendererSingleBand(self, ui):
        r = QgsSingleBandPseudoColorRenderer(None, ui.sliderSingleBand.value(), None)
        minmax = [float(ui.tbSingleBandMin.text()), float(ui.tbSingleBandMax.text())]
        cmin = min(minmax)
        cmax = max(minmax)
        r.setClassificationMin(cmin)
        r.setClassificationMax(cmax)
        colorRamp = self.ui.cbSingleBandColorRamp.currentColorRamp()
        # fix: QGIS 3.0 constructor
        shaderFunc = QgsColorRampShader(cmin, cmax)
        shaderFunc.setColorRampType(self.currentComboBoxItem(ui.cbSingleBandColorRampType))
        shaderFunc.setClip(True)
        nSteps = 10
        colorRampItems = []
        diff = cmax - cmin
        for i in range(nSteps + 1):
            f = float(i) / nSteps
            color = colorRamp.color(f)
            value = cmin + diff * f
            colorRampItems.append(QgsColorRampShader.ColorRampItem(value, color))
        shaderFunc.setColorRampItemList(colorRampItems)
        shader = QgsRasterShader()
        shader.setMaximumValue(cmax)
        shader.setMinimumValue(cmin)
        shader.setRasterShaderFunction(shaderFunc)
        r.setShader(shader)
        return r



class DatumViewUI(QFrame, loadUI('timeseriesdatumview.ui')):
    """
    Widget to host the MapCanvases of all map views that relate to a single Datum-Sensor combinbation.
    """
    def __init__(self, title='<#>', parent=None):
        super(DatumViewUI, self).__init__(parent)
        self.setupUi(self)

    def sizeHint(self):
        m = self.layout().contentsMargins()

        s = QSize(0, 0)

        map = None
        widgets = [self.layout().itemAt(i).widget() for i in range(self.layout().count())]
        widgets = [w for w in widgets if isinstance(w, QWidget)]

        maps = [w for w in widgets if isinstance(w, MapCanvas)]
        others = [w for w in widgets if not isinstance(w, MapCanvas)]

        s = self.layout().spacing()
        m = self.layout().contentsMargins()

        def totalHeight(widgetList):
            total = QSize(0,0)
            for w in widgetList:
                ws = w.size()
                if ws.width() == 0:
                    ws = w.sizeHint()
                total.setWidth(max([total.width(), ws.width()]))
                total.setHeight(total.height() +  ws.height())
            return total

        baseSize = totalHeight(widgets)
        if baseSize.width() == 0:
            for o in others:
                baseSize.setWidth(9999)
        s = QSize(baseSize.width() + m.left() + m.right(),
                  baseSize.height() + m.top() + m.bottom())
        return s

"""
    def sizeHint(self):

        if not self.ui.isVisible():
            return QSize(0,0)
        else:
            #return self.ui.sizeHint()

            size = self.ui.sizeHint()
            s = self.ui.layout().spacing()
            m = self.ui.layout().contentsMargins()
            dx = m.left() + m.right() + s
            dy = self.ui.layout().spacing()

            n = len([m for m in self.mapCanvases.keys() if m.isVisible()])
            if n > 0:
                baseSize = self.mapCanvases.values()[0].size()
                size = QSize(baseSize.width()+ dx, \
                             size.height()+ (n+1)*(dy+2*s))
            else:
                s = ""
            return size


"""



class DatumView(QObject):

    sigRenderProgress = pyqtSignal(int,int)
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigVisibilityChanged = pyqtSignal(bool)

    def __init__(self, timeSeriesDatum, stv, parent=None):
        assert isinstance(timeSeriesDatum, TimeSeriesDatum)
        assert isinstance(stv, SpatialTemporalVisualization)


        super(DatumView, self).__init__()
        self.ui = DatumViewUI(parent=parent)
        self.ui.create()
        self.showLoading(False)
        self.wOffset = self.ui.layout().count()-1
        self.minHeight = self.ui.height()
        #self.minWidth = 50
        self.renderProgress = dict()

        assert isinstance(stv, SpatialTemporalVisualization)
        self.STV = stv

        self.TSD = timeSeriesDatum
        self.scrollArea = stv.scrollArea
        self.Sensor = self.TSD.sensor
        self.Sensor.sigNameChanged.connect(lambda :self.setColumnInfo())
        self.TSD.sigVisibilityChanged.connect(self.setVisibility)
        self.setColumnInfo()
        self.MVC = stv.MVC
        self.DVC = stv.DVC
        self.mapCanvases = dict()
        self.mRenderState = dict()

    def setColumnInfo(self):

        labelTxt = '{}\n{}'.format(str(self.TSD.date), self.TSD.sensor.name())
        tooltip = '{}'.format(self.TSD.pathImg)

        self.ui.labelTitle.setText(labelTxt)
        self.ui.labelTitle.setToolTip(tooltip)

    def setVisibility(self, b):
        self.ui.setVisible(b)
        self.sigVisibilityChanged.emit(b)

    def setHighlighted(self, b=True, timeout=1000):
        styleOn = """.QFrame {
                    border: 4px solid red;
                    border-radius: 4px;
                }"""
        styleOff = """"""
        if b is True:
            self.ui.setStyleSheet(styleOn)
            if timeout > 0:
                QTimer.singleShot(timeout, lambda : self.setHighlighted(b=False))
        else:
            self.ui.setStyleSheet(styleOff)


    def setMapViewVisibility(self, bandView, isVisible):
        self.mapCanvases[bandView].setVisible(isVisible)


    def removeMapView(self, mapView):
        canvas = self.mapCanvases.pop(mapView)
        self.ui.layout().removeWidget(canvas)
        canvas.close()
        #self.adjustBaseMinSize()

    def refresh(self):

        if self.ui.isVisible():
            for c in self.mapCanvases.values():
                if c.isVisible():
                    c.refresh()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)
        from timeseriesviewer.mapcanvas import MapCanvas

        mapCanvas = MapCanvas(self.ui)
        mapCanvas.setObjectName('MapCanvas {} {}'.format(mapView.title(), self.TSD.date))
        mapCanvas.blockSignals(True)
        self.registerMapCanvas(mapView, mapCanvas)

        # register MapCanvas on MV level
        mapView.registerMapCanvas(self.Sensor, mapCanvas)
        # register MapCanvas on STV level
        self.STV.registerMapCanvas(mapCanvas)

        mapCanvas.blockSignals(False)
        mapCanvas.renderComplete.connect(lambda : self.onRenderingChange(False))
        mapCanvas.renderStarting.connect(lambda : self.onRenderingChange(True))

        mapCanvas.sigDataLoadingFinished.connect(
            lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('Map {}'.format(self.Sensor.name()), dt))
        mapCanvas.sigDataLoadingFinished.connect(
            lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('All Sensors', dt))

    def showLoading(self, b):
        if b:
            self.ui.progressBar.setRange(0,0)
            self.ui.progressBar.setValue(-1)
        else:
            self.ui.progressBar.setRange(0,1)
            self.ui.progressBar.setValue(0)

    def onRenderingChange(self, b):
        mc = self.sender()
        #assert isinstance(mc, QgsMapCanvas)
        self.mRenderState[mc] = b
        self.showLoading(any(self.mRenderState.values()))

    def onRendering(self, *args):
        renderFlags = [m.renderFlag() for m in self.mapCanvases.values()]
        drawFlags = [m.isDrawing() for m in self.mapCanvases.values()]
#        print((renderFlags, drawFlags))
        isLoading = any(renderFlags)

        self.showLoading(isLoading)

        s = ""

    def registerMapCanvas(self, mapView, mapCanvas):

        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        self.mapCanvases[mapView] = mapCanvas

        mapCanvas.layerModel().setRasterLayerSources([self.TSD.pathImg])

        self.ui.layout().insertWidget(self.wOffset + len(self.mapCanvases), mapCanvas)
        self.ui.update()

        #register signals handled on (this) DV level
        mapCanvas.renderStarting.connect(lambda: self.sigLoadingStarted.emit(mapView, self.TSD))
        mapCanvas.mapCanvasRefreshed.connect(lambda: self.sigLoadingFinished.emit(mapView, self.TSD))
        mapCanvas.sigShowProfiles.connect(lambda c, t : mapView.sigShowProfiles.emit(c,mapCanvas, t))
        mapCanvas.sigChangeDVRequest.connect(self.onMapCanvasRequest)


    def onMapCanvasRequest(self, mapCanvas, key):

        if key == 'hide_date':
            self.TSD.setVisibility(False)
        if key == 'copy_sensor':
            QApplication.clipboard().setText(self.TSD.sensor.name())
        if key == 'copy_date':
            QApplication.clipboard().setText(str(self.TSD.date))
        if key == 'copy_path':
            QApplication.clipboard().setText(str(self.TSD.pathImg))

    def __lt__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD < other.TSD

    def __eq__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD == other.TSD

class SpatialTemporalVisualization(QObject):
    """

    """
    sigLoadingStarted = pyqtSignal(DatumView, MapView)
    sigLoadingFinished = pyqtSignal(DatumView, MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)
    sigShowMapLayerInfo = pyqtSignal(dict)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigCRSChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigActivateMapTool = pyqtSignal(str)

    def __init__(self, timeSeriesViewer):
        super(SpatialTemporalVisualization, self).__init__()
        #assert isinstance(timeSeriesViewer, TimeSeriesViewer), timeSeriesViewer

        #default map settings
        self.mBlockCanvasSignals = False
        self.mSpatialExtent = SpatialExtent.world()
        self.mCRS = self.mSpatialExtent.crs()
        self.mSize = QSize(200,200)
        self.mColor = Qt.black
        self.mMapCanvases = []
        self.ui = timeSeriesViewer.ui

        #map-tool handling
        self.mMapToolActivator = None
        self.mMapTools = []

        self.scrollArea = self.ui.scrollAreaSubsets
        assert isinstance(self.scrollArea, MapViewScrollArea)


        self.mRefreshTimer = QTimer(self)
        self.mRefreshTimer.setInterval(1000)
        self.mRefreshTimer.timeout.connect(self.refresh)

        self.scrollArea.sigResized.connect(self.mRefreshTimer.start)
        self.scrollArea.horizontalScrollBar().valueChanged.connect(self.mRefreshTimer.start)


        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.TS
        self.ui.dockMapViews.setTimeSeries(self.TS)
        self.targetLayout = self.ui.scrollAreaSubsetContent.layout()



        #self.MVC = MapViewCollection(self)
        #self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.MVC = self.ui.dockMapViews
        assert isinstance(self.MVC, MapViewCollectionDock)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.vectorOverlay = None

        self.DVC = DateViewCollection(self)
        self.DVC.sigResizeRequired.connect(self.adjustScrollArea)
        self.DVC.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.DVC.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        #self.timeSeriesDateViewCollection.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        self.TS.sigTimeSeriesDatesAdded.connect(self.DVC.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.DVC.removeDates)
        #add dates, if already existing
        self.DVC.addDates(self.TS[:])
        if len(self.TS) > 0:
            self.setSpatialExtent(self.TS.getMaxSpatialExtent())
        #self.setSubsetSize(QSize(100,50))

    def createMapView(self):
        self.MVC.createMapView()

    def registerMapCanvas(self, mapCanvas):
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)


        self.mMapCanvases.append(mapCanvas)

        #set general canvas properties
        mapCanvas.setFixedSize(self.mSize)
        mapCanvas.setCrs(self.mCRS)
        mapCanvas.setSpatialExtent(self.mSpatialExtent)


        #register on map canvas signals
        mapCanvas.sigSpatialExtentChanged.connect(lambda e: self.setSpatialExtent(e, mapCanvas))



    def setCrosshairStyle(self, crosshairStyle):
        from timeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setCrosshairStyle(crosshairStyle)

        #self.MVC.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        self.MVC.setShowCrosshair(b)

    def setVectorLayer(self, lyr):
        self.MVC.setVectorLayer(lyr)



    def setMapSize(self, size):
        assert isinstance(size, QSize)
        self.mSize = size
        from timeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setFixedSize(size)
        self.sigMapSizeChanged.emit(self.mSize)
        self.adjustScrollArea()

    def subsetSize(self):
        return QSize(self.mSize)


    def refresh(self):
        #print('STV REFRESH')
        for tsdView in self.DVC:
            tsdView.refresh()
        self.mRefreshTimer.stop()

    def adjustScrollArea(self):
        #adjust scroll area widget to fit all visible widgets
        m = self.targetLayout.contentsMargins()
        nX = len(self.DVC)
        w = h = 0

        s = QSize()
        r = None
        tsdViews = [v for v in self.DVC if v.ui.isVisible()]
        mapViews = [v for v in self.MVC if v.isVisible()]
        nX = len(tsdViews)
        nY = len(mapViews)
        spacing = self.targetLayout.spacing()
        margins = self.targetLayout.contentsMargins()

        sizeX = 1
        sizeY = 50
        if nX > 0:
            s = tsdViews[0].ui.sizeHint().width()
            s = nX * (s + spacing) + margins.left() + margins.right()
            sizeX = s
        if nY > 0:
            if nX > 0:
                s = tsdViews[0].ui.sizeHint().height()
                s = s + margins.top() + margins.bottom()
            else:
                s = 50
            sizeY = s

            #s = tsdViews[0].ui.sizeHint()
            #s = QSize(nX * (s.width() + spacing) + margins.left() + margins.right(),
            #          s.height() + margins.top() + margins.bottom())

        self.targetLayout.parentWidget().setFixedSize(QSize(sizeX, sizeY))

    def setMapTool(self, mapToolKey, *args, **kwds):
        # filter map tools
        self.mMapToolActivator = self.sender()
        del self.mMapTools[:]

        from timeseriesviewer.mapcanvas import MapTools, CursorLocationMapTool, SpectralProfileMapTool, TemporalProfileMapTool
        for canvas in self.mMapCanvases:
            mt = None
            if mapToolKey in MapTools.mapToolKeys():
                mt = MapTools.create(mapToolKey, canvas, *args, **kwds)

            if isinstance(mapToolKey, QgsMapTool):
                mt = MapTools.copy(mapToolKey, canvas, *args, **kwds)

            if isinstance(mt, QgsMapTool):
                canvas.setMapTool(mt)
                self.mMapTools.append(mt)

                #if required, link map-tool with specific EnMAP-Box slots
                if isinstance(mt, CursorLocationMapTool):
                    mt.sigLocationRequest[SpatialPoint, QgsMapCanvas].connect(lambda c, m : self.sigShowProfiles.emit(c,m, mapToolKey))

        return self.mMapTools



    def setMaxTSDViews(self, n=-1):
        self.nMaxTSDViews = n
        #todo: remove views

    def setSpatialCenter(self, center, mapCanvas0=None):
        if self.mBlockCanvasSignals:
            return True

        assert isinstance(center, SpatialPoint)
        center = center.toCrs(self.mCRS)
        if not isinstance(center, SpatialPoint):
            return

        self.mBlockCanvasSignals = True
        self.mSpatialExtent.setCenter(center)
        for mapCanvas in self.mMapCanvases:
            if mapCanvas != mapCanvas0:
                oldState = mapCanvas.blockSignals(True)
                mapCanvas.setCenter(center)
                mapCanvas.blockSignals(oldState)
        self.mBlockCanvasSignals = False

        self.sigSpatialExtentChanged.emit(self.mSpatialExtent)


    def setSpatialExtent(self, extent, mapCanvas0=None):
        if self.mBlockCanvasSignals:
            return True

        assert isinstance(extent, SpatialExtent)
        extent = extent.toCrs(self.mCRS)
        if not isinstance(extent, SpatialExtent) \
            or extent.isEmpty() or not extent.isFinite() \
            or extent.width() <= 0 \
            or extent.height() <= 0 \
            or extent == self.mSpatialExtent:
            return

        self.mBlockCanvasSignals = True
        self.mSpatialExtent = extent
        for mapCanvas in self.mMapCanvases:
            if mapCanvas != mapCanvas0:
                oldState = mapCanvas.blockSignals(True)
                mapCanvas.setExtent(extent)
                mapCanvas.blockSignals(oldState)

        self.mBlockCanvasSignals = False
        #for mapCanvas in self.mMapCanvases:
        #    mapCanvas.refresh()
        self.mRefreshTimer.start()
        self.sigSpatialExtentChanged.emit(extent)

    def setBackgroundColor(self, color):
        assert isinstance(color, QColor)
        self.mColor = color
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setCanvasColor(color)
            mapCanvas.refresh()

    def backgroundColor(self):
        return self.mColor


    def mapCanvasIterator(self):
        return self.mMapCanvases[:]

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if self.mCRS != crs:
            from timeseriesviewer.utils import saveTransform
            if saveTransform(self.mSpatialExtent, self.mCRS, crs):
                self.mCRS = crs
                for mapCanvas in self.mapCanvasIterator():
                    #print(('STV set CRS {} {}', str(mapCanvas), self.mCRS.description()))
                    mapCanvas.setCrs(crs)
            else:
                pass
            self.sigCRSChanged.emit(self.mCRS)


    def crs(self):
        return self.mCRS

    def spatialExtent(self):
        return self.mSpatialExtent



    def navigateToTSD(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        #get widget related to TSD
        tsdv = self.DVC.tsdView(TSD)
        assert isinstance(self.scrollArea, QScrollArea)
        self.scrollArea.ensureWidgetVisible(tsdv.ui)


class DateViewCollection(QObject):

    sigResizeRequired = pyqtSignal()
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigShowProfiles = pyqtSignal(SpatialPoint)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def __init__(self, STViz):
        assert isinstance(STViz, SpatialTemporalVisualization)
        super(DateViewCollection, self).__init__()
        #self.tsv = tsv
        #self.timeSeries = tsv.TS

        self.views = list()
        self.STV = STViz
        self.ui = self.STV.targetLayout.parentWidget()
        self.scrollArea = self.ui.parentWidget().parentWidget()
        #potentially there are many more dates than views.
        #therefore we implement the addinng/removing of mapviews here
        #we reduce the number of layout refresh calls by
        #suspending signals, adding the new map view canvases, and sending sigResizeRequired

        self.STV.MVC.sigMapViewAdded.connect(self.addMapView)
        self.STV.MVC.sigMapViewRemoved.connect(self.removeMapView)

        self.setFocusView(None)


    def tsdFromMapCanvas(self, mapCanvas):
        assert isinstance(mapCanvas, MapCanvas)
        for view in self.views:
            assert isinstance(view, DatumView)
            if mapCanvas in view.mapCanvases.values():
                return view.TSD
        return None

    def tsdView(self, tsd):
        r = [v for v in self.views if v.TSD == tsd]
        if len(r) == 1:
            return r[0]
        else:
            raise Exception('TSD not in list')

    def addMapView(self, mapView):
        assert isinstance(mapView, MapView)
        w = self.ui
        w.setUpdatesEnabled(False)
        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.views:
            tsdv.insertMapView(mapView)

        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(True)

        #mapView.sigSensorRendererChanged.connect(lambda *args : self.setRasterRenderer(mapView, *args))
        mapView.sigMapViewVisibility.connect(lambda: self.sigResizeRequired.emit())
        mapView.sigShowProfiles.connect(self.sigShowProfiles.emit)
        w.setUpdatesEnabled(True)

        self.sigResizeRequired.emit()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        for tsdv in self.views:
            tsdv.removeMapView(mapView)
        self.sigResizeRequired.emit()


    def highlightDate(self, tsd):
        """
        Highlights a time series data for a specific time our
        :param tsd:
        :return:
        """
        tsdView = self.tsdView(tsd)
        if isinstance(tsdView, DatumView):
            tsdView.setHighlight(True)

    def setFocusView(self, tsd):
        self.focusView = tsd

    def orderedViews(self):
        #returns the
        if self.focusView is not None:
            assert isinstance(self.focusView, DatumView)
            return sorted(self.views,key=lambda v: np.abs(v.TSD.date - self.focusView.TSD.date))
        else:
            return self.views

    """
    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size

        for tsdView in self.orderedViews():
            tsdView.blockSignals(True)

        for tsdView in self.orderedViews():
            tsdView.setSubsetSize(size)

        for tsdView in self.orderedViews():
            tsdView.blockSignals(False)
    """


    def addDates(self, tsdList):
        """
        Create a new TSDView
        :param tsdList:
        :return:
        """
        for tsd in tsdList:
            assert isinstance(tsd, TimeSeriesDatum)
            DV = DatumView(tsd, self.STV, parent=self.ui)
            #tsdView.setSubsetSize(self.subsetSize)
            DV.sigLoadingStarted.connect(self.sigLoadingStarted.emit)
            DV.sigLoadingFinished.connect(self.sigLoadingFinished.emit)
            DV.sigVisibilityChanged.connect(lambda: self.STV.adjustScrollArea())


            for i, mapView in enumerate(self.STV.MVC):
                DV.insertMapView(mapView)

            bisect.insort(self.views, DV)
            i = self.views.index(DV)

            DV.ui.setParent(self.STV.targetLayout.parentWidget())
            self.STV.targetLayout.insertWidget(i, DV.ui)
            DV.ui.show()

        if len(tsdList) > 0:
            self.sigResizeRequired.emit()

    def removeDates(self, tsdList):
        toRemove = [v for v in self.views if v.TSD in tsdList]
        removedDates = []
        for DV in toRemove:
            self.views.remove(DV)

            for mapCanvas in DV.mapCanvases.values():
                toRemove = mapCanvas.layers()
                mapCanvas.setLayers([])
                toRemove = [l for l in toRemove if isinstance(l, QgsRasterLayer)]
                if len(toRemove) > 0:
                    QgsMapLayerRegistry.instance().removeMapLayers(toRemove)

            DV.ui.parent().layout().removeWidget(DV.ui)
            DV.ui.hide()
            DV.ui.close()
            removedDates.append(DV.TSD)
            del DV

        if len(removedDates) > 0:
            self.sigResizeRequired.emit()

    def __len__(self):
        return len(self.views)

    def __iter__(self):
        return iter(self.views)

    def __getitem__(self, slice):
        return self.views[slice]

    def __delitem__(self, slice):
        self.removeDates(self.views[slice])


class MapViewListModel(QAbstractListModel):
    """
    A model to keep a list of map views.

    """
    sigMapViewsAdded = pyqtSignal(list)
    sigMapViewsRemoved = pyqtSignal(list)

    def __init__(self, parent=None):
        super(MapViewListModel, self).__init__(parent)
        self.mMapViewList = []


    def addMapView(self, mapView):
        i = len(self.mMapViewList)
        self.insertMapView(i, mapView)

    def insertMapView(self, i, mapView):
        self.insertMapViews(i, [mapView])

    def insertMapViews(self, i, mapViews):
        assert isinstance(mapViews, list)
        assert i >= 0 and i <= len(self.mMapViewList)

        self.beginInsertRows(QModelIndex(), i, i + len(mapViews) - 1)

        for j in range(len(mapViews)):
            mapView = mapViews[j]
            assert isinstance(mapView, MapView)
            mapView.sigTitleChanged.connect(
                lambda : self.doRefresh([mapView])
            )
            self.mMapViewList.insert(i + j, mapView)
        self.endInsertRows()
        self.sigMapViewsAdded.emit(mapViews)


    def doRefresh(self, mapViews):
        for mapView in mapViews:
            idx = self.mapView2idx(mapView)
            self.dataChanged.emit(idx, idx)

    def removeMapView(self, mapView):
        self.removeMapViews([mapView])

    def removeMapViews(self, mapViews):
        assert isinstance(mapViews, list)
        for mv in mapViews:
            assert mv in self.mMapViewList
            idx = self.mapView2idx(mv)
            self.beginRemoveRows(idx.parent(), idx.row(), idx.row())
            self.mMapViewList.remove(mv)
            self.endRemoveRows()
        self.sigMapViewsRemoved.emit(mapViews)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mMapViewList)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1


    def idx2MapView(self, index):
        if isinstance(index, QModelIndex):
            if index.isValid():
                index = index.row()
            else:
                return None
        assert index >= 0 and index < len(self.mMapViewList)
        return self.mMapViewList[index]


    def mapView2idx(self, mapView):
        assert isinstance(mapView, MapView)
        row = self.mMapViewList.index(mapView)
        return self.createIndex(row, 0, mapView)

    def __len__(self):
        return len(self.mMapViewList)

    def __iter__(self):
        return iter(self.mMapViewList)

    def __getitem__(self, slice):
        return self.mMapViewList[slice]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mMapViewList)) or (index.row() < 0):
            return None

        mapView = self.idx2MapView(index)
        assert isinstance(mapView, MapView)

        value = None

        if role == Qt.DisplayRole:
            value = '{} {}'.format(index.row() +1 , mapView.title())
        #if role == Qt.DecorationRole:
            #value = classInfo.icon(QSize(20,20))
        if role == Qt.UserRole:
            value = mapView
        return value

class MapViewCollectionDock(QgsDockWidget, loadUI('mapviewdock.ui')):

    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def connectTimeSeries(self, timeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        self.TS.sigSensorAdded.connect(self.addSensor)
        self.TS.sigSensorRemoved.connect(self.removeSensor)

    def __init__(self, parent=None):
        super(MapViewCollectionDock, self).__init__(parent)
        self.setupUi(self)
        self.baseTitle = self.windowTitle()

        self.btnAddMapView.setDefaultAction(self.actionAddMapView)
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnRefresh.setDefaultAction(self.actionApplyStyles)
        self.btnHighlightMapView.setDefaultAction(self.actionHighlightMapView)

        self.actionAddMapView.triggered.connect(self.createMapView)
        self.actionRemoveMapView.triggered.connect(lambda : self.removeMapView(self.currentMapView()))
        self.actionHighlightMapView.triggered.connect(lambda : self.currentMapView().setHighlighted(True))
        self.actionApplyStyles.triggered.connect(lambda : self.currentMapView().refreshMapView())
        self.mMapViews = MapViewListModel()
        self.mMapViews.sigMapViewsRemoved.connect(self.onMapViewsRemoved)
        self.mMapViews.sigMapViewsAdded.connect(self.onMapViewsAdded)
        self.mMapViews.sigMapViewsAdded.connect(self.updateButtons)
        self.mMapViews.sigMapViewsRemoved.connect(self.updateButtons)
        self.cbMapView.setModel(self.mMapViews)
        self.cbMapView.currentIndexChanged[int].connect(lambda i : None if i < 0 else self.setCurrentMapView(self.mMapViews.idx2MapView(i)) )

        self.TS = None

    def onMapViewsRemoved(self, mapViews):

        for mapView in mapViews:
            idx = self.stackedWidget.indexOf(mapView.ui)
            if idx >= 0:
                self.stackedWidget.removeWidget(mapView.ui)
                mapView.ui.close()
            else:
                s = ""


        self.actionRemoveMapView.setEnabled(len(self.mMapViews) > 0)

    def onMapViewsAdded(self, mapViews):
        nextShown = None
        for mapView in mapViews:
            self.stackedWidget.addWidget(mapView.ui)
            if nextShown is None:
                nextShown = mapView

            contents = mapView.ui.scrollAreaWidgetContents
            size = contents.size()
            hint = contents.sizeHint()
            #mapView.ui.scrollArea.update()
            s = ""
            #setMinimumSize(mapView.ui.scrollAreaWidgetContents.sizeHint())
            #hint = contents.sizeHint()
            #contents.setMinimumSize(hint)
        if isinstance(nextShown, MapView):
            self.setCurrentMapView(nextShown)


    def updateButtons(self, *args):
        b = len(self.mMapViews) > 0
        self.actionRemoveMapView.setEnabled(b)
        self.actionApplyStyles.setEnabled(b)
        self.actionHighlightMapView.setEnabled(b)


    def createMapView(self):


        mapView = MapView(self)

        n = len(self.mMapViews) + 1
        title = 'Map View {}'.format(n)
        while title in [m.title() for m in self.mMapViews]:
            n += 1
            title = 'Map View {}'.format(n)
        mapView.setTitle(title)

        for sensor in self.TS.Sensors:
            mapView.addSensor(sensor)

        mapView.sigShowProfiles.connect(self.sigShowProfiles)
        self.mMapViews.addMapView(mapView)
        self.sigMapViewAdded.emit(mapView)
        return mapView

    def updateFromMapView(self, mapView):
        assert isinstance(mapView, MapView)
        self.btnToggleMapViewVisibility.setChecked(mapView)

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        assert mapView in self.mMapViews

        i = self.mMapViews.mapView2idx(mapView)
        if not i == self.stackedWidget.indexOf(mapView.ui):
            s = ""

        self.mMapViews.removeMapView(mapView)

        mapView.ui.close()

        self.sigMapViewRemoved.emit(mapView)

    def __len__(self):
        return len(self.mMapViews)

    def __iter__(self):
        return iter(self.mMapViews)

    def __getitem__(self, slice):
        return self.mMapViews[slice]

    def __contains__(self, mapView):
        return mapView in self.mMapViews

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mMapViews.index(mapView)

    def setVectorLayer(self, lyr):
        for mapView in self.mMapViews:
            assert isinstance(mapView, MapView)
            mapView.setVectorLayer(lyr)

    def addSensor(self, sensor):
        for mapView in self.mMapViews:
            mapView.addPlotStyle(sensor)
        #self.adjustScrollArea()

    def removeSensor(self, sensor):
        for mapView in self.mMapViews:
            mapView.removePlotItem(sensor)

    def applyStyles(self):
        for mapView in self.mMapViews:
            mapView.applyStyles()

    def setCrosshairStyle(self, crosshairStyle):
        for mapView in self.mMapViews:
            mapView.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        for mapView in self.mMapViews:
            mapView.setShowCrosshair(b)

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViewsDefinitions.index(mapView)


    def setCurrentMapView(self, mapView):
        assert isinstance(mapView, MapView) and mapView in self.mMapViews
        idx = self.stackedWidget.indexOf(mapView.ui)
        if idx >= 0:
            self.stackedWidget.setCurrentIndex(idx)
            self.cbMapView.setCurrentIndex(self.mMapViews.mapView2idx(mapView).row())


    def currentMapView(self):
        if len(self.mMapViews) == None:
            return None
        else:
            i = self.cbMapView.currentIndex()
            return self.mMapViews.idx2MapView(i)


"""
class MapViewDockUI(TsvDockWidgetBase, loadUi('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.baseTitle = self.windowTitle()
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)

        #self.dockLocationChanged.connect(self.adjustLayouts)



    def toggleLayout(self, p):
        newLayout = None
        l = p.layout()
        print('toggle layout {}'.format(str(p.objectName())))
        tmp = QWidget()
        tmp.setLayout(l)
        sMax = p.maximumSize()
        sMax.transpose()
        sMin = p.minimumSize()
        sMin.transpose()
        p.setMaximumSize(sMax)
        p.setMinimumSize(sMin)
        if isinstance(l, QVBoxLayout):
            newLayout = QHBoxLayout()
        else:
            newLayout = QVBoxLayout()
        print(l, '->', newLayout)

        while l.count() > 0:
            item = l.itemAt(0)
            l.removeItem(item)

            newLayout.addItem(item)


        p.setLayout(newLayout)
        return newLayout

    def adjustLayouts(self, area):
        return
        lOld = self.scrollAreaMapsViewDockContent.layout()
        if area in [Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea] \
            and isinstance(lOld, QVBoxLayout) or \
        area in [Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea] \
                        and isinstance(lOld, QHBoxLayout):

            #self.toogleLayout(self.scrollAreaMapsViewDockContent)
            self.toggleLayout(self.BVButtonList)
"""