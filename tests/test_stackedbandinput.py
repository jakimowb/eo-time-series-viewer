# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 :
    Copyright            : (C) 2017 by Benjamin Jakimow
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
import os
import unittest
from xml.etree.ElementTree import Element

import numpy as np
from osgeo import gdal, gdal_array, osr
from PyQt5.QtCore import QDateTime

from eotimeseriesviewer.dateparser import ImageDateUtils
from qgis.core import QgsRasterLayer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QDialog
from eotimeseriesviewer.qgispluginsupport.qps.utils import nextColor
from eotimeseriesviewer.stackedbandinput import InputStackInfo, InputStackTableModel, OutputImageModel, \
    OutputVRTDescription, StackedBandInputDialog
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()

PATH_STACK = r'T:\4BJ\2018-2018_000-000_LEVEL4_TSA_SEN2L_EVI_C0_S0_TSS.tif'


class TestStackedInputs(EOTSVTestCase):

    def createTestDatasets(self):

        vsiDir = r'/vsimem/tmp'
        ns = 50
        nl = 100

        r1 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(16, 'D'), dtype=np.datetime64)
        r2 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(8, 'D'), dtype=np.datetime64)
        drv = gdal.GetDriverByName(r'ENVI')

        crs = osr.SpatialReference()
        crs.ImportFromEPSG(32633)

        assert isinstance(drv, gdal.Driver)
        datasets = []
        for i, r in enumerate([r1, r2]):
            p = '{}stack{}.bsq'.format(vsiDir, i + 1)
            nb = len(r)
            ds = drv.Create(p, ns, nl, nb, eType=gdal.GDT_Float32)
            assert isinstance(ds, gdal.Dataset)

            ds.SetProjection(crs.ExportToWkt())
            ds.SetGeoTransform([0.0, 1.0, 0.0, 1.0, 0.0, -1.0])
            dateString = ','.join([str(d) for d in r])
            dateString = '{{{}}}'.format(dateString)
            ds.SetMetadataItem('wavelength', dateString, 'ENVI')

            for b, date in enumerate(r):
                dt = QDateTime(date.astype(object))
                decimalYear = ImageDateUtils.decimalYear(dt)

                band = ds.GetRasterBand(b + 1)
                assert isinstance(band, gdal.Band)
                band.Fill(decimalYear)
            ds.FlushCache()
            datasets.append(p)

            if i == 0:
                # create a classification image stack

                nc = nb
                data = np.ones((nb, ns, nl), dtype=np.uint8)
                classNames = ['unclassified']
                colorTable = gdal.ColorTable()
                colorTable.SetColorEntry(0, (0, 0, 0))
                assert isinstance(colorTable, gdal.ColorTable)
                color = QColor('green')

                for j, date in enumerate(r):
                    c = j + 1
                    data[j, j:-1, 0:j] = c
                    classNames.append('Class {}'.format(date))
                    colorTable.SetColorEntry(c, color.getRgb())
                    color = nextColor(color)

                p = '{}tmpClassificationStack.bsq'.format(vsiDir)
                ds = gdal_array.SaveArray(data, p, format='ENVI', prototype=datasets[0])
                ds.GetRasterBand(1).SetColorTable(colorTable)
                ds.GetRasterBand(1).SetCategoryNames(classNames)

                assert isinstance(ds, gdal.Dataset)
                ds.SetMetadataItem('wavelength', dateString, 'ENVI')
                ds.FlushCache()
                datasets.append(ds)
        return datasets

    @unittest.skipIf(not os.path.isfile(PATH_STACK), f'PATH_STACK does not exists: {PATH_STACK}')
    def test_FORCEStacks(self):

        d = StackedBandInputDialog()
        d.show()
        d.addSources([PATH_STACK])
        self.showGui()

    def test_inputmodel(self):
        testData = self.createTestDatasets()
        m = InputStackTableModel()
        m.insertSources(testData)
        self.assertTrue(len(m) == len(testData))

        dTotal, dIntersecton = m.dateInfo()

        self.assertTrue(len(dTotal) > 0)
        self.assertTrue(len(dIntersecton) > 0)
        self.assertTrue(len(dTotal) > len(dIntersecton))

    def test_outputmodel(self):

        m = OutputImageModel()
        m.setOutputDir('/vsimem/dub')
        m.setOutputPrefix('myPrefix')

        testData = self.createTestDatasets()
        self.assertTrue(len(testData) > 0, msg='self.createTestDatasets() failed to create testdata sets')
        stackInfo = InputStackInfo(testData[0])

        self.assertTrue(len(stackInfo) > 0)

        stackInfos = [InputStackInfo(f) for f in testData]

        dates = set()

        for s in stackInfos:
            dates.update(s.dates())

        m.setMultiStackSources(stackInfos, list(dates))

        self.assertTrue(len(m) > 0)

        outInfo = m.mOutputImages[0]
        self.assertIsInstance(outInfo, OutputVRTDescription)

        xml = m.vrtXML(outInfo)
        self.assertIsInstance(xml, str)

        eTree = m.vrtXML(outInfo, asElementTree=True)
        self.assertIsInstance(eTree, Element)

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_dialog(self):
        d = StackedBandInputDialog()
        d.addSources(self.createTestDatasets())

        r = d.exec_()

        self.assertTrue(r in [QDialog.Rejected, QDialog.Accepted])
        if r == QDialog.Accepted:
            d.saveImages()
            images = d.writtenFiles()
            self.assertTrue(len(images) > 0)

            for p in images:
                ds = gdal.Open(p)
                self.assertIsInstance(ds, gdal.Dataset)
                lyr = QgsRasterLayer(p)
                self.assertIsInstance(lyr, QgsRasterLayer)
                self.assertTrue(lyr.isValid())
        else:
            self.assertTrue(len(d.writtenFiles()) == 0)

        self.showGui(d)

    def test_withTSV(self):

        testImages = self.createTestDatasets()
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        TSV = EOTimeSeriesViewer()
        TSV.show()

        d = StackedBandInputDialog()
        d.addSources(self.createTestDatasets())
        writtenFiles = d.saveImages()
        self.assertTrue(len(writtenFiles) > 0)
        TSV.addTimeSeriesImages(writtenFiles, loadAsync=False)

        self.assertTrue(len(TSV.mTimeSeries) == len(writtenFiles))

        self.showGui(d)
        TSV.close()


if __name__ == "__main__":
    unittest.main(buffer=False)
