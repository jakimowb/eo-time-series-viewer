
import sys, os, re, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal

from timeseriesviewer.utils import loadUI, qgisInstance
from timeseriesviewer.classification.classificationscheme \
    import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, ClassificationSchemeComboBox

from timeseriesviewer.timeseries import TimeSeriesDatum

#the QgsProject(s) and QgsMapLayerStore(s) to search for QgsVectorLayers
MAP_LAYER_STORES = [QgsProject.instance()]

CONFKEY_CLASSIFICATIONSCHEME = 'classificationScheme'
CONFKEY_LABELTYPE = 'labelKey'

class LabelShortcutType(enum.Enum):
    """Enumeration for shortcuts to be derived from a TimeSeriesDatum instance"""
    Off = 'No label shortcut'
    Date = 'Date-Time'
    DOY = 'Day of Year (DOY)'
    Year = 'Year'
    DecimalYear = 'Decimal year'
    Sensor = 'Sensor name'
    Classification = 'Classification Label'

def shortcuts(field:QgsField):
    """
    Returns the possible LabelShortCutTypes for a certain field
    :param fieldName: str
    :return: [list]
    """
    assert isinstance(field, QgsField)

    shortCutsString = [LabelShortcutType.Sensor, LabelShortcutType.Date, LabelShortcutType.Classification]
    shortCutsInt = [LabelShortcutType.Year, LabelShortcutType.DOY, LabelShortcutType.Classification]
    shortCutsFloat = [LabelShortcutType.Year, LabelShortcutType.DOY, LabelShortcutType.DecimalYear, LabelShortcutType.Classification]

    options = [LabelShortcutType.Off]
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


def layerClassSchemes(layer:QgsVectorLayer)->list:
    assert isinstance(layer, QgsVectorLayer)
    schemes = []
    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            results.append(layer)
            break
    return schemes

def labelShortcutLayerClassificationSchemes(layer:QgsVectorLayer):
    """
    Returns the ClassificationSchemes used for labeling shortcuts
    :param layer: QgsVectorLayer
    :return: [list-of-classificationSchemes]
    """
    classSchemes = []
    assert isinstance(layer, QgsVectorLayer)
    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            conf = setup.config()
            ci = conf.get(CONFKEY_CLASSIFICATIONSCHEME)
            if isinstance(ci, ClassificationScheme) and ci not in classSchemes:
                classSchemes.add(ci)

    return classSchemes

def labelShortcutLayers()->list:
    """
    Returns a list of all known QgsVectorLayer which define at least one LabelShortcutEditWidget
    :return: [list-of-QgsVectorLayer]
    """
    layers = []
    classSchemes = set()
    for store in MAP_LAYER_STORES:
        assert isinstance(store, (QgsProject, QgsMapLayerStore))
        for layer in store.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                for i in range(layer.fields().count()):
                    setup = layer.editorWidgetSetup(i)
                    assert isinstance(setup, QgsEditorWidgetSetup)
                    if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                        if layer not in layers:
                            layers.append(layer)
                        break
    return layers

def applyShortcutsToRegisteredLayers(tsd:TimeSeriesDatum, classInfos:list):
    """

    :param tsd:
    :param classInfos:
    :return:
    """


    for layer in labelShortcutLayers():
        assert isinstance(layer, QgsVectorLayer)
        applyShortcuts(layer, tsd, classInfos)


def applyShortcuts(vectorLayer:QgsVectorLayer, tsd:TimeSeriesDatum, classInfos:list=None):
    """
    Labels selected features with information related to TimeSeriesDatum tsd, according to
    the settings specified in this model.
    :param tsd: TimeSeriesDatum
    :param classInfos:
    """
    assert isinstance(tsd, TimeSeriesDatum)
    assert isinstance(classInfos, list)
    assert isinstance(vectorLayer, QgsVectorLayer)

    assert vectorLayer.isEditable()

    for i in range(vectorLayer.fields().count()):
        setup = vectorLayer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            field = vectorLayer.fields().at(i)
            assert isinstance(field, QgsField)

            conf = setup.config()
            labelType = conf.get(CONFKEY_LABELTYPE)
            if isinstance(labelType, LabelShortcutType):
                value = None
                if labelType == LabelShortcutType.Sensor:
                    value = tsd.sensor().name()
                elif labelType == LabelShortcutType.DOY:
                    value = tsd.doy()
                elif labelType == LabelShortcutType.Date:
                    value = str(tsd.date())
                elif labelType == LabelShortcutType.DecimalYear:
                    value = tsd.decimalYear()
                elif labelType == LabelShortcutType.Classification:
                    classScheme = conf.get(CONFKEY_CLASSIFICATIONSCHEME)
                    if isinstance(classScheme, ClassificationScheme):
                        for classInfo in classInfos:
                            assert isinstance(classInfo, ClassInfo)
                            if classInfo in classScheme:
                                if field.type() == QVariant.String:
                                    value = classInfo.name()
                                else:
                                    value = classInfo.label()
                                break

                if value == None:
                    continue

                if field.type() == QVariant.String:
                    value = str(value)

                for feature in vectorLayer.selectedFeatures():
                    assert isinstance(feature, QgsFeature)
                    oldValue = feature.attribute(field.name())
                    vectorLayer.changeAttributeValue(feature.id(), i, value, oldValue)


    pass




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
            names = [n for n in names if n in self.mLabelTypes.keys() and self.mLabelTypes[n] != LabelShortcutType.Off]

            for feature in self.mVectorLayer.selectedFeatures():
                fid = feature.id()
                for name in names:
                    idx = fields.indexOf(name)
                    field = fields.at(idx)
                    assert isinstance(field, QgsField)
                    labelType = self.mLabelTypes[name]
                    value = None
                    if isinstance(labelType, LabelShortcutType):
                        if labelType == LabelShortcutType.Sensor:
                            value = tsd.sensor().name()
                        elif labelType == LabelShortcutType.DOY:
                            value = tsd.doy()
                        elif labelType == LabelShortcutType.Date:
                            value = str(tsd.date())
                        elif labelType == LabelShortcutType.DecimalYear:
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
                self.mLabelTypes[field.name()] = LabelShortcutType.Off

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


    def setFieldShortCut(self, fieldName:str, attributeType:LabelShortcutType):
        if isinstance(fieldName, QgsField):
            fieldName = fieldName.name()
        assert isinstance(fieldName, str)
        assert isinstance(attributeType, LabelShortcutType)

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
        return shortcuts(field)


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
                if isinstance(labelType, LabelShortcutType):
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
            if isinstance(value, LabelShortcutType) and value != oldTabelType:
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
                    assert isinstance(shortcutType, LabelShortcutType)
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
                assert isinstance(labelType, LabelShortcutType)
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

    def setFieldShortCut(self, fieldName:str, labelShortCut:LabelShortcutType):
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




class LabelShortcutEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, parent:QWidget):

        super(LabelShortcutEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        #self.setupUi(self)

        self.setLayout(QVBoxLayout())

        self.mCBShortCutType = QComboBox(self)
        self.mClassWidget = ClassificationSchemeWidget(parent=self)

        assert isinstance(vl, QgsVectorLayer)
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        self.mAllowedShortCuts = shortcuts(field)
        for i, option in enumerate(self.mAllowedShortCuts):
            self.mCBShortCutType.addItem(option.value, option)

        self.mCBShortCutType.currentIndexChanged.connect(self.onIndexChanged)

        self.layout().addWidget(self.mCBShortCutType)
        self.layout().addWidget(self.mClassWidget)

        self.mLastConfig = {}

        self.onIndexChanged()

    def config(self, *args, **kwargs)->dict:

        conf = dict()
        conf[CONFKEY_LABELTYPE] = self.mCBShortCutType.currentData()
        cs = self.mClassWidget.classificationScheme()
        assert isinstance(cs, ClassificationScheme)
        #todo: json for serialization
        conf[CONFKEY_CLASSIFICATIONSCHEME] = cs

        return conf

    def setConfig(self, config:dict):
        self.mLastConfig = config
        labelType = config.get(CONFKEY_LABELTYPE)
        if not isinstance(labelType, LabelShortcutType):
            labelType = LabelShortcutType.Off

        if labelType not in self.mAllowedShortCuts:
            labelType = self.mAllowedShortCuts[0]

        i = self.mCBShortCutType.findData(labelType)
        self.mCBShortCutType.setCurrentIndex(i)


        classScheme = config.get(CONFKEY_CLASSIFICATIONSCHEME)
        if isinstance(classScheme, ClassificationScheme):
            self.mClassWidget.setClassificationScheme(classScheme)


    def onIndexChanged(self, *args):
        ltype = self.shortcutType()
        if ltype == LabelShortcutType.Classification:
            self.mClassWidget.setEnabled(True)
        else:
            self.mClassWidget.setEnabled(False)

    def classificationScheme(self)->ClassificationScheme:
        return self.mClassWidget.classificationScheme()

    def setClassificationScheme(self, classScheme:ClassificationScheme):
        assert isinstance(classScheme, ClassificationScheme)
        self.mClassWidget.setClassificationScheme(classScheme)

    def shortcutType(self)->LabelShortcutType:
        return self.mCBShortCutType.currentData(Qt.UserRole)



class LabelShortcutEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget):
        super(LabelShortcutEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)

        self.mEditor = None
        self.mValidator = None

    def configLabelType(self)->LabelShortcutType:
        return self.config(CONFKEY_LABELTYPE)

    def configClassificationScheme(self)->ClassificationScheme:
        return self.config(CONFKEY_CLASSIFICATIONSCHEME)

    def createWidget(self, parent: QWidget):
        #log('createWidget')
        labelType = self.configLabelType()
        if labelType == LabelShortcutType.Classification:
            self.mEditor = ClassificationSchemeComboBox(parent)
        else:
            self.mEditor = QLineEdit(parent)
            self.mValidator = QRegExpValidator()
        return self.mEditor


    def initWidget(self, editor:QWidget):
        #log(' initWidget')

        if isinstance(editor, ClassificationSchemeComboBox):
            cs = self.configClassificationScheme()
            if isinstance(cs, ClassificationScheme):
                self.mEditor.setClassificationScheme(cs)
                self.mEditor.currentIndexChanged.connect(self.onValueChanged)

        if isinstance(editor, QLineEdit):
            self.mEditor = editor
            self.mEditor.textChanged.connect(self.onValueChanged)

    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs)->bool:
        return isinstance(self.mEditor, (ClassificationSchemeComboBox, QLineEdit))

    def value(self, *args, **kwargs):
        typeCode = self.field().type()
        if isinstance(self.mEditor, ClassificationSchemeComboBox):
            classInfo = self.mEditor.currentClassInfo()
            if isinstance(classInfo, ClassInfo):
                if typeCode == QVariant.String:
                    return classInfo.name()
                if typeCode in [QVariant.Int, QVariant.Double]:
                    return classInfo.label()
        elif isinstance(self.mEditor, QLineEdit):
            txt = self.mEditor.text()
            if len(txt) == '':
                return self.defaultValue()
            if typeCode == QVariant.String:
                return txt

            try:
                txt = txt.strip()
                if typeCode == QVariant.Int:
                    return int(txt)
                if typeCode == QVariant.Double:
                    return float(txt)
            except Exception as e:
                return self.defaultValue()

            return self.mLineEdit.text()

        return None


    def setEnabled(self, enabled:bool):

        if isinstance(self.mEditor, QWidget):
            self.mEditor.setEnabled(enabled)


    def setValue(self, value):

        if isinstance(self.mEditor, ClassificationSchemeComboBox):
            cs = self.mEditor.classificationScheme()
            if isinstance(cs, ClassificationScheme) and len(cs) > 0:
                i = cs.classIndexFromValue(value)
                self.mEditor.setCurrentIndex(max(i, 0))
        elif isinstance(self.mEditor, QLineEdit):
            self.mEditor.setText(str(value))


class LabelShortcutWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name:str):

        super(LabelShortcutWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer:QgsVectorLayer, fieldIdx:int, parent=QWidget)->LabelShortcutEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = LabelShortcutEditorConfigWidget(layer, fieldIdx, parent)
        key = self.configKey(layer, fieldIdx)
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

    def create(self, layer:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget)->LabelShortcutEditorWidgetWrapper:
        """
        Create a ClassificationSchemeEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: ClassificationSchemeEditorWidgetWrapper
        """
        w = LabelShortcutEditorWidgetWrapper(layer, fieldIdx, editor, parent)
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
            #return the very default configuration
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
        if field.type() in [QVariant.String, QVariant.Int] and re.search(r'.*(class|label).*', field.name(), re.I):
            return 20
        else:
            return 0 #no support

    def supportsField(self, vl:QgsVectorLayer, idx:int):
        field = vl.fields().at(idx)
        if isinstance(field, QgsField) and field.type() in [QVariant.Int, QVariant.String]:
            return True
        return False




EDITOR_WIDGET_REGISTRY_KEY = 'EOTSV_Labeling'
labelEditorWidgetFactory = None
def registerLabelShortcutEditorWidget():
    reg = QgsGui.editorWidgetRegistry()
    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        factory = LabelShortcutWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, factory)
    else:
        labelEditorWidgetFactory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
