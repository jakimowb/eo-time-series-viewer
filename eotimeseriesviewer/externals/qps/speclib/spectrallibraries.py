
# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    spectrallibraries.py

    Spectral Profiles and Libraries for a GUI context.
    ---------------------
    Date                 : Juli 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
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

#see http://python-future.org/str_literals.html for str issue discussion
import json, enum, tempfile, pickle, collections, typing, inspect
from osgeo import ogr, osr
from qgis.utils import iface
from qgis.gui import Targets, QgsMapLayerAction
from qgis.core import QgsField, QgsVectorLayer, QgsRasterLayer, QgsVectorFileWriter
from ..externals.pyqtgraph import PlotItem
from ..externals import pyqtgraph as pg
from ..models import Option, OptionListModel
from .. utils import *
from ..speclib import speclibSettings, SpectralLibrarySettingsKey
from ..plotstyling.plotstyling import PlotStyleWidget, PlotStyle

# get to now how we can import this module
MODULE_IMPORT_PATH = None
#'timeseriesviewer.plotstyling'
for name, module in sys.modules.items():
    if hasattr(module, '__file__') and module.__file__ == __file__:
        MODULE_IMPORT_PATH = name
        break


MIMEDATA_SPECLIB = 'application/hub-spectrallibrary'
MIMEDATA_SPECLIB_LINK = 'application/hub-spectrallibrary-link'
MIMEDATA_XQT_WINDOWS_CSV = 'application/x-qt-windows-mime;value="Csv"'
MIMEDATA_TEXT = 'text/plain'
MIMEDATA_URL = 'text/url'

SPECLIB_EPSG_CODE = 4326
SPECLIB_CRS = QgsCoordinateReferenceSystem('EPSG:{}'.format(SPECLIB_EPSG_CODE))

SPECLIB_CLIPBOARD = weakref.WeakValueDictionary()


OGR_EXTENSION2DRIVER = dict()
OGR_EXTENSION2DRIVER[''] = [] #list all drivers without specific extension

for i in range(ogr.GetDriverCount()):
    drv = ogr.GetDriver(i)
    extensions = drv.GetMetadataItem(gdal.DMD_EXTENSIONS)
    if isinstance(extensions, str):
        extensions = extensions.split(',')
        for ext in extensions:
            if ext not in OGR_EXTENSION2DRIVER.keys():
                OGR_EXTENSION2DRIVER[ext] = []
            OGR_EXTENSION2DRIVER[ext].append(drv.GetName())
    else:
        OGR_EXTENSION2DRIVER[''].append(drv.GetName())
OGR_EXTENSION2DRIVER[None] = OGR_EXTENSION2DRIVER['']

DEBUG = False

class SerializationMode(enum.Enum):

    JSON = 1
    PICKLE = 2

SERIALIZATION = SerializationMode.PICKLE

def log(msg:str):
    if DEBUG:
        QgsMessageLog.logMessage(msg, 'spectrallibraries.py')

def containsSpeclib(mimeData:QMimeData)->bool:
    for f in [MIMEDATA_SPECLIB, MIMEDATA_SPECLIB_LINK]:
        if f in mimeData.formats():
            return True

    return False

FILTERS = 'ENVI Spectral Library (*.sli *.esl);;CSV Table (*.csv);;Geopackage (*.gpkg)'

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
#CURRENT_SPECTRUM_STYLE = PlotStyle()
#CURRENT_SPECTRUM_STYLE.markerSymbol = None
#CURRENT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
#CURRENT_SPECTRUM_STYLE.linePen.setColor(Qt.green)



# DEFAULT_SPECTRUM_STYLE = PlotStyle()
# DEFAULT_SPECTRUM_STYLE.markerSymbol = None
# DEFAULT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
# DEFAULT_SPECTRUM_STYLE.linePen.setColor(Qt.white)

EMPTY_VALUES = [None, NULL, QVariant(), '', 'None']
EMPTY_PROFILE_VALUES = {'x': None, 'y': None, 'xUnit': None, 'yUnit': None, 'bbl': None}

FIELD_VALUES = 'values'
FIELD_NAME = 'name'
FIELD_FID = 'fid'

VSI_DIR = r'/vsimem/speclibs/'
VSIMEM_AVAILABLE = True
if not check_vsimem():
    VSI_DIR = tempfile.gettempdir()
    VSIMEM_AVAILABLE = False
try:
    gdal.Mkdir(VSI_DIR, 0)
except:
    pass


X_UNITS = ['Index', 'Micrometers', 'Nanometers', 'Millimeters', 'Centimeters', 'Meters', 'Wavenumber', 'Angstroms', 'GHz', 'MHz', '']
Y_UNITS = ['DN', 'Reflectance', 'Radiance', '']

loadSpeclibUI = lambda name: loadUIFormClass(os.path.join(os.path.dirname(__file__), name))

def vsiSpeclibs()->list:
    """
    Returns the URIs pointing on VSIMEM in memory speclibs
    :return: [list-of-str]
    """
    visSpeclibs = []
    if VSIMEM_AVAILABLE:
        for bn in gdal.ReadDir(VSI_DIR):
            if bn == '':
                continue
            p = pathlib.PurePosixPath(VSI_DIR) / bn
            p = p.as_posix()
            stats = gdal.VSIStatL(p)
            if isinstance(stats, gdal.StatBuf) and not stats.IsDirectory():
                visSpeclibs.append(p)
    else:
        visSpeclibs.extend(list(file_search(VSI_DIR, '*.gpkg')))
    return visSpeclibs

# CURRENT_SPECTRUM_STYLE.linePenplo
# pdi.setPen(fn.mkPen(QColor('green'), width=3))

def runRemoveFeatureActionRoutine(layerID, id:int):
    """
    Is applied to a set of layer features to change the plotStyle JSON string stored in styleField
    :param layerID: QgsVectorLayer or vector id str
    :param styleField: str, name of string field in layer.fields() to store the PlotStyle
    :param id: feature id of feature for which the QgsAction was called
    """

    layer = findMapLayer(layerID)

    if isinstance(layer, QgsVectorLayer):
        selectedIDs = layer.selectedFeatureIds()
        if id in selectedIDs:
            ids = selectedIDs
        else:
            ids = [id]
        if len(ids) == 0:
            return

        wasEditable = layer.isEditable()
        if not wasEditable:
            if not layer.startEditing():
                raise Exception('Layer "{}" can not be edited'.format(layer.name()))
        layer.beginEditCommand('Remove {} features'.format(len(ids)))
        layer.deleteFeatures(ids)
        layer.endEditCommand()
        if not layer.commitChanges():
            errors = layer.commitErrors()
            raise Exception('Unable to save {} to layer {}'.format('\n'.join(errors), layer.name()))

        if wasEditable:
            layer.startEditing()

    else:
        raise Exception('unable to find layer "{}"'.format(layerID))


def createRemoveFeatureAction():
    """
    Creates a QgsAction to remove selected QgsFeatures from a QgsVectorLayer
    :return: QgsAction
    """

    iconPath = ':/images/themes/default/mActionDeleteSelected.svg'
    pythonCode = """
from {modulePath} import runRemoveFeatureActionRoutine
layerId = '[% @layer_id %]'
#layerId = [% "layer" %]
runRemoveFeatureActionRoutine(layerId, [% $id %])
""".format(modulePath=MODULE_IMPORT_PATH)

    return QgsAction(QgsAction.GenericPython, 'Remove Spectrum', pythonCode, iconPath, True,
                       notificationMessage='msgRemoveSpectra',
                       actionScopes={'Feature'})

def findTypeFromString(value:str):
    """
    Returns a fitting basic python data type of a string value, i.e.
    :param value: string
    :return: type out of [str, int or float]
    """
    for t in (int, float, str):
        try:
            _ = t(value)
        except ValueError:
            continue
        return t

    # every values can be converted into a string
    return str

def setComboboxValue(cb: QComboBox, text: str):
    """
    :param cb:
    :param text:
    :return:
    """
    assert isinstance(cb, QComboBox)
    currentIndex = cb.currentIndex()
    idx = -1
    if text is None:
        text = ''
    text = text.strip()
    for i in range(cb.count()):
        v = str(cb.itemText(i)).strip()
        if v == text:
            idx = i
            break
    if not idx >= 0:
        pass

    if idx >= 0:
        cb.setCurrentIndex(idx)
    else:
        log('ComboBox index not found for "{}"'.format(text))

def toType(t, arg, empty2None=True):
    """
    Converts lists or single values into type t.

    Examples:
        toType(int, '42') == 42,
        toType(float, ['23.42', '123.4']) == [23.42, 123.4]

    :param t: type
    :param arg: value to convert
    :param empty2None: returns None in case arg is an emptry value (None, '', NoneType, ...)
    :return: arg as type t (or None)
    """
    if isinstance(arg, list):
        return [toType(t, a) for a in arg]
    else:

        if empty2None and arg in EMPTY_VALUES:
            return None
        else:
            return t(arg)


def encodeProfileValueDict(d:dict)->str:
    """
    Converts a SpectralProfile value dictionary into a compact JSON string, which can be
    extracted with `decodeProfileValueDict`.
    :param d: dict
    :return: str
    """
    if not isinstance(d, dict):
        return None
    d2 = {}
    for k in EMPTY_PROFILE_VALUES.keys():
        v = d.get(k)
        # save keys with information only
        if v is not None:
            d2[k] = v
    if SERIALIZATION == SerializationMode.JSON:
        return json.dumps(d2, sort_keys=True, separators=(',', ':'))
    elif SERIALIZATION == SerializationMode.PICKLE:
        return QByteArray(pickle.dumps(d2))
    else:
        raise NotImplementedError()


def decodeProfileValueDict(dump):
    """
    Converts a json / pickle dump  into a SpectralProfile value dictionary
    :param dump: str
    :return: dict
    """
    d = EMPTY_PROFILE_VALUES.copy()

    if dump not in EMPTY_VALUES:
        d2 = None
        if SERIALIZATION == SerializationMode.JSON:
            d2 = json.loads(dump)
        elif SERIALIZATION == SerializationMode.PICKLE:
            d2 = pickle.loads(dump)
        else:
            raise NotImplementedError()
        d.update(d2)
    return d


def qgsFieldAttributes2List(attributes)->list:
    """Returns a list of attributes with None instead of NULL or QVariant.NULL"""
    r = QVariant(None)
    return [None if v == r else v for v in attributes]


def qgsFields2str(qgsFields:QgsFields)->str:
    """Converts the QgsFields definition into a pickalbe string"""
    infos = []
    for field in qgsFields:
        assert isinstance(field, QgsField)
        info = [field.name(), field.type(), field.typeName(), field.length(), field.precision(), field.comment(), field.subType()]
        infos.append(info)
    return json.dumps(infos)

def str2QgsFields(fieldString:str)->QgsFields:
    """Converts the string from qgsFields2str into a QgsFields collection"""
    fields = QgsFields()

    infos = json.loads(fieldString)
    assert isinstance(infos, list)
    for info in infos:
        field = QgsField(*info)
        fields.append(field)
    return fields




#Lookup table for ENVI IDL DataTypes to GDAL Data Types
LUT_IDL2GDAL = {1:gdal.GDT_Byte,
                12:gdal.GDT_UInt16,
                2:gdal.GDT_Int16,
                13:gdal.GDT_UInt32,
                3:gdal.GDT_Int32,
                4:gdal.GDT_Float32,
                5:gdal.GDT_Float64,
                #:gdal.GDT_CInt16,
                #8:gdal.GDT_CInt32,
                6:gdal.GDT_CFloat32,
                9:gdal.GDT_CFloat64}

def ogrStandardFields()->list:
    """Returns the minimum set of field a Spectral Library has to contain"""
    fields = [
        ogr.FieldDefn(FIELD_FID, ogr.OFTInteger),
        ogr.FieldDefn(FIELD_NAME, ogr.OFTString),
        ogr.FieldDefn('source', ogr.OFTString),
        ogr.FieldDefn(FIELD_VALUES, ogr.OFTString) \
            if SERIALIZATION == SerializationMode.JSON else \
                ogr.FieldDefn(FIELD_VALUES, ogr.OFTBinary),
        ]
    return fields

def createStandardFields():

    fields = QgsFields()
    for f in ogrStandardFields():
        assert isinstance(f, ogr.FieldDefn)
        name = f.GetName()
        ogrType = f.GetType()

        if ogrType == ogr.OFTString:
            a, b = QVariant.String, 'varchar'
        elif ogrType in [ogr.OFTInteger, ogr.OFTInteger64]:
            a, b = QVariant.Int, 'int'
        elif ogrType in [ogr.OFTReal]:
            a, b = QVariant.Double, 'double'
        elif ogrType in [ogr.OFTBinary]:
            a, b = QVariant.ByteArray, 'Binary'
        else:
            raise NotImplementedError()

        fields.append(QgsField(name, a, b))

    return fields


def value2str(value, sep:str=' ')->str:
    """
    Converst a value into a string
    :param value:
    :param sep: str separator for listed values
    :return:
    """
    if isinstance(value, list):
        value = sep.join([value2str(v, delimiter=sep) for v in value])
    elif isinstance(value, np.ndarray):
        value = value2str(value.astype(list), delimiter=sep)
    elif value in EMPTY_VALUES:
        value = ''
    else:
        value = str(value)
    return value



class SpectralProfile(QgsFeature):

    crs = SPECLIB_CRS

    @staticmethod
    def profileName(basename:str, pxPosition:QPoint=None, geoPosition:QgsPointXY=None, index:int=None):
        """
        Unified method to generate the name of a single profile
        :param basename: base name
        :param pxPosition: optional, pixel position in source image
        :param geoPosition: optional, pixel position in geo-coordinates
        :param index: index, e.g. n'th-1 profile that was sampled from a data set
        :return: name
        """


        name = basename

        if isinstance(index, int):
            name += str(index)

        if isinstance(pxPosition, QPoint):
            name += '({}:{})'.format(pxPosition.x(), pxPosition.y())
        elif isinstance(geoPosition, QgsPoint):
            name += '({}:{})'.format(geoPosition.x(), geoPosition.y())
        return name.replace(' ', ':')

    @staticmethod
    def fromMapCanvas(mapCanvas, position)->list:
        """
        Returns a list of Spectral Profiles the raster layers in QgsMapCanvas mapCanvas.
        :param mapCanvas: QgsMapCanvas
        :param position: SpatialPoint
        """
        assert isinstance(mapCanvas, QgsMapCanvas)
        profiles = [SpectralProfile.fromRasterLayer(lyr, position) for lyr in mapCanvas.layers() if isinstance(lyr, QgsRasterLayer)]
        return [p for p in profiles if isinstance(p, SpectralProfile)]

    @staticmethod
    def fromRasterSources(sources:list, position:SpatialPoint)->list:
        """
        Returns a list of Spectral Profiles
        :param sources: list-of-raster-sources, e.g. file paths, gdal.Datasets, QgsRasterLayers
        :param position: SpatialPoint
        :return: [list-of-SpectralProfiles]
        """
        profiles = [SpectralProfile.fromRasterSource(s, position) for s in sources]
        return [p for p in profiles if isinstance(p, SpectralProfile)]



    @staticmethod
    def fromRasterLayer(layer:QgsRasterLayer, position:SpatialPoint):
        """
        Reads a SpectralProfile from a QgsRasterLayer
        :param layer: QgsRasterLayer
        :param position: SpatialPoint
        :return: SpectralProfile
        """

        position = position.toCrs(layer.crs())
        results = layer.dataProvider().identify(position, QgsRaster.IdentifyFormatValue).results()
        wl, wlu = parseWavelength(layer)

        y = list(results.values())
        for v in y:
            if not isinstance(v, (float, int)):
                return None

        profile = SpectralProfile()
        profile.setName(SpectralProfile.profileName(layer.name(), geoPosition=position))

        profile.setValues(x=wl, y=y, xUnit=wlu)

        profile.setCoordinates(position)
        profile.setSource('{}'.format(layer.source()))

        return profile

    @staticmethod
    def fromRasterSource(source, position, crs:QgsCoordinateReferenceSystem=None, gt:list=None, fields:QgsFields=None):
        """
        Returns the Spectral Profiles from source at position `position`
        :param source: str | gdal.Dataset | QgsRasterLayer - the raster source
        :param position: list of positions
                        QPoint -> pixel index position
                        QgsPointXY -> pixel geolocation position in layer/dataset CRS
                        SpatialPoint -> pixel geolocation position, will be transformed into layer/dataset CRS
        :param crs: QgsCoordinateReferenceSystem - coordinate reference system of raster source, defaults to the raster source CRS
        :param gt: geo-transformation 6-tuple, defaults to the GT of the raster source
        :return: SpectralProfile with QgsPoint-Geometry in EPSG:43
        """

        if isinstance(source, str):
            ds = gdal.Open(source)
        elif isinstance(source, gdal.Dataset):
            ds = source
        elif isinstance(source, QgsRasterLayer):
            ds = gdal.Open(source.source())

        assert isinstance(ds, gdal.Dataset)

        file = ds.GetDescription()
        if os.path.isfile(file):
            baseName = os.path.basename(file)
        else:
            baseName = 'Spectrum'

        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        if not isinstance(gt, list):
            gt = ds.GetGeoTransform()

        geoCoordinate = None
        if isinstance(position, QPoint):
            px = position
            geoCoordinate = SpatialPoint(crs, px2geo(px, gt, pxCenter=True)).toCrs(SPECLIB_CRS)
        elif isinstance(position, SpatialPoint):
            px = geo2px(position.toCrs(crs), gt)
            geoCoordinate = position.toCrs(SPECLIB_CRS)
        elif isinstance(position, QgsPointXY):
            px = geo2px(position, ds.GetGeoTransform())
            geoCoordinate = SpatialPoint(crs, position).toCrs(SPECLIB_CRS)
        else:
            raise Exception('Unsupported type of argument "position" {}'.format('{}'.format(position)))

        # check out-of-raster
        if px.x() < 0 or px.y() < 0:
            return None
        if px.x() > ds.RasterXSize - 1 or px.y() > ds.RasterYSize - 1:
            return None

        y = ds.ReadAsArray(px.x(), px.y(), 1, 1)

        y = y.flatten()
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b+1)
            nodata = band.GetNoDataValue()
            if nodata and y[b] == nodata:
                return None

        wl, wlu = parseWavelength(ds)

        profile = SpectralProfile(fields=fields)
        profile.setName(SpectralProfile.profileName(baseName, pxPosition=px))
        profile.setValues(x=wl, y=y, xUnit=wlu)
        profile.setCoordinates(geoCoordinate)
        profile.setSource('{}'.format(ds.GetDescription()))
        return profile




    @staticmethod
    def fromSpecLibFeature(feature:QgsFeature):
        """
        Converts a QgsFeature into a SpectralProfile
        :param feature: QgsFeature
        :return: SpectralProfile
        """
        assert isinstance(feature, QgsFeature)
        sp = SpectralProfile(fields=feature.fields())
        sp.setId(feature.id())
        sp.setAttributes(feature.attributes())
        sp.setGeometry(feature.geometry())
        return sp


    def __init__(self, parent=None, fields=None, values:dict=None):


        if fields is None:
            fields = createStandardFields()
        assert isinstance(fields, QgsFields)
        #QgsFeature.__init__(self, fields)
        #QObject.__init__(self)
        super(SpectralProfile, self).__init__(fields)
        #QObject.__init__(self)
        #fields = self.fields()

        assert isinstance(fields, QgsFields)
        self.mValueCache = None
        #self.setStyle(DEFAULT_SPECTRUM_STYLE)
        if isinstance(values, dict):
            self.setValues(**values)



    def fieldNames(self)->typing.List[str]:
        """
        Returns all field names
        :return:
        """
        return self.fields().names()

    def setName(self, name:str):
        if name != self.name():
            self.setAttribute(FIELD_NAME, name)
            #self.sigNameChanged.emit(name)

    def name(self)->str:
        return self.metadata(FIELD_NAME)

    def setSource(self, uri: str):
        self.setAttribute('source', uri)

    def source(self):
        return self.metadata('source')

    def setCoordinates(self, pt):
        if isinstance(pt, SpatialPoint):
            sp = pt.toCrs(SpectralProfile.crs)
            self.setGeometry(QgsGeometry.fromPointXY(sp))
        elif isinstance(pt, QgsPointXY):
            self.setGeometry(QgsGeometry.fromPointXY(pt))

    def geoCoordinate(self):
        return self.geometry()

    def updateMetadata(self, metaData):
        if isinstance(metaData, dict):
            for key, value in metaData.items():
                self.setMetadata(key, value)

    def removeField(self, name):
        fields = self.fields()
        values = self.attributes()
        i = self.fieldNameIndex(name)
        if i >= 0:
            fields.remove(i)
            values.pop(i)
            self.setFields(fields)
            self.setAttributes(values)

    def setMetadata(self, key: str, value, addMissingFields=False):
        """
        :param key: Name of metadata field
        :param value: value to add. Need to be of type None, str, int or float.
        :param addMissingFields: Set on True to add missing fields (in case value is not None)
        :return:
        """
        i = self.fieldNameIndex(key)

        if i < 0:
            if value is not None and addMissingFields:

                fields = self.fields()
                values = self.attributes()
                fields.append(createQgsField(key, value))
                values.append(value)
                self.setFields(fields)
                self.setAttributes(values)

            return False
        else:
            return self.setAttribute(key, value)

    def metadata(self, key: str, default=None):
        """
        Returns a field value or None, if not existent
        :param key: str, field name
        :param default: default value to be returned
        :return: value
        """
        assert isinstance(key, str)
        i = self.fieldNameIndex(key)
        if i < 0:
            return None

        v = self.attribute(i)
        if v == QVariant(None):
            v = None
        return default if v is None else v

    def nb(self)->int:
        """
        Returns the number of profile bands / profile values
        :return: int
        :rtype:
        """
        return len(self.yValues())

    def values(self)->dict:
        """
        Returns a dictionary with 'x', 'y', 'xUnit' and 'yUnit' values.
        :return: {'x':list,'y':list,'xUnit':str,'yUnit':str, 'bbl':list}
        """
        if self.mValueCache is None:
            jsonStr = self.attribute(self.fields().indexFromName(FIELD_VALUES))
            d = decodeProfileValueDict(jsonStr)

            # save a reference to the decoded dictionary
            self.mValueCache = d

        return self.mValueCache

    def setValues(self, x=None, y=None, xUnit=None, yUnit=None, bbl=None):

        d = self.values().copy()

        if isinstance(x, np.ndarray):
            x = x.tolist()

        if isinstance(y, np.ndarray):
            y = y.tolist()

        if isinstance(bbl, np.ndarray):
            bbl = bbl.astype(bool).tolist()

        if isinstance(x, list):
            d['x'] = x

        if isinstance(y, list):
            d['y'] = y

        if isinstance(bbl, list):
            d['bbl'] = bbl

        # ensure x/y/bbl are list or None
        assert d['x'] is None or isinstance(d['x'], list)
        assert d['y'] is None or isinstance(d['y'], list)
        assert d['bbl'] is None or isinstance(d['bbl'], list)

        # ensure same length
        if isinstance(d['x'], list):
            assert isinstance(d['y'], list), 'y values need to be specified'

            assert len(d['x']) == len(d['y']), \
                'x and y need to have the same number of values ({} != {})'.format(len(d['x']), len(d['y']))

        if isinstance(d['bbl'], list):
            assert isinstance(d['y'], list), 'y values need to be specified'
            assert len(d['bbl']) == len(d['y']), \
                'y and bbl need to have the same number of values ({} != {})'.format(len(d['y']), len(d['bbl']))

        if isinstance(xUnit, str):
            d['xUnit'] = xUnit
        if isinstance(yUnit, str):
            d['yUnit'] = yUnit

        self.setAttribute(FIELD_VALUES, encodeProfileValueDict(d))
        self.mValueCache = d


    def xValues(self)->list:
        """
        Returns the x Values / wavelength information.
        If wavelength information is not undefined it will return a list of band indices [0, ..., n-1]
        :return: [list-of-numbers]
        """
        x = self.values()['x']

        if not isinstance(x, list):
            return list(range(len(self.yValues())))
        else:
            return x



    def yValues(self)->list:
        """
        Returns the x Values / DN / spectral profile values.
        List is empty if not numbers are stored
        :return: [list-of-numbers]
        """
        y = self.values()['y']
        if not isinstance(y, list):
            return []
        else:
            return y

    def bbl(self)->list:
        """
        Returns the BadBandList.
        :return:
        :rtype:
        """
        bbl = self.values().get('bbl')
        if not isinstance(bbl, list):
            bbl = np.ones(self.nb(), dtype=np.byte).tolist()
        return bbl

    def setXUnit(self, unit : str):
        d = self.values()
        d['xUnit'] = unit
        self.setValues(**d)

    def xUnit(self)->str:
        """
        Returns the semantic unit of x values, e.g. a wavelength unit like 'nm' or 'um'
        :return: str
        """
        return self.values()['xUnit']

    def setYUnit(self, unit:str=None):
        """
        :param unit:
        :return:
        """
        d = self.values()
        d['yUnit'] = unit
        self.setValues(**d)

    def yUnit(self)->str:
        """
        Returns the semantic unit of y values, e.g. 'reflectances'"
        :return: str
        """

        return self.values()['yUnit']

    def copyFieldSubset(self, fields):

        sp = SpectralProfile(fields=fields)

        fieldsInCommon = [field for field in sp.fields() if field in self.fields()]

        sp.setGeometry(self.geometry())
        sp.setId(self.id())

        for field in fieldsInCommon:
            assert isinstance(field, QgsField)
            i = sp.fieldNameIndex(field.name())
            sp.setAttribute(i, self.attribute(field.name()))
        return sp

    def clone(self):
        """
        Create a clone of this SpectralProfile
        :return: SpectralProfile
        """
        return self.__copy__()

    def plot(self):
        """
        Plots this profile to an new PyQtGraph window
        :return:
        """
        from .plotting import SpectralProfilePlotDataItem
        pi = SpectralProfilePlotDataItem(self)
        pi.setClickable(True)
        pw = pg.plot( title=self.name())
        pw.getPlotItem().addItem(pi)

        pi.setColor('green')
        #pg.QAPP.exec_()


    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):

        if self.mValueCache is None:
            self.values()
        wkt = self.geometry().asWkt()
        state = (qgsFields2str(self.fields()), qgsFieldAttributes2List(self.attributes()), wkt)
        dump = pickle.dumps(state)
        return dump

    def __setstate__(self, state):
        state = pickle.loads(state)
        fields, attributes, wkt = state
        fields = str2QgsFields(fields)
        self.setFields(fields)
        self.setGeometry(QgsGeometry.fromWkt(wkt))
        self.setAttributes(attributes)


    def __copy__(self):
        sp = SpectralProfile(fields=self.fields())
        sp.setId(self.id())
        sp.setAttributes(self.attributes())
        sp.setGeometry(QgsGeometry.fromWkt(self.geometry().asWkt()))
        if isinstance(self.mValueCache, dict):
            sp.values()
        return sp

    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if not np.array_equal(self.fieldNames(), other.fieldNames()):
            return False

        names1 = self.fieldNames()
        names2 = other.fieldNames()
        for i1, n in enumerate(self.fieldNames()):
            if n == FIELD_FID:
                continue
            elif n == FIELD_VALUES:
                if self.xValues() != other.xValues():
                    return False
                if self.yValues() != other.yValues():
                    return False
                if self.xUnit() != other.xUnit():
                    return False
            else:
                i2 = names2.index(n)
                if self.attribute(i1) != other.attribute(i2):
                    return False

        return True

    def __hash__(self):

        return hash(id(self))

    def setId(self, id):
        self.setAttribute(FIELD_FID, id)
        if id is not None:
            super(SpectralProfile, self).setId(id)

    """
    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if len(self.mValues) != len(other.mValues):
            return False
        return all(a == b for a,b in zip(self.mValues, other.mValues)) \
            and self.mValuePositions == other.mValuePositions \
            and self.mValueUnit == other.mValueUnit \
            and self.mValuePositionUnit == other.mValuePositionUnit \
            and self.mGeoCoordinate == other.mGeoCoordinate \
            and self.mPxCoordinate == other.mPxCoordinate

    def __ne__(self, other):
        return not self.__eq__(other)
    """
    def __len__(self):
        return len(self.yValues())



class SpectralLibrary(QgsVectorLayer):
    """
    SpectralLibrary
    """
    _instances = []

    @staticmethod
    def readFromMimeData(mimeData:QMimeData):
        """
        Reads a SpectraLibrary from mime data.
        :param mimeData: QMimeData
        :return: SpectralLibrary
        """
        if MIMEDATA_SPECLIB_LINK in mimeData.formats():
            # extract from link
            sid = pickle.loads(mimeData.data(MIMEDATA_SPECLIB_LINK))
            global SPECLIB_CLIPBOARD
            sl = SPECLIB_CLIPBOARD.get(sid)
            if isinstance(sl, SpectralLibrary) and id(sl) == sid:
                return sl
            else:
                return None
        elif MIMEDATA_SPECLIB in mimeData.formats():
            return SpectralLibrary.readFromPickleDump(mimeData.data(MIMEDATA_SPECLIB))

        elif MIMEDATA_TEXT in mimeData.formats():
            txt = mimeData.text()
            from .csvdata import CSVSpectralLibraryIO
            return CSVSpectralLibraryIO.fromString(txt)

        elif MIMEDATA_URL in mimeData.formats():
            return SpectralLibrary.readFrom(mimeData.urls()[0])


        return None

    @staticmethod
    def readFromPickleDump(data):
        """
        Reads a SpectralLibrary from a pickle.dump()-generate bytes object.
        :param data: bytes
        :return: SpectralLibrary
        """
        return pickle.loads(data)

    @staticmethod
    def readFromSourceDialog(parent=None):
        """
        Opens a FileOpen dialog to select a spectral library
        :param parent:
        :return: SpectralLibrary
        """

        SETTINGS = speclibSettings()
        lastDataSourceDir = SETTINGS.value('SpeclibSourceDirectory', '')

        if not QFileInfo(lastDataSourceDir).isDir():
            lastDataSourceDir = None

        uris, filter = QFileDialog.getOpenFileNames(parent, "Open spectral library", lastDataSourceDir, filter=FILTERS + ';;All files (*.*)', )

        if len(uris) > 0:
            SETTINGS.setValue('SpeclibSourceDirectory', os.path.dirname(uris[0]))

        uris = [u for u in uris if QFileInfo(u).isFile()]

        if len(uris) == 0:
            return None

        speclib = SpectralLibrary()
        speclib.startEditing()
        for u in uris:
            sl = SpectralLibrary.readFrom(str(u))
            if isinstance(sl, SpectralLibrary):
                speclib.addProfiles(sl)
        assert speclib.commitChanges()
        return speclib

    # thanks to Ann for providing https://bitbucket.org/jakimowb/qgispluginsupport/issues/6/speclib-spectrallibrariespy
    @staticmethod
    def readFromVector(vector_qgs_layer:QgsVectorLayer=None,
                       raster_qgs_layer:QgsRasterLayer=None,
                       progressDialog:QProgressDialog=None,
                       nameField=None,
                       all_touched=False,
                       returnProfileList=False):
        """
        Reads SpectraProfiles from a raster source, based on the locations specified in a vector data set.
        Opens a Select Polygon Layer dialog to select the correct polygon and returns a Spectral Library with
        metadata according to the polygons attribute table.

        :param vector_qgs_layer: QgsVectorLayer | str
        :param raster_qgs_layer: QgsRasterLayer | str
        :param progressDialog: QProgressDialog (optional)
        :param nameField: str | int | QgsField that is used to generate individual profile names.
        :param all_touched: bool, False (default) = extract only pixel entirely covered with a geometry
                                  True = extract all pixels touched by a geometry
        :param returnProfileList: bool, False (default) = return a SpectralLibrary
                                        True = return a [list-of-SpectralProfiles] and skip the SpectralLibrary generations.
        :return: Spectral Library | [list-of-profiles]
        """

        # the SpectralLibrary to be returned
        spectral_library = SpectralLibrary()

        # homogenize source file formats
        try:
            vector_qgs_layer = qgsVectorLayer(vector_qgs_layer)
            raster_qgs_layer = qgsRasterLayer(raster_qgs_layer)
        except Exception as ex:
            print(ex, file=sys.stderr)

        # get QgsLayers of vector and raster
        from ..utils import SelectMapLayersDialog
        if not (isinstance(vector_qgs_layer, QgsVectorLayer) and isinstance(raster_qgs_layer, QgsRasterLayer)):

            dialog = SelectMapLayersDialog()
            dialog.addLayerDescription('Raster', QgsMapLayerProxyModel.RasterLayer)
            dialog.addLayerDescription('Vector', QgsMapLayerProxyModel.VectorLayer)
            dialog.exec_()
            if dialog.result() == QDialog.Accepted:
                raster_qgs_layer, vector_qgs_layer = dialog.mapLayers()

                if not isinstance(vector_qgs_layer, QgsVectorLayer) or not isinstance(raster_qgs_layer, QgsRasterLayer):
                    return

        # get the shapefile fields and check the minimum requirements

        # field in the vector source
        vector_fields = vector_qgs_layer.fields()

        # fields in the output-spectral library
        speclib_fields = createStandardFields()

        # fields we need to copy values from the vector source to each SpectralProfile
        fields_to_copy = []
        for field in vector_fields:
            if speclib_fields.indexOf(field.name()) == -1:
                speclib_fields.append(QgsField(field))
                fields_to_copy.append(field.name())
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG'
        # set spatial filter in destination CRS
        options.filterExtent = SpatialExtent.fromLayer(raster_qgs_layer)
        #options.filterExtent = SpatialExtent.fromLayer(raster_qgs_layer).toCrs(vector_qgs_layer.crs())
        options.destCRS = raster_qgs_layer.crs()
        tmpPath = '/vsimem/tmp_transform{}.gpkg'.format(vector_qgs_layer.name())
        ct = QgsCoordinateTransform()
        ct.setSourceCrs(vector_qgs_layer.crs())
        ct.setDestinationCrs(raster_qgs_layer.crs())
        options.ct = ct
        error = QgsVectorFileWriter.writeAsVectorFormat(layer=vector_qgs_layer,
                                                        fileName=tmpPath,
                                                        options=options)
        vector_qgs_layer.disconnect()
        del vector_qgs_layer

        # make the internal FID a normal attribute which gdal can rasterize
        tmp_qgs_layer = QgsVectorLayer(tmpPath)
        if tmp_qgs_layer.featureCount() == 0:
            info = 'No intersection between\nraster {} and vector {}'.format(raster_qgs_layer.source(), vector_qgs_layer.source())
            print(info)
            if isinstance(progressDialog, QProgressDialog):
                progressDialog.setLabelText('No intersection between raster and vector source')
                progressDialog.setValue(progressDialog.maximum())
            return spectral_library
        assert isinstance(tmp_qgs_layer, QgsVectorLayer)
        assert tmp_qgs_layer.isValid()
        assert tmp_qgs_layer.startEditing()
        fidName = 'tmpFID'
        i = 1
        while fidName in tmp_qgs_layer.fields().names():
            fidName = 'tmpFID{}'.format(i)
            i += 1
        tmp_qgs_layer.addAttribute(QgsField(fidName,  QVariant.Int, 'int'))
        assert tmp_qgs_layer.commitChanges()
        assert fidName in tmp_qgs_layer.fields().names()

        # let the tmpFID be fid + 1, so that there is not negative or zero tmpFID
        # this will be the value to be burned into the gdal raster
        assert tmp_qgs_layer.startEditing()

        i = tmp_qgs_layer.fields().lookupField(fidName)
        for fid in [fid for fid in tmp_qgs_layer.allFeatureIds() if fid >= 0]:
            tmp_qgs_layer.changeAttributeValue(fid, i, fid+1)
        assert tmp_qgs_layer.commitChanges()

        # get ORG/GDAL dataset and OGR/GDAL layer of vector and raster
        tmp_ogrDataSource = ogr.Open(tmpPath)
        assert isinstance(tmp_ogrDataSource, ogr.DataSource)
        assert tmp_ogrDataSource.GetLayerCount() == 1
        tmp_ogrLayer = tmp_ogrDataSource.GetLayer(0)
        assert isinstance(tmp_ogrLayer, ogr.Layer)

        raster_dataset = gdal.Open(raster_qgs_layer.source())

        badBandList = parseBadBandList(raster_dataset)
        wl, wlu = parseWavelength(raster_dataset)

        bn = os.path.basename(raster_dataset.GetDescription())
        assert isinstance(raster_dataset, gdal.Dataset)

        # create in-memory raster to burn the tempFID into
        memDrv = gdal.GetDriverByName('MEM')
        memRaster = memDrv.Create('', raster_dataset.RasterXSize, raster_dataset.RasterYSize, 1, gdal.GDT_UInt32)
        assert isinstance(memRaster, gdal.Dataset)
        band = memRaster.GetRasterBand(1)
        assert isinstance(band, gdal.Band)
        band.Fill(0)
        memRaster.SetGeoTransform(raster_dataset.GetGeoTransform())
        memRaster.SetProjection(raster_dataset.GetProjection())
        memRaster.FlushCache()
        all_touched = 'TRUE' if all_touched else 'FALSE'
        gdal.RasterizeLayer(memRaster, [1], tmp_ogrLayer,
                            options=['ALL_TOUCHED={}'.format(all_touched),
                                     'ATTRIBUTE={}'.format(fidName)])
        # read the burned tmpFIDs
        tmpFIDArray = memRaster.ReadAsArray()
        y, x = np.where(tmpFIDArray > 0)
        n_profiles = len(y)

        # decrease tmpFID array by 1 (we already got the right positions)
        # it now contains the real FID values
        tmpFIDArray = tmpFIDArray - 1

        if n_profiles == 0:
            # no profiles to extract. Return an empty speclib
            if isinstance(progressDialog, QProgressDialog):
                progressDialog.setValue(progressDialog.maximum())
            return spectral_library

        if isinstance(progressDialog, QProgressDialog):

            progressDialog.setRange(0, raster_dataset.RasterCount + n_profiles + 1)
            progressDialog.setValue(0)
            progressDialog.setLabelText('Read {} profiles...'.format(n_profiles))

        fids = tmpFIDArray[y, x]
        unique_fids = np.unique(fids).tolist()
        fids = fids.tolist()

        del tmp_ogrLayer, tmpFIDArray, memRaster, memDrv

        # save all profiles in a spectral library
        profiles = []

        # transform x/y pixel position into the speclib crs
        rasterCRS = raster_qgs_layer.crs()
        rasterGT = raster_dataset.GetGeoTransform()

        rasterSRS = osr.SpatialReference()
        rasterSRS.ImportFromWkt(rasterCRS.toWkt())
        speclibSRS = osr.SpatialReference()
        speclibSRS.ImportFromWkt(spectral_library.crs().toWkt())

        # GDAL 3.0 considers authority specific axis order
        # see https://github.com/OSGeo/gdal/issues/1974
        #     https://gdal.org/tutorials/osr_api_tut.html
        rasterSRS.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        speclibSRS.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        # transform many coordinates fast!
        transSRS = osr.CoordinateTransformation(rasterSRS, speclibSRS)

        # geo-coordinate in raster CRS
        # move to pixel center
        if True:
            x2, y2 = x + 0.5, y + 0.5
        else:
            x2, y2 = x, y

        geo_coordinates = np.empty((n_profiles, 2), dtype=np.float)
        geo_coordinates[:, 0] = rasterGT[0] + x2 * rasterGT[1] + y2 * rasterGT[2]
        geo_coordinates[:, 1] = rasterGT[3] + x2 * rasterGT[4] + y2 * rasterGT[5]

        geo_coordinates = transSRS.TransformPoints(geo_coordinates)

        attr_idx_profile = []
        attr_idx_feature = []
        tmpProfile = SpectralProfile(fields=speclib_fields)
        for fieldName in fields_to_copy:
            attr_idx_profile.append(tmpProfile.fields().indexOf(fieldName))
            attr_idx_feature.append(vector_fields.indexOf(fieldName))


        # store relevant features in memory for faster accesss
        features = {}
        featureAttributes = {}
        for f in tmp_qgs_layer.getFeatures(unique_fids):
            assert isinstance(f, QgsFeature)
            features[f.id()] = f

        # 1. read raster values

        xoff, yoff = int(min(x)), int(min(y))
        maxx, maxy = int(max(x)), int(max(y))
        win_xsize, win_ysize = maxx-xoff+1, maxy-yoff+1

        x_win, y_win = x - xoff, y - yoff

        profileData = None

        for b in range(raster_dataset.RasterCount):
            if isinstance(progressDialog, QProgressDialog):
                if progressDialog.wasCanceled():
                    return None
                progressDialog.setValue(progressDialog.value()+1)

            band = raster_dataset.GetRasterBand(b+1)
            assert isinstance(band, gdal.Band)
            bandData = band.ReadAsArray(xoff=xoff, yoff=yoff, win_xsize=win_xsize, win_ysize=win_ysize)
            pxData = bandData[y_win, x_win]

            assert len(pxData) == n_profiles

            if profileData is None:
                profileData = np.ones((raster_dataset.RasterCount, n_profiles), dtype=pxData.dtype)
            profileData[b, :] = pxData

        del raster_dataset, bandData

        # 2. write profiles + some meta data from the source vector file
        wasPointGeometry = tmp_qgs_layer.wkbType() in [QgsWkbTypes.Point, QgsWkbTypes.PointGeometry]
        if wasPointGeometry:
            pass

        # which field is to choose to describe the spectrum name?
        nameFieldIndex = None
        if isinstance(nameField, int):
            nameFieldIndex = nameField
        elif isinstance(nameField, QgsField):
            nameFieldIndex = vector_fields.lookupField(nameField.name())
        elif isinstance(nameField, str):
            nameFieldIndex = vector_fields.lookupField(nameField)

        if nameFieldIndex is None:
            for i, field in enumerate(vector_fields):
                assert isinstance(field, QgsField)
                if field.type() == QVariant.String and re.search(field.name(), 'Name', re.I):
                    nameFieldIndex = vector_fields.lookupField(field.name())
                    break
        if nameFieldIndex is None:
            for i, field in enumerate(vector_fields):
                assert isinstance(field, QgsField)
                if re.search(field.name(), '^(fid|id)$', re.I):
                    nameFieldIndex = vector_fields.lookupField(field.name())
                    break

        profileNameCounts = dict() # dictionary to store spectra names

        for iProfile, fid, in enumerate(fids):
            if isinstance(progressDialog, QProgressDialog):
                if progressDialog.wasCanceled():
                    return None
                progressDialog.setValue(progressDialog.value()+1)

            feature = features[fid]
            assert isinstance(feature, QgsFeature)
            profile = SpectralProfile(fields=speclib_fields)

            # 2.1 set profile id
            profile.setId(iProfile)

            # 2.2. set profile name
            if nameFieldIndex is None:
                px_x, px_y = x[iProfile], y[iProfile]
                profileName = '{} {},{}'.format(bn, px_x, px_y)
            else:
                profileName = str(feature.attribute(nameFieldIndex))

                n = profileNameCounts.get(profileName)
                # n = 1 -> Foobar
                # n > 1 -> Foobar (n)
                if n is None:
                    profileNameCounts[profileName] = 1
                else:
                    profileNameCounts[profileName] = n + 1
                    profileName = profileName + ' ({})'.format(n + 1)
            profile.setName(profileName)

            # 2.3 set geometry
            g = geo_coordinates[iProfile]
            profile.setGeometry(QgsPoint(g[0], g[1]))

            # 2.4 copy vector feature attribute
            for idx_p, idx_f in zip(attr_idx_profile, attr_idx_feature):
                profile.setAttribute(idx_p, feature.attribute(idx_f))

            # 2.5 set the profile values
            profile.setValues(x=wl, y=profileData[:, iProfile], xUnit=wlu, bbl=badBandList)
            profiles.append(profile)

        if returnProfileList:
            return profiles

        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setLabelText('Create speclib...')

        assert spectral_library.startEditing()
        spectral_library.addMissingFields(vector_fields)
        assert spectral_library.commitChanges()
        assert spectral_library.startEditing()

        # spectral_library.addProfiles(profiles)
        if not spectral_library.addFeatures(profiles, QgsFeatureSink.FastInsert):
            s = ""

        if not spectral_library.commitChanges():
            s = ""

        if isinstance(progressDialog, QProgressDialog):
            # print('{} {} {}'.format(progressDialog.minimum(), progressDialog.maximum(), progressDialog.value()))
            progressDialog.setValue(progressDialog.value()+1)

        tmp_qgs_layer.disconnect()
        del tmp_qgs_layer
        gdal.Unlink(tmpPath)


        return spectral_library


    @staticmethod
    def readFromVectorPositions(rasterSource, vectorSource, mode='CENTROIDS', progressDialog:QProgressDialog=None):
        """

        :param pathRaster:
        :param vectorSource:
        :param mode:
        :return:
        """
        warnings.warn(DeprecationWarning(r'Use readFromVector instead'))
        assert mode in ['CENTROIDS', 'AVERAGES', 'PIXELS']

        if isinstance(rasterSource, str):
            rasterSource = QgsRasterLayer(rasterSource)
        elif isinstance(rasterSource, gdal.Dataset):
            rasterSource = QgsRasterLayer(rasterSource, '', 'gdal')

        assert isinstance(rasterSource, QgsRasterLayer)

        if isinstance(vectorSource, str):
            vectorSource = QgsVectorLayer(vectorSource)
        elif isinstance(vectorSource, ogr.DataSource):
            raise NotImplementedError()

        assert isinstance(vectorSource, QgsVectorLayer)

        extentRaster = SpatialExtent.fromLayer(rasterSource)
        vectorSource.selectByRect(extentRaster.toCrs(vectorSource.crs()))

        trans = QgsCoordinateTransform()
        trans.setSourceCrs(vectorSource.crs())
        trans.setDestinationCrs(rasterSource.crs())

        nSelected = vectorSource.selectedFeatureCount()

        gt = layerGeoTransform(rasterSource)
        extent = rasterSource.extent()
        center = extent.center()
        #m2p = QgsMapToPixel(rasterSource.rasterUnitsPerPixelX(),
        #                    center.x() + 0.5*rasterSource.rasterUnitsPerPixelX(),
        #                    center.y() - 0.5*rasterSource.rasterUnitsPerPixelY(),
        #                    rasterSource.width(), rasterSource.height(), 0)

        pixelpositions = []

        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setMinimum(0)
            progressDialog.setMaximum(nSelected)
            progressDialog.setLabelText('Get pixel positions...')

        nMissingGeometry = []
        for i, feature in enumerate(vectorSource.selectedFeatures()):
            if isinstance(progressDialog, QProgressDialog) and progressDialog.wasCanceled():
                return None

            assert isinstance(feature, QgsFeature)

            if feature.hasGeometry():
                g = feature.geometry().constGet()

                if isinstance(g, QgsPoint):
                    point = trans.transform(QgsPointXY(g))
                    px = geo2px(point, gt)
                    pixelpositions.append(px)

                if isinstance(g, QgsMultiPoint):
                    for point in g.parts():
                        if isinstance(point, QgsPoint):
                            point = trans.transform(QgsPointXY(point))
                            px = geo2px(point, gt)
                            pixelpositions.append(px)
                    s = ""
            else:
                nMissingGeometry += 1

            if isinstance(progressDialog, QProgressDialog):
                progressDialog.setValue(progressDialog.value()+1)

        if len(nMissingGeometry) > 0:
            print('{} features without geometry in {}'.format(nMissingGeometry))

        return SpectralLibrary.readFromRasterPositions(rasterSource, pixelpositions, progressDialog=progressDialog)


    def reloadSpectralValues(self, raster, selectedOnly:bool=True):
        """
        Reloads the spectral values for each point based on the spectral values found in raster image "path-raster"
        :param raster: str | QgsRasterLayer | gdal.Dataset
        :param selectedOnly: bool, if True (default) spectral values will be retireved for selected features only.
        """
        assert self.isEditable()

        source = gdalDataset(raster)
        assert isinstance(source, gdal.Dataset)
        gt = source.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(source.GetProjection())

        geoPositions = []
        fids = []

        features = self.selectedFeatures() if selectedOnly else self.features()
        for f in features:
            assert isinstance(f, QgsFeature)
            if f.hasGeometry():
                fids.append(f.id())
                geoPositions.append(QgsPointXY(f.geometry().get()))
        if len(fids) == 0:
            return

        # transform feature coordinates into the raster data set's CRS
        if crs != self.crs():
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(self.crs())
            trans.setDestinationCrs(crs)
            geoPositions = [trans.transform(p) for p in geoPositions]

        # transform coordinates into pixel positions
        pxPositions = [geo2px(p, gt) for p in geoPositions]

        idxSPECLIB = self.fields().indexOf(FIELD_VALUES)
        idxPROFILE = None

        for fid, pxPosition in zip(fids, pxPositions):
            assert isinstance(pxPosition, QPoint)
            profile = SpectralProfile.fromRasterSource(source, pxPosition, crs=crs, gt=gt)
            if isinstance(profile, SpectralProfile):
                if idxPROFILE is None:
                    idxPROFILE = profile.fields().indexOf(FIELD_VALUES)
                assert self.changeAttributeValue(fid, idxSPECLIB, profile.attribute(idxPROFILE))


    @staticmethod
    def readFromRasterPositions(pathRaster, positions, progressDialog:QProgressDialog=None):
        """
        Reads a SpectralLibrary from a set of positions
        :param pathRaster:
        :param positions:
        :return:
        """
        if not isinstance(positions, list):
            positions = [positions]
        profiles = []

        source = gdalDataset(pathRaster)
        i = 0


        nTotal = len(positions)
        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setMinimum(0)
            progressDialog.setMaximum(nTotal)
            progressDialog.setValue(0)
            progressDialog.setLabelText('Extract pixel profiles...')

        for p, position in enumerate(positions):

            if isinstance(progressDialog, QProgressDialog) and progressDialog.wasCanceled():
                return None

            profile = SpectralProfile.fromRasterSource(source, position)
            if isinstance(profile, SpectralProfile):
                profiles.append(profile)
                i += 1

            if isinstance(progressDialog, QProgressDialog):
                progressDialog.setValue(progressDialog.value()+1)


        sl = SpectralLibrary()
        sl.startEditing()
        sl.addProfiles(profiles)
        assert sl.commitChanges()
        return sl


    def readJSONProperties(self, pathJSON:str):
        """
        Reads additional SpectralLibrary properties from a JSON definition according to
        https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual.html#labelled-spectral-library

        :param pathJSON: file path (any) | JSON dictionary | str

        :returns: None | JSON dictionary
        """
        jsonData = None
        try:
            if isinstance(pathJSON, dict):
                jsonData = pathJSON
            elif isinstance(pathJSON, str):
                if os.path.isfile(pathJSON):
                    if not re.search(r'.json$', pathJSON):
                        pathJSON = os.path.splitext(pathJSON)[0] + '.json'
                        if not os.path.isfile(pathJSON):
                            return
                    with open(pathJSON, 'r') as file:
                        jsonData = json.load(file)
                else:
                    jsonData = json.loads(pathJSON)

        except Exception as ex:
            pass

        if not isinstance(jsonData, dict):
            return None
        b = self.isEditable()
        self.startEditing()
        try:
            for fieldName in self.fields().names():
                fieldIndex = self.fields().lookupField(fieldName)
                field = self.fields().at(fieldIndex)
                assert isinstance(field, QgsField)
                assert isinstance(fieldName, str)
                if fieldName in jsonData.keys():
                    fieldProperties = jsonData[fieldName]
                    assert isinstance(fieldProperties, dict)

                    # see https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual.html#labelled-spectral-library
                    # for details
                    if 'categories' in fieldProperties.keys():
                        from ..classification.classificationscheme import ClassificationScheme, ClassInfo, classSchemeToConfig
                        from ..classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as ClassEditorKey
                        classes = []
                        for item in fieldProperties['categories']:
                            cColor = None
                            if len(item) >= 3:
                                cColor = item[2]
                                if isinstance(cColor, str):
                                    cColor = QColor(cColor)
                                elif isinstance(cColor, list):
                                    cColor = QColor(*cColor)

                            classes.append(ClassInfo(label=int(item[0]), name=str(item[1]), color=cColor))
                        classes = sorted(classes, key=lambda c: c.label())
                        scheme = ClassificationScheme()
                        for classInfo in classes:
                            scheme.insertClass(classInfo)
                        classConfig = classSchemeToConfig(scheme)

                        self.setEditorWidgetSetup(fieldIndex,
                                                  QgsEditorWidgetSetup(ClassEditorKey, classConfig))

                        s = ""
                    if 'no data value' in fieldProperties.keys():
                        defaultValue = QgsDefaultValue('{}'.format(fieldProperties['no data value']))
                        field.setDefaultValueDefinition(defaultValue)
                        pass

                    if 'description' in fieldProperties.keys():
                        field.setComment(fieldProperties['description'])

            self.commitChanges()
        except Exception as ex:
            self.rollBack()
            print(ex, file=sys.stderr)

        if b:
            self.startEditing()

        return jsonData

    def writeJSONProperties(self, pathSPECLIB:str):
        """
        Writes additional field properties into a JSON files
        :param pathSPECLIB:
        :return:
        """
        assert isinstance(pathSPECLIB, str)
        if not pathSPECLIB.endswith('.json'):
            pathJSON = os.path.splitext(pathSPECLIB)[0]+'.json'
        else:
            pathJSON = pathSPECLIB
        jsonData = collections.OrderedDict()



        from ..classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY, classSchemeFromConfig, ClassificationScheme, ClassInfo

        rendererCategories = None

        # is this speclib rendered with a QgsCategorizedSymbolRenderer?
        if isinstance(self.renderer(), QgsCategorizedSymbolRenderer):
            rendererCategories = []
            for i, c in enumerate(self.renderer().categories()):
                assert isinstance(c, QgsRendererCategory)
                symbol = c.symbol()
                assert isinstance(symbol, QgsSymbol)
                try:
                    label = int(c.value())
                except:
                    label = i
                category = [label, str(c.label()), symbol.color().name()]
                rendererCategories.append(category)
            jsonData[self.renderer().classAttribute()] = {'categories': rendererCategories}

        # is any field described as Raster Renderer or QgsCategorizedSymbolRenderer?
        for fieldIdx, field in enumerate(self.fields()):
            assert isinstance(field, QgsField)
            attributeEntry = dict()
            if len(field.comment()) > 0:
                attributeEntry['description'] = field.comment()

            defaultValue = field.defaultValueDefinition()
            assert isinstance(defaultValue, QgsDefaultValue)
            if len(defaultValue.expression()) > 0:
                attributeEntry['no data value'] = defaultValue.expression()

            setup = self.editorWidgetSetup(fieldIdx)
            assert isinstance(setup, QgsEditorWidgetSetup)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                conf = setup.config()
                classScheme = classSchemeFromConfig(conf)
                if len(classScheme) > 0:

                    categories = []
                    for classInfo in classScheme:
                        assert isinstance(classInfo, ClassInfo)
                        category = [classInfo.label(), classInfo.name(), classInfo.color().name()]
                        categories.append(category)
                    attributeEntry['categories'] = categories

            elif setup.type() == 'Classification' and isinstance(rendererCategories, list):
                    attributeEntry['categories'] = rendererCategories

            if len(attributeEntry) > 0:
                jsonData[field.name()] = attributeEntry

        if len(jsonData) > 0:
            with open(pathJSON, 'w', encoding='utf-8') as f:
                json.dump(jsonData, f)


    @staticmethod
    def readFrom(uri, progressDialog:QProgressDialog=None):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        if isinstance(uri, str) and uri.endswith('.gpkg'):
            try:
                return SpectralLibrary(uri=uri)
            except Exception as ex:
                print(ex)
                return None


        readers = AbstractSpectralLibraryIO.__subclasses__()

        for cls in sorted(readers, key=lambda r:r.score(uri)):
            try:
                if cls.canRead(uri):
                    return cls.readFrom(uri, progressDialog=progressDialog)
            except Exception as ex:
                s = ""
        return None

    sigNameChanged = pyqtSignal(str)

    __refs__ = []
    @classmethod
    def instances(cls)->list:

        refs = []
        instances = []

        for r in SpectralLibrary.__refs__:
            if r is not None:
                instance = r()
                if isinstance(instance, SpectralLibrary):
                    refs.append(r)
                    instances.append(instance)
        SpectralLibrary.__refs__ = refs
        return instances

    sigProgressInfo = pyqtSignal(int, int, str)

    def __init__(self, name='SpectralLibrary', uri=None):

        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)

        if uri is None:
            # create a new, empty backend
            existing_vsi_files = vsiSpeclibs()
            assert isinstance(existing_vsi_files, list)
            i = 0
            uri = pathlib.PurePosixPath(VSI_DIR) / '{}.gpkg'.format(name)
            uri = uri.as_posix().replace('\\', '/')
            while uri in existing_vsi_files:
                i += 1
                uri = pathlib.PurePosixPath(VSI_DIR) / '{}{:03}.gpkg'.format(name, i)
                uri = uri.as_posix().replace('\\', '/')

            drv = ogr.GetDriverByName('GPKG')
            assert isinstance(drv, ogr.Driver)
            co = ['VERSION=AUTO']
            dsSrc = drv.CreateDataSource(uri, options=co)
            assert isinstance(dsSrc, ogr.DataSource)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(SPECLIB_EPSG_CODE)
            co = ['GEOMETRY_NAME=geom',
                  'GEOMETRY_NULLABLE=YES',
                  'FID=fid'
                  ]

            lyr = dsSrc.CreateLayer(name, srs=srs, geom_type=ogr.wkbPoint, options=co)

            assert isinstance(lyr, ogr.Layer)
            ldefn = lyr.GetLayerDefn()
            assert isinstance(ldefn, ogr.FeatureDefn)
            for f in ogrStandardFields():
                lyr.CreateField(f)
            dsSrc.FlushCache()
        else:
            dsSrc = ogr.Open(uri)
            assert isinstance(dsSrc, ogr.DataSource)
            names = [dsSrc.GetLayerByIndex(i).GetName() for i in range(dsSrc.GetLayerCount())]
            i = names.index(name)
            lyr = dsSrc.GetLayer(i)
            srs = lyr.GetSpatialRef()

        # consistency check
        uri2 = '{}|{}'.format(dsSrc.GetName(), lyr.GetName())
        uri3 = '{}|layername={}'.format(dsSrc.GetName(), lyr.GetName())
        assert QgsVectorLayer(uri2).isValid()
        super(SpectralLibrary, self).__init__(uri2, name, 'ogr', lyrOptions)
        if isinstance(srs, osr.SpatialReference) and not self.crs().isValid():
            crs = self.crs()
            crs.fromWkt(srs.ExportToWkt())
            self.setCrs(crs)
        SpectralLibrary.__refs__.append(weakref.ref(self))

        self.initTableConfig()
        self.initRenderer()

    def initRenderer(self):
        """
        Initializes the default QgsFeatureRenderer
        """
        color = speclibSettings().value('DEFAULT_PROFILE_COLOR', QColor('green'))
        self.renderer().symbol().setColor(color)


    def initTableConfig(self):
        """
        Initializes the QgsAttributeTableConfig and further options
        """
        mgr = self.actions()
        assert isinstance(mgr, QgsActionManager)
        mgr.clearActions()

        # actionSetStyle = createSetPlotStyleAction(self.fields().at(self.fields().lookupField(FIELD_STYLE)))
        # assert isinstance(actionSetStyle, QgsAction)
        # mgr.addAction(actionSetStyle)

        actionRemoveSpectrum = createRemoveFeatureAction()
        assert isinstance(actionRemoveSpectrum, QgsAction)
        mgr.addAction(actionRemoveSpectrum)

        columns = self.attributeTableConfig().columns()
        visibleColumns = ['name']
        for column in columns:
            assert isinstance(column, QgsAttributeTableConfig.ColumnConfig)

            column.hidden = column.name not in visibleColumns and column.type != QgsAttributeTableConfig.Action

        # set column order
        c_action = [c for c in columns if c.type == QgsAttributeTableConfig.Action][0]
        c_name = [c for c in columns if c.name == FIELD_NAME][0]
        firstCols = [c_action, c_name]
        columns = [c_action, c_name] + [c for c in columns if c not in firstCols]

        conf = QgsAttributeTableConfig()
        conf.setColumns(columns)
        conf.setActionWidgetVisible(False)
        conf.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)

        self.setAttributeTableConfig(conf)

        # set special default editors
        # self.setEditorWidgetSetup(self.fields().lookupField(FIELD_STYLE), QgsEditorWidgetSetup(PlotSettingsEditorWidgetKey, {}))

        self.setEditorWidgetSetup(self.fields().lookupField(FIELD_VALUES), QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))


    def mimeData(self, formats:list=None)->QMimeData:
        """
        Wraps this Speclib into a QMimeData object
        :return: QMimeData
        """
        if isinstance(formats, str):
            formats = [formats]
        elif formats is None:
            formats = [MIMEDATA_SPECLIB_LINK]

        mimeData = QMimeData()

        for format in formats:
            assert format in [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_TEXT, MIMEDATA_URL]
            if format == MIMEDATA_SPECLIB_LINK:
                global SPECLIB_CLIPBOARD
                thisID = id(self)
                SPECLIB_CLIPBOARD[thisID] = self

                mimeData.setData(MIMEDATA_SPECLIB_LINK, pickle.dumps(thisID))
            elif format == MIMEDATA_SPECLIB:
                mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(self))
            elif format == MIMEDATA_URL:
                mimeData.setUrls([QUrl(self.source())])
            elif format == MIMEDATA_TEXT:
                from ..speclib.csvdata import CSVSpectralLibraryIO
                txt = CSVSpectralLibraryIO.asString(self)
                mimeData.setText(txt)

        return mimeData

    def optionalFields(self)->list:
        """
        Returns the list of optional fields that are not part of the standard field set.
        :return: [list-of-QgsFields]
        """
        standardFields = createStandardFields()
        return [f for f in self.fields() if f not in standardFields]

    def optionalFieldNames(self)->list:
        """
        Returns the names of additions fields / attributes
        :return: [list-of-str]
        """
        requiredFields = [f.name for f  in ogrStandardFields()]
        return [n for n in self.fields().names() if n not in requiredFields]

    """
    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fieldNames():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])

        red = QgsConditionalStyle('﻿"__serialized__xvalues" is NULL OR "__serialized__yvalues is NULL" ')
        red.setBackgroundColor(QColor('red'))
        styles.setRowStyles([red])
    """

    def addMissingFields(self, fields:QgsFields):
        """Adds missing fields"""
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            i = self.fields().lookupField(field.name())
            if i == -1:
                missingFields.append(field)

        for f in missingFields:
            self.addAttribute(f)
            s = ""

        s = ""
        #if len(missingFields) > 0:
        #    self.dataProvider().addAttributes(missingFields)


    def addSpeclib(self, speclib, addMissingFields=True, progressDialog:QProgressDialog=None):
        """
        Adds another SpectraLibrary
        :param speclib: SpectralLibrary
        :param addMissingFields: if True, add missing field
        """
        assert isinstance(speclib, SpectralLibrary)

        self.addProfiles(speclib, addMissingFields=addMissingFields, progressDialog=progressDialog)
        s = ""

    def addProfiles(self, profiles:typing.Union[typing.List[SpectralProfile], QgsVectorLayer],
                    addMissingFields:bool=None,
                    progressDialog:QProgressDialog=None):

        if isinstance(profiles, SpectralProfile):
            profiles = [profiles]

        if addMissingFields is None:
            addMissingFields = isinstance(profiles, SpectralLibrary)

        if len(profiles) == 0:
            return

        assert self.isEditable(), 'SpectralLibrary "{}" is not editable. call startEditing() first'.format(self.name())

        if isinstance(progressDialog, QProgressDialog):
            progressDialog.setLabelText('Add {} profiles'.format(len(profiles)))
            progressDialog.setValue(0)
            progressDialog.setRange(0, len(profiles))

        iSrcList = []
        iDstList = []

        bufferLength = 500
        profileBuffer = []

        nAdded = 0

        def flushBuffer():
            nonlocal self, nAdded, profileBuffer, progressDialog
            if not self.addFeatures(profileBuffer):
                self.raiseError()
            nAdded += len(profileBuffer)
            #print('added {}'.format(len(profileBuffer)))
            profileBuffer.clear()

            if isinstance(progressDialog, QProgressDialog):
                progressDialog.setValue(nAdded)

                QApplication.processEvents()



        for i, pSrc in enumerate(profiles):
            #print(i)
            if i == 0:
                if addMissingFields:
                    self.addMissingFields(pSrc.fields())

                for iSrc, srcName in enumerate(pSrc.fields().names()):
                    if srcName == FIELD_FID:
                        continue
                    iDst = self.fields().lookupField(srcName)
                    if iDst >= 0:
                        iSrcList.append(iSrc)
                        iDstList.append(iDst)
                    elif addMissingFields:
                        raise Exception('Missing field: "{}"'.format(srcName))

            # create new feature + copy geometry
            pDst = QgsFeature(self.fields())
            pDst.setGeometry(pSrc.geometry())

            # copy attributes
            for iSrc, iDst in zip(iSrcList, iDstList):
                pDst.setAttribute(iDst, pSrc.attribute(iSrc))

            profileBuffer.append(pDst)

            if len(profileBuffer) >= bufferLength:
                flushBuffer()


        flushBuffer()

        #s = ""

    def speclibFromFeatureIDs(self, fids):
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)

        profiles = list(self.profiles(fids))

        speclib = SpectralLibrary()
        speclib.startEditing()
        speclib.addMissingFields(self.fields())
        speclib.addProfiles(profiles)
        speclib.commitChanges()
        return speclib

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        if not isinstance(profiles, list):
            profiles = [profiles]

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        fids = [p.id() for p in profiles]
        if len(fids) == 0:
            return

        assert self.isEditable()
        self.deleteFeatures(fids)


    def features(self, fids=None)->QgsFeatureIterator:
        """
        Returns the QgsFeatures stored in this QgsVectorLayer
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: QgsFeatureIterator
        """
        featureRequest = QgsFeatureRequest()
        if fids is not None:
            if isinstance(fids, int):
                fids = [fids]
            if not isinstance(fids, list):
                fids = list(fids)
            for fid in fids:
                assert isinstance(fid, int)
            featureRequest.setFilterFids(fids)
        # features = [f for f in self.features() if f.id() in fidsToRemove]
        return self.getFeatures(featureRequest)


    def profiles(self, fids=None)->typing.Generator[SpectralProfile, None, None]:
        """
        Like features(fidsToRemove=None), but converts each returned QgsFeature into a SpectralProfile
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: generator of [List-of-SpectralProfiles]
        """
        for f in self.features(fids=fids):
            yield SpectralProfile.fromSpecLibFeature(f)




    def groupBySpectralProperties(self, excludeEmptyProfiles=True):
        """
        Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

            xValues: None | [list-of-xvalues with n>0 elements]
            xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
            yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

        :return: {(xValues, xUnit, yUnit):[list-of-profiles]}
        """

        results = dict()
        for p in self.profiles():
            assert isinstance(p, SpectralProfile)

            d = p.values()

            if excludeEmptyProfiles:
                if not isinstance(d['y'], list):
                    continue
                if not len(d['y']) > 0:
                    continue

            x = tuple(p.xValues())
            if len(x) == 0:
                x = None
            #y = None if d['y'] in [None, []] else tuple(d['y'])

            xUnit = None if d['xUnit'] in [None, ''] else d['xUnit']
            yUnit = None if d['yUnit'] in [None, ''] else d['yUnit']

            key = (x, xUnit, yUnit)

            if key not in results.keys():
                results[key] = []
            results[key].append(p)
        return results

    def exportProfiles(self, path:str, **kwds)->list:
        """
        Exports profiles to a file. This wrapper tries to identify the required SpectralLibraryIO from the file-path suffix.
        in `path`.
        :param path: str, filepath
        :param kwds: keywords to be used in specific `AbstractSpectralLibraryIO.write(...)` methods.
        :return: list of written files
        """

        if path is None:
            path, filter = QFileDialog.getSaveFileName(parent=kwds.get('parent'), caption='Save Spectral Library', directory= 'speclib', filter=FILTERS)

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            if ext in ['.sli', '.esl']:
                from .envi import EnviSpectralLibraryIO
                return EnviSpectralLibraryIO.write(self, path)

            if ext in ['.csv']:
                from .csvdata import CSVSpectralLibraryIO
                from csv import excel_tab
                return CSVSpectralLibraryIO.write(self, path, dialect=kwds.get('dialect', excel_tab))

        return []


    def yRange(self):
        profiles = self.profiles()
        minY = min([min(p.yValues()) for p in profiles])
        maxY = max([max(p.yValues()) for p in profiles])
        return minY, maxY

    def __repr__(self):
        return str(self.__class__) + '"{}" {} feature(s)'.format(self.name(), self.dataProvider().featureCount())

    def plot(self):
        """Create a plot widget and shows all SpectralProfile in this SpectralLibrary."""
        pg.mkQApp()

        win = pg.GraphicsWindow(title="Spectral Library")
        win.resize(1000, 600)

        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        # Create a plot with some random data
        p1 = win.addPlot(title="Spectral Library {}".format(self.name()), pen=0.5)
        yMin, yMax = self.yRange()
        p1.setYRange(yMin, yMax)

        # Add three infinite lines with labels
        for p in self:
            pi = pg.PlotDataItem(p.xValues(), p.yValues())
            p1.addItem(pi)

        pg.QAPP.exec_()

    def fieldNames(self)->list:
        """
        Retunrs the field names. Shortcut from self.fields().names()
        :return: [list-of-str]
        """
        return self.fields().names()

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        """
        Pickles a SpectralLibrary
        :return: pickle dump
        """

        fields = qgsFields2str(self.fields())
        data = []
        for feature in self.features():
            data.append((feature.geometry().asWkt(),
                         qgsFieldAttributes2List(feature.attributes())
                        ))


        dump = pickle.dumps((self.name(),fields, data))
        return dump
        #return self.__dict__.copy()

    def __setstate__(self, state):
        """
        Restores a pickled SpectralLibrary
        :param state:
        :return:
        """
        name, fields, data = pickle.loads(state)
        self.setName(name)
        fieldNames = self.fieldNames()
        dataFields = str2QgsFields(fields)
        fieldsToAdd = [f for f in dataFields if f.name() not in fieldNames]
        self.startEditing()
        if len(fieldsToAdd) > 0:

            for field in fieldsToAdd:
                assert isinstance(field, QgsField)
                self.fields().append(field)
            self.commitChanges()
            self.startEditing()

        fieldNames = self.fieldNames()
        order = [fieldNames.index(f.name()) for f in dataFields]
        reoder = list(range(len(dataFields))) != order

        features = []
        nextFID = self.allFeatureIds()
        nextFID = max(nextFID) if len(nextFID) else 0

        for i, datum in enumerate(data):
            nextFID += 1
            wkt, attributes = datum
            feature = QgsFeature(self.fields(), nextFID)
            if reoder:
                attributes = [attributes[i] for i in order]
            feature.setAttributes(attributes)
            feature.setAttribute(FIELD_FID, nextFID)
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feature)
        self.addFeatures(features)
        self.commitChanges()


    def __len__(self)->int:
        cnt = self.featureCount()
        # can be -1 if the number of features is unknown
        return max(cnt, 0)

    def __iter__(self):
        r = QgsFeatureRequest()
        for f in self.getFeatures(r):
            yield SpectralProfile.fromSpecLibFeature(f)

    def __getitem__(self, slice):
        fids = sorted(self.allFeatureIds())[slice]

        if isinstance(fids, list):
            return sorted(self.profiles(fids=fids), key=lambda p:p.id())
        else:
            return SpectralProfile.fromSpecLibFeature(self.getFeature(fids))

    def __delitem__(self, slice):
        profiles = self[slice]
        self.removeProfiles(profiles)

    def __eq__(self, other):
        if not isinstance(other, SpectralLibrary):
            return False

        if len(self) != len(other):
            return False

        for p1, p2 in zip(self.__iter__(), other.__iter__()):
            if not p1 == p2:
                return False
        return True

    def __hash__(self):
        return super(SpectralLibrary, self).__hash__()




class AbstractSpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    @staticmethod
    def canRead(path:str)->bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        return False

    @staticmethod
    def readFrom(path:str, progressDialog:QProgressDialog=None)->SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of Spectral Library
        :param progressDialog: QProgressDialog, which well-behave implementations can use to show the import progress.
        :return: SpectralLibrary
        """
        return None

    @staticmethod
    def write(speclib:SpectralLibrary, path:str, progressDialog:QProgressDialog)->typing.List[str]:
        """
        Writes the SpectralLibrary.
        :param speclib: SpectralLibrary to write
        :param path: file path to write the SpectralLibrary to
        :param progressDialog:  QProgressDialog, which well-behave implementations can use to show the writting progress.
        :return: a list of paths that can be used to re-open all written profiles
        """
        assert isinstance(speclib, SpectralLibrary)
        return []

    @staticmethod
    def score(uri:str)->int:
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probably that's the file format
        the reader can read.

        :param uri: str
        :return: int
        """
        return 0

    @staticmethod
    def filterString()->str:
        """
        Returns a Qt file filter string
        :return:
        :rtype:
        """

        return None

    @staticmethod
    def addImportActions(spectralLibrary:SpectralLibrary, menu:QMenu):
        """
        Returns a list of QActions or QMenus that can be called to read/import SpectralProfiles from a certain file format into a SpectralLibrary
        :param spectralLibrary: SpectralLibrary to import SpectralProfiles to
        :return: [list-of-QAction-or-QMenus]
        """

    @staticmethod
    def addExportActions(spectralLibrary:SpectralLibrary, menu:QMenu):
        """
        Returns a list of QActions or QMenus that can be called to write/export SpectralProfiles into certain file format
        :param spectralLibrary: SpectralLibrary to export SpectralProfiles from
        :return: [list-of-QAction-or-QMenus]
        """


class AddAttributeDialog(QDialog):
    """
    A dialog to set up a new QgsField.
    """
    def __init__(self, layer, parent=None):
        assert isinstance(layer, QgsVectorLayer)
        super(AddAttributeDialog, self).__init__(parent)

        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer

        self.setWindowTitle('Add Field')
        l = QGridLayout()

        self.tbName = QLineEdit('Name')
        self.tbName.setPlaceholderText('Name')
        self.tbName.textChanged.connect(self.validate)

        l.addWidget(QLabel('Name'), 0,0)
        l.addWidget(self.tbName, 0, 1)

        self.tbComment = QLineEdit()
        self.tbComment.setPlaceholderText('Comment')
        l.addWidget(QLabel('Comment'), 1, 0)
        l.addWidget(self.tbComment, 1, 1)

        self.cbType = QComboBox()
        self.typeModel = OptionListModel()

        for ntype in self.mLayer.dataProvider().nativeTypes():
            assert isinstance(ntype, QgsVectorDataProvider.NativeType)
            o = Option(ntype, name=ntype.mTypeName, toolTip=ntype.mTypeDesc)
            self.typeModel.addOption(o)
        self.cbType.setModel(self.typeModel)
        self.cbType.currentIndexChanged.connect(self.onTypeChanged)
        l.addWidget(QLabel('Type'), 2, 0)
        l.addWidget(self.cbType, 2, 1)

        self.sbLength = QSpinBox()
        self.sbLength.setRange(0, 99)
        self.sbLength.valueChanged.connect(lambda : self.setPrecisionMinMax())
        self.lengthLabel = QLabel('Length')
        l.addWidget(self.lengthLabel, 3, 0)
        l.addWidget(self.sbLength, 3, 1)

        self.sbPrecision = QSpinBox()
        self.sbPrecision.setRange(0, 99)
        self.precisionLabel = QLabel('Precision')
        l.addWidget(self.precisionLabel, 4, 0)
        l.addWidget(self.sbPrecision, 4, 1)

        self.tbValidationInfo = QLabel()
        self.tbValidationInfo.setStyleSheet("QLabel { color : red}")
        l.addWidget(self.tbValidationInfo, 5, 0, 1, 2)


        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttons.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        l.addWidget(self.buttons, 6, 1)
        self.setLayout(l)

        self.mLayer = layer

        self.onTypeChanged()

    def accept(self):

        msg = self.validate()

        if len(msg) > 0:
            QMessageBox.warning(self, "Add Field", msg)
        else:
            super(AddAttributeDialog, self).accept()

    def field(self):
        """
        Returns the new QgsField
        :return:
        """
        ntype = self.currentNativeType()
        return QgsField(name=self.tbName.text(),
                        type=QVariant(ntype.mType).type(),
                        typeName=ntype.mTypeName,
                        len=self.sbLength.value(),
                        prec=self.sbPrecision.value(),
                        comment=self.tbComment.text())




    def currentNativeType(self):
        return self.cbType.currentData().value()

    def onTypeChanged(self, *args):
        ntype = self.currentNativeType()
        vMin , vMax = ntype.mMinLen, ntype.mMaxLen
        assert isinstance(ntype, QgsVectorDataProvider.NativeType)

        isVisible = vMin < vMax
        self.sbLength.setVisible(isVisible)
        self.lengthLabel.setVisible(isVisible)
        self.setSpinBoxMinMax(self.sbLength, vMin , vMax)
        self.setPrecisionMinMax()

    def setPrecisionMinMax(self):
        ntype = self.currentNativeType()
        vMin, vMax = ntype.mMinPrec, ntype.mMaxPrec
        isVisible = vMin < vMax
        self.sbPrecision.setVisible(isVisible)
        self.precisionLabel.setVisible(isVisible)

        vMax = max(ntype.mMinPrec, min(ntype.mMaxPrec, self.sbLength.value()))
        self.setSpinBoxMinMax(self.sbPrecision, vMin, vMax)

    def setSpinBoxMinMax(self, sb, vMin, vMax):
        assert isinstance(sb, QSpinBox)
        value = sb.value()
        sb.setRange(vMin, vMax)

        if value > vMax:
            sb.setValue(vMax)
        elif value < vMin:
            sb.setValue(vMin)


    def validate(self):

        msg = []
        name = self.tbName.text()
        if name in self.mLayer.fields().names():
            msg.append('Field name "{}" already exists.'.format(name))
        elif name == '':
            msg.append('Missing field name')
        elif name == 'shape':
            msg.append('Field name "{}" already reserved.'.format(name))

        msg = '\n'.join(msg)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(len(msg) == 0)

        self.tbValidationInfo.setText(msg)

        return msg



"""
class SpectralProfileMapTool(QgsMapToolEmitPoint):

    sigProfileRequest = pyqtSignal(SpatialPoint, QgsMapCanvas)

    def __init__(self, canvas, showCrosshair=True):
        self.mShowCrosshair = showCrosshair
        self.mCanvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.mCanvas)
        self.marker = QgsVertexMarker(self.mCanvas)
        self.rubberband = QgsRubberBand(self.mCanvas, QgsWkbTypes.PolygonGeometry)

        plotStyle = QColor('red')

        self.rubberband.setLineStyle(Qt.SolidLine)
        self.rubberband.setColor(plotStyle)
        self.rubberband.setWidth(2)

        self.marker.setColor(plotStyle)
        self.marker.setPenWidth(3)
        self.marker.setIconSize(5)
        self.marker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X

    def canvasPressEvent(self, e):
        geoPoint = self.toMapCoordinates(e.pos())
        self.marker.setCenter(geoPoint)
        #self.marker.show()

    def setStyle(self, plotStyle=None, brushStyle=None, fillColor=None, lineStyle=None):
        if plotStyle:
            self.rubberband.setColor(plotStyle)
        if brushStyle:
            self.rubberband.setBrushStyle(brushStyle)
        if fillColor:
            self.rubberband.setFillColor(fillColor)
        if lineStyle:
            self.rubberband.setLineStyle(lineStyle)

    def canvasReleaseEvent(self, e):

        pixelPoint = e.pixelPoint()

        crs = self.mCanvas.mapSettings().destinationCrs()
        self.marker.hide()
        geoPoint = self.toMapCoordinates(pixelPoint)
        if self.mShowCrosshair:
            #show a temporary crosshair
            ext = SpatialExtent.fromMapCanvas(self.mCanvas)
            cen = geoPoint
            geom = QgsGeometry()
            geom.addPart([QgsPointXY(ext.upperLeftPt().x(),cen.y()), QgsPointXY(ext.lowerRightPt().x(), cen.y())],
                          Qgis.Line)
            geom.addPart([QgsPointXY(cen.x(), ext.upperLeftPt().y()), QgsPointXY(cen.x(), ext.lowerRightPt().y())],
                          Qgis.Line)
            self.rubberband.addGeometry(geom, None)
            self.rubberband.show()
            #remove crosshair after 0.1 sec
            QTimer.singleShot(100, self.hideRubberband)

        self.sigProfileRequest.emit(SpatialPoint(crs, geoPoint), self.mCanvas)

    def hideRubberband(self):
        self.rubberband.reset()

"""




class SpectralProfileValueTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """
    def __init__(self, parent=None):
        super(SpectralProfileValueTableModel, self).__init__(parent)

        self.mColumnDataTypes = [float, float]
        self.mColumnDataUnits = ['-', '-']
        self.mValues = EMPTY_PROFILE_VALUES.copy()



    def setProfileData(self, values):
        """
        :param values:
        :return:
        """
        if isinstance(values, SpectralProfile):
            values = values.values()
        assert isinstance(values, dict)

        for k in EMPTY_PROFILE_VALUES.keys():
            assert k in values.keys()

        for i, k in enumerate(['y', 'x']):
            if values[k] and len(values[k]) > 0:
                self.setColumnDataType(i, type(values[k][0]))
            else:
                self.setColumnDataType(i, float)
        self.setColumnValueUnit('y', values.get('yUnit', '') )
        self.setColumnValueUnit('x', values.get('xUnit', ''))

        self.beginResetModel()
        self.mValues.update(values)
        self.endResetModel()

    def values(self)->dict:
        """
        Returns the value dictionary of a SpectralProfile
        :return: dict
        """
        return self.mValues

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        if self.mValues['x'] is None:
            return 0
        else:
            return len(self.mValues['x'])

    def columnCount(self, parent=QModelIndex()):
        return 2

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role in [Qt.DisplayRole, Qt.EditRole]:
            value = None
            if c == 0:
                value = self.mValues['y'][i]

            elif c == 1:
                value = self.mValues['x'][i]

            #log('data: {} {}'.format(type(value), value))
            return value

        if role == Qt.UserRole:
            return self.mValues

        return None

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role == Qt.EditRole:
            #cast to correct data type
            dt = self.mColumnDataTypes[c]
            value = dt(value)

            if c == 0:
                self.mValues['y'][i] = value
                return True
            elif c == 1:
                self.mValues['x'][i] = value
                return True
        return False

    def index2column(self, index)->int:
        """
        Returns a column index
        :param index: QModelIndex, int or str from  ['x','y']
        :return: int
        """
        if isinstance(index, str):
            index = ['y','x'].index(index.strip().lower())
        elif isinstance(index, QModelIndex):
            index = index.column()

        assert isinstance(index, int) and index >= 0
        return index


    def setColumnValueUnit(self, index, valueUnit:str):
        """
        Sets the unit of the value column
        :param index: 'y','x', respective 0, 1
        :param valueUnit: str with unit, e.g. 'Reflectance' or 'um'
        """
        index = self.index2column(index)
        if valueUnit is None:
            valueUnit = '-'

        assert isinstance(valueUnit, str)

        if self.mColumnDataUnits[index] != valueUnit:
            self.mColumnDataUnits[index] = valueUnit
            self.headerDataChanged.emit(Qt.Horizontal, index, index)
            self.sigColumnValueUnitChanged.emit(index, valueUnit)

    sigColumnValueUnitChanged = pyqtSignal(int, str)

    def setColumnDataType(self, index, dataType:type):
        """
        Sets the numeric dataType in which spectral values are returned
        :param index: 'y','x', respective 0, 1
        :param dataType: int or float (default)
        """
        index = self.index2column(index)
        if isinstance(dataType, str):
            i = ['Integer', 'Float'].index(dataType)
            dataType = [int, float][i]

        assert dataType in [int, float]

        if self.mColumnDataTypes[index] != dataType:
            self.mColumnDataTypes[index] = dataType

            if index == 0:
                y = self.mValues.get('y')
                if isinstance(y, list) and len(y) > 0:
                    self.mValues['y'] = [dataType(v) for v  in self.mValues['y']]
            elif index == 1:
                x = self.mValues.get('x')
                if isinstance(x, list) and len(x) > 0:
                    self.mValues['x'] = [dataType(v) for v in self.mValues['x']]

            self.dataChanged.emit(self.createIndex(0, index), self.createIndex(self.rowCount(), index))
            self.sigColumnDataTypeChanged.emit(index, dataType)

    sigColumnDataTypeChanged = pyqtSignal(int, type)

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            if c == 0:
                flags = flags | Qt.ItemIsEditable
            elif c == 1 and self.mValues['xUnit']:
                flags = flags | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            name = ['Y','X'][col]
            unit = self.mColumnDataUnits[col]
            if unit in EMPTY_VALUES:
                unit = '-'
            return '{} [{}]'.format(name, unit)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

class SpectralProfileEditorWidget(QWidget, loadSpeclibUI('spectralprofileeditorwidget.ui')):

    sigProfileValuesChanged = pyqtSignal(dict)
    def __init__(self, parent=None):
        super(SpectralProfileEditorWidget, self).__init__(parent)
        self.setupUi(self)

        self.mDefault = None
        self.mModel = SpectralProfileValueTableModel(parent=self)
        self.mModel.dataChanged.connect(lambda :self.sigProfileValuesChanged.emit(self.profileValues()))
        self.mModel.sigColumnValueUnitChanged.connect(self.onValueUnitChanged)
        self.mModel.sigColumnDataTypeChanged.connect(self.onDataTypeChanged)

        self.cbYUnit.currentTextChanged.connect(lambda unit: self.mModel.setColumnValueUnit(0, unit))
        self.cbXUnit.currentTextChanged.connect(lambda unit: self.mModel.setColumnValueUnit(1, unit))

        self.cbYUnitDataType.currentTextChanged.connect(lambda v: self.mModel.setColumnDataType(0, v))
        self.cbXUnitDataType.currentTextChanged.connect(lambda v:self.mModel.setColumnDataType(1, v))

        self.actionReset.triggered.connect(self.resetProfileValues)
        self.btnReset.setDefaultAction(self.actionReset)

        self.onDataTypeChanged(0, float)
        self.onDataTypeChanged(1, float)

        self.setProfileValues(EMPTY_PROFILE_VALUES.copy())

    def initConfig(self, conf:dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        if 'xUnitList' in conf.keys():
            self.cbXUnit.addItems(conf['xUnitList'])

        if 'yUnitList' in conf.keys():
            self.cbYUnit.addItems(conf['yUnitList'])


    def onValueUnitChanged(self, index:int, unit:str):
        comboBox = [self.cbYUnit, self.cbXUnit][index]
        setComboboxValue(comboBox, unit)

    def onDataTypeChanged(self, index:int, dataType:type):

        if dataType == int:
            typeString = 'Integer'
        elif dataType == float:
            typeString = 'Float'
        else:
            raise NotImplementedError()
        comboBox = [self.cbYUnitDataType, self.cbXUnitDataType][index]

        setComboboxValue(comboBox, typeString)

    def setProfileValues(self, values):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """

        if isinstance(values, SpectralProfile):
            values = values.values()

        assert isinstance(values, dict)
        import copy
        self.mDefault = copy.deepcopy(values)
        self.mModel.setProfileData(values)


    def resetProfileValues(self):
        self.setProfileValues(self.mDefault)

    def profileValues(self)->dict:
        """
        Returns the value dictionary of a SpectralProfile
        :return: dict
        """
        return self.mModel.values()


def deleteSelected(layer):

    assert isinstance(layer, QgsVectorLayer)
    b = layer.isEditable()

    layer.startEditing()
    layer.beginEditCommand('Delete selected features')
    layer.deleteSelectedFeatures()
    layer.endEditCommand()

    if not b:
        layer.commitChanges()

    #saveEdits(layer, leaveEditable=b)


class UnitComboBoxItemModel(OptionListModel):
    def __init__(self, parent=None):
        super(UnitComboBoxItemModel, self).__init__(parent)

    def addUnit(self, unit):

        o = Option(unit, unit)
        self.addOption(o)


    def getUnitFromIndex(self, index):
        o = self.idx2option(index)
        assert isinstance(o, Option)
        return o.mValue

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mUnits)) or (index.row() < 0):
            return None
        unit = self.getUnitFromIndex(index)
        value = None
        if role == Qt.DisplayRole:
            value = '{}'.format(unit)
        return value



class SpectralProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget):
        super(SpectralProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mEditorWidget = None
        self.mLabel = None
        self.mDefaultValue = None

    def createWidget(self, parent: QWidget):
        #log('createWidget')
        w = None
        if not self.isInTable(parent):
            w = SpectralProfileEditorWidget(parent=parent)
        else:
            #w = PlotStyleButton(parent)
            w = QWidget(parent)
            w.setVisible(False)
        return w

    def initWidget(self, editor:QWidget):
        #log(' initWidget')
        conf = self.config()


        if isinstance(editor, SpectralProfileEditorWidget):
            self.mEditorWidget = editor
            self.mEditorWidget.sigProfileValuesChanged.connect(self.onValueChanged)
            self.mEditorWidget.initConfig(conf)

        if isinstance(editor, QWidget):
            self.mLabel = editor
            self.mLabel.setVisible(False)
            self.mLabel.setToolTip('Use Form View to edit values')


    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs)->bool:
        return isinstance(self.mEditorWidget, SpectralProfileEditorWidget) or isinstance(self.mLabel, QWidget)

    def value(self, *args, **kwargs):
        value = self.mDefaultValue
        if isinstance(self.mEditorWidget, SpectralProfileEditorWidget):
            v = self.mEditorWidget.profileValues()
            value = encodeProfileValueDict(v)

        return value


    def setEnabled(self, enabled:bool):

        if self.mEditorWidget:
            self.mEditorWidget.setEnabled(enabled)


    def setValue(self, value):
        if isinstance(self.mEditorWidget, SpectralProfileEditorWidget):
            self.mEditorWidget.setProfileValues(decodeProfileValueDict(value))
        self.mDefaultValue = value
        #if isinstance(self.mLabel, QLabel):
        #    self.mLabel.setText(value2str(value))

class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget, loadSpeclibUI('spectralprofileeditorconfigwidget.ui')):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, parent:QWidget):

        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        self.setupUi(self)

        self.mLastConfig = {}

        self.tbXUnits.textChanged.connect(lambda: self.changed.emit())
        self.tbYUnits.textChanged.connect(lambda: self.changed.emit())

        self.tbResetX.setDefaultAction(self.actionResetX)
        self.tbResetY.setDefaultAction(self.actionResetY)

    def unitTextBox(self, dim:str)->QPlainTextEdit:
        if dim == 'x':
            return self.tbXUnits
        elif dim == 'y':
            return self.tbYUnits
        else:
            raise NotImplementedError()

    def units(self, dim:str)->list:
        textEdit = self.unitTextBox(dim)
        assert isinstance(textEdit, QPlainTextEdit)
        values = []
        for line in textEdit.toPlainText().splitlines():
            v = line.strip()
            if len(v) > 0  and v not in values:
                values.append(v)
        return values


    def setUnits(self, dim:str, values:list):
        textEdit = self.unitTextBox(dim)
        assert isinstance(textEdit, QPlainTextEdit)
        textEdit.setPlainText('\n'.join(values))

    def config(self, *args, **kwargs)->dict:
        config = {'xUnitList':self.units('x'),
                  'yUnitList':self.units('y')
                  }
        return config

    def setConfig(self, config:dict):
        if 'xUnitList' in config.keys():
            self.setUnits('x', config['xUnitList'])

        if 'yUnitList' in config.keys():
            self.setUnits('y', config['yUnitList'])

        self.mLastConfig = config
        #print('setConfig')

    def resetUnits(self, dim: str):

        if dim == 'x' and 'xUnitList' in self.mLastConfig.keys():
            self.setUnit('x', self.mLastConfig['xUnitList'])

        if dim == 'y' and 'yUnitList' in self.mLastConfig.keys():
            self.setUnit('y', self.mLastConfig['yUnitList'])



class SpectralProfileEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name:str):

        super(SpectralProfileEditorWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer:QgsVectorLayer, fieldIdx:int, parent=QWidget)->SpectralProfileEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = SpectralProfileEditorConfigWidget(layer, fieldIdx, parent)
        key = self.configKey(layer, fieldIdx)
        w.setConfig(self.readConfig(key))
        w.changed.connect(lambda : self.writeConfig(key, w.config()))
        return w

    def configKey(self, layer:QgsVectorLayer, fieldIdx:int):
        """
        Returns a tuple to be used as dictionary key to identify a layer field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return (layer.id(), fieldIdx)

    def create(self, layer:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget)->SpectralProfileEditorWidgetWrapper:
        """
        Create a SpectralProfileEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: SpectralProfileEditorWidgetWrapper
        """
        w = SpectralProfileEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        return w

    def writeConfig(self, key:tuple, config:dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config
        #print('Save config')
        #print(config)

    def readConfig(self, key:tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        if key in self.mConfigurations.keys():
            conf = self.mConfigurations[key]
        else:
            #return the very default configuration
            conf = {'xUnitList' : X_UNITS[:],
                    'yUnitList' : Y_UNITS[:]
            }
        #print('Read config')
        #print((key, conf))
        return conf

    def fieldScore(self, vl:QgsVectorLayer, fieldIdx:int)->int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        #log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() == QVariant.String and field.name() == FIELD_VALUES:
            return 20
        elif field.type() == QVariant.String:
            return 0
        else:
            return 0



EDITOR_WIDGET_REGISTRY_KEY = 'Spectral Profile'

def registerSpectralProfileEditorWidget():
    reg = QgsGui.editorWidgetRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        global SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
        SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)


from ..utils import SelectMapLayersDialog
class SpectralProfileImportPointsDialog(SelectMapLayersDialog):

    def __init__(self, parent=None, f:Qt.WindowFlags=None):
        super(SpectralProfileImportPointsDialog, self).__init__()
        #self.setupUi(self)
        self.setWindowTitle('Read Spectral Profiles')
        self.addLayerDescription('Raster Layer', QgsMapLayerProxyModel.RasterLayer)
        cb = self.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        cb.layerChanged.connect(self.onVectorLayerChanged)
        self.mSpeclib = None


        self.mCbTouched = QCheckBox(self)
        self.mCbTouched.setText('All touched')
        self.mCbTouched.setToolTip('Activate to extract all touched pixels, not only thoose entirel covered by a geometry.')
        i = self.mGrid.rowCount()
        self.mGrid.addWidget(self.mCbTouched, i, 1)

        self.buttonBox().button(QDialogButtonBox.Ok).clicked.disconnect(self.accept)
        self.buttonBox().button(QDialogButtonBox.Ok).clicked.connect(self.run)
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        self.onVectorLayerChanged(cb.currentLayer())

    def onVectorLayerChanged(self, layer:QgsVectorLayer):
        self.mCbTouched.setEnabled(isinstance(layer, QgsVectorLayer) and
                                   QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry)

    def speclib(self)->SpectralLibrary:
        return self.mSpeclib

    def setRasterSource(self, lyr):
        if isinstance(lyr, str):
            lyr = QgsRasterLayer(lyr)
        assert isinstance(lyr, QgsRasterLayer)
        self.selectMapLayer(0, lyr)

    def setVectorSource(self, lyr):

        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr)
        assert isinstance(lyr, QgsVectorLayer)
        self.selectMapLayer(1, lyr)

    def run(self):
        progressDialog = QProgressDialog()
        progressDialog.setWindowModality(Qt.WindowModal)
        progressDialog.setMinimumDuration(0)

        slib = SpectralLibrary.readFromVector(self.vectorSource(),
                                              self.rasterSource(),
                                              all_touched=self.allTouched(),
                                              progressDialog=progressDialog)

        #slib = SpectralLibrary.readFromVectorPositions(self.rasterSource(), self.vectorSource(), progressDialog=progressDialog)

        if isinstance(slib, SpectralLibrary) and not progressDialog.wasCanceled():
            self.mSpeclib = slib
            self.accept()
        else:
            self.mSpeclib = None
            self.reject()

    def allTouched(self)->bool:
        return self.mCbTouched.isEnabled() and self.mCbTouched.isChecked()

    def rasterSource(self)->QgsVectorLayer:
        return self.mapLayers()[0]


    def vectorSource(self)->QgsVectorLayer:
        return self.mapLayers()[1]



class SpectralLibraryWidget(QMainWindow, loadSpeclibUI('spectrallibrarywidget.ui')):

    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)


    class CurrentProfilesMode(enum.Enum):
        normal = 0
        automatically = 1
        block = 2

    def __init__(self, *args, speclib:SpectralLibrary=None, mapCanvas=QgsMapCanvas, **kwds):
        """
        Constructor
        :param args: QMainWindow arguments
        :param speclib: SpectralLibrary, defaults: None
        :param mapCanvas: QgsMapCanvas, default: None
        :param kwds: QMainWindow keywords
        """

        super(SpectralLibraryWidget, self).__init__(*args, **kwds)
        self.setupUi(self)

        # self.statusbar.setVisible(False)

        # set spacer into menu
        # empty = QWidget(self.mToolbar)
         #empty.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        from ..speclib.plotting import SpectralLibraryPlotWidget
        assert isinstance(self.mPlotWidget, SpectralLibraryPlotWidget)

        self.m_plot_max = 500

        from .envi import EnviSpectralLibraryIO
        from .csvdata import CSVSpectralLibraryIO
        from .asd import ASDSpectralLibraryIO
        from .ecosis import EcoSISSpectralLibraryIO
        from .specchio import SPECCHIOSpectralLibraryIO
        from .artmo import ARTMOSpectralLibraryIO
        from .vectorsources import VectorSourceSpectralLibraryIO

        self.mSpeclibIOInterfaces = [
            EnviSpectralLibraryIO(),
            CSVSpectralLibraryIO(),
            ARTMOSpectralLibraryIO(),
            ASDSpectralLibraryIO(),
            EcoSISSpectralLibraryIO(),
            SPECCHIOSpectralLibraryIO(),
            VectorSourceSpectralLibraryIO(),
        ]

        self.mSpeclibIOInterfaces = sorted(self.mSpeclibIOInterfaces, key=lambda c: c.__class__.__name__)


        self.mSelectionModel = None

        if not isinstance(speclib, SpectralLibrary):
            speclib = SpectralLibrary()

        assert isinstance(speclib, SpectralLibrary)
        self.mSpeclib = speclib

        QPS_MAPLAYER_STORE.addMapLayer(speclib)

        self.mSpeclib.editingStarted.connect(self.onIsEditableChanged)
        self.mSpeclib.editingStopped.connect(self.onIsEditableChanged)
        self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
        self.mSpeclib.nameChanged.connect(lambda *args, sl=self.mSpeclib: self.setWindowTitle(sl.name()))

        if isinstance(mapCanvas, QgsMapCanvas):
            self.mCanvas = mapCanvas
        else:
            self.mCanvas = QgsMapCanvas(self.centralwidget)
            self.mCanvas.setVisible(False)
            self.mCanvas.setDestinationCrs(self.mSpeclib.crs())
            self.mSpeclib.crsChanged.connect(lambda *args : self.mCanvas.setDestinationCrs(self.mSpeclib.crs()))

        self.mSourceFilter = '*'

        assert isinstance(self.mDualView, QgsDualView)
        self.mDualView.init(self.mSpeclib, self.mCanvas)
        self.mDualView.setView(QgsDualView.AttributeTable)
        self.mDualView.setAttributeTableConfig(self.mSpeclib.attributeTableConfig())
        self.mDualView.showContextMenuExternally.connect(self.onShowContextMenuExternally)
        self.mDualView.tableView().willShowContextMenu.connect(self.onWillShowContextMenu)
        from .plotting import SpectralLibraryPlotWidget
        assert isinstance(self.mPlotWidget, SpectralLibraryPlotWidget)
        self.mPlotWidget.setDualView(self.mDualView)
        self.mPlotWidget.mUpdateTimer.timeout.connect(self.updateStatusBar)

        # change selected row plotStyle: keep plotStyle also when the attribute table looses focus

        pal = self.mDualView.tableView().palette()
        cSelected = pal.color(QPalette.Active, QPalette.Highlight)
        pal.setColor(QPalette.Inactive, QPalette.Highlight, cSelected)
        self.mDualView.tableView().setPalette(pal)

        self.splitter.setSizes([800, 300])

        self.mPlotWidget.setAcceptDrops(True)
        self.mPlotWidget.dragEnterEvent = self.dragEnterEvent
        self.mPlotWidget.dropEvent = self.dropEvent

        self.mCurrentProfiles = collections.OrderedDict()
        self.mCurrentProfilesMode = SpectralLibraryWidget.CurrentProfilesMode.normal
        self.setCurrentProfilesMode(self.mCurrentProfilesMode)

        self.initActions()

        self.mMapInteraction = True
        self.setMapInteraction(self.mMapInteraction)

        # make buttons with default actions = menu be look like menu parents
        for toolBar in self.findChildren(QToolBar):
            for toolButton in toolBar.findChildren(QToolButton):
                assert isinstance(toolButton, QToolButton)
                if isinstance(toolButton.defaultAction(), QAction) and isinstance(toolButton.defaultAction().menu(), QMenu):
                    toolButton.setPopupMode(QToolButton.MenuButtonPopup)


        # shortcuts / redundant functions
        self.spectraLibrary = self.speclib
        self.clearTable = self.clearSpectralLibrary

    def applyAllPlotUpdates(self):
        """
        Forces the plot widget to update
        :return:
        :rtype:
        """
        self.plotWidget().onPlotUpdateTimeOut()

    def updateStatusBar(self):

        assert isinstance(self.mStatusBar, QStatusBar)
        slib = self.speclib()
        nFeatures = slib.featureCount()
        nSelected = slib.selectedFeatureCount()
        nVisible = self.plotWidget().plottedProfileCount()
        msg = "{}/{}/{}".format(nFeatures, nSelected, nVisible)
        self.mStatusBar.showMessage(msg)

    def onShowContextMenuExternally(self, menu:QgsActionMenu, fid):
        s = ""



    def onImportFromVectorSource(self):

        d = SpectralProfileImportPointsDialog()
        d.exec_()
        if d.result() == QDialog.Accepted:
            sl = d.speclib()
            n = len(sl)
            if isinstance(sl, SpectralLibrary) and n > 0:

                b = self.speclib().isEditable()

                self.addSpeclib(sl)



    def canvas(self)->QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mCanvas

    def onWillShowContextMenu(self, menu:QMenu, atIndex:QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """
        menu.addSeparator()
        menu.addAction(self.actionSelectAll)
        menu.addAction(self.actionInvertSelection)
        menu.addAction(self.actionRemoveSelection)
        menu.addAction(self.actionPanMapToSelectedRows)
        menu.addAction(self.actionZoomMapToSelectedRows)
        menu.addSeparator()
        menu.addAction(self.actionDeleteSelected)
        menu.addAction(self.actionCutSelectedRows)
        menu.addAction(self.actionCopySelectedRows)
        menu.addAction(self.actionPasteFeatures)

        menu.addSeparator()

        selectedFIDs = self.mDualView.tableView().selectedFeaturesIds()
        n = len(selectedFIDs)
        menuProfileStyle = menu.addMenu('Profile Style')
        wa = QWidgetAction(menuProfileStyle)

        btnResetProfileStyles = QPushButton('Reset')

        plotStyle = self.plotWidget().colorScheme().ps
        if n == 0:
            btnResetProfileStyles.setText('Reset All')
            btnResetProfileStyles.clicked.connect(self.plotWidget().resetProfileStyles)
            btnResetProfileStyles.setToolTip('Resets all profile styles')
        else:
            from .plotting import SpectralProfilePlotDataItem
            for fid in selectedFIDs:
                spi = self.plotWidget().spectralProfilePlotDataItem(fid)
                if isinstance(spi, SpectralProfilePlotDataItem):
                    plotStyle = PlotStyle.fromPlotDataItem(spi)

            btnResetProfileStyles.setText('Reset Selected')
            btnResetProfileStyles.clicked.connect(lambda *args, fids=selectedFIDs: self.plotWidget().setProfileStyle(None, fids))

        psw = PlotStyleWidget(plotStyle=plotStyle)
        psw.setPreviewVisible(False)
        psw.cbIsVisible.setVisible(False)
        psw.sigPlotStyleChanged.connect(lambda style, fids=selectedFIDs : self.plotWidget().setProfileStyle(style, fids))

        frame = QFrame()
        l = QVBoxLayout()
        l.addWidget(btnResetProfileStyles)
        l.addWidget(psw)

        frame.setLayout(l)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

        self.mDualView.tableView().currentIndex()


    def clearSpectralLibrary(self):
        """
        Removes all SpectralProfiles and additional fields
        """
        feature_ids = [feature.id() for feature in self.spectralLibrary().getFeatures()]
        self.speclib().startEditing()
        self.speclib().deleteFeatures(feature_ids)
        self.speclib().commitChanges()

        for fieldName in self.speclib().optionalFieldNames():
            index = self.spectralLibrary().fields().indexFromName(fieldName)
            self.spectralLibrary().startEditing()
            self.spectralLibrary().deleteAttribute(index)
            self.spectralLibrary().commitChanges()

    def currentProfilesMode(self)->CurrentProfilesMode:
        """
        Returns the mode how incoming profiles are handled
        :return: CurrentProfilesMode
        """
        return self.mCurrentProfilesMode

    def setCurrentProfilesMode(self, mode:CurrentProfilesMode):
        """
        Sets the way how to handel profiles added by setCurrentProfiles
        :param mode: CurrentProfilesMode
        """
        assert isinstance(mode, SpectralLibraryWidget.CurrentProfilesMode)
        self.mCurrentProfilesMode = mode
        if mode == SpectralLibraryWidget.CurrentProfilesMode.block:
            self.optionBlockProfiles.setChecked(True)
            self.optionAddCurrentProfilesAutomatically.setEnabled(False)
            #self.actionAddProfiles.setEnabled(False)
        else:
            self.optionBlockProfiles.setChecked(False)
            self.optionAddCurrentProfilesAutomatically.setEnabled(True)
            if mode == SpectralLibraryWidget.CurrentProfilesMode.automatically:
                self.optionAddCurrentProfilesAutomatically.setChecked(True)
                #self.actionAddProfiles.setEnabled(False)
            elif mode == SpectralLibraryWidget.CurrentProfilesMode.normal:
                self.optionAddCurrentProfilesAutomatically.setChecked(False)
                #self.actionAddProfiles.setEnabled(len(self.currentSpectra()) > 0)
            else:
                raise NotImplementedError()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        #log('dropEvent')
        mimeData = event.mimeData()

        speclib = SpectralLibrary.readFromMimeData(mimeData)
        if isinstance(speclib, SpectralLibrary) and len(speclib) > 0:
            event.setAccepted(True)
            self.addSpeclib(speclib)

    def dragEnterEvent(self, dragEnterEvent:QDragEnterEvent):

        mimeData = dragEnterEvent.mimeData()
        assert isinstance(mimeData, QMimeData)
        if containsSpeclib(mimeData):
            dragEnterEvent.accept()




    def initActions(self):

        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        def onSetBlocked(isBlocked):
            if isBlocked:
                self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.block)
            else:
                if self.optionAddCurrentProfilesAutomatically.isChecked():
                    self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
                else:
                    self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.normal)
        self.optionBlockProfiles.toggled.connect(onSetBlocked)
        self.optionBlockProfiles.setVisible(False)

        self.optionAddCurrentProfilesAutomatically.toggled.connect(
            lambda b: self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
                if b else self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.normal)
        )

        self.actionImportSpeclib.triggered.connect(self.onImportSpeclib)
        self.actionImportSpeclib.setMenu(self.importSpeclibMenu())
        self.actionImportVectorSource.triggered.connect(self.onImportFromVectorSource)
        self.actionAddProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)
        self.actionReloadProfiles.triggered.connect(self.onReloadProfiles)


        m = QMenu()
        #m.addAction(self.actionImportSpeclib)
        m.addAction(self.actionImportVectorSource)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        m.addSeparator()
        m.addAction(self.optionBlockProfiles)

        self.actionAddProfiles.setMenu(m)

        self.actionExportSpeclib.triggered.connect(self.onExportSpectra)
        self.actionExportSpeclib.setMenu(self.exportSpeclibMenu())
        self.actionSaveSpeclib = self.actionExportSpeclib  # backward compatibility
        self.actionReload.triggered.connect(lambda : self.mPlotWidget.updateSpectralProfilePlotItems())
        self.actionToggleEditing.toggled.connect(self.onToggleEditing)
        self.actionSaveEdits.triggered.connect(self.onSaveEdits)
        self.actionDeleteSelected.triggered.connect(lambda : deleteSelected(self.speclib()))

        self.actionSelectAll.triggered.connect(self.selectAll)
        self.actionInvertSelection.triggered.connect(self.invertSelection)
        self.actionRemoveSelection.triggered.connect(self.removeSelection)
        self.actionPanMapToSelectedRows.triggered.connect(self.panMapToSelectedRows)
        self.actionZoomMapToSelectedRows.triggered.connect(self.zoomMapToSelectedRows)

        self.actionAddAttribute.triggered.connect(self.onAddAttribute)
        self.actionRemoveAttribute.triggered.connect(self.onRemoveAttribute)

        self.actionFormView.triggered.connect(lambda: self.mDualView.setView(QgsDualView.AttributeEditor))
        self.actionTableView.triggered.connect(lambda: self.mDualView.setView(QgsDualView.AttributeTable))

        self.actionProperties.triggered.connect(self.showProperties)


        self.actionCutSelectedRows.triggered.connect(self.cutSelectedFeatures)
        self.actionCopySelectedRows.triggered.connect(self.copySelectedFeatures)
        self.actionPasteFeatures.triggered.connect(self.pasteFeatures)

        for action in [self.actionProperties, self.actionFormView, self.actionTableView]:
            btn = QToolButton()
            btn.setDefaultAction(action)
            btn.setAutoRaise(True)
            self.statusBar().addPermanentWidget(btn)

        self.onIsEditableChanged()

    def importSpeclibMenu(self)->QMenu:
        """
        :return: QMenu with QActions and submenus to import SpectralProfiles
        """
        m = QMenu()
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO), iface
            iface.addImportActions(self.speclib(), m)
        return m

    def exportSpeclibMenu(self)->QMenu:
        """
        :return: QMenu with QActions and submenus to export SpectralProfiles
        """
        m = QMenu()
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO)
            iface.addExportActions(self.speclib(), m)
        return m


    def showProperties(self, *args):

        from ..layerproperties import showLayerPropertiesDialog

        showLayerPropertiesDialog(self.speclib(), None, parent=self, useQGISDialog=True)

        s = ""

    def onImportSpeclib(self):
        """
        Imports a SpectralLibrary
        :param path: str
        """

        slib = SpectralLibrary.readFromSourceDialog(self)

        if isinstance(slib, SpectralLibrary) and len(slib) > 0:
            self.addSpeclib(slib)


    def speclib(self)->SpectralLibrary:
        """
        Returns the SpectraLibrary
        :return: SpectralLibrary
        """
        return self.mSpeclib

    def onSaveEdits(self, *args):

        if self.mSpeclib.isModified():

            b = self.mSpeclib.isEditable()
            self.mSpeclib.commitChanges()
            if b:
                self.mSpeclib.startEditing()

    def onSelectionChanged(self, selected, deselected, clearAndSelect):
        """
        :param selected:
        :param deselected:
        :param clearAndSelect:
        :return:
        """
        hasSelected = self.speclib().selectedFeatureCount() > 0
        self.actionCopySelectedRows.setEnabled(hasSelected)
        self.actionCutSelectedRows.setEnabled(self.mSpeclib.isEditable() and hasSelected)
        self.actionDeleteSelected.setEnabled(self.mSpeclib.isEditable() and hasSelected)
        self.actionReloadProfiles.setEnabled(self.mSpeclib.isEditable() and hasSelected)

        self.actionPanMapToSelectedRows.setEnabled(hasSelected)
        self.actionRemoveSelection.setEnabled(hasSelected)
        self.actionZoomMapToSelectedRows.setEnabled(hasSelected)


    def onIsEditableChanged(self, *args):
        speclib = self.speclib()

        isEditable = speclib.isEditable()
        self.actionToggleEditing.blockSignals(True)
        self.actionToggleEditing.setChecked(isEditable)
        self.actionSaveEdits.setEnabled(isEditable)
        self.actionReload.setEnabled(not isEditable)
        self.actionToggleEditing.blockSignals(False)
        self.actionReloadProfiles.setEnabled(isEditable)

        self.actionAddAttribute.setEnabled(isEditable)
        self.actionPasteFeatures.setEnabled(isEditable)
        self.actionToggleEditing.setEnabled(not speclib.readOnly())

        self.actionRemoveAttribute.setEnabled(isEditable and len(speclib.optionalFieldNames()) > 0)

        self.onSelectionChanged(None, None, None)

    def onToggleEditing(self, b:bool):

        if b == False:

            if self.mSpeclib.isModified():
                result = QMessageBox.question(self, 'Leaving edit mode', 'Save changes?', buttons=QMessageBox.No | QMessageBox.Yes, defaultButton=QMessageBox.Yes)
                if result == QMessageBox.Yes:
                    if not self.mSpeclib.commitChanges():
                        errors = self.mSpeclib.commitErrors()
                        print(errors)
                else:
                    self.mSpeclib.rollBack()
                    s = ""

            else:
                if not self.mSpeclib.commitChanges():
                    errors = self.mSpeclib.commitErrors()
                    print(errors)
        else:
            if not self.mSpeclib.isEditable() and not self.mSpeclib.startEditing():
                print('Can not edit spectral library')


    def onReloadProfiles(self):

        cnt = self.speclib().selectedFeatureCount()
        if cnt > 0 and self.speclib().isEditable():
            # ask for profile source raster
            from ..utils import SelectMapLayersDialog

            d = SelectMapLayersDialog()
            d.setWindowIcon(QIcon(''))
            d.setWindowTitle('Reload {} selected profile(s) from'.format(cnt))
            d.addLayerDescription('Raster', QgsMapLayerProxyModel.RasterLayer)
            d.exec_()
            if d.result() == QDialog.Accepted:
                layers = d.mapLayers()
                if isinstance(layers[0], QgsRasterLayer):
                    self.speclib().beginEditCommand('Reload {} profiles from {}'.format(cnt, layers[0].name()))
                    self.speclib().reloadSpectralValues(layers[0], selectedOnly=True)
                    self.speclib().endEditCommand()

            s  =""


    def onAddAttribute(self):
        """
        Slot to add an optional QgsField / attribute
        """

        if self.mSpeclib.isEditable():
            d = AddAttributeDialog(self.mSpeclib)
            d.exec_()
            if d.result() == QDialog.Accepted:
                field = d.field()
                self.mSpeclib.addAttribute(field)
        else:
            log('call SpectralLibrary().startEditing before adding attributes')

    def onRemoveAttribute(self):
        """
        Slot to remove none-mandatory fields / attributes
        """
        if self.mSpeclib.isEditable():
            fieldNames = self.mSpeclib.optionalFieldNames()
            if len(fieldNames) > 0:
                fieldName, accepted = QInputDialog.getItem(self, 'Remove Field', 'Select', fieldNames, editable=False)
                if accepted:
                    i = self.mSpeclib.fields().indexFromName(fieldName)
                    if i >= 0:
                        b = self.mSpeclib.isEditable()
                        self.mSpeclib.startEditing()
                        self.mSpeclib.deleteAttribute(i)
                        self.mSpeclib.commitChanges()
        else:
            log('call SpectralLibrary().startEditing before removing attributes')

    def setMapInteraction(self, b: bool):
        """
        Enables/disables actions to navigate on maps or select profiles from.
        Note: you need to connect them with respective MapTools and QgsMapCanvases
        :param b: bool
        """
        if b == False:
            self.setCurrentSpectra([])
        self.mMapInteraction = b
        self.actionSelectProfilesFromMap.setVisible(b)
        self.actionPanMapToSelectedRows.setVisible(b)
        self.actionZoomMapToSelectedRows.setVisible(b)


    def mapInteraction(self)->bool:
        """
        Returns True of map-interaction actions are enables and visible
        :return: bool
        """
        return self.mMapInteraction

    def selectAll(self):
        """
        Selects all features/spectral profiles
        """
        self.speclib().selectAll()

    def invertSelection(self):
        """
        Inverts the current selection
        """
        self.speclib().invertSelection()

    def removeSelection(self):
        """
        Removes the current selection
        """
        self.speclib().removeSelection()

    def panMapToSelectedRows(self):
        """
        Pan to the selected layer features
        Requires that external maps respond to sigMapCenterRequested
        """
        crs = self.mCanvas.mapSettings().destinationCrs()
        center = SpatialPoint(self.speclib().crs(), self.speclib().boundingBoxOfSelected().center()).toCrs(crs)
        self.mCanvas.setCenter(center)
        self.sigMapCenterRequested.emit(center)

    def zoomMapToSelectedRows(self):
        """
        Zooms to the selected rows.
        Requires that external maps respond to sigMapExtentRequested
        """
        crs = self.mCanvas.mapSettings().destinationCrs()
        bbox = SpatialExtent(self.speclib().crs(), self.speclib().boundingBoxOfSelected()).toCrs(crs)
        if isinstance(bbox, SpatialExtent):
            self.mCanvas.setExtent(bbox)
            self.sigMapExtentRequested.emit(bbox)

    def deleteSelectedFeatures(self):
        """
        Deletes the selected SpectralProfiles / QgsFeatures. Requires that editing mode is enabled.
        """
        self.speclib().beginEditCommand('Delete selected features')
        self.speclib().deleteSelectedFeatures()
        self.speclib().endEditCommand()

    def cutSelectedFeatures(self):
        """
        Copies the selected SpectralProfiles to the clipboard and deletes them from the SpectraLibrary.
        Requires that editing mode is enabled.
        """
        self.copySelectedFeatures()

        self.speclib().beginEditCommand('Cut Features')
        self.speclib().deleteSelectedFeatures()
        self.speclib().endEditCommand()

    def pasteFeatures(self):
        iface = qgisAppQgisInterface()
        if isinstance(iface, QgisInterface):
            iface.pasteFromClipboard(self.mSpeclib)

    def copySelectedFeatures(self):
        iface = qgisAppQgisInterface()
        if isinstance(iface, QgisInterface):
            iface.copySelectionToClipboard(self.mSpeclib)

    #def onAttributesChanged(self):
    #    self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    #def addAttribute(self, name):
    #    name = str(name)
    #    if len(name) > 0 and name not in self.mSpeclib.metadataAttributes():
    #        self.mModel.addAttribute(name)

    def plotWidget(self):
        """
        Returns the plotwidget
        :return: SpectralLibraryPlotWidget
        """
        return self.mPlotWidget

    def plotItem(self)->PlotItem:
        """
        Returns the pyqtgraph/graphicsItems/PlotItem/PlotItem
        :return: PlotItem
        """
        pi = self.mPlotWidget.getPlotItem()
        assert isinstance(pi, PlotItem)
        return pi

    def onExportSpectra(self, *args):
        files = self.mSpeclib.exportProfiles(None)
        if len(files) > 0:
            self.sigFilesCreated.emit(files)


    def addSpeclib(self, speclib:SpectralLibrary):
        """
        Adds spectral profiles of a SpectralLibrary. Suppresses plot updates in doing so
        :param speclib: SpectralLibrary
        """
        if isinstance(speclib, SpectralLibrary):
            sl = self.speclib()


            progressDialog = QProgressDialog(self)
            progressDialog.setWindowTitle('Add Profiles')
            progressDialog.show()

            info = 'Add {} profiles...'.format(len(speclib))

            wasEditable = sl.isEditable()

            try:
                sl.startEditing()
                sl.beginEditCommand(info)
                sl.addSpeclib(speclib, progressDialog=progressDialog)
                sl.endEditCommand()
                if not wasEditable:
                    sl.commitChanges()
            except Exception as ex:
                print(ex, file=sys.stderr)
                pass

            progressDialog.hide()
            progressDialog.close()
            QApplication.processEvents()


    def addCurrentSpectraToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """

        profiles = self.currentSpectra()
        self.setCurrentSpectra([])
        b = self.speclib().isEditable()
        self.speclib().startEditing()
        self.speclib().addProfiles(profiles)
        if not b:
            self.speclib().commitChanges()

    sigCurrentSpectraChanged = pyqtSignal(list)

    def setCurrentSpectra(self, profiles: list):
        self.setCurrentProfiles(profiles)

    def setCurrentProfiles(self, profiles:list):
        from .plotting import SpectralProfilePlotDataItem
        assert isinstance(profiles, list)
        self.mCurrentProfiles.clear()

        # todo: apply source filter

        for i in range(len(profiles)):
            p = profiles[i]
            assert isinstance(p, QgsFeature)
            if not isinstance(p, SpectralProfile):
                p = SpectralProfile.fromSpecLibFeature(p)
                profiles[i] = p


        mode = self.currentProfilesMode()
        if mode == SpectralLibraryWidget.CurrentProfilesMode.block:
            #
            pass

        elif mode == SpectralLibraryWidget.CurrentProfilesMode.automatically:

            # add SpectralProfiles into the SpectralLibrary

            b = self.mSpeclib.isEditable()
            self.mSpeclib.startEditing()
            self.mSpeclib.addProfiles(profiles)
            if not b:
                self.mSpeclib.commitChanges()

        elif mode == SpectralLibraryWidget.CurrentProfilesMode.normal:

            newCurrent = collections.OrderedDict()

            colorScheme = self.plotWidget().colorScheme()
            for i, p in enumerate(profiles):
                pdi = SpectralProfilePlotDataItem(p)
                pdi.setPlotStyle(colorScheme.cs)
                newCurrent[p] = pdi

            self.mCurrentProfiles.update(newCurrent)
            # self.actionAddProfiles.setEnabled(len(profiles) > 0)
        self.mPlotWidget.setPlotOverlayItems(list(self.mCurrentProfiles.values()))

    def currentSpectra(self) -> list:
        return self.currentProfiles()

    def currentProfiles(self)->list:
        """
        Returns the SpectralProfiles which are not added to the SpectralLibrary but shown as over-plot items
        :return: [list-of-SpectralProfiles]
        """
        return list(self.mCurrentProfiles.keys())


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib:SpectralLibrary=None, **kwds):
        super(SpectralLibraryPanel, self).__init__(*args, **kwds)
        self.setObjectName('spectralLibraryPanel')
        self.setWindowTitle('Spectral Library')
        self.SLW = SpectralLibraryWidget(speclib=speclib)
        self.setWidget(self.SLW)

    def spectralLibraryWidget(self) -> SpectralLibraryWidget:
        """
        Returns the SpectralLibraryWidget
        :return: SpectralLibraryWidget
        """
        return self.SLW

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary
        :return: SpectralLibrary
        """
        return self.SLW.speclib()

    def setCurrentSpectra(self, listOfSpectra):
        """
        Adds a list of SpectralProfiles as current spectra
        :param listOfSpectra: [list-of-SpectralProfiles]
        :return:
        """
        self.SLW.setCurrentSpectra(listOfSpectra)

    def setCurrentProfilesMode(self, mode:SpectralLibraryWidget.CurrentProfilesMode):
        """
        Sets the way how to handel profiles added by setCurrentProfiles
        :param mode: SpectralLibraryWidget.CurrentProfilesMode
        """
        self.SLW.setCurrentProfilesMode(mode)


class SpectralLibraryLayerStyleWidget(QgsMapLayerConfigWidget):

    pass

