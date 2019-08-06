
import sys, re, os, collections
from os.path import join as jp


from osgeo import gdal, ogr, gdal_array
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from eotimeseriesviewer import *
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer.virtualrasters import VRTRasterInputSourceBand, VRTRasterBand, VRTRaster

def groupCBERS(dirIn, dirOut, pattern='CBERS*.tif'):
    files = file_search(dirIn, pattern, recursive=True)

    if not os.path.exists(dirOut):
        os.mkdir(dirOut)

    CONTAINERS = dict()
    for file in files:
        dn = os.path.dirname(file)
        bn = os.path.basename(file)
        #basenames like CBERS_4_MUX_20150603_167_107_L4_BAND5_GRID_SURFACE.tif
        splitted = bn.split('_')
        id = '_'.join(splitted[:4])
        bandName = splitted[7]

        if id not in CONTAINERS.keys():
            CONTAINERS[id] = dict()

        bandSources = CONTAINERS[id]
        if bandName not in bandSources.keys():
            bandSources[bandName] = list()
        bandSources[bandName].append(file)

    #mosaic all scenes of same date
    # and stack all bands related to the same channel
    for id, bandSources in CONTAINERS.items():

        pathVRT = id + '.vrt'
        pathVRT = os.path.join(dirOut, pathVRT)
        V = VRTRaster()

        #vrt = createVirtualBandStack(bandSources, pathVRT)
        #add bands in sorted order
        for bandName in sorted(bandSources.keys()):
            vBandSources = bandSources[bandName]
            VB = VRTRasterBand(name=bandName)
            for path in vBandSources:
                VB.addSourceBand(path, 0) #it's always one band only

            V.addVirtualBand(VB)
        #print(V)
        dsVRT = V.saveVRT(pathVRT)
        assert isinstance(dsVRT, gdal.Dataset)
        #add center wavelength information to ENVI domain
        import math
        #MUXCAM bands
        #see http://www.cbers.inpe.br/ingles/satellites/cameras_cbers3_4.php
        cwl = [0.5*(0.45+0.52),
               0.5*(0.52 + 0.59),
               0.5*(0.63 + 0.69),
               0.5*(0.77 + 0.89)]
        #https://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html
        dsVRT.SetMetadataItem('wavelength units','Micrometers', 'ENVI')
        dsVRT.SetMetadataItem('wavelength', '{{{}}}'.format(','.join([str(w) for w in cwl])), 'ENVI')
        dsVRT.SetMetadataItem('sensor type', 'CBERS', 'ENVI')
        for i, cw in enumerate(cwl):
            band = dsVRT.GetRasterBand(i+1)
            assert isinstance(band, gdal.Band)
            band.SetMetadataItem('wavelength',str(cw), 'ENVI')
        dsVRT = None


def groupLandsat(dirIn, dirOut, pattern='L*_sr_band*.img'):
    files = file_search(dirIn, pattern, recursive=True)

    if not os.path.exists(dirOut):
        os.mkdir(dirOut)

    CONTAINERS = dict()
    for file in files:
        dn = os.path.dirname(file)
        bn = os.path.basename(file)
        #basenames like LC82270652013140LGN01_sr_band2.img
        splitted = re.split('[_\.]', bn)
        id = splitted[0]
        bandName = splitted[2]

        if id not in CONTAINERS.keys():
            CONTAINERS[id] = dict()

        bandSources = CONTAINERS[id]
        if bandName not in bandSources.keys():
            bandSources[bandName] = list()
        bandSources[bandName].append(file)

    #mosaic all scenes of same date
    # and stack all bands related to the same channel
    for id, bandSources in CONTAINERS.items():

        pathVRT = id + '.vrt'
        pathVRT = os.path.join(dirOut, pathVRT)
        V = VRTRaster()

        #vrt = createVirtualBandStack(bandSources, pathVRT)
        #add bands in sorted order
        for bandName in sorted(bandSources.keys()):
            vBandSources = bandSources[bandName]
            VB = VRTRasterBand(name=bandName)
            for path in vBandSources:
                VB.addSourceBand(path, 0) #it's always one band only

            V.addVirtualBand(VB)
        #print(V)
        dsVRT = V.saveVRT(pathVRT)
        assert isinstance(dsVRT, gdal.Dataset)
        #add center wavelength information to ENVI domain
        import math
        #MUXCAM bands
        #see http://www.cbers.inpe.br/ingles/satellites/cameras_cbers3_4.php
        if re.search('LC8', id):
            cwl = [0.5*(0.433 + 0.453),
                   0.5*(0.450 + 0.515),
                   0.5*(0.525 + 0.600),
                   0.5*(0.630 + 0.680),
                   0.5 * (0.845 + 0.885),
                   0.5 * (1.560 + 1.660),
                   0.5 * (2.100 + 2.300)]
        else:
            raise NotImplementedError()

        #https://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html
        dsVRT.SetMetadataItem('wavelength units', 'Micrometers', 'ENVI')
        dsVRT.SetMetadataItem('wavelength', '{{{}}}'.format(','.join([str(w) for w in cwl])), 'ENVI')
        dsVRT.SetMetadataItem('sensor type', 'Landsat-8 OLI', 'ENVI')
        from eotimeseriesviewer.dateparser import datetime64FromYYYYDOY
        dt = datetime64FromYYYYDOY(id[9:16])
        assert dt > np.datetime64('1900-01-01')
        assert dt < np.datetime64('2999-12-31')
        dsVRT.SetMetadataItem('acquisition time', str(dt), 'ENVI')
        for i, cw in enumerate(cwl):
            band = dsVRT.GetRasterBand(i+1)
            assert isinstance(band, gdal.Band)
            band.SetMetadataItem('wavelength',str(cw), 'ENVI')
        dsVRT = None


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

    from eotimeseriesviewer.virtualrasters import createVirtualBandMosaic
    for date, files in sources.items():
        pathVRT = os.path.join(dirOut, 're_{}.vrt'.format(date))


        dsVRT = createVirtualBandMosaic(files, pathVRT)
        cwl = [0.5 * (440 + 510),
               0.5 * (520 + 590),
               0.5 * (630 + 685),
               0.5 * (690 + 730),
               0.5 * (760 + 850)]

        dsVRT.SetMetadataItem('wavelength units', 'Nanometers', 'ENVI')
        dsVRT.SetMetadataItem('wavelength', '{{{}}}'.format(','.join([str(w) for w in cwl])), 'ENVI')
        dsVRT.SetMetadataItem('sensor type', 'RapidEye', 'ENVI')
        dsVRT = createVirtualBandMosaic(files, pathVRT)


def copyMetadataDomains(dsSrc, dsDst, domains=['ENVI']):
    """
    Updates metadata.
    :param dsSrc:
    :param dsDst:
    :param domains:
    :return:
    """
    assert isinstance(dsSrc, gdal.Dataset)
    assert isinstance(dsDst, gdal.Dataset)

    for domain in domains:
        mdDst = dsDst.GetMetadata(domain)
        mdDst.update(dsSrc.GetMetadata(domain))
        dsDst.SetMetadata(mdDst, domain)
        for i in range(min([dsSrc.RasterCount, dsDst.RasterCount])):
            bandSrc = dsSrc.GetRasterBand(i+1)
            bandDst = dsDst.GetRasterBand(i+1)
            mdDst = bandDst.GetMetadata(domain)
            mdDst.update(bandSrc.GetMetadata(domain))
            bandDst.SetMetadata(mdDst, domain)

def addPyramids(dir, pattern, levels=None):

    for file in file_search(dir, pattern):
        ds = gdal.Open(file)
        assert isinstance(ds, gdal.Dataset)
        nb = ds.RasterCount
        #BuildOverviews(Dataset self, char const * resampling="NEAREST", int overviewlist=0,
        # GDALProgressFunc callback=0,
        # void * callback_data=None) -> int
        res = ds.BuildOverviews('NEAREST', [2,4,8])




def vrt2Binary(dirVRTs, dirBins, drvNameDst='GTiff', recursive=False, overwrite=True):
    pathVRTs = file_search(dirVRTs, '*.vrt', recursive=recursive)
    if not os.path.isdir(dirBins):
        os.mkdir(dirBins)
    drvDst = gdal.GetDriverByName(drvNameDst)
    assert isinstance(drvDst, gdal.Driver)
    for pathVRT in pathVRTs:
        bn = os.path.basename(pathVRT)
        bn = os.path.splitext(bn)[0]
        pathDst = os.path.join(dirBins, '{}.{}'.format(bn, drvDst.GetMetadataItem('DMD_EXTENSION')))
        dsSrc = gdal.Open(pathVRT)
        assert isinstance(dsSrc, gdal.Dataset)
        if overwrite or not os.path.exists(pathDst):
            options = gdal.TranslateOptions(format=drvDst.ShortName)
            print('Write {}...'.format(pathDst))
            dsDst = gdal.Translate(pathDst, dsSrc, options=options)
            assert isinstance(dsDst, gdal.Dataset)
            copyMetadataDomains(dsSrc, dsDst, ['ENVI'])



def testdataMultitemp2017():

    jp = os.path.join

    if sys.platform == 'darwin':
        root = r'/Users/Shared/Multitemp2017'
    else:
        root = r'O:\SenseCarbonProcessing\BJ_Multitemp2017'

    dirSrcCBERS = jp(root, *['01_Data','CBERS','Data'])
    dirVRTCBERS = jp(root, *['01_Data','CBERS'])
    dirSrcL8 = jp(root, *['01_Data','Landsat','L1T'])
    dirVRTL8 = jp(root, *['01_Data','Landsat'])
    dirSrcRE = jp(root, *['01_Data','RapidEye','3A'])
    dirVRTRE = jp(root, *['01_Data','RapidEye'])

    if False:
        groupCBERS(dirSrcCBERS, dirVRTCBERS, '*CBERS*167_108_*.tif')

    if False:
        groupLandsat(dirSrcL8, dirVRTL8)

    if False:
        groupRapidEyeTiles(dirSrcRE, dirVRTRE)
        #addPyramids(dirVRTRE, '*.vrt', levels=[2,4,8])

    if True:
        dirVRT = dirVRTL8
        dirBin = jp(dirVRT, '3AS')

        gdal.SetCacheMax(100*2*20)
        vrt2Binary(dirVRT, dirBin, overwrite=False)


def compressTestdata(dirTestdata, dirCompressedData=None):

    files = file_search(dirTestdata, '*.bsq')
    files += file_search(dirTestdata, '*.tif')
    if dirCompressedData is None:
        dirCompressedData = dirTestdata +'_compressed'

    if not os.path.exists(dirCompressedData):
        os.makedirs(dirCompressedData)

    drvTIFF = gdal.GetDriverByName('GTiff')
    assert isinstance(drvTIFF, gdal.Driver)
    ext = drvTIFF.GetMetadataItem('DMD_EXTENSION')
    co = ['NUM_THREADS=ALL_CPUS','COMPRESS=LZW']
    n_total = len(files)
    def callback(*args):
        progress, msg, t = args
        i, n_total, file = t
        totalProgress = (i+progress) / n_total
        print('Progress {:0.2f}'.format(totalProgress*100))

    for i,file in enumerate(files):
        bn = os.path.basename(file)
        bn = os.path.splitext(bn)[0]
        ds = gdal.Open(file)
        assert isinstance(ds, gdal.Dataset)
        band = ds.GetRasterBand(1)
        assert isinstance(band, gdal.Band)
        data = band.ReadAsArray()
        if data.std() == 0:
            continue
        if band.GetNoDataValue():
            s = ""


        pathDst = jp(dirCompressedData,bn+'.'+ext )
        """
         options = [], format = 'GTiff',
         outputType = GDT_Unknown, bandList = None, maskBand = None,
         width = 0, height = 0, widthPct = 0.0, heightPct = 0.0,
         xRes = 0.0, yRes = 0.0,
         creationOptions = None, srcWin = None, projWin = None, projWinSRS = None, strict = False,
         unscale = False, scaleParams = None, exponents = None,
         outputBounds = None, metadataOptions = None,
         outputSRS = None, GCPs = None,
         noData = None, rgbExpand = None,
         stats = False, rat = True, resampleAlg = None,
         callback = None, callback_data = None)
        """
        options = gdal.TranslateOptions(options=co, format=drvTIFF.ShortName,
                                        callback = callback, callback_data=(i,n_total, file))

        gdal.Translate(pathDst,file,options=options )
        s = ""


if __name__ == '__main__':
    #testdataMultitemp2017()
    import example.Images
    compressTestdata(os.path.dirname(example.Images.__file__))

    print('done')