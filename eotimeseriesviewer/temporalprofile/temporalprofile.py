import json
import os.path
import re
import types
import warnings
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import numpy as np
from qgis.PyQt.QtCore import NULL, pyqtSignal, QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt, QVariant
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsEditorWidgetSetup, \
    QgsFeature, QgsField, QgsFieldFormatter, QgsFieldFormatterRegistry, QgsFields, QgsIconUtils, QgsMapLayer, \
    QgsMapLayerModel, QgsPointXY, QgsProject, QgsRasterDataProvider, QgsRasterLayer, QgsVectorFileWriter, QgsVectorLayer
from qgis.PyQt.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsEditorConfigWidget, QgsEditorWidgetFactory, QgsEditorWidgetRegistry, QgsEditorWidgetWrapper, \
    QgsGui

from eotimeseriesviewer.qgispluginsupport.qps.unitmodel import UnitLookup
from eotimeseriesviewer.temporalprofile.spectralindices import spectral_index_acronyms, spectral_indices
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
TPF_SUBTYPE = 10
TPL_NAME = 'Temporal Profile Layer'


class TemporalProfileLayerProxyModel(QSortFilterProxyModel):
    """
    A model that shown only vector-layers with at least one temporal profile field.
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


class TemporalProfileLayerComboBox(QComboBox):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mProxyModel = TemporalProfileLayerProxyModel()
        self.setModel(self.mProxyModel)

    def setProject(self, project: QgsProject):
        self.mProxyModel.setProject(project)


class TemporalProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(TemporalProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mWidget: Optional[QWidget] = None

        self.mLastValue: QVariant = QVariant()

    def createWidget(self, parent: QWidget):
        # log('createWidget')

        if not self.isInTable(parent):
            self.mWidget = TemporalProfileEditorWidget(parent=parent)
        else:
            self.mWidget = QLabel('Profile', parent=parent)
        return self.mWidget

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        # conf = self.config()

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

    def create(self,
               layer: QgsVectorLayer,
               fieldIdx: int,
               editor: QWidget,
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
        :return: integer score
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
        self.mDefault: Optional[dict] = None

        vbox = QVBoxLayout()
        vbox.setSpacing(1)
        vbox.addWidget(QLabel('Temporal Profile'))
        self.setLayout(vbox)

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
        :param profile: dict() or SpectralProfile
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
    def createEmptyProfile(cls) -> dict:
        p = {
            TemporalProfileUtils.Source: [],
            TemporalProfileUtils.Date: [],
            TemporalProfileUtils.Sensor: [],
            TemporalProfileUtils.SensorIDs: [],
            TemporalProfileUtils.Values: [],
        }
        return p

    @classmethod
    def prepareBandExpression(cls, user_code: str) -> Tuple[Optional[types.CodeType], Optional[str]]:
        """
        Prepares the band expression code for execution in the applySensorExpression method.
        :param user_code: str with the band expression code specified by the user
        :return: compiled code to be used with exec(), error message
        """
        code = ['import numpy as np',
                'from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils',
                'b = lambda expr: TemporalProfileUtils.bandOrIndex(expr, band_values, sensor_specs)',
                f'y = {user_code}'
                ]
        error = None
        compiled_code = None
        try:
            compiled_code = compile('\n'.join(code), '<band sensor function>', 'exec')
        except Exception as ex:
            error = str(ex)
        return compiled_code, error

    @classmethod
    def sensorSpecs(cls, sid: str) -> dict:
        """
        Returns the sensor specifications for the given sensor id
        :param sid: sensor id string
        :return: sensor specifications as dict
        """
        SI_ACRONYMS = spectral_index_acronyms()

        band_lookup = dict()
        specs = json.loads(sid)
        if isinstance(specs.get('wlu'), str) and isinstance(specs['wl'], list):
            # convert wavelengths to nanometers
            wl: List[float] = UnitLookup.convertLengthUnit(specs['wl'], specs['wlu'], 'nm')

            for name, info in SI_ACRONYMS['band_identifier'].items():
                center_wl = 0.5 * (info['wl_min'] + info['wl_max'])

                if min(wl) <= center_wl <= max(wl):
                    band_lookup[name] = int(np.argmin(np.abs(np.asarray(wl) - center_wl)))
                else:
                    band_lookup[name] = None

        specs['sid'] = sid
        specs['band_lookup'] = band_lookup

        return specs

    @classmethod
    def applyExpressions(cls,
                         tpData: Dict[str, Any],
                         feature: QgsFeature,
                         sensor_expressions: Dict[str, Any],
                         sensor_specs: Optional[Dict[str, Any]] = None) \
            -> dict:
        """
        Applies the sensor expressions to the temporal profile data and returns the results
        in a dictionary, i.e. timestamps, y-values, and sensor indices
        :param tpData: Temporal profile data dictionary
        :param feature: QgsFeature
        :param sensor_expressions: dict with sensor expressions
        :param sensor_specs: dict with sensor specifications, as returned by sensorSpecs()
        :return: dictionary with
            'x' = timestamps,
            'y' = calculated values,
            'n' = number of observations,
            'sensor_indices' = dict with sensor indices (from numpy.where)
            'errors' = list with errors occurred during calculation
        """
        errors = []

        all_obs_dates = np.asarray([datetime.fromisoformat(d) for d in tpData[TemporalProfileUtils.Date]])
        x = np.asarray([d.timestamp() if isinstance(d, datetime) else np.NaN for d in all_obs_dates])
        n = len(x)

        y = np.empty(n, dtype=float)
        sidx = np.asarray(tpData[TemporalProfileUtils.Sensor])
        all_band_values = tpData[TemporalProfileUtils.Values]

        if sensor_specs is None:
            sensor_specs = {}

        for i, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
            is_sensor = np.where(sidx == i)[0]
            if len(is_sensor) == 0:
                continue
            expr = sensor_expressions.get(sid, sensor_expressions.get('*', None))

            if expr:
                try:
                    if isinstance(expr, str):
                        expr, err = cls.prepareBandExpression(expr)
                        assert expr, err
                    else:
                        assert isinstance(expr,
                                          types.CodeType), f'expression is not a code pre-compiled object:\n\t{sid}={expr}'
                    s_band_values = np.asarray([all_band_values[j] for j in is_sensor])
                    s_obs_dates = x[is_sensor]
                    specs = sensor_specs.get(sid, cls.sensorSpecs(sid))
                    _globals = {'sensor_specs': specs,
                                'band_values': s_band_values,
                                'dates': s_obs_dates,
                                'feature': feature}
                    for k, band_index in specs.get('band_lookup', {}).items():
                        if isinstance(band_index, int):
                            if k not in _globals:
                                _globals[k] = s_band_values[:, band_index]
                            else:
                                warnings.warn(f'Variable {k} is already defined.')
                    exec(expr, _globals)
                    s_y = _globals['y']
                    # s_y = cls.applySensorExpression(s_band_values, s_obs_dates, feature)
                    y[is_sensor] = s_y
                except Exception as ex:
                    errors.append(f'{ex}')
                    y[is_sensor] = np.NaN
            else:
                y[is_sensor] = np.NaN

        # exclude NaNs
        is_valid = np.where(np.isfinite(y))[0]
        y = y[is_valid]
        x = x[is_valid]
        sidx = sidx[is_valid]

        sensor_indices: Dict[str, np.ndarray] = dict()
        for i, sid in enumerate(tpData[TemporalProfileUtils.SensorIDs]):
            is_sensor = np.where(sidx == i)[0]
            if len(is_sensor) > 0:
                sensor_indices[sid] = is_sensor

        results = {'x': x,
                   'y': y,
                   'n': len(x),
                   'sensor_indices': sensor_indices,
                   'errors': errors,
                   }

        return results

    @classmethod
    def bandOrIndex(cls, expr, bandData: np.ndarray, sensor_specs: dict) -> Optional[np.ndarray]:
        """
        Returns the band values or spectral index values for the given expression
        :param expr:
        :param bandData:
        :param sensor_specs:
        :return: numpy array with the band values or spectral index values
        """
        n, nb = bandData.shape
        band_lookup: dict[str, int] = sensor_specs.get('band_lookup', {})
        index_descriptions = spectral_indices()

        acronyms = spectral_index_acronyms()
        constants = acronyms['constants']
        band_identifier = acronyms['band_identifier']

        if isinstance(expr, str) and re.match(r'^\d+$', expr):
            expr = int(expr)

        if isinstance(expr, int):
            assert 0 < expr <= nb, f'Invalid band number: {expr}'
            # return the n-th band
            return bandData[:, expr - 1]
        elif isinstance(expr, str):
            if expr in band_lookup:
                return bandData[:, band_lookup[expr]]
            elif expr in index_descriptions:
                index_info: dict = index_descriptions[expr]
                required_bands = index_info['bands']
                formula = index_info['formula']
                # get spectral index values

                params = {}
                for b in required_bands:
                    if b in constants:
                        params[b] = constants[b]['value']
                    elif b in band_lookup:
                        params[b] = bandData[:, band_lookup[b]]
                    else:
                        return np.ones(n) * np.NaN

                return eval(formula, {}, params)
            else:
                return np.ones(n) * np.NaN
                # s = ""
                # raise ValueError(f'Unknown band name / spectral index: {expr}')

        s = ""

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
    def verifyProfile(cls, profileDict: dict) -> Tuple[bool, Optional[str]]:

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
                assert isinstance(date, str)
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

    @staticmethod
    def profileValues(dp: Union[QgsRasterLayer, QgsRasterDataProvider], pt: QgsPointXY) -> List[Optional[float]]:
        if isinstance(dp, QgsRasterLayer):
            dp = dp.dataProvider()

        data = [dp.sample(pt, b + 1) for b in range(dp.bandCount())]
        return [None if not d[1] else d[0] for d in data]

    @classmethod
    def profileDict(cls, data: Any) -> Optional[dict]:

        if isinstance(data, str):
            data = cls.profileDictFromJson(data)

        if isinstance(data, dict):
            return data
        else:
            return None

    @classmethod
    def profileSensors(cls, profileData: dict) -> List[str]:
        d = cls.profileDict(profileData)
        return d.get(cls.SensorIDs)

    @classmethod
    def profileDictFromJson(cls, json_string: str) -> dict:
        data = json.loads(json_string)
        return data

    @classmethod
    def createProfileField(cls, name: str, field_type=QMETATYPE_QVARIANTMAP) -> QgsField:
        """
        Creates a QgsField for temporal profiles
        :param name: field name (e.g. 'profile')
        :return: QgsField
        """
        assert field_type in [QMETATYPE_QVARIANTMAP, QMETATYPE_QSTRING]
        field = QgsField(name, type=QMETATYPE_QVARIANTMAP, typeName=TPF_TYPENAME, subType=TPF_SUBTYPE)
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
        :param layers: list of QgsMapLayer or QgsProject
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
        Creates an in-memory GeoPackage (GPKG) to store temporal profiles
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
    interimResults = pyqtSignal(list)

    def __init__(self,
                 sources: List[Union[str, Path]],
                 points: List[QgsPointXY],
                 crs: QgsCoordinateReferenceSystem,
                 info: dict = None,
                 mdCache: dict = None,
                 lyrCache: dict = None,
                 n_threads: int = 0,
                 *args, **kwds):
        super().__init__(*args, **kwds)

        self.mInfo = info.copy() if isinstance(info, dict) else None
        self.mSources: List[str] = [Path(s).as_posix() for s in sources]
        self.mPoints = points[:]
        self.mCrs = crs
        self.mProfiles = []
        self.mProgressInterval = timedelta(seconds=1)
        self.mInterimResultsInterval = timedelta(seconds=2)
        self.mInterimResults: bool = False

        assert n_threads >= 0
        self.nThreads: int = n_threads
        self.mdCache: dict = mdCache if isinstance(mdCache, dict) else dict()
        self.lyrCache: Dict[str, QgsRasterLayer] = lyrCache if isinstance(lyrCache, dict) else dict()

        self.mFutures: List = []
        self.mResults: List = []
        self.mTreadPoolExecutor: Optional[ThreadPoolExecutor] = None

    def profiles(self) -> List[dict]:
        return self.mProfiles

    def profilePoints(self) -> List[QgsPointXY]:
        return self.mPoints

    def info(self) -> dict:
        return self.mInfo

    def canCancel(self):
        return True

    def loadFromSource(self,
                       lyr: Union[str, QgsRasterLayer],
                       points: List[QgsPointXY],
                       crs: QgsCoordinateReferenceSystem) -> Tuple[Optional[dict], Optional[str]]:
        """
        Returns the profiles + meta infos from a single source
        :param src:
        :return: profiles (in order of points), sensor-id, list of errors
        """

        if isinstance(lyr, str):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
            lyr = QgsRasterLayer(lyr, options=options)
        assert isinstance(lyr, QgsRasterLayer)
        src = lyr.source()
        error = None

        if not lyr.isValid():
            return None, f'Unable to load {src}'

        # sid, dtg = self.mdCache[src]
        sid = sensor_id(lyr)
        if not sid:
            return None, f'Unable to load sensor id from {lyr}'

        dtg = ImageDateUtils.dateTimeFromLayer(lyr)
        if not dtg:
            return None, f'Unable to load date-time from {lyr}'
        dtg = dtg.toString(Qt.ISODate)
        # self.mdCache[lyr.source()] = (sid, dtg)

        if lyr.crs() == crs:
            pts = points
        else:
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(crs)
            trans.setDestinationCrs(lyr.crs())
            pts = [trans.transform(pt) for pt in points]

        results = {
            TemporalProfileUtils.Source: lyr.source(),
            TemporalProfileUtils.Date: dtg,
            TemporalProfileUtils.Sensor: sid,
            TemporalProfileUtils.Values: [],
            '_points_lyr_crs': pts,
        }

        dp: QgsRasterDataProvider = lyr.dataProvider()
        for i_pt, pt in enumerate(pts):
            profile_values = None
            if lyr.extent().contains(pt):
                v = TemporalProfileUtils.profileValues(dp, pt)
                if any(v):
                    profile_values = v
            results[TemporalProfileUtils.Values].append(profile_values)

        return results, error

    def run(self) -> bool:

        # create an empty temporal profile for each point
        temporal_profiles = [TemporalProfileUtils.createEmptyProfile() for _ in self.mPoints]
        errors = []
        nTotal = len(self.mSources)
        tnow = datetime.now()
        tNextProgress = tnow + self.mProgressInterval
        tNextInterimResult = tnow + self.mInterimResultsInterval

        def appendResults(results, error):
            nonlocal tnow, tNextProgress, tNextInterimResult

            if results:
                for j, (profile, pt) in enumerate(zip(results[TemporalProfileUtils.Values], self.mPoints)):
                    if profile:
                        tp = temporal_profiles[j]
                        # append profile + sensor infos to temporal profiles
                        tp[TemporalProfileUtils.Values].append(profile)
                        for k in [TemporalProfileUtils.Sensor,
                                  TemporalProfileUtils.Date,
                                  TemporalProfileUtils.Source]:
                            tp[k].append(results[k])

            if error:
                errors.append(error)

            s = ""
            # add to existing profiles

            tNow = datetime.now()
            if tNow > tNextProgress:
                if self.isCanceled():
                    return False

                progress = (i + 1) / nTotal * 100
                self.setProgress(progress)
                tNextProgress = tNow + self.mProgressInterval

            if self.mInterimResults and tNow > tNextInterimResult:
                profiles = self.createTemporalProfiles(temporal_profiles)
                self.interimResults.emit(profiles)

        if self.nThreads > 1:
            self.mTreadPoolExecutor = ThreadPoolExecutor(max_workers=self.nThreads)
            for i, src in enumerate(self.mSources):
                future = self.mTreadPoolExecutor.submit(self.loadFromSource,
                                                        self.lyrCache.get(src, src),
                                                        self.mPoints,
                                                        self.mCrs)
                self.mFutures.append(future)

            for i, future in enumerate(as_completed(self.mFutures)):
                results, error = future.result()
                appendResults(results, error)
        else:
            for i, src in enumerate(self.mSources):
                results, error = self.loadFromSource(
                    self.lyrCache.get(src, src),
                    self.mPoints,
                    self.mCrs)
                appendResults(results, error)

        # keep only profile dictionaries for which we have at least one values

        t0 = datetime.now()
        self.mProfiles = self.createTemporalProfiles(temporal_profiles)

        td = datetime.now() - t0
        self.setProgress(100)

        return True

    def createTemporalProfiles(self, unsorted_profile_data) -> list:
        """
        Sorts the temporal profiles by sensor and date-time information
        Empty profiles will be returned as None
        :param list:
        :return:
        """
        sorted_profiles = []
        for unsorted_data in unsorted_profile_data:
            dates = unsorted_data[TemporalProfileUtils.Date]
            d = None
            if len(dates) == 0:
                sorted_profiles.append(None)
            else:
                dates = np.asarray(dates)
                i_sorted = np.argsort(dates)

                dates = [str(dates[i]) for i in i_sorted]

                values = unsorted_data[TemporalProfileUtils.Values]
                values = [values[i] for i in i_sorted]

                sensor = unsorted_data[TemporalProfileUtils.Sensor]
                sensor = [sensor[i] for i in i_sorted]
                sensor_ids = np.unique(sensor).tolist()
                sensor = [sensor_ids.index(s) for s in sensor]

                sources = unsorted_data[TemporalProfileUtils.Source]
                sources = [sources[i] for i in i_sorted]

                d = {
                    TemporalProfileUtils.Values: values,
                    TemporalProfileUtils.SensorIDs: sensor_ids,
                    TemporalProfileUtils.Sensor: sensor,
                    TemporalProfileUtils.Date: dates,
                    TemporalProfileUtils.Source: sources
                }

                success, err = TemporalProfileUtils.verifyProfile(d)
                assert success, err

            sorted_profiles.append(d)
        return sorted_profiles


class TemporalProfileLayerFieldModel(QAbstractListModel):
    """
    A list model to show all available temporal profile layer fields
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mItems = []
        self.mProject = QgsProject.instance()

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project
        self.update_model()

    def project(self) -> QgsProject:
        return self.mProject

    def update_model(self):
        """Populate the model with vector layers and their string fields."""
        self.beginResetModel()
        self.mItems.clear()

        new_items = []
        for layer in self.mProject.mapLayers().values():
            for tpField in TemporalProfileUtils.profileFields(layer):
                new_items.append((layer.id(), tpField.name()))
        self.mItems.extend(sorted(new_items))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.mItems)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()

        c = index.column()
        item = self.mItems[index.row()]
        layerId, fieldName = item

        layer = self.mProject.mapLayer(layerId)
        if not isinstance(layer, QgsVectorLayer):
            return None

        field: QgsField = layer.fields()[fieldName]
        if role == Qt.DisplayRole:
            # Display "Layer Name - Field Name"
            return f'{layer.name()}: "{fieldName}"'
        elif role == Qt.ToolTipRole:
            # Tooltip: Layer Name, Layer ID, Field Name, Field Type
            return (f"Layer: {layer.name()}<br>"
                    f"ID: {layer.id().strip()})<br>"
                    f'Source: {layer.source()}<br>'
                    f'Field: "{field.name()}" {field.displayType(True)}')
        elif role == Qt.DecorationRole:
            return QgsIconUtils.iconForLayer(layer)
        elif role == Qt.UserRole:
            # Return the field name
            return layer, field
        elif role == Qt.UserRole + 1:
            # Return the layer
            return layer
        elif role == Qt.UserRole + 2:
            # Return the QgsField object
            return field
        return None

    def roleNames(self):
        """Define custom roles for the model."""
        roles = super().roleNames()
        roles[Qt.UserRole] = b"layer_field"
        roles[Qt.UserRole + 1] = b"layer"
        roles[Qt.UserRole + 2] = b"field"
        return roles


class TemporalProfileLayerFieldComboBox(QComboBox):

    def __init__(self, *args, project: QgsProject = None, **kwds):
        super().__init__(*args, **kwds)

        if project is None:
            project = QgsProject.instance()

        self.mModel = TemporalProfileLayerFieldModel()
        self.mModel.setProject(project)

        self.setModel(self.mModel)

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)

    def project(self) -> QgsProject:
        return self.mModel.project()

    def layerField(self) -> Tuple[Optional[QgsVectorLayer], Optional[QgsField]]:
        """

        :return:
        """
        if self.currentIndex() < 0:
            return None, None
        else:
            return self.currentData(Qt.UserRole)

    def setLayerField(self, layer: Union[QgsVectorLayer, str], field: Union[QgsField, str]) -> bool:
        if isinstance(layer, QgsMapLayer):
            layer = layer.id()

        if isinstance(field, QgsField):
            field = field.name()

        for i in range(self.count()):
            lyr, fn = self.itemData(i, Qt.UserRole)
            lyr = lyr.id()
            fn = fn.name()
            if lyr == layer and fn == field:
                self.setCurrentIndex(i)
                return True

        return False
