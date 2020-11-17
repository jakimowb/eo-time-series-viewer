# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/gui.py
    Functionality to plot SpectralLibraries
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
from typing import List, Tuple

import sip
import textwrap
from .core import *
import collections
from ..externals.pyqtgraph import PlotItem, PlotWindow, PlotCurveItem
from ..externals.pyqtgraph.functions import mkPen
from ..externals import pyqtgraph as pg
from ..externals.pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu import ViewBoxMenu
from ..externals.pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from ..layerproperties import AttributeTableWidget
from ..unitmodel import BAND_INDEX, XUnitModel, UnitConverterFunctionModel

from ..plotstyling.plotstyling import PlotStyleWidget, PlotStyle, PlotStyleDialog

from qgis.core import \
    QgsFeature, QgsRenderContext, QgsNullSymbolRenderer, QgsFieldFormatter, QgsApplication, \
    QgsRasterLayer, QgsMapLayer, QgsVectorLayer, QgsFieldFormatterRegistry, \
    QgsSymbol, QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol, \
    QgsAttributeTableConfig, QgsField, QgsMapLayerProxyModel, QgsFileUtils, \
    QgsExpression, QgsFieldProxyModel

from qgis.gui import \
    QgsEditorWidgetWrapper, QgsAttributeTableView, \
    QgsActionMenu, QgsEditorWidgetFactory, QgsStatusBar, \
    QgsDualView, QgsGui, QgisInterface, QgsMapCanvas, QgsDockWidget, QgsEditorConfigWidget, \
    QgsAttributeTableFilterModel, QgsFieldExpressionWidget

SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
SPECTRAL_PROFILE_FIELD_FORMATTER: None
SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'


class SpectralXAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(SpectralXAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(True)
        self.labelAngle = 0

        self.mUnit: str = ''

    def tickStrings(self, values, scale, spacing):

        if len(values) == 0:
            return []

        if self.mUnit == 'DateTime':

            values = datetime64(np.asarray(values)).astype('datetime64[D]')

            rng = max(values) - min(values)
            ndays = rng.astype(int)

            strns = []

            for v in values:
                if ndays == 0:
                    strns.append(v.astype(str))
                else:
                    strns.append(v.astype(str))

            return strns
        else:
            return super(SpectralXAxis, self).tickStrings(values, scale, spacing)

    def setUnit(self, unit: str, labelName: str = None):
        """
        Sets the unit of this axis
        :param unit: str
        :param labelName: str, defaults to unit
        """
        self.mUnit = unit

        if isinstance(labelName, str):
            self.setLabel(labelName)
        else:
            self.setLabel(unit)


class SpectralLibraryPlotItem(pg.PlotItem):

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotItem, self).__init__(*args, **kwds)

    def addItems(self, items: list, *args, **kargs):
        """
        Add a graphics item to the view box.
        If the item has plot data (PlotDataItem, PlotCurveItem, ScatterPlotItem), it may
        be included in analysis performed by the PlotItem.
        """
        if len(items) == 0:
            return

        self.items.extend(items)
        vbargs = {}
        if 'ignoreBounds' in kargs:
            vbargs['ignoreBounds'] = kargs['ignoreBounds']
        self.vb.addItems(items, *args, **vbargs)
        # name = None
        refItem = items[0]
        if hasattr(refItem, 'implements') and refItem.implements('plotData'):
            # name = item.name()
            self.dataItems.extend(items)
            # self.plotChanged()

            for item in items:
                self.itemMeta[item] = kargs.get('params', {})
            self.curves.extend(items)

        if isinstance(refItem, PlotDataItem):
            ## configure curve for this plot
            (alpha, auto) = self.alphaState()

            for item in items:
                item.setAlpha(alpha, auto)
                item.setFftMode(self.ctrl.fftCheck.isChecked())
                item.setDownsampling(*self.downsampleMode())
                item.setClipToView(self.clipToViewMode())
                item.setPointMode(self.pointMode())

            ## Hide older plots if needed
            self.updateDecimation()

            ## Add to average if needed
            self.updateParamList()
            if self.ctrl.averageGroup.isChecked() and 'skipAverage' not in kargs:
                self.addAvgCurve(item)


class SpectralProfileRendererWidget(QWidget):
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        path_ui = speclibUiPath('spectralprofilerendererwidget.ui')
        loadUi(path_ui, self)

        self.mBlocked: bool = False

        self.mLastRenderer: SpectralProfileRenderer = None
        self.mResetRenderer: SpectralProfileRenderer = None

        self.btnColorBackground.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorForeground.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorInfo.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorSelection.colorChanged.connect(self.onProfileRendererChanged)

        self.optionUseColorsFromVectorRenderer.toggled.connect(self.onUseColorsFromVectorRendererChanged)
        self.btnUseColorsFromVectorRenderer.setDefaultAction(self.optionUseColorsFromVectorRenderer)

        self.wDefaultProfileStyle.setPreviewVisible(False)
        self.wDefaultProfileStyle.cbIsVisible.setVisible(False)
        self.wDefaultProfileStyle.sigPlotStyleChanged.connect(self.onProfileRendererChanged)
        self.wDefaultProfileStyle.setMinimumSize(self.wDefaultProfileStyle.sizeHint())
        self.btnReset.setDisabled(True)
        self.btnReset.clicked.connect(self.reset)

        self.btnColorSchemeBright.setDefaultAction(self.actionActivateBrightTheme)
        self.btnColorSchemeDark.setDefaultAction(self.actionActivateDarkTheme)
        self.actionActivateBrightTheme.triggered.connect(
            lambda: self.setRendererTheme(SpectralProfileRenderer.bright()))
        self.actionActivateDarkTheme.triggered.connect(lambda: self.setRendererTheme(SpectralProfileRenderer.dark()))

    def setResetRenderer(self, profileRenderer: SpectralProfileRenderer):
        self.mResetRenderer = profileRenderer

    def resetRenderer(self) -> SpectralProfileRenderer:
        return self.mResetRenderer

    def reset(self, *args):

        if isinstance(self.mResetRenderer, SpectralProfileRenderer):
            self.setProfileRenderer(self.mResetRenderer)

    def onUseColorsFromVectorRendererChanged(self, checked: bool):

        w: PlotStyleWidget = self.wDefaultProfileStyle
        assert isinstance(w, PlotStyleWidget)
        w.btnLinePenColor.setDisabled(checked)
        w.btnMarkerBrushColor.setDisabled(checked)
        w.btnMarkerPenColor.setDisabled(checked)

        self.onProfileRendererChanged()

    def setRendererTheme(self, profileRenderer: SpectralProfileRenderer):

        profileRenderer = profileRenderer.clone()
        # do not overwrite the following settings:
        profileRenderer.useRendererColors = self.optionUseColorsFromVectorRenderer.isChecked()
        if isinstance(self.mLastRenderer, SpectralProfileRenderer):
            profileRenderer.mFID2Style = self.mLastRenderer.mFID2Style

        self.setProfileRenderer(profileRenderer)

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        assert isinstance(profileRenderer, SpectralProfileRenderer)

        if self.mResetRenderer is None:
            self.mResetRenderer = profileRenderer.clone()

        self.mLastRenderer = profileRenderer
        self.btnReset.setEnabled(True)

        changed = profileRenderer != self.spectralProfileRenderer()

        self.mBlocked = True

        self.btnColorBackground.setColor(profileRenderer.backgroundColor)
        self.btnColorForeground.setColor(profileRenderer.foregroundColor)
        self.btnColorInfo.setColor(profileRenderer.infoColor)
        self.btnColorSelection.setColor(profileRenderer.selectionColor)
        self.wDefaultProfileStyle.setPlotStyle(profileRenderer.profileStyle)
        self.optionUseColorsFromVectorRenderer.setChecked(profileRenderer.useRendererColors)
        self.mBlocked = False
        if changed:
            self.sigProfileRendererChanged.emit(self.spectralProfileRenderer())

    def onProfileRendererChanged(self, *args):
        if not self.mBlocked:
            self.btnReset.setEnabled(isinstance(self.mResetRenderer, SpectralProfileRenderer) and
                                     self.spectralProfileRenderer() != self.mResetRenderer)
            self.sigProfileRendererChanged.emit(self.spectralProfileRenderer())

    def spectralProfileRenderer(self) -> SpectralProfileRenderer:
        if isinstance(self.mLastRenderer, SpectralProfileRenderer):
            cs = self.mLastRenderer.clone()
        else:
            cs = SpectralProfileRenderer()
        cs.backgroundColor = self.btnColorBackground.color()
        cs.foregroundColor = self.btnColorForeground.color()
        cs.infoColor = self.btnColorInfo.color()
        cs.selectionColor = self.btnColorSelection.color()
        cs.profileStyle = self.wDefaultProfileStyle.plotStyle()
        # if isinstance(self.mLastRenderer, SpectralProfileRenderer):
        #    cs.temporaryProfileStyle = self.mLastRenderer.temporaryProfileStyle.clone()
        #    cs.mFID2Style.update(self.mLastRenderer.mFID2Style)
        cs.useRendererColors = self.optionUseColorsFromVectorRenderer.isChecked()
        return cs


class SpectralProfilePlotDataItem(PlotDataItem):
    """
    A pyqtgraph.PlotDataItem to plot a SpectralProfile
    """
    sigProfileClicked = pyqtSignal(int, dict)

    def __init__(self, spectralProfile: SpectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super().__init__()

        # self.curve.sigClicked.connect(self.curveClicked)
        # self.scatter.sigClicked.connect(self.scatterClicked)
        self.mCurveMouseClickNativeFunc = self.curve.mouseClickEvent
        self.curve.mouseClickEvent = self.onCurveMouseClickEvent
        self.scatter.sigClicked.connect(self.onScatterMouseClicked)

        self.mValueConversionIsPossible: bool = True
        self.mXValueConversionFunction = lambda v, *args: v
        self.mYValueConversionFunction = lambda v, *args: v
        self.mSortByXValues: bool = False

        # self.mDefaultStyle = PlotStyle()

        self.mProfileSource = None

        self.mProfile: SpectralProfile
        self.mProfile = None
        self.mInitialDataX = None
        self.mInitialDataY = None
        self.mInitialUnitX = None
        self.mInitialUnitY = None

        self.initProfile(spectralProfile)
        self.applyMapFunctions()

    def valueConversionPossible(self) -> bool:
        return self.mValueConversionIsPossible

    def profileSource(self):
        return self.mProfileSource

    def setProfileSource(self, source: typing.Any):
        self.mProfileSource = source

    def onCurveMouseClickEvent(self, ev):
        self.mCurveMouseClickNativeFunc(ev)

        if ev.accepted:
            idx, x, y, pxDistance = self.closestDataPoint(ev.pos())
            data = {'idx': idx,
                    'xValue': x,
                    'yValue': y,
                    'pxDistance': pxDistance,
                    'pdi': self}
            self.sigProfileClicked.emit(self.id(), data)

    def onScatterMouseClicked(self, pts: pg.ScatterPlotItem):

        if isinstance(pts, pg.ScatterPlotItem):
            pdi = pts.parentItem()
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pt = pts.ptsClicked[0]
                i = pt.index()
                data = {'idx': i,
                        'xValue': pdi.xData[i],
                        'yValue': pdi.yData[i],
                        'pxDistance': 0,
                        'pdi': self}
                self.sigProfileClicked.emit(self.id(), data)

    def initProfile(self, spectralProfile: SpectralProfile):
        """
        Initializes internal spectral profile settings
        :param spectralProfile: SpectralProfile
        """
        assert isinstance(spectralProfile, SpectralProfile)
        self.mProfile = spectralProfile
        self.mInitialDataX = np.asarray(spectralProfile.xValues())
        self.mInitialDataY = np.asarray(spectralProfile.yValues())

        # sort by X value
        idx = np.argsort(self.mInitialDataX)
        self.mInitialDataX = self.mInitialDataX[idx]
        self.mInitialDataY = self.mInitialDataY[idx]

        self.mInitialUnitX = spectralProfile.xUnit()
        self.mInitialUnitY = spectralProfile.yUnit()
        for v in [self.mInitialDataX, self.mInitialDataY]:
            assert isinstance(v, np.ndarray)

    def resetSpectralProfile(self, spectralProfile: SpectralProfile = None):
        """
        Resets internal settings to either the original SpectraProfile or a new one
        :param spectralProfile: a new SpectralProfile
        """
        """

        Use this to account for changes profile values.
        """
        sp = spectralProfile if isinstance(spectralProfile, SpectralProfile) else self.spectralProfile()
        self.initProfile(sp)
        self.applyMapFunctions()

    def spectralProfile(self) -> SpectralProfile:
        """
        Returns the SpectralProfile
        :return: SpectralPrrofile
        """
        return self.mProfile

    def setMapFunctionX(self, func):
        """
        Sets the function `func` to get the values to be plotted on x-axis.
        The function must have the pattern mappedXValues = func(originalXValues, SpectralProfilePlotDataItem),
        The default function `func = lambda v, *args : v` returns the unchanged x-values in `v`
        The returned value can by of type list or np.ndarray (preferred)
        :param func: callable, mapping function
        """
        assert callable(func)
        self.mXValueConversionFunction = func

    def setMapFunctionY(self, func):
        """
        Sets the function `func` to get the values to be plotted on y-axis.
        The function must follow the pattern mappedYValues = func(originalYValues, plotDataItem),
        The default function `func = lambda v, *args : v` returns the unchanged y-values in `v`
        The second argument `plotDataItem` provides a handle to SpectralProfilePlotDataItem instance which uses this
        function when running its `.applyMapFunctions()`.
        The returned value can by of type list or np.ndarray (preferred)
        :param func: callable, mapping function
        """
        assert callable(func)
        self.mYValueConversionFunction = func

    def applyMapFunctions(self) -> bool:
        """
        Applies the two functions defined with `.setMapFunctionX` and `.setMapFunctionY` and updates the plotted values.
        :return: bool, True in case of success
        """
        success = False
        if len(self.mInitialDataX) > 0 and len(self.mInitialDataY) > 0:
            x = None
            y = None

            try:
                x = self.mXValueConversionFunction(self.mInitialDataX, self)
                y = self.mYValueConversionFunction(self.mInitialDataY, self)
                if isinstance(x, (list, np.ndarray)) and \
                        isinstance(y, (list, np.ndarray)) and len(x) > 0 and len(
                        y) > 0:
                    success = True

            except Exception as ex:
                print(ex)
                pass

        self.mValueConversionIsPossible = success
        if success:
            if True:
                # handle failed removal of NaN
                # see https://github.com/pyqtgraph/pyqtgraph/issues/1057

                # 1. convert to numpy arrays
                if not isinstance(y, np.ndarray):
                    y = np.asarray(y, dtype=np.float)
                if not isinstance(x, np.ndarray):
                    x = np.asarray(x)

                if self.mSortByXValues:
                    idx = np.argsort(x)
                    x = x[idx]
                    y = y[idx]

                is_finite = np.isfinite(y)
                connected = np.logical_and(is_finite, np.roll(is_finite, -1))
                keep = is_finite + connected
                # y[np.logical_not(is_finite)] = np.nanmin(y)
                y = y[keep]
                x = x[keep]
                connected = connected[keep]

                # convert date units to float with decimal year and second precision
                if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                    x = convertDateUnit(datetime64(x), 'DecimalYear')

                if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                    y = convertDateUnit(datetime64(y), 'DecimalYear')

                self.setData(x=x, y=y, connect=connected)
            else:
                self.setData(x=x, y=y, connect='finite')

            self.setVisible(True)
        else:
            # self.setData(x=[], y=[])
            self.setVisible(False)

        return success

    def closestDataPoint(self, pos) -> typing.Tuple[int, float, float, float]:
        x = pos.x()
        y = pos.y()
        pw = self.pixelWidth()
        ph = self.pixelHeight()
        pts = []
        dataX, dataY = self.getData()
        distX = np.abs(dataX - x) / pw
        distY = np.abs(dataY - y) / ph

        dist = np.sqrt(distX ** 2 + distY ** 2)
        idx = np.nanargmin(dist)
        return idx, dataX[idx], dataY[idx], dist[idx]

    def plot(self) -> PlotWindow:
        """
        Opens a PlotWindow and plots this SpectralProfilePlotDataItem to
        :return:
        :rtype:
        """
        pw = pg.plot(title=self.name())
        pw.getPlotItem().addItem(self)
        return pw

    def key(self) -> typing.Tuple[int, int]:
        return self.mProfile.key()

    def id(self) -> int:
        """
        Returns the profile fid
        :return: int
        """
        return self.mProfile.id()

    def name(self) -> str:
        """
        Returns the profile name
        :return:
        :rtype:
        """
        return self.mProfile.name()

    def setClickable(self, b: bool, width=None):
        """
        :param b:
        :param width:
        :return:
        """
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def raiseContextMenu(self, ev):
        menu = self.contextMenu()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def contextMenu(self, event=None):

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
        alphaSlider.setOrientation(Qt.Horizontal)
        alphaSlider.setMaximum(255)
        alphaSlider.setValue(255)
        alphaSlider.valueChanged.connect(self.setAlpha)
        alpha.setDefaultWidget(alphaSlider)
        self.menu.addAction(alpha)
        self.menu.alpha = alpha
        self.menu.alphaSlider = alphaSlider
        return self.menu


class XAxisWidgetAction(QWidgetAction):
    sigUnitChanged = pyqtSignal(str)

    def __init__(self, parent, **kwds):
        super().__init__(parent)

        self.mUnitModel: XUnitModel = XUnitModel()
        self.mUnit: str = BAND_INDEX

    def unitModel(self) -> XUnitModel:
        return self.mUnitModel

    def setUnit(self, unit: str):
        unit = self.mUnitModel.findUnit(unit)

        if isinstance(unit, str) and self.mUnit != unit:
            self.mUnit = unit
            self.sigUnitChanged.emit(unit)

    def unit(self) -> str:
        return self.mUnit

    def unitData(self, unit: str, role=Qt.DisplayRole) -> str:
        return self.mUnitModel.unitData(unit, role)

    def createUnitComboBox(self) -> QComboBox:
        unitComboBox = QComboBox()
        unitComboBox.setModel(self.mUnitModel)
        unitComboBox.setCurrentIndex(self.mUnitModel.unitIndex(self.unit()).row())
        unitComboBox.currentIndexChanged.connect(
            lambda: self.setUnit(unitComboBox.currentData(Qt.UserRole))
        )

        self.sigUnitChanged.connect(
            lambda unit, cb=unitComboBox: cb.setCurrentIndex(self.mUnitModel.unitIndex(unit).row()))
        return unitComboBox

    def createWidget(self, parent: QWidget) -> QWidget:
        # define the widget to set X-Axis options
        frame = QFrame(parent)
        l = QGridLayout()
        frame.setLayout(l)

        mCBXAxisUnit = self.createUnitComboBox()

        l.addWidget(QLabel('Unit'), 2, 0)
        l.addWidget(mCBXAxisUnit, 2, 1)
        l.setMargin(0)
        l.setSpacing(6)
        frame.setMinimumSize(l.sizeHint())
        return frame


class SpectralProfileRendererWidgetAction(QWidgetAction):
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)
    sigResetRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mProfileRenderer: SpectralProfileRenderer = SpectralProfileRenderer.default()
        self.mResetRenderer: SpectralProfileRenderer = self.mProfileRenderer

    def setResetRenderer(self, profileRenderer: SpectralProfileRenderer):
        self.mResetRenderer = profileRenderer
        self.sigResetRendererChanged.emit(self.mResetRenderer)

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        if self.mProfileRenderer != profileRenderer:
            # print(self.mProfileRenderer.printDifferences(profileRenderer))
            self.mProfileRenderer = profileRenderer
            self.sigProfileRendererChanged.emit(profileRenderer)

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.mProfileRenderer

    def createWidget(self, parent: QWidget) -> SpectralProfileRendererWidget:
        w = SpectralProfileRendererWidget(parent)
        w.setProfileRenderer(self.profileRenderer())
        w.sigProfileRendererChanged.connect(self.setProfileRenderer)
        self.sigProfileRendererChanged.connect(w.setProfileRenderer)
        self.sigResetRendererChanged.connect(w.setResetRenderer)
        return w


class MaxNumberOfProfilesWidgetAction(QWidgetAction):
    sigMaxNumberOfProfilesChanged = pyqtSignal(int)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mNProfiles = 64

    def createWidget(self, parent: QWidget):
        l = QGridLayout()
        self.sbMaxProfiles = QSpinBox()
        self.sbMaxProfiles.setToolTip('Maximum number of profiles to plot.')
        self.sbMaxProfiles.setRange(0, np.iinfo(np.int16).max)
        self.sbMaxProfiles.setValue(self.maxProfiles())
        self.sbMaxProfiles.valueChanged[int].connect(self.setMaxProfiles)

        l.addWidget(QLabel('Max. Profiles'), 0, 0)
        l.addWidget(self.sbMaxProfiles, 0, 1)
        frame = QFrame(parent)
        frame.setLayout(l)
        return frame

    def setMaxProfiles(self, n: int):
        assert isinstance(n, int) and n >= 0
        if n != self.mNProfiles:
            self.mNProfiles = n
            self.sigMaxNumberOfProfilesChanged.emit(n)

    def maxProfiles(self) -> int:
        return self.mNProfiles


class SpectralViewBoxMenu(ViewBoxMenu):
    """
    The QMenu that is shown over the profile plot
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class SpectralViewBox(pg.ViewBox):
    """
    Subclass of PyQgtGraph ViewBox

    """

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super().__init__(parent, enableMenu=False)

        self.mCurrentCursorPosition: typing.Tuple[int, int] = (0, 0)
        # define actions
        self.mActionMaxNumberOfProfiles: MaxNumberOfProfilesWidgetAction = MaxNumberOfProfilesWidgetAction(None)
        self.mActionSpectralProfileRendering: SpectralProfileRendererWidgetAction = SpectralProfileRendererWidgetAction(
            None)
        self.mActionSpectralProfileRendering.setDefaultWidget(self.mActionSpectralProfileRendering.createWidget(None))

        self.mOptionUseVectorSymbology: QAction = \
            self.mActionSpectralProfileRendering.defaultWidget().optionUseColorsFromVectorRenderer

        self.mActionXAxis: XAxisWidgetAction = XAxisWidgetAction(None)

        self.mActionShowSelectedProfilesOnly: QAction = QAction('Show Selected Profiles Only', None)
        self.mActionShowSelectedProfilesOnly.setToolTip('Activate to show selected profiles only, '
                                                        'e.g. those selected in the attribute table')

        self.mActionShowSelectedProfilesOnly.setCheckable(True)

        self.mActionShowCrosshair: QAction = QAction('Show Crosshair', None)
        self.mActionShowCrosshair.setToolTip('Activate to show a crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)

        self.mActionShowCursorValues: QAction = QAction('Show Mouse values', None)
        self.mActionShowCursorValues.setToolTip('Activate to show the values related to the cursor position.')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

        # create menu
        menu = SpectralViewBoxMenu(self)

        widgetXAxis: QWidget = menu.widgetGroups[0]
        widgetYAxis: QWidget = menu.widgetGroups[1]
        cbXUnit = self.mActionXAxis.createUnitComboBox()
        grid: QGridLayout = widgetXAxis.layout()
        grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        grid.addWidget(cbXUnit, 0, 2, 1, 2)

        menuProfileRendering = menu.addMenu('Colors')
        menuProfileRendering.addAction(self.mActionSpectralProfileRendering)

        menuOtherSettings = menu.addMenu('Others')
        menuOtherSettings.addAction(self.mActionMaxNumberOfProfiles)
        menuOtherSettings.addAction(self.mActionShowSelectedProfilesOnly)
        menuOtherSettings.addAction(self.mActionShowCrosshair)
        menuOtherSettings.addAction(self.mActionShowCursorValues)

        self.menu: SpectralViewBoxMenu = menu
        self.state['enableMenu'] = True

    def raiseContextMenu(self, ev):
        # update current renderer, as the viewbox menu is a "static" widget instance
        self.mActionSpectralProfileRendering.setResetRenderer(self.mActionSpectralProfileRendering.profileRenderer())
        super(SpectralViewBox, self).raiseContextMenu(ev)

    def addItems(self, pdis: list, ignoreBounds=False):
        """
        Add multiple QGraphicsItem to this view. The view will include this item when determining how to set its range
        automatically unless *ignoreBounds* is True.
        """
        for i, item in enumerate(pdis):
            if item.zValue() < self.zValue():
                item.setZValue(self.zValue() + 1 + i)

        scene = self.scene()
        if scene is not None and scene is not item.scene():
            for item in pdis:
                scene.addItem(item)  ## Necessary due to Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
                item.setParentItem(self.childGroup)
        if not ignoreBounds:
            self.addedItems.extend(pdis)
        # self.updateAutoRange()

    def updateCurrentPosition(self, x, y):
        self.mCurrentCursorPosition = (x, y)


class SpectralLibraryPlotStats(object):

    def __init__(self):
        self.features_total: int = 0
        self.features_selected: int = 0
        self.features_filtered: int = 0
        self.filter_mode: QgsAttributeTableFilterModel.FilterMode = QgsAttributeTableFilterModel.ShowAll

        self.profiles_plotted_max: int = 0
        self.profiles_total: int = 0
        self.profiles_empty: int = 0
        self.profiles_plotted: int = 0
        self.profiles_selected: int = 0
        self.profiles_filtered: int = 0
        self.profiles_error: int = 0

    def __eq__(self, other) -> bool:
        if not isinstance(other, SpectralLibraryPlotStats):
            return False
        for k in self.__dict__.keys():
            if self.__dict__[k] != other.__dict__[k]:
                return False
        return True


class SpectralLibraryPlotWidget(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    def __init__(self, parent=None):

        mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=mViewBox
        )

        super().__init__(parent, plotItem=plotItem)

        self.mSelectedIds = set()
        self.mXAxisUnitInitialized: bool = False
        self.mViewBox: SpectralViewBox = mViewBox
        self.setMaxProfiles(64)
        self.mDualView = None

        self.mNumberOfValueErrorsProfiles: int = 0
        self.mNumberOfEmptyProfiles: int = 0

        self.mMaxInfoLength: int = 30

        # self.centralWidget.setParent(None)
        # self.centralWidget = None
        self.setCentralWidget(plotItem)

        self.plotItem: SpectralLibraryPlotItem
        self.plotItem.sigRangeChanged.connect(self.viewRangeChanged)

        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem) and pi == plotItem and pi == self.plotItem
        self.mXAxis: SpectralXAxis = pi.getAxis('bottom')
        assert isinstance(self.mXAxis, SpectralXAxis)

        self.mSpeclib: SpectralLibrary = None
        self.mSpeclibSignalConnections = []

        self.mXUnitInitialized = False
        self.setXUnit(BAND_INDEX)

        # describe functions to convert wavelength units from unit a to unit b
        self.mUnitConverter = UnitConverterFunctionModel()

        self.mPlotDataItems: typing.List[typing.Tuple[int, str], SpectralProfilePlotDataItem] = dict()
        self.mPlotOverlayItems = []
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoScatterPoint = pg.ScatterPlotItem()
        self.mInfoScatterPoint.sigClicked.connect(self.onInfoScatterClicked)
        self.mInfoScatterPoint.setZValue(9999999)
        self.mInfoScatterPoint.setBrush(QColor('red'))

        self.mInfoScatterPointHtml: str = ""

        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)
        pi.addItem(self.mInfoScatterPoint)
        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)
        # self.proxy2D2 = pg.SignalProxy(self.scene().sigMouseClicked, rateLimit=100, slot=self.onMouseClicked)

        # set default axis unit
        self.updateXUnit()
        self.setYLabel('Y (Spectral Value)')

        self.actionXAxis().sigUnitChanged.connect(self.updateXUnit)
        self.mSPECIFIC_PROFILE_STYLES: typing.Dict[int, PlotStyle] = dict()
        self.mTEMPORARY_HIGHLIGHTED: typing.Set[typing.Tuple[int, str]] = set()
        self.mDefaultProfileRenderer: SpectralProfileRenderer
        self.mDefaultProfileRenderer = SpectralProfileRenderer.default()

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.setInterval(500)
        self.mUpdateTimer.setSingleShot(False)
        self.mUpdateTimer.timeout.connect(self.updatePlot)
        self.mUpdateTimer.start()

        self.actionSpectralProfileRendering().sigProfileRendererChanged.connect(self.setProfileRenderer)
        self.actionProfileSettings().sigMaxNumberOfProfilesChanged.connect(self.updatePlot)

        self.setProfileRenderer(self.mDefaultProfileRenderer)
        self.setAcceptDrops(True)

    def currentProfileKeys(self) -> typing.List[typing.Tuple[int, str]]:
        return sorted(self.mTEMPORARY_HIGHLIGHTED)

    def currentProfileIDs(self) -> typing.List[int]:
        return list(set([k[0] for k in self.currentProfileKeys()]))

    def currentProfiles(self) -> typing.List[SpectralProfile]:
        keys = self.currentProfileKeys()
        return list(self.speclib().profiles(profile_keys=keys))

    def onInfoScatterClicked(self, a, b):
        self.mInfoScatterPoint.setVisible(False)
        self.mInfoScatterPointHtml = ""

    def setUpdateInterval(self, msec: int):
        """
        Sets the update interval
        :param msec:
        :type msec:
        :return:
        :rtype:
        """
        self.mUpdateTimer.setInterval(msec)

    def closeEvent(self, *args, **kwds):
        """
        Stop the time to avoid calls on freed / deleted C++ object references
        """
        self.mUpdateTimer.stop()
        super(SpectralLibraryPlotWidget, self).closeEvent(*args, **kwds)

    def viewBox(self) -> SpectralViewBox:
        return self.mViewBox

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        """Sets and applies the SpectralProfileRenderer"""
        assert isinstance(profileRenderer, SpectralProfileRenderer)
        if isinstance(self.speclib(), SpectralLibrary):
            profileRenderer = profileRenderer.clone()
            profileRenderer.setInput(self.speclib())
            self.speclib().setProfileRenderer(profileRenderer)

            self.actionSpectralProfileRendering().setProfileRenderer(profileRenderer)

    def updatePlot(self, *args):
        try:
            self.updateSpectralProfilePlotItems()
        except RuntimeError as ex:
            print(ex, file=sys.stderr)

    def leaveEvent(self, ev):
        super(SpectralLibraryPlotWidget, self).leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def enterEvent(self, ev):
        super(SpectralLibraryPlotWidget, self).enterEvent(ev)

    def foregroundInfoColor(self) -> QColor:
        return self.plotItem.axes['bottom']['item'].pen().color()

    def hoverEvent(self, ev):
        if ev.enter:
            self.mouseHovering = True
        if ev.exit:
            self.mouseHovering = False

    def updatePositionInfo(self):
        x, y = self.viewBox().mCurrentCursorPosition
        positionInfoHtml = '<html><body>'
        if self.mXAxis.mUnit == 'DateTime':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(datetime64(x), y)
        elif self.mXAxis.mUnit == 'DOY':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(int(x), y)
        else:
            positionInfoHtml += 'x:{:0.5f}\ny:{:0.5f}'.format(x, y)

        positionInfoHtml += '<br/>' + self.mInfoScatterPointHtml
        positionInfoHtml += '</body></html>'
        self.mInfoLabelCursor.setHtml(positionInfoHtml)

    def onMouseClicked(self, event):
        # print(event[0].accepted)
        s = ""

    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, SpectralLibraryPlotItem)
        vb = plotItem.vb
        assert isinstance(vb, SpectralViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()

            vb.updateCurrentPosition(x, y)

            nearest_item = None
            nearest_index = -1
            nearest_distance = sys.float_info.max
            sx, sy = self.mInfoScatterPoint.getData()

            self.updatePositionInfo()

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(self.actionShowCursorValues().isChecked())
            self.mInfoLabelCursor.setPos(pos)

            b = self.actionShowCrosshair().isChecked()
            self.mCrosshairLineH.setVisible(b)
            self.mCrosshairLineV.setVisible(b)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            vb.setToolTip('')
            self.mCrosshairLineH.setVisible(False)
            self.mCrosshairLineV.setVisible(False)
            self.mInfoLabelCursor.setVisible(False)

    def actionSpectralProfileRendering(self) -> SpectralProfileRendererWidgetAction:
        return self.viewBox().mActionSpectralProfileRendering

    def optionUseVectorSymbology(self) -> QAction:
        return self.viewBox().mOptionUseVectorSymbology

    def actionProfileSettings(self) -> MaxNumberOfProfilesWidgetAction:
        return self.viewBox().mActionMaxNumberOfProfiles

    def actionXAxis(self) -> XAxisWidgetAction:
        return self.viewBox().mActionXAxis

    def actionShowCursorValues(self) -> QAction:
        return self.viewBox().mActionShowCursorValues

    def actionShowCrosshair(self) -> QAction:
        return self.viewBox().mActionShowCrosshair

    def actionShowSelectedProfilesOnly(self) -> QAction:
        return self.viewBox().mActionShowSelectedProfilesOnly

    def setPlotOverlayItems(self, items):
        """
        Adds a list of PlotItems to be overlayed
        :param items:
        :return:
        """
        if not isinstance(items, list):
            items = [items]
        assert isinstance(items, list)

        for item in items:
            assert isinstance(item, PlotDataItem)

        toRemove = self.mPlotOverlayItems[:]
        for item in toRemove:
            if item in self.plotItem.items:
                item
                self.plotItem.removeItem(item)

        self.mPlotOverlayItems.clear()
        self.mPlotOverlayItems.extend(items)
        for item in items:
            self.plotItem.addItem(item)

        if not self.mXUnitInitialized:

            xUnit = None
            for item in self.mPlotOverlayItems:
                if isinstance(item, SpectralProfilePlotDataItem):
                    if item.mInitialUnitX != self.mXUnit:
                        xUnit = item.mInitialUnitX
                        break

            if xUnit is not None:
                self.setXUnit(xUnit)
                self.mXUnitInitialized = True

    def spectralProfilePlotDataItems(self) -> typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItems
        """
        return [i for i in self.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)]

    def removeSpectralProfilePDIs(self, keys_to_remove: typing.List[typing.Tuple[int, str]], updateScene: bool = True):
        """
        :param updateScene:
        :param keys_to_remove: feature ids to remove
        :type keys_to_remove:
        :return:
        :rtype:
        """
        if len(keys_to_remove) == 0:
            return

        def disconnect(sig, slot):
            while True:
                try:
                    r = sig.disconnect(slot)
                    s = ""
                except:
                    break

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, pg.PlotItem)
        pdisToRemove = [pdi for pdi in self.spectralProfilePlotDataItems() if pdi.key() in keys_to_remove]
        for pdi in pdisToRemove:
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pdi.setClickable(False)
            disconnect(pdi, self.onProfileClicked)
            plotItem.removeItem(pdi)
            # QtGui.QGraphicsScene.items(self, *args)
            assert pdi not in plotItem.dataItems
            if pdi.key() in self.mPlotDataItems.keys():
                self.mPlotDataItems.pop(pdi.key(), None)

        if updateScene:
            self.scene().update()

    def resetProfileStyles(self):
        """
        Resets the profile colors
        """
        self.profileRenderer().reset()

    def setProfileStyles(self,
                         style: PlotStyle,
                         fids: typing.List[int]):
        """
        Sets the style of single features
        :param style:
        :type style:
        """
        updatedFIDs = self.profileRenderer().setProfilePlotStyle(style, fids)
        self.updateProfileStyles(updatedFIDs)

    def setMaxProfiles(self, n: int):
        """
        Sets the maximum number of profiles.
        :param n: maximum number of profiles visualized
        :type n: int
        """
        self.actionProfileSettings().setMaxProfiles(n)

    def maxProfiles(self) -> int:
        return self.actionProfileSettings().maxProfiles()

    def setSpeclib(self, speclib: SpectralLibrary):
        """
        Sets the SpectralLibrary to be visualized
        :param speclib: SpectralLibrary
        """
        if isinstance(speclib, SpectralLibrary) and speclib == self.speclib():
            return
        self.mUpdateTimer.stop()

        # remove old spectra
        self.removeSpectralProfilePDIs(self.mPlotDataItems.keys())
        self.disconnectSpeclibSignals()
        self.mSpeclib = None

        if isinstance(speclib, SpectralLibrary):
            self.mSpeclib = speclib
            self.connectSpeclibSignals()
            self.onProfileRendererChanged()

        self.mUpdateTimer.start()

    def setDualView(self, dualView: QgsDualView):
        assert isinstance(dualView, QgsDualView)
        speclib = dualView.masterModel().layer()
        assert isinstance(speclib, SpectralLibrary)
        self.mDualView = dualView
        if self.speclib() != speclib:
            self.setSpeclib(speclib)

    def dualView(self) -> QgsDualView:
        return self.mDualView

    def connectSpeclibSignals(self):
        """

        """
        if isinstance(self.mSpeclib, SpectralLibrary):
            self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
            self.mSpeclib.committedAttributeValuesChanges.connect(self.onCommittedAttributeValuesChanges)
            self.mSpeclib.rendererChanged.connect(self.onProfileRendererChanged)
            self.mSpeclib.sigProfileRendererChanged.connect(self.onProfileRendererChanged)
            self.setProfileRenderer(self.mSpeclib.profileRenderer())
            # additional security to disconnect
            self.mSpeclib.willBeDeleted.connect(self.onWillBeDeleted)

    def onWillBeDeleted(self):
        self.setSpeclib(None)

    def disconnectSpeclibSignals(self):
        """
        Savely disconnects all signals from the linked SpectralLibrary
        """
        if isinstance(self.mSpeclib, SpectralLibrary) and not sip.isdeleted(self.mSpeclib):
            def disconnect(sig, slot):
                while True:
                    try:
                        r = sig.disconnect(slot)
                        s = ""
                    except:
                        break

            disconnect(self.mSpeclib.featureAdded, self.onProfilesAdded)
            disconnect(self.mSpeclib.featuresDeleted, self.onProfilesRemoved)
            disconnect(self.mSpeclib.selectionChanged, self.onSelectionChanged)
            disconnect(self.mSpeclib.committedAttributeValuesChanges, self.onCommittedAttributeValuesChanges)
            disconnect(self.mSpeclib.rendererChanged, self.onProfileRendererChanged)
            disconnect(self.mSpeclib.sigProfileRendererChanged, self.onProfileRendererChanged)
            disconnect(self.mSpeclib.willBeDeleted, self.onWillBeDeleted)

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary this widget is linked to.
        :return: SpectralLibrary
        """
        return self.mSpeclib

    def onCommittedAttributeValuesChanges(self, layerID, featureMap):
        """
        Reacts on changes in spectral values
        """
        s = ""

        if layerID != self.speclib().id():
            return
        speclib: SpectralLibrary = self.speclib()
        fieldIndices = [speclib.fields().indexOf(f.name()) for f in speclib.spectralValueFields()]
        idxF = self.speclib().fields().indexOf(FIELD_VALUES)
        fids = set()

        for fid, fieldMap in featureMap.items():
            for idx in fieldIndices:
                if idx in fieldMap.keys():
                    fids.add(fid)

        if len(fids) == 0:
            return
        fids = list(fids)
        update = False
        for p in self.speclib().profiles(fids):
            assert isinstance(p, SpectralProfile)
            pdi = self.mPlotDataItems.get(p.key(), None)
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pdi.resetSpectralProfile(p)
            else:
                update = True
        if update:
            self.updateSpectralProfilePlotItems()

    @pyqtSlot()
    def onProfileRendererChanged(self):
        """
        Updates all SpectralProfilePlotDataItems
        """
        profileRenderer: SpectralProfileRenderer = self.profileRenderer()
        self.actionSpectralProfileRendering().setProfileRenderer(profileRenderer)
        # set Background color
        self.setBackground(profileRenderer.backgroundColor)

        # set Foreground color
        for axis in self.plotItem.axes.values():
            ai: pg.AxisItem = axis['item']
            if isinstance(ai, pg.AxisItem):
                ai.setPen(profileRenderer.foregroundColor)
                ai.setTextPen(profileRenderer.foregroundColor)

                # set info color
                self.mInfoLabelCursor.setColor(profileRenderer.infoColor)
                self.mCrosshairLineH.pen.setColor(profileRenderer.infoColor)
                self.mCrosshairLineV.pen.setColor(profileRenderer.infoColor)

        # set Info Color
        self.mInfoLabelCursor.setColor(profileRenderer.infoColor)
        self.mCrosshairLineH.pen.setColor(profileRenderer.infoColor)
        self.mCrosshairLineV.pen.setColor(profileRenderer.infoColor)

        self.updateProfileStyles()

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.speclib().profileRenderer()

    def onSelectionChanged(self, selected, deselected, clearAndSelect):

        # fidsBefore = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

        self.updateSpectralProfilePlotItems()

        # fidsAfter = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

    """
    def syncLibrary(self):
        s = ""
        # see https://groups.google.com/forum/#!topic/pyqtgraph/kz4U6dswEKg
        # speed problems in case of too many line items
        #profiles = list(self.speclib().profiles())
        self.disableAutoRange()
        self.blockSignals(True)
        self.setViewportUpdateMode(QGraphicsView.NoViewportUpdate)

        self.updateSpectralProfilePlotItems()
        self.updateProfileStyles()
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.blockSignals(False)
        self.enableAutoRange()
        self.viewport().update()
    """

    def unitConversionFunction(self, unitSrc, unitDst):
        """
        Returns a function to convert a numeric value from unitSrc to unitDst.
        :param unitSrc: str, e.g. `micrometers` or `um` (case insensitive)
        :param unitDst: str, e.g. `nanometers` or `nm` (case insensitive)
        :return: callable, a function of pattern `mappedValues = func(value:list, pdi:SpectralProfilePlotDataItem)`
        """

        return self.mUnitConverter.convertFunction(unitSrc, unitDst)

    def setXUnit(self, unit: str):
        """
        Sets the unit or mapping function to be shown on x-axis.
        :param unit: str, e.g. `nanometers`
        """
        # unit = UnitLookup.baseUnit(unit)
        self.actionXAxis().setUnit(unit)

    def xUnit(self) -> str:
        """
        Returns the unit to be shown on x-axis
        :return: str
        """
        return self.actionXAxis().unit()

    def xAxisUnitModel(self) -> XUnitModel:
        return self.actionXAxis().unitModel()

    def allPlotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns all PlotDataItems (not only SpectralProfilePlotDataItems)
        :return: [list-of-PlotDataItems]
        """
        return list(self.mPlotDataItems.values()) + self.mPlotOverlayItems

    def allSpectralProfilePlotDataItems(self) -> typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItem, including those used as temporary overlays.
        :return: [list-of-SpectralProfilePlotDataItem]
        """
        return [pdi for pdi in self.allPlotDataItems() if isinstance(pdi, SpectralProfilePlotDataItem)]

    def updateXUnit(self):

        unit = self.xUnit()
        label = self.xAxisUnitModel().unitData(unit, role=Qt.DisplayRole)

        # update axis label
        if unit in UnitLookup.metric_units():
            label = 'Wavelength [{}]'.format(unit)
        elif unit in UnitLookup.time_units():
            label = 'Time [{}]'.format(unit)

        elif unit in UnitLookup.date_units():
            if unit == 'DateTime':
                label = 'Date'
            else:
                label = 'Date [{}]'.format(unit)

        self.mXAxis.setUnit(unit, label)

        # update x values
        pdis = self.allSpectralProfilePlotDataItems()
        for pdi in pdis:
            pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, unit))
            pdi.applyMapFunctions()

    def updateSpectralProfilePlotItems(self):
        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem)
        n_max = self.maxProfiles()

        self.mNumberOfValueErrorsProfiles = 0
        self.mNumberOfEmptyProfiles = 0

        keys_visualized: typing.List[typing.Tuple[int, str]] = self.plottedProfileKeys()
        pdis_to_visualize: typing.List[SpectralProfilePlotDataItem] = []
        new_pdis: typing.List[SpectralProfilePlotDataItem] = []
        sort_x_values: bool = self.xUnit() in ['DOI']
        for pkey in self.profileKeysToVisualize():
            if len(pdis_to_visualize) >= n_max:
                break

            fid, field_name = pkey

            pdi: SpectralProfilePlotDataItem = self.mPlotDataItems.get(pkey, None)
            if isinstance(pdi, SpectralProfilePlotDataItem):
                if pdi.valueConversionPossible():
                    pdis_to_visualize.append(pdi)
                else:
                    self.mNumberOfValueErrorsProfiles += 1
            else:
                # create a new PDI
                profile: SpectralProfile = self.speclib().profile(fid, value_field=field_name)
                if not isinstance(profile, SpectralProfile) or profile.isEmpty():
                    self.mNumberOfEmptyProfiles += 1
                    continue

                if not self.mXUnitInitialized:
                    self.setXUnit(profile.xUnit())
                    self.mXUnitInitialized = True

                pdi = SpectralProfilePlotDataItem(profile)
                pdi.setProfileSource(self.speclib())
                pdi.setClickable(True)
                pdi.setVisible(True)
                pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, self.xUnit()))
                pdi.mSortByXValues = sort_x_values
                pdi.applyMapFunctions()
                pdi.sigProfileClicked.connect(self.onProfileClicked)
                if pdi.valueConversionPossible():
                    new_pdis.append(pdi)
                    pdis_to_visualize.append(pdi)
                else:
                    self.mNumberOfValueErrorsProfiles += 1

        keys_to_visualize = [pdi.key() for pdi in pdis_to_visualize]
        keys_to_remove = [pkey for pkey in keys_visualized if pkey not in keys_to_visualize]
        keys_new = [pdi.key() for pdi in new_pdis]
        if len(keys_to_remove) > 0:
            s = ""
        self.removeSpectralProfilePDIs(keys_to_remove)
        if len(new_pdis) > 0:
            for pdi in new_pdis:
                self.mPlotDataItems[pdi.key()] = pdi
            pi.addItems(new_pdis)

        if isinstance(self.speclib(), SpectralLibrary):
            selectedNow = set(self.speclib().selectedFeatureIds())
        else:
            selectedNow = set()

        selectionChanged = list(selectedNow.symmetric_difference(self.mSelectedIds))
        self.mSelectedIds = selectedNow

        key_to_update_style = [pkey for pkey in keys_to_visualize if pkey[0] in selectionChanged or pkey in keys_new]
        self.updateProfileStyles(key_to_update_style)

        if len(keys_new) > 0 or len(keys_to_remove) > 0 or len(key_to_update_style) > 0:
            pi.update()

    def resetSpectralProfiles(self):
        for pdi in self.spectralProfilePlotDataItems():
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pdi.resetSpectralProfile()

    def spectralProfilePlotDataItem(self,
                                    fid: typing.Union[int, QgsFeature, SpectralProfile]) -> SpectralProfilePlotDataItem:
        """
        Returns the SpectralProfilePlotDataItem related to SpectralProfile fid
        :param fid: int | QgsFeature | SpectralProfile
        :return: SpectralProfilePlotDataItem
        """
        warnings.warn('Do not use', DeprecationWarning)
        if isinstance(fid, QgsFeature):
            fid = fid.id()
        return self.mPlotDataItems.get(fid)

    def updateProfileStyles(self, keys: typing.List[typing.Tuple[int, str]] = None):
        """
        Updates the styles for a set of SpectralProfilePlotDataItems specified by its feature keys
        :param keys: profile ids to update
        """

        if not isinstance(self.speclib(), SpectralLibrary):
            return

        profileRenderer = self.profileRenderer()

        pdis = self.spectralProfilePlotDataItems()

        # update for requested FIDs only
        if isinstance(keys, list):
            if len(keys) == 0:
                return
            pdis = [pdi for pdi in pdis if pdi.key() in keys]

        # update line colors
        fids2 = [pdi.id() for pdi in pdis]
        styles = profileRenderer.profilePlotStyles(fids2)
        for pdi in pdis:
            style = styles.get(pdi.id())
            if isinstance(style, PlotStyle):
                style.apply(pdi, updateItem=False, visibility=pdi.valueConversionPossible() and style.isVisible())

        # finally, update items
        for pdi in pdis:
            z = 1 if pdi.id() in self.mSelectedIds else 0
            pdi.setZValue(z)
            pdi.updateItems()

    def onProfileClicked(self, fid: int, data: dict):
        """
        Slot to react to mouse-clicks on SpectralProfilePlotDataItems
        :param fid: Feature ID
        :param pdi: SpectralProfilePlotDataItem
        """
        modifiers = QApplication.keyboardModifiers()

        pdi: SpectralProfilePlotDataItem = data.get('pdi')
        if modifiers == Qt.AltModifier:
            x = data['xValue']
            y = data['yValue']
            b = data['idx'] + 1

            if isinstance(pdi, SpectralProfilePlotDataItem):
                profile: SpectralProfile = pdi.spectralProfile()
                if isinstance(profile, SpectralProfile):
                    ptColor: QColor = self.mInfoScatterPoint.opts['brush'].color()
                    self.mInfoScatterPointHtml = f'<span style="color:{ptColor.name()}">' + \
                                                 f'FID:{fid} Bnd:{b}<br/>' + \
                                                 f'x:{x}\ny:{y}<br/>' + \
                                                 textwrap.shorten(profile.name(),
                                                                  width=self.mMaxInfoLength,
                                                                  placeholder='...') + \
                                                 f'</span>'
            else:
                s = ""
            self.mInfoScatterPoint.setData(x=[x],
                                           y=[y],
                                           symbol='o')
            self.mInfoScatterPoint.setVisible(True)

        else:

            if isinstance(pdi, SpectralProfilePlotDataItem) and isinstance(pdi.profileSource(), SpectralLibrary):
                speclib: SpectralLibrary = pdi.profileSource()
                fids = speclib.selectedFeatureIds()

                if modifiers == Qt.NoModifier:
                    fids = [fid]
                elif modifiers == Qt.ShiftModifier or modifiers == Qt.ControlModifier:
                    if fid in fids:
                        fids.remove(fid)
                    else:
                        fids.append(fid)

                speclib.selectByIds(fids)

        self.updatePositionInfo()

    def setYLabel(self, label: str):
        """
        Sets the name of the Y axis
        :param label: str, name
        """
        pi = self.getPlotItem()
        pi.getAxis('left').setLabel(label)

    def yLabel(self) -> str:
        return self.getPlotItem().getAxis('left').label

    def xLabel(self) -> str:
        return self.getPlotItem().getAxis('bottom').label

    def profileStats(self) -> SpectralLibraryPlotStats:
        """
        Returns stats related to existing and visualized SpectralProfiles
        """
        stats = SpectralLibraryPlotStats()
        stats.profiles_plotted_max = self.maxProfiles()

        if isinstance(self.speclib(), SpectralLibrary) and not sip.isdeleted(self.speclib()):
            stats.features_total = self.speclib().featureCount()
            stats.features_selected = self.speclib().selectedFeatureCount()

            stats.filter_mode = self.dualView().filterMode()

            filtered_fids = self.dualView().filteredFeatures()
            selected_fids = self.speclib().selectedFeatureIds()

            stats.features_filtered = len(filtered_fids)

            stats.profiles_total = stats.features_total * len(self.speclib().spectralValueFields())
            stats.profiles_filtered = stats.features_filtered * len(self.speclib().spectralValueFields())
            stats.profiles_error = self.mNumberOfValueErrorsProfiles
            stats.profiles_empty = self.mNumberOfEmptyProfiles

            for pdi in self.allSpectralProfilePlotDataItems():
                fid, value_field = pdi.key()
                if pdi.isVisible():
                    stats.profiles_plotted += 1

                    if fid in selected_fids:
                        stats.profiles_selected += 1

        return stats

    def plottedProfileKeys(self) -> typing.List[typing.Tuple[int, str]]:
        return [pdi.key() for pdi in self.mPlotDataItems.values()]

    def plottedProfileIDs(self) -> typing.List[int]:
        """
        Returns the feature IDs of visualize SpectralProfiles from the connected SpectralLibrary.
        """
        return [pdi.id() for pdi in self.mPlotDataItems.values()]

    def profileKeysToVisualize(self) -> typing.List[typing.Tuple[int, str]]:
        """
        Returns the list of profile/feature ids to be visualized.
        Order of returned keys is equal to its importance.
        1st position = most important, should be plotted on top of all other profiles
        """
        if not isinstance(self.speclib(), SpectralLibrary):
            return []

        fieldNames = [f.name() for f in self.speclib().spectralValueFields()]

        if len(fieldNames) == 0:
            return []

        selectedOnly = self.actionShowSelectedProfilesOnly().isChecked()
        selectedIds = self.speclib().selectedFeatureIds()

        dualView = self.dualView()
        if isinstance(dualView, QgsDualView) and dualView.filteredFeatureCount() > 0:
            allIDs = dualView.filteredFeatures()
            selectedIds = [fid for fid in allIDs if fid in selectedIds]
        else:
            allIDs = self.speclib().allFeatureIds()

        # Order:
        # 1. visible in table
        # 2. selected
        # 3. others

        # overlaid features / current spectral
        priority0 = self.currentProfileIDs()
        priority1 = []  # visible features
        priority2 = []  # selected features
        priority3 = []  # any other : not visible / not selected

        if isinstance(dualView, QgsDualView):
            tv = dualView.tableView()
            assert isinstance(tv, QTableView)
            if not selectedOnly:
                rowHeight = tv.rowViewportPosition(1) - tv.rowViewportPosition(0)
                if rowHeight > 0:
                    for y in range(0, tv.viewport().height(), rowHeight):
                        idx = dualView.tableView().indexAt(QPoint(0, y))
                        if idx.isValid():
                            fid = tv.model().data(idx, role=Qt.UserRole)
                            priority1.append(fid)
            priority2 = self.dualView().masterModel().layer().selectedFeatureIds()
            if not selectedOnly:
                priority3 = dualView.filteredFeatures()
        else:
            priority2 = selectedIds
            if not selectedOnly:
                priority3 = allIDs

        featurePool = np.unique(priority0 + priority1 + priority2 + priority3).tolist()
        toVisualize = sorted(featurePool,
                             key=lambda fid: (fid not in priority0, fid not in priority1, fid not in priority2, fid))

        results = []
        for fid in toVisualize:
            for n in fieldNames:
                results.append((fid, n))
        return results

    def profileIDsToVisualizeOLD(self) -> typing.List[int]:
        """
        Returns the list of profile/feature ids to be visualized.
        Order of returned keys is equal to its importance.
        1st position = most important, should be plotted on top of all other profiles
        """
        if not isinstance(self.speclib(), SpectralLibrary):
            return []

        selectedOnly = self.actionShowSelectedProfilesOnly().isChecked()
        selectedIds = self.speclib().selectedFeatureIds()

        dualView = self.dualView()
        if isinstance(dualView, QgsDualView) and dualView.filteredFeatureCount() > 0:
            allIDs = dualView.filteredFeatures()
            selectedIds = [fid for fid in allIDs if fid in selectedIds]
        else:
            allIDs = self.speclib().allFeatureIds()

        nMax = len(allIDs)

        if nMax <= self.maxProfiles():
            if selectedOnly:
                return [fid for fid in allIDs if fid in selectedIds]
            else:
                return allIDs

        # Order:
        # 1. visible in table
        # 2. selected
        # 3. others

        # overlaid features / current spectral
        priority0 = self.currentProfileIDs()
        priority1 = []  # visible features
        priority2 = []  # selected features
        priority3 = []  # any other : not visible / not selected

        if isinstance(dualView, QgsDualView):
            tv = dualView.tableView()
            assert isinstance(tv, QTableView)
            if not selectedOnly:
                rowHeight = tv.rowViewportPosition(1) - tv.rowViewportPosition(0)
                for y in range(0, tv.viewport().height(), rowHeight):
                    idx = dualView.tableView().indexAt(QPoint(0, y))
                    if idx.isValid():
                        fid = tv.model().data(idx, role=Qt.UserRole)
                        priority1.append(fid)
            priority2 = self.dualView().masterModel().layer().selectedFeatureIds()
            if not selectedOnly:
                priority3 = dualView.filteredFeatures()
        else:
            priority2 = selectedIds
            if not selectedOnly:
                priority3 = allIDs

        featurePool = np.unique(priority0 + priority1 + priority2).tolist()
        toVisualize = sorted(featurePool,
                             key=lambda fid: (fid not in priority0, fid not in priority1, fid not in priority2, fid))
        maxProfiles = self.maxProfiles()
        if len(toVisualize) > maxProfiles:
            return sorted(toVisualize[0:maxProfiles])
        else:
            toVisualize = sorted(toVisualize)
            nMissing = min(maxProfiles - len(toVisualize), len(priority3))
            if nMissing > 0:
                toVisualize += sorted(priority3[0:nMissing])
            return toVisualize

    def dragEnterEvent(self, event: QDragEnterEvent):
        if containsSpeclib(event.mimeData()):
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if not containsSpeclib(event.mimeData()):
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()
        if containsSpeclib(mimeData) and isinstance(self.speclib(), SpectralLibrary):
            speclib = SpectralLibrary.readFromMimeData(mimeData)
            # print(f'DROP SPECLIB {speclib}')
            if isinstance(speclib, SpectralLibrary) and len(speclib) > 0:

                b = self.speclib().isEditable()
                self.speclib().startEditing()
                self.speclib().addSpeclib(speclib)
                if not b:
                    self.speclib().commitChanges()
            event.accept()
        else:
            super().dropEvent(event)


class SpectralProfileTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """

    sigXUnitChanged = pyqtSignal(str)
    sigYUnitChanged = pyqtSignal(str)

    def __init__(self, *args, **kwds):
        super(SpectralProfileTableModel, self).__init__(*args, **kwds)

        self.mColumnNames = {0: 'x',
                             1: 'y'}
        self.mColumnUnits = {0: None,
                             1: None}

        self.mValuesX: typing.Dict[int, typing.Any] = {}
        self.mValuesY: typing.Dict[int, typing.Any] = {}
        self.mValuesBBL: typing.Dict[int, typing.Any] = {}

        self.mLastProfile: SpectralProfile = SpectralProfile()

        self.mRows: int = 0

    def setBands(self, bands: int):
        bands = int(bands)

        assert bands >= 0

        if bands > self.bands():
            self.beginInsertRows(QModelIndex(), self.bands(), bands - 1)
            self.mRows = bands
            self.endInsertRows()

        elif bands < self.bands():
            self.beginRemoveRows(QModelIndex(), bands, self.bands() - 1)
            self.mRows = bands
            self.endRemoveRows()

    def bands(self) -> int:
        return self.rowCount()

    def setProfile(self, profile: SpectralProfile):
        """
        :param values:
        :return:
        """
        assert isinstance(profile, SpectralProfile)

        self.beginResetModel()
        self.mValuesX.clear()
        self.mValuesY.clear()
        self.mValuesBBL.clear()
        self.mLastProfile = profile
        self.mValuesX.update({i: v for i, v in enumerate(profile.xValues())})
        self.mValuesY.update({i: v for i, v in enumerate(profile.yValues())})
        self.mValuesBBL.update({i: v for i, v in enumerate(profile.bbl())})

        self.setBands(len(self.mValuesY))

        self.endResetModel()
        self.setXUnit(profile.xUnit())
        self.setYUnit(profile.yUnit())

    def setXUnit(self, unit: str):
        if self.xUnit() != unit:
            self.mColumnUnits[0] = unit
            idx0 = self.index(0, 0)
            idx1 = self.index(self.rowCount(QModelIndex()) - 1, 0)
            self.dataChanged.emit(idx0, idx1)
            # self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount(QModelIndex())-1)
            self.sigXUnitChanged.emit(unit)

    def setYUnit(self, unit: str):
        if self.yUnit() != unit:
            self.mColumnUnits[1] = unit
            # self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount(QModelIndex())-1)
            self.sigYUnitChanged.emit(unit)

    def xUnit(self) -> str:
        return self.mColumnUnits[0]

    def yUnit(self) -> str:
        return self.mColumnUnits[1]

    def profile(self) -> SpectralProfile:
        """
        Return the data as new SpectralProfile
        :return:
        :rtype:
        """
        p = SpectralProfile(fields=self.mLastProfile.fields())
        nb = self.bands()

        y = [self.mValuesY.get(b, None) for b in range(nb)]
        if self.xUnit() == BAND_INDEX:
            x = None
        else:
            x = [self.mValuesX.get(b, None) for b in range(nb)]

        bbl = [self.mValuesBBL.get(b, None) for b in range(nb)]
        bbl = np.asarray(bbl, dtype=bool)
        if np.any(bbl == False) == False:
            bbl = None
        p.setValues(x, y, xUnit=self.xUnit(), yUnit=self.yUnit(), bbl=bbl)

        return p

    def resetProfile(self):
        self.setProfile(self.mLastProfile)

    def rowCount(self, parent: QModelIndex = None, *args, **kwargs) -> int:

        return self.mRows

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.mColumnNames)

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role in [Qt.DisplayRole, Qt.EditRole]:
            value = None
            if c == 0:
                if self.xUnit() != BAND_INDEX:
                    value = self.mValuesX.get(i, None)
                    if value:
                        return str(value)
                    else:
                        return None
                else:
                    return i + 1

            elif c == 1:
                value = self.mValuesY.get(i, None)
                if value:
                    return str(value)
                else:
                    return None

        elif role == Qt.CheckStateRole:
            if c == 0:
                if bool(self.mValuesBBL.get(i, True)):
                    return Qt.Checked
                else:
                    return Qt.Unchecked
        return None

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        modified = False
        if role == Qt.CheckStateRole:
            if c == 0:
                self.mValuesBBL[i] = value == Qt.Checked
                modified = True

        if role == Qt.EditRole:
            if c == 0:
                try:
                    self.mValuesX[i] = float(value)
                    modified = True
                except:
                    pass
            elif c == 1:
                try:
                    self.mValuesY[i] = float(value)
                    modified = True
                except:
                    pass

        if modified:
            self.dataChanged.emit(index, index, [role])
        return modified

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            if c == 0:
                flags = flags | Qt.ItemIsUserCheckable
                if self.xUnit() != BAND_INDEX:
                    flags = flags | Qt.ItemIsEditable
            elif c == 1:
                flags = flags | Qt.ItemIsEditable
            return flags
        return None

    def headerData(self, col: int, orientation, role):

        if orientation == Qt.Horizontal and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            return self.mColumnNames.get(col, f'{col + 1}')
        return None


class SpectralProfileEditorWidget(QWidget):
    sigProfileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget, self).__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralprofileeditorwidget.ui'), self)
        self.mDefault: SpectralProfile = None
        self.mModel: SpectralProfileTableModel = SpectralProfileTableModel()
        self.mModel.rowsInserted.connect(self.onBandsChanged)
        self.mModel.rowsRemoved.connect(self.onBandsChanged)
        self.mModel.dataChanged.connect(lambda *args: self.onProfileChanged())
        self.mXUnitModel: XUnitModel = XUnitModel()
        self.cbXUnit.setModel(self.mXUnitModel)
        self.cbXUnit.currentIndexChanged.connect(
            lambda *args: self.mModel.setXUnit(self.cbXUnit.currentData(Qt.UserRole)))
        self.mModel.sigXUnitChanged.connect(self.onXUnitChanged)

        self.tbYUnit.textChanged.connect(self.mModel.setYUnit)
        self.mModel.sigYUnitChanged.connect(self.tbYUnit.setText)
        self.mModel.sigYUnitChanged.connect(self.onProfileChanged)
        self.mModel.sigXUnitChanged.connect(self.onProfileChanged)
        # self.mModel.sigColumnValueUnitChanged.connect(self.onValueUnitChanged)
        # self.mModel.sigColumnDataTypeChanged.connect(self.onDataTypeChanged)
        self.tableView.setModel(self.mModel)

        self.actionReset.triggered.connect(self.resetProfile)
        self.btnReset.setDefaultAction(self.actionReset)

        self.sbBands.valueChanged.connect(self.mModel.setBands)
        # self.onDataTypeChanged(0, float)
        # self.onDataTypeChanged(1, float)

        self.setProfile(SpectralProfile())

    def onProfileChanged(self):
        if self.profile() != self.mDefault:
            self.sigProfileChanged.emit()

    def onXUnitChanged(self, unit: str):
        unit = self.mXUnitModel.findUnit(unit)
        if unit is None:
            unit = BAND_INDEX
        self.cbXUnit.setCurrentIndex(self.mXUnitModel.unitIndex(unit).row())

    def onBandsChanged(self, *args):
        self.sbBands.setValue(self.mModel.bands())
        self.onProfileChanged()

    def initConfig(self, conf: dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        pass

    def setProfile(self, profile: SpectralProfile):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        assert isinstance(profile, SpectralProfile)
        self.mDefault = profile

        self.mModel.setProfile(profile)

    def resetProfile(self):
        self.mModel.setProfile(self.mDefault)

    def profile(self) -> SpectralProfile:
        """
        Returns modified SpectralProfile
        :return: dict
        """

        return self.mModel.profile()


class SpectralProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(SpectralProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mWidget: QWidget = None

        self.mLastValue = QVariant()

    def createWidget(self, parent: QWidget):
        # log('createWidget')

        if not self.isInTable(parent):
            self.mWidget = SpectralProfileEditorWidget(parent=parent)
        else:
            self.mWidget = QLabel(' Profile', parent=parent)
        return self.mWidget

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        conf = self.config()

        if isinstance(editor, SpectralProfileEditorWidget):

            editor.sigProfileChanged.connect(self.onValueChanged)
            editor.initConfig(conf)

        elif isinstance(editor, QLabel):
            editor.setText(SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE)
            editor.setToolTip('Use Form View to edit values')

    def onValueChanged(self, *args):
        self.valuesChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs) -> bool:
        return isinstance(self.mWidget, (SpectralProfileEditorWidget, QLabel))

    def value(self, *args, **kwargs):
        value = self.mLastValue
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            p = w.profile()
            value = encodeProfileValueDict(p.values())

        return value

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setEnabled(enabled)

    def setValue(self, value):
        self.mLastValue = value
        p = SpectralProfile(values=decodeProfileValueDict(value))
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setProfile(p)

        # if isinstance(self.mLabel, QLabel):
        #    self.mLabel.setText(value2str(value))


class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):

        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        loadUi(speclibUiPath('spectralprofileeditorconfigwidget.ui'), self)

        self.mLastConfig: dict = {}
        self.MYCACHE = dict()
        self.mFieldExpressionName: QgsFieldExpressionWidget
        self.mFieldExpressionSource: QgsFieldExpressionWidget

        self.mFieldExpressionName.setLayer(vl)
        self.mFieldExpressionSource.setLayer(vl)

        self.mFieldExpressionName.setFilters(QgsFieldProxyModel.String)
        self.mFieldExpressionSource.setFilters(QgsFieldProxyModel.String)

        self.mFieldExpressionName.fieldChanged[str, bool].connect(self.onFieldChanged)
        self.mFieldExpressionSource.fieldChanged[str, bool].connect(self.onFieldChanged)

    def onFieldChanged(self, expr: str, valid: bool):
        if valid:
            self.changed.emit()

    def expressionName(self) -> QgsExpression:
        exp = QgsExpression(self.mFieldExpressionName.expression())
        return exp

    def expressionSource(self) -> QgsExpression:
        exp = QgsExpression(self.mFieldExpressionSource.expression())
        return exp

    def config(self, *args, **kwargs) -> dict:
        config = {'expressionName': self.mFieldExpressionName.expression(),
                  'expressionSource': self.mFieldExpressionSource.expression(),
                  'mycache': self.MYCACHE}

        return config

    def setConfig(self, config: dict):
        self.mLastConfig = config
        field: QgsField = self.layer().fields().at(self.field())
        defaultExprName = "format('Profile %1 {}',$id)".format(field.name())
        defaultExprSource = ""
        # set some defaults
        if True:
            for field in self.layer().fields():
                assert isinstance(field, QgsField)
                if field.name() == 'name':
                    defaultExprName = f'"{field.name()}"'
                if field.name() == 'source':
                    defaultExprSource = f'"{field.name()}"'

        self.mFieldExpressionName.setExpression(config.get('expressionName', defaultExprName))
        self.mFieldExpressionSource.setExpression(config.get('expressionSource', defaultExprSource))
        # print('setConfig')


class SpectralProfileFieldFormatter(QgsFieldFormatter):

    def __init__(self, *args, **kwds):
        super(SpectralProfileFieldFormatter, self).__init__(*args, **kwds)

    def id(self) -> str:
        return EDITOR_WIDGET_REGISTRY_KEY

    def representValue(self, layer: QgsVectorLayer, fieldIndex: int, config: dict, cache, value):

        if value not in [None, NULL]:
            return SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE
        else:
            return 'Empty'
        s = ""


class SpectralProfileEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name: str):

        super(SpectralProfileEditorWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> SpectralProfileEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = SpectralProfileEditorConfigWidget(layer, fieldIdx, parent)
        key = self.configKey(layer, fieldIdx)
        w.setConfig(self.readConfig(key))
        w.changed.connect(lambda *args, ww=w, k=key: self.writeConfig(key, ww.config()))
        return w

    def configKey(self, layer: QgsVectorLayer, fieldIdx: int) -> typing.Tuple[str, int]:
        """
        Returns a tuple to be used as dictionary key to identify a layer field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return layer.id(), fieldIdx

    def create(self, layer: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> SpectralProfileEditorWidgetWrapper:
        """
        Create a SpectralProfileEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: SpectralProfileEditorWidgetWrapper
        """

        w = SpectralProfileEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        # self.editWrapper = w
        return w

    def writeConfig(self, key: tuple, config: dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config
        # print('Save config')
        # print(config)

    def readConfig(self, key: tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        return self.mConfigurations.get(key, {})

    def supportsField(self, vl: QgsVectorLayer, fieldIdx: int) -> bool:
        """
        :param vl:
        :param fieldIdx:
        :return:
        """
        field: QgsField = vl.fields().at(fieldIdx)
        return field.type() == QVariant.ByteArray

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() == QVariant.ByteArray:
            return 20
        else:
            return 0


def registerSpectralProfileEditorWidget():
    widgetRegistry = QgsGui.editorWidgetRegistry()
    fieldFormaterRegistry = QgsApplication.instance().fieldFormatterRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in widgetRegistry.factories().keys():
        global SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
        global SPECTRAL_PROFILE_FIELD_FORMATTER
        SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        SPECTRAL_PROFILE_FIELD_FORMATTER = SpectralProfileFieldFormatter()
        widgetRegistry.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)
        fieldFormaterRegistry.addFieldFormatter(SPECTRAL_PROFILE_FIELD_FORMATTER)
        s = ""


class SpectralLibraryWidget(AttributeTableWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)
    sigCurrentProfilesChanged = pyqtSignal(list)

    def __init__(self, *args, speclib: SpectralLibrary = None, mapCanvas: QgsMapCanvas = None, **kwds):

        if not isinstance(speclib, SpectralLibrary):
            speclib = SpectralLibrary()

        super().__init__(speclib)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib.svg'))
        self.mQgsStatusBar = QgsStatusBar(self.statusBar())
        self.mQgsStatusBar.setParentStatusBar(self.statusBar())
        self.mStatusLabel: SpectralLibraryInfoLabel = SpectralLibraryInfoLabel()
        self.mStatusLabel.setTextFormat(Qt.RichText)
        self.mQgsStatusBar.addPermanentWidget(self.mStatusLabel, 1, QgsStatusBar.AnchorLeft)

        self.mIODialogs: typing.List[QWidget] = list()

        from .io.envi import EnviSpectralLibraryIO
        from .io.csvdata import CSVSpectralLibraryIO
        from .io.asd import ASDSpectralLibraryIO
        from .io.ecosis import EcoSISSpectralLibraryIO
        from .io.specchio import SPECCHIOSpectralLibraryIO
        from .io.artmo import ARTMOSpectralLibraryIO
        from .io.vectorsources import VectorSourceSpectralLibraryIO
        from .io.rastersources import RasterSourceSpectralLibraryIO
        self.mSpeclibIOInterfaces = [
            EnviSpectralLibraryIO(),
            CSVSpectralLibraryIO(),
            ARTMOSpectralLibraryIO(),
            ASDSpectralLibraryIO(),
            EcoSISSpectralLibraryIO(),
            SPECCHIOSpectralLibraryIO(),
            VectorSourceSpectralLibraryIO(),
            RasterSourceSpectralLibraryIO(),
        ]

        self.mSpeclibIOInterfaces = sorted(self.mSpeclibIOInterfaces, key=lambda c: c.__class__.__name__)

        self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        self.mPlotWidget: SpectralLibraryPlotWidget = SpectralLibraryPlotWidget()
        assert isinstance(self.mPlotWidget, SpectralLibraryPlotWidget)
        self.mPlotWidget.setDualView(self.mMainView)
        self.mStatusLabel.setPlotWidget(self.mPlotWidget)
        self.mPlotWidget.mUpdateTimer.timeout.connect(self.mStatusLabel.update)

        l = QVBoxLayout()
        l.addWidget(self.mPlotWidget)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        self.widgetRight.setLayout(l)
        self.widgetRight.setVisible(True)

        # define Actions and Options

        self.actionSelectProfilesFromMap = QAction(r'Select Profiles from Map')
        self.actionSelectProfilesFromMap.setToolTip(r'Select new profile from map')
        self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddProfiles = QAction('Add Profile(s)')
        self.actionAddProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.actionAddCurrentProfiles = QAction('Add Profiles(s)')
        self.actionAddCurrentProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.optionAddCurrentProfilesAutomatically = QAction('Add profiles automatically')
        self.optionAddCurrentProfilesAutomatically.setToolTip('Activate to add profiles automatically '
                                                              'into the spectral library')
        self.optionAddCurrentProfilesAutomatically.setIcon(QIcon(':/qps/ui/icons/profile_add_auto.svg'))
        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)

        self.actionImportVectorRasterSource = QAction('Import profiles from raster + vector source')
        self.actionImportVectorRasterSource.setToolTip('Import spectral profiles from a raster image '
                                                       'based on vector geometries (Points).')
        self.actionImportVectorRasterSource.setIcon(QIcon(':/images/themes/default/mActionAddOgrLayer.svg'))
        self.actionImportVectorRasterSource.triggered.connect(self.onImportFromRasterSource)

        m = QMenu()
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        self.actionAddProfiles.setMenu(m)

        self.actionImportSpeclib = QAction('Import Spectral Profiles')
        self.actionImportSpeclib.setToolTip('Import spectral profiles from other data sources')
        self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        m = QMenu()
        m.addAction(self.actionImportVectorRasterSource)
        m.addSeparator()
        self.createSpeclibImportMenu(m)
        self.actionImportSpeclib.setMenu(m)
        self.actionImportSpeclib.triggered.connect(self.onImportSpeclib)

        self.actionExportSpeclib = QAction('Export Spectral Profiles')
        self.actionExportSpeclib.setToolTip('Export spectral profiles to other data formats')
        self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))

        m = QMenu()
        self.createSpeclibExportMenu(m)
        self.actionExportSpeclib.setMenu(m)
        self.actionExportSpeclib.triggered.connect(self.onExportSpectra)

        self.tbSpeclibAction = QToolBar('Spectral Profiles')
        self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        self.tbSpeclibAction.addAction(self.actionAddProfiles)
        self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        self.tbSpeclibAction.addAction(self.actionExportSpeclib)

        self.tbSpeclibAction.addSeparator()
        self.cbXAxisUnit = self.plotWidget().actionXAxis().createUnitComboBox()
        self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        self.tbSpeclibAction.addAction(self.plotWidget().optionUseVectorSymbology())

        self.insertToolBar(self.mToolbar, self.tbSpeclibAction)

        self.actionShowProperties = QAction('Show Spectral Library Properties')
        self.actionShowProperties.setToolTip('Show Spectral Library Properties')
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.btnShowProperties = QToolButton()
        self.btnShowProperties.setAutoRaise(True)
        self.btnShowProperties.setDefaultAction(self.actionShowProperties)

        self.centerBottomLayout.insertWidget(self.centerBottomLayout.indexOf(self.mAttributeViewButton),
                                             self.btnShowProperties)

        self.setAcceptDrops(True)

    def tableView(self) -> QgsAttributeTableView:
        return self.mMainView.tableView()

    def onShowContextMenuAttributeEditor(self, menu: QgsActionMenu, fid):
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def onWillShowContextMenuAttributeTable(self, menu: QMenu, atIndex: QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def addProfileStyleMenu(self, menu: QMenu):
        selectedFIDs = self.tableView().selectedFeaturesIds()
        n = len(selectedFIDs)
        menuProfileStyle = menu.addMenu('Profile Style')
        wa = QWidgetAction(menuProfileStyle)

        btnResetProfileStyles = QPushButton('Reset')
        btnApplyProfileStyle = QPushButton('Apply')

        plotStyle = self.plotWidget().profileRenderer().profileStyle
        if n == 0:
            btnResetProfileStyles.setText('Reset All')
            btnResetProfileStyles.clicked.connect(self.plotWidget().resetProfileStyles)
            btnResetProfileStyles.setToolTip('Resets all profile styles')
        else:
            for fid in selectedFIDs:
                ps = self.plotWidget().profileRenderer().profilePlotStyle(fid, ignore_selection=True)
                if isinstance(ps, PlotStyle):
                    plotStyle = ps.clone()
                break

            btnResetProfileStyles.setText('Reset Selected')
            btnResetProfileStyles.clicked.connect(
                lambda *args, fids=selectedFIDs: self.plotWidget().setProfileStyles(None, fids))

        psw = PlotStyleWidget(plotStyle=plotStyle)
        psw.setPreviewVisible(False)
        psw.cbIsVisible.setVisible(False)
        btnApplyProfileStyle.clicked.connect(lambda *args, fids=selectedFIDs, w=psw:
                                             self.plotWidget().setProfileStyles(psw.plotStyle(), fids))

        hb = QHBoxLayout()
        hb.addWidget(btnResetProfileStyles)
        hb.addWidget(btnApplyProfileStyle)
        l = QVBoxLayout()
        l.addWidget(psw)
        l.addLayout(hb)

        frame = QFrame()
        frame.setLayout(l)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

    def showProperties(self, *args):

        from ..layerproperties import showLayerPropertiesDialog

        showLayerPropertiesDialog(self.speclib(), None, parent=self, useQGISDialog=True)

        s = ""

    def createSpeclibImportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to import SpectralProfiles
        """
        separated = []
        from .io.rastersources import RasterSourceSpectralLibraryIO

        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO), iface
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addImportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addImportActions(self.speclib(), menu)

    def createSpeclibExportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to export the SpectralLibrary
        """
        separated = []
        from .io.rastersources import RasterSourceSpectralLibraryIO
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO)
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addExportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addExportActions(self.speclib(), menu)

    def plotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mPlotWidget

    def plotItem(self) -> SpectralLibraryPlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.mPlotWidget.getPlotItem()

    def updatePlot(self):
        self.plotWidget().updatePlot()

    def speclib(self) -> SpectralLibrary:
        return self.mLayer

    def spectralLibrary(self) -> SpectralLibrary:
        return self.speclib()

    def addSpeclib(self, speclib: SpectralLibrary):
        assert isinstance(speclib, SpectralLibrary)
        sl = self.speclib()
        wasEditable = sl.isEditable()
        try:
            sl.startEditing()
            info = 'Add {} profiles from {} ...'.format(len(speclib), speclib.name())
            sl.beginEditCommand(info)
            sl.addSpeclib(speclib)
            sl.endEditCommand()
            if not wasEditable:
                sl.commitChanges()
        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

    def addCurrentSpectraToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """

        fids = self.plotWidget().currentProfileIDs()
        self.plotWidget().mTEMPORARY_HIGHLIGHTED.clear()
        self.plotWidget().updateProfileStyles(fids)

    def setCurrentProfiles(self,
                           currentProfiles: list,
                           profileStyles: typing.Dict[SpectralProfile, PlotStyle] = None):
        assert isinstance(currentProfiles, list)

        if not isinstance(profileStyles, dict):
            profileStyles = dict()

        speclib: SpectralLibrary = self.speclib()
        plotWidget: SpectralLibraryPlotWidget = self.plotWidget()

        #  stop plot updates
        plotWidget.mUpdateTimer.stop()
        restart_editing = not speclib.startEditing()
        oldCurrentKeys = self.plotWidget().currentProfileKeys()
        oldCurrentIDs = self.plotWidget().currentProfileIDs()
        addAuto: bool = self.optionAddCurrentProfilesAutomatically.isChecked()

        if not addAuto:
            # delete previous current profiles from speclib
            speclib.deleteFeatures(oldCurrentIDs)
            plotWidget.removeSpectralProfilePDIs(oldCurrentKeys, updateScene=False)
            # now there shouldn't be any PDI or style ref related to an old ID
        else:
            self.addCurrentSpectraToSpeclib()

        self.plotWidget().mTEMPORARY_HIGHLIGHTED.clear()
        # if necessary, convert QgsFeatures to SpectralProfiles
        for i in range(len(currentProfiles)):
            p = currentProfiles[i]
            assert isinstance(p, QgsFeature)
            if not isinstance(p, SpectralProfile):
                p = SpectralProfile.fromQgsFeature(p)
                currentProfiles[i] = p

        # add current profiles to speclib
        oldIDs = set(speclib.allFeatureIds())
        res = speclib.addProfiles(currentProfiles)

        self.speclib().commitChanges()
        if restart_editing:
            speclib.startEditing()

        addedIDs = sorted(set(speclib.allFeatureIds()).difference(oldIDs))
        addedKeys = []
        value_fields = [f.name() for f in self.speclib().spectralValueFields()]

        for id in addedIDs:
            for n in value_fields:
                addedKeys.append((id, n))
        # set profile style
        PROFILE2FID = dict()
        for p, fid in zip(currentProfiles, addedIDs):
            PROFILE2FID[p] = fid

        renderer = self.speclib().profileRenderer()

        customStyles = set(profileStyles.values())
        if len(customStyles) > 0:
            profileRenderer = plotWidget.profileRenderer()
            for customStyle in customStyles:
                fids = [PROFILE2FID[p] for p, s in profileStyles.items() if s == customStyle]
                profileRenderer.setProfilePlotStyle(customStyle, fids)
            plotWidget.setProfileRenderer(profileRenderer)

        # set current profiles highlighted

        if not addAuto:
            # give current spectra the current spectral style
            self.plotWidget().mTEMPORARY_HIGHLIGHTED.update(addedKeys)

        plotWidget.mUpdateTimer.start()

    def currentProfiles(self) -> typing.List[SpectralProfile]:
        return self.mPlotWidget.currentProfiles()

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mMapCanvas

    def setAddCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def dropEvent(self, event):
        self.plotWidget().dropEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.plotWidget().dragEnterEvent(event)

    def onImportSpeclib(self):
        """
        Imports a SpectralLibrary
        :param path: str
        """

        slib = SpectralLibrary.readFromSourceDialog(self)

        if isinstance(slib, SpectralLibrary) and len(slib) > 0:
            self.addSpeclib(slib)

    def onImportFromRasterSource(self):
        from .io.rastersources import SpectralProfileImportPointsDialog
        d = SpectralProfileImportPointsDialog(parent=self)
        d.finished.connect(lambda *args, d=d: self.onIODialogFinished(d))
        d.show()
        self.mIODialogs.append(d)

    def onIODialogFinished(self, w: QWidget):
        from .io.rastersources import SpectralProfileImportPointsDialog
        if isinstance(w, SpectralProfileImportPointsDialog):
            if w.result() == QDialog.Accepted:
                profiles = w.profiles()
                info = w.rasterSource().name()
                self.addProfiles(profiles, add_missing_fields=w.allAttributes())
            else:
                s = ""

        if w in self.mIODialogs:
            self.mIODialogs.remove(w)
        w.close()

    def addProfiles(self, profiles, add_missing_fields: bool = False):
        b = self.speclib().isEditable()
        self.speclib().startEditing()
        self.speclib().beginEditCommand('Add {} profiles'.format(len(profiles)))
        self.speclib().addProfiles(profiles, addMissingFields=add_missing_fields)
        self.speclib().endEditCommand()
        self.speclib().commitChanges()
        if b:
            self.speclib().startEditing()

    def onExportSpectra(self, *args):
        files = self.speclib().write(None)
        if len(files) > 0:
            self.sigFilesCreated.emit(files)

    def clearSpectralLibrary(self):
        """
        Removes all SpectralProfiles and additional fields
        """
        warnings.warn('Deprectated and desimplemented', DeprecationWarning)


class SpectralLibraryInfoLabel(QLabel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mPW: SpectralLibraryPlotWidget = None

        self.mLastStats: SpectralLibraryPlotStats = None
        self.setStyleSheet('QToolTip{width:300px}')

    def setPlotWidget(self, pw: SpectralLibraryPlotWidget):
        assert isinstance(pw, SpectralLibraryPlotWidget)
        self.mPW = pw

    def plotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mPW

    def update(self):
        if not isinstance(self.plotWidget(), SpectralLibraryPlotWidget):
            self.setText('')
            self.setToolTip('')
            return

        stats = self.plotWidget().profileStats()
        if self.mLastStats == stats:
            return

        msg = f'<html><head/><body>'
        ttp = f'<html><head/><body><p>'

        # total + filtering
        if stats.filter_mode == QgsAttributeTableFilterModel.ShowFilteredList:
            msg += f'{stats.profiles_filtered}f'
            ttp += f'{stats.profiles_filtered} profiles filtered out of {stats.profiles_total}<br/>'
        else:
            # show all
            msg += f'{stats.profiles_total}'
            ttp += f'{stats.profiles_total} profiles in total<br/>'

        # show selected
        msg += f'/{stats.profiles_selected}'
        ttp += f'{stats.profiles_selected} selected in plot<br/>'

        if stats.profiles_empty > 0:
            msg += f'/<span style="color:red">{stats.profiles_empty}N</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_empty} profile fields empty (NULL)<br/>'

        if stats.profiles_error > 0:
            msg += f'/<span style="color:red">{stats.profiles_error}E</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_error} profiles ' \
                   f'can not be converted to X axis unit "{self.plotWidget().xUnit()}" (ERROR)</span><br/>'

        if stats.profiles_plotted >= stats.profiles_plotted_max and stats.profiles_total > stats.profiles_plotted_max:
            msg += f'/<span style="color:red">{stats.profiles_plotted}</span>'
            ttp += f'<span style="color:red">{stats.profiles_plotted} profiles plotted. Increase plot ' \
                   f'limit ({stats.profiles_plotted_max}) to show more at same time.</span><br/>'
        else:
            msg += f'/{stats.profiles_plotted}'
            ttp += f'{stats.profiles_plotted} profiles plotted<br/>'

        msg += '</body></html>'
        ttp += '</p></body></html>'

        self.setText(msg)
        self.setToolTip(ttp)
        self.setMinimumWidth(self.sizeHint().width())

        self.mLastStats = stats

    def contextMenuEvent(self, event: QContextMenuEvent):
        m = QMenu()

        stats = self.plotWidget().profileStats()

        a = m.addAction('Select axis-unit incompatible profiles')
        a.setToolTip(f'Selects all profiles that cannot be displayed in {self.plotWidget().xUnit()}')
        a.triggered.connect(self.onSelectAxisUnitIncompatibleProfiles)

        a = m.addAction('Reset to band index')
        a.setToolTip('Resets the x-axis to show the band index.')
        a.triggered.connect(lambda *args: self.plotWidget().setXUnit(BAND_INDEX))

        m.exec_(event.globalPos())

    def onSelectAxisUnitIncompatibleProfiles(self):
        incompatible = []
        pw: SpectralLibraryPlotWidget = self.plotWidget()
        if not isinstance(pw, SpectralLibraryPlotWidget) or not isinstance(pw.speclib(), SpectralLibrary):
            return

        targetUnit = pw.xUnit()
        for p in pw.speclib():
            if isinstance(p, SpectralProfile):
                f = pw.unitConversionFunction(p.xUnit(), targetUnit)
                if f == pw.mUnitConverter.func_return_none:
                    incompatible.append(p.id())

        pw.speclib().selectByIds(incompatible)


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib: SpectralLibrary = None, **kwds):
        super(SpectralLibraryPanel, self).__init__(*args, **kwds)
        self.setObjectName('spectralLibraryPanel')

        self.SLW = SpectralLibraryWidget(speclib=speclib)
        self.setWindowTitle(self.speclib().name())
        self.speclib().nameChanged.connect(lambda *args: self.setWindowTitle(self.speclib().name()))
        self.setWidget(self.SLW)

    def spectralLibraryWidget(self) -> SpectralLibraryWidget:
        """
        Returns the SpectralLibraryWidget
        :return: SpectralLibraryWidget
        """
        return self.SLW

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary
        :return: SpectralLibrary
        """
        return self.SLW.speclib()

    def setCurrentSpectra(self, listOfSpectra):
        """
        Adds a list of SpectralProfiles as current spectra
        :param listOfSpectra: [list-of-SpectralProfiles]
        :return:
        """
        self.SLW.setCurrentProfiles(listOfSpectra)


class SpectralLibraryConsistencyCheckWidget(QWidget):

    def __init__(self, speclib: SpectralLibrary = None, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryconsistencycheckwidget.ui'), self)
        self.mSpeclib: SpectralLibrary = speclib
        self.tbSpeclibInfo.setText('')
        if speclib:
            self.setSpeclib(speclib)

    def setSpeclib(self, speclib: SpectralLibrary):
        assert isinstance(speclib, SpectralLibrary)
        self.mSpeclib = speclib
        self.mSpeclib.nameChanged.connect(self.updateSpeclibInfo)
        self.updateSpeclibInfo()

    def updateSpeclibInfo(self):
        info = '{}: {} profiles'.format(self.mSpeclib.name(), len(self.mSpeclib))
        self.tbSpeclibInfo.setText(info)

    def speclib(self) -> SpectralLibrary:
        return self.mSpeclib

    def startCheck(self):
        consistencyCheck(self.mSpeclib)
