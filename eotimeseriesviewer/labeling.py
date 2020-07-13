import sys, os, re, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal

from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.externals.qps.layerproperties import *
from eotimeseriesviewer.utils import loadUi
from .externals.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.externals.qps.classification.classificationscheme \
    import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, ClassificationSchemeComboBox

from eotimeseriesviewer.timeseries import TimeSeriesDate, TimeSeriesSource

# the QgsProject(s) and QgsMapLayerStore(s) to search for QgsVectorLayers
MAP_LAYER_STORES = [QgsProject.instance()]

CONFKEY_CLASSIFICATIONSCHEME = 'classificationScheme'
CONFKEY_LABELTYPE = 'labelType'


class LabelShortcutType(enum.Enum):
    """Enumeration for shortcuts to be derived from a TimeSeriesDate instance"""
    Off = 'No Quick Label (default)'
    Date = 'Date-Time'
    DOY = 'Day of Year (DOY)'
    Year = 'Year'
    DecimalYear = 'Decimal Year'
    Sensor = 'Sensor Name'
    SourceImage = 'Source Image'
    # Classification = 'Classification'


def shortcuts(field: QgsField):
    """
    Returns the possible LabelShortCutTypes for a certain field
    :param fieldName: str
    :return: [list]
    """
    assert isinstance(field, QgsField)

    shortCutsString = [LabelShortcutType.Sensor, LabelShortcutType.Date, LabelShortcutType.SourceImage]
    shortCutsInt = [LabelShortcutType.Year, LabelShortcutType.DOY]
    shortCutsFloat = [LabelShortcutType.Year, LabelShortcutType.DOY, LabelShortcutType.DecimalYear]
    shortCutsDate = [LabelShortcutType.Year, LabelShortcutType.Date]

    options = [LabelShortcutType.Off]
    t = field.typeName().lower()
    if field.type() in [QVariant.String]:
        options.extend(shortCutsString)
        options.extend(shortCutsInt)
        options.extend(shortCutsFloat)
    elif field.type() in [QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong]:
        options.extend(shortCutsInt)
    elif field.type() in [QVariant.Double]:
        options.extend(shortCutsInt)
        options.extend(shortCutsFloat)
    elif field.type() in [QVariant.DateTime, QVariant.Date]:
        options.extend(shortCutsDate)
    else:
        s = ""
    result = []
    for o in options:
        if o not in result:
            result.append(o)
    return result


def layerClassSchemes(layer: QgsVectorLayer) -> list:
    """
    Returns a list of (ClassificationScheme, QgsField) for all QgsFields with QgsEditorWidget being QgsClassificationWidgetWrapper or RasterClassification.
    :param layer: QgsVectorLayer
    :return: list [(ClassificationScheme, QgsField), ...]
    """
    assert isinstance(layer, QgsVectorLayer)
    from .externals.qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
    from .externals.qps.classification.classificationscheme import classSchemeFromConfig
    schemes = []
    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        field = layer.fields().at(i)
        assert isinstance(field, QgsField)
        assert isinstance(setup, QgsEditorWidgetSetup)

        if setup.type() == CS_KEY:
            cs = classSchemeFromConfig(setup.config())
            if isinstance(cs, ClassificationScheme) and len(cs) > 0:
                schemes.append((cs, field))

        elif setup.type() == 'Classification' and isinstance(layer.renderer(), QgsCategorizedSymbolRenderer):
            renderer = layer.renderer()
            cs = ClassificationScheme()
            for l, cat in enumerate(renderer.categories()):
                assert isinstance(cat, QgsRendererCategory)
                symbol = cat.symbol()
                assert isinstance(symbol, QgsSymbol)
                cs.insertClass(ClassInfo(l, name=cat.value(), color=symbol.color()))
            if len(cs) > 0:
                schemes.append((cs, field))
    return schemes


def labelShortcutLayerClassificationSchemes(layer: QgsVectorLayer):
    """
    Returns the ClassificationSchemes + QgsField used for labeling shortcuts
    :param layer: QgsVectorLayer
    :return: [(ClassificationScheme, QgsField), (ClassificationScheme, QgsField), ...]
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
                classSchemes.append((ci, layer.fields().at(i)))

    return classSchemes


def quickLabelLayers() -> typing.List[QgsVectorLayer]:
    """
    Returns a list of known QgsVectorLayers with at least one LabelShortcutEditWidget
    :return: [list-of-QgsVectorLayer]
    """
    layers = []
    from .externals.qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as CS_KEY

    classSchemes = set()
    for store in MAP_LAYER_STORES:
        assert isinstance(store, (QgsProject, QgsMapLayerStore))
        for layer in store.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                for i in range(layer.fields().count()):
                    setup = layer.editorWidgetSetup(i)
                    assert isinstance(setup, QgsEditorWidgetSetup)
                    if setup.type() in [EDITOR_WIDGET_REGISTRY_KEY, CS_KEY, 'Classification']:
                        if layer not in layers:
                            layers.append(layer)
                        break
    return layers


def setQuickTSDLabelsForRegisteredLayers(tsd: TimeSeriesDate, tss: TimeSeriesSource):
    """
    :param tsd: TimeSeriesDate
    :param classInfos:
    """
    for layer in quickLabelLayers():
        assert isinstance(layer, QgsVectorLayer)
        if layer.isEditable():
            setQuickTSDLabels(layer, tsd, tss)


def setQuickClassInfo(vectorLayer: QgsVectorLayer, field, classInfo: ClassInfo):
    """
    Sets the ClassInfo value or label to selected features
    :param vectorLayer: QgsVectorLayer
    :param field: QgsField or int with field index
    :param classInfo: ClassInfo
    """
    assert isinstance(vectorLayer, QgsVectorLayer)

    assert isinstance(classInfo, ClassInfo)

    if isinstance(field, QgsField):
        idx = vectorLayer.fields().lookupField(field.name())
    else:
        idx = field

    field = vectorLayer.fields().at(idx)

    vectorLayer.beginEditCommand('Set class info "{}"'.format(classInfo.name()))

    if field.type() == QVariant.String:
        value = str(classInfo.name())
    else:
        value = classInfo.label()

    for feature in vectorLayer.selectedFeatures():
        assert isinstance(feature, QgsFeature)
        oldValue = feature.attribute(field.name())
        vectorLayer.changeAttributeValue(feature.id(), idx, value, oldValue)
    vectorLayer.endEditCommand()


def setQuickTSDLabels(vectorLayer: QgsVectorLayer, tsd: TimeSeriesDate, tss: TimeSeriesSource):
    """
    Labels selected features with information related to TimeSeriesDate tsd, according to
    the settings specified in this model. Note: this will not the any ClassInfo or the source image values
    :param tsd: TimeSeriesDate
    :param classInfos:
    """
    assert isinstance(tsd, TimeSeriesDate)
    assert isinstance(vectorLayer, QgsVectorLayer)
    if not vectorLayer.isEditable():
        return
    vectorLayer.beginEditCommand('Quick labels {}'.format(tsd.date()))

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

                if labelType == LabelShortcutType.Off:
                    pass

                elif labelType == LabelShortcutType.Sensor:
                    value = tsd.sensor().name()

                elif labelType == LabelShortcutType.DOY:
                    value = tsd.doy()

                elif labelType == LabelShortcutType.Date:
                    if field.type() == QVariant.Date:
                        value = QDate(tsd.date().astype(object))
                    elif field.type() == QVariant.DateTime:
                        value = QDateTime(tsd.date().astype(object))
                    elif field.type() == QVariant.String:
                        value = str(tsd.date())

                elif labelType == LabelShortcutType.Year:
                    year = tsd.date().astype(object).year

                    if field.type() == QVariant.String:
                        value = str(year)
                    elif field.type() == QVariant.Date:
                        value = QDate(year, 1, 1)
                    elif field.type() == QVariant.DateTime:
                        value = QDateTime(2000, 1, 1, 0, 0)

                elif labelType == LabelShortcutType.DecimalYear:
                    value = tsd.decimalYear()

                elif labelType == LabelShortcutType.SourceImage and isinstance(tss, TimeSeriesSource):
                    value = tss.uri()

                if value:
                    if field.type() == QVariant.String:
                        value = str(value)

                    for feature in vectorLayer.selectedFeatures():
                        assert isinstance(feature, QgsFeature)
                        oldValue = feature.attribute(field.name())
                        vectorLayer.changeAttributeValue(feature.id(), i, value, oldValue)

        vectorLayer.endEditCommand()
    pass


class LabelAttributeTableModel(QAbstractTableModel):

    def __init__(self, parent=None, *args):

        super(LabelAttributeTableModel, self).__init__()

        self.cnField = 'Field'
        self.cnFieldType = 'Type'
        self.cnLabel = 'Label shortcut'
        self.mColumnNames = [self.cnField, self.cnFieldType, self.cnLabel]
        # self.mLabelTypes = dict()
        self.mVectorLayer = None

    def setVectorLayer(self, layer: QgsVectorLayer):

        if isinstance(layer, QgsVectorLayer):
            layer.attributeAdded.connect(self.resetModel)
            layer.attributeDeleted.connect(self.resetModel)

            self.mVectorLayer = layer
        else:
            self.mVectorLayer = None

        self.resetModel()

    def hasVectorLayer(self) -> bool:
        """
        Returns true if a QgsVectorLayer is specified.
        :return: bool
        """
        return isinstance(self.mVectorLayer, QgsVectorLayer)

    def resetModel(self):
        self.beginResetModel()

        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            for i in range(fields.count()):
                field = fields.at(i)
                assert isinstance(field, QgsField)
                # self.mLabelTypes[field.name()] = LabelShortcutType.Off

        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        if isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.fields().count()
        else:
            return 0

    def fieldName2Index(self, fieldName: str) -> str:
        assert isinstance(fieldName, str)

        if isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            i = fields.indexOf(fieldName)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()

    def field2index(self, field: QgsField) -> QModelIndex:
        assert isinstance(field, QgsField)
        return self.fieldName2Index(field.name())

    def index2editorSetup(self, index: QModelIndex):
        if index.isValid() and isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.editorWidgetSetup(index.row())
        else:
            return None

    def index2field(self, index: QModelIndex) -> QgsField:
        if index.isValid() and isinstance(self.mVectorLayer, QgsVectorLayer):
            fields = self.mVectorLayer.fields()
            assert isinstance(fields, QgsFields)
            return fields.at(index.row())
        else:
            return None

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.mColumnNames)

    def setFieldShortCut(self, fieldName: str, attributeType: LabelShortcutType):
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

    def shortcuts(self, field: QgsField):
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

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumnNames[index.column()]
        fields = self.mVectorLayer.fields()
        assert isinstance(fields, QgsFields)
        field = fields.at(index.row())
        assert isinstance(field, QgsField)
        setup = self.mVectorLayer.editorWidgetSetup(index.row())
        assert isinstance(setup, QgsEditorWidgetSetup)

        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if columnName == self.cnField:
                value = field.name()
            elif columnName == self.cnFieldType:
                value = '{}'.format(field.typeName())
            elif columnName == self.cnLabel:
                fac = QgsGui.editorWidgetRegistry().factory(setup.type())
                value = fac.name()
            else:
                s = ""
        elif role == Qt.UserRole:
            value = setup
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        columnName = self.mColumnNames[index.column()]
        fields = self.mVectorLayer.fields()
        assert isinstance(fields, QgsFields)
        field = fields.at(index.row())
        assert isinstance(field, QgsField)
        setup = self.mVectorLayer.editorWidgetSetup(index.row())
        assert isinstance(setup, QgsEditorWidgetSetup)

        changed = False
        if columnName == self.cnLabel and role == Qt.EditRole:
            if isinstance(value, str):
                setup = QgsEditorWidgetSetup(value, {})
                self.mVectorLayer.setEditorWidgetSetup(index.row(), setup)

                changed = True
        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed

    def columnName(self, index: int) -> str:
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

    def model(self) -> LabelAttributeTableModel:
        return self.mTableView.model()

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)
        model = self.model()
        for c in [model.cnLabel]:
            i = model.mColumnNames.index(c)
            tableView.setItemDelegateForColumn(i, self)

    def columnName(self, index: QModelIndex) -> str:
        if not index.isValid():
            return None
        return self.model().mColumnNames[index.column()]

    def createEditor(self, parent, option, index):
        cname = self.columnName(index)
        model = self.model()
        layer = model.mVectorLayer
        idx = index.row()
        w = None
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel:
                w = QComboBox(parent=parent)
                reg = QgsGui.editorWidgetRegistry()
                assert isinstance(reg, QgsEditorWidgetRegistry)
                factories = reg.factories()
                i = 0
                for key, fac in reg.factories().items():
                    score = fac.fieldScore(layer, idx)
                    if score > 0:
                        w.addItem(fac.name(), key)
        return w

    def setEditorData(self, editor, index):
        cname = self.columnName(index)
        model = self.model()
        layer = model.mVectorLayer

        w = None
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel and isinstance(editor, QComboBox):
                key = model.data(index, role=Qt.UserRole)
                i = -1
                for i in range(editor.count()):
                    if editor.itemData(i, role=Qt.UserRole) == key:
                        editor.setCurrentIndex(i)
                        break

    def setModelData(self, w, model, index):
        assert isinstance(model, LabelAttributeTableModel)
        assert isinstance(index, QModelIndex)

        cname = model.columnName(index)
        if index.isValid() and isinstance(model, LabelAttributeTableModel):
            if cname == model.cnLabel and isinstance(w, QComboBox):
                model.setData(index, w.currentData(Qt.UserRole), Qt.EditRole)


class LabelWidget(AttributeTableWidget):

    def __init__(self, *args, **kwds):

        super().__init__(*args, *kwds)

        self.mActionNextFeature = QAction('Next Feature', parent=self)
        self.mActionNextFeature.setIcon(QIcon(':/images/themes/default/mActionAtlasNext.svg'))
        self.mActionNextFeature.triggered.connect(self.nextFeature)

        self.mActionPreviousFeature = QAction('Previous Feature', parent=self)
        self.mActionPreviousFeature.setIcon(QIcon(':/images/themes/default/mActionAtlasPrev.svg'))
        self.mActionPreviousFeature.triggered.connect(self.previousFeature)

        self.mToolbar: QToolBar
        self.mToolbar.insertActions(self.mActionToggleEditing, [self.mActionPreviousFeature, self.mActionNextFeature])
        self.mToolbar.insertSeparator(self.mActionToggleEditing)

    def nextFeature(self):
        """
        Selects the next feature and moves the map extent to.
        """
        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.hasFeatures():
            allIDs = sorted(self.mLayer.allFeatureIds())
            fids = self.mLayer.selectedFeatureIds()
            if len(fids) == 0:
                nextFID = allIDs[0]
            else:
                i = min(allIDs.index(max(fids)) + 1, len(allIDs) - 1)
                nextFID = allIDs[i]
            self.mLayer.selectByIds([nextFID])
            self.mVectorLayerTools.panToSelected(self.mLayer)

    def previousFeature(self):
        """
        Selects the previous feature and moves the map extent to.
        """
        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.hasFeatures():
            allIDs = sorted(self.mLayer.allFeatureIds())
            fids = self.mLayer.selectedFeatureIds()
            if len(fids) == 0:
                nextFID = allIDs[0]
            else:
                i = max(allIDs.index(min(fids)) - 1, 0)
                nextFID = allIDs[i]
            self.mLayer.selectByIds([nextFID])
            self.mVectorLayerTools.panToSelected(self.mLayer)


class LabelDockWidget(QgsDockWidget):

    def __init__(self, layer, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mLabelWidget = LabelWidget(layer)
        self.setWidget(self.mLabelWidget)
        self.setWindowTitle(self.mLabelWidget.windowTitle())
        self.mLabelWidget.windowTitleChanged.connect(self.setWindowTitle)

    def setVectorLayerTools(self, tools: QgsVectorLayerTools):
        self.mLabelWidget.setVectorLayerTools(tools)

    def vectorLayer(self) -> QgsVectorLayer:
        if isinstance(self.mLabelWidget.mLayer, QgsVectorLayer):
            return self.mLabelWidget.mLayer
        return None


class LabelShortcutEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):

        super(LabelShortcutEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        # self.setupUi(self)

        self.setLayout(QVBoxLayout())

        self.mCBShortCutType = QComboBox(self)
        # self.mClassWidget = ClassificationSchemeWidget(parent=self)
        self.layout().addWidget(self.mCBShortCutType)
        # self.layout().addWidget(self.mClassWidget)
        self.layout().addStretch(0)
        assert isinstance(vl, QgsVectorLayer)
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        self.mAllowedShortCuts = shortcuts(field)
        for i, option in enumerate(self.mAllowedShortCuts):
            self.mCBShortCutType.addItem(option.value, option)

        self.mCBShortCutType.currentIndexChanged[int].connect(self.onIndexChanged)
        self.mCBShortCutType.currentIndexChanged[int].connect(lambda: self.onIndexChanged())

        self.mLastConfig = {}

        self.onIndexChanged()

    def config(self, *args, **kwargs) -> dict:

        conf = dict()
        conf[CONFKEY_LABELTYPE] = self.mCBShortCutType.currentData()
        conf['FIELD_INDEX'] = self.field()
        # cs = self.mClassWidget.classificationScheme()
        # assert isinstance(cs, ClassificationScheme)
        # todo: json for serialization
        # conf[CONFKEY_CLASSIFICATIONSCHEME] = cs

        return conf

    def setConfig(self, config: dict):
        self.mLastConfig = config
        labelType = config.get(CONFKEY_LABELTYPE)
        fieldIndex = config.get('FIELD_INDEX')

        if not isinstance(labelType, LabelShortcutType):
            labelType = LabelShortcutType.Off

        if labelType not in self.mAllowedShortCuts:
            labelType = self.mAllowedShortCuts[0]

        i = self.mCBShortCutType.findData(labelType)
        self.mCBShortCutType.setCurrentIndex(i)

    def onIndexChanged(self, *args):

        ltype = self.shortcutType()
        # if ltype == LabelShortcutType.Classification:
        #    self.mClassWidget.setEnabled(True)
        #    self.mClassWidget.setVisible(True)
        # else:
        #    self.mClassWidget.setEnabled(False)
        #    self.mClassWidget.setVisible(False)
        self.changed.emit()

    # def classificationScheme(self) -> ClassificationScheme:
    #    return self.mClassWidget.classificationScheme()

    # def setClassificationScheme(self, classScheme:ClassificationScheme):
    #    assert isinstance(classScheme, ClassificationScheme)
    #    self.mClassWidget.setClassificationScheme(classScheme)

    def shortcutType(self) -> LabelShortcutType:
        return self.mCBShortCutType.currentData(Qt.UserRole)


class LabelShortcutEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(LabelShortcutEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)

        self.mEditor = None
        self.mValidator = None

    def configLabelType(self) -> LabelShortcutType:
        return self.config().get(CONFKEY_LABELTYPE)

    def createWidget(self, parent: QWidget):
        """
        Create the data input widget
        :param parent: QWidget
        :return: ClassificationSchemeComboBox | default widget
        """
        # log('createWidget')
        labelType = self.configLabelType()
        # if labelType == LabelShortcutType.Classification:
        #    self.mEditor = ClassificationSchemeComboBox(parent)
        # else:
        self.mEditor = QLineEdit(parent)
        self.mValidator = QRegExpValidator()
        return self.mEditor

    def initWidget(self, editor: QWidget):
        # log(' initWidget')

        # if isinstance(editor, ClassificationSchemeComboBox):
        #    cs = self.configClassificationScheme()
        #    if isinstance(cs, ClassificationScheme):
        #        self.mEditor.setClassificationScheme(cs)
        #        self.mEditor.currentIndexChanged.connect(self.onValueChanged)

        # if isinstance(editor, QLineEdit):
        self.mEditor = editor
        self.mEditor.textChanged.connect(self.onValueChanged)

    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def config(self) -> dict:
        d = dict()

        return d

    def setConfig(self, conf: dict):

        s = ""
        pass

    def valid(self, *args, **kwargs) -> bool:
        """
        Returns True if a valid editor widget exists
        :param args:
        :param kwargs:
        :return: bool
        """
        # return isinstance(self.mEditor, (ClassificationSchemeComboBox, QLineEdit))
        return isinstance(self.mEditor, QLineEdit)

    def value(self, *args, **kwargs):
        """
        Reuturns the value
        :param args:
        :param kwargs:
        :return:
        """
        typeCode = self.field().type()
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
            return txt

            return self.mLineEdit.text()

        return self.defaultValue()

    def setEnabled(self, enabled: bool):

        if isinstance(self.mEditor, QWidget):
            self.mEditor.setEnabled(enabled)

    def setValue(self, value):

        # if isinstance(self.mEditor, ClassificationSchemeComboBox):
        #    cs = self.mEditor.classificationScheme()
        #    if isinstance(cs, ClassificationScheme) and len(cs) > 0:
        #        i = cs.classIndexFromValue(value)
        #        self.mEditor.setCurrentIndex(max(i, 0))
        # elif isinstance(self.mEditor, QLineEdit):
        if value in [QVariant(), None]:
            self.mEditor.setText(None)
        else:
            self.mEditor.setText(str(value))


class LabelShortcutWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name: str):

        super(LabelShortcutWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def name(self) -> str:
        return EDITOR_WIDGET_REGISTRY_KEY

    def configWidget(self, layer: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> LabelShortcutEditorConfigWidget:
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
        w.changed.connect(lambda: self.writeConfig(key, w.config()))
        return w

    def configKey(self, layer: QgsVectorLayer, fieldIdx: int):
        """
        Returns a tuple to be used as dictionary key to identify a layer field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return (layer.id(), fieldIdx)

    def create(self, layer: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> LabelShortcutEditorWidgetWrapper:
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

    def writeConfig(self, key: tuple, config: dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config

    def readConfig(self, key: tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        if key in self.mConfigurations.keys():
            conf = self.mConfigurations[key]
        else:
            # return the very default configuration
            conf = {}
        return conf

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        if fieldIdx < 0:
            return 0
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() in [QVariant.String, QVariant.Int, QVariant.Date, QVariant.DateTime]:
            return 5
        else:
            return 0  # no support

    def supportsField(self, vl: QgsVectorLayer, idx: int) -> True:
        """
        :param vl: vectorlayers
        :param idx:
        :return: bool
        """
        field = vl.fields().at(idx)
        if isinstance(field, QgsField) and field.type() in [QVariant.Int, QVariant.String, QVariant.Date,
                                                            QVariant.DateTime]:
            return True
        return False


EDITOR_WIDGET_REGISTRY_KEY = 'EOTSV_Quick Label'
labelEditorWidgetFactory = None


def registerLabelShortcutEditorWidget():
    reg = QgsGui.editorWidgetRegistry()
    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        labelEditorWidgetFactory = LabelShortcutWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, labelEditorWidgetFactory)
    else:
        labelEditorWidgetFactory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
