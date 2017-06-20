import os, sys, re
import tempfile
from osgeo import gdal
from timeseriesviewer import file_search

class VirtualBandInputSource(object):
    def __init__(self, path, bandIndex):
        self.path = path
        self.bandIndex = bandIndex
        self.noData = None




class VirtualBand(object):

    def __init__(self, name=''):
        self.sources = []
        self.mName = name

    def addSourceBand(self, path, bandIndex):
        self.sources.append(VirtualBandInputSource(path, bandIndex))

    def sourceFiles(self):
        files = set([inputSource.path for inputSource in self.sources])
        return sorted(list(files))

    def __repr__(self):
        infos = ['VirtualBand name="{}"'.format(self.mName)]
        for i, info in enumerate(self.sources):
            assert isinstance(info, VirtualBandInputSource)
            infos.append('\t{} SourceFileName {} SourceBand {}'.format(i+1, info.path, info.bandIndex))
        return '\n'.join(infos)

class VirtualRasterBuilder(object):

    def __init__(self):
        self.vBands = []

    def addVirtualBand(self, virtualBand):
        assert isinstance(virtualBand, VirtualBand)
        self.vBands.append(virtualBand)

    def insertVirtualBand(self, i, virtualBand):
        assert isinstance(virtualBand, VirtualBand)
        self.vBands.insert(i, virtualBand)

    def addFilesAsMosaic(self, files):
        pass

    def addFilesAsStack(self, files):
        pass

    def sourceFiles(self):
        files = set()
        for vBand in self.vBands:
            assert isinstance(vBand, VirtualBand)
            files.update(set(vBand.sourceFiles()))
        return sorted(list(files))

    def saveVRT(self, pathVRT):

        dn = os.path.dirname(pathVRT)
        if not os.path.isdir(dn):
            os.mkdir(dn)

        srcFiles = self.sourceFiles()
        srcNodata = []
        for src in srcFiles:
            ds = gdal.Open(src)
            band = ds.GetRasterBand(1)
            noData = band.GetNoDataValue()
            if noData:
                srcNodata.append(noData)
        if len(srcNodata) == 0:
            srcNodata = None
        vro = gdal.BuildVRTOptions(separate=True, srcNodata=srcNodata)
        #1. build a temporary VRT that described the spatial shifts of all input sources
        gdal.BuildVRT(pathVRT, srcFiles, options=vro)
        dsVRTDst = gdal.Open(pathVRT)
        assert isinstance(dsVRTDst, gdal.Dataset)
        assert len(srcFiles) == dsVRTDst.RasterCount
        ns, nl = dsVRTDst.RasterXSize, dsVRTDst.RasterYSize
        gt = dsVRTDst.GetGeoTransform()
        crs = dsVRTDst.GetProjectionRef()
        eType = dsVRTDst.GetRasterBand(1).DataType
        SOURCE_TEMPLATES = dict()
        for i, srcFile in enumerate(srcFiles):
            vrt_sources = dsVRTDst.GetRasterBand(i+1).GetMetadata('vrt_sources')
            assert len(vrt_sources) == 1
            srcXML = vrt_sources.values()[0]
            assert os.path.basename(srcFile)+'</SourceFilename>' in srcXML
            assert '<SourceBand>1</SourceBand>' in srcXML
            SOURCE_TEMPLATES[srcFile] = srcXML
        dsVRTDst = None
        #remove the temporary VRT, we don't need it any more
        os.remove(pathVRT)

        #2. build final VRT from scratch
        drvVRT = gdal.GetDriverByName('VRT')
        assert isinstance(drvVRT, gdal.Driver)
        dsVRTDst = drvVRT.Create(pathVRT, ns, nl, eType=eType)
        #2.1. set general properties
        assert isinstance(dsVRTDst, gdal.Dataset)
        dsVRTDst.SetProjection(crs)
        dsVRTDst.SetGeoTransform(gt)

        #2.2. add virtual bands
        for i, vBand in enumerate(self.vBands):
            assert isinstance(vBand, VirtualBand)
            assert dsVRTDst.AddBand(eType, options=['subClass=VRTSourcedRasterBand']) == 0
            vrtBandDst = dsVRTDst.GetRasterBand(i+1)
            assert isinstance(vrtBandDst, gdal.Band)
            vrtBandDst.SetDescription(vBand.mName)
            md = {}
            #add all input sources for this virtual band
            for iSrc, sourceInfo in enumerate(vBand.sources):
                assert isinstance(sourceInfo, VirtualBandInputSource)
                bandIndex = sourceInfo.bandIndex
                xml = SOURCE_TEMPLATES[sourceInfo.path]
                xml = re.sub('<SourceBand>1</SourceBand>','<SourceBand>{}</SourceBand>'.format(bandIndex+1), xml)
                md['source_{}'.format(iSrc)] = xml
            vrtBandDst.SetMetadata(md,'vrt_sources')
            if True:
                vrtBandDst.ComputeBandStats(1)


        dsVRTDst = None

        #check if we get what we like to get
        dsCheck = gdal.Open(pathVRT)

        s = ""

        pass

    def __repr__(self):

        info = ['VirtualRasterBuilder: {} bands, {} source files'.format(
            len(self.vBands), len(self.sourceFiles()))]
        for vBand in self.vBands:
            info.append(str(vBand))
        return '\n'.join(info)

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
        V = VirtualRasterBuilder()

        #vrt = createVirtualBandStack(bandSources, pathVRT)
        #add bands in sorted order
        for bandName in sorted(bandSources.keys()):
            vBandSources = bandSources[bandName]
            VB = VirtualBand(name=bandName)
            for path in vBandSources:
                VB.addSourceBand(path, 0) #it's always one band only

            V.addVirtualBand(VB)
        #print(V)
        V.saveVRT(pathVRT)
        s = ""
        #add ISO time stamp

    pass

def groupLandsat(dirIn, dirOut):

    pass


if __name__ == '__main__':
    if True:
        dirIn = r'H:\CBERS\hugo\Download20170523'
        dirOut = r'H:\CBERS\VRTs'

        groupCBERS(dirIn, dirOut)
        exit(0)

    if True:
        dirIn = r'H:\CBERS\hugo\Download20170523'
        dirOut = r'H:\CBERS\VRTs'
        groupCBERS(dirIn, dirOut)

    if True:
        dirIn = r'H:\RapidEye\3A'
        dirOut = r'H:\RapidEye\VRTs'
        groupRapidEyeTiles(dirIn, dirOut)