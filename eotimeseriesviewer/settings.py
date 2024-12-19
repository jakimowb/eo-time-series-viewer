import enum
import pathlib
import sys
from json import JSONDecodeError
from typing import Any, List, Union

from osgeo import gdal

from qgis.PyQt.QtGui import QColor, QFont, QPen
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from qgis.PyQt.QtCore import QAbstractTableModel, QByteArray, QItemSelection, QItemSelectionModel, QModelIndex, \
    QSettings, QSize, QSortFilterProxyModel, Qt, QVariant
from qgis.PyQt.QtWidgets import QComboBox, QDialog, QDialogButtonBox
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsReadWriteContext, QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes
from qgis.gui import QgsFileWidget
from eotimeseriesviewer import __version__ as EOTSV_VERSION, DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi
from eotimeseriesviewer.timeseries import SensorInstrument, SensorMatching


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
    SettingsVersion = 'settings_version'
    ProfileStyleCurrent = 'profile_style_current'
    ProfileStyleAdded = 'profile_style_added'
    ProfileStyleTemporal = 'profile_style_temporal'
    Debug = 'debug'
    QgsTaskAsync = 'qgs_task_async'
    QgsTaskBlockSize = 'qgs_task_block_size'
    BandStatsSampleSize = 'band_stats_sample_size'
    RasterOverlapSampleSize = 'raster_overlap_sample_size'
    StartupRestoreProjectSettings = 'startup_load_projectsettings'


def defaultValues() -> dict:
    """
    Returns the official hard-coded dictionary of default values.
    :return: dict
    """
    d = dict()
    from eotimeseriesviewer.dateparser import DateTimePrecision

    # general settings
    home = pathlib.Path.home()
    d[Keys.ScreenShotDirectory] = str(home)
    d[Keys.RasterSourceDirectory] = str(home)
    d[Keys.VectorSourceDirectory] = str(home)
    d[Keys.DateTimePrecision] = DateTimePrecision.Day
    # d[Keys.SensorSpecs] = dict() # no default sensors
    d[Keys.SensorMatching] = SensorMatching.PX_DIMS
    import eotimeseriesviewer
    d[Keys.Debug] = eotimeseriesviewer.DEBUG

    # map visualization
    d[Keys.MapUpdateInterval] = 500  # milliseconds
    d[Keys.MapSize] = QSize(150, 150)
    d[Keys.MapBackgroundColor] = QColor('black')

    # Profiles
    stylec = PlotStyle()
    stylec.setLinePen(QPen(QColor('green')))
    stylec.setMarkerColor('green')

    style = PlotStyle()
    style.setMarkerColor('grey')
    style.setLinePen(QPen(QColor('grey')))

    d[Keys.ProfileStyleCurrent] = stylec
    d[Keys.ProfileStyleAdded] = style
    d[Keys.ProfileStyleTemporal] = style

    d[Keys.QgsTaskAsync] = True
    d[Keys.QgsTaskBlockSize] = 25
    d[Keys.BandStatsSampleSize] = 256
    d[Keys.RasterOverlapSampleSize] = 25

    d[Keys.StartupRestoreProjectSettings] = True

    d[Keys.SettingsVersion] = EOTSV_VERSION
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


def settings() -> QSettings:
    """
    Returns the EOTSV settings.
    :return: QSettings
    """
    settings = QSettings(QSettings.UserScope, 'HU-Berlin', 'EO-TimeSeriesViewer')

    return settings


if (not settings().contains(Keys.SettingsVersion.value)) or \
        str(settings().value(Keys.SettingsVersion.value)) < '1.10.2020':
    # addresses issue https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/103/tsv-crashes-qgis-on-linux
    # which was caused by a wrong serialization of a QgsTextFormat object
    settings().setValue(Keys.MapTextFormat.value, None)


def value(key: Keys, default=None):
    """
    Provides direct access to a settings value
    :param key: Keys
    :param default: default value, defaults to None
    :return: value | None
    """
    assert isinstance(key, Keys)
    assert isinstance(key.value, str)
    value = None
    try:
        value = settings().value(key.value, defaultValue=default)

        if value == QVariant():
            value = None
        if value == 'true':
            value = True
        elif value == 'false':
            value = False

        if key == Keys.MapTextFormat:
            if isinstance(value, QByteArray):
                doc = QDomDocument()
                doc.setContent(value)
                value = QgsTextFormat()
                value.readXml(doc.documentElement(), QgsReadWriteContext())

        if key == Keys.QgsTaskAsync:
            value = bool(value)

        if key == Keys.QgsTaskBlockSize:
            value = int(value)

        if key == Keys.BandStatsSampleSize:
            value = int(value)

        if key == Keys.RasterOverlapSampleSize:
            value = int(value)

        if key == Keys.MapUpdateInterval:
            value = int(value)

        if key == Keys.SensorSpecs:
            # check sensor specs
            if value is None:
                value = dict()

            assert isinstance(value, dict)

            for sensorID in list(value.keys()):
                assert isinstance(sensorID, str)
                try:
                    sensorSpecs = value[sensorID]
                    if not isinstance(sensorSpecs, dict):
                        value[sensorSpecs] = {'name': None}
                except (AssertionError, JSONDecodeError) as ex:
                    # delete old-style settings
                    del value[sensorID]

        if key in [Keys.ProfileStyleAdded,
                   Keys.ProfileStyleCurrent,
                   Keys.ProfileStyleTemporal]:
            if isinstance(value, str):
                value = PlotStyle.fromJSON(value)

    except TypeError as error:
        value = None
        settings().setValue(key.value, None)
        print(error, file=sys.stderr)
    except Exception as otherError:
        s = ""
    if value is None:
        value = default
    return value


def saveSensorName(sensor: SensorInstrument):
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


def sensorName(sid: Union[str, SensorInstrument]) -> str:
    """
    Retuns the sensor name stored for a certain sensor id
    :param sid: str
    :return: str
    """
    if isinstance(sid, SensorInstrument):
        sid = sid.id()

    sensorSpecs = value(Keys.SensorSpecs, default=dict())
    assert isinstance(sensorSpecs, dict)
    sSpecs = sensorSpecs.get(sid, dict())
    return sSpecs.get('name', None)


def setValue(key: Keys, value):
    """
    Shortcut to save a value into the EOTSV settings
    :param key: str | Key
    :param value: any value
    """
    assert isinstance(key, Keys)
    assert isinstance(key.value, str)

    if isinstance(value, QgsTextFormat):
        # make QgsTextFormat pickable
        doc = QDomDocument()
        doc.appendChild(value.writeXml(doc, QgsReadWriteContext()))
        value = doc.toByteArray()

    if key == Keys.SensorSpecs:
        s = ""

    if key in [Keys.ProfileStyleCurrent,
               Keys.ProfileStyleTemporal,
               Keys.ProfileStyleAdded]:
        if isinstance(value, PlotStyle):
            value = value.json()
    # if isinstance(value, dict) and key == Keys.SensorSpecs:
    #   settings().setValue(key.value, value)

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
    settings().sync()


def values() -> dict:
    """
    Returns all settings in a dictionary
    :return: dict
    :rtype: dict
    """
    d = dict()
    for key in Keys:
        assert isinstance(key, Keys)
        d[key] = value(key)
    return d


class SensorSettingsTableModel(QAbstractTableModel):
    """
    A table to visualize sensor-specific settings
    """

    def __init__(self):
        super(SensorSettingsTableModel, self).__init__()

        self.mSensors = []
        self.mCNKey = 'Specification'
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
            self.beginRemoveRows(parent, row, row + count - 1)

            for i in reversed(range(row, row + count)):
                del self.mSensors[i]

            self.endRemoveRows()

    def loadSettings(self):
        sensorSpecs = value(Keys.SensorSpecs, default={})

        sensors = []
        for sid, specs in sensorSpecs.items():
            sensor = SensorInstrument(sid)
            sensor.setName(specs['name'])
            sensors.append(sensor)
        self.addSensors(sensors)

    def removeSensors(self, sensors: List[SensorInstrument]):
        assert isinstance(sensors, list)

        for sensor in sensors:
            assert isinstance(sensor, SensorInstrument)
            idx = self.sensor2idx(sensor)
            self.beginRemoveRows(QModelIndex(), idx.row(), idx.row())
            self.mSensors.remove(sensor)
            self.endRemoveRows()

    def sensor2idx(self, sensor: SensorInstrument) -> QModelIndex:

        if sensor not in self.mSensors:
            return QModelIndex()
        row = self.mSensors.index(sensor)
        return self.createIndex(row, 0, sensor)

    def addSensors(self, sensors: List[SensorInstrument]):
        assert isinstance(sensors, list)
        n = len(sensors)

        if n > 0:
            self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount() + n - 1)
            self.mSensors.extend(sensors)
            self.endInsertRows()

    def setSpecs(self, specs: dict):
        sensors = []
        for sid, sensorSpecs in specs.items():
            assert isinstance(sid, str)
            assert isinstance(sensorSpecs, dict)
            sensor = SensorInstrument(sid)
            # apply specs to sensor instance
            sensor.setName(sensorSpecs.get('name', sensor.name()))
            sensors.append(sensor)
        self.clear()
        self.addSensors(sensors)

    def specs(self) -> dict:
        """
        Returns the specifications for each stored sensor
        :return:
        :rtype:
        """
        specs = dict()
        for sensor in self.mSensors:
            assert isinstance(sensor, SensorInstrument)
            s = {'name': sensor.name()}
            specs[sensor.id()] = s
        return specs

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.mSensors)

    def columnNames(self) -> List[str]:
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

    def sensor(self, index) -> SensorInstrument:
        if isinstance(index, int):
            return self.mSensors[index]
        else:
            return self.mSensors[index.row()]

    def sensorIDDisplayString(self, sensor: SensorInstrument) -> str:
        """
        Returns a short representation of the sensor id, e.g. "6bands(Int16)@30m"
        :param sensor:
        :type sensor:
        :return:
        :rtype:
        """
        assert isinstance(sensor, SensorInstrument)

        s = '{}band({})@{}m'.format(sensor.nb, gdal.GetDataTypeName(sensor.dataType), sensor.px_size_x)
        if sensor.wl is not None and sensor.wlu is not None:
            if sensor.nb == 1:
                s += ',{}{}'.format(sensor.wl[0], sensor.wlu)
            else:
                s += ',{}-{}{}'.format(sensor.wl[0], sensor.wl[-1], sensor.wlu)
        return s

    def data(self, index: QModelIndex, role: int):

        if not index.isValid():
            return None

        sensor = self.sensor(index)
        cn = self.columnNames()[index.column()]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if cn == self.mCNName:
                return sensor.name()
            if cn == self.mCNKey:
                return self.sensorIDDisplayString(sensor)

        if role in [Qt.ToolTipRole]:
            if cn == self.mCNName:
                return sensor.name()
            if cn == self.mCNKey:
                return sensor.id().replace(', "', '\n "')

        if role == Qt.BackgroundColorRole and not (self.flags(index) & Qt.ItemIsEditable):
            return QColor('gray')

        if role == Qt.UserRole:
            return sensor

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = ...) -> bool:

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


class SettingsDialog(QDialog):
    """
    A widget to change settings
    """

    def __init__(self, title='<#>', parent=None):
        super(SettingsDialog, self).__init__(parent)
        loadUi(DIR_UI / 'settingsdialog.ui', self)

        assert isinstance(self.cbDateTimePrecission, QComboBox)
        from eotimeseriesviewer.dateparser import DateTimePrecision
        for e in DateTimePrecision:
            assert isinstance(e, enum.Enum)
            self.cbDateTimePrecission.addItem(e.name, e)

        self.cbSensorMatchingPxDims.setToolTip(SensorMatching.tooltip(SensorMatching.PX_DIMS))
        self.cbSensorMatchingWavelength.setToolTip(SensorMatching.tooltip(SensorMatching.WL))
        self.cbSensorMatchingSensorName.setToolTip(SensorMatching.tooltip(SensorMatching.NAME))
        self.cbSensorMatchingPxDims.stateChanged.connect(self.validate)
        self.cbSensorMatchingWavelength.stateChanged.connect(self.validate)
        self.cbSensorMatchingSensorName.stateChanged.connect(self.validate)

        self.cbDebug.stateChanged.connect(self.validate)

        self.mFileWidgetScreenshots.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetRasterSources.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetVectorSources.setStorageMode(QgsFileWidget.GetDirectory)

        self.cbDateTimePrecission.currentIndexChanged.connect(self.validate)

        self.sbMapSizeX.valueChanged.connect(self.validate)
        self.sbMapSizeY.valueChanged.connect(self.validate)
        self.sbMapRefreshIntervall.valueChanged.connect(self.validate)

        self.mMapTextFormatButton.changed.connect(self.validate)

        assert isinstance(self.buttonBox, QDialogButtonBox)
        self.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(lambda: self.setValues(defaultValues()))
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.onAccept)
        self.buttonBox.button(QDialogButtonBox.Cancel)

        self.mLastValues = values()

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
        self.setValues(self.mLastValues)

    def onRemoveSelectedSensors(self):

        sm = self.tableViewSensorSettings.selectionModel()
        assert isinstance(sm, QItemSelectionModel)

        toRemove = []
        for r in sm.selectedRows():
            srcIdx = self.tableViewSensorSettings.model().mapToSource(r)
            sensor = srcIdx.data(role=Qt.UserRole)
            if isinstance(sensor, SensorInstrument):
                toRemove.append(sensor)
        if len(toRemove) > 0:
            self.mSensorSpecsModel.removeSensors(toRemove)

    def onSensorSettingsSelectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        self.actionDeleteSelectedSensors.setEnabled(len(selected) > 0)

    def validate(self, *args):

        values = self.values()
        if Keys.Debug in values.keys():
            import eotimeseriesviewer
            eotimeseriesviewer.DEBUG = values[Keys.Debug]

    def onAccept(self):

        self.setResult(QDialog.Accepted)

        values = self.values()
        setValues(values)

        # self.mSensorSpecsModel.saveSettings()

        if values != self.mLastValues:
            pass

    def values(self) -> dict:
        """
        Returns the settings as dictionary
        :return: dict
        """
        d = dict()

        d[Keys.ScreenShotDirectory] = self.mFileWidgetScreenshots.filePath()
        d[Keys.RasterSourceDirectory] = self.mFileWidgetRasterSources.filePath()
        d[Keys.VectorSourceDirectory] = self.mFileWidgetVectorSources.filePath()

        d[Keys.DateTimePrecision] = self.cbDateTimePrecission.currentData()

        flags = SensorMatching.PX_DIMS
        if self.cbSensorMatchingWavelength.isChecked():
            flags = flags | SensorMatching.WL
        if self.cbSensorMatchingSensorName.isChecked():
            flags = flags | SensorMatching.NAME

        d[Keys.StartupRestoreProjectSettings] = self.cbStartupRestoreSettings.isChecked()

        d[Keys.SensorMatching] = flags

        d[Keys.SensorSpecs] = self.mSensorSpecsModel.specs()
        d[Keys.MapSize] = QSize(self.sbMapSizeX.value(), self.sbMapSizeY.value())
        d[Keys.MapUpdateInterval] = self.sbMapRefreshIntervall.value()
        d[Keys.MapBackgroundColor] = self.mCanvasColorButton.color()
        d[Keys.MapTextFormat] = self.mMapTextFormatButton.textFormat()

        # profiles
        d[Keys.ProfileStyleCurrent] = self.btnProfileCurrent.plotStyle()
        d[Keys.ProfileStyleAdded] = self.btnProfileAdded.plotStyle()
        d[Keys.ProfileStyleTemporal] = self.btnProfileTemporal.plotStyle()

        # others page
        d[Keys.Debug] = self.cbDebug.isChecked()
        d[Keys.QgsTaskAsync] = self.cbAsyncQgsTasks.isChecked()
        d[Keys.QgsTaskBlockSize] = self.sbQgsTaskBlockSize.value()
        d[Keys.BandStatsSampleSize] = self.sbBandStatsSampleSize.value()
        d[Keys.RasterOverlapSampleSize] = self.sbRasterOverlapSampleSize.value()

        for k in self.mLastValues.keys():
            if k not in d.keys():
                d[k] = self.mLastValues[k]

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
                    s = ""  # TypeError: unable to convert a QVariant back to a Python object
            values = d

        assert isinstance(values, dict)

        def checkKey(val, key: Keys):
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

            if checkKey(key, Keys.StartupRestoreProjectSettings):
                self.cbStartupRestoreSettings.setChecked(bool(value in [True, 'true', 'True']))

            if checkKey(key, Keys.SensorMatching):
                assert isinstance(value, SensorMatching)
                self.cbSensorMatchingPxDims.setChecked(bool(value & SensorMatching.PX_DIMS))
                self.cbSensorMatchingWavelength.setChecked(bool(value & SensorMatching.WL))
                self.cbSensorMatchingSensorName.setChecked(bool(value & SensorMatching.NAME))

            if checkKey(key, Keys.SensorSpecs):
                assert isinstance(value, dict)
                self.mSensorSpecsModel.setSpecs(value)

            if checkKey(key, Keys.MapSize) and isinstance(value, QSize):
                self.sbMapSizeX.setValue(value.width())
                self.sbMapSizeY.setValue(value.height())

            if checkKey(key, Keys.MapUpdateInterval) and isinstance(value, (float, int)) and value > 0:
                self.sbMapRefreshIntervall.setValue(value)

            if checkKey(key, Keys.MapBackgroundColor) and isinstance(value, QColor):
                self.mCanvasColorButton.setColor(value)

            if checkKey(key, Keys.MapTextFormat) and isinstance(value, QgsTextFormat):
                self.mMapTextFormatButton.setTextFormat(value)

            # others page
            if checkKey(key, Keys.Debug) and isinstance(value, bool):
                self.cbDebug.setChecked(value)

            if checkKey(key, Keys.QgsTaskAsync) and isinstance(value, bool):
                self.cbAsyncQgsTasks.setChecked(value)

            if checkKey(key, Keys.QgsTaskBlockSize) and isinstance(value, int):
                self.sbQgsTaskBlockSize.setValue(value)

            if checkKey(key, Keys.BandStatsSampleSize) and isinstance(value, int):
                self.sbBandStatsSampleSize.setValue(value)

            if checkKey(key, Keys.RasterOverlapSampleSize) and isinstance(value, int):
                self.sbRasterOverlapSampleSize.setValue(value)

            if checkKey(key, Keys.ProfileStyleCurrent) and isinstance(value, PlotStyle):
                self.btnProfileCurrent.setPlotStyle(value)

            if checkKey(key, Keys.ProfileStyleAdded) and isinstance(value, PlotStyle):
                self.btnProfileAdded.setPlotStyle(value)

            if checkKey(key, Keys.ProfileStyleTemporal) and isinstance(value, PlotStyle):
                self.btnProfileTemporal.setPlotStyle(value)
