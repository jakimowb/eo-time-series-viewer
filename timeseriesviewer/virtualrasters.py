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

    def removeSourceBand(self, bandOrIndex):
        """
        Removes a virtual band
        :param bandOrIndex: int | VirtualBand
        :return: The VirtualBand that was removed
        """
        if not isinstance(bandOrIndex, VirtualBand):
            bandOrIndex = self.sources[bandOrIndex]
        return self.sources.remove(bandOrIndex)

    def sourceFiles(self):
        """
        :return: list of file-paths to all source files
        """
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
        self.vMetadata = dict()


    def addVirtualBand(self, virtualBand):
        """
        Adds a virtual band
        :param virtualBand: the VirtualBand to be added
        :return: VirtualBand
        """
        assert isinstance(virtualBand, VirtualBand)
        self.vBands.append(virtualBand)
        return self[-1]


    def insertVirtualBand(self, i, virtualBand):
        """
        Inserts a VirtualBand
        :param i: the insert position
        :param virtualBand: the VirtualBand to be inserted
        :return: the VirtualBand
        """
        assert isinstance(virtualBand, VirtualBand)
        self.vBands.insert(i, virtualBand)
        return self[i]



    def removeVirtualBands(self, bandsOrIndices):
        assert isinstance(bandsOrIndices, list)
        to_remove = []
        for bandOrIndex in bandsOrIndices:
            if not isinstance(bandOrIndex, VirtualBand):
                bandOrIndex = self.vBands[bandOrIndex]
            to_remove.append(bandOrIndex)

        for band in to_remove:
            self.vBands.remove(band)
        return to_remove


    def removeVirtualBand(self, bandOrIndex):
        r = self.removeVirtualBands([bandOrIndex])
        return r[0]

    def addFilesAsMosaic(self, files):
        """
        Shortcut to mosaic all input files. All bands will maintain their band position in the virtual file.
        :param files: [list-of-file-paths]
        """

        for file in files:
            ds = gdal.Open(file)
            assert isinstance(ds, gdal.Dataset)
            nb = ds.RasterCount
            for b in range(nb):
                if b+1 < len(self):
                    #add new virtual band
                    self.addVirtualBand(VirtualBand())
                vBand = self[b]
                assert isinstance(vBand, VirtualBand)
                vBand.addSourceBand(file, b)
        return self

    def addFilesAsStack(self, files):
        """
        Shortcut to stack all input files, i.e. each band of an input file will be a new virtual band.
        Bands in the virtual file will be ordered as file1-band1, file1-band n, file2-band1, file2-band,...
        :param files: [list-of-file-paths]
        :return: self
        """
        for file in files:
            ds = gdal.Open(file)
            assert isinstance(ds, gdal.Dataset)
            nb = ds.RasterCount
            ds = None
            for b in range(nb):
                #each new band is a new virtual band
                vBand = self.addVirtualBand(VirtualBand())
                assert isinstance(vBand, VirtualBand)
                vBand.addSourceBand(file, b)
        return self

    def sourceFiles(self):
        files = set()
        for vBand in self.vBands:
            assert isinstance(vBand, VirtualBand)
            files.update(set(vBand.sourceFiles()))
        return sorted(list(files))

    def saveVRT(self, pathVRT, **kwds):
        """
        :param pathVRT: path to VRT that is created
        :param options --- can be be an array of strings, a string or let empty and filled from other keywords..
        :param resolution --- 'highest', 'lowest', 'average', 'user'.
        :param outputBounds --- output bounds as (minX, minY, maxX, maxY) in target SRS.
        :param xRes, yRes --- output resolution in target SRS.
        :param targetAlignedPixels --- whether to force output bounds to be multiple of output resolution.
        :param bandList --- array of band numbers (index start at 1).
        :param addAlpha --- whether to add an alpha mask band to the VRT when the source raster have none.
        :param resampleAlg --- resampling mode.
        :param outputSRS --- assigned output SRS.
        :param allowProjectionDifference --- whether to accept input datasets have not the same projection. Note: they will *not* be reprojected.
        :param srcNodata --- source nodata value(s).
        :param callback --- callback method.
        :param callback_data --- user data for callback.
        :return: gdal.DataSet(pathVRT)
        """

        _kwds = dict()
        supported = ['options','resolution','outputBounds','xRes','yRes','targetAlignedPixels','addAlpha','resampleAlg',
        'outputSRS','allowProjectionDifference','srcNodata','VRTNodata','hideNodata','callback', 'callback_data']
        for k in kwds.keys():
            if k in supported:
                _kwds[k] = kwds[k]


        dn = os.path.dirname(pathVRT)
        if not os.path.isdir(dn):
            os.mkdir(dn)

        srcFiles = self.sourceFiles()
        srcNodata = None
        for src in srcFiles:
            ds = gdal.Open(src)
            band = ds.GetRasterBand(1)
            noData = band.GetNoDataValue()
            if noData and srcNodata is None:
                srcNodata = noData

        vro = gdal.BuildVRTOptions(separate=True, **_kwds)
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
        dsVRTDst = drvVRT.Create(pathVRT, ns, nl,0, eType=eType)
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
            if False:
                vrtBandDst.ComputeBandStats(1)


        dsVRTDst = None

        #check if we get what we like to get
        dsCheck = gdal.Open(pathVRT)

        s = ""
        return dsCheck

    def __repr__(self):

        info = ['VirtualRasterBuilder: {} bands, {} source files'.format(
            len(self.vBands), len(self.sourceFiles()))]
        for vBand in self.vBands:
            info.append(str(vBand))
        return '\n'.join(info)

    def __len__(self):
        return len(self.vBands)

    def __getitem__(self, slice):
        return self.vBands[slice]

    def __delitem__(self, slice):
        self.removeVirtualBands(self[slice])

    def __contains__(self, item):
        return item in self.vBands


    def __iter__(self):
        return iter(self.mClasses)

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
        separate=True,
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

