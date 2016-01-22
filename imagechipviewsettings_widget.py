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

from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import sys
sys.path.append(os.path.dirname(__file__))
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'imagechipviewsettings_widget_base.ui'), resource_suffix='')



class ImageChipViewSettings(QGroupBox, FORM_CLASS):

    #define signals

    removeView = pyqtSignal()

    def __init__(self, SensorConfiguration, parent=None):
        """Constructor."""
        super(ImageChipViewSettings, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)


        self.SensorConfiguration = SensorConfiguration
        self.setTitle(SensorConfiguration.sensor_name)

        self.tb_range_r_min.setValidator(QDoubleValidator())
        self.tb_range_g_min.setValidator(QDoubleValidator())
        self.tb_range_b_min.setValidator(QDoubleValidator())
        self.tb_range_r_max.setValidator(QDoubleValidator())
        self.tb_range_g_max.setValidator(QDoubleValidator())
        self.tb_range_b_max.setValidator(QDoubleValidator())

        self._initBands(self.SensorConfiguration.band_names)

    def ua_setMask(self, state):

        useMask = state != 0
        for w in [self.bt_color, self.label_maskexpression, self.tb_maskexpression]:
            w.setEnabled(useMask)



    def ua_setMaskColor(self, color):
        if color is None:
            color = QColorDialog.getColor()

        if color is not None:
            self.maskcolor = color
            r = color.red()
            g = color.green()
            b = color.blue()
            style = "background:rgb({},{},{})".format(r,g,b)
            self.bt_color.setStyleSheet(style)
            self.bt_color.update()

    def getMaskColor(self):
        return (self.maskcolor.red(), self.maskcolor.green(), self.maskcolor.blue())

    def useMaskValues(self):
        return self.cb_useMask.isChecked()

    def _initBands(self, band_names):
        cb_R = self.cb_r
        cb_G = self.cb_g
        cb_B = self.cb_b

        for i, bandname in enumerate(band_names):
            cb_R.addItem(bandname, i+1)
            cb_G.addItem(bandname, i+1)
            cb_B.addItem(bandname, i+1)

        if len(self.SensorConfiguration.band_names) >= 3:
            cb_R.setCurrentIndex(2)
            cb_G.setCurrentIndex(1)
            cb_B.setCurrentIndex(0)


    def setBands(self,bands):
        assert len(bands) == 3
        for b in bands:
            assert type(b) is int and b > 0
            assert b <= len(self.SensorConfiguration.band_names), 'TimeSeries is not initializes/has no bands to show'
        self.cb_r.setCurrentIndex(bands[0]-1)
        self.cb_g.setCurrentIndex(bands[1]-1)
        self.cb_b.setCurrentIndex(bands[2]-1)

        s = ""
        pass

    def getBands(self):
        bands = [self.cb_r.currentIndex()+1, \
                 self.cb_g.currentIndex()+1, \
                 self.cb_b.currentIndex()+1]
        return bands

    def getRanges(self):
        range_r = [float(self.tb_range_r_min.text()), float(self.tb_range_r_max.text())]
        range_g = [float(self.tb_range_g_min.text()), float(self.tb_range_g_max.text())]
        range_b = [float(self.tb_range_b_min.text()), float(self.tb_range_b_max.text())]
        return (range_r, range_g, range_b)

    def getSettings(self):

        s = ""
