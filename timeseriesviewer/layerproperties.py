
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


class LabelFieldModel(QgsFieldModel):

    def __init__(self, parent):
        super(LabelFieldModel, self).__init__(parent)
        self.mColumnNames = ['Fields', 'Type']


    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None



class FieldConfigEditorWidget(QWidget):

    class ConfigInfo(QStandardItem):
        """
        Describes a QgsEditorWidgetFactory configuration.
        """
        def __init__(self, key:str, factory:QgsEditorWidgetFactory, configWidget:QgsEditorConfigWidget):
            super(FieldConfigEditorWidget.ConfigInfo, self).__init__()

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
        super(FieldConfigEditorWidget, self).__init__(parent)

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
        self.mInitialConf = currentSetup.config()
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
                configWidget.changed.connect(lambda :self.sigChanged.emit(self))
                self.stackedWidget.addWidget(configWidget)
                confItem = FieldConfigEditorWidget.ConfigInfo(key, fac, configWidget)
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
        self.mInitialFactoryKey = conf.factoryKey()
        self.mInitialConf = conf.config()



    def setFactory(self, factoryKey:str):
        """
        Shows the QgsEditorConfigWidget of QgsEditorWidgetFactory `factoryKey`
        :param factoryKey: str
        """
        for i in range(self.mItemModel.rowCount()):
            confItem = self.mItemModel.item(i)
            assert isinstance(confItem, FieldConfigEditorWidget.ConfigInfo)
            if confItem.factoryKey() == factoryKey:
                self.cbWidgetType.setCurrentIndex(i)
                break


    def changed(self)->bool:
        """
        Returns True if the QgsEditorWidgetFactory or its configuration has been changed
        :return: bool
        """
        w = self.currentEditorConfigWidget()
        assert isinstance(w, QgsEditorConfigWidget)

        recentConfigInfo = self.currentFieldConfig()

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
        assert isinstance(fieldConfig, FieldConfigEditorWidget.ConfigInfo)

        self.sigChanged.emit(self)


class LayerFieldConfigEditorWidget(QWidget, loadUI('layerfieldconfigeditorwidget.ui')):
    """
    A widget to set QgsVetorLayer field settings
    """
    def __init__(self, parent, *args, **kwds):
        super(LayerFieldConfigEditorWidget, self).__init__(parent,  *args, **kwds)
        self.setupUi(self)

        self.mFieldModel = LabelFieldModel(self)
        self.treeView.setModel(self.mFieldModel)
        self.treeView.selectionModel().currentRowChanged.connect(self.onSelectionChanged)
        self.btnApply = self.buttonBox.button(QDialogButtonBox.Apply)
        self.btnReset = self.buttonBox.button(QDialogButtonBox.Reset)
        self.btnApply.clicked.connect(self.onApply)
        self.btnReset.clicked.connect(self.onReset)

    def onSelectionChanged(self, current:QModelIndex, previous:QModelIndex):
        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)
        sw.setCurrentWidget(sw.widget(current.row()))
        s = ""
        pass

    def onReset(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.reset()
        self.onSettingsChanged()

    def onApply(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.apply()
        self.onSettingsChanged()


    def setLayer(self, layer:QgsVectorLayer):
        """
        :param layer:
        """
        self.mFieldModel.setLayer(layer)
        self.updateFieldWidgets()

    def updateFieldWidgets(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)
        while sw.count() > 0:
            sw.removeWidget(sw.widget(0))

        lyr = self.layer()
        if isinstance(lyr, QgsVectorLayer):
            for i in range(lyr.fields().count()):
                w = FieldConfigEditorWidget(sw, lyr, i)
                w.sigChanged.connect(self.onSettingsChanged)
                sw.addWidget(w)

        self.onSettingsChanged()



    def onSettingsChanged(self):

        b = False
        for i in range(self.stackedWidget.count()):
            w = self.stackedWidget.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            if w.changed():
                b = True
                break


        self.btnReset.setEnabled(b)
        self.btnApply.setEnabled(b)


    def layer(self)->QgsVectorLayer:
        """
        Returns the current QgsVectorLayer
        :return:
        """
        return self.mFieldModel.layer()

