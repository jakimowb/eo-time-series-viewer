import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple, Union

import numpy as np
from qgis.PyQt.QtCore import pyqtSignal, QDateTime, QMimeData, QPointF, Qt
from qgis.PyQt.QtGui import QAction, QClipboard, QColor
from qgis.PyQt.QtGui import QPen
from qgis.PyQt.QtWidgets import QDateTimeEdit, QFrame, QGraphicsItem, QGridLayout, QMenu, QRadioButton, QWidget, \
    QWidgetAction
from qgis.core import QgsApplication, QgsVectorLayer

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.derivedplotdataitems.dpdicontroller import DPDIControllerModel
from eotimeseriesviewer.labeling.quicklabeling import addQuickLabelMenu
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotDataItem, ScatterPlotItem, SpotItem
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import HoverEvent, \
    MouseClickEvent
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu import ViewBoxMenu
from eotimeseriesviewer.qgispluginsupport.qps.utils import SpatialPoint
from eotimeseriesviewer.temporalprofile.plotitems import MapDateRangeItem
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileUtils


class DateTimePlotDataItem(pg.PlotDataItem):

    @staticmethod
    def default_selection_style_function(pdi: PlotDataItem):
        p = QPen(pdi.opts['pen'])
        p.setColor(QColor('yellow'))
        p.setWidth(p.width() + 3)
        pdi.setPen(p)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mFeatureID = None
        self.mLayerId = None
        self.mTemporalProfile: Optional[dict] = None
        self.mObservationIndices: Optional[np.ndarray] = None
        self.mSelectedPoints: List[SpotItem] = []
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.mIsSelected: bool = False
        self.mDefaultStyle = PlotStyle.fromPlotDataItem(self)
        self.mSelectedStyle: Union[None, PlotStyle, Callable] = self.default_selection_style_function

    def setSelectedStyle(self, style: Union[None, PlotStyle, Callable]):
        assert isinstance(style, PlotStyle) or callable(style)
        self.mSelectedStyle = style

    def isSelected(self) -> bool:
        return self.mIsSelected

    def setSelected(self, selected: bool):
        assert isinstance(selected, bool)
        was_selected = self.isSelected()
        self.mIsSelected = selected

        if was_selected != selected:
            if selected:
                # let the plotDataItem look like being selected
                if callable(self.mSelectedStyle):
                    self.mSelectedStyle(self)
                elif isinstance(self.mSelectedStyle, PlotStyle):
                    self.mSelectedStyle.apply(self)
                else:
                    # do nothing
                    pass
                # apply selection style
            else:
                # restore default style
                self.mDefaultStyle.apply(self)

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

        self.mPlotDataControllerModel: DPDIControllerModel = DPDIControllerModel()
        self.mPlotDataControllerModel.modelUpdated.connect(self.updateDerivedItems)

        self.mSelectionTolerance: int = 3
        self.mDerivedItems = list()

    def addItem(self, item, *args, **kwds):
        super().addItem(item, *args, **kwds)

        if isinstance(item, DateTimePlotDataItem):
            self.mPlotDataControllerModel.mExamplePDI = item
            item.setCurveClickable(True, self.mSelectionTolerance)
            item.scatter.sigHovered.connect(self.pdiPointsHovered)
            item.scatter.sigClicked.connect(self.pdiPointsClicked)
            item.sigClicked.connect(self.pdiCurveClicked)

    def addDerivedItem(self, item):
        self.mDerivedItems.append(item)
        super().addItem(item)

    def dateTimePlotDataItems(self):
        for item in self.items:
            if isinstance(item, DateTimePlotDataItem) and item not in self.mDerivedItems:
                yield item

    def updateDerivedItems(self):

        for item in self.mDerivedItems:
            self.removeItem(item)
        self.mDerivedItems.clear()

        model: DPDIControllerModel = self.mPlotDataControllerModel

        items = self.dateTimePlotDataItems()
        if model.showSelectedOnly():
            items = [item for item in items if item.isSelected()]

        derived_items = model.createDerivedItems(items)
        for item in derived_items:
            self.addDerivedItem(item)

    def removeItem(self, item):
        super().removeItem(item)
        for c in self.mPlotDataControllerModel.controllers():
            for d in c.derivedPlotDataItems(item):
                self.removeItem(d)

    def setSelectionTolerance(self, margin: int):
        assert isinstance(margin, int)
        assert margin >= 0
        self.mSelectionTolerance = margin
        for item in self.items:
            if item.curveClickable():
                item.setCurveClickable(True, margin)


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


def copyProfiles(pdis: List[DateTimePlotDataItem], mode: str):
    """
    Copies profile data to clipboard
    :param pdis:
    :param mode:
    :return:
    """
    assert mode in ['csv', 'json', 'tp_json']

    text = None
    if mode == 'tp_json':
        profiles = [pdi.mTemporalProfile for pdi in pdis if isinstance(pdi.mTemporalProfile, dict)]
        text = json.dumps(profiles, ensure_ascii=False)
    elif mode == 'json':

        data = []
        for pdi in pdis:
            d = dict()
            d['name'] = pdi.name()
            d['x'] = pdi.xData.tolist()
            d['y'] = pdi.yData.tolist()
            d['dates'] = [datetime.fromtimestamp(d).isoformat() for d in pdi.xData]
            data.append(d)
        text = json.dumps(data, ensure_ascii=False)

    elif mode == 'csv':
        cols = 1 + len(pdis)

        all_dates = set()
        obs_dicts = []
        # each profile can have different dates.
        # create a CSV table with one date column
        # cells can be empty if no observation exists for the requested date
        header = ['date']
        for i, pdi in enumerate(pdis):
            name = pdi.name()
            if name is None:
                if pdi.mFeatureID:
                    name = f'Feature {pdi.mFeatureID}'
                else:
                    name = f'Profile {i + 1}'
            header.append(name)
            obs_dict = dict()
            for d, v in zip(pdi.xData, pdi.yData):

                if np.isfinite(v):
                    date = datetime.fromtimestamp(d).isoformat()
                    all_dates.add(date)
                    obs_dict[date] = v
            obs_dicts.append(obs_dict)

        mem = io.StringIO()
        writer = csv.writer(mem)
        writer.writerow(header)

        sorted_dates = sorted(all_dates)
        for date in sorted_dates:
            row = [date]
            for obs_dict in obs_dicts:
                row.append(obs_dict.get(date, ''))
            writer.writerow(row)

        text = mem.getvalue()
        mem.close()

        s = ""
        pass
    else:
        raise NotImplementedError()

    cb = QgsApplication.instance().clipboard()
    if isinstance(text, str) and isinstance(cb, QClipboard):
        md = QMimeData()
        md.setText(text)
        cb.setMimeData(md)


class DateTimePlotWidget(pg.PlotWidget):
    """
    A widget to visualize temporal profiles
    """
    sigMapDateRequest = pyqtSignal(QDateTime, str)
    sigSelectFeatures = pyqtSignal(object)

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

        self.mFeaturesToSelect = dict()

    def dateTimeViewBox(self) -> DateTimeViewBox:
        return self.plotItem.vb

    def getPlotItem(self) -> DateTimePlotItem:
        return super().getPlotItem()

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

    def selectedPlotDataItems(self) -> Generator[DateTimePlotDataItem, Any, None]:
        """
        Returns the selected DateTimePlotDataItems
        :return:
        """
        for item in self.plotItem.dateTimePlotDataItems():
            if isinstance(item, DateTimePlotDataItem) and item.isSelected():
                yield item

    def selectedPointItems(self) -> Generator[DateTimePlotDataItem, Any, None]:

        for item in self.plotItem.items:
            if isinstance(item, DateTimePlotDataItem) and item.hasSelectedPoints():
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
        menu.setToolTipsVisible(True)
        selected_profiles = list(self.selectedPlotDataItems())

        m: QMenu = menu.addMenu('Copy Profile(s)')
        m.setToolTipsVisible(True)
        n = len(selected_profiles)
        m.setEnabled(n > 0)
        if n > 0:
            a = m.addAction('CSV')
            a.setToolTip(f'Copy the {n} selected profile(s) in CSV format.')
            a.triggered.connect(lambda *args, pdis=selected_profiles: copyProfiles(pdis, 'csv'))

            a = m.addAction('JSON')
            a.setToolTip(f'Copy the {n} selected profile(s) in JSON format.')
            a.triggered.connect(lambda *args, pdis=selected_profiles: copyProfiles(pdis, 'json'))

            a = m.addAction('Profile data (JSON)')
            a.setToolTip(f'Copy the multi-sensor data of all {n} selected profiles.')
            a.triggered.connect(lambda *args, pdis=selected_profiles: copyProfiles(pdis, 'tp_json'))

        hovered_layers = []
        dtg = None

        for (item, spotItem) in self.hoveredPointItems():
            if dtg is None:
                i = item.mObservationIndices[spotItem.index()]
                dtg = item.mTemporalProfile[TemporalProfileUtils.Date][i]
                dtg = ImageDateUtils.datetime(dtg)

            lyr = item.mLayer()
            if isinstance(lyr, QgsVectorLayer) and lyr not in hovered_layers:
                hovered_layers.append(lyr)
            s = ""
        cmodel = self.plotItem.mPlotDataControllerModel
        cmodel.populateContextMenu(menu)

        addQuickLabelMenu(menu, hovered_layers, dtg)

    def selectedFeatures(self) -> Dict[str, List[int]]:

        SELECT_FEATURES = dict()
        for pdi in self.selectedPlotDataItems():
            lid = pdi.mLayerId
            fid = pdi.mFeatureID

            if isinstance(lid, str) and isinstance(fid, int):
                fids = SELECT_FEATURES.get(lid, set())
                fids.add(fid)
                SELECT_FEATURES[lid] = fids

        return {k: list(sorted(v)) for k, v in SELECT_FEATURES.items()}

    def onCurveClicked(self, item, event):

        selected0 = self.selectedFeatures()
        selectedPDIs0 = list(self.selectedPlotDataItems())

        parentItem = item.parentItem()
        if isinstance(parentItem, DateTimePlotDataItem):
            is_ctrl = bool(QgsApplication.instance().keyboardModifiers() & Qt.ControlModifier)
            if is_ctrl:
                parentItem.setSelected(not parentItem.isSelected())
            else:
                for item in list(self.selectedPlotDataItems()):
                    item.setSelected(False)
                parentItem.setSelected(True)

        selected1 = self.selectedFeatures()
        selectedPDIs1 = list(self.selectedPlotDataItems())
        if selectedPDIs0 != selectedPDIs1:
            self.plotItem.updateDerivedItems()

        if selected0 != selected1:
            self.sigSelectFeatures.emit(selected1)

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
