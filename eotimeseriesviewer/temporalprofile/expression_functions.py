import json
from typing import List

import numpy as np
from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, Qt
from qgis.core import QgsExpressionContext, QgsExpressionContextScope, QgsExpressionFunction, QgsExpressionNode, \
    QgsScopedExpressionFunction

from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.qgispluginsupport.qps.unitmodel import UnitLookup
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils

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
        s = ""
        pass

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
            c = index.column()
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


def spectral_index_scope(band_model: SpectralIndexBandIdentifierModel = None) -> QgsExpressionContextScope:
    if band_model is None:
        band_model = SpectralIndexBandIdentifierModel()
        band_model.loadFromSpyndex()

    scope = QgsExpressionContextScope('spectral_index_definitions')
    v = QgsExpressionContextScope.StaticVariable()
    v.name = 'band_acronyms'
    v.value = band_model.asMap()
    scope.addVariable(v)
    scope.addHiddenVariable(v.name)
    return scope


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


class TemporalProfileExpressionFunctionUtils(object):

    @classmethod
    def cachedAcronyms(cls, context: QgsExpressionContext) -> dict:
        k = 'eotsv/acronyms'
        if context.hasVariable(k):
            index_acronyms = context.variable(k)
        elif context.hasCachedValue(k):
            index_acronyms = context.cachedValue(k)
        else:
            index_acronyms = spectral_index_acronyms()
            context.setCachedValue(k, index_acronyms)

        return index_acronyms

    @classmethod
    def cachedSensorBandLookups(cls, context: QgsExpressionContext, temporal_profile: dict, band_identifier: dict):
        k = 'eotsv/bandlookups'

        if context.hasVariable(k):
            lookups = context.variable(k)
        elif context.hasCachedValue(k):
            lookups = context.cachedValue(k)
        else:
            lookups = dict()

        changed = False
        for i, sid in enumerate(temporal_profile['sensor_ids']):
            if i not in lookups or sid not in lookups:
                lookup = cls.cachedSensorBandLookup(context, sid, band_identifier)
                lookups[i] = lookup
                lookups[sid] = lookup
                changed = True
        if changed:
            context.setCachedValue(k, lookups)
        return lookups

    @classmethod
    def cachedSensorBandLookup(cls, context: QgsExpressionContext, sensor_id: str, band_identifier: dict):  #
        k = f'eotsv/bandlookup/{sensor_id}'
        if context.hasVariable(k):
            return context.variable(k)
        elif context.hasCachedValue(k):
            return context.cachedValue(k)
        else:
            lookup = dict()
            sa = json.loads(sensor_id)
            if isinstance(sa.get('wlu'), str) and isinstance(sa['wl'], list):
                # convert wavelengths to nanometers
                sa['wl'] = UnitLookup.convertLengthUnit(sa['wl'], sa['wlu'], 'nm')

                for name, info in band_identifier.items():
                    center_wl = 0.5 * (info['wl_min'] + info['wl_max'])
                    wl = sa['wl']
                    if min(wl) <= center_wl <= max(wl):
                        lookup[name] = np.argmin(np.abs(np.asarray(wl) - center_wl))
                    else:
                        lookup[name] = None
                s = ""

            context.setCachedValue(k, lookup)

            return lookup
        # self.cachedSensorBandLookup(context, tp['sensor_ids'], acronyms['band_identifier'])

    @staticmethod
    def cachedTemporalProfile(context: QgsExpressionContext, field=None) -> dict:
        """
        Returns the temporal profile (as dict) from the current expression context.
        """
        k = 'eotsv/temporalprofiledata'

        dump = context.cachedValue(k)
        if dump is None:
            # get field
            if field is None:
                tpFields = TemporalProfileUtils.temporalProfileFields(context.fields())
                if len(tpFields) == 0:
                    return None
                field = tpFields[0].name()
            if isinstance(field, (int, str)):
                if len(context.feature().fields()) > 0:
                    dump = context.feature().attribute(field)
                    if isinstance(dump, str):
                        dump = json.loads(dump)
                    sensor_attributes = [json.loads(sid) for sid in dump['sensor_ids']]
                    for s in sensor_attributes:
                        v_wl = s.get('wl')
                        v_wlu = s.get('wlu')
                        if isinstance(v_wl, list) and isinstance(v_wlu, str):
                            # convert wavelength to nanometer
                            s['wl'] = UnitLookup.convertLengthUnit(s['wl'], s['wlu'], 'nm')
                            s['wlu'] = 'nm'

                    dump['sensor_attributes'] = sensor_attributes
                    context.setCachedValue(k, dump)
        else:
            s = ""
        return dump


class ProfileTimeExpressionFunction(QgsScopedExpressionFunction):
    NAME = 'tptime'


class ProfileValueExpressionFunction(QgsScopedExpressionFunction):
    NAME = 'tpval'

    def __init__(self, ):

        params = [
            QgsExpressionFunction.Parameter('band', optional=False),
            QgsExpressionFunction.Parameter('field', optional=True),
            QgsExpressionFunction.Parameter('date', optional=True),
        ]
        super().__init__(self.NAME, params,
                         'Timeseries',
                         'Extracts values from a temporal profile',
                         lazyEval=True)

    def clone(self) -> '':
        return ()

    def func_(self, values: List[QgsExpressionNode], context: QgsExpressionContext, parent, node):
        try:
            return self.func_core(values, context, parent, node)
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def func(self, values: List[QgsExpressionNode], context: QgsExpressionContext, parent, node):
        band = values[0].value()
        field = values[1].value()
        date = values[2].value()

        tp = TemporalProfileExpressionFunctionUtils.cachedTemporalProfile(context, field)
        if tp is None:
            return

        indices = spectral_indices()

        n_dates = len(tp[TemporalProfileUtils.Date])

        if context.hasVariable('dates'):
            dates = context.variable('dates')
            if isinstance(dates, str):
                dates = dates.split()
                date_indices = []
                for i, dtg in enumerate(tp[TemporalProfileUtils.Date]):
                    for d in dates:
                        if dtg.startswith(d) and i not in date_indices:
                            date_indices.append(i)

            elif isinstance(dates, int):
                assert 0 <= dates < n_dates
                date_indices = [dates]
        else:
            date_indices = list(range(n_dates))

        x_values = [tp[TemporalProfileUtils.Date][i] for i in date_indices]
        context.setCachedValue('eotsv/current_dates', x_values)

        y_values = []

        if isinstance(band, int):
            # return band number
            assert band >= 1, 'Band number must be >= 1'
            y_values = [tp[TemporalProfileUtils.Values][i][band - 1] for i in date_indices]


        elif isinstance(band, str):
            acronyms = TemporalProfileExpressionFunctionUtils.cachedAcronyms(context)
            constants = acronyms['constants']
            band_identifier = acronyms['band_identifier']

            band_lookups = TemporalProfileExpressionFunctionUtils.cachedSensorBandLookups(context, tp, band_identifier)

            if band in band_identifier:
                for i in date_indices:
                    profile: dict = tp[TemporalProfileUtils.Values][i]
                    sidx = tp[TemporalProfileUtils.Sensor][i]
                    bidx = band_lookups[sidx][band]
                    y_values.append(profile[bidx])
            else:
                assert band in indices, f'Unknown band / spectral index: {band}'
                index_info: dict = indices[band]
                required_bands = index_info['bands']

                for i in date_indices:
                    profile: dict = tp[TemporalProfileUtils.Values][i]
                    sidx = tp[TemporalProfileUtils.Sensor][i]

                    params = {}
                    for b in required_bands:
                        if b in constants:
                            params[b] = constants[b]['value']
                        else:
                            bidx = band_lookups[sidx][b]
                            params[b] = profile[bidx]

                    result_value = eval(index_info["formula"], {}, params)
                    y_values.append(result_value)
        else:
            raise NotImplementedError

        if len(y_values) == 1:
            y_values = y_values[0]

        return y_values
