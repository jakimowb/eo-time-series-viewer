# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    spectrallibraries.py

    Spectral Profiles and Libraries for a GUI context.
    ---------------------
    Date                 : Juli 2017
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

#see http://python-future.org/str_literals.html for str issue discussion
import os, re, tempfile, pickle, copy, shutil, locale, uuid, csv, io
from collections import OrderedDict
from qgis.core import *
from qgis.gui import *
from qgis.utils import qgsfunction
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import QgsField, QgsFields, QgsFeature, QgsMapLayer, QgsVectorLayer, QgsConditionalStyle
from qgis.gui import QgsMapCanvas, QgsDockWidget
from pyqtgraph.widgets.PlotWidget import PlotWidget
from pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from pyqtgraph.graphicsItems.PlotItem import PlotItem
import pyqtgraph.functions as fn
import numpy as np
from osgeo import gdal, gdal_array, ogr

from timeseriesviewer.utils import *
from timeseriesviewer.virtualrasters import describeRawFile
from timeseriesviewer.models import *
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleDialog, MARKERSYMBOLS2QGIS_SYMBOLS
import timeseriesviewer.mimedata as mimedata

FILTERS = 'ENVI Spectral Library + CSV (*.esl *.sli);;CSV Table (*.csv);;ESRI Shapefile (*.shp)'

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
HIDDEN_ATTRIBUTE_PREFIX = '__serialized__'
CURRENT_SPECTRUM_STYLE = PlotStyle()
CURRENT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
CURRENT_SPECTRUM_STYLE.linePen.setColor(Qt.green)


DEFAULT_SPECTRUM_STYLE = PlotStyle()
DEFAULT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
DEFAULT_SPECTRUM_STYLE.linePen.setColor(Qt.white)

EMPTY_VALUES = [None, NULL, QVariant()]

#CURRENT_SPECTRUM_STYLE.linePen
#pdi.setPen(fn.mkPen(QColor('green'), width=3))
def gdalDataset(pathOrDataset, eAccess=gdal.GA_ReadOnly):
    """

    :param pathOrDataset: path or gdal.Dataset
    :return: gdal.Dataset
    """

    if isinstance(pathOrDataset, QgsRasterLayer):
        return gdalDataset(pathOrDataset.source())

    if not isinstance(pathOrDataset, gdal.Dataset):
        pathOrDataset = gdal.Open(pathOrDataset, eAccess)

    assert isinstance(pathOrDataset, gdal.Dataset)

    return pathOrDataset


def findTypeFromString(value:str):
    """
    Returns a fitting basic data type of a string value
    :param value: string
    :return: type
    """
    for t in (int, float):
        try:
            _ = t(value)
        except ValueError:
            continue
        return t

    #every values can be converted into a string
    return str

def toType(t, arg, empty2None=True):
    """
    Converts lists or single values into type t.

    Examples:
        toType(int, '42') == 42,
        toType(float, ['23.42', '123.4']) == [23.42, 123.4]

    :param t: type
    :param arg: value to convert
    :param empty2None: returns None in case arg is an emptry value (None, '', NoneType, ...)
    :return: arg as type t (or None)
    """
    if isinstance(arg, list):
        return [toType(t, a) for a in arg]
    else:

        if empty2None and arg in EMPTY_VALUES:
            return None
        else:
            return t(arg)


@qgsfunction(0, "Spectral Libraries")
def plotStyleSymbolFillColor(values, feature, parent):
    if isinstance(feature, QgsFeature):
        i = feature.fieldNameIndex(HIDDEN_ATTRIBUTE_PREFIX+'style')
        if i >= 0:
            style = pickle.loads(feature.attribute(i))
            if isinstance(style, PlotStyle):
                r,g,b,a = style.markerBrush.color().getRgb()
                return '{},{},{},{}'.format(r,g,b, a)

    return None

@qgsfunction(0, "Spectral Libraries")
def plotStyleSymbol(values, feature, parent):
    if isinstance(feature, QgsFeature):
        i = feature.fieldNameIndex(HIDDEN_ATTRIBUTE_PREFIX+'style')
        if i >= 0:
            style = pickle.loads(feature.attribute(i))
            if isinstance(style, PlotStyle):
                symbol = style.markerSymbol

                qgisSymbolString =  MARKERSYMBOLS2QGIS_SYMBOLS.get(symbol)
                if isinstance(qgisSymbolString, str):
                    return qgisSymbolString

    return None

@qgsfunction(0, "Spectral Libraries")
def plotStyleSymbolSize(values, feature, parent):
    if isinstance(feature, QgsFeature):
        i = feature.fieldNameIndex(HIDDEN_ATTRIBUTE_PREFIX+'style')
        if i >= 0:
            style = pickle.loads(feature.attribute(i))
            if isinstance(style, PlotStyle):
                return style.markerSize
    return None


QgsExpression.registerFunction(plotStyleSymbolFillColor)
QgsExpression.registerFunction(plotStyleSymbol)
QgsExpression.registerFunction(plotStyleSymbolSize)


#Lookup table for ENVI IDL DataTypes to GDAL Data Types
LUT_IDL2GDAL = {1:gdal.GDT_Byte,
                12:gdal.GDT_UInt16,
                2:gdal.GDT_Int16,
                13:gdal.GDT_UInt32,
                3:gdal.GDT_Int32,
                4:gdal.GDT_Float32,
                5:gdal.GDT_Float64,
                #:gdal.GDT_CInt16,
                #8:gdal.GDT_CInt32,
                6:gdal.GDT_CFloat32,
                9:gdal.GDT_CFloat64}



def createStandardFields():
    fields = QgsFields()

    """﻿
    Parameters
    name Field name type Field variant type, currently supported: String / Int / Double 
    typeName Field type (e.g., char, varchar, text, int, serial, double). Field types are usually unique to the source and are stored exactly as returned from the data store. 
    len Field length 
    prec Field precision. Usually decimal places but may also be used in conjunction with other fields types (e.g., variable character fields) 
    comment Comment for the field 
    subType If the field is a collection, its element's type. When all the elements don't need to have the same type, leave this to QVariant::Invalid. 
    """
    fields.append(createQgsField('name', ''))
    fields.append(createQgsField('px_x', 0))
    fields.append(createQgsField('px_y', 0))
    fields.append(createQgsField('x_unit', ''))
    fields.append(createQgsField('y_unit', ''))
    fields.append(createQgsField('source', ''))
    fields.append(createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'xvalues', ''))
    fields.append(createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'yvalues', ''))
    fields.append(createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'style', ''))


    """
    fields.append(QgsField('name', QVariant.String,'varchar', 25))
    fields.append(QgsField('px_x', QVariant.Int, 'int'))
    fields.append(QgsField('px_y', QVariant.Int, 'int'))
    fields.append(QgsField('x_unit', QVariant.String, 'varchar', 5))
    fields.append(QgsField('y_unit', QVariant.String, 'varchar', 5))
    fields.append(QgsField('source', QVariant.String, 'varchar', 5))
    """
    return fields


def value2str(value, sep=' '):
    if isinstance(value, list):
        value = sep.join([value2str(v, sep=sep) for v in value])
    elif isinstance(value, np.ndarray):
        value = value2str(value.astype(list), sep=sep)
    elif value in EMPTY_VALUES:
        value = ''
    else:
        value = str(value)
    return value


class AddAttributeDialog(QDialog):

    def __init__(self, layer, parent=None):
        assert isinstance(layer, QgsVectorLayer)
        super(AddAttributeDialog, self).__init__(parent)

        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer

        self.setWindowTitle('Add Field')
        l = QGridLayout()

        self.tbName = QLineEdit('Name')
        self.tbName.setPlaceholderText('Name')
        self.tbName.textChanged.connect(self.validate)

        l.addWidget(QLabel('Name'), 0,0)
        l.addWidget(self.tbName, 0, 1)

        self.tbComment = QLineEdit()
        self.tbComment.setPlaceholderText('Comment')
        l.addWidget(QLabel('Comment'), 1, 0)
        l.addWidget(self.tbComment, 1, 1)

        self.cbType = QComboBox()
        self.typeModel = OptionListModel()

        for ntype in self.mLayer.dataProvider().nativeTypes():
            assert isinstance(ntype, QgsVectorDataProvider.NativeType)
            o = Option(ntype,name=ntype.mTypeName, tooltip=ntype.mTypeDesc)
            self.typeModel.addOption(o)
        self.cbType.setModel(self.typeModel)
        self.cbType.currentIndexChanged.connect(self.onTypeChanged)
        l.addWidget(QLabel('Type'), 2, 0)
        l.addWidget(self.cbType, 2, 1)

        self.sbLength = QSpinBox()
        self.sbLength.setRange(0, 99)
        self.sbLength.valueChanged.connect(lambda : self.setPrecisionMinMax())
        self.lengthLabel = QLabel('Length')
        l.addWidget(self.lengthLabel, 3, 0)
        l.addWidget(self.sbLength, 3, 1)

        self.sbPrecision = QSpinBox()
        self.sbPrecision.setRange(0, 99)
        self.precisionLabel = QLabel('Precision')
        l.addWidget(self.precisionLabel, 4, 0)
        l.addWidget(self.sbPrecision, 4, 1)

        self.tbValidationInfo = QLabel()
        self.tbValidationInfo.setStyleSheet("QLabel { color : red}")
        l.addWidget(self.tbValidationInfo, 5, 0, 1, 2)


        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttons.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        l.addWidget(self.buttons, 6, 1)
        self.setLayout(l)

        self.mLayer = layer

        self.onTypeChanged()

    def accept(self):

        msg = self.validate()

        if len(msg) > 0:
            QMessageBox.warning(self, "Add Field", msg)
        else:
            super(AddAttributeDialog, self).accept()

    def field(self):
        """
        Returns the new QgsField
        :return:
        """
        ntype = self.currentNativeType()
        return QgsField(name=self.tbName.text(),
                        type=QVariant(ntype.mType).type(),
                        typeName=ntype.mTypeName,
                        len=self.sbLength.value(),
                        prec=self.sbPrecision.value(),
                        comment=self.tbComment.text())




    def currentNativeType(self):
        return self.cbType.currentData().value()

    def onTypeChanged(self, *args):
        ntype = self.currentNativeType()
        vMin , vMax = ntype.mMinLen, ntype.mMaxLen
        assert isinstance(ntype, QgsVectorDataProvider.NativeType)

        isVisible = vMin < vMax
        self.sbLength.setVisible(isVisible)
        self.lengthLabel.setVisible(isVisible)
        self.setSpinBoxMinMax(self.sbLength, vMin , vMax)
        self.setPrecisionMinMax()

    def setPrecisionMinMax(self):
        ntype = self.currentNativeType()
        vMin, vMax = ntype.mMinPrec, ntype.mMaxPrec
        isVisible = vMin < vMax
        self.sbPrecision.setVisible(isVisible)
        self.precisionLabel.setVisible(isVisible)

        vMax = max(ntype.mMinPrec, min(ntype.mMaxPrec, self.sbLength.value()))
        self.setSpinBoxMinMax(self.sbPrecision, vMin, vMax)

    def setSpinBoxMinMax(self, sb, vMin, vMax):
        assert isinstance(sb, QSpinBox)
        value = sb.value()
        sb.setRange(vMin, vMax)

        if value > vMax:
            sb.setValue(vMax)
        elif value < vMin:
            sb.setValue(vMin)


    def validate(self):

        msg = []
        name = self.tbName.text()
        if name in self.mLayer.fields().names():
            msg.append('Field name "{}" already exists.'.format(name))
        elif name == '':
            msg.append('Missing field name')
        elif name == 'shape':
            msg.append('Field name "{}" already reserved.'.format(name))

        msg = '\n'.join(msg)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(len(msg) == 0)

        self.tbValidationInfo.setText(msg)

        return msg




class SpectralLibraryTableFilterModel(QgsAttributeTableFilterModel):

    def __init__(self, sourceModel, parent=None):

        dummyCanvas = QgsMapCanvas()
        dummyCanvas.setDestinationCrs(SpectralProfile.crs)
        dummyCanvas.setExtent(QgsRectangle(-180,-90,180,90))

        super(SpectralLibraryTableFilterModel, self).__init__(dummyCanvas, sourceModel, parent=parent)

        self.mDummyCanvas = dummyCanvas

        #self.setSelectedOnTop(True)

class SpectralLibraryTableView(QgsAttributeTableView):

    def __init__(self, parent=None):
        super(SpectralLibraryTableView, self).__init__(parent)


        #self.setSelectionBehavior(QAbstractItemView.SelectRows)
        #self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setSectionsMovable(True)
        self.willShowContextMenu.connect(self.onWillShowContextMenu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)


        self.mSelectionManager = None

    def setModel(self, filterModel):

        super(SpectralLibraryTableView, self).setModel(filterModel)


        self.mSelectionManager = SpectralLibraryFeatureSelectionManager(self.model().layer())
        self.setFeatureSelectionManager(self.mSelectionManager)
        #self.selectionModel().selectionChanged.connect(self.onSelectionChanged)


    #def contextMenuEvent(self, event):
    def onWillShowContextMenu(self, menu, index):
        assert isinstance(menu, QMenu)
        assert isinstance(index, QModelIndex)

        featureIDs = self.spectralLibrary().selectedFeatureIds()

        if len(featureIDs) == 0 and index.isValid():
            if isinstance(self.model(), QgsAttributeTableFilterModel):
                index = self.model().mapToSource(index)
                if index.isValid():
                    featureIDs.append(self.model().sourceModel().feature(index).id())
            elif isinstance(self.model(), QgsAttributeTableFilterModel):
                featureIDs.append(self.model().feature(index).id())



        if len(featureIDs) > 0:
            m = menu.addMenu('Copy...')
            a = m.addAction("Values")
            a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.VALUES: self.onCopy2Clipboard(ids, mode))
            a = m.addAction("Attributes")
            a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.ATTRIBUTES: self.onCopy2Clipboard(ids, mode))
            a = m.addAction("Values + Attributes")
            a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.ALL: self.onCopy2Clipboard(ids, mode))

        a = menu.addAction('Save as...')
        a.triggered.connect(lambda b, ids=featureIDs : self.onSaveToFile(ids))
        menu.addSeparator()
        a = menu.addAction('Set Style')
        a.triggered.connect(lambda b, ids=featureIDs : self.onSetStyle(ids))
        a = menu.addAction('Check')
        a.triggered.connect(lambda : self.setCheckState(featureIDs, Qt.Checked))
        a = menu.addAction('Uncheck')
        a.triggered.connect(lambda: self.setCheckState(featureIDs, Qt.Unchecked))
        menu.addSeparator()
        for a in self.actions():
            menu.addAction(a)

    def spectralLibrary(self):
        return self.model().layer()


    def onCopy2Clipboard(self, fids, mode):
        assert isinstance(fids, list)
        assert mode in ClipboardIO.WritingModes().modes()

        speclib = self.spectralLibrary()
        assert isinstance(speclib, SpectralLibrary)
        speclib = speclib.speclibFromFeatureIDs(fids)
        ClipboardIO.write(speclib, mode=mode)

        s = ""

    def onSaveToFile(self, fids):
        speclib = self.spectralLibrary()
        assert isinstance(speclib, SpectralLibrary)
        speclib.getFeatures(fids)
        speclib.exportProfiles()

    def fidsToIndices(self, fids):
        """
        Converts feature ids into FilterModel QModelIndices
        :param fids: [list-of-int]
        :return:
        """
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)
        fmodel = self.model()
        indices = [fmodel.fidToIndex(id) for id in fids]
        return [fmodel.index(idx.row(), 0) for idx in indices]

    def onRemoveFIDs(self, fids):

        speclib = self.spectralLibrary()
        assert isinstance(speclib, SpectralLibrary)
        b = speclib.isEditable()
        speclib.startEditing()
        speclib.deleteFeatures(fids)
        saveEdits(speclib, leaveEditable=b)

    def onSetStyle(self, ids):

        if len(ids) == 0:
            return

        speclib = self.spectralLibrary()
        assert isinstance(speclib, SpectralLibrary)

        profiles = speclib.profiles(ids)
        refProfile = profiles[0]
        styleDefault = refProfile.style()
        refStyle = PlotStyleDialog.getPlotStyle(plotStyle=styleDefault)
        if isinstance(refStyle, PlotStyle):
            refProfile.setStyle(refStyle)

        iStyle = speclib.fields().indexFromName(HIDDEN_ATTRIBUTE_PREFIX+'style')
        assert iStyle >= 0


        if isinstance(refStyle, PlotStyle):

            b = speclib.isEditable()
            speclib.startEditing()
            for f in profiles:
                assert isinstance(f, SpectralProfile)
                oldStyle = f.style()
                refStyle.setVisibility(oldStyle.isVisible())
                speclib.changeAttributeValue(f.id(), iStyle, pickle.dumps(refStyle), f.attributes()[iStyle])
            saveEdits(speclib, leaveEditable=b)




    def setCheckState(self, fids, checkState):

        speclib = self.spectralLibrary()
        speclib.startEditing()

        profiles = speclib.profiles(fids)


        iStyle = speclib.fields().indexFromName(HIDDEN_ATTRIBUTE_PREFIX + 'style')

        setVisible = checkState == Qt.Checked

        b = speclib.isEditable()
        speclib.startEditing()
        for p in profiles:
            assert isinstance(p, SpectralProfile)
            oldStyle = p.style()
            assert isinstance(oldStyle, PlotStyle)

            if oldStyle.isVisible() != setVisible:
                newStyle = p.style()
                newStyle.setVisibility(setVisible)
                p.setStyle(newStyle)
                speclib.changeAttributeValue(p.id(), iStyle, p.attributes()[iStyle], oldStyle)
        saveEdits(speclib, leaveEditable=b)



    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if self.model().rowCount() == 0:
            index = self.model().createIndex(0,0)
        else:
            index = self.indexAt(event.pos())

        if mimeData.hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            self.model().dropMimeData(mimeData, event.dropAction(), index.row(), index.column(), index.parent())
            event.accept()





    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            event.accept()
        s = ""


    def mimeTypes(self):
        pass

"""
class SpectralProfileMapTool(QgsMapToolEmitPoint):

    sigProfileRequest = pyqtSignal(SpatialPoint, QgsMapCanvas)

    def __init__(self, canvas, showCrosshair=True):
        self.mShowCrosshair = showCrosshair
        self.mCanvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.mCanvas)
        self.marker = QgsVertexMarker(self.mCanvas)
        self.rubberband = QgsRubberBand(self.mCanvas, QgsWkbTypes.PolygonGeometry)

        color = QColor('red')

        self.rubberband.setLineStyle(Qt.SolidLine)
        self.rubberband.setColor(color)
        self.rubberband.setWidth(2)

        self.marker.setColor(color)
        self.marker.setPenWidth(3)
        self.marker.setIconSize(5)
        self.marker.setIconType(QgsVertexMarker.ICON_CROSS)  # or ICON_CROSS, ICON_X

    def canvasPressEvent(self, e):
        geoPoint = self.toMapCoordinates(e.pos())
        self.marker.setCenter(geoPoint)
        #self.marker.show()

    def setStyle(self, color=None, brushStyle=None, fillColor=None, lineStyle=None):
        if color:
            self.rubberband.setColor(color)
        if brushStyle:
            self.rubberband.setBrushStyle(brushStyle)
        if fillColor:
            self.rubberband.setFillColor(fillColor)
        if lineStyle:
            self.rubberband.setLineStyle(lineStyle)

    def canvasReleaseEvent(self, e):

        pixelPoint = e.pixelPoint()

        crs = self.mCanvas.mapSettings().destinationCrs()
        self.marker.hide()
        geoPoint = self.toMapCoordinates(pixelPoint)
        if self.mShowCrosshair:
            #show a temporary crosshair
            ext = SpatialExtent.fromMapCanvas(self.mCanvas)
            cen = geoPoint
            geom = QgsGeometry()
            geom.addPart([QgsPointXY(ext.upperLeftPt().x(),cen.y()), QgsPointXY(ext.lowerRightPt().x(), cen.y())],
                          Qgis.Line)
            geom.addPart([QgsPointXY(cen.x(), ext.upperLeftPt().y()), QgsPointXY(cen.x(), ext.lowerRightPt().y())],
                          Qgis.Line)
            self.rubberband.addGeometry(geom, None)
            self.rubberband.show()
            #remove crosshair after 0.1 sec
            QTimer.singleShot(100, self.hideRubberband)

        self.sigProfileRequest.emit(SpatialPoint(crs, geoPoint), self.mCanvas)

    def hideRubberband(self):
        self.rubberband.reset()

"""

class SpectralProfilePlotDataItem(PlotDataItem):

    def __init__(self, spectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super(SpectralProfilePlotDataItem, self).__init__()
        self.mProfile = spectralProfile

        self.setData(x=spectralProfile.xValues(), y=spectralProfile.yValues())
        self.setStyle(self.mProfile.style())
    def setClickable(self, b, width=None):
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)


    def setStyle(self, style):
        assert isinstance(style, PlotStyle)
        self.setVisible(style.isVisible())

        self.setSymbol(style.markerSymbol)
        self.setSymbolBrush(style.markerBrush)
        self.setSymbolSize(style.markerSize)
        self.setSymbolPen(style.markerPen)
        self.setPen(style.linePen)


    def setColor(self, color):
        if not isinstance(color, QColor):
            color = QColor(color)
        self.setPen(color)

    def pen(self):
        return fn.mkPen(self.opts['pen'])

    def color(self):
        return self.pen().color()

    def setLineWidth(self, width):
        from pyqtgraph.functions import mkPen
        pen = mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)


class SpectralProfile(QgsFeature):

    crs = QgsCoordinateReferenceSystem('EPSG:4326')

    @staticmethod
    def fromMapCanvas(mapCanvas, position):
        """
        Returns a list of Spectral Profiles the raster layers in QgsMapCanvas mapCanvas.
        :param mapCanvas:
        :param position:
        """
        assert isinstance(mapCanvas, QgsMapCanvas)

        from timeseriesviewer.mapcanvas import MapCanvas
        if isinstance(mapCanvas, MapCanvas):
            sources = mapCanvas.layerModel().rasterLayerInfos()
            sources = [s.mSrc for s in sources]
        else:
            layers = [l for l in mapCanvas.layers() if isinstance(l, QgsRasterLayer)]
            sources = [l.source() for l in layers]
        return SpectralProfile.fromRasterSources(sources, position)

    @staticmethod
    def fromRasterSources(sources, position):
        """
        Returns a list of Spectral Profiles
        :param sources: list-of-raster-sources, e.g. file paths, gdal.Datasets, QgsRasterLayers
        :param position:
        :return:
        """
        profiles = [SpectralProfile.fromRasterSource(s, position) for s in sources]
        return [p for p in profiles if isinstance(p, SpectralProfile)]


    @staticmethod
    def fromRasterSource(source, position):
        """
        Returns the Spectral Profiles from source at position `position`
        :param source: path or gdal.Dataset
        :param position:
        :return: SpectralProfile
        """

        ds = gdalDataset(source)

        files = ds.GetFileList()
        if len(files) > 0:
            baseName = os.path.basename(files[0])
        else:
            baseName = 'Spectrum'
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())
        gt = ds.GetGeoTransform()

        if isinstance(position, QPoint):
            px = position
        elif isinstance(position, SpatialPoint):
            px = geo2px(position.toCrs(crs), gt)
        elif isinstance(position, QgsPointXY):
            px = geo2px(position, ds.GetGeoTransform())
        else:
            raise Exception('Unsupported type of argument "position" {}'.format('{}'.format(position)))
        #check out-of-raster
        if px.x() < 0 or px.y() < 0: return None
        if px.x() > ds.RasterXSize - 1 or px.y() > ds.RasterYSize - 1: return None


        values = ds.ReadAsArray(px.x(), px.y(), 1, 1)

        values = values.flatten()
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b+1)
            nodata = band.GetNoDataValue()
            if nodata and values[b] == nodata:
                return None

        wl = ds.GetMetadataItem(str('wavelength'), str('ENVI'))
        wlu = ds.GetMetadataItem(str('wavelength_units'), str('ENVI'))
        if wl is not None and len(wl) > 0:
            wl = re.sub(r'[ {}]','', wl).split(',')
            wl = [float(w) for w in wl]

        profile = SpectralProfile()
        profile.setName('{} x{} y{}'.format(baseName, px.x(), px.y()))
        #profile.setValues(values, valuePositions=wl, valuePositionUnit=wlu)
        profile.setYValues(values)
        if wl is not None:
            profile.setXValues(wl, unit=wlu)

        profile.setCoordinates(px=px, pt=SpatialPoint(crs, px2geo(px, gt)))
        profile.setSource('{}'.format(ds.GetFileList()[0]))
        return profile




    @staticmethod
    def fromSpecLibFeature(feature):
        assert isinstance(feature, QgsFeature)
        sp = SpectralProfile(fields=feature.fields())
        sp.setId(feature.id())
        sp.setAttributes(feature.attributes())
        sp.setGeometry(feature.geometry())
        return sp

    XVALUES_FIELD = HIDDEN_ATTRIBUTE_PREFIX+'xvalues'
    YVALUES_FIELD = HIDDEN_ATTRIBUTE_PREFIX + 'yvalues'
    STYLE_FIELD = HIDDEN_ATTRIBUTE_PREFIX + 'style'



    def __init__(self, parent=None, fields=None, xUnit='index', yUnit=None):

        if fields is None:
            fields = createStandardFields()

        #QgsFeature.__init__(self, fields)
        #QObject.__init__(self)
        super(SpectralProfile, self).__init__(fields)
        #QObject.__init__(self)
        fields = self.fields()
        assert isinstance(fields, QgsFields)

        self.setXUnit(xUnit)
        self.setYUnit(yUnit)
        self.setStyle(DEFAULT_SPECTRUM_STYLE)


    def fieldNames(self):
        return self.fields().names()

    def setName(self, name:str):
        if name != self.name():
            self.setAttribute('name', name)
            #self.sigNameChanged.emit(name)

    def name(self):
        return self.metadata('name')

    def setSource(self, uri: str):
        self.setAttribute('source', uri)

    def source(self):
        return self.metadata('source')

    def setCoordinates(self, px=None, pt=None):
        if isinstance(px, QPoint):

            self.setAttribute('px_x', px.x())
            self.setAttribute('px_y', px.y())

        if isinstance(pt, SpatialPoint):
            sp = pt.toCrs(SpectralProfile.crs)
            self.setGeometry(QgsGeometry.fromPointXY(sp))

    def pxCoordinate(self):
        x = self.attribute('px_x')
        y = self.attribute('px_y')
        if x == None or y == None:
            return None
        return QPoint(x, y)

    def geoCoordinate(self):
        return self.geometry()

    def isValid(self):
        return len(self.mValues) > 0 and self.mValueUnit is not None


    def setXValues(self, values, unit=None):
        if isinstance(values, np.ndarray):
            values = values.tolist()
        assert isinstance(values, list)

        self.setMetadata(SpectralProfile.XVALUES_FIELD, values)

        if isinstance(unit, str):
            self.setMetadata('x_unit', unit)

    def setYValues(self, values, unit=None):
        if isinstance(values, np.ndarray):
            values = values.tolist()
        assert isinstance(values, list)
        self.setMetadata(SpectralProfile.YVALUES_FIELD, values)
        if isinstance(unit, str):
            self.setMetadata('y_unit', unit)

        if self.xValues() is None:
            self.setXValues(list(range(len(values))), unit='index')

    def style(self):
        return self.metadata(SpectralProfile.STYLE_FIELD)

    def setStyle(self, style):
        assert isinstance(style, PlotStyle)
        self.setMetadata(SpectralProfile.STYLE_FIELD, style)

    def updateMetadata(self, metaData):
        if isinstance(metaData, dict):
            for key, value in metaData.items():
                self.setMetadata(key, value)

    def removeField(self, name):
        fields = self.fields()
        values = self.attributes()
        i = self.fieldNameIndex(name)
        if i >= 0:
            fields.remove(i)
            values.pop(i)
            self.setFields(fields)
            self.setAttributes(values)

    def setMetadata(self, key: str, value, addMissingFields=False):
        """

        :param key: Name of metadata field
        :param value: value to add. Need to be of type None, str, int or float.
        :param addMissingFields: Set on True to add missing fields (in case value is not None)
        :return:
        """
        i = self.fieldNameIndex(key)

        if key.startswith('__serialized__'):
            if value is not None:
                value = pickle.dumps(value)

        if i < 0:
            if value is not None and addMissingFields:

                fields = self.fields()
                values = self.attributes()
                if key.startswith('__serialized__'):
                    fields.append(createQgsField(key, ''))
                else:
                    fields.append(createQgsField(key, value))
                values.append(value)
                self.setFields(fields)
                self.setAttributes(values)

            return False
        else:
            return self.setAttribute(key, value)

    def metadata(self, key: str, default=None):

        assert isinstance(key, str)
        i = self.fieldNameIndex(key)
        if i < 0:
            return None

        v = self.attribute(i)
        if v == QVariant(None):
            v = None

        if key.startswith('__serialized__') and v != None:
            v = pickle.loads(v)

        return default if v is None else v

    def xValues(self):
        return self.metadata(SpectralProfile.XVALUES_FIELD)


    def yValues(self):
        return self.metadata(SpectralProfile.YVALUES_FIELD)

    def setXUnit(self, unit : str='index'):
        self.setMetadata('x_unit', unit)

    def xUnit(self):
        return self.metadata('x_unit', 'index')

    def setYUnit(self, unit:str=None):
        self.setMetadata('y_unit', unit)

    def yUnit(self):
        return self.metadata('y_unit', None)

    def copyFieldSubset(self, fields):

        sp = SpectralProfile(fields=fields)

        fieldsInCommon = [field for field in sp.fields() if field in self.fields()]

        sp.setGeometry(self.geometry())
        sp.setId(self.id())

        for field in fieldsInCommon:
            assert isinstance(field, QgsField)
            i = sp.fieldNameIndex(field.name())
            sp.setAttribute(i, self.attribute(field.name()))
        return sp

    def clone(self):

        sp = SpectralProfile(fields=self.fields())
        sp.setAttributes(self.attributes())
        return sp

    def plot(self):
        """
        Plots this profile to an new PyQtGraph window
        :return:
        """
        import pyqtgraph as pg

        pi = SpectralProfilePlotDataItem(self)
        pi.setClickable(True)
        pw = pg.plot( title=self.name())
        pw.plotItem().addItem(pi)

        pi.setColor('green')
        pg.QAPP.exec_()


    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        r = QVariant(None)
        attributes = [None if v == r else v for v  in self.attributes()]

        state = (self.__dict__, attributes)
        return pickle.dumps(state)

    def __setstate__(self, state):
        state = pickle.loads(state)
        d, a = state

        self.__dict__.update(d)
        self.setAttributes(a)

    def __copy__(self):
        sp = SpectralProfile(fields=self.fields())
        sp.setAttributes(self.attributes())
        return sp

    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        return np.array_equal(self.attributes(), other.attributes())

    def __hash__(self):

        return hash(id(self))

    """
    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if len(self.mValues) != len(other.mValues):
            return False
        return all(a == b for a,b in zip(self.mValues, other.mValues)) \
            and self.mValuePositions == other.mValuePositions \
            and self.mValueUnit == other.mValueUnit \
            and self.mValuePositionUnit == other.mValuePositionUnit \
            and self.mGeoCoordinate == other.mGeoCoordinate \
            and self.mPxCoordinate == other.mPxCoordinate

    def __ne__(self, other):
        return not self.__eq__(other)
    """
    def __len__(self):
        return len(self.mValues)



class AbstractSpectralLibraryIO(object):
    """
    Abstract Class to define I/O operations for spectral libraries
    Overwrite the canRead and read From routines.
    """
    @staticmethod
    def canRead(path):
        """
        Returns true if it can reath the source definded by path
        :param path: source uri
        :return: True, if source is readibly
        """
        return False

    @staticmethod
    def readFrom(path):
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """
        return None

    @staticmethod
    def write(speclib, path):
        """Writes the SpectralLibrary to path and returns a list of written files that can be used to open the Speclibs with readFrom"""
        assert isinstance(speclib, SpectralLibrary)
        return []

MIMEDATA_SPECLIB = 'application/hub-spectrallibrary'
MIMEDATA_XQT_WINDOWS_CSV = 'application/x-qt-windows-mime;value="Csv"'
MIMEDATA_TEXT = 'text/html'


def saveEdits(layer, leaveEditable=True, triggerRepaint=True):
    """
    function to save layer changes-
    :param layer:
    :param leaveEditable:
    :param triggerRepaint:
    """
    if isinstance(layer, QgsVectorLayer):
        if not layer.isEditable():
            return
        if not layer.commitChanges():
            layer.commitErrors()

        if leaveEditable:
            layer.startEditing()

        if triggerRepaint:
            layer.triggerRepaint()


def deleteSelected(layer):

    assert isinstance(layer, QgsVectorLayer)
    b = layer.isEditable()

    layer.startEditing()
    layer.deleteSelectedFeatures()
    saveEdits(layer, leaveEditable=b)

class ClipboardIO(AbstractSpectralLibraryIO):
    """
    Reads and write SpectralLibrary from/to system clipboard.
    """

    FORMATS = [MIMEDATA_SPECLIB, MIMEDATA_XQT_WINDOWS_CSV, MIMEDATA_TEXT]

    class WritingModes(object):

        ALL = 'ALL'
        ATTRIBUTES = 'ATTRIBUTES'
        VALUES = 'VALUES'

        def modes(self):
            return [a for a in dir(self) if not callable(getattr(self, a)) and not a.startswith("__")]

    @staticmethod
    def canRead(path=None):
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        assert isinstance(mimeData, QMimeData)
        for format in mimeData.formats():
            if format in ClipboardIO.FORMATS:
                return True
        return False

    @staticmethod
    def readFrom(path=None):
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        assert isinstance(mimeData, QMimeData)

        if MIMEDATA_SPECLIB in mimeData.formats():
            b = mimeData.data(MIMEDATA_SPECLIB)
            speclib = pickle.loads(b)
            assert isinstance(speclib, SpectralLibrary)
            return speclib

        return SpectralLibrary()

    @staticmethod
    def write(speclib, path=None, mode=None, sep=None, newline=None):
        if mode is None:
            mode = ClipboardIO.WritingModes.ALL
        assert isinstance(speclib, SpectralLibrary)

        mimeData = QMimeData()


        if not isinstance(sep, str):
            sep = '\t'

        if not isinstance(newline, str):
            newline = '\r\n'


        csvlines = []
        fields = speclib.fields()

        attributeIndices = [i for i, name in zip(fields.allAttributesList(), fields.names())
                            if not name.startswith(HIDDEN_ATTRIBUTE_PREFIX)]

        skipGeometry = mode == ClipboardIO.WritingModes.VALUES
        skipAttributes = mode == ClipboardIO.WritingModes.VALUES
        skipValues = mode == ClipboardIO.WritingModes.ATTRIBUTES

        for p in speclib.profiles():
            assert isinstance(p, SpectralProfile)
            line = []

            if not skipGeometry:
                x = ''
                y = ''
                if p.hasGeometry():
                    g = p.geometry().constGet()
                    if isinstance(g, QgsPoint):
                        x, y = g.x(), g.y()
                    else:
                        x = g.asWkt()

                line.extend([x, y])

            if not skipAttributes:
                line.extend([p.attributes()[i] for i in attributeIndices])

            if not skipValues:
                yValues = p.yValues()
                if isinstance(yValues, list):
                    line.extend(yValues)

            formatedLine = []
            excluded = [QVariant(), None]
            for value in line:
                if value in excluded:
                    formatedLine.append('')
                else:
                    if type(value) in [float, int]:
                        value = locale.str(value)
                    formatedLine.append(value)
            csvlines.append(sep.join(formatedLine))
        text = newline.join(csvlines)

        ba = QByteArray()
        ba.append(text)

        mimeData.setText(text)
        mimeData.setData(MIMEDATA_XQT_WINDOWS_CSV, ba)
        mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(speclib))
        QApplication.clipboard().setMimeData(mimeData)

        return []

class CSVWriterFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):
    """
    A QgsVectorFileWriter.FieldValueConverter to convers SpectralLibrary values into strings
    """
    def __init__(self, speclib):
        super(CSVWriterFieldValueConverter, self).__init__()
        self.mSpeclib = speclib
        self.mNames = self.mSpeclib.fields().names()
        self.mCharactersToReplace = '\t'
        self.mReplacement = ' '

    def setSeparatorCharactersToReplace(self, charactersToReplace, replacement:str= ' '):
        """
        Specifies characters that need to be masked in string, i.e. the separator, to not violate the CSV structure.
        :param charactersToReplace: str | list of strings
        :param replacement: str, Tabulator by default
        """
        if isinstance(charactersToReplace, str):
            charactersToReplace = [charactersToReplace]
        assert replacement not in charactersToReplace
        self.mCharactersToReplace = charactersToReplace
        self.mReplacement = replacement

    def clone(self):
        c = CSVWriterFieldValueConverter(self.mSpeclib)
        c.setSeparatorCharactersToReplace(self.mCharactersToReplace, replacement=self.mReplacement)
        return c

    def convert(self, i, value):
        name = self.mNames[i]
        if name.startswith(HIDDEN_ATTRIBUTE_PREFIX):
            return str(pickle.loads(value))
        else:

            v = str(value)
            for c in self.mCharactersToReplace:
                v = v.replace(c, self.mReplacement)
            return v

    def fieldDefinition(self, field):
        return field

class CSVSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    SpectralLibrary IO with CSV files.
    """
    STD_NAMES = ['WKT']+[n for n in createStandardFields().names() if not n.startswith(HIDDEN_ATTRIBUTE_PREFIX)]
    REGEX_HEADERLINE = re.compile('^'+'\\t'.join(STD_NAMES)+'\\t.*')
    REGEX_BANDVALUE_COLUMN = re.compile('^b(?P<band>\d+)[ _]*(?P<xvalue>-?\d+\.?\d*)?[ _]*(?P<xunit>\D+)?')

    @staticmethod
    def canRead(path=None):
        if not isinstance(path, str):
            return False

        found = False
        try:
            f = open(path, 'r', encoding='utf-8')
            for line in f:
                if CSVSpectralLibraryIO.REGEX_HEADERLINE.search(line):
                    found = True
                    break
            f.close()
        except Exception:
            return False
        return found

    @staticmethod
    def write(speclib, path, dialect=csv.excel_tab):
        assert isinstance(speclib, SpectralLibrary)

        text = CSVSpectralLibraryIO.asString(speclib, dialect=dialect)
        file = open(path, 'w')
        file.write(text)
        file.close()
        return [path]

    @staticmethod
    def readFrom(path=None, dialect=csv.excel_tab):
        f = open(path, 'r', encoding='utf-8')
        text = f.read()
        f.close()

        return CSVSpectralLibraryIO.fromString(text, dialect=dialect)

    @staticmethod
    def fromString(text:str, dialect=csv.excel_tab):
        # divide the text into blocks of CSV rows with same columns structure
        lines = text.splitlines(keepends=True)
        blocks = []
        currentBlock = ''
        for line in lines:
            assert isinstance(line, str)
            if len(line.strip()) == 0:
                continue
            if CSVSpectralLibraryIO.REGEX_HEADERLINE.search(line):
                if len(currentBlock) > 1:
                    blocks.append(currentBlock)

                #start new block
                currentBlock = line
            else:
                currentBlock += line
        if len(currentBlock) > 1:
            blocks.append(currentBlock)
        if len(blocks) == 0:
            return None

        SLIB = SpectralLibrary()
        SLIB.startEditing()

        #read and add CSV blocks
        for block in blocks:
            R = csv.DictReader(block.splitlines(), dialect=dialect)

            #read entire CSV table
            columnVectors = {}
            for n in R.fieldnames:
                columnVectors[n] = []

            nProfiles = 0
            for i, row in enumerate(R):
                for k, v in row.items():
                    columnVectors[k].append(v)
                nProfiles += 1

            #find missing fields, detect data type for and them to the SpectralLibrary
            knownFields = SLIB.fieldNames()
            bandValueColumnNames = sorted([n for n in R.fieldnames
                                       if CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN.match(n)])

            addGeometry = 'WKT' in R.fieldnames
            addYValues = False
            xUnit = None
            xValues = []
            if len(bandValueColumnNames) > 0:
                addYValues = True
                for n in bandValueColumnNames:
                    match = CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN.match(n)
                    xValue = match.group('xvalue')
                    if xUnit == None:
                        # extract unit from first columns that defines one
                        xUnit = match.group('xunit')
                    if xValue:
                        t = findTypeFromString(xValue)
                        xValues.append(toType(t, xValue))



            if len(xValues) > 0 and not len(xValues) == len(bandValueColumnNames):
                print('Inconsistant band value column names. Unable to extract xValues (e.g. wavelength)', file=sys.stderr)
                xValues = None
            elif len(xValues) == 0:
                xValues = None
            missingQgsFields = []

            #find data type of missing fields
            for n in R.fieldnames:
                assert isinstance(n, str)
                if n in knownFields:
                    continue

                #find a none-empty string which describes a
                #data value, get the type for and convert all str values into
                values = columnVectors[n]

                t = str
                v = ''
                for v in values:
                    if len(v) > 0:
                        t = findTypeFromString(v)
                        v = toType(t, v)
                        break
                qgsField = createQgsField(n, v)
                if n in bandValueColumnNames:
                    s = ""

                #convert values to int, float or str
                columnVectors[n] = toType(t, values)
                missingQgsFields.append(qgsField)

            #add missing fields
            if len(missingQgsFields) > 0:
                SLIB.addMissingFields(missingQgsFields)


            #create a feature for each row
            for i in range(nProfiles):
                p = SpectralProfile(fields=SLIB.fields())
                if addGeometry:
                    g = QgsGeometry.fromWkt(columnVectors['WKT'][i])
                    p.setGeometry(g)

                if addYValues:
                    yvalues = [columnVectors[n][i] for n in bandValueColumnNames]
                    p.setYValues(yvalues)
                    p.setXUnit(xUnit)
                    if xValues:
                        p.setXValues(xValues)

                SLIB.addFeature(p)


        SLIB.commitChanges()
        return SLIB


    @staticmethod
    def asString(speclib, dialect=csv.excel_tab, skipValues=False, skipGeometry=False):

        assert isinstance(speclib, SpectralLibrary)

        attributeNames = [n for n in speclib.fieldNames()
                            if not n.startswith(HIDDEN_ATTRIBUTE_PREFIX)]

        stream = io.StringIO()
        for i, item in enumerate(speclib.groupBySpectralProperties().items()):

            xvalues, xunit, yunit = pickle.loads(item[0])
            profiles = item[1]
            attributeNames = attributeNames[:]


            if xunit == 'index':
                valueNames = ['b{}'.format(b + 1) for b in range(len(xvalues))]
            else:
                valueNames = ['b{}_{}{}'.format(b + 1, xvalue, xunit) for b, xvalue in enumerate(xvalues)]


            fieldnames = []
            if not skipGeometry:
                fieldnames += ['WKT']
            fieldnames += attributeNames
            if not skipGeometry:
                fieldnames += valueNames

            W = csv.DictWriter(stream, fieldnames=fieldnames, dialect=dialect)
            W.writeheader()

            for p in profiles:
                assert isinstance(p, SpectralProfile)
                D = dict()

                if not skipGeometry:
                    D['WKT'] = p.geometry().asWkt()

                for n in attributeNames:
                    D[n] = value2str(p.attribute(n))

                if not skipValues:
                    for i, yValue in enumerate(p.yValues()):
                        D[valueNames[i]] = yValue

                W.writerow(D)
            W.writerow({}) #append empty row


        return stream.getvalue()


class EnviSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    IO of ENVI Spectral Libraries
    see http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for format description
    Additional profile metadata is written to/read from a *.csv of same base name as the ESL
    """

    REQUIRED_TAGS = ['byte order', 'data type', 'header offset', 'lines', 'samples', 'bands']
    SINGLE_VALUE_TAGS = REQUIRED_TAGS + ['description', 'wavelength', 'wavelength units']

    @staticmethod
    def canRead(pathESL):
        """
        Checks if a file can be read as SpectraLibrary
        :param pathESL: path to ENVI Spectral Library (ESL)
        :return: True, if pathESL can be read as Spectral Library.
        """
        assert isinstance(pathESL, str)
        if not os.path.isfile(pathESL):
            return False
        hdr = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=False)
        if hdr is None or hdr['file type'] != 'ENVI Spectral Library':
            return False
        return True

    @staticmethod
    def readFrom(pathESL, tmpVrt=None):
        """
        Reads an ENVI Spectral Library (ESL).
        :param pathESL: path ENVI Spectral Library
        :param tmpVrt: (optional) path of GDAL VRT that is used internally to read the ESL
        :return: SpectralLibrary
        """
        assert isinstance(pathESL, str)
        md = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=True)

        data = None

        createTmpFile = tmpVrt == None
        if createTmpFile:
            tmpVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt', dir='/vsimem/')

        ds = EnviSpectralLibraryIO.esl2vrt(pathESL, tmpVrt)
        data = ds.ReadAsArray()

        #remove the temporary VRT, as it was created internally only
        if createTmpFile:
            ds.GetDriver().Delete(ds.GetFileList()[0])
            ds = None

        #check for additional CSV to enhance profile descriptions
        pathCSV = os.path.splitext(pathESL)[0] + '.csv'
        hasCSV = os.path.isfile(pathCSV)

        nSpectra, nbands = data.shape
        yUnit = None
        xUnit = md.get('wavelength units')
        xValues = md.get('wavelength')
        if xValues is None:
            xValues = list(range(1, nbands + 1))
            xUnit = 'index'

        #get offical ENVI Spectral Library standard values
        spectraNames = md.get('spectra names', ['Spectrum {}'.format(i+1) for i in range(nSpectra)])

        SLIB = SpectralLibrary()
        SLIB.startEditing()

        profiles = []
        for i in range(nSpectra):
            p = SpectralProfile(fields=SLIB.fields())
            p.setXValues(xValues)
            p.setYValues(data[i,:])
            p.setXUnit(xUnit)
            p.setYUnit(yUnit)
            p.setName(spectraNames[i])
            profiles.append(p)
        SLIB.addProfiles(profiles)

        if hasCSV: #we have a CSV with additional metadata. Let's add it to the profiles

            SL_CSV = CSVSpectralLibraryIO.readFrom(pathCSV)

            assert len(SL_CSV) == len(SLIB), 'Inconsistent CSV: number of rows not equal to number of spectra in *.hdr {}. '.format(pathCSV)

            #update fields
            SLIB.addMissingFields(SL_CSV.fields())

            #update feature field values

            fieldNamesToUpdate = [n for n in SL_CSV.fieldNames() if not n.startswith(HIDDEN_ATTRIBUTE_PREFIX)]


            for p1, p2 in zip(SLIB.profiles(), SL_CSV.profiles()):
                assert isinstance(p1, SpectralProfile)
                assert isinstance(p2, SpectralProfile)

                assert p1.id() == p2.id()

                p1.setGeometry(p2.geometry())
                for n in fieldNamesToUpdate:
                    p1.setAttribute(n, p2.attribute(n))
                SLIB.updateFeature(p1)

            if False:
                drv = ogr.GetDriverByName('CSV')
                assert isinstance(drv, ogr.Driver)

                ds = drv.Open(pathCSV)
                assert isinstance(ds, ogr.DataSource)
                lyr = ds.GetLayer(0)
                assert isinstance(lyr, ogr.Layer)
                assert lyr.GetFeatureCount() == nSpectra

                fieldData = {}
                for i in range(lyr.GetLayerDefn().GetFieldCount()):
                    fieldData[lyr.GetLayerDefn().GetFieldDefn(i).GetName()] = []
                fieldNames = list(fieldData.keys())
                fieldList = []

                feature = lyr.GetNextFeature()
                while isinstance(feature, ogr.Feature):
                    for name in fieldNames:
                        fieldData[name].append(feature.GetFieldAsString(name).strip())
                    feature = lyr.GetNextFeature()

                #replace empty values by None and convert values to most-likely basic python data type
                for fieldName in fieldNames:
                    if fieldName in ['WKT']:
                        continue
                    values = fieldData[fieldName]
                    qgsField = None
                    for v in values:
                        if len(v) > 0:
                            t = findTypeFromString(v)
                            v = toType(t, v)
                            qgsField = createQgsField(fieldName, v)
                            break
                    if qgsField == None:
                        qgsField = createQgsField(fieldName, '')

                    values = [toType(t, v) if len(v) > 0 else None for v in values]
                    fieldList.append(qgsField)
                    fieldData[fieldName] = values

                #add the fields to the speclib
                SLIB.addMissingFields(fieldList)
                addGeometryWKT = 'WKT' in fieldNames

                for i, feature in enumerate(SLIB.getFeatures()):
                    assert isinstance(feature, QgsFeature)

                    if addGeometryWKT:
                        wkt = fieldData['WKT'][i]
                        g = QgsGeometry.fromWkt(wkt)
                        feature.setGeometry(g)

                    for field in fieldList:
                        fn = field.name()
                        feature.setAttribute(fn, fieldData[fn][i])

                SLIB.updateFeature(feature)

        SLIB.commitChanges()
        assert SLIB.featureCount() == nSpectra
        return SLIB

    @staticmethod
    def write(speclib, path, ext='sli'):
        """
        Writes a SpectralLibrary as ENVI Spectral Library (ESL).
        See http://www.harrisgeospatial.com/docs/ENVIHeaderFiles.html for ESL definition

        Additional attributes (coordinate, user-defined attributes) will be written into a CSV text file with same basename

        For example the path myspeclib.sli leads to:

            myspeclib.sli <- ESL binary file
            myspeclib.hdr <- ESL header file
            myspeclib.csv <- CSV text file, tabulator separated columns (for being used in Excel)


        :param speclib: SpectralLibrary
        :param path: str
        :param ext: str, ESL file extension of, e.g. .sli (default) or .esl
        """
        assert isinstance(path, str)
        assert ext != 'csv'
        dn = os.path.dirname(path)
        bn = os.path.basename(path)

        writtenFiles = []

        if bn.lower().endswith(ext.lower()):
            bn = os.path.splitext(bn)[0]

        if not os.path.isdir(dn):
            os.makedirs(dn)

        def value2hdrString(values):
            """
            Converts single values or a list of values into an ENVI header string
            :param values: valure or list-of-values, e.g. int(23) or [23,42]
            :return: str, e.g. "23" in case of a single value or "{23,42}" in case of list values
            """
            s = None
            maxwidth = 75

            if isinstance(values, list):
                lines = ['{']
                values = ['{}'.format(v).replace(',','-') for v in values]
                line = ' '
                l = len(values)
                for i, v in enumerate(values):
                    line += v
                    if i < l-1: line += ', '
                    if len(line) > maxwidth:
                        lines.append(line)
                        line = ' '
                line += '}'
                lines.append(line)
                s = '\n'.join(lines)

            else:
                s = '{}'.format(values)

            return s

        initialSelection = speclib.selectedFeatureIds()

        for iGrp, grp in enumerate(speclib.groupBySpectralProperties().values()):

            if len(grp) == 0:
                continue

            wl = grp[0].xValues()
            wlu = grp[0].xUnit()

            fids = [p.id() for p in grp]

            # stack profiles
            pData = [np.asarray(p.yValues()) for p in grp]
            pData = np.vstack(pData)

            #convert array to data types GDAL can handle
            if pData.dtype == np.int64:
                pData = pData.astype(np.int32)

            pNames = [p.name() for p in grp]

            if iGrp == 0:
                pathDst = os.path.join(dn, '{}.{}'.format(bn, ext))
            else:
                pathDst = os.path.join(dn, '{}.{}.{}'.format(bn, iGrp, ext))

            drv = gdal.GetDriverByName('ENVI')
            assert isinstance(drv, gdal.Driver)


            eType = gdal_array.NumericTypeCodeToGDALTypeCode(pData.dtype)
            """Create(utf8_path, int xsize, int ysize, int bands=1, GDALDataType eType, char ** options=None) -> Dataset"""
            ds = drv.Create(pathDst, pData.shape[1], pData.shape[0], 1, eType)
            band = ds.GetRasterBand(1)
            assert isinstance(band, gdal.Band)
            band.WriteArray(pData)

            #ds = gdal_array.SaveArray(pData, pathDst, format='ENVI')

            assert isinstance(ds, gdal.Dataset)
            ds.SetDescription(speclib.name())
            ds.SetMetadataItem('band names', 'Spectral Library', 'ENVI')
            ds.SetMetadataItem('spectra names',value2hdrString(pNames), 'ENVI')
            ds.SetMetadataItem('wavelength', value2hdrString(wl), 'ENVI')
            ds.SetMetadataItem('wavelength units', wlu, 'ENVI')

            fieldNames = ds.GetMetadata_Dict('ENVI').keys()
            fieldNames = [n for n in speclib.fields().names() if n not in fieldNames and not n.startswith(HIDDEN_ATTRIBUTE_PREFIX)]

            for a in fieldNames:
                v = value2hdrString([p.metadata(a) for p in grp])
                ds.SetMetadataItem(a, v, 'ENVI')

            pathHDR = ds.GetFileList()[1]
            pathCSV = os.path.splitext(pathHDR)[0]+'.csv'
            ds = None

            # re-write ENVI Hdr with file type = ENVI Spectral Library
            file = open(pathHDR)
            hdr = file.readlines()
            file.close()

            for iLine in range(len(hdr)):
                if re.search('file type =', hdr[iLine]):
                    hdr[iLine] = 'file type = ENVI Spectral Library\n'
                    break

            file = open(pathHDR, 'w', encoding='utf-8')
            file.writelines(hdr)
            file.flush()
            file.close()

            # write none-spectral data into CSV
            speclib.selectByIds(fids)
            fieldNames = [n for n in speclib.fieldNames() if not n.startswith(HIDDEN_ATTRIBUTE_PREFIX)]
            fieldIndices = [grp[0].fieldNameIndex(n) for n in fieldNames]

            sep = '\t'
            fwc = CSVWriterFieldValueConverter(speclib)
            fwc.setSeparatorCharactersToReplace([sep, ','], ' ') #replaces the separator in string by ' '

            #test ogr CSV driver options
            drv = ogr.GetDriverByName('CSV')
            optionXML = drv.GetMetadataItem('DMD_CREATIONOPTIONLIST')

            canWriteTAB = '<Value>TAB</Value>' in optionXML
            canWriteXY = '<Value>AS_XY</Value>' in optionXML
            co = []
            if canWriteTAB:
                co.append('SEPARATOR=TAB')
            if canWriteXY:
                co.append('GEOMETRY=AS_XY')
            else:
                co.append('GEOMETRY=AS_WKT')

            exitStatus, error = QgsVectorFileWriter.writeAsVectorFormat(speclib, pathCSV, 'utf-8', speclib.crs(), 'CSV',
                                                         fieldValueConverter=fwc,
                                                         onlySelected=True,
                                                         datasourceOptions=co,
                                                         attributes=fieldIndices)

            if False and not all([canWriteTAB, canWriteXY]):
                file = open(pathCSV,'r',encoding='utf-8')
                lines = file.readlines()
                file.close()

                if not canWriteTAB:
                    lines = [l.replace(',', sep) for l in lines]

                if not canWriteXY:
                    pass
                file = open(pathCSV, 'w', encoding='utf-8')
                file.writelines(lines)
                file.close()

            writtenFiles.append(pathDst)

        #restore initial feature selection
        speclib.selectByIds(initialSelection)

        return writtenFiles


    @staticmethod
    def esl2vrt(pathESL, pathVrt=None):
        """
        Creates a GDAL Virtual Raster (VRT) that allows to read an ENVI Spectral Library file
        :param pathESL: path ENVI Spectral Library file (binary part)
        :param pathVrt: (optional) path of created GDAL VRT.
        :return: GDAL VRT
        """

        hdr = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=False)
        assert hdr is not None and hdr['file type'] == 'ENVI Spectral Library'

        if hdr.get('file compression') == '1':
            raise Exception('Can not read compressed spectral libraries')

        eType = LUT_IDL2GDAL[int(hdr['data type'])]
        xSize = int(hdr['samples'])
        ySize = int(hdr['lines'])
        bands = int(hdr['bands'])
        byteOrder = 'LSB' if int(hdr['byte order']) == 0 else 'MSB'

        if pathVrt is None:
            id = uuid.UUID()
            pathVrt = '/vsimem/{}.esl.vrt'.format(id)
            #pathVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt')


        ds = describeRawFile(pathESL, pathVrt, xSize, ySize, bands=bands, eType=eType, byteOrder=byteOrder)
        for key, value in hdr.items():
            if isinstance(value, list):
                value = u','.join(v for v in value)
            ds.SetMetadataItem(key, value, 'ENVI')
        ds.FlushCache()
        return ds


    @staticmethod
    def readENVIHeader(pathESL, typeConversion=False):
        """
        Reads an ENVI Header File (*.hdr) and returns its values in a dictionary
        :param pathESL: path to ENVI Header
        :param typeConversion: Set on True to convert values related to header keys with numeric
        values into numeric data types (int / float)
        :return: dict
        """
        assert isinstance(pathESL, str)
        if not os.path.isfile(pathESL):
            return None

        pathHdr = EnviSpectralLibraryIO.findENVIHeader(pathESL)
        if pathHdr is None:
            return None


        #hdr = open(pathHdr).readlines()
        file = open(pathHdr, encoding='utf-8')
        hdr = file.readlines()
        file.close()

        i = 0
        while i < len(hdr):
            if '{' in hdr[i]:
                while not '}' in hdr[i]:
                    hdr[i] = hdr[i] + hdr.pop(i + 1)
            i += 1

        hdr = [''.join(re.split('\n[ ]*', line)).strip() for line in hdr]
        # keep lines with <tag>=<value> structure only
        hdr = [line for line in hdr if re.search('^[^=]+=', line)]

        # restructure into dictionary of type
        # md[key] = single value or
        # md[key] = [list-of-values]
        md = dict()
        for line in hdr:
            tmp = line.split('=')
            key, value = tmp[0].strip(), '='.join(tmp[1:]).strip()
            if value.startswith('{') and value.endswith('}'):
                value = [v.strip() for v in value.strip('{}').split(',')]
            md[key] = value

        # check required metadata tegs
        for k in EnviSpectralLibraryIO.REQUIRED_TAGS:
            if not k in md.keys():
                return None

        if typeConversion:
            to_int = ['bands','lines','samples','data type','header offset','byte order']
            to_float = ['fwhm','wavelength', 'reflectance scale factor']
            for k in to_int:
                if k in md.keys():
                    md[k] = toType(int, md[k])
            for k in to_float:
                if k in md.keys():
                    md[k] = toType(float, md[k])


        return md

    @staticmethod
    def findENVIHeader(pathESL):
        paths = [os.path.splitext(pathESL)[0] + '.hdr', pathESL + '.hdr']
        pathHdr = None
        for p in paths:
            if os.path.exists(p):
                pathHdr = p
        return pathHdr


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None
    def __init__(self, parent=None):
        super(SpectralLibraryPanel, self).__init__(parent)
        self.setObjectName('spectralLibraryPanel')
        self.setWindowTitle('Spectral Library')
        self.SLW = SpectralLibraryWidget(self)
        self.setWidget(self.SLW)


    def speclib(self):
        return self.SLW.speclib()

    def setCurrentSpectra(self, listOfSpectra):
        self.SLW.setCurrentSpectra(listOfSpectra)

    def setAddCurrentSpectraToSpeclibMode(self, b: bool):
        self.SLW.setAddCurrentSpectraToSpeclibMode(b)

class SpectralLibrary(QgsVectorLayer):

    @staticmethod
    def readFromPickleDump(data):
        return pickle.loads(data)

    @staticmethod
    def readFromSourceDialog(parent=None):
        """
        Opens a FileOpen dialog to select
        :param parent:
        :return:
        """

        SETTINGS = settings()
        lastDataSourceDir = SETTINGS.value('_lastSpecLibSourceDir', '')

        if not QFileInfo(lastDataSourceDir).isDir():
            lastDataSourceDir = None

        uris = QFileDialog.getOpenFileNames(parent, "Open spectral library", lastDataSourceDir, filter=FILTERS + ';;All files (*.*)', )
        if isinstance(uris, tuple):
            uris = uris[0]

        if len(uris) > 0:
            SETTINGS.setValue('_lastSpecLibSourceDir', os.path.dirname(uris[-1]))

        uris = [u for u in uris if QFileInfo(u).isFile()]
        speclib = SpectralLibrary()
        for u in uris:
            sl = SpectralLibrary.readFrom(str(u))
            if isinstance(sl, SpectralLibrary):
                speclib.addSpeclib(sl)
        return speclib


    @staticmethod
    def readFromRasterPositions(pathRaster, positions):
        #todo: handle vector file input & geometries
        if not isinstance(positions, list):
            positions = [positions]
        profiles = []
        source = gdal.Open(pathRaster)
        i = 0
        for position in positions:
            profile = SpectralProfile.fromRasterSource(source, position)
            if isinstance(profile, SpectralProfile):
                profile.setName('Spectrum {}'.format(i))
                profiles.append(profile)
                i += 1

        sl = SpectralLibrary()
        sl.addProfiles(profiles)
        return sl

    @staticmethod
    def readFrom(uri):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        for cls in AbstractSpectralLibraryIO.__subclasses__():
            if cls.canRead(uri):
                return cls.readFrom(uri)
        return None


    sigNameChanged = pyqtSignal(str)

    def __init__(self, name='SpectralLibrary', fields=None):
        crs = SpectralProfile.crs
        uri = 'Point?crs={}'.format(crs.authid())
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(SpectralLibrary, self).__init__(uri, name, 'memory', lyrOptions)

        if fields is not None:
            defaultFields = fields
        else:
            defaultFields = createStandardFields()



        assert self.startEditing()
        assert self.dataProvider().addAttributes(defaultFields)
        assert self.commitChanges()
        self.initConditionalStyles()

    def optionalFields(self):
        """
        Returns a list of optional fields.
        """
        standardFields = createStandardFields()
        return [f for f in self.fields() if f not in standardFields]

    def optionalFieldNames(self):
        return [f.name() for f in self.optionalFields()]

    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fieldNames():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])

        red = QgsConditionalStyle('﻿"__serialized__xvalues" is NULL OR "__serialized__yvalues is NULL" ')
        red.setBackgroundColor(QColor('red'))
        styles.setRowStyles([red])


    def addMissingFields(self, fields):
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            i = self.dataProvider().fieldNameIndex(field.name())
            if i == -1:
                missingFields.append(field)
        if len(missingFields) > 0:
            b = self.isEditable()
            self.startEditing()
            self.dataProvider().addAttributes(missingFields)
            saveEdits(self, leaveEditable=b)

    def addSpeclib(self, speclib, addMissingFields=True):
        assert isinstance(speclib, SpectralLibrary)
        if addMissingFields:
            self.addMissingFields(speclib.fields())
        self.addProfiles([p for p in speclib])

    def addProfiles(self, profiles, index : QModelIndex=QModelIndex(), addMissingFields=False):

        if isinstance(profiles, SpectralProfile):
            profiles = [profiles]
        elif isinstance(profiles, SpectralLibrary):
            profiles = profiles[:]

        assert isinstance(profiles, list)
        if len(profiles) == 0:
            return

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        if addMissingFields:
            self.addMissingFields(profiles[0].fields())

        b = self.isEditable()
        self.startEditing()

        if not addMissingFields:
            profiles = [p.copyFieldSubset(self.fields()) for p in profiles]

        assert self.addFeatures(profiles)
        saveEdits(self, leaveEditable=b)

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        if not isinstance(profiles, list):
            profiles = [profiles]

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        fids = [p.id() for p in profiles]
        if len(fids) == 0:
            return

        b = self.isEditable()
        self.startEditing()
        self.deleteFeatures(fids)
        saveEdits(self, leaveEditable=b)


    def features(self, fids=None):
        """
        Returns the QgsFeatures stored in this QgsVectorLayer
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: [List-of-QgsFeatures]
        """
        featureRequest = QgsFeatureRequest()
        if fids is not None:
            if not isinstance(fids, list):
                fids = list(fids)
            featureRequest.setFilterFids(fids)
        # features = [f for f in self.features() if f.id() in fids]
        return list(self.getFeatures(featureRequest))


    def profiles(self, fids=None):
        """
        Like features(fids=None), but converts each returned QgsFeature into a SpectralProfile
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: [List-of-SpectralProfiles]
        """
        return [SpectralProfile.fromSpecLibFeature(f) for f in self.features(fids=fids)]




    def speclibFromFeatureIDs(self, fids):
        sp = SpectralLibrary(fields=self.fields())
        sp.addProfiles(self.profiles(fids))
        return sp

    def groupBySpectralProperties(self, excludeEmptyProfiles = True):
        """
        Groups the SpectralProfiles by:
            wavelength (xValues), wavelengthUnit (xUnit) and yUnit

        :return: {(xValues, wlU, yUnit):[list-of-profiles]}
        """

        d = dict()
        for p in self.profiles():
            #assert isinstance(p, SpectralProfile)
            if excludeEmptyProfiles and p.xValues() in [None, QVariant()]:
                continue

            id = pickle.dumps((p.xValues(), p.xUnit(), p.yUnit()))
            if id not in d.keys():
                d[id] = list()
            d[id].append(p)
        return d


    def asTextLines(self, separator='\t'):
        return CSVSpectralLibraryIO.asString(self, dialect=separator)

    def asPickleDump(self):
        return pickle.dumps(self)

    def exportProfiles(self, path=None, parent=None):

        if path is None:

            path, filter = QFileDialog.getSaveFileName(parent=parent, caption="Save Spectral Library", filter=FILTERS)

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            if ext in ['.sli','.esl']:
                return EnviSpectralLibraryIO.write(self, path)

            if ext in ['.csv']:
                return CSVSpectralLibraryIO.write(self, path)


        return []


    def yRange(self):
        profiles = self.profiles()
        minY = min([min(p.yValues()) for p in profiles])
        maxY = max([max(p.yValues()) for p in profiles])
        return minY, maxY

    def __repr__(self):
        return str(self.__class__) + '"{}" {} feature(s)'.format(self.name(), self.dataProvider().featureCount())

    def plot(self):
        import pyqtgraph as pg
        pg.mkQApp()

        win = pg.GraphicsWindow(title="Spectral Library")
        win.resize(1000, 600)

        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        # Create a plot with some random data
        p1 = win.addPlot(title="Spectral Library {}".format(self.name()), pen=0.5)
        yMin, yMax = self.yRange()
        p1.setYRange(yMin, yMax)

        # Add three infinite lines with labels
        for p in self:
            pi = pg.PlotDataItem(p.xValues(), p.yValues())
            p1.addItem(pi)

        pg.QAPP.exec_()

    def index(self, obj):
        return self.mProfiles.index(obj)

    def fieldNames(self):
        return self.fields().names()

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        profiles = self[:]
        dump = pickle.dumps((self.name(),profiles))
        return dump
        #return self.__dict__.copy()

    def __setstate__(self, state):
        name, profiles = pickle.loads(state)

        self.setName(name)
        self.addProfiles(profiles)



    def __len__(self):
        return self.featureCount()

    def __iter__(self):
        r = QgsFeatureRequest()
        for f in self.getFeatures(r):
            yield SpectralProfile.fromSpecLibFeature(f)

    def __getitem__(self, slice):
        features = self.features()[slice]
        if isinstance(features, list):
            return [SpectralProfile.fromSpecLibFeature(f) for f in features]
        else:
            return SpectralProfile.fromSpecLibFeature(features)

    def __delitem__(self, slice):
        profiles = self[slice]
        self.removeProfiles(profiles)

    def __eq__(self, other):
        if not isinstance(other, SpectralLibrary):
            return False

        if len(self) != len(other):
            return False

        for p1, p2 in zip(self.__iter__(), other.__iter__()):
            if not p1 == p2:
                return False
        return True


class SpectralLibraryTableModel(QgsAttributeTableModel):

    #sigPlotStyleChanged = pyqtSignal(SpectralProfile)
    #sigAttributeRemoved = pyqtSignal(str)
    #sigAttributeAdded = pyqtSignal(str)

    def __init__(self, speclib=None, parent=None):

        if speclib is None:
            speclib = SpectralLibrary()

        cache = QgsVectorLayerCache(speclib, 1000)

        super(SpectralLibraryTableModel, self).__init__(cache, parent)
        self.mSpeclib = speclib
        self.mCache = cache

        assert self.mCache.layer() == self.mSpeclib

        self.loadLayer()

        self.mcnStyle = speclib.fieldNames().index(HIDDEN_ATTRIBUTE_PREFIX+'style')


    def speclib(self):
        sl = self.mSpeclib
        assert isinstance(sl, SpectralLibrary)
        return sl

    def columnNames(self):
        return self.speclib().fieldNames()

    def feature(self, index):

        id = self.rowToId(index.row())
        f = self.layer().getFeature(id)

        return f

    def spectralProfile(self, index):
        feature = self.feature(index)
        return SpectralProfile.fromSpecLibFeature(feature)

    def data(self, index, role=Qt.DisplayRole):
        """
        Returns Spectral Library data
        Use column = 0 and Qt.CheckStateRole to return PlotStyle visibility
        Use column = 0 and Qt.DecorationRole to return QIcon with PlotStyle preview
        Use column = 0 and Qt.UserRole to return entire PlotStyle
        :param index: QModelIndex
        :param role: enum Qt.ItemDataRole
        :return: value
        """
        if role is None or not index.isValid():
            return None

        result = super(SpectralLibraryTableModel,self).data(index, role=role)

        if index.column() == 0 and role in [Qt.CheckStateRole, Qt.DecorationRole, Qt.UserRole]:
            profile = self.spectralProfile(index)
            style = profile.style()
            if isinstance(style, PlotStyle):
                if role == Qt.UserRole:
                    result = style

                if role == Qt.CheckStateRole:
                    result = Qt.Checked if style.isVisible() else Qt.Unchecked

                if role == Qt.DecorationRole:
                    result = style.createIcon(QSize(21,21))

        return result


    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction


    def setData(self, index, value, role=None):
        """
        Sets the Speclib data
        use column 0 and Qt.CheckStateRole to PlotStyle visibility
        use column 0 and Qt.UserRole to set PlotStyle

        :param index: QModelIndex()
        :param value: value to set
        :param role: role
        :return: True | False
        """
        if role is None or not index.isValid():
            return False

        result = False
        speclib = self.layer()
        assert isinstance(speclib, SpectralLibrary)
        if value == None:
            value = QVariant()
        if index.column() == 0 and role in [Qt.CheckStateRole, Qt.UserRole]:
            profile = self.spectralProfile(index)




            if role == Qt.CheckStateRole:
                style = profile.style()
                style.setVisibility(value == Qt.Checked)
                profile.setStyle(style)

            if role == Qt.UserRole and isinstance(value, PlotStyle):
                profile.setStyle(value)

            b = speclib.isEditable()
            speclib.startEditing()
            result = speclib.updateFeature(profile)
            saveEdits(speclib, leaveEditable=b)

            #f = self.layer().getFeature(profile.id())
            #i = f.fieldNameIndex(SpectralProfile.STYLE_FIELD)
            #self.layer().changeAttributeValue(f.id(), i, value)
            #result = super().setData(self.index(index.row(), self.mcnStyle), value, role=Qt.EditRole)
            #if not b:
            #    self.layer().commitChanges()
        if result:
            self.dataChanged.emit(index, index, [role])
        else:
            result = super().setData(index, value, role=role)


        return result

    def supportedDragActions(self):
        return Qt.CopyAction

    def supportedDropActions(self):
        return Qt.CopyAction

    def dropMimeData(self, mimeData, action, row, column, parent):
        assert isinstance(mimeData, QMimeData)
        assert isinstance(parent, QModelIndex)

        if mimeData.hasFormat(mimedata.MDF_SPECTRALLIBRARY):

            dump = mimeData.data(mimedata.MDF_SPECTRALLIBRARY)
            speclib = SpectralLibrary.readFromPickleDump(dump)
            self.mSpecLib.addSpeclib(speclib)
            return True
        return False

    def mimeData(self, indexes):

        if len(indexes) == 0:
            return None

        profiles = self.indices2profiles(indexes)
        speclib = SpectralLibrary(profiles=profiles)
        mimeData = QMimeData()
        mimeData.setData(mimedata.MDF_SPECTRALLIBRARY, speclib.asPickleDump())

        #as text
        mimeData.setText('\n'.join(speclib.asTextLines()))

        return mimeData

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append(mimedata.MDF_DATASOURCETREEMODELDATA)
        #types.append(mimedata.MDF_LAYERTREEMODELDATA)
        types.append(mimedata.MDF_URILIST)
        return types

    def flags(self, index):

        if index.isValid():
            columnName = self.columnNames()[index.column()]
            if columnName.startswith(HIDDEN_ATTRIBUTE_PREFIX):
                return Qt.NoItemFlags
            else:
                flags = super(SpectralLibraryTableModel, self).flags(index) | Qt.ItemIsSelectable
                if index.column() == 0:
                    flags = flags | Qt.ItemIsUserCheckable
                return flags
        return None


class UnitComboBoxItemModel(OptionListModel):
    def __init__(self, parent=None):
        super(UnitComboBoxItemModel, self).__init__(parent)

    def addUnit(self, unit):

        o = Option(unit, unit)
        self.addOption(o)


    def getUnitFromIndex(self, index):
        o = self.idx2option(index)
        assert isinstance(o, Option)
        return o.mValue

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mUnits)) or (index.row() < 0):
            return None
        unit = self.getUnitFromIndex(index)
        value = None
        if role == Qt.DisplayRole:
            value = '{}'.format(unit)
        return value


class SpectralLibraryPlotWidget(PlotWidget):

    def __init__(self, parent=None):
        super(SpectralLibraryPlotWidget, self).__init__(parent)
        self.mModel = None
        self.mPlotItems = dict()
        self.setAntialiasing(True)
        self.setAcceptDrops(True)


    def setModel(self, model):
        assert isinstance(model, SpectralLibraryTableModel)
        self.mModel = model
        speclib = self.speclib()
        assert isinstance(speclib, SpectralLibrary)
        speclib.committedFeaturesAdded.connect(self.onProfilesAdded)
        speclib.committedFeaturesRemoved.connect(self.onProfilesRemoved)
        speclib.committedAttributeValuesChanges.connect(self.onProfileDataChanged)

        self.onProfilesAdded(speclib.id(), speclib[:])

        #self.mModel.rowsAboutToBeRemoved.connect(self.onRowsAboutToBeRemoved)
        #self.mModel.rowsInserted.connect(self.onRowsInserted)
        #self.mModel.dataChanged.connect(self.onDataChanged)
        #if self.mModel.rowCount() > 0:
        #    self.onRowsInserted(self.mModel.index(0,0), 0, self.mModel.rowCount())



    def speclib(self):
        if not isinstance(self.mModel, SpectralLibraryTableModel):
            return None
        return self.mModel.speclib()

    def onProfileDataChanged(self, layerID, changeMap):


        fieldNames = self.speclib().fieldNames()
        iStyle = fieldNames.index(HIDDEN_ATTRIBUTE_PREFIX+'style')

        fids = list(changeMap.keys())
        for fid in fids:
            if iStyle in changeMap[fid].keys():
                #update the local plot style
                style = changeMap[fid].get(iStyle)

                style = pickle.loads(style)

                pdi = self.mPlotItems.get(fid)
                if isinstance(pdi, SpectralProfilePlotDataItem):
                    pdi.setStyle(style)


    def onProfilesAdded(self, layerID, features):

        if len(features) == 0:
            return

        speclib = self.speclib()
        assert isinstance(speclib, SpectralLibrary)

        fids = [f.id() for f in features]
        #remove if existent
        self.onProfilesRemoved(layerID, fids)

        pdis = []
        for feature in features:
            profile = SpectralProfile.fromSpecLibFeature(feature)
            assert isinstance(profile, SpectralProfile)
            pdi = SpectralProfilePlotDataItem(profile)
            self.mPlotItems[pdi.mProfile.id()] = pdi
            pdis.append(pdi)

        for pdi in pdis:
            self.plotItem.addItem(pdi)


    def onProfilesRemoved(self, layerID, fids):

        if len(fids) == 0:
            return
        fids = [fid for fid in fids if fid in list(self.mPlotItems.keys())]
        pdis = [self.mPlotItems.pop(fid) for fid in fids]
        pdis = [pdi for pdi in pdis if isinstance(pdi, SpectralProfilePlotDataItem)]
        for pdi in pdis:
            self.removeItem(pdi)

    def onDataChanged(self, topLeft, bottomRight, roles):

        if topLeft.column() == 0:
            for row in range(topLeft.row(), bottomRight.row()+1):
                fid = self.mModel.rowToId(row)
                idx = self.mModel.idToIndex(fid)
                profile = self.mModel.spectralProfile(idx)

                pdi = self.mPlotItems.get(fid)
                if isinstance(pdi, SpectralProfilePlotDataItem):
                    if len(roles) == 0 or Qt.DecorationRole in roles or Qt.CheckStateRole in roles:
                        pdi.setStyle(profile.style())


    def onRowsAboutToBeRemoved(self, index, first, last):

        fids = [self.mModel.rowToId(i) for i in range(first, last+1)]
        fids = [fid for fid in fids if fid in list(self.mPlotItems.keys())]
        pdis = [self.mPlotItems.pop(fid) for fid in fids]
        pdis = [pdi for pdi in pdis if isinstance(pdi, SpectralProfilePlotDataItem)]
        for pdi in pdis:
            self.removeItem(pdi)

    def onRowsInserted(self, index, first, last):

        for i in range(first, last+1):
            fid = self.mModel.rowToId(i)
            if fid < 0:
                continue

            idx = self.mModel.index(i,0)
            p = self.mModel.spectralProfile(idx)
            assert fid == p.id()

            pdi = SpectralProfilePlotDataItem(p)
            self.mPlotItems[fid] = pdi
            self.addItem(pdi)

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(MIMEDATA_SPECLIB):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(MIMEDATA_SPECLIB):
            event.accept()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if mimeData.hasFormat(MIMEDATA_SPECLIB):
            speclib = pickle.loads(mimeData.data(MIMEDATA_SPECLIB))
            self.mSpeclib.addSpeclib(speclib)
            event.accept()


class SpectralLibraryWidget(QFrame, loadUI('spectrallibrarywidget.ui')):
    sigLoadFromMapRequest = pyqtSignal()

    def __init__(self, parent=None):
        super(SpectralLibraryWidget, self).__init__(parent)
        self.setupUi(self)

        self.mColorCurrentSpectra = QColor('green')
        self.mColorSelectedSpectra = QColor('yellow')

        self.m_plot_max = 500
        self.mPlotXUnitModel = UnitComboBoxItemModel()
        self.mPlotXUnitModel.addUnit('Index')


        self.mPlotXUnitModel = OptionListModel()
        self.mPlotXUnitModel.addOption(Option('Index'))

        self.cbXUnit.setModel(self.mPlotXUnitModel)
        self.cbXUnit.currentIndexChanged.connect(lambda: self.setPlotXUnit(self.cbXUnit.currentText()))
        self.cbXUnit.setCurrentIndex(0)
        self.mSelectionModel = None

        self.mCurrentSpectra = []
#        self.tableViewSpeclib.verticalHeader().setMovable(True)
        self.tableViewSpeclib.verticalHeader().setDragEnabled(True)
        self.tableViewSpeclib.verticalHeader().setDragDropMode(QAbstractItemView.InternalMove)

        self.tableViewSpeclib.setAcceptDrops(True)
        self.tableViewSpeclib.setDropIndicatorShown(True)

        self.mModel = SpectralLibraryTableModel()
        self.mFilterModel = SpectralLibraryTableFilterModel(self.mModel)
        self.mSpeclib = self.mModel.speclib()

        # view.setFeatureSelectionManager(featureSelectionManager)
        self.mTableConfig = None
        self.updateTableConfig()


        self.mOverPlotDataItems = dict() #stores plotDataItems


        #self.mModel.sigAttributeAdded.connect(self.onAttributesChanged)
        #self.mModel.sigAttributeRemoved.connect(self.onAttributesChanged)

        self.tableViewSpeclib.setModel(self.mFilterModel)
        self.plotWidget.setModel(self.mModel)


        pi = self.plotItem()
        pi.setAcceptDrops(True)

        pi.dropEvent = self.dropEvent


        self.initActions()

        self.mMapInteraction = False
        self.setMapInteraction(False)

    def initActions(self):


        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)
        self.actionSaveCurrentProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)
        self.actionAddCurrentProfilesAutomatically.toggled.connect(self.actionSaveCurrentProfiles.setDisabled)

        #self.actionSaveCurrentProfiles.event = onEvent

        self.actionImportSpeclib.triggered.connect(lambda :self.importSpeclib())
        self.actionSaveSpeclib.triggered.connect(lambda :self.speclib().exportProfiles(parent=self))

        self.actionReload.triggered.connect(lambda : self.speclib().dataProvider().forceReload())
        self.actionToggleEditing.toggled.connect(self.onToggleEditing)
        self.actionSaveEdits.triggered.connect(lambda : saveEdits(self.speclib(), leaveEditable=self.speclib().isEditable()))
        self.actionDeleteSelected.triggered.connect(lambda : deleteSelected(self.speclib()))
        self.actionCutSelectedRows.setVisible(False) #todo
        self.actionCopySelectedRows.setVisible(False) #todo
        self.actionPasteFeatures.setVisible(False)

        self.actionSelectAll.triggered.connect(lambda :
                                               self.speclib().selectAll()
                                               )

        self.actionInvertSelection.triggered.connect(lambda :
                                                     self.speclib().invertSelection()
                                                     )
        self.actionRemoveSelection.triggered.connect(lambda :
                                                     self.speclib().removeSelection()
                                                     )


        #to hide
        self.actionPanMapToSelectedRows.setVisible(False)
        self.actionZoomMapToSelectedRows.setVisible(False)


        self.actionAddAttribute.triggered.connect(self.onAddAttribute)
        self.actionRemoveAttribute.triggered.connect(self.onRemoveAttribute)

        self.tableViewSpeclib.addActions([self.actionPanMapToSelectedRows, self.actionZoomMapToSelectedRows, self.actionDeleteSelected, self.actionToggleEditing])
        self.onEditingToggled()

    def importSpeclib(self, path=None):
        slib = None
        if path is None:
            slib = SpectralLibrary.readFromSourceDialog(self)
        else:
            slib = SpectralLibrary.readFrom(path)

        if isinstance(slib, SpectralLibrary):
            self.speclib().addSpeclib(slib)


    def speclib(self):
        return self.mSpeclib

    def onToggleEditing(self, b):

        b = False
        speclib = self.speclib()

        if speclib.isEditable():
            saveEdits(speclib, leaveEditable=False)
        else:
            speclib.startEditing()


        self.onEditingToggled()

    def onEditingToggled(self):
        speclib = self.speclib()

        hasSelectedFeatures = speclib.selectedFeatureCount() > 0
        isEditable = speclib.isEditable()
        self.actionToggleEditing.blockSignals(True)
        self.actionToggleEditing.setChecked(isEditable)
        self.actionSaveEdits.setEnabled(isEditable)
        self.actionReload.setEnabled(not isEditable)
        self.actionToggleEditing.blockSignals(False)


        self.actionAddAttribute.setEnabled(isEditable)
        self.actionRemoveAttribute.setEnabled(isEditable)
        self.actionDeleteSelected.setEnabled(isEditable and hasSelectedFeatures)
        self.actionPasteFeatures.setEnabled(isEditable)
        self.actionToggleEditing.setEnabled(not speclib.readOnly())

        self.actionRemoveAttribute.setEnabled(len(speclib.optionalFieldNames()) > 0)

    def onAddAttribute(self):
        """
        Slot to add an optional QgsField / attribute
        """
        d = AddAttributeDialog(self.mSpeclib)
        d.exec_()

        if d.result() == QDialog.Accepted:

            field = d.field()
            b = self.mSpeclib.isEditable()
            self.mSpeclib.startEditing()
            self.mSpeclib.addAttribute(field)
            saveEdits(self.mSpeclib, leaveEditable=b)

        self.onEditingToggled()


    def onRemoveAttribute(self):
        """
        Slot to remove none-mandatorie fields / attributes
        """
        fieldNames = self.mSpeclib.optionalFieldNames()
        if len(fieldNames) > 0:
            fieldName, accepted = QInputDialog.getItem(self, 'Remove Field', 'Select', fieldNames, editable=False)
            if accepted:
                i = self.mSpeclib.fields().indexFromName(fieldName)
                if i >= 0:
                    b = self.mSpeclib.isEditable()
                    self.mSpeclib.startEditing()
                    self.mSpeclib.deleteAttribute(i)
                    saveEdits(self.mSpeclib, leaveEditable=b)
                self.onEditingToggled()


    def updateTableConfig(self, config = None):
        """
        Updates the QgsAttributeTableConfig, basically only to hide columns to be hidden.
        """

        if not isinstance(config, QgsAttributeTableConfig):

            config = QgsAttributeTableConfig()
            config.update(self.mSpeclib.fields())

            for i, columnConfig in enumerate(config.columns()):
                assert isinstance(columnConfig, QgsAttributeTableConfig.ColumnConfig)
                hidden = columnConfig.name.startswith(HIDDEN_ATTRIBUTE_PREFIX)
                config.setColumnHidden(i, hidden)
            #config.setActionWidgetVisible(False)
            #self.mTableConfig.setColumnHidden(i, True)
                #if columnConfig.name == 'source':
                #    self.mTableConfig.setColumnWidth(i, 25)

        self.mTableConfig = config
        self.mSpeclib.setAttributeTableConfig(self.mTableConfig)
        self.mFilterModel.setAttributeTableConfig(self.mTableConfig)
        #self.tableViewSpeclib.setAttributeTableConfig(self.mTableConfig)

    def setMapInteraction(self, b : bool):

        if b == False:
            self.setCurrentSpectra(None)

        self.mMapInteraction = b
        self.actionSelectProfilesFromMap.setVisible(b)
        self.actionSaveCurrentProfiles.setVisible(b)
        self.actionAddCurrentProfilesAutomatically.setVisible(b)
        self.actionPanMapToSelectedRows.setVisible(b)
        self.actionZoomMapToSelectedRows.setVisible(b)


    def mapInteraction(self):
        return self.mMapInteraction


    def onAttributesChanged(self):
        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    def addAttribute(self, name):
        name = str(name)
        if len(name) > 0 and name not in self.mSpeclib.metadataAttributes():
            self.mModel.addAttribute(name)

    def setPlotXUnit(self, unit):
        unit = str(unit)

        pi = self.plotItem()
        if unit == 'Index':
            for pdi in pi.dataItems:

                assert isinstance(pdi, SpectralProfilePlotDataItem)
                p = pdi.mProfile
                assert isinstance(p, SpectralProfile)
                pdi.setData(y=pdi.yData, x= p.xValues())
                pdi.setVisible(True)
        else:
            #hide items that can not be presented in unit "unit"
            for pdi in pi.dataItems[:]:
                p = pdi.mProfile
                assert isinstance(p, SpectralProfile)
                if p.xUnit() != unit:
                    pdi.setVisible(False)
                else:
                    pdi.setData(y=p.yValues(), x=p.xValues())
                    pdi.setVisible(True)
        pi.replot()

    def plotItem(self):
        pi = self.plotWidget.getPlotItem()

        assert isinstance(pi, PlotItem)
        return pi

    def onExportSpectra(self, *args):
        self.mSpeclib.exportProfiles()



    def addSpeclib(self, speclib):
        if isinstance(speclib, SpectralLibrary):
            self.speclib().addSpeclib(speclib)

    def setAddCurrentSpectraToSpeclibMode(self, b:bool):
        self.actionAddCurrentProfilesAutomatically.setChecked(b)

    def addCurrentSpectraToSpeclib(self, *args):
        self.speclib().addProfiles(self.mCurrentSpectra)
        self.setCurrentSpectra([])

    sigCurrentSpectraChanged = pyqtSignal(list)
    def setCurrentSpectra(self, listOfSpectra:list):
        if listOfSpectra is None:
            listOfSpectra = []


        for p in listOfSpectra:
            assert isinstance(p, SpectralProfile)

        plotItem = self.plotItem()

        #remove old items
        for key in list(self.mOverPlotDataItems.keys()):
            if isinstance(key, SpectralProfile):
                pdi = self.mOverPlotDataItems[key]
                self.mOverPlotDataItems.pop(key)
                self.plotItem().removeItem(pdi)

        self.mCurrentSpectra.clear()
        self.mCurrentSpectra.extend(listOfSpectra)
        if self.actionAddCurrentProfilesAutomatically.isChecked() and len(self.mCurrentSpectra) > 0:
            self.addCurrentSpectraToSpeclib()
            #this will change the speclib and add each new profile automatically to the plot
        else:
            for p in self.mCurrentSpectra:
                assert isinstance(p, SpectralProfile)
                self.mPlotXUnitModel.addOption(Option(p.xUnit()))
                pdi = SpectralProfilePlotDataItem(p)
                pdi.setStyle(CURRENT_SPECTRUM_STYLE)

                plotItem.addItem(pdi)
                pdi.setZValue(len(plotItem.dataItems))
                self.mOverPlotDataItems[p] = pdi
        self.sigCurrentSpectraChanged.emit(self.mCurrentSpectra)



    def onProfileClicked(self, pdi):
        m = self.mModel

        idx = m.profile2idx(pdi.mProfile)
        if idx is None:
            return

        currentSelection = self.mSelectionModel.selection()

        profileSelection = QItemSelection(m.createIndex(idx.row(), 0), \
                                          m.createIndex(idx.row(), m.columnCount()-1))

        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ShiftModifier:
            profileSelection.merge(currentSelection, QItemSelectionModel.Toggle)

        self.mSelectionModel.select(profileSelection, QItemSelectionModel.ClearAndSelect)



    def currentSpectra(self):
        return self.mCurrentSpectra[:]




class SpectralLibraryFeatureSelectionManager(QgsIFeatureSelectionManager):


    def __init__(self, layer, parent=None):
        s =""
        super(SpectralLibraryFeatureSelectionManager, self).__init__(parent)
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.mLayer.selectionChanged.connect(self.selectionChanged)

    def layer(self):
        return self.mLayer

    def deselect(self, ids):

        if len(ids) > 0:
            selected = [id for id in self.selectedFeatureIds() if id not in ids]
            self.mLayer.deselect(ids)

            self.selectionChanged.emit(selected, ids, True)

    def select(self, ids):
        self.mLayer.select(ids)

    def selectFeatures(self, selection, command):

        super(SpectralLibraryFeatureSelectionManager, self).selectF
        s = ""
    def selectedFeatureCount(self):
        return self.mLayer.selectedFeatureCount()

    def selectedFeatureIds(self):
        return self.mLayer.selectedFeatureIds()

    def setSelectedFeatures(self, ids):
        self.mLayer.selectByIds(ids)

def __sandbox():


    app = initQgisApplication()
    app.messageLog().messageReceived.connect(lambda args: print(args) )


    from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, re_2014_06_25

    mapCanvas = QgsMapCanvas()
    p = Img_2014_06_16_LE72270652014167CUB00_BOA
    ext = SpatialExtent.fromRasterSource(p)
    pos = []
    center = ext.spatialCenter()
    for dx in range(-120,120, 60):
        for dy in range(-120,120,60):
            pos.append(SpatialPoint(ext.crs(), center.x()+dx, center.y()+dy))

    speclib = SpectralLibrary()
    p1 = SpectralProfile()
    p1.setName('No Geometry')
    p1.setXValues([1,2,3,4,5])
    p1.setYValues([0.2,0.3,0.2,0.5,0.7])

    p2 = SpectralProfile()
    p2.setName('No Geom/NoData')

    speclib.addProfiles([p1,p2],0)
    speclib.addSpeclib(SpectralLibrary.readFromRasterPositions(p, pos))
    speclib.startEditing()

    mapCanvas.show()



    lyr = QgsRasterLayer(Img_2014_06_16_LE72270652014167CUB00_BOA)
    lyrs = [speclib, lyr]
    QgsProject.instance().addMapLayers(lyrs)
    mapCanvas.setLayers(lyrs)
    mapCanvas.setDestinationCrs(lyr.crs())
    mapCanvas.setExtent(lyr.extent())
    sp = SpectralProfile.fromMapCanvas(mapCanvas,
                                       SpatialPoint(mapCanvas.mapSettings().destinationCrs(), mapCanvas.center()))

    if False:

        w = QFrame()
        w.setLayout(QHBoxLayout())

        model = SpectralLibraryTableModel(speclib=speclib, parent=w)
        fmodel = SpectralLibraryTableFilterModel(model)
        view = SpectralLibraryTableView(parent=w)
        #view = QgsAttributeTableView(parent=w)
        # view = QTableView()
        # from qgis.gui import QgsVectorLayerSelectionManager
        # featureSelectionManager = QgsVectorLayerSelectionManager(speclib)

        view.setModel(fmodel)


        # view.setFeatureSelectionManager(featureSelectionManager)
        config = QgsAttributeTableConfig()
        config.update(speclib.fields())

        for i, columnConfig in enumerate(config.columns()):

            if columnConfig.name.startswith(HIDDEN_ATTRIBUTE_PREFIX):
                config.setColumnHidden(i, True)

        speclib.setAttributeTableConfig(config)
        fmodel.setAttributeTableConfig(config)
        view.setAttributeTableConfig(config)

        #view.setSelectionBehavior(QAbstractItemView.SelectItems)
        #view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        w.layout().addWidget(view)
    else:
        w = SpectralLibraryWidget()
        w.setMapInteraction(True)

        w.mSpeclib.addSpeclib(speclib)

        w.setCurrentSpectra(sp)
        w.show()
        w.resize(QSize(800, 200))

    app.exec_()
    print('Finished')

