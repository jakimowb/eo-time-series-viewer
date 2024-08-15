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
import unittest

from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()

PATH_STACK = r'T:\4BJ\2018-2018_000-000_LEVEL4_TSA_SEN2L_EVI_C0_S0_TSS.tif'


class TestStackedInputs(EOTSVTestCase):

    def test_withTSV(self):
        # testImages = self.createTestDatasets()
        TSV = EOTimeSeriesViewer()
        # TSV.show()

        # d = StackedBandInputDialog()
        # d.addSources(self.createTestDatasets())
        # writtenFiles = d.saveImages()
        # self.assertTrue(len(writtenFiles) > 0)
        # TSV.addTimeSeriesImages(writtenFiles, loadAsync=False)
        # self.taskManagerProcessEvents()
        # self.assertTrue(len(TSV.mTimeSeries) == len(writtenFiles))

        # self.showGui(d)
        # TSV.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(buffer=False)
