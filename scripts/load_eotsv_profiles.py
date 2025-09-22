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
import datetime
import json
import os
import re
from pathlib import Path
from typing import List, Union, Tuple, Optional

from osgeo import gdal, ogr, osr
from osgeo.gdal import Dataset
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


def read_timestamp_default(ds: gdal.Dataset) -> datetime.datetime:
    """
    Reads the observation time stamp from a gdal raster dataset.
    If not defined in the metadata, it tries to extract it from the filename or parent
    folder name, if available.
    :param ds:
    :return: datetime.datetime
    """
    pass


def read_wavelengths_default(ds: gdal.Dataset) -> Tuple[List[float], str]:
    """
    Returns the wavelengths per raster band and wavelength unit from a gdal raster dataset.
    """
    pass


def dataset_info(ds: gdal.Dataset, f_wl=read_wavelengths_default, f_dtg=read_timestamp_default) -> Tuple[datetime, str]:
    """
    Reads the sensor ID from a raster dataset:
    :param ds:
    :return:
    """

    timestamp = f_dtg(ds)
    wl, wlu = f_wl(ds)

    nb = ds.RasterCount
    dt = ds.GetRasterBand(1)
    px_x = px_y = None
    sid: str = sensorID(nb, px_x, px_y, dt, wl, wlu)
    return timestamp, sid


def read_profiles_from_files(files, points: dict, srs_wkt: str):
    errors = []

    srs = osr.SpatialReference()
    srs.ImportFromWkt(srs_wkt)
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

    for file in files:

        ds: gdal.Dataset = gdal.Open(file)
        assert isinstance(ds, gdal.Dataset), f'Unable to open raster {file}'

        r_srs = ds.GetSpatialRef()
        r_wkt = r_srs.ExportToWkt()
        if r_wkt not in POINTS2SRS:
            # transform points to raster SRS
            trans = osr.CoordinateTransformation(srs, r_srs)
            points_transformed = dict()
            for fid, point in points.items():
                point_t = trans.TransformPoint(*point)
                points_transformed[fid] = point_t
            # keep transformed points in memory.
            # we don't need to re-transform them for each raster file'
            POINTS2SRS[r_wkt] = points_transformed

        transformer = gdal.Transformer(ds, None, [])
        points_r = POINTS2SRS[r_wkt]
        points_rt = {fid: (p[1], p[0]) for fid, p in points_r.items()}
        px, succ = transformer.TransformPoints(True, list(points_r.values()))
        px2, succ2 = transformer.TransformPoints(True, list(points_rt.values()))

        for px, success in transformer.TransformPoints(0, POINTS2SRS[r_wkt].values()):
            s = ""

    s = ""


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
