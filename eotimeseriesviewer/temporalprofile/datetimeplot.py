import re
from typing import Dict, Iterable, List, Optional, Tuple
from datetime import datetime

import numpy as np

from qgis.PyQt.QtWidgets import QDateTimeEdit, QFrame, QGridLayout, QMenu, QRadioButton, QWidget, QWidgetAction
from qgis.core import QgsVectorLayer
from qgis.PyQt.QtGui import QAction, QColor
from qgis.PyQt.QtCore import pyqtSignal, QDateTime, QPointF, Qt
from eotimeseriesviewer.labeling.quicklabeling import addQuickLabelMenu
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu import ViewBoxMenu
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotCurveItem, ScatterPlotItem, SpotItem
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import HoverEvent, \
    MouseClickEvent
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.temporalprofile.plotitems import MapDateRangeItem, TemporalProfilePlotDataItem


class DateTimePlotDataItem(pg.PlotDataItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mFeatureID = None
        self.mLayerId = None
        self.mTemporalProfile: Optional[dict] = None
        self.mObservationIndices: Optional[np.ndarray] = None
        self.mSelectedPoints: List[SpotItem] = []

    def hasSelectedPoints(self) -> bool:
        return len(self.mSelectedPoints) > 0

    def addSelectedPoints(self, indices: Iterable[SpotItem]):
        for p in indices:
            if p not in self.mSelectedPoints:
                self.mSelectedPoints.append(p)

    def setSelectedPoints(self, indices: Iterable[SpotItem]):
        self.mSelectedPoints.clear()
        self.addSelectedPoints(indices)

    def removeSelectedPoints(self, indices: Iterable[SpotItem]) -> List[SpotItem]:
        removed = []
        for p in indices:
            if p in self.mSelectedPoints:
                self.mSelectedPoints.remove(p)
                removed.append(p)
        return removed

    def selectedPoints(self) -> List[SpotItem]:
        return sorted(self.mSelectedPoints, key=lambda s: s.index())

    def setTemporalProfile(self, d: dict, obs_indices: np.ndarray):
        self.mTemporalProfile = d
        self.mObservationIndices = obs_indices


class DateTimePlotItem(pg.PlotItem):
    pdiPointsHovered = pyqtSignal(object, object, object)
    pdiPointsClicked = pyqtSignal(object, object, object)
    pdiCurveClicked = pyqtSignal(object, object)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def addItem(self, item, *args, **kwds):
        super().addItem(item, *args, **kwds)

        if isinstance(item, DateTimePlotDataItem):
            item.scatter.sigHovered.connect(self.pdiPointsHovered)
            item.scatter.sigClicked.connect(self.pdiPointsClicked)
            item.sigClicked.connect(self.pdiCurveClicked)


class DateTimeViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    moveToDate = pyqtSignal(QDateTime, str)
    moveToLocation = pyqtSignal(SpatialPoint)

    populateContextMenu = pyqtSignal(QMenu)

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(DateTimeViewBox, self).__init__(parent)

        self.mCurrentDate: QDateTime = QDateTime(datetime.now())

        self.mXAxisUnit = 'date'

        menuXAxis = QMenu('X axis')  # self.menu.addMenu('X Axis')

        # define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()

        frame.setLayout(l)
        # l.addWidget(self, QWidget, int, int, alignment: Qt.Alignment = 0): not enough arguments
        self.rbXManualRange = QRadioButton('Manual')
        self.dateEditX0 = QDateTimeEdit()
        self.dateEditX0.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('Start time')
        self.dateEditX0.setCalendarPopup(True)
        self.dateEditX0.dateChanged.connect(self.updateXRange)
        self.dateEditX1 = QDateTimeEdit()
        self.dateEditX1.setDisplayFormat('yyyy-MM-dd')
        self.dateEditX0.setToolTip('End time')
        self.dateEditX1.setCalendarPopup(True)
        self.dateEditX1.dateChanged.connect(self.updateXRange)

        self.rbXAutoRange = QRadioButton('Auto')
        self.rbXAutoRange.setChecked(True)
        self.rbXAutoRange.toggled.connect(self.updateXRange)

        l.addWidget(self.rbXManualRange, 0, 0)
        l.addWidget(self.dateEditX0, 0, 1)
        l.addWidget(self.dateEditX1, 0, 2)
        l.addWidget(self.rbXAutoRange, 1, 0)

        l.setContentsMargins(1, 1, 1, 1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuXAxis)
        wa.setDefaultWidget(frame)
        menuXAxis.addAction(wa)
        self.mMenuXAxis = menuXAxis

        # self.mActionMoveToDate = self.menu.addAction(f'Move to {self.mCurrentDate.toString(Qt.ISODate)}')
        self.mActionMoveToDate = QAction(f'Move to {self.mCurrentDate.toString(Qt.ISODate)}')
        self.mActionMoveToDate.triggered.connect(lambda *args: self.moveToDate.emit(self.mCurrentDate, 'center'))

        # self.mActionMoveToProfile = self.menu.addAction('Move to profile location')
        # self.mActionMoveToProfile.triggered.connect(lambda *args: self.sigM.emit(self.mCurrentDate))

        # self.mActionShowCrosshair = self.menu.addAction('Show Crosshair')
        self.mActionShowCrosshair = QAction('Show Crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)
        # self.mActionShowCrosshair.setEnabled(False)

        # self.mActionShowCursorValues = self.menu.addAction('Show Mouse values')
        self.mActionShowCursorValues = QAction('Show Mouse Values')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

        self.mActionShowMapViewRange = QAction('Show Map View Range')
        self.mActionShowMapViewRange.setCheckable(True)
        self.mActionShowMapViewRange.setChecked(True)

    def getMenu(self, ev):
        m = ViewBoxMenu(self)
        xAction = [a for a in m.actions() if re.search('X Axis', a.text(), re.IGNORECASE)][0]
        m.insertMenu(xAction, self.mMenuXAxis)
        m.removeAction(xAction)

        m.insertAction(None, self.mActionMoveToDate)
        m.insertAction(None, self.mActionShowCrosshair)
        m.insertAction(None, self.mActionShowCursorValues)
        m.insertAction(None, self.mActionShowMapViewRange)

        self.populateContextMenu.emit(m)

        return m

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
            t0 = ImageDateUtils.timestamp(self.dateEditX0.dateTime())
            t1 = ImageDateUtils.timestamp(self.dateEditX1.dateTime())

            t0 = min(t0, t1)
            t1 = max(t0, t1)

            self.setXRange(t0, t1)

    def updateCurrentDate(self, dtg: QDateTime):
        assert isinstance(dtg, QDateTime)
        self.mCurrentDate = dtg
        # print(f'# Update actionMovetoDate: {dtg.toString(Qt.ISODate)}')
        self.mActionMoveToDate.setData(dtg)
        self.mActionMoveToDate.setText(f'Move maps to {dtg.toString(Qt.ISODate)}')

    def raiseContextMenu(self, ev):

        xRange, yRange = self.viewRange()
        if min(xRange) > 0:
            t0 = ImageDateUtils.datetime(xRange[0])
            t1 = ImageDateUtils.datetime(xRange[1])
            self.dateEditX0.setDate(t0.date())
            self.dateEditX1.setDate(t1.date())

        menu = self.getMenu(ev)

        self.scene().addParentContextMenus(self, menu, ev)
        menu.exec_(ev.screenPos().toPoint())


class DateTimePlotWidget(pg.PlotWidget):
    """
    A widget to visualize temporal profiles
    """
    sigMapDateRequest = pyqtSignal(QDateTime, str)
    preUpdateTask = pyqtSignal(str, dict)

    def __init__(self, parent: QWidget = None):
        """
        Constructor of the widget
        """
        viewBox = DateTimeViewBox()
        plotItem = DateTimePlotItem(
            axisItems={'bottom': DateTimeAxis(orientation='bottom')},
            viewBox=viewBox
        )
        super(DateTimePlotWidget, self).__init__(parent, plotItem=plotItem)
        self.plotItem = plotItem
        viewBox.populateContextMenu.connect(self.onPopulateContextMenu)
        self.mDateTimeViewBox = viewBox
        # self.setCentralItem(self.plotItem)
        # self.xAxisInitialized = False
        self.plotItem.pdiPointsHovered.connect(self.onPointsHovered)
        self.plotItem.pdiPointsClicked.connect(self.onPointsClicked)
        self.plotItem.pdiCurveClicked.connect(self.onCurveClicked)

        pi: DateTimePlotItem = self.getPlotItem()
        pi.getAxis('bottom').setLabel('Date')
        pi.getAxis('left').setLabel('Value')

        self.mInfoColor = QColor('yellow')
        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mMapDateRangeItem = MapDateRangeItem()
        self.mMapDateRangeItem.sigMapDateRequest.connect(self.sigMapDateRequest.emit)
        viewBox.mActionShowMapViewRange.toggled.connect(self.mMapDateRangeItem.setVisible)

        b = self.backgroundBrush()
        c = b.color()
        c.setAlpha(125)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', fill=c, anchor=(1.0, 0.0))
        self.mInfoLabelCursor.setColor(QColor('yellow'))

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())
        # self.plot2DLabel.setAnchor()
        # self.plot2DLabel.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(0, 0))
        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)
        pi.addItem(self.mMapDateRangeItem, ignoreBounds=True)

        assert isinstance(self.scene(), pg.GraphicsScene)
        self.mSignalProxyMouseMoved = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self.onMouseMoved2D)
        self.mHoveredPositions: Dict[str, List[Tuple[DateTimePlotDataItem, SpotItem]]] = dict()
        self.mClickedPositions: Dict[Tuple, Tuple[DateTimePlotDataItem, int]] = dict()

    def dateTimeViewBox(self) -> DateTimeViewBox:
        return self.mDateTimeViewBox

    def getPlotItem(self) -> DateTimePlotItem:
        return super().getPlotItem()

    def closeEvent(self, *args, **kwds):
        """
        Stop the time to avoid calls on freed / deleted C++ object references
        """
        self.mUpdateTimer.stop()
        super().closeEvent(*args, **kwds)

    def temporalProfilePlotDataItems(self) -> List[TemporalProfilePlotDataItem]:
        return [i for i in self.plotItem.items if isinstance(i, DateTimePlotDataItem)]

    def resetViewBox(self):
        self.plotItem.getViewBox().autoRange()

    def onPointsHovered(self, item: ScatterPlotItem, array: np.ndarray, event: HoverEvent):

        if isinstance(item, ScatterPlotItem):
            if isinstance(item.parentItem(), DateTimePlotDataItem):
                if len(array) == 0:
                    s = ""
                dataItem: DateTimePlotDataItem = item.parentItem()
                try:
                    k = str(event.pos())
                    # k = item.pos()
                except AttributeError:
                    k = None

                if isinstance(k, str):
                    if k not in self.mHoveredPositions:
                        self.mHoveredPositions.clear()
                        self.mHoveredPositions[k] = []

                    for spotItem in array.tolist():
                        self.mHoveredPositions[k].append((dataItem, spotItem))

                    if len(self.mHoveredPositions[k]) > 1:
                        s = ""
            else:
                s = ""
        # print(self.mHoveredPositions)
        return True

    def hoveredPointItems(self) -> Iterable[Tuple[DateTimePlotDataItem, SpotItem]]:
        for values in self.mHoveredPositions.values():
            for (pdi, spotItem) in values:
                yield pdi, spotItem

    def selectedPointItems(self):

        for item in self.plotItem.items:
            if isinstance(item, DateTimePlotDataItem):
                if item.hasSelectedPoints():
                    yield item

    def onPointsClicked(self, item: ScatterPlotItem, array: np.ndarray, event: MouseClickEvent):

        parent = item.parentItem()
        if isinstance(parent, DateTimePlotDataItem):
            parent: DateTimePlotDataItem
            # print(parent)
            if bool(event.modifiers() & Qt.ControlModifier):
                parent.addSelectedPoints(array)
            else:
                parent.setSelectedPoints(array)

            if False:
                for spotItem in array:
                    spotItem: SpotItem
                    k = (id(parent), spotItem.index())
                    if bool(event.modifiers() & Qt.ControlModifier):
                        if k in self.mClickedPositions:
                            self.mClickedPositions.pop(k)
                        else:
                            self.mClickedPositions[k] = (parent, spotItem.index())
                    else:
                        self.mClickedPositions.clear()
                        self.mClickedPositions[k] = (parent, spotItem.index())

        # print(f'# {parent}:\n\t {",".join([str(p.index()) for p in parent.selectedPoints()])}')

    def setMapDateRange(self, date0: QDateTime, date1: QDateTime):
        self.mMapDateRangeItem.setMapDateRange(date0, date1)

    def onPopulateContextMenu(self, menu: QMenu):

        layers = []
        dtg = None
        for (item, spotItem) in self.hoveredPointItems():
            if dtg is None:
                i = item.mObservationIndices[spotItem.index()]
                dtg = item.mTemporalProfile[TemporalProfileUtils.Date][i]
                dtg = ImageDateUtils.datetime(dtg)

            lyr = item.mLayer()
            if isinstance(lyr, QgsVectorLayer) and lyr not in layers:
                layers.append(lyr)
            s = ""

        if False:
            for item in self.selectedPointItems():
                item: DateTimePlotDataItem
                if src is None:
                    for spotItem in item.selectedPoints():
                        spotItem: SpotItem
                        i = item.mObservationIndices[spotItem.index()]
                        dtg = item.mTemporalProfile[TemporalProfileUtils.Date][i]
                        src = ImageDateUtils.datetime(dtg)
                        # get TSD / TSS
                lyr = item.mLayer()
                if isinstance(lyr, QgsVectorLayer) and lyr not in layers:
                    layers.append(lyr)

        addQuickLabelMenu(menu, layers, dtg)

    def onCurveClicked(self, item, event):

        s = ""
        # print(f'Clicked {item}')

        pdi = None
        if isinstance(item, DateTimePlotDataItem):
            pdi = item
        elif isinstance(item, PlotCurveItem) and isinstance(item.parentItem(), DateTimePlotDataItem):
            pdi = item.parentItem()

        if isinstance(pdi, DateTimePlotDataItem):
            s = ""
            lyr = pdi.mLayer()
            fid = pdi.mFeatureID
            fids_new = None

            if isinstance(lyr, QgsVectorLayer) and isinstance(fid, int):
                fids_old: set = set(lyr.selectedFeatureIds())
                if event.modifiers() & Qt.ControlModifier:
                    if fid in fids_old:
                        # remove from selection if already in
                        fids_new = fids_old - {fid}
                    else:
                        # add to selection
                        fids_new = fids_old | {fid}
                else:
                    fids_new = {fid}
                lyr: QgsVectorLayer
                if fids_old != fids_new:
                    # lyr.selectByIds(list(fids_new))

                    self.preUpdateTask.emit('select_features', {'layer': lyr, 'fids': list(fids_new)})

                # lyr.selectByIds([fid])
            # select feature in layer
            event.accept()

    def onMouseMoved2D(self, evt):
        pos = evt[0]  # using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()

        vb = plotItem.vb
        assert isinstance(vb, DateTimeViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()

            if x < 0:
                self.hideInfoItems()
                return

            date = ImageDateUtils.datetime(x)
            # print(f'#update: {date.toString(Qt.ISODate)}')
            vb.updateCurrentDate(date)

            infoText = []
            for k, pointValues in self.mHoveredPositions.items():
                for (dataItem, spotItem) in pointValues:
                    dataItem: DateTimePlotDataItem

                    spotItem: SpotItem
                    spotDate = ImageDateUtils.datetime(spotItem.pos().x())
                    spotValue = spotItem.pos().y()
                    spotDoy = ImageDateUtils.doiFromDateTime(spotDate)

                    info = [f'{spotValue}',
                            f'{spotDate.date().toString(Qt.ISODate)}',
                            f'DOY: {spotDoy}',
                            dataItem.name()]

                    infoText.append('\n'.join([v for v in info if v not in [None, '']]))

            infoText = '\n'.join(infoText)
            self.mInfoLabelCursor.setText(infoText, color=self.mInfoColor)

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(vb.mActionShowCursorValues.isChecked())
            self.mInfoLabelCursor.setPos(pos)

            b = vb.mActionShowCrosshair.isChecked()
            self.mCrosshairLineH.setVisible(b)
            self.mCrosshairLineV.setVisible(b)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            self.hideInfoItems()

    def hideInfoItems(self):
        plotItem = self.getPlotItem()
        vb = plotItem.vb
        vb.setToolTip('')
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)


class DateTimeAxis(pg.DateAxisItem):

    def __init__(self, *args, **kwds):
        super(DateTimeAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(False)
        self.labelAngle = 0

    def tickValues(self, minVal, maxVal, size):
        d = super(DateTimeAxis, self).tickValues(minVal, maxVal, size)
        return d

    def tickFont(self):
        return self.style.get('tickFont', None)

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):

        p.setRenderHint(p.Antialiasing, False)
        p.setRenderHint(p.TextAntialiasing, True)

        # draw long line along axis
        pen, p1, p2 = axisSpec
        p.setPen(pen)
        p.drawLine(p1, p2)
        p.translate(0.5, 0)  # resolves some damn pixel ambiguity

        # draw ticks
        for pen, p1, p2 in tickSpecs:
            p.setPen(pen)
            p.drawLine(p1, p2)

        # Draw all text
        if self.tickFont() is not None:
            p.setFont(self.tickFont())
        p.setPen(self.pen())

        # for rect, flags, text in textSpecs:
        #    p.drawText(rect, flags, text)
        #    # p.drawRect(rect)

        # see https://github.com/pyqtgraph/pyqtgraph/issues/322
        for rect, flags, text in textSpecs:
            p.save()  # save the painter state
            p.translate(rect.center())  # move coordinate system to center of text rect
            p.rotate(self.labelAngle)  # rotate text
            p.translate(-rect.center())  # revert coordinate system
            p.drawText(rect, flags, text)
            p.restore()  # restore the painter state
