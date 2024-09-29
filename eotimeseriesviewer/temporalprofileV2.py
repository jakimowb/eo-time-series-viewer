import json
import os.path
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Union
from uuid import uuid4

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.qgisenums import QMETATYPE_QSTRING, QMETATYPE_QVARIANTMAP
from eotimeseriesviewer.tasks import EOTSVTask
from eotimeseriesviewer.timeseries import sensor_id, sensorIDtoProperties
from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields,
                       QgsPointXY, QgsProject, QgsRasterDataProvider, QgsRasterLayer, QgsVectorFileWriter,
                       QgsVectorLayer)

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

TPF_COMMENT = 'Temporal profile data'
TPF_TYPE = QMETATYPE_QVARIANTMAP
TPF_TYPENAME = 'JSON'
TPF_SUBTYPE = None
TPL_NAME = 'Temporal Profile Layer'


class TemporalProfileUtils(object):
    Source = 'source'  # optional
    Date = 'date'
    SensorIDs = 'sensor_ids'
    Sensor = 'sensor'
    Values = 'values'

    @staticmethod
    def isProfileField(field: QgsField) -> bool:

        return isinstance(field, QgsField) and field.type() == TPF_TYPE and field.comment() == TPF_COMMENT

    @staticmethod
    def isProfileDict(d: dict) -> bool:
        for k in [TemporalProfileUtils.Date,
                  TemporalProfileUtils.SensorIDs,
                  TemporalProfileUtils.Sensor,
                  TemporalProfileUtils.Values]:
            if k not in d:
                return False

        return True

    @staticmethod
    def verifyProfile(profileDict: dict) -> Tuple[bool, str]:

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

    @staticmethod
    def profileJsonFromDict(d: dict) -> str:
        txt = json.dumps(d)
        return txt

    @staticmethod
    def profileDictFromJson(json_string: str) -> dict:
        data = json.loads(json_string)
        return data

    @staticmethod
    def createProfileField(name: str) -> QgsField:
        field = QgsField(name, type=QMETATYPE_QVARIANTMAP, typeName=TPF_TYPENAME)
        field.setComment(TPF_COMMENT)
        return field

    @staticmethod
    def temporalProfileFields(source: Union[str, Path, QgsFeature, QgsVectorLayer, QgsFields]):

        if isinstance(source, (str, Path)):
            lyr = QgsVectorLayer(Path(str).as_posix())
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

        self.mInfo = info.copy() if info else None
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

                dtg = ImageDateUtils.datetimeFromLayer(lyr)
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
                profile[TemporalProfileUtils.Date].append(dtg.isoformat())

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
