# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming
from __future__ import absolute_import
import os, sys, re, pickle, tempfile
from collections import OrderedDict
import tempfile
from osgeo import gdal, osr, ogr
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

def px2geo(px, gt):
    #see http://www.gdal.org/gdal_datamodel.html
    gx = gt[0] + px.x()*gt[1]+px.y()*gt[2]
    gy = gt[3] + px.x()*gt[4]+px.y()*gt[5]
    return QgsPoint(gx,gy)


class VRTRasterInputSourceBand(object):
    def __init__(self, path, bandIndex, bandName=''):
        self.mPath = os.path.normpath(path)
        self.mBandIndex = bandIndex
        self.mBandName = bandName
        self.mNoData = None
        self.mVirtualBand = None


    def isEqual(self, other):
        if isinstance(other, VRTRasterInputSourceBand):
            return self.mPath == other.mPath and self.mBandIndex == other.mBandIndex
        else:
            return False

    def __reduce_ex__(self, protocol):

        return self.__class__, (self.mPath, self.mBandIndex, self.mBandName), self.__getstate__()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('mVirtualBand')
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def virtualBand(self):
        return self.mVirtualBand


class VRTRasterBand(QObject):
    sigNameChanged = pyqtSignal(str)
    sigSourceInserted = pyqtSignal(int, VRTRasterInputSourceBand)
    sigSourceRemoved = pyqtSignal(int, VRTRasterInputSourceBand)
    def __init__(self, name='', parent=None):
        super(VRTRasterBand, self).__init__(parent)
        self.sources = []
        self.mName = name
        self.mVRT = None


    def setName(self, name):
        oldName = self.mName
        self.mName = name
        if oldName != self.mName:
            self.sigNameChanged.emit(name)

    def name(self):
        return self.mName



    def addSource(self, virtualBandInputSource):
        assert isinstance(virtualBandInputSource, VRTRasterInputSourceBand)
        self.insertSource(len(self.sources), virtualBandInputSource)

    def insertSource(self, index, virtualBandInputSource):
        assert isinstance(virtualBandInputSource, VRTRasterInputSourceBand)
        virtualBandInputSource.mVirtualBand = self
        assert index <= len(self.sources)
        self.sources.insert(index, virtualBandInputSource)
        self.sigSourceInserted.emit(index, virtualBandInputSource)

    def bandIndex(self):
        if isinstance(self.mVRT, VRTRaster):
            return self.mVRT.mBands.index(self)
        else:
            return None


    def removeSource(self, vrtRasterInputSourceBand):
        """
        Removes a VRTRasterInputSourceBand
        :param vrtRasterInputSourceBand: band index| VRTRasterInputSourceBand
        :return: The VRTRasterInputSourceBand that was removed
        """
        if not isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand):
            vrtRasterInputSourceBand = self.sources[vrtRasterInputSourceBand]
        if vrtRasterInputSourceBand in self.sources:
            i = self.sources.index(vrtRasterInputSourceBand)
            self.sources.remove(vrtRasterInputSourceBand)
            self.sigSourceRemoved.emit(i, vrtRasterInputSourceBand)


    def sourceFiles(self):
        """
        :return: list of file-paths to all source files
        """
        files = set([inputSource.mPath for inputSource in self.sources])
        return sorted(list(files))

    def __repr__(self):
        infos = ['VirtualBand name="{}"'.format(self.mName)]
        for i, info in enumerate(self.sources):
            assert isinstance(info, VRTRasterInputSourceBand)
            infos.append('\t{} SourceFileName {} SourceBand {}'.format(i + 1, info.mPath, info.mBandIndex))
        return '\n'.join(infos)

LUT_ReampleAlg = {'nearest': gdal.GRA_NearestNeighbour,
                  'bilinear': gdal.GRA_Bilinear,
                  'mode':gdal.GRA_Mode,
                  'lanczos':gdal.GRA_Lanczos,
                  'average':gdal.GRA_Average,
                  'cubic':gdal.GRA_Cubic,
                  'cubic_splie':gdal.GRA_CubicSpline}


class VRTRaster(QObject):

    sigSourceBandInserted = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigSourceBandRemoved = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigSourceRasterAdded = pyqtSignal(list)
    sigSourceRasterRemoved = pyqtSignal(list)
    sigBandInserted = pyqtSignal(int, VRTRasterBand)
    sigBandRemoved = pyqtSignal(int, VRTRasterBand)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)


    def __init__(self, parent=None):
        super(VRTRaster, self).__init__(parent)
        self.mBands = []
        self.mCrs = None
        self.mResampleAlg = gdal.GRA_NearestNeighbour
        self.mMetadata = dict()
        self.mSourceRasterBounds = dict()
        self.mOutputBounds = None
        self.sigSourceBandRemoved.connect(self.updateSourceRasterBounds)
        self.sigSourceBandInserted.connect(self.updateSourceRasterBounds)
        self.sigBandRemoved.connect(self.updateSourceRasterBounds)
        self.sigBandInserted.connect(self.updateSourceRasterBounds)

    def setCrs(self, crs):
        if isinstance(crs, osr.SpatialReference):
            auth = '{}:{}'.format(crs.GetAttrValue('AUTHORITY',0), crs.GetAttrValue('AUTHORITY',1))
            crs = QgsCoordinateReferenceSystem(auth)
        if isinstance(crs, QgsCoordinateReferenceSystem):
            if crs != self.mCrs:
                self.mCrs = crs
                self.sigCrsChanged.emit(self.mCrs)


    def crs(self):
        return self.mCrs

    def addVirtualBand(self, virtualBand):
        """
        Adds a virtual band
        :param virtualBand: the VirtualBand to be added
        :return: VirtualBand
        """
        assert isinstance(virtualBand, VRTRasterBand)
        return self.insertVirtualBand(len(self), virtualBand)

    def insertSourceBand(self, virtualBandIndex, pathSource, sourceBandIndex):
        """
        Inserts a source band into the VRT stack
        :param virtualBandIndex: target virtual band index
        :param pathSource: path of source file
        :param sourceBandIndex: source file band index
        """

        while virtualBandIndex > len(self.mBands)-1:

            self.insertVirtualBand(len(self.mBands), VRTRasterBand())

        vBand = self.mBands[virtualBandIndex]
        vBand.addSourceBand(pathSource, sourceBandIndex)


    def insertVirtualBand(self, index, virtualBand):
        """
        Inserts a VirtualBand
        :param index: the insert position
        :param virtualBand: the VirtualBand to be inserted
        :return: the VirtualBand
        """
        assert isinstance(virtualBand, VRTRasterBand)
        assert index <= len(self.mBands)
        if len(virtualBand.name()) == 0:
            virtualBand.setName('Band {}'.format(index+1))
        virtualBand.mVRT = self

        virtualBand.sigSourceInserted.connect(
            lambda _, sourceBand: self.sigSourceBandInserted.emit(virtualBand, sourceBand))
        virtualBand.sigSourceRemoved.connect(
            lambda _, sourceBand: self.sigSourceBandInserted.emit(virtualBand, sourceBand))

        self.mBands.insert(index, virtualBand)
        self.sigBandInserted.emit(index, virtualBand)

        return self[index]



    def removeVirtualBands(self, bandsOrIndices):
        assert isinstance(bandsOrIndices, list)
        to_remove = []
        for virtualBand in bandsOrIndices:
            if not isinstance(virtualBand, VRTRasterBand):
                virtualBand = self.mBands[virtualBand]
            to_remove.append((self.mBands.index(virtualBand), virtualBand))

        to_remove = sorted(to_remove, key=lambda t: t[0], reverse=True)
        for index, virtualBand in to_remove:
            self.mBands.remove(virtualBand)
            self.sigBandRemoved.emit(index, virtualBand)



    def removeVirtualBand(self, bandOrIndex):
        self.removeVirtualBands([bandOrIndex])


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
                    self.addVirtualBand(VRTRasterBand())
                vBand = self[b]
                assert isinstance(vBand, VRTRasterBand)
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
                vBand = self.addVirtualBand(VRTRasterBand())
                assert isinstance(vBand, VRTRasterBand)
                vBand.addSource(VRTRasterInputSourceBand(file, b))
        return self

    def sourceRaster(self):
        files = set()
        for vBand in self.mBands:
            assert isinstance(vBand, VRTRasterBand)
            files.update(set(vBand.sourceFiles()))
        return sorted(list(files))

    def sourceRasterBounds(self):
        return self.mSourceRasterBounds

    def outputBounds(self):
        if isinstance(self.mOutputBounds, RasterBounds):
            return
            #calculate from source rasters

    def setOutputBounds(self, bounds):
        assert isinstance(self, RasterBounds)
        self.mOutputBounds = bounds


    def updateSourceRasterBounds(self):

        srcFiles = self.sourceRaster()
        toRemove = [f for f in self.mSourceRasterBounds.keys() if f not in srcFiles]
        toAdd = [f for f in srcFiles if f not in self.mSourceRasterBounds.keys()]

        for f in toRemove:
            del self.mSourceRasterBounds[f]
        for f in toAdd:
            self.mSourceRasterBounds[f] = RasterBounds(f)

        if len(srcFiles) > 0 and self.crs() == None:
            self.setCrs(self.mSourceRasterBounds[srcFiles[0]].crs)

        elif len(srcFiles) == 0:
            self.setCrs(None)


        if len(toRemove) > 0:
            self.sigSourceRasterRemoved.emit(toRemove)
        if len(toAdd) > 0:
            self.sigSourceRasterAdded.emit(toAdd)


    def saveVRT(self, pathVRT, resampleAlg=gdal.GRA_NearestNeighbour, **kwds):
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

        assert os.path.splitext(pathVRT)[-1].lower() == '.vrt'

        _kwds = dict()
        supported = ['options','resolution','outputBounds','xRes','yRes','targetAlignedPixels','addAlpha','resampleAlg',
        'outputSRS','allowProjectionDifference','srcNodata','VRTNodata','hideNodata','callback', 'callback_data']
        for k in kwds.keys():
            if k in supported:
                _kwds[k] = kwds[k]

        if 'resampleAlg' not in _kwds:
            _kwds['resampleAlg'] = resampleAlg

        if isinstance(self.mOutputBounds, RasterBounds):
            bounds = self.mOutputBounds.polygon
            xmin, ymin,xmax, ymax = bounds
            _kwds['outputBounds'] = (xmin, ymin,xmax, ymax)

        dirVrt = os.path.dirname(pathVRT)
        dirWarpedVRT = os.path.join(dirVrt, 'WarpedVRTs')
        if not os.path.isdir(dirVrt):
            os.mkdir(dirVrt)

        srcLookup = dict()
        srcNodata = None
        for i, pathSrc in enumerate(self.sourceRaster()):
            dsSrc = gdal.Open(pathSrc)
            assert isinstance(dsSrc, gdal.Dataset)
            band = dsSrc.GetRasterBand(1)
            noData = band.GetNoDataValue()
            if noData and srcNodata is None:
                srcNodata = noData

            crs = QgsCoordinateReferenceSystem(dsSrc.GetProjection())

            if crs == self.mCrs:
                srcLookup[pathSrc] = pathSrc
            else:

                if not os.path.isdir(dirWarpedVRT):
                    os.mkdir(dirWarpedVRT)
                pathVRT2 = os.path.join(dirWarpedVRT, 'warped.{}.vrt'.format(os.path.basename(pathSrc)))
                wops = gdal.WarpOptions(format='VRT',
                                        dstSRS=self.mCrs.toWkt())
                tmp = gdal.Warp(pathVRT2, dsSrc, options=wops)
                assert isinstance(tmp, gdal.Dataset)
                tmp = None
                srcLookup[pathSrc] = pathVRT2




        srcFiles = [srcLookup[src] for src in self.sourceRaster()]

        vro = gdal.BuildVRTOptions(separate=True, **_kwds)
        #1. build a temporary VRT that described the spatial shifts of all input sources
        gdal.BuildVRT(pathVRT, srcFiles, options=vro)
        dsVRTDst = gdal.Open(pathVRT)
        assert isinstance(dsVRTDst, gdal.Dataset)
        assert len(srcLookup) == dsVRTDst.RasterCount
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
        for i, vBand in enumerate(self.mBands):
            assert isinstance(vBand, VRTRasterBand)
            assert dsVRTDst.AddBand(eType, options=['subClass=VRTSourcedRasterBand']) == 0
            vrtBandDst = dsVRTDst.GetRasterBand(i+1)
            assert isinstance(vrtBandDst, gdal.Band)
            vrtBandDst.SetDescription(vBand.mName)
            md = {}
            #add all input sources for this virtual band
            for iSrc, sourceInfo in enumerate(vBand.sources):
                assert isinstance(sourceInfo, VRTRasterInputSourceBand)
                bandIndex = sourceInfo.mBandIndex
                xml = SOURCE_TEMPLATES[srcLookup[sourceInfo.mPath]]
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
            len(self.mBands), len(self.sourceRaster()))]
        for vBand in self.mBands:
            info.append(str(vBand))
        return '\n'.join(info)

    def __len__(self):
        return len(self.mBands)

    def __getitem__(self, slice):
        return self.mBands[slice]

    def __delitem__(self, slice):
        self.removeVirtualBands(self[slice])

    def __contains__(self, item):
        return item in self.mBands

    def __iter__(self):
        return iter(self.mClasses)





class VRTRasterVectorLayer(QgsVectorLayer):

    def __init__(self, vrtRaster, crs=None):
        assert isinstance(vrtRaster, VRTRaster)
        if crs is None:
            crs = QgsCoordinateReferenceSystem('EPSG:4326')

        uri = 'Linestring?crs={}'.format(crs.authid())
        super(VRTRasterVectorLayer, self).__init__(uri, 'VRTRaster', 'memory', False)
        self.mCrs = crs
        self.mVRTRaster = vrtRaster

        #initialize fields
        assert self.startEditing()
        # standard field names, types, etc.
        fieldDefs = [('oid', QVariant.Int, 'integer'),
                     ('type', QVariant.String, 'string'),
                     ('name', QVariant.String, 'string'),
                     ('path', QVariant.String, 'string'),
                     ]
        # initialize fields
        for fieldDef in fieldDefs:
            field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
            self.addAttribute(field)
        self.commitChanges()

        symbol = QgsFillSymbolV2.createSimple({'style': 'no', 'color': 'red', 'outline_color':'black'})
        self.rendererV2().setSymbol(symbol)
        self.label().setFields(self.fields())
        self.label().setLabelField(3,3)
        self.mVRTRaster.sigSourceRasterAdded.connect(self.onRasterInserted)
        self.mVRTRaster.sigSourceRasterRemoved.connect(self.onRasterRemoved)
        self.onRasterInserted(self.mVRTRaster.sourceRaster())


    def onRasterInserted(self, listOfNewFiles):
        assert isinstance(listOfNewFiles, list)
        if len(listOfNewFiles) == 0:
            return

        for f in listOfNewFiles:
            bounds = self.mVRTRaster.sourceRasterBounds()[f]
            assert isinstance(bounds, RasterBounds)
            oid = str(id(bounds))
            geometry =QgsPolygonV2(bounds.polygon)
            #geometry = QgsCircularStringV2(bounds.curve)
            trans = QgsCoordinateTransform(bounds.crs, self.crs())
            geometry.transform(trans)




            feature = QgsFeature(self.pendingFields())
            #feature.setGeometry(QgsGeometry(geometry))
            feature.setGeometry(QgsGeometry.fromWkt(geometry.asWkt()))
            #feature.setFeatureId(int(oid))
            feature.setAttribute('oid', oid)
            feature.setAttribute('type', 'source file')
            feature.setAttribute('name', str(os.path.basename(f)))
            feature.setAttribute('path', str(f))
            #feature.setValid(True)
            self.startEditing()
            assert self.dataProvider().addFeatures([feature])
            assert self.commitChanges()
            self.updateExtents()


    def onRasterRemoved(self, files):

        self.startEditing()
        self.selectAll()
        toRemove = []
        for f in self.selectedFeatures():
            if f.attribute('path') in files:
                toRemove.append(f.id())
        self.setSelectedFeatures(toRemove)
        self.deleteSelectedFeatures()
        self.commitChanges()
        s = ""


    def spectralLibrary(self):
        return self.mVRTRaster

    def nSpectra(self):
        return len(self.mVRTRaster)



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


from timeseriesviewer.utils import loadUi

class TreeNode(QObject):
    sigWillAddChildren = pyqtSignal(QObject, int, int)
    sigAddedChildren = pyqtSignal(QObject, int, int)
    sigWillRemoveChildren = pyqtSignal(QObject, int, int)
    sigRemovedChildren = pyqtSignal(QObject, int, int)
    sigUpdated = pyqtSignal(QObject)

    def __init__(self, parentNode, name=None):
        super(TreeNode, self).__init__()
        self.mParent = parentNode

        self.mChildren = []
        self.mName = name
        self.mValues = []
        self.mIcon = None
        self.mToolTip = None


        if isinstance(parentNode, TreeNode):
            parentNode.appendChildNodes(self)

    def detach(self):
        """
        Detaches this TreeNode from its parent TreeNode
        :return:
        """
        if isinstance(self.mParent, TreeNode):
            self.mParent.mChildren.remove(self)
            self.setParentNode(None)

    def appendChildNodes(self, listOfChildNodes):
        self.insertChildNodes(len(self.mChildren), listOfChildNodes)

    def insertChildNodes(self, index, listOfChildNodes):
        assert index <= len(self.mChildren)
        if isinstance(listOfChildNodes, TreeNode):
            listOfChildNodes = [listOfChildNodes]
        assert isinstance(listOfChildNodes, list)
        l = len(listOfChildNodes)
        idxLast = index+l-1
        self.sigWillAddChildren.emit(self, index, idxLast)
        for i, node in enumerate(listOfChildNodes):
            assert isinstance(node, TreeNode)
            node.mParent = self
            # connect node signals
            node.sigWillAddChildren.connect(self.sigWillAddChildren)
            node.sigAddedChildren.connect(self.sigAddedChildren)
            node.sigWillRemoveChildren.connect(self.sigWillRemoveChildren)
            node.sigRemovedChildren.connect(self.sigRemovedChildren)
            node.sigUpdated.connect(self.sigUpdated)

            self.mChildren.insert(index+i, node)

        self.sigAddedChildren.emit(self, index, idxLast)

    def removeChildNode(self, node):
        assert node in self.mChildren
        i = self.mChildren.index(node)
        self.removeChildNodes(i, 1)

    def removeChildNodes(self, row, count):

        if row < 0 or count <= 0:
            return False

        rowLast = row + count - 1

        if rowLast >= self.childCount():
            return False

        self.sigWillRemoveChildren.emit(self, row, rowLast)
        to_remove = self.childNodes()[row:rowLast+1]
        for n in to_remove:
            self.mChildren.remove(n)
            #n.mParent = None

        self.sigRemovedChildren.emit(self, row, rowLast)



    def setToolTip(self, toolTip):
        self.mToolTip = toolTip
    def toolTip(self):
        return self.mToolTip

    def parentNode(self):
        return self.mParent

    def setParentNode(self, treeNode):
        assert isinstance(treeNode, TreeNode)
        self.mParent = treeNode

    def setIcon(self, icon):
        self.mIcon = icon

    def icon(self):
        return self.mIcon

    def setName(self, name):
        self.mName = name

    def name(self):
        return self.mName

    def contextMenu(self):
        return None


    def setValues(self, listOfValues):
        if not isinstance(listOfValues, list):
            listOfValues = [listOfValues]
        self.mValues = listOfValues[:]
    def values(self):
        return self.mValues[:]

    def childCount(self):
        return len(self.mChildren)

    def childNodes(self):
        return self.mChildren[:]

class SourceRasterFileNode(TreeNode):

    def __init__(self, parentNode, path):
        super(SourceRasterFileNode, self).__init__(parentNode)

        self.mPath = path
        self.setName(os.path.basename(path))
        self.setValues([path])
        #populate metainfo
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)

        crsNode = TreeNode(self, name='CRS')
        crs = osr.SpatialReference()
        crs.ImportFromWkt(ds.GetProjection())

        authInfo = '{}:{}'.format(crs.GetAttrValue('AUTHORITY',0), crs.GetAttrValue('AUTHORITY',1))
        crsNode.setValues([authInfo,crs.ExportToWkt()])
        self.bandNode = TreeNode(None, name='Bands')
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b+1)

            inputSource = VRTRasterInputSourceBand(path, b)
            inputSource.mBandName = band.GetDescription()
            if inputSource.mBandName in [None,'']:
                inputSource.mBandName = '{}'.format(b + 1)
            inputSource.mNoData = band.GetNoDataValue()

            SourceRasterBandNode(self.bandNode, inputSource)
        self.bandNode.setParentNode(self)
        self.appendChildNodes(self.bandNode)

    def sourceBands(self):
        return [n.mSrcBand for n in self.bandNode.mChildren if isinstance(n, SourceRasterBandNode)]

class SourceRasterBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(SourceRasterBandNode, self).__init__(parentNode)

        self.mSrcBand = vrtRasterInputSourceBand
        self.setName(self.mSrcBand.mBandName)
        #self.setValues([self.mSrcBand.mPath])
        self.setToolTip('band {}:{}'.format(self.mSrcBand.mBandIndex+1, self.mSrcBand.mPath))

class VRTRasterNode(TreeNode):
    def __init__(self, parentNode, vrtRaster):
        assert isinstance(vrtRaster, VRTRaster)

        super(VRTRasterNode, self).__init__(parentNode)
        self.mVRTRaster = vrtRaster
        self.mVRTRaster.sigBandInserted.connect(self.onBandInserted)
        self.mVRTRaster.sigBandRemoved.connect(self.onBandRemoved)

    def onBandInserted(self, index, vrtRasterBand):
        assert isinstance(vrtRasterBand, VRTRasterBand)
        i = vrtRasterBand.bandIndex()
        assert i == index
        node = VRTRasterBandNode(None, vrtRasterBand)
        self.insertChildNodes(i, [node])

    def onBandRemoved(self, removedIdx):
        self.removeChildNodes(removedIdx, 1)


class VRTRasterBandNode(TreeNode):
    def __init__(self, parentNode, virtualBand):
        assert isinstance(virtualBand, VRTRasterBand)

        super(VRTRasterBandNode, self).__init__(parentNode)
        self.mVirtualBand = virtualBand

        self.setName(virtualBand.name())

        #self.nodeBands = TreeNode(self, name='Input Bands')
        #self.nodeBands.setToolTip('Source bands contributing to this virtual raster band')
        self.nodeBands = self
        virtualBand.sigNameChanged.connect(self.setName)
        virtualBand.sigSourceInserted.connect(lambda _, src: self.onSourceInserted(src))
        virtualBand.sigSourceRemoved.connect(self.onSourceRemoved)
        for src in self.mVirtualBand.sources:
            self.onSourceInserted(src)


    def onSourceInserted(self, inputSource):
        assert isinstance(inputSource, VRTRasterInputSourceBand)
        assert inputSource.virtualBand() == self.mVirtualBand
        i = self.mVirtualBand.sources.index(inputSource)

        node = VRTRasterInputSourceBandNode(None, inputSource)
        self.nodeBands.insertChildNodes(i, node)

    def onSourceRemoved(self, row, inputSource):
        assert isinstance(inputSource, VRTRasterInputSourceBand)

        node = self.nodeBands.childNodes()[row]
        if  node.mSrc != inputSource:
            s = ""
        self.nodeBands.removeChildNode(node)




class VRTRasterInputSourceBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(VRTRasterInputSourceBandNode, self).__init__(parentNode)

        self.mSrc = vrtRasterInputSourceBand
        name = '{}:{}'.format(self.mSrc.mBandIndex+1, os.path.basename(self.mSrc.mPath))
        self.setName(name)
        #self.setValues([self.mSrc.mPath, self.mSrc.mBandIndex])

    def sourceBand(self):
        return self.mSrc

class TreeView(QTreeView):

    def __init__(self, *args, **kwds):
        super(TreeView, self).__init__(*args, **kwds)

class TreeModel(QAbstractItemModel):
    def __init__(self, parent=None, rootNode = None):
        super(TreeModel, self).__init__(parent)

        self.mColumnNames = ['Node','Value']
        self.mRootNode = rootNode if isinstance(rootNode, TreeNode) else TreeNode(None)
        self.mRootNode.sigWillAddChildren.connect(self.nodeWillAddChildren)
        self.mRootNode.sigAddedChildren.connect(self.nodeAddedChildren)
        self.mRootNode.sigWillRemoveChildren.connect(self.nodeWillRemoveChildren)
        self.mRootNode.sigRemovedChildren.connect(self.nodeRemovedChildren)
        self.mRootNode.sigUpdated.connect(self.nodeUpdated)

        self.mTreeView = None
        if isinstance(parent, QTreeView):
            self.connectTreeView(parent)

    def nodeWillAddChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginInsertRows(idxNode, idx1, idxL)


    def nodeAddedChildren(self, node, idx1, idxL):
        self.endInsertRows()
        #for i in range(idx1, idxL+1):
        for n in node.childNodes():
            self.setColumnSpan(node)

    def nodeWillRemoveChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginRemoveRows(idxNode, idx1, idxL)

    def nodeRemovedChildren(self, node, idx1, idxL):
        self.endRemoveRows()


    def nodeUpdated(self, node):
        idxNode = self.node2idx(node)
        self.dataChanged.emit(idxNode, idxNode)
        self.setColumnSpan(node)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:

            if len(self.mColumnNames) > section:
                return self.mColumnNames[section]
            else:
                return ''

        else:
            return None

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = self.idx2node(index)
        if not isinstance(node, TreeNode):
            return QModelIndex()

        parentNode = node.parentNode()
        if not isinstance(parentNode, TreeNode):
            return QModelIndex()

        return self.node2idx(parentNode)

        if node not in parentNode.mChildren:
            return QModelIndex
        row = parentNode.mChildren.index(node)
        return self.createIndex(row, 0, parentNode)

    def rowCount(self, index):

        node = self.idx2node(index)
        return len(node.mChildren) if isinstance(node, TreeNode) else 0

    def hasChildren(self, index):
        node = self.idx2node(index)
        return isinstance(node, TreeNode) and len(node.mChildren) > 0

    def columnNames(self):
        return self.mColumnNames

    def columnCount(self, index):

        return len(self.mColumnNames)

    def connectTreeView(self, treeView):
        self.mTreeView = treeView

    def setColumnSpan(self, node):
        if isinstance(self.mTreeView, QTreeView) \
                and isinstance(node, TreeNode) \
                and isinstance(node.parentNode(), TreeNode) :
            idxNode = self.node2idx(node)
            idxParent = self.node2idx(node.parentNode())
            span = len(node.values()) == 0
            self.mTreeView.setFirstColumnSpanned(idxNode.row(), idxParent, span)
            for n in node.childNodes():
                self.setColumnSpan(n)


    def index(self, row, column, parentIndex=None):



        if parentIndex is None:
            parentNode = self.mRootNode
        else:
            parentNode = self.idx2node(parentIndex)

        if row < 0 or row >= parentNode.childCount():
            return QModelIndex()
        if column < 0 or column >= len(self.mColumnNames):
            return QModelIndex()

        if isinstance(parentNode, TreeNode) and row < len(parentNode.mChildren):
            return self.createIndex(row,column,parentNode.mChildren[row])
        else:
            return QModelIndex()

    def findParentNode(self, node, parentNodeType):
        assert isinstance(node, TreeNode)
        while True:
            if isinstance(node, parentNodeType):
                return node
            if not isinstance(node.parentNode(), TreeNode):
                return None
            node = node.parentNode()

    def indexes2nodes(self, indexes):
        assert isinstance(indexes, list)
        nodes = []
        for idx in indexes:
            n = self.idx2node(idx)
            if n not in nodes:
                nodes.append(n)
        return nodes

    def idx2node(self, index):
        if not index.isValid():
            return self.mRootNode
        else:
            return index.internalPointer()

    def node2idx(self, node):
        assert isinstance(node, TreeNode)
        if node == self.mRootNode:
            return QModelIndex()
        else:
            parentNode = node.parentNode()
            assert isinstance(parentNode, TreeNode)
            if node not in parentNode.mChildren:
                return QModelIndex()
            r = parentNode.mChildren.index(node)
            return self.createIndex(r,0,node)


    def data(self, index, role):
        node = self.idx2node(index)
        col = index.column()
        if role == Qt.UserRole:
            return node

        if col == 0:
            if role in [Qt.DisplayRole, Qt.EditRole]:
                return node.name()
            if role == Qt.DecorationRole:
                return node.icon()
            if role == Qt.ToolTipRole:
                return node.toolTip()
        if col > 0:
            i = col-1

            if role in [Qt.DisplayRole, Qt.EditRole] and len(node.values())>i:
                return node.values()[i]

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        node = self.idx2node(index)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class RasterBounds(object):
    def __init__(self, path):
        self.path = None
        self.polygon = None
        self.curve = None
        self.crs = None

        if path is not None:
            self.fromImage(path)

    def fromRectangle(self, crs, rectangle):
        assert isinstance(rectangle, QgsRectangle)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.crs = crs
        self.path = ''
        s = ""


    def fromImage(self, path):
        self.path = path
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        gt = ds.GetGeoTransform()
        bounds = [px2geo(QPoint(0, 0), gt),
                  px2geo(QPoint(ds.RasterXSize, 0), gt),
                  px2geo(QPoint(ds.RasterXSize, ds.RasterYSize), gt),
                  px2geo(QPoint(0, ds.RasterYSize), gt)]
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for p in bounds:
            assert isinstance(p, QgsPoint)
            ring.AddPoint(p.x(), p.y())

        curve = ogr.Geometry(ogr.wkbLinearRing)
        curve.AddGeometry(ring)
        self.curve = QgsCircularStringV2()
        self.curve.fromWkt(curve.ExportToWkt())

        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)
        self.polygon = QgsPolygonV2()
        self.polygon.fromWkt(polygon.ExportToWkt())
        self.polygon.exteriorRing().close()
        assert self.polygon.exteriorRing().isClosed()

        self.crs = crs

    def __repr__(self):
        return self.polygon.ExportToWkt()

class SourceRasterModel(TreeModel):
    def __init__(self, parent=None):
        super(SourceRasterModel, self).__init__(parent)

        self.mColumnNames = ['File', 'Value']


    def files(self):
        return [n.mPath for n in self.mRootNode.childNodes() if isinstance(n, SourceRasterFileNode)]

    def addFile(self, file):
        self.addFiles([file])


    def addFiles(self, newFiles):
        assert isinstance(newFiles, list)
        existingFiles = self.files()
        newFiles = [os.path.normpath(f) for f in newFiles]
        newFiles = [f for f in newFiles if f not in existingFiles and isinstance(gdal.Open(f), gdal.Dataset)]
        if len(newFiles) > 0:
            for f in newFiles:
                SourceRasterFileNode(self.mRootNode, f)


    def file2node(self, file):
        for node in self.mRootNode.childNodes():
            if isinstance(node, SourceRasterFileNode) and node.mPath == file:
                return node
        return None

    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

        toRemove = [n for n in self.mRootNode.childNodes() \
            if isinstance(n, SourceRasterFileNode) and n.mPath in listOfFiles]

        for n in toRemove:
            n.parentNode().removeChildNode(n)


    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        node = self.idx2node(index)

        flags = super(SourceRasterModel, self).flags(index)
        #return flags
        if isinstance(node, SourceRasterFileNode) or \
            isinstance(node, SourceRasterBandNode):
            flags |= Qt.ItemIsDragEnabled
        return flags

    def contextMenu(self):

        return None

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        return types


    def mimeData(self, indexes):
        indexes = sorted(indexes)
        if len(indexes) == 0:
            return None
        nodes = []
        for i in indexes:
            n = self.idx2node(i)
            if n not in nodes:
                nodes.append(n)


        sourceBands = []

        for node in nodes:
            if isinstance(node, SourceRasterFileNode):
                sourceBands.extend(node.sourceBands())
            if isinstance(node, SourceRasterBandNode):
                sourceBands.append(node.mSrcBand)

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mPath for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData('hub.vrtbuilder/bandlist', pickle.dumps(sourceBands))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            #mimeData.setText('\n'.join(uriList))
        return mimeData



class VRTRasterTreeModel(TreeModel):
    def __init__(self, parent=None, vrtRaster=None):

        vrtRaster = vrtRaster if isinstance(vrtRaster, VRTRaster) else VRTRaster()
        rootNode = VRTRasterNode(None, vrtRaster)
        super(VRTRasterTreeModel, self).__init__(parent, rootNode=rootNode)
        self.mVRTRaster = vrtRaster
        self.mColumnNames = ['Virtual Raster']

    def setData(self, index, value, role):
        node = self.idx2node(index)
        col = index.column()

        if role == Qt.EditRole:
            if isinstance(node, VRTRasterBandNode) and col == 0:
                if len(value) > 0:
                    node.setName(value)
                    return True


        return False

    def removeNodes(self, nodes):

        for vBandNode in [n for n in nodes if isinstance(n, VRTRasterBandNode)]:
            self.mVRTRaster.removeVirtualBand(vBandNode.mVirtualBand)

        for vBandSrcNode in [n for n in nodes if isinstance(n, VRTRasterInputSourceBandNode)]:
            assert isinstance(vBandSrcNode, VRTRasterInputSourceBandNode)
            srcBand = vBandSrcNode.mSrc

            srcBand.virtualBand().removeSource(srcBand)


    def removeRows(self, row, count, parent):
        parentNode = self.idx2node(parent)


        if isinstance(parentNode, VRTRasterBandNode):
            #self.beginRemoveRows(parent, row, row+count-1)
            vBand = parentNode.mVirtualBand
            for n in parentNode.childNodes()[row:row+count]:
                vBand.removeSource(n.mSrc)
            #self.endRemoveRows()
            return True
        else:
            return False


    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        node = self.idx2node(index)
        flags = super(VRTRasterTreeModel, self).flags(index)

        if isinstance(node, VRTRasterBandNode):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsEditable
        if isinstance(node, VRTRasterInputSourceBandNode):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsDragEnabled
        return flags

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            event.accept()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)

        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            parent = self.mRootNode
            p = self.node2idx(parent)
            self.dropMimeData(event.mimeData(), event.dropAction(),0,0,p )


            event.accept()

        s = ""


    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        types.append('hub.vrtbuilder/bandlist')
        return types


    def mimeData(self, indexes):
        indexes = sorted(indexes)
        nodes = [self.idx2node(i) for i in indexes]

        sourceBands = []

        for node in nodes:
            if isinstance(node, VRTRasterInputSourceBandNode):
                sourceBand = node.sourceBand()
                assert isinstance(sourceBand, VRTRasterInputSourceBand)
                sourceBands.append(sourceBand)

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mPath for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData('hub.vrtbuilder/bandlist', pickle.dumps(sourceBands))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            mimeData.setText('\n'.join(uriList))

        return mimeData



    def dropMimeData(self, mimeData, action, row, column, parentIndex):
        if action == Qt.IgnoreAction:
            return True

        assert isinstance(mimeData, QMimeData)
        #assert isinstance(action, QDropEvent)
        sourceBands = []

        if u'hub.vrtbuilder/bandlist' in mimeData.formats():
            dump = mimeData.data(u'hub.vrtbuilder/bandlist')
            sourceBands = pickle.loads(dump)

        if u'hub.vrtbuilder/vrt.indices' in mimeData.formats():
            dump = mimeData.data(u'hub.vrtbuilder/vrt.indices')
            indices = pickle.loads(dump)
            s = ""

            if action == Qt.MoveAction:
                s = ""

        if len(sourceBands) == 0:
            return False
        parentNode = self.idx2node(parentIndex)
        if isinstance(parentNode,VRTRasterNode):
            #add VRT band per band
            for sourceBand in sourceBands:
                assert isinstance(sourceBand, VRTRasterInputSourceBand)
                vBand = VRTRasterBand()
                vBand.addSource(sourceBand)
                self.mVRTRaster.addVirtualBand(vBand)
            return True

        if isinstance(parentNode, VRTRasterInputSourceBandNode):
            #insert after this node
            row = parentNode.parentNode().mChildren.index(parentNode)+1
            parentNode = parentNode.parentNode()

        if isinstance(parentNode, VRTRasterBandNode):
            vBand = parentNode.mVirtualBand
            assert isinstance(vBand, VRTRasterBand)
            if row < 0:
                row = 0
            for sourceBand in sourceBands:
                vBand.insertSource(row, sourceBand)
                row += 1
            return True


            s = ""
        return False

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

class VRTBuilderWidget(QFrame, loadUi('vrtbuilder.ui')):

    def __init__(self, parent=None):
        super(VRTBuilderWidget, self).__init__(parent)
        self.setupUi(self)
        self.sourceFileModel = SourceRasterModel(parent=self.treeViewSourceFiles)

        self.treeViewSourceFiles.setModel(self.sourceFileModel)
        self.treeViewSourceFiles.selectionModel().selectionChanged.connect(self.onSrcModelSelectionChanged)

        self.mCrsManuallySet = False
        self.mBoundsManuallySet = False

        self.tbNoData.setValidator(QDoubleValidator())

        self.tbOutputPath.textChanged.connect(self.onOutputPathChanged)

        filter='GDAL Virtual Raster (*.vrt);;GeoTIFF (*.tiff *.tif);;ENVI (*.bsq *.bil *.bip)'
        self.btnSelectVRTPath.clicked.connect(lambda :
                                              self.tbOutputPath.setText(
                                                  QFileDialog.getSaveFileName(self,
                                                                              directory=self.tbOutputPath.text(),
                                                                              caption='Select output image',
                                                                              filter=filter)
                                              ))
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.saveFile)
        self.vrtRaster = VRTRaster()
        self.vrtRasterLayer = VRTRasterVectorLayer(self.vrtRaster)
        QgsMapLayerRegistry.instance().addMapLayer(self.vrtRasterLayer)

        assert isinstance(self.previewMap, QgsMapCanvas)
        self.previewMap.setLayerSet([QgsMapCanvasLayer(self.vrtRasterLayer)])
        self.previewMap.contextMenuEvent = self.mapCanvasContextMenuEvent

        self.previewMapTool = QgsMapToolEmitPoint(self.previewMap)
        self.previewMapTool.canvasClicked.connect(self.onMapFeatureIdentified)

        self.previewMap.setMapTool(self.previewMapTool)

        self.vrtRaster.sigCrsChanged.connect(self.updateSummary)
        self.vrtRaster.sigSourceBandInserted.connect(self.updateSummary)
        self.vrtRaster.sigSourceBandRemoved.connect(self.updateSummary)

        self.vrtRaster.sigBandInserted.connect(self.updateSummary)
        self.vrtRaster.sigBandRemoved.connect(self.updateSummary)

        self.vrtRaster.sigSourceRasterAdded.connect(self.mapRefresh)
        self.vrtBuilderModel = VRTRasterTreeModel(parent=self.treeViewVRT, vrtRaster=self.vrtRaster)
        self.treeViewVRT.setModel(self.vrtBuilderModel)
        self.treeViewVRT.selectionModel().selectionChanged.connect(self.onVRTModelSelectionChanged)
        #self.vrtBuilderModel.redirectDropEvent(self.treeViewVRT)
        #self.treeViewVRT.dragEnterEvent = self.vrtBuilderModel.dragEnterEvent
        #self.treeViewVRT.dragMoveEvent = self.vrtBuilderModel.dragMoveEvent



        self.treeViewVRT.setAutoExpandDelay(50)
        self.treeViewVRT.setDragEnabled(True)
        self.treeViewVRT.contextMenuEvent = self.vrtTreeViewContextMenuEvent


        self.btnExpandAllVRT.clicked.connect(lambda :self.expandNodes(self.treeViewVRT, True))
        self.btnCollapseAllVRT.clicked.connect(lambda: self.expandNodes(self.treeViewVRT, False))

        self.btnExpandAllSrc.clicked.connect(lambda :self.expandNodes(self.treeViewSourceFiles, True))
        self.btnCollapseAllSrc.clicked.connect(lambda: self.expandNodes(self.treeViewSourceFiles, False))

        self.btnAddVirtualBand.clicked.connect(lambda : self.vrtRaster.addVirtualBand(VRTRasterBand(name='Band {}'.format(len(self.vrtRaster)+1))))
        self.btnRemoveVirtualBands.clicked.connect(lambda : self.vrtBuilderModel.removeNodes(
                                                   self.vrtBuilderModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
                                                    )
                                                   )
        self.btnAddFromRegistry.clicked.connect(self.loadSrcFromMapLayerRegistry)
        self.btnAddSrcFiles.clicked.connect(lambda :
                                            self.sourceFileModel.addFiles(
                                                QFileDialog.getOpenFileNames(self, "Open raster images",
                                                                            directory='')
                                            ))

        self.btnRemoveSrcFiles.clicked.connect(lambda : self.sourceFileModel.removeFiles(
            [n.mPath for n in self.selectedSourceFileNodes()]
        ))

        self.mQgsProjectionSelectionWidget.dialog().setMessage('Set VRT CRS')
        self.mQgsProjectionSelectionWidget.crsChanged.connect(self.vrtRaster.setCrs)

    @pyqtSlot(QgsFeature)
    def onMapFeatureIdentified(self, point, button):
        assert isinstance(point, QgsPoint)
        if self.sender() == self.previewMapTool:
            searchRadius = (QgsTolerance.toleranceInMapUnits(5, self.vrtRasterLayer,
                                    self.previewMap.mapRenderer(), QgsTolerance.Pixels))
            if button == Qt.LeftButton:
                rect = QgsRectangle()
                lyr = self.vrtRasterLayer
                lyr.setSelectedFeatures([])
                rect.setXMinimum(point.x() - searchRadius);
                rect.setXMaximum(point.x() + searchRadius);
                rect.setYMinimum(point.y() - searchRadius);
                rect.setYMaximum(point.y() + searchRadius);
                lyr.select(rect, True)
                #for feature in lyr.selectedFeatures():
            # do something with the feature

            #id = qgsFeature.id()
           # self.vrtRasterLayer.setSelectedFeatures([id])
        f = ""

    def loadSrcFromMapLayerRegistry(self):

        reg = QgsMapLayerRegistry.instance()
        for lyr in reg.mapLayers().values():
            if isinstance(lyr, QgsRasterLayer):
                self.sourceFileModel.addFile(lyr.source())


    def expandNodes(self, treeView, expand):
        assert isinstance(treeView, QTreeView)

        indices = treeView.selectedIndexes()
        if len(indices) == 0:
            treeView.selectAll()
            indices += treeView.selectedIndexes()
            treeView.clearSelection()
        for idx in indices:
            treeView.setExpanded(idx, expand)


    def onVRTModelSelectionChanged(self, selected, deselected):

        self.btnRemoveVirtualBands.setEnabled(selected.count() > 0)

        self.vrtRasterLayer.setSelectedFeatures([])

    def selectedSourceFileNodes(self):

        indexes =  self.treeViewSourceFiles.selectionModel().selectedIndexes()
        selectedFileNodes = [self.sourceFileModel.idx2node(idx) for idx in indexes]
        return [n for n in selectedFileNodes if isinstance(n, SourceRasterFileNode)]

    def setSelectedSourceFiles(self, sourceFiles):

        pass

    def saveFile(self):
        path = self.tbOutputPath.text()
        ext = os.path.splitext(path)[-1]

        saveBinary = ext != '.vrt'
        if saveBinary:
            pathVrt = path+'.vrt'
        else:
            pathVrt = path


        self.vrtRaster.saveVRT(pathVrt)


    def onOutputPathChanged(self, path):
        assert isinstance(self.buttonBox, QDialogButtonBox)
        isEnabled = False
        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            isEnabled = ext in ['.vrt', '.bsq', '.tif', '.tiff']

        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(isEnabled)


    def onSrcModelSelectionChanged(self, selected, deselected):

        self.btnRemoveSrcFiles.setEnabled(len(self.selectedSourceFileNodes()) > 0)
        s = ""


    def addSourceFiles(self, files):
        """
        Adds a list of source files to the source file list.
        :param files: list-of-file-paths
        """
        self.sourceFileModel.addFiles(files)

    def updateSummary(self):


        self.tbSourceFileCount.setText('{}'.format(len(self.vrtRaster.sourceRaster())))
        self.tbVRTBandCount.setText('{}'.format(len(self.vrtRaster)))

        crs = self.vrtRaster.crs()
        if isinstance(crs, QgsCoordinateReferenceSystem):
            self.previewMap.setDestinationCrs(crs)
            if crs != self.mQgsProjectionSelectionWidget.crs():
                self.mQgsProjectionSelectionWidget.setCrs(crs)
        self.mapRefresh()

    def mapCanvasContextMenuEvent(self, event):
        menu = QMenu()
        action = menu.addAction('Refresh')
        action.triggered.connect(self.previewMap.refresh)

        action = menu.addAction('Reset')
        action.triggered.connect(self.mapReset)

        menu.exec_(event.globalPos())


    def vrtTreeViewContextMenuEvent(self, event):

        idx = self.treeViewVRT.indexAt(event.pos())
        if not idx.isValid():
            pass

        nodes = self.vrtBuilderModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        menu = QMenu(self.treeViewVRT)
        a = menu.addAction('Remove')
        a.triggered.connect(lambda: self.vrtBuilderModel.removeNodes(nodes))

        a = menu.addAction('Move map to')

        menu.exec_(self.treeViewVRT.viewport().mapToGlobal(event.pos()))
        """
        if (menu & & menu->actions().count() != 0 )
        menu->exec (mapToGlobal(event->pos() ) );
        delete
        menu;
        """

    def mapReset(self):

        self.mapRefresh()
        self.vrtRasterLayer.setSelectedFeatures([])

    def mapRefresh(self):
        extent = self.vrtRasterLayer.extent()
        if isinstance(extent, QgsRectangle):
            extent.scale(1.05)
            self.previewMap.setExtent(extent)
            self.previewMap.refresh()


        s = ""
if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import utils, DIR_EXAMPLES
    qgsApp = utils.initQgisApplication()

    from example.Images import Img_2014_03_20_LC82270652014079LGN00_BOA, re_2014_08_17

    #r = VRTRaster()
    #r.addFilesAsStack([Img_2014_03_20_LC82270652014079LGN00_BOA, Img_2014_04_29_LE72270652014119CUB00_BOA])
    #print(r.sourceRasterBounds())
    if False:
        drv = gdal.GetDriverByName('MEM')
        ds = drv.Create('', 50, 100, 0, gdal.GDT_Byte)
        from osgeo import gdal_array
        assert isinstance(ds, gdal.Dataset)

        import numpy as np
        data = np.ones((100,50), dtype=np.byte)
        dPt = data.__array_interface__['data']

        ns, nl, nb = ds.RasterXSize, ds.RasterYSize, ds.RasterCount
        #path = 'MEM:::DATAPOINTER={dPt},PIXELS={ns},LINES={nl},BANDS={nb},DATATYPE={dt},PIXELOFFSET=1,LINEOFFSET=300,BANDOFFSET=1'.format(
        #    dPt=dPt, ns=ns, nl=nl, nb=nb, dt=dt)
        ds.AddBand(gdal.GDT_Byte)
        band = ds.GetRasterBand(1)
        band.WriteArray(data)

        arr2 = band.ReadAsArray()
        dPt2 = arr2.__array_interface__['data']

        s = ""
        #ds2= gdal.Open(path, gdal.GA_ReadOnly)
        band2 = ds2.GetRasterBand(1)
        data = band2.ReadAsArray()
        s = ""

    w = VRTBuilderWidget()
    p1 = r'S:/temp/temp_ar/4benjamin/05_CBERS/CBERS_4_MUX_20150603_167_107_L4_BAND5_GRID_SURFACE.tif'
    p2 = r'D:/Repositories/QGIS_Plugins/hub-timeseriesviewer/example/Images/re_2014-06-25.tif'
    p3 = r'D:/Repositories/QGIS_Plugins/hub-timeseriesviewer/example/Images/2014-08-27_LC82270652014239LGN00_BOA.tif'
    w.addSourceFiles([p1, p2, p3])
    w.vrtRaster.addFilesAsStack([p1, p2, p3])

    w.show()
    pathTmp = os.path.join(DIR_EXAMPLES, 'test.vrt')
    w.vrtRaster.saveVRT(pathTmp)
    # w.vrtBuilder.addVirtualBand(VRTRasterBand(name='Band 1'))

    qgsApp.exec_()
    qgsApp.exitQgis()
