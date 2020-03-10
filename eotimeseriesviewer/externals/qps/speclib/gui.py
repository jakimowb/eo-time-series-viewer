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
from .core import *
from ..speclib import SpectralLibrarySettingsKey
from ..externals.pyqtgraph import PlotItem, PlotWindow
from ..externals.pyqtgraph.functions import mkPen
from ..externals import pyqtgraph as pg
from ..externals.pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem

from ..models import Option, OptionListModel
from ..plotstyling.plotstyling import PlotStyleWidget, PlotStyle
from ..layerproperties import AddAttributeDialog

BAND_INDEX = 'Band Index'
SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None

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
            scheme.profileStyle = PlotStyle.fromJSON(settings.value(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name))
        if SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name in settings.allKeys():
            scheme.temporaryProfileStyle = PlotStyle.fromJSON(settings.value(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name))

        scheme.backgroundColor = settings.value(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, scheme.backgroundColor)
        scheme.foregroundColor = settings.value(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, scheme.foregroundColor)
        scheme.infoColor = settings.value(SpectralLibrarySettingsKey.INFO_COLOR.name, scheme.infoColor)
        scheme.useRendererColors = settings.value(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, scheme.useRendererColors) in ['True', 'true', True]

        return scheme


    @staticmethod
    def dark():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('white')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotColorScheme(
            name='Dark',
            fg=QColor('white'),
            bg=QColor('black'),
            ic=QColor('yellow'),
            sc=QColor('yellow'),
            ps=ps, cs=cs, useRendererColors=False)

    @staticmethod
    def bright():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('black')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotColorScheme(
            name='Bright',
            fg=QColor('black'),
            bg=QColor('white'),
            ic=QColor('red'),
            sc=QColor('red'),
            ps=ps, cs=cs, useRendererColors=False)

    def __init__(self, name:str='color_scheme',
                 fg: QColor = QColor('white'),
                 bg: QColor = QColor('black'),
                 ps: PlotStyle = None,
                 cs: PlotStyle = None,
                 ic: QColor = QColor('yellow'),
                 sc: QColor = QColor('yellow'),
                 useRendererColors:bool=True):
        """
        :param name: name of color scheme
        :type name: str
        :param fg: foreground color
        :type fg: QColor
        :param bg: background color
        :type bg: QColor
        :param ps: default profile style
        :type ps: PlotStyle
        :param cs: current profile style, i.e. selected profiles
        :type cs: PlotStyle
        :param ic: info color, color of additional information, like crosshair and cursor location
        :type ic: QColor
        :param useRendererColors: if true (default), use colors from the QgsVectorRenderer to colorize plot lines
        :type useRendererColors: bool
        """

        if ps is None:
            ps = defaultCurvePlotStyle()

        if cs is None:
            cs = defaultCurvePlotStyle()
            cs.setLineColor('green')


        self.name: str
        self.name = name

        self.foregroundColor: QColor
        self.foregroundColor = fg

        self.backgroundColor: QColor
        self.backgroundColor = bg

        self.profileStyle: PlotStyle
        self.profileStyle = ps

        self.temporaryProfileStyle: PlotStyle
        self.temporaryProfileStyle = cs

        self.infoColor: QColor
        self.infoColor = ic

        self.selectionColor : QColor
        self.selectionColor = sc
        self.useRendererColors: bool
        self.useRendererColors = useRendererColors

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

        settings.setValue(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name, self.profileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name, self.temporaryProfileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, self.backgroundColor)
        settings.setValue(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, self.foregroundColor)
        settings.setValue(SpectralLibrarySettingsKey.INFO_COLOR.name, self.infoColor)
        settings.setValue(SpectralLibrarySettingsKey.SELECTION_COLOR.name, self.selectionColor)
        settings.setValue(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, self.useRendererColors)


    def __eq__(self, other):
        if not isinstance(other, SpectralLibraryPlotColorScheme):
            return False
        else:

            return self.backgroundColor == other.backgroundColor and \
                   self.foregroundColor == other.foregroundColor and \
                   self.infoColor == other.infoColor and \
                   self.selectionColor == other.selectionColor and \
                   self.profileStyle == other.profileStyle and \
                   self.temporaryProfileStyle == other.temporaryProfileStyle and \
                   self.useRendererColors == other.useRendererColors

class SpectralLibraryPlotColorSchemeWidget(QWidget):

    sigColorSchemeChanged = pyqtSignal(SpectralLibraryPlotColorScheme)

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotColorSchemeWidget, self).__init__(*args, **kwds)
        path_ui = speclibUiPath('spectrallibraryplotcolorschemewidget.ui')
        loadUi(path_ui, self)

        self.mBlocked = False

        self.mLastColorScheme: SpectralLibraryPlotColorScheme
        self.mLastColorScheme = None


        self.btnColorBackground.colorChanged.connect(self.onColorSchemeChanged)
        self.btnColorForeground.colorChanged.connect(self.onColorSchemeChanged)
        self.btnColorInfo.colorChanged.connect(self.onColorSchemeChanged)
        self.btnColorSelection.colorChanged.connect(self.onColorSchemeChanged)
        self.cbUseRendererColors.clicked.connect(self.onCbUseRendererColorsClicked)

        self.wDefaultProfileStyle.setPreviewVisible(False)
        self.wDefaultProfileStyle.cbIsVisible.setVisible(False)
        self.wDefaultProfileStyle.sigPlotStyleChanged.connect(self.onColorSchemeChanged)
        self.wDefaultProfileStyle.setMinimumSize(self.wDefaultProfileStyle.sizeHint())
        self.btnReset.setDisabled(True)
        self.btnReset.clicked.connect(lambda : self.setColorScheme(self.mLastColorScheme))
        self.btnColorSchemeBright.clicked.connect(lambda : self.setColorScheme(SpectralLibraryPlotColorScheme.bright()))
        self.btnColorSchemeDark.clicked.connect(lambda: self.setColorScheme(SpectralLibraryPlotColorScheme.dark()))

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

        self.btnColorBackground.setColor(colorScheme.backgroundColor)
        self.btnColorForeground.setColor(colorScheme.foregroundColor)
        self.btnColorInfo.setColor(colorScheme.infoColor)
        self.btnColorSelection.setColor(colorScheme.selectionColor)
        self.wDefaultProfileStyle.setPlotStyle(colorScheme.profileStyle)
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
        cs.backgroundColor = self.btnColorBackground.color()
        cs.foregroundColor = self.btnColorForeground.color()
        cs.infoColor = self.btnColorInfo.color()
        cs.selectionColor = self.btnColorSelection.color()
        cs.profileStyle = self.wDefaultProfileStyle.plotStyle()
        if isinstance(self.mLastColorScheme, SpectralLibraryPlotColorScheme):
            cs.temporaryProfileStyle = self.mLastColorScheme.temporaryProfileStyle.clone()
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


        self.mProfile: SpectralProfile
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
                if isinstance(x, list) and isinstance(y, list) and len(x) > 0 and len(y) > 0:
                    success = True
            except Exception as ex:
                print(ex)
                pass

        if success:
            if True:
                # handle failed removal of NaN
                # see https://github.com/pyqtgraph/pyqtgraph/issues/1057
                if not isinstance(y, np.ndarray):
                    y = np.asarray(y, dtype=np.float)
                if not isinstance(x, np.ndarray):
                    x = np.asarray(x)

                is_finite = np.isfinite(y)
                connected = np.logical_and(is_finite, np.roll(is_finite, -1))
                keep = is_finite + connected
                #y[np.logical_not(is_finite)] = np.nanmin(y)
                y = y[keep]
                x = x[keep]
                connected = connected[keep]
                self.setData(x=x, y=y, connect=connected)
            else:
                self.setData(x=x, y=y, connect='finite')
            self.setVisible(True)
        else:
            # self.setData(x=[], y=[])
            self.setVisible(False)

        return success

    def plot(self)->PlotWindow:
        """
        Opens a PlotWindow and plots this SpectralProfilePlotDataItem to
        :return:
        :rtype:
        """
        pw = pg.plot(title=self.name())
        pw.getPlotItem().addItem(self)
        return pw

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

    def depr_setSelected(self, b: bool):
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

    def depr_setPlotStyle(self, plotStyle:PlotStyle, updateItem=True):
        """
        Applies a PlotStyle to this SpectralProfilePlotDataItem
        :param plotStyle:
        :type plotStyle:
        :param updateItem: set True (default) to apply changes immediately.
        :type updateItem: bool
        """
        assert isinstance(plotStyle, PlotStyle)
        plotStyle.apply(self, updateItem=updateItem)

    def depr_plotStyle(self)->PlotStyle:
        """
        Returns the SpectralProfilePlotDataItems' PlotStyle
        :return: PlotStyle
        :rtype: PlotStyle
        """
        return PlotStyle.fromPlotDataItem(self)

    def depr_setColor(self, color: QColor):
        """
        Sets the profile line + marker color
        :param color: QColor
        """
        if not isinstance(color, QColor):
            color = QColor(color)

        self.lineWidth()
        style = self.profileStyle()
        style.linePen.setColor(color)
        self.setProfileStyle(style)

    def depr_pen(self) -> QPen:
        """
        Returns the QPen of the profile
        :return: QPen
        """
        return mkPen(self.opts['pen'])

    def depr_color(self) -> QColor:
        """
        Returns the profile plotStyle
        :return: QColor
        """
        return self.pen().color()

    def depr_setLineWidth(self, width:int):
        """
        Set the profile width in px
        :param width: int
        """
        pen = mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)

    def depr_lineWidth(self)->int:
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
        self.mActionShowSelectedProfilesOnly = menuProfiles.addAction('Selected Only')
        self.mActionShowSelectedProfilesOnly.setCheckable(True)

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
        self.mSelectedIds = set()
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
        self.plotItem: SpectralLibraryPlotItem
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
        self.mDefaultColorScheme: SpectralLibraryPlotColorScheme
        self.mDefaultColorScheme = SpectralLibraryPlotColorScheme.default()
        self.mColorScheme: SpectralLibraryPlotColorScheme
        self.mColorScheme = SpectralLibraryPlotColorScheme.fromUserSettings()
        self.setColorScheme(self.mColorScheme)

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.setInterval(500)
        self.mUpdateTimer.setSingleShot(False)
        self.mUpdateTimer.timeout.connect(self.onPlotUpdateTimeOut)
        self.mUpdateTimer.start()

    def setUpdateInterval(self, msec:int):
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


    def viewBox(self)->SpectralViewBox:
        return self.mViewBox

    def setColorScheme(self, colorScheme:SpectralLibraryPlotColorScheme):
        """Sets and applies the SpectralProfilePlotColorScheme"""
        assert isinstance(colorScheme, SpectralLibraryPlotColorScheme)
        old = self.colorScheme()
        self.mColorScheme = colorScheme

        # set Background color
        if old.backgroundColor != colorScheme.backgroundColor:
            self.setBackground(colorScheme.backgroundColor)

        # set Foreground color
        if old.foregroundColor != colorScheme.foregroundColor:
            for axis in self.plotItem.axes.values():
                ai = axis['item']
                if isinstance(ai, pg.AxisItem):
                    ai.setPen(colorScheme.foregroundColor)

                    # set info color
                    self.mInfoLabelCursor.setColor(colorScheme.infoColor)
                    self.mCrosshairLineH.pen.setColor(colorScheme.infoColor)
                    self.mCrosshairLineV.pen.setColor(colorScheme.infoColor)

        # set Info Color
        if old.infoColor != colorScheme.infoColor:
            self.mInfoLabelCursor.setColor(colorScheme.infoColor)
            self.mCrosshairLineH.pen.setColor(colorScheme.infoColor)
            self.mCrosshairLineV.pen.setColor(colorScheme.infoColor)

        # update profile colors
        if old.profileStyle != colorScheme.profileStyle or \
                old.temporaryProfileStyle != colorScheme.temporaryProfileStyle or \
                old.useRendererColors != colorScheme.useRendererColors:
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

    def removeSpectralProfilePDIs(self, fidsToRemove: typing.List[int], updateScene=True):
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

        # remove fid from profile styles
        for fid in fidsToRemove:
            self.mSPECIFIC_PROFILE_STYLES.pop(fid, None)

        if updateScene:
            self.scene().update()
        s = ""


    def resetProfileStyles(self):
        """
        Resets the profile colors
        """
        self.mSPECIFIC_PROFILE_STYLES.clear()

    def setProfileStyles(self, styles:typing.List[typing.Tuple[PlotStyle, typing.List[int]]]):
        """
        Sets the styles of features
        :param style: list of (PlotStyle, [feature ids])
        :type style:
        :param fids:
        :type fids:
        :return:
        :rtype:
        """
        if styles is None:
            return
        updatedFIDs = []
        for style, fids  in styles:
            if isinstance(fids, (list, set)):
                if isinstance(style, PlotStyle):
                    for fid in fids:
                        self.mSPECIFIC_PROFILE_STYLES[fid] = style
                elif style is None:
                    # delete existing
                    for fid in fids:
                        self.mSPECIFIC_PROFILE_STYLES.pop(fid, None)
                updatedFIDs.extend(fids)
        self.updateProfileStyles(updatedFIDs)

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
        if speclib == self.speclib():
            return
        self.mUpdateTimer.stop()

        # remove old spectra
        self.removeSpectralProfilePDIs(self.mPlotDataItems.keys())
        self.mSpeclib = None

        if isinstance(speclib, SpectralLibrary):
            self.mSpeclib = speclib
            self.connectSpeclibSignals()


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
            self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
            self.mSpeclib.committedAttributeValuesChanges.connect(self.onCommittedAttributeValuesChanges)
            self.mSpeclib.rendererChanged.connect(self.onRendererChanged)
            #additional security to disconnect
            self.mSpeclib.willBeDeleted.connect(lambda: self.setSpeclib(None))


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

        #fidsBefore = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

        self.updateSpectralProfilePlotItems()

        #fidsAfter = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]




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

    FUNC_BAND_INDEX = lambda x, *args: list(range(len(x)))

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

        if unitDst == BAND_INDEX.lower():
            return SpectralLibraryPlotWidget.FUNC_BAND_INDEX

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

            #self.getPlotItem().update()

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
        for pdi in pdis:
            pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, unit))

            pdi.applyMapFunctions()

        s = ""

    def updateSpectralProfilePlotItems(self):
        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem)

        toBeVisualized = self.profileIDsToVisualize()
        visualized = self.plottedProfileIDs()
        toBeRemoved = [fid for fid in visualized if fid not in toBeVisualized]
        toBeAdded = [fid for fid in toBeVisualized if fid not in visualized]

        selectedNow = set(self.speclib().selectedFeatureIds())
        selectionChanged = list(selectedNow.symmetric_difference(self.mSelectedIds))
        self.mSelectedIds = selectedNow

        if len(toBeRemoved) > 0:
            self.removeSpectralProfilePDIs(toBeRemoved)

        if len(toBeAdded) > 0:
            addedPDIs = []
            addedProfiles = self.speclib().profiles(toBeAdded)
            for profile in addedProfiles:
                assert isinstance(profile, SpectralProfile)
                pdi = SpectralProfilePlotDataItem(profile)
                pdi.setClickable(True)
                pdi.setVisible(True)
                pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, self.xUnit()))
                pdi.applyMapFunctions()
                pdi.sigClicked.connect(self.onProfileClicked)
                self.mPlotDataItems[profile.id()] = pdi
                addedPDIs.append(pdi)
            pi.addItems(addedPDIs)

        update_styles = list(set(toBeAdded + selectionChanged))
        if len(update_styles) > 0:
            self.updateProfileStyles(update_styles)

        if len(toBeAdded + toBeRemoved + selectionChanged) > 0:
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

    def updateProfileStyles(self, fids: typing.List[int] = None):
        """
        Updates the styles for a set of SpectralProfilePlotDataItems specified by its feature ids
        :param listOfProfiles: [list-of-SpectralProfiles IDs]
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
                fid = pdi.id()
                style = self.mSPECIFIC_PROFILE_STYLES.get(fid, cs.profileStyle)
                style.apply(pdi, updateItem=False)
        else:
            renderer.startRender(renderContext, self.speclib().fields())
            for pdi in pdis:
                profile = pdi.spectralProfile()

                style = self.mSPECIFIC_PROFILE_STYLES.get(pdi.id(), None)
                # now explicit style give. derive from qgis renderer
                if not isinstance(style, PlotStyle):
                    style = cs.profileStyle.clone()
                    symbol = renderer.symbolForFeature(profile, renderContext)
                    if not isinstance(symbol, QgsSymbol):
                        symbol = renderer.sourceSymbol()
                    assert isinstance(symbol, QgsSymbol)
                    if isinstance(symbol, (QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol)):
                        style.setLineColor(symbol.color())
                style.apply(pdi, updateItem=False)

            renderer.stopRender(renderContext)

        # update selection color
        sc = self.colorScheme().selectionColor
        for pdi in [pdi for pdi in pdis if pdi.id() in self.speclib().selectedFeatureIds()]:
            line_increase = 2
            linePen = QPen(pdi.opts['pen'])
            linePen.setColor(sc)
            linePen.setWidth(linePen.width() + line_increase)
            pdi.opts['pen'] = linePen
            pdi.opts['symbolPen'].setColor(sc)
            pdi.opts['symbolBrush'].setColor(sc)
            pdi.opts['symbolSize'] = pdi.opts['symbolSize'] + line_increase
        for pdi in [pdi for pdi in pdis if pdi.id() not in self.speclib().selectedFeatureIds()]:
            s = ""

        # finally, update items
        for pdi in pdis:
            pdi.updateItems()

        if isinstance(xUnit, str):
            self.setXUnit(xUnit)
            self.mXUnitInitialized = True

    def onProfileClicked(self, pdi: SpectralProfilePlotDataItem):
        """
        Slot to react mouse-click on a SpectralProfilePlotDataItem
        :param pdi: SpectralProfilePlotDataItem
        """
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
        Order of returned fids is equal to its importance.
        1st position = most important, should be plottet on top of all other profiles
        """
        nMax = len(self.speclib())
        selectedOnly = self.viewBox().mActionShowSelectedProfilesOnly.isChecked()
        selectedIds = self.speclib().selectedFeatureIds()

        allIDs = self.speclib().allFeatureIds()
        if nMax <= self.mMaxProfiles:
            if selectedOnly:
                return [fid for fid in allIDs if fid in selectedIds]
            else:
                return allIDs

        # Order:
        # 1. visible in table
        # 2. selected
        # 3. others

        dualView = self.dualView()

        # overlaided features / current spectral
        priority0 = [fid for fid, v in self.mSPECIFIC_PROFILE_STYLES.items() if v == self.colorScheme().temporaryProfileStyle]
        priority1 = [] # visible features
        priority2 = [] # selected features
        priority3 = [] # any other : not visible / not selected

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
        toVisualize = sorted(featurePool, key=lambda fid : (fid not in priority0, fid not in priority1, fid not in priority2, fid))

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


class SpectralProfileValueTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """
    def __init__(self, *args, **kwds):
        super(SpectralProfileValueTableModel, self).__init__(*args, **kwds)

        self.mColumnDataTypes = [float, float]
        self.mColumnDataUnits = ['-', '-']
        self.mValues = EMPTY_PROFILE_VALUES.copy()

    def setProfileData(self, values):
        """
        :param values:
        :return:
        """
        if isinstance(values, SpectralProfile):
            values = values.values()
        assert isinstance(values, dict)

        for k in EMPTY_PROFILE_VALUES.keys():
            assert k in values.keys()

        for i, k in enumerate(['y', 'x']):
            if values[k] and len(values[k]) > 0:
                self.setColumnDataType(i, type(values[k][0]))
            else:
                self.setColumnDataType(i, float)
        self.setColumnValueUnit('y', values.get('yUnit', '') )
        self.setColumnValueUnit('x', values.get('xUnit', ''))

        self.beginResetModel()
        self.mValues.update(values)
        self.endResetModel()

    def values(self)->dict:
        """
        Returns the value dictionary of a SpectralProfile
        :return: dict
        """
        return self.mValues

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        if self.mValues['y'] is None:
            return 0
        else:
            return len(self.mValues['y'])

    def columnCount(self, parent=QModelIndex()):
        return 2

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role in [Qt.DisplayRole, Qt.EditRole]:
            value = None
            if c == 0:
                value = self.mValues['y'][i]

            elif c == 1:
                value = self.mValues['x'][i]

            #log('data: {} {}'.format(type(value), value))
            return value

        if role == Qt.UserRole:
            return self.mValues

        return None

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role == Qt.EditRole:
            #cast to correct data type
            dt = self.mColumnDataTypes[c]
            value = dt(value)

            if c == 0:
                self.mValues['y'][i] = value
                return True
            elif c == 1:
                self.mValues['x'][i] = value
                return True
        return False

    def index2column(self, index)->int:
        """
        Returns a column index
        :param index: QModelIndex, int or str from  ['x','y']
        :return: int
        """
        if isinstance(index, str):
            index = ['y','x'].index(index.strip().lower())
        elif isinstance(index, QModelIndex):
            index = index.column()

        assert isinstance(index, int) and index >= 0
        return index


    def setColumnValueUnit(self, index, valueUnit:str):
        """
        Sets the unit of the value column
        :param index: 'y','x', respective 0, 1
        :param valueUnit: str with unit, e.g. 'Reflectance' or 'um'
        """
        index = self.index2column(index)
        if valueUnit is None:
            valueUnit = '-'

        assert isinstance(valueUnit, str)

        if self.mColumnDataUnits[index] != valueUnit:
            self.mColumnDataUnits[index] = valueUnit
            self.headerDataChanged.emit(Qt.Horizontal, index, index)
            self.sigColumnValueUnitChanged.emit(index, valueUnit)

    sigColumnValueUnitChanged = pyqtSignal(int, str)

    def setColumnDataType(self, index, dataType:type):
        """
        Sets the numeric dataType in which spectral values are returned
        :param index: 'y','x', respective 0, 1
        :param dataType: int or float (default)
        """
        index = self.index2column(index)
        if isinstance(dataType, str):
            i = ['Integer', 'Float'].index(dataType)
            dataType = [int, float][i]

        assert dataType in [int, float]

        if self.mColumnDataTypes[index] != dataType:
            self.mColumnDataTypes[index] = dataType

            if index == 0:
                y = self.mValues.get('y')
                if isinstance(y, list) and len(y) > 0:
                    self.mValues['y'] = [dataType(v) for v  in self.mValues['y']]
            elif index == 1:
                x = self.mValues.get('x')
                if isinstance(x, list) and len(x) > 0:
                    self.mValues['x'] = [dataType(v) for v in self.mValues['x']]

            self.dataChanged.emit(self.createIndex(0, index), self.createIndex(self.rowCount(), index))
            self.sigColumnDataTypeChanged.emit(index, dataType)

    sigColumnDataTypeChanged = pyqtSignal(int, type)

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            if c == 0:
                flags = flags | Qt.ItemIsEditable
            elif c == 1 and self.mValues['xUnit']:
                flags = flags | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            name = ['Y','X'][col]
            unit = self.mColumnDataUnits[col]
            if unit in EMPTY_VALUES:
                unit = '-'
            return '{} [{}]'.format(name, unit)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

class SpectralProfileEditorWidget(QWidget):

    sigProfileValuesChanged = pyqtSignal(dict)
    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget, self).__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralprofileeditorwidget.ui'), self)
        self.mDefault = None
        self.mModel = SpectralProfileValueTableModel(parent=self)
        self.mModel.dataChanged.connect(lambda: self.sigProfileValuesChanged.emit(self.profileValues()))
        self.mModel.sigColumnValueUnitChanged.connect(self.onValueUnitChanged)
        self.mModel.sigColumnDataTypeChanged.connect(self.onDataTypeChanged)

        self.cbYUnit.currentTextChanged.connect(lambda unit: self.mModel.setColumnValueUnit(0, unit))
        self.cbXUnit.currentTextChanged.connect(lambda unit: self.mModel.setColumnValueUnit(1, unit))

        self.cbYUnitDataType.currentTextChanged.connect(lambda v: self.mModel.setColumnDataType(0, v))
        self.cbXUnitDataType.currentTextChanged.connect(lambda v:self.mModel.setColumnDataType(1, v))

        self.actionReset.triggered.connect(self.resetProfileValues)
        self.btnReset.setDefaultAction(self.actionReset)

        self.onDataTypeChanged(0, float)
        self.onDataTypeChanged(1, float)

        self.setProfileValues(EMPTY_PROFILE_VALUES.copy())


    def initConfig(self, conf:dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        if 'xUnitList' in conf.keys():
            self.cbXUnit.addItems(conf['xUnitList'])

        if 'yUnitList' in conf.keys():
            self.cbYUnit.addItems(conf['yUnitList'])


    def onValueUnitChanged(self, index:int, unit:str):
        comboBox = [self.cbYUnit, self.cbXUnit][index]
        setComboboxValue(comboBox, unit)

    def onDataTypeChanged(self, index:int, dataType:type):

        if dataType == int:
            typeString = 'Integer'
        elif dataType == float:
            typeString = 'Float'
        else:
            raise NotImplementedError()
        comboBox = [self.cbYUnitDataType, self.cbXUnitDataType][index]

        setComboboxValue(comboBox, typeString)

    def setProfileValues(self, values):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """

        if isinstance(values, SpectralProfile):
            values = values.values()

        assert isinstance(values, dict)
        import copy
        self.mDefault = copy.deepcopy(values)
        self.mModel.setProfileData(values)


    def resetProfileValues(self):
        self.setProfileValues(self.mDefault)

    def profileValues(self)->dict:
        """
        Returns the value dictionary of a SpectralProfile
        :return: dict
        """
        return self.mModel.values()

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

class SpectralProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget):
        super(SpectralProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mEditorWidget = None
        self.mLabel = None
        self.mDefaultValue = None

    def createWidget(self, parent: QWidget):
        #log('createWidget')
        w = None
        if not self.isInTable(parent):
            w = SpectralProfileEditorWidget(parent=parent)
        else:
            #w = PlotStyleButton(parent)
            w = QWidget(parent)
            w.setVisible(False)
        return w

    def initWidget(self, editor:QWidget):
        #log(' initWidget')
        conf = self.config()


        if isinstance(editor, SpectralProfileEditorWidget):
            self.mEditorWidget = editor
            self.mEditorWidget.sigProfileValuesChanged.connect(self.onValueChanged)
            self.mEditorWidget.initConfig(conf)

        if isinstance(editor, QWidget):
            self.mLabel = editor
            self.mLabel.setVisible(False)
            self.mLabel.setToolTip('Use Form View to edit values')


    def onValueChanged(self, *args):
        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs)->bool:
        return isinstance(self.mEditorWidget, SpectralProfileEditorWidget) or isinstance(self.mLabel, QWidget)

    def value(self, *args, **kwargs):
        value = self.mDefaultValue
        if isinstance(self.mEditorWidget, SpectralProfileEditorWidget):
            v = self.mEditorWidget.profileValues()
            value = encodeProfileValueDict(v)

        return value


    def setEnabled(self, enabled:bool):

        if self.mEditorWidget:
            self.mEditorWidget.setEnabled(enabled)


    def setValue(self, value):
        if isinstance(self.mEditorWidget, SpectralProfileEditorWidget):
            self.mEditorWidget.setProfileValues(decodeProfileValueDict(value))
        self.mDefaultValue = value
        #if isinstance(self.mLabel, QLabel):
        #    self.mLabel.setText(value2str(value))

class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl:QgsVectorLayer, fieldIdx:int, parent:QWidget):

        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        loadUi(speclibUiPath('spectralprofileeditorconfigwidget.ui'), self)

        self.mLastConfig = {}

        self.tbXUnits.textChanged.connect(lambda: self.changed.emit())
        self.tbYUnits.textChanged.connect(lambda: self.changed.emit())

        self.tbResetX.setDefaultAction(self.actionResetX)
        self.tbResetY.setDefaultAction(self.actionResetY)

    def unitTextBox(self, dim:str)->QPlainTextEdit:
        if dim == 'x':
            return self.tbXUnits
        elif dim == 'y':
            return self.tbYUnits
        else:
            raise NotImplementedError()

    def units(self, dim:str)->list:
        textEdit = self.unitTextBox(dim)
        assert isinstance(textEdit, QPlainTextEdit)
        values = []
        for line in textEdit.toPlainText().splitlines():
            v = line.strip()
            if len(v) > 0  and v not in values:
                values.append(v)
        return values


    def setUnits(self, dim:str, values:list):
        textEdit = self.unitTextBox(dim)
        assert isinstance(textEdit, QPlainTextEdit)
        textEdit.setPlainText('\n'.join(values))

    def config(self, *args, **kwargs)->dict:
        config = {'xUnitList':self.units('x'),
                  'yUnitList':self.units('y')
                  }
        return config

    def setConfig(self, config:dict):
        if 'xUnitList' in config.keys():
            self.setUnits('x', config['xUnitList'])

        if 'yUnitList' in config.keys():
            self.setUnits('y', config['yUnitList'])

        self.mLastConfig = config
        #print('setConfig')

    def resetUnits(self, dim: str):

        if dim == 'x' and 'xUnitList' in self.mLastConfig.keys():
            self.setUnit('x', self.mLastConfig['xUnitList'])

        if dim == 'y' and 'yUnitList' in self.mLastConfig.keys():
            self.setUnit('y', self.mLastConfig['yUnitList'])

class SpectralProfileEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name:str):

        super(SpectralProfileEditorWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer:QgsVectorLayer, fieldIdx:int, parent=QWidget)->SpectralProfileEditorConfigWidget:
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
        w.changed.connect(lambda : self.writeConfig(key, w.config()))
        return w

    def configKey(self, layer:QgsVectorLayer, fieldIdx:int):
        """
        Returns a tuple to be used as dictionary key to identify a layer field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return (layer.id(), fieldIdx)

    def create(self, layer:QgsVectorLayer, fieldIdx:int, editor:QWidget, parent:QWidget)->SpectralProfileEditorWidgetWrapper:
        """
        Create a SpectralProfileEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: SpectralProfileEditorWidgetWrapper
        """
        w = SpectralProfileEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        return w

    def writeConfig(self, key:tuple, config:dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config
        #print('Save config')
        #print(config)

    def readConfig(self, key:tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        if key in self.mConfigurations.keys():
            conf = self.mConfigurations[key]
        else:
            #return the very default configuration
            conf = {'xUnitList' : X_UNITS[:],
                    'yUnitList' : Y_UNITS[:]
            }
        #print('Read config')
        #print((key, conf))
        return conf

    def fieldScore(self, vl:QgsVectorLayer, fieldIdx:int)->int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        #log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() == QVariant.String and field.name() == FIELD_VALUES:
            return 20
        elif field.type() == QVariant.String:
            return 0
        else:
            return 0


def registerSpectralProfileEditorWidget():
    reg = QgsGui.editorWidgetRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys():
        global SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
        SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)

class SpectralLibraryWidget(QMainWindow):

    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)


    class CurrentProfilesMode(enum.Enum):
        normal = 0
        automatically = 1
        block = 2

    def __init__(self, *args, speclib:SpectralLibrary = None, mapCanvas:QgsMapCanvas = None, **kwds):

        """
        Constructor
        :param args: QMainWindow arguments
        :param speclib: SpectralLibrary, defaults: None
        :param mapCanvas: QgsMapCanvas, default: None
        :param kwds: QMainWindow keywords
        """

        super(SpectralLibraryWidget, self).__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibrarywidget.ui'), self)

        assert isinstance(self.mPlotWidget, SpectralLibraryPlotWidget)

        self.m_plot_max = 500

        from .io.envi import EnviSpectralLibraryIO
        from .io.csvdata import CSVSpectralLibraryIO
        from .io.asd import ASDSpectralLibraryIO
        from .io.ecosis import EcoSISSpectralLibraryIO
        from .io.specchio import SPECCHIOSpectralLibraryIO
        from .io.artmo import ARTMOSpectralLibraryIO
        from .io.vectorsources import VectorSourceSpectralLibraryIO


        self.mSpeclibIOInterfaces = [
            EnviSpectralLibraryIO(),
            CSVSpectralLibraryIO(),
            ARTMOSpectralLibraryIO(),
            ASDSpectralLibraryIO(),
            EcoSISSpectralLibraryIO(),
            SPECCHIOSpectralLibraryIO(),
            VectorSourceSpectralLibraryIO(),
        ]

        self.mSpeclibIOInterfaces = sorted(self.mSpeclibIOInterfaces, key=lambda c: c.__class__.__name__)


        self.mSelectionModel = None

        if not isinstance(speclib, SpectralLibrary):
            speclib = SpectralLibrary()

        assert isinstance(speclib, SpectralLibrary)
        self.mSpeclib = speclib

        #QPS_MAPLAYER_STORE.addMapLayer(speclib)

        self.mSpeclib.editingStarted.connect(self.onIsEditableChanged)
        self.mSpeclib.editingStopped.connect(self.onIsEditableChanged)
        self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
        self.mSpeclib.nameChanged.connect(lambda *args, sl=self.mSpeclib: self.setWindowTitle(sl.name()))

        if isinstance(mapCanvas, QgsMapCanvas):
            self.mCanvas = mapCanvas
        else:
            self.mCanvas = QgsMapCanvas(self.centralwidget)
            self.mCanvas.setVisible(False)
            self.mCanvas.setDestinationCrs(self.mSpeclib.crs())
            self.mSpeclib.crsChanged.connect(lambda *args : self.mCanvas.setDestinationCrs(self.mSpeclib.crs()))

        self.mSourceFilter = '*'

        self.mDualView : QgsDualView
        assert isinstance(self.mDualView, QgsDualView)
        self.mDualView.init(self.mSpeclib, self.mCanvas)
        self.mDualView.setView(QgsDualView.AttributeTable)
        self.mDualView.setAttributeTableConfig(self.mSpeclib.attributeTableConfig())
        self.mDualView.showContextMenuExternally.connect(self.onShowContextMenuExternally)
        self.mDualView.tableView().willShowContextMenu.connect(self.onWillShowContextMenu)

        self.mSpeclib.attributeAdded.connect(self.onAttributesChanges)
        self.mSpeclib.attributeDeleted.connect(self.onAttributesChanges)

        self.mPlotWidget: SpectralLibraryPlotWidget
        assert isinstance(self.mPlotWidget, SpectralLibraryPlotWidget)
        self.mPlotWidget.setDualView(self.mDualView)
        self.mPlotWidget.mUpdateTimer.timeout.connect(self.updateStatusBar)

        # change selected row plotStyle: keep plotStyle also when the attribute table looses focus
        pal = self.mDualView.tableView().palette()
        cSelected = pal.color(QPalette.Active, QPalette.Highlight)
        pal.setColor(QPalette.Inactive, QPalette.Highlight, cSelected)
        self.mDualView.tableView().setPalette(pal)

        self.splitter.setSizes([800, 300])

        self.mPlotWidget.setAcceptDrops(True)
        self.mPlotWidget.dragEnterEvent = self.dragEnterEvent
        self.mPlotWidget.dropEvent = self.dropEvent

        # self.mCurrentProfiles = collections.OrderedDict()
        self.mCurrentProfilesMode : SpectralLibraryWidget.CurrentProfilesMode
        self.mCurrentProfilesMode = SpectralLibraryWidget.CurrentProfilesMode.normal
        self.setCurrentProfilesMode(self.mCurrentProfilesMode)

        self.mCurrentProfileIDs:list = []


        self.initActions()

        self.mMapInteraction = True
        self.setMapInteraction(self.mMapInteraction)

        # make buttons with default actions = menu be look like menu parents
        for toolBar in self.findChildren(QToolBar):
            for toolButton in toolBar.findChildren(QToolButton):
                assert isinstance(toolButton, QToolButton)
                if isinstance(toolButton.defaultAction(), QAction) and isinstance(toolButton.defaultAction().menu(), QMenu):
                    toolButton.setPopupMode(QToolButton.MenuButtonPopup)

        # shortcuts / redundant functions
        self.spectraLibrary = self.speclib
        self.clearTable = self.clearSpectralLibrary

        self.mIODialogs = list()

    def onAttributesChanges(self):
        import collections

        speclib = self.speclib()

        all_names = speclib.fields().names()

        # as it should be
        shouldBeVisible = []
        tableConfig = speclib.attributeTableConfig()
        assert isinstance(tableConfig, QgsAttributeTableConfig)
        names = []
        hidden = []
        for c in tableConfig.columns():
            assert isinstance(c, QgsAttributeTableConfig.ColumnConfig)
            names.append(c.name)
            hidden.append(c.hidden)
        missing = [n for n in all_names if n not in names and n not in [FIELD_VALUES, FIELD_FID]]

        if len(missing) > 0:
            self.mDualView.setAttributeTableConfig(QgsAttributeTableConfig())


    def closeEvent(self, *args, **kwargs):

        super(SpectralLibraryWidget, self).closeEvent(*args, **kwargs)

    def applyAllPlotUpdates(self):
        """
        Forces the plot widget to update
        :return:
        :rtype:
        """
        self.plotWidget().onPlotUpdateTimeOut()

    def updateStatusBar(self):

        assert isinstance(self.mStatusBar, QStatusBar)
        slib = self.speclib()
        import sip
        if not sip.isdeleted(slib):
            nFeatures = slib.featureCount()
            nSelected = slib.selectedFeatureCount()
            nVisible = self.plotWidget().plottedProfileCount()
            msg = "{}/{}/{}".format(nFeatures, nSelected, nVisible)
            self.mStatusBar.showMessage(msg)


    def onShowContextMenuExternally(self, menu:QgsActionMenu, fid):
        s = ""

    def onImportFromRasterSource(self):
        from .io.rastersources import SpectralProfileImportPointsDialog
        d = SpectralProfileImportPointsDialog(parent=self)
        d.finished.connect(lambda *args, d=d: self.onIODialogFinished(d))
        d.show()
        self.mIODialogs.append(d)


    def onIODialogFinished(self, w:QWidget):
        from .io.rastersources import SpectralProfileImportPointsDialog
        if isinstance(w, SpectralProfileImportPointsDialog):
            if w.result() == QDialog.Accepted:
                b = self.mSpeclib.isEditable()
                profiles = w.profiles()
                self.mSpeclib.startEditing()
                self.mSpeclib.beginEditCommand('Add {} profiles from {}'.format(len(profiles), w.rasterSource().name()))
                self.mSpeclib.addProfiles(profiles, addMissingFields=False)
                self.mSpeclib.endEditCommand()
                self.mSpeclib.commitChanges()

                if b:
                    self.mSpeclib.startEditing()
            else:
                s = ""

        if w in self.mIODialogs:
            self.mIODialogs.remove(w)
        w.close()

    def canvas(self)->QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mCanvas

    def onWillShowContextMenu(self, menu:QMenu, atIndex:QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """
        menu.addSeparator()
        menu.addAction(self.actionSelectAll)
        menu.addAction(self.actionInvertSelection)
        menu.addAction(self.actionRemoveSelection)
        menu.addAction(self.actionPanMapToSelectedRows)
        menu.addAction(self.actionZoomMapToSelectedRows)
        menu.addSeparator()
        menu.addAction(self.actionDeleteSelected)
        menu.addAction(self.actionCutSelectedRows)
        menu.addAction(self.actionCopySelectedRows)
        menu.addAction(self.actionPasteFeatures)

        menu.addSeparator()

        selectedFIDs = self.mDualView.tableView().selectedFeaturesIds()
        n = len(selectedFIDs)
        menuProfileStyle = menu.addMenu('Profile Style')
        wa = QWidgetAction(menuProfileStyle)

        btnResetProfileStyles = QPushButton('Reset')

        plotStyle = self.plotWidget().colorScheme().profileStyle
        if n == 0:
            btnResetProfileStyles.setText('Reset All')
            btnResetProfileStyles.clicked.connect(self.plotWidget().resetProfileStyles)
            btnResetProfileStyles.setToolTip('Resets all profile styles')
        else:
            for fid in selectedFIDs:
                spi = self.plotWidget().spectralProfilePlotDataItem(fid)
                if isinstance(spi, SpectralProfilePlotDataItem):
                    plotStyle = PlotStyle.fromPlotDataItem(spi)

            btnResetProfileStyles.setText('Reset Selected')
            btnResetProfileStyles.clicked.connect(lambda *args, fids=selectedFIDs: self.plotWidget().setProfileStyles([(None, fids)]))

        psw = PlotStyleWidget(plotStyle=plotStyle)
        psw.setPreviewVisible(False)
        psw.cbIsVisible.setVisible(False)
        psw.sigPlotStyleChanged.connect(lambda style, fids=selectedFIDs : self.plotWidget().setProfileStyles([(style, fids)]))

        frame = QFrame()
        l = QVBoxLayout()
        l.addWidget(btnResetProfileStyles)
        l.addWidget(psw)

        frame.setLayout(l)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

        self.mDualView.tableView().currentIndex()


    def clearSpectralLibrary(self):
        """
        Removes all SpectralProfiles and additional fields
        """
        feature_ids = self.speclib().allFeatureIds()
        self.speclib().startEditing()
        self.speclib().deleteFeatures(feature_ids)
        self.speclib().commitChanges()

        for fieldName in self.speclib().optionalFieldNames():
            index = self.spectralLibrary().fields().indexFromName(fieldName)
            self.spectralLibrary().startEditing()
            self.spectralLibrary().deleteAttribute(index)
            self.spectralLibrary().commitChanges()

    def currentProfilesMode(self)->CurrentProfilesMode:
        """
        Returns the mode how incoming profiles are handled
        :return: CurrentProfilesMode
        """
        return self.mCurrentProfilesMode

    def setCurrentProfilesMode(self, mode:CurrentProfilesMode):
        """
        Sets the way how to handel profiles added by setCurrentProfiles
        :param mode: CurrentProfilesMode
        """
        assert isinstance(mode, SpectralLibraryWidget.CurrentProfilesMode)
        self.mCurrentProfilesMode = mode
        if mode == SpectralLibraryWidget.CurrentProfilesMode.block:
            self.optionBlockProfiles.setChecked(True)
            self.optionAddCurrentProfilesAutomatically.setEnabled(False)
            #self.actionAddProfiles.setEnabled(False)
        else:
            self.optionBlockProfiles.setChecked(False)
            self.optionAddCurrentProfilesAutomatically.setEnabled(True)
            if mode == SpectralLibraryWidget.CurrentProfilesMode.automatically:
                self.optionAddCurrentProfilesAutomatically.setChecked(True)
                #self.actionAddProfiles.setEnabled(False)
            elif mode == SpectralLibraryWidget.CurrentProfilesMode.normal:
                self.optionAddCurrentProfilesAutomatically.setChecked(False)
                #self.actionAddProfiles.setEnabled(len(self.currentSpectra()) > 0)
            else:
                raise NotImplementedError()


    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)
        #log('dropEvent')
        mimeData = event.mimeData()

        speclib = SpectralLibrary.readFromMimeData(mimeData)
        if isinstance(speclib, SpectralLibrary) and len(speclib) > 0:
            event.setAccepted(True)
            self.addSpeclib(speclib)

    def dragEnterEvent(self, dragEnterEvent:QDragEnterEvent):

        mimeData = dragEnterEvent.mimeData()
        assert isinstance(mimeData, QMimeData)
        if containsSpeclib(mimeData):
            dragEnterEvent.accept()

    def initActions(self):
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        def onSetBlocked(isBlocked):
            if isBlocked:
                self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.block)
            else:
                if self.optionAddCurrentProfilesAutomatically.isChecked():
                    self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
                else:
                    self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.normal)
        self.optionBlockProfiles.toggled.connect(onSetBlocked)
        self.optionBlockProfiles.setVisible(False)

        self.optionAddCurrentProfilesAutomatically.toggled.connect(
            lambda b: self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
                if b else self.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.normal)
        )

        self.actionImportSpeclib.triggered.connect(self.onImportSpeclib)
        self.actionImportSpeclib.setMenu(self.importSpeclibMenu())
        self.actionImportVectorSource.triggered.connect(self.onImportFromRasterSource)
        self.actionAddProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)
        self.actionReloadProfiles.triggered.connect(self.onReloadProfiles)

        m = QMenu()
        #m.addAction(self.actionImportSpeclib)
        m.addAction(self.actionImportVectorSource)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        m.addSeparator()
        m.addAction(self.optionBlockProfiles)

        self.actionAddProfiles.setMenu(m)

        self.actionExportSpeclib.triggered.connect(self.onExportSpectra)
        self.actionExportSpeclib.setMenu(self.exportSpeclibMenu())
        self.actionSaveSpeclib = self.actionExportSpeclib  # backward compatibility
        self.actionReload.triggered.connect(lambda : self.mPlotWidget.updateSpectralProfilePlotItems())
        self.actionToggleEditing.toggled.connect(self.onToggleEditing)
        self.actionSaveEdits.triggered.connect(self.onSaveEdits)
        self.actionDeleteSelected.triggered.connect(lambda : deleteSelected(self.speclib()))

        self.actionSelectAll.triggered.connect(self.selectAll)
        self.actionInvertSelection.triggered.connect(self.invertSelection)
        self.actionRemoveSelection.triggered.connect(self.removeSelection)
        self.actionPanMapToSelectedRows.triggered.connect(self.panMapToSelectedRows)
        self.actionZoomMapToSelectedRows.triggered.connect(self.zoomMapToSelectedRows)

        self.actionAddAttribute.triggered.connect(self.onAddAttribute)
        self.actionRemoveAttribute.triggered.connect(self.onRemoveAttribute)

        self.actionFormView.triggered.connect(lambda: self.mDualView.setView(QgsDualView.AttributeEditor))
        self.actionTableView.triggered.connect(lambda: self.mDualView.setView(QgsDualView.AttributeTable))

        self.actionProperties.triggered.connect(self.showProperties)


        self.actionCutSelectedRows.triggered.connect(self.cutSelectedFeatures)
        self.actionCopySelectedRows.triggered.connect(self.copySelectedFeatures)
        self.actionPasteFeatures.triggered.connect(self.pasteFeatures)

        for action in [self.actionProperties, self.actionFormView, self.actionTableView]:
            btn = QToolButton()
            btn.setDefaultAction(action)
            btn.setAutoRaise(True)
            self.statusBar().addPermanentWidget(btn)

        self.onIsEditableChanged()

    def importSpeclibMenu(self)->QMenu:
        """
        :return: QMenu with QActions and submenus to import SpectralProfiles
        """
        m = QMenu()
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO), iface
            iface.addImportActions(self.speclib(), m)
        return m

    def exportSpeclibMenu(self)->QMenu:
        """
        :return: QMenu with QActions and submenus to export SpectralProfiles
        """
        m = QMenu()
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO)
            iface.addExportActions(self.speclib(), m)
        return m


    def showProperties(self, *args):

        from ..layerproperties import showLayerPropertiesDialog

        showLayerPropertiesDialog(self.speclib(), None, parent=self, useQGISDialog=True)

        s = ""

    def onImportSpeclib(self):
        """
        Imports a SpectralLibrary
        :param path: str
        """

        slib = SpectralLibrary.readFromSourceDialog(self)

        if isinstance(slib, SpectralLibrary) and len(slib) > 0:
            self.addSpeclib(slib)


    def speclib(self)->SpectralLibrary:
        """
        Returns the SpectraLibrary
        :return: SpectralLibrary
        """
        return self.mSpeclib

    def onSaveEdits(self, *args):
        speclib = self.speclib()
        if isinstance(speclib, SpectralLibrary) and speclib.isModified():
            b = speclib.isEditable()
            success = speclib.commitChanges()
            if not success:
                speclib.reload()
            if b:
                speclib.startEditing()

    def onSelectionChanged(self, selected, deselected, clearAndSelect):
        """
        :param selected:
        :param deselected:
        :param clearAndSelect:
        :return:
        """
        hasSelected = self.speclib().selectedFeatureCount() > 0
        self.actionCopySelectedRows.setEnabled(hasSelected)
        self.actionCutSelectedRows.setEnabled(self.mSpeclib.isEditable() and hasSelected)
        self.actionDeleteSelected.setEnabled(self.mSpeclib.isEditable() and hasSelected)
        self.actionReloadProfiles.setEnabled(self.mSpeclib.isEditable() and hasSelected)

        self.actionPanMapToSelectedRows.setEnabled(hasSelected)
        self.actionRemoveSelection.setEnabled(hasSelected)
        self.actionZoomMapToSelectedRows.setEnabled(hasSelected)


    def onIsEditableChanged(self, *args):
        speclib = self.speclib()

        isEditable = speclib.isEditable()
        self.actionToggleEditing.blockSignals(True)
        self.actionToggleEditing.setChecked(isEditable)
        self.actionSaveEdits.setEnabled(isEditable)
        self.actionReload.setEnabled(not isEditable)
        self.actionToggleEditing.blockSignals(False)
        self.actionReloadProfiles.setEnabled(isEditable)

        self.actionAddAttribute.setEnabled(isEditable)
        self.actionPasteFeatures.setEnabled(isEditable)
        self.actionToggleEditing.setEnabled(not speclib.readOnly())

        self.actionRemoveAttribute.setEnabled(isEditable and len(speclib.optionalFieldNames()) > 0)

        self.onSelectionChanged(None, None, None)

    def onToggleEditing(self, b:bool):

        if b == False:

            if self.mSpeclib.isModified():
                result = QMessageBox.question(self, 'Leaving edit mode', 'Save changes?', buttons=QMessageBox.No | QMessageBox.Yes, defaultButton=QMessageBox.Yes)
                if result == QMessageBox.Yes:
                    if not self.mSpeclib.commitChanges():
                        errors = self.mSpeclib.commitErrors()
                        print(errors)
                else:
                    self.mSpeclib.rollBack()
                    s = ""

            else:
                if not self.mSpeclib.commitChanges():
                    errors = self.mSpeclib.commitErrors()
                    print(errors)
        else:
            if not self.mSpeclib.isEditable() and not self.mSpeclib.startEditing():
                print('Can not edit spectral library')


    def onReloadProfiles(self):

        cnt = self.speclib().selectedFeatureCount()
        if cnt > 0 and self.speclib().isEditable():
            # ask for profile source raster
            from ..utils import SelectMapLayersDialog

            d = SelectMapLayersDialog()
            d.setWindowIcon(QIcon(''))
            d.setWindowTitle('Reload {} selected profile(s) from'.format(cnt))
            d.addLayerDescription('Raster', QgsMapLayerProxyModel.RasterLayer)
            d.exec_()
            if d.result() == QDialog.Accepted:
                layers = d.mapLayers()
                if isinstance(layers[0], QgsRasterLayer):
                    self.speclib().beginEditCommand('Reload {} profiles from {}'.format(cnt, layers[0].name()))
                    self.speclib().reloadSpectralValues(layers[0], selectedOnly=True)
                    self.speclib().endEditCommand()

            s  =""


    def onAddAttribute(self):
        """
        Slot to add an optional QgsField / attribute
        """
        speclib = self.speclib()
        if speclib.isEditable():
            d = AddAttributeDialog(self.mSpeclib, case_sensitive=False)
            d.exec_()
            if d.result() == QDialog.Accepted:
                field = d.field()
                speclib.addAttribute(field)
        else:
            log('call SpectralLibrary().startEditing before adding attributes')

    def onRemoveAttribute(self):
        """
        Slot to remove none-mandatory fields / attributes
        """
        if self.mSpeclib.isEditable():
            fieldNames = self.mSpeclib.optionalFieldNames()
            if len(fieldNames) > 0:
                fieldName, accepted = QInputDialog.getItem(self, 'Remove Field', 'Select', fieldNames, editable=False)
                if accepted:
                    i = self.mSpeclib.fields().indexFromName(fieldName)
                    if i >= 0:
                        self.mSpeclib.startEditing()
                        self.mSpeclib.deleteAttribute(i)
                        self.mSpeclib.commitChanges()
        else:
            log('call SpectralLibrary().startEditing before removing attributes')

    def setMapInteraction(self, b: bool):
        """
        Enables/disables actions to navigate on maps or select profiles from.
        Note: you need to connect them with respective MapTools and QgsMapCanvases
        :param b: bool
        """
        if b == False:
            self.setCurrentSpectra([])
        self.mMapInteraction = b
        self.actionSelectProfilesFromMap.setVisible(b)
        self.actionPanMapToSelectedRows.setVisible(b)
        self.actionZoomMapToSelectedRows.setVisible(b)


    def mapInteraction(self)->bool:
        """
        Returns True of map-interaction actions are enables and visible
        :return: bool
        """
        return self.mMapInteraction

    def selectAll(self):
        """
        Selects all features/spectral profiles
        """
        self.speclib().selectAll()

    def invertSelection(self):
        """
        Inverts the current selection
        """
        self.speclib().invertSelection()

    def removeSelection(self):
        """
        Removes the current selection
        """
        self.speclib().removeSelection()

    def panMapToSelectedRows(self):
        """
        Pan to the selected layer features
        Requires that external maps respond to sigMapCenterRequested
        """
        crs = self.mCanvas.mapSettings().destinationCrs()
        center = SpatialPoint(self.speclib().crs(), self.speclib().boundingBoxOfSelected().center()).toCrs(crs)
        self.mCanvas.setCenter(center)
        self.sigMapCenterRequested.emit(center)

    def zoomMapToSelectedRows(self):
        """
        Zooms to the selected rows.
        Requires that external maps respond to sigMapExtentRequested
        """
        crs = self.mCanvas.mapSettings().destinationCrs()
        bbox = SpatialExtent(self.speclib().crs(), self.speclib().boundingBoxOfSelected()).toCrs(crs)
        if isinstance(bbox, SpatialExtent):
            self.mCanvas.setExtent(bbox)
            self.sigMapExtentRequested.emit(bbox)

    def deleteSelectedFeatures(self):
        """
        Deletes the selected SpectralProfiles / QgsFeatures. Requires that editing mode is enabled.
        """
        self.speclib().beginEditCommand('Delete selected features')
        self.speclib().deleteSelectedFeatures()
        self.speclib().endEditCommand()

    def cutSelectedFeatures(self)->bool:
        """
        Copies the selected SpectralProfiles to the clipboard and deletes them from the SpectraLibrary.
        Requires that editing mode is enabled.
        """
        if self.copySelectedFeatures():
            self.speclib().beginEditCommand('Cut Features')
            self.speclib().deleteSelectedFeatures()
            self.speclib().endEditCommand()
            return True
        else:
            return False

    def pasteFeatures(self)->bool:
        import qgis.utils
        if isinstance(qgis.utils.iface, QgisInterface):
            qgis.utils.iface.pasteFromClipboard(self.mSpeclib)
            return True
        else:
            return False

    def copySelectedFeatures(self)->bool:
        import qgis.utils
        if isinstance(qgis.utils.iface, QgisInterface):
            qgis.utils.iface.copySelectionToClipboard(self.mSpeclib)
            return True
        else:
            return False


    #def onAttributesChanged(self):
    #    self.btnRemoveAttribute.setEnabled(len(self.mSpeclib.metadataAttributes()) > 0)

    #def addAttribute(self, name):
    #    name = str(name)
    #    if len(name) > 0 and name not in self.mSpeclib.metadataAttributes():
    #        self.mModel.addAttribute(name)

    def plotWidget(self)->SpectralLibraryPlotWidget:
        """
        Returns the plotwidget
        :return: SpectralLibraryPlotWidget
        """
        return self.mPlotWidget

    def plotItem(self)->PlotItem:
        """
        Returns the pyqtgraph/graphicsItems/PlotItem/PlotItem
        :return: PlotItem
        """
        pi = self.mPlotWidget.getPlotItem()
        assert isinstance(pi, PlotItem)
        return pi

    def onExportSpectra(self, *args):
        files = self.mSpeclib.exportProfiles(None)
        if len(files) > 0:
            self.sigFilesCreated.emit(files)


    def addSpeclib(self, speclib:SpectralLibrary):
        """
        Adds spectral profiles of a SpectralLibrary. Suppresses plot updates in doing so
        :param speclib: SpectralLibrary
        """
        if isinstance(speclib, SpectralLibrary):
            sl = self.speclib()


            self._progressDialog = QProgressDialog(parent=self)
            self._progressDialog.setWindowTitle('Add Profiles')
            #progressDialog.show()

            info = 'Add {} profiles...'.format(len(speclib))

            wasEditable = sl.isEditable()

            try:
                sl.startEditing()
                sl.beginEditCommand(info)
                sl.addSpeclib(speclib, progressDialog=self._progressDialog)
                sl.endEditCommand()
                if not wasEditable:
                    sl.commitChanges()
            except Exception as ex:
                print(ex, file=sys.stderr)
                pass

            self._progressDialog.hide()
            self._progressDialog.close()
            del self._progressDialog
            #QApplication.processEvents()


    def addCurrentSpectraToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """
        self.plotWidget().setProfileStyles([(None, self.mCurrentProfileIDs)])
        self.mCurrentProfileIDs.clear()

    sigCurrentSpectraChanged = pyqtSignal(list)

    def setCurrentSpectra(self, profiles: list):
        self.setCurrentProfiles(profiles)

    def setCurrentProfiles(self, currentProfiles:list):
        assert isinstance(currentProfiles, list)

        speclib : SpectralLibrary = self.speclib()
        plotWidget : SpectralLibraryPlotWidget = self.plotWidget()
        colorScheme = plotWidget.colorScheme()

        mode = self.currentProfilesMode()
        if mode == SpectralLibraryWidget.CurrentProfilesMode.block:
            #
            return

        #  stop plot updates
        plotWidget.mUpdateTimer.stop()
        restart_editing = not speclib.startEditing()
        oldCurrentIds = self.mCurrentProfileIDs[:]


        if mode == SpectralLibraryWidget.CurrentProfilesMode.normal:
            # delete previous current profiles from speclib
            speclib.deleteFeatures(oldCurrentIds)
            plotWidget.removeSpectralProfilePDIs(oldCurrentIds, updateScene=False)
            # now there should'nt be any PDI or style ref related to an old ID
            if True:
                all_lyr = speclib.allFeatureIds()
                all_style = plotWidget.mSPECIFIC_PROFILE_STYLES.keys()
                for id in oldCurrentIds:
                    if id in all_lyr:
                        s = ""
                    assert id not in all_lyr
                    assert id not in all_style
        if mode == SpectralLibraryWidget.CurrentProfilesMode.automatically:
            self.addCurrentSpectraToSpeclib()

        self.mCurrentProfileIDs.clear()
        # if necessary, convert QgsFeatures to SpectralProfiles
        for i in range(len(currentProfiles)):
            p = currentProfiles[i]
            assert isinstance(p, QgsFeature)
            if not isinstance(p, SpectralProfile):
                p = SpectralProfile.fromSpecLibFeature(p)
                currentProfiles[i] = p

        # add current profiles to speclib
        oldIDs = set(speclib.allFeatureIds())
        speclib.addProfiles(currentProfiles)
        self.mSpeclib.commitChanges()
        if restart_editing:
            speclib.startEditing()
        addedIDs = set(speclib.allFeatureIds()).difference(oldIDs)

        if mode == SpectralLibraryWidget.CurrentProfilesMode.normal:
            # give current spectral the current spectral style
            self.mCurrentProfileIDs.extend(addedIDs)
            plotWidget.setProfileStyles([(colorScheme.temporaryProfileStyle, addedIDs)])

        plotWidget.mUpdateTimer.start()

    def currentSpectra(self) -> list:
        return self.currentProfiles()

    def currentProfiles(self)->list:
        """
        Returns the SpectralProfiles which are not added to the SpectralLibrary but shown as over-plot items
        :return: [list-of-SpectralProfiles]
        """
        fids = self.mCurrentProfileIDs[:]
        return list(self.mSpeclib.profiles(fids))


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib:SpectralLibrary=None, **kwds):
        super(SpectralLibraryPanel, self).__init__(*args, **kwds)
        self.setObjectName('spectralLibraryPanel')
        self.setWindowTitle('Spectral Library')
        self.SLW = SpectralLibraryWidget(speclib=speclib)
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
        self.SLW.setCurrentSpectra(listOfSpectra)

    def setCurrentProfilesMode(self, mode:SpectralLibraryWidget.CurrentProfilesMode):
        """
        Sets the way how to handel profiles added by setCurrentProfiles
        :param mode: SpectralLibraryWidget.CurrentProfilesMode
        """
        self.SLW.setCurrentProfilesMode(mode)
