"""
***************************************************************************
    layerconfigwidget/gdalmetadata.py - A QgsMapLayerConfigWidget to show GDAL Metadata
    -----------------------------------------------------------------------
    begin                : 2020-02-24
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib
import typing
import re
import pathlib
import sys
import copy
from osgeo import gdal, ogr
import numpy as np
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsMapLayer, \
    QgsVectorDataProvider, QgsRasterDataProvider, Qgis
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidgetFactory, QgsDoubleSpinBox
from .core import QpsMapLayerConfigWidget
from ..classification.classificationscheme import ClassificationScheme, ClassificationSchemeWidget
from ..utils import loadUi, gdalDataset, parseWavelength, parseFWHM
from ..unitmodel import XUnitModel, BAND_INDEX

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
        if value in [None, '']:
            self.value = None
        else:
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

    def __str__(self):
        return f'{self.major_object}:{self.domain}:{self.key}={self.value}'

class GDALErrorHandler(object):
    def __init__(self):
        self.err_level=gdal.CE_None
        self.err_no=0
        self.err_msg=''

    def handler(self, err_level, err_no, err_msg):
        self.err_level=err_level
        self.err_no=err_no
        self.err_msg=err_msg


class GDALBandMetadataItem(object):

    def __init__(self):

        self.name: str = None
        self.wavelength: str = None
        self.fwhm: str = None
        self.wavelength_unit: str = None
        self.items: typing.List[GDALMetadataItem]


class GDALBandMetadataModel(QAbstractTableModel):
    sigWavelengthUnitsChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cnName = 'Name'
        self.cnWavelength = 'Wavelength'
        self.cnFWHM = 'FWHM'

        self.mWavelengthUnitModel = XUnitModel()
        self.mWavelengthUnitModel.mDescription[BAND_INDEX] = 'None'
        self.mWavelengthUnitModel.mToolTips[BAND_INDEX] = 'No wavelength defined'

        self.mColumnNames = [
            self.cnName,
            self.cnWavelength,
            self.cnFWHM
        ]
        self.mColumnTooltips = {
            self.cnName: 'Band name',
            self.cnWavelength: 'Band wavelengths',
            self.cnFWHM: 'Full width half maximum'
        }
        for i, c in enumerate(self.mColumnNames):
            self.mColumnTooltips[i] = self.mColumnTooltips[c]

        self.mWavelengthUnit: str = BAND_INDEX
        self.mMapLayer: QgsMapLayer = None
        self.mBandMetadata: typing.List[GDALBandMetadataItem] = []
        self.mBandMetadata0: typing.List[GDALBandMetadataItem] = []

    def registerWavelengthUnitComboBox(self, combobox: QComboBox):

        combobox.setModel(self.mWavelengthUnitModel)
        i = self.mWavelengthUnitModel.unitIndex(self.wavelenghtUnit()).row()
        combobox.setCurrentIndex(i)
        combobox.currentIndexChanged.connect(lambda *args, cb=combobox: self.setWavelengthUnit(cb.currentData(Qt.UserRole)))
        self.sigWavelengthUnitsChanged.connect(lambda *args, cb=combobox:
                                               cb.setCurrentIndex(
                                                   self.mWavelengthUnitModel.unitIndex(self.wavelenghtUnit()).row()
                                               ))

    def setWavelengthUnit(self, wlu: str):
        if wlu in ['', None]:
            # BAND_INDEX is a proxy for undefined values
            wlu = BAND_INDEX

        if wlu != self.mWavelengthUnit:
            self.mWavelengthUnit = wlu

            ul = self.createIndex(0, 0)
            lr = self.createIndex(self.rowCount()-1, self.columnCount()-1)
            self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount()-1)
            self.dataChanged.emit(ul, lr)
            self.sigWavelengthUnitsChanged.emit(self.mWavelengthUnit)

    def wavelenghtUnit(self) -> str:
        return self.mWavelengthUnit

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mBandMetadata)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mColumnNames)

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal:
            cname = self.mColumnNames[col]
            if role == Qt.DisplayRole:
                return self.mColumnNames[col]
            if role == Qt.ToolTipRole:
                return self.mColumnTooltips[col]
            if role == Qt.TextColorRole:
                if cname == self.cnWavelength and self.mWavelengthUnit == BAND_INDEX:
                    return QColor('grey')
                if cname == self.cnFWHM and not self.isMetricUnit():
                    return QColor('grey')

        elif orientation == Qt.Vertical:
            if role == Qt.DisplayRole:
                return col+1
        return None

    def setLayer(self, mapLayer: QgsMapLayer):

        if isinstance(mapLayer, QgsRasterLayer):

            self.mMapLayer = mapLayer
        else:
            self.mMapLayer = None

        self.syncToLayer()

    def columnIsEnabled(self, index: QModelIndex) -> bool:
        if isinstance(index, QModelIndex):
            index = index.column()

        if index == 0:
            return True

        cname = self.mColumnNames[index]
        if cname == self.cnWavelength:
            return self.mWavelengthUnit != BAND_INDEX
        if cname == self.cnFWHM:
            return cname != BAND_INDEX and not self.isDateUnit()
        return False

    def castWLType(self, value):
        if value in ['', None, 'None']:
            return None
        if self.isMetricUnit():
            return float(value)
        if self.isDateUnit():
            return str(value)
        return str(value)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if self.columnIsEnabled(index):
            flags = flags | Qt.ItemIsEditable
        return flags

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        cname = self.mColumnNames[index.column()]
        item: GDALBandMetadataItem = self.mBandMetadata[index.row()]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if cname == self.cnName:
                return item.name
            if cname == self.cnWavelength:
                return item.wavelength
            if cname == self.cnFWHM:
                return item.fwhm

        if role == Qt.ToolTipRole:
            if cname == self.cnName:
                return f'Band name band {index.row()+1}="{item.name}"'
            if cname == self.cnWavelength:
                if item.wavelength in [None, '']:
                    return f'Wavelength band {index.row() + 1} undefined'
                else:
                    return f'Wavelength band {index.row() + 1}: {item.wavelength}'

        if role == Qt.UserRole:
            return item

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return None

        cname = self.mColumnNames[index.column()]
        item: GDALBandMetadataItem = self.mBandMetadata[index.row()]
        changed: bool = False

        if role == Qt.EditRole:
            if cname == self.cnName:
                item.name = value
                changed = True
            elif cname == self.cnWavelength:
                item.wavelength = value
                changed = True
            elif cname == self.cnFWHM:
                item.fwhm = value
                changed = True

        if changed:
            idx0 = self.createIndex(index.row(), 0)
            idx1 = self.createIndex(index.row(), self.columnCount()-1)
            self.dataChanged.emit(idx0, idx1, [role, Qt.TextColorRole])

        return changed

    def isMetricUnit(self) -> bool:
        return re.search(r'^(m|.m|.*meters?)$', self.mWavelengthUnit) is not None

    def isDateUnit(self) -> bool:
        return re.search(r'Date|DOY|Week', self.mWavelengthUnit, re.IGNORECASE) is not None

    def isValidTypeList(self, l: list, t):
        for i in l:
            try:
                v = t(i)
            except:
               return False
        return True

    def applyToLayer(self, *args):
        if isinstance(self.mMapLayer, QgsRasterLayer) and self.mMapLayer.isValid():

            def list_or_empty(values):
                for v in values:
                    if v not in ['', None, 'None']:
                        return ','.join(values)

                return ''

            if self.mMapLayer.dataProvider().name() == 'gdal':
                try:
                    ds: gdal.Dataset = gdal.Open(self.mMapLayer.source(), gdal.GA_Update)
                    assert isinstance(ds, gdal.Dataset)
                except Exception as ex:
                    print(f'unable to open image in update mode: {self.mMapLayer.source()}')
                    print(ex, file=sys.stderr)
                    ds: gdal.Dataset = gdal.Open(self.mMapLayer.source(), gdal.GA_ReadOnly)

                is_envi = ds.GetDriver().ShortName == 'ENVI'
                if is_envi:
                    domain = 'ENVI'
                else:
                    domain = None
                if self.mWavelengthUnit not in [None, '', BAND_INDEX]:
                    ds.SetMetadataItem('wavelength units ', self.mWavelengthUnit, domain)

                    wl = [str(item.wavelength) for item in self.mBandMetadata]
                    ds.SetMetadataItem('wavelength', list_or_empty(wl), domain)

                    fwhm = [str(item.fwhm) for item in self.mBandMetadata]
                    ds.SetMetadataItem('fwhm', list_or_empty(fwhm), domain)

                for b, item in enumerate(self.mBandMetadata):
                    assert isinstance(item, GDALBandMetadataItem)
                    band: gdal.Band = ds.GetRasterBand(b+1)
                    band.SetDescription(item.name)

                    band.FlushCache()

                ds.FlushCache()
                del ds

    def validate(self) -> typing.List[str]:
        # todo: implement some internal validation and return descriptive error messages
        errors = []

        return errors

    def reset(self):
        self.beginResetModel()
        self.mBandMetadata.clear()
        self.mBandMetadata.extend([copy.copy(item) for item in self.mBandMetadata0])
        self.endResetModel()

    def syncToLayer(self, *args):

        self.beginResetModel()
        self.mBandMetadata.clear()
        self.mBandMetadata0.clear()

        if isinstance(self.mMapLayer, QgsRasterLayer) and self.mMapLayer.isValid():
            dp = self.mMapLayer.dataProvider()
            if isinstance(dp, QgsRasterDataProvider) and dp.name() == 'gdal':
                ds: gdal.Dataset = gdal.Open(self.mMapLayer.source())
                wl, wlu = parseWavelength(ds)

                if wlu in [None, '']:
                    self.setWavelengthUnit(BAND_INDEX)
                else:
                    self.setWavelengthUnit(wlu)

                fwhm = parseFWHM(ds)

                for b in range(ds.RasterCount):
                    band: gdal.Band = ds.GetRasterBand(b+1)
                    item = GDALBandMetadataItem()
                    item.name = band.GetDescription()
                    if isinstance(wl, np.ndarray) and len(wl) > b:
                        item.wavelength = self.castWLType(wl[b])
                    if isinstance(fwhm, np.ndarray) and len(fwhm) > b:
                        item.fwhm = self.castWLType(fwhm[b])

                    self.mBandMetadata.append(item)

        self.mBandMetadata0.extend([copy.copy(item) for item in self.mBandMetadata])
        self.endResetModel()



class GDALBandMetadataModelTableViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, tableView: QTableView, parent=None):
        assert isinstance(tableView, GDALBandMetadataModelTableView)
        super().__init__(parent=parent)
        self.mTableView = tableView
        # self.mTableView.model().rowsInserted.connect(self.onRowsInserted)

    def sortFilterProxyModel(self) -> QSortFilterProxyModel:
        return self.mTableView.model()

    def bandModel(self) -> GDALBandMetadataModel:
        return self.sortFilterProxyModel().sourceModel()

    def setItemDelegates(self, tableView: QTableView):

        m: GDALBandMetadataModel = self.bandModel()
        for c in [m.cnWavelength, m.cnFWHM]:
            for i in range(self.sortFilterProxyModel().columnCount()):
                cname = self.sortFilterProxyModel().headerData(i, Qt.Horizontal, role=Qt.DisplayRole)
                if cname == c:
                    tableView.setItemDelegateForColumn(i, self)

    def createEditor(self, parent, option, index):
        w = None
        m = self.bandModel()
        if index.isValid() and isinstance(m, GDALBandMetadataModel):
            cname = self.sortFilterProxyModel().headerData(index.column(), Qt.Horizontal)
            wlu = self.bandModel().wavelenghtUnit()

            if cname in [m.cnWavelength, m.cnFWHM]:
                if self.bandModel().isMetricUnit():
                    w = QgsDoubleSpinBox(parent=parent)
                    w.setClearValue(0)
                    w.setMaximum(16000)
                    w.setMinimum(0)
                    w.setDecimals(4)
                elif self.bandModel().isDateUnit():
                    w = QLineEdit(parent=parent)

        if w is None:
            w = super().createEditor(parent, option, index)
        return w

    def setEditorData(self, w: QWidget, index):
        m = self.bandModel()
        if index.isValid() and isinstance(m, GDALBandMetadataModel):
            cname = self.sortFilterProxyModel().headerData(index.column(), Qt.Horizontal)
            value = index.data(Qt.DisplayRole)

            if isinstance(w, QDoubleSpinBox):
                if value in [None, 'None', '']:
                    value = w.clearValue()
                value = float(value)
                w.setValue(value)
            elif isinstance(w, QLineEdit):
                w.setText(str(value))
            else:
                raise NotImplementedError()

    def setModelData(self, w, bridge, proxyIndex):
        value = None
        if isinstance(w, QDoubleSpinBox):
            value = w.value()
            if isinstance(w, QgsDoubleSpinBox) and value == w.clearValue():
                value = None
        elif isinstance(w, QLineEdit):
            value = w.text()
        self.sortFilterProxyModel().setData(proxyIndex, value, role=Qt.EditRole)


class GDALBandMetadataModelTableView(QTableView):
    """
    A QTreeView for the GDALBandMetadataModelTableView
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Opens a context menu
        """
        index = self.indexAt(event.pos())
        if index.isValid():

            item = index.data(Qt.UserRole)
            if not isinstance(item, GDALBandMetadataItem):
                return

            selectedIndexes = self.selectionModel().selectedIndexes()
            selectedColumnIndexes = [i for i in selectedIndexes if i.column() == index.column()]

            cname = self.model().headerData(index.column(), Qt.Horizontal)
            m = QMenu()
            a = m.addAction(f'Copy value(s)')
            a.triggered.connect(lambda *args, idx=selectedIndexes: self.copyValues(idx, sep='\n'))

            a = m.addAction(f'Copy "{cname}" (newline)')
            a.triggered.connect(lambda *args, idx=selectedColumnIndexes: self.copyValues(idx, sep='\n'))

            a = m.addAction(f'Copy "{cname}" (,)')
            a.triggered.connect(lambda *args, idx=selectedColumnIndexes: self.copyValues(idx, sep=','))

            a = m.addAction(f'Paste "{cname}" value(s)')
            a.triggered.connect(lambda *args, idx=index: self.pasteValues(idx))

            m.addSeparator()
            a = m.addAction(f'Clear selected')
            a.setEnabled(len(selectedIndexes) > 0)
            a.triggered.connect(lambda *args, idx=selectedIndexes: self.clearValues(idx))

            m.exec_(event.globalPos())

    def clearValues(self, indices: typing.List[QModelIndex]):
        for idx in indices:
            self.model().setData(idx, '', role=Qt.EditRole)

    def copyValues(self, indices: typing.List[QModelIndex], sep='\n'):
        values = [str(idx.data(Qt.DisplayRole)) for idx in indices]
        values = sep.join(values)
        QApplication.clipboard().setText(values)

    def pasteValues(self, idx: QModelIndex):
        md: QMimeData = QApplication.clipboard().mimeData()
        values = md.text()
        values = re.split(r'[,\n]', values)

        r0 = idx.row()
        for i, v in enumerate(values):
            row = r0 + i
            if row >= self.model().rowCount():
                break
            index = self.model().index(row, idx.column())
            self.model().setData(index, v, role=Qt.EditRole)


class GDALMetadataModel(QAbstractTableModel):

    sigEditable = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(GDALMetadataModel, self).__init__(parent)
        self.mLayer: QgsMapLayer = None

        self.mErrorHandler: GDALErrorHandler = GDALErrorHandler()

        self.cnItem = 'Item'
        self.cnDomain = 'Domain'
        self.cnKey = 'Key'
        self.cnValue = 'Value(s)'

        self._column_names = [self.cnItem, self.cnDomain, self.cnKey, self.cnValue]
        self._isEditable = False
        self._MDItems: typing.List[GDALMetadataItem] = []
        self._MOKs:typing.List[str] = []

    def resetChanges(self):
        c = self._column_names.index(self.cnValue)
        for r, item in enumerate(self._MDItems):
            if item.isModified():
                idx = self.createIndex(r, c, None)
                self.setData(idx, item.initialValue, Qt.EditRole)

    def domains(self) -> typing.List[str]:

        domains = set()
        for item in self._MDItems:
            domains.add(item.domain)
        return sorted(domains)

    def major_objects(self) -> typing.List[str]:
        return sorted(self._MOKs, key=lambda k: (re.search('^(Band|Layer).*', k) is not None, k))

    def setIsEditable(self, b: bool):
        assert isinstance(b, bool)
        if b != self._isEditable:
            self._isEditable = b
            self.sigEditable.emit(self.isEditable())

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

    def syncToLayer(self, *args):
        self.beginResetModel()
        self._MOKs.clear()
        self._MDItems.clear()
        mdItems, moks = self._read_maplayer()
        self._MDItems.extend(mdItems)
        self._MOKs.extend(moks)
        self.endResetModel()

    def removeItem(self, item:GDALMetadataItem):
        assert isinstance(item, GDALMetadataItem)
        assert item in self._MDItems

        r = self._MDItems.index(item)
        idx = self.index(r, self._column_names.index(self.cnValue), None)
        self.setData(idx, None, role=Qt.EditRole)

    def addItem(self, item: GDALMetadataItem):
        assert isinstance(item, GDALMetadataItem)
        if item not in self._MDItems:
            r = self.rowCount()
            self.beginInsertRows(QModelIndex(), r, r)
            self._MDItems.append(item)
            self.endInsertRows()

    def applyToLayer(self):

        changed: typing.List[GDALMetadataItem] = [md for md in self._MDItems if md.isModified()]

        if isinstance(self.mLayer, QgsRasterLayer) and isinstance(self.mLayer.dataProvider(), QgsRasterDataProvider):

            if self.mLayer.dataProvider().name() == 'gdal':
                gdal.PushErrorHandler(self.mErrorHandler.handler)
                try:
                    ds = gdal.Open(self.mLayer.source(), gdal.GA_ReadOnly)
                    if isinstance(ds, gdal.Dataset):
                        for item in changed:
                            mo: gdal.MajorObject = None
                            assert isinstance(item, GDALMetadataItem)
                            if item.major_object == 'Dataset':
                                mo = ds
                            elif item.major_object.startswith('Band'):
                                mo = ds.GetRasterBand(int(item.major_object[4:]))

                            if isinstance(mo, gdal.MajorObject):
                                mo.SetMetadataItem(item.key, item.value, item.domain)

                        ds.FlushCache()
                        del ds

                    if self.mErrorHandler.err_level >= gdal.CE_Warning:
                        raise RuntimeError(self.mErrorHandler.err_level,
                                           self.mErrorHandler.err_no,
                                           self.mErrorHandler.err_msg)
                except Exception as ex:
                    print(ex, file=sys.stderr)
                finally:
                    gdal.PopErrorHandler()

        if isinstance(self.mLayer, QgsVectorLayer) and isinstance(self.mLayer.dataProvider(), QgsVectorDataProvider):
            if self.mLayer.dataProvider().name() == 'ogr':
                path = self.mLayer.source().split('|')[0]
                gdal.PushErrorHandler(self.mErrorHandler.handler)
                try:
                    ds: ogr.DataSource = ogr.Open(path, update=1)
                    if isinstance(ds, ogr.DataSource):
                        for item in changed:
                            assert isinstance(item, GDALMetadataItem)
                            mo: ogr.MajorObject = None
                            if item.major_object == 'DataSource':
                                mo = ds
                            elif item.major_object.startswith('Layer'):
                                mo = ds.GetLayer(int(item.major_object[5:])-1)

                            if isinstance(mo, ogr.MajorObject):
                                mo.SetMetadataItem(item.key, item.value, item.domain)

                        ds.FlushCache()
                    if self.mErrorHandler.err_level >= gdal.CE_Warning:
                        raise RuntimeError(self.mErrorHandler.err_level,
                                           self.mErrorHandler.err_no,
                                           self.mErrorHandler.err_msg)
                except Exception as ex:
                    print(ex, file=sys.stderr)
                finally:
                    gdal.PopErrorHandler()

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

        if role == Qt.TextColorRole:
            if item.value in ['', None]:
                return QColor('red')

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
            idx0 = self.createIndex(index.row(), 0)
            idx1 = self.createIndex(index.row(), self.columnCount()-1)
            self.dataChanged.emit(idx0, idx1, [role, Qt.TextColorRole])

        return False

    def _read_majorobject(self, obj):
        assert isinstance(obj, (gdal.MajorObject, ogr.MajorObject))
        domains = obj.GetMetadataDomainList()
        if isinstance(domains, list):
            domains = list(set(domains))
            for domain in domains:
                domainItems = obj.GetMetadata(domain)
                if isinstance(domainItems, dict):
                    for key, value in domainItems.items():
                        yield domain, key, value

    def _read_maplayer(self) -> typing.Tuple[
                                typing.List[GDALMetadataItem],
                                typing.List[str]
                                ]:
        items = []
        major_objects = []

        if not isinstance(self.mLayer, QgsMapLayer) or not self.mLayer.isValid():
            return items, major_objects

        if isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.dataProvider().name() == 'gdal':
            ds = gdal.Open(self.mLayer.source())

            if isinstance(ds, gdal.Dataset):
                z = len(str(ds.RasterCount))
                mok = 'Dataset'
                major_objects.append(mok)
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataItem(mok, domain, key, value))
                for b in range(ds.RasterCount):
                    band = ds.GetRasterBand(b + 1)
                    assert isinstance(band, gdal.Band)
                    mok = 'Band{}'.format(str(b + 1).zfill(z))
                    major_objects.append(mok)
                    for (domain, key, value) in self._read_majorobject(band):
                        items.append(GDALMetadataItem(mok, domain, key, value))

        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.dataProvider().name() == 'ogr':
            ds = ogr.Open(self.mLayer.source().split('|')[0])
            if isinstance(ds, ogr.DataSource):
                sep = self.mLayer.dataProvider().sublayerSeparator()
                subLayers = self.mLayer.dataProvider().subLayers()
                if len(subLayers) > 0:
                    parts = subLayers[0].split(sep)
                    layerIndex = int(parts[0])
                    layerName = parts[1]

                mok = 'DataSource'
                major_objects.append(mok)
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataItem(mok, domain, key, value))
                z = len(str(ds.GetLayerCount()))
                for b in range(ds.GetLayerCount()):
                    lyr = ds.GetLayer(b)
                    assert isinstance(lyr, ogr.Layer)
                    mok = 'Layer{}'.format(str(b + 1).zfill(z))
                    major_objects.append(mok)
                    for (domain, key, value) in self._read_majorobject(lyr):
                        items.append(GDALMetadataItem(mok, domain, key, value))

        return items, major_objects


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


class GDALMetadataItemDialog(QDialog):

    def __init__(self, *args,
                 major_objects: typing.List[str] = [],
                 domains: typing.List[str] = [],
                 **kwds):
        super().__init__(*args, **kwds)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'gdalmetadatamodelitemwidget.ui'
        loadUi(pathUi, self)

        self.tbKey: QLineEdit
        self.tbValue: QLineEdit
        self.cbDomain: QComboBox
        self.cbMajorObject: QComboBox

        self.cbMajorObject.addItems(major_objects)
        self.cbDomain.addItems(domains)

        self.tbKey.textChanged.connect(self.validate)
        self.tbValue.textChanged.connect(self.validate)
        self.cbDomain.currentTextChanged.connect(self.validate)
        self.cbMajorObject.currentTextChanged.connect(self.validate)


        self.validate()

    def validate(self, *args):
        errors = []

        item = self.metadataItem()
        if item.key == '':
            errors.append('missing key')
        if item.value == '':
            errors.append('missing value')
        if item.major_object in ['', None]:
            errors.append('missing item')

        self.infoLabel.setText('\n'.join(errors))
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(len(errors) == 0)

    def setKey(self, name:str):
        self.tbKey.setText(str(name))

    def setValue(self, value:str):
        self.tbValue.setText(str(value))

    def setDomain(self, domain: str):

        idx = self.cbDomain.findText(domain)
        if idx >= 0:
            self.cbDomain.setCurrentIndex(idx)
        else:
            self.cbDomain.setCurrentText(domain)

    def setMajorObject(self, major_object: str):

        idx = self.cbMajorObject.findText(major_object)
        assert idx >= 0, f'major_object does not exist: {major_object}'
        self.cbMajorObject.setCurrentIndex(idx)

    def metadataItem(self) -> GDALMetadataItem:

        key = self.tbKey.text()
        value = self.tbValue.text()
        domain = self.cbDomain.currentText()
        major_object = self.cbMajorObject.currentText()
        item = GDALMetadataItem(major_object, domain, key, value)
        item.initialValue = None
        return item


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

        self.bandMetadataModel = GDALBandMetadataModel()
        self.bandMetadataProxyModel = QSortFilterProxyModel()
        self.bandMetadataProxyModel.setSourceModel(self.bandMetadataModel)
        self.bandMetadataProxyModel.setFilterKeyColumn(-1)

        self.tvBandNames.setModel(self.bandMetadataProxyModel)
        self.bandMetadataModelViewDelegate = GDALBandMetadataModelTableViewDelegate(self.tvBandNames)
        self.bandMetadataModelViewDelegate.setItemDelegates(self.tvBandNames)

        self.cbWavelengthUnits: QComboBox
        self.bandMetadataModel.registerWavelengthUnitComboBox(self.cbWavelengthUnits)

        self.metadataModel = GDALMetadataModel()
        self.metadataModel.sigEditable.connect(self.onEditableChanged)
        self.metadataProxyModel = QSortFilterProxyModel()
        self.metadataProxyModel.setSourceModel(self.metadataModel)
        self.metadataProxyModel.setFilterKeyColumn(-1)

        self.tvGDALMetadata: GDALMetadataModelTableView
        assert isinstance(self.tvGDALMetadata, GDALMetadataModelTableView)
        self.tvGDALMetadata.setModel(self.metadataProxyModel)
        self.tvGDALMetadata.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.tbFilter.textChanged.connect(self.updateFilter)
        self.optionMatchCase.changed.connect(self.updateFilter)
        self.optionRegex.changed.connect(self.updateFilter)
        assert isinstance(self.classificationSchemeWidget, ClassificationSchemeWidget)

        self.is_gdal = self.is_ogr = self.supportsGDALClassification = False
        self.classificationSchemeWidget.setIsEditable(False)

        self.setLayer(layer)

        self.btnAddItem.setDefaultAction(self.actionAddItem)
        self.btnRemoveItem.setDefaultAction(self.actionRemoveItem)
        self.btnReset.setDefaultAction(self.actionReset)

        self.actionReset.triggered.connect(self.onReset)
        self.actionRemoveItem.setEnabled(False)
        self.actionAddItem.triggered.connect(self.onAddItem)
        self.actionRemoveItem.triggered.connect(self.onRemoveSelectedItems)
        self.onEditableChanged(self.metadataModel.isEditable())

    def onWavelengthUnitsChanged(self):
        wlu = self.bandMetadataModel.wavelenghtUnit()

        wlu = self.cbWavelengthUnits.currentData(role=Qt.UserRole)
        self.bandMetadataModel.setWavelengthUnit(wlu)

    def onReset(self):

        self.metadataModel.resetChanges()

    def onAddItem(self):
        protectedDomains = [p.split(':')[0] for p in PROTECTED if not p.startswith(':')]
        domains = [d for d in self.metadataModel.domains() if d not in protectedDomains]
        d = GDALMetadataItemDialog(parent=self,
                                   domains=domains,
                                   major_objects=self.metadataModel.major_objects())

        if d.exec_() == QDialog.Accepted:
            item = d.metadataItem()
            self.metadataModel.addItem(item)

    def onRemoveSelectedItems(self):

        rows = self.tvGDALMetadata.selectionModel().selectedRows()

        items = [self.tvGDALMetadata.model().data(row, role=Qt.UserRole) for row in rows]
        for item in items:
            self.metadataModel.removeItem(item)

    def onSelectionChanged(self, *args):

        rows = self.tvGDALMetadata.selectionModel().selectedRows()
        self.actionRemoveItem.setEnabled(len(rows) > 0)

    def onEditableChanged(self, *args):
        isEditable = self.metadataModel.isEditable()
        self.btnAddItem.setVisible(isEditable)
        self.btnRemoveItem.setVisible(isEditable)
        self.btnReset.setVisible(isEditable)
        self.actionReset.setEnabled(isEditable)
        self.actionAddItem.setEnabled(isEditable)
        self.onSelectionChanged() # this sets the actionRemoveItem

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

            self.syncToLayer(layer)

    def apply(self):
        if self.is_gdal:
            ds = gdalDataset(self.mapLayer(), gdal.GA_Update)
            assert isinstance(ds, gdal.Dataset)

            if self.supportsGDALClassification:
                cs = self.classificationSchemeWidget.classificationScheme()
                if isinstance(cs, ClassificationScheme):
                    #self.mapLayer().dataProvider().setEditable(True)
                    cs.saveToRaster(ds)
                    ds.FlushCache()

        self.bandMetadataModel.applyToLayer()
        self.metadataModel.applyToLayer()

        QTimer.singleShot(1000, self.syncToLayer)

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        self.bandMetadataModel.setLayer(lyr)
        self.metadataModel.setLayer(lyr)
        if self.supportsGDALClassification:
            self._cs = ClassificationScheme.fromMapLayer(lyr)

        if isinstance(self._cs, ClassificationScheme) and len(self._cs) > 0:
            self.gbClassificationScheme.setVisible(True)
            self.classificationSchemeWidget.setClassificationScheme(self._cs)
        else:
            self.classificationSchemeWidget.classificationScheme().clear()
            self.gbClassificationScheme.setVisible(False)

        self.gbBandNames.setVisible(self.is_gdal)

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

    def icon(self) -> QIcon:
        if self.mIsGDAL:
            return QIcon(self.mIconGDAL)
        if self.mIsOGR:
            return QIcon(self.mIconOGR)
        return QIcon()

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

    def createWidget(self, layer, canvas, dockWidget=True, parent=None) -> GDALMetadataModelConfigWidget:
        w = GDALMetadataModelConfigWidget(layer, canvas, parent=parent)
        w.metadataModel.setIsEditable(True)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w

    def title(self) -> str:
        if self.mIsGDAL:
            return 'GDAL Metadata'
        if self.mIsOGR:
            return 'OGR Metadata'
        return 'Metadata'
