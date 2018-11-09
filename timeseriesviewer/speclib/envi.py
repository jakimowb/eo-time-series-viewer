# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    envi.py
    Reading and writing spectral profiles to ENVI Spectral Libraries
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
import os, csv
from .spectrallibraries import *


CSV_PROFILE_NAME_COLUMN_NAMES = ['spectra names', 'name']
CSV_GEOMETRY_COLUMN = 'wkt'

def findENVIHeader(pathESL:str)->str:
    """
    Get a path and returns the ENVI header (*.hdr) for
    :param pathESL: str
    :return: str pathESL.hdr
    """
    paths = [os.path.splitext(pathESL)[0] + '.hdr', pathESL + '.hdr']
    pathHdr = None
    for p in paths:
        if os.path.exists(p):
            pathHdr = p
    return pathHdr


def value2hdrString(values):
    """
    Converts single values or a list of values into an ENVI header string
    :param values: valure or list-of-values, e.g. int(23) or [23,42]
    :return: str, e.g. 23 to "23" (single value), [23,24,25] to "{23,42}" (lists)
    """
    s = None
    maxwidth = 75

    if isinstance(values, (tuple, list)):
        lines = ['{']
        values = ['{}'.format(v).replace(',', '-') for v in values]
        line = ' '
        l = len(values)
        for i, v in enumerate(values):
            line += v
            if i < l - 1: line += ', '
            if len(line) > maxwidth:
                lines.append(line)
                line = ' '
        line += '}'
        lines.append(line)
        s = '\n'.join(lines)

    else:
        s = '{}'.format(values)

    return s



def readCSVMetadata(pathESL):
    """
    Returns ESL metadata stored in a extra CSV file
    :param pathESL: str, path of ENVI spectral library
    :return: ([list-of-tuples], QgsFields) or None
    """

    pathCSV = os.path.splitext(pathESL)[0] + '.csv'
    if not os.path.isfile(pathCSV):
        return None


    lines = None
    with open(pathCSV) as f:
        lines = f.readlines()
    if not isinstance(lines, list):
        print('Unable to read {}'.format(pathCSV))
        return None

    lines = [l.strip() for l in lines]
    lines = [l for l in lines if len(l) > 0]
    if len(lines) <= 1:
        print('CSV does not contain enough values')
        return None

    hasSpectrumNames = False
    match = re.search('spectra names[ ]*([;\t,])', lines[0])
    if match:
        sep = match.group(1)
    else:
        print('Unable to find column name "spectra names" in {}.'.format(pathCSV), file=sys.stderr)
        match = re.search('name[ ]*([;\t,])', lines[0], re.I)
        if match:
            sep = match.group(1)
        else:
            print('Unable to find column name like "*name*" in {}. Use "," as delimiter'.format(pathCSV), file=sys.stderr)
            sep = ','

    METADATA_LINES = []
    fieldNames = lines[0].split(sep)

    #read CSV data
    reader = csv.DictReader(lines[1:], fieldnames=fieldNames, delimiter=sep)
    for i, row in enumerate(reader):
        METADATA_LINES.append(tuple(row.values()))

    #set emtpy value to None
    def stripped(value:str):
        if value is None:
            return None
        value = value.strip()
        return None if len(value) == 0 else value
    METADATA_LINES = [tuple([stripped(v) for v in row]) for row in METADATA_LINES]


    # find type for undefined metadata names
    QGSFIELD_PYTHON_TYPES = []
    QGSFIELDS = QgsFields()
    for i, fieldName in enumerate(fieldNames):
        fieldValues = [row[i] for row in METADATA_LINES if row[i] is not None]
        fieldTypes = [findTypeFromString(v) for v in fieldValues]
        if len(fieldTypes) == 0:
            fieldTypes = [str]

        if str in fieldTypes:
            t = str
            a, b = QVariant.String, 'varchar'
        elif float in fieldTypes:
            t = float
            a, b = QVariant.Double, 'double'
        elif int in fieldTypes:
            t = int
            a, b = QVariant.Int, 'int'
        else:
            raise NotImplementedError()
        QGSFIELD_PYTHON_TYPES.append(t)
        QGSFIELDS.append(QgsField(fieldName, a, b))

    # convert metadata string values to basic python type
    def typeOrNone(value:str, t:type):
        return value if value is None else t(value)

    METADATA_LINES = [tuple(typeOrNone(v, QGSFIELD_PYTHON_TYPES[i]) for i, v in enumerate(line)) for line in METADATA_LINES]

    return (METADATA_LINES, QGSFIELDS)


def writeCSVMetadata(pathCSV:str, profiles:list):
    """
    Write profile Metadata as CSV file
    :param pathCSV: str, path of CSV file
    :param profiles: [list-of-SpectralProfiles]
    """
    assert isinstance(profiles, list)
    if len(profiles) == 0:
        return

    excludedNames = CSV_PROFILE_NAME_COLUMN_NAMES + [CSV_GEOMETRY_COLUMN, FIELD_FID, FIELD_VALUES, FIELD_STYLE]
    fieldNames = [n for n in profiles[0].fields().names() if n not in excludedNames]
    allFieldNames = ['spectra names'] + fieldNames + [CSV_GEOMETRY_COLUMN]


    with open(pathCSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=allFieldNames)
        writer.writeheader()
        for p in profiles:
            assert isinstance(p, SpectralProfile)
            d = {}
            d['spectra names'] = p.name()
            d[CSV_GEOMETRY_COLUMN] = p.geometry().asWkt()
            for name in fieldNames:
                v = p.attribute(name)
                if v not in EMPTY_VALUES:
                    d[name] = v
            writer.writerow(d)



class EnviSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    IO of ENVI Spectral Libraries
    see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for format description
    Additional profile metadata is written to/read from a *.csv of same base name as the ESL
    """

    REQUIRED_TAGS = ['byte order', 'data type', 'header offset', 'lines', 'samples', 'bands']
    SINGLE_VALUE_TAGS = REQUIRED_TAGS + ['description', 'wavelength', 'wavelength units']

    @staticmethod
    def canRead(pathESL):
        """
        Checks if a file can be read as SpectraLibrary
        :param pathESL: path to ENVI Spectral Library (ESL)
        :return: True, if pathESL can be read as Spectral Library.
        """
        assert isinstance(pathESL, str)
        if not os.path.isfile(pathESL):
            return False
        hdr = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=False)
        if hdr is None or hdr['file type'] != 'ENVI Spectral Library':
            return False
        return True

    @staticmethod
    def score(uri:str):
        if not isinstance(uri, str):
            return 0
        if re.search(r'\.(esl|sli)$', uri, ):
            return 20
        return 0

    @staticmethod
    def readFrom(pathESL):
        """
        Reads an ENVI Spectral Library (ESL).
        :param pathESL: path ENVI Spectral Library
        :return: SpectralLibrary
        """
        assert isinstance(pathESL, str)
        md = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=True)

        data = None

        tmpVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt', dir=os.path.join(VSI_DIR, 'ENVIIO'))
        ds = EnviSpectralLibraryIO.esl2vrt(pathESL, tmpVrt)
        data = ds.ReadAsArray()

        #remove the temporary VRT, as it was created internally only
        ds.GetDriver().Delete(ds.GetFileList()[0])
        #gdal.Unlink(ds)


        nSpectra, nbands = data.shape
        yUnit = None
        xUnit = md.get('wavelength units')
        xValues = md.get('wavelength')
        zPlotTitles = md.get('z plot titles')
        if isinstance(zPlotTitles, str) and len(zPlotTitles.split(','))>=2:
            xUnit, yUnit = zPlotTitles.split(',')[0:2]

        #get official ENVI Spectral Library standard values
        spectraNames = md.get('spectra names', ['Spectrum {}'.format(i+1) for i in range(nSpectra)])

        speclibFields = createStandardFields()

        # check for additional CSV metadata to enhance profile descriptions
        CSV_METADATA = None
        try:
            CSV_METADATA = readCSVMetadata(pathESL)
        except Exception as ex:
            print(str(ex), file=sys.stderr)

        if CSV_METADATA is not None:
            CSV_DATA, CSV_FIELDS = CSV_METADATA

            for csvField in CSV_FIELDS:
                assert isinstance(csvField, QgsField)
                if csvField.name() not in speclibFields.names() and \
                   csvField.name() not in CSV_PROFILE_NAME_COLUMN_NAMES:
                    speclibFields.append(csvField)

            CSVLine2ESLProfile = {}
            #look if we can match a CSV column with names to profile names
            for profileNameColumnName in CSV_PROFILE_NAME_COLUMN_NAMES:
                if profileNameColumnName in CSV_FIELDS.names():
                    c = CSV_FIELDS.lookupField(profileNameColumnName)
                    for r, row in enumerate(CSV_DATA):
                        nameCSV = row[c]
                        if nameCSV in spectraNames:
                            CSVLine2ESLProfile[r] = spectraNames.index(nameCSV)
                    break
            #backup: match csv line with profile index
            if len(CSVLine2ESLProfile) == 0:
                indices = range(min(nSpectra, len(CSV_DATA)))
                CSVLine2ESLProfile = dict(zip(indices, indices))

        profiles = []
        for i in range(nSpectra):
            p = SpectralProfile(fields=speclibFields)
            p.setValues(x=xValues, y=data[i,:].tolist(), xUnit=xUnit, yUnit=yUnit)
            name = spectraNames[i]
            p.setName(name)
            profiles.append(p)



        if CSV_METADATA is not None:
            #find which column index from CSV table matches which QgsFeature attribute index
            for csvField in CSV_FIELDS:
                assert isinstance(csvField, QgsField)
                fieldName = csvField.name()
                #is this a geometry field?
                if fieldName == CSV_GEOMETRY_COLUMN:
                    # copy CSV values to profile geometry attribute
                    for iCSV, iProfile in CSVLine2ESLProfile.items():
                        value = CSV_DATA[iCSV][aCSV]
                        if isinstance(value, str):
                            g = QgsGeometry.fromWkt(value)
                            if g.wkbType() == QgsWkbTypes.Point:
                                profile = profiles[iProfile]
                                assert isinstance(profile, SpectralProfile)
                                profile.setGeometry(g)
                else:
                    #set normal value fields
                    if fieldName in CSV_PROFILE_NAME_COLUMN_NAMES:
                        #map CSV field "spectrum names" or "name" to speclib "name" columns
                        aSpeclib = speclibFields.lookupField(FIELD_NAME)
                    else:
                        aSpeclib = speclibFields.lookupField(fieldName)

                    if aSpeclib < 0:
                        s = ""
                    aCSV = CSV_FIELDS.lookupField(fieldName)

                    #copy CSV values to profile attribute
                    for iCSV, iProfile in CSVLine2ESLProfile.items():
                        profile = profiles[iProfile]
                        assert isinstance(profile, SpectralProfile)
                        value = CSV_DATA[iCSV][aCSV]
                        if value not in EMPTY_VALUES:
                            assert profile.setAttribute(aSpeclib, value)
                            s = ""


        SLIB = SpectralLibrary()
        SLIB.startEditing()
        SLIB.addMissingFields(speclibFields)
        #SLIB.commitChanges()
        #SLIB.startEditing()
        SLIB.addProfiles(profiles)
        assert SLIB.commitChanges()
        assert SLIB.featureCount() == nSpectra
        return SLIB

    @staticmethod
    def write(speclib:SpectralLibrary, path:str):
        """
        Writes a SpectralLibrary as ENVI Spectral Library (ESL).
        See http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for ESL definition

        Additional attributes (coordinate, user-defined attributes) will be written into a CSV text file with same basename

        For example path 'myspeclib.sli' leads to:

            myspeclib.sli <- ESL binary file
            myspeclib.hdr <- ESL header file
            myspeclib.csv <- CSV text file, tabulator separated columns (for being used in Excel)

        :param speclib: SpectralLibrary
        :param path: str
        """
        assert isinstance(path, str)

        dn = os.path.dirname(path)
        bn, ext = os.path.splitext(os.path.basename(path))
        assert ext in ['.sli', '.esl'], "Path needs extension .sli or .esl: {}".format(path)

        writtenFiles = []

        if not os.path.isdir(dn):
            os.makedirs(dn)

        iGrp = -1
        for key, profiles in speclib.groupBySpectralProperties().items():
            iGrp += 1
            if len(profiles) == 0:
                continue
            xValues, wlu, yUnit = key

            # stack profiles
            pData = [np.asarray(p.yValues()) for p in profiles]
            pData = np.vstack(pData)

            #convert array to data type GDAL is able to write
            if pData.dtype == np.int64:
                pData = pData.astype(np.int32)

            #todo: other cases?

            pNames = [p.name() for p in profiles]

            if iGrp == 0:
                pathDst = os.path.join(dn, '{}{}'.format(bn, ext))
            else:
                pathDst = os.path.join(dn, '{}.{}{}'.format(bn, iGrp, ext))

            drv = gdal.GetDriverByName('ENVI')
            assert isinstance(drv, gdal.Driver)

            eType = gdal_array.NumericTypeCodeToGDALTypeCode(pData.dtype)
            """Create(utf8_path, int xsize, int ysize, int bands=1, GDALDataType eType, char ** options=None) -> Dataset"""
            ds = drv.Create(pathDst, pData.shape[1], pData.shape[0], 1, eType)
            band = ds.GetRasterBand(1)
            assert isinstance(band, gdal.Band)
            band.WriteArray(pData)

            assert isinstance(ds, gdal.Dataset)

            #write ENVI header metadata
            ds.SetDescription(speclib.name())
            ds.SetMetadataItem('band names', 'Spectral Library', 'ENVI')
            ds.SetMetadataItem('spectra names',value2hdrString(pNames), 'ENVI')
            ds.SetMetadataItem('wavelength', value2hdrString(xValues), 'ENVI')
            ds.SetMetadataItem('wavelength units', wlu, 'ENVI')
            ds.FlushCache()

            pathHDR = ds.GetFileList()[1]
            ds = None

            # re-write ENVI Hdr with file type = ENVI Spectral Library
            file = open(pathHDR)
            hdr = file.readlines()
            file.close()
            for iLine in range(len(hdr)):
                if re.search('file type =', hdr[iLine]):
                    hdr[iLine] = 'file type = ENVI Spectral Library\n'
                    break

            file = open(pathHDR, 'w', encoding='utf-8')
            file.writelines(hdr)
            file.flush()
            file.close()

            # write other metadata to CSV
            pathCSV = os.path.splitext(pathHDR)[0] + '.csv'

            writeCSVMetadata(pathCSV, profiles)

            writtenFiles.append(pathDst)

        return writtenFiles


    @staticmethod
    def esl2vrt(pathESL, pathVrt=None):
        """
        Creates a GDAL Virtual Raster (VRT) that allows to read an ENVI Spectral Library file
        :param pathESL: path ENVI Spectral Library file (binary part)
        :param pathVrt: (optional) path of created GDAL VRT.
        :return: GDAL VRT
        """

        hdr = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=False)
        assert hdr is not None and hdr['file type'] == 'ENVI Spectral Library'

        if hdr.get('file compression') == '1':
            raise Exception('Can not read compressed spectral libraries')

        eType = LUT_IDL2GDAL[int(hdr['data type'])]
        xSize = int(hdr['samples'])
        ySize = int(hdr['lines'])
        bands = int(hdr['bands'])
        byteOrder = 'LSB' if int(hdr['byte order']) == 0 else 'MSB'

        if pathVrt is None:
            id = uuid.UUID()
            pathVrt = '/vsimem/{}.esl.vrt'.format(id)
            #pathVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt')


        ds = describeRawFile(pathESL, pathVrt, xSize, ySize, bands=bands, eType=eType, byteOrder=byteOrder)
        for key, value in hdr.items():
            if isinstance(value, list):
                value = u','.join(v for v in value)
            ds.SetMetadataItem(key, value, 'ENVI')
        ds.FlushCache()
        return ds


    @staticmethod
    def readENVIHeader(pathESL, typeConversion=False):
        """
        Reads an ENVI Header File (*.hdr) and returns its values in a dictionary
        :param pathESL: path to ENVI Header
        :param typeConversion: Set on True to convert values related to header keys with numeric
        values into numeric data types (int / float)
        :return: dict
        """
        assert isinstance(pathESL, str)
        if not os.path.isfile(pathESL):
            return None

        pathHdr = findENVIHeader(pathESL)
        if pathHdr is None:
            return None


        #hdr = open(pathHdr).readlines()
        file = open(pathHdr, encoding='utf-8')
        hdr = file.readlines()
        file.close()

        i = 0
        while i < len(hdr):
            if '{' in hdr[i]:
                while not '}' in hdr[i]:
                    hdr[i] = hdr[i] + hdr.pop(i + 1)
            i += 1

        hdr = [''.join(re.split('\n[ ]*', line)).strip() for line in hdr]
        # keep lines with <tag>=<value> structure only
        hdr = [line for line in hdr if re.search('^[^=]+=', line)]

        # restructure into dictionary of type
        # md[key] = single value or
        # md[key] = [list-of-values]
        md = dict()
        for line in hdr:
            tmp = line.split('=')
            key, value = tmp[0].strip(), '='.join(tmp[1:]).strip()
            if value.startswith('{') and value.endswith('}'):
                value = [v.strip() for v in value.strip('{}').split(',')]
            md[key] = value

        # check required metadata tegs
        for k in EnviSpectralLibraryIO.REQUIRED_TAGS:
            if not k in md.keys():
                return None

        if typeConversion:
            to_int = ['bands','lines','samples','data type','header offset','byte order']
            to_float = ['fwhm','wavelength', 'reflectance scale factor']
            for k in to_int:
                if k in md.keys():
                    md[k] = toType(int, md[k])
            for k in to_float:
                if k in md.keys():
                    md[k] = toType(float, md[k])


        return md

