# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    cursorlocationvalue.py
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


import os, collections

import numpy as np
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from timeseriesviewer.utils import loadUI, SpatialExtent, SpatialPoint, createCRSTransform, geo2px
from timeseriesviewer.trees import *

class SourceValueSet(object):
    def __init__(self, source, crs, geoCoordinate):
        assert isinstance(geoCoordinate, QgsPointXY)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.source = source
        self.point = geoCoordinate
        self.wktCrs = crs.toWkt()

    def baseName(self):
        return os.path.basename(self.source)

    def crs(self):
        return QgsCoordinateReferenceSystem(self.wktCrs)

class RasterValueSet(SourceValueSet):

    class BandInfo(object):
        def __init__(self, bandIndex, bandValue, bandName):
            assert bandIndex >= 0
            if bandValue is not None:
                assert type(bandValue) in [float, int]
            if bandName is not None:
                assert isinstance(bandName, str)

            self.bandIndex = bandIndex
            self.bandValue = bandValue
            self.bandName = bandName


    def __init__(self, source, crs, geoCoordinate, pxPosition):
        assert isinstance(pxPosition, QPoint)
        super(RasterValueSet, self).__init__(source, crs, geoCoordinate)
        self.pxPosition = pxPosition
        self.noDataValue = None
        self.bandValues = []

class VectorValueSet(SourceValueSet):
    class FeatureInfo(object):
        def __init__(self, fid):
            assert isinstance(fid, int)
            self.fid = fid
            self.attributes = collections.OrderedDict()

    def __init__(self, source, geoCoordinate, crs):
        super(VectorValueSet, self).__init__(source, geoCoordinate, crs)
        self.features = []

    def addFeatureInfo(self, featureInfo):
        assert isinstance(featureInfo, VectorValueSet.FeatureInfo)
        self.features.append(featureInfo)


class CursorLocationInfoModel(TreeModel):

    ALWAYS_EXPAND = 'always'
    NEVER_EXPAND = 'never'
    REMAINDER = 'reminder'

    def __init__(self, parent=None):
        super(CursorLocationInfoModel, self).__init__(parent)

        self.mColumnNames = ['Band/Field','Value','Description']
        self.mExpandedNodeRemainder = {}
        self.mNodeExpansion = CursorLocationInfoModel.REMAINDER

    def setNodeExpansion(self, type):

        assert type in [CursorLocationInfoModel.ALWAYS_EXPAND,
                        CursorLocationInfoModel.NEVER_EXPAND,
                        CursorLocationInfoModel.REMAINDER]
        self.mNodeExpansion = type


    def setExpandedNodeRemainder(self, node=None):
        treeView = self.mTreeView
        assert isinstance(treeView, QTreeView)
        if node is None:
            for n in self.mRootNode.childNodes():
                self.setExpandedNodeRemainder(node = n)
        else:
            self.mExpandedNodeRemainder[self.weakNodeId(node)] = self.mTreeView.isExpanded(self.node2idx(node))
            for n in node.childNodes():
                self.setExpandedNodeRemainder(node = n)


    def weakNodeId(self, node):
        assert isinstance(node, TreeNode)
        n = node.name()
        while node.parentNode() != self.mRootNode:
            node = node.parentNode()
            n += '{}:{}'.format(node.name(), n)
        return n



    def flags(self, index):

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def addSourceValues(self, sourceValueSet):
        if not isinstance(sourceValueSet, SourceValueSet):
            return

        #get-or-create node
        def gocn(root, name):
            assert isinstance(root, TreeNode)
            n = TreeNode(root, name)
            weakId = self.weakNodeId(n)


            expand = False
            if self.mNodeExpansion == CursorLocationInfoModel.REMAINDER:
                expand = self.mExpandedNodeRemainder.get(weakId, False)
            elif self.mNodeExpansion == CursorLocationInfoModel.NEVER_EXPAND:
                expand = False
            elif self.mNodeExpansion == CursorLocationInfoModel.ALWAYS_EXPAND:
                expand = True

            self.mTreeView.setExpanded(self.node2idx(n), expand)
            return n

        bn = os.path.basename(sourceValueSet.source)

        if isinstance(sourceValueSet, RasterValueSet):
            root = gocn(self.mRootNode, name=bn)
            self.setColumnSpan(root, True)
            root.setIcon(QIcon(':/enmapbox/icons/mIconRasterLayer.png'))

            #add subnodes
            n = gocn(root, 'Pixel')
            n.setValues('{},{}'.format(sourceValueSet.pxPosition.x(), sourceValueSet.pxPosition.y()))

            for bv in sourceValueSet.bandValues:
                assert isinstance(bv, RasterValueSet.BandInfo)
                n = gocn(root, 'Band {}'.format(bv.bandIndex+1))
                n.setToolTip('Band {} {}'.format(bv.bandIndex+1, bv.bandName).strip())
                n.setValues([bv.bandValue, bv.bandName])

        if isinstance(sourceValueSet, VectorValueSet):
            if len(sourceValueSet.features) == 0:
                return
            root = gocn(self.mRootNode, name=bn)
            self.setColumnSpan(root, True)
            refFeature = sourceValueSet.features[0]
            assert isinstance(refFeature, QgsFeature)
            typeName = QgsWkbTypes.displayString(refFeature.geometry().wkbType()).lower()
            if 'polygon' in typeName: path = ':/enmapbox/icons/mIconPolygonLayer.png'
            if 'line' in typeName: path = ':/enmapbox/icons/mIconLineLayer.png'
            if 'point' in typeName: path = ':/enmapbox/icons/mIconLineLayer.png'
            root.setIcon(QIcon(path))

            for field in refFeature.fields():
                assert isinstance(field, QgsField)

                fieldNode = gocn(root, name=field.name())

                for i, feature in enumerate(sourceValueSet.features):
                    assert isinstance(feature, QgsFeature)
                    nf = gocn(fieldNode, name='{}'.format(feature.id()))
                    nf.setValues([feature.attribute(field.name()), field.typeName()])
                    nf.setToolTip('Value of feature "{}" in field with name "{}"'.format(feature.id(), field.name()))

        s = ""

    def clear(self):
        self.mRootNode.removeChildNodes(0, self.mRootNode.childCount())


class ComboBoxOption(object):
    def __init__(self, value, name=None, tooltip=None, icon=None):
        self.value = value
        self.name = str(value) if name is None else str(name)
        self.tooltip = tooltip
        self.icon = icon

LUT_GEOMETRY_ICONS = {}

RASTERBANDS = [
    ComboBoxOption('VISIBLE', 'RGB', 'Visible bands only.'),
    ComboBoxOption('ALL', 'All','All raster bands.'),

]

LAYERMODES = [
    ComboBoxOption('ALL_LAYERS', 'All layers', 'Show values of all map layers.'),
    ComboBoxOption('TOP_LAYER', 'Top layer', 'Show values of the top-most map layer only.')
    ]

LAYERTYPES = [
    ComboBoxOption('ALL', 'Raster and Vector', 'Show values of both, raster and vector layers.'),
    ComboBoxOption('VECTOR', 'Vector only', 'Show values of vector layers only.'),
    ComboBoxOption('RASTER', 'Raster only', 'Show values of raster layers only.')
    ]

class ComboBoxOptionModel(QAbstractListModel):

    def __init__(self, options, parent=None, ):
        super(ComboBoxOptionModel, self).__init__(parent)
        assert isinstance(options, list)

        for o in options:
            assert isinstance(o, ComboBoxOption)

        self.mOptions = options

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mOptions)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1



    def index2option(self, index):

        if isinstance(index, QModelIndex) and index.isValid():
            return self.mOptions[index.row()]
        elif isinstance(index, int):
            return self.mOptions[index]
        return None

    def option2index(self, option):
        assert option in self.mOptions
        return self.mOptions.index(option)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        option = self.index2option(index)
        assert isinstance(option, ComboBoxOption)
        value = None
        if role == Qt.DisplayRole:
            value = option.name
        if role == Qt.ToolTipRole:
            value = option.tooltip
        if role == Qt.DecorationRole:
            value = option.icon
        if role == Qt.UserRole:
            value = option
        return value


class CursorLocationInfoDock(QDockWidget,
                             loadUI('cursorlocationinfodock.ui')):

    sigLocationRequest = pyqtSignal()
    sigCursorLocationInfoAdded = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        QWidget.__init__(self, parent)
        #super(CursorLocationValueWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.mMaxPoints = 1
        self.mLocationHistory = []

        self.mCrs = None
        self.mCanvases = []

        self.btnCrs.crsChanged.connect(self.setCrs)
        self.btnCrs.setCrs(QgsCoordinateReferenceSystem())



        self.mLocationInfoModel = CursorLocationInfoModel(parent=self.treeView)
        self.treeView.setModel(self.mLocationInfoModel)

        self.mLayerModeModel = ComboBoxOptionModel(LAYERMODES, parent=self)
        self.mLayerTypeModel = ComboBoxOptionModel(LAYERTYPES, parent=self)
        self.mRasterBandsModel = ComboBoxOptionModel(RASTERBANDS, parent=self)

        self.cbLayerModes.setModel(self.mLayerModeModel)
        self.cbLayerTypes.setModel(self.mLayerTypeModel)
        self.cbRasterBands.setModel(self.mRasterBandsModel)
        self.actionRequestCursorLocation.triggered.connect(self.sigLocationRequest)
        self.actionReload.triggered.connect(self.reloadCursorLocation)

        self.btnActivateMapTool.setDefaultAction(self.actionRequestCursorLocation)
        self.btnReload.setDefaultAction(self.actionReload)


        self.actionAllRasterBands.triggered.connect(lambda : self.btnRasterBands.setDefaultAction(self.actionAllRasterBands))
        self.actionVisibleRasterBands.triggered.connect(lambda : self.btnRasterBands.setDefaultAction(self.actionVisibleRasterBands))


    def options(self):



        layerType = self.mLayerTypeModel.index2option(self.cbLayerTypes.currentIndex()).value
        layerMode = self.mLayerModeModel.index2option(self.cbLayerModes.currentIndex()).value
        rasterBands = self.mRasterBandsModel.index2option(self.cbRasterBands.currentIndex()).value

        return (layerMode, layerType, rasterBands)

    def loadCursorLocation(self, point, canvas):


        assert isinstance(canvas, QgsMapCanvas)

        crs = canvas.mapSettings().destinationCrs()
        self.setCursorLocation(crs, point)
        self.setCanvas(canvas)
        self.reloadCursorLocation()


    def reloadCursorLocation(self):

        crsInfo, ptInfo = self.cursorLocation()

        if ptInfo is None or len(self.mCanvases) == 0:
            return

        mode, type, rasterbands = self.options()

        def layerFilter(canvas):
            assert isinstance(canvas, QgsMapCanvas)
            lyrs = canvas.layers()
            if type == 'VECTOR':
                lyrs = [l for l in lyrs if isinstance(l, QgsVectorLayer)]
            if type == 'RASTER':
                lyrs = [l for l in lyrs if isinstance(l, QgsRasterLayer)]

            if len(lyrs) > 0 and mode == 'TOP_LAYER':
                lyrs = [lyrs[0]]
            return lyrs

        lyrs = []
        for c in self.mCanvases:
            lyrs.extend(layerFilter(c))

        #convert location of interest into WGS-84 GCS
        crsWorld = QgsCoordinateReferenceSystem('EPSG:4326')



        info2World = createCRSTransform(crsInfo, crsWorld)
        pointWorld = info2World.transform(ptInfo)

        self.mLocationInfoModel.setExpandedNodeRemainder()

        self.mLocationInfoModel.clear()

        for l in lyrs:
            assert isinstance(l, QgsMapLayer)
            lyr2World = createCRSTransform(l.crs(), crsWorld)
            world2lyr = createCRSTransform(crsWorld, l.crs())

            #check in GCS WGS-84 if the point-of-interest intersects with layer
            lyrExt = lyr2World.transformBoundingBox(l.extent())
            assert isinstance(lyrExt, QgsRectangle)
            if not lyrExt.contains(pointWorld):
                continue

            #transform relquested location into layer CRS coordinates
            pointLyr = world2lyr.transform(pointWorld)


            if isinstance(l, QgsRasterLayer):
                renderer = l.renderer()
                ds = gdal.Open(l.source())
                if ds.RasterCount == 0:
                    continue
                    
                if isinstance(renderer, QgsRasterRenderer) and isinstance(ds, gdal.Dataset):
                    #transform geo into pixel coodinates
                    px = geo2px(pointLyr, ds.GetGeoTransform())
                    if px.x() >= 0 and px.x() < ds.RasterXSize and \
                       px.y() >= 0 and px.y() < ds.RasterYSize:

                        v = RasterValueSet(l.source(), crsInfo, ptInfo, px)

                        # !Note: b is not zero-based -> 1st band means b == 1
                        if rasterbands == 'VISIBLE':
                            bandNumbers = renderer.usesBands()
                        elif rasterbands == 'ALL':
                            bandNumbers = range(1, ds.RasterCount + 1)
                        else:
                            bandNumbers = [0]

                        for i, b in enumerate(bandNumbers):

                            band = ds.GetRasterBand(b)
                            assert isinstance(band, gdal.Band)
                            if i == 0:
                                v.noDataValue = band.GetNoDataValue()

                            value = band.ReadAsArray(px.x(), px.y(), 1,1)
                            if value is None:
                                s =""
                            value = np.asscalar(value.flatten()[0])
                            bandInfo = RasterValueSet.BandInfo(b-1, value, band.GetDescription())
                            v.bandValues.append(bandInfo)

                        self.mLocationInfoModel.addSourceValues(v)

            if isinstance(l, QgsVectorLayer):
                #searchRect = QgsRectangle(pt, pt)

                #searchRadius = QgsTolerance.toleranceInMapUnits(1, l, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
                searchRadius = QgsTolerance.toleranceInMapUnits(1, l, self.mCanvases[0].mapSettings(), QgsTolerance.Pixels)
                #searchRadius = QgsTolerance.defaultTolerance(l, self.mCanvas.mapSettings())
                #searchRadius = QgsTolerance.toleranceInProjectUnits(1, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
                searchRect = QgsRectangle()
                searchRect.setXMinimum(pointLyr.x() - searchRadius);
                searchRect.setXMaximum(pointLyr.x() + searchRadius);
                searchRect.setYMinimum(pointLyr.y() - searchRadius);
                searchRect.setYMaximum(pointLyr.y() + searchRadius);

                flags = QgsFeatureRequest.ExactIntersect
                features = l.getFeatures(QgsFeatureRequest() \
                                         .setFilterRect(searchRect) \
                                         .setFlags(flags))
                feature = QgsFeature()
                s = VectorValueSet(l.source(), crsInfo, pointLyr)
                while features.nextFeature(feature):
                    s.features.append(QgsFeature(feature))

                self.mLocationInfoModel.addSourceValues(s)
                s = ""

                pass

    def setCursorLocation(self, crs, point):
        """
        :param crs:
        :param point:
        :return:
        """
        assert isinstance(point, QgsPointXY)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mLocationHistory.insert(0, (crs, point))
        if len(self.mLocationHistory) > self.mMaxPoints:
            del self.mLocationHistory[self.mMaxPoints:]

        if self.mCrs is None:
            self.setCrs(crs)

        self.setCursorLocationInfo()


    def setCursorLocationInfo(self):
        # transform this point to targeted CRS
        crs, pt = self.cursorLocation()
        if isinstance(pt, QgsPointXY):
            if crs != self.mCrs:
                trans = QgsCoordinateTransform(crs, self.mCrs)
                pt = trans.transform(pt)

            self.tbX.setText('{}'.format(pt.x()))
            self.tbY.setText('{}'.format(pt.y()))

    def setCanvas(self,  mapCanvas):
        self.setCanvases([mapCanvas])

    def setCanvases(self, mapCanvases):
        assert isinstance(mapCanvases, list)
        for c in mapCanvases:
            assert isinstance(c, QgsMapCanvas)

        if len(mapCanvases) == 0:
            self.setCrs(None)
        else:
            setNew = True
            for c in mapCanvases:
                if c in self.mCanvases:
                    setNew = False
            if setNew:
                self.setCrs(mapCanvases[0].mapSettings().destinationCrs())
        self.mCanvases = mapCanvases

    def setCrs(self, crs):
        """
        Set the coordinate reference system in which coordinates are shown
        :param crs:
        :return:
        """
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if crs != self.mCrs:
            self.mCrs = crs
            self.btnCrs.setCrs(crs)
        self.setCursorLocationInfo()


    def cursorLocation(self):
        """
        Returns the last location that was set.
        """
        if len(self.mLocationHistory) > 0:
            return self.mLocationHistory[0]
        else:
            return None, None



class Resulthandler(QObject):

    def __init__(self):
        super(Resulthandler, self).__init__()

    def onResult(self, *args):
        print(args)


R = Resulthandler()
if __name__ == '__main__':
    from timeseriesviewer.utils import initQgisApplication
    from timeseriesviewer import DIR_QGIS_RESOURCES
    qgsApp = initQgisApplication(qgisResourceDir=DIR_QGIS_RESOURCES)

    from example.Images import Img_2014_05_31_LE72270652014151CUB00_BOA
    from example import exampleEvents

    canvas = QgsMapCanvas()
    lyr = QgsRasterLayer(Img_2014_05_31_LE72270652014151CUB00_BOA)
    shp = QgsVectorLayer(exampleEvents, 'events')
    QgsProject.instance().addMapLayers([lyr,shp])
    canvas.setLayers([shp, lyr])
    canvas.setDestinationCrs(lyr.crs())
    canvas.setExtent(lyr.extent())
    canvas.show()

    d = CursorLocationInfoDock()
    d.show()
    d.loadCursorLocation(lyr.extent().center(), canvas)
    pass

    qgsApp.exec_()