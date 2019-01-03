
import sys, os, re, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal

from timeseriesviewer.utils import loadUI
from timeseriesviewer.classificationscheme import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, getTextColorWithContrast
from timeseriesviewer.timeseries import TimeSeriesDatum


class LabelAttributeType(enum.Enum):
    NoLabeling = 0
    Date = 1
    DOY = 2
    ClassLabel = 4


class LabelAttributeTableModel(QAbstractTableModel):

    def __init__(self, parent=None, *args):

        super(LabelAttributeTableModel, self).__init__()

        self.cnField = 'Field'
        self.cnFieldType = 'Type'
        self.cnLabel = 'Label'
        self.mColumnNames = [self.cnField, self.cnFieldType, self.cnLabel]
        self.mLabelTypes = dict()
        self.mVectorLayer = None

    def setVectorLayer(self, layer:QgsVectorLayer):

        if isinstance(layer, QgsVectorLayer):
            layer.attributeAdded.connect(self.resetModel)
            layer.attributeDeleted.connect(self.resetModel)
            self.mVectorLayer = layer
        else:
            self.mVectorLayer = None
        self.resetModel()


    def hasVectorLayer(self)->bool:
        return isinstance(self.mVectorLayer, QgsVectorLayer)

    def resetModel(self):
        self.beginResetModel()
        self.mLabelTypes.clear()
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            for i in range(fields.count()):
                field = fields.at(i)
                assert isinstance(field, QgsField)
                self.mLabelTypes[field.name()] = LabelAttributeType.NoLabeling

        self.endResetModel()

    def rowCount(self, parent = QModelIndex())->int:
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.fields().count()
        else:
            return 0

    def field2index(self, field:QgsField)->QModelIndex:
        assert isinstance(field, QgsField)

        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            i = fields.indexOf(field)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()

    def index2field(self, index:QModelIndex)->QgsField:
        if index.isValid() and isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            return fields.at(index.row())
        else:
            return None

    def columnCount(self, parent = QModelIndex())->int:
        return len(self.mColumnNames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumnNames[index.column()]
        field = self.index2field(index)
        assert isinstance(field, QgsField)
        labelType = self.mLabelTypes.get(field.name())

        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if columnName == self.cnField:
                value = field.name()
            elif columnName == self.cnFieldType:
                value = '{}'.format(field.typeName())
            elif columnName == self.cnLabel:
                value = labelType
            else:
                s = ""
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        columnName = self.mColumnNames[index.column()]
        field = self.index2field(index)
        assert isinstance(field, QgsField)
        oldTabelType = self.mLabelTypes.get(field.name())
        changed = False
        if columnName == self.cnLabel and role == Qt.EditRole:
            if isinstance(value, LabelAttributeType) and value != oldTabelType:
                self.mLabelTypes[field.name()] = value
                changed = True
        if changed:
            self.dataChanged(index, index, roles=[role])
        return changed

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None




class LabelingDock(QgsDockWidget, loadUI('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDock, self).__init__(parent)
        self.setupUi(self)
        assert isinstance(self.mVectorLayerComboBox, QgsMapLayerComboBox)


        self.mLabelAttributeModel = LabelAttributeTableModel()
        self.tableView.setModel(self.mLabelAttributeModel)

        self.mVectorLayerComboBox.setAllowEmptyLayer(True)
        allowed = ['DB2', 'WFS', 'arcgisfeatureserver', 'delimitedtext', 'memory', 'mssql', 'ogr', 'oracle', 'ows',
                   'postgres', 'spatialite', 'virtual']
        excluded = [k for k in QgsProviderRegistry.instance().providerList() if k not in allowed]
        self.mVectorLayerComboBox.setExcludedProviders(excluded)
        self.mVectorLayerComboBox.currentIndexChanged.connect(
            lambda : self.mLabelAttributeModel.setVectorLayer(self.currentVectorSource()))


    def currentVectorSource(self)->QgsVectorLayer:
        return self.mVectorLayerComboBox.currentLayer()


    def updateTemporalLabels(self, tsd):
        pass

    def updateClassLabels(self, classScheme, classInfo):
        pass

