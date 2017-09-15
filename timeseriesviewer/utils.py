# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import
import os, sys, math, StringIO, re

import logging
logger = logging.getLogger(__name__)

from collections import defaultdict
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtXml import QDomDocument
from PyQt4 import uic
from osgeo import gdal

import weakref
import numpy as np

jp = os.path.join
dn = os.path.dirname

from timeseriesviewer import DIR_UI


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
        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialPoint, self).__init__(*args)
        self.mCrs = crs

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
        pt = QgsPoint(self)

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
            logger.debug('Can not transform from {} to {} on rectangle {}'.format( \
                crs1.description(), crs2.description(), str(geom)))

    elif isinstance(geom, QgsPoint):

        transform = QgsCoordinateTransform(crs1, crs2);
        try:
            pt = transform.transform(geom);
            result = SpatialPoint(crs2, pt)
        except:
            logger.debug('Can not transform from {} to {} on QgsPoint {}'.format( \
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
    assert isinstance(geo, QgsPoint)
    # see http://www.gdal.org/gdal_datamodel.html
    px = (geo.x() - gt[0]) / gt[1]  # x pixel
    py = (geo.y() - gt[3]) / gt[5]  # y pixel
    return QPointF(px,py)

def geo2px(geo, gt):
    """
    Returns the pixel position related to a Geo-Coordinate as integer number.
    Floating-point coordinate are casted to integer coordinate, e.g. the pixel coordinate (0.815, 23.42) is returned as (0,23)
    :param geo: Geo-Coordinate as QgsPoint
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html
    :return: pixel position as QPpint
    """
    px = geo2pxF(geo, gt)
    return QPoint(int(px.x()), int(px.y()))


def px2geo(px, gt):
    #see http://www.gdal.org/gdal_datamodel.html
    gx = gt[0] + px.x()*gt[1]+px.y()*gt[2]
    gy = gt[3] + px.x()*gt[4]+px.y()*gt[5]
    return QgsPoint(gx,gy)


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


    def __eq__(self, other):
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
    def __str__(self):
        return self.__repr__()

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



loadUi = lambda p : loadUIFormClass(jp(DIR_UI, p))
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

    buffer = StringIO.StringIO() #buffer to store modified XML
    if pathUi not in FORM_CLASSES.keys():
        #parse *.ui xml and replace *.h by qgis.gui
        doc = QDomDocument()

        #remove new-lines. this prevents uic.loadUiType(buffer, resource_suffix=RC_SUFFIX)
        #to mess up the *.ui xml
        txt = ''.join(open(pathUi).readlines())
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



        #logger.debug('Load UI file: {}'.format(pathUi))
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
            logger.info('{}\n{}:"{}"\ncall instead uic.loadUiType(path,...) directly'.format(pathUi, ex, ex.text))
            FORM_CLASS, _ = uic.loadUiType(pathUi, resource_suffix=RC_SUFFIX)

        FORM_CLASSES[pathUi] = FORM_CLASS

        #remove temporary added directories from python path
        for d in tmpDirs:
            sys.path.remove(d)

    return FORM_CLASSES[pathUi]


def initQgisApplication(pythonPlugins=None, PATH_QGIS=None, qgisDebug=False):
    """
    Initializes the QGIS Environment
    :return: QgsApplication instance of local QGIS installation
    """
    import site
    if pythonPlugins is None:
        pythonPlugins = []
    assert isinstance(pythonPlugins, list)

    from timeseriesviewer import DIR_REPO
    #pythonPlugins.append(os.path.dirname(DIR_REPO))
    PLUGIN_DIR = os.path.dirname(DIR_REPO)

    if os.path.isdir(PLUGIN_DIR):
        for subDir in os.listdir(PLUGIN_DIR):
            if not subDir.startswith('.'):
                pythonPlugins.append(os.path.join(PLUGIN_DIR, subDir))

    envVar = os.environ.get('QGIS_PLUGINPATH', None)
    if isinstance(envVar, list):
        pythonPlugins.extend(re.split('[;:]', envVar))

    #make plugin paths available to QGIS and Python
    os.environ['QGIS_PLUGINPATH'] = ';'.join(pythonPlugins)
    os.environ['QGIS_DEBUG'] = '1' if qgisDebug else '0'
    for p in pythonPlugins:
        sys.path.append(p)

    if isinstance(QgsApplication.instance(), QgsApplication):
        #alread started
        return QgsApplication.instance()
    else:



        if PATH_QGIS is None:
            # find QGIS Path
            if sys.platform == 'darwin':
                #search for the QGIS.app
                import qgis, re
                assert '.app' in qgis.__file__, 'Can not locate path of QGIS.app'
                PATH_QGIS_APP = re.split('\.app[\/]', qgis.__file__)[0]+ '.app'
                PATH_QGIS = os.path.join(PATH_QGIS_APP, *['Contents','MacOS'])

                if not 'GDAL_DATA' in os.environ.keys():
                    os.environ['GDAL_DATA'] = r'/Library/Frameworks/GDAL.framework/Versions/2.1/Resources/gdal'

                QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns']))
                QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns','qgis']))


            else:
                # assume OSGeo4W startup
                PATH_QGIS = os.environ['QGIS_PREFIX_PATH']

        assert os.path.exists(PATH_QGIS)

        QgsApplication.setGraphicsSystem("raster")
        qgsApp = QgsApplication([], True)
        qgsApp.setPrefixPath(PATH_QGIS, True)
        qgsApp.initQgis()
        return qgsApp



if __name__ == '__main__':
    #nice predecessors
    from timeseriesviewer.sandbox import initQgisEnvironment
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
