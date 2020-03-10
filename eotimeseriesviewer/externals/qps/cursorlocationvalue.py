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
from . import DIR_UI_FILES
from .utils import *
from .models import *
from .classification.classificationscheme import ClassInfo, ClassificationScheme

class SourceValueSet(object):
    def __init__(self, source, point:SpatialPoint):
        assert isinstance(point, SpatialPoint)
        self.source = source
        self.point = point


    def baseName(self):
        return os.path.basename(self.source)

    def crs(self):
        return QgsCoordinateReferenceSystem(self.wktCrs)


class RasterValueSet(SourceValueSet):

    class BandInfo(object):
        def __init__(self, bandIndex, bandValue, bandName, classInfo=None):
            assert bandIndex >= 0
            if bandValue is not None:
                assert type(bandValue) in [float, int]
            if bandName is not None:
                assert isinstance(bandName, str)

            self.bandIndex = bandIndex
            self.bandValue = bandValue
            self.bandName = bandName
            self.classInfo = classInfo


    def __init__(self, source, point, pxPosition):
        assert isinstance(pxPosition, QPoint)
        super(RasterValueSet, self).__init__(source, point)
        self.pxPosition = pxPosition
        self.noDataValue = None
        self.bandValues = []

class VectorValueSet(SourceValueSet):
    class FeatureInfo(object):
        def __init__(self, fid):
            assert isinstance(fid, int)
            self.fid = fid
            self.attributes = collections.OrderedDict()

    def __init__(self, source, point:SpatialPoint):
        super(VectorValueSet, self).__init__(source, point)
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

        self.mColumnNames = ['Band/Field', 'Value', 'Description']
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
                self.setExpandedNodeRemainder(node=n)
        else:
            self.mExpandedNodeRemainder[self.weakNodeId(node)] = self.mTreeView.isExpanded(self.node2idx(node))
            for n in node.childNodes():
                self.setExpandedNodeRemainder(node=n)

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

        # get-or-create node
        def gocn(root, name)->TreeNode:
            assert isinstance(root, TreeNode)
            n = TreeNode(root, name)
            weakId = self.weakNodeId(n)

            expand = False
            if not isinstance(root.parentNode(), TreeNode):
                expand = True
            else:
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
            root.setIcon(QIcon(':/qps/ui/icons/raster.svg'))

            # add subnodes
            n = gocn(root, 'Pixel')
            n.setValues('{},{}'.format(sourceValueSet.pxPosition.x(), sourceValueSet.pxPosition.y()))

            for bv in sourceValueSet.bandValues:
                if isinstance(bv, RasterValueSet.BandInfo):
                    n = gocn(root, 'Band {}'.format(bv.bandIndex + 1))
                    n.setToolTip('Band {} {}'.format(bv.bandIndex + 1, bv.bandName).strip())
                    n.setValues([bv.bandValue, bv.bandName])

                    if isinstance(bv.classInfo, ClassInfo):
                        nc = gocn(root, 'Class')
                        nc.setValues(bv.classInfo.name())
                        nc.setIcon(bv.classInfo.icon())


                elif isinstance(bv, QColor):
                    n = gocn(root, 'Color')
                    n.setToolTip('Color selected from screen pixel')
                    n.setValues(bv.getRgb())


        if isinstance(sourceValueSet, VectorValueSet):
            if len(sourceValueSet.features) == 0:
                return
            root = gocn(self.mRootNode, name=bn)
            refFeature = sourceValueSet.features[0]
            assert isinstance(refFeature, QgsFeature)
            typeName = QgsWkbTypes.displayString(refFeature.geometry().wkbType()).lower()
            if 'polygon' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconPolygonLayer.svg'))
            elif 'line' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconLineLayer.svg'))
            if 'point' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconPointLayer.svg'))


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
    ComboBoxOption('VISIBLE', 'Visible', 'Visible bands only.'),
    ComboBoxOption('ALL', 'All', 'All raster bands.'),

]

LAYERMODES = [
    ComboBoxOption('TOP_LAYER', 'Top layer', 'Show values of the top-most map layer only.'),
    ComboBoxOption('ALL_LAYERS', 'All layers', 'Show values of all map layers.')
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


class CursorLocationInfoDock(QDockWidget):
    sigLocationRequest = pyqtSignal()
    sigCursorLocationInfoAdded = pyqtSignal()

    def __init__(self, *args, **kwds):
        """Constructor."""
        super().__init__(*args, **kwds)

        path_ui = DIR_UI_FILES / 'cursorlocationinfodock.ui'
        loadUi(path_ui, self)

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

        self.actionAllRasterBands.triggered.connect(
            lambda: self.btnRasterBands.setDefaultAction(self.actionAllRasterBands))
        self.actionVisibleRasterBands.triggered.connect(
            lambda: self.btnRasterBands.setDefaultAction(self.actionVisibleRasterBands))

    def options(self):

        layerType = self.mLayerTypeModel.index2option(self.cbLayerTypes.currentIndex()).value
        layerMode = self.mLayerModeModel.index2option(self.cbLayerModes.currentIndex()).value
        rasterBands = self.mRasterBandsModel.index2option(self.cbRasterBands.currentIndex()).value

        return (layerMode, layerType, rasterBands)

    def loadCursorLocation(self, point:SpatialPoint, canvas:QgsMapCanvas):
        """
        :param point:
        :param canvas:
        :return:
        """
        assert isinstance(canvas, QgsMapCanvas)
        assert isinstance(point, SpatialPoint)
        crs = canvas.mapSettings().destinationCrs()
        self.setCursorLocation(point)
        self.setCanvas(canvas)
        self.reloadCursorLocation()

    def reloadCursorLocation(self):
        """
        Call to load / re-load the data for the cursor location
        """

        ptInfo = self.cursorLocation()

        if not isinstance(ptInfo, SpatialPoint) or len(self.mCanvases) == 0:
            return

        mode, type, rasterbands = self.options()

        def layerFilter(canvas):
            assert isinstance(canvas, QgsMapCanvas)
            lyrs = canvas.layers()
            if type == 'VECTOR':
                lyrs = [l for l in lyrs if isinstance(l, QgsVectorLayer)]
            if type == 'RASTER':
                lyrs = [l for l in lyrs if isinstance(l, QgsRasterLayer)]

            return lyrs

        lyrs = []
        for c in self.mCanvases:
            lyrs.extend(layerFilter(c))

        self.mLocationInfoModel.setExpandedNodeRemainder()
        self.mLocationInfoModel.clear()

        for l in lyrs:
            assert isinstance(l, QgsMapLayer)
            if mode == 'TOP_LAYER' and self.mLocationInfoModel.mRootNode.childCount() > 0:
                s = ""
                break
            assert isinstance(l, QgsMapLayer)

            pointLyr = ptInfo.toCrs(l.crs())
            if not (isinstance(pointLyr, SpatialPoint) and l.extent().contains(pointLyr)):
                continue

            if isinstance(l, QgsRasterLayer):
                renderer = l.renderer()
                px = geo2px(pointLyr, l)
                v = RasterValueSet(l.name(), pointLyr, px)

                # !Note: b is not zero-based -> 1st band means b == 1
                if rasterbands == 'VISIBLE':
                    if isinstance(renderer, QgsPalettedRasterRenderer):
                        bandNumbers = renderer.usesBands()
                        # sometime the rendere is set to band 0 (which does not exist)
                        # QGIS bug
                        if bandNumbers == [0] and l.bandCount() > 0:
                            bandNumbers = [1]
                    else:
                        bandNumbers = renderer.usesBands()

                elif rasterbands == 'ALL':
                    bandNumbers = list(range(1, l.bandCount()+1))
                else:
                    bandNumbers = [1]

                pt2 = QgsPointXY(pointLyr.x() + l.rasterUnitsPerPixelX() * 3,
                                 pointLyr.y() - l.rasterUnitsPerPixelY() * 3)
                ext2Px = QgsRectangle(pointLyr.x(), pt2.y(), pt2.x(), pointLyr.y())

                if l.dataProvider().name() in ['wms']:
                    for b in bandNumbers:
                        block = l.renderer().block(b, ext2Px, 3, 3)
                        assert isinstance(block, QgsRasterBlock)
                        v.bandValues.append(QColor(block.color(0, 0)))
                else:
                    results = l.dataProvider().identify(pointLyr, QgsRaster.IdentifyFormatValue).results()
                    classScheme = None
                    if isinstance(l.renderer(), QgsPalettedRasterRenderer):
                        classScheme = ClassificationScheme.fromRasterRenderer(l.renderer())
                    for b in bandNumbers:
                        if b in results.keys():
                            bandValue = results[b]

                            classInfo = None
                            if isinstance(bandValue, (int, float)) \
                                and isinstance(classScheme, ClassificationScheme) \
                                and bandValue >= 0 \
                                and bandValue < len(classScheme):
                                classInfo = classScheme[int(bandValue)]
                            info = RasterValueSet.BandInfo(b - 1, bandValue, l.bandName(b), classInfo=classInfo)
                            v.bandValues.append(info)

                self.mLocationInfoModel.addSourceValues(v)
                s = ""

            if isinstance(l, QgsVectorLayer):
                # searchRect = QgsRectangle(pt, pt)

                # searchRadius = QgsTolerance.toleranceInMapUnits(1, l, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
                searchRadius = QgsTolerance.toleranceInMapUnits(1, l, self.mCanvases[0].mapSettings(),
                                                                QgsTolerance.Pixels)
                # searchRadius = QgsTolerance.defaultTolerance(l, self.mCanvas.mapSettings())
                # searchRadius = QgsTolerance.toleranceInProjectUnits(1, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
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
                s = VectorValueSet(l.source(), pointLyr)
                while features.nextFeature(feature):
                    s.features.append(QgsFeature(feature))

                self.mLocationInfoModel.addSourceValues(s)
                s = ""

                pass

    def setCursorLocation(self, spatialPoint:SpatialPoint):
        """
        Set the cursor lcation to be loaded.
        :param crs: QgsCoordinateReferenceSystem
        :param point: QgsPointXY
        """
        assert isinstance(spatialPoint, SpatialPoint)
        self.mLocationHistory.insert(0, spatialPoint)
        if len(self.mLocationHistory) > self.mMaxPoints:
            del self.mLocationHistory[self.mMaxPoints:]

        if self.mCrs is None:
            self.setCrs(spatialPoint.crs())
        self.updateCursorLocationInfo()

    def updateCursorLocationInfo(self):
        # transform this point to targeted CRS
        pt = self.cursorLocation()
        if isinstance(pt, SpatialPoint):
            pt = pt.toCrs(self.mCrs)
            self.tbX.setText('{}'.format(pt.x()))
            self.tbY.setText('{}'.format(pt.y()))

    def setCanvas(self, mapCanvas):
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
        self.updateCursorLocationInfo()

    def cursorLocation(self)->SpatialPoint:
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
