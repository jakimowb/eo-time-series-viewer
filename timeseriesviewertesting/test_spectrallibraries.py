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
from timeseriesviewertesting import initQgisApplication
from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, re_2014_06_25
qapp = initQgisApplication()
import gdal
gdal.AllRegister()
from timeseriesviewer.speclib.spectrallibraries import *

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


        #for dx in range(-120, 120, 90):
        #    for dy in range(-120, 120, 90):
        #        pos.append(SpatialPoint(ext.crs(), center.x() + dx, center.y() + dy))

        speclib = SpectralLibrary()
        p1 = SpectralProfile()
        p1.setName('No Geometry')
        p1.setXValues([1, 2, 3, 4, 5])
        p1.setYValues([0.2, 0.3, 0.2, 0.5, 0.7])

        p2 = SpectralProfile()
        p2.setName('No Geom & NoData')


        p3 = SpectralProfile()
        p3.setXValues([250., 251., 253., 254., 256.])
        p3.setYValues([0.2, 0.3, 0.2, 0.5, 0.7])
        p3.setXUnit('nm')

        p4 = SpectralProfile()
        p4.setXValues([0.250, 0.251, 0.253, 0.254, 0.256])
        p4.setYValues([0.22, 0.333, 0.222, 0.555, 0.777])
        p4.setXUnit('um')


        path = Img_2014_06_16_LE72270652014167CUB00_BOA
        ext = SpatialExtent.fromRasterSource(path)
        posA = ext.spatialCenter()
        posB = SpatialPoint(posA.crs(), posA.x()+60, posA.y()+ 90)

        p5 = SpectralProfile.fromRasterSource(path, posA)
        p5.setName('Position A')
        p6 = SpectralProfile.fromRasterSource(path, posB)
        p6.setName('Position B')
        speclib.addProfiles([p1, p2, p3, p4, p5, p6])

        return speclib


    def test_fields(self):

        f = createQgsField('foo', 9999)

        self.assertEqual(f.name(),'foo')
        self.assertEqual(f.type(), QVariant.Int)
        self.assertEqual(f.typeName(), 'int')

        f = createQgsField('bar', 9999.)
        self.assertEqual(f.type(), QVariant.Double)
        self.assertEqual(f.typeName(), 'double')


    def test_AttributeDialog(self):

        speclib = self.createSpeclib()

        d = AddAttributeDialog(speclib)
        d.exec_()

        if d.result() == QDialog.Accepted:
            field = d.field()
            self.assertIsInstance(field, QgsField)
            s = ""
        s = ""


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
            self.assertIsInstance(p.geometry(), QgsGeometry)
            self.assertTrue(p.hasGeometry())




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
        sp1.setName('Name A')
        sp1.setYValues([0, 4, 3, 2, 1])
        sp1.setXValues([450, 500, 750, 1000, 1500])


        sp2 = SpectralProfile()
        sp2.setName('Name B')
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

        sl2 = sl1.speclibFromFeatureIDs(sl1[:][1].id())
        self.assertIsInstance(sl2, SpectralLibrary)
        self.assertEqual(len(sl2), 1)
        self.assertEqual(sl2[0], sl1[1])


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
            self.assertIsInstance(sl[0], SpectralProfile)
            self.assertTrue(sl[0].hasGeometry())

        self.assertTrue(len(sl3) == 2)


    def test_others(self):

        self.assertEqual(23, toType(int, '23'))
        self.assertEqual([23, 42], toType(int, ['23','42']))
        self.assertEqual(23., toType(float, '23'))
        self.assertEqual([23., 42.], toType(float, ['23','42']))

        self.assertTrue(findTypeFromString('23') is int)
        self.assertTrue(findTypeFromString('23.3') is float)
        self.assertTrue(findTypeFromString('xyz23.3') is str)
        self.assertTrue(findTypeFromString('') is str)

        regex = CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN

        #REGEX to identify band value column names

        for text in ['b1', 'b1_']:
            match = regex.match(text)
            self.assertEqual(match.group('band'), '1')
            self.assertEqual(match.group('xvalue'), None)
            self.assertEqual(match.group('xunit'), None)


        match = regex.match('b1 23.34 nm')
        self.assertEqual(match.group('band'), '1')
        self.assertEqual(match.group('xvalue'), '23.34')
        self.assertEqual(match.group('xunit'), 'nm')


    def test_io(self):

        sl1 = self.createSpeclib()
        tempDir = tempfile.gettempdir()
        tempDir = os.path.join(DIR_REPO, *['test','outputs'])
        pathESL = os.path.join(tempDir,'speclibESL.esl')
        pathCSV = os.path.join(tempDir,'speclibCSV.csv')

        #test clipboard IO
        QApplication.clipboard().setMimeData(QMimeData())
        self.assertFalse(ClipboardIO.canRead())
        writtenFiles = ClipboardIO.write(sl1)
        self.assertEqual(len(writtenFiles), 0)
        self.assertTrue(ClipboardIO.canRead())
        sl1b = ClipboardIO.readFrom()
        self.assertIsInstance(sl1b, SpectralLibrary)
        self.assertEqual(sl1, sl1b)

        #!!! clear clipboard
        QApplication.clipboard().setMimeData(QMimeData())


        #test ENVI Spectral Library
        writtenFiles = EnviSpectralLibraryIO.write(sl1, pathESL)
        n = 0
        for path in writtenFiles:
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith('.sli'))

            basepath = os.path.splitext(path)[0]
            pathHDR = basepath + '.hdr'
            pathCSV = basepath + '.csv'
            self.assertTrue(os.path.isfile(pathHDR))
            self.assertTrue(os.path.isfile(pathCSV))

            self.assertTrue(EnviSpectralLibraryIO.canRead(path))
            sl_read1 = EnviSpectralLibraryIO.readFrom(path)
            self.assertIsInstance(sl_read1, SpectralLibrary)
            sl_read2 = SpectralLibrary.readFrom(path)
            self.assertIsInstance(sl_read2, SpectralLibrary)
            print(sl_read1)
            self.assertTrue(len(sl_read1) > 0)
            self.assertEqual(sl_read1, sl_read2)
            n += len(sl_read1)
        self.assertEqual(len(sl1) - 1, n ) #-1 because of a missing data profile


        #TEST CSV writing
        writtenFiles = sl1.exportProfiles(pathCSV)
        self.assertIsInstance(writtenFiles, list)
        self.assertTrue(len(writtenFiles) == 1)

        n = 0
        for path in writtenFiles:
            f = open(path, encoding='utf-8')
            text = f.read()
            lines = [l.strip() for l in text.splitlines()]
            lines = [l for l in lines if len(l) > 0 and not l.startswith('WKT')]
            nProfiles = len(lines)

            f.close()

            self.assertTrue(CSVSpectralLibraryIO.canRead(path))
            sl_read1 = CSVSpectralLibraryIO.readFrom(path)
            sl_read2 = SpectralLibrary.readFrom(path)

            self.assertIsInstance(sl_read1, SpectralLibrary)
            self.assertIsInstance(sl_read2, SpectralLibrary)

            n += len(sl_read1)
        self.assertEqual(n, len(sl1)-1)





        self.SPECLIB = sl1


    def test_mergeSpeclibs(self):

        sp = SpectralProfile()
        fieldName = 'newField'
        sp.setMetadata(fieldName, 'foo', addMissingFields=True)
        sl = SpectralLibrary()
        sl.startEditing()
        sl.addAttribute(createQgsField(fieldName, ''))
        sl.commitChanges()
        self.assertIn(fieldName, sl.fieldNames())

        sl = SpectralLibrary()
        sl.addProfiles(sp)

        sl = SpectralLibrary()
        self.assertTrue(fieldName not in sl.fieldNames())
        self.assertTrue(len(sl) == 0)
        sl.addProfiles(sp, addMissingFields=False)
        self.assertTrue(fieldName not in sl.fieldNames())
        self.assertTrue(len(sl) == 1)


        sl = SpectralLibrary()
        self.assertTrue(fieldName not in sl.fieldNames())
        sl.addProfiles(sp, addMissingFields=True)
        self.assertTrue(fieldName in sl.fieldNames())
        self.assertTrue(len(sl) == 1)
        p = sl[0]
        self.assertIsInstance(p, SpectralProfile)
        self.assertEqual(p.metadata(fieldName), sp.metadata(fieldName))

    def test_filterModel(self):
        w = QFrame()
        speclib = self.createSpeclib()
        dmodel = SpectralLibraryTableModel(speclib, parent=w)
        fmodel = SpectralLibraryTableFilterModel(dmodel, parent=w)

        cnt = len(speclib)
        self.assertEqual(cnt, dmodel.rowCount())
        speclib.removeProfiles(speclib[0])
        self.assertEqual(cnt - 1, len(speclib))
        self.assertEqual(cnt - 1, dmodel.rowCount())
        self.assertEqual(cnt - 1, fmodel.rowCount())



        #https://stackoverflow.com/questions/671340/qsortfilterproxymodel-maptosource-crashes-no-info-why
        #!!! use filterModel.index(row, col), NOT filterModel.createIndex(row, col)!
        fmodel.sort(0, Qt.DescendingOrder)

        idx0f = fmodel.index(0,0)
        idx0d = fmodel.mapToSource(idx0f)

        self.assertNotEqual(idx0f.row(), idx0d.row())

        namef = fmodel.data(idx0f, Qt.DisplayRole)
        named = dmodel.data(idx0d, Qt.DisplayRole)
        self.assertEqual(namef, named)




    def test_speclibTableView(self):

        v = SpectralLibraryTableView()
        v.show()

    def test_speclibWidget(self):

        speclib = self.createSpeclib()
        p = SpectralLibraryWidget()
        p.addSpeclib(speclib)
        p.show()

        self.assertEqual(p.speclib(), speclib)

        p = SpectralLibraryWidget()
        p.show()

        self.assertIsInstance(p.speclib(), SpectralLibrary)
        fieldNames = p.speclib().fieldNames()
        self.assertIsInstance(fieldNames, list)

        self.assertIsInstance(p.mModel, SpectralLibraryTableModel)
        self.assertTrue(p.mModel.headerData(0, Qt.Horizontal) == fieldNames[0])

        cs = [speclib[0], speclib[3], speclib[-1]]
        p.setAddCurrentSpectraToSpeclibMode(False)
        p.setCurrentSpectra(cs)
        self.assertTrue(len(p.speclib()) == 0)
        p.addCurrentSpectraToSpeclib()
        self.assertTrue(len(p.speclib()) == len(cs))
        self.assertEqual(p.speclib()[:], cs)

        p.speclib().removeProfiles(p.speclib()[:])
        self.assertTrue(len(p.speclib()) == 0)

        p.setAddCurrentSpectraToSpeclibMode(True)
        p.setCurrentSpectra(cs)
        self.assertTrue(len(p.speclib()) == len(cs))

        qapp.exec_()
    def test_plotWidget(self):

        speclib = self.createSpeclib()
        model = SpectralLibraryTableModel(speclib=speclib)
        w = SpectralLibraryPlotWidget()
        w.setModel(model)

        self.assertIsInstance(w, SpectralLibraryPlotWidget)

        pdis = [i for i in w.plotItem.items if isinstance(i, SpectralProfilePlotDataItem)]
        self.assertTrue(len(speclib), len(pdis))
        for pdi in pdis:
            self.assertTrue(pdi.isVisible())


        p = speclib[3]
        fid = p.id()

        speclib.removeProfiles(p)

        pdis = [i for i in w.plotItem.items if isinstance(i, SpectralProfilePlotDataItem)]
        for pdi in pdis:
            self.assertFalse(pdi.mProfile.id() == fid)




if __name__ == '__main__':
    unittest.main()
