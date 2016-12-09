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

class ImageChipViewSettings(QGroupBox,
                            loadUIFormClass(PATH_IMAGECHIPVIEWSETTINGS_UI)):

    #define signals

    removeView = pyqtSignal()

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(ImageChipViewSettings, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        from timeseriesviewer.timeseries import SensorInstrument
        assert isinstance(sensor, SensorInstrument)
        self.sensor = sensor

        self.setTitle(sensor.sensorName)

        self.minValues = [self.tbRedMin, self.tbGreenMin, self.tbBlueMin]
        self.maxValues = [self.tbRedMax, self.tbGreenMax, self.tbBlueMax]
        self.sliders = [self.sliderRed, self.sliderGreen, self.sliderBlue]
        for tb in self.minValues + self.maxValues:
            tb.setValidator(QDoubleValidator())
        for sl in self.sliders:
            sl.setMinimum(1)
            sl.setMaximum(self.sensor.nb)

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



    def setBands(self,bands):
        assert len(bands) == 3
        for b in bands:
            assert type(b) is int and b > 0
            assert b <= len(self.sensor.band_names), 'TimeSeries is not initializes/has no bands to show'
        self.cb_r.setCurrentIndex(bands[0]-1)
        self.cb_g.setCurrentIndex(bands[1]-1)
        self.cb_b.setCurrentIndex(bands[2]-1)

        s = ""
        pass

    def setLayerRenderer(self, renderer):
        assert isinstance(renderer, QgsRasterRenderer)

        if isinstance(renderer, QgsMultiBandColorRenderer):
            s = ""

        bands, ranges = bands_and_ranges
        assert len(bands) == 3
        assert len(ranges) == 3
        for range in ranges:
            assert len(range) == 2 and range[0] <= range[1]

        #copy values only if all bands fit to this sensor
        for b in bands:
            if b > self.sensor.nb:
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



class BandViewSettings(QGroupBox,
                       loadUIFormClass(PATH_BANDVIEWSETTINGS_UI)):

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