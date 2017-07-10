# noinspection PyPep8Naming

import os
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np

from timeseriesviewer import *
from timeseriesviewer.utils import *

#from timeseriesviewer.ui.widgets import loadUIFormClass
#load = lambda p : loadUIFormClass(jp(DIR_UI,p))


# noinspection PyPep8Naming
def getTextColorWithContrast(c):
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')


class ClassInfo(QObject):
    sigSettingsChanged = pyqtSignal()
    def __init__(self, label=0, name='unclassified', color=None):
        super(ClassInfo, self).__init__()
        self.mName = name
        self.mLabel = label
        self.mColor = QColor('black')
        if color:
            self.setColor(color)

    def setLabel(self, label):
        assert isinstance(label, int)
        assert label >= 0
        self.mLabel = label
        self.sigSettingsChanged.emit()

    def setColor(self, color):
        assert isinstance(color, QColor)
        self.mColor = color
        self.sigSettingsChanged.emit()

    def setName(self, name):
        assert isinstance(name, str)
        self.mName = name
        self.sigSettingsChanged.emit()

    def clone(self):
        return ClassInfo(name=self.mName, color=self.mColor)

    def __str__(self):
        return '{} "{}"'.format(self.mLabel,self.mName)

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

    sigClassRemoved = pyqtSignal(ClassInfo)
    sigClassAdded = pyqtSignal(ClassInfo)

    def __init__(self):
        super(ClassificationScheme, self).__init__()

        self.classes = []

    def clear(self):
        removed = self.classes[:]
        del self.classes[:]


    def __getitem__(self, slice):
        return self.classes[slice]

    def __delitem__(self, slice):
        classes = self[slice]
        for c in classes:
            self.removeClass(c)

    def __contains__(self, item):
        return item in self.classes

    def __len__(self):
        return len(self.classes)

    def __iter__(self):
        return  self.classes.__iter__()

    def removeClass(self, c):
        assert c in self.classes
        self.classes.remove(c)
        self.sigClassRemoved.emit(c)

    def addClass(self, c, index=None):
        assert isinstance(c, ClassInfo)
        if index is None:
            index = len(self.classes)
        c.setLabel(index)
        self.classes.insert(index, c)
        self.sigClassAdded.emit(c)

    def saveToRaster(self, path, bandIndex=0):

        ds = gdal.Open(path)
        assert ds is not None
        assert ds.RasterCount < bandIndex
        band = ds.GetRasterBand(bandIndex+1)
        ct = gdal.ColorTable()
        cat = []
        for i, classInfo in enumerate(self.classes):
            c = classInfo.mColor
            cat.append(classInfo.mName)
            assert isinstance(c, QColor)
            rgba = (c.red(), c.green(), c.blue(), c.alpha())
            ct.SetColorEntry(i, *rgba)

        band.SetColorTable(ct)
        band.SetCategoryNames(cat)

        ds = None


    def toString(self, sep=';'):
        lines = [sep.join(['class_value', 'class_name', 'R', 'G', 'B', 'A'])]
        for classInfo in self.classes:
            c = classInfo.mColor
            info = [classInfo.mValue, classInfo.mName, c.red(), c.green(), c.blue(), c.alpha()]
            info = ['{}'.format(v) for v in info]

            lines.append(sep.join(info))
        return '\n'.join(lines)

    def saveToCsv(self, path, sep=';'):
        lines = self.toString(sep=sep)
        file = open(path, 'w')
        file.write(lines)
        file.close()




class ClassificationSchemeTableModel(QAbstractTableModel):


    def __init__(self, scheme, parent=None):
        self.cLABEL = 'Label'
        self.cNAME = 'Name'
        self.cCOLOR = 'Color'
        self.columnNames = [self.cLABEL, self.cNAME, self.cCOLOR]
        assert isinstance(scheme, ClassificationScheme)
        super(ClassificationSchemeTableModel, self).__init__(parent)

        self.valLabel = QIntValidator(0, 99999)

        self.scheme = scheme
        #self.scheme.sigClassRemoved.connect(lambda : self.reset())
        #self.scheme.sigClassAdded.connect(self.onClassAdded)

        #self.modelReset.emit()

        #idx = self.getIndexFromClassInfo(c)
        #self.beginInsertRows(idx.parent(), idx.row(), 1)
        #self.endInsertRows()

    def removeClass(self, c):
        idx = self.getIndexFromClassInfo(c)
        if idx:
            self.beginRemoveRows(idx.parent(), idx.row(), idx.row())
            self.scheme.removeClass(c)
            self.endRemoveRows()

    def insertClass(self, c, i=None):
        if i is None:
            i = len(self.scheme)
        self.beginInsertRows(QModelIndex(), i, i)
        self.scheme.addClass(c,i)
        self.endInsertRows()


    def clear(self):
        self.beginRemoveRows(QModelIndex(), 0, self.rowCount()-1)
        self.scheme.clear()
        self.endRemoveRows()

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.scheme)

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnNames)

    def getIndexFromClassInfo(self, classInfo):
        return self.createIndex(self.scheme.classes.index(classInfo),0)

    def getClassInfoFromIndex(self, index):
        if index.isValid():
            return self.scheme[index.row()]
        return None



    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        columnName = self.columnNames[index.column()]

        classInfo = self.getClassInfoFromIndex(index)
        assert isinstance(classInfo, ClassInfo)

        value = None
        if role == Qt.DisplayRole:
            if columnName == self.cLABEL:
                value = classInfo.mLabel
            elif columnName == self.cNAME:
                value = classInfo.mName
            elif columnName == self.cCOLOR:
                value = classInfo.mColor
            else:
                s = ""
        if role == Qt.BackgroundRole:
            if columnName == self.cCOLOR:
                return QBrush(classInfo.mColor)
        if role == Qt.ForegroundRole:
            if columnName == self.cCOLOR:
                return getTextColorWithContrast(classInfo.mColor)


        if role == Qt.UserRole:
            return classInfo
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        columnName = self.columnNames[index.column()]

        classInfo = self.getClassInfoFromIndex(index)
        assert isinstance(classInfo, ClassInfo)

        if role == Qt.EditRole:
            if columnName == self.cNAME and len(value) > 0:
                # do not accept empty strings
                classInfo.setName(str(value))
                return True
            if columnName == self.cCOLOR and isinstance(value, QColor):
                classInfo.setColor(value)
                return True
            if columnName == self.cLABEL and \
               self.valLabel.validate(value,0)[0] == QValidator.Acceptable:
                classInfo.setLabel(int(value))
                return True
        return False

    def flags(self, index):
        if index.isValid():
            columnName = self.columnNames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in [self.cLABEL, self.cNAME]:  # allow check state
                flags = flags | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None


class ClassificationWidgetDelegates(QStyledItemDelegate):

    def __init__(self, tableView, parent=None):
        assert isinstance(tableView, QTableView)
        super(ClassificationWidgetDelegates, self).__init__(parent=parent)
        self.tableView = tableView
        self.tableView.doubleClicked.connect(self.onDoubleClick)
        #self.tableView.model().rowsInserted.connect(self.onRowsInserted)

    def onDoubleClick(self, idx):
        model = self.tableView.model()
        classInfo = model.getClassInfoFromIndex(idx)
        if idx.column() == model.columnNames.index(model.cCOLOR):

            w1 = QColorDialog(classInfo.mColor, self.tableView)
            w1.exec_()
            if w1.result() == QDialog.Accepted:
                c = w1.getColor()
                model.setData(idx, c, role=Qt.EditRole)



    def getColumnName(self, index):
        assert index.isValid()
        assert isinstance(index.model(), ClassificationSchemeTableModel)
        return index.model().columnNames[index.column()]

    def createEditor(self, parent, option, index):
        cname = self.getColumnName(index)
        model = index.model()
        assert isinstance(model, ClassificationSchemeTableModel)
        w = None
        if False and cname == model.cCOLOR:
            classInfo = model.getClassInfoFromIndex(index)
            w = QgsColorButton(parent, 'Class {}'.format(classInfo.mName))
            w.setColor(QColor(index.data()))
            w.colorChanged.connect(lambda: self.commitData.emit(w))
        return w

    def setEditorData(self, editor, index):
        cname = self.getColumnName(index)
        model = index.model()
        assert isinstance(model, ClassificationSchemeTableModel)

        classInfo = model.getClassInfoFromIndex(index)
        assert isinstance(classInfo, ClassInfo)
        if False and cname == model.cCOLOR:
            lastColor = classInfo.mColor
            assert isinstance(editor, QgsColorButton)
            assert isinstance(lastColor, QColor)
            editor.setColor(QColor(lastColor))
            editor.setText('{},{},{}'.format(lastColor.red(), lastColor.green(), lastColor.blue()))

    def setModelData(self, w, model, index):
        cname = self.getColumnName(index)
        model = index.model()
        assert isinstance(model, ClassificationSchemeTableModel)

        if False and cname == model.cCOLOR:
            assert isinstance(w, QgsColorButton)
            if index.data() != w.color():
                model.setData(index, w.color(), Qt.EditRole)

class ClassificationSchemeWidget(QWidget, loadUi('classificationscheme.ui')):



    def __init__(self, parent=None, classificationScheme=None):
        super(ClassificationSchemeWidget, self).__init__(parent)
        self.setupUi(self)

        self.mScheme = ClassificationScheme()

        if classificationScheme is not None:
            self.setClassificationScheme(classificationScheme)
        self.schemeModel = ClassificationSchemeTableModel(self.mScheme, self)

        self.tableClassificationScheme.verticalHeader().setMovable(True)
        self.tableClassificationScheme.verticalHeader().setDragEnabled(True)
        self.tableClassificationScheme.verticalHeader().setDragDropMode(QAbstractItemView.InternalMove)
        self.tableClassificationScheme.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableClassificationScheme.setModel(self.schemeModel)
        self.tableClassificationScheme.doubleClicked.connect(self.onTableDoubleClick)
        self.selectionModel = QItemSelectionModel(self.schemeModel)
        self.selectionModel.selectionChanged.connect(self.onSelectionChanged)
        self.onSelectionChanged() #enable/disabel widgets depending on a selection
        self.tableClassificationScheme.setSelectionModel(self.selectionModel)

        #self.delegate = ClassificationWidgetDelegates(self.tableClassificationScheme)
        #self.tableClassificationScheme.setItemDelegateForColumn(2, self.delegate)


        self.btnLoadClasses.clicked.connect(self.loadClasses)
        self.btnRemoveClasses.clicked.connect(self.removeSelectedClasses)
        self.btnAddClasses.clicked.connect(lambda:self.createClasses(1))

    def onTableDoubleClick(self, idx):
        model = self.tableClassificationScheme.model()
        classInfo = model.getClassInfoFromIndex(idx)
        if idx.column() == model.columnNames.index(model.cCOLOR):

            c = QColorDialog.getColor(classInfo.mColor, self.tableClassificationScheme, \
                                      'Set class color')
            model.setData(idx, c, role=Qt.EditRole)
    def onSelectionChanged(self, *args):
        self.btnRemoveClasses.setEnabled(self.selectionModel is not None and
                                         len(self.selectionModel.selectedRows()) > 0)

    def createClasses(self, n):
        for i in range(n):
            c = ClassInfo(name = '<empty>', color = QColor('red'))
            self.schemeModel.insertClass(c)


    def removeSelectedClasses(self):
        model = self.tableClassificationScheme.model()
        indices = reversed(self.selectionModel.selectedRows())
        classes = [self.schemeModel.getClassInfoFromIndex(idx) for idx in indices]
        for c in classes:
            self.schemeModel.removeClass(c)


    def loadClasses(self, *args):
        path = QFileDialog.getOpenFileName(self, 'Select Raster File', '')
        if os.path.exists(path):
            scheme = ClassificationScheme.fromRasterImage(path)
            if scheme is not None:
                self.appendClassificationScheme(scheme)


    def appendClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        for c in classificationScheme:
            self.schemeModel.insertClass(c.clone())


    def setClassificationScheme(self, classificationScheme):
        assert isinstance(classificationScheme, ClassificationScheme)
        self.schemeModel.clear()
        self.appendClassificationScheme(classificationScheme)

    def classificationScheme(self):
        return self.mScheme


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
            return d.classificationScheme()
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
        return self.w.classificationScheme()

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
