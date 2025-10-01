# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import bisect
import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterator, List, Optional, Set, Union, Dict, Generator

import numpy as np
from osgeo import gdal

from eotimeseriesviewer import messageLog
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.utils import relativePath, SpatialExtent
from eotimeseriesviewer.sensors import sensorIDtoProperties, SensorInstrument, SensorMatching
from eotimeseriesviewer.settings.settings import EOTSVSettingsManager
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource
from eotimeseriesviewer.timeseries.tasks import TimeSeriesFindOverlapTask, TimeSeriesLoadingTask
from eotimeseriesviewer.utils import findNearestDateIndex
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QDateTime, QModelIndex, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDateTimeRange, \
    QgsRasterLayer, QgsRectangle, QgsTask, QgsProcessingFeedback, QgsProcessingMultiStepFeedback, \
    QgsTaskManager
from qgis.core import QgsSpatialIndex

logger = logging.getLogger(__name__)
gdal.SetConfigOption('VRT_SHARED_SOURCE', '0')  # !important. really. do not change this.

DEFAULT_CRS = 'EPSG:4326'

LUT_WAVELENGTH_UNITS = {}
for siUnit in [r'nm', r'μm', r'mm', r'cm', r'dm']:
    LUT_WAVELENGTH_UNITS[siUnit] = siUnit
LUT_WAVELENGTH_UNITS[r'nanometers'] = r'nm'
LUT_WAVELENGTH_UNITS[r'micrometers'] = r'μm'
LUT_WAVELENGTH_UNITS[r'um'] = r'μm'
LUT_WAVELENGTH_UNITS[r'millimeters'] = r'mm'
LUT_WAVELENGTH_UNITS[r'centimeters'] = r'cm'
LUT_WAVELENGTH_UNITS[r'decimeters'] = r'dm'


def transformGeometry(geom, crsSrc, crsDst, trans=None):
    if trans is None:
        assert isinstance(crsSrc, QgsCoordinateReferenceSystem)
        assert isinstance(crsDst, QgsCoordinateReferenceSystem)
        return transformGeometry(geom, None, None, trans=QgsCoordinateTransform(crsSrc, crsDst))
    else:
        assert isinstance(trans, QgsCoordinateTransform)
        return trans.transform(geom)


METRIC_EXPONENTS = {
    "nm": -9, "um": -6, "mm": -3, "cm": -2, "dm": -1, "m": 0, "hm": 2, "km": 3
}
# add synonyms
METRIC_EXPONENTS['nanometers'] = METRIC_EXPONENTS['nm']
METRIC_EXPONENTS['micrometers'] = METRIC_EXPONENTS['um']
METRIC_EXPONENTS['millimeters'] = METRIC_EXPONENTS['mm']
METRIC_EXPONENTS['centimeters'] = METRIC_EXPONENTS['cm']
METRIC_EXPONENTS['decimeters'] = METRIC_EXPONENTS['dm']
METRIC_EXPONENTS['meters'] = METRIC_EXPONENTS['m']
METRIC_EXPONENTS['hectometers'] = METRIC_EXPONENTS['hm']
METRIC_EXPONENTS['kilometers'] = METRIC_EXPONENTS['km']


def convertMetricUnit(value, u1, u2):
    assert u1 in METRIC_EXPONENTS.keys()
    assert u2 in METRIC_EXPONENTS.keys()

    e1 = METRIC_EXPONENTS[u1]
    e2 = METRIC_EXPONENTS[u2]

    return value * 10 ** (e1 - e2)


def getDS(pathOrDataset) -> Optional[gdal.Dataset]:
    """
    Returns a gdal.Dataset
    :param pathOrDataset: str | gdal.Dataset | QgsRasterLayer | None
    :return:
    """
    if isinstance(pathOrDataset, QgsRasterLayer):
        return getDS(pathOrDataset.source())
    elif isinstance(pathOrDataset, gdal.Dataset):
        return pathOrDataset
    elif isinstance(pathOrDataset, str):
        ds = gdal.Open(pathOrDataset)
        assert isinstance(ds, gdal.Dataset)
        return ds
    else:
        return None


class TimeSeries(QAbstractItemModel):
    """
    The sorted list of data sources that specify the time series
    """

    sigTimeSeriesDatesAdded = pyqtSignal(list)
    sigTimeSeriesDatesRemoved = pyqtSignal(list)

    sigLoadingTaskFinished = pyqtSignal()
    sigFindOverlapTaskFinished = pyqtSignal()

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigSensorNameChanged = pyqtSignal(SensorInstrument)

    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)

    sigVisibilityChanged = pyqtSignal()
    sigProgress = pyqtSignal(float)
    sigMessage = pyqtSignal(str, Qgis.MessageLevel)
    _sep = ';'

    cDate = 0
    cSensor = 1
    cNS = 2
    cNL = 3
    cNB = 4
    cCRS = 5
    cImages = 6

    def __init__(self, imageFiles=None):
        super(TimeSeries, self).__init__()

        self.mLUT_TSD: Dict[str, TimeSeriesDate] = {}
        self.mLUT_TSS: Dict[str, TimeSeriesSource] = {}

        self.mTSDs: List[TimeSeriesDate] = list()
        self.mSensors: List[SensorInstrument] = []
        self.mShape = None
        self.mTreeView: QTreeView = None
        self.mDateTimePrecision = DateTimePrecision.Day
        self.mSensorMatchingFlags = SensorMatching.PX_DIMS

        self.mSpatialIndex: QgsSpatialIndex = QgsSpatialIndex()

        self.mLUT_Path2TSD = {}
        self.mVisibleDates: Set[TimeSeriesDate] = set()

        self.mColumnNames = {
            self.cDate: 'Date-Time',
            self.cSensor: 'Sensor',
            self.cNS: 'ns',
            self.cNB: 'nb',
            self.cNL: 'nl',
            self.cCRS: 'CRS',
            self.cImages: 'Source Image(s)'
        }
        self.mColumnToolTip = {
            self.cDate: 'Date and time of observation, grouped by sensor',
            self.cSensor: 'Sensor or product type',
            self.cNS: 'Number of raster samples / pixel in x direction',
            self.cNB: 'Number of raster bands',
            self.cNL: 'Number of raster lines / pixel in y direction',
            self.cCRS: 'Coordinate Reference System of the raster source',
            self.cImages: 'Source image(s) of the time series'
        }
        self.mRootIndex = QModelIndex()
        self.mTasks = dict()

        if imageFiles is not None:
            self.addSources(imageFiles)

    def focusVisibility(self,
                        ext: SpatialExtent,
                        date_of_interest: Optional[QDateTime] = None):
        """
        Changes TSDs visibility according to its intersection with a SpatialExtent
        :param date_of_interest:
        :type date_of_interest:
        :param ext: SpatialExtent
        """
        assert isinstance(ext, SpatialExtent)

        sources = list(self.timeSeriesSources())

        if len(sources) > 0:
            settings = EOTSVSettingsManager.settings()
            qgsTask = TimeSeriesFindOverlapTask(ext,
                                                sources,
                                                date_of_interest=date_of_interest,
                                                n_threads=settings.qgsTaskFileReadingThreads,
                                                sample_size=settings.rasterOverlapSampleSize)

            qgsTask.sigTimeSeriesSourceOverlap.connect(self.onFoundOverlap)
            qgsTask.progressChanged.connect(self.sigProgress.emit)
            qgsTask.executed.connect(self.onTaskFinished)

            tm: QgsTaskManager = QgsApplication.taskManager()
            # stop previous tasks, allow to run one only
            for t in tm.tasks():
                if isinstance(t, TimeSeriesFindOverlapTask):
                    t.cancel()
            tid = tm.addTask(qgsTask)
            self.mTasks[tid] = qgsTask

    def onFoundOverlap(self, results: dict):

        URI2TSS = dict()
        for tsd in self:
            for tss in tsd:
                URI2TSS[tss.source()] = tss

        affectedTSDs = set()
        for tssUri, b in results.items():
            assert isinstance(tssUri, str)
            tss = URI2TSS.get(tssUri, None)
            if isinstance(tss, TimeSeriesSource):
                tss.setIsVisible(b)
                tsd = tss.timeSeriesDate()
                if isinstance(tsd, TimeSeriesDate):
                    affectedTSDs.add(tsd)
        if len(affectedTSDs) == 0:
            return

        affectedTSDs = sorted(affectedTSDs)

        rowMin = rowMax = None
        for i, tsd in enumerate(affectedTSDs):
            idx = self.tsdToIdx(tsd)
            if i == 0:
                rowMin = rowMax = idx.row()
            else:
                rowMin = min(rowMin, idx.row())
                rowMax = max(rowMax, idx.row())

        idx0 = self.index(rowMin, 0)
        idx1 = self.index(rowMax, 0)
        self.dataChanged.emit(idx0, idx1, [Qt.CheckStateRole])

    def setVisibleDates(self, tsds: list):
        """
        Sets the TimeSeriesDates currently shown
        :param tsds: [list-of-TimeSeriesDate]
        """
        self.mVisibleDates.clear()
        self.mVisibleDates.update(tsds)
        for tsd in tsds:
            assert isinstance(tsd, TimeSeriesDate)
            if tsd in self:
                idx = self.tsdToIdx(tsd)
                # force reset of background color
                idx2 = self.index(idx.row(), self.columnCount() - 1)
                self.dataChanged.emit(idx, idx2, [Qt.BackgroundColorRole])

    def findMatchingSensor(self, sensorID: Union[str, tuple, dict]) -> Optional[SensorInstrument]:
        if isinstance(sensorID, str):
            nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorIDtoProperties(sensorID)

        elif isinstance(sensorID, tuple):
            assert len(sensorID) == 7
            nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorID
        else:
            raise NotImplementedError()

        PX_DIMS = (nb, px_size_y, px_size_x, dt)
        for sensor in self.sensors():
            PX_DIMS2 = (sensor.nb, sensor.px_size_y, sensor.px_size_x, sensor.dataType)

            samePxDims = PX_DIMS == PX_DIMS2
            sameName = sensor.mNameOriginal == name
            sameWL = wlu == sensor.wlu and np.array_equal(wl, sensor.wl)

            if bool(self.mSensorMatchingFlags & SensorMatching.PX_DIMS) and not samePxDims:
                continue

            if bool(self.mSensorMatchingFlags & SensorMatching.NAME) and not sameName:
                continue

            if bool(self.mSensorMatchingFlags & SensorMatching.WL) and not sameWL:
                continue

            return sensor

        return None

    def sensor(self, sensor_id: str) -> SensorInstrument:
        """
        Returns the sensor with sid = sid
        :param sensor_id: str, sensor id
        :return: SensorInstrument
        """
        assert isinstance(sensor_id, str)

        nb, px_size_x, px_size_y, dt, wl, wlu, name = sensorIDtoProperties(sensor_id)

        refValues = (nb, px_size_y, px_size_x, dt, wl, wlu, name)
        for sensor in self.sensors():
            sValues = (
                sensor.nb, sensor.px_size_y, sensor.px_size_x, sensor.dataType, sensor.wl, sensor.wlu,
                sensor.mNameOriginal)
            if refValues == sValues:
                return sensor

        return None

    def sensors(self) -> List[SensorInstrument]:
        """
        Returns the list of sensors derived from the TimeSeries data sources
        :return: [list-of-SensorInstruments]
        """
        return self.mSensors[:]

    def loadFromFile(self, path: Union[str, Path], n_max=None, runAsync: bool = None):
        """
        Loads a CSV file with source images of a TimeSeries
        :param path: str, Path of CSV file
        :param n_max: optional, maximum number of files to load
        :param runAsync: optional,
        """

        images = self.sourcesFromFile(path)

        if n_max:
            n_max = min([len(images), n_max])
            images = images[0:n_max]

        self.addSources(images, runAsync=runAsync)

    @classmethod
    def sourcesFromFile(cls, path: Union[str, Path]) -> List[str]:
        path = Path(path)
        refDir = Path(path).parent
        images = []
        masks = []

        if path.suffix in ['.csv', '.txt']:
            with open(path, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if re.match('^[ ]*[;#&]', line):
                        continue
                    line = line.strip()
                    path = Path(line)
                    if not path.is_absolute():
                        path = refDir / path

                    images.append(path.as_posix())
        elif path.suffix == '.json':

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                sensors = data.get('sensors', {})
                # convert json str keys ('0') to int (0)
                sensors = {int(k): v for k, v in sensors.items()}

                for source in data.get('sources', []):

                    path = Path(source['source'])
                    if not path.is_absolute():
                        path = (refDir / path).resolve()
                        source['source'] = str(path)
                    i_sensor = source.get('sensor', None)
                    sid = sensors.get(i_sensor, None)
                    tss = TimeSeriesSource.fromMap(source, sid=sid)
                    if isinstance(tss, TimeSeriesSource):
                        images.append(tss)

        return images

    def saveToFile(self, path: Union[str, Path], relative_path: bool = True) -> Optional[Path]:
        """
        Saves the TimeSeries sources into a CSV or JSON file
        :param path: str, path of CSV file
        :return: path of CSV file
        """
        if isinstance(path, str):
            path = Path(path)
        assert isinstance(path, Path)

        assert path.suffix in ['.csv', '.txt', '.json']

        to_write = None

        if path.suffix in ['.csv', '.txt']:
            lines = []
            lines.append('#Time series definition file: {}'.format(np.datetime64('now').astype(str)))
            lines.append('#<image path>')
            for TSD in self:
                assert isinstance(TSD, TimeSeriesDate)
                for TSS in TSD:
                    uri = TSS.source()
                    if relative_path:
                        uri = relativePath(uri, path.parent)
                    lines.append(str(uri))
            to_write = '\n'.join(lines)
        elif path.suffix == '.json':
            data = self.asMap()
            if relative_path:
                for source in data.get('sources', []):
                    source['source'] = str(relativePath(source['source'], path.parent))

            to_write = json.dumps(data, indent=4, ensure_ascii=False)

        if isinstance(to_write, str):
            with open(path, 'w', newline='\n', encoding='utf-8') as f:
                f.write(to_write)
                messageLog('Time series source images written to {}'.format(path))
            return path
        else:
            return None

    def pixelSizes(self):
        """
        Returns the pixel sizes of all SensorInstruments
        :return: [list-of-QgsRectangles]
        """

        r = []
        for sensor in self.mSensors2TSDs.keys():
            r.append((QgsRectangle(sensor.px_size_x, sensor.px_size_y)))
        return r

    def maxSpatialExtent(self, crs: QgsCoordinateReferenceSystem = None) -> SpatialExtent:
        """
        Returns the maximum SpatialExtent of all images of the TimeSeries
        :param crs: QgsCoordinateSystem to express the SpatialExtent coordinates.
        :return:
        """
        extent = None
        for i, tsd in enumerate(self.mTSDs):
            assert isinstance(tsd, TimeSeriesDate)
            ext = tsd.spatialExtent(crs=crs)
            if isinstance(extent, SpatialExtent):
                extent = extent.combineExtentWith(ext)
            else:
                extent = ext

        return extent

    def getTSD(self, pathOfInterest):
        """
        Returns the TimeSeriesDate related to an image source
        :param pathOfInterest: str, image source uri
        :return: TimeSeriesDate
        """
        tsd = self.mLUT_Path2TSD.get(pathOfInterest)
        if isinstance(tsd, TimeSeriesDate):
            return tsd
        else:
            for tsd in self.mTSDs:
                assert isinstance(tsd, TimeSeriesDate)
                if pathOfInterest in tsd.sourceUris():
                    return tsd
        return None

    def tsd(self, dtr: QgsDateTimeRange, sensor: Union[None, SensorInstrument, str]) -> Optional[TimeSeriesDate]:
        """
        Returns the TimeSeriesDate identified by date-time-range and sensorID
        :param dtr: QgsDateTimeRange
        :param sensor: SensorInstrument | str with sensor id
        :return:
        """
        assert isinstance(dtr, QgsDateTimeRange)
        if isinstance(sensor, str):
            sensor = self.sensor(sensor)

        if isinstance(sensor, SensorInstrument):
            for tsd in self.mTSDs:
                if tsd.dateTimeRange() == dtr and tsd.sensor() == sensor:
                    return tsd
        else:
            for tsd in self.mTSDs:
                if tsd.dateTimeRange() == dtr:
                    return tsd
        return None

    def insertTSD(self, tsd: TimeSeriesDate) -> TimeSeriesDate:
        """
        Inserts a TimeSeriesDate
        :param tsd: TimeSeriesDate
        """
        # insert sorted by time & sensor
        assert tsd not in self.mTSDs
        assert tsd.sensor() in self.mSensors

        self._connectTSD(tsd)

        row = bisect.bisect(self.mTSDs, tsd)
        self.beginInsertRows(self.mRootIndex, row, row)
        self.mTSDs.insert(row, tsd)
        self.endInsertRows()
        return tsd

    def _connectTSD(self, tsd: TimeSeriesDate):
        tsd.mTimeSeries = self
        tsd.sigRemoveMe.connect(lambda t=tsd: self.removeTSDs([t]))

        tsd.rowsAboutToBeRemoved.connect(
            lambda p, first, last, t=tsd: self.beginRemoveRows(self.tsdToIdx(t), first, last))
        tsd.rowsRemoved.connect(self.endRemoveRows)
        tsd.rowsAboutToBeInserted.connect(
            lambda p, first, last, t=tsd: self.beginInsertRows(self.tsdToIdx(t), first, last))
        tsd.rowsInserted.connect(self.endInsertRows)

        tsd.sigSourcesAdded.connect(self.sigSourcesAdded)
        tsd.sigSourcesRemoved.connect(self.sigSourcesRemoved)

    def showTSDs(self, tsds: list, b: bool = True):
        tsds = sorted(set([t for t in tsds if t in self]))
        if len(tsds) == 0:
            return

        idx0 = self.tsdToIdx(tsds[0])
        idx1 = self.tsdToIdx(tsds[-1])

        for i, tsd in enumerate(tsds):
            assert isinstance(tsd, TimeSeriesDate)
            for tss in tsd:
                tss.setIsVisible(b)

        self.dataChanged.emit(idx0, idx1, [Qt.CheckStateRole])
        self.sigVisibilityChanged.emit()

    def hideTSDs(self, tsds):
        self.showTSDs(tsds, False)

    def removeTSDs(self, tsds: List[TimeSeriesDate]):
        """
        Removes a list of TimeSeriesDate
        :param tsds: [list-of-TimeSeriesDate]
        """
        removed = list()
        toRemove = set()
        for t in tsds:
            if isinstance(t, TimeSeriesDate):
                toRemove.add(t)
            if isinstance(t, TimeSeriesSource):
                toRemove.add(t.timeSeriesDate())
        toRemove = sorted(list(toRemove))
        removed = []
        while len(toRemove) > 0:
            block: List[TimeSeriesDate] = [toRemove.pop(0)]

            r0 = r1 = self.tsdToIdx(block[0]).row()
            while len(toRemove) > 0:
                if self.index(r1 + 1, 0).data(Qt.UserRole) != toRemove[0]:
                    break
                else:
                    block.append(toRemove.pop(0))
                    r1 += 1

            self.beginRemoveRows(self.mRootIndex, r0, r1)
            for tsd in block:
                self.mTSDs.remove(tsd)
                tsd.mTimeSeries = None
                tsd.sigSourcesAdded.disconnect(self.sigSourcesAdded)
                tsd.sigSourcesRemoved.disconnect(self.sigSourcesRemoved)

                for tss in tsd.sources():
                    self.mSpatialIndex.deleteFeature(tss.feature())

                removed.append(tsd)
            self.endRemoveRows()

        if len(removed) > 0:
            pathsToRemove = [path for path, tsd in self.mLUT_Path2TSD.items() if tsd in removed]
            for path in pathsToRemove:
                self.mLUT_Path2TSD.pop(path)

            self.checkSensorList()
            self.sigTimeSeriesDatesRemoved.emit(removed)

    def timeSeriesSources(self,
                          copy: Optional[bool] = False,
                          sensor: Optional[SensorInstrument] = None) -> List[TimeSeriesSource]:
        """
        Returns a flat list of all sources
        :param copy:
        :return:
        """
        if isinstance(sensor, SensorInstrument):
            tsds = self.tsds(None, sensor)
        else:
            tsds = self[:]

        for tsd in tsds:
            for tss in tsd:
                if copy:
                    tss = tss.clone()
                yield tss

    def tsds(self, date: np.datetime64 = None, sensor: SensorInstrument = None) -> List[TimeSeriesDate]:

        """
        Returns a list of  TimeSeriesDate of the TimeSeries. By default all TimeSeriesDate will be returned.
        :param date: numpy.datetime64 to return the TimeSeriesDate for
        :param sensor: SensorInstrument of interest to return the [list-of-TimeSeriesDate] for.
        :return: [list-of-TimeSeriesDate]
        """
        tsds = self.mTSDs[:]
        if date:
            tsds = [tsd for tsd in tsds if tsd.dtg() == date]
        if sensor:
            tsds = [tsd for tsd in tsds if tsd.sensor() == sensor]
        return tsds

    def clear(self):
        """
        Removes all data sources from the TimeSeries (which will be empty after calling this routine).
        """
        self.removeTSDs(self[:])

    def addSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]) -> List[SensorInstrument]:
        """
        Adds a Sensor
        :param sensors: SensorInstrument or list of SensorInstruments
        """
        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]
        added_sensors = []
        for sensor in sensors:
            assert isinstance(sensor, SensorInstrument)

            if sensor not in self.mSensors:
                self._connectSensor(sensor)
                self.mSensors.append(sensor)
                self.sigSensorAdded.emit(sensor)
                added_sensors.append(sensor)
        return added_sensors

    def _connectSensor(self, sensor: SensorInstrument):
        sensor.sigNameChanged.connect(self.onSensorNameChanged)

    def onSensorNameChanged(self, name: str):
        sensor = self.sender()

        if isinstance(sensor, SensorInstrument) and sensor in self.sensors():
            idx0 = self.index(0, self.cSensor)
            idx1 = self.index(self.rowCount() - 1, self.cSensor)
            self.dataChanged.emit(idx0, idx1)
            self.sigSensorNameChanged.emit(sensor)
        s = ""

    def checkSensorList(self):
        """
        Removes sensors without linked TSD / no data
        """
        to_remove = []
        for sensor in self.sensors():
            tsds = [tsd for tsd in self.mTSDs if tsd.sensor() == sensor]
            if len(tsds) == 0:
                to_remove.append(sensor)
        for sensor in to_remove:
            self.removeSensor(sensor)

    def removeSensor(self, sensor: SensorInstrument) -> Optional[SensorInstrument]:
        """
        Removes a sensor and all linked images
        :param sensor: SensorInstrument
        :return: SensorInstrument or none, if sensor was not defined in the TimeSeries
        """
        assert isinstance(sensor, SensorInstrument)
        if sensor in self.mSensors:
            tsds = [tsd for tsd in self.mTSDs if tsd.sensor() == sensor]
            self.removeTSDs(tsds)
            if sensor in self.mSensors:
                self.mSensors.remove(sensor)
            self.sigSensorRemoved.emit(sensor)
            return sensor
        return None

    def addTimeSeriesSources(self, sources: List[TimeSeriesSource]):
        """
        Adds a list of TimeSeriesSource to the time series
        :param sources:  list-of-TimeSeriesSources
        """
        assert isinstance(sources, list)
        n = len(sources)
        if n > 0:
            # print(f'Add {len(sources)} sources...', flush=True)

            addedDates = []
            t0 = datetime.datetime.now()
            for i, source in enumerate(sources):
                assert isinstance(source, TimeSeriesSource)
                newTSD = self.addTimeSeriesSource(source)
                if isinstance(newTSD, TimeSeriesDate):
                    addedDates.append(newTSD)
            t1 = datetime.datetime.now()

            if len(addedDates) > 0:
                self.sigTimeSeriesDatesAdded.emit(addedDates)
            t2 = datetime.datetime.now()
            dt1 = (t1 - t0).total_seconds()
            dt2 = (t2 - t1).total_seconds()

            logger.debug(f'# added {n} sources: t_avg: {dt1 / n: 0.3f}s t_total: {dt1} s, signals: {dt2: 0.3f}s')

    def addSources(self,
                   sources: List[Union[str, Path, TimeSeriesSource, gdal.Dataset, QgsRasterLayer]],
                   runAsync: bool = None,
                   n_threads: Optional[int] = None):
        """
        Adds source images to the TimeSeries
        :param sources: list of source images, e.g., a list of file paths
        :param runAsync: bool
        :param n_threads:
        """

        if runAsync is None:
            runAsync = EOTSVSettingsManager.settings().qgsTaskAsync

        source_paths = []
        ts_sources = []
        for s in sources:
            path = None
            if isinstance(s, TimeSeriesSource):
                ts_sources.append(s)
                continue
            elif isinstance(s, gdal.Dataset):
                path = s.GetDescription()
            elif isinstance(s, QgsRasterLayer):
                path = s.source()
            else:
                path = str(s)
            if path:
                source_paths.append(path)

        if len(ts_sources) > 0:
            self.addTimeSeriesSources(ts_sources)

        if len(source_paths) > 0:
            if n_threads is None:
                settings = EOTSVSettingsManager.settings()
                n_threads = settings.qgsTaskFileReadingThreads
            qgsTask = TimeSeriesLoadingTask(source_paths,
                                            description=f'Load {len(source_paths)} images',
                                            n_threads=n_threads)

            qgsTask.imagesLoaded.connect(self.addTimeSeriesSources)
            qgsTask.progressChanged.connect(self.sigProgress.emit)
            qgsTask.executed.connect(self.onTaskFinished)

            self.mTasks[id(qgsTask)] = qgsTask

            if runAsync:
                tm: QgsTaskManager = QgsApplication.taskManager()
                assert isinstance(tm, QgsTaskManager)
                tm.addTask(qgsTask)
            else:
                qgsTask.run_serial()

    def onRemoveTask(self, key):
        # print(f'remove {key}', flush=True)
        if isinstance(key, QgsTask):
            key = id(key)
        if key in self.mTasks.keys():
            self.mTasks.pop(key)

    def onTaskFinished(self, success, task: QgsTask):
        # print(':: onAddSourcesAsyncFinished')
        if isinstance(task, TimeSeriesLoadingTask):
            if len(task.invalidSources()) > 0:
                info = ['Unable to load {} data source(s):'.format(len(task.mInvalidSources))]
                for (s, ex) in task.mInvalidSources:
                    info.append('Path="{}"\nError="{}"'.format(str(s), str(ex).replace('\n', ' ')))
                info = '\n'.join(info)
                messageLog(info, Qgis.Critical)

            self.sigLoadingTaskFinished.emit()

        elif isinstance(task, TimeSeriesFindOverlapTask):
            # if success:
            #    intersections = task.intersections()
            #    if len(intersections) > 0:
            #        self.onFoundOverlap(intersections)
            self.sigFindOverlapTaskFinished.emit()
        self.onRemoveTask(task)

    def addTimeSeriesSource(self, tss: TimeSeriesSource) -> TimeSeriesDate:
        """
        :param tss:
        :return: TimeSeriesDate (if new created)
        """
        assert isinstance(tss, TimeSeriesSource)

        newTSD = None

        tsr: QgsDateTimeRange = ImageDateUtils.dateRange(tss.dtg(), self.mDateTimePrecision)

        sid = tss.sid()
        sensor = self.findMatchingSensor(sid)

        # if necessary, add a new sensor instance
        if not isinstance(sensor, SensorInstrument):
            sensor = SensorInstrument(sid)
            assert sensor in self.addSensors(sensor)
        assert isinstance(sensor, SensorInstrument)
        tsd = self.tsd(tsr, sensor)

        # if necessary, add a new TimeSeriesDate instance
        if not isinstance(tsd, TimeSeriesDate):
            tsd = TimeSeriesDate(tsr, sensor)
            tsd.mTimeSeries = self
            newTSD = self.insertTSD(tsd)
            assert tsd == newTSD
            # addedDates.append(tsd)
        assert isinstance(tsd, TimeSeriesDate)

        # add the source

        tsd.addSource(tss)
        self.mSpatialIndex.addFeature(tss.feature())
        self.mLUT_Path2TSD[tss.source()] = tsd
        return newTSD

    def dateTimePrecision(self) -> DateTimePrecision:
        return self.mDateTimePrecision

    def setDateTimePrecision(self, mode: DateTimePrecision):
        """
        Sets the precision with which the parsed DateTime information will be handled.
        :param mode: TimeSeriesViewer:DateTimePrecision
        :return:
        """
        assert isinstance(mode, DateTimePrecision)
        all_sources = list(self.timeSeriesSources())
        self.beginResetModel()
        self.clear()
        self.mDateTimePrecision = mode
        self.addTimeSeriesSources(all_sources)
        self.endResetModel()
        # do we like to update existing sources?

    def setSensorMatching(self, flags: SensorMatching):
        """
        Sets the mode under which two source images can be considered as to be from the same sensor/product
        :param flags:
        :return:
        """
        assert isinstance(flags, SensorMatching)
        assert bool(flags & SensorMatching.PX_DIMS), 'SensorMatching flags PX_DIMS needs to be set'
        self.mSensorMatchingFlags = flags

    def sources(self) -> Generator[TimeSeriesSource, Any, None]:
        """
        Returns the input sources
        :return: iterator over [list-of-TimeSeriesSources]
        """

        for tsd in self:
            for source in tsd:
                yield source

    def sourceUris(self) -> List[str]:
        """
        Returns the uris of all sources
        :return: [list-of-str]
        """
        uris = []
        for tsd in self:
            assert isinstance(tsd, TimeSeriesDate)
            uris.extend(tsd.sourceUris())
        return uris

    def __len__(self):
        return len(self.mTSDs)

    def __iter__(self) -> Iterator[TimeSeriesDate]:
        return iter(self.mTSDs)

    def __getitem__(self, slice):
        return self.mTSDs[slice]

    def __delitem__(self, slice):
        self.removeTSDs(slice)

    def __contains__(self, item):
        return item in self.mTSDs

    def __repr__(self):
        info = []
        info.append('TimeSeries:')
        l = len(self)
        info.append('  Scenes: {}'.format(l))

        return '\n'.join(info)

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)

        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames.get(section, str(section))
            if role == Qt.ToolTipRole:
                return self.mColumnToolTip.get(section, str(section))
        return None

    def parent(self, index: QModelIndex) -> QModelIndex:
        """
        Returns the parent index of a QModelIndex `index`
        :param index: QModelIndex
        :return: QModelIndex
        """
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        tsd = None
        tss = None

        if isinstance(node, TimeSeriesDate):
            return self.mRootIndex

        elif isinstance(node, TimeSeriesSource):
            tss = node
            tsd = node.timeSeriesDate()
            return self.createIndex(self.mTSDs.index(tsd), 0, tsd)

    def rowCount(self, index: QModelIndex = None) -> int:
        """
        Return the row-count, i.e. number of child node for a TreeNode as index `index`.
        :param index: QModelIndex
        :return: int
        """
        if index is None:
            index = QModelIndex()

        if not index.isValid():
            return len(self)

        node = index.internalPointer()
        if isinstance(node, TimeSeriesDate):
            return len(node)

        if isinstance(node, TimeSeriesSource):
            return 0

    def columnCount(self, index: QModelIndex = None) -> int:
        """
        Returns the number of columns
        :param index: QModelIndex
        :return:
        """

        return len(self.mColumnNames)

    def connectTreeView(self, treeView):
        self.mTreeView = treeView

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        if parent is None:
            parent = self.mRootIndex
        else:
            assert isinstance(parent, QModelIndex)

        if row < 0 or row >= len(self):
            return QModelIndex()
        if column < 0 or column >= len(self.mColumnNames):
            return QModelIndex()

        if parent == self.mRootIndex:
            # TSD node
            if row < 0 or row >= len(self):
                return QModelIndex()
            return self.createIndex(row, column, self[row])

        elif parent.parent() == self.mRootIndex:
            # TSS node
            tsd = self.tsdFromIdx(parent)
            if row < 0 or row >= len(tsd):
                return QModelIndex()
            return self.createIndex(row, column, tsd[row])

        return QModelIndex()

    def tsdToIdx(self, tsd: TimeSeriesDate) -> QModelIndex:
        """
        Returns an QModelIndex pointing on a TimeSeriesDate of interest
        :param tsd: TimeSeriesDate
        :return: QModelIndex
        """
        row = self.mTSDs.index(tsd)
        return self.index(row, 0)

    def tsdFromIdx(self, index: QModelIndex) -> TimeSeriesDate:
        """
        Returns the TimeSeriesDate related to an QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if index.row() == -1 and index.column() == -1:
            return None
        elif not index.isValid():
            return None
        else:
            node = index.internalPointer()
            if isinstance(node, TimeSeriesDate):
                return node
            elif isinstance(node, TimeSeriesSource):
                return node.timeSeriesDate()

        return None

    def visibleTSDs(self) -> List[TimeSeriesDate]:
        """
        Returns the visible TSDs (which have TimeSeriesSource to be shown)
        :return:
        :rtype:
        """
        return [tsd for tsd in self if not tsd.checkState() == Qt.Unchecked]

    def asMap(self) -> dict:

        results = {}
        sources = []
        sensors = {}
        for tss in self.timeSeriesSources():
            d = tss.asMap()
            sid = tss.sid()
            d[TimeSeriesSource.MKeySensor] = sensors.setdefault(sid, len(sensors))
            sources.append(d)

        results['sensors'] = {i: sid if isinstance(sid, dict) else json.loads(sid)
                              for sid, i in sensors.items()}
        results['sources'] = sources
        return results

    def fromMap(self, data: dict, feedback: QgsProcessingFeedback = QgsProcessingFeedback()):

        multistep = QgsProcessingMultiStepFeedback(4, feedback)
        multistep.setCurrentStep(1)
        multistep.setProgressText('Clean')
        self.clear()

        uri_vis = dict()

        multistep.setCurrentStep(2)
        multistep.setProgressText('Read Sources')
        sources = []

        for d in data.get('sources', []):
            src = d.get('source')

            if src:
                tss = TimeSeriesSource.create(src)
                uri_vis[tss.source()] = d.get('visible', True)
                if isinstance(tss, TimeSeriesSource):
                    sources.append(tss)

        multistep.setCurrentStep(3)
        multistep.setProgressText('Add Sources')

        if len(sources) > 0:
            self.addTimeSeriesSources(sources)

        for tss in self.timeSeriesSources():
            tss.setIsVisible(uri_vis.get(tss.source(), tss.isVisible()))

    def data(self, index: QModelIndex, role: Qt.DisplayRole):
        """
        :param index: QModelIndex
        :param role: Qt.ItemRole
        :return: object
        """
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None

        node = index.internalPointer()
        tsd = None
        tss = None
        if isinstance(node, TimeSeriesSource):
            tsd = node.timeSeriesDate()
            tss = node
        elif isinstance(node, TimeSeriesDate):
            tsd = node

        if role == Qt.UserRole:
            return node

        c = index.column()

        if isinstance(node, TimeSeriesSource):
            if role == Qt.DisplayRole:
                if c == self.cDate:
                    dateStr = tss.dtg().toString(Qt.ISODate)
                    if role == Qt.DisplayRole:
                        return ImageDateUtils.shortISODateString(dateStr)
                    else:
                        return dateStr
                if c == self.cImages:
                    return tss.source()
                if c == self.cNB:
                    return tss.nb()
                if c == self.cNL:
                    return tss.nl()
                if c == self.cNS:
                    return tss.ns()
                if c == self.cCRS:
                    return tss.crs().description()
                if c == self.cSensor:
                    return tsd.sensor().name()

            if role == Qt.ToolTipRole:
                tt = []

                if c == self.cDate:
                    dateStr = tss.dtg().toString(Qt.ISODate)
                    if role == Qt.DisplayRole:
                        dateStr = ImageDateUtils.shortISODateString(dateStr)
                    tt.append(dateStr)
                if c == self.cCRS:
                    tt.append(tss.crs().description())
                else:
                    tt.append(self.data(index, role=Qt.DisplayRole))
                if tss.isMissing():
                    tt.append(f'<span style="color:red">Cannot open: "{tss.source()}"</span>')
                return '<br>'.join([str(t) for t in tt])

            if role == Qt.CheckStateRole and c == 0:
                return Qt.Checked if node.isVisible() else Qt.Unchecked

            if role == Qt.DecorationRole and c == 0:
                return None

            if role == Qt.BackgroundRole and tsd in self.mVisibleDates:
                return QColor('yellow')

            if role == Qt.ForegroundRole and tss.isMissing():
                return QColor('red')

        if isinstance(node, TimeSeriesDate):
            if role in [Qt.DisplayRole, Qt.ToolTipRole]:
                if c == self.cSensor:
                    return tsd.sensor().name()
                if c == self.cImages:
                    return len(tsd)
                if c == self.cDate:
                    return ImageDateUtils.dateString(tsd.dtg(), self.dateTimePrecision())

            if role == Qt.CheckStateRole and index.column() == 0:
                return node.checkState()

            if role == Qt.BackgroundRole and tsd in self.mVisibleDates:
                return QColor('yellow')

        return None

    def dateRangeString(self, dateTimeRange: QgsDateTimeRange):

        return dateTimeRange.begin().toString(Qt.ISODate)

    def setData(self, index: QModelIndex, value: Any, role: int):

        if not index.isValid():
            return False

        result = False
        bVisibilityChanged = False
        node = index.internalPointer()
        if isinstance(node, TimeSeriesDate):
            if role == Qt.CheckStateRole and index.column() == 0:
                # update all TSS
                tssVisible = value == Qt.Checked

                n = len(node)
                if n > 0:
                    for tss in node:
                        tss.setIsVisible(tssVisible)
                    self.dataChanged.emit(self.index(0, 0, index),
                                          self.index(self.rowCount(index) - 1, 0, index),
                                          [role])

                result = bVisibilityChanged = True

        if isinstance(node, TimeSeriesSource):
            if role == Qt.CheckStateRole and index.column() == 0:
                b = node.isVisible()
                node.setIsVisible(value == Qt.Checked)
                result = bVisibilityChanged = b != node.isVisible()

                if bVisibilityChanged:
                    # update parent TSD node
                    self.dataChanged.emit(index.parent(), index.parent(), [role])

        if result:
            self.dataChanged.emit(index, index, [role])

        if bVisibilityChanged:
            self.sigVisibilityChanged.emit()

        return result

    def findSource(self, tss: TimeSeriesSource) -> TimeSeriesSource:
        """
        Returns the first TimeSeriesSource instance that is equal to the TimeSeriesSource.
        """
        for tsd in self:
            for tssCandidate in tsd:
                if tssCandidate == tss:
                    return tssCandidate
        return None

    def findDate(self, date: Union[str, QDateTime, datetime.datetime, TimeSeriesDate, TimeSeriesSource]) \
            -> Optional[TimeSeriesDate]:
        """
        Returns the TimeSeriesDate closest to the date input argument
        :param date: QDateTime | str | TimeSeriesDate | datetime.datetime
        :return: TimeSeriesDate
        """
        if len(self) == 0:
            return None

        i = findNearestDateIndex(date, self.mTSDs)
        return self.mTSDs[i]

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            flags = flags | Qt.ItemIsUserCheckable
        return flags


def getSpatialPropertiesFromDataset(ds):
    assert isinstance(ds, gdal.Dataset)

    nb = ds.RasterCount
    nl = ds.RasterYSize
    ns = ds.RasterXSize
    proj = ds.GetGeoTransform()
    px_x = float(abs(proj[1]))
    px_y = float(abs(proj[5]))

    crs = QgsCoordinateReferenceSystem(ds.GetProjection())

    return nb, nl, ns, crs, px_x, px_y


def extractWavelengthsFromGDALMetaData(ds: gdal.Dataset) -> (list, str):
    """
    Reads the wavelength info from standard metadata strings
    :param ds: gdal.Dataset
    :return: (list, str)
    """

    regWLkey = re.compile('^(center )?wavelength[_ ]*$', re.I)
    regWLUkey = re.compile('^wavelength[_ ]*units?$', re.I)
    regNumeric = re.compile(r"([-+]?\d*\.\d+|[-+]?\d+)", re.I)

    def findKey(d: dict, regex) -> str:
        for key in d.keys():
            if regex.search(key):
                return key

    # 1. try band level
    wlu = []
    wl = []
    for b in range(ds.RasterCount):
        band = ds.GetRasterBand(b + 1)
        assert isinstance(band, gdal.Band)
        domains = band.GetMetadataDomainList()
        if not isinstance(domains, list):
            continue
        for domain in domains:
            md = band.GetMetadata_Dict(domain)

            keyWLU = findKey(md, regWLUkey)
            keyWL = findKey(md, regWLkey)

            if isinstance(keyWL, str) and isinstance(keyWLU, str):

                valueWL = float(md[keyWL])
                valueWLU = str(md[keyWLU]).lower()

                if valueWL > 0:
                    wl.append(valueWL)

                if valueWLU in LUT_WAVELENGTH_UNITS.keys():
                    wlu.append(LUT_WAVELENGTH_UNITS[valueWLU])

                break

    if len(wlu) == len(wl) and len(wl) == ds.RasterCount:
        return wl, wlu[0]

    # 2. try data set level
    for domain in ds.GetMetadataDomainList():
        md = ds.GetMetadata_Dict(domain)

        keyWLU = findKey(md, regWLUkey)
        keyWL = findKey(md, regWLkey)

        if isinstance(keyWL, str) and isinstance(keyWLU, str):

            wlu = LUT_WAVELENGTH_UNITS[md[keyWLU].lower()]
            matches = regNumeric.findall(md[keyWL])
            wl = [float(n) for n in matches]

            if len(wl) == ds.RasterCount:
                return wl, wlu

    return None, None


def extractWavelengthsFromRapidEyeXML(ds: gdal.Dataset, dom: QDomDocument) -> (list, str):
    nodes = dom.elementsByTagName('re:bandSpecificMetadata')
    # see http://schemas.rapideye.de/products/re/4.0/RapidEye_ProductMetadata_GeocorrectedLevel.xsd
    # wavelength and units not given in the XML
    # -> use values from https://www.satimagingcorp.com/satellite-sensors/other-satellite-sensors/rapideye/
    if nodes.count() == ds.RasterCount and ds.RasterCount == 5:
        wlu = r'nm'
        wl = [0.5 * (440 + 510),
              0.5 * (520 + 590),
              0.5 * (630 + 685),
              0.5 * (760 + 850),
              0.5 * (760 + 850)
              ]
        return wl, wlu
    return None, None


def extractWavelengthsFromDIMAPXML(ds: gdal.Dataset, dom: QDomDocument) -> (list, str):
    """
    :param dom: QDomDocument | gdal.Dataset
    :return: (list of wavelengths, str wavelength unit)
    """
    # DIMAP XML metadata?
    assert isinstance(dom, QDomDocument)
    nodes = dom.elementsByTagName('Band_Spectral_Range')
    if nodes.count() > 0:
        candidates = []
        for element in [nodes.item(i).toElement() for i in range(nodes.count())]:
            _band = element.firstChildElement('BAND_ID').text()
            _wlu = element.firstChildElement('MEASURE_UNIT').text()
            wlMin = float(element.firstChildElement('MIN').text())
            wlMax = float(element.firstChildElement('MAX').text())
            _wl = 0.5 * wlMin + wlMax
            candidates.append((_band, _wl, _wlu))

        if len(candidates) == ds.RasterCount:
            candidates = sorted(candidates, key=lambda t: t[0])

            wlu = candidates[0][2]
            wlu = LUT_WAVELENGTH_UNITS[wlu]
            wl = [c[1] for c in candidates]
            return wl, wlu
    return None, None


def extractWavelengths(ds):
    """
    Returns the wavelength and wavelength units
    :param ds: gdal.Dataset
    :return: (float [list-of-wavelengths], str with wavelength unit)
    """

    if isinstance(ds, QgsRasterLayer):

        if ds.dataProvider().name() == 'gdal':
            uri = ds.source()
            return extractWavelengths(gdal.Open(uri))
        else:

            md = [l.split('=') for l in str(ds.metadata()).splitlines() if 'wavelength' in l.lower()]

            wl = wlu = None
            for kv in md:
                key, value = kv
                key = key.lower()
                value = value.strip()

                if key == 'wavelength':
                    tmp = re.findall(r'\d*\.\d+|\d+', value)  # find floats
                    if len(tmp) == 0:
                        tmp = re.findall(r'\d+', value)  # find integers
                    if len(tmp) == ds.bandCount():
                        wl = [float(w) for w in tmp]

                if key == 'wavelength units':
                    wlu = value
                    if wlu in LUT_WAVELENGTH_UNITS.keys():
                        wlu = LUT_WAVELENGTH_UNITS[wlu]

                if isinstance(wl, list) and isinstance(wlu, str):
                    return wl, wlu

    elif isinstance(ds, gdal.Dataset):

        def testWavelLengthInfo(wl, wlu) -> bool:
            return isinstance(wl, list) and len(wl) == ds.RasterCount and isinstance(wlu,
                                                                                     str) and wlu in LUT_WAVELENGTH_UNITS.keys()

        # try band-specific metadata
        wl, wlu = extractWavelengthsFromGDALMetaData(ds)
        if testWavelLengthInfo(wl, wlu):
            return wl, wlu

        # try internal locations with XML info
        # SPOT DIMAP
        if 'xml:dimap' in ds.GetMetadataDomainList():
            md = ds.GetMetadata_Dict('xml:dimap')
            for key in md.keys():
                dom = QDomDocument()
                dom.setContent(key + '=' + md[key])
                wl, wlu = extractWavelengthsFromDIMAPXML(ds, dom)
                if testWavelLengthInfo(wl, wlu):
                    return wl, wlu

        # try separate XML files
        xmlReaders = [extractWavelengthsFromDIMAPXML, extractWavelengthsFromRapidEyeXML]
        for path in ds.GetFileList():
            if re.search(r'\.xml$', path, re.I) and not re.search(r'\.aux.xml$', path, re.I):
                dom = QDomDocument()
                with open(path, encoding='utf-8') as f:
                    dom.setContent(f.read())

                if dom.hasChildNodes():
                    for xmlReader in xmlReaders:
                        wl, wlu = xmlReader(ds, dom)
                        if testWavelLengthInfo(wl, wlu):
                            return wl, wlu

    return None, None
