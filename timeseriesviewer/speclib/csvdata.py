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
import os, sys, re, pathlib
import csv as pycsv
from .spectrallibraries import *

class CSVSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    SpectralLibrary IO with CSV files.
    """
    STD_NAMES = ['WKT']+[n for n in createStandardFields().names()]
    REGEX_HEADERLINE = re.compile('^'+'\\t'.join(STD_NAMES)+'\\t.*')
    REGEX_BANDVALUE_COLUMN = re.compile(r'^(?P<bandprefix>\D+)?(?P<band>\d+)[ _]*(?P<xvalue>-?\d+\.?\d*)?[ _]*(?P<xunit>\D+)?', re.IGNORECASE)

    @staticmethod
    def canRead(path=None):
        if not isinstance(path, str):
            return False

        found = False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if CSVSpectralLibraryIO.REGEX_HEADERLINE.search(line):
                        found = True
                        break
        except Exception as ex:
            return False
        return found

    @staticmethod
    def write(speclib, path, dialect=pycsv.excel_tab):
        assert isinstance(speclib, SpectralLibrary)

        text = CSVSpectralLibraryIO.asString(speclib, dialect=dialect)
        file = open(path, 'w')
        file.write(text)
        file.close()
        return [path]

    @staticmethod
    def readFrom(path=None, dialect=pycsv.excel_tab):
        f = open(path, 'r', encoding='utf-8')
        text = f.read()
        f.close()

        return CSVSpectralLibraryIO.fromString(text, dialect=dialect)

    @staticmethod
    def fromString(text:str, dialect=pycsv.excel_tab):
        # divide the text into blocks of CSV rows with same columns structure
        lines = text.splitlines(keepends=True)
        blocks = []
        currentBlock = ''
        for line in lines:
            assert isinstance(line, str)
            if len(line.strip()) == 0:
                continue
            if CSVSpectralLibraryIO.REGEX_HEADERLINE.search(line):
                if len(currentBlock) > 1:
                    blocks.append(currentBlock)

                #start new block
                currentBlock = line
            else:
                currentBlock += line
        if len(currentBlock) > 1:
            blocks.append(currentBlock)
        if len(blocks) == 0:
            return None

        SLIB = SpectralLibrary()
        SLIB.startEditing()

        #read and add CSV blocks
        for block in blocks:
            R = pycsv.DictReader(block.splitlines(), dialect=dialect)

            #read entire CSV table
            columnVectors = {}
            for n in R.fieldnames:
                columnVectors[n] = []

            nProfiles = 0
            for i, row in enumerate(R):
                for k, v in row.items():
                    columnVectors[k].append(v)
                nProfiles += 1

            #find missing fields, detect data type for and them to the SpectralLibrary

            bandValueColumnNames = sorted([n for n in R.fieldnames
                                       if CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN.match(n)])
            specialHandlingColumns = bandValueColumnNames + ['WKT']
            addGeometry = 'WKT' in R.fieldnames
            addYValues = False
            xUnit = None
            x = []

            if len(bandValueColumnNames) > 0:
                addYValues = True
                for n in bandValueColumnNames:
                    match = CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN.match(n)
                    xValue = match.group('xvalue')
                    if xUnit == None:
                        # extract unit from first columns that defines one
                        xUnit = match.group('xunit')
                    if xValue:
                        t = findTypeFromString(xValue)
                        x.append(toType(t, xValue))



            if len(x) > 0 and not len(x) == len(bandValueColumnNames):
                print('Inconsistant band value column names. Unable to extract xValues (e.g. wavelength)', file=sys.stderr)
                x = None
            elif len(x) == 0:
                x = None
            missingQgsFields = []

            #find data type of missing fields
            for n in R.fieldnames:
                assert isinstance(n, str)
                if n in specialHandlingColumns:
                    continue

                #find a none-empty string which describes a
                #data value, get the type for and convert all str values into
                values = columnVectors[n]

                t = str
                v = ''
                for v in values:
                    if len(v) > 0:
                        t = findTypeFromString(v)
                        v = toType(t, v)
                        break
                qgsField = createQgsField(n, v)
                if n in bandValueColumnNames:
                    s = ""

                #convert values to int, float or str
                columnVectors[n] = toType(t, values, empty2None=True)
                missingQgsFields.append(qgsField)

            #add missing fields
            if len(missingQgsFields) > 0:
                SLIB.addMissingFields(missingQgsFields)


            #create a feature for each row
            yValueType = None
            for i in range(nProfiles):
                p = SpectralProfile(fields=SLIB.fields())
                if addGeometry:
                    g = QgsGeometry.fromWkt(columnVectors['WKT'][i])
                    p.setGeometry(g)

                if addYValues:
                    y = [columnVectors[n][i] for n in bandValueColumnNames]
                    if yValueType is None and len(y) > 0:
                        yValueType = findTypeFromString(y[0])

                    y = toType(yValueType, y, True)
                    p.setValues(y=y, x=x, xUnit=xUnit)

                #add other attributes
                for n in [n for n in p.fieldNames() if n in list(columnVectors.keys())]:

                    p.setAttribute(n, columnVectors[n][i])

                SLIB.addFeature(p)


        SLIB.commitChanges()
        return SLIB


    @staticmethod
    def asString(speclib, dialect=pycsv.excel_tab, skipValues=False, skipGeometry=False):

        assert isinstance(speclib, SpectralLibrary)

        attributeNames = [n for n in speclib.fieldNames()]

        stream = io.StringIO()
        for i, item in enumerate(speclib.groupBySpectralProperties().items()):

            xvalues, xunit, yunit = item[0]
            profiles = item[1]
            assert isinstance(profiles, list)
            attributeNames = attributeNames[:]

            valueNames = []
            for b, xvalue in enumerate(xvalues):

                name = 'b{}'.format(b+1)

                suffix = ''
                if xunit is not None:
                    suffix+=str(xvalue)
                    suffix += xunit
                elif xvalue != b:
                    suffix += str(xvalue)

                if len(suffix)>0:
                    name += '_'+suffix
                valueNames.append(name)

            fieldnames = []
            if not skipGeometry:
                fieldnames += ['WKT']
            fieldnames += attributeNames
            if not skipGeometry:
                fieldnames += valueNames

            W = pycsv.DictWriter(stream, fieldnames=fieldnames, dialect=dialect)


            W.writeheader()

            for p in profiles:
                assert isinstance(p, SpectralProfile)
                D = dict()

                if not skipGeometry:
                    D['WKT'] = p.geometry().asWkt()

                for n in attributeNames:
                    D[n] = value2str(p.attribute(n))

                if not skipValues:
                    for i, yValue in enumerate(p.yValues()):
                        D[valueNames[i]] = yValue

                W.writerow(D)
            W.writerow({}) #append empty row


        return stream.getvalue()



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
        if name.startswith(HIDDEN_ATTRIBUTE_PREFIX):
            return str(pickle.loads(value))
        else:

            v = str(value)
            for c in self.mCharactersToReplace:
                v = v.replace(c, self.mReplacement)
            return v

    def fieldDefinition(self, field):
        return field

