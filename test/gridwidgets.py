
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from timeseriesviewer.utils import *


class MapViewGridLayout(QGridLayout):

    def __init__(self):
        pass

class GridWidgetModel(QAbstractTableModel):
    def __init__(self):

        super(GridWidgetModel, self).__init__()
    def columnNames(self)->list:
        """
        Returns the column names
        :return: [list-of-str]
        """
        return [self.mColLabel, self.mColName, self.mColColor]

    def rowCount(self, parent:QModelIndex=None):
        """
        Returns the number of row / ClassInfos
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






if __name__ == '__main__':

    app = initQgisApplication()

    view = QTableView()


    view.resize(QSize(300,200))
    view.show()

    app.exec_()