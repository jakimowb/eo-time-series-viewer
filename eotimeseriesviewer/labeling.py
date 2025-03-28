import enum
import math
from typing import Dict, List, Union

import numpy as np
from qgis.PyQt.QtCore import pyqtSignal, QAbstractTableModel, QDate, QDateTime, QModelIndex, QSortFilterProxyModel, Qt, \
    QTime, QVariant
from qgis.gui import QgsAttributeTableModel, QgsAttributeTableView, QgsDateEdit, QgsDateTimeEdit, QgsDoubleSpinBox, \
    QgsEditorConfigWidget, QgsEditorWidgetFactory, QgsEditorWidgetRegistry, QgsEditorWidgetWrapper, QgsGui, QgsSpinBox, \
    QgsTimeEdit
from qgis.PyQt.QtGui import QIcon, QKeySequence, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAction, QComboBox, QLineEdit, QMenu, QStyledItemDelegate, QTableView, QToolBar, \
    QToolButton, QWidget
from qgis.core import QgsCategorizedSymbolRenderer, QgsEditorWidgetSetup, QgsFeature, QgsField, QgsFields, \
    QgsMapLayerStore, QgsProject, QgsRendererCategory, QgsSymbol, QgsVectorLayer

from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.vectorlayertools import EOTSVVectorLayerTools
from .qgispluginsupport.qps.classification.classificationscheme import ClassificationScheme, ClassInfo, \
    EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
from .qgispluginsupport.qps.layerproperties import showLayerPropertiesDialog
from .qgispluginsupport.qps.utils import datetime64, loadUi, SpatialExtent, SpatialPoint
from .timeseries.source import TimeSeriesDate, TimeSeriesSource

# the QgsProject(s) and QgsMapLayerStore(s) to search for QgsVectorLayers
MAP_LAYER_STORES = []

EDITOR_WIDGET_REGISTRY_KEY = 'EOTSV Quick Label'


def mapLayerStores() -> List[Union[QgsProject, QgsMapLayerStore]]:
    if len(MAP_LAYER_STORES) == 0:
        MAP_LAYER_STORES.append(QgsProject.instance())

    return MAP_LAYER_STORES[:]


class LabelConfigurationKey(object):
    ClassificationScheme = 'classificationScheme'
    LabelType = 'labelType'
    LabelGroup = 'labelGroup'


class LabelShortcutType(enum.Enum):
    """Enumeration for shortcuts to be derived from a TimeSeriesDate instance"""
    Off = 'No Quick Label (default)'
    Date = 'Date'
    DateTime = 'Date-Time'
    Time = 'Time'
    DOY = 'Day of Year (DOY)'
    Year = 'Year'
    DecimalYear = 'Decimal Year'
    Sensor = 'Sensor Name'
    SourceImage = 'Source Image'

    # Classification = 'Classification'

    @staticmethod
    def fromConfValue(value: str):
        for t in LabelShortcutType:
            if value in [t.name, t.value]:
                return t
        return LabelShortcutType.Off

    def confValue(self) -> str:
        return self.name

    def text(self) -> str:
        return self.value

    def __str__(self):
        return str(self.name)


def shortcuts(field: QgsField) -> List[LabelShortcutType]:
    """
    Returns the possible LabelShortCutTypes for a certain field
    :param field:
    :type field:
    :param fieldName: str
    :return: [list]
    """
    assert isinstance(field, QgsField)

    shortCutsString = [LabelShortcutType.Sensor, LabelShortcutType.Date, LabelShortcutType.Time,
                       LabelShortcutType.DateTime, LabelShortcutType.SourceImage]
    shortCutsInt = [LabelShortcutType.Year, LabelShortcutType.DOY]
    shortCutsFloat = [LabelShortcutType.Year, LabelShortcutType.DOY, LabelShortcutType.DecimalYear]

    options = [LabelShortcutType.Off]
    fieldType = field.type()
    if fieldType in [QVariant.String]:
        options.extend(shortCutsString)
        options.extend(shortCutsInt)
        options.extend(shortCutsFloat)
    elif fieldType in [QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong]:
        options.extend(shortCutsInt)
    elif fieldType in [QVariant.Double]:
        options.extend(shortCutsInt)
        options.extend(shortCutsFloat)
    elif fieldType == QVariant.DateTime:
        options.extend([LabelShortcutType.DateTime])
    elif fieldType == QVariant.Date:
        options.extend([LabelShortcutType.Date])
    elif fieldType == QVariant.Time:
        options.extend([LabelShortcutType.Time])
    else:
        s = ""
    result = []
    for o in options:
        if o not in result:
            result.append(o)
    return result


def layerClassSchemes(layer: QgsVectorLayer) -> List[ClassificationScheme]:
    """
    Returns a list of (ClassificationScheme, QgsField) for all QgsFields with QgsEditorWidget being QgsClassificationWidgetWrapper or RasterClassification.
    :param layer: QgsVectorLayer
    :return: list [(ClassificationScheme, QgsField), ...]
    """
    assert isinstance(layer, QgsVectorLayer)
    from .qgispluginsupport.qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
    from .qgispluginsupport.qps.classification.classificationscheme import classSchemeFromConfig
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
            ci = conf.get(LabelConfigurationKey.ClassificationScheme.value)
            if isinstance(ci, ClassificationScheme) and ci not in classSchemes:
                classSchemes.append((ci, layer.fields().at(i)))

    return classSchemes


def quickLabelLayers() -> List[QgsVectorLayer]:
    """
    Returns a list of known QgsVectorLayers with at least one LabelShortcutEditWidget
    :return: [list-of-QgsVectorLayer]
    """
    layers = []

    classSchemes = set()
    for store in mapLayerStores():
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


def quickLayerGroups(layer) -> List[str]:
    groups = set()
    if isinstance(layer, list):
        for l in layer:
            groups.update(quickLayerGroups(l))
    else:
        for i, field in enumerate(layer.fields()):
            setup = layer.editorWidgetSetup(i)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                groups.add(setup.config().get(LabelConfigurationKey.LabelGroup, ''))
    return sorted(groups)


def quickLayerFieldSetup(layer, label_group: str = None) -> List[QgsField]:
    fields = []
    if isinstance(layer, list):
        for l in layer:
            fields.extend(quickLayerFieldSetup(l))
    else:
        for i, field in enumerate(layer.fields()):
            setup = layer.editorWidgetSetup(i)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                if isinstance(label_group, str):
                    grp = setup.config().get(LabelConfigurationKey.LabelGroup, '')
                    if grp != label_group:
                        continue
                fields.append(field)
    return fields


def setQuickTSDLabelsForRegisteredLayers(tsd: TimeSeriesDate,
                                         tss: TimeSeriesSource,
                                         layer_group: str = ''):
    """
    :param tsd: TimeSeriesDate
    :param classInfos:
    """
    for layer in quickLabelLayers():
        assert isinstance(layer, QgsVectorLayer)
        if layer.isEditable():
            setQuickTSDLabels(layer, tsd, tss, label_group=layer_group)


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


def setQuickTSDLabels(vectorLayer: QgsVectorLayer,
                      tsd: TimeSeriesDate,
                      tss: TimeSeriesSource,
                      label_group: str = ''):
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
    vectorLayer.beginEditCommand('Quick labels {}'.format(tsd.dtg()))
    for field in quickLayerFieldSetup(vectorLayer, label_group=label_group):
        assert isinstance(field, QgsField)
        iField: int = vectorLayer.fields().lookupField(field.name())
        assert iField >= 0
        setup: QgsEditorWidgetSetup = vectorLayer.editorWidgetSetup(iField)
        assert isinstance(setup, QgsEditorWidgetSetup)
        assert setup.type() == EDITOR_WIDGET_REGISTRY_KEY

        fieldType = field.type()
        conf = setup.config()
        labelType: LabelShortcutType = LabelShortcutType.fromConfValue(conf.get(LabelConfigurationKey.LabelType))

        value = quickLabelValue(fieldType, labelType, tsd, tss)

        if value is not None:
            for feature in vectorLayer.selectedFeatures():
                assert isinstance(feature, QgsFeature)
                oldValue = feature.attribute(field.name())
                vectorLayer.changeAttributeValue(feature.id(), iField, value, oldValue)

        vectorLayer.endEditCommand()
        vectorLayer.triggerRepaint()
    pass


def quickLabelValue(fieldType: QVariant,
                    labelType: LabelShortcutType,
                    tsd: TimeSeriesDate,
                    tss: TimeSeriesSource):
    value = None
    dt: QDateTime = tsd.dtg()

    if labelType == LabelShortcutType.Off:
        return value

    if labelType == LabelShortcutType.Sensor:
        if fieldType == QVariant.String:
            value = tsd.sensor().name()

    elif labelType == LabelShortcutType.DOY:
        if fieldType in [QVariant.Double, QVariant.Int]:
            value = tsd.doy()
        elif fieldType == QVariant.String:
            value = str(tsd.doy())

    elif labelType == LabelShortcutType.Date:
        if fieldType == QVariant.Date:
            value = dt.date()
        elif fieldType == QVariant.DateTime:
            value = dt
        elif fieldType == QVariant.String:
            value = dt.toString(Qt.ISODate)

    elif labelType == LabelShortcutType.DateTime:
        if fieldType == QVariant.Date:
            value = dt.date()
        elif fieldType == QVariant.DateTime:
            value = dt
        elif fieldType == QVariant.String:
            value = dt.toPyDateTime().isoformat()

    elif labelType == LabelShortcutType.Time:
        if fieldType == QVariant.Date:
            value = None
        elif fieldType == QVariant.DateTime:
            value = dt
        elif fieldType == QVariant.Time:
            value = dt.time()
        elif fieldType == QVariant.String:
            value = dt.time().toString(Qt.ISODate)

    elif labelType == LabelShortcutType.Year:

        if fieldType == QVariant.String:
            value = str(dt.date().year())
        elif fieldType == QVariant.Date:
            value = dt.date()
        elif fieldType == QVariant.DateTime:
            value = dt
        elif fieldType == QVariant.Time:
            value = dt.time()
        elif fieldType == QVariant.Int:
            value = dt.date().year()

    elif labelType == LabelShortcutType.DecimalYear:
        if fieldType == QVariant.String:
            value = str(tsd.decimalYear())
        elif fieldType == QVariant.Int:
            value = int(tsd.decimalYear())
        elif fieldType == QVariant.Double:
            value = tsd.decimalYear()

    elif labelType == LabelShortcutType.SourceImage and isinstance(tss, TimeSeriesSource):
        if fieldType == QVariant.String:
            value = tss.source()

    if value is not None and fieldType == QVariant.String:
        value = str(value)
    return value


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


class GotoFeatureOptions(enum.IntFlag):
    SelectFeature = 1
    PanToFeature = 2
    ZoomToFeature = 4
    FocusVisibility = 8


def gotoLayerFeature(fid: int, layer: QgsVectorLayer, tools: EOTSVVectorLayerTools, options: GotoFeatureOptions):
    if GotoFeatureOptions.SelectFeature in options:
        layer.selectByIds([fid])
    if GotoFeatureOptions.PanToFeature in options:
        tools.panToSelected(layer)
    if GotoFeatureOptions.ZoomToFeature in options:
        tools.zoomToSelected(layer)
    if GotoFeatureOptions.FocusVisibility in options:
        tools.focusVisibility()


def gotoFeature(attributeTable: AttributeTableWidget,
                goDown: bool = True,
                options: GotoFeatureOptions = GotoFeatureOptions.SelectFeature

                ) -> int:
    assert isinstance(attributeTable, AttributeTableWidget)

    tv: QgsAttributeTableView = attributeTable.mMainView.tableView()
    model: QSortFilterProxyModel = tv.model()

    FID_ORDER = []

    for r in range(model.rowCount()):
        fid = model.data(model.index(r, 0), Qt.UserRole)
        FID_ORDER.append(fid)

    if len(FID_ORDER) > 0:
        sfids = tv.selectedFeaturesIds()
        if len(sfids) == 0:
            nextFID = FID_ORDER[0]
        elif goDown:
            row = FID_ORDER.index(sfids[-1])
            nextFID = model.data(model.index(row + 1, 0), Qt.UserRole)
            if nextFID is None:
                nextFID = FID_ORDER[-1]
        else:
            row = FID_ORDER.index(sfids[0])
            nextFID = model.data(model.index(row - 1, 0), Qt.UserRole)
            if nextFID is None:
                nextFID = FID_ORDER[0]

        if isinstance(nextFID, int):
            tv.scrollToFeature(nextFID)
        gotoLayerFeature(nextFID, attributeTable.mLayer, attributeTable.vectorLayerTools(), options)
        return nextFID
    return None


class LabelWidget(AttributeTableWidget):
    sigMoveTo = pyqtSignal([QDateTime],
                           [QDateTime, object])

    def __init__(self, *args, **kwds):

        super().__init__(*args, *kwds)

        self.mActionNextFeature: QAction = QAction('Next Feature', parent=self)
        self.mActionPreviousFeature: QAction = QAction('Previous Feature', parent=self)
        self.mActionNextFeature.setIcon(QIcon(':/images/themes/default/mActionArrowDown.svg'))
        self.mActionPreviousFeature.setIcon(QIcon(':/images/themes/default/mActionArrowUp.svg'))
        self.mActionNextFeature.setShortcuts([QKeySequence(QKeySequence.MoveToNextLine),
                                              QKeySequence(Qt.Key_S)])
        self.mActionPreviousFeature.setShortcuts([QKeySequence(QKeySequence.MoveToPreviousLine),
                                                  QKeySequence(Qt.Key_W)])

        self.mActionNextFeature.triggered.connect(self.onGotoNextFeature)
        self.mActionPreviousFeature.triggered.connect(self.onGotoPreviousFeature)

        for action in [self.mActionNextFeature, self.mActionPreviousFeature]:
            # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            pass

        m = QMenu()
        m.setToolTip('Optional actions after clicking the next / previous feature button.')
        m.setToolTipsVisible(True)

        self.mOptionAutoSelectNextFeature = m.addAction('Auto select')
        self.mOptionAutoSelectNextFeature.setToolTip('Automatically selects the next / previous feature')
        self.mOptionAutoSelectNextFeature.setCheckable(True)
        self.mOptionAutoSelectNextFeature.setIcon(QIcon(':/images/themes/default/mIconSelected.svg'))
        self.mOptionAutoSelectNextFeature.setChecked(True)
        self.mOptionAutoSelectNextFeature.setVisible(False)

        self.mOptionAutoPan = m.addAction('Auto pan')
        self.mOptionAutoPan.setToolTip('Automatically pans the the next / previous feature')
        self.mOptionAutoPan.setIcon(QIcon(':/images/themes/default/mActionPanToSelected.svg'))
        self.mOptionAutoPan.setCheckable(True)
        self.mOptionAutoPan.setChecked(True)

        self.mOptionAutoUpdateImageVisibility = m.addAction('Auto visibility update')
        self.mOptionAutoUpdateImageVisibility.setToolTip(
            r'Automatically shows/hides dates that do/don\'t intersect with spatial map extent.')
        self.mOptionAutoUpdateImageVisibility.setCheckable(True)
        self.mOptionAutoUpdateImageVisibility.setChecked(False)
        self.mOptionAutoUpdateImageVisibility.setIcon(QIcon(':/eotimeseriesviewer/icons/mapview.svg'))

        self.mActionNextFeature.setMenu(m)
        # self.mActionPreviousFeature.setMenu(m)

        m = QMenu()
        m.setToolTipsVisible(True)

        self.mOptionSelectBehaviour: QAction = m.addAction('Selection behaviour')
        self.mOptionSelectBehaviour.setCheckable(True)
        self.mOptionSelectBehaviour.setChecked(True)

        self.mOptionSelectionSetSelection = m.addAction('Set Selection')
        self.mOptionSelectionSetSelection.setIcon(QIcon(':/images/themes/default/mIconSelected.svg'))
        self.mOptionSelectionSetSelection.setToolTip('Selects a feature.')

        self.mOptionSelectionAddToSelection = m.addAction('Add to Selection')
        self.mOptionSelectionAddToSelection.setIcon(QIcon(':/images/themes/default/mIconSelectAdd.svg'))
        self.mOptionSelectionAddToSelection.setToolTip('Adds a new feature to an existing selection.')

        # self.mOptionSelectionIntersectSelection = m.addAction('Intersect Selection')
        # self.mOptionSelectionIntersectSelection.setIcon(QIcon(':/images/themes/default/mIconSelectIntersect.svg'))

        # self.mOptionRemoveFromSelection = m.addAction('Remove from Selection')
        # self.mOptionRemoveFromSelection.setIcon(QIcon(':/images/themes/default/mIconSelectRemove.svg'))

        self.mOptionSelectBehaviour.setMenu(m)

        for o in [self.mOptionSelectionSetSelection,
                  self.mOptionSelectionAddToSelection,
                  # self.mOptionSelectionIntersectSelection,
                  # self.mOptionRemoveFromSelection
                  ]:
            o.setCheckable(True)
            o.triggered.connect(self.onSelectBehaviourOptionTriggered)

        self.mOptionSelectionSetSelection.trigger()
        # show selected feature on top by default
        # self.mActionSelectedToTop.setChecked(True)

        self.mToolbar: QToolBar
        self.mToolbar.insertActions(self.mActionToggleEditing,
                                    [self.mActionPreviousFeature,
                                     self.mActionNextFeature,
                                     self.mOptionSelectBehaviour])

        self.mToolbar.insertSeparator(self.mActionToggleEditing)

        self.actionShowProperties = QAction('Show Layer Properties')
        self.actionShowProperties.setToolTip('Show Layer Properties')
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.btnShowProperties = QToolButton()
        self.btnShowProperties.setAutoRaise(True)
        self.btnShowProperties.setDefaultAction(self.actionShowProperties)

        self.centerBottomLayout.insertWidget(self.centerBottomLayout.indexOf(self.mAttributeViewButton),
                                             self.btnShowProperties)

        self.mLayer.featureAdded.connect(self.onLabelFeatureAdded)
        self.mMainView.tableView().willShowContextMenu.connect(self.onShowContextMenu)

    def onGotoNextFeature(self, *arg):
        gotoFeature(self, goDown=True, options=self.gotoFeatureOptions())

    def gotoFeatureOptions(self) -> GotoFeatureOptions:
        """
        Returns the GoTo-Feature options
        :return:
        :rtype:
        """
        options = GotoFeatureOptions(0)
        if self.mOptionAutoSelectNextFeature.isChecked():
            options = options | GotoFeatureOptions.SelectFeature
        if self.mOptionAutoPan.isChecked():
            options = options | GotoFeatureOptions.PanToFeature
        if self.mOptionAutoUpdateImageVisibility.isChecked():
            options = options | GotoFeatureOptions.FocusVisibility
        return options

    def onGotoPreviousFeature(self, *args):
        gotoFeature(self, goDown=False, options=self.gotoFeatureOptions())

    def onShowContextMenu(self, menu: QMenu, idx: QModelIndex):

        fid = idx.data(QgsAttributeTableModel.FeatureIdRole)
        fieldIdx = idx.data(QgsAttributeTableModel.FieldIndexRole)
        lyr = self.mLayer
        if not isinstance(lyr, QgsVectorLayer):
            return

        feature: QgsFeature = self.mLayer.getFeature(fid)
        if not isinstance(feature, QgsFeature):
            return

        ACTIONS = dict()
        for a in menu.findChildren(QAction):
            ACTIONS[a.text()] = a

        # todo: connect default options

        extent: SpatialExtent = SpatialExtent(lyr.crs(), feature.geometry().boundingBox())
        center: SpatialPoint = SpatialPoint(lyr.crs(), feature.geometry().centroid().asPoint())
        field = lyr.fields().at(fieldIdx)

        if field.type() in [QVariant.Date, QVariant.DateTime]:

            if isinstance(feature, QgsFeature):
                datetime = feature.attribute(fieldIdx)
                try:
                    datetime = QDateTime(datetime64(datetime).astype(object))
                except Exception:
                    pass

                # add temporal options
                if isinstance(datetime, QDateTime):
                    date_string = datetime.toString(Qt.ISODate)
                    a1 = QAction('Move time to', menu)
                    a1.setToolTip(f'Moves the current date to {date_string}')
                    a1.triggered.connect(lambda *args, d=datetime:
                                         self.sigMoveTo[QDateTime].emit(d))

                    a2 = QAction('Move time && pan to', menu)
                    a2.setToolTip(f'Moves the current date to {date_string} and pans to feature {feature.id()}')
                    a2.triggered.connect(lambda *args, f=feature, d=datetime:
                                         self.sigMoveTo[QDateTime, object].emit(d, center))

                    a3 = QAction('Move time && zoom to', menu)
                    a2.setToolTip(f'Moves the current date to {date_string} and zooms to feature {feature.id()}')
                    a3.triggered.connect(lambda *args, f=feature, d=datetime:
                                         self.sigMoveTo[QDateTime, object].emit(d, extent))

                    menu.insertActions(menu.actions()[0], [a1, a2, a3])
                    menu.insertSeparator(menu.actions()[3])

    def selectBehaviour(self) -> QgsVectorLayer.SelectBehavior:
        if self.mOptionSelectionSetSelection.isChecked():
            return QgsVectorLayer.SetSelection
        elif self.mOptionSelectionAddToSelection.isChecked():
            return QgsVectorLayer.AddToSelection
        elif self.mOptionSelectionIntersectSelection.isChecked():
            return QgsVectorLayer.IntersectSelection
        elif self.mOptionRemoveFromSelection.isChecked():
            return QgsVectorLayer.RemoveFromSelection
        else:
            return QgsVectorLayer.SetSelection

    def onSelectBehaviourOptionTriggered(self):

        a: QAction = self.sender()
        m: QMenu = self.mOptionSelectBehaviour.menu()

        if isinstance(a, QAction) and isinstance(m, QMenu) and a in m.actions():
            for ca in m.actions():
                assert isinstance(ca, QAction)
                if ca == a:
                    self.mOptionSelectBehaviour.setIcon(a.icon())
                    self.mOptionSelectBehaviour.setText(a.text())
                    self.mOptionSelectBehaviour.setToolTip(a.toolTip())
                    self.mOptionSelectBehaviour.setChecked(True)
                ca.setChecked(ca == a)

    def onLabelFeatureAdded(self, fid):
        if self.mOptionSelectBehaviour.isChecked():
            lastSelection: List[int] = self.mLayer.selectedFeatureIds()
            self.mLayer.selectByIds([fid], self.selectBehaviour())

    def showProperties(self, *args):
        showLayerPropertiesDialog(self.mLayer, None, parent=self, useQGISDialog=True)


class LabelShortcutEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):

        super(LabelShortcutEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        loadUi(DIR_UI / 'labelshortcuteditorconfigwidget.ui', self)

        self.cbLabelType: QComboBox
        self.cbLabelGroup: QComboBox
        assert isinstance(vl, QgsVectorLayer)
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        self.mAllowedShortCuts = shortcuts(field)
        for i, option in enumerate(self.mAllowedShortCuts):
            self.cbLabelType.addItem(option.value, option)

        self.cbLabelType.currentIndexChanged[int].connect(self.changed.emit)
        self.cbLabelGroup.setEditable(True)
        self.cbLabelGroup.setInsertPolicy(QComboBox.InsertAtTop)
        self.cbLabelGroup.currentIndexChanged.connect(self.changed.emit)
        self.btnAddGroup.setDefaultAction(self.actionAddGroup)
        self.actionAddGroup.triggered.connect(self.onAddGroup)

        # self.setConfig(vl.editorWidgetSetup(fieldIdx).config())
        self.mLastConfig = {}

    def onAddGroup(self):

        grp = self.cbLabelGroup.currentText()
        if grp in ['', None]:
            return
        m = self.cbLabelGroup.model()
        if isinstance(m, QStandardItemModel):
            for r in range(m.rowCount()):
                item = m.item(r)
                if grp == item.data(Qt.DisplayRole):
                    return

            #
            newItem = QStandardItem(grp)
            m.appendRow(newItem)

    def setLayerGroupModel(self, model: QStandardItemModel):
        self.cbLabelGroup.setModel(model)

    def config(self, *args, **kwargs) -> dict:
        """
        Return the widget configuration
        :param args:
        :type args:
        :param kwargs:
        :type kwargs:
        :return:
        :rtype:
        """
        conf = createWidgetConf(self.cbLabelType.currentData(),
                                group=self.cbLabelGroup.currentText())

        grp = conf.get(LabelConfigurationKey.LabelGroup, '')
        # add group to group model to share it with other LabelShortcutEditorConfigWidgets
        self.addLabelGroup(grp)
        return conf

    def addLabelGroup(self, grp: str):

        m: QStandardItemModel = self.cbLabelGroup.model()

        if grp not in ['', None] and isinstance(m, QStandardItemModel):
            exists = False
            for r in range(m.rowCount()):
                item = m.item(r)
                if grp == item.data(Qt.DisplayRole):
                    exists = True
                    break
            if not exists:
                m.appendRow(QStandardItem(grp))

    def setLabelGroup(self, grp):

        if grp is None:
            grp = ''
        else:
            grp = str(grp).strip()

        i = self.cbLabelGroup.findText(grp)
        if i == -1 and grp != '':
            self.addLabelGroup(grp)
            i = self.cbLabelGroup.findText(grp)

        if i >= 0:
            self.cbLabelGroup.setCurrentIndex(i)
            s = ""
        else:
            self.cbLabelGroup.setCurrentText(grp)

    def fieldName(self) -> str:
        field = self.layer().fields().at(self.field())
        return field.name()

    def setConfig(self, config: dict):
        self.mLastConfig = config
        if len(config) > 0:
            s = ""

        labelType: LabelShortcutType = LabelShortcutType.fromConfValue(
            config.get(LabelConfigurationKey.LabelType, None)
        )

        assert isinstance(labelType, LabelShortcutType)
        labelGroup: str = config.get(LabelConfigurationKey.LabelGroup, '')
        if labelType not in self.mAllowedShortCuts:
            labelType = self.mAllowedShortCuts[0]

        i = self.cbLabelType.findData(labelType)
        self.cbLabelType.setCurrentIndex(i)
        self.setLabelGroup(labelGroup)
        grp2 = self.cbLabelGroup.currentText()
        if grp2 != labelGroup:
            s = ""

    def onIndexChanged(self, *args):
        self.changed.emit()


class LabelShortcutEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(LabelShortcutEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)

    def createWidget(self, parent: QWidget = None) -> QWidget:
        """
        Create the data input widget
        :param parent: QWidget
        :return: QLineEdit | QgsDateTimeEdit | QSpinBox
        """
        # log('createWidget')
        # labelType = self.configLabelType()
        fieldType = self.field().type()
        if fieldType == QVariant.Date:
            return QgsDateEdit(parent)
        elif fieldType == QVariant.DateTime:
            return QgsDateTimeEdit(parent)
        elif fieldType == QVariant.Time:
            return QgsTimeEdit(parent)
        elif fieldType == QVariant.Double:
            return QgsDoubleSpinBox(parent)
        elif fieldType == QVariant.Int:
            return QgsSpinBox(parent)
        else:
            return QLineEdit(parent)

    def initWidget(self, editor: QWidget):
        # log(' initWidget')

        # if isinstance(editor, ClassificationSchemeComboBox):
        #    cs = self.configClassificationScheme()
        #    if isinstance(cs, ClassificationScheme):
        #        self.mEditor.setClassificationScheme(cs)
        #        self.mEditor.currentIndexChanged.connect(self.onValueChanged)

        if isinstance(editor, QLineEdit):
            editor.textChanged.connect(self.onValueChanged)
        elif isinstance(editor, (QgsTimeEdit, QgsDateEdit, QgsDateTimeEdit)):
            if isinstance(editor, QgsDateEdit):
                editor.setDisplayFormat('yyyy-MM-dd')
            elif isinstance(editor, QgsDateTimeEdit):
                editor.setDisplayFormat('yyyy-MM-dd HH:mm')
            elif isinstance(editor, QgsTimeEdit):
                pass
            editor.clear()
            editor.valueChanged.connect(self.onValueChanged)
        elif isinstance(editor, (QgsDoubleSpinBox, QgsSpinBox)):
            editor.valueChanged.connect(self.onValueChanged)

        else:
            s = ""

    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs) -> bool:
        """
        Returns True if a valid editor widget exists
        :param args:
        :param kwargs:
        :return: bool
        """
        # return isinstance(self.mEditor, (ClassificationSchemeComboBox, QLineEdit))
        return isinstance(self.widget(), (QLineEdit, QgsDateTimeEdit, QgsTimeEdit,
                                          QgsDateEdit, QgsSpinBox, QgsDoubleSpinBox))

    def value(self, *args, **kwargs):
        """
        Returns the value
        :param args:
        :param kwargs:
        :return:
        """
        typeCode = self.field().type()

        editor = self.widget()
        if isinstance(editor, QLineEdit):
            value = editor.text()
            dt64 = None
            try:
                dt64 = datetime64(value)
            except Exception:
                pass

            if isinstance(dt64, np.datetime64) and np.isfinite(dt64):
                if typeCode == QVariant.DateTime:
                    return QDateTime(dt64.astype(object))
                elif typeCode == QVariant.Date:
                    return QDate(dt64.astype(object))
            if typeCode == QVariant.String:
                return value

        elif isinstance(editor, QgsDateTimeEdit):
            if typeCode == QVariant.DateTime:
                return editor.dateTime()
            elif typeCode == QVariant.Date:
                return editor.date()
            elif typeCode == QVariant.String:
                return str(editor.dateTime())

        elif isinstance(editor, (QgsSpinBox, QgsDoubleSpinBox)):
            return editor.value()
        else:
            s = ""
        return self.defaultValue()

    def setEnabled(self, enabled: bool):
        editor = self.widget()
        if isinstance(editor, QWidget):
            editor.setEnabled(enabled)

    # def setFeature(self, feature:QgsFeature):
    #    s = ""

    def setValue(self, value):

        # if isinstance(self.mEditor, ClassificationSchemeComboBox):
        #    cs = self.mEditor.classificationScheme()
        #    if isinstance(cs, ClassificationScheme) and len(cs) > 0:
        #        i = cs.classIndexFromValue(value)
        #        self.mEditor.setCurrentIndex(max(i, 0))
        # elif isinstance(self.mEditor, QLineEdit):
        w = self.widget()

        if value in [None, QVariant()]:
            if isinstance(w, (QgsTimeEdit, QgsDateEdit, QgsDateTimeEdit)):
                w.setEmpty()
            elif isinstance(w, (QgsSpinBox, QgsDoubleSpinBox)):
                w.clear()
            elif isinstance(w, QLineEdit):
                w.clear()
            else:
                s = ""
        else:
            if isinstance(w, QgsTimeEdit):
                w.setTime(QTime(value))
            elif isinstance(w, QgsDateEdit):
                w.setDate(QDate(value))
            elif isinstance(w, QgsDateTimeEdit):
                w.setDateTime(QDateTime(value))
            elif isinstance(w, (QgsSpinBox, QgsDoubleSpinBox)):
                if w.maximum() <= value:
                    e = int(math.log10(value)) + 1
                    w.setMaximum(int(10 ** e))
                w.setClearValue(value)
                w.setValue(value)
            elif isinstance(w, QLineEdit):
                w.setText(str(value))
            else:
                s = ""


def createWidgetConf(labelType: LabelShortcutType,
                     group: str = None) -> Dict[str, str]:
    assert isinstance(labelType, LabelShortcutType)
    if group is None:
        group = ''
    group = str(group).strip()

    conf = {LabelConfigurationKey.LabelType: labelType.confValue()}
    if group != '':
        conf[LabelConfigurationKey.LabelGroup] = group
    return conf


def createWidgetSetup(labelType: LabelShortcutType,
                      group: str = None
                      ) -> QgsEditorWidgetSetup:
    conf = createWidgetConf(labelType, group)
    return QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, conf)


class LabelShortcutWidgetFactory(QgsEditorWidgetFactory):
    """
    A QgsEditorWidgetFactory to create widgets for EOTSV Quick Labeling
    """

    @staticmethod
    def instance():
        return QgsGui.editorWidgetRegistry().factory(EDITOR_WIDGET_REGISTRY_KEY)

    @staticmethod
    def createWidgetSetup(*args, **kwds) -> QgsEditorWidgetSetup:
        return createWidgetSetup(*args, **kwds)

    def __init__(self, name: str):

        super(LabelShortcutWidgetFactory, self).__init__(name)

        self.mLabelGroupModel: QStandardItemModel = QStandardItemModel()
        self.mLabelGroupModel.appendRow(QStandardItem(''))

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
        w.setLayerGroupModel(self.mLabelGroupModel)
        w.setConfig(layer.editorWidgetSetup(fieldIdx).config())
        return w

    def create(self, layer: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> LabelShortcutEditorWidgetWrapper:
        """
        Create a LabelShortcutEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: ClassificationSchemeEditorWidgetWrapper
        """
        w = LabelShortcutEditorWidgetWrapper(layer, fieldIdx, editor, parent)

        return w

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
        if isinstance(field, QgsField) and field.type() in \
                [QVariant.Double, QVariant.Int, QVariant.String, QVariant.Date, QVariant.DateTime]:
            return True
        return False


labelEditorWidgetFactory = None


def registerLabelShortcutEditorWidget():
    reg = QgsGui.editorWidgetRegistry()
    global labelEditorWidgetFactory
    if EDITOR_WIDGET_REGISTRY_KEY not in reg.factories().keys():
        labelEditorWidgetFactory = LabelShortcutWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, labelEditorWidgetFactory)
    else:
        labelEditorWidgetFactory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
