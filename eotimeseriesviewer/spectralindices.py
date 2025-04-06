import json
from typing import List, Set

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from eotimeseriesviewer import DIR_REPO

INDICES = dict()
CONSTANTS = dict()

DIR_SPYNDEX = DIR_REPO / 'eotimeseriesviewer' / 'spyndex'
assert DIR_SPYNDEX.is_dir()


class BandIdentifier(object):

    def __init__(self,
                 identifier: str,
                 name: str = None,
                 tooltip: str = None,
                 wl_min: float = None,
                 wl_max: float = None,
                 ):
        self.identifier = identifier
        self.name = name
        self.toolTip = tooltip
        self.wl_min = wl_min
        self.wl_max = wl_max

    def __eq__(self, other):
        if not isinstance(other, BandIdentifier):
            return False
        for k, v in self.__dict__.items():
            if k.startswith('_'):
                continue
            v2 = getattr(other, k)
            if v != v2:
                return False
        return True

    def asMap(self) -> dict:
        d = dict()
        for k in self.__dict__.keys():
            if not k.startswith('_'):
                d[k] = self.__dict__[k]
        return d

    @staticmethod
    def fromMap(data: dict) -> 'BandIdentifier':

        a = BandIdentifier('')
        for k, v in data.items():
            setattr(a, k, v)
        return a

    def setWavelength(self, wl1, wl2):
        assert wl1 < wl2
        assert wl1 > 0
        self.wl_min = wl1
        self.wl_max = wl2

    def centerWavelength(self):
        return 0.5 * (self.wl_min + self.wl_max)


class SpectralIndexConstantModel(QAbstractTableModel):
    cIdentifier = 0
    cValue = 1
    cDescription = 2

    _instance = None

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mConstantDefinitions: dict = dict()
        self.mColumnNames = {self.cIdentifier: 'Identifier',
                             self.cValue: 'Value',
                             self.cDescription: 'Description'}
        self.mColumnToolTips = dict()

    @classmethod
    def instance(cls) -> 'SpectralIndexBandIdentifierModel':
        if cls._instance is None:
            cls._instance = SpectralIndexConstantModel()
            cls._instance.loadFromSpyndex()
        return cls._instance

    def asMap(self) -> dict:
        return self.mConstantDefinitions.copy()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mConstantDefinitions)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.mColumnNames)

    def short_names(self) -> List[str]:
        return list(self.mConstantDefinitions.keys())

    def addConstants(self, constantDefinitions: dict):

        new_data = dict()
        for short_name, data in constantDefinitions.items():
            assert short_name == data['short_name']
            keys = ['short_name', 'description', 'default']
            new_item = {k: data[k] for k in keys}
            new_item['value'] = new_item.get('value', new_item['default'])
            new_data[short_name] = new_item

        existing_names = self.short_names()
        to_update = [i for i in new_data.values() if i['short_name'] in existing_names]
        to_add = [i for i in new_data.values() if i['short_name'] not in existing_names]
        for item in to_update:
            row = existing_names.index(short_name)
            self.mConstantDefinitions[short_name] = item
            idx1 = self.index(row, 0, QModelIndex())
            idx2 = self.index(row, self.columnCount() - 1, QModelIndex())
            self.dataChanged(QModelIndex(), idx1, idx2)
        n = len(to_add)

        if n > 0:

            r0 = self.rowCount()
            r1 = r0 + n - 1
            self.beginInsertRows(QModelIndex(), r0, r1)
            for item in to_add:
                self.mConstantDefinitions[item['short_name']] = item
            self.endInsertRows()
        pass

    def removeConstants(self, keys: List[str]):
        if isinstance(keys, str):
            keys = [keys]

        to_remove = [k for k in keys if k in self.short_names()]
        for k in to_remove:
            row = self.short_names().index(k)
            self.beginRemoveRows(QModelIndex(), row, row)
            self.mConstantDefinitions.pop(k)
            self.endRemoveRows()

    def loadFromSpyndex(self):
        """
        Loads the band definition for the given satellite sensor from the awesome-spectral-library model
        :param plattform:
        :return:
        """
        with open(DIR_SPYNDEX / 'data' / 'constants.json') as f:
            constants = json.load(f)

        self.addConstants(constants)

    def loadFromMap(self, data: dict):

        self.addConstants(data)

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames.get(col)
            if role == Qt.ToolTipRole:
                return self.mColumnToolTips.get(col)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(col)
        return None

    def data(self, index: QModelIndex, role: Qt.ItemDataRole):

        if not index.isValid():
            return None

        info = self.mConstantDefinitions[list(self.mConstantDefinitions.keys())[index.row()]]
        if role == Qt.UserRole:
            return info

        c = index.column()
        if role == Qt.DisplayRole:
            if c == self.cIdentifier:
                return info['short_name']
            if c == self.cDescription:
                return info['description']
            if c == self.cValue:
                return info['value']

        return None


class SpectralIndexBandIdentifierModel(QAbstractTableModel):
    """A model that describes the properties of a band acronym"""

    cIdentifier = 0
    cName = 1
    cWLRange = 2

    _instance = None

    @classmethod
    def instance(cls) -> 'SpectralIndexBandIdentifierModel':
        if cls._instance is None:
            cls._instance = SpectralIndexBandIdentifierModel()
            cls._instance.loadFromSpyndex()
        return cls._instance

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mAcronyms: List[BandIdentifier] = []

        self.mColumnNames = {self.cIdentifier: 'Identifier',
                             self.cName: 'Name',
                             self.cWLRange: 'Range [nm]'}
        self.mColumnToolTips = dict()

    def asMap(self) -> dict:

        d = dict()
        for a in self.mAcronyms:
            a: BandIdentifier
            d[a.identifier] = a.asMap()
        return d

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mAcronyms)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.mColumnNames)

    def acronyms(self) -> List[str]:
        return [info.name for info in self.mAcronyms]

    def flags(self, index):
        if index.isValid():
            # c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            # return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def data(self, index: QModelIndex, role: Qt.ItemDataRole):

        if not index.isValid():
            return None

        info = self.mAcronyms[index.row()]
        if role == Qt.UserRole:
            return info

        c = index.column()
        if role == Qt.DisplayRole:
            if c == self.cIdentifier:
                return info.identifier
            if c == self.cName:
                return info.name
            if c == self.cWLRange:
                return f'{info.wl_min} - {info.wl_max}'

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        return self.createIndex(row, column, self.mAcronyms[row])

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames.get(col)
            if role == Qt.ToolTipRole:
                return self.mColumnToolTips.get(col)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(col)
        return None

    def loadFromSpyndex(self, plattform: str = 'sentinel2a'):
        """
        Loads the band definition for the given satellite sensor from the awesome-spectral-library model
        :param plattform:
        :return:
        """

        acronyms = band_acronyms(plattform)
        a_names = [a.name for a in acronyms]
        to_remove = [a for a in self.mAcronyms if a.name in a_names]
        acronyms = sorted(acronyms, key=lambda a: a.centerWavelength())
        self.removeAcronyms(to_remove)
        self.addAcronyms(acronyms)

    def loadFromMap(self, data: dict):

        self.beginRemoveRows(QModelIndex(), 0, len(self.mAcronyms) - 1)
        self.mAcronyms.clear()
        self.endRemoveRows()

        to_add = []
        for k, v in data.items():
            to_add.append(BandIdentifier.fromMap(v))

        n = len(data)
        if n > 0:
            self.beginInsertRows(QModelIndex(), 0, n - 1)
            self.mAcronyms.extend(to_add)
            self.endInsertRows()

    def addAcronyms(self, acronyms: List[BandIdentifier]):

        existing = self.acronyms()
        to_add = [a for a in acronyms if a.name not in existing]
        n = len(to_add)
        if n > 0:
            r0 = self.rowCount()
            r1 = r0 + n - 1
            self.beginInsertRows(QModelIndex(), r0, r1)
            self.mAcronyms.extend(to_add)
            self.endInsertRows()

        pass

    def removeAcronyms(self, acronyms: List[BandIdentifier]):

        to_remove = [a for a in acronyms if a in self.mAcronyms]

        n = len(to_remove)

        if n > 0:
            for a in reversed(to_remove):
                row = self.mAcronyms.index(a)
                self.beginRemoveRows(QModelIndex(), row, row)
                self.mAcronyms.remove(a)
                self.endRemoveRows()


def band_acronyms(plattform: str = None) -> List[BandIdentifier]:
    path_bands = DIR_SPYNDEX / 'data' / 'bands.json'

    to_add: List[BandIdentifier] = []
    with open(path_bands) as f:
        dump = json.load(f)
        for acronym, infos in dump.items():
            if plattform and plattform not in infos['platforms']:
                continue

            a = BandIdentifier(infos['short_name'])
            a.name = infos['long_name']
            a.setWavelength(infos['min_wavelength'], infos['max_wavelength'])

            to_add.append(a)
    return to_add


def spectral_indices() -> dict:
    global INDICES, CONSTANTS
    if len(INDICES) == 0:
        path_indices = DIR_SPYNDEX / 'data' / 'spectral-indices-dict.json'
        path_constants = DIR_SPYNDEX / 'data' / 'constants.json'

        with open(path_indices) as f:
            dump = json.load(f)
            INDICES = dump['SpectralIndices']

        with open(path_constants) as f:
            dump = json.load(f)
            CONSTANTS = dump
    return INDICES


def spectral_index_acronyms(band_identifier_model: SpectralIndexBandIdentifierModel = None,
                            constant_model: SpectralIndexConstantModel = None) -> dict:
    if band_identifier_model is None:
        band_identifier_model = SpectralIndexBandIdentifierModel.instance()

    if constant_model is None:
        constant_model = SpectralIndexConstantModel.instance()

    return {'band_identifier': band_identifier_model.asMap(),
            'constants': constant_model.asMap()}


class SpectralIndexModel(QAbstractTableModel):
    """
    A model that lists all spectral indices and their details
    """

    cShortName = 0
    cFormula = 1
    cLongName = 2
    cDomain = 3
    cPlatforms = 4
    cReference = 5

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        indices = spectral_indices()
        self._indices: List[dict] = list(indices.values())
        self._indices0: List[dict] = list(indices.values())

        self.mColumnNames = {
            self.cShortName: 'Name',
            self.cLongName: 'Long Name',
            self.cDomain: 'Domain',
            self.cFormula: 'Formula',
            self.cReference: 'Reference',
            self.cPlatforms: 'Platforms',
        }

        self.mShortcuts: Set[str] = set()

    def shortcuts(self) -> List[str]:
        return sorted(self.mShortcuts)

    def setShortcuts(self, shortcuts: List[str]):
        self.beginResetModel()
        for s in shortcuts:
            self.mShortcuts.add(s)
        self.endResetModel()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._indices)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.mColumnNames)

    def flags(self, index: QModelIndex):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if index.column() == self.cShortName:
                flags = flags | Qt.ItemIsUserCheckable
            return flags
        return Qt.NoItemFlags

    def headerData(self, section, orientation, role=None):

        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[section]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return section + 1
        return None

    def setData(self, index: QModelIndex, value, role=None):
        if not index.isValid():
            return None

        col = index.column()
        row = index.row()

        sidx: dict = self._indices[row]

        changed = False
        if col == self.cShortName and role == Qt.CheckStateRole:
            short_name = sidx['short_name']
            if value == Qt.Checked:
                self.mShortcuts.add(short_name)
            else:
                if short_name in self.mShortcuts:
                    self.mShortcuts.remove(short_name)
            changed = True
        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed

    def data(self, index: QModelIndex, role=None):

        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        sidx: dict = self._indices[row]

        if role == Qt.DisplayRole:
            if col == self.cShortName:
                return sidx.get('short_name')
            if col == self.cLongName:
                return sidx.get('long_name')
            if col == self.cPlatforms:
                return ','.join(sidx.get('platforms'))
            if col == self.cDomain:
                return sidx.get('application_domain')
            if col == self.cReference:
                uri = sidx.get('reference')
                return uri
                # return f'<a href="{uri}">{uri}</a>'
            if col == self.cFormula:
                return sidx.get('formula')
        if role == Qt.ToolTipRole:
            uri = sidx.get('reference')
            tt = [
                f'<b>{sidx.get('short_name')}</b>',
                f'<i>{sidx.get('long_name')}</i>',
                f'Formula: {sidx.get('formula')}',
                f'Domain: {sidx.get('domain')}',
                f'Platforms: {",".join(sidx.get('platforms'))}',
                f'Reference: <a href="{uri}">{uri}</a>',
            ]
            return '<br>'.join(tt)

        if role == Qt.CheckStateRole:
            if col == self.cShortName:
                sn = sidx.get('short_name')
                return Qt.Checked if sn in self.mShortcuts else Qt.Unchecked

        return None


class SpectralIndexProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._model = SpectralIndexModel()
        self.setSourceModel(self._model)
