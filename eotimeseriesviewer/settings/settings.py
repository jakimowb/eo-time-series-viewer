import enum
from pathlib import Path
from typing import Dict, List, Optional, Union

from qgis.PyQt.QtCore import QMimeData, QSize
from qgis.PyQt.QtGui import QPen, QColor, QFont
from qgis.core import QgsSettings, QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes

from eotimeseriesviewer import __version__, TITLE
from eotimeseriesviewer.dateparser import DateTimePrecision
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from eotimeseriesviewer.sensors import SensorInstrument, SensorMatching


class EOTSVSettings(object):
    """
    Class with all EOTSV Settings
    """

    def __init__(self):

        self.dirScreenShots: Path = Path.home()
        self.dirRasterSources: Path = Path.home()
        self.dirVectorSources: Path = Path.home()

        self.dateTimePrecision: DateTimePrecision = DateTimePrecision.Day
        self.sensorMatching: SensorMatching = SensorMatching.PX_DIMS
        self.debug: bool = False

        self.mapUpdateInterval: int = 500
        self.mapSize: QSize = QSize(150, 150)
        self.mapBackgroundColor: QColor = QColor('black')

        # Profiles
        stylec = PlotStyle()
        stylec.setLinePen(QPen(QColor('green')))
        stylec.setMarkerColor(QColor('green'))

        style = PlotStyle()
        style.setMarkerColor(QColor('grey'))
        style.setLinePen(QPen(QColor('grey')))

        self.profileStyleCurrent = stylec.clone()
        self.profileStyleAdded = style.clone()
        self.profileStyleTemporal = style.clone()

        self.qgsTaskAsync = True
        self.qgsTaskBlockSize = 25
        self.bandStatsSampleSize = 256
        self.rasterOverlapSampleSize = 25

        self.restoreProjectSettings = True

        self.version = __version__

        mapTextFormat = QgsTextFormat()
        mapTextFormat.setColor(QColor('black'))
        mapTextFormat.setSizeUnit(QgsUnitTypes.RenderPoints)
        mapTextFormat.setFont(QFont('Helvetica'))
        mapTextFormat.setSize(11)

        buffer = QgsTextBufferSettings()
        buffer.setColor(QColor('white'))
        buffer.setSize(5)
        buffer.setSizeUnit(QgsUnitTypes.RenderPixels)
        buffer.setEnabled(True)
        mapTextFormat.setBuffer(buffer)
        self.mapTextFormat = mapTextFormat

        self.sensorSpecifications: Dict[str, str] = dict()

        # FORCE
        self.forceRootDir: Path = Path.home()
        self.forceProduct: str = 'BOA'

    def keys(self) -> List[str]:
        return [k for k in self.__dict__.keys() if not k.startswith('_')]

    def asMap(self) -> dict:

        d = {}
        for k in self.keys():
            v = getattr(self, k)
            if v is None or isinstance(v, (int, float, str, list, dict, QColor, QSize)):
                v2 = v
            # map none-standard types
            elif isinstance(v, Path):
                v2 = str(v)
            elif isinstance(v, enum.Enum):
                v2 = v.value
            elif isinstance(v, QgsTextFormat):
                md = v.toMimeData()
                v2 = md.text()
            elif isinstance(v, PlotStyle):
                v2 = v.map()
            else:
                raise NotImplementedError(f'Unsupported type: {type(v)} {v}')
            d[k] = v2
        return d

    def updateFromMap(self, d: dict):
        assert isinstance(d, dict)

        for k in self.keys():
            if k not in d:
                continue
            newValue = d[k]

            defaultValue = getattr(self, k)

            # Convert provided values into values used by EOTSVSettings class = same type as defined by defaults
            if type(newValue) is not type(defaultValue):

                if isinstance(defaultValue, Path):
                    newValue = Path(newValue)
                elif isinstance(defaultValue, PlotStyle):
                    if isinstance(newValue, str):
                        newValue = PlotStyle.fromJSON(newValue)
                    elif isinstance(newValue, dict):
                        newValue = PlotStyle.fromMap(newValue)
                elif isinstance(defaultValue, QgsTextFormat):
                    md = QMimeData()
                    md.setText(newValue)
                    fmt, success = QgsTextFormat.fromMimeData(md)
                    if success:
                        newValue = fmt
                elif isinstance(defaultValue, DateTimePrecision):
                    if isinstance(newValue, str):
                        for p in DateTimePrecision:
                            if p.value == newValue:
                                newValue = p
                                break
                    assert isinstance(newValue, DateTimePrecision)
                elif isinstance(defaultValue, SensorMatching):
                    if isinstance(newValue, int):
                        for flag in SensorMatching:
                            if flag.value == newValue:
                                newValue = flag

            if type(newValue) is type(defaultValue) or defaultValue is None:
                setattr(self, k, newValue)
            else:
                raise NotImplementedError(f'Unable to update {k} from {type(newValue)} {newValue}')


class EOTSVSettingsManager(object):
    """
    Returns the EOTSV Settings
    and handles storing into QgsSettings system
    """

    @classmethod
    def settings(cls) -> EOTSVSettings:
        defaultSettings = EOTSVSettings()

        # retrieve settings from QGIS/Qt
        settings = QgsSettings()
        settings.beginGroup(TITLE)

        # map settings values to preferences object
        defaultValues = defaultSettings.asMap()
        updatedValues = dict()
        for k, d in defaultValues.items():
            u = settings.value(k, defaultValue=d)
            updatedValues[k] = u

        settings.endGroup()

        defaultSettings.updateFromMap(updatedValues)
        return defaultSettings

    @classmethod
    def saveSettings(cls, settings: EOTSVSettings):
        # retrieve settings from QGIS/Qt
        qgs_settings = QgsSettings()
        qgs_settings.beginGroup(TITLE)

        for k, v in settings.asMap().items():
            qgs_settings.setValue(k, v)

        qgs_settings.endGroup()

    @classmethod
    def saveSensorName(cls, sensor: SensorInstrument):
        """
        Saves the sensor name
        :param sensor: SensorInstrument
        :return:
        """
        assert isinstance(sensor, SensorInstrument)

        settings = cls.settings()
        sensorSpecs = settings.sensorSpecifications
        sSpecs = sensorSpecs.get(sensor.id(), dict())
        sSpecs['name'] = sensor.name()
        sensorSpecs[sensor.id()] = sSpecs

        cls.saveSettings(settings)

    @classmethod
    def sensorName(cls, sid: Union[str, SensorInstrument]) -> Optional[str]:
        """
        Returns the sensor name stored for a certain sensor id
        :param sid: str
        :return: str
        """
        if isinstance(sid, SensorInstrument):
            sid = sid.id()

        sensorSpecs = cls.settings().sensorSpecifications
        sSpecs = sensorSpecs.get(sid, dict())
        return sSpecs.get('name', None)
