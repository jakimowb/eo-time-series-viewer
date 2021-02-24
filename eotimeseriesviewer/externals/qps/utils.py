# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/utils.py

    A module for several utilities to be used in other QPS modules
    ---------------------
    Beginning            : 2019-01-11
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

import os
import sys
import importlib
import re
import fnmatch
import io
import zipfile
import itertools
import pathlib
import warnings
import collections
import copy
import shutil
import typing
import gc
import sip
import traceback
import calendar
import datetime
from qgis.core import *
from qgis.core import QgsField, QgsVectorLayer, QgsRasterLayer, QgsRasterDataProvider, QgsMapLayer, QgsMapLayerStore, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsRectangle, QgsPointXY, QgsProject, \
    QgsMapLayerProxyModel, QgsRasterRenderer, QgsMessageOutput, QgsFeature, QgsTask, Qgis, QgsGeometry
from qgis.gui import *
from qgis.gui import QgisInterface, QgsDialog, QgsMessageViewer, QgsMapLayerComboBox, QgsMapCanvas

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import *
from osgeo import gdal, ogr, osr, gdal_array
import numpy as np
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QDialogButtonBox, QLabel, QGridLayout, QMainWindow

try:
    from .. import qps
except:
    import qps
from . import DIR_UI_FILES

# dictionary to store form classes and avoid multiple calls to read <myui>.i
QGIS_RESOURCE_WARNINGS = set()

REMOVE_setShortcutVisibleInContextMenu = hasattr(QAction, 'setShortcutVisibleInContextMenu')

jp = os.path.join
dn = os.path.dirname


def rm(p):
    """
    Removes the file or directory `p`
    :param p: path of file or directory to be removed.
    """
    if os.path.isfile(p):
        os.remove(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)


def relativePath(absPath: pathlib.Path, parentDir: pathlib.Path) -> pathlib.Path:
    """
    Returns the path relative to a parent directory
    :param absPath: absolute path to be converted into a relative path
    :param parentDir: the reference directory, from which the relative path will be calculated
                      if both paths are in the same directory, absPath = parentDir / relativePath
    :return: relative path
    """
    if isinstance(absPath, str):
        absPath = pathlib.Path(absPath)
    if isinstance(parentDir, str):
        parentDir = pathlib.Path(parentDir)

    assert isinstance(parentDir, pathlib.Path)
    assert isinstance(absPath, pathlib.Path)
    n = min(len(parentDir.parts), len(absPath.parts))
    i = 0

    relPath = pathlib.Path()
    while i < n:
        if parentDir.parts[i] == absPath.parts[i]:
            i += 1
        else:
            break
    if i > 0:
        for _ in range(len(parentDir.parts[i:])):
            relPath = relPath / '..'

    for part in absPath.parts[i:]:
        relPath = relPath / part

    return relPath


def cleanDir(d):
    """
    Remove content from directory 'd'
    :param d: directory to be cleaned.
    """
    assert os.path.isdir(d)
    for root, dirs, files in os.walk(d):
        for p in dirs + files: rm(jp(root, p))
        break


# a QPS internal map layer store
QPS_MAPLAYER_STORE = QgsMapLayerStore()

# a list of all known maplayer stores.
MAP_LAYER_STORES = [QPS_MAPLAYER_STORE, QgsProject.instance()]


def findUpwardPath(basepath, name, is_directory: bool = True) -> pathlib.Path:
    """
    Searches for an file or directory in an upward path of the base path

    :param basepath:
    :param name:
    :param is_directory:
    :return:
    """
    tmp = pathlib.Path(basepath).resolve()
    while tmp != pathlib.Path(tmp.anchor):
        if (is_directory and os.path.isdir(tmp / name)) or os.path.isfile(tmp / name):
            return tmp / name
        else:
            tmp = tmp.parent
    return None


def file_search(rootdir,
                pattern,
                recursive: bool = False,
                ignoreCase: bool = False,
                directories: bool = False,
                fullpath: bool = False):
    """
    Searches for files or folders
    :param rootdir: root directory to search in
    :param pattern: wildcard ("my*files.*") or regular expression that describes the file or folder name.
    :param recursive: set True to search recursively.
    :param ignoreCase: set True to ignore character case.
    :param directories: set True to search for directories/folders instead of files.
    :param fullpath: set True if the entire path should be evaluated and not the file name only
    :return: enumerator over file paths
    """
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))

    for entry in os.scandir(rootdir):
        if directories == False:
            if entry.is_file():
                if fullpath:
                    name = entry.path
                else:
                    name = os.path.basename(entry.path)
                if isinstance(pattern, regType):
                    if pattern.search(name):
                        yield entry.path.replace('\\', '/')

                elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                        or fnmatch.fnmatch(name, pattern):
                    yield entry.path.replace('\\', '/')
            elif entry.is_dir() and recursive == True:
                for r in file_search(entry.path, pattern, recursive=recursive, directories=directories):
                    yield r
        else:
            if entry.is_dir():
                if recursive == True:
                    for d in file_search(entry.path, pattern, recursive=recursive, directories=directories):
                        yield d

                if fullpath:
                    name = entry.path
                else:
                    name = os.path.basename(entry.path)
                if isinstance(pattern, regType):
                    if pattern.search(name):
                        yield entry.path.replace('\\', '/')

                elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                        or fnmatch.fnmatch(name, pattern):
                    yield entry.path.replace('\\', '/')


def registerMapLayerStore(store):
    """
    Registers an QgsMapLayerStore or QgsProject to search QgsMapLayers in
    :param store: QgsProject | QgsMapLayerStore
    """
    assert isinstance(store, (QgsProject, QgsMapLayerStore))
    if store not in MAP_LAYER_STORES:
        MAP_LAYER_STORES.append(store)


def registeredMapLayers() -> list:
    """
    Returns the QgsMapLayers which are stored in known QgsMapLayerStores
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    for store in [QgsProject.instance()] + MAP_LAYER_STORES:
        for layer in store.mapLayers().values():
            if layer not in layers:
                layers.append(layer)
    return layers


class UnitLookup(object):
    METRIC_EXPONENTS = {
        'nm': -9, 'μm': -6, 'mm': -3, 'cm': -2, 'dm': -1, 'm': 0, 'hm': 2, 'km': 3
    }

    DATE_UNITS = ['DateTime', 'DOY', 'DecimalYear', 'DecimalYear[366]', 'DecimalYear[365]', 'Y', 'M', 'W', 'D']
    TIME_UNITS = ['h', 'm', 's', 'ms', 'us', 'ns', 'ps', 'fs', 'as']

    UNIT_LOOKUP = {}

    @staticmethod
    def metric_units() -> typing.List[str]:
        return list(UnitLookup.METRIC_EXPONENTS.keys())

    @staticmethod
    def date_units() -> typing.List[str]:
        return list(UnitLookup.DATE_UNITS)

    @staticmethod
    def time_units() -> typing.List[str]:
        return list(UnitLookup.TIME_UNITS)

    @staticmethod
    def baseUnit(unit: str) -> str:
        """
        Tries to return the basic physical unit
        e.g. "m" for string of "Meters"

        :param unit:
        :type unit:
        :return:
        :rtype:
        """
        if not isinstance(unit, str):
            return None

        unit = unit.strip()

        if unit in UnitLookup.UNIT_LOOKUP.keys():
            return UnitLookup.UNIT_LOOKUP[unit]

        # so far this unit is unknown. Try to find the base unit
        # store unit string in Lookup table for fast conversion into its base unit
        # e.g. to convert string like "MiKrOMetErS" to "μm"
        base_unit = None

        if unit in UnitLookup.metric_units() + \
                UnitLookup.date_units() + \
                UnitLookup.time_units():
            base_unit = unit
        elif re.search(r'^(Nanomet(er|re)s?)$', unit, re.I):
            base_unit = 'nm'
        elif re.search(r'^(Micromet(er|re)s?|um|μm)$', unit, re.I):
            base_unit = 'μm'
        elif re.search(r'^(Millimet(er|re)s?)$', unit, re.I):
            base_unit = 'mm'
        elif re.search(r'^(Centimet(er|re)s?)$', unit, re.I):
            base_unit = 'cm'
        elif re.search(r'^(Decimet(er|re)s?)$', unit, re.I):
            base_unit = 'dm'
        elif re.search(r'^(Met(er|re)s?)$', unit, re.I):
            base_unit = 'm'
        elif re.search(r'^(Hectomet(er|re)s?)$', unit, re.I):
            base_unit = 'hm'
        elif re.search(r'^(Kilomet(er|re)s?)$', unit, re.I):
            base_unit = 'km'
        # date units
        elif re.search(r'(Date([_\- ]?Time)?([_\- ]?Group)?|DTG)$', unit, re.I):
            base_unit = 'DateTime'
        elif re.search(r'^(doy|Day[-_ ]?Of[-_ ]?Year?)$', unit, re.I):
            base_unit = 'DOY'
        elif re.search(r'decimal[_\- ]?years?$', unit, re.I):
            base_unit = 'DecimalYear'
        elif re.search(r'decimal[_\- ]?years?\[356\]$', unit, re.I):
            base_unit = 'DecimalYear[365]'
        elif re.search(r'decimal[_\- ]?years?\[366\]$', unit, re.I):
            base_unit = 'DecimalYear[366]'
        elif re.search(r'^Years?$', unit, re.I):
            base_unit = 'Y'
        elif re.search(r'^Months?$', unit, re.I):
            base_unit = 'M'
        elif re.search(r'^Weeks?$', unit, re.I):
            base_unit = 'W'
        elif re.search(r'^Days?$', unit, re.I):
            base_unit = 'D'
        elif re.search(r'^Hours?$', unit, re.I):
            base_unit = 'h'
        elif re.search(r'^Minutes?$', unit, re.I):
            base_unit = 'm'
        elif re.search(r'^Seconds?$', unit, re.I):
            base_unit = 's'
        elif re.search(r'^MilliSeconds?$', unit, re.I):
            base_unit = 'ms'
        elif re.search(r'^MicroSeconds?$', unit, re.I):
            base_unit = 'us'
        elif re.search(r'^NanoSeconds?$', unit, re.I):
            base_unit = 'ns'
        elif re.search(r'^Picoseconds?$', unit, re.I):
            base_unit = 'ps'
        elif re.search(r'^Femtoseconds?$', unit, re.I):
            base_unit = 'fs'
        elif re.search(r'^Attoseconds?$', unit, re.I):
            base_unit = 'as'

        if base_unit:
            UnitLookup.UNIT_LOOKUP[unit] = base_unit
        return base_unit

    @staticmethod
    def isMetricUnit(unit: str) -> bool:
        baseUnit = UnitLookup.baseUnit(unit)
        return baseUnit in UnitLookup.metric_units()

    @staticmethod
    def isTemporalUnit(unit: str) -> bool:
        baseUnit = UnitLookup.baseUnit(unit)
        return baseUnit in UnitLookup.time_units() + UnitLookup.date_units()

    @staticmethod
    def convertMetricUnit(value: typing.Union[float, np.ndarray], u1: str, u2: str) -> float:
        """
        Converts value `value` from unit `u1` into unit `u2`
        :param value: float | int | might work with numpy.arrays as well
        :param u1: str, identifier of unit 1
        :param u2: str, identifier of unit 2
        :return: float | numpy.array, converted values
                 or None in case conversion is not possible
        """
        assert isinstance(u1, str), 'Source unit needs to be a str'
        assert isinstance(u2, str), 'Destination unit needs to be a str'
        u1 = UnitLookup.baseUnit(u1)
        u2 = UnitLookup.baseUnit(u2)

        e1 = UnitLookup.METRIC_EXPONENTS.get(u1)
        e2 = UnitLookup.METRIC_EXPONENTS.get(u2)

        if all([arg is not None for arg in [value, e1, e2]]):
            if e1 == e2:
                return copy.copy(value)
            elif isinstance(value, list):
                return [v * 10 ** (e1 - e2) for v in value]
            else:
                return value * 10 ** (e1 - e2)
        else:
            return None

    @staticmethod
    def convertDateUnit(value: np.datetime64, unit: str):
        """
        Converts a
        :param value: numpy.datetime64 | datetime.date | datetime.datetime | float | int
                      int values are interpreted as year
                      float values are interpreted as decimal year
        :param unit: output unit
                    (integer) Y - Year, M - Month, W - Week, D - Day, DOY - Day-of-Year
                    (float) DecimalYear (based on True number of days per year)
                    (float) DecimalYear[365] (based on 365 days per year, i.e. wrong for leap years)
                    (float) DecimalYear[366] (based on 366 days per year, i.e. wrong for none-leap years)

        :return: float (if unit is decimal year), int else
        """
        unit = UnitLookup.baseUnit(unit)
        if not UnitLookup.isTemporalUnit(unit):
            return None
        # see https://numpy.org/doc/stable/reference/arrays.datetime.html#arrays-dtypes-dateunits
        # for valid date units
        if isinstance(value, np.ndarray):
            func = np.vectorize(UnitLookup.convertDateUnit)
            return func(value, unit)

        value = datetime64(value)
        if unit == 'Y':
            return value.astype(object).year
        elif unit == 'M':
            return value.astype(object).month
        elif unit == 'D':
            return value.astype(object).day
        elif unit == 'W':
            return value.astype(object).week
        elif unit == 'DOY':
            return int(((value - value.astype('datetime64[Y]')).astype('timedelta64[D]') + 1).astype(int))

        elif unit.startswith('DecimalYear'):
            year = value.astype(object).year
            year64 = value.astype('datetime64[Y]')

            # second of year
            soy = (value - year64).astype('timedelta64[s]').astype(np.float64)

            # seconds per year
            if unit == 'DecimalYear[366]':
                spy = 366 * 86400
            elif unit == 'DecimalYear[365]':
                spy = 365 * 86400
            else:
                spy = 366 if calendar.isleap(year) else 365
                spy *= 86400
            spy2 = np.datetime64('{:04}-01-01T00:00:00'.format(year + 1)) - np.datetime64(
                '{:04}-01-01T00:00:00'.format(year))
            spy2 = int(spy2.astype(int))
            if spy != spy2:
                s = ""
            return float(year + soy / spy)
        else:
            raise NotImplementedError()


convertMetricUnit = UnitLookup.convertMetricUnit
convertDateUnit = UnitLookup.convertDateUnit

METRIC_EXPONENTS = UnitLookup.METRIC_EXPONENTS

# contains the wavelengths
LUT_WAVELENGTH = dict({'B': 480,
                       'G': 570,
                       'R': 660,
                       'NIR': 850,
                       'SWIR': 1650,
                       'SWIR1': 1650,
                       'SWIR2': 2150
                       })

NEXT_COLOR_HUE_DELTA_CON = 10
NEXT_COLOR_HUE_DELTA_CAT = 100


def nextColor(color, mode='cat') -> QColor:
    """
    Returns another color.
    :param color: QColor
    :param mode: str, 'cat' for categorical colors (much difference from 'color')
                      'con' for continuous colors (similar to 'color')
    :return: QColor
    """
    assert mode in ['cat', 'con']
    assert isinstance(color, QColor)
    hue, sat, value, alpha = color.getHsl()
    if mode == 'cat':
        hue += NEXT_COLOR_HUE_DELTA_CAT
    elif mode == 'con':
        hue += NEXT_COLOR_HUE_DELTA_CON
    if sat == 0:
        sat = 255
        value = 128
        alpha = 255
        s = ""
    while hue >= 360:
        hue -= 360

    return QColor.fromHsl(hue, sat, value, alpha)


def findMapLayerStores() -> typing.List[typing.Union[QgsProject, QgsMapLayerStore]]:
    import gc
    yield QgsProject.instance()
    for obj in gc.get_objects():
        if isinstance(obj, QgsMapLayerStore):
            yield obj


def findMapLayer(layer) -> QgsMapLayer:
    """
    Returns the first QgsMapLayer out of all layers stored in MAP_LAYER_STORES that matches layer
    :param layer: str layer id or layer name or QgsMapLayer
    :return: QgsMapLayer
    """
    assert isinstance(layer, (QgsMapLayer, str))
    if isinstance(layer, QgsMapLayer):
        return layer

    elif isinstance(layer, str):
        for store in findMapLayerStores():
            lyr = store.mapLayer(layer)
            if isinstance(lyr, QgsMapLayer):
                return lyr
            layers = store.mapLayersByName(layer)
            if len(layers) > 0:
                return layers[0]

    for lyr in gc.get_objects():
        if isinstance(lyr, QgsMapLayer):
            if lyr.id() == layer or lyr.source() == layer:
                return lyr

    return None


def gdalFileSize(path) -> int:
    """
    Returns the size of a local gdal readible file (including metadata files etc.)
    :param path: str
    :return: int
    """
    ds = gdal.Open(path)
    if not isinstance(ds, gdal.Dataset):
        return 0
    else:
        size = 0
        for file in ds.GetFileList():
            size += os.stat(file).st_size

            # recursively inspect VRT sources
            if file.endswith('.vrt') and file != path:
                size += gdalFileSize(file)

        return size


def qgisLayerTreeLayers() -> list:
    """
    Returns the layers shown in the QGIS LayerTree
    :return: [list-of-QgsMapLayers]
    """
    iface = qgisAppQgisInterface()
    if isinstance(iface, QgisInterface):
        return [ln.layer() for ln in iface.layerTreeView().layerTreeModel().rootGroup().findLayers()
                if isinstance(ln.layer(), QgsMapLayer)]
    else:
        return []


def createQgsField(name: str, exampleValue: typing.Any, comment: str = None) -> QgsField:
    """
    Creates a QgsField based on the type properties of an Python-datatype exampleValue
    :param name: field name
    :param exampleValue: value, can be any type
    :param comment: (optional) field comment.
    :return: QgsField
    """
    if isinstance(exampleValue, str):
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif isinstance(exampleValue, bool):
        return QgsField(name, QVariant.Bool, 'int', len=1, comment=comment)
    elif isinstance(exampleValue, (int, np.int, np.int8, np.int16, np.int32, np.int64)):
        return QgsField(name, QVariant.Int, 'int', comment=comment)
    elif isinstance(exampleValue, (np.uint, np.uint8, np.uint16, np.uint32, np.uint64)):
        return QgsField(name, QVariant.UInt, 'uint', comment=comment)
    elif isinstance(exampleValue, (float, np.double, np.float, np.double, np.float16, np.float32, np.float64)):
        return QgsField(name, QVariant.Double, 'double', comment=comment)
    elif isinstance(exampleValue, np.ndarray):
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif isinstance(exampleValue, np.datetime64):
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif isinstance(exampleValue, (bytes, QByteArray)):
        return QgsField(name, QVariant.ByteArray, 'Binary', comment=comment)
    elif isinstance(exampleValue, list):
        assert len(exampleValue) > 0, 'need at least one value in provided list'
        v = exampleValue[0]
        prototype = createQgsField(name, v)
        subType = prototype.type()
        typeName = prototype.typeName()
        return QgsField(name, QVariant.List, typeName, comment=comment, subType=subType)
    else:
        raise NotImplemented()


def filenameFromString(text: str):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    see https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    :return: path
    """
    if text is None:
        return ''
    isInValid = re.compile(r"[\\/:?\"<>| ,']")

    isValid = re.compile(r"([-_.()]|\d|\D)", re.ASCII + re.IGNORECASE)
    import unicodedata
    cleaned = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore')

    chars = []
    for c in cleaned.decode():
        if isValid.search(c) and not isInValid.search(c):
            chars.append(c)
        else:
            chars.append('_')

    return ''.join(chars)


def value2str(value, sep: str = None, delimiter: str = ' '):
    """
    Converts a value into a string
    :param value: any
    :param delimiter: delimiter to be used for list values
    :return:
    """

    if sep is not None:
        delimiter = sep

    if isinstance(value, list):
        value = delimiter.join([str(v) for v in value])
    elif isinstance(value, np.ndarray):
        value = value2str(value.tolist(), delimiter=delimiter)
    elif value is None:
        value = ''
    else:
        value = str(value)
    return value


def setQgsFieldValue(feature: QgsFeature, field, value):
    """
    Wrties the Python value v into a QgsFeature field, taking care of required conversions
    :param feature: QgsFeature
    :param field: QgsField | field name (str) | field index (int)
    :param value: any python value
    """

    if isinstance(field, int):
        field = feature.fields().at(field)
    elif isinstance(field, str):
        field = feature.fields().at(feature.fieldNameIndex(field))
    assert isinstance(field, QgsField)

    if value is None:
        value = QVariant.NULL
    if field.type() == QVariant.String:
        value = str(value)
    elif field.type() in [QVariant.Int, QVariant.Bool]:
        value = int(value)
    elif field.type() in [QVariant.Double]:
        value = float(value)

    feature.setAttribute(field.name(), value)


def showMessage(message: str, title: str, level):
    """
    Shows a message using the QgsMessageViewer
    :param message: str, message
    :param title: str, title of viewer
    :param level:
    """

    v = QgsMessageViewer()
    v.setTitle(title)

    isHtml = message.startswith('<html>')
    v.setMessage(message, QgsMessageOutput.MessageHtml if isHtml else QgsMessageOutput.MessageText)
    v.showMessage(True)


def gdalDataset(dataset: typing.Union[str,
                                      pathlib.Path,
                                      QgsRasterLayer,
                                      QgsRasterDataProvider,
                                      gdal.Dataset],
                eAccess: int = gdal.GA_ReadOnly) -> gdal.Dataset:
    """
    Returns a gdal.Dataset object instance
    :param dataset:
    :param pathOrDataset: path | gdal.Dataset | QgsRasterLayer | QgsRasterDataProvider
    :return: gdal.Dataset
    """
    if isinstance(dataset, gdal.Dataset):
        return dataset
    if isinstance(dataset, pathlib.Path):
        dataset = dataset.as_posix()
    if isinstance(dataset, QgsRasterLayer):
        return gdalDataset(dataset.source())
    if isinstance(dataset, QgsRasterDataProvider):
        return gdalDataset(dataset.dataSourceUri())
    if isinstance(dataset, str):
        ds = gdal.Open(dataset, eAccess)
        assert isinstance(ds, gdal.Dataset), f'Can not read {dataset} as gdal.Dataset'
        return ds
    else:
        raise NotImplementedError(f'Can not open {dataset} as gdal.Dataset')

    return dataset


def ogrDataSource(data_source) -> ogr.DataSource:
    """
    Returns an OGR DataSource instance
    :param data_source: ogr.DataSource | str | pathlib.Path | QgsVectorLayer
    :return: ogr.Datasource
    """
    if isinstance(data_source, ogr.DataSource):
        return data_source

    if isinstance(data_source, QgsVectorLayer):
        dpn = data_source.dataProvider().name()
        if dpn not in ['ogr']:
            raise Exception(f'Unsupported vector data provider: {dpn}')
        uri = data_source.source().split('|')[0]
        return ogrDataSource(uri)

    if isinstance(data_source, pathlib.Path):
        data_source = data_source.as_posix()

    if isinstance(data_source, str):
        data_source = ogr.Open(data_source)

    assert isinstance(data_source, ogr.DataSource), 'Can not read {} as ogr.DataSource'.format(data_source)
    return data_source


def optimize_block_size(ds: gdal.Dataset,
                        nb: int = None,
                        cache: int = 5 * 2 ** 20  # defaults: 5 megabytes
                        ) -> typing.List[int]:
    """
    Calculates a block_size for fast raster access given a defined cache size in bytes.
    :param ds: gdal.Dataset
    :param nb: number of bands to read, defaults to total number of bands = ds.RasterCount
    :param cache: maximum number of bytes to load with one block. defaults to 5 MB.
    :return:
    """
    if isinstance(ds, gdal.Band):
        ds = ds.GetDataset()
    assert isinstance(ds, gdal.Dataset)
    if nb is None:
        nb = ds.RasterCount
    block_size = ds.GetRasterBand(1).GetBlockSize()
    # bytes per value
    bpv = gdal_array.flip_code(ds.GetRasterBand(1).DataType)(0).itemsize

    # bytes per profile
    bpp = nb * bpv

    size = block_size[0] * block_size[1] * bpp
    if size > cache:
        # todo: reduce block sizes
        pass
    elif size < cache:
        # increase
        if block_size[0] >= ds.RasterXSize:
            bbl = ds.RasterXSize * bpp
            nl = min(int(cache / bbl), ds.RasterYSize)
            block_size = [ds.RasterXSize, nl]
        elif block_size[1] >= ds.RasterYSize:
            bbs = ds.RasterYSize * bpp
            ns = min(int(cache / bbs), ds.RasterXSize)
            block_size = [ns, ds.RasterYSize]

    return block_size


def fid2pixelindices(raster: gdal.Dataset,
                     vector: ogr.DataSource,
                     layer: typing.Union[int, str] = None,
                     all_touched: bool = True) -> typing.Tuple[np.ndarray, int]:
    """
    Returns vector feature pixel positions.

    :param raster: gdal.Dataset | QgsRasterLayer or path to
    :param vector: ogr.DataSource | QgsVectorLayer or path to
    :param layer: optional, layer name (str) or index (0), defaults to first layer (index = 0)
    :param all_touched: optional, set FALSE to return pixels entirely covered only
    :param fids_of_interest: options, set a list of FIDs of interest.
    :return: np.ndarray, int no data value
    """
    raster: gdal.Dataset = gdalDataset(raster)
    vector: ogr.DataSource = ogrDataSource(vector)

    if isinstance(layer, str):
        layernames = [vector.GetLayer(i).GetName() for i in range(vector.GetLayerCount())]
        if layer in layernames:
            layer = layernames.index(layer)
        else:
            raise Exception(f'Invalid layer name "{layer}". Possible values: {",".join(layernames)}')

    assert isinstance(layer, int)
    assert layer >= 0
    assert layer < vector.GetLayerCount()
    layer: ogr.Layer = vector.GetLayerByIndex(layer)
    nf = layer.GetFeatureCount()
    if nf < np.iinfo(np.uint8).max:
        no_data = int(np.iinfo(np.uint8).max)
        eType = gdal_array.flip_code(np.uint8)
    elif nf < np.iinfo(np.uint16).max:
        no_data = int(np.iinfo(np.uint16).max)
        eType = gdal_array.flip_code(np.uint16)
    elif nf < np.iinfo(np.uint32).max:
        no_data = int(np.iinfo(np.uint32).max)
        eType = gdal_array.flip_code(np.uint32)
    else:
        # worst case: burn fid into float
        no_data = -1
        eType = gdal_array.flip_code(np.float64)

    dsMEM: gdal.Dataset = gdal.GetDriverByName('MEM') \
        .Create('', raster.RasterXSize, raster.RasterYSize, 1, eType=eType)
    dsMEM.SetGeoTransform(raster.GetGeoTransform())
    dsMEM.SetProjection(raster.GetProjection())
    band: gdal.Band = dsMEM.GetRasterBand(1)
    band.Fill(no_data)
    band.SetNoDataValue(no_data)
    dsMEM.FlushCache()

    # print(f'Rasterize FIDs of {layer.GetDescription()}...')

    drvMem: ogr.Driver = ogr.GetDriverByName('Memory')
    dsMem: ogr.DataSource = drvMem.CreateDataSource('')
    lyrMem: ogr.Layer = dsMem.CreateLayer(layer.GetName(),
                                          srs=layer.GetSpatialRef(),
                                          geom_type=layer.GetGeomType())
    ldef: ogr.FeatureDefn = lyrMem.GetLayerDefn()
    ldef.AddFieldDefn(ogr.FieldDefn('FID_BURN', ogr.OFTInteger64))
    dsMem.FlushCache()

    for f in layer:
        assert isinstance(f, ogr.Feature)
        # Create the feature and set values
        fMem: ogr.Feature = ogr.Feature(ldef)
        fMem.SetGeometry(f.GetGeometryRef())
        fMem.SetField("FID_BURN", f.GetFID())

        lyrMem.CreateFeature(fMem)
    lyrMem.ResetReading()

    all_touched = 'TRUE' if all_touched else 'FALSE'

    result = gdal.RasterizeLayer(dsMEM, [1], lyrMem,
                                 options=['ALL_TOUCHED={}'.format(all_touched),
                                          'ATTRIBUTE={}'.format('FID_BURN')])
    assert result == ogr.OGRERR_NONE, f'Failed to rasterize vector layer {vector.GetDescription()}'

    fidArray: np.ndarray = dsMEM.ReadAsArray()

    return fidArray, int(no_data)


def qgsVectorLayer(source) -> QgsVectorLayer:
    """
    Returns a QgsVectorLayer from different source types
    :param source: QgsVectorLayer | ogr.DataSource | file path
    :return: QgsVectorLayer
    :rtype: QgsVectorLayer
    """
    if isinstance(source, QgsVectorLayer):
        return source
    if isinstance(source, pathlib.Path):
        return QgsRasterLayer(source.as_posix())
    if isinstance(source, str):
        return QgsVectorLayer(source)
    if isinstance(source, ogr.DataSource):
        return QgsVectorLayer(source.GetDescription())
    if isinstance(source, QUrl):
        return qgsVectorLayer(pathlib.Path(source.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)).resolve())

    raise Exception('Unable to transform {} into QgsVectorLayer'.format(source))


def qgsRasterLayer(source) -> QgsRasterLayer:
    """
    Returns a QgsVectorLayer from different source types
    :param source: QgsVectorLayer | ogr.DataSource | file path
    :return: QgsVectorLayer
    :rtype: QgsVectorLayer
    """
    if isinstance(source, QgsRasterLayer):
        return source
    if isinstance(source, pathlib.Path):
        return QgsRasterLayer(source.as_posix())
    if isinstance(source, str):
        return QgsRasterLayer(source)
    if isinstance(source, gdal.Dataset):
        return QgsRasterLayer(source.GetDescription())
    if isinstance(source, QUrl):
        return qgsRasterLayer(pathlib.Path(source.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)).resolve())

    raise Exception('Unable to transform {} into QgsRasterLayer'.format(source))


def qgsRasterLayers(sources) -> typing.Iterator[QgsRasterLayer]:
    """
    Like qgsRasterLayer, but on multiple inputs and with extraction of sub-layers
    :param sources:
    :return:
    """
    if not isinstance(sources, list):
        sources = [sources]
    assert isinstance(sources, list)

    for source in sources:
        lyr: QgsRasterLayer = qgsRasterLayer(source)
        if lyr.isValid():
            yield lyr
        for lyr in qgsRasterLayers(lyr.subLayers()):
            yield lyr


def qgsMapLayer(value: typing.Any) -> QgsMapLayer:
    """
    Tries to convert the input into a QgsMapLayer
    :param value: any
    :return: QgsMapLayer or None
    """
    if isinstance(value, QgsMapLayer):
        return value
    try:
        lyr = qgsRasterLayer(value)
        if isinstance(lyr, QgsRasterLayer):
            return lyr
    except:
        pass

    try:
        lyr = qgsVectorLayer(value)
        if isinstance(lyr, QgsVectorLayer):
            return lyr
    except:
        pass

    return None


def loadUi(uifile, baseinstance=None, package='', resource_suffix='_rc', remove_resource_references=True,
           loadUiType=False):
    """
    :param uifile:
    :type uifile:
    :param baseinstance:
    :type baseinstance:
    :param package:
    :type package:
    :param resource_suffix:
    :type resource_suffix:
    :param remove_resource_references:
    :type remove_resource_references:
    :return:
    :rtype:
    """

    assert os.path.isfile(uifile), '*.ui file does not exist: {}'.format(uifile)

    with open(uifile, 'r', encoding='utf-8') as f:
        txt = f.read()

    dirUi = os.path.dirname(uifile)

    QGIS_QRC = REGEX_QGIS_IMAGES_QRC = re.compile(r'.*QGIS[^\/]*[\/]images[\/]images\.qrc$')
    locations = []

    for m in re.findall(r'(<include location="(.*\.qrc)"/>)', txt):
        locations.append(m)

    missing = []
    for t in locations:
        line, path = t
        if not os.path.isabs(path):
            p = os.path.join(dirUi, path)
        else:
            p = path

        if not os.path.isfile(p):
            missing.append(t)

    match = re.search(r'resource="[^:].*/QGIS[^/"]*/images/images.qrc"', txt)
    if match:
        txt = txt.replace(match.group(), 'resource=":/images/images.qrc"')

    if len(missing) > 0:

        missingQrc = []
        missingQgs = []

        for t in missing:
            line, path = t
            if re.search(r'.*(?i:qgis)/images/images\.qrc.*', line):
                missingQgs.append(m)
            else:
                missingQrc.append(m)

        if len(missingQrc) > 0:
            print('{}\nrefers to {} none-existing resource (*.qrc) file(s):'.format(uifile, len(missingQrc)))
            for i, t in enumerate(missingQrc):
                line, path = t
                print('{}: "{}"'.format(i + 1, path), file=sys.stderr)

        if len(missingQgs) > 0 and not isinstance(qgisAppQgisInterface(), QgisInterface):
            missingFiles = [p[1] for p in missingQrc if p[1] not in QGIS_RESOURCE_WARNINGS]

            if len(missingFiles) > 0:
                print('{}\nrefers to {} none-existing resource (*.qrc) file(s) '.format(uifile, len(missingFiles)))
                for i, path in enumerate(missingFiles):
                    print('{}: "{}"'.format(i + 1, path))
                    QGIS_RESOURCE_WARNINGS.add(path)
                print('These files are likely available in a QGIS Desktop session. Further warnings will be skipped')

    doc = QDomDocument()
    doc.setContent(txt)

    if REMOVE_setShortcutVisibleInContextMenu and 'shortcutVisibleInContextMenu' in txt:
        toRemove = []
        actions = doc.elementsByTagName('action')
        for iAction in range(actions.count()):
            properties = actions.item(iAction).toElement().elementsByTagName('property')
            for iProperty in range(properties.count()):
                prop = properties.item(iProperty).toElement()
                if prop.attribute('name') == 'shortcutVisibleInContextMenu':
                    toRemove.append(prop)
        for prop in toRemove:
            prop.parentNode().removeChild(prop)
        del toRemove

    elem = doc.elementsByTagName('customwidget')
    for child in [elem.item(i) for i in range(elem.count())]:
        child = child.toElement()

        cClass = child.firstChildElement('class').firstChild()
        cHeader = child.firstChildElement('header').firstChild()
        cExtends = child.firstChildElement('extends').firstChild()

        sClass = str(cClass.nodeValue())
        sExtends = str(cHeader.nodeValue())
        if False:
            if sClass.startswith('Qgs'):
                cHeader.setNodeValue('qgis.gui')
        if True:
            # replace 'qps' package location with local absolute position
            if sExtends.startswith('qps.'):
                cHeader.setNodeValue(re.sub(r'^qps\.', qps.__spec__.name + '.', sExtends))

    if remove_resource_references:
        # remove resource file locations to avoid import errors.
        elems = doc.elementsByTagName('include')
        for i in range(elems.count()):
            node = elems.item(i).toElement()
            attribute = node.attribute('location')
            if len(attribute) > 0 and attribute.endswith('.qrc'):
                node.parentNode().removeChild(node)

        # remove iconset resource names, e.g.<iconset resource="../qpsresources.qrc">
        elems = doc.elementsByTagName('iconset')
        for i in range(elems.count()):
            node = elems.item(i).toElement()
            attribute = node.attribute('resource')
            if len(attribute) > 0:
                node.removeAttribute('resource')

    buffer = io.StringIO()  # buffer to store modified XML
    buffer.write(doc.toString())
    buffer.flush()
    buffer.seek(0)

    if not loadUiType:
        return uic.loadUi(buffer, baseinstance=baseinstance, package=package, resource_suffix=resource_suffix)
    else:
        return uic.loadUiType(buffer, resource_suffix=resource_suffix)


def loadUIFormClass(pathUi: str, from_imports=False, resourceSuffix: str = '', fixQGISRessourceFileReferences=True,
                    _modifiedui=None):
    """
    Backport, deprecated
    """
    info = ''.join(traceback.format_stack()) + '\nUse loadUi(... , loadUiType=True) instead.'
    warnings.warn(info, DeprecationWarning)
    return loadUi(pathUi, resource_suffix=resourceSuffix, loadUiType=True)[0]


def typecheck(variable, type_):
    """
    Checks for `variable` if it is an instance of type `type_`.
    In case `variable` is a list, all list elements will be checked.
    :param variable:
    :type variable:
    :param type_:
    :type type_:
    :return:
    :rtype:
    """
    if isinstance(type_, list):
        for i in range(len(type_)):
            typecheck(variable[i], type_[i])
    else:
        assert isinstance(variable, type_)


# thanks to https://gis.stackexchange.com/questions/75533/how-to-apply-band-settings-using-gdal-python-bindings
def read_vsimem(fn):
    """
    Reads VSIMEM path as string
    :param fn: vsimem path (str)
    :return: result of gdal.VSIFReadL(1, vsileng, vsifile)
    """
    vsifile = gdal.VSIFOpenL(fn, 'r')
    gdal.VSIFSeekL(vsifile, 0, 2)
    vsileng = gdal.VSIFTellL(vsifile)
    gdal.VSIFSeekL(vsifile, 0, 0)
    return gdal.VSIFReadL(1, vsileng, vsifile)


def write_vsimem(fn: str, data: str):
    """
    Writes data to vsimem path
    :param fn: vsimem path (str)
    :param data: string to write
    :return: result of gdal.VSIFCloseL(vsifile)
    """
    '''Write GDAL vsimem files'''
    vsifile = gdal.VSIFOpenL(fn, 'w')
    size = len(data)
    gdal.VSIFWriteL(data, 1, size, vsifile)
    return gdal.VSIFCloseL(vsifile)


from collections import defaultdict
import weakref


class KeepRefs(object):
    __refs__ = defaultdict(list)

    def __init__(self):
        self.__refs__[self.__class__].append(weakref.ref(self))

    @classmethod
    def instances(cls):
        for inst_ref in cls.__refs__[cls]:
            inst = inst_ref()
            if inst is not None:
                yield inst


def appendItemsToMenu(menu, itemsToAdd):
    """
    Appends items to QMenu "menu"
    :param menu: the QMenu to be extended
    :param itemsToAdd: QMenu or [list-of-QActions-or-QMenus]
    :return: menu
    """
    assert isinstance(menu, QMenu)
    if isinstance(itemsToAdd, QMenu):
        itemsToAdd = itemsToAdd.children()[1:]
    if not isinstance(itemsToAdd, list):
        itemsToAdd = [itemsToAdd]

    for item in itemsToAdd:
        if isinstance(item, QAction):
            item.setParent(menu)
            menu.addAction(item)
            s = ""
        elif isinstance(item, QMenu):
            # item.setParent(menu)
            sub = menu.addMenu(item.title())
            sub.setIcon(item.icon())
            appendItemsToMenu(sub, item.children()[1:])
        else:
            s = ""
    return menu


def allSubclasses(cls):
    """
    Returns all subclasses of class 'cls'
    Thx to: http://stackoverflow.com/questions/3862310/how-can-i-find-all-subclasses-of-a-class-given-its-name
    :param cls:
    :return:
    """
    return cls.__subclasses__() + [g for s in cls.__subclasses__()
                                   for g in allSubclasses(s)]


def check_package(name, package=None, stop_on_error=False):
    try:
        importlib.import_module(name, package)
    except Exception as e:
        if stop_on_error:
            raise Exception('Unable to import package/module "{}"'.format(name))
        return False
    return True


def as_py_value(value, datatype: Qgis.DataType):
    """
    Converts values into a corresponding python_type
    :param value:
    :param datatype:
    :return:
    """
    if value in [None, QVariant()]:
        return None
    if datatype in [Qgis.Byte, Qgis.Int16, Qgis.Int32, Qgis.UInt16, Qgis.UInt32]:
        return int(value)
    elif datatype in [Qgis.Float32, Qgis.Float64, Qgis.CFloat32, Qgis.CFloat64]:
        return float(value)
    return value


def zipdir(pathDir, pathZip):
    """
    :param pathDir: directory to compress
    :param pathZip: path to new zipfile
    """
    # thx to https://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory
    """
    import zipfile
    assert os.path.isdir(pathDir)
    zipf = zipfile.ZipFile(pathZip, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(pathDir):
        for file in files:
            zipf.write(os.path.join(root, file))
    zipf.close()
    """
    relroot = os.path.abspath(os.path.join(pathDir, os.pardir))
    with zipfile.ZipFile(pathZip, "w", zipfile.ZIP_DEFLATED) as zip:
        for root, dirs, files in os.walk(pathDir):
            # add directory (needed for empty dirs)
            zip.write(root, os.path.relpath(root, relroot))
            for file in files:
                filename = os.path.join(root, file)
                if os.path.isfile(filename):  # regular files only
                    arcname = os.path.join(os.path.relpath(root, relroot), file)
                    zip.write(filename, arcname)


def scanResources(path=':') -> typing.Iterator[str]:
    """
    Returns all resource-paths of the Qt Resource system
    :param path:
    :type path:
    :return:
    :rtype:
    """
    D = QDirIterator(path)
    while D.hasNext():
        entry = D.next()
        if D.fileInfo().isDir():
            yield from scanResources(path=entry)
        elif D.fileInfo().isFile():
            yield D.filePath()


def datetime64(value, dpy: int = None) -> np.datetime64:
    """
    Converts an input value into a numpy.datetime64 value.
    :param value: the value to be converted into a numpy.datetime64 value
    :param dpy: days per year. If `value` is a float, it is considered to be a decimal year value.
                    By default it is assumed that the year fraction is calculated on 366 year in leap years and 365
                    in none-leap year. However, dpy can be used to use any other number of days per year to convert
                    the fraction back into days.
    :return: numpy.datetime64
    """
    if isinstance(value, np.datetime64):
        return value
    elif isinstance(value, QDate):
        return np.datetime64(value.toPyDate())
    elif isinstance(value, QDateTime):
        return np.datetime64(value.toPyDateTime())
    elif isinstance(value, (str, datetime.date, datetime.datetime)):
        return np.datetime64(value)
    elif isinstance(value, int):
        # expect a year
        return np.datetime64('{:04}-01-01'.format(value))
    elif isinstance(value, float):
        # expect a decimal year
        year = int(value)
        fraction = value - year

        if dpy is None:
            dpy = 366 if calendar.isleap(year) else 365
        else:
            assert dpy in [365, 366]
        # seconds of year
        soy = np.round(fraction * dpy * 86400).astype(int)
        return np.datetime64('{:04}-01-01'.format(year)) + np.timedelta64(soy, 's')

    if isinstance(value, np.ndarray):
        func = np.vectorize(datetime64)
        return func(value)
    else:
        raise NotImplementedError('Unsupported input value: {}'.format(value))


def day_of_year(date: np.datetime64) -> int:
    """
    Returns a date's Day-of-Year (DOY) (considering leap-years)
    :param date: numpy.datetime64
    :return: numpy.ndarray[int]
    """
    if not isinstance(date, np.datetime64):
        date = np.datetime64(date)

    dt = date - date.astype('datetime64[Y]') + 1
    return dt.astype(int)


def days_per_year(year):
    """
    Returns the days per year
    :param year:
    :return:
    """
    # is it a leap year?
    if isinstance(year, float):
        year = int(year)
    elif isinstance(year, np.number):
        year = int(year)
    elif isinstance(year, np.datetime64):
        year = year.astype(object).year
    elif isinstance(year, datetime.date):
        year = year.year
    elif isinstance(year, datetime.datetime):
        year = year.year
    elif isinstance(year, np.ndarray):
        func = np.vectorize(days_per_year)
        return func(year)

    return 366 if calendar.isleap(year) else 365

    """
    1. If the year is evenly divisible by 4, go to step 2. Otherwise, False.
    2. If the year is evenly divisible by 100, go to step 3. Otherwise, False
    3. If the year is evenly divisible by 400, True Otherwise, False

    """
    """
    Every year that is exactly divisible by four is a leap year, except for years that are exactly divisible by 100, 
    but these centurial years are leap years, if they are exactly divisible by 400.
    """
    # is_leap = (year % 4 == 0 and not year % 100 == 0) or (year % 100 == 0 and year % 400 == 0)
    # return np.where(is_leap, 366, 365)


def displayBandNames(rasterSource, bands=None, leadingBandNumber=True):
    """
    Returns a list of readable band names from a raster source.
    Will use "Band 1"  ff no band name is defined.
    :param rasterSource: QgsRasterLayer | gdal.DataSource | str
    :param bands:
    :return:
    """

    if isinstance(rasterSource, str):
        return displayBandNames(QgsRasterLayer(rasterSource), bands=bands, leadingBandNumber=leadingBandNumber)
    if isinstance(rasterSource, QgsRasterLayer):
        if not rasterSource.isValid():
            return None
        else:
            return displayBandNames(rasterSource.dataProvider(), bands=bands, leadingBandNumber=leadingBandNumber)
    if isinstance(rasterSource, gdal.Dataset):
        # use gdal.Band.GetDescription() for band name
        results = []
        if bands is None:
            bands = range(1, rasterSource.RasterCount + 1)
        for band in bands:
            b = rasterSource.GetRasterBand(band)
            name = b.GetDescription()
            if len(name) == 0:
                name = 'Band {}'.format(band)
            if leadingBandNumber:
                name = '{}:{}'.format(band, name)
            results.append(name)
        return results
    if isinstance(rasterSource, QgsRasterDataProvider):
        if rasterSource.name() == 'gdal':
            ds = gdal.Open(rasterSource.dataSourceUri())
            return displayBandNames(ds, bands=bands, leadingBandNumber=leadingBandNumber)
        else:
            # in case of WMS and other data providers use QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, rasterSource.bandCount() + 1)
            for band in bands:
                name = rasterSource.generateBandName(band)
                colorInterp = '{}'.format(rasterSource.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    name += '({})'.format(colorInterp)
                if leadingBandNumber:
                    name = '{}:{}'.format(band, name)
                results.append(name)

            return results

    return None


def defaultBands(dataset) -> list:
    """
    Returns a list of 3 default bands
    :param dataset:
    :return:
    """
    if isinstance(dataset, str):
        return defaultBands(gdal.Open(dataset))
    elif isinstance(dataset, QgsRasterDataProvider):
        return defaultBands(dataset.dataSourceUri())
    elif isinstance(dataset, QgsRasterLayer) and \
            isinstance(dataset.dataProvider(), QgsRasterDataProvider) and \
            dataset.dataProvider().name() == 'gdal':
        return defaultBands(dataset.source())
    elif isinstance(dataset, gdal.Dataset):

        # check ENVI style metadata default band definition
        for k in ['default_bands', 'default bands']:
            db = dataset.GetMetadataItem(k, str('ENVI'))
            if db != None:
                db = [int(n) for n in re.findall(r'\d+', db)]
                return db

        db = [0, 0, 0]
        cis = [gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand]
        for b in range(dataset.RasterCount):
            band = dataset.GetRasterBand(b + 1)
            assert isinstance(band, gdal.Band)
            ci = band.GetColorInterpretation()
            if ci in cis:
                db[cis.index(ci)] = b
        if db != [0, 0, 0]:
            return db

        rl = QgsRasterLayer(dataset.GetDescription())
        defaultRenderer = rl.renderer()
        if isinstance(defaultRenderer, QgsRasterRenderer):
            db = defaultRenderer.usesBands()
            if len(db) == 0:
                return [0, 1, 2]
            if len(db) > 3:
                db = db[0:3]
            db = [b - 1 for b in db]
        return db

    else:
        return [0, 0, 0]


def bandClosestToWavelength(dataset, wl, wl_unit='nm') -> int:
    """
    Returns the band index of an image raster closest to wavelength `wl`.
    :param dataset: str | gdal.Dataset
    :param wl: wavelength to search the closed band for
    :param wl_unit: unit of wavelength. Default = nm
    :return: band index | 0 if wavelength information is not provided
    """
    if isinstance(wl, str):
        assert wl.upper() in LUT_WAVELENGTH.keys(), wl
        return bandClosestToWavelength(dataset, LUT_WAVELENGTH[wl.upper()], wl_unit='nm')
    else:
        try:
            wl = float(wl)
            ds_wl, ds_wlu = parseWavelength(dataset)

            if ds_wl is None or ds_wlu is None:
                return 0

            if ds_wlu != wl_unit:
                wl = UnitLookup.convertMetricUnit(wl, wl_unit, ds_wlu)
            return int(np.argmin(np.abs(ds_wl - wl)))
        except:
            pass
    return 0


def parseBadBandList(dataset) -> typing.List[int]:
    """
    Returns the bad-band-list if it is specified explicitly
    :param dataset:
    :type dataset:
    :return: list of booleans. True = valid band, False = excluded / bad band
    :rtype:
    """
    bbl = None

    try:
        dataset = gdalDataset(dataset)
    except:
        return None
        pass

    if not isinstance(dataset, gdal.Dataset):
        return None

    # 1. search for ENVI style definition of band band list
    bblStr1 = dataset.GetMetadataItem('bbl')
    bblStr2 = dataset.GetMetadataItem('bbl', 'ENVI')

    for bblStr in [bblStr1, bblStr2]:
        if isinstance(bblStr, str) and len(bblStr) > 0:
            parts = bblStr.split(',')
            if len(parts) == dataset.RasterCount:
                bbl = [int(p) for p in parts]

    return bbl


def parseFWHM(dataset) -> typing.Tuple[np.ndarray]:
    """
    Returns the full width half maximum
    :param dataset:
    :return:
    """
    try:
        dataset = gdalDataset(dataset)
    except:
        return None

    key_positions = [('fwhm', None),
                     ('fwhm', 'ENVI')]

    if isinstance(dataset, gdal.Dataset):
        for key, domain in key_positions:
            values = dataset.GetMetadataItem(key, domain)
            if isinstance(values, str):
                values = re.sub('[{}]', '', values).strip()
                try:
                    values = np.fromstring(values, sep=',', count=dataset.RasterCount)
                    if len(values) == dataset.RasterCount:
                        return values
                except:
                    pass

        # search band by band
        values = []
        for b in range(dataset.RasterCount):
            band: gdal.Band = dataset.GetRasterBand(b + 1)
            for key, domain in key_positions:
                value = dataset.GetMetadataItem(key, domain)
                if value not in ['', None]:
                    values.append(value)
                    break
        if len(values) == dataset.RasterCount:
            return np.asarray(values)
    return None


def checkWavelength(key: str, values: str, expected: int = 1) -> np.ndarray:
    wl: np.ndarray = None
    if re.search(r'^(center[ _]*)?wavelengths?$', key, re.I):
        # remove trailing / ending { } and whitespace
        values = re.sub('[{}]', '', values).strip()
        if ',' not in values:
            sep = ' '
        else:
            sep = ','
        try:
            wl = np.asarray(values.split(sep), dtype=float)
            if len(wl) != expected:
                wl = None
            # wl = np.fromstring(values, count=expected, sep=sep)
        except ValueError as exV:
            pass
        except Exception as ex:
            pass
    return wl


def checkWavelengthUnit(key: str, value: str) -> str:
    wlu: str = None
    value = value.strip()
    if re.search(r'^wavelength[ _]?units?', key, re.I):
        # metric length units
        wlu = UnitLookup.baseUnit(value)

        if wlu is not None:
            return wlu

        if re.search(r'^Wavenumber$', value, re.I):
            wlu = '-'
        elif re.search(r'^GHz$', value, re.I):
            wlu = 'GHz'
        elif re.search(r'^MHz$', value, re.I):
            wlu = 'MHz'
        # date / time units
        elif re.search(r'^(Date|DTG|Date[_ ]?Time[_ ]?Group|Date[_ ]?Stamp|Time[_ ]?Stamp)$', value, re.I):
            wlu = 'DateTime'
        elif re.search(r'^Decimal[_ ]?Years?$', value, re.I):
            wlu = 'DecimalYear'
        elif re.search(r'^(Seconds?|s|secs?)$', value, re.I):
            wlu = 's'
        elif re.search(r'^Index$', value, re.I):
            wlu = None
        else:
            wlu = None
    return wlu


def parseWavelength(dataset) -> typing.Tuple[np.ndarray, str]:
    """
    Returns the wavelength + wavelength unit of a raster
    :param dataset:
    :return: (wl, wl_u) or (None, None), if not existing
    """

    def sort_domains(domains) -> typing.List[str]:
        if not isinstance(domains, list):
            domains = []
        return sorted(domains, key=lambda n: n != ['ENVI'])

    try:
        dataset = gdalDataset(dataset)
    except Exception:
        return None, None

    if isinstance(dataset, gdal.Dataset):
        # 1. check on raster level
        for domain in sort_domains(dataset.GetMetadataDomainList()):
            # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units

            mdDict = dataset.GetMetadata_Dict(domain)

            domainWLU: str = None
            domainWL: np.ndarray = None
            # search domain
            for key, values in mdDict.items():
                if domainWL is None:
                    domainWL = checkWavelength(key, values, expected=dataset.RasterCount)
                if domainWLU is None:
                    domainWLU = checkWavelengthUnit(key, values)

            if isinstance(domainWL, np.ndarray) and isinstance(domainWLU, str):
                if domain == 'FORCE' and domainWLU == 'DecimalYear':
                    # make decimal-year values leap-year sensitive
                    domainWL = convertDateUnit(datetime64(domainWL, dpy=365), 'DecimalYear')

                if len(domainWL) > dataset.RasterCount:
                    domainWL = domainWL[0:dataset.RasterCount]

                return domainWL, domainWLU

        # 2. check on band level. collect wl from each single band
        # first domain that defines wl and wlu is prototyp domain for all other bands

        wl = []  # list of wavelength values
        wlu: str = None  # wavelength unit string
        wlDomain: str = None  # the domain in which the WL and WLU are defined
        wlKey: str = None  # key that stores the wavelength value
        wluKey: str = None  # key that stores the wavelength unit

        for b in range(dataset.RasterCount):
            band: gdal.Band = dataset.GetRasterBand(b + 1)
            if b == 0:
                for domain in sort_domains(band.GetMetadataDomainList()):
                    # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units
                    domainWL = domainWLU = None

                    mdDict = band.GetMetadata_Dict(domain)

                    for key, values in mdDict.items():
                        if domainWLU is None:
                            domainWLU = checkWavelengthUnit(key, values)
                            if domainWLU:
                                wluKey = key

                        if domainWL is None:
                            domainWL = checkWavelength(key, values, expected=1)
                            if isinstance(domainWL, np.ndarray):
                                wlKey = key

                    if isinstance(domainWL, np.ndarray) and isinstance(domainWLU, str):
                        wlDomain = domain
                        wlu = domainWLU
                        wl.append(domainWL[0])

                if len(wl) == 0:
                    # we did not found a WL + WLU for the 1st band. stop searching and return
                    return None, None
            else:
                bandWLU = checkWavelengthUnit(wluKey, band.GetMetadataItem(wluKey, wlDomain))
                bandWL = checkWavelength(wlKey, band.GetMetadataItem(wlKey, wlDomain), expected=1)

                if bandWLU != wlu or bandWL is None:
                    print(f'{dataset.GetDescription()}: inconsistent use of metadata key {wluKey} per band')
                    return None, None
                wl.append(bandWL[0])

        if len(wl) == 0:
            return None, None

        wl = np.asarray(wl)
        if domain == 'FORCE' and wlu == 'DecimalYear':
            # make decimal-year values leap-year sensitive
            wl = UnitLookup.convertDateUnit(datetime64(wl, dpy=365), 'DecimalYear')

        return wl, wlu
    else:
        return None, None


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def qgisAppQgisInterface() -> QgisInterface:
    """
    Returns the QgisInterface of the QgisApp in case everything was started from within the QGIS Main Application
    :return: QgisInterface | None in case the qgis.utils.iface points to another QgisInterface (e.g. the EnMAP-Box itself)
    """
    try:
        import qgis.utils
        if not isinstance(qgis.utils.iface, QgisInterface):
            return None
        mainWindow = qgis.utils.iface.mainWindow()
        if not isinstance(mainWindow, QMainWindow) or mainWindow.objectName() != 'QgisApp':
            return None
        return qgis.utils.iface
    except:
        return None


def chunks(iterable, size=10):
    """
    Returns list or generator output as chunks
    Example taken from: https://stackoverflow.com/a/24527424
    :param iterable:
    :param size:
    :return:
    """
    iterator = iter(iterable)
    for first in iterator:
        yield itertools.chain([first], itertools.islice(iterator, size - 1))


def getDOMAttributes(elem) -> dict:
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[attr.nodeName()] = attr.nodeValue()
    return values


def fileSizeString(num, suffix='B', div=1000) -> str:
    """
    Returns a human-readable file size string.
    thanks to Fred Cirera
    http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    :param num: number in bytes
    :param suffix: 'B' for bytes by default.
    :param div: divisor of num, 1000 by default.
    :return: the file size string
    """
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < div:
            return "{:3.1f}{}{}".format(num, unit, suffix)
        num /= div
    return "{:.1f} {}{}".format(num, unit, suffix)


def geo2pxF(geo, gt) -> QPointF:
    """
    Returns the pixel position related to a Geo-Coordinate in floating point precision.
    :param geo: Geo-Coordinate as QgsPoint
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html
    :return: pixel position as QPointF
    """
    assert isinstance(geo, QgsPointXY)
    # see http://www.gdal.org/gdal_datamodel.html
    px = (geo.x() - gt[0]) / gt[1]  # x pixel
    py = (geo.y() - gt[3]) / gt[5]  # y pixel
    return QPointF(px, py)


def geo2px(geo, gt) -> QPoint:
    """
    Returns the pixel position related to a Geo-Coordinate as integer number.
    Floating-point coordinate are casted to integer coordinate, e.g. the pixel coordinate (0.815, 23.42) is returned as (0,23)
    :param geo: Geo-Coordinate as QgsPointXY
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html or
          gdal.Dataset or QgsRasterLayer
    :return: pixel position as QPpint
    """

    if isinstance(gt, QgsRasterLayer):
        return geo2px(geo, layerGeoTransform(gt))
    elif isinstance(gt, gdal.Dataset):
        return geo2px(gt.GetGeoTransform())
    else:
        px = geo2pxF(geo, gt)
        return QPoint(int(px.x()), int(px.y()))


def check_vsimem() -> bool:
    """
    Checks if the gdal/ogr vsimem is available to the QGIS API
    (might be not the case for QGIS
    :return: bool
    """
    result = False
    try:
        from osgeo import gdal
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer
        import uuid
        # create an 2x2x1 in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        assert isinstance(driver, gdal.Driver)
        path = f'/vsimem/inmemorytestraster.{uuid.uuid4()}.tif'

        dataSet: gdal.Dataset = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
        assert isinstance(dataSet, gdal.Dataset)
        drv: gdal.Driver = dataSet.GetDriver()
        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        assert isinstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        assert isinstance(layer, QgsRasterLayer)
        result = layer.isValid()
        del layer
        drv.Delete(path)

    except Exception as ex:
        return False
    return result


def layerGeoTransform(rasterLayer: QgsRasterLayer) -> typing.Tuple[float, float, float, float, float, float]:
    """
    Returns the geo-transform vector from a QgsRasterLayer.
    See https://www.gdal.org/gdal_datamodel.html
    :param rasterLayer: QgsRasterLayer
    :return: [array]
    """
    assert isinstance(rasterLayer, QgsRasterLayer)
    ext = rasterLayer.extent()
    x0 = ext.xMinimum()
    y0 = ext.yMaximum()

    gt = (x0, rasterLayer.rasterUnitsPerPixelX(), 0, y0, \
          0, -1 * rasterLayer.rasterUnitsPerPixelY())
    return gt


def osrSpatialReference(input) -> osr.SpatialReference:
    """
    Returns the input as osr.SpatialReference
    :param input: any
    :return: osr.SpatialReference
    """
    srs: osr.SpatialReference = osr.SpatialReference()
    if isinstance(input, osr.SpatialReference):
        return input
    if isinstance(input, gdal.Dataset):
        return input.GetSpatialRef()
    if isinstance(input, ogr.Layer):
        return input.GetSpatialRef()
    if isinstance(input, ogr.DataSource):
        return osrSpatialReference(input.GetLayer(0))
    if isinstance(input, gdal.Band):
        return osrSpatialReference(input.GetDataset())
    if isinstance(input, QgsMapLayer):
        return osrSpatialReference(input.crs())

    if isinstance(input, QgsCoordinateReferenceSystem):
        srs.ImportFromWkt(input.toWkt())
    elif isinstance(input, str):
        wkt = osr.GetUserInputAsWKT(input)
        if isinstance(wkt, str):
            srs.ImportFromWkt(wkt)
    else:
        raise Exception(f'Unable to convert {str(input)} to osr.SpatialReference')

    return srs


def px2geocoordinates(raster, target_srs=None, pxCenter: bool = True) -> typing.Tuple[np.ndarray, np.ndarray]:
    """
    Returns the pixel positions as geo-coordinates
    :param raster: any, must be readible to as gdal.Dataset
    :param target_srs: any, must be convertable to osr.SpatialReference
    :return:
    """
    # returns pixel coordinates in arrays with the x and y pixel coodinates in target_srs

    raster: gdal.Dataset = gdalDataset(raster)
    if target_srs:
        target_srs = osrSpatialReference(target_srs)
    else:
        target_srs = osrSpatialReference(raster)

    gt = raster.GetGeoTransform()
    indices = np.indices((raster.RasterYSize, raster.RasterXSize))
    if pxCenter:
        indices = indices + 0.5

    geo_x = gt[0] + indices[1, :, :] * gt[1] + indices[1, :, :] * gt[2]
    geo_y = gt[3] + indices[0, :, :] * gt[4] + indices[0, :, :] * gt[5]

    if not target_srs.IsSame(raster.GetSpatialRef()):
        drv = gdal.GetDriverByName('MEM')
        dsMEM: gdal.Dataset = drv.Create('', raster.RasterXSize, raster.RasterYSize, 3, gdal.GDT_Float64)
        dsMEM.GetRasterBand(1).WriteArray(geo_x)
        dsMEM.GetRasterBand(2).WriteArray(geo_y)

        transformer = gdal.Transformer(None, None, [f'SRC_SRS={raster.GetSpatialRef().ExportToProj4()}',
                                                    f'DST_SRS={target_srs.ExportToProj4()}'])
        status = transformer.TransformGeolocations(dsMEM.GetRasterBand(1),
                                                   dsMEM.GetRasterBand(2),
                                                   dsMEM.GetRasterBand(3))
        if status != ogr.OGRERR_NONE:
            raise Exception(f'Error transforming coordinates: {gdal.GetLastErrorMsg()}')

        geo_x = dsMEM.GetRasterBand(1).ReadAsArray()
        geo_y = dsMEM.GetRasterBand(2).ReadAsArray()
    return geo_x, geo_y


def px2geo(px: QPoint, gt, pxCenter: bool = True) -> QgsPointXY:
    """
    Converts a pixel coordinate into a geo-coordinate
    :param px: QPoint() with pixel coordinates
    :param gt: geo-transformation
    :param pxCenter: True (default) to return geo-coordinate of pixel center,
                     False to return the pixel's upper-left edge.
    :return:
    """

    # see http://www.gdal.org/gdal_datamodel.html

    gx = gt[0] + px.x() * gt[1] + px.y() * gt[2]
    gy = gt[3] + px.x() * gt[4] + px.y() * gt[5]

    if pxCenter:
        p2 = px2geo(QPoint(px.x() + 1, px.y() + 1), gt, pxCenter=False)

        gx = 0.5 * (gx + p2.x())
        gy = 0.5 * (gy + p2.y())

    return QgsPointXY(gx, gy)


class SpatialPoint(QgsPointXY):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def readXml(node: QDomNode):
        node_crs = node.firstChildElement('SpatialPointCrs')
        crs = QgsCoordinateReferenceSystem()
        if not node_crs.isNull():
            crs.readXml(node_crs)
        point = QgsGeometry.fromWkt(node.firstChildElement('SpatialPoint').text()).asPoint()
        return SpatialPoint(crs, point)

    @staticmethod
    def fromMapCanvasCenter(mapCanvas: QgsMapLayer):
        assert isinstance(mapCanvas, QgsMapCanvas)
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialPoint(crs, mapCanvas.center())

    @staticmethod
    def fromMapLayerCenter(mapLayer: QgsMapLayer):
        assert isinstance(mapLayer, QgsMapLayer) and mapLayer.isValid()
        crs = mapLayer.crs()
        return SpatialPoint(crs, mapLayer.extent().center())

    @staticmethod
    def fromSpatialExtent(spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        crs = spatialExtent.crs()
        return SpatialPoint(crs, spatialExtent.center())

    def __init__(self, crs, *args):
        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialPoint, self).__init__(*args)
        self.mCrs = crs

    def __hash__(self):
        return hash(str(self))

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def toPixelPosition(self, rasterDataSource, allowOutOfRaster=False):
        """
        Returns the pixel position of this SpatialPoint within the rasterDataSource
        :param rasterDataSource: gdal.Dataset
        :param allowOutOfRaster: set True to return out-of-raster pixel positions, e.g. QPoint(-1,0)
        :return: the pixel position as QPoint
        """
        ds = gdalDataset(rasterDataSource)
        ns, nl = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()

        pt = self.toCrs(ds.GetProjection())
        if pt is None:
            return None

        px = geo2px(pt, gt)
        if not allowOutOfRaster:
            if px.x() < 0 or px.x() >= ns:
                return None
            if px.y() < 0 or px.y() >= nl:
                return None
        return px

    def writeXml(self, node: QDomNode, doc: QDomDocument):
        node_geom = doc.createElement('SpatialPoint')
        node_geom.appendChild(doc.createTextNode(self.asWkt()))
        node_crs = doc.createElement('SpatialPointCrs')
        self.crs().writeXml(node_crs, doc)
        node.appendChild(node_geom)
        node.appendChild(node_crs)

    def toCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        pt = QgsPointXY(self)

        if self.mCrs != crs:
            pt = saveTransform(pt, self.mCrs, crs)

        return SpatialPoint(crs, pt) if pt else None

    def __reduce_ex__(self, protocol):
        return self.__class__, (self.crs().toWkt(), self.x(), self.y()), {}

    def __eq__(self, other):
        if not isinstance(other, SpatialPoint):
            return False
        return self.x() == other.x() and \
               self.y() == other.y() and \
               self.crs() == other.crs()

    def __copy__(self):
        return SpatialPoint(self.crs(), self.x(), self.y())

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return '{} {} {}'.format(self.x(), self.y(), self.crs().authid())


def findParent(qObject, parentType, checkInstance=False):
    parent = qObject.parent()
    if checkInstance:
        while parent != None and not isinstance(parent, parentType):
            parent = parent.parent()
    else:
        while parent != None and type(parent) != parentType:
            parent = parent.parent()
    return parent


def createCRSTransform(src: QgsCoordinateReferenceSystem, dst: QgsCoordinateReferenceSystem):
    """

    :param src:
    :param dst:
    :return:
    """
    assert isinstance(src, QgsCoordinateReferenceSystem)
    assert isinstance(dst, QgsCoordinateReferenceSystem)
    t = QgsCoordinateTransform()
    t.setSourceCrs(src)
    t.setDestinationCrs(dst)
    return t


def saveTransform(geom, crs1, crs2):
    """

    :param geom:
    :param crs1:
    :param crs2:
    :return:
    """
    assert isinstance(crs1, QgsCoordinateReferenceSystem)
    assert isinstance(crs2, QgsCoordinateReferenceSystem)

    result = None
    if isinstance(geom, QgsRectangle):
        if geom.isEmpty():
            return None

        transform = QgsCoordinateTransform()
        transform.setSourceCrs(crs1)
        transform.setDestinationCrs(crs2)
        try:
            rect = transform.transformBoundingBox(geom);
            result = SpatialExtent(crs2, rect)
        except:
            print('Can not transform from {} to {} on rectangle {}'.format( \
                crs1.description(), crs2.description(), str(geom)), file=sys.stderr)

    elif isinstance(geom, QgsPointXY):

        transform = QgsCoordinateTransform();
        transform.setSourceCrs(crs1)
        transform.setDestinationCrs(crs2)
        try:
            pt = transform.transform(geom);
            result = SpatialPoint(crs2, pt)
        except:
            print('Can not transform from {} to {} on QgsPointXY {}'.format( \
                crs1.description(), crs2.description(), str(geom)), file=sys.stderr)
    return result


def scaledUnitString(num, infix=' ', suffix='B', div=1000):
    """
    Returns a human-readable file size string.
    thanks to Fred Cirera
    http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    :param num: number in bytes
    :param suffix: 'B' for bytes by default.
    :param div: divisor of num, 1000 by default.
    :return: the file size string
    """
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < div:
            return "{:3.1f}{}{}{}".format(num, infix, unit, suffix)
        num /= div
    return "{:.1f}{}{}{}".format(num, infix, unit, suffix)


class SpatialExtent(QgsRectangle):
    """
    Object that combines a QgsRectangle and QgsCoordinateReferenceSystem
    """

    @staticmethod
    def readXml(node: QDomNode):
        node_crs = node.firstChildElement('SpatialExtentCrs')
        crs = QgsCoordinateReferenceSystem()
        if not node_crs.isNull():
            crs.readXml(node_crs)
        rectangle = QgsRectangle.fromWkt(node.firstChildElement('SpatialExtent').text())
        return SpatialExtent(crs, rectangle)

    @staticmethod
    def fromMapCanvas(mapCanvas, fullExtent: bool = False):
        assert isinstance(mapCanvas, QgsMapCanvas)

        if fullExtent:
            extent = mapCanvas.fullExtent()
        else:
            extent = mapCanvas.extent()
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialExtent(crs, extent)

    @staticmethod
    def world():
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        ext = QgsRectangle(-180, -90, 180, 90)
        return SpatialExtent(crs, ext)

    @staticmethod
    def fromRasterSource(pathSrc):
        ds = gdalDataset(pathSrc)
        assert isinstance(ds, gdal.Dataset)
        ns, nl = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        xValues = []
        yValues = []
        for x in [0, ns]:
            for y in [0, nl]:
                px = px2geo(QPoint(x, y), gt, pxCenter=False)
                xValues.append(px.x())
                yValues.append(px.y())

        return SpatialExtent(crs, min(xValues), min(yValues),
                             max(xValues), max(yValues))

    @staticmethod
    def fromLayer(mapLayer):
        assert isinstance(mapLayer, QgsMapLayer)
        extent = mapLayer.extent()
        crs = mapLayer.crs()
        return SpatialExtent(crs, extent)

    def __init__(self, crs, *args):
        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialExtent, self).__init__(*args)
        self.mCrs = crs

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def writeXml(self, node: QDomNode, doc: QDomDocument):
        node_geom = doc.createElement('SpatialExtent')
        node_geom.appendChild(doc.createTextNode(self.asWktPolygon()))
        node_crs = doc.createElement('SpatialExtentCrs')
        self.crs().writeXml(node_crs, doc)
        #if QgsCoordinateReferenceSystem(self.crs().authid()) == self.crs():
        #    node_crs.appendChild(doc.createTextNode(self.crs().authid()))
        #else:
        #    node_crs.appendChild(doc.createTextNode(self.crs().toWkt()))
        node.appendChild(node_geom)
        node.appendChild(node_crs)

    def toCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        box = QgsRectangle(self)
        if self.mCrs != crs:
            box = saveTransform(box, self.mCrs, crs)
        return SpatialExtent(crs, box) if box else None

    def spatialCenter(self):
        return SpatialPoint(self.crs(), self.center())

    def combineExtentWith(self, *args):
        if args is None:
            return
        elif isinstance(args[0], SpatialExtent):
            extent2 = args[0].toCrs(self.crs())
            self.combineExtentWith(QgsRectangle(extent2))
        else:
            super(SpatialExtent, self).combineExtentWith(*args)

        return self

    def setCenter(self, centerPoint, crs=None):
        """
        Shift the center of this rectange
        :param centerPoint:
        :param crs:
        :return:
        """
        if crs and crs != self.crs():
            trans = QgsCoordinateTransform(crs, self.crs())
            centerPoint = trans.transform(centerPoint)

        delta = centerPoint - self.center()
        self.setXMaximum(self.xMaximum() + delta.x())
        self.setXMinimum(self.xMinimum() + delta.x())
        self.setYMaximum(self.yMaximum() + delta.y())
        self.setYMinimum(self.yMinimum() + delta.y())

        return self

    def __cmp__(self, other):
        if other is None:
            return 1
        s = ""

    def upperRightPt(self) -> QgsPointXY:
        """
        Returns the upper-right coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperRight())

    def upperLeftPt(self) -> QgsPointXY:
        """
        Returns the upper-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperLeft())

    def lowerRightPt(self) -> QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerRight())

    def lowerLeftPt(self) -> QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerLeft())

    def upperRight(self) -> tuple:
        """
        Returns the upper-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMaximum()

    def upperLeft(self) -> tuple:
        """
        Returns the upper-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self) -> tuple:
        """
        Returns the lower-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMinimum()

    def lowerLeft(self) -> tuple:
        """
        Returns the lower-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMinimum()

    def __eq__(self, other) -> bool:
        """
        Checks for equality
        :param other: SpatialExtent
        :return: bool
        """
        if not isinstance(other, SpatialExtent):
            return False
        else:
            return self.toString() == other.toString()

    def __sub__(self, other):
        raise NotImplementedError()

    def __mul__(self, other):
        raise NotImplementedError()

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

    def __reduce__(self):

        return self.__class__, ('',), self.__getstate__()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('mCrs')
        state['_crs_'] = self.crs().toWkt()
        state['_xmin_'] = self.xMinimum()
        state['_xmax_'] = self.xMaximum()
        state['_ymin_'] = self.yMinimum()
        state['_ymax_'] = self.yMaximum()
        return state

    def __setstate__(self, state):
        self.setCrs(QgsCoordinateReferenceSystem(state.pop('_crs_')))
        self.setXMinimum(state.pop('_xmin_'))
        self.setXMaximum(state.pop('_xmax_'))
        self.setYMinimum(state.pop('_ymin_'))
        self.setYMaximum(state.pop('_ymax_'))
        self.__dict__.update(state)

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return self.__repr__()

    def __repr__(self) -> str:
        """
        Returns a representation string
        :return: str
        """

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())


def setToolButtonDefaultActionMenu(toolButton: QToolButton, actions: list):
    if isinstance(toolButton, QAction):
        for btn in toolButton.parent().findChildren(QToolButton):
            assert isinstance(btn, QToolButton)
            if btn.defaultAction() == toolButton:
                toolButton = btn
                break

    assert isinstance(toolButton, QToolButton)
    toolButton.setPopupMode(QToolButton.MenuButtonPopup)
    menu = QMenu(toolButton)
    for i, a in enumerate(actions):
        assert isinstance(a, QAction)
        a.setParent(menu)
        menu.addAction(a)
        if i == 0:
            toolButton.setDefaultAction(a)

    menu.triggered.connect(toolButton.setDefaultAction)
    toolButton.setMenu(menu)


class SelectMapLayersDialog(QgsDialog):
    class LayerDescription(object):

        def __init__(self, info: str, filters: QgsMapLayerProxyModel.Filters, allowEmptyLayer=False):
            self.labelText = info
            self.filters = filters
            self.allowEmptyLayer = allowEmptyLayer

    def __init__(self, *args, layerDescriptions: list = None, **kwds):
        super(SelectMapLayersDialog, self).__init__(buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.setWindowTitle('Select layer(s)')

        gl = QGridLayout()
        assert isinstance(gl, QGridLayout)
        self.mGrid = gl
        gl.setSpacing(6)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 1)
        self.layout().addLayout(gl)

        self.mMapLayerBoxes = []

        self.buttonBox().button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

    def selectMapLayer(self, i, layer):
        """
        Selects the QgsMapLayer layer in QgsMapLayerComboBox.
        :param i: int
        :param layer: QgsMapLayer.
        """
        if isinstance(i, QgsMapLayerComboBox):
            i = self.mMapLayerBoxes.index(i)
        box = self.mMapLayerBoxes[i]
        assert isinstance(layer, QgsMapLayer)
        assert isinstance(box, QgsMapLayerComboBox)
        QgsProject.instance().addMapLayer(layer)

        for i in range(box.count()):
            l = box.layer(i)
            if isinstance(l, QgsMapLayer) and l == layer:
                box.setCurrentIndex(i)
                break

    def exec_(self):

        if len(self.mMapLayerBoxes) == 0:
            self.addLayerDescription('Map Layer', QgsMapLayerProxyModel.All)
        super(SelectMapLayersDialog, self).exec_()

    def addLayerDescription(self, info: str,
                            filters: QgsMapLayerProxyModel.Filters,
                            allowEmptyLayer=False,
                            layerDescription=None) -> QgsMapLayerComboBox:
        """
        Adds a map layer description
        :param info: description text
        :param filters: map layer filters
        :param allowEmptyLayer: bool
        :param layerDescription: SelectMapLayersDialog.LayerDescription (overwrites the other attributes)
        :return: the QgsMapLayerComboBox that relates to this layer description
        """

        if not isinstance(layerDescription, SelectMapLayersDialog.LayerDescription):
            layerDescription = SelectMapLayersDialog.LayerDescription(info, filters, allowEmptyLayer=allowEmptyLayer)

        assert isinstance(layerDescription, SelectMapLayersDialog.LayerDescription)
        i = self.mGrid.rowCount()

        layerbox = QgsMapLayerComboBox(self)
        layerbox.setFilters(layerDescription.filters)
        self.mMapLayerBoxes.append(layerbox)
        self.mGrid.addWidget(QLabel(layerDescription.labelText, self), i, 0)
        self.mGrid.addWidget(layerbox, i, 1)

        return layerbox

    def mapLayers(self) -> list:
        """
        Returns the user's list of map layers
        :return: [list-of-QgsMapLayers]
        """
        return [b.currentLayer() for b in self.mMapLayerBoxes]


class QgsTaskMock(QgsTask):
    """
    A mocked QgsTask
    """

    def __init__(self):
        super(QgsTaskMock, self).__init__()
