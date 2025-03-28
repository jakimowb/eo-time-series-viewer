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
import os
import unittest
import uuid
from pathlib import Path
from xml.etree.ElementTree import Element
from typing import List

import numpy as np
from osgeo import gdal, gdal_array, osr
from PyQt5.QtWidgets import QApplication
from qgis._core import QgsProject
from qgis.PyQt.QtCore import QDateTime
from qgis.core import QgsRasterLayer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QDialog

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import nextColor
from eotimeseriesviewer.stackedbandinput import InputStackInfo, InputStackTableModel, OutputImageModel, \
    OutputVRTDescription, StackedBandInputDialog
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer.timeseries.source import TimeSeriesSource

start_app()

PATH_STACK = r'T:\4BJ\2018-2018_000-000_LEVEL4_TSA_SEN2L_EVI_C0_S0_TSS.tif'


class TestStackedInputs(EOTSVTestCase):

    def createTestDatasets(self) -> List[str]:

        uid = uuid.uuid4()
        vsiDir = Path(f'/vsimem/tmp{uid}')
        ns = 5
        nl = 10

        r1 = np.arange('2000-01-01', '2005-04-14', step=np.timedelta64(16, 'D'), dtype=np.datetime64)
        r2 = np.arange('2000-01-01', '2005-04-14', step=np.timedelta64(8, 'D'), dtype=np.datetime64)
        drv = gdal.GetDriverByName(r'ENVI')

        crs = osr.SpatialReference()
        crs.ImportFromEPSG(32633)

        assert isinstance(drv, gdal.Driver)
        datasets: List[gdal.Dataset] = []
        for i, r in enumerate([r1, r2]):
            p = vsiDir / f'stacksource_{i + 1}.bsq'
            nb = len(r)
            ds = drv.Create(p.as_posix(), ns, nl, nb, eType=gdal.GDT_Float32)
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
                arr = band.ReadAsArray()
                arr[:] = decimalYear
                arr[0, 0] = decimalYear - 100
                band.WriteArray(arr)

            ds.FlushCache()
            datasets.append(ds)

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
                    classNames.append(f'Class {date}')
                    colorTable.SetColorEntry(c, color.getRgb())
                    color = nextColor(color)

                p = vsiDir / 'tmpClassificationStack.bsq'
                ds = gdal_array.SaveArray(data, p.as_posix(), format='ENVI', prototype=datasets[0])
                ds.GetRasterBand(1).SetColorTable(colorTable)
                ds.GetRasterBand(1).SetCategoryNames(classNames)

                assert isinstance(ds, gdal.Dataset)
                ds.SetMetadataItem('wavelength', dateString, 'ENVI')
                ds.FlushCache()
                datasets.append(ds)
        return [d.GetDescription() for d in datasets]

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

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking Dialog')
    def test_dialog(self):

        testdata = self.createTestDatasets()

        for d in testdata:
            ds: gdal.Dataset = gdal.Open(d)
            self.assertIsInstance(ds, gdal.Dataset)
            arr = ds.ReadAsArray()
            self.assertIsInstance(arr, np.ndarray)
            del ds

        dialog = StackedBandInputDialog()
        dialog.addSources(testdata)

        r = dialog.exec_()

        self.assertTrue(r in [QDialog.Rejected, QDialog.Accepted])
        if r == QDialog.Accepted:
            dialog.saveImages()
            images = dialog.writtenFiles()
            self.assertTrue(len(images) > 0)

            for p in images:
                ds = gdal.Open(p)
                self.assertIsInstance(ds, gdal.Dataset)
                lyr = QgsRasterLayer(p)
                self.assertIsInstance(lyr, QgsRasterLayer)
                self.assertTrue(lyr.isValid())
                del lyr
                del ds
        else:
            self.assertTrue(len(dialog.writtenFiles()) == 0)

        self.showGui(dialog)
        for d in testdata:
            gdal.Unlink(d)

    def test_withTSV(self):

        datasets = self.createTestDatasets()
        d = StackedBandInputDialog()
        d.show()
        QApplication.processEvents()
        d.addSources(datasets)
        d.show()

        writtenFiles = d.saveImages()
        self.assertTrue(len(writtenFiles) > 0)

        for f in writtenFiles:
            lyr = QgsRasterLayer(f)
            self.assertTrue(lyr.isValid())

            tss = TimeSeriesSource.create(lyr)
            self.assertIsInstance(tss, TimeSeriesSource)
            del tss
            del lyr

        TSV = EOTimeSeriesViewer()
        TSV.timeSeries().setDateTimePrecision(DateTimePrecision.Year)

        TSV.addTimeSeriesImages(writtenFiles, loadAsync=False)
        self.assertEqual(len(list(TSV.timeSeries().sources())), len(writtenFiles))

        self.showGui(TSV)
        QApplication.processEvents()
        TSV.close()
        QApplication.processEvents()
        QgsProject.instance().removeAllMapLayers()
        del TSV

        for d in datasets:
            gdal.Unlink(d)

        QgsProject.instance().removeAllMapLayers()


if __name__ == "__main__":
    unittest.main(buffer=False)
