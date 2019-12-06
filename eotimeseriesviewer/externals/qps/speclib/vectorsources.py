
import os, sys, re, pathlib, json, io, re, linecache
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *


from .spectrallibraries import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, FIELD_FID, FIELD_VALUES, FIELD_NAME, findTypeFromString, createQgsField, OGR_EXTENSION2DRIVER

class VectorSourceSpectralLibraryIO(AbstractSpectralLibraryIO):
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
        try:

            lyr = QgsVectorLayer(path)
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


    @staticmethod
    def readFrom(path, progressDialog:QProgressDialog=None, addAttributes:bool = True)->SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """

        lyr = QgsVectorLayer(path)
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
        for feature in lyr.getFeatures():
            profile = SpectralProfile(fields=speclib.fields())
            for name in speclib.fieldNames():
                profile.setAttribute(name, feature.attribute(name))
            profiles.append(profile)

        speclib.addProfiles(profiles, addMissingFields=False)

        assert speclib.commitChanges()
        return speclib

    @staticmethod
    def write(speclib:SpectralLibrary, path:str, progressDialog:QProgressDialog=None, options:QgsVectorFileWriter.SaveVectorOptions=None):
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
        """
        assert isinstance(speclib, SpectralLibrary)
        basePath, ext = os.path.splitext(path)



        if not isinstance(options, QgsVectorFileWriter.SaveVectorOptions):
            driverName = OGR_EXTENSION2DRIVER.get(ext, 'GPKG')
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.fileEncoding = 'utf-8'
            options.driverName = driverName

            if driverName == 'GPKG' and not ext == '.gpkg':
                path += '.gpkg'

        if options.layerName in [None, '']:
            options.layerName = speclib.name()

        errors = QgsVectorFileWriter.writeAsVectorFormat(layer=speclib,
                                                         fileName=path,
                                                         options=options)
        writtenFiles = []
        if os.path.exists(path):
            writtenFiles.append(path)
        return writtenFiles

    @staticmethod
    def score(uri:str)->int:
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probably thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        return 0

    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='Vector File',
                                               filter='All type (*.*)')
            if os.path.isfile(path) and VectorSourceSpectralLibraryIO.canRead(path):
                sl = VectorSourceSpectralLibraryIO.readFrom(path)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add Spectral Library profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('Vector Layer')
        m.setToolTip('Adds profiles from another vector source\'s "{}" and "{}" attributes.'.format(FIELD_VALUES, FIELD_NAME))
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))


    @staticmethod
    def addExportActions(spectralLibrary:SpectralLibrary, menu:QMenu) -> list:

        def write(speclib: SpectralLibrary):
            # https://gdal.org/drivers/vector/index.html
            LUT_Files = {'Geopackage (*.gpkg)': 'GPKG',
                         'ESRI Shapefile (*.shp)' : 'ESRI Shapefile',
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