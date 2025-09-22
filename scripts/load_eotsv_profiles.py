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
import datetime
import os
from pathlib import Path
from typing import List, Optional, Union

from osgeo import gdal, ogr

gdal.UseExceptions()
ogr.UseExceptions()


def read_timestamp(ds: gdal.Dataset) -> datetime.datetime:
    """
    Reads the observation time stamp from a raster dataset.
    If not defined in the metadata, it tries to extract it from the filename or parent
    folder name, if available.
    :param ds:
    :return: datetime.datetime
    """
    pass


def read_sensor_id(ds: gdal.Dataset) -> dict:
    """
    Reads the sensor ID from a raster dataset:
    :param ds:
    :return:
    """
    pass


def read_profiles(ds: gdal.Dataset, locations: List[ogr.Feature]) -> Optional[dict]:
    """
    Returns for each location that intersets with the raster dataset the
    pixel profiles and general metadata, like the source file name,
    the sensor ID, the observation time stamp, etc.

    :param ds:
    :param locations:
    :return: dict with keys 'sensor_id', 'dtg', 'uri' and 'profiles'
    """
    sensor_id = read_sensor_id(ds)
    timestamp = read_timestamp(ds)

    if timestamp is None:
        return None

def read_profiles(layer: ogr.Layer, raster: gdal.Dataset):

    if layer.GetLayerDefn():
        return read_profiles_from_points(layer, raster)
    else:
        raise read_profiles_from_geom(layer, raster, can_overlap=True)


def read_profiles_from_points(layer: ogr.Layer,
                              raster: gdal.Dataset):
    assert layer.GetSpatialRef().IsSame(raster.GetSpatialRef())


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


def load_eotsv_profiles(vector: Union[str, Path, ogr.DataSource],
                        raster: List[str],
                        field_name: str = 'profiles',
                        recursive: bool = False,
                        threads: int = 4) -> :
    if isinstance(vector, (str, Path)):
        vector = ogr.Open(str(vector))
    assert isinstance(vector, ogr.DataSource)

    # convert geom to target srs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sample temporal profiles from a EO raster time series for each vector feature.")
    parser.add_argument('-v', '--vector', required=True, help='Vector file with point geometries')
    parser.add_argument('-r', '--rasters', nargs='*',
                        help='Raster files to sample (space-separated). If omitted, use -r_dir')
    parser.add_argument('-r_dir', '--rasters-dir', help='Directory containing rasters (alternative to -r).')
    parser.add_argument('--id-field', help='Vector attribute to use as ID. If omitted, uses feature FID.')
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

    # Open and prepare rasters
    rasters_info = []
    for rpath in raster_paths:
        rds = open_raster(rpath)
        rinfo = get_raster_info(rds)
        rinfo['path'] = rpath
        rinfo['basename'] = os.path.splitext(os.path.basename(rpath))[0]
        rasters_info.append(rinfo)

    # Prepare vector layer
    vds, layer, lyr_defn = prepare_vector_layer(args.vector)

    # detect vector layer SRS
    v_srs = layer.GetS_
