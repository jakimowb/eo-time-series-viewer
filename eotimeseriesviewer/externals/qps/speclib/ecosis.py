
import os, sys, re, pathlib, json, io, re, linecache
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *


import csv as pycsv
from .spectrallibraries import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, FIELD_FID, FIELD_VALUES, FIELD_NAME, findTypeFromString, createQgsField

class EcoSISCSVDialect(pycsv.Dialect):
    delimiter = ','
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\n'
    escapechar = '\\'
    quoting = pycsv.QUOTE_NONE


def findDialect(file)->pycsv.Dialect:

    if isinstance(file, str):
        file = open(file, 'r', encoding='utf-8')

    line = ''
    while len(line) == 0:
        line = file.readline()


    delimiters = [',', ';', '\t']
    counts = [len(line.split(delimiter)) for delimiter in delimiters]


    dialect = EcoSISCSVDialect()
    dialect.delimiter = delimiters[counts.index(max(counts))]
    dialect.lineterminator = '\n\r' if line.endswith('\n\r') else line[-1]

    file.seek(0)
    s = ""
    return dialect

class EcoSISSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for the EcoSIS spectral library format.
    See https://ecosis.org for details.
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
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = f.readline().strip()
                    if len(line) > 0:
                        # most-right header name must be a number
                        lastColumn = [c for c in re.split(r'[\t\n;,]', line) if c != ''][-1]
                        return re.search(r'^\d+(\.\d+)?$', lastColumn) is not None
        except Exception as ex:
            print(ex, file=sys.stderr)

        return False

    @staticmethod
    def readFrom(path, progressDialog:QProgressDialog=None)->SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """

        # the EcoSIS CSV outputs are encoded as UTF-8 with BOM
        with open(path, 'r', encoding='utf-8-sig') as f:

            bn = os.path.basename(path)

            dialect = findDialect(f)

            reader = pycsv.DictReader(f, dialect=dialect)
            fieldnames = reader.fieldnames

            if fieldnames[0].startswith('\ufeff'):
                s = ""
            fieldnames = [n for n in fieldnames if len(n) > 0]


            xUnit = yUnit = None
            xValueNames = []
            for fieldName in reversed(fieldnames):
                if re.search(r'^\d+(\.\d+)?$', fieldName):
                    xValueNames.insert(0, fieldName)
                else:
                    break
            s = ""
            xValues = [float(n) for n in xValueNames]
            if len(xValues) == 0:
                s = ""
            if xValues[0] > 200:
                xUnit = 'nm'


            fieldnames = [n for n in fieldnames if n not in xValueNames]

            speclib = SpectralLibrary()
            speclib.startEditing()

            profiles = []
            LUT_FIELD_TYPES = dict()
            missing_field_definitions = [n for n in fieldnames if n not in speclib.fieldNames()]
            for i, row in enumerate(reader):
                if len(missing_field_definitions) > 0:
                    for fieldName in missing_field_definitions[:]:
                        fieldValue = row[fieldName]
                        if fieldValue == 'NA':
                            continue

                        fieldType = findTypeFromString(fieldValue)
                        LUT_FIELD_TYPES[fieldName] = fieldType

                        qgsField = createQgsField(fieldName, fieldType(fieldValue))
                        speclib.addAttribute(qgsField)
                        assert speclib.commitChanges()
                        speclib.startEditing()
                        missing_field_definitions.remove(fieldName)

                profile = SpectralProfile(fields=speclib.fields())
                yValues = [float(row[n]) for n in xValueNames]
                profile.setValues(x=xValues, y=yValues, xUnit=xUnit, yUnit=yUnit)

                for fieldName, fieldType in LUT_FIELD_TYPES.items():
                    fieldValue = fieldType(row[fieldName])
                    profile.setAttribute(fieldName, fieldValue)

                if FIELD_NAME not in fieldnames:
                    profile.setName('{}:{}'.format(bn, i+1))
                else:
                    profile.setName(row[FIELD_NAME])
                profiles.append(profile)

            speclib.addProfiles(profiles)


            s = ""
        s = ""
        assert speclib.commitChanges()
        return speclib

    @staticmethod
    def write(speclib:SpectralLibrary, path:str, progressDialog:QProgressDialog, delimiter:str=';'):
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
        """
        assert isinstance(speclib, SpectralLibrary)
        basePath, ext = os.path.splitext(path)
        s = ""

        writtenFiles = []
        fieldNames = [n for n in speclib.fields().names() if n not in [FIELD_VALUES, FIELD_FID]]
        groups = speclib.groupBySpectralProperties()
        for i, grp in enumerate(groups.keys()):
            # in-memory text buffer
            stream = io.StringIO()
            xValues, xUnit, yUnit = grp
            profiles = groups[grp]
            if i == 0:
                path = basePath + ext
            else:
                path = basePath + '{}{}'.format(i+1, ext)


            headerNames = fieldNames + [str(v) for v in xValues]
            W = pycsv.DictWriter(stream, fieldnames=headerNames, dialect=EcoSISCSVDialect())
            W.writeheader()

            for profile in profiles:
                assert isinstance(profile, SpectralProfile)

                rowDict = dict()
                for n in fieldNames:
                    v = profile.attribute(n)
                    if v in [None, QVariant(None), '']:
                        v = 'NA'
                    rowDict[n] = v

                yValues = profile.yValues()
                for i, xValue in enumerate(xValues):
                    rowDict[str(xValue)] = yValues[i]
                W.writerow(rowDict)

            stream.write('\n')
            lines = stream.getvalue().replace('\r', '')

            with open(path, 'w', encoding='utf-8') as f:
                f.write(lines)
                writtenFiles.append(path)

        return writtenFiles

    @staticmethod
    def score(uri:str)->int:
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probalby thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        return 0

    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='EcoSIS CSV File',
                                               filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if os.path.isfile(path):

                sl = EcoSISSpectralLibraryIO.readFrom(path)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add EcoSIS profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('EcoSIS')
        m.setToolTip('Adds profiles from an EcoSIS csv text file.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))


    @staticmethod
    def addExportActions(spectralLibrary:SpectralLibrary, menu:QMenu) -> list:

        def write(speclib: SpectralLibrary):

            path, filter = QFileDialog.getSaveFileName(caption='Write to EcoSIS CSV File',
                                                    filter='EcoSIS CSV (*.csv);;Text files (*.txt)')
            if isinstance(path, str) and len(path) > 0:
                sl = EcoSISSpectralLibraryIO.write(spectralLibrary, path)

        m = menu.addAction('EcoSIS CSV')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))