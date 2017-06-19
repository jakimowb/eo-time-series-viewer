import os, sys, re
from osgeo import gdal
from timeseriesviewer import file_search



def createVirtualBandMosaic(bandFiles, pathVRT):
    drv = gdal.GetDriverByName('VRT')

    refPath = bandFiles[0]
    refDS = gdal.Open(refPath)
    ns, nl, nb = refDS.RasterXSize, refDS.RasterYSize, refDS.RasterCount
    noData = refDS.GetRasterBand(1).GetNoDataValue()

    vrtOptions = gdal.BuildVRTOptions(
        # here we can use the options known from http://www.gdal.org/gdalbuildvrt.html
        separate=False
    )
    if len(bandFiles) > 1:
        s =""
    vrtDS = gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS.FlushCache()

    assert vrtDS.RasterCount == nb
    return vrtDS

def createVirtualBandStack(bandFiles, pathVRT):

    nb = len(bandFiles)

    drv = gdal.GetDriverByName('VRT')

    refPath = bandFiles[0]
    refDS = gdal.Open(refPath)
    ns, nl = refDS.RasterXSize, refDS.RasterYSize
    noData = refDS.GetRasterBand(1).GetNoDataValue()

    vrtOptions = gdal.BuildVRTOptions(
        # here we can use the options known from http://www.gdal.org/gdalbuildvrt.html
        separate=True
    )
    vrtDS = gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS.FlushCache()

    assert vrtDS.RasterCount == nb

    #copy band metadata from
    for i in range(nb):
        band = vrtDS.GetRasterBand(i+1)
        band.SetDescription(bandFiles[i])
        band.ComputeBandStats()

        if noData:
            band.SetNoDataValue(noData)
    return vrtDS


def groupRapidEyeTiles(dirIn, dirOut):
    """

    :param dirIn:
    :param dirOut:
    :return:
    """

    files = file_search(dirIn, '*_RE*_3A_*2.tif', recursive=True)

    if not os.path.exists(dirOut):
        os.mkdir(dirOut)

    sources = dict()
    for file in files:
        if not file.endswith('.tif'):
            continue
        dn = os.path.dirname(file)
        bn = os.path.basename(file)
        print(bn)
        id, date, sensor, product, _ = tuple(bn.split('_'))

        if not date in sources.keys():
            sources[date] = []
        sources[date].append(file)
    for date, files in sources.items():
        pathVRT = os.path.join(dirOut, 're_{}.vrt'.format(date))
        createVirtualBandMosaic(files, pathVRT)

def groupCBERS(dirIn, dirOut):
    files = file_search(dirIn, 'CBERS*.tif', recursive=True)

    if not os.path.exists(dirOut):
        os.mkdir(dirOut)

    sources = dict()
    for file in files:
        dn = os.path.dirname(file)
        bn = os.path.basename(file)
        #basenames like CBERS_4_MUX_20150603_167_107_L4_BAND5_GRID_SURFACE.tif
        id = bn.split('_')[:7]
        id.insert(0,dn)
        id = tuple(id)
        if id not in sources.keys():
            sources[id] = list()
        sources[id].append(file)

    for id, bands in sources.items():
        bands = sorted(bands)

        pathVRT = '_'.join(id[1:])+'.vrt'
        pathVRT = os.path.join(dirOut, pathVRT)
        vrt = createVirtualBandStack(bands, pathVRT)
        #add ISO time stamp

    pass

def groupLandsat(dirIn, dirOut):

    pass


if __name__ == '__main__':

    if True:
        dirIn = r'H:\CBERS\hugo\Download20170523'
        dirOut = r'H:\CBERS\VRTs'
        groupCBERS(dirIn, dirOut)

    if True:
        dirIn = r'H:\RapidEye\3A'
        dirOut = r'H:\RapidEye\VRTs'
        groupRapidEyeTiles(dirIn, dirOut)