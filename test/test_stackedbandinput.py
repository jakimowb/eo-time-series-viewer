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

from timeseriesviewer.utils import initQgisApplication
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import unittest, tempfile

from timeseriesviewer.stackedbandinput import *
from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, Img_2014_05_07_LC82270652014127LGN00_BOA
resourceDir = os.path.join(DIR_REPO,'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)


class testclassDialogTest(unittest.TestCase):
    """Test rerources work."""

    @classmethod
    def setUpClass(cls):
        pass
        #cls.srcDir = r'F:\Temp\EOTSV_Dev\DF'
        #cls.stackFiles = file_search(cls.srcDir, '*.tif')

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass

    def createTestDatasets(self):

        vsiDir = '/vsimem/tmp'
        from timeseriesviewer.temporalprofiles2d import date2num
        ns = 50
        nl = 100

        r1 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(16, 'D'), dtype=np.datetime64)
        r2 = np.arange('2000-01-01', '2005-06-14', step=np.timedelta64(8, 'D'), dtype=np.datetime64)
        drv = gdal.GetDriverByName('ENVI')

        crs = osr.SpatialReference()
        crs.ImportFromEPSG(32633)

        assert isinstance(drv, gdal.Driver)
        datasets = []
        for i, r in enumerate([r1, r2]):
            p = '{}tmpstack{}.bsq'.format(vsiDir, i+1)

            ds = drv.Create(p, ns, nl, len(r), eType=gdal.GDT_Float32)
            assert isinstance(ds, gdal.Dataset)

            ds.SetProjection(crs.ExportToWkt())

            dateString = ','.join([str(d) for d in r])
            dateString = '{{{}}}'.format(dateString)
            ds.SetMetadataItem('wavelength', dateString, 'ENVI')

            for b, date in enumerate(r):
                decimalYear = date2num(date)

                band = ds.GetRasterBand(b+1)
                assert isinstance(band, gdal.Band)
                band.Fill(decimalYear)
            ds.FlushCache()
            datasets.append(p)




        return datasets


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
        self.assertIsInstance(eTree, ElementTree.Element)


    def test_dateparsing(self):

        dsDates = gdal.OpenEx(self.stackFiles[1], allowed_drivers=['ENVI'])

        #dsDates = gdal.Open(self.stackFiles[1])
        dates = datesFromDataset(dsDates)
        self.assertEqual(len(dates), dsDates.RasterCount)

        dsNoDates = gdal.OpenEx(self.stackFiles[0], allowed_drivers=['ENVI'])
        dates = datesFromDataset(dsNoDates)
        self.assertEqual(len(dates), 0)

        s = ""

    def test_dialog(self):
        d = StackedBandInputDialog()
        d.addSources(self.createTestDatasets())

        r = d.exec_()

        self.assertTrue(r in [QDialog.Rejected, QDialog.Accepted])
        if r == QDialog.Accepted:
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

        #QGIS_APP.exec_()
        pass

    def test_withTSV(self):



        testImages = self.createTestDatasets()
        from timeseriesviewer.main import TimeSeriesViewer
        TSV = TimeSeriesViewer(None)
        TSV.show()

        d = StackedBandInputDialog()
        d.addSources(self.createTestDatasets())
        writtenFiles = d.saveImages()
        self.assertTrue(len(writtenFiles) > 0)
        TSV.loadImageFiles(writtenFiles)

        self.assertTrue(len(TSV.TS) == len(writtenFiles))

        QGIS_APP.exec_()
if __name__ == "__main__":
    unittest.main()
