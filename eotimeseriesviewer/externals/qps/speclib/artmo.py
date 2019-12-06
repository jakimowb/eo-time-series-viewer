
import os, sys, re, pathlib, json, io, re, linecache, collections
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import csv as pycsv
from .spectrallibraries import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, FIELD_FID, FIELD_VALUES, FIELD_NAME, findTypeFromString, createQgsField

class ARTMOSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for ARTMO CSV profile outputs.
    See https://artmotoolbox.com/tools.html for details.
    """
    @staticmethod
    def canRead(path:str):
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        if not isinstance(path, str) and os.path.isfile(path):
            return False

        # check if an _meta.txt exists
        pathMeta = os.path.splitext(path)[0] + '_meta.txt'
        if not os.path.isfile(pathMeta):
            return False

        with open(pathMeta, 'r', encoding='utf-8') as f:
            for line in f:
                if re.search(r'Line 1, Column \d \.{3} end:', line, re.I):
                    return True

        return False

    @staticmethod
    def readFrom(path, progressDialog:QProgressDialog=None)->SpectralLibrary:
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


    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

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

