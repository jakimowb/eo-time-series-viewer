# script to load EOTSV-like spectral profiles
# !/usr/bin/env python3
"""
load_eotsv_profiles.py

Samples EOTSV temporal profiles from a set of raster images for each point in a vector file.
Uses GDAL/OGR Python API (osgeo.gdal, osgeo.ogr, osgeo.osr) and standard python libraries only.

Adds a new text or JSON field to the vector file that contains the loaded temporal profiles.

Example:
    python load_eotsv_profiles.py \
        points.gpkg \
        /path/to/rasters \
        --field profiles
        --recursive
        --threads 4

"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Union, Tuple, Optional

from osgeo import gdal, ogr, osr, gdalconst
from osgeo.ogr import OGRERR_NONE

gdal.UseExceptions()
ogr.UseExceptions()

GDAL_DATATYPES = {}
for var in vars(gdal):
    match = re.search(r'^GDT_(?P<type>.*)$', var)
    if match:
        number = getattr(gdal, var)
        GDAL_DATATYPES[match.group('type')] = number
        GDAL_DATATYPES[match.group()] = number


class SourceInfoProvider(object):
    """
    A SourceInfoProvider provides information on the temporal and spectral characteristics of a raster source.
    Subclasses need to provide three methods:

    .dataset(uri) -> gdal.Dataset: returns a gdal dataset for input URI.
        Overwriting this method allows reading the dataset with customized parameters, e.g., using gdal.OpenEx()
        instead of gdal.Open().
        https://gdal.org/en/stable/api/python/raster_api.html#osgeo.gdal.OpenEx

        If it can be read GDAL, we can use the data source.

    .datetime(gdal.Dataset) -> datetime: returns the observation date-time for a gdal.Dataset.
        If we get a timestamp (date-time-group = dtg), we can sort it into a EO timeseries.

    .wavelengths(gdal.Dataset) -> (list[float], str): returns a list of wavelength values, one for each raster band and,
     the unit of wavelength values (e.g. 'nm').

        If we know the band wavelengths, we can calculate the spectral indices and provide short-cuts to select band
        combinations

    """

    rxDTGKey = re.compile(r'(acquisition|observation)[ _]*(time|date|datetime)', re.IGNORECASE)

    # date-time formats supported to read
    # either as fmt = datetime.strptime format code, or
    # or (fmt, rx), with rx being the regular expression to extract the part to be parsed with fmt.
    # The compiled regex 'rx' needs to define a group 'dtg' that defines the substring to parse
    # the date-time information from, as in `datetime.strptime(match.group('dtg'), fmt)`
    DATETIME_FORMATS = [
        # Landsat Scene ID
        ('%Y%j', re.compile(r'L[COTEM][45789]\d{3}\d{3}(?P<dtg>\d{4}\d{3})[A-Z]{2}[A-Z1]\d{2}')),

        # RapidEye
        ('%Y%m%d', re.compile(r'(?P<dtg>\d{8})')),
        ('%Y-%m-%d', re.compile(r'(?P<dtg>\d{4}-\d{2}-\d{2})')),
        ('%Y/%m/%d', re.compile(r'(?P<dtg>\d{4}/\d{2}/\d{2})')),

        # FORCE outputs
        ('%Y%m%d', re.compile(r'(?P<dtg>\d{8})_LEVEL\d_.+_(BOA|QAI|DST|HOT|VZN)')),
    ]

    rx_wlu = re.compile(r'^(wlu|wavelength[ -_]??units?)$', re.I)
    rx_wl = re.compile(r'^(wl|wavelengths?|center[_ ]?wavelengths?)$', re.I)

    @classmethod
    def dataset(cls, uri: Union[Path, str]) -> gdal.Dataset:
        """
        Returns a gdal dataset from a URI.
        """
        uri = str(uri)
        return gdal.Open(uri)

    @classmethod
    def sensorName(cls, ds: gdal.Dataset) -> Optional[str]:
        """
        Can return a specific sensor name, e.g. "Landsat 8" or "RapidEye".
        """
        metadata_positions = [
            # see https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing
            ('SATELLITEID', 'IMAGERY'),
            # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html
            ('SENSOR_TYPE', 'ENVI'),
            # FORCE outputs https://force-eo.readthedocs.io/en/latest/index.html
            ('FORCE', 'Sensor'),
        ]
        # check at Dataset level first
        for (key, domain) in metadata_positions:
            if value := ds.GetMetadataItem(key, domain):
                return value

        # check 1st band metadata
        if ds.RasterCount > 0:
            band1: gdal.Band = ds.GetRasterBand(1)
            for (key, domain) in metadata_positions:
                if value := band1.GetMetadataItem(key, domain):
                    return value
        return None

    @classmethod
    def datetime(cls, ds: gdal.Dataset) -> Optional[datetime]:
        """
        Return the observation date-time for a gdal.Dataset.
        """
        # 1. search in well-known metadata domains
        domain_keys = [
            # see https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing
            ('IMAGE_STRUCTURE', 'ACQUISITIONDATETIME'),
            ('ENVI', 'ACQUISITIONDATETIME'),
            ('FORCE', 'Date'),
        ]

        for (domain, key) in domain_keys:
            value = ds.GetMetadataItem(key, domain)
            if isinstance(value, str):
                dtg = cls._datetime_from_string(value)
                if isinstance(dtg, datetime):
                    return dtg

        # 2. search in path
        filenames = ds.GetFileList()
        if len(filenames) > 0:
            path = Path(filenames[0])

            # a) check the filename
            if dtg := cls._datetime_from_string(path.name):
                return dtg

            # b) check the file's folder name
            if dtg := cls._datetime_from_string(path.parent.name):
                return dtg

        return None

    @classmethod
    def wavelengths(cls, ds: gdal.Dataset) -> Tuple[Optional[List[float]], Optional[str]]:
        """
        Returns (i) a list of wavelength values, one for each raster band and,
        (ii) a string with the corresponding wavelength unit, e.g. "nm" for nanometers.
        """

        def deduce_wlu(wl: float) -> Optional[str]:
            """Try to deduce a wavelength unit from the wavelength value."""
            if 100 <= wl:
                return 'nm'
            elif 0 < wl < 100:  # even TIR sensors are below 100 μm
                return 'μm'
            else:
                return None

        def to_float_list(items: List[str]) -> Optional[List[Optional[float]]]:
            """
            Convert a list of strings or None values into a list of floats or None values.
            """
            results = []
            for s in items:
                try:
                    results.append(float(s))
                except TypeError:
                    results.append(None)
            if any(results):
                return results
            else:
                return None

        # 1. check for GDAL 3.10+ wavelength definition
        # see https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing for details

        wl = []
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            wl.append(band.GetMetadataItem('CENTRAL_WAVELENGTH_UM', 'IMAGERY'))
        if any(wl):
            wl = to_float_list(wl)
            return wl, 'μm'

        # 2. check for ENVI header style definitions
        # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html
        wlu = ds.GetMetadataItem('wavelength_units', 'ENVI')
        wl = ds.GetMetadataItem('wavelengths', 'ENVI')

        if wl:
            wl = to_float_list(wl)
            if wlu is None:
                # try to deduce wavelength unit from the highest wavelength
                wlu = deduce_wlu(max(wl), float)
            if len(wl) == ds.RasterCount:
                return wl, wlu

        # 3. generic checking for wavelengths in dataset metadata
        wl = wlu = None
        for domain in sorted(ds.GetMetadataDomainList()):
            for key, value in ds.GetMetadata_Dict(domain).items():
                if wl is None and cls.rx_wl.search(key):
                    # try to parse the wavelength
                    wl = re.split(',', re.sub('[{} ]', '', value.strip()))
                if wlu is None and cls.rx_wlu.search(key):
                    wlu = value

        if isinstance(wl, list) and len(wl) == ds.RasterCount:
            wl = to_float_list(wl)
            if wlu is None:
                wlu = deduce_wlu(max(wl))
            return wl, wlu

        # 4. generic checking for wavelengths in band metadata
        wl = []
        wlu = []
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            _wl = _wlu = None
            for key, value in band.GetMetadata_Dict().items():
                if _wl is None and cls.rx_wl.search(key):
                    # try to parse the wavelength
                    _wl = value
                    continue
                if _wlu is None and cls.rx_wlu.search(key):
                    _wlu = value
                    continue
            wl.append(_wl)
            wlu.append(_wlu)

        wl = to_float_list(wl)
        if len(wlu) > 0:
            for wlu_ in wlu:
                if isinstance(wlu_, str):
                    wlu = wlu_
                    break
            if isinstance(wlu, list):
                wlu = None
        elif isinstance(wl, list):
            # deduce wavelength unit from wavelength values
            wlu = deduce_wlu(max(wl), float)
        return wl, wlu

    @classmethod
    def _datetime_from_string(cls, text: str) -> Optional['datetime']:
        """
        Tries to parse a datetime from a string.
        """

        # 1. try to parse ISO datetime
        try:
            return datetime.fromisoformat(text)
        except (ValueError, AttributeError):
            pass

        # 2. try to parse other formats
        for fmt in cls.DATETIME_FORMATS:
            try:
                if isinstance(fmt, str):
                    return datetime.strptime(text, fmt)

                elif isinstance(fmt, tuple):
                    fmt, rx = fmt
                    if match := rx.search(text):
                        return datetime.strptime(match.group('dtg'), fmt)
            except (ValueError, AttributeError) as ex:
                s = ""
        return None

    @staticmethod
    def sensorID(nb: int,  # number of bands
                 px_size_x: float,  # pixel size x
                 px_size_y: float,  # pixel size y
                 dt: int,  # the GDAL datatype
                 wl: Optional[list] = None,  # list of wavelengths
                 wlu: Optional[str] = None,  # wavelength unit
                 name: Optional[str] = None) -> str:  # sensor name
        """
        Creates a sensor ID str
        :param name:
        :param dt:
        :param nb: number of bands
        :param px_size_x: pixel size x
        :param px_size_y: pixel size y
        :param wl: list of wavelength
        :param wlu: str, wavelength unit
        :return: str
        """
        assert dt in GDAL_DATATYPES.values()
        assert isinstance(dt, int)
        assert isinstance(nb, int) and nb > 0
        assert isinstance(px_size_x, (int, float)) and px_size_x > 0
        assert isinstance(px_size_y, (int, float)) and px_size_y > 0

        if wl is not None:
            assert isinstance(wl, list)
            assert len(wl) == nb

            if all([w is None for w in wl]):
                wl = None

        if wlu is not None:
            assert isinstance(wlu, str)

        if name is not None:
            assert isinstance(name, str)

        jsonDict = {'nb': nb,
                    'px_size_x': px_size_x,
                    'px_size_y': px_size_y,
                    'dt': int(dt),
                    'wl': wl,
                    'wlu': wlu,
                    'name': name
                    }
        # return jsonDict
        return json.dumps(jsonDict, ensure_ascii=False)


def aggregate_profiles(results):
    s = ""


def read_profiles(files: List,
                  points: dict,
                  srs_wkt: str,
                  provider: SourceInfoProvider = SourceInfoProvider) -> Tuple[List[dict], List[str]]:
    srs = osr.SpatialReference()
    srs.ImportFromWkt(srs_wkt)
    r = srs.Validate()
    # get Lat Lon coordinates in Lon Lat / x y order
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    assert isinstance(srs, osr.SpatialReference)
    assert srs.Validate() == OGRERR_NONE, f'Invalid SRS: {srs_wkt}'

    # ensure that point coordinates are stored as tuple
    def point2tuple(p):
        if isinstance(p, str):
            p = ogr.CreateGeometryFromWkt(p)
        if isinstance(p, bytes):
            p = ogr.CreateGeometryFromWkb(p)
        if isinstance(p, ogr.Geometry):
            p = p.GetPoint()
        assert 2 <= len(p) <= 3, f'Invalid point: {p}'
        return p

    points = {fid: point2tuple(g) for fid, g in points.items()}

    POINTS2SRS = dict()
    POINTS2SRS[srs_wkt] = points

    results: List[dict] = list()

    errors = list()
    for file in files:

        ds: gdal.Dataset = provider.dataset(file)
        if not isinstance(ds, gdal.Dataset):
            errors.append(f'Unable to open raster {file}')
            continue

        ds: gdal.Dataset = provider.dataset(file)
        if not isinstance(ds, gdal.Dataset):
            errors.append(f'Unable to open raster {file}')
            continue

        dtg = provider.datetime(ds)
        if not isinstance(dtg, datetime):
            errors.append(f'Unable to read datetime from {file}')
            continue
        # convert to ISO format string
        dtg = dtg.isoformat()

        # remove trailing zeros to keep the json short
        dtg = re.sub(r'T00(:00)*$', '', dtg)

        wl, wlu = provider.wavelengths(ds)
        sname = provider.sensorName(ds)

        nb = ds.RasterCount
        dt = ds.GetRasterBand(1).DataType

        # use the gdal.Transformer to get the pixel size of the center pixe
        # this way we can use images with RPCs
        trans2px = gdal.Transformer(ds, None, [])
        cx, cy = int(0.5 * ds.RasterXSize), int(0.5 * ds.RasterYSize)
        b1, xyz1 = trans2px.TransformPoint(False, cx, cy)
        b2, xyz2 = trans2px.TransformPoint(False, cx + 1, cy + 1)
        px_x = abs(xyz1[0] - xyz2[0])
        px_y = abs(xyz1[1] - xyz2[1])

        # create the sensor ID
        sid: str = SourceInfoProvider.sensorID(nb, px_x, px_y, dt, wl, wlu, name=sname)

        nodata = [ds.GetRasterBand(b + 1).GetNoDataValue() for b in range(nb)]

        r_info = {'source': ds.GetDescription(),
                  'dtg': dtg,
                  'sid': sid,
                  'nodata': nodata}

        # raster SRS
        r_srs = ds.GetSpatialRef()
        r_wkt = r_srs.ExportToWkt()

        # do we need to transform point coordinates to raster SRS?
        if r_wkt not in POINTS2SRS:
            # transform points to raster SRS
            trans2r = osr.CoordinateTransformation(srs, r_srs)
            points_transformed = dict()

            for fid, point in points.items():
                points_transformed[fid] = trans2r.TransformPoint(*point)

            # keep transformed points in memory.
            # we don't want to re-transform them for each raster file'
            POINTS2SRS[r_wkt] = points_transformed

        # points in raster SRS
        R_POINTS = POINTS2SRS[r_wkt]

        # convert SRS coordinate into raster pixel coordinates

        pixel, success = trans2px.TransformPoints(True, list(R_POINTS.values()))

        # read profiles for pixel coordinates within the image
        profiles = dict()
        for fid, xyz, success in zip(R_POINTS.keys(), pixel, success):
            if success:
                px_x, px_y = int(xyz[0]), int(xyz[1])

                if 0 <= px_x < ds.RasterXSize and 0 <= px_y < ds.RasterYSize:

                    profile = ds.ReadAsArray(px_x, px_y, 1, 1).flatten().tolist()
                    profile = [None if v == nd else v for nd, v in zip(nodata, profile)]
                    if any(profile):
                        profiles[fid] = profile

        if len(profiles) > 0:
            r_info['profiles'] = profiles
            results.append(r_info)

    return results, errors


def file_search(rootdir,
                pattern,
                recursive: bool = False,
                ignoreCase: bool = False,
                directories: bool = False,
                fullpath: bool = False):
    """
    Searches for files or folders
    :param rootdir: root directory to search in
    :param pattern: wildcard ("my*files.*") or regular expression that describes the file or folder name.
    :param recursive: set True to search recursively.
    :param ignoreCase: set True to ignore character case.
    :param directories: set True to search for directories/folders instead of files.
    :param fullpath: set True if the entire path should be evaluated and not the file name only
    :return: enumerator over file paths
    """
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))

    with os.scandir(rootdir) as entry_search:
        for entry in entry_search:
            if directories is False:
                if entry.is_file():
                    if fullpath:
                        name = entry.path
                    else:
                        name = os.path.basename(entry.path)
                    if isinstance(pattern, regType):
                        if pattern.search(name):
                            yield entry.path.replace('\\', '/')

                    elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                            or fnmatch.fnmatch(name, pattern):
                        yield entry.path.replace('\\', '/')
                elif entry.is_dir() and recursive is True:
                    for r in file_search(entry.path, pattern,
                                         recursive=recursive,
                                         directories=directories,
                                         fullpath=fullpath):
                        yield r
            else:
                if entry.is_dir():
                    if recursive is True:
                        for d in file_search(entry.path, pattern,
                                             recursive=recursive,
                                             directories=directories,
                                             fullpath=fullpath):
                            yield d

                    if fullpath:
                        name = entry.path
                    else:
                        name = os.path.basename(entry.path)
                    if isinstance(pattern, regType):
                        if pattern.search(name):
                            yield entry.path.replace('\\', '/')

                    elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                            or fnmatch.fnmatch(name, pattern):
                        yield entry.path.replace('\\', '/')


import fnmatch


def callback(progress, msg, data):
    print(f'Progress: {progress}')


def create_profile_layer(rasters, vector,
                         pattern: str = '*.tif',
                         n_jobs: int = 4,
                         layer_name: Optional[Union[int, str]] = None,
                         output_vector=None,
                         output_field: str = 'profiles',
                         output_format: str = None,
                         recursive=False) -> Tuple[gdal.Dataset, dict[int, dict]]:
    if isinstance(rasters, (str, Path)):
        rasters = Path(rasters)

    in_place = output_vector is None

    assert isinstance(vector, (str, Path))
    if in_place:
        ds = ogr.Open(str(vector), update=gdal.OF_UPDATE)
    else:
        if output_format is None:
            output_format = gdal.IdentifyDriver(str(vector)).ShortName

        drv: ogr.Driver = ogr.GetDriverByName(output_format)
        # ds_src = ogr.Open(str(vector))
        ds_src = gdal.OpenEx(str(vector), gdalconst.OF_VECTOR)

        if isinstance(layer_name, int):
            lyr_src = ds_src.GetLayer(layer_name)
        elif isinstance(layer_name, str):
            lyr_src = ds_src.GetLayerByName(layer_name)
        else:
            lyr_src = ds_src.GetLayer()

        assert isinstance(lyr_src, ogr.Layer), f"Could not find layer {layer_name}"
        assert lyr_src.GetFeatureCount() > 0, f'Layer {layer_name} is empty'

        out = Path(output_vector)
        if out.exists():
            out.unlink()

        if True:
            toptions = gdal.VectorTranslateOptions(
                # accessMode='update',
                layers=[lyr_src.GetName()],
                layerName=layer_name,
                emptyStrAsNull=True,
                format=output_format)

            gdal.VectorTranslate(str(output_vector), ds_src, options=toptions)
            ds = gdal.OpenEx(str(output_vector), nOpenFlags=gdalconst.OF_VECTOR | gdalconst.OF_UPDATE)

        else:

            # ds = drv.CopyDataSource(ds_src, str(output_vector))
            ds = drv.CreateDataSource(str(output_vector))
            lyr = ds.CopyLayer(lyr_src, layer_name)

        # ds = gdal.OpenEx(str(output_vector), gdalconst.OF_VECTOR)
        # del lyr_src
        # del ds_src

    assert isinstance(ds, (gdal.Dataset, ogr.DataSource)), 'Unable to open vector dataset'

    if isinstance(layer_name, str):
        lyr = ds.GetLayerByName(layer_name)
    elif isinstance(layer_name, int):
        lyr = ds.GetLayer(layer_name)
    else:
        lyr = ds.GetLayer()

    assert isinstance(lyr, ogr.Layer), 'Could not find layer'
    assert lyr.GetFeatureCount() > 0, f'Layer {lyr.GetName()} is empty'
    assert isinstance(output_field, str)
    field_names = [field.GetName() for field in lyr.schema]
    if output_field not in field_names:
        assert ogr.OGRERR_NONE == lyr.CreateField(
            ogr.FieldDefn(output_field, ogr.OFSTJSON))

    print('Search for potential source image files ...')
    if isinstance(pattern, str) and pattern.startswith('rx:'):
        pattern = re.compile(pattern[3:])

    files = list(file_search(rasters, pattern=pattern, recursive=recursive))
    n_total = len(files)
    assert n_total > 0, 'No raster files found'
    print(f'Found {n_total} files')

    points, srs_wkt = points_info(lyr)

    badges = []
    badge = []
    for file in files:
        badge.append(file)
        if len(badge) == 10:
            badges.append(badge.copy())
            badge.clear()
    if len(badge) > 0:
        badges.append(badge.copy())
    errors = []
    POINT2RESULTS = dict()

    # ProcessPoolExecutor
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
        # Start the load operations and mark each future with its URL
        future_to_url = {executor.submit(read_profiles, badge, points.copy(), srs_wkt): badge for badge in
                         badges}
        for future in concurrent.futures.as_completed(future_to_url):
            files = future_to_url[future]
            b_results, b_errors = future.result()
            for result in b_results:
                for fid, profile in result['profiles'].items():
                    POINT2RESULTS.setdefault(fid, []).append(result)
            errors.extend(b_errors)

    # convert results into multi-sensor profiles for each point

    TEMPORAL_PROFILES = create_temporal_profiles(POINT2RESULTS)

    # write results
    for f in lyr:
        fid = f.GetFID()
        if fid in TEMPORAL_PROFILES:
            data = TEMPORAL_PROFILES[fid]
            dump = json.dumps(data, ensure_ascii=False)
            f.SetField(output_field, dump)
            lyr.SetFeature(f)

    ds.FlushCache()
    return ds, TEMPORAL_PROFILES


def create_temporal_profiles(POINT2RESULTS: dict[int, dict]) -> dict[int, dict]:
    """
    Creates a compact representation of the temporal profiles for each point.
    """
    TEMPORAL_PROFILES: dict[int, dict] = {}

    for fid, point_results in POINT2RESULTS.items():
        point_dates = []
        point_profiles = []
        point_sids = []

        for result in point_results:
            point_dates.append(result['dtg'])
            point_profiles.append(result['profiles'][fid])
            point_sids.append(result['sid'])

        # order temporal profiles by observation time
        i_sorted = sorted(range(len(point_dates)), key=lambda i: point_dates[i])

        sorted_dates = []
        sorted_profiles = []
        sorted_sensor_idx = []

        SID2IDX = dict()

        for i in i_sorted:
            sorted_dates.append(point_dates[i])
            sorted_profiles.append(point_profiles[i])
            sid = point_sids[i]
            if sid not in SID2IDX:
                SID2IDX[sid] = len(SID2IDX)
            sorted_sensor_idx.append(SID2IDX[sid])

        temporal_profile = {
            # 'source'  # optional
            'date': sorted_dates,
            'sensor_ids': list(SID2IDX.keys()),
            'sensor': sorted_sensor_idx,
            'values': sorted_profiles,
        }

        TEMPORAL_PROFILES[fid] = temporal_profile
    return TEMPORAL_PROFILES


def points_info(layer: ogr.Layer) -> Tuple[dict, str]:
    """
    Returns a dictionary of point geometries and their corresponding SRS as WKT string.
    """
    assert isinstance(layer, ogr.Layer)
    points = dict()
    for feature in layer:
        feature: ogr.Feature
        g = feature.GetGeometryRef()
        points[feature.GetFID()] = g.ExportToWkt()

    srs_wkt = layer.GetSpatialRef().ExportToWkt()

    return points, srs_wkt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sample temporal profiles from EO raster time series for each vector feature.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage with default settings
    python load_eotsv_profiles.py -v points.gpkg -r_dir /path/to/rasters

    # With multiple specific raster files
    python load_eotsv_profiles.py -v points.gpkg -r file1.tif file2.tif file3.tif

    # Advanced usage with all options
    python load_eotsv_profiles.py -v points.gpkg -r_dir /path/to/rasters \\
        --recursive --threads 8 --field custom_profiles \\
        --output output.gpkg --pattern "*.tif"
        """
    )

    # Required arguments
    parser.add_argument('-v', '--vector', required=True,
                        help='Input vector file with point geometries')

    # Raster input options (mutually exclusive)
    raster_group = parser.add_mutually_exclusive_group(required=True)
    raster_group.add_argument('-r', '--rasters', nargs='+',
                              help='Space-separated list of raster files or directories to sample from')
    # Optional arguments
    parser.add_argument('--pattern', default='*.tif',
                        help='File pattern for raster search. Default: *.tif')
    parser.add_argument('-j', '--jobs', type=int, default=4,
                        help='Number of jobs to execute in parallel. Default: 4')
    parser.add_argument('--recursive', action='store_true',
                        help='Recursively search for raster files in directories')
    parser.add_argument('-f', '--field', default='profiles',
                        help='Field name to store the extracted profiles. Default: profiles')
    parser.add_argument('-o', '--output',
                        help='Output vector file. If omitted, input file will be modified in-place')
    parser.add_argument('-l', '--layer',
                        help='Layer name/index in the vector file to choose. '
                             'If omitted, first layer is used')
    parser.add_argument('--format', default='GPKG',
                        help='Output vector format (if --output is specified). Default: GPKG')

    args = parser.parse_args()

    # Prepare a raster input list
    raster_files = []
    if args.rasters:
        raster_files = args.rasters
    elif args.rasters_dir:
        raster_files = file_search(args.rasters_dir,
                                   pattern=args.pattern,
                                   recursive=args.recursive)

    if not raster_files:
        parser.error("No raster files found/provided")

    try:
        # Run the main function with parsed arguments
        ds_out, profiles = create_profile_layer(
            rasters=raster_files,
            vector=args.vector,
            pattern=args.pattern,
            n_jobs=args.threads,
            layer_name=args.layer,
            output_vector=args.output,
            output_field=args.field,
            output_format=args.format,
            recursive=args.recursive
        )

        print(f"Successfully processed {len(raster_files)} raster files")
        print(f"Results saved to: {args.output or args.vector}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
