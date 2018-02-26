# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import
import os, sys, pickle, datetime, re, collections
from collections import OrderedDict
from qgis.gui import *
from qgis.core import QgsCoordinateReferenceSystem, \
    QgsVectorLayer, QgsRasterLayer, \
    QgsField, QgsFields, QgsFeature, \
    QgsExpression, QgsExpressionContext, QgsExpressionContextScope

from PyQt4.Qt import pyqtSignal,Qt, QObject, QColor, QVariant, QDate, QPoint, QPointF
from PyQt4.QtCore import QAbstractTableModel, QAbstractListModel, QModelIndex
from PyQt4.QtXml import *
from PyQt4.QtGui import *
import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph import AxisItem

from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument
from timeseriesviewer.plotstyling import PlotStyle
from timeseriesviewer.pixelloader import PixelLoader, PixelLoaderTask
from timeseriesviewer.utils import SpatialExtent, SpatialPoint

LABEL_DN = 'DN or Index'
LABEL_TIME = 'Date'
DEBUG = False

def qgsFieldFromKeyValue(fieldName, value):
    t = type(value)
    if t in [int, float] or np.isreal(value):

        fLen  = 0
        fPrec = 0
        fComm = ''
        fType = ''
        f = QgsField(fieldName, QVariant.Double, 'double', 40, 5)
    else:
        f = QgsField(fieldName, QVariant.String, 'text', 40, 5)
    return f

def sensorExampleQgsFeature(sensor):
    assert isinstance(sensor, SensorInstrument)
    #populate with exemplary band values (generally stored as floats)
    fieldValues = collections.OrderedDict()
    for b in range(sensor.nb):
        fn = bandIndex2bandKey(b)
        fieldValues[fn] = 1.0

    date = datetime.date.today()
    doy = dateDOY(date)
    fieldValues['doy'] = doy
    fieldValues['date'] = str(date)


    fields = QgsFields()
    for k, v in fieldValues.items():
        fields.append(qgsFieldFromKeyValue(k,v))
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


def saveTemporalProfiles(profiles, path, mode='all', sep=','):
    if path is None or len(path) == 0:
        return

    assert mode in ['coordinate','all']
    ext = os.path.splitext(path)

    assert ext in ['shp','csv']
    for p in profiles:
        assert isinstance(p, TemporalProfile)
        p.loadMissingData()

    def tsdValueList(tp, tsd, toString=False):
        assert isinstance(tp, TemporalProfile)
        assert isinstance(tsd, TimeSeriesDatum)

        d = collections.OrderedDict()

        return d

    if ext == 'csv':
        lines = ['Temporal Profiles']
        for p in profiles:
            assert isinstance(p, TemporalProfile)
            lines.append('Profile {} "{}": {}'.format(p.mID, p.name(), p.mCoordinate))
            assert isinstance(p, TemporalProfile)
            for i, tsd in enumerate(p.mTimeSeries):
                assert isinstance(tsd, TimeSeriesDatum)
                continue

                #todo:
                values = tsdValueList(p, tsd, toString=True)
                if i == 0:
                    lines.append(sep.join(values.keys()))
                lines.append(sep.join(values.values()))

        open(path, 'w').writelines(lines)
    if ext == 'shp':
        pass




def depr_date2num(d):
    d2 = d.astype(datetime.datetime)
    o = d2.toordinal()

    #assert d == num2date(o)

    return o

def depr_num2date(n):
    n = int(np.round(n))
    if n < 1:
        n = 1
    d = datetime.datetime.fromordinal(n)
    d = d.date()

    return np.datetime64('{:04}-{:02}-{:02}'.format(d.year,d.month,d.day), 'D')

regBandKey = re.compile("(?<!\w)b\d+(?!\w)", re.IGNORECASE)
regBandKeyExact = re.compile('^' + regBandKey.pattern + '$', re.IGNORECASE)


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
        pi.getAxis('left').setLabel(LABEL_DN)

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


    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        if plotItem.sceneBoundingRect().contains(pos):
            mousePoint = plotItem.vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()
            date = num2date(x)

            plotItem.vb.updateCurrentDate(num2date(x, dt64=True))
            self.mInfoLabelCursor.setText('x {}\ny {:0.2f}'.format(
                                          date, mousePoint.y()),
                                          color=self.mInfoColor)

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setPos(pos)
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

        xAction = [a for a in self.menu.actions() if a.text() == 'X Axis'][0]
        yAction = [a for a in self.menu.actions() if a.text() == 'Y Axis'][0]

        menuXAxis = self.menu.addMenu('X Axis')
        #define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()
        frame.setLayout(l)
        #l.addWidget(self, QWidget, int, int, alignment: Qt.Alignment = 0): not enough arguments
        self.rbXAutoRange = QRadioButton('Auto Range')
        self.rbXAutoRange.setChecked(True)
        self.rbXAutoRange.clicked.connect(self.updateXRange)
        self.rbXManualRange = QRadioButton('Manual Range')
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
        l.addWidget(self.rbXAutoRange,0,0,0,2)
        l.addWidget(self.rbXManualRange, 1,0,1,2)
        l.addWidget(self.dateEditX0, 2,1,1,1)
        l.addWidget(self.dateEditX1, 3,1,1,1)

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

    def updateXRange(self, *args):
        isAutoRange = self.rbXAutoRange.isChecked()
        self.enableAutoRange('x', isAutoRange)
        if not isAutoRange:
            self.setXRange(date2num(self.dateEditX0.date()),
                           date2num(self.dateEditX1.date())
                           )

    def updateCurrentDate(self, date):
        if isinstance(date, np.datetime64):
            self.mCurrentDate = date
            self.mActionMoveToDate.setData(date)
            self.mActionMoveToDate.setText('Move maps to {}'.format(date))

        xRange, yRange = self.viewRange()

        t0 = num2date(xRange[0], qDate=True)
        t1 = num2date(xRange[1], qDate=True)
        self.dateEditX0.setDate(t0)
        self.dateEditX1.setDate(t1)


    def raiseContextMenu(self, ev):

        pt = self.mapDeviceToView(ev.pos())
        self.updateCurrentDate(num2date(pt.x(), dt64=True))

        menu = self.getMenu(ev)
        self.scene().addParentContextMenus(self, menu, ev)
        menu.exec_(ev.screenPos().toPoint())



class TemporalProfile2DPlotStyle(PlotStyle):

    sigExpressionUpdated = pyqtSignal()
    sigSensorChanged = pyqtSignal(SensorInstrument)

    def __init__(self, temporalProfile):
        super(TemporalProfile2DPlotStyle, self).__init__()
        assert isinstance(temporalProfile, TemporalProfile)
        self.mSensor = None
        self.mTP = temporalProfile
        self.mExpression = u'"b1"'
        self.mPlotItems = []

        if isinstance(temporalProfile, TemporalProfile):
            self.setTemporalProfile(temporalProfile)

    def createPlotItem(self, plotWidget):
        pdi = TemporalProfilePlotDataItem(self)
        self.mPlotItems.append(pdi)
        return pdi

    def temporalProfile(self):
        return self.mTP

    def setTemporalProfile(self, temporalPofile):
        assert isinstance(temporalPofile, TemporalProfile)
        b = temporalPofile != self.mTP
        self.mTP = temporalPofile
        if b: self.update()

    def setSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        b = sensor != self.mSensor
        self.mSensor = sensor
        if b:
            self.update()
            self.sigSensorChanged.emit(sensor)


    def update(self):
        super(TemporalProfile2DPlotStyle, self).update()

        for pdi in self.mPlotItems:
            assert isinstance(pdi, TemporalProfilePlotDataItem)
            pdi.updateStyle()
            #pdi.updateItems()



    def sensor(self):
        return self.mSensor


    def setExpression(self, exp):
        assert isinstance(exp, unicode)
        b = self.mExpression != exp
        self.mExpression = exp
        if b:
            self.update()
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



class TemporalProfile3DPlotStyle(PlotStyle):


    def __init__(self,sensor):
        super(TemporalProfile3DPlotStyle, self).__init__()
        #assert isinstance(temporalProfile, TemporalProfile)
        assert isinstance(sensor, SensorInstrument)
        self.mSensor = sensor
        #self.mTP = temporalProfile
        self.mScale = 1.0
        self.mOffset = 0.0
        self.mColor = QColor('green')

        #self.setTemporalProfile(temporalProfile)

    def setColor(self, color):
        assert isinstance(color, QColor)
        old = self.mColor
        self.mColor = color
        if old != color:
            self.update()

    def color(self):
        return self.mColor

    def setScaling(self, scale, offset):
        scale = float(scale)
        offset = float(offset)
        x,y =self.mScale, self.mOffset
        self.mScale = scale
        self.mOffset = offset

        if x != scale or y != offset:
            self.update()

    def sensor(self):
        return self.mSensor

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = super(TemporalProfile3DPlotStyle, self).__getstate__()
        #remove
        del result['mSensor']

        return result




class TemporalProfile(QObject):

    _mNextID = 0
    @staticmethod
    def nextID():
        n = TemporalProfile._mNextID
        TemporalProfile._mNextID += 1
        return n

    def __init__(self, timeSeries, spatialPoint):
        super(TemporalProfile, self).__init__()
        assert isinstance(timeSeries, TimeSeries)
        assert isinstance(spatialPoint, SpatialPoint)

        self.mTimeSeries = timeSeries
        self.mCoordinate = spatialPoint
        self.mID = TemporalProfile.nextID()
        self.mData = {}
        self.mUpdated = False
        self.mName = '#{}'.format(self.mID)

        self.mLoaded = self.mLoadedMax = 0
        self.initMetadata()
        self.updateLoadingStatus()

    def initMetadata(self):
        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            meta = {'doy':tsd.doy,
                    'date':str(tsd.date)}

            self.updateData(tsd, meta)

    def pullDataUpdate(self, d):
        assert isinstance(d, PixelLoaderTask)
        if d.success() and self.mID in d.temporalProfileIDs:
            i = d.temporalProfileIDs.index(self.mID)
            tsd = self.mTimeSeries.getTSD(d.sourcePath)
            assert isinstance(tsd, TimeSeriesDatum)
            profileData = d.resProfiles[i]
            if not isinstance(profileData, tuple):
                s = ""
            try:
                vMean, vStd = profileData
            except Exception as ex:
                s = ""
            values = {}
            validValues = not isinstance(vMean, str)
            # 1. add the pixel values per returned band

            for iBand, bandIndex in enumerate(d.bandIndices):
                key = 'b{}'.format(bandIndex + 1)
                values[key] = vMean[iBand] if validValues else None
                key = 'std{}'.format(bandIndex + 1)
                values[key] = vStd[iBand] if validValues else None
            self.updateData(tsd, values)


    def loadMissingData(self, showGUI=False):
        """
        Loads the missing data
        :return:
        """
        tasks = []
        for tsd in self.mTimeSeries:
            missingIndices = self.missingBandIndices(tsd)

            if len(missingIndices) > 0:
                task = PixelLoaderTask(tsd.pathImg, [self.mCoordinate],
                                       bandIndices=missingIndices,
                                       temporalProfileIDs=[self.mID])
                tasks.append(task)

        if len(tasks) > 0:

            px = PixelLoader()
            px.setNumberOfProcesses(0)
            px.sigPixelLoaded.connect(self.pullDataUpdate)
            self.pixelLoader.startLoading(tasks)

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

    sigNameChanged = pyqtSignal(str)
    def setName(self, name):
        if name != self.mName:
            self.mName = name
            self.sigNameChanged.emit(self.mName)

    def name(self):
        return self.mName


    def plot(self):

        import pyqtgraph as pg

        for sensor in self.mTimeSeries.sensors():
            assert isinstance(sensor, SensorInstrument)

            plotStyle = TemporalProfile2DPlotStyle(self)
            plotStyle.setSensor(sensor)

            pi = TemporalProfilePlotDataItem(plotStyle)
            pi.setClickable(True)
            pw = pg.plot(title=self.name())
            pw.getPlotItem().addItem(pi)
            pi.setColor('green')
            pg.QAPP.exec_()

    def updateData(self, tsd, values):
        assert isinstance(tsd, TimeSeriesDatum)
        assert isinstance(values, dict)

        if tsd not in self.mData.keys():
            self.mData[tsd] = {}

        self.mData[tsd].update(values)
        self.updateLoadingStatus()
        self.mUpdated = True

    def resetUpdatedFlag(self):
        self.mUpdated = False

    def updated(self):
        return self.mUpdated


    def dataFromExpression(self, sensor, expression, dateType='date'):
        assert dateType in ['date','doy']
        x = []
        y = []


        if not isinstance(expression, QgsExpression):
            expression = QgsExpression(expression)
        assert isinstance(expression, QgsExpression)

        expression = QgsExpression(expression)



        fields = QgsFields()
        sensorTSDs = sorted([tsd for tsd in self.mData.keys() if tsd.sensor == sensor])
        for tsd in sensorTSDs:
            data = self.mData[tsd]
            for k, v in data.items():
                if v is not None and fields.fieldNameIndex(k) == -1:
                    fields.append(qgsFieldFromKeyValue(k, v))

        for i, tsd in enumerate(sensorTSDs):
            assert isinstance(tsd, TimeSeriesDatum)
            data = self.mData[tsd]
            context = QgsExpressionContext()
            scope = QgsExpressionContextScope()
            f = QgsFeature()
            f.setFields(fields)
            f.setValid(True)
            for k, v in data.items():
                if v is None:
                    continue
                idx = f.fieldNameIndex(k)
                field = f.fields().field(idx)
                if field.typeName() == 'text':
                    v = str(v)
                else:
                    v = float(v)

                f.setAttribute(k,v)

            scope.setFeature(f)
            context.appendScope(scope)
            #value = expression.evaluatePrepared(f)
            value = expression.evaluate(context)


            if value in [None]:
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
        return self.mLoaded, self.mLoadedMax

    def updateLoadingStatus(self):
        """
        Calculates and the loading status in terms of single pixel values.
        nMax is the sum of all bands over each TimeSeriesDatum and Sensors
        """

        self.mLoaded = self.mLoadedMax

        for tsd in self.mTimeSeries:
            assert isinstance(tsd, TimeSeriesDatum)
            self.mLoadedMax += tsd.sensor.nb
            if self.hasData(tsd):
                self.mLoaded += len([k for k in self.mData[tsd].keys() if k.startswith('b')])


    def hasData(self,tsd):
        assert isinstance(tsd, TimeSeriesDatum)
        return tsd in self.mData.keys()

    def __repr__(self):
        return 'TemporalProfile {}'.format(self.mCoordinate)




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
            x, y = TP.dataFromExpression(self.mPlotStyle.sensor(), self.mPlotStyle.expression())
            x =  np.asarray(x, dtype=np.float)
            y = np.asarray(y, dtype=np.float)
            if len(y) > 0:
                self.setData(x=x, y=y)
            else:
                self.setData(x=[], y=[]) #dummy
        self.updateStyle()

    def updateStyle(self):
        """
        Updates visibility properties
        """

        if DEBUG:
            print('{} updateStyle'.format(self))
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



class TemporalProfileCollection(QAbstractTableModel):
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
    def __init__(self, ):
        super(TemporalProfileCollection, self).__init__()
        #self.sensorPxLayers = dict()
        #self.memLyrCrs = QgsCoordinateReferenceSystem('EPSG:4326')
        self.newDataFlag = False

        self.mcnID = 'id'
        self.mcnCoordinate = 'Coordinate'
        self.mcnLoaded = 'Loading'
        self.mcnName = 'Name'
        self.mColumNames = [self.mcnName, self.mcnLoaded, self.mcnCoordinate]

        crs = QgsCoordinateReferenceSystem('EPSG:4862')
        uri = 'Point?crs={}'.format(crs.authid())

        self.TS = None
        self.mLocations = QgsVectorLayer(uri, 'LOCATIONS', 'memory', False)
        self.mTemporalProfiles = []
        self.mTPLookupSpatialPoint = {}
        self.mTPLookupID = {}
        self.mCurrentTPID = 0
        self.mMaxProfiles = 10

        self.nextID = 0

    def __len__(self):
        return len(self.mTemporalProfiles)

    def __iter__(self):
        return iter(self.mTemporalProfiles)

    def __getitem__(self, slice):
        return self.mTemporalProfiles[slice]

    def __contains__(self, item):
        return item in self.mTemporalProfiles

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mTemporalProfiles)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.mColumNames)

    def idx2tp(self, index):
        if index.isValid() and index.row() < len(self.mTemporalProfiles) :
            return self.mTemporalProfiles[index.row()]
        return None

    def tp2idx(self, temporalProfile):
        assert isinstance(temporalProfile, TemporalProfile)

        if temporalProfile in self.mTemporalProfiles:
            row = self.mTemporalProfiles.index(temporalProfile)
            return self.createIndex(row, 0)
        else:
            return QModelIndex()

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.mColumNames[index.column()]
        TP = self.idx2tp(index)
        if not isinstance(TP, TemporalProfile):
            return None
        #self.mColumNames = ['id','coordinate','loaded']
        if role == Qt.DisplayRole:
            if columnName == self.mcnID:
                value = TP.mID
            elif columnName == self.mcnName:
                value = TP.name()
            elif columnName == self.mcnCoordinate:
                value = '{}'.format(TP.mCoordinate)
            elif columnName == self.mcnLoaded:
                nIs, nMax = TP.loadingStatus()
                if nMax > 0:
                    value = '{}/{} ({:0.2f} %)'.format(nIs, nMax, float(nIs) / nMax * 100)
        elif role == Qt.EditRole:
            if columnName == self.mcnName:
                value = TP.name()
        elif role == Qt.ToolTipRole:
            if columnName == self.mcnID:
                value = 'ID Temporal Profile'
            elif columnName == self.mcnName:
                value = TP.name()
            elif columnName == self.mcnCoordinate:
                value = '{}'.format(TP.mCoordinate)
            elif columnName == self.mcnLoaded:
                nIs, nMax = TP.loadingStatus()
                value = '{}'.format(TP.mCoordinate)
        elif role == Qt.UserRole:
            value = TP

        return value

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            cName = self.mColumNames[index.column()]
            if cName == self.mcnName:
                flags = flags | Qt.ItemIsEditable

            return flags
            #return item.qt_flags(index.column())
        return None


    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        cName = self.mColumNames[index.column()]
        TP = self.idx2tp(index)
        if isinstance(TP, TemporalProfile):
            if role == Qt.EditRole and cName == self.mcnName:
                if len(value) == 0: #do not accept empty strings
                    return False
                else:
                    TP.setName(value)
                return True

        return False

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.mColumNames[col]
            elif orientation == Qt.Vertical:
                return col
        return None

    def insertTemporalProfiles(self, temporalProfiles, i=None):
        if isinstance(temporalProfiles, TemporalProfile):
            temporalProfiles = [temporalProfiles]

        assert isinstance(temporalProfiles, list)
        for temporalProfile in temporalProfiles:
            assert isinstance(temporalProfile, TemporalProfile)

        if i is None:
            i = len(self.mTemporalProfiles)

        temporalProfiles = [t for t in temporalProfiles if t not in self]
        l = len(temporalProfiles)

        if l > 0:

            #remove older profiles
            self.prune(nMax=self.mMaxProfiles - l)

            self.beginInsertRows(QModelIndex(), i, i + l - 1)
            for temporalProfile in temporalProfiles:
                assert isinstance(temporalProfile, TemporalProfile)
                id = self.nextID
                self.nextID += 1
                temporalProfile.mID = id
                self.mTemporalProfiles.insert(i, temporalProfile)
                self.mTPLookupID[id] = temporalProfile
                self.mTPLookupSpatialPoint[temporalProfile.mCoordinate] = temporalProfile
                i += 1
            self.endInsertRows()

            self.sigTemporalProfilesAdded.emit(temporalProfiles)


    def temporalProfileFromGeometry(self, geometry):
        if geometry in self.mTPLookupSpatialPoint.keys():
            return self.mTPLookupSpatialPoint[geometry]
        else:
            return None

    def temporalProfileFromID(self, id):
        if id in self.mTPLookupID.keys():
            return self.mTPLookupID[id]
        else:
            return None

    def id(self, temporalProfile):
        """
        Returns the id of an TemporalProfile
        :param temporalProfile: TemporalProfile
        :return: id or None, inf temporalProfile is not part of this collections
        """

        for k, tp in self.mTPLookupID.items():
            if tp == temporalProfile:
                return k
        return None

    def fromID(self, id):
        if self.mTPLookupID.has_key(id):
            return self.mTPLookupID[id]
        else:
            return None

    def fromSpatialPoint(self, spatialPoint):
        if self.mTPLookupSpatialPoint.has_key(spatialPoint):
            return self.mTPLookupSpatialPoint[spatialPoint]
        else:
            return None

    def removeTemporalProfiles(self, temporalProfiles):
        """
        Removes temporal profiles from this collection
        :param temporalProfile: TemporalProfile
        """

        if isinstance(temporalProfiles, TemporalProfile):
            temporalProfiles = [temporalProfiles]
        assert isinstance(temporalProfiles, list)

        temporalProfiles = [tp for tp in temporalProfiles if isinstance(tp, TemporalProfile) and tp in self.mTemporalProfiles]

        if len(temporalProfiles) > 0:

            def deleteFromDict(d, value):
                assert isinstance(d, dict)
                if value in d.values():
                    key = d.keys()[d.values().index(value)]
                    d.pop(key)

            for temporalProfile in temporalProfiles:
                assert isinstance(temporalProfile, TemporalProfile)
                idx = self.tp2idx(temporalProfile)
                row = idx.row()
                self.beginRemoveRows(QModelIndex(), row, row)
                self.mTemporalProfiles.remove(temporalProfile)

                deleteFromDict(self.mTPLookupID, temporalProfile)
                deleteFromDict(self.mTPLookupSpatialPoint,  temporalProfile)

                self.endRemoveRows()
            self.sigTemporalProfilesRemoved.emit(temporalProfiles)


    def connectTimeSeries(self, timeSeries):
        self.clear()

        if isinstance(timeSeries, TimeSeries):
            self.TS = timeSeries
            #for sensor in self.TS.Sensors:
            #    self.addSensor(sensor)
            #self.TS.sigSensorAdded.connect(self.addSensor)
            #self.TS.sigSensorRemoved.connect(self.removeSensor)
        else:
            self.TS = None

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


    def prune(self, nMax=None):
        """
        Reduces the number of temporal profile to the value n defined with .setMaxProfiles(n)
        :return: [list-of-removed-TemporalProfiles]
        """
        if nMax is None:
            nMax = self.mMaxProfiles

        nMax = max(nMax, 0)

        toRemove = len(self) - nMax
        if toRemove > 0:
            toRemove = sorted(self[:], key=lambda p:p.mID)[0:toRemove]
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

    def setFeatureAttribute(self, feature, name, value):
        assert isinstance(feature, QgsFeature)
        assert isinstance(name, str)
        i = feature.fieldNameIndex(name)
        assert i >= 0, 'Field "{}" does not exist'.format(name)
        field = feature.fields()[i]
        if field.isNumeric():
            if field.type() == QVariant.Int:
                value = int(value)
            elif field.type() == QVariant.Double:
                value = float(value)
            else:
                raise NotImplementedError()
        feature.setAttribute(i, value)

    def sort(self, col, order):
        if self.rowCount() == 0:
            return

        self.layoutAboutToBeChanged.emit()
        colName = self.mColumNames[col]
        r = order != Qt.AscendingOrder

        if colName == self.mcnName:
            self.items.sort(key = lambda TP:TP.name(), reverse=r)
        elif colName == self.mcnCoordinate:
            self.items.sort(key=lambda TP: str(TP.mCoordinate), reverse=r)
        elif colName == self.mcnID:
            self.items.sort(key=lambda TP: TP.mID, reverse=r)
        elif colName == self.mcnLoaded:
            self.items.sort(key=lambda TP: TP.loadingStatus(), reverse=r)
        self.layoutChanged.emit()


    def addPixelLoaderResult(self, d):
        assert isinstance(d, PixelLoaderTask)
        if d.success():
            for TPid in d.temporalProfileIDs:
                TP = self.temporalProfileFromID(TPid)
                assert isinstance(TP, TemporalProfile)
                TP.pullDataUpdate(d)

    def clear(self):
        #todo: remove TS Profiles
        #self.mTemporalProfiles.clear()
        #self.sensorPxLayers.clear()
        pass



class TemporalProfileCollectionListModel(QAbstractListModel):


    def __init__(self, temporalProfileCollection, *args, **kwds):

        super(TemporalProfileCollectionListModel, self).__init__(*args, **kwds)
        assert isinstance(temporalProfileCollection, TemporalProfileCollection)

        self.mTPColl = temporalProfileCollection
        self.mTPColl.rowsAboutToBeInserted.connect(self.rowsAboutToBeInserted)
        self.mTPColl.rowsInserted.connect(self.rowsInserted.emit)
        #self.mTPColl.rowsAboutToBeRemoved.connect(self.rowsAboutToBeRemoved)
        self.mTPColl.rowsRemoved.connect(lambda : self.modelReset.emit())


    def idx2tp(self, *args, **kwds):
        return self.mTPColl.idx2tp(*args, **kwds)

    def tp2idx(self, *args, **kwds):
        return self.mTPColl.tp2idx(*args, **kwds)

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            return flags
            #return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def rowCount(self, *args, **kwds):
        return self.mTPColl.rowCount(*args, **kwds)


    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None



        TP = self.mTPColl.idx2tp(index)
        value = None
        if isinstance(TP, TemporalProfile):
            if role == Qt.DisplayRole:
                value = '{}'.format(TP.name())
            elif role == Qt.ToolTipRole:
                value = '#{} "{}" {}'.format(TP.mID, TP.name(), TP.mCoordinate)
            elif role == Qt.UserRole:
                value = TP

        return value

