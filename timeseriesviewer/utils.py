# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import os, sys, math, re, io, fnmatch, uuid


from collections import defaultdict
from qgis.core import *
from qgis.gui import *
import qgis.utils
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtXml import QDomDocument
from PyQt5 import uic
from osgeo import gdal, ogr

import weakref
import numpy as np

jp = os.path.join
dn = os.path.dirname

from timeseriesviewer import DIR_UI, DIR_REPO
from timeseriesviewer import messageLog
import timeseriesviewer
MAP_LAYER_STORES = [QgsProject.instance()]

def qgisInstance():
    """
    If existent, returns the QGIS Instance.
    :return: QgisInterface | None
    """

    from timeseriesviewer.main import TimeSeriesViewer
    if isinstance(qgis.utils.iface, QgisInterface) and \
        not isinstance(qgis.utils.iface, TimeSeriesViewer):
        return qgis.utils.iface
    else:
        return None


def findMapLayer(layer)->QgsMapLayer:
    """
    Returns the first QgsMapLayer out of all layers stored in MAP_LAYER_STORES that matches layer
    :param layer: str layer id or layer name or QgsMapLayer
    :return: QgsMapLayer
    """
    if isinstance(layer, QgsMapLayer):
        return layer
    elif isinstance(layer, str):
        #check for IDs
        for store in MAP_LAYER_STORES:
            l = store.mapLayer(layer)
            if isinstance(l, QgsMapLayer):
                return l
        #check for name
        for store in MAP_LAYER_STORES:
            l = store.mapLayersByName(layer)
            if len(l) > 0:
                return l[0]
    return None


def file_search(rootdir, pattern, recursive=False, ignoreCase=False, directories=False, fullpath=False):
    """
    Searches for files
    :param rootdir: root directory to search for files.
    :param pattern: wildcard ("my*files.*") or regular expression to describe the file name.
    :param recursive: set True to search recursively.
    :param ignoreCase: set True to ignore character case.
    :param directories: set True to search for directories instead of files.
    :return: [list-of-paths]
    """
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))

    for entry in os.scandir(rootdir):
        if directories == False:
            if entry.is_file():
                if fullpath:
                    name = entry.path
                else:
                    name =  os.path.basename(entry.path)
                if isinstance(pattern, regType):
                    if pattern.search(name):
                        yield entry.path.replace('\\','/')

                elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                        or fnmatch.fnmatch(name, pattern):
                    yield entry.path.replace('\\','/')
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
                        yield entry.path.replace('\\','/')

                elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                        or fnmatch.fnmatch(name, pattern):
                    yield entry.path.replace('\\','/')






NEXT_COLOR_HUE_DELTA_CON = 10
NEXT_COLOR_HUE_DELTA_CAT = 100
def nextColor(color, mode='cat'):
    """
    Returns another color
    :param color: the previous color
    :param mode: 'cat' - for categorical color jump (next color looks pretty different to previous)
                 'con' - for continuous color jump (next color looks similar to previous)
    :return:
    """
    assert mode in ['cat','con']
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
    while hue > 360:
        hue -= 360

    return QColor.fromHsl(hue, sat, value, alpha)





def createQgsField(name : str, exampleValue, comment:str=None):
    """
    Create a QgsField using a Python-datatype exampleValue
    :param name: field name
    :param exampleValue: value, can be any type
    :param comment: (optional) field comment.
    :return: QgsField
    """
    t = type(exampleValue)
    if t in [str]:
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif t in [bool]:
        return QgsField(name, QVariant.Bool, 'int', len=1, comment=comment)
    elif t in [int, np.int32, np.int64]:
        return QgsField(name, QVariant.Int, 'int', comment=comment)
    elif t in [float, np.double, np.float16, np.float32, np.float64]:
        return QgsField(name, QVariant.Double, 'double', comment=comment)
    elif isinstance(exampleValue, np.ndarray):
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif isinstance(exampleValue, list):
        assert len(exampleValue) > 0, 'need at least one value in provided list'
        v = exampleValue[0]
        prototype = createQgsField(name, v)
        subType = prototype.type()
        typeName = prototype.typeName()
        return QgsField(name, QVariant.List, typeName, comment=comment, subType=subType)
    else:
        raise NotImplemented()



def setQgsFieldValue(feature:QgsFeature, field, value):
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
    else:
        raise NotImplementedError()

   # i = feature.fieldNameIndex(field.name())
    feature.setAttribute(field.name(), value)


def appendItemsToMenu(menu, itemsToAdd):
    """
    Appends items to QMenu "menu"
    :param menu: the QMenu to be extended
    :param itemsToAdd: QMenu or [list-of-QActions-or-QMenus]
    :return: menu
    """
    assert isinstance(menu, QMenu)
    if isinstance(itemsToAdd, QMenu):
        itemsToAdd = itemsToAdd.children()
    if not isinstance(itemsToAdd, list):
        itemsToAdd = [itemsToAdd]
    for item in itemsToAdd:
        if isinstance(item, QAction):
            #item.setParent(menu)


            a = menu.addAction(item.text(), item.triggered, item.shortcut())
            a.setEnabled(item.isEnabled())
            a.setIcon(item.icon())
            menu.addAction(a)
            s = ""
        elif isinstance(item, QMenu):
            item.setParent(menu)
            menu.addMenu(menu)
        else:
            s = ""

    return menu


def toVectorLayer(src) -> QgsVectorLayer:
    """
    Returns a QgsRasterLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsRasterLayer or None
    """
    lyr = None
    try:
        if isinstance(src, str):
            lyr = QgsVectorLayer(src)
        elif isinstance(src, QgsMimeDataUtils.Uri):
            lyr, b = src.vectorLayer()
            if not b:
                lyr = None
        if isinstance(src, ogr.DataSource):
            path = src.GetDescription()
            bn = os.path.basename(path)
            lyr = QgsVectorLayer(path, bn, 'ogr')
        elif isinstance(src, QgsVectorLayer):
            lyr = src

    except Exception as ex:
        print(ex)

    return lyr

def toDataset(src, readonly=True)->gdal.Dataset:
    """
    Returns a gdal.Dataset if it can be extracted from src
    :param src: input source
    :param readonly: bool, true by default, set False to upen the gdal.Dataset in update mode
    :return: gdal.Dataset
    """
    ga = gdal.GA_ReadOnly if readonly else gdal.GA_Update
    if isinstance(src, str):
        return gdal.Open(src, ga)
    elif isinstance(src, QgsRasterLayer) and src.dataProvider().name() == 'gdal':
        return toDataset(src.source(), readonly=readonly)
    elif isinstance(src, gdal.Dataset):
        return src
    else:
        return None

def toQgsMimeDataUtilsUri(mapLayer:QgsMapLayer)->QgsMimeDataUtils.Uri:
    """
    Creates a QgsMimeDataUtils.Uri that describes the QgsMapLayer `mapLayer`
    :param mapLayer: QgsMapLayer
    :return: QgsMimeDataUtils.Uri
    """
    assert isinstance(mapLayer, QgsMapLayer)
    uri = QgsMimeDataUtils.Uri()
    uri.uri = mapLayer.source()
    uri.name = mapLayer.name()
    if uri.name == '':
        uri.name = os.path.basename(uri.uri)
    uri.providerKey = mapLayer.dataProvider().name()

    if isinstance(mapLayer, QgsRasterLayer):
        uri.layerType = 'raster'
    elif isinstance(mapLayer, QgsVectorLayer):
        uri.layerType = 'vector'
    elif isinstance(mapLayer, QgsPluginLayer):
        uri.layerType = 'plugin'
    else:
        raise NotImplementedError()
    return uri


def toMapLayer(src)->QgsMapLayer:
    """
    Return a QgsMapLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsMapLayer
    """
    lyr = toRasterLayer(src)
    if isinstance(lyr, QgsMapLayer):
        return lyr
    lyr = toVectorLayer(src)
    if isinstance(lyr, QgsMapLayer):
        return lyr
    return lyr

def toRasterLayer(src) -> QgsRasterLayer:
    """
    Returns a QgsRasterLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsRasterLayer or None
    """
    lyr = None
    try:
        if isinstance(src, str):
            lyr = QgsRasterLayer(src)
        elif isinstance(src, QgsMimeDataUtils.Uri):
            lyr, b = src.rasterLayer('')
            if not b:
                lyr = None
        elif isinstance(src, gdal.Dataset):
            lyr = QgsRasterLayer(src.GetFileList()[0], '', 'gdal')
        elif isinstance(src, QgsMapLayer) :
            lyr = src
        elif isinstance(src, gdal.Band):
            return toRasterLayer(src.GetDataset())

    except Exception as ex:
        print(ex)

    if isinstance(lyr, QgsRasterLayer) and lyr.isValid():
        return lyr
    else:
        return None


def allSubclasses(cls):
    """
    Returns all subclasses of class 'cls'
    Thx to: http://stackoverflow.com/questions/3862310/how-can-i-find-all-subclasses-of-a-class-given-its-name
    :param cls:
    :return:
    """
    return cls.__subclasses__() + [g for s in cls.__subclasses__()
                                   for g in allSubclasses(s)]

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
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < div:
            return "{:3.1f}{}{}{}".format(num, infix, unit, suffix)
        num /= div
    return "{:.1f}{}{}{}".format(num, infix, unit, suffix)


class SpatialPoint(QgsPointXY):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def fromMapCanvasCenter(mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialPoint(crs, mapCanvas.center())

    @staticmethod
    def fromMapLayerCenter(mapLayer:QgsMapLayer):
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

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return SpatialPoint(self.crs(), self.x(), self.y())

    def __str__(self):
        return self.__repr__()

    def __repr__(self):

        if self.crs().mapUnits() == QgsUnitTypes.DistanceDegrees:
            return '{:.1f} {:.1f} {}'.format(self.x(), self.y(), self.crs().authid())
        else:
            return '{:.5f} {:.5f} {:}'.format(self.x(), self.y(), self.crs().authid())



def findParent(qObject, parentType, checkInstance = False):
    parent = qObject.parent()
    if checkInstance:
        while parent != None and not isinstance(parent, parentType):
            parent = parent.parent()
    else:
        while parent != None and type(parent) != parentType:
            parent = parent.parent()
    return parent

def saveTransform(geom, crs1, crs2):
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
            rect = transform.transformBoundingBox(geom)
            result = SpatialExtent(crs2, rect)
        except:
            messageLog('Can not transform from {} to {} on rectangle {}'.format( \
                crs1.description(), crs2.description(), str(geom)))

    elif isinstance(geom, QgsPointXY):

        transform = QgsCoordinateTransform()
        transform.setSourceCrs(crs1)
        transform.setDestinationCrs(crs2)
        try:
            pt = transform.transform(geom);
            result = SpatialPoint(crs2, pt)
        except:
            messageLog('Can not transform from {} to {} on QgsPointXY {}'.format( \
                crs1.description(), crs2.description(), str(geom)))
    return result


def gdalDataset(pathOrDataset, eAccess=gdal.GA_ReadOnly):
    """

    :param pathOrDataset: path or gdal.Dataset
    :return: gdal.Dataset
    """
    if not isinstance(pathOrDataset, gdal.Dataset):
        pathOrDataset = gdal.Open(pathOrDataset, eAccess)
    assert isinstance(pathOrDataset, gdal.Dataset)
    return pathOrDataset


def geo2pxF(geo, gt):
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
    return QPointF(px,py)

def createGeoTransform(gsd, ul_x, ul_y):
    """
    Create a GDAL Affine GeoTransform vector for north-up images.
    See http://www.gdal.org/gdal_datamodel.html for details
    :param gsd: ground-sampling-distance / pixel-size
    :param ul_x: upper-left X
    :param ul_y: upper-left Y
    :return: (tuple)
    """
    if isinstance(gsd, tuple) or isinstance(gsd, list):
        gt1 = gsd[0] #pixel width
        gt5 = gsd[1] #pixel height
    else:
        gsd = float(gsd)
        gt1 = gt5 = gsd #pixel width == pixel height

    gt0 = ul_x
    gt3 = ul_y

    gt2 = gt4 = 0

    return (gt0, gt1, gt2, gt3, gt4, gt5)

def geo2px(geo, gt):
    """
    Returns the pixel position related to a Geo-Coordinate as integer number.
    Floating-point coordinate are casted to integer coordinate, e.g. the pixel coordinate (0.815, 23.42) is returned as (0,23)
    :param geo: Geo-Coordinate as QgsPointXY
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html
    :return: pixel position as QPpint
    """
    px = geo2pxF(geo, gt)
    return QPoint(int(px.x()), int(px.y()))


def px2geo(px, gt, pxCenter=True):
    """
    Converts a pixel coordinate into a geo-coordinate
    :param px: QPoint() with pixel coordinates
    :param gt: geo-transformation
    :param pxCenter: True to return geo-coordinate of pixel center, False to return upper-left edge
    :return:
    """

    #see http://www.gdal.org/gdal_datamodel.html

    gx = gt[0] + px.x()*gt[1]+px.y()*gt[2]
    gy = gt[3] + px.x()*gt[4]+px.y()*gt[5]

    if pxCenter:
        p2 = px2geo(QPoint(px.x()+1, px.y()+1), gt, pxCenter=False)

        gx = 0.5*(gx + p2.x())
        gy = 0.5*(gy + p2.y())

    return QgsPointXY(gx, gy)





class SpatialExtent(QgsRectangle):
    """
    Object to keep QgsRectangle and QgsCoordinateReferenceSystem together
    """
    @staticmethod
    def fromMapCanvas(mapCanvas, fullExtent=False):
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
        ext = QgsRectangle(-180,-90,180,90)
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
                px = px2geo(QPoint(x,y), gt)
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
            ext = args[0]
            extent2 = ext.toCrs(self.crs())
            self.combineExtentWith(QgsRectangle(extent2))
        else:
            super(SpatialExtent, self).combineExtentWith(*args)

        return self

    def setCenter(self, centerPoint:SpatialPoint, crs=None):
        """
        Sets the center. Can be used to move the SpatialExtent
        :param centerPoint:
        :param crs: QgsCoordinateReferenceSystem
        :return:
        """
        if isinstance(centerPoint, SpatialPoint):
            crs = centerPoint.crs()

        if isinstance(crs, QgsCoordinateReferenceSystem) and crs != self.crs():
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(crs)
            trans.setDestinationCrs(self.crs())
            centerPoint = trans.transform(centerPoint)

        delta = centerPoint - self.center()
        self.setXMaximum(self.xMaximum() + delta.x())
        self.setXMinimum(self.xMinimum() + delta.x())
        self.setYMaximum(self.yMaximum() + delta.y())
        self.setYMinimum(self.yMinimum() + delta.y())

        return self

    def __cmp__(self, other):
        if other is None: return 1
        s = ""

    def upperRightPt(self):
        return QgsPointXY(*self.upperRight())

    def upperLeftPt(self):
        return QgsPointXY(*self.upperLeft())

    def lowerRightPt(self):
        return QgsPointXY(*self.lowerRight())

    def lowerLeftPt(self):
        return QgsPointXY(*self.lowerLeft())


    def upperRight(self):
        return self.xMaximum(), self.yMaximum()

    def upperLeft(self):
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self):
        return self.xMaximum(), self.yMinimum()

    def lowerLeft(self):
        return self.xMinimum(), self.yMinimum()


    def __eq__(self, other):
        if not isinstance(other, SpatialExtent):
            return False
        return self.toString() == other.toString()

    def __sub__(self, other):
        raise NotImplementedError()

    def __mul__(self, other):
        raise NotImplementedError()

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

    def __reduce_ex__(self, protocol):
        return self.__class__, (self.crs().toWkt(),
                                self.xMinimum(), self.yMinimum(),
                                self.xMaximum(), self.yMaximum()
                                ), {}


    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return self.__repr__()

    def __repr__(self):

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())




def saveFilePath(text : str):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    see https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    :return: path
    """
    text = re.sub(r'[^\w\s.-]', '', text).strip().lower()
    text = re.sub(r'[-\s]+', '_', text)
    return re.sub(r'[ ]+]','',text)


def value2str(value, sep=' '):
    """
    Converts a value into a string
    :param value:
    :param sep:
    :return:
    """
    if isinstance(value, list):
        value = sep.join([str(v) for v in value])
    elif isinstance(value, np.array):
        value = value2str(value.astype(list), sep=sep)
    elif value is None:
        value = ''
    else:
        value = str(value)
    return value


# works in Python 2 & 3
class _Singleton(type):
    """ A metaclass that creates a Singleton base class when called. """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(_Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Singleton(_Singleton('SingletonMeta', (object,), {})): pass

"""
#work, but require metaclass pattern 
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwds):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args,**kwds)
        return cls._instances[cls]
"""

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



def defaultBands(dataset):
    """
    Returns a list of 3 default bands
    :param dataset:
    :return:
    """
    if isinstance(dataset, str):
        return defaultBands(gdal.Open(dataset))
    elif isinstance(dataset, QgsRasterDataProvider):
        return defaultBands(dataset.dataSourceUri())
    elif isinstance(dataset, QgsRasterLayer):
        return defaultBands(dataset.source())
    elif isinstance(dataset, gdal.Dataset):

        db = dataset.GetMetadataItem(str('default_bands'), str('ENVI'))
        if db != None:
            db = [int(n) for n in re.findall(r'\d+')]
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

        rl = QgsRasterLayer(dataset.GetFileList()[0])
        defaultRenderer = rl.renderer()
        if isinstance(defaultRenderer, QgsRasterRenderer):
            db = defaultRenderer.usesBands()
            if len(db) == 0:
                return [0, 1, 2]
            if len(db) > 3:
                db = db[0:3]
            db = [b-1 for b in db]
        return db

    else:
        raise Exception()

######### Lookup  tables
METRIC_EXPONENTS = {
    "nm": -9, "um": -6, u"µm": -6, "mm": -3, "cm": -2, "dm": -1, "m": 0, "hm": 2, "km": 3
}
# add synonyms
METRIC_EXPONENTS['nanometers'] = METRIC_EXPONENTS['nm']
METRIC_EXPONENTS['micrometers'] = METRIC_EXPONENTS['um']
METRIC_EXPONENTS['millimeters'] = METRIC_EXPONENTS['mm']
METRIC_EXPONENTS['centimeters'] = METRIC_EXPONENTS['cm']
METRIC_EXPONENTS['decimeters'] = METRIC_EXPONENTS['dm']
METRIC_EXPONENTS['meters'] = METRIC_EXPONENTS['m']
METRIC_EXPONENTS['hectometers'] = METRIC_EXPONENTS['hm']
METRIC_EXPONENTS['kilometers'] = METRIC_EXPONENTS['km']


LUT_WAVELENGTH = dict({'B': 480,
                       'G': 570,
                       'R': 660,
                       'NIR': 850,
                       'SWIR': 1650,
                       'SWIR1': 1650,
                       'SWIR2': 2150
                       })

def convertMetricUnit(value, u1, u2):
    """converts value, given in unit u1, to u2"""
    assert u1 in METRIC_EXPONENTS.keys()
    assert u2 in METRIC_EXPONENTS.keys()

    e1 = METRIC_EXPONENTS[u1]
    e2 = METRIC_EXPONENTS[u2]

    return value * 10 ** (e1 - e2)

def bandClosestToWavelength(dataset, wl, wl_unit='nm'):
    """
    Returns the band index (!) of an image dataset closest to wavelength `wl`.
    :param dataset: str | gdal.Dataset
    :param wl: wavelength to search the closed band for
    :param wl_unit: unit of wavelength. Default = nm
    :return: band index | 0 of wavelength information is not provided
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
                wl = convertMetricUnit(wl, wl_unit, ds_wlu)
            return int(np.argmin(np.abs(ds_wl - wl)))
        except:
            pass
    return 0

def cloneRenderer(renderer):

    assert isinstance(renderer, QgsRasterRenderer)
    cloned = renderer.clone()

    #handle specific issues if cloning is not exactly the same
    if isinstance(cloned, QgsSingleBandPseudoColorRenderer):
        cloned.setClassificationMin(renderer.classificationMin())
        cloned.setClassificationMax(renderer.classificationMax())

    return cloned


def parseWavelength(dataset):
    """
    Returns the wavelength + wavelength unit of a dataset
    :param dataset:
    :return: (wl, wl_u) or (None, None), if not existing
    """

    wl = None
    wlu = None

    if isinstance(dataset, str):
        return parseWavelength(gdal.Open(dataset))
    elif isinstance(dataset, QgsRasterDataProvider):
        return parseWavelength(dataset.dataSourceUri())
    elif isinstance(dataset, QgsRasterLayer):
        return parseWavelength(dataset.source())
    elif isinstance(dataset, gdal.Dataset):

        for domain in dataset.GetMetadataDomainList():
            # see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for supported wavelength units

            mdDict = dataset.GetMetadata_Dict(domain)

            for key, values in mdDict.items():
                key = key.lower()
                if re.search(r'wavelength$', key, re.I):
                    tmp = re.findall(r'\d*\.\d+|\d+', values)  # find floats
                    if len(tmp) != dataset.RasterCount:
                        tmp = re.findall(r'\d+', values)  # find integers
                    if len(tmp) == dataset.RasterCount:
                        wl = np.asarray([float(w) for w in tmp])

                if re.search(r'wavelength.units?', key):
                    if re.search('(Micrometers?|um)', values, re.I):
                        wlu = 'um'  # fix with python 3 UTF
                    elif re.search('(Nanometers?|nm)', values, re.I):
                        wlu = 'nm'
                    elif re.search('(Millimeters?|mm)', values, re.I):
                        wlu = 'nm'
                    elif re.search('(Centimeters?|cm)', values, re.I):
                        wlu = 'nm'
                    elif re.search('(Meters?|m)', values, re.I):
                        wlu = 'nm'
                    elif re.search('Wavenumber', values, re.I):
                        wlu = '-'
                    elif re.search('GHz', values, re.I):
                        wlu = 'GHz'
                    elif re.search('MHz', values, re.I):
                        wlu = 'MHz'
                    elif re.search('Index', values, re.I):
                        wlu = '-'
                    else:
                        wlu = '-'

        if wl is not None and len(wl) > dataset.RasterCount:
            wl = wl[0:dataset.RasterCount]

    return wl, wlu



def filterSubLayers(filePaths, subLayerEndings):
    """
    Returns sub layers endings from all gdal Datasets within filePaths
    :param filePaths:
    :param subLayerEndings:
    :return:
    """
    results = []
    if len(subLayerEndings) == 0:
        return filePaths[:]

    for path in filePaths:
        try:
            ds = gdal.Open(path)
            if ds.RasterCount == 0:
                for s in ds.GetSubDatasets():
                    for ending in subLayerEndings:
                        if s[0].endswith(ending):
                            results.append(s[0])
            else:
                results.append(path)
        except:
            pass
    return results


def copyRenderer(renderer, targetLayer):
    """
    Copies and applies renderer to targetLayer.
    :param renderer:
    :param targetLayer:
    :return: True, if 'renderer' could be copied and applied to 'targetLayer'
    """
    from timeseriesviewer.mapvisualization import cloneRenderer
    if isinstance(targetLayer, QgsRasterLayer) and isinstance(renderer, QgsRasterRenderer):

        targetLayer.setRenderer(cloneRenderer(renderer))
        return True
    elif isinstance(targetLayer, QgsVectorLayer) and isinstance(renderer, QgsFeatureRenderer):

        targetLayer.setRenderer(cloneRenderer(renderer))
        return True

    return False


def getSubLayerEndings(files):
    subLayerEndings = []
    for file in files:
        try:
            ds = gdal.Open(file)
            for subLayer in ds.GetSubDatasets():
                ending = subLayer[0].split(':')[-2:]
                if ending not in subLayerEndings:
                    subLayerEndings.append(':'.join(ending))
        except:
            s = ""
            pass

    return subLayerEndings


def settings():
    return QSettings('HU-Berlin', 'EO Time Series Viewer')

def niceNumberString(number):
    if isinstance(number, int):
        return '{}'.format(number)
    else:
        if math.fabs(number) > 1:
            return '{:0.2f}'.format(number)
        else:
            return '{:f}'.format(number)



def nicePredecessor(l):
    mul = -1 if l < 0 else 1
    l = np.abs(l)
    if l > 1.0:
        exp = np.fix(np.log10(l))
        # normalize to [0.0,1.0]
        l2 = l / 10 ** (exp)
        m = np.fix(l2)
        rest = l2 - m
        if rest >= 0.5:
            m += 0.5

        return mul * m * 10 ** exp

    elif l < 1.0:
        exp = np.fix(np.log10(l))
        #normalize to [0.0,1.0]
        m = l / 10 ** (exp-1)
        if m >= 5:
            m = 5.0
        else:
            m = 1.0
        return mul * m * 10 ** (exp-1)
    else:
        return 0.0



loadUI = lambda p : loadUIFormClass(jp(DIR_UI, p))
loadIcon = lambda p: jp(DIR_UI, *['icons',p])
#dictionary to store form classes and avoid multiple calls to read <myui>.ui
FORM_CLASSES = dict()


def loadUIFormClass(pathUi, from_imports=False, resourceSuffix=''):
    """
    Loads Qt UI files (*.ui) while taking care on QgsCustomWidgets.
    Uses PyQt4.uic.loadUiType (see http://pyqt.sourceforge.net/Docs/PyQt4/designer.html#the-uic-module)
    :param pathUi: *.ui file path
    :param from_imports:  is optionally set to use import statements that are relative to '.'. At the moment this only applies to the import of resource modules.
    :param resourceSuffix: is the suffix appended to the basename of any resource file specified in the .ui file to create the name of the Python module generated from the resource file by pyrcc4. The default is '_rc', i.e. if the .ui file specified a resource file called foo.qrc then the corresponding Python module is foo_rc.
    :return: the form class, e.g. to be used in a class definition like MyClassUI(QFrame, loadUi('myclassui.ui'))
    """

    RC_SUFFIX =  resourceSuffix
    assert os.path.exists(pathUi), '*.ui file does not exist: {}'.format(pathUi)


    if pathUi not in FORM_CLASSES.keys():
        #parse *.ui xml and replace *.h by qgis.gui
        doc = QDomDocument()

        #remove new-lines. this prevents uic.loadUiType(buffer, resource_suffix=RC_SUFFIX)
        #to mess up the *.ui xml

        f = open(pathUi, 'r')
        txt = ''.join(f.readlines())
        f.close()
        doc.setContent(txt)

        # Replace *.h file references in <customwidget> with <class>Qgs...</class>, e.g.
        #       <header>qgscolorbutton.h</header>
        # by    <header>qgis.gui</header>
        # this is require to compile QgsWidgets on-the-fly
        elem = doc.elementsByTagName('customwidget')
        for child in [elem.item(i) for i in range(elem.count())]:
            child = child.toElement()
            className = str(child.firstChildElement('class').firstChild().nodeValue())
            if className.startswith('Qgs'):
                cHeader = child.firstChildElement('header').firstChild()
                cHeader.setNodeValue('qgis.gui')

        #collect resource file locations
        elem = doc.elementsByTagName('include')
        qrcPathes = []
        for child in [elem.item(i) for i in range(elem.count())]:
            path = child.attributes().item(0).nodeValue()
            if path.endswith('.qrc'):
                qrcPathes.append(path)



        buffer = io.StringIO()  # buffer to store modified XML
        buffer.write(doc.toString())
        buffer.flush()
        buffer.seek(0)


        #make resource file directories available to the python path (sys.path)
        baseDir = os.path.dirname(pathUi)
        tmpDirs = []
        for qrcPath in qrcPathes:
            d = os.path.dirname(os.path.join(baseDir, os.path.dirname(qrcPath)))
            if d not in sys.path:
                tmpDirs.append(d)
        sys.path.extend(tmpDirs)

        #load form class
        try:
            FORM_CLASS, _ = uic.loadUiType(buffer, resource_suffix=RC_SUFFIX)
        except SyntaxError as ex:
            FORM_CLASS, _ = uic.loadUiType(pathUi, resource_suffix=RC_SUFFIX)
        buffer.close()
        FORM_CLASSES[pathUi] = FORM_CLASS

        #remove temporary added directories from python path
        for d in tmpDirs:
            sys.path.remove(d)

    return FORM_CLASSES[pathUi]


def zipdir(pathDir, pathZip):
    """
    :param pathDir: directory to compress
    :param pathZip: path to new zipfile
    """
    #thx to https://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory
    """
    import zipfile
    assert os.path.isdir(pathDir)
    zipf = zipfile.ZipFile(pathZip, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(pathDir):
        for file in files:
            zipf.write(os.path.join(root, file))
    zipf.close()
    """
    import zipfile
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

        for zname in zip.namelist():
            if zname.find('..') != -1 or zname.find(os.path.sep) == 0:
                s = ""

        s  =""




class TestObjects():
    """
    A class to provide test data
    """
    @staticmethod
    def testImagePaths()->list:
        import example
        files = list(file_search(os.path.dirname(example.__file__), '*.tif', recursive=True))
        assert len(files) > 0
        return files


    @staticmethod
    def createTestImageSeries(n=1) -> list:
        assert n > 0

        datasets = []
        for i in range(n):
            ds = TestObjects.inMemoryImage()
            datasets.append(ds)
        return datasets

    @staticmethod
    def createMultiSourceTimeSeries() -> list:
        import example
        #real files
        files = TestObjects.testImagePaths()
        movedFiles = []
        d = r'/vsimem/'
        for pathSrc in files:
            bn = os.path.basename(pathSrc)
            pathDst = d + 'shifted_'+bn+'.bsq'
            dsSrc = gdal.Open(pathSrc)
            tops = gdal.TranslateOptions(format='ENVI')
            gdal.Translate(pathDst, dsSrc, options=tops)
            dsDst = gdal.Open(pathDst, gdal.GA_Update)
            assert isinstance(dsDst, gdal.Dataset)
            gt = list(dsSrc.GetGeoTransform())
            ns, nl = dsDst.RasterXSize, dsDst.RasterYSize
            gt[0] = gt[0] + 0.5 * ns * gt[1]
            gt[3] = gt[3] + abs(0.5 * nl * gt[5])
            dsDst.SetGeoTransform(gt)
            dsDst.SetMetadata(dsSrc.GetMetadata(''), '')
            dsDst.FlushCache()

            dsDst = None
            dsDst = gdal.Open(pathDst)
            assert list(dsDst.GetGeoTransform()) == gt
            movedFiles.append(pathDst)
        return files + movedFiles

    @staticmethod
    def inMemoryImage(nl=10, ns=20, nb=3, crs='EPSG:32632', eType:int=None, path:str=None)->gdal.Dataset:
        """
        Create an in-memory gdal.Dataset
        :param nl:
        :param ns:
        :param nb:
        :param crs:
        :return:
        """
        drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)
        id = uuid.uuid4()
        if not isinstance(path, str):
            path = '/vsimem/testimage.multiband.{}.tif'.format(id)

        if eType is None:
            eType = gdal.GDT_Float32

        assert isinstance(eType, int) and eType >= 0

        ds = drv.Create(path, ns, nl, bands=nb, eType=eType)

        if isinstance(crs, str):
            c = QgsCoordinateReferenceSystem(crs)
            ds.SetProjection(c.toWkt())

        gt = [1000,30,0, \
              1000,0 ,-30]

        ds.SetGeoTransform(gt)
        for b in range(1, nb + 1):
            band = ds.GetRasterBand(b)
            assert isinstance(band, gdal.Band)
            array = np.random.random((nl, ns)) - 1
            band.WriteArray(array)
        ds.FlushCache()
        return ds



    @staticmethod
    def inMemoryClassification(n=3, nl=10, ns=20, nb=1, crs='EPSG:32632'):
        from .classificationscheme import ClassificationScheme
        scheme = ClassificationScheme()
        scheme.createClasses(n)

        drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)

        id = uuid.uuid4()
        path = '/vsimem/testimage.class._{}.tif'.format(id)
        ds = drv.Create(path, ns, nl, bands=nb, eType=gdal.GDT_Byte)

        if isinstance(crs, str):
            c = QgsCoordinateReferenceSystem(crs)
            ds.SetProjection(c.toWkt())

        step = int(np.ceil(float(nl) / len(scheme)))

        assert isinstance(ds, gdal.Dataset)
        for b in range(1, nb + 1):
            band = ds.GetRasterBand(b)
            array = np.zeros((nl, ns), dtype=np.uint8) - 1
            y0 = 0
            for i, c in enumerate(scheme):
                y1 = min(y0 + step, nl - 1)
                array[y0:y1, :] = c.label()
                y0 += y1 + 1
            band.SetCategoryNames(scheme.classNames())
            band.SetColorTable(scheme.gdalColorTable())
        ds.FlushCache()
        return ds

    @staticmethod
    def qgisInterfaceMockup():

        return QgisMockup()

    @staticmethod
    def createDropEvent(mimeData:QMimeData):
        """Creates a QDropEvent conaining the provided QMimeData"""
        return QDropEvent(QPointF(0, 0), Qt.CopyAction, mimeData, Qt.LeftButton, Qt.NoModifier)


    @staticmethod
    def processingAlgorithm():

        from qgis.core import QgsProcessingAlgorithm

        class TestProcessingAlgorithm(QgsProcessingAlgorithm):

            def __init__(self):
                super(TestProcessingAlgorithm, self).__init__()
                s = ""

            def createInstance(self):
                return TestProcessingAlgorithm()

            def name(self):
                return 'exmaplealg'

            def displayName(self):
                return 'Example Algorithm'

            def groupId(self):
                return 'exampleapp'

            def group(self):
                return 'TEST APPS'

            def initAlgorithm(self, configuration=None):
                self.addParameter(QgsProcessingParameterRasterLayer('pathInput', 'The Input Dataset'))
                self.addParameter(
                    QgsProcessingParameterNumber('value', 'The value', QgsProcessingParameterNumber.Double, 1, False,
                                                 0.00, 999999.99))
                self.addParameter(QgsProcessingParameterRasterDestination('pathOutput', 'The Output Dataset'))

            def processAlgorithm(self, parameters, context, feedback):
                assert isinstance(parameters, dict)
                assert isinstance(context, QgsProcessingContext)
                assert isinstance(feedback, QgsProcessingFeedback)


                outputs = {}
                return outputs

        return TestProcessingAlgorithm()



class QgisMockup(QgisInterface):
    """
    A "fake" QGIS Desktop instance that should provide all the inferfaces a plugin developer might need (and nothing more)
    """

    def pluginManagerInterface(self)->QgsPluginManagerInterface:
        return self.mPluginManager

    @staticmethod
    def create()->QgisInterface:
        """
        Create the QgisMockup and sets the global variables
        :return: QgisInterface
        """

        iface = QgisMockup()

        import qgis.utils
        # import processing
        # p = processing.classFactory(iface)
        if not isinstance(qgis.utils.iface, QgisInterface):

            import processing
            qgis.utils.iface = iface
            processing.Processing.initialize()

            import pkgutil
            prefix = str(processing.__name__ + '.')
            for importer, modname, ispkg in pkgutil.walk_packages(processing.__path__, prefix=prefix):
                try:
                    module = __import__(modname, fromlist="dummy")
                    if hasattr(module, 'iface'):
                        print(modname)
                        module.iface = iface
                except:
                    pass
        #set 'home_plugin_path', which is required from the QGIS Plugin manager
        assert qgis.utils.iface == iface
        qgis.utils.home_plugin_path = os.path.join(QgsApplication.instance().qgisSettingsDirPath(), *['python', 'plugins'])
        return iface

    def __init__(self, *args):
        # QgisInterface.__init__(self)
        super(QgisMockup, self).__init__()

        self.mCanvas = QgsMapCanvas()
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mCanvas.extentsChanged.connect(self.testSlot)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mRootNode = QgsLayerTree()
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeMapCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mRootNode, self.mCanvas)
        self.mLayerTreeMapCanvasBridge.setAutoSetupOnFirstLayer(True)

        import pyplugin_installer.installer
        PI = pyplugin_installer.instance()
        self.mPluginManager = QgsPluginManagerMockup()

        self.ui = QMainWindow()



        self.mMessageBar = QgsMessageBar()
        mainFrame = QFrame()

        self.ui.setCentralWidget(mainFrame)
        self.ui.setWindowTitle('QGIS Mockup')


        l = QHBoxLayout()
        l.addWidget(self.mLayerTreeView)
        l.addWidget(self.mCanvas)
        v = QVBoxLayout()
        v.addWidget(self.mMessageBar)
        v.addLayout(l)
        mainFrame.setLayout(v)
        self.ui.setCentralWidget(mainFrame)
        self.lyrs = []
        self.createActions()

    def iconSize(self, dockedToolbar=False):
        return QSize(30,30)

    def testSlot(self, *args):
        # print('--canvas changes--')
        s = ""

    def mainWindow(self):
        return self.ui


    def addToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def removeToolBarIcon(self, action):
        assert isinstance(action, QAction)


    def addVectorLayer(self, path, basename=None, providerkey=None):
        if basename is None:
            basename = os.path.basename(path)
        if providerkey is None:
            bn, ext = os.path.splitext(basename)

            providerkey = 'ogr'
        l = QgsVectorLayer(path, basename, providerkey)
        assert l.isValid()
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()
        s = ""

    def legendInterface(self):
        return None

    def addRasterLayer(self, path, baseName=''):
        l = QgsRasterLayer(path, os.path.basename(path))
        self.lyrs.append(l)

        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()
        return

        cnt = len(self.canvas.layers())

        self.canvas.setLayers([QgsMapCanvasLayer(l)])
        l.dataProvider()
        if cnt == 0:
            self.canvas.mapSettings().setDestinationCrs(l.crs())
            self.canvas.setExtent(l.extent())

            spatialExtent = SpatialExtent.fromMapLayer(l)
            # self.canvas.blockSignals(True)
            self.canvas.setDestinationCrs(spatialExtent.crs())
            self.canvas.setExtent(spatialExtent)
            # self.blockSignals(False)
            self.canvas.refresh()

        self.canvas.refresh()

    def createActions(self):
        m = self.ui.menuBar().addAction('Add Vector')
        m = self.ui.menuBar().addAction('Add Raster')

    def mapCanvas(self):
        return self.mCanvas

    def mapNavToolToolBar(self):
        super().mapNavToolToolBar()

    def messageBar(self, *args, **kwargs):
        return self.mMessageBar

    def rasterMenu(self):
        super().rasterMenu()

    def vectorMenu(self):
        super().vectorMenu()

    def viewMenu(self):
        super().viewMenu()

    def windowMenu(self):
        super().windowMenu()

    def zoomFull(self, *args, **kwargs):
        super().zoomFull(*args, **kwargs)



class PythonRunnerImpl(QgsPythonRunner):
    """
    A Qgs PythonRunner implementation
    """

    def __init__(self):
        super(PythonRunnerImpl, self).__init__()


    def evalCommand(self, cmd:str, result:str):
        try:
            o = compile(cmd)
        except Exception as ex:
            result = str(ex)
            return False
        return True

    def runCommand(self, command, messageOnError=''):
        try:
            o = compile(command, 'fakemodule', 'exec')
            exec(o)
        except Exception as ex:
            messageOnError = str(ex)
            command = ['{}:{}'.format(i+1, l) for i,l in enumerate(command.splitlines())]
            print('\n'.join(command), file=sys.stderr)
            raise ex
            return False
        return True


def createCRSTransform(src, dst):
    assert isinstance(src, QgsCoordinateReferenceSystem)
    assert isinstance(dst, QgsCoordinateReferenceSystem)
    t = QgsCoordinateTransform()
    t.setSourceCrs(src)
    t.setDestinationCrs(dst)
    return t
