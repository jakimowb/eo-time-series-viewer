# -*- coding: utf-8 -*-


import os, sys, importlib, re, fnmatch, io, zipfile, pathlib, warnings, collections, copy, shutil, typing

from qgis.core import *
from qgis.core import QgsFeature, QgsPointXY, QgsRectangle
from qgis.gui import *
from qgis.gui import QgisInterface, QgsDockWidget, QgsPluginManagerInterface
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtCore import QMimeData
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt import uic
from osgeo import gdal, ogr
import numpy as np

from qgis.PyQt.QtWidgets import QAction

REMOVE_setShortcutVisibleInContextMenu = hasattr(QAction, 'setShortcutVisibleInContextMenu')

from . import resourcemockup

try:

    from .. import qps
except:
    import qps

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


def cleanDir(d):
    """
    Remove content from directory 'd'
    :param d: directory to be cleaned.
    """
    assert os.path.isdir(d)
    for root, dirs, files in os.walk(d):
        for p in dirs + files: rm(jp(root, p))
        break


def mkDir(d, delete=False):
    """
    Make directory.
    :param d: path of directory to be created
    :param delete: set on True to delete the directory contents, in case the directory already existed.
    """
    if delete and os.path.isdir(d):
        cleanDir(d)
    if not os.path.isdir(d):
        os.makedirs(d)


# for python development only. try to find a qgisresources directory
DIR_QGISRESOURCES = None

# a QPS internal map layer store
QPS_MAPLAYER_STORE = QgsMapLayerStore()

# a list of all known maplayer stores.
MAP_LAYER_STORES = [QPS_MAPLAYER_STORE, QgsProject.instance()]


def findUpwardPath(basepath, name, isDirectory=True):
    """

    :param basepath:
    :param name:
    :param isDirectory:
    :return:
    """
    tmp = pathlib.Path(basepath)
    while tmp != pathlib.Path(tmp.anchor):
        if (isDirectory and os.path.isdir(tmp / name)) or \
            os.path.isfile(tmp / name):
            return str(tmp / name)
        else:
            tmp = tmp.parent
    return None


DIR_QGISRESOURCES = findUpwardPath(__file__, 'qgisresources')


def file_search(rootdir, pattern, recursive=False, ignoreCase=False, directories=False, fullpath=False):
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


"""
def file_search(rootdir, pattern, recursive=False, ignoreCase=False):
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))
    results = []

    for root, dirs, files in os.walk(rootdir):
        for file in files:
            if isinstance(pattern, regType):
                if pattern.search(file):
                    path = os.path.join(root, file)
                    results.append(path)

            elif (ignoreCase and fnmatch.fnmatch(file.lower(), pattern.lower())) \
                    or fnmatch.fnmatch(file, pattern):

                path = os.path.join(root, file)
                results.append(path)
        if not recursive:
            break
            pass

    return results
"""


UI_DIRECTORIES = []
if os.path.isdir(jp(dn(__file__), 'ui')):
    UI_DIRECTORIES.append(jp(dn(__file__), 'ui'))
for f in file_search(os.path.dirname(__file__), '*.ui', recursive=True):
    path = os.path.dirname(f)
    if path not in UI_DIRECTORIES:
        UI_DIRECTORIES.append(path)


def registerMapLayerStore(store):
    """
    Registers an QgsMapLayerStore or QgsProject to search QgsMapLayers in
    :param store: QgsProject | QgsMapLayerStore
    """
    assert isinstance(store, (QgsProject, QgsMapLayerStore))
    if store not in MAP_LAYER_STORES:
        MAP_LAYER_STORES.append(store)


def registeredMapLayers()->list:
    """
    Returns the QgsMapLayers which are stored in known QgsMapLayerStores
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    for store in MAP_LAYER_STORES:
        for layer in store.mapLayers().values():
            if layer not in layers:
                layers.append(layer)
    return layers


# Lookup tables
METRIC_EXPONENTS = {
    "nm": -9, "um": -6, u"µm": -6, "mm": -3, "cm": -2, "dm": -1, "m": 0, "hm": 2, "km": 3
}
# add synonyms (lower-case)
METRIC_EXPONENTS['nanometers'] = METRIC_EXPONENTS['nm']
METRIC_EXPONENTS['micrometers'] = METRIC_EXPONENTS['μm'] = METRIC_EXPONENTS['um']
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


def mkdir(path):
    if not os.path.isdir(path):
        os.mkdir(path)



NEXT_COLOR_HUE_DELTA_CON = 10
NEXT_COLOR_HUE_DELTA_CAT = 100

def nextColor(color, mode='cat')->QColor:
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




def findMapLayer(layer)->QgsMapLayer:
    """
    Returns the first QgsMapLayer out of all layers stored in MAP_LAYER_STORES that matches layer
    :param layer: str layer id or layer name or QgsMapLayer
    :return: QgsMapLayer
    """
    assert isinstance(layer, (QgsMapLayer, str))
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


        s = ""


def qgisLayerTreeLayers() -> list:
    """
    Returns the layers shown in the QGIS LayerTree
    :return: [list-of-QgsMapLayers]
    """
    iface = qgisAppQgisInterface()
    if isinstance(iface, QgisInterface):
        return [ln.layer() for ln in iface.layerTreeView().model().rootGroup().findLayers()
                if isinstance(ln.layer(), QgsMapLayer)]
    else:
        return []


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
    elif t in [int, np.int, np.int8, np.int16, np.int32, np.int64]:
        return QgsField(name, QVariant.Int, 'int', comment=comment)
    elif t in [np.uint, np.uint8, np.uint16, np.uint32, np.uint64]:
        return QgsField(name, QVariant.UInt, 'uint', comment=comment)
    elif t in [float, np.double, np.float, np.double, np.float16, np.float32, np.float64]:
        return QgsField(name, QVariant.Double, 'double', comment=comment)
    elif isinstance(exampleValue, np.ndarray):
        return QgsField(name, QVariant.String, 'varchar', comment=comment)
    elif isinstance(exampleValue, np.datetime64):
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


def filenameFromString(text : str):
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


def value2str(value, sep:str=None, delimiter:str=' '):
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


def showMessage(message:str, title:str, level):
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


def gdalDataset(pathOrDataset:typing.Union[str, QgsRasterLayer, QgsRasterDataProvider, gdal.Dataset], eAccess=gdal.GA_ReadOnly)->gdal.Dataset:
    """
    Returns a gdal.Dataset object instance
    :param pathOrDataset: path | gdal.Dataset | QgsRasterLayer | QgsRasterDataProvider
    :return: gdal.Dataset
    """
    if isinstance(pathOrDataset, QgsRasterLayer):
        return gdalDataset(pathOrDataset.source())
    elif isinstance(pathOrDataset, QgsRasterDataProvider):
        return gdalDataset(pathOrDataset.dataSourceUri())

    if not isinstance(pathOrDataset, gdal.Dataset):
        pathOrDataset = gdal.Open(pathOrDataset, eAccess)

    assert isinstance(pathOrDataset, gdal.Dataset), 'Can not read {} as gdal.Dataset'.format(pathOrDataset)

    return pathOrDataset

def ogrDataSource(pathOrDataSource)->ogr.DataSource:
    """
    Returns an OGR DataSource instance
    :param pathOrDataSource: ogr.DataSource | str | QgsVectorLayer
    :return: ogr.Datasource
    """
    if isinstance(pathOrDataSource, QgsVectorLayer):
        uri = pathOrDataSource.source().split('|')[0]
        return ogrDataSource(uri)

    if not isinstance(pathOrDataSource, ogr.DataSource):
        pathOrDataSource = ogr.Open(pathOrDataSource)

    assert isinstance(pathOrDataSource, ogr.DataSource), 'Can not read {} as ogr.DataSource'.format(pathOrDataSource)
    return pathOrDataSource


def qgsVectorLayer(source)->QgsVectorLayer:
    """
    Returns a QgsVectorLayer from different source types
    :param source: QgsVectorLayer | ogr.DataSource | file path
    :return: QgsVectorLayer
    :rtype: QgsVectorLayer
    """
    if isinstance(source, QgsVectorLayer):
        return source
    if isinstance(source, str):
        return QgsVectorLayer(source)
    if isinstance(source, ogr.DataSource):
        return QgsVectorLayer(source.GetDescription())

    raise Exception('Unable to transform {} into QgsVectorLayer'.format(source))

def qgsRasterLayer(source)->QgsRasterLayer:
    """
    Returns a QgsVectorLayer from different source types
    :param source: QgsVectorLayer | ogr.DataSource | file path
    :return: QgsVectorLayer
    :rtype: QgsVectorLayer
    """
    if isinstance(source, QgsRasterLayer):
        return source
    if isinstance(source, str):
        return QgsRasterLayer(source)
    if isinstance(source, gdal.Dataset):
        return QgsRasterLayer(source.GetDescription())

    raise Exception('Unable to transform {} into QgsRasterLayer'.format(source))


def loadUI(basename: str):
    """
    Loads a UI using the basename ("file.ui") only.
    Will search all directories specified in UI_DIRECTORIES
    :param basename:
    :return:
    """
    assert isinstance(basename, str)
    for pathDir in UI_DIRECTORIES:
        assert isinstance(pathDir, str)
        if os.path.isdir(pathDir):
            pathUi = jp(pathDir, basename)
            if os.path.isfile(pathUi):
                return loadUIFormClass(pathUi)
    raise Exception('Unable to find full path for "{}". Make its directory known to UI_DIRECTORIES'.format(basename))

# dictionary to store form classes and avoid multiple calls to read <myui>.ui
FORM_CLASSES = dict()
QGIS_RESOURCE_WARNINGS = set()

def loadUIFormClass(pathUi:str, from_imports=False, resourceSuffix:str='', fixQGISRessourceFileReferences=True, _modifiedui=None):
    """
    Loads Qt UI files (*.ui) while taking care on QgsCustomWidgets.
    Uses PyQt4.uic.loadUiType (see http://pyqt.sourceforge.net/Docs/PyQt4/designer.html#the-uic-module)
    :param pathUi: *.ui file path
    :param from_imports:  is optionally set to use import statements that are relative to '.'. At the moment this only applies to the import of resource modules.
    :param resourceSuffix: is the suffix appended to the basename of any resource file specified in the .ui file to create the name of the Python module generated from the resource file by pyrcc4. The default is '_rc', i.e. if the .ui file specified a resource file called foo.qrc then the corresponding Python module is foo_rc.
    :return: the form class, e.g. to be used in a class definition like MyClassUI(QFrame, loadUi('myclassui.ui'))
    """

    RC_SUFFIX = resourceSuffix
    assert os.path.isfile(pathUi), '*.ui file does not exist: {}'.format(pathUi)


    if pathUi not in FORM_CLASSES.keys():
        #parse *.ui xml and replace *.h by qgis.gui

        with open(pathUi, 'r', encoding='utf-8') as f:
            txt = f.read()

        dirUi = os.path.dirname(pathUi)

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

        match = re.search(r'resource="[^:].*/QGIS[^/"]*/images/images.qrc"',txt)
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
                print('{}\nrefers to {} none-existing resource (*.qrc) file(s):'.format(pathUi, len(missingQrc)))
                for i, t in enumerate(missingQrc):
                    line, path = t
                    print('{}: "{}"'.format(i+1, path), file=sys.stderr)

            if len(missingQgs) > 0 and not isinstance(qgisAppQgisInterface(), QgisInterface):
                missingFiles = [p[1] for p in missingQrc if p[1] not in QGIS_RESOURCE_WARNINGS]

                if len(missingFiles) > 0:
                    print('{}\nrefers to {} none-existing resource (*.qrc) file(s) '.format(pathUi, len(missingFiles)))
                    for i, path in enumerate(missingFiles):
                        print('{}: "{}"'.format(i+1, path))
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

            if sClass.startswith('Qgs'):
                cHeader.setNodeValue('qgis.gui')
            if sExtends.startswith('qps.'):
                cHeader.setNodeValue(re.sub(r'^qps\.', qps.__spec__.name + '.', sExtends))

        # collect resource file locations
        elems = doc.elementsByTagName('include')
        qrcPaths = []
        for i in range(elems.count()):
            node = elems.item(i).toElement()
            lpath = node.attribute('location')
            if len(lpath) > 0 and lpath.endswith('.qrc'):
                p = lpath
                if not os.path.isabs(lpath):
                    p = os.path.join(dirUi, lpath)
                else:
                    p = lpath
                qrcPaths.append(p)


        buffer = io.StringIO()  # buffer to store modified XML

        if isinstance(_modifiedui, str):
            f = open(_modifiedui, 'w', encoding='utf-8')
            f.write(doc.toString())
            f.flush()
            f.close()

        buffer.write(doc.toString())
        buffer.flush()
        buffer.seek(0)

        # if existent, make resource file directories available to the python path (sys.path)
        baseDir = os.path.dirname(pathUi)
        tmpDirs = []
        if True:
            for qrcPath in qrcPaths:
                d = os.path.abspath(os.path.join(baseDir, qrcPath))
                d = os.path.dirname(d)
                if os.path.isdir(d) and d not in sys.path:
                    tmpDirs.append(d)
            sys.path.extend(tmpDirs)

        # create requried mockups
        if True:
            FORM_CLASS_MOCKUP_MODULES = [os.path.splitext(os.path.basename(p))[0] for p in qrcPaths]
            FORM_CLASS_MOCKUP_MODULES = [m for m in FORM_CLASS_MOCKUP_MODULES if m not in sys.modules.keys()]
            for mockupModule in FORM_CLASS_MOCKUP_MODULES:
                #print('ADD MOCKUP MODULE {}'.format(mockupModule))

                sys.modules[mockupModule] = resourcemockup

        # load form class
        try:
            FORM_CLASS, _ = uic.loadUiType(buffer, resource_suffix=RC_SUFFIX)
        except Exception as ex1:
            print(doc.toString(), file=sys.stderr)
            info = 'Unable to load {}'.format(pathUi) + '\n{}'.format(str(ex1))
            ex = Exception(info)
            raise ex

        for mockupModule in FORM_CLASS_MOCKUP_MODULES:
            if mockupModule in sys.modules.keys():
                sys.modules.pop(mockupModule)


        buffer.close()

        FORM_CLASSES[pathUi] = FORM_CLASS

        #remove temporary added directories from python path
        for d in tmpDirs:
            sys.path.remove(d)


    return FORM_CLASSES[pathUi]



def typecheck(variable, type_):
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
    vsifile = gdal.VSIFOpenL(fn,'r')
    gdal.VSIFSeekL(vsifile, 0, 2)
    vsileng = gdal.VSIFTellL(vsifile)
    gdal.VSIFSeekL(vsifile, 0, 0)
    return gdal.VSIFReadL(1, vsileng, vsifile)

def write_vsimem(fn:str,data:str):
    """
    Writes data to vsimem path
    :param fn: vsimem path (str)
    :param data: string to write
    :return: result of gdal.VSIFCloseL(vsifile)
    """
    '''Write GDAL vsimem files'''
    vsifile = gdal.VSIFOpenL(fn,'w')
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


def convertMetricUnit(value: float, u1: str, u2: str)->float:
    """
    Converts value `value` from unit `u1` into unit `u2`
    :param value: float | int | might work with numpy.arrays as well
    :param u1: str, identifier of unit 1
    :param u2: str, identifier of unit 2
    :return: float | numpy.array, converted values
             or None in case conversion is not possible
    """

    assert isinstance(u1, str)
    assert isinstance(u2, str)

    u1 = u1.lower()
    u2 = u2.lower()

    e1 = METRIC_EXPONENTS.get(u1)
    e2 = METRIC_EXPONENTS.get(u2)

    if all([arg is not None for arg in [value, e1, e2]]):
        if e1 == e2:
            return copy.copy(value)
        elif isinstance(value, list):
            return [v * 10 ** (e1-e2) for v in value]
        else:
            return value * 10 ** (e1 - e2)
    else:
        return None


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
        #use gdal.Band.GetDescription() for band name
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
            #in case of WMS and other data providers use QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, rasterSource.bandCount() + 1)
            for band in bands:
                name = rasterSource.generateBandName(band)
                colorInterp ='{}'.format(rasterSource.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    name += '({})'.format(colorInterp)
                if leadingBandNumber:
                    name = '{}:{}'.format(band, name)
                results.append(name)

            return results

    return None


def defaultBands(dataset)->list:
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
            db = [b-1 for b in db]
        return db

    else:
        raise Exception()


def bandClosestToWavelength(dataset, wl, wl_unit='nm')->int:
    """
    Returns the band index of an image dataset closest to wavelength `wl`.
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
                wl = convertMetricUnit(wl, wl_unit, ds_wlu)
            return int(np.argmin(np.abs(ds_wl - wl)))
        except:
            pass
    return 0

def parseBadBandList(dataset)->typing.List[int]:
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
        pass

    if not isinstance(dataset, gdal.Dataset):
        return None



    # 1. search for ENVI style definition of band band list
    bblStr1 = dataset.GetMetadataItem('bbl')
    bblStr2 = dataset.GetMetadataItem('bbl', 'ENVI')

    for bblStr in  [bblStr1, bblStr2]:
        if isinstance(bblStr, str) and len(bblStr) > 0:
            parts = bblStr.split(',')
            if len(parts) == dataset.RasterCount:
                bbl = [int(p) for p in parts]

    return bbl


def parseWavelength(dataset):
    """
    Returns the wavelength + wavelength unit of a dataset
    :param dataset:
    :return: (wl, wl_u) or (None, None), if not existing
    """

    wl = None
    wlu = None
    try:
        dataset = gdalDataset(dataset)
    except:
        pass

    if isinstance(dataset, gdal.Dataset):
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
                    if wl is None and len(tmp) > 0 and len(tmp) != dataset.RasterCount:
                        print('Wavelength definition in "{}" contains {} instead {} values'
                              .format(key, len(tmp), dataset.RasterCount), file=sys.stderr)

                if re.search(r'wavelength.units?', key):
                    if re.search(r'(Micrometers?|um|μm)', values, re.I):
                        wlu = 'um'  # fix with python 3 UTF
                    elif re.search(r'(Nanometers?|nm)', values, re.I):
                        wlu = 'nm'
                    elif re.search(r'(Millimeters?|mm)', values, re.I):
                        wlu = 'nm'
                    elif re.search(r'(Centimeters?|cm)', values, re.I):
                        wlu = 'nm'
                    elif re.search(r'(Meters?|m)', values, re.I):
                        wlu = 'nm'
                    elif re.search(r'Wavenumber', values, re.I):
                        wlu = '-'
                    elif re.search(r'GHz', values, re.I):
                        wlu = 'GHz'
                    elif re.search(r'MHz', values, re.I):
                        wlu = 'MHz'
                    elif re.search(r'Index', values, re.I):
                        wlu = '-'
                    else:
                        wlu = '-'

        if wl is not None and len(wl) > dataset.RasterCount:
            wl = wl[0:dataset.RasterCount]

    return wl, wlu


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def qgisAppQgisInterface()->QgisInterface:
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


def getDOMAttributes(elem)->dict:
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[attr.nodeName()] = attr.nodeValue()
    return values


def fileSizeString(num, suffix='B', div=1000)->str:
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


def geo2pxF(geo, gt)->QPointF:
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

def geo2px(geo, gt)->QPoint:
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

def check_vsimem()->bool:
    """
    Checks if the gdal/ogr vsimem is available to the QGIS API
    (might be not the case for QGIS
    :return: bool
    """
    result = False
    try:
        from osgeo import gdal
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

        # create an 2x2x1 in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        assert isinstance(driver, gdal.Driver)
        path = '/vsimem/inmemorytestraster.tif'

        dataSet = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
        assert isinstance(dataSet, gdal.Dataset)
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

    except Exception as ex:
        return False
    return result

def layerGeoTransform(rasterLayer:QgsRasterLayer)->typing.Tuple[float, float, float, float, float, float]:
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

def px2geo(px:QPoint, gt, pxCenter=True)->QgsPointXY:
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


class SpatialPoint(QgsPointXY):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def fromMapCanvasCenter(mapCanvas:QgsMapLayer):
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


def createCRSTransform(src:QgsCoordinateReferenceSystem, dst:QgsCoordinateReferenceSystem):
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

    def upperRightPt(self)->QgsPointXY:
        """
        Returns the upper-right coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperRight())

    def upperLeftPt(self)->QgsPointXY:
        """
        Returns the upper-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperLeft())

    def lowerRightPt(self)->QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerRight())

    def lowerLeftPt(self)->QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerLeft())


    def upperRight(self)->tuple:
        """
        Returns the upper-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMaximum()

    def upperLeft(self)->tuple:
        """
        Returns the upper-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self)->tuple:
        """
        Returns the lower-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMinimum()

    def lowerLeft(self)->tuple:
        """
        Returns the lower-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMinimum()


    def __eq__(self, other)->bool:
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

    def __reduce_ex__(self, protocol):
        return self.__class__, (self.crs().toWkt(),
                                self.xMinimum(), self.yMinimum(),
                                self.xMaximum(), self.yMaximum()
                                ), {}

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return self.__repr__()

    def __repr__(self)->str:
        """
        Returns a representation string
        :return: str
        """

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())


def setToolButtonDefaultActionMenu(toolButton:QToolButton, actions:list):

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

        def __init__(self, info:str, filters:QgsMapLayerProxyModel.Filters, allowEmptyLayer = False):
            self.labelText = info
            self.filters = filters
            self.allowEmptyLayer = allowEmptyLayer

    def __init__(self, *args, layerDescriptions:list=None, **kwds):
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


    def addLayerDescription(self, info:str,
                            filters:QgsMapLayerProxyModel.Filters,
                            allowEmptyLayer = False,
                            layerDescription=None)->QgsMapLayerComboBox:
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




    def mapLayers(self)->list:
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