import datetime
import math
import warnings
from typing import Dict, List, Tuple

from osgeo import gdal

from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialExtent, geo2px
from eotimeseriesviewer.tasks import EOTSVTask
from eotimeseriesviewer.timeseries.source import TimeSeriesSource, datasetExtent
from qgis.PyQt.QtCore import pyqtSignal, QDateTime
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCoordinateTransformContext, \
    QgsProject, QgsRasterBandStats, QgsRasterLayer, QgsRectangle, QgsTask
from qgis.core import QgsRasterDataProvider, QgsPointXY

EMPTY_STATS: QgsRasterBandStats = QgsRasterBandStats()


def hasValidPixel(source: str,
                  crs: QgsCoordinateReferenceSystem,
                  extent: QgsRectangle,
                  sample_size: int = 16,
                  use_gdal: bool = True,
                  transform_context: QgsCoordinateTransformContext = None) -> Tuple[bool, str]:
    if transform_context is None:
        transform_context = QgsProject.instance().transformContext()

    if not (isinstance(extent, QgsRectangle) and extent.isFinite()):
        return False, 'Invalid spatial extent'

    ext = QgsRectangle(extent)

    error = None
    if use_gdal:
        # use GDAL only
        ds: gdal.Dataset = gdal.Open(source)
        if not isinstance(ds, gdal.Dataset):
            return False, f'Unable to open {source} as GDAL Dataset'

        if ds.RasterCount == 0:
            return False, f'No bands in {source}'

        if ds.RasterXSize == 0 or ds.RasterYSize == 0:
            return False, f'Empty raster in {source}'

        ds_crs, ds_extent = datasetExtent(ds)

        if ds_crs != crs:
            transform = QgsCoordinateTransform(crs, ds_crs, transform_context)
            if not transform.isValid():
                return False, (f'Unable to get coordinate transformation from {crs.description()} '
                               f'to {ds_crs.description()}: {source}')
            ext = transform.transformBoundingBox(ext)

        inter = ext.intersect(ds_extent.boundingBox())
        if inter.isEmpty():
            # not an error, just no overlap
            return False, ''

        s = int(math.sqrt(sample_size))
        band1: gdal.Band = ds.GetRasterBand(1)
        no_data = band1.GetNoDataValue()
        if not isinstance(no_data, (int, float)):
            return True, ''

        # sample within overlap
        w, h = inter.width(), inter.height()
        gt = ds.GetGeoTransform()
        ul = geo2px(QgsPointXY(inter.xMinimum(), inter.yMaximum()), gt)
        lr = geo2px(QgsPointXY(inter.xMaximum(), inter.yMinimum()), gt)

        step_x = max(1, int((lr.x() - ul.x()) / s))
        step_y = max(1, int((lr.y() - ul.y()) / s))

        n_total = 0
        for x in range(ul.x() + step_x, lr.x(), step_x):
            for y in range(ul.y() + step_y, lr.y(), step_y):
                value = band1.ReadAsArray(x, y, 1, 1)[0][0]
                n_total += 1
                if value != no_data:
                    return True, ''
        if n_total != sample_size:
            s = ""
        return False, ''

    else:
        # use QGIS API
        options = QgsRasterLayer.LayerOptions(loadDefaultStyle=False, transformContext=transform_context)
        lyr = QgsRasterLayer(source, options=options)
        if not lyr.isValid():
            return False, f'Unable to open {source} {lyr.error()}'

        if crs != lyr.crs():
            trans = QgsCoordinateTransform(crs, lyr.crs(), transform_context)
            if not trans.isValid():
                error = f'Unable to get coordinate transformation from {crs.description()} to {lyr.crs().description()}: {lyr.source()}'
                return False, error
            ext = trans.transformBoundingBox(ext)

        if not ext.intersects(lyr.extent()):
            return False, ''

        dp: QgsRasterDataProvider = lyr.dataProvider()
        if not dp.sourceHasNoDataValue(1):
            # all values are valid
            return True, ''

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=DeprecationWarning)
            # get band statistics for 1st band in given spatial extent, based on n random samples

            stats: QgsRasterBandStats = dp.bandStatistics(1,
                                                          stats=Qgis.RasterBandStatistic.Range,
                                                          extent=ext,
                                                          sampleSize=sample_size)

        if not isinstance(stats, QgsRasterBandStats):
            return False, 'Could not retrieve stats'

        return (stats.minimumValue, stats.maximumValue) != (EMPTY_STATS.minimumValue, EMPTY_STATS.maximumValue), ''


class TimeSeriesFindOverlapSubTask(QgsTask):
    """
    A task to check which time series sources have valid data within a give spatial extent
    """
    foundSourceOverlaps = pyqtSignal(dict)
    executed = pyqtSignal(bool, dict)
    emptyStats: QgsRasterBandStats = QgsRasterBandStats()

    def __init__(self,
                 extent: QgsRectangle,
                 crs: QgsCoordinateReferenceSystem,
                 sources: List[str],
                 sample_size: int = 16):
        super().__init__(flags=QgsTask.CancelWithoutPrompt)
        assert isinstance(extent, QgsRectangle)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        assert isinstance(sources, list)
        assert isinstance(sample_size, int) and sample_size > 0

        self.extent = extent
        self.sources = [str(s) for s in sources]
        self.crs = crs
        self.sample_size = sample_size
        self.errors: List[str] = []
        self.transformContext: QgsCoordinateTransformContext = QgsCoordinateTransformContext(
            QgsProject.instance().transformContext())
        self.intersections: Dict[str, bool] = dict()

    def canCancel(self):
        return True

    def run(self) -> bool:

        n_total = len(self.sources)

        intersections = dict()
        for i, source in enumerate(self.sources):

            if self.isCanceled():
                return False
            b, err = hasValidPixel(source, self.crs, self.extent, use_gdal=True)

            intersections[source] = b
            if err not in ['', None]:
                self.errors.append(err)

            if (i > 0 and i % 20 == 0) or i >= n_total - 1:
                self.setProgress(100 * (i + 1) / n_total)
                self.foundSourceOverlaps.emit(intersections.copy())
                self.intersections.update(intersections)
                intersections.clear()

        assert len(intersections) == 0
        assert len(self.intersections) == len(self.sources)
        self.executed.emit(True, self.intersections)
        return True


class TimeSeriesFindOverlapTask(EOTSVTask):
    sigTimeSeriesSourceOverlap = pyqtSignal(dict)
    executed = pyqtSignal(bool, EOTSVTask)

    def __init__(self,
                 extent: SpatialExtent,
                 time_series_sources: List[TimeSeriesSource],
                 date_of_interest: QDateTime = None,
                 sample_size: int = 16,
                 n_threads: int = 4,
                 description: str = None):
        """

        :param extent:
        :param time_series_sources:
        :param date_of_interest: date of interest from which to start searching. "pivot" date
        :param description:
        :param sample_size: number of samples in x and y direction
        """
        if description is None:
            if isinstance(date_of_interest, QDateTime):
                s = date_of_interest.toString('yyyy-MM-dd')
                description = f'Find image overlap ({s})'
            else:
                description = 'Find image overlap'

        super().__init__(description=description,
                         flags=QgsTask.CancelWithoutPrompt | QgsTask.Silent)
        assert sample_size >= 1
        assert isinstance(extent, SpatialExtent)

        sources = list(time_series_sources)

        if isinstance(date_of_interest, QDateTime):
            sources = sorted(sources, key=lambda tss: abs(date_of_interest.secsTo(tss.dtg())))

        self.mExtent = QgsRectangle(extent)
        self.mCrs = extent.crs()
        self.mSampleSize = sample_size
        self.mIntersections: Dict[str, bool] = dict()
        self.mErrors: List[str] = []
        self.mErrors: List[str] = []

        n_sources = len(sources)
        n_badge = math.ceil(n_sources / n_threads)

        current_badge = []
        for s in sources:
            current_badge.append(s.source())
            if len(current_badge) >= n_badge:
                subTask = TimeSeriesFindOverlapSubTask(
                    QgsRectangle(self.mExtent),
                    QgsCoordinateReferenceSystem(self.mCrs),
                    current_badge[:],
                    sample_size=self.mSampleSize
                )
                subTask.foundSourceOverlaps.connect(self.sigTimeSeriesSourceOverlap)
                subTask.executed.connect(self.subTaskExecuted)
                self.addSubTask(subTask, subTaskDependency=QgsTask.SubTaskDependency.ParentDependsOnSubTask)
                current_badge.clear()

    def errors(self) -> List[str]:
        return self.mErrors[:]

    def intersections(self):
        return self.mIntersections

    def subTaskExecuted(self, success: bool, results: dict):
        if success:
            self.mIntersections.update(results)

    def run(self):
        """
        Start the Task and returns the results.
        :return:
        """

        for subTask in self.subTasks():
            subTask: TimeSeriesFindOverlapSubTask
            self.mIntersections.update(subTask.intersections)
            self.mErrors.extend(subTask.errors)

        self.executed.emit(True, self)

        return True

    def canCancel(self) -> bool:
        return True


class TimeSeriesLoadingSubTask(QgsTask):
    imagesLoaded = pyqtSignal(object)

    def __init__(self,
                 sources: List[str], *args,
                 progress_interval: int = 5,
                 report_block_size: int = 25, **kwds):
        super().__init__(*args, **kwds)
        assert 0 < report_block_size
        self.report_block_size = report_block_size
        self.sources = [str(s) for s in sources]
        self.progress_interval = progress_interval
        self.invalid_sources: List[Tuple[str, Exception]] = []
        self.valid_sources: List[TimeSeriesSource] = []

    def canCancel(self):
        return True

    def run(self):

        n_total = len(self.sources)
        block: List[TimeSeriesSource] = []

        t0 = datetime.datetime.now()

        for i, source in enumerate(self.sources):
            if self.isCanceled():
                return False

            try:
                tss = TimeSeriesSource.create(source)
                assert isinstance(tss, TimeSeriesSource), f'Unable to open {source} as TimeSeriesSource'
                # self.mSources.append(tss)
                self.valid_sources.append(tss)
                block.append(tss)
                del tss
            except Exception as ex:
                self.invalid_sources.append((source, ex))

            dts = (datetime.datetime.now() - t0).seconds
            if dts > self.progress_interval:
                self.setProgress(100 * (i + 1) / n_total)
                t0 = datetime.datetime.now()

            if len(block) >= self.report_block_size:
                self.imagesLoaded.emit(block[:])
                block.clear()

        if len(block) > 0:
            self.imagesLoaded.emit(block)
        self.setProgress(100.0)
        return True


class TimeSeriesLoadingTask(EOTSVTask):
    imagesLoaded = pyqtSignal(object)

    executed = pyqtSignal(bool, EOTSVTask)

    def __init__(self,
                 files: List[str],
                 description: str = "Load Images",
                 report_block_size=25,
                 n_threads: int = 4,
                 progress_interval: int = 5):
        """
        :param files: list of files to load
        :param description:
        :param report_block_size: number of images to load before emitting them via the sigFoundSources signal.
        :param n_threads: number of loading threads running in parallel.
        :param progress_interval:
        """
        super().__init__(description=description,
                         flags=QgsTask.Silent | QgsTask.CanCancel | QgsTask.CancelWithoutPrompt)

        assert progress_interval >= 1

        n_badge = math.ceil(len(files) / n_threads)

        badge = []
        n_files = len(files)
        for i, file in enumerate(files):
            badge.append(file)
            if len(badge) >= n_badge or i == (n_files - 1):
                subTask = TimeSeriesLoadingSubTask(badge[:],
                                                   report_block_size=report_block_size,
                                                   description=self.description())
                subTask.imagesLoaded.connect(self.imagesLoaded)
                badge.clear()
                self.addSubTask(subTask, subTaskDependency=QgsTask.SubTaskDependency.ParentDependsOnSubTask)

        self.mInvalidSources: List[Tuple[str, Exception]] = []
        self.mValidSources: List[TimeSeriesSource] = []

    def canCancel(self) -> bool:
        return True

    def validSources(self) -> List[TimeSeriesSource]:
        return self.mValidSources[:]

    def invalidSources(self) -> List[Tuple[str, Exception]]:
        return self.mInvalidSources[:]

    def run(self) -> bool:
        for subTask in self._sub_tasks:
            assert isinstance(subTask, TimeSeriesLoadingSubTask)
            self.mInvalidSources.extend(subTask.invalid_sources)
            self.mValidSources.extend(subTask.valid_sources)
        self.executed.emit(True, self)
        return True
