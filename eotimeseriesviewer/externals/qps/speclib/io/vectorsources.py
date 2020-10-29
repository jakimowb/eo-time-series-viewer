# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/vectorsources.py

    Input/Output of spectral library data from vector + raster sources
    ---------------------
    Beginning            : 2019-11-27
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

import json
import os
import pathlib
import re
import sys
import typing

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *

from qgis.core import QgsField, QgsVectorLayer, QgsVectorFileWriter, QgsProviderRegistry, \
    QgsProject, QgsProviderMetadata, QgsFileUtils

from ..core import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, \
    decodeProfileValueDict, encodeProfileValueDict, \
    SerializationMode, \
    FIELD_VALUES, FIELD_NAME, ProgressHandler


class VectorSourceFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):

    def __init__(self, speclib: SpectralLibrary, destinationFormat: str):
        super().__init__()

        self.mSpeclib: SpectralLibrary = speclib
        self.mDstFormat = destinationFormat

        self.mBLOB2TXT = []
        for i, name in enumerate(speclib.fields().names()):
            f: QgsField = speclib.fields().at(i)

            if f.type() == QVariant.ByteArray:
                if destinationFormat in ['ESRI Shapefile', 'CSV', 'KML', 'GeoJSONSeq', 'GeoJSON']:
                    self.mBLOB2TXT.extend([i, name])
                else:
                    s = ""

    def clone(self):
        return VectorSourceFieldValueConverter(self.mSpeclib, self.mDstFormat)

    def convert(self, fieldIndex: int, value: any):
        if fieldIndex in self.mBLOB2TXT:
            dataDict = decodeProfileValueDict(value)
            dataJSON = json.dumps(dataDict)
            return dataJSON
        return value

    def fieldDefinition(self, field: QgsField) -> QgsField:
        if field.name() in self.mBLOB2TXT:
            return QgsField(field.name(), QVariant.String, 'varchar', comment=field.comment())
        return field


class VectorSourceSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for Vector File Formats.
    """

    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        path = str(path)
        try:
            options = QgsVectorLayer.LayerOptions(loadDefaultStyle=False)
            lyr = QgsVectorLayer(path, options=options)
            assert isinstance(lyr, QgsVectorLayer)
            assert lyr.isValid()

            fieldNames = lyr.fields().names()
            for fn in [FIELD_NAME, FIELD_VALUES]:
                assert fn in fieldNames

            typeName = lyr.fields().at(lyr.fields().lookupField(FIELD_NAME)).typeName()
            assert re.search('(string|varchar|char|json)', typeName, re.I)

            return True
        except:
            return False
        return False

    @classmethod
    def readFrom(cls, path,
                 progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None,
                 addAttributes: bool = True) -> SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param progressDialog:
        :type progressDialog:
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """
        path = str(path)
        options = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        lyr = QgsVectorLayer(path, options=options)
        assert isinstance(lyr, QgsVectorLayer)

        speclib = SpectralLibrary()
        assert isinstance(speclib, SpectralLibrary)
        speclib.setName(lyr.name())

        assert speclib.startEditing()
        if addAttributes:
            speclib.addMissingFields(lyr.fields())
            assert speclib.commitChanges()
            assert speclib.startEditing()

        profiles = []

        TXT2BLOB = False
        for i, n in enumerate(lyr.fields().names()):
            f: QgsField = lyr.fields().at(i)
            if n == FIELD_VALUES:
                if f.type() == QVariant.String:
                    TXT2BLOB = True

        for feature in lyr.getFeatures():
            profile = SpectralProfile(fields=speclib.fields())
            for i, name in enumerate(speclib.fieldNames()):
                if TXT2BLOB and name == FIELD_VALUES:
                    jsonStr = feature.attribute(name)
                    d = json.loads(jsonStr)
                    blob = encodeProfileValueDict(d, mode=SerializationMode.PICKLE)
                    profile.setAttribute(name, blob)
                else:
                    profile.setAttribute(name, feature.attribute(name))

            profiles.append(profile)

        speclib.addProfiles(profiles, addMissingFields=False)

        assert speclib.commitChanges()

        # load style
        pathStyle = os.path.splitext(path)[0] + '.qml'
        if os.path.isfile(pathStyle):
            success, errorMsg = speclib.loadNamedStyle(pathStyle)
            if not success:
                print(errorMsg, file=sys.stderr)
        return speclib

    @classmethod
    def write(cls, speclib: SpectralLibrary,
              path: str,
              progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None,
              options: QgsVectorFileWriter.SaveVectorOptions = None,
              filterFormat: QgsVectorFileWriter.FilterFormatDetails = None):
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
        """
        assert isinstance(speclib, SpectralLibrary)
        path = pathlib.Path(path)
        basePath, ext = os.path.splitext(path)

        providerMETA = []
        for pk in QgsProviderRegistry.instance().providerList():
            md = QgsProviderRegistry.instance().providerMetadata(pk)
            filters = md.filters(QgsProviderMetadata.FilterType.FilterVector)
            if len(filters) > 0:
                providerMETA.append(md)

        assert ext[1:] in QgsVectorFileWriter.supportedFormatExtensions(), f'Unknown vector file extension: {ext}'

        if filterFormat is None:
            FILTER_AND_FORMAT = QgsVectorFileWriter.supportedFiltersAndFormats(QgsVectorFileWriter.SortRecommended)
            for f in FILTER_AND_FORMAT:
                if ext in f.filterString:
                    filterFormat = f
                    break

        if not isinstance(options, QgsVectorFileWriter.SaveVectorOptions):
            # driverName = OGR_EXTENSION2DRIVER.get(ext, 'GPKG')
            options = QgsVectorFileWriter.SaveVectorOptions()
            # options.fileEncoding = 'utf-8'
            options.driverName = filterFormat.driverName
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
            # driver specific options

        if options.fieldValueConverter is None:
            converter = VectorSourceFieldValueConverter(speclib, filterFormat.driverName)
            options.fieldValueConverter = converter

        if options.layerName in [None, '']:
            options.layerName = speclib.name()
        transform_context = QgsProject.instance().transformContext()
        errCode, errMsg = QgsVectorFileWriter.writeAsVectorFormatV2(
            speclib,
            path.as_posix(),
            transform_context,
            options)

        if len(errMsg) > 0:
            raise Exception(errMsg)

        if not path.is_file() and filterFormat.driverName.startswith('GeoJSON'):
            path = path.parent / f'{path.name}.json'

        pathStyle = os.path.splitext(path)[0] + '.qml'
        msg, success = speclib.saveNamedStyle(pathStyle)
        print(msg)

        pathMD = os.path.splitext(path)[0] + '.qmd'
        msg, success = speclib.saveNamedMetadata(pathMD)
        print(msg)
        return [path]

    @classmethod
    def supportedFileExtensions(cls) -> typing.Dict[str, str]:

        filters = {'.gpkg': 'Geopackage',
                   '.shp': 'ESRI Shapefile',
                   '.kml': 'Keyhole Markup Language',
                   '.csv': 'Character Separated Value'
                   }

        return filters

    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='Vector File',
                                                       filter='All type (*.*)',
                                                       directory=QgsFileUtils.stringToSafeFilename(speclib.name())
                                                       )
            if os.path.isfile(path) and VectorSourceSpectralLibraryIO.canRead(path):
                sl = VectorSourceSpectralLibraryIO.readFrom(path)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add Spectral Library profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('Vector Layer')
        m.setToolTip(
            'Adds profiles from another vector source\'s "{}" and "{}" attributes.'.format(FIELD_VALUES, FIELD_NAME))
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))

    @classmethod
    def addExportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:
        """
        def write_new(speclib: SpectralLibrary):
            # this is not available in Python. Why?
            from qgis.gui import QgsVectorLayerSaveAsDialog
            options = QgsVectorLayerSaveAsDialog.Symbology | \
                      QgsVectorLayerSaveAsDialog.DestinationCrs | \
                      QgsVectorLayerSaveAsDialog.Symbology.Fields | \
                      QgsVectorLayerSaveAsDialog.SelectedOnly | \
                      QgsVectorLayerSaveAsDialog.GeometryType | \
                      QgsVectorLayerSaveAsDialog.Extent

            d = QgsVectorLayerSaveAsDialog(speclib, options=options)
            d.show()
        """

        def write(speclib: SpectralLibrary):
            # https://gdal.org/drivers/vector/index.html
            LUT_Files = {'Geopackage (*.gpkg)': 'GPKG',
                         'ESRI Shapefile (*.shp)': 'ESRI Shapefile',
                         'Keyhole Markup Language (*.kml)': 'KML',
                         'Comma Separated Value (*.csv)': 'CSV'}

            path, filter = QFileDialog.getSaveFileName(caption='Write to Vector Layer',
                                                       filter=';;'.join(LUT_Files.keys()))
            if isinstance(path, str) and len(path) > 0:
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.fileEncoding = 'UTF-8'

                ogrType = LUT_Files.get(filter)
                if isinstance(ogrType, str):
                    options.driverName = ogrType
                    if ogrType == 'GPKG':
                        pass
                    elif ogrType == 'ESRI Shapefile':
                        pass
                    elif ogrType == 'KML':
                        pass
                    elif ogrType == 'CSV':
                        pass
                sl = VectorSourceSpectralLibraryIO.write(spectralLibrary, path, options=options)

        m = menu.addAction('Vector Source')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))
