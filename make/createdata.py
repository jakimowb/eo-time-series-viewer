# -*- coding: utf-8 -*-

"""
***************************************************************************
    
    ---------------------
    Date                 : 10.08.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
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

from eotimeseriesviewer.virtualrasters import *
from eotimeseriesviewer.utils import *
from osgeo import gdal, gdal_array
pathSrcDir = r'Z:\SenseCarbon\BJ\COS_BACKUP\01_RasterData\01_UncutVRT'
pathDstDir = r'D:\Temp\TSData'
#H:\RapidEye\VRTs\re_2014-08-26.vrt
if not os.path.exists(pathDstDir):
    os.makedirs(pathDstDir)

files = []
files += file_search(pathSrcDir, '*_BOA.vrt')
files += file_search(r'H:\RapidEye\VRTs', 're_*.vrt')


for i, pathVRT in enumerate(files):

    bn = os.path.basename(pathVRT)
    bn = os.path.splitext(bn)[0]
    pathDst = os.path.join(pathDstDir, bn+'.tif')
    co = ['COMPRESS=LZW','NUM_THREADS=ALL_CPUS']
    print('Write {}/{} {}...'.format(i + 1, len(files), pathDst))
    o = gdal.TranslateOptions(format='GTiff', creationOptions=co)
    dsSrc = gdal.Open(pathVRT)
    dsDst = gdal.Translate(pathDst, dsSrc, options=o)




exit(0)


