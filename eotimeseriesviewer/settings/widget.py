#! python3  # noqa: E265

"""
    Plugin settings form integrated into QGIS 'Options' menu.
"""
import enum
from pathlib import Path
from typing import Any, List

from osgeo import gdal
from qgis.PyQt.QtCore import pyqtSignal, QAbstractTableModel, QItemSelection, QItemSelectionModel, QModelIndex, \
    QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QDesktopServices, QIcon
from qgis.gui import QgsColorButton, QgsFileWidget, QgsOptionsPageWidget, QgsOptionsWidgetFactory
# PyQGIS
from qgis.core import QgsApplication
from qgis.PyQt.Qt import QUrl

from eotimeseriesviewer import __version__, HOMEPAGE, icon, ISSUE_TRACKER, TITLE
from eotimeseriesviewer.dateparser import DateTimePrecision
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi
from eotimeseriesviewer.settings.settings import EOTSVSettings, EOTSVSettingsManager
from eotimeseriesviewer.sensors import SensorInstrument, SensorMatching
from eotimeseriesviewer.utils import setFontButtonPreviewBackgroundColor

# standard

path_ui = Path(__file__).parent / "settings.ui"


class EOTSVSettingsWidget(QgsOptionsPageWidget):
    """Settings form embedded into QGIS 'options' menu."""

    configChanged = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        loadUi(path_ui, self)
        # self.log = PlgLogger().log
        self.settingsManager = EOTSVSettingsManager()

        # header
        self.tbTitle.setText(f"{TITLE} - Version {__version__}")

        # customization
        self.btnHelp.setIcon(QIcon(QgsApplication.iconPath("mActionHelpContents.svg")))
        self.btnHelp.pressed.connect(lambda: QDesktopServices.openUrl(QUrl(HOMEPAGE)))

        self.btnReport.setIcon(
            QIcon(QgsApplication.iconPath("console/iconSyntaxErrorConsole.svg"))
        )
        self.btnReport.pressed.connect(lambda: QDesktopServices.openUrl(QUrl(f'{ISSUE_TRACKER}/new')))

        self.btnReset.setIcon(QIcon(QgsApplication.iconPath("mActionUndo.svg")))
        self.btnReset.pressed.connect(self.resetSettings)

        self.cbSensorMatchingPxDims.setToolTip(SensorMatching.tooltip(SensorMatching.PX_DIMS))
        self.cbSensorMatchingWavelength.setToolTip(SensorMatching.tooltip(SensorMatching.WL))
        self.cbSensorMatchingSensorName.setToolTip(SensorMatching.tooltip(SensorMatching.NAME))

        self.mFileWidgetScreenshots.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetRasterSources.setStorageMode(QgsFileWidget.GetDirectory)
        self.mFileWidgetVectorSources.setStorageMode(QgsFileWidget.GetDirectory)

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

        self.mCanvasColorButton: QgsColorButton
        self.mCanvasColorButton.colorChanged.connect(
            lambda c: setFontButtonPreviewBackgroundColor(c, self.mMapTextFormatButton))

        # load previously saved settings
        self.loadSettings()
        self.listWidget.setCurrentRow(0, QItemSelectionModel.Select)

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

    def apply(self):
        """
        Called to permanently apply the settings shown in the options page (e.g. \
        save them to QgsSettings objects). This is usually called when the options \
        dialog is accepted.
        """
        settings = self.settingsManager.settings()

        settings.dirScreenShots = Path(self.mFileWidgetScreenshots.filePath())
        settings.dirScreenShots = Path(self.mFileWidgetRasterSources.filePath())
        settings.dirScreenShots = Path(self.mFileWidgetVectorSources.filePath())

        settings.dateTimePrecision = self.cbDateTimePrecission.currentData()
        settings.restoreProjectSettings = self.cbStartupRestoreSettings.isChecked()

        sensorMatching = SensorMatching.PX_DIMS
        if self.cbSensorMatchingWavelength.isChecked():
            sensorMatching = sensorMatching | SensorMatching.WL
        if self.cbSensorMatchingSensorName.isChecked():
            sensorMatching = sensorMatching | SensorMatching.NAME
        settings.sensorMatching = sensorMatching

        settings.sensorSpecifications = self.mSensorSpecsModel.specs()

        settings.mapSize.setWidth(self.sbMapSizeX.value())
        settings.mapSize.setHeight(self.sbMapSizeY.value())

        settings.mapUpdateInterval = self.sbMapRefreshIntervall.value()
        settings.mapBackgroundColor = self.mCanvasColorButton.color()

        settings.mapTextFormat = self.mMapTextFormatButton.textFormat()

        # others page
        settings.debug = self.cbDebug.isChecked()

        settings.qgsTaskAsync = self.cbAsyncQgsTasks.isChecked()
        settings.qgsTaskFileReadingThreads = self.sbQgsTaskFileReadingThreads.value()
        settings.bandStatsSampleSize = self.sbBandStatsSampleSize.value()
        settings.rasterOverlapSampleSize = self.sbRasterOverlapSampleSize.value()
        settings.profileStyleCurrent = self.btnProfileCurrent.plotStyle()
        settings.profileStyleAdded = self.btnProfileAdded.plotStyle()

        settings.profileStyleTemporal = self.btnProfileTemporal.plotStyle()

        self.settingsManager.saveSettings(settings)

        self.configChanged.emit()

    def loadSettings(self):
        """Load options from QgsSettings into UI form."""
        settings: EOTSVSettings = self.settingsManager.settings()

        self.mFileWidgetScreenshots.setFilePath(str(settings.dirScreenShots))
        self.mFileWidgetRasterSources.setFilePath(str(settings.dirRasterSources))
        self.mFileWidgetVectorSources.setFilePath(str(settings.dirVectorSources))

        for e in DateTimePrecision:
            assert isinstance(e, enum.Enum)
            self.cbDateTimePrecission.addItem(e.name, e)

        i = self.cbDateTimePrecission.findData(settings.dateTimePrecision)
        if i > -1:
            self.cbDateTimePrecission.setCurrentIndex(i)

        self.cbStartupRestoreSettings.setChecked(settings.restoreProjectSettings)

        self.cbSensorMatchingPxDims.setChecked(bool(settings.sensorMatching & SensorMatching.PX_DIMS))
        self.cbSensorMatchingWavelength.setChecked(bool(settings.sensorMatching & SensorMatching.WL))
        self.cbSensorMatchingSensorName.setChecked(bool(settings.sensorMatching & SensorMatching.NAME))

        self.mSensorSpecsModel.setSpecs(settings.sensorSpecifications)

        self.sbMapSizeX.setValue(settings.mapSize.width())
        self.sbMapSizeY.setValue(settings.mapSize.height())
        self.sbMapRefreshIntervall.setValue(settings.mapUpdateInterval)
        self.mCanvasColorButton.setColor(settings.mapBackgroundColor)
        self.mMapTextFormatButton.setTextFormat(settings.mapTextFormat)

        # others page
        self.cbDebug.setChecked(settings.debug)
        self.cbAsyncQgsTasks.setChecked(settings.qgsTaskAsync)
        self.sbQgsTaskFileReadingThreads.setValue(settings.qgsTaskFileReadingThreads)
        self.sbBandStatsSampleSize.setValue(settings.bandStatsSampleSize)
        self.sbRasterOverlapSampleSize.setValue(settings.rasterOverlapSampleSize)
        self.btnProfileCurrent.setPlotStyle(settings.profileStyleCurrent.clone())
        self.btnProfileAdded.setPlotStyle(settings.profileStyleAdded.clone())

        self.btnProfileTemporal.setPlotStyle(settings.profileStyleTemporal.clone())

    def resetSettings(self):
        """Reset settings to default values"""
        default_settings = EOTSVSettings()

        # dump default settings into QgsSettings
        self.settingsManager.saveSettings(default_settings)

        # update the form
        self.loadSettings()
        self.configChanged.emit()


class EOTSVSettingsWidgetFactory(QgsOptionsWidgetFactory):
    """Factory for options widget."""

    configChanged = pyqtSignal()
    _INSTANCE = None

    defaultObjectName = 'mOptionsPageEOTimeSeriesViewerSettings'

    @staticmethod
    def instance() -> 'EOTSVSettingsWidgetFactory':
        if EOTSVSettingsWidgetFactory._INSTANCE is None:
            EOTSVSettingsWidgetFactory._INSTANCE = EOTSVSettingsWidgetFactory()
        return EOTSVSettingsWidgetFactory._INSTANCE

    def __init__(self):
        """Constructor."""
        super().__init__()

    def icon(self) -> QIcon:
        """Returns plugin icon, used to as tab icon in QGIS options tab widget.

        :return: _description_
        :rtype: QIcon
        """
        return icon()

    def createWidget(self, parent) -> EOTSVSettingsWidget:
        """Create settings widget.

        :param parent: Qt parent where to include the options page.
        :type parent: QObject

        :return: options page for tab widget
        :rtype: ConfigOptionsPage
        """
        page = EOTSVSettingsWidget(parent)
        page.setObjectName(self.defaultObjectName)
        page.configChanged.connect(self.configChanged.emit)
        return page

    def title(self) -> str:
        """Returns plugin title, used to name the tab in QGIS options tab widget.

        :return: plugin title from about module
        :rtype: str
        """
        return TITLE

    def helpId(self) -> str:
        """Returns plugin help URL.

        :return: plugin homepage url from about module
        :rtype: str
        """
        return HOMEPAGE


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
        sensorSpecs = EOTSVSettingsManager.settings().sensorSpecifications

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
