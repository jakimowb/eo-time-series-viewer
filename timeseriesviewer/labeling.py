
import sys, os, re, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal

from timeseriesviewer.utils import loadUI, qgisInstance
from timeseriesviewer.classificationscheme import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, getTextColorWithContrast
from timeseriesviewer.timeseries import TimeSeriesDatum


class LabelShortCutType(enum.Enum):
    """Enumeration for shortcuts to be derived from a TimeSeriesDatum instance"""
    Off = 'No label shortcut'
    Date = 'Date-Time'
    DOY = 'Day of Year (DOY)'
    Year = 'Year'
    DecimalYear = 'Decimal year'
    Sensor = 'Sensor name'



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


    def contextMenuTSD(self, tsd:TimeSeriesDatum, parentMenu:QMenu)->QMenu:
        """
        Create a QMenu to label selected QgsFeatures via shortcuts.
        :param tsd: TimeSeriesDatum
        :param parentMenu: parent QMenu to add
        :return: QMenu parent
        """

        if self.hasVectorLayer():
            n = len(self.mVectorLayer.selectedFeatureIds())
            m = parentMenu.addMenu('Label shortcuts "{}"'.format(self.mVectorLayer.name()))
            m.setToolTip('Label {} selected feature(s) in {}'.format(n, self.mVectorLayer.name()))

            sm = m.addAction('Shortcuts {}'.format(str(tsd.date())))
            sm.triggered.connect(lambda : self.applyOnSelectedFeatures(tsd))
            sm.setEnabled(n > 0)
        else:
            a = parentMenu.addAction('Label shortcuts undefined')
            a.setToolTip('Use the labeling panel and specify a vector layer to selected features.')
            a.setEnabled(False)

        return parentMenu

    def applyOnSelectedFeatures(self, tsd:TimeSeriesDatum, classInfos:list=None):
        """
        Labels selected features with information related to TimeSeriesDatum tsd, according to
        the settings specified in this model.
        :param tsd: TimeSeriesDatum
        :param classInfos:
        """

        assert isinstance(tsd, TimeSeriesDatum)
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            names = fields.names()
            names = [n for n in names if n in self.mLabelTypes.keys()  and self.mLabelTypes[n] != LabelShortCutType.Off]

            for feature in self.mVectorLayer.selectedFeatures():
                fid = feature.id()
                for name in names:
                    idx = fields.indexOf(name)
                    field = fields.at(idx)
                    assert isinstance(field, QgsField)
                    labelType = self.mLabelTypes[name]
                    value = None
                    if isinstance(labelType, LabelShortCutType):
                        if labelType == LabelShortCutType.Sensor:
                            value = tsd.sensor().name()
                        elif labelType == LabelShortCutType.DOY:
                            value = tsd.doy()
                        elif labelType == LabelShortCutType.Date:
                            value = str(tsd.date())
                        elif labelType == LabelShortCutType.DecimalYear:
                            value = tsd.decimalYear()
                    else:
                        pass
                        #todo: support class infos

                    if value == None:
                        continue

                    if field.typeName == 'String':
                        value = str(value)

                    oldValue = feature.attribute(name)
                    self.mVectorLayer.changeAttributeValue(fid, idx, value, oldValue)



        pass

    def hasVectorLayer(self)->bool:
        """
        Returns true if a QgsVectorLayer is specified.
        :return: bool
        """
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
                self.mLabelTypes[field.name()] = LabelShortCutType.Off

        self.endResetModel()

    def rowCount(self, parent = QModelIndex())->int:
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.fields().count()
        else:
            return 0


    def fieldName2Index(self, fieldName:str)->str:
        assert isinstance(fieldName, str)

        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            i = fields.indexOf(fieldName)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()


    def field2index(self, field:QgsField)->QModelIndex:

        assert isinstance(field, QgsField)
        return self.fieldName2Index(field.name())


    def index2field(self, index:QModelIndex)->QgsField:
        if index.isValid() and isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            return fields.at(index.row())
        else:
            return None

    def columnCount(self, parent = QModelIndex())->int:
        return len(self.mColumnNames)


    def setFieldShortCut(self, fieldName:str, attributeType:LabelShortCutType):
        if isinstance(fieldName, QgsField):
            fieldName = fieldName.name()
        assert isinstance(fieldName, str)
        assert isinstance(attributeType, LabelShortCutType)

        if self.hasVectorLayer():
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            i = self.mVectorLayer.fields().indexFromName(fieldName)
            assert i >= 0
            field = self.mVectorLayer.fields().at(i)
            idx = self.field2index(field)

            self.setData(self.createIndex(idx.row(), 2), attributeType, role=Qt.EditRole)

    def shortcuts(self, field:QgsField):
        """
        Returns the possible LabelShortCutTypes for a certain field
        :param fieldName: str
        :return: [list]
        """
        if not self.hasVectorLayer():
            return []

        if isinstance(field, QModelIndex):
            field = self.index2field(field)

        if isinstance(field, str):
            i = self.mVectorLayer.fields().lookupField(field)
            field = self.mVectorLayer.fields().at(i)

        assert isinstance(field, QgsField)

        shortCutsString = [LabelShortCutType.Sensor, LabelShortCutType.Date]
        shortCutsInt = [LabelShortCutType.Year, LabelShortCutType.DOY]
        shortCutsFloat = [LabelShortCutType.DecimalYear]

        options = [LabelShortCutType.Off]
        t = field.typeName().lower()
        if t == 'string':
            options.extend(shortCutsString)
            options.extend(shortCutsInt)
            options.extend(shortCutsFloat)
        elif t.startswith('integer'):
            options.extend(shortCutsInt)
        elif t.startswith('real'):
            options.extend(shortCutsInt)
            options.extend(shortCutsFloat)
        else:
            s = ""
        return options


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
                if isinstance(labelType, LabelShortCutType):
                    value = labelType.name
                else:
                    value = str(labelType)
            else:
                s = ""
        elif role == Qt.UserRole:
            value = labelType
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
            if isinstance(value, LabelShortCutType) and value != oldTabelType:
                self.mLabelTypes[field.name()] = value
                changed = True
        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed

    def columnName(self, index: int)->str:
        if isinstance(index, QModelIndex):
            if not index.isValid():
                return None
            index = index.column()
        return self.mColumnNames[index]

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if self.columnName(index) == self.cnLabel:
                flags = flags | Qt.ItemIsEditable
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


class LabelAttributeTypeWidgetDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, tableView: QTableView, labelAttributeTableModel: LabelAttributeTableModel, parent=None):
        super(LabelAttributeTypeWidgetDelegate, self).__init__(parent=parent)
        assert isinstance(tableView, QTableView)
        assert isinstance(labelAttributeTableModel, LabelAttributeTableModel)

        self.mTableView = tableView
        self.mLabelAttributeTableModel = labelAttributeTableModel
        self.setItemDelegates(tableView)

    def model(self)->LabelAttributeTableModel:
        return self.mTableView.model()

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)
        model = self.model()
        for c in [model.cnLabel]:
            i = model.mColumnNames.index(c)
            tableView.setItemDelegateForColumn(i, self)

    def columnName(self, index:QModelIndex)->str:
        if not index.isValid():
            return None
        return self.model().mColumnNames[index.column()]

    def createEditor(self, parent, option, index):
        cname = self.columnName(index)
        model = self.mTableView.model()
        w = None
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel:
                w = QComboBox(parent=parent)
                for i, shortcutType in enumerate(model.shortcuts(index)):
                    assert isinstance(shortcutType, LabelShortCutType)
                    w.addItem(shortcutType.name, shortcutType)
                    w.setItemData(i, shortcutType.value, Qt.ToolTipRole)
        return w


    def setEditorData(self, editor, index):
        cname = self.columnName(index)
        model = self.mTableView.model()

        w = None
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel and isinstance(editor, QComboBox):
                labelType = model.data(index, role=Qt.UserRole)
                assert isinstance(labelType, LabelShortCutType)
                for i in range(editor.count()):
                    d = editor.itemData(i)
                    if d == labelType:
                        editor.setCurrentIndex(i)
                        break

    def setModelData(self, w, model, index):

        model = self.mTableView.model()
        cname = model.columnName(index)
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel and isinstance(w, QComboBox):
                model.setData(index, w.currentData(), Qt.EditRole)


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
        self.mVectorLayerComboBox.currentIndexChanged.connect(self.onVectorLayerChanged)

        self.delegateTableView = LabelAttributeTypeWidgetDelegate(self.tableView, self.mLabelAttributeModel)
        self.delegateTableView.setItemDelegates(self.tableView)

        self.mDualView = None
        self.mCanvas = QgsMapCanvas(self)
        self.mCanvas.setVisible(False)



        self.initActions()
        self.onVectorLayerChanged()

    def setFieldShortCut(self, fieldName:str, labelShortCut:LabelShortCutType):
        self.mLabelAttributeModel.setFieldShortCut(fieldName, labelShortCut)

    def onVectorLayerChanged(self):
        lyr = self.currentVectorSource()
        self.mLabelAttributeModel.setVectorLayer(lyr)

        if isinstance(lyr, QgsVectorLayer):

            lyr.editingStarted.connect(lambda : self.actionToggleEditing.setChecked(True))
            lyr.editingStopped.connect(lambda: self.actionToggleEditing.setChecked(False))

            self.mDualView = QgsDualView(self.gbAttributeTable)
            assert isinstance(self.mDualView, QgsDualView)
            self.gbAttributeTable.layout().addWidget(self.mDualView)
            self.mCanvas.setLayers([lyr])
            self.mCanvas.setDestinationCrs(lyr.crs())
            self.mCanvas.setExtent(lyr.extent())
            self.mDualView.init(lyr, self.mCanvas)  # , context=self.mAttributeEditorContext)
            self.mDualView.setView(QgsDualView.AttributeTable)
            self.mDualView.setAttributeTableConfig(lyr.attributeTableConfig())
            self.btnBar.setEnabled(True)
        else:
            self.mCanvas.setLayers([])

            if isinstance(self.mDualView, QgsDualView):
                self.mDualView.setParent(None)
                self.mDualView.hide()



            self.btnBar.setEnabled(False)




    def initActions(self):

        iface = qgisInstance()

        if isinstance(iface, QgisInterface):
            self.actionAddFeature = iface.actionAddFeature()
            self.actionSaveEdits = iface.actionSaveEdits()
            self.actionCancelEdits = iface.actionCancelEdits()
            self.actionToggleEditing = iface.actionToggleEditing()
            self.actionAddOgrLayer = iface.actionAddOgrLayer()


        def onToggleEditing(b):

            lyr = self.currentVectorSource()
            if isinstance(lyr, QgsVectorLayer):
                if b:
                    lyr.startEditing()
                else:
                    lyr.commitChanges()

        def onCancelEdits(*args):
            lyr = self.currentVectorSource()
            if isinstance(lyr, QgsVectorLayer):
                lyr.rollBack()

        def onSaveEdits(*args):
            lyr = self.currentVectorSource()
            if isinstance(lyr, QgsVectorLayer):
                b = lyr.isEditable()
                lyr.commitChanges()

                if b:
                    lyr.startEditing()

        self.actionToggleEditing.toggled.connect(onToggleEditing)
        self.actionCancelEdits.triggered.connect(onCancelEdits)
        self.actionSaveEdits.triggered.connect(onSaveEdits)


        self.btnAddFeature.setDefaultAction(self.actionAddFeature)
        self.btnSaveEdits.setDefaultAction(self.actionSaveEdits)
        self.btnCancelEdits.setDefaultAction(self.actionCancelEdits)
        self.btnToggleEditing.setDefaultAction(self.actionToggleEditing)
        self.btnAddOgrLayer.setDefaultAction(self.actionAddOgrLayer)


    def currentVectorSource(self)->QgsVectorLayer:
        return self.mVectorLayerComboBox.currentLayer()


    def updateTemporalLabels(self, tsd):
        pass

    def updateClassLabels(self, classScheme, classInfo):
        pass

