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
qapp = initQgisApplication()

from timeseriesviewer.spectrallibraries import *

class TestInit(unittest.TestCase):

    def setUp(self):

        self.SP = None
        self.SPECLIB = None

    def test_spectralprofile(self):
        spec1 = SpectralProfile()


        spec1.setValues([0,4,3,2,1],['-'], [450,500,750, 1000, 1500], 'nm')


        values = [('key','value'),('key', 100),('Üä','ÜmlÄute')]
        for md in values:
            k, v = md
            spec1.setMetadata(k,v)
            v2 = spec1.metadata(k)
            self.assertEqual(v,v2)

        self.SP = spec1

    def test_spectralLibrary(self):

        spec1 = SpectralProfile()
        spec1.setValues([0, 4, 3, 2, 1], ['-'], [450, 500, 750, 1000, 1500], 'nm')

        spec2 = SpectralProfile()
        spec2.setValues([3, 2, 1, 0, 1], ['-'], [450, 500, 750, 1000, 1500], 'nm')

        sl = SpectralLibrary()
        sl.addProfiles([spec1, spec2])
        self.assertEqual(len(sl),2)
        self.assertEqual(sl[0], spec1)


        tempDir = tempfile.gettempdir()
        pathESL = tempfile.mktemp(prefix='speclib.', suffix='.esl')
        pathCSV = tempfile.mktemp(prefix='speclib.', suffix='.csv')
        try:
            sl.exportProfiles(pathESL)
        except Exception as ex:
            self.fail('Unable to write ESL. {}'.format(ex))

        try:
            sl2 = SpectralLibrary.readFrom(pathESL)
        except Exception as ex:
            self.fail('Unable to read ESL. {}'.format(ex))


        try:
            sl.exportProfiles(pathCSV)
        except Exception as ex:
            self.fail('Unable to write CSV. {}'.format(ex))

        try:
            sl2 = SpectralLibrary.readFrom(pathCSV)
        except Exception as ex:
            self.fail('Unable to read CSV. {}'.format(ex))




        self.SPECLIB = sl

    def test_speclibWidget(self):
        p = SpectralLibraryWidget()
        p.addSpeclib(self.SPECLIB)
        p.show()







        pass


if __name__ == '__main__':
    unittest.main()
