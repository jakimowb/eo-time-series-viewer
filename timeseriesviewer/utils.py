
import os, math
from collections import defaultdict
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from osgeo import gdal

import weakref
import numpy as np

jp = os.path.join
dn = os.path.dirname




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


class SpatialPoint(QgsPoint):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def fromMapCanvasCenter(mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialPoint(crs, mapCanvas.center())

    @staticmethod
    def fromSpatialExtent(spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        crs = spatialExtent.crs()
        return SpatialPoint(crs, spatialExtent.center())

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
            pt = saveTransform(pt, self.mCrs, crs)

        return SpatialPoint(crs, pt) if pt else None

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

def saveTransform(geom, crs1, crs2):
    assert isinstance(crs1, QgsCoordinateReferenceSystem)
    assert isinstance(crs2, QgsCoordinateReferenceSystem)

    result = None
    if isinstance(geom, QgsRectangle):
        if geom.isEmpty():
            return None


        transform = QgsCoordinateTransform(crs1, crs2);
        try:
            rect = transform.transformBoundingBox(geom);
            result = SpatialExtent(crs2, rect)
        except:
            print('Can not transform from {} to {} on rectangle {}'.format( \
                crs1.description(), crs2.description(), str(geom)))

    elif isinstance(geom, QgsPoint):

        transform = QgsCoordinateTransform(crs1, crs2);
        try:
            pt = transform.transform(geom);
            result = SpatialPoint(crs2, pt)
        except:
            print('Can not transform from {} to {} on QgsPoint {}'.format( \
                crs1.description(), crs2.description(), str(geom)))
    return result

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
            box = saveTransform(box, self.mCrs, crs)
        return SpatialExtent(crs, box) if box else None

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
        return self.toString() == other.toString()

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
    if isinstance(targetLayer, QgsRasterLayer) and isinstance(renderer, QgsRasterRenderer):
        if isinstance(renderer, QgsMultiBandColorRenderer):
            r = renderer.clone()
            r.setInput(targetLayer.dataProvider())
            targetLayer.setRenderer(r)
            return True
        elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
            r = renderer.clone()
            # r = QgsSingleBandPseudoColorRenderer(None, renderer.band(), None)
            r.setInput(targetLayer.dataProvider())
            cmin = renderer.classificationMin()
            cmax = renderer.classificationMax()
            r.setClassificationMin(cmin)
            r.setClassificationMax(cmax)
            targetLayer.setRenderer(r)
            return True
    elif isinstance(targetLayer, QgsVectorLayer) and isinstance(renderer, QgsFeatureRendererV2):
        #todo: add render-specific switches
        targetLayer.setRenderer(renderer)
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
    return QSettings('HU-Berlin', 'HUB TimeSeriesViewer')

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


if __name__ == '__main__':
    #nice predecessors
    from sandbox import initQgisEnvironment
    qgsApp = initQgisEnvironment()
    se = SpatialExtent.world()
    assert nicePredecessor(26) == 25
    assert nicePredecessor(25) == 25
    assert nicePredecessor(23) == 20
    assert nicePredecessor(999) == 950
    assert nicePredecessor(1001) == 1000
    assert nicePredecessor(1.2) == 1.0      #
    assert nicePredecessor(0.8) == 0.5
    assert nicePredecessor(0.2) == 0.1
    assert nicePredecessor(0.021) == 0.01
    assert nicePredecessor(0.0009991) == 0.0005
