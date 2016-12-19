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


class ImageChipViewSettingsUI(QGroupBox,
                             loadUIFormClass(PATH_IMAGECHIPVIEWSETTINGS_UI)):

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(ImageChipViewSettingsUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect

        self.setupUi(self)


class ImageChipViewSettings(QObject):

    #define signals

    removeView = pyqtSignal()

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(ImageChipViewSettings, self).__init__(parent)

        self.ui = ImageChipViewSettingsUI(sensor, parent)
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
            sl.valueChanged.connect(self.bandSelectionChanged)

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
        self.setLayerRenderer(lyr.renderer())

        #provide default min max

        s = ""


    def bandSelectionChanged(self, *args):

        text = 'RGB {}-{}-{}'.format(self.ui.sliderRed.value(),
                                        self.ui.sliderGreen.value(),
                                        self.ui.sliderBlue.value())
        self.ui.labelBands.setText(text)
        s = ""

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
                e.setMinimumValue(float(self.ui.minValues[i].text()))
                e.setMaximumValue(float(self.ui.maxValues[i].text()))
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
        action.triggered.connect(lambda : self.removeView.emit())
        #add QGIS specific options
        txt = QApplication.clipboard().text()
        if re.search('<!DOCTYPE(.|\n)*rasterrenderer.*type="multibandcolor"', txt) is not None:
            import qgis_add_ins
            action = menu.addAction('Paste style')
            action.setToolTip('Uses the QGIS raster layer style to specify band selection and band value ranges.')
            action.triggered.connect(lambda : self.setLayerRenderer(qgis_add_ins.paste_band_settings(txt)))


        menu.exec_(event.globalPos())


