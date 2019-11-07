# -*- coding: utf-8 -*-

"""
***************************************************************************
    classificationscheme.py

    Methods and Objects to describe raster classifications
    ---------------------
    Date                 : Juli 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import os, json, pickle, warnings, csv, re, sys, typing
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import *
import numpy as np
from osgeo import gdal
from ..utils import gdalDataset, nextColor, loadUIFormClass, findMapLayer, registeredMapLayers


loadClassificationUI = lambda name: loadUIFormClass(os.path.join(os.path.dirname(__file__), name))

DEFAULT_UNCLASSIFIEDCOLOR = QColor('black')
DEFAULT_FIRST_COLOR = QColor('#a6cee3')

MIMEDATA_KEY = 'hub-classscheme'
MIMEDATA_KEY_TEXT = 'text/plain'
MIMEDATA_INTERNAL_IDs = 'classinfo_ids'
MIMEDATA_KEY_QGIS_STYLE = 'application/qgis.style'
MAX_UNIQUE_CLASSES = 100

def findMapLayersWithClassInfo()->list:
    """
    Returns QgsMapLayers from which a ClassificationScheme can be derived.
    Searches in all QgsMapLayerStores known to classification.MAP_LAYER_STORES
    :return: [list-of-QgsMapLayer]
    """

    results = []
    for lyr in registeredMapLayers():
        if isinstance(lyr, QgsVectorLayer) and isinstance(lyr.renderer(), QgsCategorizedSymbolRenderer):
            results.append(lyr)
        elif isinstance(lyr, QgsRasterLayer) and isinstance(lyr.renderer(), QgsPalettedRasterRenderer):
            results.append(lyr)
    return results




def hasClassification(pathOrDataset):
    """
    This function tests if a gdal-readable raster data set contains
    categorical information that can be used to retrieve a ClassificationScheme
    :param pathOrDataset: string | gdal.Dataset
    :return: True | False
    """
    ds = None
    try:
        if isinstance(pathOrDataset, gdal.Dataset):
            ds = pathOrDataset
        elif isinstance(pathOrDataset, str):
            ds = gdal.Open(pathOrDataset)
        elif isinstance(ds, QgsRasterLayer):
            ds = gdal.Open(ds.source())
    except Exception as ex:
        pass

    if not isinstance(ds, gdal.Dataset):
        return False

    for b in range(ds.RasterCount):
        band = ds.GetRasterBand(b + 1)
        assert isinstance(band, gdal.Band)
        if band.GetCategoryNames() or band.GetColorTable():
            return True
    return False


def getTextColorWithContrast(c:QColor)->QColor:
    """
    Returns a QColor with good contrast to c
    :param c: QColor
    :return: QColor
    """
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')



class ClassInfo(QObject):
    sigSettingsChanged = pyqtSignal()

    def __init__(self, label=0, name=None, color=None, parent=None):
        super(ClassInfo, self).__init__(parent)

        if name is None:
            name = 'Unclassified' if label == 0 else 'Class {}'.format(label)

        if color is None:
            if label == 0:
                color = DEFAULT_UNCLASSIFIEDCOLOR
            else:
                color = DEFAULT_FIRST_COLOR


        self.mName = name
        self.mLabel = label
        self.mColor = color
        if color:
            self.setColor(color)


    def setLabel(self, label:int):
        """
        Sets the label value.
        :param label: int, must be >= 0
        """
        assert isinstance(label, int)
        assert label >= 0
        self.mLabel = label
        self.sigSettingsChanged.emit()

    def label(self)->int:
        """
        Returns the class label values
        :return: int
        """
        return self.mLabel

    def color(self)->QColor:
        """
        Returns the class color.
        :return: QColor
        """
        return QColor(self.mColor)

    def name(self)->str:
        """
        Returns the class name
        :return: str
        """
        return self.mName

    def setColor(self, color:QColor):
        """
        Sets the class color.
        :param color: QColor
        """
        assert isinstance(color, QColor)
        self.mColor = color
        self.sigSettingsChanged.emit()

    def setName(self, name:str):
        """
        Sets thes class name
        :param name: str
        """
        assert isinstance(name, str)
        self.mName = name
        self.sigSettingsChanged.emit()


    def pixmap(self, *args)->QPixmap:
        """
        Returns a QPixmap. Default size is 20x20px
        :param args: QPixmap arguments.
        :return: QPixmap
        """
        if len(args) == 0:
            args = (QSize(20, 20),)

        pm = QPixmap(*args)
        pm.fill(self.mColor)
        return pm

    def icon(self, *args)->QIcon:
        """
        Returns the class color as QIcon
        :param args: QPixmap arguments
        :return: QIcon
        """
        return QIcon(self.pixmap(*args))

    def clone(self):
        """
        Create a copy of this ClassInfo
        :return: ClassInfo
        """
        return ClassInfo(name=self.mName, color=self.mColor)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, ClassInfo):
            return False
        return other.mName == self.mName and \
               other.mLabel == self.mLabel and \
               other.mColor.getRgb() == self.mColor.getRgb()

    def __repr__(self):
        return 'ClassInfo' + self.__str__()

    def __str__(self):
        return '{} "{}" ({})'.format(self.mLabel, self.mName, self.mColor.name())

    def json(self)->str:
        return json.dumps([self.label(), self.name(), self.color().name()])

    def fromJSON(self, jsonString:str):
        try:
            label, name, color = json.loads(jsonString)
            color = QColor(color)
            return ClassInfo(label=label, name=name, color=color)
        except:
            return None


class ClassificationScheme(QAbstractTableModel):

    sigClassesRemoved = pyqtSignal(list)
    #sigClassRemoved = pyqtSignal(ClassInfo, int)
    #sigClassAdded = pyqtSignal(ClassInfo, int)
    sigClassesAdded = pyqtSignal(list)
    sigNameChanged = pyqtSignal(str)

    def __init__(self, name : str = None):
        super(ClassificationScheme, self).__init__()
        self.mClasses = []
        self.mName = name
        self.mIsEditable = True

        if name is None:
            name = 'Classification'

        self.mColColor = 'Color'
        self.mColName = 'Name'
        self.mColLabel = 'Label'

    def setIsEditable(self, b:bool):
        """
        Sets if class names and colors can be changed
        :param b: bool
        """
        if b != self.mIsEditable:
            self.mIsEditable = True
            self.dataChanged(self.createIndex(0,0),
                             self.createIndex(self.rowCount()-1, self.columnCount()-1))

    def isEditable(self)->bool:
        """
        Returns if class names and colors can be changed.
        :return: bool
        """
        return self.mIsEditable

    def columnNames(self)->list:
        """
        Returns the column names.
        :return: [list-of-str]
        """
        return [self.mColLabel, self.mColName, self.mColColor]

    def dropMimeData(self, mimeData:QMimeData, action:Qt.DropAction, row:int, column:int, parent:QModelIndex):
        if row == -1:
            row = parent.row()
        if action == Qt.MoveAction:
            if MIMEDATA_INTERNAL_IDs in mimeData.formats():
                ba = bytes(mimeData.data(MIMEDATA_INTERNAL_IDs))
                ids = pickle.loads(ba)

                classesToBeMoved = [c for c in self if id(c) in ids]
                self.beginResetModel()
                for c in reversed(classesToBeMoved):
                    idx = self.classInfo2index(c)


                    #self.beginMoveRows(QModelIndex(), idx.row(), idx.row(), QModelIndex(), row)
                    del self.mClasses[idx.row()]
                    self.mClasses.insert(row, c)
                    #self.endMoveRows()
                self.endResetModel()
                self._updateLabels()
                return True
        elif action == Qt.CopyAction:
            if MIMEDATA_KEY in mimeData.formats():
                cs = ClassificationScheme.fromQByteArray(mimeData.data(MIMEDATA_KEY))
                self.insertClasses(cs[:], row)

        return False

    def mimeData(self, indexes)->QMimeData:
        """
        Returns class infos as QMimeData.
        :param indexes:
        :return:
        """

        if indexes is None:
            indexes = [self.createIndex(r, 0) for r in range(len(self))]

        classes = [self[idx.row()] for idx in indexes]
        cs = ClassificationScheme()
        cs.insertClasses(classes)
        mimeData = QMimeData()
        mimeData.setData(MIMEDATA_KEY, cs.qByteArray())
        mimeData.setData(MIMEDATA_INTERNAL_IDs, QByteArray(pickle.dumps([id(c) for c in classes])))
        mimeData.setText(cs.toString())

        renderer = self.featureRenderer()

        doc = QDomDocument()
        err = ''
        for typeName in ['POLYGON']:
            lyr = QgsVectorLayer('{}?crs=epsg:4326&field=id:integer'.format(typeName), cs.name(), 'memory')
            assert isinstance(lyr, QgsVectorLayer) and lyr.isValid()
            lyr.setRenderer(renderer.clone())
            err = lyr.exportNamedStyle(doc)
            xml = doc.toString()
            s = ""
        mimeData.setData(MIMEDATA_KEY_QGIS_STYLE, doc.toByteArray())
        mimeData.setText(doc.toString())
        return mimeData

    def mimeTypes(self)->list:
        """
        Returns a list of supported mimeTypes.
        :return: [list-of-str]
        """
        return [MIMEDATA_KEY, MIMEDATA_INTERNAL_IDs, MIMEDATA_KEY_TEXT]


    def rowCount(self, parent:QModelIndex=None):
        """
        Returns the number of row / ClassInfos.
        :param parent: QModelIndex
        :return: int
        """
        return len(self.mClasses)

    def columnCount(self, parent: QModelIndex=None):
        return len(self.columnNames())


    def index2ClassInfo(self, index)->ClassInfo:
        if isinstance(index, QModelIndex):
            index = index.row()
        return self.mClasses[index]

    def classInfo2index(self, classInfo:ClassInfo)->QModelIndex:
        row = self.mClasses.index(classInfo)
        return self.createIndex(row, 0)


    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        value = None
        col = index.column()
        row = index.row()
        classInfo = self.index2ClassInfo(row)

        if role == Qt.DisplayRole:
            if col == 0:
                return classInfo.label()
            if col == 1:
                return classInfo.name()
            if col == 2:
                return classInfo.color().name()

        if role == Qt.ForegroundRole:
            if col == self.mColColor:
                return QBrush(getTextColorWithContrast(classInfo.color()))

        if role == Qt.BackgroundColorRole:
            if col == 2:
                return QBrush(classInfo.color())

        if role == Qt.AccessibleTextRole:
            if col == 0:
                return str(classInfo.label())
            if col == 1:
                return classInfo.name()
            if col == 2:
                return classInfo.color().name()

        if role == Qt.ToolTipRole:
            if col == 0:
                return 'Class label "{}"'.format(classInfo.label())
            if col == 1:
                return 'Class name "{}"'.format(classInfo.name())
            if col == 2:
                return 'Class color "{}"'.format(classInfo.color().name())

        if role == Qt.EditRole:
            if col == 1:
                return classInfo.name()
            if col == 2:
                return classInfo.color()

        if role == Qt.UserRole:
            return classInfo

        return None

    def supportedDragActions(self):
        return Qt.MoveAction

    def supportedDropActions(self):
        return Qt.MoveAction | Qt.CopyAction

    def setData(self, index: QModelIndex, value, role: int):
        if not index.isValid():
            return False

        col = index.column()
        row = index.row()
        classInfo = self.index2ClassInfo(row)
        b = False
        if role == Qt.EditRole:
            if col == 1:
                classInfo.setName(value)
                b = True
            if col == 2:
                classInfo.setColor(value)
                b = True
        if b:
            self.dataChanged.emit(index, index, [role])
        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        col = index.column()

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if self.mIsEditable:
            flags |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
            if col == 1:
                flags |= Qt.ItemIsEditable
        return flags


    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):

        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.columnNames()[section]

        return super(ClassificationScheme, self).headerData(section, orientation, role)


    def setName(self, name:str='')->str:
        """
        Sets ClassificationScheme name
        :param name: str
        :return: str, the name
        """
        b = name != self.mName
        self.mName = name
        if b:
            self.sigNameChanged.emit(self.mName)
        return self.mName

    def name(self)->str:
        """
        Returns the ClassificationScheme name
        :return:
        """
        return self.mName

    def json(self)->str:
        """
        Returns a JSON string of this ClassificationScheme which can be deserialized with ClassificationScheme.fromJSON()
        :return: str, JSON string
        """
        data = {'name':self.mName,
                'classes':[(c.label(), c.name(), c.color().name()) for c in self]
                }

        return json.dumps(data)

    def pickle(self)->bytes:
        """
        Serializes this ClassificationScheme a byte object, which can be deserializes with ClassificationScheme.fromPickle()
        :return: bytes
        """
        return pickle.dumps(self.json())

    def qByteArray(self)->QByteArray:
        """
        Serializes this ClassicationScheme as QByteArray.
        Can be deserialized with ClassificationScheme.fromQByteArray()
        :return: QByteArray
        """
        return QByteArray(self.pickle())

    @staticmethod
    def fromQByteArray(array:QByteArray):
        return ClassificationScheme.fromPickle(bytes(array))

    @staticmethod
    def fromPickle(pkl:bytes):
        return ClassificationScheme.fromJson(pickle.loads(pkl))


    @staticmethod
    def fromFile(p:str):
        try:
            if os.path.isfile(p):
                if p.endswith('.json'):
                    jsonStr = None
                    with open(p, 'r') as f:
                        jsonStr = f.read()
                    return ClassificationScheme.fromJson(jsonStr)

        except Exception as ex:
            print(ex, file=sys.stderr)
        return None

    @staticmethod
    def fromJson(jsonStr:str):
        try:
            data = json.loads(jsonStr)

            s = ""
            cs = ClassificationScheme(name= data['name'])
            classes = []
            for classData in data['classes']:
                label, name, colorName = classData
                classes.append(ClassInfo(label=label, name=name, color=QColor(colorName)))
            cs.insertClasses(classes)
            return cs
        except Exception as ex:
            print(ex, file=sys.stderr)
            return None


    def rasterRenderer(self, band=0)->QgsPalettedRasterRenderer:
        """
        Returns the ClassificationScheme as QgsPalettedRasterRenderer
        :return: ClassificationScheme
        """
        #DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)


        classes = []
        for classInfo in self:
            qgsClass = QgsPalettedRasterRenderer.Class(
                classInfo.label(),
                classInfo.color(),
                classInfo.name())
            classes.append(qgsClass)
        renderer = QgsPalettedRasterRenderer(None, band, classes)
        return renderer

    @staticmethod
    def fromRasterRenderer(renderer:QgsRasterRenderer):
        """
        Extracts a ClassificatonScheme from a QgsRasterRenderer
        :param renderer: QgsRasterRenderer
        :return: ClassificationScheme
        """
        if not isinstance(renderer, QgsPalettedRasterRenderer):
            return None

        classes = []
        for qgsClass in renderer.classes():
            classInfo = ClassInfo(label=qgsClass.value,
                                  name=qgsClass.label,
                                  color=QColor(qgsClass.color))
            classes.append(classInfo)

        cs = ClassificationScheme()
        cs.insertClasses(classes)

        return cs

    def featureRenderer(self, symbolType:typing.Union[QgsMarkerSymbol, QgsFillSymbol, QgsLineSymbol]=QgsFillSymbol)->QgsCategorizedSymbolRenderer:
        """
        Returns the ClassificationScheme as QgsCategorizedSymbolRenderer
        :return: ClassificationScheme
        """

        r = QgsCategorizedSymbolRenderer(self.name(), [])

        for c in self:
            assert isinstance(c, ClassInfo)
            symbol = symbolType()
            symbol.setColor(QColor(c.color()))
            cat = QgsRendererCategory(c.label(), symbol, c.name(), render=True)
            r.addCategory(cat)
        return r


    @staticmethod
    def fromFeatureRenderer(renderer:QgsCategorizedSymbolRenderer):
        """
        Extracts a ClassificatonScheme from a QgsCategorizedSymbolRenderer
        :param renderer: QgsCategorizedSymbolRenderer
        :return: ClassificationScheme
        """
        if not isinstance(renderer, QgsCategorizedSymbolRenderer):
            return None
        classes = []

        # move a None element to first position
        categories = renderer.categories()
        cNames = [c.value() for c in categories]
        if None in cNames:
            i = cNames.index(None)
            categories.insert(0, categories.pop(i))

        for cat in categories:
            assert isinstance(cat, QgsRendererCategory)
            c = ClassInfo(name=cat.label(), color=QColor(cat.symbol().color()))
            classes.append(c)
        cs = ClassificationScheme()
        cs.insertClasses(classes)
        return cs


    def clear(self):
        """
        Removes all ClassInfos
        """
        self.beginRemoveColumns(QModelIndex(), 0, self.rowCount()-1)
        removed = self.mClasses[:]
        del self.mClasses[:]
        self.endRemoveRows()
        self.sigClassesRemoved.emit(removed)


    def clone(self):
        return self.copy()

    def copy(self):
        """
        Create a copy of this ClassificationScheme
        :return:
        """
        cs = ClassificationScheme()
        classes = [c.clone() for c in self.mClasses]
        cs.insertClasses(classes, 0)
        return cs

    def __getitem__(self, slice):
        return self.mClasses[slice]

    def __delitem__(self, slice):
        classes = self[slice]
        self.removeClasses(classes)

    def __contains__(self, item):
        return item in self.mClasses

    def __len__(self):
        return len(self.mClasses)

    def __iter__(self):
        return iter(self.mClasses)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not (isinstance(other, ClassificationScheme) and len(self) == len(other)):
            return False
        return all(self[i] == other[i] for i in range(len(self)))

    def __str__(self):
        return self.__repr__() + '{} classes'.format(len(self))


    def range(self):
        """
        Returns the class label range (min,max).
        """
        labels = self.classLabels()
        return min(labels), max(labels)

    def classNames(self):
        """
        Returns all class names.
        :return: [list-of-class-names (str)]
        """
        return [c.name() for c in self.mClasses]

    def classColors(self):
        """
        Returns all class color.
        :return: [list-of-class-colors (QColor)]
        """
        return [QColor(c.color()) for c in self.mClasses]

    def classLabels(self)->list:
        """
        Returns the list of class labels [0,...,n-1]
        :return: [list-of-int]
        """
        return [c.label() for c in self.mClasses]

    def classColorArray(self)->np.ndarray:
        """
        Returns the RGBA class-colors as array
        :return: numpy.ndarray([nClasses,4])
        """
        return np.asarray([c.color().getRgb() for c in self])

    def gdalColorTable(self)->gdal.ColorTable:
        """
        Returns the class colors as GDAL Color Table
        :return: gdal.Colortable
        """
        ct = gdal.ColorTable()
        for i, c in enumerate(self):
            assert isinstance(c, ClassInfo)
            ct.SetColorEntry(i, c.mColor.getRgb())
        return ct

    def _updateLabels(self):
        """
        Assigns class labels according to the ClassInfo position
        """
        for i, c in enumerate(self.mClasses):
            c.mLabel = i
        self.dataChanged.emit(self.createIndex(0,0),
                              self.createIndex(self.rowCount()-1,0),
                              [Qt.DisplayRole, Qt.ToolTipRole])
        s = ""

    def removeClasses(self, classes):
        """
        Removes as single ClassInfo or a list of ClassInfos.
        :param classes: ClassInfo or [list-of-ClassInfo-to-remove]
        :returns: [list-of-removed-ClassInfo]
        """
        if isinstance(classes, ClassInfo):
            classes = [classes]
        assert isinstance(classes, list)

        removedIndices = []
        for c in classes:
            assert c in self.mClasses
            removedIndices.append(self.mClasses.index(c))

        removedIndices = list(reversed(sorted(removedIndices)))
        removedClasses = []
        for i in removedIndices:
            c = self.mClasses[i]
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mClasses.remove(c)
            removedClasses.append(c)
            self.endRemoveRows()
        self._updateLabels()
        self.sigClassesRemoved.emit(removedClasses)



    def createClasses(self, n:int):
        """
        Creates n new classes with default an default initialization.
        Can be used to populate the ClassificationScheme.
        :param n: int, number of classes to add.
        """
        assert isinstance(n, int)
        assert n >= 0
        classes = []

        if len(self) > 0:
            nextCol = nextColor(self[-1].color())
        else:
            nextCol = DEFAULT_FIRST_COLOR

        for i in range(n):
            j = len(self) + i
            if j == 0:
                color = QColor('black')
                name = 'Unclassified'
            else:
                color = QColor(nextCol)
                nextCol = nextColor(nextCol)
                name = 'Class {}'.format(j)
            classes.append(ClassInfo(name=name, color=color))
        self.insertClasses(classes)

    def addClasses(self, classes, index=None):
        warnings.warn('use insertClasses()', DeprecationWarning)
        self.insertClasses(classes, index=index)

    def insertClasses(self, classes, index=None):
        """
        Adds / inserts a list of ClassInfos
        :param classes: [list-of-ClassInfo]
        :param index: int, index to insert the first of the new classes.
                           defaults to len(ClassificationScheme)

        """
        if isinstance(classes, ClassInfo):
            classes = [ClassInfo]

        assert isinstance(classes, list)
        if len(classes) == 0:
            return

        for c in classes:
            assert isinstance(c, ClassInfo)
            assert id(c) not in [id(c) for c in self.mClasses], 'You cannot add the same ClassInfo instance to a ClassificationScheme twice. Create a copy first.'

        if index is None:
            #default: add new classes to end of list
            index = len(self.mClasses)
        #negative index? insert to beginning
        index = max(index, 0)


        self.beginInsertRows(QModelIndex(), index, index+len(classes)-1)
        for i, c in enumerate(classes):
            assert isinstance(c, ClassInfo)
            index = index + i
            #c.sigSettingsChanged.connect(self.onClassInfoSettingChanged)
            self.mClasses.insert(index, c)
        self.endInsertRows()
        self._updateLabels()
        self.sigClassesAdded.emit(classes)


    #sigClassInfoChanged = pyqtSignal(ClassInfo)
    #def onClassInfoSettingChanged(self, *args):
    #    self.sigClassInfoChanged.emit(self.sender())

    def classIndexFromValue(self, value, matchSimilarity=False)->int:
        """
        Get a values and returns the index of ClassInfo that matches best to.
        :param value: any
        :return: int
        """
        classNames = self.classNames()
        i = -1

        #1. match on identity
        if isinstance(value, (int, float)):
            i = int(value)

        elif isinstance(value, str):
            if value in classNames:
                i = classNames.index(value)

        #2. not found? match on similarity
        if i == -1 and matchSimilarity == True:
            if isinstance(value, (int, float)):
                pass

            elif isinstance(value, str):
                if value in classNames:
                    i = classNames.index(value)
            pass
        return i

    def classFromValue(self, value, matchSimilarity=False)->ClassInfo:
        i = self.classIndexFromValue(value, matchSimilarity=matchSimilarity)
        if i != -1:
            return self[i]
        else:
            return None

    def addClass(self, c, index=None):
        warnings.warn('Use insert class', DeprecationWarning)


    def insertClass(self, c, index=None):
        """
        Adds a ClassInfo
        :param c: ClassInfo
        :param index: int, index to add the ClassInfo. Defaults to the end.
        """
        assert isinstance(c, ClassInfo)
        self.insertClasses([c], index=index)


    def saveToRasterBand(self, band:gdal.Band):
        """
        Saves the ClassificationScheme to the gdal.Band.
        ClassInfo names are stored by gdal.Band.SetCategoryNames and colors as gdal.ColorTable.
        :param band: gdal.Band
        """
        assert isinstance(band, gdal.Band)
        ct = gdal.ColorTable()
        cat = []
        for i, classInfo in enumerate(self.mClasses):
            c = classInfo.mColor
            cat.append(classInfo.mName)
            assert isinstance(c, QColor)
            rgba = (c.red(), c.green(), c.blue(), c.alpha())
            ct.SetColorEntry(i, rgba)

        band.SetColorTable(ct)
        band.SetCategoryNames(cat)


    def saveToRaster(self, path, bandIndex=0):
        """
        Saves this ClassificationScheme to an raster image
        :param path: path (str) of raster image or gdal.Dataset instance
        :param bandIndex: band index of raster band to set this ClassificationScheme.
                          Defaults to 0 = the first band
        """
        if isinstance(path, str):
            ds = gdal.Open(path)
        elif isinstance(path, gdal.Dataset):
            ds = path

        assert isinstance(ds, gdal.Dataset)
        assert ds.RasterCount < bandIndex
        band = ds.GetRasterBand(bandIndex + 1)
        self.saveToRasterBand(band)


        ds = None

    def toString(self, sep=';')->str:
        """
        A quick dump of all ClassInfos
        :param sep: value separator, ';' by default
        :return: str
        """
        lines = ['ClassificationScheme("{}")'.format(self.name())]
        lines += [sep.join(['label', 'name', 'color'])]
        for classInfo in self.mClasses:
            c = classInfo.color()
            info = [classInfo.label(), classInfo.name(), c.name()]
            info = ['{}'.format(v) for v in info]
            lines.append(sep.join(info))
        return '\n'.join(lines)

    def saveToCsv(self, path:str, sep:str=';', mode:str = None)->str:
        """
        Saves the ClassificationScheme as CSV table.
        :param path: str, path of CSV file
        :param sep: separator (';' by default)
        :returns: the path of written file (if something was written)
        """
        if mode == None:
            lines = self.toString(sep=sep)
            with open(path, 'w') as f:
                f.write(lines)

            return path

        return None


    def saveToJson(self, path:str, mode:str=None)->str:
        """
        Save the ClassificationScheme as JSON file.
        :param path: str, path of JSON file
        :return: path of written file
        """
        if mode == None:
            lines = self.json()
            with open(path, 'w') as f:
                f.write(lines)
            return path

        return None


    @staticmethod
    def create(n):
        """
        Create a ClassificationScheme with n classes (including 'Unclassified' with label = 0)
        :param n: number of classes including 'Unclassified'
        :return: ClassificationScheme
        """
        s = ClassificationScheme()
        s.createClasses(n)
        return s

    @staticmethod
    def fromMimeData(mimeData:QMimeData):

        if not isinstance(mimeData, QMimeData):
            return None

        if MIMEDATA_KEY in mimeData.formats():
            ba = ClassificationScheme.fromQByteArray(mimeData.data(MIMEDATA_KEY))
            if isinstance(ba, ClassificationScheme):
                return ba
        if MIMEDATA_KEY_TEXT in mimeData.formats():
            ba = ClassificationScheme.fromQByteArray(mimeData.data(MIMEDATA_KEY_TEXT))
            if isinstance(ba, ClassificationScheme):
                return ba
        if MIMEDATA_KEY_QGIS_STYLE in mimeData.formats():
            s = ""

        return None

    @staticmethod
    def fromUniqueFieldValues(layer:QgsVectorLayer, fieldIndex):
        scheme = None

        if not isinstance(layer, QgsVectorLayer):
            return scheme

        if isinstance(fieldIndex, str):
            fieldIndex = layer.fields().indexFromName(fieldIndex)
        elif isinstance(fieldIndex, QgsField):
            fieldIndex = layer.fields().indexFromName(fieldIndex.name())

        if not isinstance(fieldIndex, int) and fieldIndex >= 0 and fieldIndex < layer.fields().count():
            return scheme

        field = layer.fields().at(fieldIndex)
        if re.search('int|string', field.typeName(), re.I):
            values = layer.uniqueValues(fieldIndex, limit=MAX_UNIQUE_CLASSES)
            values = sorted(values)

            if len(values) > 0:
                scheme = ClassificationScheme()
                scheme.insertClass(ClassInfo(0, 'unclassified'))
                if field.isNumeric():
                    for v in values:
                        scheme.insertClass(ClassInfo(int(v), name=str(v)))
                else:
                    for i, v in enumerate(values):
                        scheme.insertClass(ClassInfo(i+1, name=str(v)))

        return scheme

    @staticmethod
    def fromMapLayer(layer:QgsMapLayer):
        """

        :param layer:
        :return:
        """
        scheme = None
        if isinstance(layer, QgsRasterLayer):
            scheme = ClassificationScheme.fromRasterRenderer(layer.renderer())
            if not isinstance(scheme, ClassificationScheme):
                if layer.dataProvider().name() == 'gdal':
                    scheme = ClassificationScheme.fromRasterImage(layer.source())


        if isinstance(layer, QgsVectorLayer):
            scheme = ClassificationScheme.fromFeatureRenderer(layer.renderer())

        return scheme

    @staticmethod
    def fromRasterBand(band: gdal.Band):
        """
        Reads the ClassificationScheme of a gdal.Band
        :param band: gdal.Band
        :return: ClassificationScheme, None if classes are undefined.
        """
        assert isinstance(band, gdal.Band)
        cat = band.GetCategoryNames()
        ct = band.GetColorTable()
        if cat is None or len(cat) == 0:
            return None
        scheme = ClassificationScheme()
        classes = []
        for i, catName in enumerate(cat):
            cli = ClassInfo(name=catName, label=i)
            if ct is not None:
                cli.setColor(QColor(*ct.GetColorEntry(i)))
            classes.append(cli)
        scheme.insertClasses(classes)
        return scheme

    @staticmethod
    def fromRasterImage(path, bandIndex=None):
        """
        Reads a ClassificationScheme from a gdal.Dataset
        :param path: str with path to gdal.Dataset or gdal.Dataset instances
        :param bandIndex: int with band index
        :return: ClassificationScheme
        """
        ds = gdalDataset(path)
        assert ds is not None

        if bandIndex is None:
            for b in range(ds.RasterCount):
                band = ds.GetRasterBand(b + 1)
                cat = band.GetCategoryNames()

                if cat != None:
                    bandIndex = b
                    break
                s = ""
            if bandIndex is None:
                return None

        assert bandIndex >= 0 and bandIndex < ds.RasterCount
        band = ds.GetRasterBand(bandIndex + 1)
        return ClassificationScheme.fromRasterBand(band)

    @staticmethod
    def fromCsv(pathCSV:str, mode:str=None):
        """
        Read the ClassificationScheme from a CSV table
        :param path: str, path of CSV file
        :return: ClassificationScheme
        """
        text = None
        with open(pathCSV) as f:
            text = f.read()
        if not isinstance(text, str):
            raise Exception('Unable to read {}'.format(pathCSV))

        lines = text.splitlines()
        lines = [l.strip() for l in lines]
        lines = [l for l in lines if len(l) > 0]
        if len(lines) <= 1:
            raise Exception('CSV does not contain enough values')

        match = re.search(r'ClassificationScheme\("(.*)"\)', text)
        if match:
            name = re.search(r'ClassificationScheme\("(.*)"\)', text).group(1)
        else:
            name = 'Classification'

        b = False
        columnNames = None
        delimiter = ';'
        for i, line in enumerate(lines):
            match = re.search(r'^[ ]*(?P<label>label)[ ]*[;\t,][ ]*(?P<name>name)[ ]*([;\t,][ ]*(?P<color>color))?',
                              line, re.IGNORECASE)
            if match:
                delimiter = re.search(r'[;\t,]', line).group()
                b = True
                break

        if not match:
            raise Exception('Missing column header "label;name:color"')

        cName = match.group('name')
        cColor = match.group('color')
        fieldnames = [match.group('label'), match.group('name'), match.group('color')]

        cs = ClassificationScheme()
        cs.setName(name)
        # read CSV data
        reader = csv.DictReader(lines[i:], delimiter=delimiter)

        iName = None
        iColor = None
        for i, name in enumerate(reader.fieldnames):
            if iName is None and re.search(r'name', name, re.I):
                iName = i
            if iColor is None and re.search(r'color', name, re.I):
                iColor = i
        rows = [row for row in reader]

        nc = len(rows)
        if nc == 0:
            return None

        cs = ClassificationScheme.create(nc)
        for i, row in enumerate(rows):
            c = cs[i]
            assert isinstance(c, ClassInfo)
            if iName is not None:
                c.setName(row[fieldnames[iName]])
            if iColor is not None:
                colorValue = row[fieldnames[iColor]].strip()

                match = re.search(r'^(?P<R>\d+),(?P<G>\d+),(?P<B>\d+)(,(?P<A>\d+))?$', colorValue)
                if match:
                    R = int(match.group('R'))
                    G = int(match.group('G'))
                    B = int(match.group('B'))
                    A = match.group('B')
                    if A:
                        A = int(A)
                    c.setColor(QColor(R,G,B,A))
                else:
                    c.setColor(QColor(colorValue))

        return cs

    def saveToQml(self, path):
        """
        Saves the class infos into a QML file
        :param path: str, path of QML file
        """
        raise NotImplementedError()

    @staticmethod
    def fromQml(path:str):
        """
        Reads a ClassificationScheme from a QML file.
        :param path: str, path to QML file
        :return: ClassificationScheme
        """
        raise NotImplementedError()


class ClassificationSchemeComboBoxModel(QAbstractListModel):

    def __init__(self):
        super(ClassificationSchemeComboBoxModel, self).__init__()

        self.mClassScheme = None
        self.mAllowEmptyField = False

    def setAllowEmptyField(self, b:bool):
        assert isinstance(b, bool)
        changed = self.mAllowEmptyField != b

        if changed:
            if b:
                self.beginInsertRows(QModelIndex(), 0, 0)
                self.mAllowEmptyField = b
                self.endInsertRows()
            else:
                self.beginRemoveRows(QModelIndex(), 0, 0)
                self.mAllowEmptyField = b
                self.endRemoveRows()



    def allowEmptyField(self)->bool:
        return self.mAllowEmptyField

    def setClassificationScheme(self, classScheme:ClassificationScheme):
        assert isinstance(classScheme, ClassificationScheme)
        self.beginResetModel()
        self.mClassScheme = classScheme
        self.endResetModel()

    def classificationScheme(self)->ClassificationScheme:
        return self.mClassScheme

    def rowCount(self, parent)->int:
        if not isinstance(self.mClassScheme, ClassificationScheme):
            return 0

        n = len(self.mClassScheme)
        if self.allowEmptyField():
            n += 1
        return n

    def columnCount(self, parent: QModelIndex):
        return 1

    def idx2csIdx(self, index:QModelIndex):

        if not isinstance(self.mClassScheme, ClassificationScheme):
            return QModelIndex()

        if self.allowEmptyField():
            return self.mClassScheme.createIndex(index.row() - 1, index.column())
        else:
            return self.mClassScheme.createIndex(index.row(), index.column())

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):

        if not index.isValid():
            return None

        if self.allowEmptyField() and index.row() == 0:
            if role == Qt.DisplayRole:
                return ''

        idxCs = self.idx2csIdx(index)
        if not idxCs.isValid():
            return None
        else:

            classInfo = self.mClassScheme.data(idxCs, role=Qt.UserRole)
            assert isinstance(classInfo, ClassInfo)
            if role == Qt.UserRole:
                return classInfo
            assert isinstance(classInfo, ClassInfo)
            nCols = self.mClassScheme.columnCount(idxCs)
            if role in [Qt.DisplayRole, Qt.ToolTipRole, Qt.WhatsThisRole]:
                infos = []
                for col in range(nCols):
                    idx = self.mClassScheme.createIndex(idxCs.row(), col)
                    infos.append(str(self.mClassScheme.data(idx, role=role)))
                if role == Qt.DisplayRole:
                    return ' '.join(infos[0:2])
                if role == Qt.ToolTipRole:
                    return '\n'.join(infos)
                if role == Qt.WhatsThisRole:
                    return '\n'.join(infos)

            elif role == Qt.DecorationRole:
                return classInfo.icon()


        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return None
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class ClassificationSourceComboBox(QgsMapLayerComboBox):

    def __init__(self, parent):
        super(ClassificationSourceComboBox, self).__init__(parent)


    def addClassificationSource(self, source):

        if hasClassification(source):
            pass

    def currentClassificationScheme(self)->ClassificationScheme:

        raise NotImplementedError()

    def currentClassificationSource(self)->str:

        raise NotImplementedError()


class ClassificationSchemeComboBox(QComboBox):

    def __init__(self, parent=None, classification:ClassificationScheme=None):
        super(ClassificationSchemeComboBox, self).__init__(parent)
        if not isinstance(classification, ClassificationScheme):
            classification = ClassificationScheme()
        self.view().setMinimumWidth(200)
        model = ClassificationSchemeComboBoxModel()
        model.setClassificationScheme(classification)
        self.setModel(model)

    def classIndexFromValue(self, value)->int:
        """
        Returns the index
        :param value:
        :return:
        """
        cs = self.classificationScheme()
        i = cs.classIndexFromValue(value)

        if isinstance(self.mModel, ClassificationSchemeComboBoxModel) and self.mModel.allowEmptyField():
            i += 1
        return i

    def setModel(self, model: ClassificationSchemeComboBoxModel):
        """
        Sets the combobox model. Must be of type `ClassificationSchemeComboBoxModel`.
        :param model: ClassificationSchemeComboBoxModel
        """
        assert isinstance(model, ClassificationSchemeComboBoxModel)
        super(ClassificationSchemeComboBox, self).setModel(model)
        self.mModel = model

    def classificationScheme(self)->ClassificationScheme:
        """
        Returns the ClassificationScheme
        :return: ClassificationScheme
        """
        return self.mModel.classificationScheme()

    def setClassificationScheme(self, classificationScheme:ClassificationScheme):
        """
        Specifies the ClassificationScheme which is represented by this mode.
        :param classificationScheme: ClassificationScheme
        """
        self.mModel.setClassificationScheme(classificationScheme)

    def currentClassInfo(self)->ClassInfo:
        """
        Returns the currently selected ClassInfo
        :return: ClassInfo
        """
        i = self.currentIndex()
        classInfo = None
        if i >= 0 and i < self.count():
            classInfo = self.itemData(i, role=Qt.UserRole)
        return classInfo

class ClassificationSchemeWidget(QWidget, loadClassificationUI('classificationscheme.ui')):

    sigValuesChanged = pyqtSignal()

    def __init__(self, parent=None, classificationScheme=None):
        super(ClassificationSchemeWidget, self).__init__(parent)
        self.setupUi(self)

        self.mScheme = ClassificationScheme()
        if classificationScheme is not None:
            self.setClassificationScheme(classificationScheme)




        assert isinstance(self.tableClassificationScheme, QTableView)
        #self.tableClassificationScheme.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableClassificationScheme.setModel(self.mScheme)
        self.tableClassificationScheme.doubleClicked.connect(self.onTableDoubleClick)
        self.tableClassificationScheme.resizeColumnsToContents()
        self.selectionModel = QItemSelectionModel(self.mScheme)
        self.selectionModel.selectionChanged.connect(self.onSelectionChanged)
        self.onSelectionChanged()  # enable/disable widgets depending on a selection
        self.tableClassificationScheme.setSelectionModel(self.selectionModel)

        self.initActions()

    def onCopyClasses(self):

        classes = self.selectedClasses()
        if len(classes) == 0:
            return
        cs = ClassificationScheme()
        cs.insertClasses(classes)
        cb = QApplication.clipboard()
        assert isinstance(cb, QClipboard)
        cb.setMimeData(cs.mimeData(None))

    def onPasteClasses(self):
        cb = QApplication.clipboard()
        assert isinstance(cb, QClipboard)
        mimeData = QApplication.clipboard().mimeData()

        cs = ClassificationScheme.fromMimeData(mimeData)
        if isinstance(cs, ClassificationScheme):
            self.mScheme.insertClasses(cs[:])

    def onSaveClasses(self):

        classes = self.selectedClasses()
        if len(classes) == 0:
            return

        cs = ClassificationScheme()
        cs.insertClasses(classes)

        filter = "CSV (*.csv *.txt);;JSON (*.json)"
        path, filter = QFileDialog.getSaveFileName(self, "Save classes to file",
                                                   "/home", filter)
        if isinstance(path, str) and len(path) > 0:

            if path.endswith('.json'):

                pass

            elif path.endswith('.csv'):

                cs.saveToCsv(path)

            if filter == 'csv':
                pass

            s  =""

    def onLoadClassesFromRenderer(self, layer):
        cs = ClassificationScheme.fromMapLayer(layer)
        if isinstance(cs, ClassificationScheme):
            self.mScheme.insertClasses(cs[:])

    def onLoadClassesFromField(self, layer, field):

        if field is None:
            raise NotImplementedError()

        cs = ClassificationScheme.fromUniqueFieldValues(layer, field)
        if isinstance(cs, ClassificationScheme):
            self.mScheme.insertClasses(cs[:])
        pass

    def onLoadClasses(self, mode:str):
        """
        Opens a dialog to add ClassInfos from other sources, like raster images, text files and QgsMapLayers.
        :param mode: 'raster', 'layer', 'textfile'
        """
        if mode == 'raster':
            filter = QgsProviderRegistry.instance().fileRasterFilters()
            path, filter = QFileDialog.getOpenFileName(self,
                                                   "Read classes from raster image",
                                                   "/home", filter)
            if isinstance(path, str) and os.path.isfile(path):
                cs = ClassificationScheme.fromRasterImage(path)
                if isinstance(cs, ClassificationScheme):
                    self.mScheme.insertClasses(cs[:])


        if mode == 'layer':
            possibleLayers = findMapLayersWithClassInfo()
            if len(possibleLayers) == 0:
                QMessageBox.information(self, 'Load classes from layer', 'No layers with categorical render styles available.')
            else:
                choices = ['{} ({})'.format(l.name(), l.source()) for l  in possibleLayers]

                dialog = QInputDialog(parent=self)
                dialog.setWindowTitle('Load classes from layer')
                dialog.setTextValue('Select map layer')
                dialog.setComboBoxItems(choices)
                dialog.setOption(QInputDialog.UseListViewForComboBoxItems)
                if dialog.exec_() == QDialog.Accepted:
                    selection = dialog.textValue()
                    i = choices.index(selection)
                    layer = possibleLayers[i]
                    if isinstance(layer, QgsVectorLayer):
                        cs = ClassificationScheme.fromFeatureRenderer(layer.renderer())
                    elif isinstance(layer, QgsRasterLayer):
                        cs = ClassificationScheme.fromRasterRenderer(layer.renderer())
                    if isinstance(cs, ClassificationScheme):
                        self.mScheme.insertClasses(cs[:])
            pass

        if mode == 'textfile':

            filter = "CSV (*.csv *.txt);;JSON (*.json);;QML (*.qml)"
            path, filter = QFileDialog.getOpenFileName(self,
                                                   "Read classes from text file",
                                                    "/home", filter)
            if isinstance(path, str) and os.path.isfile(path):
                cs = ClassificationScheme.fromFile()
                if isinstance(cs, ClassificationScheme):
                    self.mScheme.insertClasses(cs[:])


    def initActions(self):

        m = QMenu('Load classes')
        m.setToolTip('Load classes ...')
        a = m.addAction('Load from raster')
        a.triggered.connect(lambda : self.onLoadClasses('raster'))
        a = m.addAction('Load from map layer')
        a.triggered.connect(lambda : self.onLoadClasses('layer'))
        a = m.addAction('Load from other textfile')
        a.triggered.connect(lambda : self.onLoadClasses('textfile'))


        parent = self.parent()
        if isinstance(parent, ClassificationSchemeEditorConfigWidget):
            layer = parent.layer()
            idx = parent.field()

            if isinstance(layer, QgsVectorLayer) and idx >= 0:
                field = layer.fields().at(idx)
                m.addSeparator()
                a = m.addAction('Unique values "{}"'.format(field.name()))
                a.triggered.connect(lambda _, lyr=layer, f=idx: self.onLoadClassesFromField(lyr, idx))

                if isinstance(layer.renderer(), QgsCategorizedSymbolRenderer):
                    a = m.addAction('Current Symbols'.format(layer.name()))
                    a.triggered.connect(lambda _, lyr=layer: self.onLoadClassesFromRenderer(lyr))


        self.btnLoadClasses.setMenu(m)

        self.actionRemoveClasses.triggered.connect(self.removeSelectedClasses)
        self.actionAddClasses.triggered.connect(lambda : self.createClasses(1))

        self.actionSaveClasses.setIcon(QIcon(r'://images/themes/default/mActionFileSaveAs.svg'))
        self.actionSaveClasses.triggered.connect(self.onSaveClasses)

        QApplication.clipboard().dataChanged.connect(self.onClipboard)
        self.actionPasteClasses.setIcon(QIcon(r'://images/themes/default/mActionEditPaste.svg'))
        self.actionPasteClasses.triggered.connect(self.onPasteClasses)

        self.actionCopyClasses.setIcon(QIcon(r'://images/themes/default/mActionEditCopy.svg'))
        self.actionCopyClasses.triggered.connect(self.onCopyClasses)

        self.btnSaveClasses.setDefaultAction(self.actionSaveClasses)
        self.btnRemoveClasses.setDefaultAction(self.actionRemoveClasses)
        self.btnAddClasses.setDefaultAction(self.actionAddClasses)
        self.btnCopyClasses.setDefaultAction(self.actionCopyClasses)
        self.btnPasteClasses.setDefaultAction(self.actionPasteClasses)

        self.onClipboard()

    def onClipboard(self, *args):
        mimeData = QApplication.clipboard().mimeData()
        b = isinstance(mimeData, QMimeData) and (MIMEDATA_KEY_TEXT in mimeData.formats() or MIMEDATA_KEY_QGIS_STYLE in mimeData.formats())
        self.actionPasteClasses.setEnabled(b)


    def onTableDoubleClick(self, idx):
        model = self.tableClassificationScheme.model()
        assert isinstance(model, ClassificationScheme)
        classInfo = model.index2ClassInfo(idx)
        if idx.column() == model.columnNames().index(model.mColColor):
            c = QColorDialog.getColor(classInfo.mColor, self.tableClassificationScheme, \
                                      'Set color for "{}"'.format(classInfo.name()))
            model.setData(idx, c, role=Qt.EditRole)

    def onSelectionChanged(self, *args):
        b = self.selectionModel is not None and len(self.selectionModel.selectedRows()) > 0
        self.actionRemoveClasses.setEnabled(b)
        self.actionCopyClasses.setEnabled(b)
        self.actionSaveClasses.setEnabled(b)

    def createClasses(self, n):
        self.mScheme.createClasses(n)




    def selectedClasses(self)->list:
        """
        Returns the list of selected ClassInfos
        :return: [list-of-ClassInfo]
        """
        indices = reversed(self.selectionModel.selectedRows())
        return [self.mScheme.index2ClassInfo(idx) for idx in indices]

    def removeSelectedClasses(self):
        classes = self.selectedClasses()
        if len(classes) > 0:
            self.mScheme.removeClasses(classes)

    def loadClasses(self, *args):

        defDir = None
        path, _ = QFileDialog.getOpenFileName(self, 'Select Raster File', directory=defDir)
        if os.path.exists(path):

            try:
                scheme = ClassificationScheme.fromRasterImage(path)
                if scheme is not None:
                    self.appendClassificationScheme(scheme)
            except Exception as ex:
                QMessageBox.critical(self, "Unable to load class info", str(ex))


    def appendClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.mScheme.insertClasses([c for c in classificationScheme])

    def setClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.mScheme.clear()
        self.appendClassificationScheme(classificationScheme)

    def classificationScheme(self):
        return self.mScheme


class ClassificationSchemeDialog(QgsDialog):
    @staticmethod
    def getClassificationScheme(*args, **kwds):
        """
        Opens a dialog to edit a ClassificationScheme
        :param args:
        :param kwds:
        :return: None | ClassificationScheme
        """
        d = ClassificationSchemeDialog(*args, **kwds)
        d.exec_()

        if d.result() == QDialog.Accepted:
            return d.classificationScheme()
        else:
            return None

    def __init__(self, parent=None, classificationScheme=None, title='Specify Classification Scheme'):
        super(ClassificationSchemeDialog, self).__init__(parent=parent, \
                                                         buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = ClassificationSchemeWidget(parent=self, classificationScheme=classificationScheme)
        self.setWindowTitle(title)
        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cancel')
        buttonBar = QHBoxLayout()
        # buttonBar.addWidget(self.btCancel)
        # buttonBar.addWidget(self.btOk)
        l = self.layout()
        l.addWidget(self.w)
        l.addLayout(buttonBar)
        # self.setLayout(l)

        if isinstance(classificationScheme, ClassificationScheme):
            self.setClassificationScheme(classificationScheme)
        s = ""

    def classificationScheme(self):
        return self.w.classificationScheme()

    def setClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.w.setClassificationScheme(classificationScheme)


class ClassificationSchemeEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget):
        super(ClassificationSchemeEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)

        self.mComboBox = None
        self.mDefaultValue = None

    def createWidget(self, parent: QWidget):
        #log('createWidget')
        w = ClassificationSchemeComboBox(parent)
        w.model().setAllowEmptyField(True)
        w.setVisible(True)
        return w

    def initWidget(self, editor:QWidget):
        #log(' initWidget')
        conf = self.config()

        if isinstance(editor, ClassificationSchemeComboBox):
            self.mComboBox = editor
            self.mComboBox.setClassificationScheme(classSchemeFromConfig(conf))
            self.mComboBox.currentIndexChanged.connect(self.onValueChanged)

        else:
            s = ""

    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs)->bool:
        return isinstance(self.mComboBox, ClassificationSchemeComboBox)

    def value(self, *args, **kwargs):

        value = None
        if isinstance(self.mComboBox, ClassificationSchemeComboBox):
            classInfo = self.mComboBox.currentClassInfo()
            if isinstance(classInfo, ClassInfo):

                typeCode = self.field().type()
                if typeCode == QVariant.String:
                    value =  classInfo.name()
                elif typeCode in [QVariant.Int, QVariant.Double]:
                    value = classInfo.label()
                else:
                    s = ""

        return value


    def setEnabled(self, enabled:bool):

        if isinstance(self.mComboBox, ClassificationSchemeComboBox):
            self.mComboBox.setEnabled(enabled)


    def setValue(self, value):

        if isinstance(self.mComboBox, ClassificationSchemeComboBox):
            i = self.mComboBox.classIndexFromValue(value)
            self.mComboBox.setCurrentIndex(i)


class ClassificationSchemeEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, parent:QWidget):

        super(ClassificationSchemeEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        #self.setupUi(self)
        self.mSchemeWidget = ClassificationSchemeWidget(parent=self)
        self.mSchemeWidget.sigValuesChanged.connect(self.changed)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.mSchemeWidget)
        self.mLastConfig = {}


    def config(self, *args, **kwargs)->dict:
        return classSchemeToConfig(self.mSchemeWidget.classificationScheme())

    def setConfig(self, config:dict):
        self.mLastConfig = config
        cs = classSchemeFromConfig(config)
        cs.setName(self.layer().fields()[self.field()].name())
        self.mSchemeWidget.setClassificationScheme(cs)

    def resetClassificationScheme(self):
        self.setConfig(self.mLastConfig)

def classSchemeToConfig(classScheme:ClassificationScheme)->dict:
    """Converts a ClassificationScheme into a dictionary that can be used in an QgsEditorWidgetSetup"""
    config = {'classes': classScheme.json()}
    return config

def classSchemeFromConfig(conf:dict)->ClassificationScheme:
    """
    Converts a configuration dictionary into a ClassificationScheme.
    :param conf: dict
    :return: ClassificationScheme
    """
    cs = None
    if 'classes' in conf.keys():
        cs = ClassificationScheme.fromJson(conf['classes'])
    if not isinstance(cs, ClassificationScheme):
        return ClassificationScheme()
    else:
        return cs


class ClassificationSchemeWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name:str):

        super(ClassificationSchemeWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer:QgsVectorLayer, fieldIdx:int, parent=QWidget)->ClassificationSchemeEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = ClassificationSchemeEditorConfigWidget(layer, fieldIdx, parent)

        key = self.configKey(layer, fieldIdx)

        initialConfig = layer.editorWidgetSetup(fieldIdx).config()
        self.writeConfig(key, initialConfig)
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

    def create(self, layer:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget)->ClassificationSchemeEditorWidgetWrapper:
        """
        Create a ClassificationSchemeEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: ClassificationSchemeEditorWidgetWrapper
        """
        w = ClassificationSchemeEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        return w

    def writeConfig(self, key:tuple, config:dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config

    def readConfig(self, key:tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        if key in self.mConfigurations.keys():
            conf = self.mConfigurations[key]
        else:
            # return the very default "empty" configuration
            conf = {}
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
        if fieldIdx < 0:
            return 0
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if re.search('(int|float|double|text|string)', field.typeName(), re.I):
            if re.search('class', field.name(), re.I):
                return 5 # should we return 10 for showing specialized support?
            else:
                return 5
        else:
            return 0 # no support

    def supportsField(self, vl:QgsVectorLayer, idx:int):
        field = vl.fields().at(idx)
        if isinstance(field, QgsField) and re.search('(int|float|double|text|string)', field.typeName(), re.I):
            return True
        return False


EDITOR_WIDGET_REGISTRY_KEY = 'Raster Classification'

def registerClassificationSchemeEditorWidget():
    reg = QgsGui.editorWidgetRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        global CLASS_SCHEME_EDITOR_WIDGET_FACTORY
        factory = ClassificationSchemeWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, factory)
        CLASS_SCHEME_EDITOR_WIDGET_FACTORY = factory
