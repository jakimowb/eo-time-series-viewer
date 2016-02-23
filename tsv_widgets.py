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

import sys, re, os
sys.path.append(os.path.dirname(__file__))


def loadFormClass(name_ui):
    FORM_CLASS, _ = uic.loadUiType(os.path.join(
        os.path.dirname(__file__), name_ui), resource_suffix='')
    return FORM_CLASS


FORM_CLASS_BANDVIEWSETTINGS = loadFormClass('bandviewsettings_widget_base.ui')
FORM_CLASS_IMAGECHIPVIEWSETTINGS = loadFormClass('imagechipviewsettings_widget_base.ui')


class ImageChipViewSettings(QGroupBox, FORM_CLASS_IMAGECHIPVIEWSETTINGS):

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

    def setRGBSettings(self, bands_and_ranges):
        bands, ranges = bands_and_ranges
        assert len(bands) == 3
        assert len(ranges) == 3
        for range in ranges:
            assert len(range) == 2 and range[0] <= range[1]

        #copy values only if all bands fit to this sensor
        for b in bands:
            if b > self.SensorConfiguration.nb:
                return

        self.cb_r.setCurrentIndex(bands[0]-1)
        self.cb_g.setCurrentIndex(bands[1]-1)
        self.cb_b.setCurrentIndex(bands[2]-1)

        self.tb_range_r_min.setText(str(ranges[0][0]))
        self.tb_range_g_min.setText(str(ranges[1][0]))
        self.tb_range_b_min.setText(str(ranges[2][0]))

        self.tb_range_r_max.setText(str(ranges[0][1]))
        self.tb_range_g_max.setText(str(ranges[1][1]))
        self.tb_range_b_max.setText(str(ranges[2][1]))


    def getRGBSettings(self):
        bands = [self.cb_r.currentIndex()+1, \
                 self.cb_g.currentIndex()+1, \
                 self.cb_b.currentIndex()+1]

        range_r = [float(self.tb_range_r_min.text()), float(self.tb_range_r_max.text())]
        range_g = [float(self.tb_range_g_min.text()), float(self.tb_range_g_max.text())]
        range_b = [float(self.tb_range_b_min.text()), float(self.tb_range_b_max.text())]
        ranges = (range_r, range_g, range_b)

        return bands, ranges

    def contextMenuEvent(self, event):
        menu = QMenu()

        #add general options

        #add QGIS specific options
        txt = QApplication.clipboard().text()
        if re.search('<!DOCTYPE(.|\n)*rasterrenderer.*type="multibandcolor"', txt) is not None:
            import qgis_add_ins
            action = menu.addAction('Paste style')
            action.setToolTip('Uses the QGIS raster layer style to specify band selection and band value ranges.')
            action.triggered.connect(lambda : self.setRGBSettings(qgis_add_ins.paste_band_settings(txt)))


        menu.exec_(event.globalPos())



class BandViewSettings(QGroupBox, FORM_CLASS_BANDVIEWSETTINGS):

    #define signals

    removeView = pyqtSignal()

    def __init__(self, SensorConfiguration, parent=None):
        """Constructor."""
        super(BandViewSettings, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)


        self.SensorConfiguration = SensorConfiguration
        self.setTitle(SensorConfiguration.sensor_name)

        self.tb_range_min.setValidator(QDoubleValidator())
        self.tb_range_max.setValidator(QDoubleValidator())

        self._initBands(self.SensorConfiguration.band_names)

    def ua_setMask(self, state):
        raise NotImplementedError()
        useMask = state != 0
        for w in [self.bt_color, self.label_maskexpression, self.tb_maskexpression]:
            w.setEnabled(useMask)

    def ua_setMaskColor(self, color):
        raise NotImplementedError()
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
        raise NotImplementedError()
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

    def getRGBSettings(self):
        bands = [self.cb_r.currentIndex()+1, \
                 self.cb_g.currentIndex()+1, \
                 self.cb_b.currentIndex()+1]

        range = [float(self.tb_range_min.text()), float(self.tb_range_max.text())]
        ranges = (range, range, range)

        return bands, ranges


if __name__ == '__main__':

    import PyQt4.Qt

    app=PyQt4.Qt.QApplication([])
    W = QDialog()
    W.setLayout(QHBoxLayout())
    L = W.layout()
    import sensecarbon_tsv
    S = sensecarbon_tsv.SensorConfiguration(6,30,30)
    w = BandViewSettings(S)
    L.addWidget(w)
    W.show()
    sys.exit(app.exec_())

    print('Done')