from typing import List

from qgis.PyQt.QtCore import pyqtSignal, QAbstractTableModel, QDateTime, QModelIndex, Qt, QVariant
from qgis.core import QgsEditorWidgetSetup, QgsFeature, QgsField, QgsFields, QgsVectorLayer
from qgis.PyQt.QtGui import QIcon, QKeySequence
from qgis.PyQt.QtWidgets import QAction, QComboBox, QMenu, QStyledItemDelegate, QTableView, QToolBar, QToolButton
from qgis.gui import QgsAttributeTableModel, QgsEditorWidgetRegistry, QgsGui

from eotimeseriesviewer.labeling.editorconfig import LabelShortcutType
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget, showLayerPropertiesDialog
from eotimeseriesviewer.qgispluginsupport.qps.unitmodel import datetime64
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent, SpatialPoint
from eotimeseriesviewer.utils import gotoFeature, GotoFeatureOptions


class QuickLabelAttributeTableWidget(AttributeTableWidget):
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
