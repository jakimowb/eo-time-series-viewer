# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2017-08-04
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

import os, sys, pickle, datetime, re, collections

from collections import OrderedDict
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.Qt import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph import AxisItem
from osgeo import ogr, osr, gdal
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument
from timeseriesviewer.plotstyling import PlotStyle
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderTask
from timeseriesviewer.utils import *
from timeseriesviewer.spectrallibraries import createQgsField
from timeseriesviewer.models import OptionListModel, Option
LABEL_EXPRESSION_2D = 'DN or Index'
LABEL_TIME = 'Date'
DEBUG = False
OPENGL_AVAILABLE = False

DEFAULT_CRS = QgsCoordinateReferenceSystem('EPSG:4326')

FN_ID = 'id'
FN_X = 'x'
FN_Y = 'y'
FN_NAME = 'name'
FN_N_TOTAL = 'n'
FN_N_NODATA = 'no_data'
FN_N_LOADED = 'loaded'
FN_N_LOADED_PERCENT = 'percent'

try:
    import OpenGL

    OPENGL_AVAILABLE = True

except:
    pass



def sensorExampleQgsFeature(sensor, singleBandOnly=False):
    # populate with exemplary band values (generally stored as floats)

    if sensor is None:
        singleBandOnly = True

    fieldValues = collections.OrderedDict()
    if singleBandOnly:
        fieldValues['b'] = 1.0
    else:
        assert isinstance(sensor, SensorInstrument)
        for b in range(sensor.nb):
            fn = bandIndex2bandKey(b)
            fieldValues[fn] = 1.0

    date = datetime.date.today()
    doy = dateDOY(date)
    fieldValues['doy'] = doy
    fieldValues['date'] = str(date)


    fields = QgsFields()
    for k, v in fieldValues.items():
        fields.append(createQgsField(k,v))
    f = QgsFeature(fields)
    for k, v in fieldValues.items():
        f.setAttribute(k, v)
    return f


def dateDOY(date):
    if isinstance(date, np.datetime64):
        date = date.astype(datetime.date)
    return date.timetuple().tm_yday

def daysPerYear(year):

    if isinstance(year, np.datetime64):
        year = year.astype(datetime.date)
    if isinstance(year, datetime.date):
        year = year.timetuple().tm_year

    return dateDOY(datetime.date(year=year, month=12, day=31))

def date2num(d):
    #kindly taken from https://stackoverflow.com/questions/6451655/python-how-to-convert-datetime-dates-to-decimal-years
    if isinstance(d, np.datetime64):
        d = d.astype(datetime.datetime)

    if isinstance(d, QDate):
        d = datetime.date(d.year(), d.month(), d.day())

    assert isinstance(d, datetime.date)

    yearDuration = daysPerYear(d)
    yearElapsed = d.timetuple().tm_yday
    fraction = float(yearElapsed) / float(yearDuration)
    if fraction == 1.0:
        fraction = 0.9999999
    return float(d.year) + fraction

def num2date(n, dt64=True, qDate=False):
    n = float(n)
    if n < 1:
        n += 1

    year = int(n)
    fraction = n - year
    yearDuration = daysPerYear(year)
    yearElapsed = fraction * yearDuration

    import math
    doy = round(yearElapsed)
    if doy < 1:
        doy = 1
    try:
        date = datetime.date(year, 1, 1) + datetime.timedelta(days=doy-1)
    except:
        s = ""
    if qDate:
        return QDate(date.year, date.month, date.day)
    if dt64:
        return np.datetime64(date)
    else:
        return date



    #return np.datetime64('{:04}-01-01'.format(year), 'D') + np.timedelta64(int(yearElapsed), 'D')


def saveTemporalProfiles(profiles, path, mode='all', sep=',', loadMissingValues=False):
    if path is None or len(path) == 0:
        return

    assert mode in ['coordinate','all']

    nbMax = 0
    for sensor in profiles[0].timeSeries().sensors():
        assert isinstance(sensor, SensorInstrument)
        nbMax = max(nbMax, sensor.nb)

    ext = os.path.splitext(path)[1].lower()

    assert isinstance(ext, str)
    if ext.startswith('.'):
        ext = ext[1:]

    if loadMissingValues:
        for p in profiles:
            assert isinstance(p, TemporalProfile)
            p.loadMissingData()


    if ext == 'csv':
        #write a flat list of profiles
        lines = ['Temporal Profiles']
        lines.append(sep.join(['pid', 'name', 'date', 'img', 'location', 'band values']))

        for nP, p in enumerate(profiles):
            assert isinstance(p, TemporalProfile)
            lines.append('Profile {} "{}": {}'.format(p.mID, p.name(), p.coordinate()))
            assert isinstance(p, TemporalProfile)
            c = p.coordinate()
            for i, tsd in enumerate(p.mTimeSeries):
                assert isinstance(tsd, TimeSeriesDatum)

                data = p.data(tsd)
                line = [p.id(), p.name(), data['date'], tsd.pathImg, c.asWkt()]
                for b in range(tsd.sensor.nb):
                    key = 'b{}'.format(b+1)
                    if key in data.keys():
                        line.append(data[key])
                    else:
                        line.append('')

                line = sep.join([str(l) for l in line])
                lines.append(line)
        file = open(path, 'w', encoding='utf8')
        file.writelines('\n'.join(lines))
        file.flush()
        file.close()

    else:

        drv = None
        for i in range(ogr.GetDriverCount()):
            d = ogr.GetDriver(i)
            driverExtensions = d.GetMetadataItem('DMD_EXTENSIONS')
            if driverExtensions is not None and ext in driverExtensions:
                drv = d
                break

        if not isinstance(drv, ogr.Driver):
            raise Exception('Unable to find a OGR driver to write {}'.format(path))


        drvMEM = ogr.GetDriverByName('Memory')
        assert isinstance(drvMEM, ogr.Driver)
        dsMEM = drvMEM.CreateDataSource('')
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        crs = DEFAULT_CRS
        assert isinstance(dsMEM, ogr.DataSource)
        #lines.append(sep.join(['pid', 'name', 'date', 'img', 'location', 'band values']))
        lyr = dsMEM.CreateLayer(os.path.basename(path), srs, ogr.wkbPoint)
        lyr.CreateField(ogr.FieldDefn('pid', ogr.OFTInteger64))
        lyr.CreateField(ogr.FieldDefn('name', ogr.OFTString))
        lyr.CreateField(ogr.FieldDefn('date', ogr.OFTDateTime))
        lyr.CreateField(ogr.FieldDefn('doy', ogr.OFTInteger))
        lyr.CreateField(ogr.FieldDefn('img', ogr.OFTString))
        lyr.CreateField(ogr.FieldDefn('lat', ogr.OFTReal))
        lyr.CreateField(ogr.FieldDefn('lon', ogr.OFTReal))
        lyr.CreateField(ogr.FieldDefn('nodata', ogr.OFTBinary))

        for b in range(nbMax):
            lyr.CreateField(ogr.FieldDefn('b{}'.format(b+1), ogr.OFTReal))


        for iP, p in enumerate(profiles):
            assert isinstance(p, TemporalProfile)

            c = p.coordinate().toCrs(crs)
            assert isinstance(c, SpatialPoint)

            for iT, tsd in enumerate(p.timeSeries()):
                feature = ogr.Feature(lyr.GetLayerDefn())
                assert isinstance(feature, ogr.Feature)
                data = p.data(tsd)
                assert isinstance(tsd, TimeSeriesDatum)
                feature.SetField('pid', p.id())
                feature.SetField('name', p.name())
                feature.SetField('date', str(tsd.date))
                feature.SetField('doy', int(tsd.doy))

                feature.SetField('img', tsd.pathImg)
                feature.SetField('lon', c.x())
                feature.SetField('lat', c.y())

                point = ogr.CreateGeometryFromWkt(c.asWkt())
                feature.SetGeometry(point)

                if 'nodata' in data.keys():
                    feature.SetField('nodata', data['nodata'])

                for b in range(tsd.sensor.nb):
                    key = 'b{}'.format(b+1)
                    if key in data.keys():
                        feature.SetField(key, data[key])
                lyr.CreateFeature(feature)
        drv.CopyDataSource(dsMEM, path)

        pass


regBandKey = re.compile(r"(?<!\w)b\d+(?!\w)", re.IGNORECASE)
regBandKeyExact = re.compile(r'^' + regBandKey.pattern + '$', re.IGNORECASE)


def bandIndex2bandKey(i):
    assert isinstance(i, int)
    assert i >= 0
    return 'b{}'.format(i + 1)

def bandKey2bandIndex(key):
    match = regBandKeyExact.search(key)
    assert match
    idx = int(match.group()[1:]) - 1
    return idx



class DateTimePlotWidget(pg.PlotWidget):
    """
    Subclass of PlotWidget
    """
    def __init__(self, parent=None):
        """
        Constructor of the widget
        """
        super(DateTimePlotWidget, self).__init__(parent)
        self.plotItem = pg.PlotItem(
            axisItems={'bottom':DateTimeAxis(orientation='bottom')}
            ,viewBox=DateTimeViewBox()
        )
        self.setCentralItem(self.plotItem)
        #self.xAxisInitialized = False

        pi = self.getPlotItem()
        pi.getAxis('bottom').setLabel(LABEL_TIME)
        pi.getAxis('left').setLabel(LABEL_EXPRESSION_2D)

        self.mInfoColor = QColor('yellow')
        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)
        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoLabelCursor.setColor(QColor('yellow'))

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())
        #self.plot2DLabel.setAnchor()
        #self.plot2DLabel.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(0, 0))
        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)

        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self.onMouseMoved2D)

    def resetViewBox(self):
        self.plotItem.getViewBox().autoRange()


    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        if plotItem.sceneBoundingRect().contains(pos):
            vb = plotItem.vb
            assert isinstance(vb, DateTimeViewBox)
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            if x >= 0:
                y = mousePoint.y()
                date = num2date(x)
                doy = dateDOY(date)
                plotItem.vb.updateCurrentDate(num2date(x, dt64=True))
                self.mInfoLabelCursor.setText('DN {:0.2f}\nDate {}\nDOY {}'.format(
                                              mousePoint.y(), date, doy),
                                              color=self.mInfoColor)

                s = self.size()
                pos = QPointF(s.width(), 0)
                self.mInfoLabelCursor.setVisible(vb.mActionShowCursorValues.isChecked())
                self.mInfoLabelCursor.setPos(pos)

                b = vb.mActionShowCrosshair.isChecked()
                self.mCrosshairLineH.setVisible(b)
                self.mCrosshairLineV.setVisible(b)
                self.mCrosshairLineH.pen.setColor(self.mInfoColor)
                self.mCrosshairLineV.pen.setColor(self.mInfoColor)
                self.mCrosshairLineV.setPos(mousePoint.x())
                self.mCrosshairLineH.setPos(mousePoint.y())


class DateTimeAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(DateTimeAxis, self).__init__(*args, **kwds)
        self.setRange(1,3000)
        self.enableAutoSIPrefix(False)
        self.labelAngle = 0

    def logTickStrings(self, values, scale, spacing):
        s = ""


    def tickStrings(self, values, scale, spacing):
        strns = []

        if len(values) == 0:
            return []
        #assert isinstance(values[0],

        values = [num2date(v) if v > 0 else num2date(1) for v in values]
        rng = max(values)-min(values)
        ndays = rng.astype(int)

        strns = []

        for v in values:
            if ndays == 0:
                strns.append(v.astype(str))
            else:
                strns.append(v.astype(str))

        return strns

    def tickValues(self, minVal, maxVal, size):
        d = super(DateTimeAxis, self).tickValues(minVal, maxVal, size)

        return d


    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):


        p.setRenderHint(p.Antialiasing, False)
        p.setRenderHint(p.TextAntialiasing, True)

        ## draw long line along axis
        pen, p1, p2 = axisSpec
        p.setPen(pen)
        p.drawLine(p1, p2)
        p.translate(0.5, 0)  ## resolves some damn pixel ambiguity

        ## draw ticks
        for pen, p1, p2 in tickSpecs:
            p.setPen(pen)
            p.drawLine(p1, p2)


        ## Draw all text
        if self.tickFont is not None:
            p.setFont(self.tickFont)
        p.setPen(self.pen())

        #for rect, flags, text in textSpecs:
        #    p.drawText(rect, flags, text)
        #    # p.drawRect(rect)

        #see https://github.com/pyqtgraph/pyqtgraph/issues/322
        for rect, flags, text in textSpecs:
            p.save()  # save the painter state
            p.translate(rect.center())   # move coordinate system to center of text rect
            p.rotate(self.labelAngle)  # rotate text
            p.translate(-rect.center())  # revert coordinate system
            p.drawText(rect, flags, text)
            p.restore()  # restore the painter state



class DateTimeViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    sigMoveToDate = pyqtSignal(np.datetime64)
    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(DateTimeViewBox, self).__init__(parent)
        #self.menu = None # Override pyqtgraph ViewBoxMenu
        #self.menu = self.getMenu() # Create the menu
        #self.menu = None
        self.mCurrentDate = np.datetime64('today')
        self.mXAxisUnit = 'date'
        xAction = [a for a in self.menu.actions() if a.text() == 'X Axis'][0]
        yAction = [a for a in self.menu.actions() if a.text() == 'Y Axis'][0]

        menuXAxis = self.menu.addMenu('X Axis')
        #define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()

        frame.setLayout(l)
        #l.addWidget(self, QWidget, int, int, alignment: Qt.Alignment = 0): not enough arguments
        self.rbXManualRange = QRadioButton('Manual')
        self.dateEditX0 = QDateEdit()
        self.dateEditX0.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('Start time')
        self.dateEditX0.setCalendarPopup(True)
        self.dateEditX0.dateChanged.connect(self.updateXRange)
        self.dateEditX1 = QDateEdit()
        self.dateEditX1.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('End time')
        self.dateEditX1.setCalendarPopup(True)
        self.dateEditX1.dateChanged.connect(self.updateXRange)

        self.rbXAutoRange = QRadioButton('Auto')
        self.rbXAutoRange.setChecked(True)
        self.rbXAutoRange.toggled.connect(self.updateXRange)


        l.addWidget(self.rbXManualRange, 0,0)
        l.addWidget(self.dateEditX0, 0,1)
        l.addWidget(self.dateEditX1, 0,2)
        l.addWidget(self.rbXAutoRange, 1, 0)

        l.setMargin(1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuXAxis)
        wa.setDefaultWidget(frame)
        menuXAxis.addAction(wa)


        self.menu.insertMenu(xAction, menuXAxis)
        self.menu.removeAction(xAction)

        self.mActionMoveToDate = self.menu.addAction('Move to {}'.format(self.mCurrentDate))
        self.mActionMoveToDate.triggered.connect(lambda : self.sigMoveToDate.emit(self.mCurrentDate))
        self.mActionShowCrosshair = self.menu.addAction('Show Crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)
        self.mActionShowCursorValues = self.menu.addAction('Show Mouse values')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

    sigXAxisUnitChanged = pyqtSignal(str)
    def setXAxisUnit(self, unit):
        assert unit in ['date', 'doy']
        old = self.mXAxisUnit
        self.mXAxisUnit = unit
        if old != self.mXAxisUnit:
            self.sigXAxisUnitChanged.emit(self.mXAxisUnit)

    def xAxisUnit(self):
        return self.mXAxisUnit

    def updateXRange(self, *args):
        isAutoRange = self.rbXAutoRange.isChecked()
        self.enableAutoRange('x', isAutoRange)

        self.dateEditX0.setEnabled(not isAutoRange)
        self.dateEditX1.setEnabled(not isAutoRange)

        if not isAutoRange:
            t0 = date2num(self.dateEditX0.date())
            t1 = date2num(self.dateEditX1.date())
            t0 = min(t0, t1)
            t1 = max(t0, t1)

            self.setXRange(t0, t1)

    def updateCurrentDate(self, date):
        if isinstance(date, np.datetime64):
            self.mCurrentDate = date
            self.mActionMoveToDate.setData(date)
            self.mActionMoveToDate.setText('Move maps to {}'.format(date))



    def raiseContextMenu(self, ev):

        pt = self.mapDeviceToView(ev.pos())
        self.updateCurrentDate(num2date(pt.x(), dt64=True))

        xRange, yRange = self.viewRange()
        t0 = num2date(xRange[0], qDate=True)
        t1 = num2date(xRange[1], qDate=True)
        self.dateEditX0.setDate(t0)
        self.dateEditX1.setDate(t1)

        menu = self.getMenu(ev)
        self.scene().addParentContextMenus(self, menu, ev)
        menu.exec_(ev.screenPos().toPoint())


class TemporalProfilePlotStyleBase(PlotStyle):

    sigStyleUpdated = pyqtSignal()
    sigDataUpdated = pyqtSignal()
    sigExpressionUpdated = pyqtSignal()
    sigSensorChanged = pyqtSignal(SensorInstrument)

    def __init__(self, parent=None, temporalProfile=None):
        super(TemporalProfilePlotStyleBase, self).__init__()
        self.mSensor = None
        self.mTP = None
        self.mExpression = 'b1'
        self.mPlotItems = []
        self.mIsVisible = True

        if isinstance(temporalProfile, TemporalProfile):
            self.setTemporalProfile(temporalProfile)

    def isPlotable(self):
        return self.isVisible() and isinstance(self.temporalProfile(), TemporalProfile) and isinstance(self.sensor(), SensorInstrument)

    def createPlotItem(self):
        raise NotImplementedError()

    def temporalProfile(self):
        return self.mTP

    def setTemporalProfile(self, temporalPofile):

        b = temporalPofile != self.mTP
        self.mTP = temporalPofile
        if temporalPofile in [None, QVariant()]:
            s  =""
        else:
            assert isinstance(temporalPofile, TemporalProfile)
        if b:
            self.updateDataProperties()

    def setSensor(self, sensor):
        assert sensor is None or isinstance(sensor, SensorInstrument)
        b = sensor != self.mSensor
        self.mSensor = sensor
        if b:
            self.update()
            self.sigSensorChanged.emit(sensor)

    def sensor(self):
        return self.mSensor

    def updateStyleProperties(self):
        raise NotImplementedError()

    def updateDataProperties(self):
        raise NotImplementedError()

    def update(self):
        self.updateDataProperties()

    def setExpression(self, exp):
        assert isinstance(exp, str)
        b = self.mExpression != exp
        self.mExpression = exp
        self.updateDataProperties()
        if b:
            self
            self.sigExpressionUpdated.emit()

    def expression(self):
        return self.mExpression

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = super(TemporalProfile2DPlotStyle, self).__getstate__()
        #remove
        del result['mTP']
        del result['mSensor']

        return result

    def isVisible(self):
        return self.mIsVisible

    def setVisibility(self, b):
        assert isinstance(b, bool)
        old = self.isVisible()
        self.mIsVisible = b

        if b != old:
            self.updateStyleProperties()
            #self.update()

    def copyFrom(self, plotStyle):
        if isinstance(plotStyle, PlotStyle):
            super(TemporalProfilePlotStyleBase, self).copyFrom(plotStyle)
            self.updateStyleProperties()

        if isinstance(plotStyle, TemporalProfilePlotStyleBase):
            self.setExpression(plotStyle.expression())
            self.setSensor(plotStyle.sensor())
            self.setTemporalProfile(plotStyle.temporalProfile())
            self.updateDataProperties()




class TemporalProfile2DPlotStyle(TemporalProfilePlotStyleBase):


    def __init__(self, temporalProfile=None):
        super(TemporalProfile2DPlotStyle, self).__init__(temporalProfile=temporalProfile)
        #PlotStyle.__init__(self)
       #TemporalProfilePlotStyleBase.__init__(self, temporalProfile=temporalProfile)

    def createPlotItem(self, plotWidget):
        pdi = TemporalProfilePlotDataItem(self)
        self.mPlotItems.append(pdi)
        return pdi

    def updateStyleProperties(self):
        for pdi in self.mPlotItems:
            assert isinstance(pdi, TemporalProfilePlotDataItem)
            pdi.updateStyle()

    def updateDataProperties(self):
        for pdi in self.mPlotItems:
            assert isinstance(pdi, TemporalProfilePlotDataItem)
            pdi.updateDataAndStyle()







class TemporalProfile(QObject):


    sigNameChanged = pyqtSignal(str)
    sigDataChanged = pyqtSignal()

    def __init__(self, layer, fid):
        super(TemporalProfile, self).__init__()
        assert isinstance(layer, TemporalProfileLayer)
        assert fid >= 0

        self.mID = fid
        self.mLayer = layer
        self.mTimeSeries = layer.timeSeries()
        assert isinstance(self.mTimeSeries, TimeSeries)
        self.mData = {}
        self.mUpdated = False
        self.mLoaded = self.mLoadedMax = self.mNoData = 0

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            meta = {'doy': tsd.doy,
                    'date': str(tsd.date),
                    'nodata':False}

            self.updateData(tsd, meta, skipStatusUpdate=True)
        #self.updateLoadingStatus()
        s = ""



    def __hash__(self):
        return hash('{}{}'.format(self.mID, self.mLayer.layerId()))

    def __eq__(self, other):
        """
        Two temporal profiles are equal if they have the same feature id and source layer
        :param other:
        :return:
        """

        if not isinstance(other, TemporalProfile):
            return False

        return other.mID == self.mID and self.mLayer == other.mLayer

    def geometry(self):
        return self.mLayer.getFeature(self.mID).geometry()

    def coordinate(self):
        x,y = self.geometry().asPoint()
        return SpatialPoint(self.mLayer.crs(), x,y)

    def id(self):
        """Feature ID in connected QgsVectorLayer"""
        return self.mID

    def attribute(self, key):
        f = self.mLayer.getFeature(self.mID)
        return f.attribute(f.fieldNameIndex(key))

    def setAttribute(self, key, value):
        f = self.mLayer.getFeature(self.id())

        b = self.mLayer.isEditable()
        self.mLayer.startEditing()
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(key), value)
        self.mLayer.saveEdits(leaveEditable=b)

    def name(self):
        return self.attribute('name')

    def setName(self, name:str):
        self.setAttribute('name', name)

    def data(self):
        return self.mData

    def timeSeries(self):
        return self.mTimeSeries

    def pullDataUpdate(self, d):
        assert isinstance(d, PixelLoaderTask)
        if d.success() and self.mID in d.temporalProfileIDs:
            i = d.temporalProfileIDs.index(self.mID)
            tsd = self.mTimeSeries.getTSD(d.sourcePath)
            assert isinstance(tsd, TimeSeriesDatum)

            values = {}
            if d.validPixelValues(i):
                profileData = d.resProfiles[i]

                vMean, vStd = profileData

                validValues = not isinstance(vMean, str)
                # 1. add the pixel values per returned band

                for iBand, bandIndex in enumerate(d.bandIndices):
                    key = 'b{}'.format(bandIndex + 1)
                    values[key] = vMean[iBand] if validValues else None
                    key = 'std{}'.format(bandIndex + 1)
                    values[key] = vStd[iBand] if validValues else None
            else:
                values['nodata'] = True

            self.updateData(tsd, values)


    def loadMissingData(self, showGUI=False):
        """
        Loads the missing data
        :return:
        """
        from timeseriesviewer.pixelloader import PixelLoaderTask, doLoaderTask
        tasks = []
        for tsd in self.mTimeSeries:
            missingIndices = self.missingBandIndices(tsd)

            if len(missingIndices) > 0:
                task = PixelLoaderTask(tsd.pathImg, [self.coordinate()],
                                       bandIndices=missingIndices,
                                       temporalProfileIDs=[self.mID])
                tasks.append(task)


        for task in tasks:
            result = doLoaderTask(task)
            assert isinstance(result, PixelLoaderTask)
            self.pullDataUpdate(result)

    def missingBandIndices(self, tsd, requiredIndices=None):
        """
        Returns the band indices [0, sensor.nb) that have not been loaded yet.
        :param tsd: TimeSeriesDatum of interest
        :param requiredIndices: optional subset of possible band-indices to return the missing ones from.
        :return: [list-of-indices]
        """
        assert isinstance(tsd, TimeSeriesDatum)
        if requiredIndices is None:
            requiredIndices = list(range(tsd.sensor.nb))
        requiredIndices = [i for i in requiredIndices if i >= 0 and i < tsd.sensor.nb]
        existingBandIndices = [bandKey2bandIndex(k) for k in self.data(tsd).keys() if regBandKeyExact.search(k)]
        return [i for i in requiredIndices if i not in existingBandIndices]


    def plot(self):

        import pyqtgraph as pg

        for sensor in self.mTimeSeries.sensors():
            assert isinstance(sensor, SensorInstrument)

            plotStyle = TemporalProfile2DPlotStyle(self)
            plotStyle.setSensor(sensor)

            pi = TemporalProfilePlotDataItem(plotStyle)
            pi.setClickable(True)
            pw = pg.plot(title=self.name())
            pw.plotItem().addItem(pi)
            pi.setColor('green')
            pg.QAPP.exec_()

    def updateData(self, tsd, values, skipStatusUpdate=False):
        assert isinstance(tsd, TimeSeriesDatum)
        assert isinstance(values, dict)

        if tsd not in self.mData.keys():
            self.mData[tsd] = {}

        self.mData[tsd].update(values)
        if not skipStatusUpdate:
            self.updateLoadingStatus()
            self.mUpdated = True
            self.sigDataChanged.emit()

    def resetUpdatedFlag(self):
        self.mUpdated = False

    def updated(self):
        return self.mUpdated

    def dataFromExpression(self, sensor, expression:str, dateType='date'):
        assert dateType in ['date','doy']
        x = []
        y = []


        if not isinstance(expression, QgsExpression):
            expression = QgsExpression(expression)
        assert isinstance(expression, QgsExpression)
        expression = QgsExpression(expression)

        #define required QgsFields
        fields = QgsFields()
        sensorTSDs = sorted([tsd for tsd in self.mData.keys() if tsd.sensor == sensor])
        for tsd in sensorTSDs:
            data = self.mData[tsd]
            for k, v in data.items():
                if v is not None and fields.indexFromName(k) == -1:
                    fields.append(createQgsField(k, v))

        for i, tsd in enumerate(sensorTSDs):
            assert isinstance(tsd, TimeSeriesDatum)
            data = self.mData[tsd]
            context = QgsExpressionContext()
            context.setFields(fields)

            #scope = QgsExpressionContextScope()
            f = QgsFeature(fields)
            for k, v in data.items():
                setQgsFieldValue(f, k, v)

            context.setFeature(f)
           # scope.setFeature(f)
            #context.appendScope(scope)
            #value = expression.evaluatePrepared(f)
            value = expression.evaluate(context)


            if value in [None, QVariant()]:
                s = ""
            else:
                if dateType == 'date':
                    x.append(date2num(tsd.date))
                elif dateType == 'doy':
                    x.append(tsd.doy)
                y.append(value)

        #return np.asarray(x), np.asarray(y)
        assert len(x) == len(y)
        return x, y

    def data(self, tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        if self.hasData(tsd):
            return self.mData[tsd]
        else:
            return {}


    def loadingStatus(self):
        """
        Returns the loading status in terms of single pixel values.
        nLoaded = sum of single band values
        nLoadedMax = potential maximum of band values that might be loaded
        :return: (nLoaded, nLoadedMax)
        """
        return self.mLoaded, self.mNoData, self.mLoadedMax

    def updateLoadingStatus(self):
        """
        Calculates the loading status in terms of single pixel values.
        nMax is the sum of all bands over each TimeSeriesDatum and Sensors
        """

        self.mLoaded = 0
        self.mLoadedMax = 0
        self.mNoData = 0

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            nb = tsd.sensor.nb

            self.mLoadedMax += nb
            if self.hasData(tsd):
                if self.isNoData(tsd):
                    self.mNoData += nb
                else:
                    self.mLoaded += len([k for k in self.mData[tsd].keys() if regBandKey.search(k)])

        f = self.mLayer.getFeature(self.id())

        b = self.mLayer.isEditable()
        self.mLayer.startEditing()
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_NODATA), self.mNoData)
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_TOTAL), self.mLoadedMax)
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED), self.mLoaded)
        self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED_PERCENT), round(100. * float(self.mLoaded + self.mNoData) / self.mLoadedMax,2))

        self.mLayer.saveEdits(leaveEditable=b)
        s = ""
    def isNoData(self, tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        return self.mData[tsd]['nodata']

    def hasData(self, tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        return tsd in self.mData.keys()

    def __repr__(self):
        return 'TemporalProfile {}'.format(self.mID)


class TemporalProfilePlotDataItem(pg.PlotDataItem):

    def __init__(self, plotStyle, parent=None):
        assert isinstance(plotStyle, TemporalProfile2DPlotStyle)


        super(TemporalProfilePlotDataItem, self).__init__([], [], parent=parent)
        self.menu = None
        #self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.mPlotStyle = plotStyle
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.mPlotStyle.sigUpdated.connect(self.updateDataAndStyle)
        self.updateStyle()

    # On right-click, raise the context menu
    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def getContextMenus(self, event=None):
        if self.menu is None:
            self.menu = QMenu()
            self.menu.setTitle(self.name + " options..")

            green = QAction("Turn green", self.menu)
            green.triggered.connect(self.setGreen)
            self.menu.addAction(green)
            self.menu.green = green

            blue = QAction("Turn blue", self.menu)
            blue.triggered.connect(self.setBlue)
            self.menu.addAction(blue)
            self.menu.green = blue

            alpha = QWidgetAction(self.menu)
            alphaSlider = QSlider()
            alphaSlider.setOrientation(QtCore.Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu


    def updateDataAndStyle(self):

        TP = self.mPlotStyle.temporalProfile()
        sensor = self.mPlotStyle.sensor()

        if isinstance(TP, TemporalProfile) and isinstance(sensor, SensorInstrument):
            x, y = TP.dataFromExpression(self.mPlotStyle.sensor(), self.mPlotStyle.expression(), dateType='date')
            if len(y) > 0:
                x = np.asarray(x, dtype=np.float)
                y = np.asarray(y, dtype=np.float)
                self.setData(x=x, y=y)
            else:
                self.setData(x=[], y=[]) # dummy
        else:
            self.setData(x=[], y=[])  # dummy for empty data
        self.updateStyle()


    def updateStyle(self):
        """
        Updates visibility properties
        """
        from pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol
#        path = drawSymbol(p, self.markerSymbol, self.markerSize, self.markerPen, self.markerBrush)
    #                    #painter, symbol, size, pen, brush
        self.setVisible(self.mPlotStyle.isVisible())
        self.setSymbol(self.mPlotStyle.markerSymbol)
        self.setSymbolSize(self.mPlotStyle.markerSize)
        self.setSymbolBrush(self.mPlotStyle.markerBrush)
        self.setSymbolPen(self.mPlotStyle.markerPen)
        self.setPen(self.mPlotStyle.linePen)
        self.update()

        #self.setPen(fn.mkPen(self.mPlotStyle.linePen))
        #self.setFillBrush(fn.mkBrush(self.mPlotStyle.mExpression))
        #self.setSymbolBrush(fn.mkBrush(self.mPlotStyle.markerBrush))

        # self.setFillBrush(self.mPlotStyle.)

        #self.update()

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



class TemporalProfileLayer(QgsVectorLayer):
    """
    A collection to store the TemporalProfile data delivered by a PixelLoader
    """

    #sigSensorAdded = pyqtSignal(SensorInstrument)
    #sigSensorRemoved = pyqtSignal(SensorInstrument)
    #sigPixelAdded = pyqtSignal()
    #sigPixelRemoved = pyqtSignal()

    sigTemporalProfilesAdded = pyqtSignal(list)
    sigTemporalProfilesRemoved = pyqtSignal(list)
    sigMaxProfilesChanged = pyqtSignal(int)


    def __init__(self, timeSeries, name='Temporal Profiles'):
        assert isinstance(timeSeries, TimeSeries)
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        uri = 'Point?crs={}'.format(crs.authid())
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(TemporalProfileLayer, self).__init__(uri, name, 'memory', lyrOptions)

        from collections import OrderedDict
        self.mProfiles = OrderedDict()
        self.mTimeSeries = timeSeries
        #symbol = QgsFillSymbol.createSimple({'style': 'no', 'color': 'red', 'outline_color': 'black'})
        #self.mLocations.renderer().setSymbol(symbol)
        self.mNextID = 1
        self.mMaxProfiles = 64
        self.TS = None

        fields = QgsFields()
        fields.append(createQgsField(FN_ID, self.mNextID))
        fields.append(createQgsField(FN_NAME,''))
        fields.append(createQgsField(FN_X, 0.0, comment='Longitude'))
        fields.append(createQgsField(FN_Y, 0.0, comment='Latitude'))
        fields.append(createQgsField(FN_N_TOTAL, 0, comment='Total number of band values'))
        fields.append(createQgsField(FN_N_NODATA,0, comment='Total of no-data values.'))
        fields.append(createQgsField(FN_N_LOADED, 0, comment='Loaded valid band values.'))
        fields.append(createQgsField(FN_N_LOADED_PERCENT,0.0, comment='Loading progress (%)'))
        assert self.startEditing()
        assert self.dataProvider().addAttributes(fields)
        assert self.commitChanges()
        self.initConditionalStyles()

        self.committedFeaturesAdded.connect(self.onFeaturesAdded)
        self.committedFeaturesRemoved.connect(self.onFeaturesRemoved)

    def __getitem__(self, slice):
        return list(self.mProfiles.values())[slice]

    def timeSeries(self):
        """
        Returns the TimeSeries instance.
        :return: TimeSeries
        """
        return self.mTimeSeries


    def onFeaturesAdded(self, layerID, addedFeatures):
        """
        Create a TemporalProfile object for each QgsFeature added to the backend QgsVectorLayer
        :param layerID:
        :param addedFeatures:
        :return:
        """

        if len(addedFeatures) > 0:

            temporalProfiles = []
            for feature in addedFeatures:
                fid = feature.id()
                if fid < 0:
                    continue
                tp = TemporalProfile(self, fid)

                self.mProfiles[fid] = tp
                temporalProfiles.append(tp)

            if len(temporalProfiles) > 0:
                pass
                #self.sigTemporalProfilesAdded.emit(temporalProfiles)


    def onFeaturesRemoved(self,  layerID, removedFIDs):
        if len(removedFIDs) > 0:

            toRemove = []

            for fid in removedFIDs:
                toRemove.append(self.mProfiles.pop(fid))

            self.sigTemporalProfilesRemoved.emit(toRemove)


    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fields().names():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])
        #styles.setRowStyles([red])


    def createTemporalProfiles(self, coordinates):
        """
        Creates temporal profiles
        :param coordinates:
        :return:
        """
        if not isinstance(coordinates, list):
            coordinates = [coordinates]

        features = []
        n = self.featureCount()
        for i, coordinate in enumerate(coordinates):
            assert isinstance(coordinate, SpatialPoint)

            f = QgsFeature(self.fields())
            f.setGeometry(QgsGeometry.fromPointXY(coordinate.toCrs(self.crs())))
            f.setAttribute(FN_ID, self.mNextID)
            f.setAttribute(FN_NAME, 'Location {}'.format(self.mNextID))
            f.setAttribute(FN_X, coordinate.x())
            f.setAttribute(FN_Y, coordinate.y())
            f.setAttribute(FN_N_LOADED_PERCENT, 0.0)
            f.setAttribute(FN_N_LOADED, 0)
            f.setAttribute(FN_N_TOTAL, 0)
            f.setAttribute(FN_N_NODATA, 0)
            self.mNextID += 1
            features.append(f)

        b = self.isEditable()
        tps_before = list(self.mProfiles.values())
        self.startEditing()
        success = self.addFeatures(features)
        self.saveEdits(leaveEditable=b)


        if success:
            assert n+len(features) == self.featureCount()
            assert self.featureCount() == len(self.mProfiles)
            profiles = [tp for tp in self.mProfiles.values() if tp not in tps_before]
            for p in profiles:
                p.updateLoadingStatus()
            return profiles
        else:
            return None


    def saveEdits(self, leaveEditable=True, triggerRepaint=True):
        """
        function to save layer changes-
        :param layer:
        :param leaveEditable:
        :param triggerRepaint:
        """
        if not self.isEditable():
            return
        if not self.commitChanges():
            self.commitErrors()

        if leaveEditable:
            self.startEditing()

        if triggerRepaint:
            self.triggerRepaint()

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
            self.saveEdits(leaveEditable=b)


    def __len__(self):
        return self.featureCount()

    def __iter__(self):
        r = QgsFeatureRequest()
        for f in self.getFeatures(r):
            yield self.mProfiles[f.id()]

    def __contains__(self, item):
        return item in self.mProfiles.values()


    def temporalProfileToLocationFeature(self, tp:TemporalProfile):

        self.mLocations.selectByIds([tp.id()])
        for f in self.mLocations.selectedFeatures():
            assert isinstance(f, QgsFeature)
            return f

        return None


    def fromSpatialPoint(self, spatialPoint):
        """ Tests if a Temporal Profile already exists for the given spatialPoint"""

        spatialPoint = spatialPoint.toCrs(self.crs())
        unit = QgsUnitTypes.toAbbreviatedString(self.crs().mapUnits()).lower()
        x = spatialPoint.x() + 0.00001
        y = spatialPoint.y() + 0.

        if 'degree' in unit:
            dx = dy = 0.000001
        else:
            dx = dy = 0.1
        rect = QgsRectangle(x-dx,y-dy, x+dy,y+dy)
        for f  in self.getFeatures(rect):
            return self.mProfiles[f.id()]
        return None

    def removeTemporalProfiles(self, temporalProfiles):
        """
        Removes temporal profiles from this collection
        :param temporalProfile: TemporalProfile
        """

        if isinstance(temporalProfiles, TemporalProfile):
            temporalProfiles = [temporalProfiles]
        assert isinstance(temporalProfiles, list)

        temporalProfiles = [tp for tp in temporalProfiles if isinstance(tp, TemporalProfile) and tp.id() in self.mProfiles.keys()]

        if len(temporalProfiles) > 0:
            b = self.isEditable()
            assert self.startEditing()

            fids = [tp.mID for tp in temporalProfiles]

            self.deleteFeatures(fids)
            self.saveEdits(leaveEditable=b)

            self.sigTemporalProfilesRemoved.emit(temporalProfiles)



    def setMaxProfiles(self, n):
        """
        Sets the maximum number of temporal profiles to be stored in this container.
        :param n: number of profiles, must be >= 1
        """
        old = self.mMaxProfiles

        assert n >= 1
        if old != n:
            self.mMaxProfiles = n

            self.prune()
            self.sigMaxProfilesChanged.emit(self.mMaxProfiles)

    def maxProfiles(self):
        return self.mMaxProfiles


    def prune(self, nMax=None):
        """
        Reduces the number of temporal profile to the value n defined with .setMaxProfiles(n)
        :return: [list-of-removed-TemporalProfiles]
        """
        if nMax is None:
            nMax = self.mMaxProfiles

        nMax = max(nMax, 1)

        toRemove = len(self) - nMax
        if toRemove > 0:

            toRemove = sorted(self[:], key=lambda p:p.id())[0:toRemove]
            self.removeTemporalProfiles(toRemove)





    def getFieldDefn(self, name, values):
        if isinstance(values, np.ndarray):
            # add bands
            if values.dtype in [np.int8, np.int16, np.int32, np.int64,
                                np.uint8, np.uint16, np.uint32, np.uint64]:
                fType = QVariant.Int
                fTypeName = 'integer'
            elif values.dtype in [np.float16, np.float32, np.float64]:
                fType = QVariant.Double
                fTypeName = 'decimal'
        else:
            raise NotImplementedError()

        return QgsField(name, fType, fTypeName)


    def addPixelLoaderResult(self, d):
        assert isinstance(d, PixelLoaderTask)
        if d.success():
            for fid in d.temporalProfileIDs:
                TP = self.mProfiles.get(fid)
                if isinstance(TP, TemporalProfile):
                    TP.pullDataUpdate(d)
                else:
                    pass
                    s = ""

    def clear(self):
        #todo: remove TS Profiles
        #self.mTemporalProfiles.clear()
        #self.sensorPxLayers.clear()
        pass


class TemporalProfileTableFilterModel(QgsAttributeTableFilterModel):

    def __init__(self, sourceModel, parent=None):


        dummyCanvas = QgsMapCanvas()
        dummyCanvas.setDestinationCrs(DEFAULT_CRS)
        dummyCanvas.setExtent(QgsRectangle(-180,-90,180,90))

        super(TemporalProfileTableFilterModel, self).__init__(dummyCanvas, sourceModel, parent=parent)

        self.mDummyCanvas = dummyCanvas

        #self.setSelectedOnTop(True)



class TemporalProfileTableModel(QgsAttributeTableModel):

    #sigPlotStyleChanged = pyqtSignal(SpectralProfile)
    #sigAttributeRemoved = pyqtSignal(str)
    #sigAttributeAdded = pyqtSignal(str)

    AUTOGENERATES_COLUMNS = [FN_Y, FN_X, FN_N_LOADED, FN_N_TOTAL, FN_N_NODATA, FN_ID, FN_N_LOADED_PERCENT]

    def __init__(self, temporalProfileLayer=None, parent=None):

        if temporalProfileLayer is None:
            temporalProfileLayer = TemporalProfileLayer()

        cache = QgsVectorLayerCache(temporalProfileLayer, 1000)

        super(TemporalProfileTableModel, self).__init__(cache, parent)
        self.mTemporalProfileLayer = temporalProfileLayer
        self.mCache = cache

        assert self.mCache.layer() == self.mTemporalProfileLayer

        self.loadLayer()

    def columnNames(self):
        return self.mTemporalProfileLayer.fields().names()

    def feature(self, index):

        id = self.rowToId(index.row())
        f = self.layer().getFeature(id)

        return f

    def temporalProfile(self, index):
        feature = self.feature(index)
        return self.mTemporalProfileLayer.temporalProfileFromFeature(feature)

    def data(self, index, role=Qt.DisplayRole):
        """
        Returns Temporal Profile Layer values
        :param index: QModelIndex
        :param role: enum Qt.ItemDataRole
        :return: value
        """
        if role is None or not index.isValid():
            return None

        result = super(TemporalProfileTableModel, self).data(index, role=role)
        return result


    def setData(self, index, value, role=None):
        """
        Sets Temporal Profile Data.
        :param index: QModelIndex()
        :param value: value to set
        :param role: role
        :return: True | False
        """
        if role is None or not index.isValid():
            return False

        f = self.feature(index)
        result = False

        if value == None:
            value = QVariant()
        cname = self.columnNames()[index.column()]
        if role == Qt.EditRole and cname not in TemporalProfileTableModel.AUTOGENERATES_COLUMNS:
            i = f.fieldNameIndex(cname)
            if f.attribute(i) == value:
                return False
            b = self.mTemporalProfileLayer.isEditable()
            self.mTemporalProfileLayer.startEditing()
            self.mTemporalProfileLayer.changeAttributeValue(f.id(), i, value)
            self.mTemporalProfileLayer.saveEdits(leaveEditable=b)
            result = True
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


    def headerData(self, section:int, orientation:Qt.Orientation, role:int):
        data = super(TemporalProfileTableModel, self).headerData(section, orientation, role)
        if role == Qt.ToolTipRole and orientation == Qt.Horizontal:
            #add the field comment to column description
            field = self.layer().fields().at(section)
            assert isinstance(field, QgsField)
            comment = field.comment()
            if len(comment) > 0:
                data = re.sub('</p>$', ' <i>{}</i></p>'.format(comment), data)

        return data

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction


    def supportedDragActions(self):
        return Qt.CopyAction

    def supportedDropActions(self):
        return Qt.CopyAction

    def flags(self, index):

        if index.isValid():
            columnName = self.columnNames()[index.column()]
            flags = super(TemporalProfileTableModel, self).flags(index) | Qt.ItemIsSelectable
            #if index.column() == 0:
            #    flags = flags | Qt.ItemIsUserCheckable

            if columnName in TemporalProfileTableModel.AUTOGENERATES_COLUMNS:
                flags = flags ^ Qt.ItemIsEditable
            return flags
        return None


class TemporalProfileFeatureSelectionManager(QgsIFeatureSelectionManager):


    def __init__(self, layer, parent=None):
        s =""
        super(TemporalProfileFeatureSelectionManager, self).__init__(parent)
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

        super(TemporalProfileFeatureSelectionManager, self).selectF
        s = ""
    def selectedFeatureCount(self):
        return self.mLayer.selectedFeatureCount()

    def selectedFeatureIds(self):
        return self.mLayer.selectedFeatureIds()

    def setSelectedFeatures(self, ids):
        self.mLayer.selectByIds(ids)



class TemporalProfileTableView(QgsAttributeTableView):

    def __init__(self, parent=None):
        super(TemporalProfileTableView, self).__init__(parent)


        #self.setSelectionBehavior(QAbstractItemView.SelectRows)
        #self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setSectionsMovable(True)
        self.willShowContextMenu.connect(self.onWillShowContextMenu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)


        self.mSelectionManager = None

    def setModel(self, filterModel):

        super(TemporalProfileTableView, self).setModel(filterModel)


        self.mSelectionManager = TemporalProfileFeatureSelectionManager(self.model().layer())
        self.setFeatureSelectionManager(self.mSelectionManager)
        #self.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mContextMenuActions = []

    def setContextMenuActions(self, actions:list):
        self.mContextMenuActions = actions

    #def contextMenuEvent(self, event):
    def onWillShowContextMenu(self, menu, index):
        assert isinstance(menu, QMenu)
        assert isinstance(index, QModelIndex)

        featureIDs = self.temporalProfileLayer().selectedFeatureIds()

        if len(featureIDs) == 0 and index.isValid():
            if isinstance(self.model(), QgsAttributeTableFilterModel):
                index = self.model().mapToSource(index)
                if index.isValid():
                    featureIDs.append(self.model().sourceModel().feature(index).id())
            elif isinstance(self.model(), QgsAttributeTableFilterModel):
                featureIDs.append(self.model().feature(index).id())



        if len(featureIDs) > 0:
            a = menu.addAction('Load missing values')
            a.setToolTip('Load missing values')
            #m = menu.addMenu('Copy...')
            #a = m.addAction("Values")
            #a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.VALUES: self.onCopy2Clipboard(ids, mode))
            #a = m.addAction("Attributes")
            #a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.ATTRIBUTES: self.onCopy2Clipboard(ids, mode))
            #a = m.addAction("Values + Attributes")
            #a.triggered.connect(lambda b, ids=featureIDs, mode=ClipboardIO.WritingModes.ALL: self.onCopy2Clipboard(ids, mode))

        a = menu.addAction('Save as...')
        a.triggered.connect(lambda b, ids=featureIDs : self.onSaveToFile(ids))
        menu.addSeparator()
        #a = menu.addAction('Set Style')
        #a.triggered.connect(lambda b, ids=featureIDs : self.onSetStyle(ids))
        #a = menu.addAction('Check')
        #a.triggered.connect(lambda : self.setCheckState(featureIDs, Qt.Checked))
        #a = menu.addAction('Uncheck')
        #a.triggered.connect(lambda: self.setCheckState(featureIDs, Qt.Unchecked))
        #menu.addSeparator()

        for a in self.mContextMenuActions:
            menu.addAction(a)

        for a in self.actions():
            menu.addAction(a)


    def temporalProfileLayer(self):
        return self.model().layer()



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

        layer = self.temporalProfileLayer()
        assert isinstance(layer, TemporalProfileLayer)
        b = layer.isEditable()
        layer.startEditing()
        layer.deleteFeatures(fids)
        layer.saveEdits(leaveEditable=b)


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()

        if self.model().rowCount() == 0:
            index = self.model().createIndex(0,0)
        else:
            index = self.indexAt(event.pos())

        #if mimeData.hasFormat(mimedata.MDF_SPECTRALLIBRARY):
         #   self.model().dropMimeData(mimeData, event.dropAction(), index.row(), index.column(), index.parent())
          #  event.accept()





    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        #if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
        #    event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        #if event.mimeData().hasFormat(mimedata.MDF_SPECTRALLIBRARY):
        #    event.accept()
        s = ""


    def mimeTypes(self):
        pass


if __name__ == '__main__':
    import site, sys
    from timeseriesviewer import utils
    qgsApp = utils.initQgisApplication()
    DEBUG = False



    w = TemporalProfileTableView()
    w.show()

    #btn = TemporalProfile3DPlotStyleButton()
    #btn.show()
    qgsApp.exec_()
    qgsApp.exitQgis()
