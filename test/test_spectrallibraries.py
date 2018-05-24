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
import os, sys, unittest, tempfile
from timeseriesviewer.utils import initQgisApplication
from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, re_2014_06_25
qapp = initQgisApplication()
import gdal
gdal.AllRegister()
from timeseriesviewer.spectrallibraries import *

class TestInit(unittest.TestCase):

    def setUp(self):

        self.SP = None
        self.SPECLIB = None
        self.lyr1 = QgsRasterLayer(Img_2014_06_16_LE72270652014167CUB00_BOA)
        self.lyr2 = QgsRasterLayer(re_2014_06_25)
        self.layers = [self.lyr1, self.lyr2]
        QgsProject.instance().addMapLayers(self.layers)


    def createSpeclib(self):
        from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, re_2014_06_25

        path = Img_2014_06_16_LE72270652014167CUB00_BOA
        ext = SpatialExtent.fromRasterSource(path)
        pos = []
        center = ext.spatialCenter()
        for dx in range(-120, 120, 60):
            for dy in range(-120, 120, 60):
                pos.append(SpatialPoint(ext.crs(), center.x() + dx, center.y() + dy))

        speclib = SpectralLibrary()
        p1 = SpectralProfile()
        p1.setName('No Geometry')
        p1.setXValues([1, 2, 3, 4, 5])
        p1.setYValues([0.2, 0.3, 0.2, 0.5, 0.7])

        p2 = SpectralProfile()
        p2.setName('No Geom/NoData')

        speclib.addProfiles([p1,p2])
        speclib.addSpeclib(SpectralLibrary.readFromRasterPositions(path, pos))
        return speclib

    def test_spectralprofile(self):

        canvas = QgsMapCanvas()
        canvas.setLayers(self.layers)
        canvas.setExtent(self.lyr2.extent())
        canvas.setDestinationCrs(self.lyr1.crs())
        pos = SpatialPoint(self.lyr2.crs(), *self.lyr2.extent().center())
        profiles = SpectralProfile.fromMapCanvas(canvas, pos)
        self.assertIsInstance(profiles, list)
        self.assertEqual(len(profiles), 2)
        for p in profiles:
            self.assertIsInstance(p, SpectralProfile)





        sp1 = SpectralProfile()
        yVal = [0.23, 0.4, 0.3, 0.8, 0.7]
        xVal = [300,400, 600, 1200, 2500]

        #default: empty profile
        self.assertEqual(sp1.xUnit(), 'index')
        self.assertEqual(sp1.yUnit(), None)

        sp1.setYValues(yVal)
        self.assertTrue(np.array_equal(sp1.yValues(), np.asarray(yVal)))
        self.assertTrue(np.array_equal(sp1.xValues(), np.arange(len(yVal))))
        self.assertEqual(sp1.xUnit(), 'index')
        self.assertEqual(sp1.yUnit(), None)

        sp1.setYUnit('reflectance')
        self.assertEqual(sp1.yUnit(), 'reflectance')





        sp1.setXValues(xVal)
        sp1.setYValues(yVal)
        name = 'missingAttribute'
        sp1.setMetadata(name, 'myvalue')
        self.assertTrue(name not in sp1.fieldNames())
        sp1.setMetadata(name, 'myvalue', addMissingFields=True)
        self.assertTrue(name in sp1.fieldNames())
        self.assertEqual(sp1.metadata(name), 'myvalue')
        sp1.removeField(name)
        self.assertTrue(name not in sp1.fieldNames())
        self.assertIsInstance(sp1.xValues(), list)
        self.assertIsInstance(sp1.yValues(), list)

        sp1.setXUnit('nm')
        self.assertEqual(sp1.xUnit(), 'nm')
        self.assertTrue(np.array_equal(xVal, sp1.xValues()))

        self.assertEqual(sp1, sp1)


        for sp2 in[sp1.clone(), copy.copy(sp1), sp1.__copy__()]:
            self.assertIsInstance(sp2, SpectralProfile)
            self.assertEqual(sp1, sp2)


        dump = pickle.dumps(sp1)
        sp2 = pickle.loads(dump)

        self.assertEqual(sp1, sp2)

        sp2 = SpectralProfile(xUnit='nm')
        #sp2.setValues(yVal, xValues=xVal)
        sp2.setXValues(xVal)
        sp2.setYValues(yVal)

        self.assertNotEqual(sp1, sp2)

        sp2.setYUnit('reflectance')
        self.assertEqual(sp1, sp2)

        values = [('key','value'),('key', 100),('Üä','ÜmlÄute')]
        for md in values:
            k, v = md
            sp1.setMetadata(k,v)
            v2 = sp1.metadata(k)
            self.assertEqual(v2, None)

        for md in values:
            k, v = md
            sp1.setMetadata(k, v, addMissingFields=True)
            v2 = sp1.metadata(k)
            self.assertEqual(v, v2)

        self.SP = sp1

    def test_spectralLibrary(self):

        sp1 = SpectralProfile()
        sp1.setYValues([0, 4, 3, 2, 1])
        sp1.setXValues([450, 500, 750, 1000, 1500])


        sp2 = SpectralProfile()
        sp2.setYValues([3, 2, 1, 0, 1])
        sp2.setXValues([450, 500, 750, 1000, 1500])

        sl1 = SpectralLibrary()

        self.assertEqual(sl1.name(), 'SpectralLibrary')
        sl1.setName('MySpecLib')
        self.assertEqual(sl1.name(), 'MySpecLib')

        sl1.addProfiles([sp1, sp2])
        self.assertEqual(len(sl1),2)
        t = sl1[0:1]
        self.assertIsInstance(sl1[0], SpectralProfile)
        self.assertEqual(sl1[0], sp1)
        self.assertEqual(sl1[1], sp2)
        self.assertNotEqual(sl1[0], sp2)

        dump = pickle.dumps(sl1)

        sl2 = pickle.loads(dump)
        self.assertIsInstance(sl2, SpectralLibrary)
        self.assertEqual(sl1, sl2)

        sl2.addProfiles([sp2])
        self.assertNotEqual(sl1, sl2)
        self.assertEqual(sl2[2], sp2)


        #read from image

        if self.lyr1.isValid():
            center1 = self.lyr1.extent().center()
            center2 = SpatialPoint.fromSpatialExtent(SpatialExtent.fromLayer(self.lyr1))
        else:
            center1 = SpatialExtent.fromRasterSource(self.lyr1.source()).spatialCenter()
            center2 = SpatialExtent.fromRasterSource(self.lyr1.source()).spatialCenter()
            s  =""
        sl1 = SpectralLibrary.readFromRasterPositions(Img_2014_06_16_LE72270652014167CUB00_BOA,center1)
        sl2 = SpectralLibrary.readFromRasterPositions(Img_2014_06_16_LE72270652014167CUB00_BOA,center2)

        sl3 = SpectralLibrary.readFromRasterPositions(Img_2014_06_16_LE72270652014167CUB00_BOA,[center1, center2])

        for sl in [sl1, sl2]:
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) == 1)
        self.assertTrue(len(sl3) == 2)

        #sl1.plot()

        tempDir = tempfile.gettempdir()
        pathESL = tempfile.mktemp(prefix='speclib.', suffix='.esl')
        pathCSV = tempfile.mktemp(prefix='speclib.', suffix='.csv')

        #test ENVI Spectral Library
        try:
            writtenFiles = sl1.exportProfiles(pathESL)
        except Exception as ex:
            self.fail('Unable to write ESL. {}'.format(ex))
        for f in writtenFiles:
            self.assertTrue(os.path.isfile(f))
            try:
                self.assertTrue(EnviSpectralLibraryIO.canRead(f))
                sl = EnviSpectralLibraryIO.readFrom(f)
                self.assertIsInstance(sl, SpectralLibrary)
                sl = SpectralLibrary.readFrom(f)
            except Exception as ex:
                self.fail('Failed SpectralLibrary.readFrom(p) p = {}\n{}'.format(f, ex))
            self.assertIsInstance(sl, SpectralLibrary)

        try:
            writtenFiles = sl1.exportProfiles(pathCSV)
        except Exception as ex:
            self.fail('Unable to write CSV. {}'.format(ex))

        for f in writtenFiles:
            try:
                sl1 = SpectralLibrary.readFrom(f)
            except Exception as ex:
                self.fail('Unable to read CSV. {}'.format(ex))




        self.SPECLIB = sl1



    def test_mergeSpeclibs(self):

        sp = SpectralProfile()
        sp.setMetadata('newfield', 'foo', addMissingFields=True)
        sl1 = SpectralLibrary()
        sl1.startEditing()
        sl1.addAttribute(SpectralProfile.createQgsField('newField', ''))
        sl1.commitChanges()
        sl1.addProfiles(sp)

        sl2 = SpectralLibrary()


    def test_filterModel(self):
        w = QFrame()
        speclib = self.createSpeclib()
        speclib
        dmodel = SpectralLibraryTableModel(speclib, parent=w)
        fmodel = SpectralLibraryTableFilterModel(dmodel, parent=w)

        import example
        layer = QgsVectorLayer(example.exampleEvents)
        QgsProject.instance().addMapLayer(layer)
        cache = QgsVectorLayerCache(layer, 1000)
        table = QgsAttributeTableModel(cache)


        dummyCanvas = QgsMapCanvas()
        dummyCanvas.setDestinationCrs(SpectralProfile.crs)
        dummyCanvas.setExtent(QgsRectangle(-180,-90,180,90))

        fmodel = QgsAttributeTableFilterModel(dummyCanvas, table)
        fmodel.sort(0, Qt.DescendingOrder)

        idx0 = fmodel.createIndex(0,0)
        idx0d = fmodel.mapToSource(idx0)
        s = ""

    def test_speclibTableView(self):

        v = SpectralLibraryTableView()
        v.show()

    def test_speclibWidget(self):
        p = SpectralLibraryWidget()
        p.addSpeclib(self.SPECLIB)
        p.show()







        pass


if __name__ == '__main__':
    unittest.main()
