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
from future.utils import text_to_native_str
import os, re, tempfile, pickle, copy, shutil
from collections import OrderedDict
from qgis.core import *
from qgis.gui import *
import pyqtgraph as pg
from pyqtgraph import functions as fn
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import numpy as np
from osgeo import gdal, gdal_array

from timeseriesviewer.utils import geo2px, px2geo, SpatialExtent, SpatialPoint, loadUI, settings
from timeseriesviewer.virtualrasters import describeRawFile
from timeseriesviewer.models import Option, OptionListModel


FILTERS = 'ENVI Spectral Library (*.esl *.sli);;CSV Table (*.csv)'

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

class SpectralLibraryTableView(QTableView):

    def __init__(self, parent=None):
        super(SpectralLibraryTableView, self).__init__(parent)
        s = ""

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

        a = menu.addAction('Set color')
        a.triggered.connect(self.onSetColor)

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

    def onSetColor(self):
        c = QColorDialog.getColor()
        if isinstance(c, QColor):
            model = self.model()
            for idx in self.selectedRowsIndexes():
                model.setData(model.createIndex(idx, 1), c, Qt.BackgroundRole)

    def setCheckState(self, checkState):
        model = self.model()

        for idx in self.selectedRowsIndexes():
            model.setData(model.createIndex(idx, 0), checkState, Qt.CheckStateRole)

        selectionModel = self.selectionModel()
        assert isinstance(selectionModel, QItemSelectionModel)
        selectionModel.clearSelection()

    def selectedRowsIndexes(self):
        selectionModel = self.selectionModel()
        assert isinstance(selectionModel, QItemSelectionModel)
        return sorted(list(set([i.row() for i in self.selectionModel().selectedIndexes()])))

    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if self.model().rowCount() == 0:
            index = self.model().createIndex(0,0)
        else:
            index = self.indexAt(event.pos())

        if mimeData.hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
            self.model().dropMimeData(mimeData, event.dropAction(), index.row(), index.column(), index.parent())
            event.accept()





    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
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

    def __init__(self, spectralProfle):
        assert isinstance(spectralProfle, SpectralProfile)
        super(SpectralProfilePlotDataItem, self).__init__(spectralProfle.xValues(), spectralProfle.yValues())
        self.mProfile = spectralProfle

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


class SpectralProfile(QObject):

    @staticmethod
    def fromMapCanvas(mapCanvas, position):
        """
        Returns a list of Spectral Profiles the raster layers in QgsMapCanvas mapCanvas.
        :param mapCanvas:
        :param position:
        """
        assert isinstance(mapCanvas, QgsMapCanvas)

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
        elif isinstance(position, QgsPoint):
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

        wl = ds.GetMetadataItem(str('wavelength'),str('ENVI'))
        wlu = ds.GetMetadataItem(str('wavelength_units'),str('ENVI'))
        if wl is not None and len(wl) > 0:
            wl = re.sub(r'[ {}]','', wl).split(',')
            wl = [float(w) for w in wl]

        profile = SpectralProfile()
        profile.setValues(values, valuePositions=wl, valuePositionUnit=wlu)
        profile.setCoordinates(px=px, spatialPoint=SpatialPoint(crs,px2geo(px, gt)))
        profile.setSource('{}'.format(ds.GetFileList()[0]))
        return profile

    def __init__(self, parent=None):
        super(SpectralProfile, self).__init__(parent)
        self.mName = ''
        self.mValues = []
        self.mValueUnit = None
        self.mValuePositions = []
        self.mValuePositionUnit = None
        self.mMetadata = dict()
        self.mSource = None
        self.mPxCoordinate = None
        self.mGeoCoordinate = None

    sigNameChanged = pyqtSignal(str)
    def setName(self, name):
        assert isinstance(name, str)

        if name != self.mName:
            self.mName = name
            self.sigNameChanged.emit(name)

    def name(self):
        return self.mName

    def setSource(self, uri):
        assert isinstance(uri, str)
        self.mSource = uri

    def source(self):
        return self.mSource

    def setCoordinates(self, px=None, spatialPoint=None):
        if isinstance(px, QPoint):
            self.mPxCoordinate = px
        if isinstance(spatialPoint, SpatialPoint):
            self.mGeoCoordinate = spatialPoint

    def pxCoordinate(self):
        return self.mPxCoordinate

    def geoCoordinate(self):
        return self.mGeoCoordinate

    def isValid(self):
        return len(self.mValues) > 0 and self.mValueUnit is not None

    def setValues(self, values, valueUnit=None,
                  valuePositions=None, valuePositionUnit=None):
        n = len(values)
        self.mValues = values[:]

        if valuePositions is None:
            valuePositions = list(range(n))
            valuePositionUnit = 'Index'
        self.setValuePositions(valuePositions, unit=valuePositionUnit)

    def setValuePositions(self, positions, unit=None):
        assert len(positions) == len(self.mValues)
        self.mValuePositions = positions[:]
        self.mValuePositionUnit = unit

    def updateMetadata(self, metaData):
        assert isinstance(metaData, dict)
        self.mMetadata.update(metaData)

    def setMetadata(self, key, value):

        assert isinstance(key, str)

        self.mMetadata[key] = value

    def metadata(self, key, default=None):
        assert isinstance(key, str)
        v = self.mMetadata.get(key)
        return default if v is None else v

    def yValues(self):
        return self.mValues[:]

    def yUnit(self):
        return self.mValueUnit

    def xValues(self):
        return self.mValuePositions[:]

    def xUnit(self):
        return self.mValuePositionUnit

    def valueIndexes(self):
        return np.arange(len(self.yValues()))

    def clone(self):
        return copy.copy(self)

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
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)

    def __copy__(self):
        return copy.deepcopy(self)

    def isEqual(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if len(self.mValues) != len(other.mValues):
            return False
        return all(a == b for a, b in zip(self.mValues, other.mValues)) \
               and self.mValuePositions == other.mValuePositions \
               and self.mValueUnit == other.mValueUnit \
               and self.mValuePositionUnit == other.mValuePositionUnit \
               and self.mGeoCoordinate == other.mGeoCoordinate \
               and self.mPxCoordinate == other.mPxCoordinate

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

class SpectralLibraryWriter(object):

    @staticmethod
    def writeSpeclib(speclib):
        assert isinstance(speclib, SpectralLibrary)



class SpectralLibraryIO(object):
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
        """Writes the SpectralLibrary speclib to path, returns a list of written files"""
        assert isinstance(speclib, SpectralLibrary)
        return None


class CSVSpectralLibraryIO(SpectralLibraryIO):

    @staticmethod
    def write(speclib, path, separator='\t'):

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

    @staticmethod
    def asTextLines(speclib, separator='\t'):
        lines = []
        attributes = speclib.metadataAttributes()
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


class EnviSpectralLibraryIO(SpectralLibraryIO):

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
            ds = None

            #remove the temporary VRT, as it was created internally only
            for file in to_delete:
                os.remove(file)

        except Exception as ex:
        #if False:
            pathHdr = EnviSpectralLibraryIO.findENVIHeader(pathESL)

            pathTmpBin = tempfile.mktemp(prefix='tmpESL', suffix='.esl.bsq')
            pathTmpHdr = re.sub('bsq$','hdr',pathTmpBin)
            shutil.copyfile(pathESL, pathTmpBin)
            shutil.copyfile(pathHdr, pathTmpHdr)
            assert os.path.isfile(pathTmpBin)
            assert os.path.isfile(pathTmpHdr)

            import codecs
            hdr = codecs.open(pathTmpHdr, encoding='utf-8').readlines()
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
        valueUnit = ''
        valuePositionUnit = md.get('wavelength units')
        valuePositions = md.get('wavelength')
        if valuePositions is None:
            valuePositions = list(range(1, nbands+1))
            valuePositionUnit = 'Band'

        spectraNames = md.get('spectra names', ['Spectrum {}'.format(i+1) for i in range(nSpectra)])
        listAttributes = [(k, v) for k,v in md.items() \
                          if k not in ['spectra names','wavelength'] and \
                          isinstance(v, list) and len(v) == nSpectra]


        profiles = []
        for i, name in enumerate(spectraNames):
            p = SpectralProfile()
            p.setValues(data[i,:],
                        valueUnit=valueUnit,
                        valuePositions=valuePositions,
                        valuePositionUnit=valuePositionUnit)
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

            drv = gdal.GetDriverByName(str('ENVI'))
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


            for a in speclib.metadataAttributes():
                v = value2hdrString([p.metadata(a) for p in grp])
                ds.SetMetadataItem(a, v, str('ENVI'))

            pathHdr = ds.GetFileList()[1]
            ds = None

            # last step: change ENVI Hdr
            hdr = open(pathHdr).readlines()
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
            ds.SetMetadataItem(key, text_to_native_str(value), 'ENVI')
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
        hdr = codecs.open(pathHdr, encoding='utf-8').readlines()
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
        self.setWindowTitle('Spectral Library')
        self.SLW = SpectralLibraryWidget(self)
        self.setWidget(self.SLW)


class SpectralLibraryVectorLayer(QgsVectorLayer):

    def __init__(self, speclib, crs=None):
        assert isinstance(speclib, SpectralLibrary)
        if crs is None:
            crs = QgsCoordinateReferenceSystem('EPSG:4326')

        uri = 'Point?crs={}'.format(crs.authid())
        super(SpectralLibraryVectorLayer, self).__init__(uri, speclib.name(), 'memory', False)
        self.mCrs = crs
        self.mSpeclib = speclib
        self.mSpeclib.sigNameChanged.connect(self.setName)
        self.nameChanged.connect(self.mSpeclib.setName)

        #todo QGIS3: use QgsFieldContraint instead self.mOIDs
        self.mOIDs = dict()


        #initialize fields
        assert self.startEditing()
        # standard field names, types, etc.
        fieldDefs = [('oid', QVariant.Int, 'integer'),
                     ('name', QVariant.String, 'string'),
                     ('geo_x', QVariant.Double, 'decimal'),
                     ('geo_y', QVariant.Double, 'decimal'),
                     ('px_x', QVariant.Int, 'integer'),
                     ('px_y', QVariant.Int, 'integer'),
                     ('source', QVariant.String, 'string'),
                     ]
        # initialize fields
        for fieldDef in fieldDefs:
            field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
            self.addAttribute(field)
        self.commitChanges()

        self.mSpeclib.sigProfilesAdded.connect(self.onProfilesAdded)
        self.mSpeclib.sigProfilesRemoved.connect(self.onProfilesRemoved)
        self.onProfilesAdded(self.mSpeclib[:])

    def onProfilesAdded(self, profiles):
        for p in [p for p in profiles if p.geoCoordinate() is not None]:
            assert isinstance(p, SpectralProfile)
            oid = str(id(p))
            if oid in self.mOIDs.keys():
                continue
            geo = p.geoCoordinate().toCrs(self.mCrs)
            if isinstance(geo, SpatialPoint):
                geometry = QgsPointXY(geo.x(), geo.y())
                feature = QgsFeature(self.fields())
                feature.setGeometry(QgsGeometry(geometry))
                feature.setAttribute('oid', oid)
                feature.setAttribute('name', str(p.name()))
                feature.setAttribute('geo_x', p.geoCoordinate().x())
                feature.setAttribute('geo_y', p.geoCoordinate().y())
                feature.setAttribute('source', str(p.source()))

                px = p.pxCoordinate()
                if isinstance(px, QPoint):
                    feature.setAttribute('px_x', px.x())
                    feature.setAttribute('px_y', px.y())

            self.startEditing()
            assert self.addFeature(feature)

            assert self.commitChanges()
            self.mOIDs[oid] = feature.id()
            self.updateExtents()

    def onProfilesRemoved(self, profiles):

        oids = [str(id(p)) for p in profiles]
        oids = [o for o in oids if o in self.mOIDs.keys()]
        #fids = [self.mOIDs[o] for o in  oids]
        self.selectByExpression('"oid" in ({})'.format(','.join(oids)))
        self.deleteSelectedFeatures()


    def spectralLibrary(self):
        return self.mSpeclib

    def nSpectra(self):
        return len(self.mSpeclib)


class SpectralLibrary(QObject):
    _pickle_protocol = pickle.HIGHEST_PROTOCOL
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
    def readFrom(uri):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        for cls in SpectralLibraryIO.__subclasses__():
            if cls.canRead(uri):
                return cls.readFrom(uri)
        return None


    def __init__(self, parent=None, profiles=None):
        super(SpectralLibrary, self).__init__(parent)

        self.mProfiles = []
        self.mName = ''
        if profiles is not None:
            self.mProfiles.extend(profiles[:])



    sigNameChanged = pyqtSignal(str)
    def setName(self, name):
        if name != self.mName:
            self.mName = name
            self.sigNameChanged.emit(name)

    def name(self):
        return self.mName

    def addSpeclib(self, speclib):
        assert isinstance(speclib, SpectralLibrary)
        self.addProfiles([p for p in speclib])

    sigProfilesAdded = pyqtSignal(list)

    def addProfile(self, profile):
        self.addProfiles([profile])

    def addProfiles(self, profiles, index=None):
        to_add = self.extractProfileList(profiles)
        to_add = [p for p in to_add if p not in self.mProfiles]
        if len(to_add) > 0:
            if index is None:
                index = len(self.mProfiles)
            self.mProfiles[index:index] = to_add
            self.sigProfilesAdded.emit(to_add)
        return to_add

    def extractProfileList(self, profiles):
        if isinstance(profiles, SpectralProfile):
            profiles = [profiles]
        if isinstance(profiles, list):
            profiles = [p for p in profiles if isinstance(p, SpectralProfile)]
        elif isinstance(profiles, SpectralLibrary):
            profiles = profiles.mProfiles[:]
        else:
            raise Exception('Unknown type {}'.format(type(profiles)))
        return profiles


    def groupBySpectralProperties(self):
        """
        Groups the SpectralProfiles by:
            wavelength (xValues), wavelengthUnit (xUnit) and yUnit
        :return: {(xValues, wlU, yUnit):[list-of-profiles]}
        """

        d = dict()
        for p in self.mProfiles:
            #assert isinstance(p, SpectralProfile)
            id = (str(p.xValues()), str(p.xUnit()), str(p.yUnit()))
            if id not in d.keys():
                d[id] = list()
            d[id].append(p)
        return d

    def metadataAttributes(self):
        attributes = set()
        for p in self:
            for k in p.mMetadata.keys():
                attributes.add(k)
        return sorted(list(attributes))

    def renameMetadataAttribute(self,oldName, newName):
        assert oldName in self.metadataAttributes()
        assert isinstance(oldName, str)
        assert isinstance(newName, str)

        for p in self:
            if oldName in p.mMetadata.keys:
                p.mMetadata[newName] = p.mMetadata.pop(oldName)

    def asTextLines(self, separator='\t'):
        return CSVSpectralLibraryIO.asTextLines(self, separator=separator)

    def asPickleDump(self):
        return pickle.dumps(self, SpectralLibrary._pickle_protocol)

    def exportProfiles(self, path=None):

        if path is None:

            path = QFileDialog.getSaveFileName(parent=None, caption="Save Spectral Library", filter=FILTERS)

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            if ext in ['.sli','.esl']:
                EnviSpectralLibraryIO.write(self, path)

            if ext in ['.csv']:
                CSVSpectralLibraryIO.write(self, path, separator='\t')

            s = ""

    sigProfilesRemoved = pyqtSignal(list)
    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        to_remove = self.extractProfileList(profiles)
        to_remove = [p for p in to_remove if p in self.mProfiles]
        if len(to_remove) > 0:
            for p in to_remove:
                self.mProfiles.remove(p)
            self.sigProfilesRemoved.emit(to_remove)
        return to_remove

    def yRange(self):
        minY = min([min(p.yValues()) for p in self.mProfiles])
        maxY = max([max(p.yValues()) for p in self.mProfiles])
        return  minY, maxY

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

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)


    def __len__(self):
        return len(self.mProfiles)

    def __iter__(self):
        return iter(self.mProfiles)

    def __getitem__(self, slice):
        return self.mProfiles[slice]

    def __delitem__(self, slice):
        profiles = self[slice]
        self.removeProfiles(profiles)

    def __eq__(self, other):
        if not isinstance(other, SpectralLibrary):
            return False

        if len(self) != len(other):
            return False

        for p1, p2 in zip(self.__iter__(), other.__iter__()):
            if p1 != p2:
                return False
        return True


class SpectralLibraryTableViewModel(QAbstractTableModel):

    #sigPlotStyleChanged = pyqtSignal(SpectralProfile)
    #sigAttributeRemoved = pyqtSignal(str)
    #sigAttributeAdded = pyqtSignal(str)

    class ProfileWrapper(object):
        def __init__(self, profile):
            assert isinstance(profile, SpectralProfile)
            self.profile = profile
            self.style = QColor('white')
            self.checkState = Qt.Unchecked

    def __init__(self, parent=None):
        super(SpectralLibraryTableViewModel, self).__init__(parent)

        self.cIndex = '#'
        self.cStyle = 'Style'
        self.cName = 'Name'
        self.cPxX = 'px x'
        self.cPxY = 'px y'
        self.cCRS = 'CRS'
        self.cGeoX = 'x'
        self.cGeoY = 'y'
        self.cSrc = 'Source'


        self.mAttributeColumns = []


        self.mSpecLib = SpectralLibrary()
        self.mProfileWrappers = OrderedDict()

    def addAttribute(self, name, i = None):
        assert isinstance(name, str)
        if name != self.cName and name not in self.mAttributeColumns:
            if i is None:
                i = len(self.mAttributeColumns)
            self.beginInsertColumns(QModelIndex(), i, i)
            self.mAttributeColumns.insert(i, name)
            self.endInsertColumns()

    def removeAttribute(self, name):
        assert isinstance(name, str)

        if name in self.mAttributeColumns:
            i = self.mAttributeColumns
            self.beginRemoveColumns(QModelIndex(), i,i)
            self.mAttributeColumns.remove(name)
            for s in self.mSpecLib:
                assert isinstance(s, SpectralProfile)
                if name in s.mMetadata.keys():
                    s.mMetadata.pop(name)
            self.endRemoveColumns()

    def columnNames(self):

        return [self.cIndex, self.cStyle, self.cName] + self.mAttributeColumns + \
               [self.cPxX, self.cPxY, self.cGeoX, self.cGeoY, self.cCRS, self.cSrc]


    def insertProfiles(self, profiles, i=None):
        if isinstance(profiles, SpectralLibrary):
            profiles = profiles[:]

        if not isinstance(profiles, list):
            profiles =  [profiles]

        profiles = [p for p in profiles if isinstance(p, SpectralProfile)]
        l = len(profiles)
        if l > 0:
            if i is None:
                i = len(self.mSpecLib)
            self.beginInsertRows(QModelIndex(), i, i + len(profiles) - 1)
            self.mSpecLib.addProfiles(profiles, i)
            self.endInsertRows()

            for p in profiles:
                self.mProfileWrappers[p] = SpectralLibraryTableViewModel.ProfileWrapper(p)
                # update attribute columns
            #self.mAttributeColumns = sorted(list(set(self.mAttributeColumns + self.mSpecLib.metadataAttributes())))

    def removeProfiles(self, profiles):
        if isinstance(profiles, SpectralLibrary):
            profiles = profiles[:]

        profiles = [p for p in profiles if isinstance(p, SpectralProfile) and p in self.mSpecLib]

        removed = []
        for p in profiles:
            idx = self.profile2idx(p)
            self.beginRemoveRows(QModelIndex(), idx.row(), idx.row())
            self.mSpecLib.removeProfiles([p])
            self.endRemoveRows()
            removed.append(p)

        for p in profiles:
            self.mProfileWrappers.pop(p)

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames()[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setHeaderData(self, col, orientation, newName, role=None):
        oldName = self.columnNames()[col]
        assert isinstance(newName, str)
        if orientation == Qt.Horizontal:
            if role == Qt.EditRole and oldName in self.mAttributeColumns:
                self.mSpecLib.renameMetadataAttribute(oldName, newName)
                self.headerDataChanged.emit()
                return True
        return False


    def sort(self, col, order):
        """Sort table by given column number.
        """
        return
        self.layoutAboutToBeChanged.emit()
        columnName = self.columnNames()[col]
        rev = order == Qt.DescendingOrder
        sortedProfiles = None
        profiles = self.mProfileWrappers.keys()
        if columnName == self.cName:
            sortedProfiles = sorted(profiles, key= lambda p: p.name(), reverse=rev)
        elif columnName == self.cSrc:
            sortedProfiles = sorted(profiles, key=lambda p: p.source(), reverse=rev)
        elif columnName == self.cIndex:
            sortedProfiles = sorted(profiles, key=lambda p: self.mSpecLib.index(p), reverse=rev)
        elif columnName in self.mAttributeColumns:
            sortedProfiles = sorted(profiles, key=lambda p: p.metadata(columnName), reverse=rev)
        if sortedProfiles is not None:
            tmp = OrderedDict([(p, self.mProfileWrappers[p]) for p in sortedProfiles])
            self.mProfileWrappers.clear()
            self.mProfileWrappers.update(tmp)
        self.layoutChanged.emit()

    def rowCount(self, parentIdx=None, *args, **kwargs):
        return len(self.mSpecLib)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.columnNames())

    def profile2idx(self, profile):
        assert isinstance(profile, SpectralProfile)
        #return self.createIndex(self.mSpecLib.index(profile), 0)
        #pw = self.mProfileWrappers[profile]
        if not profile in self.mProfileWrappers.keys():
            return None
        return self.createIndex(self.mProfileWrappers.keys().index(profile), 0)



    def idx2profileWrapper(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None
        return list(self.mProfileWrappers.values())[index.row()]

        """
        p = self.idx2profile(index)
        assert isinstance(p, SpectralProfile)
        pw = self.mProfileWrappers[p]
        assert isinstance(pw, SpectralLibraryTableViewModel.ProfileWrapper)
        return pw
        """

    def indices2profiles(self, indices):
        profiles = []
        for idx in indices:
            p = list(self.mProfileWrappers.keys())[idx.row()]
            if p not in profiles:
                profiles.append(p)
        return profiles


    def idx2profile(self, index):
        pw = self.idx2profileWrapper(index)
        if isinstance(pw, SpectralLibraryTableViewModel.ProfileWrapper):
            return  pw.profile
        else:
            return None

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        columnName = self.columnNames()[index.column()]
        profileWrapper = self.idx2profileWrapper(index)
        profile = profileWrapper.profile
        assert isinstance(profile, SpectralProfile)
        px = profile.pxCoordinate()
        geo = profile.geoCoordinate()
        value = None

        if role == Qt.DisplayRole:
            if columnName == self.cIndex:
                value = self.mSpecLib.index(profile)+1
            elif columnName == self.cName:
                value = profile.name()
            elif columnName == self.cSrc:
                value = profile.source()
            elif columnName in self.mAttributeColumns:
                value = profile.metadata(columnName)
                value = '' if value is None else value
            if px is not None:
                if columnName == self.cPxX:
                    value = profile.pxCoordinate().x()
                elif columnName == self.cPxY:
                    value = profile.pxCoordinate().y()

            if geo is not None:
                if columnName == self.cGeoX:
                    value = '{:0.10f}'.format(profile.geoCoordinate().x())
                elif columnName == self.cGeoY:
                    value = '{:0.10f}'.format(profile.geoCoordinate().y())
                elif columnName == self.cCRS:
                    value = profile.geoCoordinate().crs().authid()


        if role == Qt.BackgroundRole:
            if columnName == self.cStyle:
                return self.mProfileWrappers[profile].style

        if role == Qt.EditRole:
            if columnName == self.cName:
                value = profile.name()
            elif columnName in self.mAttributeColumns:
                value = profile.metadata(columnName)

        if role == Qt.UserRole:
            value = profile
        if role == Qt.CheckStateRole:
            if columnName == self.cIndex:
                value = profileWrapper.checkState
        return value


    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction


    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return False
        assert isinstance(index, QModelIndex)
        cName = self.columnNames()[index.column()]
        profileWrapper = self.idx2profileWrapper(index)
        profile = profileWrapper.profile

        if role  == Qt.EditRole:
            if cName == self.cName:
                profile.setName(value)
                return True
            if cName in self.mAttributeColumns:
                profile.setMetadata(cName, value)

        if role == Qt.CheckStateRole:
            if cName == self.cIndex:
                profileWrapper.checkState = value
                return True
        if role == Qt.BackgroundRole:
            if cName == self.cStyle:
                profileWrapper.style = value
                return True

        return False

    def supportedDragActions(self):
        return Qt.CopyAction

    def supportedDropActions(self):
        return Qt.CopyAction

    def dropMimeData(self, mimeData, action, row, column, parent):
        assert isinstance(mimeData, QMimeData)
        assert isinstance(parent, QModelIndex)

        if mimeData.hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):

            dump = mimeData.data(MimeDataHelper.MDF_SPECTRALLIBRARY)
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
        mimeData.setData(MimeDataHelper.MDF_SPECTRALLIBRARY, speclib.asPickleDump())

        #as text
        mimeData.setText('\n'.join(speclib.asTextLines()))

        return mimeData

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append(MimeDataHelper.MDF_DATASOURCETREEMODELDATA)
        types.append(MimeDataHelper.MDF_LAYERTREEMODELDATA)
        types.append(MimeDataHelper.MDF_URILIST)
        return types

    def flags(self, index):
        if index.isValid():
            columnName = self.columnNames()[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
            if columnName in [self.cName] + self.mAttributeColumns:  # allow check state
                flags = flags | Qt.ItemIsEditable | Qt.ItemIsUserCheckable
            if columnName == self.cIndex:
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

        self.mModel = SpectralLibraryTableViewModel()
        self.mSpeclib = self.mModel.mSpecLib

        self.mSpeclib.sigProfilesAdded.connect(self.onProfilesAdded)
        self.mSpeclib.sigProfilesRemoved.connect(self.onProfilesRemoved)
        self.mPlotDataItems = dict()


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
        if event.mimeData().hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
            event.accept()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if mimeData.hasFormat(MimeDataHelper.MDF_SPECTRALLIBRARY):
            speclib = SpectralLibrary.readFromPickleDump(mimeData.data(MimeDataHelper.MDF_SPECTRALLIBRARY))
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
        pi = self.getPlotItem()
        for p in profiles:
            self.removePDI(p)
        self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    def addSpeclib(self, speclib):
        if isinstance(speclib, SpectralLibrary):
            self.mModel.insertProfiles([p.clone() for p in speclib])
            #self.mSpeclib.addProfiles([copy.copy(p) for p in speclib])

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
        if not isinstance(self.mModel, SpectralLibraryTableViewModel):
            return None

        assert isinstance(selected, QItemSelection)
        assert isinstance(deselected, QItemSelection)

        for selectionRange in deselected:
            for idx in selectionRange.indexes():
                p = self.mModel.idx2profile(idx)
                pdi = self.mPlotDataItems[p]
                assert isinstance(pdi, SpectralProfilePlotDataItem)
                pdi.setPen(fn.mkPen(self.mModel.mProfileWrappers[p].style))
                pdi.setShadowPen(None)


        to_front = []
        for selectionRange in selected:
            for idx in selectionRange.indexes():
                p = self.mModel.idx2profile(idx)
                pdi = self.mPlotDataItems[p]
                assert isinstance(pdi, SpectralProfilePlotDataItem)
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

    import timeseriesviewer
    from timeseriesviewer.utils import initQgisApplication

    app = initQgisApplication()
    app.messageLog().messageReceived.connect(lambda args: print(args) )


    sl = SpectralLibrary.readFrom(r'D:\Temp\myspeclibPX.sli')

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
    #view.show()
    W = SpectralLibraryWidget()
    W.show()
    W.addSpeclib(sl)
    #m.mSpecLib.addProfile(spec0)

    if False:
        w =SpectralLibraryTableView()
        #w = SpectralLibraryWidget()
        w.mSpeclib.addProfile(spec0)
        #w.addSpeclib(sl)
        w.show()

    app.exec_()

