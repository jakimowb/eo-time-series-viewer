import typing
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
import numpy as np

from .utils import UnitLookup, METRIC_EXPONENTS, datetime64

BAND_INDEX = 'Band Index'

class UnitModel(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mUnits = []
        self.mDescription = dict()
        self.mToolTips = dict()

    def rowCount(self, parent=None, *args, **kwargs) -> int:
        return len(self.mUnits)

    def findUnit(self, value: str) -> str:
        """
        Returns a matching unit string, e.g. nm for Nanometers
        :param value:
        :return:
        """
        if not isinstance(value, str):
            return None

        if value in self.mUnits:
            return value

        baseUnit = UnitLookup.baseUnit(value)
        if baseUnit in self.mUnits:
            return baseUnit

        value = value.lower()
        for u, v in self.mDescription.items():
            if v.lower() == value:
                return u

        for u, v in self.mToolTips.items():
            if v.lower() == value:
                return u

        return None

    def removeUnit(self, unit: str):
        """
        Removes a unit from this model
        :param unit: str
        """
        unit = self.findUnit(unit)
        if isinstance(unit, str) and unit in self.mUnits:
            row = self.mUnits.index(unit)
            self.beginRemoveRows(QModelIndex(), row, row)

            if unit in self.mToolTips.keys():
                self.mToolTips.pop(unit)
            if unit in self.mDescription.keys():
                self.mDescription.pop(unit)
            self.mUnits.remove(unit)
            self.endRemoveRows()

    def addUnit(self, unit: str,
                description: str = None,
                tooltip: str = None,
                aliases: typing.List[str] = []):
        """
        Adds a unit to the unit model
        :param unit:
        :type unit:
        :param description:
        :type description:
        :param tooltip:
        :type tooltip:
        :return:
        :rtype:
        """
        if unit not in self.mUnits:

            r = len(self.mUnits)
            self.beginInsertRows(QModelIndex(), r, r)
            self.mUnits.append(unit)
            if isinstance(description, str):
                self.mDescription[unit] = description
            if isinstance(tooltip, str):
                self.mToolTips[unit] = tooltip
            self.endInsertRows()

    def unitIndex(self, unit: str) -> QModelIndex:
        """
        Returns the QModelIndex of a unit.
        :param unit:
        :type unit:
        :return:
        :rtype:
        """
        unit = self.findUnit(unit)
        row = self.mUnits.index(unit)
        return self.createIndex(row, 0, unit)

    def unitData(self, unit: str, role=Qt.DisplayRole):
        """
        Convenience function to access unit metadata
        :param unit:
        :type unit:
        :param role:
        :type role:
        :return:
        :rtype:
        """
        return self.data(self.unitIndex(unit), role=role)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        unit = self.mUnits[index.row()]

        if role == Qt.DisplayRole:
            return self.mDescription.get(unit, unit)
        if role == Qt.ToolTipRole:
            return self.mToolTips.get(unit, unit)
        if role == Qt.UserRole:
            return unit


class UnitConverterFunctionModel(object):

    def __init__(self):

        # look-up table with functions to conver from unit1 to unit2, with unit1 != unit2 and
        # unit1 != None and unit2 != None
        self.mLUT = dict()

        self.func_return_band_index = lambda v, *args: np.arange(len(v))
        self.func_return_none = lambda v, *args: None
        self.func_return_same = lambda v, *args: v
        self.func_return_decimalyear = lambda v, *args: UnitLookup.convertDateUnit(v, 'DecimalYear')

        # metric units
        for u1, e1 in METRIC_EXPONENTS.items():
            for u2, e2 in METRIC_EXPONENTS.items():
                key = (u1, u2)
                if key not in self.mLUT.keys():
                    if u1 != u2:
                        self.mLUT[key] = lambda v, *args, k1=u1, k2=u2: UnitLookup.convertMetricUnit(v, k1, k2)

        # time units
        # convert between DecimalYear and DateTime stamp
        self.mLUT[('DecimalYear', 'DateTime')] = lambda v, *args: datetime64(v)
        self.mLUT[('DateTime', 'DecimalYear')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DecimalYear')

        # convert to DOY (reversed operation is not possible)
        self.mLUT[('DecimalYear', 'DOY')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DOY')
        self.mLUT[('DateTime', 'DOY')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DOY')

    def convertFunction(self, unitSrc: str, unitDst: str):
        if unitDst == BAND_INDEX:
            return self.func_return_band_index
        unitSrc = UnitLookup.baseUnit(unitSrc)
        unitDst = UnitLookup.baseUnit(unitDst)
        if unitSrc is None or unitDst is None:
            return self.func_return_none
        if unitSrc == unitDst:
            return self.func_return_same
        key = (unitSrc, unitDst)
        if key not in self.mLUT.keys():
            s = ""
        return self.mLUT.get((unitSrc, unitDst), self.func_return_none)


class XUnitModel(UnitModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.addUnit(BAND_INDEX, description=BAND_INDEX)
        for u in ['Nanometers',
                  'Micrometers',
                  'Millimeters',
                  'Meters',
                  'Kilometers']:
            baseUnit = UnitLookup.baseUnit(u)
            assert isinstance(baseUnit, str), u
            self.addUnit(baseUnit, description='{} [{}]'.format(u, baseUnit))

        self.addUnit('DateTime', description='Date')
        self.addUnit('DecimalYear', description='Date [Decimal Year]')
        self.addUnit('DOY', description='Day of Year [DOY]')

    def findUnit(self, unit):
        if unit in [None, NULL]:
            unit = BAND_INDEX
        return super(XUnitModel, self).findUnit(unit)