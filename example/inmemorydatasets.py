# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 06.03.2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

from osgeo import gdal, ogr, osr, gdalconst
from timeseriesviewer.utils import createGeoTransform
def createInMemoryRaster(x=200,y=100,b=7, gsd=30, ulx=200, uly=300, nodata=-9999, epsg='EPSG:32721', eType=gdal.GDT_Int16):

    drv = gdal.GetDriverByName('MEM')
    assert isinstance(drv, gdal.Driver)
    """Create(Driver self, char const * utf8_path, int xsize, int ysize, int bands=1, GDALDataType eType, char ** options=None) -> Dataset"""
    ds = drv.Create('', x,y,bands=b, eType=eType)
    assert isinstance(ds, gdal.Dataset)
    srs = osr.SpatialReference()
    srs.SetFromUserInput(epsg)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform(createGeoTransform(gsd, ulx, uly))
    for b in range(ds.RasterCount):
        band = ds.GetRasterBand(b+1)
        assert isinstance(band, gdal.Band)
        if nodata is not None:
            band.SetNoDataValue(nodata)
    return ds




if __name__ == '__main__':
    ds = createInMemoryRaster()
    print(ds)
