# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2017-08-04
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
# noinspection PyPep8Naming

import datetime
import os
import pathlib
import re
import sys
import traceback
import uuid
from collections import OrderedDict
from typing import Dict, List, Tuple

import numpy as np
from osgeo import gdal, ogr, osr

from qgis.core import QgsApplication, QgsConditionalLayerStyles, QgsConditionalStyle, QgsCoordinateReferenceSystem, \
    QgsCoordinateTransform, QgsExpression, QgsExpressionContext, QgsFeature, QgsFeatureRequest, QgsField, QgsFields, \
    QgsFileUtils, QgsGeometry, QgsPointXY, QgsProviderRegistry, QgsRectangle, QgsTask, QgsTaskManager, \
    QgsVectorFileWriter, QgsVectorLayer, QgsVectorLayerCache, QgsWkbTypes
from qgis.gui import QgsAttributeTableFilterModel, QgsAttributeTableModel, QgsAttributeTableView, \
    QgsIFeatureSelectionManager
from qgis.PyQt.QtCore import pyqtSignal, QDate, QModelIndex, QObject, QPoint, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from qgis.PyQt.QtWidgets import QFileDialog, QHeaderView, QMenu
from .qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from .qgispluginsupport.qps.utils import createQgsField, geo2px, px2geo, setQgsFieldValue, SpatialExtent, SpatialPoint
from .tasks import EOTSVTask
from .timeseries import SensorInstrument, TimeSeries, TimeSeriesDate, TimeSeriesSource

LABEL_EXPRESSION_2D = 'DN or Index'
LABEL_TIME = 'Date'
DEBUG = False
OPENGL_AVAILABLE = False
DEFAULT_SAVE_PATH = None

VSI_DIR = r'/vsimem/temporalprofiles/'

FN_ID = 'fid'
FN_X = 'x'
FN_Y = 'y'
FN_NAME = 'name'

FN_DOY = 'DOY'
FN_DTG = 'DTG'
FN_IS_NODATA = 'is_nodata'
FN_SOURCE_IMAGE = 'source_image'
FN_GEO_X = 'geo_x'
FN_GEO_Y = 'geo_y'
FN_PX_X = 'px_x'
FN_PX_Y = 'px_y'

rxBandKey = re.compile(r"(?<!\w)b\d+(?!\w)", re.IGNORECASE)
rxBandKeyExact = re.compile(r'^' + rxBandKey.pattern + '$', re.IGNORECASE)

try:
    __import__('OpenGL')
    OPENGL_AVAILABLE = True
except ModuleNotFoundError:
    pass


def temporalProfileFeatureFields(sensor: SensorInstrument, singleBandOnly=False) -> QgsFields:
    """
    Returns the fields of a single temporal profile
    :return:
    """
    assert isinstance(sensor, SensorInstrument)
    fields = QgsFields()
    fields.append(createQgsField(FN_DTG, '2011-09-12', comment='Date-time-group'))
    fields.append(createQgsField(FN_DOY, 42, comment='Day-of-year'))
    fields.append(createQgsField(FN_GEO_X, 12.1233, comment='geo-coordinate x/east value'))
    fields.append(createQgsField(FN_GEO_Y, 12.1233, comment='geo-coordinate y/north value'))
    fields.append(createQgsField(FN_PX_X, [42], comment='pixel-coordinate x indices'))
    fields.append(createQgsField(FN_PX_Y, [24], comment='pixel-coordinate y indices'))

    for b in range(sensor.nb):
        bandKey = bandIndex2bandKey(b)
        fields.append(createQgsField(bandKey, 1.0, comment='value band {}'.format(b + 1)))

    return fields


def sensorExampleQgsFeature(sensor: SensorInstrument, singleBandOnly=False) -> QgsFeature:
    """
    Returns an exemplary QgsFeature with value for a specific sensor
    :param sensor: SensorInstrument
    :param singleBandOnly:
    :return:
    """
    # populate with exemplary band values (generally stored as floats)

    fields = temporalProfileFeatureFields(sensor)
    f = QgsFeature(fields)
    pt = QgsPointXY(12.34567, 12.34567)
    f.setGeometry(QgsGeometry.fromPointXY(pt))
    f.setAttribute(FN_GEO_X, pt.x())
    f.setAttribute(FN_GEO_Y, pt.y())
    f.setAttribute(FN_PX_X, 1)
    f.setAttribute(FN_PX_Y, 1)
    dtg = datetime.date.today()
    doy = dateDOY(dtg)
    f.setAttribute(FN_DTG, str(dtg))
    f.setAttribute(FN_DOY, doy)

    for b in range(sensor.nb):
        bandKey = bandIndex2bandKey(b)
        f.setAttribute(bandKey, 1.0)
    return f


def geometryToPixel(ds: gdal.Dataset, geometry: QgsGeometry) -> Tuple[list, list]:
    """
    Returns the pixel-positions of pixels whose pixel center is covered by a geometry
    :param datset:
    :param geometry:
    :return:
    """
    assert isinstance(ds, gdal.Dataset)
    if isinstance(geometry, QgsPointXY):
        geometry = QgsGeometry.fromPointXY(geometry)
    elif isinstance(geometry, str):
        geometry = QgsGeometry.fromWkt(geometry)
    elif isinstance(geometry, QgsRectangle):
        geometry = QgsGeometry.fromRect(geometry)
    assert isinstance(geometry, QgsGeometry)

    x_indices = []
    y_indices = []

    if geometry.isMultipart():
        raise NotImplementedError()
    else:
        gt = ds.GetGeoTransform()
        bounds = SpatialExtent.fromRasterSource(ds)

        if geometry.boundingBoxIntersects(bounds):
            if geometry.type() == QgsWkbTypes.PointGeometry:
                px = geo2px(QgsPointXY(geometry.asQPointF()), gt)
                x_indices.append(px.x())
                y_indices.append(px.y())
            elif geometry.type() in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                ibb = geometry.boundingBox()
                pxUL = geo2px(QgsPointXY(ibb.xMinimum(), ibb.yMaximum()), gt)
                pxLR = geo2px(QgsPointXY(ibb.xMaximum(), ibb.yMinimum()), gt)
                x_range = [max(0, pxUL.x()), min(pxLR.x(), ds.RasterXSize - 1)]
                y_range = [max(0, pxUL.y()), min(pxLR.y(), ds.RasterYSize - 1)]
                x = x_range[0]
                while x <= x_range[1]:
                    y = y_range[0]
                    while y <= y_range[1]:
                        #
                        pt = px2geo(QPoint(x, y), gt)

                        if geometry.contains(pt):
                            x_indices.append(x)
                            y_indices.append(y)
                        else:
                            s = ""
                        y += 1
                    x += 1
            else:
                raise NotImplementedError()

    return x_indices, y_indices


def dateDOY(date):
    if isinstance(date, np.datetime64):
        date = date.astype(datetime.date)
    return date.timetuple().tm_yday


def daysPerYear(year):
    if isinstance(year, np.datetime64):
        year = year.astype(datetime.date)
    if isinstance(year, datetime.date):
        year = year.timetuple().tm_year

    return dateDOY(datetime.date(year=year, month=12, day=31))


def date2num(d):
    # kindly taken from https://stackoverflow.com/questions/6451655/python-how-to-convert-datetime-dates-to-decimal-years
    if isinstance(d, np.datetime64):
        d = d.astype(datetime.datetime)

    if isinstance(d, QDate):
        d = datetime.date(d.year(), d.month(), d.day())

    assert isinstance(d, datetime.date)

    yearDuration = daysPerYear(d)
    yearElapsed = d.timetuple().tm_yday
    fraction = float(yearElapsed) / float(yearDuration)
    if fraction == 1.0:
        fraction = 0.9999999
    return float(d.year) + fraction


def num2date(n, dt64=True, qDate=False):
    n = float(n)
    if n < 1:
        n += 1

    year = int(n)
    fraction = n - year
    yearDuration = daysPerYear(year)
    yearElapsed = fraction * yearDuration

    doy = round(yearElapsed)
    if doy < 1:
        doy = 1
    try:
        date = datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
    except Exception:
        s = ""
    if qDate:
        return QDate(date.year, date.month, date.day)
    if dt64:
        return np.datetime64(date)
    else:
        return date


def bandIndex2bandKey(i: int):
    assert i >= 0
    return 'b{}'.format(i + 1)


def bandKey2bandIndex(key: str):
    match = rxBandKeyExact.search(key)
    assert match
    idx = int(match.group()[1:]) - 1
    return idx


class TemporalProfile(QObject):
    sigLoadMissingImageDataRequest = pyqtSignal(list)
    sigNameChanged = pyqtSignal(str)

    def __init__(self, layer, fid: int, geometry: QgsGeometry):
        super(TemporalProfile, self).__init__()
        assert isinstance(geometry, QgsGeometry)
        assert isinstance(layer, TemporalProfileLayer)
        assert fid >= 0

        self.mID = fid
        self.mLayer = layer
        self.mTimeSeries = layer.timeSeries()
        assert isinstance(self.mTimeSeries, TimeSeries)
        self.mData = {}
        self.mUpdated = False
        self.mLoaded = self.mLoadedMax = self.mNoData = 0
        self.initDataStore()

    def initDataStore(self):
        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)
            meta = {FN_DOY: tsd.mDOY,
                    FN_DTG: str(tsd.mDate),
                    FN_IS_NODATA: False,
                    FN_SOURCE_IMAGE: None}
            self.mData[tsd] = meta

    def printData(self, sensor: SensorInstrument = None):
        """
        Prints the entire temporal profile. For debug purposes.
        """
        for tsd in sorted(self.mData.keys()):
            assert isinstance(tsd, TimeSeriesDate)
            data = self.mData[tsd]
            if isinstance(sensor, SensorInstrument) and tsd.sensor() != sensor:
                continue
            assert isinstance(data, dict)
            info = '{}:{}={}'.format(tsd.date(), tsd.sensor().name(), str(data))
            print(info)

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        """
        Two temporal profiles are equal if they have the same feature id and source layer
        :param other:
        :return:
        """

        if not isinstance(other, TemporalProfile):
            return False

        return other.mID == self.mID and self.mLayer == other.mLayer

    def geometry(self, crs: QgsCoordinateReferenceSystem = None) -> QgsGeometry:
        """
        Returns the temporal profile geometry
        :param crs:
        :return: QgsGeometry. usually a QgsPoint
        """
        g = self.mLayer.getFeature(self.mID).geometry()

        if not isinstance(g, QgsGeometry):
            return None

        if isinstance(crs, QgsCoordinateReferenceSystem) and crs != self.mLayer.crs():
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(self.mLayer.crs())
            trans.setDestinationCrs(crs)
            g.transform(trans)
        return g

    def coordinate(self) -> SpatialPoint:
        """
        Returns the profile coordinate
        :return:
        """
        x, y = self.geometry().asPoint()
        return SpatialPoint(self.mLayer.crs(), x, y)

    def id(self) -> int:
        """Feature ID within connected QgsVectorLayer"""
        return self.mID

    def attribute(self, key: str):
        f = self.mLayer.getFeature(self.mID)
        i = f.fieldNameIndex(key)
        if i >= 0:
            return f.attribute(f.fieldNameIndex(key))
        else:
            return None

    def setAttribute(self, key: str, value):
        f = self.mLayer.getFeature(self.id())

        b = self.mLayer.isEditable()
        self.mLayer.startEditing()
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(key), value)
        self.mLayer.saveEdits(leaveEditable=b)

    def name(self):
        return self.attribute('name')

    def setName(self, name: str):
        self.setAttribute('name', name)

    def timeSeries(self):
        return self.mTimeSeries

    def loadMissingData(self):
        """
        Loads the missing data for this profile (synchronous execution, may take some time).
        """
        qgsTask = TemporalProfileLoaderTask(self.mLayer,
                                            required_profiles=[self],
                                            callback=self.mLayer.updateProfileData)
        qgsTask.finished(qgsTask.run())

    def missingBandIndices(self, tsd: TimeSeriesDate, required_indices: List[int] = None):
        """
        Returns the band indices [0, sensor.nb) that have not been loaded yet for a given time series date.
        :param tsd: TimeSeriesDate of interest
        :param required_indices: optional subset of possible band-indices to return the missing ones from.
        :return: [list-of-indices]
        """
        assert isinstance(tsd, TimeSeriesDate)
        if required_indices is None:
            required_indices = list(range(tsd.mSensor.nb))
        required_indices = [i for i in required_indices if i >= 0 and i < tsd.mSensor.nb]

        existingBandIndices = [bandKey2bandIndex(k) for k in self.data(tsd).keys() if rxBandKeyExact.search(k)]

        if FN_PX_X not in self.data(tsd).keys() and len(required_indices) == 0:
            required_indices.append(0)

        return [i for i in required_indices if i not in existingBandIndices]

    def plot(self):
        from .profilevisualization import TemporalProfilePlotStyle, TemporalProfilePlotDataItem
        for sensor in self.mTimeSeries.sensors():
            assert isinstance(sensor, SensorInstrument)

            plotStyle = TemporalProfilePlotStyle(self)
            plotStyle.setSensor(sensor)

            pi = TemporalProfilePlotDataItem(plotStyle)
            pi.setClickable(True)
            pw = pg.plot(title=self.name())
            pw.plotItem().addItem(pi)
            pi.setColor('green')
            pg.QAPP.exec_()

    def updateData(self, tsd: TimeSeriesDate, newValues: dict, skipStatusUpdate: bool = False):
        assert isinstance(tsd, TimeSeriesDate)
        assert isinstance(newValues, dict)

        if tsd not in self.mData.keys():
            self.mData[tsd] = dict()

        for k, v in newValues.items():
            self.mData[tsd][k] = v

    def dataFromExpression(self,
                           sensor: SensorInstrument,
                           expression: str,
                           dateType: str = 'date'):

        assert dateType in ['date', 'doy']
        x = []
        y = []

        if not isinstance(expression, QgsExpression):
            expression = QgsExpression(expression)
        assert isinstance(expression, QgsExpression)
        expression = QgsExpression(expression)

        sensorTSDs = sorted([tsd for tsd in self.mData.keys() if tsd.sensor() == sensor])

        # define required QgsFields
        fields = temporalProfileFeatureFields(sensor)

        geo_x = self.geometry().centroid().get().x()
        geo_y = self.geometry().centroid().get().y()

        for i, tsd in enumerate(sensorTSDs):
            assert isinstance(tsd, TimeSeriesDate)
            data = self.mData[tsd]

            if dateType == 'date':
                xValue = date2num(tsd.mDate)
            elif dateType == 'doy':
                xValue = tsd.mDOY

            context = QgsExpressionContext()
            context.setFields(fields)

            f = QgsFeature(fields)

            # set static properties (same for all TSDs)
            f.setGeometry(QgsGeometry(self.geometry()))
            f.setAttribute(FN_GEO_X, geo_x)
            f.setAttribute(FN_GEO_Y, geo_y)

            # set TSD specific properties
            f.setAttribute(FN_DOY, tsd.doy())
            f.setAttribute(FN_DTG, str(tsd.date()))

            for fn in fields.names():
                value = data.get(fn)
                if value:
                    if isinstance(value, list):
                        value = str(value)
                    setQgsFieldValue(f, fn, value)

            context.setFeature(f)

            yValue = expression.evaluate(context)

            if yValue in [None, QVariant()]:
                yValue = np.NaN

            y.append(yValue)
            x.append(xValue)

        assert len(x) == len(y)
        return x, y

    def data(self, tsd: TimeSeriesDate) -> dict:
        """
        Returns a dictionary with all data related to this temporal profile
        :param tsd: TimeSeriesData
        :return: dictionary
        """
        assert isinstance(tsd, TimeSeriesDate)
        if self.hasData(tsd):
            return self.mData[tsd]
        else:
            return {}

    def loadingStatus(self):
        """
        Returns the loading status in terms of single pixel values.
        nLoaded = sum of single band values
        nLoadedMax = potential maximum of band values that might be loaded
        :return: (nLoaded, nLoadedMax)
        """
        return self.mLoaded, self.mNoData, self.mLoadedMax

    # def updateLoadingStatus(self):
    #    """
    #    Calculates the loading status in terms of single pixel values.
    #    nMax is the sum of all bands over each TimeSeriesDate and Sensors
    #    """
    """
        self.mLoaded = 0
        self.mLoadedMax = 0
        self.mNoData = 0

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)
            nb = tsd.mSensor.nb

            self.mLoadedMax += nb
            if self.hasData(tsd):
                if self.isNoData(tsd):
                    self.mNoData += nb
                else:
                    self.mLoaded += len([k for k in self.mData[tsd].keys() if regBandKey.search(k)])

        f = self.mLayer.getFeature(self.id())

        b = self.mLayer.isEditable()
        self.mLayer.startEditing()
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_NODATA), self.mNoData)
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_TOTAL), self.mLoadedMax)
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED), self.mLoaded)
        # if self.mLoadedMax > 0:
        #     self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED_PERCENT), round(100. * float(self.mLoaded + self.mNoData) / self.mLoadedMax, 2))

        self.mLayer.saveEdits(leaveEditable=b)
        s = ""
    """

    def isNoData(self, tsd):
        assert isinstance(tsd, TimeSeriesDate)
        return self.mData[tsd][FN_IS_NODATA]

    def hasData(self, tsd):
        assert isinstance(tsd, TimeSeriesDate)
        return tsd in self.mData.keys()

    def __lt__(self, other):
        assert isinstance(other, TemporalProfile)
        return self.id() < other.id()

    def __repr__(self):
        return 'TemporalProfile {} "{}"'.format(self.id(), self.name())


class TemporalProfileLayer(QgsVectorLayer):
    """
    A collection to store the TemporalProfile data delivered by a PixelLoader
    """

    # sigSensorAdded = pyqtSignal(SensorInstrument)
    # sigSensorRemoved = pyqtSignal(SensorInstrument)
    # sigPixelAdded = pyqtSignal()
    # sigPixelRemoved = pyqtSignal()

    sigTemporalProfilesAdded = pyqtSignal(list)
    sigTemporalProfilesRemoved = pyqtSignal(list)
    sigMaxProfilesChanged = pyqtSignal(int)
    sigTemporalProfilesUpdated = pyqtSignal(list)

    def __init__(self,
                 path: str = None,
                 baseName: str = 'Temporal Profiles',
                 options: QgsVectorLayer.LayerOptions = None,
                 ):

        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        if not isinstance(options, QgsVectorLayer.LayerOptions):
            options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)

        if path is None:
            # create a new, empty backend
            baseName2 = QgsFileUtils.stringToSafeFilename(baseName)
            baseName2 = re.sub(r'\W', '_', baseName2)
            while True:
                path = pathlib.PurePosixPath(VSI_DIR) / f'{baseName2}.{uuid.uuid4()}.gpkg'
                path = path.as_posix().replace('\\', '/')
                stats = gdal.VSIStatL(path)
                if not isinstance(stats, gdal.StatBuf):
                    break

            drv = ogr.GetDriverByName('GPKG')
            missingGPKGInfo = \
                "Your GDAL/OGR installation does not support the GeoPackage (GPKG) vector driver " + \
                "(https://gdal.org/drivers/vector/gpkg.html).\n" + \
                "Linux users might need to install libsqlite3."
            assert isinstance(drv, ogr.Driver), missingGPKGInfo

            co = ['VERSION=AUTO']
            dsSrc = drv.CreateDataSource(path, options=co)
            assert isinstance(dsSrc, ogr.DataSource)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            co = ['GEOMETRY_NAME=geom',
                  'GEOMETRY_NULLABLE=YES',
                  # 'FID=fid'
                  ]

            lyr = dsSrc.CreateLayer(baseName, srs=srs, geom_type=ogr.wkbPoint, options=co)

            assert isinstance(lyr, ogr.Layer)
            ldefn = lyr.GetLayerDefn()
            assert isinstance(ldefn, ogr.FeatureDefn)

            try:
                dsSrc.FlushCache()
            except RuntimeError as rt:
                if 'failed: no such module: rtree' in str(rt):
                    pass
                else:
                    raise rt

        assert isinstance(path, str)
        super(TemporalProfileLayer, self).__init__(path, baseName, 'ogr', options)

        """
        assert isinstance(timeSeries, TimeSeries)
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        uri = 'Point?crs={}'.format(crs.authid())
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(TemporalProfileLayer, self).__init__(uri, name, 'memory', lyrOptions)
        """
        self.mProfiles = OrderedDict()
        self.mTimeSeries: TimeSeries = None

        self.setName('EOTS Temporal Profiles')
        fields = QgsFields()
        # fields.append(createQgsField(FN_ID, self.mNextID))
        fields.append(createQgsField(FN_NAME, ''))
        fields.append(createQgsField(FN_X, 0.0, comment='Longitude'))
        fields.append(createQgsField(FN_Y, 0.0, comment='Latitude'))
        # fields.append(createQgsField(FN_N_TOTAL, 0, comment='Total number of band values'))
        # fields.append(createQgsField(FN_N_NODATA,0, comment='Total of no-data values.'))
        # fields.append(createQgsField(FN_N_LOADED, 0, comment='Loaded valid band values.'))
        # fields.append(createQgsField(FN_N_LOADED_PERCENT,0.0, comment='Loading progress (%)'))
        assert self.startEditing()
        assert self.dataProvider().addAttributes(fields)
        assert self.commitChanges()
        self.initConditionalStyles()

        self.committedFeaturesAdded.connect(self.onFeaturesAdded)
        self.featuresDeleted.connect(self.onFeaturesRemoved)
        self.committedGeometriesChanges.connect(self.onGeometryChanged)

        self.mTasks = dict()

    def __getitem__(self, slice):
        return list(self.mProfiles.values())[slice]

    def saveTemporalProfiles(self, pathVector, sep='\t'):
        if pathVector is None or len(pathVector) == 0:
            global DEFAULT_SAVE_PATH
            if DEFAULT_SAVE_PATH is None:
                DEFAULT_SAVE_PATH = 'temporalprofiles.shp'
            d = os.path.dirname(DEFAULT_SAVE_PATH)
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            pathVector, filter = QFileDialog.getSaveFileName(None, 'Save {}'.format(self.name()), DEFAULT_SAVE_PATH,
                                                             filter=filters)

            if len(pathVector) == 0:
                return None
            else:
                DEFAULT_SAVE_PATH = pathVector

        drvName = QgsVectorFileWriter.driverForExtension(os.path.splitext(pathVector)[-1])
        QgsVectorFileWriter.writeAsVectorFormat(self, pathVector, 'utf-8', destCRS=self.crs(), driverName=drvName)

        pathCSV = os.path.splitext(pathVector)[0] + '.data.csv'
        # write a flat list of profiles
        csvLines = ['Temporal Profiles']
        nBands = max([s.nb for s in self.mTimeSeries.sensors()])
        csvLines.append(
            sep.join(['id', 'name', 'sensor', 'date', 'doy'] + ['b{}'.format(b + 1) for b in range(nBands)]))

        for p in list(self.getFeatures()):

            assert isinstance(p, QgsFeature)
            fid = p.id()
            tp = self.mProfiles.get(fid)
            if tp is None:
                continue
            assert isinstance(tp, TemporalProfile)
            name = tp.name()
            for tsd, values in tp.mData.items():
                assert isinstance(tsd, TimeSeriesDate)
                line = [fid, name, tsd.mSensor.name(), tsd.mDate, tsd.mDOY]
                for b in range(tsd.mSensor.nb):
                    key = 'b{}'.format(b + 1)
                    line.append(values.get(key))

                line = ['' if v is None else str(v) for v in line]
                line = sep.join([str(l) for l in line])
                csvLines.append(line)
            s = ""

        # write CSV file
        with open(pathCSV, 'w', encoding='utf8') as f:
            f.write('\n'.join(csvLines))

        return [pathVector, pathCSV]

    def setTimeSeries(self, timeSeries: TimeSeries):
        self.clear()
        self.mTimeSeries = timeSeries

    def loadMissingBandInfos(self,
                             required_profiles: List[TemporalProfile] = None,
                             required_sensor_bands: Dict[SensorInstrument, List[int]] = None,
                             run_async: bool = True):
        from eotimeseriesviewer import debugLog
        debugLog('Load temporal profile data')
        qgsTask = TemporalProfileLoaderTask(self,
                                            required_profiles=required_profiles,
                                            required_sensor_bands=required_sensor_bands,
                                            callback=self.updateProfileData)

        # nothing missed? nothing to do
        if len(qgsTask.MISSING_DATA) == 0:
            return

        # tid = id(qgsTask)
        # self.mTasks[tid] = qgsTask

        # qgsTask.taskCompleted.connect(lambda *args, t=tid: self.onRemoveTask(t))
        # qgsTask.taskTerminated.connect(lambda *args, t=tid: self.onRemoveTask(t))

        if run_async:
            tm = QgsApplication.taskManager()
            assert isinstance(tm, QgsTaskManager)
            tm.addTask(qgsTask)
        else:
            qgsTask.finished(qgsTask.run())

    def updateProfileData(self, successful: bool, task) -> List[TemporalProfile]:
        """
        Updates TemporalProfiles
        :param qgsTask:
        :param dump:
        :return: [updated TemporalProfiles]
        """
        assert isinstance(task, TemporalProfileLoaderTask)
        updated_profiles = set()
        if successful:
            for tpID, newData in task.MISSING_DATA.items():
                tp = self.mProfiles.get(tpID)
                if not isinstance(tp, TemporalProfile):
                    s = ""
                    continue
                assert isinstance(tp, TemporalProfile)
                for tsd, newTSDData in newData.items():
                    tp.updateData(tsd, newTSDData)
                updated_profiles.add(tp)
        else:

            for e in task.mErrors:
                print(e, file=sys.stderr)

        updated_profiles = sorted(updated_profiles)
        if len(updated_profiles) > 0:
            self.sigTemporalProfilesUpdated.emit(updated_profiles)
        return updated_profiles

    def onRemoveTask(self, tid):
        if tid in self.mTasks.keys():
            del self.mTasks[tid]

    def timeSeries(self) -> TimeSeries:
        """
        Returns the TimeSeries instance.
        :return: TimeSeries
        """
        return self.mTimeSeries

    def onGeometryChanged(self, fid: int, g: QgsGeometry):
        # geometryChanged (QgsFeatureId fid, const QgsGeometry &geometry)
        s = ""

    def onFeaturesAdded(self, layerID, addedFeatures):
        """
        Create a TemporalProfile object for each QgsFeature added to the backend QgsVectorLayer
        :param layerID:
        :param addedFeatures:
        :return:
        """
        if layerID != self.id():
            s = ""

        if len(addedFeatures) > 0:

            temporalProfiles = []
            for feature in addedFeatures:
                fid = feature.id()
                if fid < 0:
                    continue
                tp = TemporalProfile(self, fid, feature.geometry())

                self.mProfiles[fid] = tp
                temporalProfiles.append(tp)

            if len(temporalProfiles) > 0:
                self.sigTemporalProfilesAdded.emit(temporalProfiles)

    def onFeaturesRemoved(self, removedFIDs):
        # only features which have been permanent before
        removedFIDs = [fid for fid in removedFIDs if fid >= 0]
        if len(removedFIDs) > 0:

            removed = []

            for fid in removedFIDs:
                removed.append(self.mProfiles.pop(fid))

            self.sigTemporalProfilesRemoved.emit(removed)

    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fields().names():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])
        # styles.setRowStyles([red])

    def createTemporalProfiles(self,
                               coordinates: List[SpatialPoint],
                               names: List[str] = None) -> List[TemporalProfile]:
        """
        Creates temporal profiles for a list of coordinates
        :param coordinates:
        :return:
        """
        if isinstance(coordinates, SpatialPoint):
            coordinates = [coordinates]
        assert isinstance(coordinates, list)
        if not isinstance(names, list):
            n = self.featureCount()
            names = []
            for i in range(len(coordinates)):
                names.append('Profile {}'.format(n + i + 1))

        assert len(coordinates) == len(names)

        features = []
        n = self.dataProvider().featureCount()
        for i, (coordinate, name) in enumerate(zip(coordinates, names)):
            assert isinstance(coordinate, SpatialPoint)
            g = QgsGeometry.fromPointXY(coordinate.toCrs(self.crs()))
            f = QgsFeature(self.fields())
            f.setGeometry(g)
            f.setAttribute(FN_NAME, name)
            f.setAttribute(FN_X, coordinate.x())
            f.setAttribute(FN_Y, coordinate.y())
            features.append(f)

        if len(features) == 0:
            return []

        self.startEditing()

        newFeatures = []

        def onFeaturesAdded(lid, fids):
            newFeatures.extend(fids)

        self.committedFeaturesAdded.connect(onFeaturesAdded)
        self.beginEditCommand('Add {} profile locations'.format(len(features)))
        self.addFeatures(features)
        self.endEditCommand()
        self.saveEdits(leaveEditable=True)
        self.committedFeaturesAdded.disconnect(onFeaturesAdded)

        assert self.featureCount() == len(self.mProfiles)
        profiles = [self.mProfiles[f.id()] for f in newFeatures]
        return profiles

    def saveEdits(self, leaveEditable=False, triggerRepaint=True):
        """
        function to save layer changes-
        :param layer:
        :param leaveEditable:
        :param triggerRepaint:
        """
        if not self.isEditable():
            return
        if not self.commitChanges():
            self.commitErrors()

        if leaveEditable:
            self.startEditing()

        if triggerRepaint:
            self.triggerRepaint()

    def addMissingFields(self, fields):
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            i = self.dataProvider().fieldNameIndex(field.name())
            if i == -1:
                missingFields.append(field)
        if len(missingFields) > 0:
            b = self.isEditable()
            self.startEditing()
            self.dataProvider().addAttributes(missingFields)
            self.saveEdits(leaveEditable=b)

    def __len__(self):
        return self.dataProvider().featureCount()

    def __iter__(self):
        r = QgsFeatureRequest()
        for f in self.getFeatures(r):
            yield self.mProfiles[f.id()]

    def __contains__(self, item):
        return item in self.mProfiles.values()

    def selectByCoordinate(self, spatialPoint: SpatialPoint):
        """ Tests if a Temporal Profile already exists for the given spatialPoint"""
        for p in list(self.mProfiles.values()):
            assert isinstance(p, TemporalProfile)
            if p.coordinate() == spatialPoint:
                return p
        return None

    def removeTemporalProfiles(self, temporalProfiles: List[TemporalProfile]):
        """
        Removes temporal profiles from this collection
        :param temporalProfile: TemporalProfile
        """

        assert isinstance(temporalProfiles, list)

        temporalProfiles = [tp for tp in temporalProfiles
                            if isinstance(tp, TemporalProfile) and tp.id() in self.mProfiles.keys()]

        if len(temporalProfiles) > 0:
            b = self.isEditable()
            assert self.startEditing()

            fids = [tp.mID for tp in temporalProfiles]

            self.deleteFeatures(fids)
            self.saveEdits(leaveEditable=b)

            self.sigTemporalProfilesRemoved.emit(temporalProfiles)

    def loadCoordinatesFromOgr(self, path):
        """Loads the TemporalProfiles for vector geometries in data source 'path' """
        if path is None:
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            defDir = None
            if isinstance(DEFAULT_SAVE_PATH, str) and len(DEFAULT_SAVE_PATH) > 0:
                defDir = os.path.dirname(DEFAULT_SAVE_PATH)
            path, filter = QFileDialog.getOpenFileName(directory=defDir, filter=filters)

        if isinstance(path, str) and len(path) > 0:
            sourceLyr = QgsVectorLayer(path)

            nameAttribute = None

            fieldNames = [n.lower() for n in sourceLyr.fields().names()]
            for candidate in ['name', 'id']:
                if candidate in fieldNames:
                    nameAttribute = sourceLyr.fields().names()[fieldNames.index(candidate)]
                    break

            if len(self.timeSeries()) == 0:
                sourceLyr.selectAll()
            else:
                extent = self.timeSeries().maxSpatialExtent(sourceLyr.crs())
                sourceLyr.selectByRect(extent)
            newProfiles = []
            for feature in sourceLyr.selectedFeatures():
                assert isinstance(feature, QgsFeature)
                geom = feature.geometry()
                if isinstance(geom, QgsGeometry):
                    point = geom.centroid().constGet()
                    try:
                        TPs = self.createTemporalProfiles(SpatialPoint(sourceLyr.crs(), point))
                        for TP in TPs:
                            if nameAttribute:
                                name = feature.attribute(nameAttribute)
                            else:
                                name = 'FID {}'.format(feature.id())
                            TP.setName(name)
                            newProfiles.append(TP)
                    except Exception as ex:
                        print(ex)

    def clear(self):
        """
        Removes all temporal profiles
        """
        b = self.isEditable()
        self.startEditing()
        fids = self.allFeatureIds()
        self.deleteFeatures(fids)
        self.commitChanges()

        if b:
            self.startEditing()
        # todo: remove TS Profiles
        # self.mTemporalProfiles.clear()
        # self.sensorPxLayers.clear()
        pass


class TemporalProfileLoaderTask(EOTSVTask):
    """
    A QgsTask to load pixel-band values from different Time Series Source images and
    different Temporal Profiles geometries.
    """
    sigProfilesLoaded = pyqtSignal(list)

    def __init__(self,
                 temporalProfileLayer: TemporalProfileLayer,
                 required_profiles: List[TemporalProfile] = None,
                 required_sensor_bands: Dict[SensorInstrument, List[int]] = None,
                 callback=None,
                 progress_interval: int = 10):

        super().__init__(description='Load Temporal Profiles',
                         flags=QgsTask.CanCancel | QgsTask.CancelWithoutPrompt | QgsTask.Silent)

        assert isinstance(progress_interval, int) and progress_interval > 0
        assert isinstance(temporalProfileLayer, TemporalProfileLayer)
        timeSeries: TimeSeries = temporalProfileLayer.timeSeries()
        self.nTotal = len(timeSeries)
        self.mProgressInterval = datetime.timedelta(seconds=progress_interval)
        self.mRequiredSensorBands: Dict[SensorInstrument, List[int]] = dict()
        self.mRequiredSensorBandKeys: Dict[SensorInstrument, List[str]] = dict()
        self.mTSS2TSD = dict()

        crsWKTs = set()

        self.mErrors = []
        if required_sensor_bands is None:
            for s in timeSeries.sensors():
                self.mRequiredSensorBands[s] = list(range(s.nb))
        else:
            for sensor, band_indices in required_sensor_bands.items():
                assert isinstance(sensor, SensorInstrument)
                self.mRequiredSensorBands[sensor] = sorted(band_indices)
                for band_index in self.mRequiredSensorBands[sensor]:
                    assert isinstance(band_index, int)
                    assert 0 <= band_index < sensor.nb

        for sensor, band_indices in self.mRequiredSensorBands.items():
            self.mRequiredSensorBandKeys[sensor] = [bandIndex2bandKey(i) for i in band_indices]

        # check for all profiles if none are set
        if required_profiles is None:
            required_profiles = temporalProfileLayer[:]

        self.GEOMETRY_CACHE = dict()
        self.MISSING_DATA = dict()

        required_tsds = dict()
        for sensor in self.mRequiredSensorBands.keys():
            required_tsds[sensor] = timeSeries.tsds(None, sensor)
        # create empty dictionaries for each profile and missing band
        for tp in required_profiles:
            assert isinstance(tp, TemporalProfile)
            self.GEOMETRY_CACHE[tp.id()] = dict()
            missingTPData: Dict[TimeSeriesDate] = dict()
            for sensor, tsds in required_tsds.items():
                for tsd in timeSeries.tsds(sensor=sensor):
                    existingTSDData: dict = tp.data(tsd)
                    missingTSDData: dict = dict()
                    for band_key in self.mRequiredSensorBandKeys[sensor]:
                        existingData = existingTSDData.get(band_key)
                        if existingData is None:
                            missingTSDData[band_key] = None
                    if len(missingTSDData) > 0:
                        missingTPData[tsd] = missingTSDData
            if len(missingTPData) > 0:
                self.MISSING_DATA[tp.id()] = missingTPData

        if len(self.MISSING_DATA) == 0:
            return

        for sensor, tsds in required_tsds.items():
            for tsd in tsds:
                for tss in tsd:
                    crsWKTs.add(tss.crsWkt())
                    self.mTSS2TSD[tss] = tss.timeSeriesDate()

        # add geometries in target image coordinates
        for crsWKT in crsWKTs:
            crs = QgsCoordinateReferenceSystem(crsWKT)
            for tp in required_profiles:
                if tp.id() in self.profileIDs():
                    self.GEOMETRY_CACHE[tp.id()][crsWKT] = tp.geometry(crs)

        self.mCallback = callback

    def profileIDs(self) -> List[int]:
        return list(self.MISSING_DATA.keys())

    def timeSeriesSources(self) -> List[TimeSeriesSource]:
        return list(self.mTSS2TSD.keys())

    def run(self) -> bool:

        if len(self.MISSING_DATA) == 0:
            return True

        block_results = []
        n_total = len(self.timeSeriesSources())

        t0 = datetime.datetime.now()
        try:
            for n, tss in enumerate(self.timeSeriesSources()):
                assert isinstance(tss, TimeSeriesSource)
                ext: SpatialExtent = tss.spatialExtent()
                tsd: TimeSeriesDate = self.mTSS2TSD[tss]

                # find intersecting TPs
                INTERSECTING = dict()
                for tpID, GEOM in self.GEOMETRY_CACHE.items():
                    geom = GEOM.get(tss.crsWkt())
                    if isinstance(geom, QgsGeometry) and not geom.isEmpty():
                        if ext.intersects(geom.boundingBox()):
                            INTERSECTING[tpID] = geom
                    else:
                        print('Missing geometry for crsWKT={}\nTSS={}\n'.format(tss.crsWkt(), tss.uri()))
                    del geom, GEOM

                if len(INTERSECTING) == 0:
                    continue

                ds: gdal.Dataset = tss.asDataset()
                assert isinstance(ds, gdal.Dataset)

                # get the px indices for each geometry
                PX_INDICES = dict()
                for tpID, geom in INTERSECTING.items():
                    px_x, px_y = geometryToPixel(ds, geom)
                    if len(px_x) > 0:
                        PX_INDICES[tpID] = (px_x, px_y)

                    del tpID, geom

                if len(PX_INDICES) == 0:
                    # profiles are out of image
                    del PX_INDICES
                    continue

                # create a dictionary that tells us which pixels / TPs positions are to load from which band
                required_band_profiles = dict()
                for tpID in INTERSECTING.keys():
                    missingTSDValues = self.MISSING_DATA[tpID].get(tsd)
                    if isinstance(missingTSDValues, dict):
                        for band_key, v in missingTSDValues.items():
                            if v is None:
                                if band_key not in required_band_profiles:
                                    required_band_profiles[band_key] = set()

                                required_band_profiles[band_key].add(tpID)
                    del missingTSDValues

                # load required bands and required pixel positions only
                for band_key, tpIds in required_band_profiles.items():
                    band: gdal.Band = ds.GetRasterBand(bandKey2bandIndex(band_key) + 1)
                    if not isinstance(band, gdal.Band):
                        s = ""
                        continue

                    for tpID, px_idx in PX_INDICES.items():
                        px_x, px_y = px_idx
                        xoff = int(min(px_x))
                        yoff = int(min(px_y))
                        win_xsize = int(max(px_x) - xoff + 1)
                        win_ysize = int(max(px_y) - yoff + 1)
                        s = ""
                        try:
                            block = band.ReadAsArray(xoff=xoff,
                                                     yoff=yoff,
                                                     win_xsize=win_xsize,
                                                     win_ysize=win_ysize)
                        except RuntimeError as ex:
                            self.mErrors.append(f'band.ReadAsArray({xoff},{yoff},{win_xsize},{win_ysize}) in '
                                                f'ds ({ds.RasterCount}, {ds.RasterYSize}, {ds.RasterXSize})\n{ex}')
                            continue
                        block = block[np.asarray(px_x) - xoff, np.asarray(px_y) - yoff]
                        if band.GetNoDataValue():
                            block = block[np.where(block != band.GetNoDataValue())]
                        if len(block) == 0:
                            del block
                            continue

                        # get mean pixel value
                        value = np.nanmean(block)
                        del block
                        if np.isfinite(value):
                            tpData = self.MISSING_DATA.get(tpID, {})
                            tsdData = tpData.get(tsd, {})
                            tsdData[band_key] = value
                            tpData[tsd] = tsdData
                            self.MISSING_DATA[tpID] = tpData

                    del band
                del required_band_profiles

                dt = datetime.datetime.now() - t0
                if dt > self.mProgressInterval:
                    if self.isCanceled():
                        self.mErrors.append('Canceled')
                        return False
                    t0 = datetime.datetime.now()
                    progress = 100 * n / n_total
                    self.setProgress(progress)

                del INTERSECTING
                del PX_INDICES
                del ds
                del ext
                del tsd
                del tss

                s = ""

        except Exception as ex:
            print(traceback.format_exc())
            raise ex
            info = traceback.format_exc()
            info += '\n{}'.format(ex)
            self.mErrors.append(info)
            return False
        return True

    def canCancel(self) -> bool:
        return True

    def finished(self, result):
        if self.mCallback is not None:
            self.mCallback(result, self)


class TemporalProfileTableModel(QgsAttributeTableModel):
    AUTOGENERATES_COLUMNS = [FN_ID, FN_Y, FN_X]

    def __init__(self, temporalProfileLayer=None, parent=None):

        if temporalProfileLayer is None:
            temporalProfileLayer = TemporalProfileLayer()

        cache = QgsVectorLayerCache(temporalProfileLayer, 1000)

        super(TemporalProfileTableModel, self).__init__(cache, parent)
        self.mTemporalProfileLayer = temporalProfileLayer
        self.mCache = cache

        assert self.mCache.layer() == self.mTemporalProfileLayer

        self.loadLayer()

    def columnNames(self):
        return self.mTemporalProfileLayer.fields().names()

    def feature(self, index):

        id = self.rowToId(index.row())
        f = self.layer().getFeature(id)

        return f

    def temporalProfile(self, index):
        feature = self.feature(index)
        return self.mTemporalProfileLayer.temporalProfileFromFeature(feature)

    def data(self, index, role=Qt.DisplayRole):
        """
        Returns Temporal Profile Layer values
        :param index: QModelIndex
        :param role: enum Qt.ItemDataRole
        :return: value
        """
        if role is None or not index.isValid():
            return None

        result = super(TemporalProfileTableModel, self).data(index, role=role)
        return result

    def setData(self, index, value, role=None):
        """
        Sets Temporal Profile Data.
        :param index: QModelIndex()
        :param value: value to set
        :param role: role
        :return: True | False
        """
        if role is None or not index.isValid():
            return False

        f = self.feature(index)
        result = False

        if value is None:
            value = QVariant()
        cname = self.columnNames()[index.column()]
        if role == Qt.EditRole and cname not in TemporalProfileTableModel.AUTOGENERATES_COLUMNS:
            i = f.fieldNameIndex(cname)
            if f.attribute(i) == value:
                return False
            b = self.mTemporalProfileLayer.isEditable()
            self.mTemporalProfileLayer.startEditing()
            self.mTemporalProfileLayer.changeAttributeValue(f.id(), i, value)
            self.mTemporalProfileLayer.saveEdits(leaveEditable=b)
            result = True

        if result:
            self.dataChanged.emit(index, index, [role])
        else:
            result = super().setData(index, value, role=role)

        return result

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        data = super(TemporalProfileTableModel, self).headerData(section, orientation, role)
        if role == Qt.ToolTipRole and orientation == Qt.Horizontal:
            # add the field comment to column description
            field = self.layer().fields().at(section)
            assert isinstance(field, QgsField)
            comment = field.comment()
            if len(comment) > 0:
                data = re.sub('</p>$', ' <i>{}</i></p>'.format(comment), data)

        return data

    def supportedDragActions(self):
        return Qt.CopyAction

    def supportedDropActions(self):
        return Qt.CopyAction

    def flags(self, index):

        if index.isValid():
            columnName = self.columnNames()[index.column()]
            flags = super(TemporalProfileTableModel, self).flags(index) | Qt.ItemIsSelectable
            # if index.column() == 0:
            #    flags = flags | Qt.ItemIsUserCheckable

            if columnName in TemporalProfileTableModel.AUTOGENERATES_COLUMNS:
                flags = flags ^ Qt.ItemIsEditable
            return flags
        return None


class TemporalProfileFeatureSelectionManager(QgsIFeatureSelectionManager):
    def __init__(self, layer, parent=None):
        super(TemporalProfileFeatureSelectionManager, self).__init__(parent)
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.mLayer.selectionChanged.connect(self.selectionChanged)

    def layer(self):
        return self.mLayer

    def deselect(self, ids):
        if len(ids) > 0:
            selected = [id for id in self.selectedFeatureIds() if id not in ids]
            self.mLayer.deselect(ids)

            self.selectionChanged.emit(selected, ids, True)

    def select(self, ids):
        self.mLayer.select(ids)

    def selectFeatures(self, selection, command):
        super(TemporalProfileFeatureSelectionManager, self).selectFeatures(selection, command)

    def selectedFeatureCount(self):
        return self.mLayer.selectedFeatureCount()

    def selectedFeatureIds(self):
        return self.mLayer.selectedFeatureIds()

    def setSelectedFeatures(self, ids):
        self.mLayer.selectByIds(ids)


class TemporalProfileTableView(QgsAttributeTableView):

    def __init__(self, parent=None):
        super(TemporalProfileTableView, self).__init__(parent)

        # self.setSelectionBehavior(QAbstractItemView.SelectRows)
        # self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setSectionsMovable(True)
        self.willShowContextMenu.connect(self.onWillShowContextMenu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.mSelectionManager = None

    def setModel(self, filterModel):

        super(TemporalProfileTableView, self).setModel(filterModel)

        self.mSelectionManager = TemporalProfileFeatureSelectionManager(self.model().layer())
        self.setFeatureSelectionManager(self.mSelectionManager)
        # self.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mContextMenuActions = []

    def setContextMenuActions(self, actions: list):
        self.mContextMenuActions = actions

    # def contextMenuEvent(self, event):
    def onWillShowContextMenu(self, menu, index):
        assert isinstance(menu, QMenu)
        assert isinstance(index, QModelIndex)

        featureIDs = self.temporalProfileLayer().selectedFeatureIds()

        if len(featureIDs) == 0 and index.isValid():
            if isinstance(self.model(), QgsAttributeTableFilterModel):
                index = self.model().mapToSource(index)
                if index.isValid():
                    featureIDs.append(self.model().sourceModel().feature(index).id())
            elif isinstance(self.model(), QgsAttributeTableFilterModel):
                featureIDs.append(self.model().feature(index).id())

        for a in self.mContextMenuActions:
            menu.addAction(a)

        for a in self.actions():
            menu.addAction(a)

    def temporalProfileLayer(self):
        return self.model().layer()

    def fidsToIndices(self, fids):
        """
        Converts feature ids into FilterModel QModelIndices
        :param fids: [list-of-int]
        :return:
        """
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)
        fmodel = self.model()
        indices = [fmodel.fidToIndex(id) for id in fids]
        return [fmodel.index(idx.row(), 0) for idx in indices]

    def onRemoveFIDs(self, fids):

        layer = self.temporalProfileLayer()
        assert isinstance(layer, TemporalProfileLayer)
        b = layer.isEditable()
        layer.startEditing()
        layer.deleteFeatures(fids)
        layer.saveEdits(leaveEditable=b)

    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if self.model().rowCount() == 0:
            index = self.model().createIndex(0, 0)
        else:
            index = self.indexAt(event.pos())

        # if mimeData.hasFormat(mimedata.MDF_SPECTRALLIBRARY):
        #   self.model().dropMimeData(mimeData, event.dropAction(), index.row(), index.column(), index.parent())
        #  event.accept()

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        # if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
        #    event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        # if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
        #    event.accept()
        s = ""

    def mimeTypes(self):
        pass
