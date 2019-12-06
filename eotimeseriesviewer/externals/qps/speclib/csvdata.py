# -*- coding: utf-8 -*-
#!/usr/bin/env python3
# noinspection PyPep8Naming
"""
***************************************************************************
    csv.py
    Reading and writing spectral profiles from CSV data
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This file is part of the EnMAP-Box.                                   *
*                                                                         *
*   The EnMAP-Box is free software; you can redistribute it and/or modify *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
*   The EnMAP-Box is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          *
*   GNU General Public License for more details.                          *
*                                                                         *
*   You should have received a copy of the GNU General Public License     *
*   along with the EnMAP-Box. If not, see <http://www.gnu.org/licenses/>. *
*                                                                         *
***************************************************************************
"""
import os, sys, re, pathlib, json
import csv as pycsv
from .spectrallibraries import *

# max size a CSV file can have, in MBytes
MAX_CSV_SIZE = 5


class CSVSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    SpectralLibrary IO with CSV files.
    """
    STD_NAMES = ['WKT']+[n for n in createStandardFields().names()]
    REGEX_HEADERLINE = re.compile('^'+'[\t;,]'.join(STD_NAMES)+'\\t.*')
    REGEX_BANDVALUE_COLUMN = re.compile(r'^(?P<bandprefix>\D+)?(?P<band>\d+)[ _]*(?P<xvalue>-?\d+\.?\d*)?[ _]*(?P<xunit>\D+)?', re.IGNORECASE)

    @staticmethod
    def addImportActions(spectralLibrary:SpectralLibrary, menu:QMenu)->list:

        def read(speclib:SpectralLibrary, dialect):

            path, ext = QFileDialog.getOpenFileName(caption='Import CSV File', filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if isinstance(path, str) and os.path.isfile(path):

                sl = CSVSpectralLibraryIO.readFrom(path, dialect)
                if isinstance(sl, SpectralLibrary):
                    speclib.addSpeclib(sl, True)
        m = menu.addMenu('CSV')

        a = m.addAction('Excel (TAB)')
        a.setToolTip('Imports Spectral Profiles from a Excel CSV sheet.')
        a.triggered.connect(lambda *args, sl=spectralLibrary: read(sl, pycsv.excel_tab))

        a = m.addAction('Excel (,)')
        a.setToolTip('Imports Spectral Profiles from a Excel CSV sheet.')
        a.triggered.connect(lambda *args, sl=spectralLibrary: read(sl, pycsv.excel))

    @staticmethod
    def addExportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def write(speclib: SpectralLibrary):
            path, filter = QFileDialog.getSaveFileName(caption='Write to CSV File',
                                                       filter='CSV (*.csv);;Text files (*.txt)')
            if isinstance(path, str) and len(path) > 0:
                CSVSpectralLibraryIO.write(spectralLibrary, path)


        m = menu.addAction('CSV Table')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))

    @staticmethod
    def isHeaderLine(line: str) -> str:
        """
        Returns True if str ``line`` could be a CSV header
        :param line: str
        :return: str with CSV dialect
        """
        for dialect in [pycsv.excel_tab, pycsv.excel]:
            fieldNames = [n.lower() for n in pycsv.DictReader([line], dialect=dialect).fieldnames]
            for column in ['wkt', 'name', 'fid', 'source', 'b1']:
                if column in fieldNames:
                    return dialect
        return None

    @staticmethod
    def canRead(path=None):
        if not isinstance(path, str):
            return False

        if not os.path.isfile(path):
            return False

        mbytes = os.path.getsize(path) / 1000 ** 2
        if mbytes > MAX_CSV_SIZE:
            return False

        try:

            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if len(line) > 0 and not line.startswith('#'):
                        dialect = CSVSpectralLibraryIO.isHeaderLine(line)
                        if dialect is not None:
                            return dialect
        except Exception as ex:
            return None
        return None



    @staticmethod
    def write(speclib, path, progressDialog:QProgressDialog=None, dialect=pycsv.excel_tab)->list:
        """
        Writes the speclib into a CSv file
        :param speclib: SpectralLibrary
        :param path: str
        :param dialect: CSV dialect, python csv.excel_tab by default
        :return: [list-with-csv-filepath]
        """
        assert isinstance(speclib, SpectralLibrary)

        text = CSVSpectralLibraryIO.asString(speclib, dialect=dialect)
        file = open(path, 'w')
        file.write(text)
        file.close()
        return [path]

    @staticmethod
    def readFrom(path=None, progressDialog:QProgressDialog=None, dialect=pycsv.excel_tab):
        f = open(path, 'r', encoding='utf-8')
        text = f.read()
        f.close()

        return CSVSpectralLibraryIO.fromString(text, dialect=dialect)

    @staticmethod
    def extractDataBlocks(text:str)->(list, list):
        # divides a text into blocks of CSV rows with same column structure
        lines = text.splitlines(keepends=True)
        # lines = [l.strip() for l in lines]
        # lines = [l for l in lines if len(l) > 0 and not l.startswith('#')]
        BLOCKDATA = []
        BLOCKMETADATA = []
        currentBlock = ''
        iBlockStart = None

        def headerLineMetadata(iLine)->dict:
            # check for #META tag
            metadata = {}
            if isinstance(iLine, int) and iBlockStart > 0:
                if lines[iLine - 1].startswith('#META='):
                    try:
                        metadata = json.loads(re.sub('#META=', '', lines[iLine - 1]))
                    except Exception as ex:
                        print('Unable to retrieve CSV json metadata from line {}: "{}"'
                              .format(iLine - 1, lines[iLine - 1]))
            return metadata

        for iLine, line in enumerate(lines):
            assert isinstance(line, str)

            if len(line.strip()) == 0 or line.startswith('#'):
                continue

            if CSVSpectralLibraryIO.isHeaderLine(line):
                if len(currentBlock) > 1:
                    BLOCKMETADATA.append(headerLineMetadata(iBlockStart))
                    BLOCKDATA.append(currentBlock)

                # start new block
                iBlockStart = iLine
                currentBlock = line
            else:
                if not currentBlock.endswith('\n'):
                    currentBlock += '\n'
                currentBlock += line

        if len(currentBlock) > 1:
            BLOCKMETADATA.append(headerLineMetadata(iBlockStart))
            BLOCKDATA.append(currentBlock)

        assert len(BLOCKDATA) == len(BLOCKMETADATA)
        return BLOCKDATA, BLOCKMETADATA

    @staticmethod
    def fromString(text:str, dialect=pycsv.excel_tab):
        """
        Reads oneCSV
        :param text:
        :param dialect:
        :return:
        """
        BLOCKDATA, BLOCKMETADATA = CSVSpectralLibraryIO.extractDataBlocks(text)

        SLIB = SpectralLibrary()
        SLIB.startEditing()

        # read and add CSV blocks
        for blockData, blockMetaData in zip(BLOCKDATA, BLOCKMETADATA):

            R = pycsv.DictReader(blockData.splitlines(), dialect=dialect)

            # read entire CSV table
            columnVectors = {}
            for n in R.fieldnames:
                columnVectors[n] = []

            nProfiles = 0
            for i, row in enumerate(R):
                for k, v in row.items():
                    columnVectors[k].append(v)
                nProfiles += 1

            # find missing fields, detect data type for and them to the SpectralLibrary
            bandValueColumnNames = [n for n in R.fieldnames if re.search(r'^b\d+$', n, re.I)]
            bandValueColumnNames = sorted(bandValueColumnNames, key = lambda n: int(n[1:]))
            specialHandlingColumns = bandValueColumnNames + ['WKT']
            addGeometry = 'WKT' in R.fieldnames
            addYValues = False
            xUnit = blockMetaData.get('xunit', None)
            yUnit = blockMetaData.get('yunit', None)
            x = blockMetaData.get('xvalues', None)

            if isinstance(x, list):
                if len(x) > 0 and not len(x) == len(bandValueColumnNames):
                    print('Unable to extract xValues (e.g. wavelength)',
                          file=sys.stderr)
                    x = None

            missingQgsFields = []

            # find data type of missing fields
            for n in R.fieldnames:
                assert isinstance(n, str)
                if n in specialHandlingColumns:
                    continue

                # find a none-empty string which describes a
                # data value, get the type for and convert all str values into
                values = columnVectors[n]

                t = str
                v = ''
                for value in values:
                    if value is not None and len(value) > 0:
                        t = findTypeFromString(value)
                        v = toType(t, value)
                        break
                qgsField = createQgsField(n, v)
                if n in bandValueColumnNames:
                    s = ""

                # convert values to int, float or str
                columnVectors[n] = toType(t, values, empty2None=True)
                missingQgsFields.append(qgsField)

            # add missing fields
            if len(missingQgsFields) > 0:
                SLIB.addMissingFields(missingQgsFields)

            # create a feature for each row
            yValueType = None
            for i in range(nProfiles):
                p = SpectralProfile(fields=SLIB.fields())
                if addGeometry:
                    g = QgsGeometry.fromWkt(columnVectors['WKT'][i])
                    p.setGeometry(g)

                if len(bandValueColumnNames) > 0:
                    y = [columnVectors[n][i] for n in bandValueColumnNames]
                    if yValueType is None and len(y) > 0:
                        yValueType = findTypeFromString(y[0])

                    y = toType(yValueType, y, True)
                    p.setValues(y=y, x=x, xUnit=xUnit, yUnit=yUnit)

                # add other attributes
                for n in [n for n in p.fieldNames() if n in list(columnVectors.keys())]:

                    p.setAttribute(n, columnVectors[n][i])

                SLIB.addFeature(p)


        SLIB.commitChanges()
        return SLIB


    @staticmethod
    def asString(speclib:SpectralLibrary, dialect=pycsv.excel_tab, skipValues=False, skipGeometry=False)->str:
        """
        Returns a SpectralLibrary as CSV string
        :param speclib:
        :param dialect:
        :param skipValues:
        :param skipGeometry:
        :return: str
        """
        assert isinstance(speclib, SpectralLibrary)

        attributeNames = [n for n in speclib.fieldNames() if n not in [FIELD_VALUES]]

        # in-memory text buffer
        stream = io.StringIO()

        for iCSVTable, item in enumerate(speclib.groupBySpectralProperties(excludeEmptyProfiles=False).items()):
            xvalues, xunit, yunit = item[0]
            profiles = item[1]
            refProfile = profiles[0]
            assert isinstance(refProfile, SpectralProfile)
            nbands = len(refProfile.xValues())
            nattributes = len(refProfile.attributes())
            jsonData = {'xvalues': xvalues, 'xunit': xunit, 'yunit': yunit, 'nbands': nbands, 'nattributes': nattributes}
            jsonString = json.dumps(jsonData)
            stream.write('#META={}\n'.format(jsonString))

            assert isinstance(profiles, list)

            bandNames = ['b{}'.format(i + 1) for i in range(nbands)]
            fieldnames = []

            if not skipGeometry:
                fieldnames.append('WKT')

            fieldnames.extend(attributeNames)
            if not skipValues:
                fieldnames.extend(bandNames)

            W = pycsv.DictWriter(stream, fieldnames=fieldnames, dialect=dialect)
            W.writeheader()
            for p in profiles:
                assert isinstance(p, SpectralProfile)
                D = dict()

                # write the geometry
                if not skipGeometry:
                    D['WKT'] = p.geometry().asWkt()

                # write the attributes
                for n in attributeNames:
                    D[n] = value2str(p.attribute(n)).replace('\n', '')

                # write profile values
                if not skipValues:
                    for iValue, yValue in enumerate(p.yValues()):
                        if iValue >= len(bandNames):
                            s = ""
                        D[bandNames[iValue]] = yValue

                W.writerow(D)

            stream.write('\n')
        return stream.getvalue().replace('\r', '')


class CSVWriterFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):
    """
    A QgsVectorFileWriter.FieldValueConverter to convers SpectralLibrary values into strings
    """
    def __init__(self, speclib):
        super(CSVWriterFieldValueConverter, self).__init__()
        self.mSpeclib = speclib
        self.mNames = self.mSpeclib.fields().names()
        self.mCharactersToReplace = '\t'
        self.mReplacement = ' '

    def setSeparatorCharactersToReplace(self, charactersToReplace, replacement:str= ' '):
        """
        Specifies characters that need to be masked in string, i.e. the separator, to not violate the CSV structure.
        :param charactersToReplace: str | list of strings
        :param replacement: str, Tabulator by default
        """
        if isinstance(charactersToReplace, str):
            charactersToReplace = [charactersToReplace]
        assert replacement not in charactersToReplace
        self.mCharactersToReplace = charactersToReplace
        self.mReplacement = replacement

    def clone(self):
        c = CSVWriterFieldValueConverter(self.mSpeclib)
        c.setSeparatorCharactersToReplace(self.mCharactersToReplace, replacement=self.mReplacement)
        return c

    def convert(self, i, value):
        name = self.mNames[i]
        if name.startswith(FIELD_VALUES):
            return json.loads(value)
        else:
            v = str(value)
            for c in self.mCharactersToReplace:
                v = v.replace(c, self.mReplacement)
            return v

    def fieldDefinition(self, field):
        return field

