
import sys, os, re, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal

from eotimeseriesviewer.externals.qps.layerproperties import *
from eotimeseriesviewer.utils import loadUI, qgisInstance
from eotimeseriesviewer.externals.qps.classification.classificationscheme \
    import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, ClassificationSchemeComboBox

from eotimeseriesviewer.timeseries import TimeSeriesDatum

#the QgsProject(s) and QgsMapLayerStore(s) to search for QgsVectorLayers
MAP_LAYER_STORES = [QgsProject.instance()]

CONFKEY_CLASSIFICATIONSCHEME = 'classificationScheme'
CONFKEY_LABELTYPE = 'labelType'

class LabelShortcutType(enum.Enum):
    """Enumeration for shortcuts to be derived from a TimeSeriesDatum instance"""
    Off = 'No labeling (default)'
    Date = 'Date-Time'
    DOY = 'Day of Year (DOY)'
    Year = 'Year'
    DecimalYear = 'Decimal year'
    Sensor = 'Sensor name'
    Classification = 'Classificaton'

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
    result = []
    for o in options:
        if o not in result:
            result.append(o)
    return result


def layerClassSchemes(layer:QgsVectorLayer)->list:
    assert isinstance(layer, QgsVectorLayer)
    schemes = []
    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            cs = setup.config().get(CONFKEY_CLASSIFICATIONSCHEME)
            if isinstance(cs, ClassificationScheme):
                schemes.append(cs)
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
    Returns a list of all known QgsVectorLayers with at least one LabelShortcutEditWidget
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


def applyShortcuts(vectorLayer:QgsVectorLayer, tsd:TimeSeriesDatum, classInfos:dict=None):
    """
    Labels selected features with information related to TimeSeriesDatum tsd, according to
    the settings specified in this model.
    :param tsd: TimeSeriesDatum
    :param classInfos:
    """
    assert isinstance(tsd, TimeSeriesDatum)
    assert isinstance(vectorLayer, QgsVectorLayer)
    vectorLayer.beginEditCommand('Set quick labels {}'.format(tsd.date()))

    #Lookup-Table for classiicationSchemes
    LUT_Classifications = dict()
    for i in range(vectorLayer.fields().count()):
        field = vectorLayer.fields().at(i)
        setup = vectorLayer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            conf = setup.config()
            labelType = conf.get(CONFKEY_LABELTYPE)
            classScheme = conf.get(CONFKEY_CLASSIFICATIONSCHEME)
            if labelType == LabelShortcutType.Classification and isinstance(classScheme, ClassificationScheme):
                LUT_Classifications[i] = classScheme
                LUT_Classifications[classScheme.name()] = classScheme
                LUT_Classifications[field.name()] = classScheme

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
                    fieldClassScheme = conf.get(CONFKEY_CLASSIFICATIONSCHEME)
                    if isinstance(fieldClassScheme, ClassificationScheme) and isinstance(classInfos, dict):
                        for ciKey, classInfo in classInfos.items():
                            classScheme = LUT_Classifications.get(ciKey)
                            if classScheme == fieldClassScheme and classInfo in fieldClassScheme:
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

        vectorLayer.endEditCommand()


    pass



class LabelAttributeTableModel(QAbstractTableModel):

    def __init__(self, parent=None, *args):

        super(LabelAttributeTableModel, self).__init__()

        self.cnField = 'Field'
        self.cnFieldType = 'Type'
        self.cnLabel = 'Label shortcut'
        self.mColumnNames = [self.cnField, self.cnFieldType, self.cnLabel]
        #self.mLabelTypes = dict()
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
                #self.mLabelTypes[field.name()] = LabelShortcutType.Off

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


    def index2editorSetup(self, index:QModelIndex):
        if index.isValid() and isinstance(self.mVectorLayer, QgsVectorLayer):
            return self.mVectorLayer.editorWidgetSetup(index.row())
        else:
            return None


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
                setup = QgsEditorWidgetSetup(value,{})
                self.mVectorLayer.setEditorWidgetSetup(index.row(), setup)

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




class LabelingDock(QgsDockWidget, loadUI('labelingdock.ui')):

    sigVectorLayerChanged = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)

    def __init__(self, parent=None, canvas=None):
        super(LabelingDock, self).__init__(parent)
        self.setupUi(self)
        assert isinstance(self.mVectorLayerComboBox, QgsMapLayerComboBox)

        self.mVectorLayerComboBox.setAllowEmptyLayer(True)
        allowed = ['DB2', 'WFS', 'arcgisfeatureserver', 'delimitedtext', 'memory', 'mssql', 'ogr', 'oracle', 'ows',
                   'postgres', 'spatialite', 'virtual']

        excluded = [k for k in QgsProviderRegistry.instance().providerList() if k not in allowed]
        self.mVectorLayerComboBox.setExcludedProviders(excluded)
        self.mVectorLayerComboBox.currentIndexChanged.connect(self.onVectorLayerChanged)

        self.mDualView = None

        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas(self)
            canvas.setVisible(False)

        self.mCanvas = canvas

        self.initActions()
        self.onVectorLayerChanged()

    def canvas(self)->QgsMapCanvas:
        """
        Returns the internal map canvas
        :return: QgsMapCanvas
        """
        return self.mCanvas

    def onCheckApply(self):
        """
        Checks if any QgsVectorLayer settings have changed and enables/disable buttons
        """
        btnApply = self.buttonBoxEditorWidget.button(QDialogButtonBox.Apply)
        btnReset = self.buttonBoxEditorWidget.button(QDialogButtonBox.Reset)
        changed = False
        for w in self.stackedFieldConfigs.findChildren(FieldConfigEditorWidget):
            assert isinstance(w, FieldConfigEditorWidget)
            if w.changed():
                changed = True
                break

        btnApply.setEnabled(changed)
        btnReset.setEnabled(not changed)

    def onReset(self):
        """
        Reloads the QgsVectorLayer and all its current settings
        """
        self.onVectorLayerChanged()

    def onApply(self):
        """
        Stores changes settings to current QgsVectorLayer
        """
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):
            for w in self.stackedFieldConfigs.findChildren(FieldConfigEditorWidget):
                assert isinstance(w, FieldConfigEditorWidget)
                if w.changed():
                    config = w.currentFieldConfig()
                    lyr.setEditFormConfig(config.index(), config.editorWidgetSetup())
        self.onVectorLayerChanged()

    def isModified(self)->bool:
        return isinstance(self.currentVectorSource(), QgsVectorLayer) and self.currentVectorSource().isModified()

    def onVectorLayerChanged(self):
        lyr = self.currentVectorSource()
        # remove old QgsDualView
        if isinstance(self.mDualView, QgsDualView):
            self.mDualView.setParent(None)
            self.mDualView = None

        i = self.stackedWidget.count() - 1
        while i >= 0:
            self.stackedWidget.widget(i).setParent(None)
            i -= 1

        self.mCanvas.setLayers([])


        assert isinstance(self.stackedWidget, QStackedWidget)

        # add a config widget for each QgsField
        if isinstance(lyr, QgsVectorLayer):
            lyr.editingStarted.connect(lambda: self.mActionToggleEditing.setChecked(True))
            lyr.editingStopped.connect(lambda: self.mActionToggleEditing.setChecked(False))
            lyr.allowCommitChanged.connect(self.updateActions)

            self.mCanvas.setLayers([lyr])

            if not self.mCanvas.mapSettings().destinationCrs().isValid():
                self.mCanvas.setDestinationCrs(lyr.crs())
            if self.mCanvas.extent().width() == 0:
                self.mCanvas.setExtent(lyr.extent())

            self.mDualView = QgsDualView(self)

            # change selected row color: keep color also when attribute table looses focus
            pal = self.mDualView.tableView().palette()
            cSelected = pal.color(QPalette.Active, QPalette.Highlight)
            pal.setColor(QPalette.Inactive, QPalette.Highlight, cSelected)
            self.mDualView.tableView().setPalette(pal)

            self.stackedWidget.addWidget(self.mDualView)
            self.mDualView.init(lyr, self.mCanvas)  # , context=self.mAttributeEditorContext)
            self.mDualView.setView(QgsDualView.AttributeTable)
            self.mDualView.setAttributeTableConfig(lyr.attributeTableConfig())


        self.updateActions()
        self.sigVectorLayerChanged.emit()

    def updateActions(self, *args):
        if isinstance(self.currentVectorSource(), QgsVectorLayer):
            self.mActionToggleEditing.setEnabled(True)

            b = self.currentVectorSource().isEditable()
            self.mActionToggleEditing.setChecked(b)

            self.mActionAddFeature.setEnabled(b)

            gType = self.currentVectorSource().geometryType()
            if gType == QgsWkbTypes.PointGeometry:
                self.mActionAddFeature.setIcon(QIcon(':/images/themes/default/mActionCapturePoint.svg'))
            elif gType == QgsWkbTypes.LineGeometry:
                self.mActionAddFeature.setIcon(QIcon(':/images/themes/default/mActionCaptureLine.svg'))
            elif gType == QgsWkbTypes.PolygonGeometry:
                self.mActionAddFeature.setIcon(QIcon(':/images/themes/default/mActionCapturePolygon.svg'))
            else:
                # unknown geometry type?
                self.mActionAddFeature.setIcon(QIcon(':/images/themes/default/mActionCapturePolygon.svg'))

            buffer = self.currentVectorSource().editBuffer()
            b2 = b and isinstance(buffer, QgsVectorLayerEditBuffer)
            self.mActionCancelEdits.setEnabled(b2)
            self.mActionSaveEdits.setEnabled(b2)

            self.mActionSelectAll.setEnabled(True)
            self.mActionInvertSelection.setEnabled(True)
            self.mActionRemoveSelection.setEnabled(True)
            self.mActionPanMapToSelectedRows.setEnabled(True)
            self.mActionZoomMapToSelectedRows.setEnabled(True)

        else:



            self.mActionToggleEditing.setEnabled(False)
            self.mActionSaveEdits.setEnabled(False)
            self.mActionCancelEdits.setEnabled(False)
            self.mActionAddFeature.setEnabled(False)

            self.mActionSelectAll.setEnabled(False)
            self.mActionInvertSelection.setEnabled(False)
            self.mActionRemoveSelection.setEnabled(False)
            self.mActionPanMapToSelectedRows.setEnabled(False)
            self.mActionZoomMapToSelectedRows.setEnabled(False)

    def actionAddFeature(self)->QAction:
        return self.mActionAddFeature

    def actionSaveEdits(self)->QAction:
        return self.mActionSaveEdits

    def actionToggleEditing(self)->QAction:
        return self.mActionToggleEditing

    def onToggleEditing(self, b: bool):
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):

            if b:
                lyr.startEditing()
            else:
                if lyr.isModified():
                    if QMessageBox.question(self, '{}'.format(lyr.name()), 'Save changes?') == QMessageBox.Ok:
                        lyr.commitChanges()
                    else:
                        lyr.rollBack()
                else:
                    lyr.commitChanges()


        self.updateActions()

    def cancelEdits(self, *args):
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):
            lyr.rollBack()

    def saveEdits(self, *args):
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):
            b = lyr.isEditable()
            lyr.commitChanges()
            if b:
                lyr.startEditing()


    def initActions(self):

        iface = qgisInstance()

        # if isinstance(iface, QgisInterface):
        # self.mActionAddFeature = iface.actionAddFeature()
        # self.mActionSaveEdits = iface.actionSaveEdits()
        # self.mActionCancelEdits = iface.actionCancelEdits()
        # self.mActionToggleEditing = iface.actionToggleEditing()
        # self.mActionAddOgrLayer = iface.actionAddOgrLayer()



        self.mActionToggleEditing.toggled.connect(self.onToggleEditing)
        self.mActionCancelEdits.triggered.connect(self.cancelEdits)
        self.mActionSaveEdits.triggered.connect(self.saveEdits)

        self.mActionSwitchToTableView.triggered.connect(self.showTableView)
        self.mActionShowLayerProperties.triggered.connect(self.showLayerProperties)
        self.mActionSwitchToFormView.triggered.connect(self.showFormView)

        self.mActionSelectAll.triggered.connect(self.selectAll)
        self.mActionInvertSelection.triggered.connect(self.invertSelection)
        self.mActionRemoveSelection.triggered.connect(self.removeSelection)
        self.mActionPanMapToSelectedRows.triggered.connect(self.panMapToSelectedRows)
        self.mActionZoomMapToSelectedRows.triggered.connect(self.zoomMapToSelectedRows)

        self.btnAddFeature.setDefaultAction(self.mActionAddFeature)
        self.btnSaveEdits.setDefaultAction(self.mActionSaveEdits)
        self.btnCancelEdits.setDefaultAction(self.mActionCancelEdits)
        self.btnToggleEditing.setDefaultAction(self.mActionToggleEditing)

        self.btnSelectAll.setDefaultAction(self.mActionSelectAll)
        self.btnInvertSelection.setDefaultAction(self.mActionInvertSelection)
        self.btnRemoveSelection.setDefaultAction(self.mActionRemoveSelection)
        self.btnPanMapToSelectedRows.setDefaultAction(self.mActionPanMapToSelectedRows)
        self.btnZoomMapToSelectedRows.setDefaultAction(self.mActionZoomMapToSelectedRows)

        self.btnAddOgrLayer.setDefaultAction(self.mActionAddOgrLayer)
        self.btnAddOgrLayer.setVisible(False)

        # bottom button bar
        self.btnAttributeView.setDefaultAction(self.mActionSwitchToTableView)
        self.btnShowLayerProperties.setDefaultAction(self.mActionShowLayerProperties)
        self.btnFormView.setDefaultAction(self.mActionSwitchToFormView)

    def selectAll(self):
        if isinstance(self.currentVectorSource(), QgsVectorLayer):
            self.currentVectorSource().selectAll()

    def invertSelection(self):
        if isinstance(self.currentVectorSource(), QgsVectorLayer):
            self.currentVectorSource().invertSelection()

    def removeSelection(self):
        if isinstance(self.currentVectorSource(), QgsVectorLayer):
            self.currentVectorSource().removeSelection()

    def panMapToSelectedRows(self):
        """
        Pan to the selected layer features
        Requires that external maps respond to sigMapCenterRequested
        """
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):
            crs = self.canvas().mapSettings().destinationCrs()
            center = SpatialPoint(lyr.crs(), lyr.boundingBoxOfSelected().center()).toCrs(crs)
            self.mCanvas.setCenter(center)
            self.sigMapCenterRequested.emit(center)

    def zoomMapToSelectedRows(self):
        """
        Zooms to the selected rows.
        Requires that external maps respond to sigMapExtentRequested
        """
        lyr = self.currentVectorSource()

        if isinstance(lyr, QgsVectorLayer):
            crs = self.canvas().mapSettings().destinationCrs()
            bbox = SpatialExtent(lyr.crs(), lyr.boundingBoxOfSelected()).toCrs(crs)
            self.mCanvas.setExtent(bbox)
            self.sigMapExtentRequested.emit(bbox)

    def showTableView(self):
        """
        Call to show the QgsDualView Attribute Table
        """
        if isinstance(self.mDualView, QgsDualView):
            self.mDualView.setView(QgsDualView.AttributeTable)

    def showFormView(self):
        """
        Call to show the QgsDualView Attribute Editor
        """
        if isinstance(self.mDualView, QgsDualView):
            self.mDualView.setView(QgsDualView.AttributeEditor)

    def showLayerProperties(self):
        """
        Call to show the QgsVectorLayer field settings
        """
        from .externals.qps.layerproperties import showLayerPropertiesDialog
        lyr = self.currentVectorSource()
        if isinstance(lyr, QgsVectorLayer):
            showLayerPropertiesDialog(lyr, self.mCanvas, parent=self)



    def setCurrentVectorSource(self, layer:QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if layer not in QgsProject.instance().mapLayers().values():
            QgsProject.instance().addMapLayer(layer)

        cboxLayers = [self.mVectorLayerComboBox.layer(i) for i in range(self.mVectorLayerComboBox.count())]
        if layer in cboxLayers:
            self.mVectorLayerComboBox.setCurrentIndex(cboxLayers.index(layer))

    def currentVectorSource(self)->QgsVectorLayer:
        """
        Returns the current QgsVectorLayer
        :return: QgsVectorLayer
        """
        return self.mVectorLayerComboBox.currentLayer()





class LabelShortcutEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, parent:QWidget):

        super(LabelShortcutEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        #self.setupUi(self)

        self.setLayout(QVBoxLayout())

        self.mCBShortCutType = QComboBox(self)
        self.mClassWidget = ClassificationSchemeWidget(parent=self)
        self.layout().addWidget(self.mCBShortCutType)
        self.layout().addWidget(self.mClassWidget)
        self.layout().addStretch(0)
        assert isinstance(vl, QgsVectorLayer)
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        self.mAllowedShortCuts = shortcuts(field)
        for i, option in enumerate(self.mAllowedShortCuts):
            self.mCBShortCutType.addItem(option.value, option)

        self.mCBShortCutType.currentIndexChanged[int].connect(self.onIndexChanged)
        self.mCBShortCutType.currentIndexChanged[int].connect(lambda : self.onIndexChanged())

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
        #self.mCBShortCutType.currentIndexChanged.connect(self.onIndexChanged)
        self.mCBShortCutType.setCurrentIndex(i)


        classScheme = config.get(CONFKEY_CLASSIFICATIONSCHEME)
        if isinstance(classScheme, ClassificationScheme):
            self.mClassWidget.setClassificationScheme(classScheme)


    def onIndexChanged(self, *args):

        ltype = self.shortcutType()
        if ltype == LabelShortcutType.Classification:
            self.mClassWidget.setEnabled(True)
            self.mClassWidget.setVisible(True)
        else:
            self.mClassWidget.setEnabled(False)
            self.mClassWidget.setVisible(False)
        self.changed.emit()

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
        """
        Create the data input widget
        :param parent: QWidget
        :return: ClassificationSchemeComboBox | default widget
        """
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
        """
        Returns True if a valid editor widget exists
        :param args:
        :param kwargs:
        :return: bool
        """
        return isinstance(self.mEditor, (ClassificationSchemeComboBox, QLineEdit))

    def value(self, *args, **kwargs):
        """
        Reuturns the value
        :param args:
        :param kwargs:
        :return:
        """
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
                return txt

            return self.mLineEdit.text()

        return self.defaultValue()


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
            if value in [QVariant(), None]:
                self.mEditor.setText(None)
            else:
                self.mEditor.setText(str(value))


class LabelShortcutWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name:str):

        super(LabelShortcutWidgetFactory, self).__init__(name)

        self.mConfigurations = {}


    def name(self)->str:
        return 'EOTSV Label Shortcut'

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
        if field.type() in [QVariant.String, QVariant.Int]:
            return 5
        else:
            return 0 # no support

    def supportsField(self, vl:QgsVectorLayer, idx:int)->True:
        """
        :param vl: vectorlayers
        :param idx:
        :return: bool
        """
        field = vl.fields().at(idx)
        if isinstance(field, QgsField) and field.type() in [QVariant.Int, QVariant.String]:
            return True
        return False




EDITOR_WIDGET_REGISTRY_KEY = 'EOTSV_Labeling'
labelEditorWidgetFactory = None
def registerLabelShortcutEditorWidget():
    reg = QgsGui.editorWidgetRegistry()
    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        labelEditorWidgetFactory = LabelShortcutWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, labelEditorWidgetFactory)
    else:
        labelEditorWidgetFactory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]