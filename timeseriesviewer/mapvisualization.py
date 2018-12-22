# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
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


import os, sys, re, fnmatch, collections, copy, traceback, bisect
from qgis.core import *
from qgis.core import QgsContrastEnhancement, QgsRasterShader, QgsColorRampShader,  QgsProject, QgsCoordinateReferenceSystem, \
    QgsRasterLayer, QgsVectorLayer, QgsMapLayer, QgsMapLayerProxyModel, QgsColorRamp, QgsSingleBandPseudoColorRenderer

from qgis.gui import *
from qgis.gui import QgsDockWidget, QgsMapCanvas, QgsMapTool, QgsCollapsibleGroupBox
from PyQt5.QtXml import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import numpy as np
from timeseriesviewer.utils import *

from timeseriesviewer.timeseries import SensorInstrument, TimeSeriesDatum, TimeSeries
from timeseriesviewer.ui.docks import loadUI
from timeseriesviewer.ui.mapviewscrollarea import MapViewScrollArea
from timeseriesviewer.mapcanvas import MapCanvas
from timeseriesviewer.crosshair import CrosshairStyle



#assert os.path.isfile(dummyPath)
#lyr = QgsRasterLayer(dummyPath)
#assert lyr.isValid()
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)



class MapViewUI(QFrame, loadUI('mapviewdefinition.ui')):


    def __init__(self, parent=None):
        super(MapViewUI, self).__init__(parent)
        self.setupUi(self)
        self.mSensors = collections.OrderedDict()

        m = QMenu(self.btnToggleCrosshair)
        m.addAction(self.actionSetCrosshairStyle)
        #a = m.addAction('Set Crosshair Style')

        self.btnToggleCrosshair.setMenu(m)

        from timeseriesviewer.main import TimeSeriesViewer
        tsv = TimeSeriesViewer.instance()
        if isinstance(tsv, TimeSeriesViewer):
            self.mStore = tsv.mapLayerStore()
            self.mVectorSourceModel = self.cbQgsVectorLayer.model().sourceModel()
            self.mStore.layersAdded.connect(self.mVectorSourceModel.addLayers)
            self.mStore.layersRemoved.connect(self.mVectorSourceModel.removeLayers)

        #connect the QActions with the QgsCollapsibleGroupBoxes
        self.gbVectorRendering.toggled.connect(self.actionToggleVectorVisibility.setChecked)
        self.gbRasterRendering.toggled.connect(self.actionToggleRasterVisibility.setChecked)

        #self.connectActionWithGroupBox(self.actionToggleVectorVisibility, self.gbVectorRendering)
        #self.connectActionWithGroupBox(self.actionToggleRasterVisibility, self.gbRasterRendering)

        #self.gbVectorRendering.toggled.connect(self.actionToggleVectorVisibility.toggle)
        #self.gbRasterRendering.toggled.connect(self.actionToggleRasterVisibility.toggle)
        #self.actionToggleVectorVisibility.toggled.connect(self.gbVectorRendering.setChecked)
        #self.actionToggleRasterVisibility.toggled.connect(self.gbRasterRendering.setChecked)

        self.btnToggleCrosshair.setDefaultAction(self.actionToggleCrosshairVisibility)
        self.btnToggleMapViewVisibility.setDefaultAction(self.actionToggleMapViewHidden)
        self.btnSetVectorStyle.setDefaultAction(self.actionSetVectorStyle)



    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)

        #w = MapViewSensorSettings(sensor)
        w = MapViewRenderSettings(sensor)
        w.collapsedStateChanged.connect(self.onSensorBoxCollapsed)
        l = self.gbRasterRendering.layout()
        assert sensor not in self.mSensors.keys()

        i = l.count()-1
        while i > 0 and not isinstance(l.itemAt(i), QWidget):
            i -= 1
        l.insertWidget(i, w, stretch=0, alignment=Qt.AlignTop)
        self.mSensors[sensor] = w
        #self.resize(self.sizeHint())

        return w


    def removeSensor(self, sensor):

        assert isinstance(sensor, SensorInstrument)
        sensorSettings = self.mSensors.pop(sensor)
        assert isinstance(sensorSettings, MapViewRenderSettings)

        #l = self.renderSettingsLayout
        l = self.gbRasterRendering.layout()
        l.removeWidget(sensorSettings)
        sensorSettings.close()
        #self.resize(self.sizeHint())

    def onSensorBoxCollapsed(self, b:bool):
        l = self.gbRasterRendering.layout()
        for i in range(l.count()):
            item = l.itemAt(i)

            s = ""

class RendererWidgetModifications(object):

    def __init__(self, *args):
        self.initWidgetNames()
        self.mBandComboBoxes = []


    def modifyGridLayout(self):

        gridLayoutOld = self.layout().children()[0]
        self.gridLayout = QGridLayout()
        while gridLayoutOld.count() > 0:
            w = gridLayoutOld.takeAt(0)
            w = w.widget()
            gridLayoutOld.removeWidget(w)
            w.setVisible(False)

        self.gridLayout.setSpacing(2)

        l = self.layout()
        l.removeItem(gridLayoutOld)
        if isinstance(l, QBoxLayout):
            l.insertItem(0, self.gridLayout)
            self.layout().addStretch()
        elif isinstance(l, QGridLayout):
            l.addItem(self.gridLayout, 0, 0)


        minMaxWidget = self.minMaxWidget()
        if isinstance(minMaxWidget, QWidget):
            minMaxWidget.layout().itemAt(0).widget().collapsedStateChanged.connect(self.onCollapsed)


    def initWidgetNames(self, parent=None):
        """
        Create a python variables to access QObjects which are child of parent
        :param parent: QObject, self by default
        """
        if parent is None:
            parent = self

        for c in parent.children():
            setattr(parent, c.objectName(), c)





    def onCollapsed(self, b):
        hint = self.sizeHint()
        self.parent().adjustSize()
       # self.parent().setFixedSize(hint)
        self.parent().parent().adjustSize()

    def connectSliderWithBandComboBox(self, slider, combobox):
        """
        Connects a band-selection slider with a band-selection combobox
        :param widget: QgsRasterRendererWidget
        :param slider: QSlider to show the band number
        :param combobox: QComboBox to show the band name
        :return:
        """
        assert isinstance(self, QgsRasterRendererWidget)
        assert isinstance(slider, QSlider)
        assert isinstance(combobox, QComboBox)

        # init the slider
        lyr = self.rasterLayer()
        if lyr.isValid():
            nb = lyr.dataProvider().bandCount()
        else:
            ds = gdal.Open(lyr.source())
            if isinstance(ds, gdal.Dataset):
                nb = ds.RasterCount
            else:
                nb = 1
        slider.setTickPosition(QSlider.TicksAbove)
        slider.valueChanged.connect(combobox.setCurrentIndex)
        slider.setMinimum(1)
        slider.setMaximum(nb)
        intervals = [1, 2, 5, 10, 25, 50]
        for interval in intervals:
            if nb / interval < 10:
                break
        slider.setTickInterval(interval)
        slider.setPageStep(interval)

        def onBandValueChanged(self, idx, slider):
            assert isinstance(self, QgsRasterRendererWidget)
            assert isinstance(idx, int)
            assert isinstance(slider, QSlider)

            # i = slider.value()
            slider.blockSignals(True)
            slider.setValue(idx)
            slider.blockSignals(False)

            # self.minMaxWidget().setBands(myBands)
            # self.widgetChanged.emit()

        if self.comboBoxWithNotSetItem(combobox):
            combobox.currentIndexChanged[int].connect(lambda idx: onBandValueChanged(self, idx, slider))
        else:
            combobox.currentIndexChanged[int].connect(lambda idx: onBandValueChanged(self, idx + 1, slider))

        s = ""

    def comboBoxWithNotSetItem(self, cb)->bool:
        assert isinstance(cb, QComboBox)
        data = cb.itemData(0, role=Qt.DisplayRole)
        return re.search(r'^(not set|none|nonetype)$', str(data).strip(), re.I) is not None

    def setLayoutItemVisibility(self, grid, isVisible):
        assert isinstance(self, QgsRasterRendererWidget)
        for i in range(grid.count()):
            item = grid.itemAt(i)
            if isinstance(item, QLayout):
                s = ""
            elif isinstance(item, QWidgetItem):
                item.widget().setVisible(isVisible)
                item.widget().setParent(self)
            else:
                s = ""

    def setBandSelection(self, key):
        key = key.upper()
        if key == 'DEFAULT':
            bandIndices = defaultBands(self.rasterLayer())
        else:
            colors = re.split('[ ,;:]', key)

            bandIndices = [bandClosestToWavelength(self.rasterLayer(), c) for c in colors]

        n = min(len(bandIndices), len(self.mBandComboBoxes))
        for i in range(n):
            cb = self.mBandComboBoxes[i]
            bandIndex = bandIndices[i]
            if self.comboBoxWithNotSetItem(cb):
                cb.setCurrentIndex(bandIndex+1)
            else:
                cb.setCurrentIndex(bandIndex)


    def fixBandNames(self, comboBox):
        """
        Changes the QGIS default bandnames ("Band 001") to more meaningfull information including gdal.Dataset.Descriptions.
        :param widget:
        :param comboBox:
        """
        nb = self.rasterLayer().bandCount()

        assert isinstance(self, QgsRasterRendererWidget)
        assert isinstance(comboBox, QComboBox)
        #comboBox.clear()
        m = comboBox.model()
        assert isinstance(m, QStandardItemModel)
        bandNames = displayBandNames(self.rasterLayer())


        b = 1 if nb < comboBox.count() else 0
        for i in range(nb):
            item = m.item(i+b,0)
            assert isinstance(item, QStandardItem)
            item.setData(bandNames[i], Qt.DisplayRole)
            item.setData('Band {} "{}"'.format(i+1, bandNames[i]), Qt.ToolTipRole)








def displayBandNames(provider_or_dataset, bands=None):
    results = None
    if isinstance(provider_or_dataset, QgsRasterLayer):
        return displayBandNames(provider_or_dataset.dataProvider())
    elif isinstance(provider_or_dataset, QgsRasterDataProvider):
        if provider_or_dataset.name() == 'gdal':
            ds = gdal.Open(provider_or_dataset.dataSourceUri())
            results = displayBandNames(ds, bands=bands)
        else:
            # same as in QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, provider_or_dataset.bandCount() + 1)
            for band in bands:
                result = provider_or_dataset.generateBandName(band)
                colorInterp ='{}'.format(provider_or_dataset.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    result += '({})'.format(colorInterp)
                results.append(result)

    elif isinstance(provider_or_dataset, gdal.Dataset):
        results = []
        if bands is None:
            bands = range(1, provider_or_dataset.RasterCount+1)
        for band in bands:
            b = provider_or_dataset.GetRasterBand(band)
            descr = b.GetDescription()
            if len(descr) == 0:
                descr = 'Band {}'.format(band)
            results.append(descr)

    return results

class SingleBandGrayRendererWidget(QgsSingleBandGrayRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandGrayRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandGrayRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()
        self.mGrayBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mGrayBandComboBox)
        self.fixBandNames(self.mGrayBandComboBox)
        self.connectSliderWithBandComboBox(self.mGrayBandSlider, self.mGrayBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()

        self.gridLayout.addWidget(self.mGrayBandLabel, 0, 0)
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 4, Qt.AlignLeft)

        self.gridLayout.addWidget(self.mGrayBandSlider, 1, 1, 1, 2)
        self.gridLayout.addWidget(self.mGrayBandComboBox, 1, 3,1,2)

        self.gridLayout.addWidget(self.label, 2, 0)
        self.gridLayout.addWidget(self.mGradientComboBox, 2, 1, 1, 4)

        self.gridLayout.addWidget(self.mMinLabel, 3, 1)
        self.gridLayout.addWidget(self.mMinLineEdit, 3, 2)
        self.gridLayout.addWidget(self.mMaxLabel, 3, 3)
        self.gridLayout.addWidget(self.mMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementLabel, 4, 0)
        self.gridLayout.addWidget(self.mContrastEnhancementComboBox, 4, 1, 1 ,4)
        self.gridLayout.setSpacing(2)

        self.setLayoutItemVisibility(self.gridLayout, True)

        self.mDefaultRenderer = layer.renderer()


    def initActionButtons(self):
            wl, wlu = parseWavelength(self.rasterLayer())
            self.wavelengths = wl
            self.wavelengthUnit = wlu

            self.mBtnBar.setLayout(QHBoxLayout())
            self.mBtnBar.layout().addStretch()
            self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
            self.mBtnBar.layout().setSpacing(2)

            self.actionSetDefault = QAction('Default')
            self.actionSetRed = QAction('R')
            self.actionSetGreen = QAction('G')
            self.actionSetBlue = QAction('B')
            self.actionSetNIR = QAction('nIR')
            self.actionSetSWIR = QAction('swIR')

            self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
            self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
            self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
            self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
            self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
            self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


            def addBtnAction(action):
                btn = QToolButton()
                btn.setDefaultAction(action)
                self.mBtnBar.layout().addWidget(btn)
                self.insertAction(None, action)
                return btn

            self.btnDefault = addBtnAction(self.actionSetDefault)
            self.btnRed = addBtnAction(self.actionSetRed)
            self.btnGreen = addBtnAction(self.actionSetGreen)
            self.btnBlue = addBtnAction(self.actionSetRed)
            self.btnNIR = addBtnAction(self.actionSetNIR)
            self.btnSWIR = addBtnAction(self.actionSetSWIR)

            b = self.wavelengths is not None
            for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
                a.setEnabled(b)



class SingleBandPseudoColorRendererWidget(QgsSingleBandPseudoColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandPseudoColorRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandPseudoColorRendererWidget, self).__init__(layer, extent)

        self.gridLayout = self.layout()
        assert isinstance(self.gridLayout, QGridLayout)
        for i in range(self.gridLayout.count()):
            w = self.gridLayout.itemAt(i)
            w = w.widget()
            if isinstance(w, QWidget):
                setattr(self, w.objectName(), w)

        toReplace = [self.mBandComboBox,self.mMinLabel,self.mMaxLabel, self.mMinLineEdit, self.mMaxLineEdit ]
        for w in toReplace:
            self.gridLayout.removeWidget(w)
            w.setVisible(False)
        self.mBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mBandComboBox)
        self.fixBandNames(self.mBandComboBox)
        self.connectSliderWithBandComboBox(self.mBandSlider, self.mBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()
        grid = QGridLayout()
        grid.addWidget(self.mBtnBar,0,0,1,4, Qt.AlignLeft)
        grid.addWidget(self.mBandSlider, 1,0, 1,2)
        grid.addWidget(self.mBandComboBox, 1,2, 1,2)
        grid.addWidget(self.mMinLabel, 2, 0)
        grid.addWidget(self.mMinLineEdit, 2, 1)
        grid.addWidget(self.mMaxLabel, 2, 2)
        grid.addWidget(self.mMaxLineEdit, 2, 3)
        #grid.setContentsMargins(2, 2, 2, 2, )
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 2)
        grid.setSpacing(2)
        self.gridLayout.addItem(grid, 0,1,2,4)
        self.gridLayout.setSpacing(2)
        self.setLayoutItemVisibility(grid, True)


    def initActionButtons(self):

            wl, wlu = parseWavelength(self.rasterLayer())
            self.wavelengths = wl
            self.wavelengthUnit = wlu

            self.mBtnBar.setLayout(QHBoxLayout())
            self.mBtnBar.layout().addStretch()
            self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
            self.mBtnBar.layout().setSpacing(2)

            self.actionSetDefault = QAction('Default')
            self.actionSetRed = QAction('R')
            self.actionSetGreen = QAction('G')
            self.actionSetBlue = QAction('B')
            self.actionSetNIR = QAction('nIR')
            self.actionSetSWIR = QAction('swIR')

            self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
            self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
            self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
            self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
            self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
            self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


            def addBtnAction(action):
                btn = QToolButton()
                btn.setDefaultAction(action)
                self.mBtnBar.layout().addWidget(btn)
                self.insertAction(None, action)
                return btn

            self.btnDefault = addBtnAction(self.actionSetDefault)
            self.btnRed = addBtnAction(self.actionSetRed)
            self.btnGreen = addBtnAction(self.actionSetGreen)
            self.btnBlue = addBtnAction(self.actionSetRed)
            self.btnNIR = addBtnAction(self.actionSetNIR)
            self.btnSWIR = addBtnAction(self.actionSetSWIR)

            b = self.wavelengths is not None
            for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
                a.setEnabled(b)




class MultiBandColorRendererWidget(QgsMultiBandColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return MultiBandColorRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(MultiBandColorRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()

        self.mRedBandSlider = QSlider(Qt.Horizontal)
        self.mGreenBandSlider = QSlider(Qt.Horizontal)
        self.mBlueBandSlider = QSlider(Qt.Horizontal)

        self.mBandComboBoxes.extend([self.mRedBandComboBox, self.mGreenBandComboBox, self.mBlueBandComboBox])
        self.mSliders = [self.mRedBandSlider, self.mGreenBandSlider, self.mBlueBandSlider]
        nb = self.rasterLayer().dataProvider().bandCount()
        for cbox, slider in zip(self.mBandComboBoxes, self.mSliders):
            self.connectSliderWithBandComboBox(slider, cbox)


        self.fixBandNames(self.mRedBandComboBox)
        self.fixBandNames(self.mGreenBandComboBox)
        self.fixBandNames(self.mBlueBandComboBox)

        self.mBtnBar = QFrame()
        self.mBtnBar.setLayout(QHBoxLayout())
        self.initActionButtons()
        self.mBtnBar.layout().addStretch()
        self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
        self.mBtnBar.layout().setSpacing(2)

        #self.gridLayout.deleteLater()
#        self.gridLayout = newGrid
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 3)
        self.gridLayout.addWidget(self.mRedBandLabel, 1, 0)
        self.gridLayout.addWidget(self.mRedBandSlider, 1, 1)
        self.gridLayout.addWidget(self.mRedBandComboBox, 1, 2)
        self.gridLayout.addWidget(self.mRedMinLineEdit, 1, 3)
        self.gridLayout.addWidget(self.mRedMaxLineEdit, 1, 4)

        self.gridLayout.addWidget(self.mGreenBandLabel, 2, 0)
        self.gridLayout.addWidget(self.mGreenBandSlider, 2, 1)
        self.gridLayout.addWidget(self.mGreenBandComboBox, 2, 2)
        self.gridLayout.addWidget(self.mGreenMinLineEdit, 2, 3)
        self.gridLayout.addWidget(self.mGreenMaxLineEdit, 2, 4)

        self.gridLayout.addWidget(self.mBlueBandLabel, 3, 0)
        self.gridLayout.addWidget(self.mBlueBandSlider, 3, 1)
        self.gridLayout.addWidget(self.mBlueBandComboBox, 3, 2)
        self.gridLayout.addWidget(self.mBlueMinLineEdit, 3, 3)
        self.gridLayout.addWidget(self.mBlueMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmLabel, 4, 0, 1, 2)
        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmComboBox, 4, 2, 1, 3)

        self.setLayoutItemVisibility(self.gridLayout, True)


        self.mRedBandLabel.setText('R')
        self.mGreenBandLabel.setText('G')
        self.mBlueBandLabel.setText('B')

        self.mDefaultRenderer = layer.renderer()



    def initActionButtons(self):

        wl, wlu = parseWavelength(self.rasterLayer())
        self.wavelengths = wl
        self.wavelengthUnit = wlu

        self.actionSetDefault = QAction('Default')
        self.actionSetTrueColor = QAction('RGB')
        self.actionSetCIR = QAction('nIR')
        self.actionSet453 = QAction('swIR')

        self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
        self.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('R,G,B'))
        self.actionSetCIR.triggered.connect(lambda: self.setBandSelection('nIR,R,G'))
        self.actionSet453.triggered.connect(lambda: self.setBandSelection('nIR,swIR,R'))


        def addBtnAction(action):
            btn = QToolButton()
            btn.setDefaultAction(action)
            self.mBtnBar.layout().addWidget(btn)
            self.insertAction(None, action)
            return btn

        self.btnDefault = addBtnAction(self.actionSetDefault)
        self.btnTrueColor = addBtnAction(self.actionSetTrueColor)
        self.btnCIR = addBtnAction(self.actionSetCIR)
        self.btn453 = addBtnAction(self.actionSet453)

        b = self.wavelengths is not None
        for a in [self.actionSetCIR, self.actionSet453, self.actionSetTrueColor]:
            a.setEnabled(b)


def displayBandNames(provider_or_dataset, bands=None):
    results = None
    if isinstance(provider_or_dataset, QgsRasterLayer):
        return displayBandNames(provider_or_dataset.dataProvider())
    elif isinstance(provider_or_dataset, QgsRasterDataProvider):
        if provider_or_dataset.name() == 'gdal':
            ds = gdal.Open(provider_or_dataset.dataSourceUri())
            results = displayBandNames(ds, bands=bands)
        else:
            # same as in QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, provider_or_dataset.bandCount() + 1)
            for band in bands:
                result = provider_or_dataset.generateBandName(band)
                colorInterp ='{}'.format(provider_or_dataset.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    result += '({})'.format(colorInterp)
                results.append(result)

    elif isinstance(provider_or_dataset, gdal.Dataset):
        results = []
        if bands is None:
            bands = range(1, provider_or_dataset.RasterCount+1)
        for band in bands:
            b = provider_or_dataset.GetRasterBand(band)
            descr = b.GetDescription()
            if len(descr) == 0:
                descr = 'Band {}'.format(band)
            results.append(descr)

    return results

class SingleBandGrayRendererWidget(QgsSingleBandGrayRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandGrayRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandGrayRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()
        self.mGrayBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mGrayBandComboBox)
        self.fixBandNames(self.mGrayBandComboBox)
        self.connectSliderWithBandComboBox(self.mGrayBandSlider, self.mGrayBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()

        self.gridLayout.addWidget(self.mGrayBandLabel, 0, 0)
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 4, Qt.AlignLeft)

        self.gridLayout.addWidget(self.mGrayBandSlider, 1, 1, 1, 2)
        self.gridLayout.addWidget(self.mGrayBandComboBox, 1, 3,1,2)

        self.gridLayout.addWidget(self.label, 2, 0)
        self.gridLayout.addWidget(self.mGradientComboBox, 2, 1, 1, 4)

        self.gridLayout.addWidget(self.mMinLabel, 3, 1)
        self.gridLayout.addWidget(self.mMinLineEdit, 3, 2)
        self.gridLayout.addWidget(self.mMaxLabel, 3, 3)
        self.gridLayout.addWidget(self.mMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementLabel, 4, 0)
        self.gridLayout.addWidget(self.mContrastEnhancementComboBox, 4, 1, 1 ,4)
        self.gridLayout.setSpacing(2)

        self.setLayoutItemVisibility(self.gridLayout, True)

        self.mDefaultRenderer = layer.renderer()
        self.setFromRenderer(self.mDefaultRenderer)

    def initActionButtons(self):

        wl, wlu = parseWavelength(self.rasterLayer())
        self.wavelengths = wl
        self.wavelengthUnit = wlu

        self.mBtnBar.setLayout(QHBoxLayout())
        self.mBtnBar.layout().addStretch()
        self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
        self.mBtnBar.layout().setSpacing(2)

        self.actionSetDefault = QAction('Default')
        self.actionSetRed = QAction('R')
        self.actionSetGreen = QAction('G')
        self.actionSetBlue = QAction('B')
        self.actionSetNIR = QAction('nIR')
        self.actionSetSWIR = QAction('swIR')

        self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
        self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
        self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
        self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
        self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
        self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


        def addBtnAction(action):
            btn = QToolButton()
            btn.setDefaultAction(action)
            self.mBtnBar.layout().addWidget(btn)
            self.insertAction(None, action)
            return btn

        self.btnDefault = addBtnAction(self.actionSetDefault)
        self.btnBlue = addBtnAction(self.actionSetBlue)
        self.btnGreen = addBtnAction(self.actionSetGreen)
        self.btnRed = addBtnAction(self.actionSetRed)
        self.btnNIR = addBtnAction(self.actionSetNIR)
        self.btnSWIR = addBtnAction(self.actionSetSWIR)

        b = self.wavelengths is not None
        for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
            a.setEnabled(b)



class SingleBandPseudoColorRendererWidget(QgsSingleBandPseudoColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandPseudoColorRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandPseudoColorRendererWidget, self).__init__(layer, extent)

        #self.mColormapTreeWidget.setMinimumSize(QSize(1,1))

        self.gridLayout = self.layout().children()[0]
        assert isinstance(self.gridLayout, QGridLayout)
        for i in range(self.gridLayout.count()):
            w = self.gridLayout.itemAt(i)
            w = w.widget()
            if isinstance(w, QWidget):
                setattr(self, w.objectName(), w)

        toReplace = [self.mBandComboBox,self.mMinLabel,self.mMaxLabel, self.mMinLineEdit, self.mMaxLineEdit ]
        for w in toReplace:
            self.gridLayout.removeWidget(w)
            w.setVisible(False)
        self.mBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mBandComboBox)
        self.fixBandNames(self.mBandComboBox)
        self.connectSliderWithBandComboBox(self.mBandSlider, self.mBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()
        grid = QGridLayout()
        grid.addWidget(self.mBtnBar,0,0,1,4, Qt.AlignLeft)
        grid.addWidget(self.mBandSlider, 1,0, 1,2)
        grid.addWidget(self.mBandComboBox, 1,2, 1,2)
        grid.addWidget(self.mMinLabel, 2, 0)
        grid.addWidget(self.mMinLineEdit, 2, 1)
        grid.addWidget(self.mMaxLabel, 2, 2)
        grid.addWidget(self.mMaxLineEdit, 2, 3)
        #grid.setContentsMargins(2, 2, 2, 2, )
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 2)
        grid.setSpacing(2)
        self.gridLayout.addItem(grid, 0,1,2,4)
        self.gridLayout.setSpacing(2)
        self.setLayoutItemVisibility(grid, True)

        s = ""

    def initActionButtons(self):
            wl, wlu = parseWavelength(self.rasterLayer())
            self.wavelengths = wl
            self.wavelengthUnit = wlu

            self.mBtnBar.setLayout(QHBoxLayout())
            self.mBtnBar.layout().addStretch()
            self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
            self.mBtnBar.layout().setSpacing(2)

            self.actionSetDefault = QAction('Default')
            self.actionSetRed = QAction('R')
            self.actionSetGreen = QAction('G')
            self.actionSetBlue = QAction('B')
            self.actionSetNIR = QAction('nIR')
            self.actionSetSWIR = QAction('swIR')

            self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
            self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
            self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
            self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
            self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
            self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


            def addBtnAction(action):
                btn = QToolButton()
                btn.setDefaultAction(action)
                self.mBtnBar.layout().addWidget(btn)
                self.insertAction(None, action)
                return btn

            self.btnDefault = addBtnAction(self.actionSetDefault)
            self.btnBlue = addBtnAction(self.actionSetBlue)
            self.btnGreen = addBtnAction(self.actionSetGreen)
            self.btnRed = addBtnAction(self.actionSetRed)
            self.btnNIR = addBtnAction(self.actionSetNIR)
            self.btnSWIR = addBtnAction(self.actionSetSWIR)

            b = self.wavelengths is not None
            for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
                a.setEnabled(b)


class PalettedRendererWidget(QgsPalettedRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return PalettedRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(PalettedRendererWidget, self).__init__(layer, extent)

        #self.modifyGridLayout()

        self.fixBandNames(self.mBandComboBox)
        self.mTreeView.setMinimumSize(QSize(10,10))
        s = ""



class MultiBandColorRendererWidget(QgsMultiBandColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return MultiBandColorRendererWidget(layer, extent)


    def __init__(self, layer, extent):
        super(MultiBandColorRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()

        self.mRedBandSlider = QSlider(Qt.Horizontal)
        self.mGreenBandSlider = QSlider(Qt.Horizontal)
        self.mBlueBandSlider = QSlider(Qt.Horizontal)

        self.mBandComboBoxes.extend([self.mRedBandComboBox, self.mGreenBandComboBox, self.mBlueBandComboBox])
        self.mSliders = [self.mRedBandSlider, self.mGreenBandSlider, self.mBlueBandSlider]
        for cbox, slider in zip(self.mBandComboBoxes, self.mSliders):
            self.connectSliderWithBandComboBox(slider, cbox)


        self.fixBandNames(self.mRedBandComboBox)
        self.fixBandNames(self.mGreenBandComboBox)
        self.fixBandNames(self.mBlueBandComboBox)

        self.mBtnBar = QFrame()
        self.mBtnBar.setLayout(QHBoxLayout())
        self.initActionButtons()
        self.mBtnBar.layout().addStretch()
        self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
        self.mBtnBar.layout().setSpacing(2)

        #self.gridLayout.deleteLater()
#        self.gridLayout = newGrid
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 3)
        self.gridLayout.addWidget(self.mRedBandLabel, 1, 0)
        self.gridLayout.addWidget(self.mRedBandSlider, 1, 1)
        self.gridLayout.addWidget(self.mRedBandComboBox, 1, 2)
        self.gridLayout.addWidget(self.mRedMinLineEdit, 1, 3)
        self.gridLayout.addWidget(self.mRedMaxLineEdit, 1, 4)

        self.gridLayout.addWidget(self.mGreenBandLabel, 2, 0)
        self.gridLayout.addWidget(self.mGreenBandSlider, 2, 1)
        self.gridLayout.addWidget(self.mGreenBandComboBox, 2, 2)
        self.gridLayout.addWidget(self.mGreenMinLineEdit, 2, 3)
        self.gridLayout.addWidget(self.mGreenMaxLineEdit, 2, 4)

        self.gridLayout.addWidget(self.mBlueBandLabel, 3, 0)
        self.gridLayout.addWidget(self.mBlueBandSlider, 3, 1)
        self.gridLayout.addWidget(self.mBlueBandComboBox, 3, 2)
        self.gridLayout.addWidget(self.mBlueMinLineEdit, 3, 3)
        self.gridLayout.addWidget(self.mBlueMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmLabel, 4, 0, 1, 2)
        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmComboBox, 4, 2, 1, 3)

        self.setLayoutItemVisibility(self.gridLayout, True)


        self.mRedBandLabel.setText('R')
        self.mGreenBandLabel.setText('G')
        self.mBlueBandLabel.setText('B')

        self.mDefaultRenderer = layer.renderer()



    def initActionButtons(self):

        wl, wlu = parseWavelength(self.rasterLayer())
        self.wavelengths = wl
        self.wavelengthUnit = wlu

        self.actionSetDefault = QAction('Default')
        self.actionSetTrueColor = QAction('RGB')
        self.actionSetCIR = QAction('nIR')
        self.actionSet453 = QAction('swIR')

        self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
        self.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('R,G,B'))
        self.actionSetCIR.triggered.connect(lambda: self.setBandSelection('nIR,R,G'))
        self.actionSet453.triggered.connect(lambda: self.setBandSelection('nIR,swIR,R'))


        def addBtnAction(action):
            btn = QToolButton()
            btn.setDefaultAction(action)
            self.mBtnBar.layout().addWidget(btn)
            self.insertAction(None, action)
            return btn

        self.btnDefault = addBtnAction(self.actionSetDefault)
        self.btnTrueColor = addBtnAction(self.actionSetTrueColor)
        self.btnCIR = addBtnAction(self.actionSetCIR)
        self.btn453 = addBtnAction(self.actionSet453)

        b = self.wavelengths is not None
        for a in [self.actionSetCIR, self.actionSet453, self.actionSetTrueColor]:
            a.setEnabled(b)


class MapView(QObject):

    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibility = pyqtSignal(bool)
    #sigVectorVisibility = pyqtSignal(bool)
    #sigRasterVisibility = pyqtSignal(bool)

    sigTitleChanged = pyqtSignal(str)
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)


    sigVectorLayerChanged = pyqtSignal()

    sigShowProfiles = pyqtSignal(SpatialPoint, MapCanvas, str)

    def __init__(self, mapViewCollectionDock, name='Map View', recommended_bands=None, parent=None):
        super(MapView, self).__init__()
        assert isinstance(mapViewCollectionDock, MapViewCollectionDock)

        self.ui = MapViewUI(mapViewCollectionDock.stackedWidget)
        self.ui.show()
        self.ui.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.ui.cbQgsVectorLayer.layerChanged.connect(self.setVectorLayer)


        self.ui.tbName.textChanged.connect(self.sigTitleChanged.emit)
        from timeseriesviewer.crosshair import getCrosshairStyle
        self.ui.actionSetCrosshairStyle.triggered.connect(
            lambda : self.onCrosshairChanged(getCrosshairStyle(
                parent=self.ui,
                crosshairStyle=self.crosshairStyle()))
        )

        self.mapViewCollection = mapViewCollectionDock
        self.mSensorViews = collections.OrderedDict()

        self.mVectorLayer = None
        self.setVectorLayer(None)

        self.mIsVisible = True

        self.ui.actionToggleVectorVisibility.toggled.connect(self.setVectorVisibility)
        self.ui.actionToggleRasterVisibility.toggled.connect(self.setRasterVisibility)
        self.ui.actionToggleCrosshairVisibility.toggled.connect(self.onCrosshairChanged)
        self.ui.actionToggleMapViewHidden.toggled.connect(lambda b: self.setIsVisible(not b))

        self.ui.actionToggleVectorVisibility.setChecked(False)
        self.ui.actionToggleRasterVisibility.setChecked(True)

        self.ui.actionSetVectorStyle.triggered.connect(self.setVectorLayerStyle)

        for sensor in self.mapViewCollection.TS.sensors():
            self.addSensor(sensor)

        self.setTitle(name)
        #forward actions with reference to this band view
    def dummy(self, *args):
        print(args)
    def setIsVisible(self, b):
        assert isinstance(b, bool)

        changed = False

        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            if not mapCanvas.isVisible() == b:
                changed = True
                mapCanvas.setVisible(b)

        if self.ui.actionToggleMapViewHidden.isChecked() == b:
            self.ui.actionToggleMapViewHidden.setChecked(not b)

        if changed:
            self.sigMapViewVisibility.emit(b)


    def isVisible(self):
        return not self.ui.actionToggleMapViewHidden.isChecked()

    def mapCanvases(self):
        m = []
        for sensor, sensorView in self.mSensorViews.items():
            m.extend(sensorView.mapCanvases())
        return m




    def setVectorLayerStyle(self, *args):
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            d = QgsRendererPropertiesDialog(self.mVectorLayer, QgsStyle.defaultStyle())

            mc = self.mapCanvases()
            if len(mc) > 0:
                d.setMapCanvas(mc[0])
            d.exec_()
            s = ""


    def vectorLayerRenderer(self):
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.renderer()
        return None


    def setVectorLayerRenderer(self, renderer):
        if isinstance(renderer, QgsFeatureRenderer) and \
            isinstance(self.mVectorLayer, QgsVectorLayer):
            self.mVectorLayer.setRendererV2(renderer)

    def setVectorLayer(self, lyr:QgsVectorLayer):
        """
        Sets a QgsVectorLayer that is shown on top of all other QgsRasterLayers
        :param lyr:
        :return:
        """
        b = False
        #remove last layer
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            for mapCanvas in self.mapCanvases():
                if self.mVectorLayer in mapCanvas.mLayerSources.remove(self.mVectorLayer):
                    mapCanvas.mLayerSources.remove(self.mVectorLayer)
                    b = True
        # add new layer
        if isinstance(lyr, QgsVectorLayer) and self.ui.gbVectorRendering.isChecked():
            b = True
            #add vector layer
            self.mVectorLayer = lyr
            self.mVectorLayer.rendererChanged.connect(self.sigVectorLayerChanged)

            for mapCanvas in self.mapCanvases():
                assert isinstance(mapCanvas, MapCanvas)
                mapCanvas.mapLayerModel().addMapLayerSources([self.mVectorLayer])
        if b:
            self.sigVectorLayerChanged.emit()

    def applyStyles(self):
        """Applies all style changes to all sensor views."""
        for sensorView in self.mSensorViews.values():
            sensorView.applyStyle()

    def setTitle(self, title:str):
        """
        Sets the widget title
        :param title: str
        """
        old = self.title()
        if old != title:
            self.ui.tbName.setText(title)


    def title(self)->str:
        """Returns the title."""
        return self.ui.tbName.text()

    def refreshMapView(self, sensor=None):

        if isinstance(sensor, SensorInstrument):
            sensorSettings = [self.mSensorViews[sensor]]
        else:
            #update all sensors
            sensorSettings = self.mSensorViews.values()

        for renderSetting in sensorSettings:
            assert isinstance(renderSetting, MapViewRenderSettings)
            renderSetting.applyStyle()

        for mapCanvas in self.mapCanvases():
            if isinstance(mapCanvas, MapCanvas):
                mapCanvas.refresh()

    def setCrosshairStyle(self, crosshairStyle:CrosshairStyle):
        """
        Seths the CrosshairStyle of this MapVaie
        :param crosshairStyle: CrosshairStyle
        """
        self.onCrosshairChanged(crosshairStyle)

    def setHighlighted(self, b=True, timeout=1000):
        """
        Activates or deactivates a red-line border of the MapCanvases
        :param b: True | False to activate / deactivate the highlighted lines-
        :param timeout: int, milliseconds how long the highlighted frame should appear
        """
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



    def rasterVisibility(self)->bool:
        """
        Returns whether raster images should be visible.
        :return: bool
        """
        return self.ui.actionToggleRasterVisibility.isChecked()

    def vectorVisibility(self)->bool:
        """
        Returns whether vector images should be visible.
        :return: bool
        """
        return self.ui.actionToggleVectorVisibility.isChecked()

    def setRasterVisibility(self, b:bool):
        """
        Sets visibility of rasters.
        :param b: bool
        """
        assert isinstance(b, bool)


        self.ui.actionToggleRasterVisibility.setChecked(b)

        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setLayerVisibility(QgsRasterLayer, b)

    def setVectorVisibility(self, b:bool):
        """
        Sets the visibility of vector layers.
        :param b:
        :return:
        """
        assert isinstance(b, bool)
        self.mVectorsVisible = b
        self.ui.actionToggleVectorVisibility.setChecked(b)

        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setLayerVisibility(QgsVectorLayer, b)


    def removeSensor(self, sensor:SensorInstrument):
        assert sensor in self.mSensorViews.keys()
        self.mSensorViews.pop(sensor)
        self.ui.removeSensor(sensor)
        return True

    def hasSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        return sensor in self.mSensorViews.keys()

    def registerMapCanvas(self, sensor:SensorInstrument, mapCanvas:MapCanvas):
        """
        Registers a new MapCanvas to this MapView
        :param sensor:
        :param mapCanvas:
        :return:
        """
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        assert isinstance(sensor, SensorInstrument)

        mapViewRenderSettings = self.mSensorViews[sensor]
        assert isinstance(mapViewRenderSettings, MapViewRenderSettings)
        mapViewRenderSettings.registerMapCanvas(mapCanvas)
        mapCanvas.setMapView(self)

        #register signals sensor specific signals
        mapCanvas.sigCrosshairVisibilityChanged.connect(self.onCrosshairChanged)
        mapCanvas.sigCrosshairStyleChanged.connect(self.onCrosshairChanged)

        #register non-sensor specific signals for this mpa view
        self.sigMapViewVisibility.connect(mapCanvas.refresh)
        self.sigVectorLayerChanged.connect(mapCanvas.refresh)
#        self.sigVectorVisibility.connect(mapCanvas.refresh)

    def crosshairStyle(self)->CrosshairStyle:
        """
        Returns the CrosshairStyle
        :return:
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            style = c.crosshairStyle()
            if isinstance(style, CrosshairStyle):
                return style
        return None

    def onCrosshairChanged(self, obj):
        """
        Synchronizes all crosshair positions. Takes care of CRS differences.
        :param spatialPoint: SpatialPoint of the new Crosshair position
        """
        from timeseriesviewer.crosshair import CrosshairStyle

        srcCanvas = self.sender()
        if isinstance(srcCanvas, MapCanvas):
            dstCanvases = [c for c in self.mapCanvases() if c != srcCanvas]
        else:
            dstCanvases = [c for c in self.mapCanvases()]

        if isinstance(obj, bool):
            for mapCanvas in dstCanvases:
                mapCanvas.setCrosshairVisibility(obj, emitSignal=False)

        if isinstance(obj, CrosshairStyle):
            for mapCanvas in dstCanvases:
                mapCanvas.setCrosshairStyle(obj, emitSignal=False)


    def addSensor(self, sensor):
        """
        :param sensor:
        :return:
        """
        if isinstance(sensor, SensorInstrument) and sensor not in self.mSensorViews.keys():

            #w.showSensorName(False)
            w = self.ui.addSensor(sensor)
            w.sigRendererChanged.connect(lambda s=sensor : self.refreshMapView(sensor=s))
            #w.sigSensorRendererChanged.connect(self.onSensorRenderingChanged)
            self.mSensorViews[sensor] = w
            s  =""

    """
    def onSensorRenderingChanged(self, renderer):
        sensorSettings = self.sender()
        assert isinstance(sensorSettings, MapViewSensorSettings)
        for mapCanvas in sensorSettings.mapCanvases():
            mapCanvas.setRenderer(renderer)
            #mapCanvas.refresh()
    """
    def sensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.mSensorViews[sensor]

def displayBandNames(provider_or_dataset, bands=None):
    results = None
    if isinstance(provider_or_dataset, QgsRasterLayer):
        return displayBandNames(provider_or_dataset.dataProvider())
    elif isinstance(provider_or_dataset, QgsRasterDataProvider):
        if provider_or_dataset.name() == 'gdal':
            ds = gdal.Open(provider_or_dataset.dataSourceUri())
            results = displayBandNames(ds, bands=bands)
        else:
            # same as in QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, provider_or_dataset.bandCount() + 1)
            for band in bands:
                result = provider_or_dataset.generateBandName(band)
                colorInterp ='{}'.format(provider_or_dataset.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    result += '({})'.format(colorInterp)
                results.append(result)

    elif isinstance(provider_or_dataset, gdal.Dataset):
        results = []
        if bands is None:
            bands = range(1, provider_or_dataset.RasterCount+1)
        for band in bands:
            b = provider_or_dataset.GetRasterBand(band)
            descr = b.GetDescription()
            if len(descr) == 0:
                descr = 'Band {}'.format(band)
            results.append(descr)

    return results


class RasterDataProviderMockup(QgsRasterDataProvider):

    def __init__(self):
        super(RasterDataProviderMockup, self).__init__('')




class MapViewRenderSettings(QgsCollapsibleGroupBox, loadUI('mapviewrendersettings.ui')):


    LUT_RENDERER = {QgsMultiBandColorRenderer:QgsMultiBandColorRendererWidget,
                    QgsSingleBandGrayRenderer:QgsSingleBandGrayRendererWidget,
                    QgsSingleBandPseudoColorRenderer:QgsSingleBandPseudoColorRendererWidget,
                    QgsPalettedRasterRenderer:QgsPalettedRendererWidget}
    LUT_RENDERER[QgsMultiBandColorRenderer]=MultiBandColorRendererWidget
    LUT_RENDERER[QgsSingleBandPseudoColorRenderer]=SingleBandPseudoColorRendererWidget
    LUT_RENDERER[QgsSingleBandGrayRenderer]=SingleBandGrayRendererWidget
    LUT_RENDERER[QgsPalettedRasterRenderer] = PalettedRendererWidget

    sigRendererChanged = pyqtSignal()
    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(MapViewRenderSettings, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect

        self.setupUi(self)

        QApplication.clipboard().dataChanged.connect(self.onClipboardChanged)

        assert isinstance(sensor, SensorInstrument)
        self.mSensor = sensor
        self.mSensor.sigNameChanged.connect(self.onSensorNameChanged)
        self.setTitle(self.mSensor.name())

        from timeseriesviewer.models import OptionListModel, Option
        rasterRendererModel = OptionListModel()
        #rasterRendererModel.addOption(Option(QgsMultiBandColorRendererWidget, name='multibandcolor (QGIS)', mRenderType = QgsMultiBandColorRenderer))
        #rasterRendererModel.addOption(Option(QgsPalettedRendererWidget, name='paletted (QGIS)', mRenderType = QgsPalettedRasterRenderer))
        #rasterRendererModel.addOption(Option(QgsSingleBandGrayRendererWidget, name='singlegray (QGIS)', mRenderType = QgsSingleBandGrayRenderer))
        #rasterRendererModel.addOption(Option(QgsSingleBandPseudoColorRendererWidget, name='singlebandpseudocolor (QGIS)', mRenderType = QgsSingleBandPseudoColorRenderer))

        rasterRendererModel.addOption(Option(MultiBandColorRendererWidget, name='Multibandcolor', mRenderType=QgsMultiBandColorRenderer))
        rasterRendererModel.addOption(Option(SingleBandGrayRendererWidget, name='Singlegray', mRenderType=QgsSingleBandGrayRenderer))
        rasterRendererModel.addOption(Option(SingleBandPseudoColorRendererWidget, name='Singleband Pseudocolor', mRenderType=QgsSingleBandPseudoColorRenderer))
        rasterRendererModel.addOption(Option(PalettedRendererWidget, name='Paletted', mRenderType=QgsPalettedRasterRenderer))
        self.mRasterRendererModel = rasterRendererModel

        self.cbRenderType.setModel(self.mRasterRendererModel)
        assert isinstance(self.stackedWidget, QStackedWidget)

        self.mMockupCanvas = QgsMapCanvas(parent=parent)
        self.mMockupCanvas.setVisible(False)
        self.mMockupRasterLayer = self.mSensor.mockupLayer()
        self.mMockupCanvas.setLayers([self.mMockupRasterLayer])
        for func in rasterRendererModel.optionValues():

            #extent = self.canvas.extent()
            #w = func.create(self.mMockupRasterLayer, self.mMockupRasterLayer.extent())
            w = func(self.mMockupRasterLayer, self.mMockupRasterLayer.extent())
            #w = func(QgsRasterLayer(), QgsRectangle())

            w.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))
            #w.sizeHint = lambda : QSize(300, 50)
            w.setMapCanvas(self.mMockupCanvas)

            self.stackedWidget.addWidget(w)

        self.mMapCanvases = []
        self.initActions()

    def initActions(self):


        self.btnPasteStyle.setDefaultAction(self.actionPasteStyle)
        self.btnCopyStyle.setDefaultAction(self.actionCopyStyle)
        self.btnApplyStyle.setDefaultAction(self.actionApplyStyle)

        clipboardRenderer = rendererFromXml(QApplication.clipboard().mimeData())
        self.actionPasteStyle.setEnabled(isinstance(clipboardRenderer, QgsRasterRenderer))
        self.actionPasteStyle.triggered.connect(self.pasteStyleFromClipboard)
        self.actionCopyStyle.triggered.connect(self.pasteStyleToClipboard)
        self.actionApplyStyle.triggered.connect(self.applyStyle)

    def mapCanvases(self):
        return self.mMapCanvases[:]

    def registerMapCanvas(self, mapCanvas):

        assert isinstance(mapCanvas, MapCanvas)
        self.mMapCanvases.append(mapCanvas)
        mapCanvas.sigChangeSVRequest.connect(self.onMapCanvasRendererChangeRequest)

    def onMapCanvasRendererChangeRequest(self, mapCanvas, renderer):
        self.setRasterRenderer(renderer)
        self.applyStyle()
        s = ""

    def onSensorNameChanged(self, newName):
        self.setTitle(self.mSensor.name())
        self.actionApplyStyle.setToolTip('Apply style to all map view images from "{}"'.format(self.mSensor.name()))


    def currentRenderWidget(self):
        """
        Returns the current QgsRasterRendererWidget
        :return: QgsRasterRendererWidget
        """
        return self.stackedWidget.currentWidget()


    def setRasterRenderer(self, renderer):
        assert isinstance(renderer, QgsRasterRenderer)
        assert isinstance(self.stackedWidget, QStackedWidget)

        self.mMockupRasterLayer.setRenderer(renderer)

        #find the widget class that fits
        cls = None

        for option in self.mRasterRendererModel:
            if type(renderer) == option.mRenderType:
                cls = option.value()
                break
        if cls == None:
            return

        widgets = []
        for i in range(self.stackedWidget.count()):
            w = self.stackedWidget.widget(i)
            if isinstance(w, cls):
                widgets.append(w)

        if len(widgets) > 0:
            for w in widgets:
                assert isinstance(w, QgsRasterRendererWidget)

                #w.setRasterLayer(self.mMockupRasterLayer)
                #w.setFromRenderer(cloneRenderer(renderer))
                w.setFromRenderer(renderer)
                #w.doComputations()

            w = widgets[0]
            self.stackedWidget.setCurrentWidget(w)

            self.cbRenderType.setCurrentIndex(self.stackedWidget.currentIndex())


    def rasterRenderer(self):

        return self.stackedWidget.currentWidget().renderer()


    def apply(self):

        mRendererWidget = self.currentRenderWidget()
        mRendererWidget.doComputations()

    def onClipboardChanged(self):
        mimeData = QApplication.clipboard().mimeData()
        renderer = rendererFromXml(mimeData)
        b = isinstance(renderer, QgsRasterRenderer)
        #if b == False:
        #    print(mimeData.formats())
        #    s = ""
        self.actionPasteStyle.setEnabled(b)



    def pasteStyleFromClipboard(self):
        mimeData = QApplication.clipboard().mimeData()
        renderer = rendererFromXml(mimeData)
        if isinstance(renderer, QgsRasterRenderer):
            self.setRasterRenderer(renderer)

    def pasteStyleToClipboard(self):
        xml = rendererToXml(self.rasterRenderer())
        assert isinstance(xml, QDomDocument)
        md = QMimeData()
        #['application/qgis.style', 'text/plain']

        md.setData('application/qgis.style', xml.toByteArray())
        md.setData('text/plain', xml.toByteArray())
        QApplication.clipboard().setMimeData(md)

    def applyStyle(self, *args):
        r = self.rasterRenderer()
        if isinstance(r, QgsRasterRenderer):
            for mapCanvas in self.mapCanvases():
                assert isinstance(mapCanvas, MapCanvas)
                mapCanvas.addToRefreshPipeLine(MapCanvas.Command.RefreshRenderer)




RENDER_CLASSES = {}
RENDER_CLASSES['rasterrenderer'] = {
    'singlebandpseudocolor': QgsSingleBandPseudoColorRenderer,
    'singlebandgray': QgsSingleBandGrayRenderer,
    'paletted': QgsPalettedRasterRenderer,
    'multibandcolor': QgsMultiBandColorRenderer,
    'hillshade': QgsHillshadeRenderer
}
RENDER_CLASSES['renderer-v2'] = {
    'categorizedSymbol':QgsCategorizedSymbolRenderer,
    'singleSymbol':QgsSingleSymbolRenderer
}




def rendererToXml(renderer):
    """
    Returns a renderer XML representation
    :param renderer: QgsRasterRender | QgsFeatureRenderer
    :return: QDomDocument
    """
    doc = QDomDocument()
    err = ''
    if isinstance(renderer, QgsRasterRenderer):
        #create a dummy raster layer
        import uuid
        from timeseriesviewer.virtualrasters import write_vsimem, read_vsimem
        xml = """<VRTDataset rasterXSize="1" rasterYSize="1">
                  <GeoTransform>  0.0000000000000000e+00,  1.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00, -1.0000000000000000e+00</GeoTransform>
                  <VRTRasterBand dataType="Float32" band="1">
                    <Metadata>
                      <MDI key="STATISTICS_MAXIMUM">0</MDI>
                      <MDI key="STATISTICS_MEAN">0</MDI>
                      <MDI key="STATISTICS_MINIMUM">0</MDI>
                      <MDI key="STATISTICS_STDDEV">0</MDI>
                    </Metadata>
                    <Description>Band 1</Description>
                    <Histograms>
                      <HistItem>
                        <HistMin>0</HistMin>
                        <HistMax>0</HistMax>
                        <BucketCount>1</BucketCount>
                        <IncludeOutOfRange>0</IncludeOutOfRange>
                        <Approximate>0</Approximate>
                        <HistCounts>0</HistCounts>
                      </HistItem>
                    </Histograms>
                  </VRTRasterBand>
                </VRTDataset>
                """
        path = '/vsimem/{}.vrt'.format(uuid.uuid4())
        drv = gdal.GetDriverByName('VRT')
        assert isinstance(drv, gdal.Driver)
        write_vsimem(path, xml)
        lyr = QgsRasterLayer(path)
        assert lyr.isValid()
        lyr.setRenderer(renderer.clone())
        lyr.exportNamedStyle(doc)
        #remove dummy raster layer
        lyr = None
        drv.Delete(path)

    elif isinstance(renderer, QgsFeatureRenderer):
        #todo: distinguish vector type from requested renderer
        lyr = QgsVectorLayer('Point?crs=epsg:4326&field=id:integer', 'dummy', 'memory')
        lyr.setRenderer(renderer.clone())
        lyr.exportNamedStyle(doc)
        lyr = None
    else:
        raise NotImplementedError()


    return doc


def rendererFromXml(xml):
    """
    Reads a string `text` and returns the first QgsRasterRenderer or QgsFeatureRenderer (if defined).
    :param text:
    :return:
    """

    if isinstance(xml, QMimeData):
        for format in ['application/qgis.style', 'text/plain']:
            if format in xml.formats():
                dom  = QDomDocument()
                dom.setContent(xml.data(format))
                return rendererFromXml(dom)
        return None

    elif isinstance(xml, str):
        dom = QDomDocument()
        dom.setContent(xml)
        return rendererFromXml(dom)

    assert isinstance(xml, QDomDocument)
    root = xml.documentElement()
    for baseClass, renderClasses in RENDER_CLASSES.items():
        elements = root.elementsByTagName(baseClass)
        if elements.count() > 0:
            elem = elements.item(0).toElement()
            typeName = elem.attributes().namedItem('type').nodeValue()
            if typeName in renderClasses.keys():
                rClass = renderClasses[typeName]
                if baseClass == 'rasterrenderer':

                    return rClass.create(elem, DUMMY_RASTERINTERFACE)
                elif baseClass == 'renderer-v2':
                    context = QgsReadWriteContext()
                    return rClass.load(elem, context)
                    #return rClass.create(elem)
            else:
                print(typeName)
                s =""
    return None





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
                if w.isVisible():
                    total.setWidth(max([total.width(), ws.width()]))
                    total.setHeight(total.height() +  ws.height())
            return total

        baseSize = totalHeight(widgets)
        if baseSize.width() == 0:
            for o in others:
                baseSize.setWidth(9999)
        s = QSize(baseSize.width() + m.left() + m.right(),
                  baseSize.height() + m.top() + m.bottom())
        #print(s)
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

    def __init__(self, timeSeriesDatum:TimeSeriesDatum, stv, parent=None):
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
        self.mSensor = self.TSD.mSensor
        self.mSensor.sigNameChanged.connect(lambda :self.setColumnInfo())
        self.TSD.sigVisibilityChanged.connect(self.setVisibility)
        self.setColumnInfo()
        self.MVC = stv.MVC
        self.DVC = stv.DVC
        self.mMapCanvases = dict()
        self.mRenderState = dict()

    def setColumnInfo(self):

        labelTxt = '{}\n{}'.format(str(self.TSD.mDate), self.TSD.mSensor.name())
        tooltip = '\n'.join([tss.uri()for tss in self.TSD.sources()])

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

    def removeMapView(self, mapView):
        canvas = self.mMapCanvases.pop(mapView)
        self.ui.layout().removeWidget(canvas)
        canvas.close()

    def mapCanvases(self)->list:
        """
        Retuns the MapCanvases of this DataView
        :return: [list-of-MapCanvases]
        """
        return self.mMapCanvases.values()

    def refresh(self):
        """
        Refreshes the MapCanvases in this DatumView, if they are not hidden behind a scroll area.
        """
        if self.ui.isVisible():
            for c in self.mapCanvases():
                if c.isVisible():
                    c.refresh()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)
        from timeseriesviewer.mapcanvas import MapCanvas

        mapCanvas = MapCanvas(self.ui)
        mapCanvas.setObjectName('MapCanvas {} {}'.format(mapView.title(), self.TSD.mDate))

        self.registerMapCanvas(mapView, mapCanvas)
        mapCanvas.setMapView(mapView)
        mapCanvas.setTSD(self.TSD)

        #mapCanvas.setMapView(mapView)
        mapView.registerMapCanvas(self.mSensor, mapCanvas)
        self.STV.registerMapCanvas(mapCanvas)
        mapCanvas.renderComplete.connect(lambda : self.onRenderingChange(False))
        mapCanvas.renderStarting.connect(lambda : self.onRenderingChange(True))

        #mapCanvas.sigMapRefreshed[float, float].connect(
        #    lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('Map {}'.format(self.mSensor.name()), dt))
        #mapCanvas.sigMapRefreshed.connect(
        #    lambda dt: self.STV.TSV.ui.dockSystemInfo.addTimeDelta('All Sensors', dt))

    def showLoading(self, b):
        if b:
            self.ui.progressBar.setRange(0, 0)
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
        renderFlags = [m.renderFlag() for m in self.mMapCanvases.values()]
        drawFlags = [m.isDrawing() for m in self.mMapCanvases.values()]
#        print((renderFlags, drawFlags))
        isLoading = any(renderFlags)

        self.showLoading(isLoading)

        s = ""

    def registerMapCanvas(self, mapView, mapCanvas):

        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        assert isinstance(mapView, MapView)
        self.mMapCanvases[mapView] = mapCanvas
        mapCanvas.setVisible(mapView.isVisible())


        #mapView.sigTitleChanged.connect(lambda title : mapCanvas.setSaveFileName('{}_{}'.format(self.TSD.date, title)))
        mapCanvas.mapLayerModel().addMapLayerSources(self.TSD.qgsMimeDataUtilsUris())

        #self.ui.layout().insertWidget(self.wOffset + len(self.mapCanvases), mapCanvas)
        self.ui.layout().insertWidget(self.ui.layout().count() - 1, mapCanvas)
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
            QApplication.clipboard().setText(self.TSD.mSensor.name())
        if key == 'copy_date':
            QApplication.clipboard().setText(str(self.TSD.date()))
        if key == 'copy_path':
            QApplication.clipboard().setText('\n'.join(self.TSD.sourceUris()))

    def __lt__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD < other.TSD

    def __eq__(self, other):
        """
        :param other:
        :return:
        """
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


        #self.scrollArea.sigResized.connect(self.refresh())
        #self.scrollArea.horizontalScrollBar().valueChanged.connect(self.mRefreshTimer.start)


        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.timeSeries()
        self.ui.dockMapViews.setTimeSeries(self.TS)
        self.targetLayout = self.ui.scrollAreaSubsetContent.layout()



        #self.MVC = MapViewCollection(self)
        #self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.MVC = self.ui.dockMapViews
        assert isinstance(self.MVC, MapViewCollectionDock)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)
        self.MVC.sigMapViewAdded.connect(self.onMapViewAdded)
        self.vectorOverlay = None

        self.DVC = DateViewCollection(self)
        self.DVC.sigResizeRequired.connect(self.adjustScrollArea)
        #self.DVC.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        #self.DVC.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        #self.timeSeriesDateViewCollection.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        self.TS.sigTimeSeriesDatesAdded.connect(self.DVC.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.DVC.removeDates)
        #add dates, if already existing
        self.DVC.addDates(self.TS[:])
        if len(self.TS) > 0:
            self.setSpatialExtent(self.TS.maxSpatialExtent())
        #self.setSubsetSize(QSize(100,50))

        self.mMapRefreshTimer = QTimer(self)
        self.mMapRefreshTimer.timeout.connect(self.timedCanvasRefresh)
        self.mMapRefreshTimer.setInterval(500)
        self.mMapRefreshTimer.start()
        self.mNumberOfHiddenMapsToRefresh = 2



    def timedCanvasRefresh(self, *args, force:bool=False):
        #do refresh maps

        assert isinstance(self.scrollArea, MapViewScrollArea)

        visibleMaps = [m for m in self.mapCanvases() if m.isVisibleToViewport()]

        hiddenMaps = sorted([m for m in self.mapCanvases() if not m.isVisibleToViewport()],
                            key = lambda c : self.scrollArea.distanceToCenter(c) )

        n = 0
        #redraw all visible maps
        for c in visibleMaps:
            assert isinstance(c, MapCanvas)
            c.timedRefresh()
            n += 1

        if n < 10:
            #refresh up to mNumberOfHiddenMapsToRefresh maps which are not visible to the user
            i = 0
            for c in hiddenMaps:
                assert isinstance(c, MapCanvas)
                c.timedRefresh()
                i += 1
                if i >= self.mNumberOfHiddenMapsToRefresh and not force:
                    break






    def mapViewFromCanvas(self, mapCanvas:MapCanvas)->MapView:
        """
        Returns the MapView a mapCanvas belongs to
        :param mapCanvas: MapCanvas
        :return: MapView
        """
        for mapView in self.MVC:
            assert isinstance(mapView, MapView)
            if mapCanvas in mapView.mapCanvases():
                return mapView
        return None

    def onMapViewAdded(self, *args):
        self.adjustScrollArea()
        s = ""
    def createMapView(self):
        self.MVC.createMapView()

    def registerMapCanvas(self, mapCanvas:MapCanvas):
        """
        Connects a MapCanvas and its signals
        :param mapCanvas: MapCanvas
        """
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)

        mapCanvas.setMapLayerStore(self.TSV.mMapLayerStore)
        self.mMapCanvases.append(mapCanvas)

        #set general canvas properties
        mapCanvas.setFixedSize(self.mSize)
        mapCanvas.setDestinationCrs(self.mCRS)
        mapCanvas.setSpatialExtent(self.mSpatialExtent)

        #register on map canvas signals
        def onChanged(e, mapCanvas0=None):
            self.setSpatialExtent(e, mapCanvas0=mapCanvas0)
        #mapCanvas.sigSpatialExtentChanged.connect(lambda e: self.setSpatialExtent(e, mapCanvas0=mapCanvas))
        mapCanvas.sigSpatialExtentChanged.connect(lambda e: onChanged(e, mapCanvas0=mapCanvas))
        mapCanvas.sigCrosshairPositionChanged.connect(self.onCrosshairChanged)

    def onCrosshairChanged(self, spatialPoint:SpatialPoint):
        """
        Synchronizes all crosshair positions. Takes care of CRS differences.
        :param spatialPoint: SpatialPoint of new Crosshair position
        """
        from timeseriesviewer.crosshair import CrosshairStyle

        srcCanvas = self.sender()
        if isinstance(srcCanvas, MapCanvas):
            dstCanvases = [c for c in self.mapCanvases() if c != srcCanvas]
        else:
            dstCanvases = [c for c in self.mapCanvases()]

        if isinstance(spatialPoint, SpatialPoint):
            for mapCanvas in dstCanvases:
                mapCanvas.setCrosshairPosition(spatialPoint, emitSignal=False)


    def setCrosshairStyle(self, crosshairStyle:CrosshairStyle):
        """
        Sets a crosshair style to all map canvas
        :param crosshairStyle: CrosshairStyle

        """
        for mapView in self.mapViews():
            assert isinstance(mapView, MapView)
            mapView.setCrosshairStyle(crosshairStyle)


    def setCrosshairVisibility(self, b:bool):
        assert isinstance(b, bool)
        self.onCrosshairChanged(b)


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

    def mapSize(self):
        return QSize(self.mSize)


    def refresh(self):
        """
        Refreshes all visible MapCanvases
        """
        for c in self.mapCanvases():
            assert isinstance(c, MapCanvas)
            c.refresh()

        #self.mMapRefreshTimer.stop()

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
        if nY > 0 and nX > 0:
                s = tsdViews[0].ui.sizeHint().height()
                s = s + margins.top() + margins.bottom()
                sizeY = s

            #s = tsdViews[0].ui.sizeHint()
            #s = QSize(nX * (s.width() + spacing) + margins.left() + margins.right(),
            #          s.height() + margins.top() + margins.bottom())

        #print(sizeX, sizeY)
        self.targetLayout.parentWidget().resize(QSize(sizeX, sizeY))

    def setMapTool(self, mapToolKey, *args, **kwds):
        # filter map tools
        self.mMapToolActivator = self.sender()
        del self.mMapTools[:]

        from timeseriesviewer.maptools import MapTools, CursorLocationMapTool, SpectralProfileMapTool, TemporalProfileMapTool
        for canvas in self.mMapCanvases:
            mt = None
            if mapToolKey in MapTools.mapToolKeys():
                mt = MapTools.create(mapToolKey, canvas, *args, **kwds)

            if isinstance(mapToolKey, QgsMapTool):
                mt = MapTools.copy(mapToolKey, canvas, *args, **kwds)

            if isinstance(mt, QgsMapTool):
                canvas.setMapTool(mt)
                self.mMapTools.append(mt)

                #if required, link map-tool with specific slots
                if isinstance(mt, CursorLocationMapTool):
                    mt.sigLocationRequest[SpatialPoint, QgsMapCanvas].connect(lambda c, m : self.sigShowProfiles.emit(c,m, mapToolKey))

        return self.mMapTools



    def setMaxTSDViews(self, n=-1):
        self.nMaxTSDViews = n
        #todo: remove views

    def setSpatialCenter(self, center, mapCanvas0=None):
        assert isinstance(center, SpatialPoint)
        center = center.toCrs(self.mCRS)
        if not isinstance(center, SpatialPoint):
            return


        self.mSpatialExtent.setCenter(center)
        for mapCanvas in self.mMapCanvases:
            if mapCanvas != mapCanvas0:
                oldState = mapCanvas.blockSignals(True)
                mapCanvas.setCenter(center)
                mapCanvas.blockSignals(oldState)


        self.sigSpatialExtentChanged.emit(self.mSpatialExtent)


    def setSpatialCenter(self, center:SpatialPoint, mapCanvas0=None):
        """
        Sets the MapCanvas center.
        :param center: SpatialPoint
        :param mapCanvas0: MapCanvas0 optional
        """

        assert isinstance(center, SpatialPoint)
        center = center.toCrs(self.mCRS)
        if not isinstance(center, SpatialPoint):
            return None


        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            if mapCanvas != mapCanvas0:
                center0 = mapCanvas.spatialCenter()
                if center0 != center:
                    oldState = mapCanvas.blockSignals(True)
                    mapCanvas.setCenter(center)
                    mapCanvas.blockSignals(oldState)

        self.mMapRefreshTimer.start()

    def setSpatialExtent(self, extent, mapCanvas0=None):
        """
        Sets the spatial extent of all MapCanvases
        :param extent: SpatialExtent
        :param mapCanvas0:
        :return:
        """
        assert isinstance(extent, SpatialExtent)
        extent = extent.toCrs(self.mCRS)
        if not isinstance(extent, SpatialExtent) \
            or extent.isEmpty() or not extent.isFinite() \
            or extent.width() <= 0 \
            or extent.height() <= 0 \
            or extent == self.mSpatialExtent:
            return

        if self.mSpatialExtent == extent:
            return

        self.mSpatialExtent = extent
        for mapCanvas in self.mapCanvases():
            assert isinstance(mapCanvas, MapCanvas)
            extent0 = mapCanvas.spatialExtent()
            if mapCanvas != mapCanvas0 and extent0 != extent:
                mapCanvas.addToRefreshPipeLine(extent)

        self.sigSpatialExtentChanged.emit(extent)

    def setBackgroundColor(self, color:QColor):
        """
        Sets the MapCanvas background color
        :param color: QColor
        """
        assert isinstance(color, QColor)
        self.mColor = color
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setCanvasColor(color)


    def backgroundColor(self)->QColor:
        """
        Returns the MapCanvas background color
        :return: QColor
        """
        return self.mColor


    def mapCanvases(self, mapView=None)->list:
        """
        Returns MapCanvases
        :param mapView: a MapView to return MapCanvases from only, defaults to None
        :return: [list-of-MapCanvas]
        """
        if isinstance(mapView, MapView):
            s = ""
        return self.mMapCanvases[:]

    def mapViews(self)->list:
        """
        Returns a list of all mapviews
        :return [list-of-MapViews]:
        """
        return self.MVC[:]

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if self.mCRS != crs:
            transform = QgsCoordinateTransform()
            transform.setSourceCrs(self.mCRS)
            transform.setDestinationCrs(crs)
            if transform.isValid() and not transform.isShortCircuited():
                self.mCRS = crs
                for mapCanvas in self.mapCanvases():
                    # print(('STV set CRS {} {}', str(mapCanvas), self.mCRS.description()))
                    mapCanvas.setDestinationCrs(QgsCoordinateReferenceSystem(crs))
                """
                from timeseriesviewer.utils import saveTransform
                if saveTransform(self.mSpatialExtent, self.mCRS, crs):
                    self.mCRS = crs
                    
                else:
                    pass
                """
                self.sigCRSChanged.emit(self.crs())


    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Returns the QgsCoordinateReferenceSystem
        :return: QgsCoordinateReferenceSystem
        """
        return self.mCRS

    def spatialExtent(self)->SpatialExtent:
        """
        Returns the SpatialExtent
        :return: SpatialExtent
        """
        return self.mSpatialExtent



    def navigateToTSD(self, TSD:TimeSeriesDatum):
        """
        Changes the viewport of the scroll window to show the requested TimeSeriesDatum
        :param TSD: TimeSeriesDatum
        """
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

        self.mViews = list()
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
        for view in self.mViews:
            assert isinstance(view, DatumView)
            if mapCanvas in view.mMapCanvases.values():
                return view.TSD
        return None

    def tsdView(self, tsd):
        r = [v for v in self.mViews if v.TSD == tsd]
        if len(r) == 1:
            return r[0]
        else:
            raise Exception('TSD not in list')

    def addMapView(self, mapView):
        assert isinstance(mapView, MapView)
        w = self.ui
        #w.setUpdatesEnabled(False)
        #for tsdv in self.mViews:
        #    tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.mViews:
            tsdv.insertMapView(mapView)

        #for tsdv in self.mViews:
        #    tsdv.ui.setUpdatesEnabled(True)

        #mapView.sigSensorRendererChanged.connect(lambda *args : self.setRasterRenderer(mapView, *args))
        mapView.sigMapViewVisibility.connect(lambda: self.sigResizeRequired.emit())
        mapView.sigShowProfiles.connect(self.sigShowProfiles.emit)
        #w.setUpdatesEnabled(True)

        self.sigResizeRequired.emit()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        for tsdv in self.mViews:
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
            return sorted(self.mViews, key=lambda v: np.abs(v.TSD.date - self.focusView.TSD.date))
        else:
            return self.mViews

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

            bisect.insort(self.mViews, DV)
            i = self.mViews.index(DV)

            DV.ui.setParent(self.STV.targetLayout.parentWidget())
            self.STV.targetLayout.insertWidget(i, DV.ui)
            DV.ui.show()

        if len(tsdList) > 0:
            self.sigResizeRequired.emit()

    def removeDates(self, tsdList):
        toRemove = [v for v in self.mViews if v.TSD in tsdList]
        removedDates = []
        for DV in toRemove:
            self.mViews.remove(DV)

            for mapCanvas in DV.mMapCanvases.values():
                toRemove = mapCanvas.layers()
                mapCanvas.setLayers([])
                toRemove = [l for l in toRemove if isinstance(l, QgsRasterLayer)]
                if len(toRemove) > 0:
                    QgsProject.instance().removeMapLayers([l.id() for l in toRemove])

            DV.ui.parent().layout().removeWidget(DV.ui)
            DV.ui.hide()
            DV.ui.close()
            removedDates.append(DV.TSD)
            del DV

        if len(removedDates) > 0:
            self.sigResizeRequired.emit()

    def __len__(self):
        return len(self.mViews)

    def __iter__(self):
        return iter(self.mViews)

    def __getitem__(self, slice):
        return self.mViews[slice]

    def __delitem__(self, slice):
        self.removeDates(self.mViews[slice])


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

    sigMapCanvasColorChanged = pyqtSignal(QColor)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigMapSizeChanged = pyqtSignal(QSize)

    def setTimeSeries(self, timeSeries):
        assert isinstance(timeSeries, TimeSeries)
        self.TS = timeSeries
        self.TS.sigSensorAdded.connect(self.addSensor)
        self.TS.sigSensorRemoved.connect(self.removeSensor)

    def __init__(self, parent=None):
        super(MapViewCollectionDock, self).__init__(parent)
        self.setupUi(self)

        self.mMapViews = MapViewListModel()
        self.baseTitle = self.windowTitle()

        self.btnAddMapView.setDefaultAction(self.actionAddMapView)
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnRefresh.setDefaultAction(self.actionApplyStyles)
        self.btnHighlightMapView.setDefaultAction(self.actionHighlightMapView)

        self.btnCrs.crsChanged.connect(self.sigCrsChanged)
        self.btnMapCanvasColor.colorChanged.connect(self.sigMapCanvasColorChanged)
        self.btnApplySizeChanges.clicked.connect(lambda : self.sigMapSizeChanged.emit(QSize(self.spinBoxMapSizeX.value(),self.spinBoxMapSizeY.value())))

        self.actionAddMapView.triggered.connect(self.createMapView)
        self.actionRemoveMapView.triggered.connect(lambda : self.removeMapView(self.currentMapView()) if self.currentMapView() else None)
        self.actionHighlightMapView.triggered.connect(lambda : self.currentMapView().setHighlighted(True) if self.currentMapView() else None)
        self.actionApplyStyles.triggered.connect(self.refreshCurrentMapView)
        #self.actionApplyStyles.triggered.connect(self.dummySlot)

        self.mMapViews.sigMapViewsRemoved.connect(self.onMapViewsRemoved)
        self.mMapViews.sigMapViewsAdded.connect(self.onMapViewsAdded)
        self.mMapViews.sigMapViewsAdded.connect(self.updateButtons)
        self.mMapViews.sigMapViewsRemoved.connect(self.updateButtons)
        self.cbMapView.setModel(self.mMapViews)
        self.cbMapView.currentIndexChanged[int].connect(lambda i : None if i < 0 else self.setCurrentMapView(self.mMapViews.idx2MapView(i)) )


        self.spinBoxMapSizeX.valueChanged.connect(lambda: self.onMapSizeChanged('X'))
        self.spinBoxMapSizeY.valueChanged.connect(lambda: self.onMapSizeChanged('Y'))
        self.mLastMapSize = self.mapSize()
        #self.mapSize() #inits mLastMapSize
        self.TS = None

    def setCrs(self, crs):
        if isinstance(crs, QgsCoordinateReferenceSystem):
            old = self.btnCrs.crs()
            if old != crs:
                self.btnCrs.setCrs(crs)
                self.btnCrs.setLayerCrs(crs)


    def setMapSize(self, size):
        assert isinstance(size, QSize)
        ws = [self.spinBoxMapSizeX, self.spinBoxMapSizeY]
        oldSize = self.mapSize()
        b = oldSize != size
        for w in ws:
            w.blockSignals(True)

        self.spinBoxMapSizeX.setValue(size.width()),
        self.spinBoxMapSizeY.setValue(size.height())
        self.mLastMapSize = QSize(size)
        for w in ws:
            w.blockSignals(False)
        self.mLastMapSize = QSize(size)
        if b:
            self.sigMapSizeChanged.emit(size)

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
        self.setMapSize(newSize)

    def mapSize(self):
        return QSize(self.spinBoxMapSizeX.value(),
                     self.spinBoxMapSizeY.value())


    def refreshCurrentMapView(self, *args):
        mv = self.currentMapView()
        if isinstance(mv, MapView):
            mv.refreshMapView()
        else:
            s  =""
    def dummySlot(self):
        s  =""

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
            mapView.sigTitleChanged.connect(self.updateTitle)
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

        for mapView in mapViews:
            self.sigMapViewAdded.emit(mapView)

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


        mapView.sigShowProfiles.connect(self.sigShowProfiles)
        self.mMapViews.addMapView(mapView)
        #self.sigMapViewAdded.emit(mapView)
        return mapView


    def removeMapView(self, mapView):
        if isinstance(mapView, MapView):
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
            mapView.addSensor(sensor)


    def removeSensor(self, sensor):
        for mapView in self.mMapViews:
            mapView.removeSensor(sensor)

    def applyStyles(self):
        for mapView in self.mMapViews:
            mapView.applyStyles()

    def setCrosshairStyle(self, crosshairStyle):
        for mapView in self.mMapViews:
            mapView.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        for mapView in self.mMapViews:
            mapView.setCrosshairVisibility(b)

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViewsDefinitions.index(mapView)


    def setCurrentMapView(self, mapView):
        assert isinstance(mapView, MapView) and mapView in self.mMapViews
        idx = self.stackedWidget.indexOf(mapView.ui)
        if idx >= 0:
            self.stackedWidget.setCurrentIndex(idx)
            self.cbMapView.setCurrentIndex(self.mMapViews.mapView2idx(mapView).row())

        self.updateTitle()

    def updateTitle(self, *args):
        # self.btnToggleMapViewVisibility.setChecked(mapView)
        mapView = self.currentMapView()
        if isinstance(mapView, MapView):
            if mapView in self.mMapViews:
                i = str(self.mMapViews.mapView2idx(mapView).row()+1)
            else:
                i = ''
            #title = '{} | {} "{}"'.format(self.baseTitle, i, mapView.title())
            title = '{} | {}'.format(self.baseTitle, i)
            self.setWindowTitle(title)

    def currentMapView(self):
        if len(self.mMapViews) == 0:
            return None
        else:
            i = self.cbMapView.currentIndex()
            if i >= 0:
                return self.mMapViews.idx2MapView(i)
            else:
                return None

