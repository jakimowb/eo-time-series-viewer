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
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import numpy as np
from osgeo import ogr, osr, gdal
from .externals import pyqtgraph as pg
from .externals.pyqtgraph import functions as fn, AxisItem
from .externals.qps.plotstyling.plotstyling import PlotStyle

from .timeseries import TimeSeries, TimeSeriesDate, SensorInstrument
from .pixelloader import PixelLoader, PixelLoaderTask
from .utils import *
from .externals.qps.speclib.spectrallibraries import createQgsField

LABEL_EXPRESSION_2D = 'DN or Index'
LABEL_TIME = 'Date'
DEBUG = False
OPENGL_AVAILABLE = False
DEFAULT_SAVE_PATH = None
DEFAULT_CRS = QgsCoordinateReferenceSystem('EPSG:4326')

FN_ID = 'fid'
FN_X = 'x'
FN_Y = 'y'
FN_NAME = 'name'

FN_DOY = 'DOY'
FN_DTG = 'DTG'

#FN_N_TOTAL = 'n'
#FN_N_NODATA = 'no_data'
#FN_N_LOADED = 'loaded'
#FN_N_LOADED_PERCENT = 'percent'


regBandKey = re.compile(r"(?<!\w)b\d+(?!\w)", re.IGNORECASE)
regBandKeyExact = re.compile(r'^' + regBandKey.pattern + '$', re.IGNORECASE)

try:
    import OpenGL

    OPENGL_AVAILABLE = True

except:
    pass



def sensorExampleQgsFeature(sensor:SensorInstrument, singleBandOnly=False)->QgsFeature:
    """
    Returns an exemplary QgsFeature with value for a specific sensor
    :param sensor: SensorInstrument
    :param singleBandOnly:
    :return:
    """
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
    fieldValues[FN_DOY] = doy
    fieldValues[FN_DTG] = str(date)

    fields = QgsFields()
    for k, v in fieldValues.items():
        fields.append(createQgsField(k, v))
    f = QgsFeature(fields)
    #f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1.0, 1.0)))
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





def bandIndex2bandKey(i : int):
    assert i >= 0
    return 'b{}'.format(i + 1)

def bandKey2bandIndex(key: str):
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
        self.mActionMoveToDate.triggered.connect(lambda *args : self.sigMoveToDate.emit(self.mCurrentDate))
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
        self.mShowLastLocation = True

        if isinstance(temporalProfile, TemporalProfile):
            self.setTemporalProfile(temporalProfile)

    def showLastLocation(self)->bool:
        """
        """
        return self.mShowLastLocation

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

    def __init__(self, layer, fid:int, geometry:QgsGeometry):
        super(TemporalProfile, self).__init__()
        assert isinstance(geometry, QgsGeometry)
        assert isinstance(layer, TemporalProfileLayer)
        assert fid >= 0

        self.mGeometry = geometry
        self.mID = fid
        self.mLayer = layer
        self.mTimeSeries = layer.timeSeries()
        assert isinstance(self.mTimeSeries, TimeSeries)
        self.mData = {}
        self.mUpdated = False
        self.mLoaded = self.mLoadedMax = self.mNoData = 0

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)
            meta = {FN_DOY: tsd.mDOY,
                    FN_DTG: str(tsd.mDate),
                    'nodata': False}

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

    def coordinate(self)->SpatialPoint:
        """
        Returns the profile coordinate
        :return:
        """
        x, y = self.geometry().asPoint()
        return SpatialPoint(self.mLayer.crs(), x, y)

    def id(self):
        """Feature ID in connected QgsVectorLayer"""
        return self.mID

    def attribute(self, key:str):
        f = self.mLayer.getFeature(self.mID)
        return f.attribute(f.fieldNameIndex(key))

    def setAttribute(self, key:str, value):
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

    def pullDataUpdate(self, d:PixelLoaderTask):
        assert isinstance(d, PixelLoaderTask)
        if d.success() and self.mID in d.temporalProfileIDs:
            i = d.temporalProfileIDs.index(self.mID)
            tsd = self.mTimeSeries.getTSD(d.sourcePath)
            assert isinstance(tsd, TimeSeriesDate)

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
        Loads the missing data for this profile.
        :return:
        """
        from eotimeseriesviewer.pixelloader import PixelLoaderTask, doLoaderTask
        tasks = []
        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)
            missingIndices = self.missingBandIndices(tsd)

            if len(missingIndices) > 0:

                for pathImg in tsd.sourceUris():

                    task = PixelLoaderTask(pathImg, [self.coordinate()],
                                           bandIndices=missingIndices,
                                           temporalProfileIDs=[self.mID])
                    tasks.append(task)

        results = doLoaderTask(TaskMock(), pickle.dumps(tasks))
        for result in pickle.loads(results):
            self.pullDataUpdate(result)

    def missingBandIndices(self, tsd, requiredIndices=None):
        """
        Returns the band indices [0, sensor.nb) that have not been loaded yet.
        :param tsd: TimeSeriesDate of interest
        :param requiredIndices: optional subset of possible band-indices to return the missing ones from.
        :return: [list-of-indices]
        """
        assert isinstance(tsd, TimeSeriesDate)
        if requiredIndices is None:
            requiredIndices = list(range(tsd.mSensor.nb))
        requiredIndices = [i for i in requiredIndices if i >= 0 and i < tsd.mSensor.nb]
        existingBandIndices = [bandKey2bandIndex(k) for k in self.data(tsd).keys() if regBandKeyExact.search(k)]
        return [i for i in requiredIndices if i not in existingBandIndices]


    def plot(self):


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
        assert isinstance(tsd, TimeSeriesDate)
        assert isinstance(values, dict)

        if tsd not in self.mData.keys():
            self.mData[tsd] = {}

        self.mData[tsd].update(values)
        if not skipStatusUpdate:
            #self.updateLoadingStatus()
            self.mUpdated = True
            self.sigDataChanged.emit()

    def resetUpdatedFlag(self):
        self.mUpdated = False

    def updated(self):
        return self.mUpdated

    def dataFromExpression(self, sensor, expression:str, dateType='date'):
        assert dateType in ['date', 'doy']
        x = []
        y = []


        if not isinstance(expression, QgsExpression):
            expression = QgsExpression(expression)
        assert isinstance(expression, QgsExpression)
        expression = QgsExpression(expression)

        # define required QgsFields
        fields = QgsFields()
        sensorTSDs = sorted([tsd for tsd in self.mData.keys() if tsd.sensor() == sensor])
        for tsd in sensorTSDs:
            data = self.mData[tsd]
            for k, v in data.items():
                if v is not None and fields.indexFromName(k) == -1:
                    fields.append(createQgsField(k, v))

        for i, tsd in enumerate(sensorTSDs):
            assert isinstance(tsd, TimeSeriesDate)
            data = self.mData[tsd]
            context = QgsExpressionContext()
            context.setFields(fields)

            f = QgsFeature(fields)
            f.setGeometry(self.mGeometry)
            for k, v in data.items():
                setQgsFieldValue(f, k, v)

            context.setFeature(f)

            yValue = expression.evaluate(context)

            if dateType == 'date':
                xValue = date2num(tsd.mDate)
            elif dateType == 'doy':
                xValue = tsd.mDOY

            if yValue in [None, QVariant()]:
                yValue = np.NaN

            y.append(yValue)
            x.append(xValue)

        #return np.asarray(x), np.asarray(y)
        assert len(x) == len(y)
        return x, y

    def data(self, tsd):
        assert isinstance(tsd, TimeSeriesDate)
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

    #def updateLoadingStatus(self):
    #    """
    #    Calculates the loading status in terms of single pixel values.
    #    nMax is the sum of all bands over each TimeSeriesDate and Sensors
    #    """
    """
        self.mLoaded = 0
        self.mLoadedMax = 0
        self.mNoData = 0

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)
            nb = tsd.mSensor.nb

            self.mLoadedMax += nb
            if self.hasData(tsd):
                if self.isNoData(tsd):
                    self.mNoData += nb
                else:
                    self.mLoaded += len([k for k in self.mData[tsd].keys() if regBandKey.search(k)])

        f = self.mLayer.getFeature(self.id())

        b = self.mLayer.isEditable()
        self.mLayer.startEditing()
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_NODATA), self.mNoData)
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_TOTAL), self.mLoadedMax)
        # self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED), self.mLoaded)
        # if self.mLoadedMax > 0:
        #     self.mLayer.changeAttributeValue(f.id(), f.fieldNameIndex(FN_N_LOADED_PERCENT), round(100. * float(self.mLoaded + self.mNoData) / self.mLoadedMax, 2))

        self.mLayer.saveEdits(leaveEditable=b)
        s = ""
    """

    def isNoData(self, tsd):
        assert isinstance(tsd, TimeSeriesDate)
        return self.mData[tsd]['nodata']

    def hasData(self, tsd):
        assert isinstance(tsd, TimeSeriesDate)
        return tsd in self.mData.keys()

    def __repr__(self):
        return 'TemporalProfile {} "{}"'.format(self.id(), self.name())


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

            if np.any(np.isfinite(y)):
                self.setData(x=x, y=y, connect='finite')
            else:
                self.setData(x=[], y=[]) # dummy
        else:
            self.setData(x=[], y=[])  # dummy for empty data
        self.updateStyle()


    def updateStyle(self):
        """
        Updates visibility properties
        """

        self.setVisible(self.mPlotStyle.isVisible())
        self.setSymbol(self.mPlotStyle.markerSymbol)
        self.setSymbolSize(self.mPlotStyle.markerSize)
        self.setSymbolBrush(self.mPlotStyle.markerBrush)
        self.setSymbolPen(self.mPlotStyle.markerPen)
        self.setPen(self.mPlotStyle.linePen)
        self.update()



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



VSI_DIR = r'/vsimem/temporalprofiles/'

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


    def __init__(self, timeSeries:TimeSeries, uri=None, name='Temporal Profiles'):

        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)

        if uri is None:
            # create a new, empty backend
            # existing_vsi_files = vsiSpeclibs()
            existing_vsi_files = []
            # todo:
            assert isinstance(existing_vsi_files, list)
            i = 0
            _name = name.replace(' ', '_')
            uri = (pathlib.Path(VSI_DIR) / '{}.gpkg'.format(_name)).as_posix()
            while not ogr.Open(uri) is None:
                i += 1
                uri = (pathlib.Path(VSI_DIR) / '{}{:03}.gpkg'.format(_name, i)).as_posix()

            drv = ogr.GetDriverByName('GPKG')
            assert isinstance(drv, ogr.Driver)
            co = ['VERSION=AUTO']
            dsSrc = drv.CreateDataSource(uri, options=co)
            assert isinstance(dsSrc, ogr.DataSource)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            co = ['GEOMETRY_NAME=geom',
                  'GEOMETRY_NULLABLE=YES',
                  'FID={}'.format(FN_ID)
                  ]

            lyr = dsSrc.CreateLayer(name, srs=srs, geom_type=ogr.wkbPoint, options=co)

            assert isinstance(lyr, ogr.Layer)
            ldefn = lyr.GetLayerDefn()
            assert isinstance(ldefn, ogr.FeatureDefn)
            dsSrc.FlushCache()
        else:
            dsSrc = ogr.Open(uri)
            assert isinstance(dsSrc, ogr.DataSource)
            names = [dsSrc.GetLayerByIndex(i).GetName() for i in range(dsSrc.GetLayerCount())]
            i = names.index(name)
            lyr = dsSrc.GetLayer(i)


        # consistency check
        uri2 = '{}|{}'.format(dsSrc.GetName(), lyr.GetName())
        assert QgsVectorLayer(uri2).isValid()
        super(TemporalProfileLayer, self).__init__(uri2, name, 'ogr', lyrOptions)


        """
        assert isinstance(timeSeries, TimeSeries)
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        uri = 'Point?crs={}'.format(crs.authid())
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(TemporalProfileLayer, self).__init__(uri, name, 'memory', lyrOptions)
        """

        from collections import OrderedDict
        self.mProfiles = OrderedDict()
        self.mTimeSeries = timeSeries
        #symbol = QgsFillSymbol.createSimple({'style': 'no', 'color': 'red', 'outline_color': 'black'})
        #self.mLocations.renderer().setSymbol(symbol)
        #self.mNextID = 1

        self.TS = None
        self.setName('EOTS Temporal Profiles')
        fields = QgsFields()
        #fields.append(createQgsField(FN_ID, self.mNextID))
        fields.append(createQgsField(FN_NAME, ''))
        fields.append(createQgsField(FN_X, 0.0, comment='Longitude'))
        fields.append(createQgsField(FN_Y, 0.0, comment='Latitude'))
        #fields.append(createQgsField(FN_N_TOTAL, 0, comment='Total number of band values'))
        #fields.append(createQgsField(FN_N_NODATA,0, comment='Total of no-data values.'))
        #fields.append(createQgsField(FN_N_LOADED, 0, comment='Loaded valid band values.'))
        #fields.append(createQgsField(FN_N_LOADED_PERCENT,0.0, comment='Loading progress (%)'))
        assert self.startEditing()
        assert self.dataProvider().addAttributes(fields)
        assert self.commitChanges()
        self.initConditionalStyles()

        self.committedFeaturesAdded.connect(self.onFeaturesAdded)
        self.committedFeaturesRemoved.connect(self.onFeaturesRemoved)

    def __getitem__(self, slice):
        return list(self.mProfiles.values())[slice]

    def loadMissingData(self, backgroundProcess=False):
        assert isinstance(self.mTimeSeries, TimeSeries)

        # Get or create the TimeSeriesProfiles which will store the loaded values
        tasks = []

        theGeometries = []

        # Define which (new) bands need to be loaded for each sensor
        LUT_bandIndices = dict()
        for sensor in self.mTimeSeries.sensors():
                LUT_bandIndices[sensor] = list(range(sensor.nb))

        PL = PixelLoader()
        PL.sigPixelLoaded.connect(self.addPixelLoaderResult)

        # update new / existing points

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDate)


            requiredIndices = LUT_bandIndices[tsd.mSensor]
            requiredIndexKeys = [bandIndex2bandKey(b) for b in requiredIndices]
            TPs = []
            missingIndices = set()
            for TP in self.mProfiles.values():
                assert isinstance(TP, TemporalProfile)
                dataValues = TP.mData[tsd]
                existingKeys = list(dataValues.keys())
                missingIdx = [bandKey2bandIndex(k) for k in requiredIndexKeys if k not in existingKeys]
                if len(missingIdx) > 0:
                    TPs.append(TP)
                    missingIndices.union(set(missingIdx))

            if len(TPs) > 0:
                theGeometries = [tp.coordinate() for tp in TPs]
                theIDs = [tp.id() for tp in TPs]
                for pathImg in tsd.sourceUris():
                    task = PixelLoaderTask(pathImg, theGeometries,
                                           bandIndices=requiredIndices,
                                           temporalProfileIDs=theIDs)
                    tasks.append(task)


        if len(tasks) > 0:

            if backgroundProcess:
                PL.startLoading(tasks)
            else:
                import eotimeseriesviewer.pixelloader
                dump = pickle.dumps(tasks)
                tasks =pickle.loads(eotimeseriesviewer.pixelloader.doLoaderTask(eotimeseriesviewer.pixelloader.TaskMock(), dump))
                for i, task in enumerate(tasks):
                    PL.sigPixelLoaded.emit(task)


        else:
            if DEBUG:
                print('Data for geometries already loaded')

        s = ""

    def saveTemporalProfiles(self, pathVector, loadMissingValues=False, sep='\t'):
        if pathVector is None or len(pathVector) == 0:
            global DEFAULT_SAVE_PATH
            if DEFAULT_SAVE_PATH == None:
                DEFAULT_SAVE_PATH = 'temporalprofiles.shp'
            d = os.path.dirname(DEFAULT_SAVE_PATH)
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            pathVector, filter = QFileDialog.getSaveFileName(None, 'Save {}'.format(self.name()), DEFAULT_SAVE_PATH,
                                                             filter=filters)

            if len(pathVector) == 0:
                return None
            else:
                DEFAULT_SAVE_PATH = pathVector

        if loadMissingValues:
            self.loadMissingData(backgroundProcess=False)
            for p in self.mProfiles.values():
                assert isinstance(p, TemporalProfile)
                p.loadMissingData()

        drvName = QgsVectorFileWriter.driverForExtension(os.path.splitext(pathVector)[-1])
        QgsVectorFileWriter.writeAsVectorFormat(self, pathVector, 'utf-8', destCRS=self.crs(), driverName=drvName)

        pathCSV = os.path.splitext(pathVector)[0] + '.data.csv'
        # write a flat list of profiles
        csvLines = ['Temporal Profiles']
        nBands = max([s.nb for s in self.mTimeSeries.sensors()])
        csvLines.append(sep.join(['id', 'name', 'sensor', 'date', 'doy', 'sensor'] + ['b{}'.format(b+1) for b in range(nBands)]))

        for p in list(self.getFeatures()):

            assert isinstance(p, QgsFeature)
            fid = p.id()
            tp = self.mProfiles.get(fid)
            if tp is None:
                continue
            assert isinstance(tp, TemporalProfile)
            name = tp.name()
            for tsd, values in tp.mData.items():
                assert isinstance(tsd, TimeSeriesDate)
                line = [fid, name, tsd.mSensor.name(), tsd.mDate, tsd.mDOY]
                for b in range(tsd.mSensor.nb):
                    key = 'b{}'.format(b+1)
                    line.append(values.get(key))

                line = ['' if v == None else str(v) for v in line]
                line = sep.join([str(l) for l in line])
                csvLines.append(line)
            s = ""

        # write CSV file
        with open(pathCSV, 'w', encoding='utf8') as f:
            f.write('\n'.join(csvLines))

        return [pathVector, pathCSV]

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
        if layerID != self.id():
            s = ""

        if len(addedFeatures) > 0:

            temporalProfiles = []
            for feature in addedFeatures:
                fid = feature.id()
                if fid < 0:
                    continue
                tp = TemporalProfile(self, fid, feature.geometry())

                self.mProfiles[fid] = tp
                temporalProfiles.append(tp)

            if len(temporalProfiles) > 0:
                pass
                #self.sigTemporalProfilesAdded.emit(temporalProfiles)


    def onFeaturesRemoved(self,  layerID, removedFIDs):
        if layerID != self.id():
            s = ""

        if len(removedFIDs) > 0:

            removed = []

            for fid in removedFIDs:
                removed.append(self.mProfiles.pop(fid))

            self.sigTemporalProfilesRemoved.emit(removed)


    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fields().names():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])
        #styles.setRowStyles([red])


    def createTemporalProfiles(self, coordinates, names:list=None)->list:
        """
        Creates temporal profiles
        :param coordinates:
        :return:
        """

        if isinstance(coordinates, QgsVectorLayer):
            lyr = coordinates
            coordinates = []
            names = []
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(lyr.crs())
            trans.setDestinationCrs(self.crs())

            nameField = None
            if isinstance(names, str) and names in lyr.fields().names():
                nameField = names
            else:
                for name in lyr.fields().names():
                    if re.search('names?', name, re.I):
                        nameField = name
                        break
            if nameField is None:
                nameField = lyr.fields().names()[0]

            for f in lyr.getFeatures():
                assert isinstance(f, QgsFeature)
                g = f.geometry()
                if g.isEmpty():
                    continue
                g = g.centroid()
                assert g.transform(trans) == 0
                coordinates.append(SpatialPoint(self.crs(), g.asPoint()))
                names.append(f.attribute(nameField))

            del trans

        elif not isinstance(coordinates, list):
            coordinates = [coordinates]

        assert isinstance(coordinates, list)

        if not isinstance(names, list):
            n = self.featureCount()
            names = []
            for i in range(len(coordinates)):
                names.append('Profile {}'.format(n+i+1))

        assert len(coordinates) == len(names)

        features = []
        n = self.dataProvider().featureCount()
        for i, (coordinate, name) in enumerate(zip(coordinates, names)):
            assert isinstance(coordinate, SpatialPoint)

            f = QgsFeature(self.fields())
            f.setGeometry(QgsGeometry.fromPointXY(coordinate.toCrs(self.crs())))
            #f.setAttribute(FN_ID, self.mNextID)
            f.setAttribute(FN_NAME, name)
            f.setAttribute(FN_X, coordinate.x())
            f.setAttribute(FN_Y, coordinate.y())
            #f.setAttribute(FN_N_LOADED_PERCENT, 0.0)
            #f.setAttribute(FN_N_LOADED, 0)
            #f.setAttribute(FN_N_TOTAL, 0)
            #f.setAttribute(FN_N_NODATA, 0)
            #self.mNextID += 1
            features.append(f)

        if len(features) == 0:
            return []

        b = self.isEditable()
        self.startEditing()

        newFeatures = []
        def onFeaturesAdded(lid, fids):
            newFeatures.extend(fids)

        self.committedFeaturesAdded.connect(onFeaturesAdded)
        self.beginEditCommand('Add {} profile locations'.format(len(features)))
        success = self.addFeatures(features)
        self.endEditCommand()
        self.saveEdits(leaveEditable=b)
        self.committedFeaturesAdded.disconnect(onFeaturesAdded)

        assert self.featureCount() == len(self.mProfiles)
        profiles = [self.mProfiles[f.id()] for f in newFeatures]
        return profiles


    def saveEdits(self, leaveEditable=False, triggerRepaint=True):
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
        return self.dataProvider().featureCount()

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


        for p in list(self.mProfiles.values()):
            assert isinstance(p, TemporalProfile)
            if p.coordinate() == spatialPoint:
                return p
        """
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
        """
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



    def loadCoordinatesFromOgr(self, path):
        """Loads the TemporalProfiles for vector geometries in data source 'path' """
        if path is None:
            filters = QgsProviderRegistry.instance().fileVectorFilters()
            defDir = None
            if isinstance(DEFAULT_SAVE_PATH, str) and len(DEFAULT_SAVE_PATH) > 0:
                defDir = os.path.dirname(DEFAULT_SAVE_PATH)
            path, filter = QFileDialog.getOpenFileName(directory=defDir, filter=filters)

        if isinstance(path, str) and len(path) > 0:
            sourceLyr = QgsVectorLayer(path)

            nameAttribute = None

            fieldNames = [n.lower() for n in sourceLyr.fields().names()]
            for candidate in ['name', 'id']:
                if candidate in fieldNames:
                    nameAttribute = sourceLyr.fields().names()[fieldNames.index(candidate)]
                    break

            if len(self.timeSeries()) == 0:
                sourceLyr.selectAll()
            else:
                extent = self.timeSeries().maxSpatialExtent(sourceLyr.crs())
                sourceLyr.selectByRect(extent)
            newProfiles = []
            for feature in sourceLyr.selectedFeatures():
                assert isinstance(feature, QgsFeature)
                geom = feature.geometry()
                if isinstance(geom, QgsGeometry):
                    point = geom.centroid().constGet()
                    try:
                        TPs = self.createTemporalProfiles(SpatialPoint(sourceLyr.crs(), point))
                        for TP in TPs:
                            if nameAttribute:
                                name = feature.attribute(nameAttribute)
                            else:
                                name = 'FID {}'.format(feature.id())
                            TP.setName(name)
                            newProfiles.append(TP)
                    except Exception as ex:
                        print(ex)

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


        dummyCanvas = QgsMapCanvas(parent)
        dummyCanvas.setDestinationCrs(DEFAULT_CRS)
        dummyCanvas.setExtent(QgsRectangle(-180,-90,180,90))

        super(TemporalProfileTableFilterModel, self).__init__(dummyCanvas, sourceModel, parent=parent)

        self.mDummyCanvas = dummyCanvas

        #self.setSelectedOnTop(True)



class TemporalProfileTableModel(QgsAttributeTableModel):

    #sigPlotStyleChanged = pyqtSignal(SpectralProfile)
    #sigAttributeRemoved = pyqtSignal(str)
    #sigAttributeAdded = pyqtSignal(str)

    AUTOGENERATES_COLUMNS = [FN_ID, FN_Y, FN_X]
                             #FN_N_LOADED, FN_N_TOTAL, FN_N_NODATA,
                             #FN_N_LOADED_PERCENT


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
