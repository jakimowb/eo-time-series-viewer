

import os

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer import *
from timeseriesviewer.utils import *

from timeseriesviewer.ui.widgets import loadUIFormClass

load = lambda p : loadUIFormClass(jp(DIR_UI,p))

class ClassInfo(QObject):

    def __init__(self, name=None, color=None):
        self.mName = ''
        self.mColor = QColor('black')
        if name:
            self.setName(name)
        if color:
            self.setColor(color)

    def setColor(self, color):
        assert isinstance(color, QColor)
        self.mColor = color

    def setName(self, name):
        assert isinstance(name, str)
        self.mName = name

    def clone(self):
        return ClassInfo(name=self.mName, color=self.mColor)

class ClassificationScheme(QObject):
    @staticmethod
    def fromRasterImage(path, bandIndex=None):
        ds = gdal.Open(path)
        assert ds is not None
        if bandIndex is None:
            for b in range(ds.RasterCount):
                band = ds.GetRasterBand(b + 1)
                cat = band.GetCategoryNames()

                if cat != None:
                    bandIndex = b
                    break
                s = ""


        assert bandIndex >= 0 and bandIndex < ds.RasterCount
        band = ds.GetRasterBand(bandIndex + 1)
        cat = band.GetCategoryNames()
        ct = band.GetColorTable()
        if len(cat) == 0:
            return None
        scheme = ClassificationScheme()
        for i, catName in enumerate(cat):
            cli = ClassInfo(name=catName)
            if ct is not None:
                cli.setColor(QColor(*ct.GetColorEntry(i)))
            scheme.addClass(cli)
        return scheme

    @staticmethod
    def fromVectorFile(self, path, fieldClassName='classname', fieldClassColor='classColor'):
        pass

    def clear(self):
        del self.classes[:]

    def __init__(self):
        super(ClassificationScheme, self).__init__()

        self.classes = []

    def __len__(self):
        return len(self.classes)

    def __iter__(self):
        return  self.classes.__iter__()

    def removeClass(self, c):
        assert c in self.classes

    def addClass(self, c, index=None):
        assert isinstance(c, ClassInfo)
        if index is None:
            index = len(self.classes)
        self.classes.insert(index, c)


class ClassificationSchemeTableModel(QAbstractTableModel):
    columnNames = ['label', 'name', 'color']

    def __init__(self, parent=None):
        super(ClassificationSchemeTableModel, self).__init__(parent)

        self.scheme = ClassificationScheme()

    def loadClassesFromImage(self, path, append=True):

        if not append:
            for c in self.classes:
                self.removeClass(c)

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.scheme)

    def columnCount(self, parent = QModelIndex()):
        return len(self.columNames)

    def getIndexFromClassInfo(self, classInfo):
        return self.createIndex(self.scheme.index(classInfo),0)

    def getClassInfoFromIndex(self, index):
        if index.isValid():
            return self.scheme[index.row()]
        return None



    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        columnName = self.columnames[index.column()]

        classInfo = self.getClassInfoFromIndex(index)
        assert isinstance(classInfo, ClassInfo)

        value = None
        if role == Qt.DisplayRole:
            if columnName == 'id':
                value = index.row()
            if columnName == 'name':
                value = classInfo.mName
            elif columnName == 'color':
                value = str(classInfo.mColor)
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        columnName = self.columnames[index.column()]

        classInfo = self.getClassInfoFromIndex(index)
        assert isinstance(classInfo, ClassInfo)

        if role == Qt.EditRole and columnName == 'name':
            if len(value) == 0:  # do not accept empty strings
                return False
            classInfo.setName(str(value))
            return True

        return False

    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in ['name']:  # allow check state
                flags = flags | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

class ClassificationSchemeWidget(QWidget, load('classificationscheme.ui')):

    def __init__(self, parent=None, classificationScheme=None):
        super(ClassificationSchemeWidget, self).__init__(parent)
        self.setupUi(self)

        self.mScheme = ClassificationScheme()
        if classificationScheme is not None:
            self.setClassificationScheme(classificationScheme)
        self.tableViewModel = ClassificationSchemeTableModel(self)
        self.tableClassificationScheme.setModel(self.tableViewModel)

        self.btnLoadClasses.clicked.connect(self.loadClasses)
        self.btnRemoveClasses.clicked.connect(self.removeSelectedClasses)
        self.btnAddClasses.clicked.connect(self.addClasses)

    def addClasses(self, n):
        for i in range(n):
            c = ClassInfo(name = '<empty>', color = QColor('red'))
            self.mScheme.addClass(c)


    def loadClasses(self, *args):
        path = QFileDialog.getOpenFileName(self, 'Select Raster File', '')
        if os.path.exists(path):
            scheme = ClassificationScheme.fromRasterImage(path)
            if scheme is not None:
                self.appendClassificationScheme(scheme)


    def appendClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        for c in classificationScheme:
            self.mScheme.addClass(c)


    def setClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.mScheme.classes[:]
        self.appendClassificationScheme(classificationScheme)


class ClassificationSchemeDialog(QgsDialog):

    @staticmethod
    def getClassificationScheme(*args, **kwds):
        """
        Opens a CrosshairDialog.
        :param args:
        :param kwds:
        :return: specified CrosshairStyle if accepted, else None
        """
        d = ClassificationSchemeDialog(*args, **kwds)
        d.exec_()

        if d.result() == QDialog.Accepted:
            return d.classificationSheme()
        else:
            return None

    def __init__(self, parent=None, classificationScheme=None, title='Specify Classification Scheme'):
        super(ClassificationSchemeDialog, self).__init__(parent=parent , \
            buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = ClassificationSchemeWidget(parent=self, classificationScheme=classificationScheme)
        self.setWindowTitle(title)
        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cancel')
        buttonBar = QHBoxLayout()
        #buttonBar.addWidget(self.btCancel)
        #buttonBar.addWidget(self.btOk)
        l = self.layout()
        l.addWidget(self.w)
        l.addLayout(buttonBar)
        #self.setLayout(l)

        if isinstance(classificationScheme, ClassificationScheme):
            self.setClassificationSheme(classificationScheme)
        s = ""

    def classificationScheme(self):
        return self.w.crosshairStyle()

    def setClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.w.setClassificationScheme(classificationScheme)


if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    pathClassImg = r'D:\Repositories\QGIS_Plugins\enmap-box\enmapbox\testdata\HymapBerlinA\HymapBerlinA_test.img'
    pathShp = r''

    w = ClassificationSchemeWidget()
    w.setClassificationScheme(ClassificationScheme.fromRasterImage(pathClassImg))
    w.show()

    qgsApp.exec_()
    qgsApp.exitQgis()
