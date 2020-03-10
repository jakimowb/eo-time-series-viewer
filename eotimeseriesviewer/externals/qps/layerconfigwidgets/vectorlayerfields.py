import typing, pathlib, sys
from qgis.core import QgsRasterLayer, QgsRasterRenderer
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsRasterBandComboBox
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt import Qt
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import QIcon
from ..utils import loadUi
import numpy as np
from .core import QpsMapLayerConfigWidget
from ..layerproperties import AddAttributeDialog


class LayerFieldsTableModel(QgsFieldModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        assert isinstance(self, QAbstractItemModel)
        self.cnId = 'Id'
        self.cnName = 'Name'
        self.cnAlias = 'Alias'
        self.cnType = 'Type'
        self.cnTypeName = 'Type name'
        self.cnLength = 'Length'
        self.cnPrecision = 'Precision'
        self.cnComment = 'Comment'
        self.cnWMS = 'WMS'
        self.cnWFS = 'WFS'

        self.mColumnNames = [self.cnId, self.cnName, self.cnAlias, self.cnType, self.cnTypeName, self.cnLength, self.cnPrecision, self.cnComment, self.cnWMS, self.cnWFS]

    def columnNames(self):
        return self.mColumnNames[:]

    def columnCount(self, parent):
        return len(self.mColumnNames)

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        """
        Returns header data
        :param col: int
        :param orientation: Qt.Horizontal | Qt.Vertical
        :param role:
        :return: value
        """
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def columnCount(self, parent:QModelIndex):
        return len(self.mColumnNames)

    def data(self, index:QModelIndex, role:int):
        if not index.isValid():
            return None

        if not isinstance(self.layer(), QgsMapLayer):
            return None

        cn = self.mColumnNames[index.column()]
        field = self.layer().fields().at(index.row())
        if not isinstance(field, QgsField):
            return None
        if role == Qt.DisplayRole:
            if cn == self.cnId:
                return index.row()
            if cn == self.cnName:
                return field.name()
            if cn == self.cnAlias:
                return field.alias()
            if cn == self.cnType:
                return QVariant.typeToName(field.type())
            if cn == self.cnTypeName:
                return field.typeName()
            if cn == self.cnLength:
                return field.length()
            if cn == self.cnPrecision:
                return field.precision()
            if cn == self.cnComment:
                return field.comment()
            if cn == self.cnWMS:
                return None
            if cn == self.cnWFS:
                return None
        if role in [QgsFieldModel.FieldNameRole ,
                    QgsFieldModel.FieldIndexRole,
                    QgsFieldModel.ExpressionRole,
                    QgsFieldModel.IsExpressionRole,
                    QgsFieldModel.ExpressionValidityRole,
                    QgsFieldModel.FieldTypeRole,
                    QgsFieldModel.FieldOriginRole,
                    QgsFieldModel.IsEmptyRole,
                    QgsFieldModel.EditorWidgetType,
                    QgsFieldModel.JoinedFieldIsEditable
                    ]:
            return super().data(index, role)



class LayerFieldsListModel(QgsFieldModel):
    """
    A model to show the QgsFields of an QgsVectorLayer as vertical list
    Inherits QgsFieldModel and allows to change the name of the 1st column.
    """
    def __init__(self, parent):
        """
        Constructor
        :param parent:
        """
        super(LayerFieldsListModel, self).__init__(parent)
        self.mColumnNames = ['Fields']

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        """
        Returns header data
        :param col: int
        :param orientation: Qt.Horizontal | Qt.Vertical
        :param role:
        :return: value
        """
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setHeaderData(self, col, orientation, value, role=Qt.EditRole):
        """
        Sets the header data.
        :param col: int
        :param orientation:
        :param value: any
        :param role:
        """
        result = False

        if role == Qt.EditRole:
            if orientation == Qt.Horizontal and col < len(self.mColumnNames) and isinstance(value, str):
                self.mColumnNames[col] = value
                result = True

        if result == True:
            self.headerDataChanged.emit(orientation, col, col)
        return result

class LayerAttributeFormConfigEditorWidget(QWidget):

    class ConfigInfo(QStandardItem):
        """
        Describes a QgsEditorWidgetFactory configuration.
        """
        def __init__(self, key:str, factory:QgsEditorWidgetFactory, configWidget:QgsEditorConfigWidget):
            super(LayerAttributeFormConfigEditorWidget.ConfigInfo, self).__init__()

            assert isinstance(key, str)
            assert isinstance(factory, QgsEditorWidgetFactory)
            assert isinstance(configWidget, QgsEditorConfigWidget)
            self.mKey = key
            self.mFactory = factory
            self.mConfigWidget = configWidget
            self.setText(factory.name())
            self.setToolTip(factory.name())
            self.mInitialConfig = dict(configWidget.config())


        def resetConfig(self):
            """
            Resets the widget to its initial values
            """
            self.mConfigWidget.setConfig(dict(self.mInitialConfig))

        def factoryKey(self)->str:
            """
            Returns the QgsEditorWidgetFactory key, e.g. "CheckBox"
            :return: str
            """
            return self.mKey

        def factoryName(self)->str:
            """
            Returns the QgsEditorWidgetFactory name, e.g. "Checkbox"
            :return: str
            """
            return self.factory().name()

        def config(self)->dict:
            """
            Returns the config dictionary
            :return: dict
            """
            return self.mConfigWidget.config()

        def configWidget(self)->QgsEditorConfigWidget:
            """
            Returns the QgsEditorConfigWidget
            :return: QgsEditorConfigWidget
            """
            return self.mConfigWidget

        def factory(self)->QgsEditorWidgetFactory:
            """
            Returns the QgsEditorWidgetFactory
            :return: QgsEditorWidgetFactory
            """
            return self.mFactory

        def editorWidgetSetup(self)->QgsEditorWidgetSetup:
            """
            Creates a QgsEditorWidgetSetup
            :return: QgsEditorWidgetSetup
            """
            return QgsEditorWidgetSetup(self.factoryKey(), self.config())


    sigChanged = pyqtSignal(object)

    def __init__(self, parent, layer:QgsVectorLayer, index:int):
        super(LayerAttributeFormConfigEditorWidget, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        assert isinstance(layer, QgsVectorLayer)
        assert isinstance(index, int)

        self.mLayer = layer
        self.mField = layer.fields().at(index)
        assert isinstance(self.mField, QgsField)
        self.mFieldIndex = index

        self.mFieldNameLabel = QLabel(parent)
        self.mFieldNameLabel.setText(self.mField.name())

        self.layout().addWidget(self.mFieldNameLabel)

        self.gbWidgetType = QgsCollapsibleGroupBox(self)
        self.gbWidgetType.setTitle('Widget Type')
        self.gbWidgetType.setLayout(QVBoxLayout())
        self.cbWidgetType = QComboBox(self.gbWidgetType)

        self.stackedWidget = QStackedWidget(self.gbWidgetType)
        self.gbWidgetType.layout().addWidget(self.cbWidgetType)
        self.gbWidgetType.layout().addWidget(self.stackedWidget)

        currentSetup = self.mLayer.editorWidgetSetup(self.mFieldIndex)

        refkey = currentSetup.type()
        if refkey == '':
            refkey = QgsGui.editorWidgetRegistry().findBest(self.mLayer, self.mField.name()).type()

        self.mItemModel = QStandardItemModel(parent=self.cbWidgetType)

        iCurrent = -1
        i = 0
        factories = QgsGui.editorWidgetRegistry().factories()
        for key, fac in factories.items():
            assert isinstance(key, str)
            assert isinstance(fac, QgsEditorWidgetFactory)
            score = fac.fieldScore(self.mLayer, self.mFieldIndex)
            configWidget = fac.configWidget(self.mLayer, self.mFieldIndex, self.stackedWidget)

            if isinstance(configWidget, QgsEditorConfigWidget):
                configWidget.changed.connect(lambda: self.sigChanged.emit(self))
                self.stackedWidget.addWidget(configWidget)
                confItem = LayerAttributeFormConfigEditorWidget.ConfigInfo(key, fac, configWidget)
                if key == refkey:
                    iCurrent = i
                confItem.setEnabled(score > 0)
                confItem.setData(self, role=Qt.UserRole)
                self.mItemModel.appendRow(confItem)

                i += 1

        self.cbWidgetType.setModel(self.mItemModel)
        self.cbWidgetType.currentIndexChanged.connect(self.updateConfigWidget)

        self.layout().addWidget(self.gbWidgetType)
        self.layout().addStretch()
        self.cbWidgetType.setCurrentIndex(iCurrent)


        conf = self.currentFieldConfig()
        self.mInitialFactoryKey = None
        self.mInitialConf = None
        if isinstance(conf, LayerAttributeFormConfigEditorWidget.ConfigInfo):
            self.mInitialFactoryKey = conf.factoryKey()
            self.mInitialConf = conf.config()



    def setFactory(self, factoryKey:str):
        """
        Shows the QgsEditorConfigWidget of QgsEditorWidgetFactory `factoryKey`
        :param factoryKey: str
        """
        for i in range(self.mItemModel.rowCount()):
            confItem = self.mItemModel.item(i)
            assert isinstance(confItem, LayerAttributeFormConfigEditorWidget.ConfigInfo)
            if confItem.factoryKey() == factoryKey:
                self.cbWidgetType.setCurrentIndex(i)
                break


    def changed(self)->bool:
        """
        Returns True if the QgsEditorWidgetFactory or its configuration has been changed
        :return: bool
        """

        recentConfigInfo = self.currentFieldConfig()
        if isinstance(recentConfigInfo, LayerAttributeFormConfigEditorWidget.ConfigInfo):
            if self.mInitialFactoryKey != recentConfigInfo.factoryKey():
                return True
            elif self.mInitialConf != recentConfigInfo.config():
                return True

        return False

    def apply(self):
        """
        Applies the
        :return:
        """
        if self.changed():
            configInfo = self.currentFieldConfig()
            self.mInitialConf = configInfo.config()
            self.mInitialFactoryKey = configInfo.factoryKey()
            setup = QgsEditorWidgetSetup(self.mInitialFactoryKey, self.mInitialConf)
            self.mLayer.setEditorWidgetSetup(self.mFieldIndex, setup)

    def reset(self):
        """
        Resets the widget to its initial status
        """
        if self.changed():

            self.setFactory(self.mInitialFactoryKey)
            self.currentEditorConfigWidget().setConfig(self.mInitialConf)

    def currentFieldConfig(self)->ConfigInfo:
        i = self.cbWidgetType.currentIndex()
        return self.mItemModel.item(i)

    def currentEditorConfigWidget(self)->QgsEditorConfigWidget:
        return self.currentFieldConfig().configWidget()

    def updateConfigWidget(self, index):
        self.stackedWidget.setCurrentIndex(index)
        fieldConfig = self.currentFieldConfig()
        if isinstance(fieldConfig, LayerAttributeFormConfigEditorWidget.ConfigInfo):

            self.sigChanged.emit(self)


class LayerAttributeFormConfigWidget(QpsMapLayerConfigWidget):
    """
    A widget to set QgsVectorLayer field settings
    """
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        from .core import configWidgetUi
        loadUi(configWidgetUi('layerattributeformconfigwidget.ui'), self)

        assert isinstance(self.mapLayer(), QgsVectorLayer)
        self.scrollArea.resizeEvent = self.onScrollAreaResize
        self.mFieldModel = LayerFieldsListModel(self)
        self.mFieldModel.setLayer(self.mapLayer())
        self.treeView.setModel(self.mFieldModel)
        self.treeView.selectionModel().currentRowChanged.connect(self.onSelectedFieldChanged)
        self.updateFieldWidgets()


    def menuButtonMenu(self) ->QMenu:
        m = QMenu('Reset')
        a = m.addAction('Reset')
        a.triggered.connect(self.onReset)
        return m

    def onSelectedFieldChanged(self, index1:QModelIndex, index2:QModelIndex):
        """
        Shows the widget for the selected QgsField
        :param index1:
        :param index2:
        """
        if isinstance(index1, QModelIndex) and index1.isValid():
            r = index1.row()
            if r < 0 or r >= self.stackedWidget.count():
                s = ""
            self.stackedWidget.setCurrentIndex(r)

    def onScrollAreaResize(self, resizeEvent:QResizeEvent):
        """
        Forces the stackedWidget's width to fit into the scrollAreas viewport
        :param resizeEvent: QResizeEvent
        """
        assert isinstance(resizeEvent, QResizeEvent)
        self.stackedWidget.setMaximumWidth(resizeEvent.size().width())
        s =""

    def onReset(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, LayerAttributeFormConfigEditorWidget)
            w.reset()
        self.onSettingsChanged()

    def apply(self):
        """
        Applies all changes to the QgsVectorLayer
        :return:
        """

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, LayerAttributeFormConfigEditorWidget)
            w.apply()
        self.onSettingsChanged()



    def updateFieldWidgets(self):
        """
        Empties the stackedWidget and populates it with a FieldConfigEditor
        for each QgsVectorLayer field.
        """
        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)
        i = sw.count() - 1
        while i >= 0:
            w = sw.widget(i)
            w.setParent(None)
            i -= 1

        lyr = self.mapLayer()
        if isinstance(lyr, QgsVectorLayer):
            for i in range(lyr.fields().count()):
                w = LayerAttributeFormConfigEditorWidget(sw, lyr, i)
                w.sigChanged.connect(self.onSettingsChanged)
                sw.addWidget(w)

        self.onSettingsChanged()

    def onSettingsChanged(self):
        """
        Enables/disables buttons
        :return:
        """
        b = False
        for i in range(self.stackedWidget.count()):
            w = self.stackedWidget.widget(i)
            assert isinstance(w, LayerAttributeFormConfigEditorWidget)
            if w.changed():
                b = True
                break


class LayerAttributeFormConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Attributes Form', icon=QIcon(':/images/themes/default/mActionFormView.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return LayerAttributeFormConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer)->bool:
        return isinstance(layer, QgsVectorLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

class LayerFieldsConfigWidget(QpsMapLayerConfigWidget):
    """
    A widget to edit the fields of a QgsVectorLayer
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        from .core import configWidgetUi
        loadUi(configWidgetUi('layerfieldsconfigwidget.ui'), self)

        lyr = self.mapLayer()
        self.mFieldModel = LayerFieldsTableModel()
        self.mFieldModel.setLayer(lyr)

        self.mProxyModel = QSortFilterProxyModel()
        self.mProxyModel.setSourceModel(self.mFieldModel)
        assert isinstance(self.tableView, QTableView)
        self.tableView.setModel(self.mProxyModel)
        self.tableView.selectionModel().selectionChanged.connect(self.validate)
        self.btnAddField.setDefaultAction(self.actionAddField)
        self.btnRemoveField.setDefaultAction(self.actionRemoveField)
        self.btnToggleEditing.setDefaultAction(self.actionToggleEditing)
        self.btnFieldCalculator.setDefaultAction(self.actionFieldCalculator)

        self.actionAddField.triggered.connect(self.onAddField)
        self.actionRemoveField.triggered.connect(self.onRemoveField)
        self.actionToggleEditing.toggled.connect(self.onToggleEditing)

        self.actionFieldCalculator.setEnabled(False)
        self.actionFieldCalculator.setVisible(False)


        self.validate()

        lyr.editingStarted.connect(self.validate)
        lyr.editingStopped.connect(self.validate)

    def validate(self, *args):

        bEdit = isinstance(self.mapLayer(), QgsVectorLayer) and self.mapLayer().isEditable()
        bSelected = len(self.tableView.selectionModel().selectedRows()) > 0


        self.actionAddField.setEnabled(bEdit)
        self.actionRemoveField.setEnabled(bEdit and bSelected)
        self.actionToggleEditing.setChecked(bEdit)


    def onAddField(self):
        lyr = self.mapLayer()
        if isinstance(lyr, QgsVectorLayer) and lyr.isEditable():
            d = AddAttributeDialog(lyr)
            d.exec_()
            if d.result() == QDialog.Accepted:
                field = d.field()
                lyr.addAttribute(field)

    def onToggleEditing(self, b):

        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return

        isEditable = lyr.isEditable()
        if isEditable == b:
            return

        errors = None
        if b:
            lyr.startEditing()
        else:
            if lyr.isModified():
                result = QMessageBox.question(self, 'Leaving edit mode', 'Save changes?',
                                          buttons=QMessageBox.No | QMessageBox.Yes, defaultButton=QMessageBox.Yes)
                if result == QMessageBox.Yes:
                    if not lyr.commitChanges():
                        errors = lyr.commitErrors()
                else:
                    lyr.rollBack()
            else:
                lyr.commitChanges()
        if errors:
            print(str(errors), file=sys.stderr)

    def onRemoveField(self):

        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return
        indices = [self.mProxyModel.mapToSource(idx).data(QgsFieldModel.FieldIndexRole) for idx in self.tableView.selectionModel().selectedRows()]

        if not lyr.deleteAttributes(indices):
            errors = lyr.errors()
        self.validate()

    def apply(self):

        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return
        if lyr.isEditable():
            lyr.commitChanges()
            lyr.startEditing()

    def syncToLayer(self):
        self.mFieldModel.setLayer(self.mapLayer())


class LayerFieldsConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Fields', icon=QIcon(':/images/themes/default/mSourceFields.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return LayerFieldsConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer)->bool:
        return isinstance(layer, QgsVectorLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


