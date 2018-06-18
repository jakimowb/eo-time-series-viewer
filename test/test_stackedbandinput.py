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

        cls.srcDir = r'F:\Temp\EOTSV_Dev\DF'
        cls.stackFiles = file_search(cls.srcDir, '*.tif')

    def setUp(self):
        """Runs before each test."""
        pass
    def tearDown(self):
        """Runs after each test."""
        pass

    def createTestDatasets(self):

        vsiDir = '/vsimem/tmp'

        ns = 50
        nl = 100

        r1 = np.arange('2000-01-01', '2001-06-14', step=np.timedelta64(16, 'D'), dtype=np.datetime64)
        r2 = np.arange('2000-01-01', '2001-06-14', step=np.timedelta64(8, 'D'), dtype=np.datetime64)
        drv = gdal.GetDriverByName('ENVI')
        assert isinstance(drv, gdal.Driver)
        for i, r in enumerate([r1, r2]):
            p = '{}stack{}.bsq'.format(vsiDir, i+1)
            p.

        datasets = []

        pass

    def test_outputmodel(self):

        m = OutputImageModel()
        m.setOutputDir('/vsimem/dub')
        m.setOutputPrefix('myPrefix')

        stackInfos = [InputStackInfo(f) for f in self.stackFiles]
        m.setMultiStackSources(stackInfos)

        self.assertTrue(len(m) > 0)


        outInfo = m.mOutputImages[0]
        self.assertIsInstance(outInfo, OutputVRTDescription)

        xml = m.vrtXML(outInfo)
        self.assertIsInstance(xml, str)
        eTree = m.vrtXML(outInfo, asElementTree=True)
        self.assertIsInstance(eTree, ElementTree.ElementTree)





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
        d.addSources(self.stackFiles)
        d.show()

        QGIS_APP.exec_()
        pass



if __name__ == "__main__":
    unittest.main()
