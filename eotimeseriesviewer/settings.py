
import os, enum, pathlib, re, json
from collections import namedtuple
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *

from eotimeseriesviewer import *
from eotimeseriesviewer.utils import loadUI
from eotimeseriesviewer.timeseries import SensorMatching, SensorInstrument




class Keys(enum.Enum):
    """
    Enumeration of settings keys.
    """
    DateTimePrecision = 'date_time_precision'
    MapSize = 'map_size'
    MapUpdateInterval = 'map_update_interval'
    MapBackgroundColor = 'map_background_color'
    MapTextFormat = 'map_text_format'
    SensorSpecs = 'sensor_specs'
    SensorMatching = 'sensor_matching'
    ScreenShotDirectory = 'screen_shot_directory'
    RasterSourceDirectory = 'raster_source_directory'
    VectorSourceDirectory = 'vector_source_directory'
    MapImageExportDirectory = 'map_image_export_directory'



def defaultValues() -> dict:
    """
    Returns the official hard-coded dictionary of default values.
    :return: dict
    """
    d = dict()
    from eotimeseriesviewer.timeseries import DateTimePrecision

    # general settings
    home = pathlib.Path.home()
    d[Keys.ScreenShotDirectory] = str(home)
    d[Keys.RasterSourceDirectory] = str(home)
    d[Keys.VectorSourceDirectory] = str(home)
    d[Keys.DateTimePrecision] = DateTimePrecision.Day
    d[Keys.SensorSpecs] = dict()
    d[Keys.SensorMatching] = SensorMatching.DIMS_WL_Name

    # map visualization
    d[Keys.MapUpdateInterval] = 500  # milliseconds
    d[Keys.MapSize] = QSize(150, 150)
    d[Keys.MapBackgroundColor] = QColor('black')

    textFormat = QgsTextFormat()
    textFormat.setColor(QColor('black'))
    textFormat.setSizeUnit(QgsUnitTypes.RenderPoints)
    textFormat.setFont(QFont('Helvetica'))
    textFormat.setSize(11)

    buffer = QgsTextBufferSettings()
    buffer.setColor(QColor('white'))
    buffer.setSize(5)
    buffer.setSizeUnit(QgsUnitTypes.RenderPixels)
    buffer.setEnabled(True)
    textFormat.setBuffer(buffer)

    d[Keys.MapTextFormat] = textFormat


    # tbd. other settings

    return d


DEFAULT_VALUES = defaultValues()



def settings()->QSettings:
    """
    Returns the EOTSV settings.
    :return: QSettings
    """
    settings = QSettings(QSettings.UserScope, 'HU-Berlin', 'EO-TimeSeriesViewer')

    return settings


def value(key:Keys, default=None):
    """
    Provides direct access to a settings value
    :param key: Keys
    :param default: default value, defaults to None
    :return: value | None
    """
    assert isinstance(key, Keys)
    value = None
    try:
        value = settings().value(key.value, defaultValue=default)

        if value == QVariant():
            value = None

        if value and key == Keys.MapTextFormat:
           s = ""

        if isinstance(value, str) and key == Keys.SensorSpecs:
            value = json.loads(value)
            assert isinstance(value, dict)
            for k in value.keys():
                if not isinstance(value[k], dict):
                    value[k] = {'name': None}


    except TypeError as error:
        value = None
        settings().setValue(key.value, None)
        print(error, file=sys.stderr)
    return value


def saveSensorName(sensor:SensorInstrument):
    """
    Saves the sensor name
    :param sensor: SensorInstrument
    :return:
    """
    assert isinstance(sensor, SensorInstrument)

    sensorSpecs = value(Keys.SensorSpecs, default=dict())
    assert isinstance(sensorSpecs, dict)

    sSpecs = sensorSpecs.get(sensor.id(), dict())
    sSpecs['name'] = sensor.name()

    sensorSpecs[sensor.id()] = sSpecs

    setValue(Keys.SensorSpecs, sensorSpecs)

def sensorName(id:str)->str:
    """
    Retuns the sensor name stored for a certain sensor id
    :param id: str
    :return: str
    """
    if isinstance(id, SensorInstrument):
        id = id.id()

    sensorSpecs = value(Keys.SensorSpecs, default=dict())
    assert isinstance(sensorSpecs, dict)
    sSpecs = sensorSpecs.get(id, dict())
    return sSpecs.get('name', None)




def setValue(key:Keys, value):
    """
    Shortcut to save a value into the EOTSV settings
    :param key: str | Key
    :param value: any value
    """
    assert isinstance(key, Keys)

    if isinstance(value, QgsTextFormat):
        value = value.toMimeData()

    if isinstance(value, dict) and key == Keys.SensorSpecs:
        settings().setValue(key.value, json.dumps(value))

    settings().setValue(key.value, value)



def setValues(values: dict):
    """
    Writes the EOTSV settings
    :param values: dict
    :return:
    """
    assert isinstance(values, dict)
    for key, val in values.items():
        setValue(key, val)

class SensorSettingsTableModel(QAbstractTableModel):
    """
    A table to visualize sensor-specific settings
    """
    def __init__(self):
        super(SensorSettingsTableModel, self).__init__()

        self.mSensors = []
        self.mCNKey = 'Key'
        self.mCNName = 'Name'
        self.loadSettings()

    def clear(self):
        """Removes all entries"""
        self.removeRows(0, self.rowCount())
        assert len(self.mSensors) == 0

    def reload(self):
        """
        Reloads the entire table
        :return:
        """
        self.clear()
        self.loadSettings()

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:

        if count > 0:
            self.beginRemoveRows(parent, row, row+count-1)

            for i in reversed(range(row, row+count)):
                del self.mSensors[i]

            self.endRemoveRows()

    def loadSettings(self):
        sensorSpecs = value(Keys.SensorSpecs, default={})

        sensors = []
        for id, specs in sensorSpecs.items():
            sensor = SensorInstrument(id)
            sensor.setName(specs['name'])
            sensors.append(sensor)
        self.addSensors(sensors)

    def removeSensors(self, sensors:typing.List[SensorInstrument]):
        assert isinstance(sensors, list)
        n = len(sensors)

        if n > 0:
            self.beginInsertRows(QModelIndex(), self.rowCount() - 1, self.rowCount() - 1 + n)
            self.mSensors.extend(sensors)
            self.endInsertRows()


    def addSensors(self, sensors:typing.List[SensorInstrument]):
        assert isinstance(sensors, list)
        n = len(sensors)

        if n > 0:
            self.beginInsertRows(QModelIndex(), self.rowCount()-1, self.rowCount() -1 + n)
            self.mSensors.extend(sensors)
            self.endInsertRows()

    def saveSettings(self):

        specs = dict()
        for sensor in self.mSensors:
            assert isinstance(sensor, SensorInstrument)
            specs[sensor.id()] = sensor.name()
        setValue(Keys.SensorSpecs, specs)

    def rowCount(self, parent: QModelIndex = QModelIndex())->int:
        return len(self.mSensors)

    def columnNames(self)->typing.List[str]:
        return [self.mCNKey, self.mCNName]

    def columnCount(self, parent: QModelIndex):
        return len(self.columnNames())

    def flags(self, index: QModelIndex):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        cn = self.columnNames()[index.column()]
        if cn == self.mCNName:
            flags = flags | Qt.ItemIsEditable

        return flags

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames()[section]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return section + 1
        else:
            return None

    def sensor(self, index)->SensorInstrument:
        if isinstance(index, int):
            return self.mSensors[index]
        else:
            return self.mSensors[index.row()]

    def data(self, index: QModelIndex, role: int):

        if not index.isValid():
            return None

        sensor = self.sensor(index)
        cn = self.columnNames()[index.column()]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if cn == self.mCNName:
                return sensor.name()
            if cn == self.mCNKey:
                return sensor.id()

        if role == Qt.BackgroundColorRole and not (self.flags(index) & Qt.ItemIsEditable):
            return QColor('gray')


        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return False

        changed = False
        sensor = self.sensor(index)
        cn = self.columnNames()[index.column()]

        if cn == self.mCNName and isinstance(value, str):
            sensor.setName(value)
            changed = True

        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed



class SettingsDialog(QDialog, loadUI('settingsdialog.ui')):
    """
    A widget to change settings
    """

    def __init__(self, title='<#>', parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setupUi(self)

        assert isinstance(self.cbDateTimePrecission, QComboBox)
        from eotimeseriesviewer.timeseries import DateTimePrecision
        for e in DateTimePrecision:
            assert isinstance(e, enum.Enum)
            self.cbDateTimePrecission.addItem(e.name, e)

        for e in SensorMatching:
            assert isinstance(e, enum.Enum)
            self.cbSensorMatching.addItem(e.value, e)

        self.mFileWidgetScreenshots.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetRasterSources.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetVectorSources.setStorageMode(QgsFileWidget.GetDirectory)

        self.cbDateTimePrecission.currentIndexChanged.connect(self.validate)
        self.cbSensorMatching.currentIndexChanged.connect(self.validate)
        self.sbMapSizeX.valueChanged.connect(self.validate)
        self.sbMapSizeY.valueChanged.connect(self.validate)
        self.sbMapRefreshIntervall.valueChanged.connect(self.validate)

        self.mMapTextFormatButton.changed.connect(self.validate)

        assert isinstance(self.buttonBox, QDialogButtonBox)
        self.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(lambda: self.setValues(defaultValues()))
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.onAccept)
        self.buttonBox.button(QDialogButtonBox.Cancel)

        self.mLastValues = dict()

        self.mSensorSpecsModel = SensorSettingsTableModel()
        self.mSensorSpecsProxyModel = QSortFilterProxyModel()
        self.mSensorSpecsProxyModel.setSourceModel(self.mSensorSpecsModel)

        self.tableViewSensorSettings.setModel(self.mSensorSpecsProxyModel)
        sm = self.tableViewSensorSettings.selectionModel()
        assert isinstance(sm, QItemSelectionModel)
        sm.selectionChanged.connect(self.onSensorSettingsSelectionChanged)

        self.btnDeleteSelectedSensors.setDefaultAction(self.actionDeleteSelectedSensors)
        self.btnReloadSensorSettings.setDefaultAction(self.actionRefreshSensorList)
        self.actionRefreshSensorList.triggered.connect(self.mSensorSpecsModel.reload)

        self.actionDeleteSelectedSensors.triggered.connect(self.onRemoveSelectedSensors)
        self.actionDeleteSelectedSensors.setEnabled(len(sm.selectedRows()) > 0)
        self.mSensorSpecsModel.clear()
        self.setValues(settings())


    def onRemoveSelectedSensors(self):

        sm = self.tableViewSensorSettings.selectionModel()
        assert isinstance(sm, QItemSelectionModel)

        for r in sm.selectedRows():
            s = ""

    def onSensorSettingsSelectionChanged(self, selected:QItemSelection, deselected:QItemSelection):
        self.actionDeleteSelectedSensors.setEnabled(len(selected) > 0)

    def validate(self, *args):

        values = self.values()

    def onAccept(self):

        self.setResult(QDialog.Accepted)

        values = self.values()
        setValues(values)

        self.mSensorSpecsModel.saveSettings()

        if values != self.mLastValues:

            pass

    def values(self)->dict:
        """
        Returns the settings as dictionary
        :return: dict
        """
        d = dict()

        d[Keys.ScreenShotDirectory] = self.mFileWidgetScreenshots.filePath()
        d[Keys.RasterSourceDirectory] = self.mFileWidgetRasterSources.filePath()
        d[Keys.VectorSourceDirectory] = self.mFileWidgetVectorSources.filePath()

        d[Keys.DateTimePrecision] = self.cbDateTimePrecission.currentData()
        d[Keys.SensorMatching] = self.cbSensorMatching.currentData()
        d[Keys.MapSize] = QSize(self.sbMapSizeX.value(), self.sbMapSizeY.value())
        d[Keys.MapUpdateInterval] = self.sbMapRefreshIntervall.value()
        d[Keys.MapBackgroundColor] = self.mCanvasColorButton.color()
        d[Keys.MapTextFormat] = self.mMapTextFormatButton.textFormat()

        return d

    def setValues(self, values: dict):
        """
        Sets the values as stored in a dictionary or QSettings object
        :param values: dict | QSettings
        """

        if isinstance(values, QSettings):
            d = dict()
            for k in values.allKeys():
                try:
                    d[k] = values.value(k)
                except Exception as ex:
                    s = "" #TypeError: unable to convert a QVariant back to a Python object
            values = d

        assert isinstance(values, dict)

        def checkKey(val, key:Keys):
            assert isinstance(key, Keys)
            return val in [key, key.value, key.name]

        for key, value in values.items():
            if checkKey(key, Keys.ScreenShotDirectory) and isinstance(value, str):
                self.mFileWidgetScreenshots.setFilePath(value)
            if checkKey(key, Keys.RasterSourceDirectory) and isinstance(value, str):
                self.mFileWidgetRasterSources.setFilePath(value)
            if checkKey(key, Keys.VectorSourceDirectory) and isinstance(value, str):
                self.mFileWidgetVectorSources.setFilePath(value)

            if checkKey(key, Keys.DateTimePrecision):
                i = self.cbDateTimePrecission.findData(value)
                if i > -1:
                    self.cbDateTimePrecission.setCurrentIndex(i)

            if checkKey(key, Keys.SensorMatching):
                i = self.cbSensorMatching.findData(value)
                if i > -1:
                    self.cbSensorMatching.setCurrentIndex(i)

            if checkKey(key, Keys.MapSize) and isinstance(value, QSize):
                self.sbMapSizeX.setValue(value.width())
                self.sbMapSizeY.setValue(value.height())

            if checkKey(key, Keys.MapUpdateInterval) and isinstance(value, (float, int)) and value > 0:
                self.sbMapRefreshIntervall.setValue(value)

            if checkKey(key, Keys.MapBackgroundColor) and isinstance(value, QColor):
                self.mCanvasColorButton.setColor(value)

            if checkKey(key, Keys.MapTextFormat) and isinstance(value, QgsTextFormat):
                self.mMapTextFormatButton.setTextFormat(value)



