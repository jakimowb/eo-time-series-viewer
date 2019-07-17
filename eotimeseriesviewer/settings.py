
import os, enum, pathlib, re
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *

from eotimeseriesviewer import *
from eotimeseriesviewer.utils import loadUI


class Keys(enum.Enum):
    """
    Enumeration of settings keys.
    """
    DateTimePrecision = 'date_time_precision'
    MapSize = 'map_size'
    MapUpdateInterval = 'map_update_interval'
    MapBackgroundColor = 'map_background_color'
    MapTextFormat = 'map_text_format'
    SensorNames = 'sensor_names'
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
    d[Keys.SensorNames] = dict()

    # map visualization
    d[Keys.MapUpdateInterval] = 500  # milliseconds
    d[Keys.MapSize] = QSize(150, 150)
    d[Keys.MapBackgroundColor] = QColor('black')

    textFormat = QgsTextFormat()
    textFormat.setColor(QColor('yellow'))
    textFormat.setSizeUnit(QgsUnitTypes.RenderPoints)
    textFormat.setFont(QFont('Helvetica'))
    textFormat.setSize(11)

    buffer = QgsTextBufferSettings()
    buffer.setColor(QColor('black'))
    buffer.setSize(1)
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

    except TypeError as error:
        value = None
        settings().setValue(key.value, None)
        print(error, file=sys.stderr)
    return value


def setValue(key:Keys, value):
    """
    Shortcut to save a value into the EOTSV settings
    :param key: str | Key
    :param value: any value
    """
    assert isinstance(key, Keys)

    if isinstance(value, QgsTextFormat):
        value = value.toMimeData()

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

        self.mLastValues = dict()

        self.setValues(settings())

    def validate(self, *args):

        values = self.values()

    def onAccept(self):
        pass
        self.setResult(QDialog.Accepted)

        values = self.values()
        setValues(values)
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
                d[k] = values.value(k)
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

            if checkKey(key, Keys.MapSize) and isinstance(value, QSize):
                self.sbMapSizeX.setValue(value.width())
                self.sbMapSizeY.setValue(value.height())

            if checkKey(key, Keys.MapUpdateInterval) and isinstance(value, (float, int)) and value > 0:
                self.sbMapRefreshIntervall.setValue(value)

            if checkKey(key, Keys.MapBackgroundColor) and isinstance(value, QColor):
                self.mCanvasColorButton.setColor(value)

            if checkKey(key, Keys.MapTextFormat) and isinstance(value, QgsTextFormat):
                self.mMapTextFormatButton.setTextFormat(value)





