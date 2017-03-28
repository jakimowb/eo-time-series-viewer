
import os
from collections import defaultdict
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from osgeo import gdal

import weakref

jp = os.path.join
dn = os.path.dirname

def fileSizeString(num, suffix='B', div=1000):
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
            return "{:3.1f}{}{}".format(num, unit, suffix)
        num /= div
    return "{:.1f} {}{}".format(num, unit, suffix)



class SpatialPoint(QgsPoint):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def fromMapCanvasCenter(mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialPoint(crs, mapCanvas.center())

    def __init__(self, crs, *args):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialPoint, self).__init__(*args)
        self.mCrs = crs

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def toCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        pt = QgsPoint(self)
        if self.mCrs != crs:
            trans = QgsCoordinateTransform(self.mCrs, crs)
            pt = trans.transform(pt)
        return SpatialPoint(crs, pt)

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

    def __repr__(self):
        return '{} {} {}'.format(self.x(), self.y(), self.crs().authid())


def findParent(qObject, parentType, checkInstance = False):
    parent = qObject.parent()
    if checkInstance:
        while parent != None and not isinstance(parent, parentType):
            parent = parent.parent()
    else:
        while parent != None and type(parent) != parentType:
            parent = parent.parent()
    return parent

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
    def fromLayer(mapLayer):
        assert isinstance(mapLayer, QgsMapLayer)
        extent = mapLayer.extent()
        crs = mapLayer.crs()
        return SpatialExtent(crs, extent)

    def __init__(self, crs, *args):
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
            trans = QgsCoordinateTransform(self.mCrs, crs)
            box = trans.transformBoundingBox(box)
        return SpatialExtent(crs, box)

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

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
        if other is None: return 1
        s = ""

    def __eq__(self, other):
        s = ""

    def __sub__(self, other):
        raise NotImplementedError()

    def __mul__(self, other):
        raise NotImplementedError()

    def upperRightPt(self):
        return QgsPoint(*self.upperRight())

    def upperLeftPt(self):
        return QgsPoint(*self.upperLeft())

    def lowerRightPt(self):
        return QgsPoint(*self.lowerRight())

    def lowerLeftPt(self):
        return QgsPoint(*self.lowerLeft())


    def upperRight(self):
        return self.xMaximum(), self.yMaximum()

    def upperLeft(self):
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self):
        return self.xMaximum(), self.yMinimum()

    def lowerLeft(self):
        return self.xMinimum(), self.yMinimum()


    def __repr__(self):

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())


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
