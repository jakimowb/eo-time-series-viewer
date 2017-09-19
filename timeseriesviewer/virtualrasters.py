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
import os, sys, re, pickle
import tempfile
from osgeo import gdal
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from timeseriesviewer import file_search

class VirtualBandInputSource(object):
    def __init__(self, path, bandIndex):
        self.path = os.path.normpath(path)
        self.bandIndex = bandIndex
        self.noData = None
        self.mVirtualBand = None

    def __eq__(self, other):
        if isinstance(other, VirtualBandInputSource):
            return self.path == other.path and self.bandIndex == other.bandIndex
        else:
            return False

    def virtualBand(self):
        return self.mVirtualBand


class VirtualBand(QObject):

    def __init__(self, name='', parent=None):
        super(VirtualBand, self).__init__(parent)
        self.sources = []
        self.mName = name
        self.mVRT = None

    sigNameChanged = pyqtSignal(str)
    def setName(self, name):
        oldName = self.mName
        self.mName = name
        if oldName != self.mName:
            self.sigNameChanged.emit(name)

    def name(self):
        return self.mName


    def addSourceBand(self, path, bandIndex):
        vBand = VirtualBandInputSource(path, bandIndex)
        return self.insertSourceBand(len(self.sources), vBand)

    sigSourceBandInserted = pyqtSignal(VirtualBandInputSource)
    def insertSourceBand(self, index, virtualBandInputSource):
        assert isinstance(virtualBandInputSource, VirtualBandInputSource)
        virtualBandInputSource.mVirtualBand = self
        assert index <= len(self.sources)
        self.sources.insert(index, virtualBandInputSource)
        self.sigSourceBandInserted.emit(virtualBandInputSource)

    def bandIndex(self):
        if isinstance(self.mVRT, VirtualRasterBuilder):
            return self.mVRT.vBands.index(self)
        else:
            return None

    sigSourceBandRemoved = pyqtSignal(int, VirtualBandInputSource)
    def removeSourceBand(self, bandOrIndex):
        """
        Removes a virtual band
        :param bandOrIndex: int | VirtualBand
        :return: The VirtualBand that was removed
        """
        if not isinstance(bandOrIndex, VirtualBand):
            bandOrIndex = self.sources[bandOrIndex]
        i = self.sources.index(bandOrIndex)
        self.sources.remove(bandOrIndex)
        self.sigSourceBandRemoved.emit(i, bandOrIndex)
        return bandOrIndex

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



class VirtualRasterBuilder(QObject):

    def __init__(self, parent=None):
        super(VirtualRasterBuilder, self).__init__(parent)
        self.vBands = []
        self.vMetadata = dict()


    def addVirtualBand(self, virtualBand):
        """
        Adds a virtual band
        :param virtualBand: the VirtualBand to be added
        :return: VirtualBand
        """
        assert isinstance(virtualBand, VirtualBand)
        return self.insertVirtualBand(len(self), virtualBand)



    def insertSourceBand(self, virtualBandIndex, pathSource, sourceBandIndex):
        """
        Inserts a source band into the VRT stack
        :param virtualBandIndex: target virtual band index
        :param pathSource: path of source file
        :param sourceBandIndex: source file band index
        """

        while virtualBandIndex > len(self.vBands)-1:
            self.insertVirtualBand(len(self.vBands), VirtualBand())

        vBand = self.vBands[virtualBandIndex]
        vBand.addSourceBand(pathSource, sourceBandIndex)

    sigSourceAdded = pyqtSignal(VirtualBand, VirtualBandInputSource)
    sigBandAdded = pyqtSignal(VirtualBand)
    def insertVirtualBand(self, i, virtualBand):
        """
        Inserts a VirtualBand
        :param i: the insert position
        :param virtualBand: the VirtualBand to be inserted
        :return: the VirtualBand
        """
        assert isinstance(virtualBand, VirtualBand)
        assert i <= len(self.vBands)
        virtualBand.mVRT = self
        virtualBand.sigSourceBandInserted.connect(lambda sourceBand: self.sigSourceAdded(virtualBand, VirtualBandInputSource))
        self.vBands.insert(i, virtualBand)
        self.sigBandAdded.emit(virtualBand)

        return self[i]


    sigBandsRemoved = pyqtSignal(list)
    def removeVirtualBands(self, bandsOrIndices):
        assert isinstance(bandsOrIndices, list)
        to_remove = []
        for bandOrIndex in bandsOrIndices:
            if not isinstance(bandOrIndex, VirtualBand):
                bandOrIndex = self.vBands[bandOrIndex]
            to_remove.append(bandOrIndex)

        for band in to_remove:
            self.vBands.remove(band)

        self.sigBandsRemoved.emit(to_remove)
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


from timeseriesviewer.utils import loadUi

class TreeNode(QObject):

    def __init__(self, parentNode):
        super(TreeNode, self).__init__()
        self.mParent = parentNode
        if isinstance(parentNode, TreeNode):
            parentNode.mChildren.append(self)
        self.mChildren = []
        self.mName = None
        self.mValues = []
        self.mIcon = None
        self.mToolTip = None

    def setToolTip(self, toolTip):
        self.mToolTip = toolTip
    def toolTip(self):
        return self.mToolTip

    def parent(self):
        return self.mParent

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


class SourceRasterFileNode(TreeNode):

    def __init__(self, parentNode, path):
        super(SourceRasterFileNode, self).__init__(parentNode)

        self.mPath = path
        self.setName(os.path.basename(path))
        self.setValues([path])
        #populate metainfo
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b+1)
            bandNode = SourceRasterBandNode(self, b)
            bandNode.setName('Band {}'.format(b+1))
            bandNode.setValues([band.GetDescription()])


class SourceRasterBandNode(TreeNode):
    def __init__(self, parentNode, bandIndex):
        assert isinstance(parentNode, SourceRasterFileNode)
        super(SourceRasterBandNode, self).__init__(parentNode)

        self.mBandIndex = bandIndex

class VirtualBandNode(TreeNode):
    def __init__(self, parentNode, virtualBand):
        assert isinstance(virtualBand, VirtualBand)
        assert isinstance(parentNode, TreeNode) and parentNode.parent() == None
        super(VirtualBandNode, self).__init__(parentNode)
        self.mVirtualBand = virtualBand

        self.setName(virtualBand.name())



        virtualBand.sigNameChanged.connect(self.setName)

    def onSourceAdded(self, inputSource):
        assert isinstance(inputSource, VirtualBandInputSource)
        assert inputSource.virtualBand() == self.mVirtualBand
        i = self.mVirtualBand.sources.index(inputSource)
        node = TreeNode(None)
        node.setName(os.path.basename(inputSource.path))
        node.setValues([inputSource.path])
        self.mChildren.insert(i, node)

    def onSourceRemoved(self, inputSource):
        to_remove = [n for n in self.mChildren if inputSource.path in n.values()]
        for n in to_remove:
            self.mChildren.remove(n)


class TreeModelBase(QAbstractItemModel):
    def __init__(self, parent=None):
        super(TreeModelBase, self).__init__(parent)

        self.mColumnNames = ['Node','Value']
        self.mRootNode = TreeNode(None)

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
        node = index.internalPointer()
        parentNode = node.parent()
        if parentNode is None:
            return QModelIndex()
        else:
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


    def index(self, row, column, parentIndex=None):

        if parentIndex is None:
            parentNode = self.mRootNode
        else:
            parentNode = self.idx2node(parentIndex)
        if isinstance(parentNode, TreeNode) and row < len(parentNode.mChildren):
            return self.createIndex(row,column,parentNode.mChildren[row])
        else:
            return QModelIndex()



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
            parentNode = node.parent()
            assert isinstance(parentNode, TreeNode)
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

class VRTRasterSourceModel(TreeModelBase):
    def __init__(self, parent=None):
        super(VRTRasterSourceModel, self).__init__(parent)

        self.mFiles = []
        self.mColumnNames = ['File', 'Value']

    def addFile(self, file):
        self.addFiles([file])


    def addFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)
        listOfFiles = [os.path.normpath(f) for f in listOfFiles]
        listOfFiles = [f for f in listOfFiles if f not in self.mFiles and isinstance(gdal.Open(f), gdal.Dataset)]
        if len(listOfFiles) > 0:
            rootNode = self.mRootNode
            rootIndex = self.node2idx(rootNode)
            r0 = rootNode.childCount()

            self.beginInsertRows(rootIndex, r0,  r0+len(listOfFiles) )
            for f in listOfFiles:
                SourceRasterFileNode(self.mRootNode, f)
            self.endInsertRows()


    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        node = self.idx2node(index)

        flags = super(VRTRasterSourceModel, self).flags(index)
        #return flags
        if isinstance(node, SourceRasterFileNode) or \
            isinstance(node, SourceRasterBandNode):
            flags |= Qt.ItemIsDragEnabled
        return flags

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


        bandNodes = []

        for node in nodes:
            if isinstance(node, SourceRasterFileNode):
                for n in [n for n in node.mChildren if isinstance(n, SourceRasterBandNode)]:
                    if n not in bandNodes:
                        bandNodes.append(n)
            if isinstance(node, SourceRasterBandNode):
                if node not in bandNodes:
                    bandNodes.append(node)

        fileNodes = []
        for n in bandNodes:
            fileNode = n.parent()
            assert isinstance(fileNode, SourceRasterFileNode)
            if fileNode not in fileNodes:
                fileNodes.append(fileNode)

        uriList = [n.mPath for n in fileNodes]
        bandList = [(n.parent().mPath, n.mBandIndex) for n in bandNodes]

        mimeData = QMimeData()

        if len(bandList) > 0:
            mimeData.setData('hub.vrtbuilder/bandlist', pickle.dumps(bandList))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            mimeData.setText('\n'.join(uriList))
        return mimeData



class VRTModel(TreeModelBase):
    def __init__(self, parent=None, vrtBuilder=None):
        super(VRTModel, self).__init__(parent)

        if vrtBuilder is None:
            vrtBuilder = VirtualRasterBuilder()
        else:
            assert isinstance(vrtBuilder, VirtualRasterBuilder)
        self.mVRTBuilder = vrtBuilder
        self.mVRTBuilder.sigBandAdded.connect(self.onBandAdded)
        self.mVRTBuilder.sigSourceAdded.connect(self.onSourceAdded)


    def vBand2vBandNode(self, virtualBand):
        assert isinstance(virtualBand, VirtualBand)
        row = self.mVRTBuilder.vBands.index(virtualBand)
        return self.mRootNode.mChildren[row]

    def onSourceAdded(self, virtualBand, inputSource):
        assert isinstance(virtualBand, VirtualBand)
        assert isinstance(inputSource, VirtualBandInputSource)
        vBandNode = self.vBand2vBandNode(virtualBand)
        assert isinstance(vBandNode, VirtualBandNode)
        idx = self.node2idx(vBandNode)
        row = virtualBand.bandIndex()
        self.beginInsertRows(idx, row, row)
        node = TreeNode(None)
        node.setName(os.path.basename(inputSource.path))
        node.setValues([inputSource.path])
        vBandNode.mChildren.insert(row, node)
        self.endInsertRows()

    def onBandAdded(self, virtualBand):
        assert isinstance(virtualBand, VirtualBand)

        i = virtualBand.bandIndex()
        rootNode = self.mRootNode
        rootIdx = self.node2idx(self.mRootNode)
        self.beginInsertRows(rootIdx, i, i)
        vBandNode = VirtualBandNode(self.mRootNode, virtualBand)

        #self.mRootNode.mChildren.insert(i, vBandNode)
        self.endInsertRows()

        virtualBand.sigSourceBandInserted.connect(self.onSourceBandInserted)
        for inputSource in virtualBand.sources:
            self.onSourceBandInserted(inputSource)

    def onSourceBandInserted(self, sourceBand):
        assert isinstance(sourceBand, VirtualBandInputSource)

        vBand = sourceBand.virtualBand()
        assert isinstance(vBand, VirtualBand)
        VRT = vBand.mVRT
        assert isinstance(VRT, VirtualRasterBuilder)

        i = vBand.sources.index(sourceBand)

        idxParent = self.createIndex(VRT.vBands.index(vBand), 0, vBand)
        sNode = VirtualBandInputSource


    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags


        flags = super(VRTModel, self).flags(index)
        flags |= Qt.ItemIsDropEnabled | Qt.ItemIsEditable
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

    def dropMimeData(self, mimeData, action, row, column, parentIndex):
        assert isinstance(mimeData, QMimeData)
        #assert isinstance(action, QDropEvent)
        bands = []

        if u'hub.vrtbuilder/bandlist' in mimeData.formats():
            dump = mimeData.data(u'hub.vrtbuilder/bandlist')
            bands = pickle.loads(dump)

        parentNode = self.idx2node(parentIndex)
        if parentNode == self.mRootNode:
            #add VRT band per band
            for band in bands:
                path, bandIndex = band
                vBand = VirtualBand()
                vBand.addSourceBand(path, bandIndex)
                self.mVRTBuilder.addVirtualBand(vBand)
            s = ""
        s = ""

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

class VirtualRasterBuilderWidget(QFrame, loadUi('vrtbuilder.ui')):

    def __init__(self, parent=None):
        super(VirtualRasterBuilderWidget, self).__init__(parent)
        self.setupUi(self)
        self.sourceFileModel = VRTRasterSourceModel()
        self.treeViewSourceFiles.setModel(self.sourceFileModel)

        self.vrtBuilder = VirtualRasterBuilder()
        self.vrtBuilderModel = VRTModel(parent=self, vrtBuilder=self.vrtBuilder)
        self.treeViewVRT.setModel(self.vrtBuilderModel)
        self.treeViewVRT.dragEnterEvent = self.vrtBuilderModel.dragEnterEvent
        self.treeViewVRT.dragMoveEvent = self.vrtBuilderModel.dragMoveEvent
        self.treeViewVRT.dropEvent = self.vrtBuilderModel.dropEvent


    def addSourceFiles(self, files):
        """
        Adds a list of source files to the source file list.
        :param files: list-of-file-paths
        """
        self.sourceFileModel.addFiles(files)

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import utils
    qgsApp = utils.initQgisApplication()

    from example.Images import Img_2014_03_20_LC82270652014079LGN00_BOA, Img_2014_04_29_LE72270652014119CUB00_BOA

    w = VirtualRasterBuilderWidget()
    w.addSourceFiles([Img_2014_03_20_LC82270652014079LGN00_BOA, Img_2014_04_29_LE72270652014119CUB00_BOA])

    w.vrtBuilder.addVirtualBand(VirtualBand(name='Band 1'))

    w.show()

    qgsApp.exec_()
    qgsApp.exitQgis()
