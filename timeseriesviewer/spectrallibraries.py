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
import os, re, tempfile, pickle, copy, shutil
from collections import OrderedDict
from qgis.core import *
from qgis.gui import *
import pyqtgraph as pg
from pyqtgraph import functions as fn
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import numpy as np
from osgeo import gdal, gdal_array

from timeseriesviewer.utils import *
from timeseriesviewer.virtualrasters import *
from timeseriesviewer.models import *
from timeseriesviewer.plotstyling import PlotStyle, PlotStyleDialog
import timeseriesviewer.mimedata as mimedata

FILTERS = 'ENVI Spectral Library (*.esl *.sli);;CSV Table (*.csv)'

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
HIDDEN_ATTRIBUTE_PREFIX = '__serialized__'

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

def value2str(value, sep=' '):
    if isinstance(value, list):
        value = sep.join([str(v) for v in value])
    elif isinstance(value, np.array):
        value = value2str(value.astype(list), sep=sep)
    elif value is None:
        value = str('')
    else:
        value = str(value)
    return value

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

    def contextMenuEvent(self, event):

        menu = QMenu(self)

        m = menu.addMenu('Copy...')
        a = m.addAction("Cell Values")
        a.triggered.connect(lambda :self.onCopy2Clipboard('CELLVALUES', separator=';'))
        a = m.addAction("Spectral Values")
        a.triggered.connect(lambda: self.onCopy2Clipboard('YVALUES', separator=';'))
        a = m.addAction("Spectral Values + Metadata")
        a.triggered.connect(lambda: self.onCopy2Clipboard('ALL', separator=';'))

        a = m.addAction("Spectral Values (Excel)")
        a.triggered.connect(lambda: self.onCopy2Clipboard('YVALUES', separator='\t'))
        a = m.addAction("Spectral Values + Metadata (Excel)")
        a.triggered.connect(lambda: self.onCopy2Clipboard('ALL', separator='\t'))

        a = menu.addAction('Save to file')
        a.triggered.connect(self.onSaveToFile)

        a = menu.addAction('Set Style')
        a.triggered.connect(self.onSetStyle)

        m.addSeparator()

        a = menu.addAction('Check')
        a.triggered.connect(lambda : self.setCheckState(Qt.Checked))
        a = menu.addAction('Uncheck')
        a.triggered.connect(lambda: self.setCheckState(Qt.Unchecked))

        menu.addSeparator()
        a = menu.addAction('Remove')
        a.triggered.connect(lambda : self.model().removeProfiles(self.selectedSpectra()))
        menu.popup(QCursor.pos())

    def onCopy2Clipboard(self, key, separator='\t'):
        assert key in ['CELLVALUES', 'ALL', 'YVALUES']
        txt = None
        if key == 'CELLVALUES':
            lines = []
            line = []
            row = None
            for idx in self.selectionModel().selectedIndexes():
                if row is None:
                    row = idx.row()
                elif row != idx.row():
                    lines.append(line)
                    line = []
                line.append(self.model().data(idx, role=Qt.DisplayRole))
            lines.append(line)
            lines = [value2str(l, sep=separator) for l in lines]
            QApplication.clipboard().setText('\n'.join(lines))
        else:
            sl = SpectralLibrary(profiles=self.selectedSpectra())
            txt = None
            if key == 'ALL':
                lines = CSVSpectralLibraryIO.asTextLines(sl, separator=separator)
                txt = '\n'.join(lines)
            elif key == 'YVALUES':
                lines = []
                for p in sl:
                    assert isinstance(p, SpectralProfile)
                    lines.append(separator.join([str(v) for v in p.yValues()]))
                txt = '\n'.join(lines)
            if txt:
                QApplication.clipboard().setText(txt)

    def onSaveToFile(self, *args):
        sl = SpectralLibrary(profiles=self.selectedSpectra())
        sl.exportProfiles()




    def selectedSpectra(self):
        rows = self.selectedRowsIndexes()
        m = self.model()
        return [m.idx2profile(m.createIndex(r, 0)) for r in rows]

    def onSetStyle(self):
        fmodel = self.model()
        dmodel = self.model()
        styleDefault = None

        indices = self.selectionModel().selectedIndexes()
        if len(indices) == 0:
            indices.append(self.selectionModel().currentIndex())

        if len(indices) > 0:
            indices = [fmodel.createIndex(idx.row(), 0) for idx in indices]
            styleDefault = model.data(fmodel.mapToSource(indices[0]), role=Qt.DecorationRole)

            if not isinstance(styleDefault, PlotStyle):
                styleDefault = None

            style = PlotStyleDialog.getPlotStyle(plotStyle=styleDefault)
            if isinstance(style, PlotStyle):
                for idx in indices:
                    dmodel.setData(idx, style, Qt.DecorationRole)

    def setCheckState(self, checkState):
        model = self.model()

        for idx in self.selectedRowsIndexes():
            model.setData(model.createIndex(idx, 0), checkState, Qt.CheckStateRole)

        selectionModel = self.selectionModel()
        assert isinstance(selectionModel, QItemSelectionModel)
        selectionModel.clearSelection()


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

class SpectralProfilePlotDataItem(pg.PlotDataItem):

    def __init__(self, spectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super(SpectralProfilePlotDataItem, self).__init__()
        self.mProfile = spectralProfile
        self.setData(x=spectralProfile.xValues(), y=spectralProfile.yValues())

    def setClickable(self, b, width=None):
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setColor(self, color):
        if not isinstance(color, QColor):
            color = QColor(color)
        self.setPen(color)

    def pen(self):
        return fn.mkPen(self.opts['pen'])

    def color(self):
        return self.pen().color()

    def setLineWidth(self, width):
        pen = pg.mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)


class SpectralProfile(QgsFeature):

    crs = QgsCoordinateReferenceSystem('EPSG:4689')

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
        #profile.setValues(values, valuePositions=wl, valuePositionUnit=wlu)
        profile.setYValues(values)
        if wl is not None:
            profile.setXValues(wl, unit=wlu)

        profile.setCoordinates(px=px, pt=SpatialPoint(crs, px2geo(px, gt)))
        profile.setSource('{}'.format(ds.GetFileList()[0]))
        return profile

    @staticmethod
    def createQgsField(name : str, exampleValue):
        if isinstance(exampleValue, str):
            return QgsField(name, QVariant.String, 'varchar')
        elif isinstance(exampleValue, int):
            return QgsField(name, QVariant.Int, 'int')
        elif isinstance(exampleValue, float):
            return QgsField(name, QVariant.Double, 'double')
        elif isinstance(exampleValue, np.ndarray):
            return QgsField(name, QVariant.String, 'varchar')
        else:
            raise NotImplemented()

    @staticmethod
    def standardFields():
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
        fields.append(SpectralProfile.createQgsField('name', ''))
        fields.append(SpectralProfile.createQgsField('px_x', 0))
        fields.append(SpectralProfile.createQgsField('px_y', 0))
        fields.append(SpectralProfile.createQgsField('x_unit', ''))
        fields.append(SpectralProfile.createQgsField('y_unit', ''))
        fields.append(SpectralProfile.createQgsField('source', ''))
        fields.append(SpectralProfile.createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'xvalues', ''))
        fields.append(SpectralProfile.createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'yvalues', ''))
        fields.append(SpectralProfile.createQgsField(HIDDEN_ATTRIBUTE_PREFIX + 'style', ''))


        """
        fields.append(QgsField('name', QVariant.String,'varchar', 25))
        fields.append(QgsField('px_x', QVariant.Int, 'int'))
        fields.append(QgsField('px_y', QVariant.Int, 'int'))
        fields.append(QgsField('x_unit', QVariant.String, 'varchar', 5))
        fields.append(QgsField('y_unit', QVariant.String, 'varchar', 5))
        fields.append(QgsField('source', QVariant.String, 'varchar', 5))
        """
        return fields

    @staticmethod
    def fromSpecLibFeature(feature):

        sp = SpectralProfile(fields=feature.fields())
        sp.setId(feature.id())
        sp.setAttributes(feature.attributes())
        return sp

    XVALUES_FIELD = HIDDEN_ATTRIBUTE_PREFIX+'xvalues'
    YVALUES_FIELD = HIDDEN_ATTRIBUTE_PREFIX + 'yvalues'
    STYLE_FIELD = HIDDEN_ATTRIBUTE_PREFIX + 'style'

    def __init__(self, parent=None, fields=None, xUnit='index', yUnit=None):

        if fields is None:
            fields = SpectralProfile.standardFields()

        #QgsFeature.__init__(self, fields)
        #QObject.__init__(self)
        super(SpectralProfile, self).__init__(fields)
        #QObject.__init__(self)
        fields = self.fields()
        assert isinstance(fields, QgsFields)

        self.setXUnit(xUnit)
        self.setYUnit(yUnit)
        self.setStyle(PlotStyle())

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
        return QPoint(self.attribute('px_x'), self.attribute('px_y'))

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
                    fields.append(SpectralProfile.createQgsField(key, ''))
                else:
                    fields.append(SpectralProfile.createQgsField(key, value))
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
        pw.getPlotItem().addItem(pi)

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


class CSVSpectralLibraryIO(AbstractSpectralLibraryIO):

    @staticmethod
    def write(speclib, path, separator='\t'):

        writtenFiles = []
        assert isinstance(speclib, SpectralLibrary)
        lines = ['Spectral Library {}'.format(speclib.name())]

        lines.extend(
            CSVSpectralLibraryIO.asTextLines(speclib, separator=separator)
        )

        file = open(path, 'w')
        for line in lines:
            file.write(line+'\n')
        file.flush()
        file.close()
        writtenFiles.append(path)

        return writtenFiles


    @staticmethod
    def asTextLines(speclib, separator='\t'):
        assert isinstance(speclib, SpectralLibrary)
        lines = []
        attributes = speclib.fieldNames()
        grouping = speclib.groupBySpectralProperties()
        for profiles in grouping.values():
            wlU = profiles[0].xUnit()
            wavelength = profiles[0].xValues()

            columns = ['n', 'name', 'geo', 'px', 'src']+attributes
            if wlU in [None, 'Index']:
                columns.extend(['b{}'.format(i + 1) for i in range(len(wavelength))])
            else:
                for i, wl in enumerate(wavelength):
                    columns.append('b{}_{}'.format(i + 1, wl))
            lines.append(value2str(columns, sep=separator))

            for i, p in enumerate(profiles):
                line = [i + 1, p.name(), p.geoCoordinate(), p.pxCoordinate(), p.source()]
                line.extend([p.metadata(a) for a in attributes])
                line.extend(p.yValues())
                lines.append(value2str(line, sep=separator))
            lines.append('')
        return lines


class EnviSpectralLibraryIO(AbstractSpectralLibraryIO):

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
        if hdr is None or hdr[u'file type'] != u'ENVI Spectral Library':
            return False
        return True

    @staticmethod
    def readFrom(pathESL, tmpVrt=None):
        """
        Reads an ENVI Spectral Library (ESL).
        :param pathESL: path ENVI Spectral Library
        :param tmpVrt: (optional) path of GDAL VRt that is used to read the ESL
        :return: SpectralLibrary
        """
        assert isinstance(pathESL, str)
        md = EnviSpectralLibraryIO.readENVIHeader(pathESL, typeConversion=True)
        data = None
        try:
            to_delete = []
            if tmpVrt is None:
                tmpVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt')
                to_delete.append(tmpVrt)
            ds = EnviSpectralLibraryIO.esl2vrt(pathESL, tmpVrt)
            data = ds.ReadAsArray()
           # md = ds.GetMetadata_Dict()
            ds = None

            #remove the temporary VRT, as it was created internally only
            for file in to_delete:
                os.remove(file)

        except Exception as ex:
            pathHdr = EnviSpectralLibraryIO.findENVIHeader(pathESL)

            pathTmpBin = tempfile.mktemp(prefix='tmpESL', suffix='.esl.bsq')
            pathTmpHdr = re.sub('bsq$','hdr',pathTmpBin)
            shutil.copyfile(pathESL, pathTmpBin)
            shutil.copyfile(pathHdr, pathTmpHdr)
            assert os.path.isfile(pathTmpBin)
            assert os.path.isfile(pathTmpHdr)

            import codecs
            file = codecs.open(pathTmpHdr, encoding='utf-8')
            hdr = file.readlines()
            file.close()

            for iLine in range(len(hdr)):
                if re.search('file type =', hdr[iLine]):
                    hdr[iLine] = 'file type = ENVI Standard\n'
                    break
            file = codecs.open(pathTmpHdr, 'w', encoding='utf-8')
            file.writelines(hdr)
            file.flush()
            file.close()
            assert os.path.isfile(pathTmpHdr)
            hdr = EnviSpectralLibraryIO.readENVIHeader(pathTmpBin)
            ds = gdal.Open(pathTmpBin)
            data = ds.ReadAsArray()
            #md = ds.GetMetadata_Dict()
            ds = None

            try:
                os.remove(pathTmpBin)
            except:
                pass
            try:
                os.remove(pathTmpHdr)
            except:
                pass
        assert data is not None




        nSpectra, nbands = data.shape
        yUnit = None
        xUnit = md.get('wavelength units')
        xValues = md.get('wavelength')
        if xValues is None:
            xValues = list(range(1, nbands + 1))
            xUnit = 'index'

        spectraNames = md.get('spectra names', ['Spectrum {}'.format(i+1) for i in range(nSpectra)])
        listAttributes = [(k, v) for k,v in md.items() \
                          if k not in ['spectra names','wavelength'] and \
                          isinstance(v, list) and len(v) == nSpectra]


        profiles = []
        for i, name in enumerate(spectraNames):
            p = SpectralProfile()
            p.setYValues(data[i,:], unit=yUnit)
            p.setXValues(xValues, unit=xUnit)
            p.setName(name.strip())
            for listAttribute in listAttributes:
                p.setMetadata(listAttribute[0], listAttribute[1][i])
            p.setSource(pathESL)
            profiles.append(p)


        SLIB = SpectralLibrary()
        SLIB.addProfiles(profiles)
        return SLIB

    @staticmethod
    def write(speclib, path, ext='sli'):
        assert isinstance(path, str)
        dn = os.path.dirname(path)
        bn = os.path.basename(path)

        writtenFiles = []

        if bn.lower().endswith(ext.lower()):
            bn = os.path.splitext(bn)[0]

        if not os.path.isdir(dn):
            os.makedirs(dn)

        def value2hdrString(values):
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

            #strdata.normalize('NFKD', title).encode('ascii','ignore')
            #return s
            return s


        for iGrp, grp in enumerate(speclib.groupBySpectralProperties().values()):

            wl = grp[0].xValues()
            wlu = grp[0].xUnit()


            # stack profiles
            pData = [np.asarray(p.yValues()) for p in grp]
            pData = np.vstack(pData)
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
            ds.SetDescription(str(speclib.name()))
            ds.SetMetadataItem(str('band names'), str('Spectral Library'), str('ENVI'))
            ds.SetMetadataItem(str('spectra names'),value2hdrString(pNames), str('ENVI'))
            ds.SetMetadataItem(str('wavelength'), value2hdrString(wl), str('ENVI'))
            ds.SetMetadataItem(str('wavelength units'), str(wlu), str('ENVI'))

            fieldNames = ds.GetMetadata_Dict('ENVI').keys()
            fieldNames = [n for n in speclib.fields().names() if n not in fieldNames and not n.startswith('__')]



            for a in fieldNames:
                v = value2hdrString([p.metadata(a) for p in grp])
                ds.SetMetadataItem(a, v, str('ENVI'))

            pathHdr = ds.GetFileList()[1]
            ds = None

            # last step: change ENVI Hdr
            file = open(pathHdr)
            hdr = file.readlines()
            file.close()

            for iLine in range(len(hdr)):
                if re.search('file type =', hdr[iLine]):
                    hdr[iLine] = 'file type = ENVI Spectral Library\n'
                    break

            file = open(pathHdr, 'w')
            file.writelines(hdr)
            file.flush()
            file.close()
            writtenFiles.append(pathDst)

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
        byteOrder = 'MSB' if hdr['byte order'] == 0 else 'LSB'

        if pathVrt is None:
            pathVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt')


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
        :param typeConversion: Set on True to convert header keys with numeric
        values into numeric data types (int / float)
        :return: dict
        """
        assert isinstance(pathESL, str)
        if not os.path.isfile(pathESL):
            return None

        pathHdr = EnviSpectralLibraryIO.findENVIHeader(pathESL)
        if pathHdr is None:
            return None

        import codecs
        #hdr = open(pathHdr).readlines()
        file = codecs.open(pathHdr, encoding='utf-8')
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
        for k in ['byte order', 'data type', 'header offset', 'lines', 'samples', 'bands']:
            if not k in md.keys():
                return None

        #todo: transform known strings into int/floats?
        def toType(t, arg):
            if isinstance(arg, list):
                return [toType(t, a) for a  in arg]
            else:
                return t(arg)

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


    sigProfilesAdded = pyqtSignal([list], [list, list])
    sigProfilesRemoved = pyqtSignal([list], [list, list])
    sigNameChanged = pyqtSignal(str)

    def __init__(self, name='SpectralLibrary'):
        crs = SpectralProfile.crs
        uri = 'Point?crs={}'.format(crs.authid())
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(SpectralLibrary, self).__init__(uri, name, 'memory', lyrOptions)

        defaultFields = SpectralProfile.standardFields()



        assert self.startEditing()
        assert self.dataProvider().addAttributes(defaultFields)
        assert self.commitChanges()
        self.initConditionalStyles()

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
            self.startEditing()
            b = self.dataProvider().addAttributes(missingFields)
            # for field in missingFields:
            #    assert isinstance(field, QgsField)
            if b:
                self.commitChanges()
            else:
                self.commitErrors()
            s = ""

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

        inEditMode = self.isEditable()
        if not inEditMode:
            self.startEditing()
        #b, l = self.dataProvider().addFeatures(profiles)
        self.addFeatures(profiles)
        if not inEditMode:
            self.commitChanges()

    def profiles(self):
        return self[:]

    def groupBySpectralProperties(self):
        """
        Groups the SpectralProfiles by:
            wavelength (xValues), wavelengthUnit (xUnit) and yUnit
        :return: {(xValues, wlU, yUnit):[list-of-profiles]}
        """

        d = dict()
        for p in self.profiles():
            #assert isinstance(p, SpectralProfile)
            id = (str(p.xValues()), str(p.xUnit()), str(p.yUnit()))
            if id not in d.keys():
                d[id] = list()
            d[id].append(p)
        return d


    def asTextLines(self, separator='\t'):
        return CSVSpectralLibraryIO.asTextLines(self, separator=separator)

    def asPickleDump(self):
        return pickle.dumps(self, SpectralLibrary.PICKLE_PROTOCOL)

    def exportProfiles(self, path=None):

        if path is None:

            path = QFileDialog.getSaveFileName(parent=None, caption="Save Spectral Library", filter=FILTERS)
            if isinstance(path, tuple):
                path = path[0]

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            if ext in ['.sli','.esl']:
                return EnviSpectralLibraryIO.write(self, path)

            if ext in ['.csv']:
                return CSVSpectralLibraryIO.write(self, path, separator='\t')


        return []

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        to_remove = self.extractProfileList(profiles)

        indices_to_remove = sorted([self.mProfiles.index(p) for p in to_remove if p in self.mProfiles], reverse=True)
        to_remove = [self.mProfiles[i] for i in indices_to_remove]

        if len(to_remove) > 0:
            for p in to_remove:
                self.mProfiles.remove(p)
            self.sigProfilesRemoved[list].emit(to_remove)
            self.sigProfilesRemoved[list, list].emit(to_remove, indices_to_remove)

        s = ""



    def yRange(self):
        profiles = self.profiles()
        minY = min([min(p.yValues()) for p in profiles])
        maxY = max([max(p.yValues()) for p in profiles])
        return minY, maxY

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
        features = list(self.getFeatures())[slice]
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

    class ProfileWrapper(object):
        def __init__(self, profile):
            assert isinstance(profile, SpectralProfile)
            self.profile = profile
            self.style = QColor('white')
            self.checkState = Qt.Unchecked

        def id(self):
            return self.profile.id()

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
        if role is None or not index.isValid():
            return None

        result = super(SpectralLibraryTableModel,self).data(index, role=role)

        if index.column() == 0 and role in [Qt.CheckStateRole, Qt.DecorationRole]:
            profile = self.spectralProfile(index)
            style = profile.style()
            assert isinstance(style, PlotStyle)
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
        if role is None or not index.isValid():
            return False

        speclib = self.layer()
        assert isinstance(speclib, SpectralLibrary)
        if index.column() == 0 and role in [Qt.CheckStateRole, Qt.DecorationRole]:
            profile = self.spectralProfile(index)
            style = profile.style()
            b = speclib.isEditable()

            assert isinstance(style, PlotStyle)
            if role == Qt.CheckStateRole:
                style.setVisibility(value == Qt.Checked)
                profile.setStyle(style)
            if role == Qt.DecorationRole and isinstance(value, PlotStyle):
                profile.setStyle(value)

            if not b:
                speclib.startEditing()
            speclib.updateFeature(profile)
            if not b:
                speclib.commitChanges()
            return True

            #f = self.layer().getFeature(profile.id())
            #i = f.fieldNameIndex(SpectralProfile.STYLE_FIELD)
            #self.layer().changeAttributeValue(f.id(), i, value)
            #result = super().setData(self.index(index.row(), self.mcnStyle), value, role=Qt.EditRole)
            #if not b:
            #    self.layer().commitChanges()

        else:
            return super().setData(index, value, role=role)


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
                flags = super(SpectralLibraryTableModel, self).flags(index)
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
        self.tableViewSpeclib.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableViewSpeclib.setAcceptDrops(True)
        self.tableViewSpeclib.setDropIndicatorShown(True)

        self.mModel = SpectralLibraryTableModel()
        self.mSpeclib = self.mModel.mSpecLib

        self.mSpeclib.sigProfilesAdded.connect(self.onProfilesAdded)
        self.mSpeclib.sigProfilesRemoved.connect(self.onProfilesRemoved)
        self.mPlotDataItems = dict() #stores plotDataItems


        #self.mModel.sigAttributeAdded.connect(self.onAttributesChanged)
        #self.mModel.sigAttributeRemoved.connect(self.onAttributesChanged)

        self.tableViewSpeclib.setModel(self.mModel)
        self.mSelectionModel = QItemSelectionModel(self.mModel)
        self.mSelectionModel.selectionChanged.connect(self.onSelectionChanged)
        #self.mSelectionModel.currentChanged.connect(self.onCurrentSelectionChanged)
        self.tableViewSpeclib.setSelectionModel(self.mSelectionModel)


        self.plotWidget.setAntialiasing(True)
        self.plotWidget.setAcceptDrops(True)

        self.plotWidget.dragEnterEvent = self.dragEnterEvent
        self.plotWidget.dragMoveEvent = self.dragMoveEvent
        self.plotWidget.dropEvent = self.dropEvent
        pi = self.plotWidget.getPlotItem()
        pi.setAcceptDrops(True)

        pi.dropEvent = self.dropEvent

        self.btnLoadFromFile.clicked.connect(lambda : self.addSpeclib(SpectralLibrary.readFromSourceDialog(self)))
        self.btnExportSpeclib.clicked.connect(self.onExportSpectra)

        self.btnAddCurrentToSpeclib.clicked.connect(self.addCurrentSpectraToSpeclib)

        self.btnLoadfromMap.clicked.connect(self.sigLoadFromMapRequest.emit)

        self.btnAddAttribute.clicked.connect(
            lambda :self.mModel.addAttribute(
                QInputDialog.getText(self, 'Add Attribute', 'Attribute', text='New Attribute')[0])
        )

        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib) > 0)
        self.btnRemoveAttribute.clicked.connect(
            lambda : self.mModel.removeAttribute(
                QInputDialog.getItem(self, 'Delete Attribute', 'Attributes',
                                     self.mModel.mAttributeColumns, editable=False)[0]
            )
        )

    def setMapInteraction(self, b):
        assert isinstance(b, bool)
        if b is None or b is False:
            self.setCurrentSpectra(None)
        self.btnBoxMapInteraction.setEnabled(b)

    def mapInteraction(self):
        return self.btnBoxMapInteraction.isEnabled()

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            event.accept()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if mimeData.hasFormat(mimedata.MDF_SPECTRALLIBRARY):
            speclib = SpectralLibrary.readFromPickleDump(mimeData.data(mimedata.MDF_SPECTRALLIBRARY))
            self.mSpeclib.addSpeclib(speclib)
            event.accept()

    def onAttributesChanged(self):
        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    def addAttribute(self, name):
        name = str(name)
        if len(name) > 0 and name not in self.mSpeclib.metadataAttributes():
            self.mModel.addAttribute(name)

    def setPlotXUnit(self, unit):
        unit = str(unit)

        pi = self.getPlotItem()
        if unit == 'Index':
            for pdi in pi.dataItems:

                assert isinstance(pdi, SpectralProfilePlotDataItem)
                p = pdi.mProfile
                pdi.setData(y=pdi.yData, x= p.valueIndexes())
                pdi.setVisible(True)
        else:
            #hide items that can not be presented in unit "unit"
            for pdi in pi.dataItems[:]:
                p = pdi.mProfile
                if pdi.mProfile.xUnit() != unit:
                    pdi.setVisible(False)
                else:
                    pdi.setData(y=pdi.yData, x=pdi.mProfile.xValues())
                    pdi.setVisible(True)
        pi.replot()
    def getPlotItem(self):
        pi = self.plotWidget.getPlotItem()
        assert isinstance(pi, pg.PlotItem)
        return pi

    def onExportSpectra(self, *args):
        self.mSpeclib.exportProfiles()


    def onProfilesAdded(self, profiles):
        # todo: remove some PDIs from plot if there are too many
        pi = self.getPlotItem()
        if True:
            to_remove = max(0, len(pi.listDataItems()) - self.m_plot_max)
            if to_remove > 0:
                for pdi in pi.listDataItems()[0:to_remove]:
                    pi.removeItem(pdi)

        for p in profiles:
            self.mPlotXUnitModel.addOption(Option(p.xUnit()))
            pi.addItem(self.createPDI(p))

        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    def addSpectralPlotItem(self, pdi):
        assert isinstance(pdi, SpectralProfilePlotDataItem)
        pi = self.getPlotItem()

        pi.addItem(pdi)

    def onProfilesRemoved(self, profiles):
        for p in profiles:
            self.removePDI(p)
        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    def addSpeclib(self, speclib):
        if isinstance(speclib, SpectralLibrary):
            self.mModel.insertProfiles([p.clone() for p in speclib])
            #self.mSpeclib.addProfiles([copy.copy(p) for p in speclib])

    def setAddCurrentSpectraToSpeclibMode(self, b:bool):
        self.cbAddCurrentSpectraToSpeclib.setChecked(b)

    def addCurrentSpectraToSpeclib(self, *args):
        self.mModel.insertProfiles([p.clone() for p in self.mCurrentSpectra])
        #self.mSpeclib.addProfiles([p.clone() for p in self.mCurrentSpectra])

    sigCurrentSpectraChanged = pyqtSignal(list)
    def setCurrentSpectra(self, listOfSpectra):
        if listOfSpectra is None or not self.mapInteraction():
            listOfSpectra = []

        plotItem = self.getPlotItem()
        #remove old items
        for p in self.mCurrentSpectra:
            if p not in self.mSpeclib:
                self.removePDI(p)

        self.mCurrentSpectra = listOfSpectra[:]
        if self.cbAddCurrentSpectraToSpeclib.isChecked():
            self.addCurrentSpectraToSpeclib()

        for p in self.mCurrentSpectra:
            self.mPlotXUnitModel.addOption(Option(p.xUnit()))
            pdi = self.createPDI(p)
            pdi.setPen(fn.mkPen(QColor('green'), width=3))
            plotItem.addItem(pdi)
            pdi.setZValue(len(plotItem.dataItems))

        self.sigCurrentSpectraChanged.emit(self.mCurrentSpectra)

    def createPDI(self, profile, color=None):
        if color is None:
            color = QColor('white')
        if not isinstance(color, QColor):
            color = QColor(color)
        assert isinstance(profile, SpectralProfile)
        if profile not in self.mPlotDataItems.keys():

            pdi = SpectralProfilePlotDataItem(profile)
            pdi.setClickable(True)
            pdi.setPen(fn.mkPen(color, width=1))

            pdi.sigClicked.connect(self.onProfileClicked)
            self.mPlotDataItems[profile] = pdi
            pdi = self.mPlotDataItems[profile]
        return pdi

    def removePDI(self, profile):
        """
        Removes the SpectraProfilePlotDataItem realted to SpectraProfile 'profile'
        :param profile:
        :return:
        """
        assert isinstance(profile, SpectralProfile)
        if profile in self.mPlotDataItems.keys():
            pdi = self.mPlotDataItems.pop(profile)
            self.getPlotItem().removeItem(pdi)
            return pdi
        else:
            return None

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





    def onSelectionChanged(self, selected, deselected):
        if not isinstance(self.mModel, SpectralLibraryTableModel):
            return None

        assert isinstance(selected, QItemSelection)
        assert isinstance(deselected, QItemSelection)

        for selectionRange in deselected:
            for idx in selectionRange.indexes():
                p = self.mModel.idx2profile(idx)
                pdi = self.mPlotDataItems.get(p)
                if isinstance(pdi, SpectralProfilePlotDataItem):
                    pdi.setPen(fn.mkPen(self.mModel.mProfileWrapperLUT[p].style))
                    pdi.setShadowPen(None)


        to_front = []
        for selectionRange in selected:
            for idx in selectionRange.indexes():
                p = self.mModel.idx2profile(idx)
                pdi = self.mPlotDataItems.get(p)
                if isinstance(pdi, SpectralProfilePlotDataItem):
                    pdi.setPen(fn.mkPen(QColor('red'), width = 2))
                    pdi.setShadowPen(fn.mkPen(QColor('black'), width=4))
                    to_front.append(pdi)

        pi = self.getPlotItem()
        l = len(pi.dataItems)
        for pdi in to_front:
            pdi.setZValue(l)
            if pdi not in pi.dataItems:
                pi.addItem(pdi)






if __name__ == "__main__":



    app = initQgisApplication()
    app.messageLog().messageReceived.connect(lambda args: print(args) )

    from example.Images import Img_2014_06_16_LE72270652014167CUB00_BOA, re_2014_06_25

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
    w = QFrame()
    w.setLayout(QHBoxLayout())

    model = SpectralLibraryTableModel(speclib=speclib, parent=w)
    fmodel = SpectralLibraryTableFilterModel(model)
    view = SpectralLibraryTableView(parent=w)
    #view = QTableView()
    view.setModel(fmodel)

    config = QgsAttributeTableConfig()
    config.update(speclib.fields())

    for i, columnConfig in enumerate(config.columns()):

        if columnConfig.name.startswith(HIDDEN_ATTRIBUTE_PREFIX):
            config.setColumnHidden(i, True)

    speclib.setAttributeTableConfig(config)
    fmodel.setAttributeTableConfig(config)
    view.setAttributeTableConfig(config)

    w.layout().addWidget(view)
    w.show()
    w.resize(QSize(800,200))

    if False:

        sl = SpectralLibrary.readFrom(r'C:\Users\geo_beja\Repositories\QGIS_Plugins\enmap-box\enmapboxtestdata\SpecLib_BerlinUrbanGradient.sli')

        cb = QComboBox()
        m = UnitComboBoxItemModel()
        cb.setModel(m)

        spec0 = sl[0]

        m = SpectralLibraryTableViewModel()
        m.insertProfiles(spec0)
        m.insertProfiles(sl)

        view = QTableView()
        view.show()
        view.setModel(m)

        W = SpectralLibraryWidget()
        W.show()
        W.addSpeclib(sl)
        m.mSpecLib.addProfile(spec0)

        if False:
            w =SpectralLibraryTableView()
            #w = SpectralLibraryWidget()
            w.mSpeclib.addProfile(spec0)
            #w.addSpeclib(sl)
            w.show()

    app.exec_()

