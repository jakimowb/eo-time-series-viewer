# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    plotting.py
    Functionality to plot SpectralLibraries
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This file is part of the EnMAP-Box.                                   *
*                                                                         *
*   The EnMAP-Box is free software; you can redistribute it and/or modify *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
*   The EnMAP-Box is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          *
*   GNU General Public License for more details.                          *
*                                                                         *
*   You should have received a copy of the GNU General Public License     *
*   along with the EnMAP-Box. If not, see <http://www.gnu.org/licenses/>. *
*                                                                         *
***************************************************************************
"""
import sys, re, os, collections, typing, random, copy
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.gui import *
from qgis.core import *
from ..externals.pyqtgraph.functions import mkPen
from ..externals import pyqtgraph as pg
from ..externals.pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from ..utils import METRIC_EXPONENTS, convertMetricUnit
from .spectrallibraries import SpectralProfile, SpectralLibrary, MIMEDATA_SPECLIB_LINK, FIELD_VALUES, X_UNITS, speclibSettings, SpectralLibrarySettingsKey, loadSpeclibUI
from ..plotstyling.plotstyling import PlotStyleWidget, PlotStyle

BAND_INDEX = 'Band Index'


def defaultCurvePlotStyle()->PlotStyle:
    ps = PlotStyle()
    ps.setLineColor('white')
    ps.markerSymbol = None
    ps.linePen.setStyle(Qt.SolidLine)
    return ps

class SpectralXAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(SpectralXAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(True)
        self.labelAngle = 0


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
            # item.setMeta(params)
            self.curves.extend(items)
            # self.addItem(c)

        # if hasattr(item, 'setLogMode'):
        #    item.setLogMode(self.ctrl.logXCheck.isChecked(), self.ctrl.logYCheck.isChecked())

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

            # c.connect(c, QtCore.SIGNAL('plotChanged'), self.plotChanged)
            # item.sigPlotChanged.connect(self.plotChanged)
            # self.plotChanged()
        # name = kargs.get('name', getattr(item, 'opts', {}).get('name', None))
        # if name is not None and hasattr(self, 'legend') and self.legend is not None:
        #    self.legend.addItem(item, name=name)


class SpectralLibraryPlotColorScheme(object):

    @staticmethod
    def default():
        """
        Returns the default plotStyle scheme.
        :return:
        :rtype: SpectralLibraryPlotColorScheme
        """
        return SpectralLibraryPlotColorScheme.dark()

    @staticmethod
    def fromUserSettings():
        """
        Returns the SpectralLibraryPlotColorScheme last  saved in then library settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        scheme = SpectralLibraryPlotColorScheme.default()

        if SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name in settings.allKeys():
            scheme.ps = PlotStyle.fromJSON(settings.value(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name))
        if SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name in settings.allKeys():
            scheme.cs = PlotStyle.fromJSON(settings.value(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name))

        scheme.bg = settings.value(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, scheme.bg)
        scheme.fg = settings.value(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, scheme.fg)
        scheme.ic = settings.value(SpectralLibrarySettingsKey.INFO_COLOR.name, scheme.ic)
        scheme.useRendererColors = settings.value(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, scheme.useRendererColors) in ['True', 'true', True]

        return scheme


    @staticmethod
    def dark():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('white')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotColorScheme(
            name='Dark', fg=QColor('white'), bg=QColor('black'),
            ic=QColor('yellow'), ps=ps, cs=cs, userRendererColors=False)

    @staticmethod
    def bright():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('black')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotColorScheme(
            name='Bright', fg=QColor('black'), bg=QColor('white'),
            ic=QColor('red'), ps=ps, cs=cs, userRendererColors=False)

    def __init__(self, name:str='color_scheme',
                 fg:QColor=QColor('white'),
                 bg:QColor=QColor('black'),
                 ps:PlotStyle=PlotStyle(),
                 cs:PlotStyle=PlotStyle(),
                 ic:QColor=QColor('yellow'),
                 userRendererColors:bool=True):

        self.name:str
        self.name = name

        self.fg : QColor
        self.fg = fg

        self.bg : QColor
        self.bg = bg

        self.ps:PlotStyle
        self.ps = ps
        self.cs: PlotStyle
        self.cs = cs
        self.ic:QColor
        self.ic = ic
        self.useRendererColors:bool
        self.useRendererColors = userRendererColors

    def clone(self):
        return copy.deepcopy(self)

    def __copy__(self):
        return copy.copy(self)

    def saveToUserSettings(self):
        """
        Saves this plotStyle scheme to the user Qt user settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        settings.setValue(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name, self.ps.json())
        settings.setValue(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name, self.cs.json())
        settings.setValue(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, self.bg)
        settings.setValue(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, self.fg)
        settings.setValue(SpectralLibrarySettingsKey.INFO_COLOR.name, self.ic)
        settings.setValue(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, self.useRendererColors)


    def __eq__(self, other):
        if not isinstance(other, SpectralLibraryPlotColorScheme):
            return False
        else:

            return self.bg == other.bg and \
                   self.fg == other.fg and \
                   self.ic == other.ic and \
                   self.ps == other.ps and \
                   self.cs == other.cs and \
                   self.useRendererColors == other.useRendererColors





class SpectralLibraryPlotColorSchemeWidget(QWidget, loadSpeclibUI('spectrallibraryplotcolorschemewidget.ui')):

    sigColorSchemeChanged = pyqtSignal(SpectralLibraryPlotColorScheme)

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotColorSchemeWidget, self).__init__(*args, **kwds)
        self.setupUi(self)

        self.mBlocked = False

        self.mLastColorScheme: SpectralLibraryPlotColorScheme
        self.mLastColorScheme = None


        self.btnColorBackground.colorChanged.connect(self.onColorSchemeChanged)
        self.btnColorForeground.colorChanged.connect(self.onColorSchemeChanged)
        self.btnColorInfo.colorChanged.connect(self.onColorSchemeChanged)
        self.cbUseRendererColors.clicked.connect(self.onCbUseRendererColorsClicked)

        self.wDefaultProfileStyle.setPreviewVisible(False)
        self.wDefaultProfileStyle.cbIsVisible.setVisible(False)
        self.wDefaultProfileStyle.sigPlotStyleChanged.connect(self.onColorSchemeChanged)
        self.wDefaultProfileStyle.setMinimumSize(self.wDefaultProfileStyle.sizeHint())
        self.btnReset.setDisabled(True)
        self.btnReset.clicked.connect(lambda : self.setColorScheme(self.mLastColorScheme))
        self.btnColorSchemeBright.clicked.connect(lambda : self.setColorScheme(SpectralLibraryPlotColorScheme.bright()))
        self.btnColorSchemeDark.clicked.connect(lambda: self.setColorScheme(SpectralLibraryPlotColorScheme.dark()))



        #l.setMargin(1)
        #l.setSpacing(2)
        #frame.setMinimumSize(l.sizeHint())

    def onCbUseRendererColorsClicked(self, checked:bool):
        self.onColorSchemeChanged()
        w = self.wDefaultProfileStyle
        assert isinstance(w, PlotStyleWidget)
        w.btnLinePenColor.setDisabled(checked)


    def setColorScheme(self, colorScheme:SpectralLibraryPlotColorScheme):
        assert isinstance(colorScheme, SpectralLibraryPlotColorScheme)

        if self.mLastColorScheme is None:
            self.mLastColorScheme = colorScheme
            self.btnReset.setEnabled(True)


        changed = colorScheme != self.colorScheme()

        self.mBlocked = True

        self.btnColorBackground.setColor(colorScheme.bg)
        self.btnColorForeground.setColor(colorScheme.fg)
        self.btnColorInfo.setColor(colorScheme.ic)
        self.wDefaultProfileStyle.setPlotStyle(colorScheme.ps)
        ''
        self.cbUseRendererColors.setChecked(colorScheme.useRendererColors)

        self.mBlocked = False
        if changed:
            self.sigColorSchemeChanged.emit(self.colorScheme())

    def onColorSchemeChanged(self, *args):
        if not self.mBlocked:
            self.sigColorSchemeChanged.emit(self.colorScheme())

        self.btnReset.setEnabled(isinstance(self.mLastColorScheme, SpectralLibraryPlotColorScheme) and
                                 self.colorScheme() != self.mLastColorScheme)

    def colorScheme(self)->SpectralLibraryPlotColorScheme:
        cs = SpectralLibraryPlotColorScheme()
        cs.bg = self.btnColorBackground.color()
        cs.fg = self.btnColorForeground.color()
        cs.ic = self.btnColorInfo.color()
        cs.ps = self.wDefaultProfileStyle.plotStyle()
        cs.cs = self.mLastColorScheme.cs
        cs.useRendererColors = self.cbUseRendererColors.isChecked()
        return cs




class SpectralProfilePlotDataItem(PlotDataItem):
    """
    A pyqtgraph.PlotDataItem to plot a SpectralProfile
    """

    def __init__(self, spectralProfile: SpectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super(SpectralProfilePlotDataItem, self).__init__()

        self.mXValueConversionFunction = lambda v, *args: v
        self.mYValueConversionFunction = lambda v, *args: v

        self.mDefaultStyle = PlotStyle()


        self.mProfile:SpectralProfile
        self.mProfile = None
        self.mInitialDataX = None
        self.mInitialDataY = None
        self.mInitialUnitX = None
        self.mInitialUnitY = None


        self.initProfile(spectralProfile)
        self.applyMapFunctions()

    def initProfile(self, spectralProfile: SpectralProfile):
        """
        Initializes internal spectral profile settings
        :param spectralProfile: SpectralProfile
        """
        assert isinstance(spectralProfile, SpectralProfile)
        self.mProfile = spectralProfile
        self.mInitialDataX = spectralProfile.xValues()
        self.mInitialDataY = spectralProfile.yValues()
        self.mInitialUnitX = spectralProfile.xUnit()
        self.mInitialUnitY = spectralProfile.yUnit()
        for v in [self.mInitialDataX, self.mInitialDataY]:
            assert isinstance(v, list)

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
        :param func: callable, mapping function
        """
        assert callable(func)
        self.mYValueConversionFunction = func

    def applyMapFunctions(self) -> bool:
        """
        Applies the two functions defined with `.setMapFunctionX` and `.setMapFunctionY`.
        :return: bool, True in case of success
        """
        success = False
        if len(self.mInitialDataX) > 0 and len(self.mInitialDataY) > 0:
            x = None
            y = None

            try:
                x = self.mXValueConversionFunction(self.mInitialDataX, self)
                y = self.mYValueConversionFunction(self.mInitialDataY, self)
                if isinstance(x, list) and isinstance(y, list) and len(x) > 0 and len(y) > 0:
                    success = True
            except Exception as ex:
                print(ex)
                pass

        if success:
            self.setData(x=x, y=y)
            self.setVisible(True)
        else:
            # self.setData(x=[], y=[])
            self.setVisible(False)

        return success

    def id(self) -> int:
        """
        Returns the profile id
        :return: int
        """
        return self.mProfile.id()

    def setClickable(self, b: bool, width=None):
        """

        :param b:
        :param width:
        :return:
        """
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setSelected(self, b: bool):
        """
        Sets if this profile should appear as "selected"
        :param b: bool
        """

        if b:
            self.setLineWidth(self.mDefaultStyle.lineWidth() + 3)
            self.setZValue(999999)
            # self.setColor(Qgis.DEFAULT_HIGHLIGHT_COLOR)
        else:
            self.setLineWidth(self.mDefaultStyle.lineWidth())
            self.setZValue(1)

    def setPlotStyle(self, plotStyle:PlotStyle, updateItem=True):
        """
        Applies a PlotStyle to this SpectralProfilePlotDataItem
        :param plotStyle:
        :type plotStyle:
        :param updateItem: set True (default) to apply changes immediately.
        :type updateItem: bool
        """
        assert isinstance(plotStyle, PlotStyle)
        plotStyle.apply(self, updateItem=updateItem)

    def plotStyle(self)->PlotStyle:
        """
        Returns the SpectralProfilePlotDataItems' PlotStyle
        :return: PlotStyle
        :rtype: PlotStyle
        """
        return PlotStyle.fromPlotDataItem(self)

    def setColor(self, color: QColor):
        """
        Sets the profile plotStyle
        :param color: QColor
        """
        if not isinstance(color, QColor):
            color = QColor(color)

        style = self.profileStyle()
        style.linePen.setColor(color)
        self.setProfileStyle(style)

    def pen(self) -> QPen:
        """
        Returns the QPen of the profile
        :return: QPen
        """
        return mkPen(self.opts['pen'])

    def color(self) -> QColor:
        """
        Returns the profile plotStyle
        :return: QColor
        """
        return self.pen().color()


    def setLineWidth(self, width:int):
        """
        Set the profile width in px
        :param width: int
        """
        pen = mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)

    def lineWidth(self)->int:
        """
        Returns the line width
        :return: line width in pixel
        :rtype: int
        """
        return self.pen().width()

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

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


class SpectralViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    sigXUnitChanged = pyqtSignal(str)
    sigColorSchemeChanged = pyqtSignal(SpectralLibraryPlotColorScheme)
    sigMaxNumberOfProfilesChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(SpectralViewBox, self).__init__(parent)
        # self.menu = None # Override pyqtgraph ViewBoxMenu
        # self.menu = self.getMenu() # Create the menu
        # self.menu = None

        xAction = [a for a in self.menu.actions() if a.text() == 'X Axis'][0]
        yAction = [a for a in self.menu.actions() if a.text() == 'Y Axis'][0]


        self.cbXAxisUnits = QComboBox(parent)


        # profile settings
        menuProfiles = self.menu.addMenu('Profiles')
        l = QGridLayout()
        self.sbMaxProfiles = QSpinBox(parent)
        self.sbMaxProfiles.setToolTip('Maximum number of profiles to plot.')
        self.sbMaxProfiles.setRange(0, 256)
        self.sbMaxProfiles.setValue(64)
        self.sbMaxProfiles.valueChanged[int].connect(self.sigMaxNumberOfProfilesChanged)
        l.addWidget(QLabel('Max.'), 0, 0)
        l.addWidget(self.sbMaxProfiles, 0, 1)
        frame = QFrame()
        frame.setLayout(l)
        wa = QWidgetAction(menuProfiles)
        wa.setDefaultWidget(frame)
        menuProfiles.addAction(wa)

        # color settings
        menuColors = self.menu.addMenu('Colors')
        wa = QWidgetAction(menuColors)
        self.wColorScheme = SpectralLibraryPlotColorSchemeWidget(parent)
        self.wColorScheme.sigColorSchemeChanged.connect(self.sigColorSchemeChanged.emit)
        wa.setDefaultWidget(self.wColorScheme)
        menuColors.addAction(wa)

        menuXAxis = self.menu.addMenu('X Axis')

        # define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()
        frame.setLayout(l)
        self.rbXManualRange = QRadioButton('Manual')
        self.rbXAutoRange = QRadioButton('Auto')
        self.rbXAutoRange.setChecked(True)

        l.addWidget(self.rbXManualRange, 0, 0)
        l.addWidget(self.rbXAutoRange, 1, 0)

        self.mCBXAxisUnit = QComboBox()

        # Order of X units:
        # 1. long names
        # 2. short si names
        # 3. within these groups: by exponent
        items = sorted(METRIC_EXPONENTS.items(), key=lambda item: item[1])
        fullNames = []
        siNames = []
        for item in items:
            if len(item[0]) > 5:
                # make centimeters to Centimeters
                item = (item[0].title(), item[1])
                fullNames.append(item)
            else:
                siNames.append(item)

        self.mCBXAxisUnit.addItem(BAND_INDEX, userData='')
        for item in fullNames + siNames:
            name, exponent = item
            self.mCBXAxisUnit.addItem(name, userData=name)
        self.mCBXAxisUnit.setCurrentIndex(0)

        self.mCBXAxisUnit.currentIndexChanged.connect(
            lambda: self.sigXUnitChanged.emit(self.mCBXAxisUnit.currentText()))

        l.addWidget(QLabel('Unit'), 2, 0)
        l.addWidget(self.mCBXAxisUnit, 2, 1)

        self.mXAxisUnit = 'index'

        l.setMargin(1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuXAxis)
        wa.setDefaultWidget(frame)
        menuXAxis.addAction(wa)

        self.menu.insertMenu(xAction, menuXAxis)
        self.menu.removeAction(xAction)

        self.mActionShowCrosshair = self.menu.addAction('Show Crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)
        self.mActionShowCursorValues = self.menu.addAction('Show Mouse values')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

    def raiseContextMenu(self, ev):
        self.mLastColorScheme = self.colorScheme()
        super(SpectralViewBox, self).raiseContextMenu(ev)

    def setColorScheme(self, colorScheme:SpectralLibraryPlotColorScheme):
        assert isinstance(colorScheme, SpectralLibraryPlotColorScheme)
        self.wColorScheme.setColorScheme(colorScheme)

    def colorScheme(self)->SpectralLibraryPlotColorScheme:
        """
        Returns the color scheme
        """
        return self.wColorScheme.colorScheme()

    def setXAxisUnit(self, unit: str):
        """
        Sets the X axis unit.
        :param unit: str, metric unit like `nm` or `Nanometers`.
        """
        i = self.mCBXAxisUnit.findText(unit)
        if i == -1:
            i = 0
        if i != self.mCBXAxisUnit.currentIndex():
            self.mCBXAxisUnit.setCurrentIndex(i)

    def xAxisUnit(self) -> str:
        """
        Returns unit of X-Axis values
        :return: str
        """
        return self.mCBXAxisUnit.currentText()

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
        self.mCurrentPosition = (x, y)
        pass




class SpectralLibraryPlotWidget(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    def __init__(self, parent=None):
        super(SpectralLibraryPlotWidget, self).__init__(parent)

        self.mMaxProfiles = 64

        self.mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=self.mViewBox
        )
        self.mViewBox.sbMaxProfiles.setValue(self.mMaxProfiles)
        self.mViewBox.sigColorSchemeChanged.connect(self.setColorScheme)
        self.mViewBox.sigMaxNumberOfProfilesChanged.connect(self.setMaxProfiles)
        self.mDualView = None

        self.centralWidget.setParent(None)
        self.centralWidget = None
        self.setCentralWidget(plotItem)
        self.plotItem:SpectralLibraryPlotItem
        self.plotItem = plotItem
        for m in ['addItem', 'removeItem', 'autoRange', 'clear', 'setXRange',
                  'setYRange', 'setRange', 'setAspectLocked', 'setMouseEnabled',
                  'setXLink', 'setYLink', 'enableAutoRange', 'disableAutoRange',
                  'setLimits', 'register', 'unregister', 'viewRect']:
            setattr(self, m, getattr(self.plotItem, m))
        # QtCore.QObject.connect(self.plotItem, QtCore.SIGNAL('viewChanged'), self.viewChanged)
        self.plotItem.sigRangeChanged.connect(self.viewRangeChanged)

        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem) and pi == plotItem and pi == self.plotItem
        #pi.disableAutoRange()


        self.mSpeclib:SpectralLibrary
        self.mSpeclib = None
        self.mSpeclibSignalConnections = []


        self.mXUnitInitialized = False
        self.mXUnit = BAND_INDEX
        self.mYUnit = None


        # describe function to convert length units from unit a to unit b
        self.mLUT_UnitConversions = dict()
        returnNone = lambda v, *args: None
        returnSame = lambda v, *args: v
        self.mLUT_UnitConversions[(None, None)] = returnSame
        keys = list(METRIC_EXPONENTS.keys())
        exponents = list(METRIC_EXPONENTS.values())

        for key in keys:
            self.mLUT_UnitConversions[(None, key)] = returnNone
            self.mLUT_UnitConversions[(key, None)] = returnNone
            self.mLUT_UnitConversions[(key, key)] = returnSame

        for i, key1 in enumerate(keys[0:]):
            e1 = exponents[i]
            for key2 in keys[i + 1:]:
                e2 = exponents[keys.index(key2)]
                if e1 == e2:
                    self.mLUT_UnitConversions[(key1, key2)] = returnSame

        self.mViewBox.sigXUnitChanged.connect(self.setXUnit)

        self.mPlotDataItems = dict()
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mPlotOverlayItems = []

        self.mLastFIDs = []
        self.mNeedsPlotUpdate = False

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)


        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)


        # set default axis unit
        self.setXLabel(self.mViewBox.xAxisUnit())
        self.setYLabel('Y (Spectral Value)')

        self.mViewBox.sigXUnitChanged.connect(self.updateXUnit)
        self.mSPECIFIC_PROFILE_STYLES = dict()
        self.mDefaultColorScheme:SpectralLibraryPlotColorScheme
        self.mDefaultColorScheme = SpectralLibraryPlotColorScheme.default()
        self.mColorScheme:SpectralLibraryPlotColorScheme
        self.mColorScheme = SpectralLibraryPlotColorScheme.fromUserSettings()
        self.setColorScheme(self.mColorScheme)

        self.mUpdateTimer = QTimer()
        self.mUpdateTimeIsBlocked = False
        self.mUpdateTimerInterval = 500
        self.mUpdateTimer.timeout.connect(self.onPlotUpdateTimeOut)


    def viewBox(self)->SpectralViewBox:
        return self.mViewBox

    def setColorScheme(self, colorScheme:SpectralLibraryPlotColorScheme):
        """Sets and applies the SpectralProfilePlotColorScheme"""
        assert isinstance(colorScheme, SpectralLibraryPlotColorScheme)
        old = self.colorScheme()
        self.mColorScheme = colorScheme

        # set Background color
        if old.bg != colorScheme.bg:
            self.setBackground(colorScheme.bg)

        # set Foreground color
        if old.fg != colorScheme.fg:
            for axis in self.plotItem.axes.values():
                ai = axis['item']
                if isinstance(ai, pg.AxisItem):
                    ai.setPen(colorScheme.fg)

                    # set info color
                    self.mInfoLabelCursor.setColor(colorScheme.ic)
                    self.mCrosshairLineH.pen.setColor(colorScheme.ic)
                    self.mCrosshairLineV.pen.setColor(colorScheme.ic)

        # set Info Color
        if old.ic != colorScheme.ic:
            self.mInfoLabelCursor.setColor(colorScheme.ic)
            self.mCrosshairLineH.pen.setColor(colorScheme.ic)
            self.mCrosshairLineV.pen.setColor(colorScheme.ic)

        # update profile colors
        if old.ps != colorScheme.ps or old.cs != colorScheme.cs or old.useRendererColors != colorScheme.useRendererColors:
            self.updateProfileStyles()

        # update viewbox context menu and
        self.viewBox().setColorScheme(self.mColorScheme)
        self.mColorScheme.saveToUserSettings()




    def colorScheme(self)->SpectralLibraryPlotColorScheme:
        """
        Returns the used SpectralProfileColorScheme
        :return:
        :rtype:
        """
        return self.mColorScheme.clone()

    def onPlotUpdateTimeOut(self, *args):



        try:

            if not self.mUpdateTimeIsBlocked:
                self.mUpdateTimeIsBlocked = True
                self.updateSpectralProfilePlotItems()
                self.mUpdateTimeIsBlocked = False
            else:
                s =""
        except RuntimeError as ex:
            print(ex, file=sys.stderr)
            self.mUpdateTimeIsBlocked = False
        finally:

            # adapt changes to update interval
            if self.mUpdateTimer.interval() != self.mUpdateTimerInterval:
                self.mUpdateTimer.setInterval(self.mUpdateTimerInterval)
                self.mUpdateTimer.start()

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

    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, SpectralLibraryPlotItem)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            vb = plotItem.vb
            assert isinstance(vb, SpectralViewBox)
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()

            # todo: add infos about plot data below mouse, e.g. profile band number
            rect = QRectF(pos.x() - 2, pos.y() - 2, 5, 5)
            itemsBelow = plotItem.scene().items(rect)
            if SpectralProfilePlotDataItem in itemsBelow:
                s = ""


            vb.updateCurrentPosition(x, y)
            self.mInfoLabelCursor.setText('x:{:0.5f}\ny:{:0.5f}'.format(x, y))

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
            self.mCrosshairLineH.setVisible(False)
            self.mCrosshairLineV.setVisible(False)
            self.mInfoLabelCursor.setVisible(False)


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

            if xUnit is not None:
                self.setXUnit(xUnit)
                self.mXUnitInitialized = True

    def spectralProfilePlotDataItems(self) -> typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItems
        """
        return [i for i in self.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)]

    def _removeSpectralProfilePDIs(self, fidsToRemove: typing.List[int]):
        """

        :param fidsToRemove: feature ids to remove
        :type fidsToRemove:
        :return:
        :rtype:
        """

        def disconnect(sig, slot):
            while True:
                try:
                    r = sig.disconnect(slot)
                    s = ""
                except:
                    break

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, pg.PlotItem)
        pdisToRemove = [pdi for pdi in self.spectralProfilePlotDataItems() if pdi.id() in fidsToRemove]
        for pdi in pdisToRemove:
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pdi.setClickable(False)
            disconnect(pdi, self.onProfileClicked)
            plotItem.removeItem(pdi)
            #QtGui.QGraphicsScene.items(self, *args)
            assert pdi not in plotItem.dataItems
            if pdi.id() in self.mPlotDataItems.keys():
                self.mPlotDataItems.pop(pdi.id(), None)
                self.mSPECIFIC_PROFILE_STYLES.pop(pdi.id(), None)
        self.scene().update()
        s = ""


    def resetProfileStyles(self):
        """
        Resets the profile colors
        """
        self.mSPECIFIC_PROFILE_STYLES.clear()

    def setProfileStyle(self, style:PlotStyle, fids:typing.List[int]):
        """
        Sets the specific profile style
        :param style:
        :type style:
        :param fids:
        :type fids:
        :return:
        :rtype:
        """
        if isinstance(fids, list):
            if isinstance(style, PlotStyle):
                for fid in fids:
                    self.mSPECIFIC_PROFILE_STYLES[fid] = style
            elif style is None:
                # delete existing
                for fid in fids:
                    self.mSPECIFIC_PROFILE_STYLES.pop(fid, None)
            self.updateProfileStyles(fids)

    def setMaxProfiles(self, n:int):
        """
        Sets the maximum number of profiles.
        :param n: maximum number of profiles visualized
        :type n: int
        """
        assert n > 0

        self.mMaxProfiles = n
        self.mViewBox.sbMaxProfiles.setValue(self.mMaxProfiles)

    def setSpeclib(self, speclib: SpectralLibrary):
        """
        Sets the SpectralLibrary to be visualized
        :param speclib: SpectralLibrary
        """
        assert isinstance(speclib, SpectralLibrary)
        self.mUpdateTimer.stop()
        # remove old spectra
        if isinstance(self.speclib(), SpectralLibrary):
            self._removeSpectralProfilePDIs(self.speclib().allFeatureIds())
        self.mSpeclib = speclib
        self.connectSpeclibSignals()
        self.mUpdateTimer.start(self.mUpdateTimerInterval)


    def setDualView(self, dualView:QgsDualView):
        assert isinstance(dualView, QgsDualView)
        speclib = dualView.masterModel().layer()
        assert isinstance(speclib, SpectralLibrary)
        self.mDualView = dualView
        if self.speclib() != speclib:
            self.setSpeclib(speclib)


    def dualView(self)->QgsDualView:
        return self.mDualView

    def connectSpeclibSignals(self):
        """

        """
        if isinstance(self.mSpeclib, SpectralLibrary):

            #self.mSpeclib.featureAdded.connect(self.onProfilesAdded)
            #self.mSpeclib.featuresDeleted.connect(self.onProfilesRemoved)
            self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
            self.mSpeclib.committedAttributeValuesChanges.connect(self.onCommittedAttributeValuesChanges)
            self.mSpeclib.rendererChanged.connect(self.onRendererChanged)


    def disconnectSpeclibSignals(self):
        """
        Savely disconnects all signals from the linked SpectralLibrary
        """
        if isinstance(self.mSpeclib, SpectralLibrary):
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
            disconnect(self.mSpeclib.rendererChanged, self.onRendererChanged)

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

        idxF = self.speclib().fields().indexOf(FIELD_VALUES)
        fids = []

        for fid, fieldMap in featureMap.items():
            if idxF in fieldMap.keys():
                fids.append(fid)

        if len(fids) == 0:
            return
        for p in self.speclib().profiles(fids):
            assert isinstance(p, SpectralProfile)
            pdi = self.spectralProfilePlotDataItem(p.id())
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pdi.resetSpectralProfile(p)

    @pyqtSlot()
    def onRendererChanged(self):
        """
        Updates all SpectralProfilePlotDataItems
        """
        self.updateProfileStyles()


    def onSelectionChanged(self, selected, deselected, clearAndSelect):
        self.updateSpectralProfilePlotItems()
        for pdi in self.allSpectralProfilePlotDataItems():
            if pdi.id() in selected:
                pdi.setSelected(True)
            elif pdi.id() in deselected:
                pdi.setSelected(False)

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
        if isinstance(unitSrc, str):
            unitSrc = unitSrc.lower()
        if isinstance(unitDst, str):
            unitDst = unitDst.lower()

        key = (unitSrc, unitDst)
        func = self.mLUT_UnitConversions.get(key)
        if callable(func):
            return func
        else:
            if isinstance(unitSrc, str) and isinstance(unitDst, str) and convertMetricUnit(1, unitSrc,
                                                                                           unitDst) is not None:
                func = lambda values, pdi, a=unitSrc, b=unitDst: convertMetricUnit(values, a, b)
            else:
                func = lambda values, pdi: None

            self.mLUT_UnitConversions[key] = func

            return self.mLUT_UnitConversions[key]

    def setXUnit(self, unit: str):
        """
        Sets the unit or mapping function to be shown on x-axis.
        :param unit: str, e.g. `nanometers`
        """

        if self.mXUnit != unit:
            self.mViewBox.setXAxisUnit(unit)
            self.mXUnit = unit
            self.updateXUnit()

            self.getPlotItem().update()

    def xUnit(self) -> str:
        """
        Returns the unit to be shown on x-axis
        :return: str
        """
        return self.mXUnit

    def allPlotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns all PlotDataItems (not only SpectralProfilePlotDataItems)
        :return: [list-of-PlotDataItems]
        """
        return list(self.mPlotDataItems.values()) + self.mPlotOverlayItems

    def allSpectralProfilePlotDataItems(self)->typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItem, including those used as temporary overlays.
        :return: [list-of-SpectralProfilePlotDataItem]
        """
        return [pdi for pdi in self.allPlotDataItems() if isinstance(pdi, SpectralProfilePlotDataItem)]

    def updateXUnit(self):
        unit = self.xUnit()

        # update axis label
        self.setXLabel(unit)

        # update x values
        pdis = self.allSpectralProfilePlotDataItems()
        if unit == BAND_INDEX:
            func = lambda x, *args: list(range(len(x)))
            for pdi in pdis:
                pdi.setMapFunctionX(func)
                pdi.applyMapFunctions()
        else:
            for pdi in pdis:
                pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, unit))
                pdi.applyMapFunctions()

        s = ""

    def updateSpectralProfilePlotItems(self):
        """

        """

        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem)

        toBeVisualized = self.profileIDsToVisualize()
        visualized = self.plottedProfileIDs()
        toBeRemoved = [fid for fid in visualized if fid not in toBeVisualized]
        toBeAdded = [fid for fid in toBeVisualized if fid not in visualized]

        if len(toBeRemoved) > 0:
            self._removeSpectralProfilePDIs(toBeRemoved)

        if len(toBeAdded) > 0:
            addedPDIs = []
            addedProfiles = self.speclib().profiles(toBeAdded)

            defaultPlotStyle = self.mColorScheme.ps
            for profile in addedProfiles:
                assert isinstance(profile, SpectralProfile)
                pdi = SpectralProfilePlotDataItem(profile)
                defaultPlotStyle.apply(pdi)
                pdi.setClickable(True)
                pdi.setVisible(True)
                pdi.sigClicked.connect(self.onProfileClicked)
                self.mPlotDataItems[profile.id()] = pdi
                addedPDIs.append(pdi)
            pi.addItems(addedPDIs)
            self.updateProfileStyles(toBeAdded)
            s = ""

        if len(toBeAdded) > 0 or len(toBeRemoved) > 0:
            pi.update()


    def resetSpectralProfiles(self):
        for pdi in self.spectralProfilePlotDataItems():
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pdi.resetSpectralProfile()


    def spectralProfilePlotDataItem(self, fid:typing.Union[int, QgsFeature, SpectralProfile]) -> SpectralProfilePlotDataItem:
        """
        Returns the SpectralProfilePlotDataItem related to SpectralProfile fid
        :param fid: int | QgsFeature | SpectralProfile
        :return: SpectralProfilePlotDataItem
        """
        if isinstance(fid, QgsFeature):
            fid = fid.id()
        return self.mPlotDataItems.get(fid)

    def updateProfileStyles(self, fids: typing.List[SpectralProfile]=None):
        """
        Updates the styles for a set of SpectralProfilePlotDataItems
        :param listOfProfiles: [list-of-SpectralProfiles]
        """

        if not isinstance(self.speclib(), SpectralLibrary):
            return

        cs = self.mColorScheme

        xUnit = None
        renderContext = QgsRenderContext()
        renderContext.setExtent(self.speclib().extent())
        renderer = self.speclib().renderer().clone()



        pdis = self.spectralProfilePlotDataItems()

        # update requested FIDs only
        if isinstance(fids, list):
            pdis = [pdi for pdi in pdis if pdi.id() in fids]

        # update X Axis unit
        if not self.mXUnitInitialized:
            for pdi in pdis:
                profile = pdi.spectralProfile()
                if profile.xUnit() in X_UNITS:
                    self.setXUnit(profile.xUnit())
                    break

        # update line colors
        if not cs.useRendererColors or isinstance(renderer, QgsNullSymbolRenderer):
            for pdi in pdis:
                style = self.mSPECIFIC_PROFILE_STYLES.get(pdi.id(), cs.ps)
                style.apply(pdi)
        else:
            renderer.startRender(renderContext, self.speclib().fields())
            for pdi in pdis:
                profile = pdi.spectralProfile()

                style = self.mSPECIFIC_PROFILE_STYLES.get(pdi.id(), None)

                if not isinstance(style, PlotStyle):
                    style = cs.ps.clone()
                    symbol = renderer.symbolForFeature(profile, renderContext)
                    if not isinstance(symbol, QgsSymbol):
                        symbol = renderer.sourceSymbol()
                    assert isinstance(symbol, QgsSymbol)
                    if isinstance(symbol, (QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol)):
                        style.setLineColor(symbol.color())
                style.apply(pdi)

            renderer.stopRender(renderContext)

        if isinstance(xUnit, str):
            self.setXUnit(xUnit)
            self.mXUnitInitialized = True

    def onProfileClicked(self, pdi):

        if isinstance(pdi, SpectralProfilePlotDataItem) and pdi in self.mPlotDataItems.values():
            modifiers = QApplication.keyboardModifiers()
            speclib = self.speclib()
            assert isinstance(speclib, SpectralLibrary)
            fid = pdi.id()

            fids = speclib.selectedFeatureIds()
            if modifiers == Qt.ShiftModifier:
                if fid in fids:
                    fids.remove(fid)
                else:
                    fids.append(fid)
                speclib.selectByIds(fids)
            else:
                speclib.selectByIds([fid])

    def setXLabel(self, label: str):
        """
        Sets the name of the X axis
        :param label: str, name
        """
        pi = self.getPlotItem()
        pi.getAxis('bottom').setLabel(label)

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

    def plottedProfileCount(self)->int:
        """
        Returns the number of plotted profiles
        :return: int
        :rtype: int
        """
        return len(self.allSpectralProfilePlotDataItems())

    def plottedProfileIDs(self)->typing.List[int]:
        """
        Returns the feature IDs of all visualized SpectralProfiles.
        """
        return [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

    def profileIDsToVisualize(self)->typing.List[int]:
        """
        Returns the list of profile/feature ids to be visualized.
        The maximum number is determined by self.mMaxProfiles
        Order of returned fids is equal to its importance. 1st postion = most important
        """
        nMax = len(self.speclib())

        allIDs = self.speclib().allFeatureIds()
        if nMax <= self.mMaxProfiles:
            return allIDs

        # Order:
        # 1. visible in table
        # 2. selected
        # 3. others



        vis = self.plottedProfileIDs()
        dualView = self.dualView()

        priority1 = []
        if isinstance(dualView, QgsDualView):
            tv = dualView.tableView()
            assert isinstance(tv, QTableView)
            rowHeight = tv.rowViewportPosition(1) - tv.rowViewportPosition(0)
            for y in range(0, tv.viewport().height(), rowHeight):
                idx = dualView.tableView().indexAt(QPoint(0, y))
                if idx.isValid():
                    fid = tv.model().data(idx, role=Qt.UserRole)
                    priority1.append(fid)
            priority2 = self.dualView().masterModel().layer().selectedFeatureIds()
            priority3 = dualView.filteredFeatures()
        else:
            priority2 = self.speclib().selectedFeatureIds()
            priority3 = self.speclib().allFeatureIds()

        #featurePool = priority3
        featurePool = priority1+priority2
        toVisualize = sorted(featurePool, key=lambda fid : (fid not in priority1, fid not in priority2, fid))

        if len(toVisualize) >= self.mMaxProfiles:
            return sorted(toVisualize[0:self.mMaxProfiles])
        else:
            toVisualize = sorted(toVisualize)
            nMissing = min(self.mMaxProfiles - len(toVisualize), len(priority3))
            if nMissing > 0:
                toVisualize += sorted(priority3[0:nMissing])
            return toVisualize



    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if MIMEDATA_SPECLIB_LINK in event.mimeData().formats():
            event.accept()

    def dragMoveEvent(self, event):
        if MIMEDATA_SPECLIB_LINK in event.mimeData().formats():
            event.accept()

