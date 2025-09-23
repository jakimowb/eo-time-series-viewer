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
from datetime import datetime
from pathlib import Path
from typing import List, Union, Tuple, Optional

from osgeo import gdal, ogr, osr
from osgeo.gdal import Dataset
from osgeo.ogr import OGRERR_NONE

from eotimeseriesviewer.qgispluginsupport.qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties

gdal.UseExceptions()
ogr.UseExceptions()

GDAL_DATATYPES = {}
for var in vars(gdal):
    match = re.search(r'^GDT_(?P<type>.*)$', var)
    if match:
        number = getattr(gdal, var)
        GDAL_DATATYPES[match.group('type')] = number
        GDAL_DATATYPES[match.group()] = number


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
    return json.dumps(jsonDict, ensure_ascii=False)


rxDTGKey = re.compile(r'(acquisition|observation)[ _]*(time|date|datetime)', re.IGNORECASE)

# date-time formats supported to read
# either as fmt = datetime.strptime format code, or
# or (fmt, rx), with rx being the regular expression to extract the part to be parsed with fmt
# regex needs to define a group called 'dtg' that can be extracted with match.group('dtg')
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


def datetimeFromString(text: str) -> Optional[datetime]:
    """
    Reads a datetime from a string.
    """

    # 1. try to parse ISO datetime
    try:
        return datetime.fromisoformat(text)
    except (ValueError, AttributeError):
        pass

    # 2. try to parse other formats
    for fmt in DATETIME_FORMATS:
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


class SourceInfoCreator(object):

    @classmethod
    def dataset(cls, uri: Union[Path, str]) -> gdal.Dataset:
        """
        Returns a gdal dataset from a URI.
        """
        uri = str(uri)
        return gdal.Open(uri)

    @classmethod
    def wavelength_info(cls, ds: gdal.Dataset) -> Tuple[Optional[List[float]], Optional[str]]:
        """
        Returns the wavelengths for each raster band and the
        corresponding wavelength unit.
        """
        s = ""

        # 1. test of GDAL-style wavelength definition
        wlu = 'um'
        wl = []
        
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            wl.append(band.GetMetadataItem('CENTRAL_WAVELENGTH_UM', 'IMAGERY'))
        if any(wl):
            return wlu, wl

        # 2. test ENVI header style definitions
        wlu = ds.GetMetadataItem('wavelength_unit', 'ENVI')
        wl = ds.GetMetadataItem('wavelengths', 'ENVI')

        # 3. check per-band definitions, very generic
        s = ""
        p = QgsRasterLayerSpectralProperties.fromGDALDataset(ds)

        s = ""
        return None, None

    @classmethod
    def datetime(cls, ds: gdal.Dataset) -> Optional[datetime]:

        # 1. search in well-known metadata domains
        domain_keys = [
            ('IMAGE_STRUCTURE', 'ACQUISITIONDATETIME'),
            ('ENVI', 'ACQUISITIONDATETIME'),
            ('FORCE', ''),
        ]

        for (domain, key) in domain_keys:
            value = ds.GetMetadataItem(key, domain)
            if isinstance(value, str):
                dtg = datetimeFromString(value)
                if isinstance(dtg, datetime):
                    return dtg

        # 2. search in filenames
        filenames = ds.GetFileList()
        if len(filenames) > 0:
            path = Path(filenames[0])

            if dtg := datetimeFromString(path.name):
                return dtg

            if dtg := datetimeFromString(path.parent.name):
                return dtg
        return None


def dataset_info(uri: str,
                 info_creator=SourceInfoCreator) -> Optional[dict]:
    """
    Reads the sensor ID from a raster dataset:
    :param ds:
    :return:
    """

    ds: gdal.Dataset = info_creator.dataset(uri)
    if not isinstance(ds, gdal.Dataset):
        return None

    timestamp = info_creator.datetime(ds)
    if not isinstance(timestamp, datetime):
        return None

    wl, wlu = info_creator.wavelength_info(ds)

    nb = ds.RasterCount
    dt = ds.GetRasterBand(1)

    trans = gdal.Transformer(ds, None, [])
    x1, y1 = trans.TransformPoint(False, 0, 0)
    x2, y2 = trans.TransformPoint(False, 1, 1)
    px_x = abs(x2 - x1)
    px_y = abs(y2 - y1)

    sid: str = sensorID(nb, px_x, px_y, dt, wl, wlu)

    nodata = [ds.GetRasterBand(b + 1).GetNoDataValue() for b in range(nb)]

    info = {'source': ds.GetDescription(),
            'dtg': datetime,
            'sid': sid,
            'nodata': nodata}

    return info


def read_profiles_from_files(files, points: dict, srs_wkt: str):
    errors = []
    results = []
    srs = osr.SpatialReference()
    srs.ImportFromWkt(srs_wkt)
    # get Lat Lon coordinates in Lon Lat / x y order
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    assert isinstance(srs, osr.SpatialReference)
    assert srs.Validate() == OGRERR_NONE, f'Invalid SRS: {srs_wkt}'

    # ensure that points are stored as tuple
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

    results = list()

    for file in files:

        ds: gdal.Dataset = gdal.Open(file)
        assert isinstance(ds, gdal.Dataset), f'Unable to open raster {file}'

        ds_info = dataset_info(ds)

        profiles = dict()

        r_srs = ds.GetSpatialRef()
        r_wkt = r_srs.ExportToWkt()

        if r_wkt not in POINTS2SRS:
            # transform points to raster SRS
            trans = osr.CoordinateTransformation(srs, r_srs)
            points_transformed = dict()

            for fid, point in points.items():
                points_transformed[fid] = trans.TransformPoint(*point)

            # keep transformed points in memory.
            # we don't want to re-transform them for each raster file'
            POINTS2SRS[r_wkt] = points_transformed

        transformer = gdal.Transformer(ds, None, [])

        points_r = POINTS2SRS[r_wkt]
        pixel, success = transformer.TransformPoints(True, list(points_r.values()))
        nodata = ds_info['nodata']
        for (px_x, px_y), succ in zip(pixel, success):
            px_x, px_y = int(px_x), int(px_y)

            if 0 <= px_x < ds.RasterXSize and 0 <= px_y < ds.RasterYSize:

                profile = ds.ReadAsArray(px_x, px_y, 1, 1).flatten()
                profile = [None if v == nd else v for nd, v in zip(nodata, profile)]
                if any(profile):
                    profiles[fid] = profile
        if len(profiles) > 0:
            ds_info['profiles'] = profiles
            results.append(ds_info)

    return results


def read_profiles_from_geom(layer: ogr.Layer,
                            raster: gdal.Dataset,
                            can_overlap: bool = False):
    assert layer.GetSpatialRef().IsSame(raster.GetSpatialRef())

    n_features = layer.GetFeatureCount()

    nl, ns = raster.RasterYSize, raster.RasterXSize

    drvMEM = gdal.GetDriverByName('MEM')
    mask_ds: gdal.Dataset = drvMEM.Create('', nl, ns, 1, gdal.GDT_UInt32)
    mask_ds.SetGeoTransform(raster.GetGeoTransform())
    mask_ds.SetProjection(raster.GetProjection())

    r = gdal.RasterizeLayer(mask_ds, [1], layer, burn_values=[1])
    assert r == gdal.CE_None

    mask = mask_ds.ReadAsArray()


def process_batch_files(batch_files: List[str], vector: ogr.DataSource, field_name: str = 'profiles'):
    """
    Process a batch of raster files in a single thread

    Args:
        batch_files: List of raster file paths to process
        vector: Vector data source containing the features
        field_name: Name of the field to store the profiles

    Returns:
        Dictionary of processed results
    """
    results = {}
    for file_path in batch_files:
        try:
            # Open the raster dataset
            ds = gdal.Open(file_path)
            if ds is None:
                print(f"Warning: Could not open raster {file_path}")
                continue

            # Process the raster (implementation would go here)
            # This is a placeholder for the actual processing logic
            print(f"Processing {file_path} in thread {concurrent.futures.thread.get_ident()}")

            # Store results
            results[file_path] = {
                'status': 'processed',
                'file': file_path
            }

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            results[file_path] = {
                'status': 'error',
                'message': str(e)
            }

    return results


def find_raster_files(raster, pattern='*.tif', recursive=False, regex: bool = False):
    raster = Path(raster)
    all_files = []
    if raster.is_dir():
        if recursive:
            # Walk through all subdirectories
            for root, _, files in os.walk(raster):
                for file in files:
                    if fnmatch.fnmatch(file, pattern):
                        all_files.append(os.path.join(root, file))

        else:
            # Just look in the specified directory
            with os.scandir(raster) as scan:
                for entry in scan:
                    if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                        all_files.append(entry.path)

    return all_files


import fnmatch


def main(rasters, vector, output_field: str = 'profiles',
         pattern='*.tif', threads=4,
         layer_name: Optional[Union[int, str]] = None,
         output_vector=None, recursive=False):
    if isinstance(rasters, (str, Path)):
        rasters = Path(rasters)

    if isinstance(vector, (str, Path)):
        vector = ogr.Open(str(vector))
    assert isinstance(vector, Dataset)

    if isinstance(layer_name, str):
        layer = vector.GetLayerByName(layer_name)
    elif isinstance(layer_name, int):
        layer = vector.GetLayer(layer_name)
    else:
        layer = vector.GetLayer()

    assert isinstance(layer, ogr.Layer), "Could not find layer"

    print('Search time series sources...')
    files = find_raster_files(rasters, pattern=pattern, recursive=recursive)

    assert len(files) > 0, 'No raster files found'

    points, srs_wkt = points_info(layer)

    # Calculate batch size
    n_files = len(files)
    batch_size = max(1, n_files // threads)
    batches = [files[i:i + batch_size] for i in range(0, n_files, batch_size)]

    # Process batches in parallel
    results = {}

    def collect_results(results: dict):

        for point, profiles in results.items():
            collection = results.get(point, [])
            collection.extend(profiles)
            results[point] = collection

    # create for each point the temporal profile

    s = ""

    if False:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            # Submit each batch to the executor
            future_to_batch = {
                executor.submit(process_batch_files, batch, vector, field_name): i
                for i, batch in enumerate(batches)
            }

            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_batch):
                batch_index = future_to_batch[future]
                try:
                    batch_results = future.result()
                    results.update(batch_results)
                    print(f"Completed batch {batch_index + 1}/{len(batches)}")
                except Exception as e:
                    print(f"Batch {batch_index} generated an exception: {str(e)}")
    else:
        for batch in batches:
            collect_results(read_profiles_from_files(batch, points, srs_wkt))

    # Process files using multithreading
    print(f"Processing {len(files)} files using {threads} threads")
    results = load_eotsv_profiles(
        vector=vector,
        raster=files,  # Pass the list of files directly
        field_name=output_field,
        recursive=recursive,
        threads=threads  # Fixed typo: theads -> threads
    )

    print(f"Completed processing {len(results) if results else 0} files")
    return results


def points_info(layer: ogr.Layer) -> Tuple[dict, str]:
    assert isinstance(layer, ogr.Layer)
    points = dict()
    for feature in layer:
        feature: ogr.Feature
        g = feature.GetGeometryRef()
        points[feature.GetFID()] = g.ExportToWkt()

    wkt_points = layer.GetSpatialRef().ExportToWkt()

    return points, wkt_points


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sample temporal profiles from a EO raster time series for each vector feature.")
    parser.add_argument('-v', '--vector', required=True, help='Vector file with point geometries')
    parser.add_argument('-r', '--rasters', nargs='*',
                        help='Raster files to sample (space-separated). If omitted, use -r_dir')
    parser.add_argument('-r_dir', '--rasters-dir', help='Directory containing rasters (alternative to -r).')
    parser.add_argument('--id-field', help='Vector attribute to use as ID. If omitted, uses feature FID.')
    parser.add_argument('-t', '--threads', type=int, default=4,
                        help='Number of threads to use for processing. Default is 4.')
    parser.add_argument('--recursive', action='store_true',
                        help='Recursively search for raster files in subdirectories.')
    parser.add_argument('-f', '--field', default='profiles',
                        help='Field name to store the extracted profiles. Default is "profiles".')
    args = parser.parse_args()

    raster_paths = []
    if args.rasters and len(args.rasters) > 0:
        raster_paths = args.rasters
    elif args.rasters_dir:
        raster_paths = list_rasters_from_dir(args.rasters_dir)
    else:
        parser.error("You must provide raster files with -r or a raster directory with -r_dir")

    if not raster_paths:
        raise RuntimeError("No raster files found/provided.")

    # detect vector layer SRS
    v_srs = layer.GetS_
