import typing, pathlib, sys, re
from qgis.core import QgsRasterLayer, QgsRasterRenderer
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsRasterBandComboBox
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from ..utils import loadUi, gdalDataset, ogrDataSource
import numpy as np
from .core import QpsMapLayerConfigWidget
from ..classification.classificationscheme import ClassificationScheme, ClassificationSchemeWidget, ClassInfo
from osgeo import gdal, ogr

TYPE_LOOKUP = {
    ':STATISTICS_MAXIMUM': float,
    ':STATISTICS_MEAN': float,
    ':STATISTICS_MINIMUM': float,
    ':STATISTICS_STDDEV': float,
    ':STATISTICS_VALID_PERCENT': float,

               }

PROTECTED = [
    'IMAGE_STRUCTURE:INTERLEAVE',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_NAME',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_DESC'
    ':AREA_OR_POINT'
]

class GDALMetadataItem(object):
    """
    A light-weight object to describe a GDAL/OGR metadata item
    """
    def __init__(self, major_object: str, domain: str, key: str, value: str):
        self.major_object: str = major_object
        self.domain: str = domain
        self.key: str = key
        self.value: str = value
        self.initialValue: str = value

    def editorValue(self):
        """
        Converts the value string into a numeric/other type, if specified in TYPE_LOOKUP
        :return: any
        """
        t = TYPE_LOOKUP.get(self.keyDK())
        if t:
            return t(self.value)
        else:
            self.value

    def setEditorValue(self, value):
        t = TYPE_LOOKUP.get(self.keyDK())
        if t:
            self.value = str(t(value))
        else:
            self.value = str(value)

    def isModified(self) -> bool:
        """
        Returns True if the MDItems' value was modified
        :return: bool
        """
        return self.initialValue != self.value

    def keyDK(self) -> str:
        return '{}:{}'.format(self.domain, self.key)

    def keyMDK(self) -> str:
        return '{}:'.format(self.major_object) + self.keyDK()


class GDALMetadataModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super(GDALMetadataModel, self).__init__(parent)

        self.mLayer: QgsMapLayer = None

        self.cnItem = 'Item'
        self.cnDomain = 'Domain'
        self.cnKey = 'Key'
        self.cnValue = 'Value(s)'

        self._column_names = [self.cnItem, self.cnDomain, self.cnKey, self.cnValue]

        self._isEditable = False

        self._MDItems = []

    def setIsEditable(self, b: bool):
        assert isinstance(b, bool)
        self._isEditable = b

    def isEditable(self) -> bool:
        return self._isEditable

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._MDItems)

    def columnNames(self) -> typing.List[str]:
        """
        Returns the column names
        :return: list
        """
        return self._column_names

    def columnCount(self, parent=None, *args, **kwargs) -> int:
        """
        Returns the number of columns
        :param parent:
        :type parent:
        :param args:
        :type args:
        :param kwargs:
        :type kwargs:
        :return:
        :rtype:
        """

        return len(self._column_names)

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._column_names[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        md = self._MDItems[row]
        return self.createIndex(row, column, md)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        if index.column() == 3 and self.isEditable() and self.index2MDItem(index).keyDK() not in PROTECTED:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def setLayer(self, layer: QgsMapLayer):
        assert isinstance(layer, (QgsRasterLayer, QgsVectorLayer))
        self.mLayer = layer
        self.syncToLayer()

    def syncToLayer(self):
        self.beginResetModel()
        self._MDItems = self._read_maplayer()
        self.endResetModel()

    def applyToLayer(self):

        changed = [md for md in self._MDItems if md.isModified()]

        major_objects = dict()
        for md in changed:
            assert isinstance(md, GDALMetadataItem)
            if md.major_object not in major_objects.keys():
                major_objects[md.major_object] = dict()

            if md.domain not in major_objects[md.major_object].keys():
                major_objects[md.major_object] = []
            major_objects[md.major_object].append(md)



        lyr = self.mLayer
        if isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.dataProvider().name() == 'gdal':
            ds = gdal.Open(self.mLayer.source(), gdal.GA_Update)
            if isinstance(ds, gdal.Dataset):
                for objID, items in major_objects.items():
                    if objID == 'Dataset':
                        majorObject = ds
                    elif objID.startswith('Band'):
                        majorObject = ds.GetRasterBand(int(objID[4:]))

                    if isinstance(majorObject, gdal.MajorObject):
                        for item in items:
                            assert isinstance(item, GDALMetadataItem)
                            majorObject.SetMetadataItem(item.key, item.value, item.domain)
                ds.FlushCache()
                del ds

            #self.syncToLayer()

        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.dataProvider().name() == 'ogr':
            s = ""
            #self.syncToLayer()

        QTimer.singleShot(1000, self.syncToLayer)

    def index2MDItem(self, index: QModelIndex) -> GDALMetadataItem:
        """
        Converts a model index into the corresponding MDItem
        :param index:
        :type index:
        :return:
        :rtype:
        """
        return self._MDItems[index.row()]

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        item = self.index2MDItem(index)
        cname = self._column_names[index.column()]

        if role == Qt.DisplayRole:
            if cname == self.cnItem:
                return item.major_object
            elif cname == self.cnDomain:
                return item.domain
            elif cname == self.cnKey:
                return item.key
            elif cname == self.cnValue:
                return item.value

        if role == Qt.FontRole and cname == self.cnValue:
            if item.isModified():
                f = QFont()
                f.setItalic(True)
                return f

        if role == Qt.EditRole:
            if cname == self.cnValue:
                return item.value

        if role == Qt.UserRole:
            return item

        return None  # super(GDALMetadataModel, self).data(index, role)

    def setData(self, index: QModelIndex, value, role=None):

        item = self.index2MDItem(index)
        cname = self._column_names[index.column()]

        changed = False

        if role == Qt.EditRole:
            if cname == self.cnValue:
                try:
                    item.setEditorValue(value)
                    changed = True
                except:
                    pass
        if changed:
            self.dataChanged.emit(index, index, [role])
        return False

    def _read_majorobject(self, obj):
        assert isinstance(obj, (gdal.MajorObject, ogr.MajorObject))
        domains = obj.GetMetadataDomainList()
        if isinstance(domains, list):
            domains = list(set(domains))
            for domain in domains:
                for key, value in obj.GetMetadata(domain).items():
                    yield domain, key, value

    def _read_maplayer(self) -> list:
        items = []

        if not isinstance(self.mLayer, QgsMapLayer) or not self.mLayer.isValid():
            return items

        if isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.dataProvider().name() == 'gdal':
            ds = gdal.Open(self.mLayer.source())

            if isinstance(ds, gdal.Dataset):
                z = len(str(ds.RasterCount))
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataItem('Dataset', domain, key, value))
                for b in range(ds.RasterCount):
                    band = ds.GetRasterBand(b + 1)
                    assert isinstance(band, gdal.Band)
                    bandKey = 'Band{}'.format(str(b + 1).zfill(z))
                    for (domain, key, value) in self._read_majorobject(band):
                        items.append(GDALMetadataItem(bandKey, domain, key, value))

        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.dataProvider().name() == 'ogr':
            ds = ogr.Open(self.mLayer.source())
            if isinstance(ds, ogr.DataSource):
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataItem('Datasource', domain, key, value))
                z = len(str(ds.GetLayerCount()))
                for b in range(ds.GetLayerCount()):
                    lyr = ds.GetLayer(b)
                    assert isinstance(lyr, ogr.Layer)
                    lyrKey = 'Layer{}'.format(str(b + 1).zfill(z))
                    for (domain, key, value) in self._read_majorobject(lyr):
                        items.append(GDALMetadataItem(lyrKey, domain, key, value))

        return items


class GDALMetadataModelTableView(QTableView):
    """
    A QTreeView for the GDALMetadataModel
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Opens a context menue
        """
        index = self.indexAt(event.pos())
        if index.isValid():

            item = index.data(Qt.UserRole)
            value = item.value
            m = QMenu()
            a = m.addAction('Copy Value')
            a.triggered.connect(lambda *args, v=value: QApplication.clipboard().setText(v))

            if self.model().sourceModel().isEditable() and item.isModified():
                a = m.addAction('Reset')
                a.triggered.connect(lambda *args, v=item.initialValue: self.model().setData(index, v, Qt.EditRole))

            m.exec_(event.globalPos())


class GDALMetadataModelConfigWidget(QpsMapLayerConfigWidget):

    def __init__(self, layer: QgsMapLayer = None, canvas: QgsMapCanvas = None, parent: QWidget = None):
        """
        Constructor
        :param layer: QgsMapLayer
        :param canvas: QgsMapCanvas
        :param parent:
        :type parent:
        """

        if layer is None:
            layer = QgsRasterLayer()
        if canvas is None:
            canvas = QgsMapCanvas()

        super(GDALMetadataModelConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'gdalmetadatamodelwidget.ui'
        loadUi(pathUi, self)

        self.tbFilter: QLineEdit
        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)
        self._cs = None
        self.metadataModel = GDALMetadataModel()
        self.metadataProxyModel = QSortFilterProxyModel()
        self.metadataProxyModel.setSourceModel(self.metadataModel)
        self.metadataProxyModel.setFilterKeyColumn(-1)
        assert isinstance(self.tableView, GDALMetadataModelTableView)
        self.tableView.setModel(self.metadataProxyModel)
        self.tbFilter.textChanged.connect(self.updateFilter)
        self.optionMatchCase.changed.connect(self.updateFilter)
        self.optionRegex.changed.connect(self.updateFilter)
        assert isinstance(self.classificationSchemeWidget, ClassificationSchemeWidget)

        self.is_gdal = self.is_ogr = self.supportsGDALClassification = False
        self.classificationSchemeWidget.setIsEditable(False)

        self.setLayer(layer)

    def setLayer(self, layer:QgsMapLayer):
        """
        Set the maplayer
        :param layer:
        :type layer:
        :return:
        :rtype:
        """

        if not (isinstance(layer, QgsMapLayer) and layer.isValid()):
            self.is_gdal = self.is_ogr = self.supportsGDALClassification = False
        else:

            self.is_gdal = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
            self.is_ogr = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'

            if isinstance(layer, QgsRasterLayer):
                self.setPanelTitle('GDAL Metadata')
                self.setToolTip('Layer metadata according to the GDAL Metadata model')
                self.setWindowIcon(QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))
                self.supportsGDALClassification = \
                    self.is_gdal and layer.dataProvider().dataType(1) in \
                    [Qgis.Byte, Qgis.UInt16, Qgis.Int16, Qgis.UInt32, Qgis.Int32, Qgis.Int32]


            elif isinstance(layer, QgsVectorLayer):
                self.setPanelTitle('OGR Metadata')
                self.setToolTip('Layer metadata according to the OGR Metadata model')
                self.setWindowIcon(QIcon(':/qps/ui/icons/edit_ogr_metadata.svg'))

            self.syncToLayer()

    def apply(self):
        if self.is_gdal:
            ds = gdalDataset(self.mapLayer(), gdal.GA_Update)
            assert isinstance(ds, gdal.Dataset)

            if self.supportsGDALClassification:
                cs = self.classificationSchemeWidget.classificationScheme()
                if isinstance(cs, ClassificationScheme):
                    self.mapLayer().dataProvider().setEditable(True)
                    cs.saveToRaster(ds)
                    ds.FlushCache()
        self.metadataModel.applyToLayer()

    def syncToLayer(self):
        lyr = self.mapLayer()
        self.metadataModel.setLayer(lyr)
        if self.supportsGDALClassification:
            self._cs = ClassificationScheme.fromMapLayer(lyr)

        if isinstance(self._cs, ClassificationScheme) and len(self._cs) > 0:
            self.gbClassificationScheme.setVisible(True)
            self.classificationSchemeWidget.setClassificationScheme(self._cs)
        else:
            self.classificationSchemeWidget.classificationScheme().clear()
            self.gbClassificationScheme.setVisible(False)

    def updateFilter(self, *args):

        text = self.tbFilter.text()
        if self.optionMatchCase.isChecked():
            matchCase = Qt.CaseSensitive
        else:
            matchCase = Qt.CaseInsensitive

        if self.optionRegex.isChecked():
            syntax = QRegExp.RegExp
        else:
            syntax = QRegExp.Wildcard
        rx = QRegExp(text, cs=matchCase, syntax=syntax)
        if rx.isValid():
            self.metadataProxyModel.setFilterRegExp(rx)
        else:
            self.metadataProxyModel.setFilterRegExp(None)

class GDALMetadataConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(GDALMetadataConfigWidgetFactory, self).__init__('GDAL/OGR Metadata', QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))
        self.mIsGDAL = False
        self.mIsOGR = False

        self.mIconGDAL = QIcon(':/qps/ui/icons/edit_gdal_metadata.svg')
        self.mIconOGR = QIcon(':/qps/ui/icons/edit_ogr_metadata.svg')

    def supportsLayer(self, layer):
        self.mIsGDAL = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        self.mIsOGR = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'
        return self.mIsGDAL or self.mIsOGR

    def icon(self)->QIcon:
        if self.mIsGDAL:
            return QIcon(self.mIconGDAL)
        if self.mIsOGR:
            return QIcon(self.mIconOGR)
        return QIcon()

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

    def createWidget(self, layer, canvas, dockWidget=True, parent=None)->GDALMetadataModelConfigWidget:
        w = GDALMetadataModelConfigWidget(layer, canvas, parent=parent)
        w.metadataModel.setIsEditable(True)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w

    def title(self)->str:
        if self.mIsGDAL:
            return 'GDAL Metadata'
        if self.mIsOGR:
            return 'OGR Metadata'
        return 'Metadata'
