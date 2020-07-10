# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/artmo.py

    Input/Output of ARTMO spectral library data
    ---------------------
    Beginning            : 2019-09-03
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import os, sys, re, pathlib, json, io, re, linecache, collections, typing
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import csv as pycsv
from ..core import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, \
    FIELD_FID, FIELD_VALUES, FIELD_NAME, findTypeFromString, createQgsField, \
    ProgressHandler

class ARTMOSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for ARTMO CSV profile outputs.
    See https://artmotoolbox.com/tools.html for details.
    """
    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        if not isinstance(path, str) and os.path.isfile(path):
            return False
        try:
            # check if an _meta.txt exists
            pathMeta = os.path.splitext(path)[0] + '_meta.txt'
            if not os.path.isfile(pathMeta):
                return False

            with open(pathMeta, 'r', encoding='utf-8') as f:
                for line in f:
                    if re.search(r'Line 1, Column \d \.{3} end:', line, re.I):
                        return True
        except Exception:
            return False

        return False

    @classmethod
    def readFrom(cls, path: str, progressDialog:typing.Union[QProgressDialog, ProgressHandler] = None) -> SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """
        delimiter = ','
        xUnit = 'nm'
        bn = os.path.basename(path)

        pathMeta = os.path.splitext(path)[0]+'_meta.txt'

        assert os.path.isfile(path)
        assert os.path.isfile(pathMeta)


        with open(pathMeta, 'r', encoding='utf-8') as f:

            meta = f.read()

        header = re.search(r'Line (\d+).*Column (\d+) ... end: Wavelength', meta)
        firstLine = int(header.group(1)) - 1
        firstXValueColumn = int(header.group(2)) - 1

        COLUMNS = collections.OrderedDict()
        for c, name in re.findall(r'Column (\d+): ([^\t]+)', meta):
            COLUMNS[int(c)-1] = name



        speclib = SpectralLibrary()
        speclib.startEditing()

        for name in COLUMNS.values():
            speclib.addAttribute(createQgsField(name, 1.0))
        speclib.commitChanges()


        profiles = []

        with open(path, 'r', encoding='utf-8') as f:
            for iLine, line in enumerate(f.readlines()):

                if len(line) == 0:
                    continue

                parts = line.split(delimiter)
                if iLine == firstLine:
                    # read the header data

                    xValues = [float(v) for v in parts[firstXValueColumn:]]
                elif iLine > firstLine:


                    yValues = [float(v) for v in parts[firstXValueColumn:]]
                    profile = SpectralProfile(fields=speclib.fields())

                    name = None
                    if name is None:
                        name = '{}:{}'.format(bn, len(profiles) +1)

                    profile.setName(name)

                    for iCol, name in COLUMNS.items():
                        profile.setAttribute(name, float(parts[iCol]))

                    profile.setValues(x=xValues, y=yValues, xUnit=xUnit)
                    profiles.append(profile)





        speclib.startEditing()
        speclib.addProfiles(profiles)
        speclib.commitChanges()
        return speclib


    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='ARTMO CSV File',
                                               filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if os.path.isfile(path):

                sl = ARTMOSpectralLibraryIO.readFrom(path)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add ARTMO profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('ARTMO')
        m.setToolTip('Adds profiles from an ARTMO csv text file.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))

