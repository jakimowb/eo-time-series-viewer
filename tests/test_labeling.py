# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 30.11.2017
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
import os, sys, re
from timeseriesviewer.tests import initQgisApplication, testRasterFiles
import unittest, tempfile

from timeseriesviewer.labeling import *
from timeseriesviewer import DIR_REPO
resourceDir = os.path.join(DIR_REPO, 'qgisresources')
QGIS_APP = initQgisApplication(qgisResourceDir=resourceDir)
SHOW_GUI = True

class testclassLabelingTest(unittest.TestCase):



    def test_LabelingDock(self):

        dock = LabelingDock()
        self.assertIsInstance(dock, LabelingDock)

        from timeseriesviewer.tests import TestObjects

        ds = TestObjects.createVectorDataSet()
        path = ds.GetDescription()
        import example
        path = example.exampleEvents
        lyr = QgsVectorLayer(path)
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.featureCount() > 0)
        QgsProject.instance().addMapLayer(lyr)

        self.assertIsInstance(dock.mVectorLayerComboBox, QgsMapLayerComboBox)
        dock.mVectorLayerComboBox.setCurrentIndex(1)
        self.assertTrue(dock.mVectorLayerComboBox.currentLayer() == lyr)

        model = dock.mLabelAttributeModel
        self.assertIsInstance(model, LabelAttributeTableModel)
        self.assertTrue(model.mVectorLayer == lyr)
        self.assertTrue(lyr.fields().count() == model.rowCount())



        if SHOW_GUI:
            dock.show()
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()
