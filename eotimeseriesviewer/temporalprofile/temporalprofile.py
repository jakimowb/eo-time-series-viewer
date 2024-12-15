import json
import os.path
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from uuid import uuid4

from qgis.PyQt.QtCore import NULL, pyqtSignal, QModelIndex, QSortFilterProxyModel, Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsEditorWidgetSetup, \
    QgsFeature, QgsField, QgsFieldFormatter, QgsFieldFormatterRegistry, QgsFields, QgsMapLayer, QgsMapLayerModel, \
    QgsPointXY, QgsProject, QgsRasterDataProvider, QgsRasterLayer, QgsVectorFileWriter, QgsVectorLayer
from qgis.gui import QgsEditorConfigWidget, QgsEditorWidgetFactory, QgsEditorWidgetRegistry, QgsEditorWidgetWrapper, \
    QgsGui
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.qgisenums import QMETATYPE_QSTRING, QMETATYPE_QVARIANTMAP
from eotimeseriesviewer.tasks import EOTSVTask
from eotimeseriesviewer.timeseries import sensor_id, sensorIDtoProperties

# TimeSeriesProfileData JSON Format
# { sensors_ids = [sid 1 <str>, ..., sid n],
#   sources = [n source strings],
#   dates = [n date-time-stamps],
#   sensors = [n sensor id indices],
#   band_values = [n band value dictionaries]
# }
#
#
#
#

TPF_EDITOR_WIDGET_KEY = 'Temporal Profile'
TPF_COMMENT = 'Temporal profile data'
TPF_TYPE = QMETATYPE_QVARIANTMAP
TPF_TYPENAME = 'JSON'
TPF_SUBTYPE = None
TPL_NAME = 'Temporal Profile Layer'


class TemporalProfileLayerProxyModel(QSortFilterProxyModel):
    """
    A model that shown only vectorlayer with a temporal profile fields.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mModel = QgsMapLayerModel()
        self.setSourceModel(self.mModel)

    def filterAcceptsRow(self, source_row: QModelIndex, source_parent: QModelIndex):
        idx: QModelIndex = self.sourceModel().index(source_row, 0, parent=source_parent)

        layer = idx.data(QgsMapLayerModel.CustomRole.Layer)
        return TemporalProfileUtils.isProfileLayer(layer)

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)


class TemporalProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(TemporalProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mWidget: QWidget = None

        self.mLastValue: QVariant = QVariant()
        s = ""

    def createWidget(self, parent: QWidget):
        # log('createWidget')

        if not self.isInTable(parent):
            self.mWidget = TemporalProfileEditorWidget(parent=parent)
        else:
            self.mWidget = QLabel('Profile', parent=parent)
        return self.mWidget

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        conf = self.config()

        if isinstance(editor, TemporalProfileEditorWidget):
            pass

        elif isinstance(editor, QLabel):
            editor.setText(f'Temporal Profile ({self.field().typeName()})')
            editor.setToolTip('Use Form View to edit values')

    def onValueChanged(self, *args):
        self.valuesChanged.emit(self.value())

    def valid(self, *args, **kwargs) -> bool:
        return isinstance(self.mWidget, (TemporalProfileEditorWidget, QLabel))

    def value(self, *args, **kwargs):
        value = self.mLastValue
        w = self.widget()
        if isinstance(w, TemporalProfileEditorWidget):
            pass
        return value

    def setFeature(self, feature: QgsFeature) -> None:
        super(TemporalProfileEditorWidgetWrapper, self).setFeature(feature)

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, TemporalProfileEditorWidget):
            w.setEnabled(enabled)

    def setValue(self, value: Any) -> None:
        self.mLastValue = value
        w = self.widget()
        if isinstance(w, TemporalProfileEditorWidget):
            pass


class TemporalProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):
        super(TemporalProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        self.label = QLabel('A field to store temporal profiles')
        hbox = QHBoxLayout()
        hbox.addWidget(self.label)
        self.setLayout(hbox)

    def config(self, *args, **kwargs) -> dict:
        config = {}

        return config

    def setConfig(self, config: dict):
        pass


class TemporalProfileFieldFormatter(QgsFieldFormatter):

    def __init__(self, *args, **kwds):
        super(TemporalProfileFieldFormatter, self).__init__(*args, **kwds)

    def id(self) -> str:
        return TPF_EDITOR_WIDGET_KEY

    def representValue(self, layer: QgsVectorLayer, fieldIndex: int, config: dict, cache, value):

        if value not in [None, NULL]:
            return str(value)
            # return f'{SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE} ({layer.fields().at(fieldIndex).typeName()})'
        else:
            return 'NULL'
        s = ""


class TemporalProfileEditorWidgetFactory(QgsEditorWidgetFactory):
    _INSTANCE_WF: Optional['TemporalProfileEditorWidgetFactory'] = None
    _INSTANCE_FF: Optional[TemporalProfileFieldFormatter] = None

    @classmethod
    def register(cls):
        if not isinstance(cls._INSTANCE_FF, TemporalProfileFieldFormatter):
            cls._INSTANCE_FF = TemporalProfileFieldFormatter()
            fmtReg: QgsFieldFormatterRegistry = QgsApplication.instance().fieldFormatterRegistry()
            fmtReg.addFieldFormatter(cls._INSTANCE_FF)

        if not isinstance(cls._INSTANCE_WF, TemporalProfileEditorWidgetFactory):
            cls._INSTANCE_WF = TemporalProfileEditorWidgetFactory(TPF_EDITOR_WIDGET_KEY)
            ewReg: QgsEditorWidgetRegistry = QgsGui.editorWidgetRegistry()
            ewReg.registerWidget(TPF_EDITOR_WIDGET_KEY, cls._INSTANCE_WF)

    def __init__(self, name: str):

        super(TemporalProfileEditorWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> TemporalProfileEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = TemporalProfileEditorConfigWidget(layer, fieldIdx, parent)
        key = self.configKey(layer, fieldIdx)
        w.setConfig(self.readConfig(key))
        w.changed.connect(lambda *args, ww=w, k=key: self.writeConfig(key, ww.config()))
        return w

    def configKey(self, layer: QgsVectorLayer, fieldIdx: int) -> Tuple[str, int]:
        """
        Returns a tuple to be used as dictionary key to identify a layer profile_field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return layer.id(), fieldIdx

    def create(self, layer: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> TemporalProfileEditorWidgetWrapper:
        """
        Create a SpectralProfileEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: SpectralProfileEditorWidgetWrapper
        """

        w = TemporalProfileEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        # self.editWrapper = w
        return w

    def writeConfig(self, key: tuple, config: dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config
        # print('Save config')
        # print(config)

    def readConfig(self, key: tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        return self.mConfigurations.get(key, {})

    def supportsField(self, vl: QgsVectorLayer, fieldIdx: int) -> bool:
        """
        :param vl:
        :param fieldIdx:
        :return:
        """
        field: QgsField = vl.fields().at(fieldIdx)
        return TemporalProfileUtils.isProfileField(field)

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain profile_field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if TemporalProfileUtils.isProfileField(field):
            return 20
        elif field.type() in [QMETATYPE_QVARIANTMAP, QMETATYPE_QSTRING]:
            return 5
        else:
            return 0


class TemporalProfileEditorWidget(QGroupBox):
    VIEW_TABLE = 1
    VIEW_JSON_EDITOR = 2

    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(TemporalProfileEditorWidget, self).__init__(*args, **kwds)
        self.setWindowIcon(QIcon(':/eotimeseriesviewer/icons/mIconTemporalProfile.svg'))
        self.mDefault: dict = False

        vbox = QVBoxLayout()
        vbox.setSpacing(1)
        vbox.addWidget(QLabel('Temporal Profile'))
        self.setLayout(vbox)

        s = ""

    def editorProfileChanged(self):

        w = self.stackedWidget.currentWidget()

        if self.sender() != w:
            return

    def initConfig(self, conf: dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        pass

    def setProfile(self, profile: dict):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        pass

    def resetProfile(self):
        if isinstance(self.mDefault, dict):
            self.setProfile(self.mDefault)


class TemporalProfileUtils(object):
    Source = 'source'  # optional
    Date = 'date'
    SensorIDs = 'sensor_ids'
    Sensor = 'sensor'
    Values = 'values'

    @classmethod
    def isProfileField(cls, field: QgsField) -> bool:

        return (isinstance(field,
                           QgsField) and field.type() == TPF_TYPE and field.editorWidgetSetup().type() == TPF_EDITOR_WIDGET_KEY)

    @classmethod
    def isProfileDict(cls, d: dict) -> bool:
        for k in [TemporalProfileUtils.Date,
                  TemporalProfileUtils.SensorIDs,
                  TemporalProfileUtils.Sensor,
                  TemporalProfileUtils.Values]:
            if k not in d:
                return False

        return True

    @classmethod
    def isProfileLayer(cls, layer: QgsMapLayer) -> bool:
        if isinstance(layer, QgsVectorLayer):
            return any([cls.isProfileField(f) for f in layer.fields()])
        else:
            return False

    @classmethod
    def verifyProfile(cls, profileDict: dict) -> Tuple[bool, str]:

        n = len(profileDict[TemporalProfileUtils.Date])
        sensorIds = profileDict[TemporalProfileUtils.SensorIDs]
        nSensors = len(sensorIds)

        optionalSource = TemporalProfileUtils.Source in profileDict

        for sid in sensorIds:
            try:
                sdict = sensorIDtoProperties(sid)
            except Exception as ex:
                return False, f'Invalid sensor ID string: {sid}\n{ex}'

        for i, (date, sensor, values) in enumerate(zip(profileDict[TemporalProfileUtils.Date],
                                                       profileDict[TemporalProfileUtils.Sensor],
                                                       profileDict[TemporalProfileUtils.Values])):
            try:
                dtg = datetime.fromisoformat(date)
                assert dtg is not None
                assert 0 <= sensor < nSensors
                if optionalSource:
                    src = profileDict[TemporalProfileUtils.Source][i]
                    assert isinstance(src, str), f'profile source {src} is not string'

            except Exception as ex:
                return False, f'Item {i + 1}: {ex}\n{date},{sensor},{values}'

        return True, None

    @classmethod
    def profileJsonFromDict(cls, d: dict) -> str:
        txt = json.dumps(d)
        return txt

    @classmethod
    def profileDict(cls, input) -> Optional[dict]:

        if isinstance(input, str):
            input = cls.profileDictFromJson(input)

        if isinstance(input, dict):
            return input
        else:
            return None

    @classmethod
    def profileSensors(cls, profile: dict) -> List[str]:
        d = cls.profileDict(cls)
        return d.get(cls.SensorIDs)

    @classmethod
    def profileDictFromJson(cls, json_string: str) -> dict:
        data = json.loads(json_string)
        return data

    @classmethod
    def createProfileField(cls, name: str) -> QgsField:
        field = QgsField(name, type=QMETATYPE_QVARIANTMAP, typeName=TPF_TYPENAME)
        setup = QgsEditorWidgetSetup(TPF_EDITOR_WIDGET_KEY, {})
        field.setEditorWidgetSetup(setup)
        field.setComment(TPF_COMMENT)
        return field

    @classmethod
    def temporalProfileFields(cls, source: Union[str, Path, QgsFeature, QgsVectorLayer, QgsFields]):

        if isinstance(source, (str, Path)):
            lyr = QgsVectorLayer(Path(source).as_posix())
            assert lyr.isValid()
            return TemporalProfileUtils.temporalProfileFields(lyr.fields())

        elif isinstance(source, (QgsVectorLayer, QgsFeature)):
            return TemporalProfileUtils.temporalProfileFields(source.fields())

        elif isinstance(source, QgsFields):

            results = QgsFields()
            for field in source:
                if TemporalProfileUtils.isProfileField(field):
                    results.append(QgsField(field))
            return results
        else:
            raise NotImplementedError(f'Unable to extract profile fields from {source}')

    @classmethod
    def profileLayers(cls, layers: Union[List[QgsMapLayer], QgsProject]) -> List[QgsVectorLayer]:
        """
        Returns the vector layer with temporal profile fields
        :param layers:
        :param project:
        :return:
        """
        if isinstance(layers, QgsProject):
            layers = layers.mapLayers().values()

        return [l for l in layers if cls.isProfileLayer(l)]

    @classmethod
    def profileFields(cls, layer: QgsVectorLayer) -> QgsFields:
        """
        Returns the fields with temporal profiles
        :param layer: QgaVectorLayer
        :return: QgsFields
        """
        assert isinstance(layer, QgsVectorLayer)
        fields = QgsFields()
        for f in layer.fields():
            if cls.isProfileField(f):
                fields.append(f)
        return fields

    @staticmethod
    def createProfileLayer(path: Union[str, Path] = None) -> QgsVectorLayer:
        """
        Creates a GPKG to store temporal profiles
        :param path:
        :return:
        """
        if path is None:
            path = Path(f'/vsimem/temporalprofiles.{uuid4()}.gpkg')

        fields = QgsFields()
        fields.append(TemporalProfileUtils.createProfileField('profile'))
        fields.append(QgsField(name='notes', type=QMETATYPE_QSTRING))

        wkbType = Qgis.WkbType.Point
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        transformContext = QgsProject.instance().transformContext()

        driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(path.name)[1])
        dmd = QgsVectorFileWriter.MetaData()
        assert QgsVectorFileWriter.driverMetadata(driver, dmd)

        f1: QgsField = fields['profile']
        f2: QgsField = QgsField(f1)
        assert TemporalProfileUtils.isProfileField(f1), f'{f1}: {f1.comment()}'
        assert TemporalProfileUtils.isProfileField(f2), f'{f2}: {f2.comment()}'

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver

        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

        writer = QgsVectorFileWriter.create(path.as_posix(), fields, wkbType, crs, transformContext, options)
        assert QgsVectorFileWriter.WriterError.NoError == writer.hasError(), \
            f'Error creating {path}:\n{writer.errorMessage()}'

        writer.flushBuffer()

        del writer

        lyr = QgsVectorLayer(path.as_posix())
        assert lyr.isValid()
        idx = lyr.fields().lookupField('profile')
        lyr.setEditorWidgetSetup(idx, QgsEditorWidgetSetup(TPF_EDITOR_WIDGET_KEY, {}))
        field: QgsField = lyr.fields()['profile']
        assert TemporalProfileUtils.isProfileField(field), f'{field}:{field.comment()}'
        lyr.setName(TPL_NAME)
        return lyr


class LoadTemporalProfileTask(EOTSVTask):

    def __init__(self,
                 sources: List[Union[str, Path]],
                 points: List[QgsPointXY],
                 crs: QgsCoordinateReferenceSystem,
                 info: dict = None,
                 cache: dict = None,
                 *args, **kwds):
        super().__init__(*args, **kwds)

        self.mInfo = info.copy() if isinstance(info, dict) else None
        self.mSources: List[Path] = [Path(s) for s in sources]
        self.mPoints = points[:]
        self.mCrs = crs
        self.mProfiles = []
        self.mProgressInterval = timedelta(seconds=1)
        self.mLoadingTime: Optional[timedelta] = None
        self.mCache: dict = cache.copy() if isinstance(cache, dict) else dict()
        self.mTimeIt: dict = dict()

    def loadingTime(self) -> Optional[timedelta]:
        return self.mLoadingTime

    def profiles(self) -> List[dict]:
        return self.mProfiles

    def profilePoints(self) -> List[QgsPointXY]:
        return self.mPoints

    def info(self) -> dict:
        return self.mInfo

    def timeIt(self, key: str, datetime: datetime):
        l = self.mTimeIt.get(key, [])
        l.append(datetime.now() - datetime)
        self.mTimeIt[key] = l

    def run(self) -> bool:
        errors = []
        t0 = datetime.now()
        tNextProgress = datetime.now() + self.mProgressInterval

        nTotal = len(self.mSources)

        profiles = [{TemporalProfileUtils.Source: [],
                     TemporalProfileUtils.Date: [],
                     TemporalProfileUtils.Sensor: [],
                     TemporalProfileUtils.SensorIDs: [],
                     TemporalProfileUtils.Values: [],
                     }
                    for _ in self.mPoints]

        sensor_ids = []

        for i, src in enumerate(self.mSources):
            if self.isCanceled():
                return False

            t1 = datetime.now()
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
            lyr = QgsRasterLayer(src.as_posix(), options=options)
            self.timeIt('initLayer', t1)

            if not lyr.isValid():
                errors.append(f'Unable to load {src}')
                continue

            t1 = datetime.now()
            if lyr.source() in self.mCache:
                sid, dtg = self.mCache[lyr.source()]
            else:
                sid = sensor_id(lyr)
                if not sid:
                    errors.append(f'Unable to load sensor id from {lyr}')
                    continue

                dtg = ImageDateUtils.dateTimeFromLayer(lyr)
                if not dtg:
                    errors.append(f'Unable to load date-time from {lyr}')
                    continue

                self.mCache[lyr.source()] = (sid, dtg)
            self.timeIt('sid_dtg', t1)

            if sid not in sensor_ids:
                sensor_ids.append(sid)

            dp: QgsRasterDataProvider = lyr.dataProvider()

            if lyr.crs() == self.mCrs:
                pts = self.mPoints
            else:
                trans = QgsCoordinateTransform()
                trans.setSourceCrs(self.mCrs)
                trans.setDestinationCrs(lyr.crs())
                pts = [trans.transform(pt) for pt in self.mPoints]
                s = ""

            for i_pt, pt in enumerate(pts):
                if not lyr.extent().contains(pt):
                    continue

                profile: dict = profiles[i_pt]
                values = None

                if False:
                    t1 = datetime.now()
                    data = dp.identify(pt, Qgis.RasterIdentifyFormat.Value)
                    self.timeIt('identify', t1)

                    if data.isValid():
                        bandValues = data.results()
                        if len(bandValues) > 0:
                            valuesI = list(bandValues.values())

                if True:
                    # from benchmark, loading full-band time series with 100 images:
                    # Avg initLayer: 0:00:00.014435
                    # Avg sid_dtg: 0:00:00.006734
                    # Avg identify: 0:00:00.173399 <- takes too long, total duration 19.sec
                    # Avg sample: 0:00:00.000056 <- better use dataprovider.sample, total duration 17 sec
                    t1 = datetime.now()
                    data = [dp.sample(pt, b + 1) for b in range(dp.bandCount())]
                    self.timeIt('sample', t1)
                    values = [None if not d[1] else d[0] for d in data]

                # assert valuesI == values

                if not any(values):
                    continue

                # we have at least one -none-masked band value
                profile[TemporalProfileUtils.Source].append(src.as_posix())
                profile[TemporalProfileUtils.Values].append(values)
                profile[TemporalProfileUtils.Sensor].append(sensor_ids.index(sid))
                profile[TemporalProfileUtils.Date].append(dtg.toString(Qt.ISODateWithMs))

            tNow = datetime.now()
            if tNow > tNextProgress:
                progress = (i + 1) / nTotal * 100
                self.setProgress(progress)
                tNextProgress = tNow + self.mProgressInterval

        # keep only profile dictionaries for which we have at least one values
        for p in profiles:
            p[TemporalProfileUtils.SensorIDs] = sensor_ids
        profiles = [p for p in profiles if len(p[TemporalProfileUtils.Source]) > 0]
        self.mProfiles = profiles
        self.setProgress(100)
        self.mLoadingTime = datetime.now() - t0

        for k in self.mTimeIt.keys():
            deltas = self.mTimeIt[k]
            if len(deltas) > 1:
                d = deltas[0]
                for d2 in deltas[1:]:
                    d += d2
            else:
                d = deltas[0]

            self.mTimeIt[k] = d / len(deltas)

        return True
