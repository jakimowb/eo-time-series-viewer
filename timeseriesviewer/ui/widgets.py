# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'imagechipviewsettings_widget_base.ui'
#
# Created: Mon Oct 26 16:10:40 2015
#      by: PyQt4 UI code generator 4.10.2
#
# WARNING! All changes made in this file will be lost!

'''
/***************************************************************************
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 ***************************************************************************/
'''

import os, collections
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtXml import *
import PyQt4.QtWebKit


import sys, re, os, six

#widgets defined without UI file
class TsvScrollArea(QScrollArea):

    sigResized = pyqtSignal()
    def __init__(self, *args, **kwds):
        super(TsvScrollArea, self).__init__(*args, **kwds)

    def resizeEvent(self, event):
        super(TsvScrollArea, self).resizeEvent(event)
        self.sigResized.emit()


class VerticalLabel(QLabel):
    def __init__(self, text, orientation='vertical', forceWidth=True):
        QLabel.__init__(self, text)
        self.forceWidth = forceWidth
        self.orientation = None
        self.setOrientation(orientation)

    def setOrientation(self, o):
        if self.orientation == o:
            return
        self.orientation = o
        self.update()
        self.updateGeometry()

    def paintEvent(self, ev):
        p = QPainter(self)
        # p.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 200)))
        # p.setPen(QtGui.QPen(QtGui.QColor(50, 50, 100)))
        # p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))

        if self.orientation == 'vertical':
            p.rotate(-90)
            rgn = QRect(-self.height(), 0, self.height(), self.width())
        else:
            rgn = self.contentsRect()
        align = self.alignment()
        # align  = QtCore.Qt.AlignTop|QtCore.Qt.AlignHCenter

        self.hint = p.drawText(rgn, align, self.text())
        p.end()

        if self.orientation == 'vertical':
            self.setMaximumWidth(self.hint.height())
            self.setMinimumWidth(0)
            self.setMaximumHeight(16777215)
            if self.forceWidth:
                self.setMinimumHeight(self.hint.width())
            else:
                self.setMinimumHeight(0)
        else:
            self.setMaximumHeight(self.hint.height())
            self.setMinimumHeight(0)
            self.setMaximumWidth(16777215)
            if self.forceWidth:
                self.setMinimumWidth(self.hint.width())
            else:
                self.setMinimumWidth(0)

    def sizeHint(self):
        if self.orientation == 'vertical':
            if hasattr(self, 'hint'):
                return QSize(self.hint.height(), self.hint.width())
            else:
                return QSize(19, 50)
        else:
            if hasattr(self, 'hint'):
                return QSize(self.hint.width(), self.hint.height())
            else:
                return QSize(50, 19)




from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.ui import loadUIFormClass, DIR_UI
from timeseriesviewer.main import SpatialExtent, QgisTsvBridge, TsvMimeDataUtils

PATH_MAIN_UI = jp(DIR_UI, 'timeseriesviewer.ui')
PATH_MAPVIEWSETTINGS_UI = jp(DIR_UI, 'mapviewsettings.ui')
PATH_MAPVIEWRENDERSETTINGS_UI = jp(DIR_UI, 'mapviewrendersettings.ui')
PATH_MAPVIEWDEFINITION_UI = jp(DIR_UI, 'mapviewdefinition.ui')
PATH_TSDVIEW_UI = jp(DIR_UI, 'timeseriesdatumview.ui')
PATH_ABOUTDIALOG_UI = jp(DIR_UI, 'aboutdialog.ui')
PATH_SETTINGSDIALOG_UI = jp(DIR_UI, 'settingsdialog.ui')

PATH_PROFILEVIEWDOCK_UI = jp(DIR_UI, 'profileviewdock.ui')
PATH_RENDERINGDOCK_UI = jp(DIR_UI, 'renderingdock.ui')




def maxWidgetSizes(layout):
    assert isinstance(layout, QBoxLayout)

    p = layout.parentWidget()
    m = layout.contentsMargins()

    sizeX = 0
    sizeY = 0
    horizontal = isinstance(layout, QHBoxLayout)

    for item in [layout.itemAt(i) for i in range(layout.count())]:
        wid = item.widget()
        if wid:
            s = wid.sizeHint()
        elif isinstance(item, QLayout):
            s = ""
            continue
        if horizontal:
            sizeX += s.width() + layout.spacing()
            sizeY = max([sizeY, s.height()])  + layout.spacing()
        else:
            sizeX = max([sizeX, s.width()])  + layout.spacing()
            sizeY += s.height()  + layout.spacing()


    return QSize(sizeX + m.left()+ m.right(),
                 sizeY + m.top() + m.bottom())




class TimeSeriesViewerUI(QMainWindow,
                         loadUIFormClass(PATH_MAIN_UI)):

    sigQgsSyncChanged = pyqtSignal(bool, bool, bool)

    def __init__(self, parent=None):
        """Constructor."""
        super(TimeSeriesViewerUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.addActions(self.findChildren(QAction))



        #set button default actions -> this will show the action icons as well
        #I don't know why this is not possible in the QDesigner when QToolButtons are
        #placed outside a toolbar

        import timeseriesviewer.ui.docks as docks

        area = None

        def addDockWidget(dock):
            """
            shortcut to add a created dock and return it
            :param dock:
            :return:
            """
            self.addDockWidget(area, dock)
            return dock

        area = Qt.LeftDockWidgetArea

        self.dockRendering = addDockWidget(docks.RenderingDockUI(self))
        self.dockNavigation = addDockWidget(docks.NavigationDockUI(self))
        self.dockLabeling = addDockWidget(docks.LabelingDockUI(self))
        #self.tabifyDockWidget(self.dockNavigation, self.dockRendering)
        #self.tabifyDockWidget(self.dockNavigation, self.dockLabeling)

        from timeseriesviewer.sensorvisualization import SensorDockUI
        self.dockSensors = addDockWidget(SensorDockUI(self))
        #area = Qt.RightDockWidgetArea


        area = Qt.BottomDockWidgetArea

        self.dockMapViews = addDockWidget(docks.MapViewDockUI(self))
        self.dockTimeSeries = addDockWidget(docks.TimeSeriesDockUI(self))
        from timeseriesviewer.profilevisualization import ProfileViewDockUI
        self.dockProfiles = addDockWidget(ProfileViewDockUI(self))
        self.tabifyDockWidget(self.dockTimeSeries, self.dockMapViews)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)


        for dock in self.findChildren(QDockWidget):
            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())


        self.dockLabeling.setHidden(True)

        self.dockTimeSeries.raise_()
        self.dockNavigation.raise_()

        self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)


        #todo: move to QGS_TSV_Bridge
        self.dockRendering.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)

        #define subset-size behaviour

        self.restoreSettings()


    def restoreSettings(self):
        from timeseriesviewer import SETTINGS

        #set last CRS
        self.dockNavigation.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        s = ""


    def setQgsLinkWidgets(self):
        #enable/disable widgets that rely on QGIS instance interaction
        from timeseriesviewer import QGIS_TSV_BRIDGE
        from timeseriesviewer.main import QgisTsvBridge
        b = isinstance(QGIS_TSV_BRIDGE, QgisTsvBridge)
        self.dockNavigation.gbSyncQgs.setEnabled(b)
        self.dockRendering.gbQgsVectorLayer.setEnabled(b)

    def _blockSignals(self, widgets, block=True):
        states = dict()
        if isinstance(widgets, dict):
            for w, block in widgets.items():
                states[w] = w.blockSignals(block)
        else:
            for w in widgets:
                states[w] = w.blockSignals(block)
        return states






    sigSubsetSizeChanged = pyqtSignal(QSize)
    def setSubsetSize(self, size, blockSignal=False):
        old = self.subsetSize()

        if blockSignal:
            states = self._blockSignals(w, True)

        self.spinBoxSubsetSizeX.setValue(size.width())
        self.spinBoxSubsetSizeY.setValue(size.height())
        self._setUpdateBehaviour()

        if blockSignal:
            self._blockSignals(states)
        elif old != size:
            self.sigSubsetSizeChanged(size)


    def setProgress(self, value, valueMax=None, valueMin=0):
        p = self.progressBar
        if valueMin is not None and valueMin != self.progessBar.minimum():
            p.setMinimum(valueMin)
        if valueMax is not None and valueMax != self.progessBar.maximum():
            p.setMaximum(valueMax)
        self.progressBar.setValue(value)



class AboutDialogUI(QDialog,
                    loadUIFormClass(PATH_ABOUTDIALOG_UI)):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialogUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.init()

    def init(self):
        self.mTitle = self.windowTitle()
        self.listWidget.currentItemChanged.connect(lambda: self.setAboutTitle())
        self.setAboutTitle()

        # page About
        from timeseriesviewer import PATH_LICENSE, VERSION, DIR_DOCS
        import pyqtgraph
        self.labelVersion.setText('Version ' + VERSION)

        lf = lambda p: str(open(p).read())
        # page Changed
        self.tbChanges.setText(lf(jp(DIR_DOCS, 'CHANGES.html')))

        # page Credits
        self.CREDITS = dict()
        self.CREDITS['QGIS'] = lf(jp(DIR_DOCS, 'README_QGIS.html'))
        self.CREDITS['PYQTGRAPH'] = lf(jp(DIR_DOCS, 'README_PyQtGraph.html'))
        self.webViewCredits.setHtml(self.CREDITS['QGIS'])
        self.btnPyQtGraph.clicked.connect(lambda: self.showCredits('PYQTGRAPH'))
        self.btnQGIS.clicked.connect(lambda: self.showCredits('QGIS'))

        # page License
        self.tbLicense.setText(lf(PATH_LICENSE))


    def showCredits(self, key):
        self.webViewCredits.setHtml(self.CREDITS[key])
        self.setAboutTitle(key)

    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)


class MapViewDefinitionUI(QGroupBox, loadUIFormClass(PATH_MAPVIEWDEFINITION_UI)):

    sigHideMapView = pyqtSignal()
    sigShowMapView = pyqtSignal()
    sigVectorVisibility = pyqtSignal(bool)

    def __init__(self, mapViewDefinition,parent=None):
        super(MapViewDefinitionUI, self).__init__(parent)

        self.setupUi(self)
        self.mMapViewDefinition = mapViewDefinition
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnMapViewVisibility.setDefaultAction(self.actionToggleVisibility)
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)
        self.btnVectorOverlayVisibility.setDefaultAction(self.actionToggleVectorVisibility)
        self.actionToggleVisibility.toggled.connect(lambda: self.setVisibility(not self.actionToggleVisibility.isChecked()))
        self.actionToggleVectorVisibility.toggled.connect(lambda : self.sigVectorVisibility.emit(self.actionToggleVectorVisibility.isChecked()))

    def _sizeHint(self):

        m = self.layout().contentsMargins()
        sl = maxWidgetSizes(self.sensorList)
        sm = self.buttonList.size()
        w = sl.width() + m.left()+ m.right() + sm.width() + 50
        h = sl.height() + m.top() + m.bottom() + sm.height() + 50

        return QSize(w,h)


    def mapViewDefinition(self):
        return self.mMapViewDefinition


    def setVisibility(self, isVisible):
        if isVisible != self.actionToggleVisibility.isChecked():
            self.btnMapViewVisibility.setChecked(isVisible)
            if isVisible:
                self.sigShowMapView.emit()
            else:
                self.sigHideMapView.emit()

    def visibility(self):
        return self.actionToggleVisibility.isChecked()

class TimeSeriesDatumViewUI(QFrame, loadUIFormClass(PATH_TSDVIEW_UI)):

    def __init__(self, title='<#>', parent=None):
        super(TimeSeriesDatumViewUI, self).__init__(parent)
        self.setupUi(self)

    def sizeHint(self):
        m = self.layout().contentsMargins()

        s = QSize(0, 0)

        for w in [self.layout().itemAt(i).widget() for i in range(self.layout().count())]:
            if w:
                s = s + w.size()

        if isinstance(self.layout(), QVBoxLayout):
            s = QSize(self.line.width() + m.left() + m.right(),
                      s.height() + m.top() + m.bottom())
        else:
            s = QSize(self.line.heigth() + m.top() + m.bottom(),
                      s.width() + m.left() + m.right())

        return s





class MapViewRenderSettingsUI(QGroupBox,
                              loadUIFormClass(PATH_MAPVIEWRENDERSETTINGS_UI)):

    def __init__(self, parent=None):
        """Constructor."""
        super(MapViewRenderSettingsUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect

        self.setupUi(self)

        self.btnDefaultMB.setDefaultAction(self.actionSetDefaultMB)
        self.btnTrueColor.setDefaultAction(self.actionSetTrueColor)
        self.btnCIR.setDefaultAction(self.actionSetCIR)
        self.btn453.setDefaultAction(self.actionSet453)

        self.btnSingleBandDef.setDefaultAction(self.actionSetDefaultSB)
        self.btnSingleBandBlue.setDefaultAction(self.actionSetB)
        self.btnSingleBandGreen.setDefaultAction(self.actionSetG)
        self.btnSingleBandRed.setDefaultAction(self.actionSetR)
        self.btnSingleBandNIR.setDefaultAction(self.actionSetNIR)
        self.btnSingleBandSWIR.setDefaultAction(self.actionSetSWIR)

        self.btnPasteStyle.setDefaultAction(self.actionPasteStyle)
        self.btnCopyStyle.setDefaultAction(self.actionCopyStyle)
        self.btnApplyStyle.setDefaultAction(self.actionApplyStyle)



class MapViewSensorSettings(QObject):
    """
    Describes the rendering of images of one Sensor
    """

    sigSensorRendererChanged = pyqtSignal(QgsRasterRenderer)

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(MapViewSensorSettings, self).__init__(parent)
        from timeseriesviewer.timeseries import SensorInstrument
        assert isinstance(sensor, SensorInstrument)
        self.sensor = sensor

        self.ui = MapViewRenderSettingsUI(parent)
        self.ui.create()
        self.sensor.sigNameChanged.connect(self.onSensorNameChanged)
        self.onSensorNameChanged(self.sensor.name())

        self.ui.bandNames = sensor.bandNames

        self.multiBandMinValues = [self.ui.tbRedMin, self.ui.tbGreenMin, self.ui.tbBlueMin]
        self.multiBandMaxValues = [self.ui.tbRedMax, self.ui.tbGreenMax, self.ui.tbBlueMax]
        self.multiBandSliders = [self.ui.sliderRed, self.ui.sliderGreen, self.ui.sliderBlue]

        for tb in self.multiBandMinValues + self.multiBandMaxValues + [self.ui.tbSingleBandMin, self.ui.tbSingleBandMax]:
            tb.setValidator(QDoubleValidator())
        for sl in self.multiBandSliders + [self.ui.sliderSingleBand]:
            sl.setMinimum(1)
            sl.setMaximum(sensor.nb)
            sl.valueChanged.connect(self.updateUi)

        self.ceAlgs = collections.OrderedDict()

        self.ceAlgs["No enhancement"] = QgsContrastEnhancement.NoEnhancement
        self.ceAlgs["Stretch to MinMax"] = QgsContrastEnhancement.StretchToMinimumMaximum
        self.ceAlgs["Stretch and clip to MinMax"] = QgsContrastEnhancement.StretchAndClipToMinimumMaximum
        self.ceAlgs["Clip to MinMax"] = QgsContrastEnhancement.ClipToMinimumMaximum

        self.colorRampType = collections.OrderedDict()
        self.colorRampType['Interpolated'] = QgsColorRampShader.INTERPOLATED
        self.colorRampType['Discrete'] = QgsColorRampShader.DISCRETE
        self.colorRampType['Exact'] = QgsColorRampShader.EXACT

        self.colorRampClassificationMode = collections.OrderedDict()
        self.colorRampClassificationMode['Continuous'] = 1
        self.colorRampClassificationMode['Equal Interval'] = 2
        self.colorRampClassificationMode['Quantile'] = 3

        def populateCombobox(cb, d):
            for key, value in d.items():
                cb.addItem(key, value)
            cb.setCurrentIndex(0)

        populateCombobox(self.ui.comboBoxContrastEnhancement, self.ceAlgs)
        populateCombobox(self.ui.cbSingleBandColorRampType, self.colorRampType)
        populateCombobox(self.ui.cbSingleBandMode, self.colorRampClassificationMode)

        self.ui.cbSingleBandColorRamp.populate(QgsStyleV2.defaultStyle())


        nb = self.sensor.nb
        lyr = QgsRasterLayer(self.sensor.pathImg)

        #define default renderers:
        bands = [min([b,nb-1]) for b in range(3)]
        extent = lyr.extent()

        bandStats = [lyr.dataProvider().bandStatistics(b, QgsRasterBandStats.All, extent, 500) for b in range(nb)]

        def createEnhancement(bandIndex):
            bandIndex = min([nb - 1, bandIndex])
            e = QgsContrastEnhancement(self.sensor.bandDataType)
            e.setMinimumValue(bandStats[bandIndex].Min)
            e.setMaximumValue(bandStats[bandIndex].Max)
            e.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            return e

        self.defaultMB = QgsMultiBandColorRenderer(lyr.dataProvider(), bands[0], bands[1], bands[2])
        self.defaultMB.setRedContrastEnhancement(createEnhancement(bands[0]))
        self.defaultMB.setGreenContrastEnhancement(createEnhancement(bands[1]))
        self.defaultMB.setBlueContrastEnhancement(createEnhancement(bands[2]))

        self.defaultSB = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 0, None)

        colorRamp = self.ui.cbSingleBandColorRamp.currentColorRamp()

        #fix: QGIS 3.0 constructor
        shaderFunc = QgsColorRampShader(bandStats[0].Min, bandStats[0].Max)
        shaderFunc.setColorRampType(QgsColorRampShader.INTERPOLATED)
        shaderFunc.setClip(True)
        nSteps = 5
        colorRampItems = []
        diff = bandStats[0].Max - bandStats[0].Min
        for  i in range(nSteps+1):
            f = float(i) / nSteps
            color = colorRamp.color(f)
            value = bandStats[0].Min + diff * f
            colorRampItems.append(QgsColorRampShader.ColorRampItem(value, color))
        shaderFunc.setColorRampItemList(colorRampItems)
        shader = QgsRasterShader()
        shader.setMaximumValue(bandStats[0].Min)
        shader.setMinimumValue(bandStats[0].Max)
        shader.setRasterShaderFunction(shaderFunc)
        self.defaultSB.setShader(shader)
        self.defaultSB.setClassificationMin(shader.minimumValue())
        self.defaultSB.setClassificationMax(shader.maximumValue())
        #init connect signals
        self.ui.actionSetDefaultMB.triggered.connect(lambda : self.setBandSelection('defaultMB'))
        self.ui.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('TrueColor'))
        self.ui.actionSetCIR.triggered.connect(lambda: self.setBandSelection('CIR'))
        self.ui.actionSet453.triggered.connect(lambda: self.setBandSelection('453'))

        self.ui.actionSetDefaultSB.triggered.connect(lambda: self.setBandSelection('defaultSB'))
        self.ui.actionSetB.triggered.connect(lambda: self.setBandSelection('B'))
        self.ui.actionSetG.triggered.connect(lambda: self.setBandSelection('G'))
        self.ui.actionSetR.triggered.connect(lambda: self.setBandSelection('R'))
        self.ui.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
        self.ui.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


        self.ui.actionApplyStyle.triggered.connect(lambda : self.sigSensorRendererChanged.emit(self.layerRenderer()))
        self.ui.actionCopyStyle.triggered.connect(lambda : QApplication.clipboard().setMimeData(self.mimeDataStyle()))
        self.ui.actionPasteStyle.triggered.connect(lambda : self.pasteStyleFromClipboard())

        #self.ui.stackedWidget

        if not self.sensor.wavelengthsDefined():
            self.ui.btnTrueColor.setEnabled(False)
            self.ui.btnCIR.setEnabled(False)
            self.ui.btn453.setEnabled(False)

            self.ui.btnSingleBandBlue.setEnabled(False)
            self.ui.btnSingleBandGreen.setEnabled(False)
            self.ui.btnSingleBandRed.setEnabled(False)
            self.ui.btnSingleBandNIR.setEnabled(False)
            self.ui.btnSingleBandSWIR.setEnabled(False)

        #apply recent or default renderer
        renderer = lyr.renderer()

        #set defaults
        self.setLayerRenderer(self.defaultSB)
        self.setLayerRenderer(self.defaultMB)

        if type(renderer) in [QgsMultiBandColorRenderer, QgsSingleBandPseudoColorRenderer]:
            self.setLayerRenderer(renderer)


        QApplication.clipboard().dataChanged.connect(self.onClipboardChange)
        self.onClipboardChange()

    def onSensorNameChanged(self, newName):
        self.sensor.sigNameChanged.connect(self.ui.labelTitle.setText)
        self.ui.labelTitle.setText(self.sensor.name())
        self.ui.actionApplyStyle.setToolTip('Apply style to all map view images from "{}"'.format(self.sensor.name()))

    def pasteStyleFromClipboard(self):
        utils = TsvMimeDataUtils(QApplication.clipboard().mimeData())
        if utils.hasRasterStyle():
            renderer = utils.rasterStyle(self.sensor.bandDataType)
            if renderer is not None:
                self.setLayerRenderer(renderer)

    def applyStyle(self):
        self.sigSensorRendererChanged.emit(self.layerRenderer())

    def onClipboardChange(self):
        utils = TsvMimeDataUtils(QApplication.clipboard().mimeData())
        self.ui.btnPasteStyle.setEnabled(utils.hasRasterStyle())


    def setBandSelection(self, key):


        if key == 'defaultMB':
            bands = [self.defaultMB.redBand(), self.defaultMB.greenBand(), self.defaultMB.blueBand()]
        elif key == 'defaultSB':
            bands = [self.defaultSB.band()]

        else:
            if key in ['R','G','B','nIR','swIR']:
                colors = [key]
            elif key == 'TrueColor':
                colors = ['R','G','B']
            elif key == 'CIR':
                colors = ['nIR', 'R', 'G']
            elif key == '453':
                colors = ['nIR','swIR', 'R']
            bands = [self.sensor.bandClosestToWavelength(c) for c in colors]

        if len(bands) == 1:
            self.ui.sliderSingleBand.setValue(bands[0]+1)
        elif len(bands) == 3:
            for i, b in enumerate(bands):
                self.multiBandSliders[i].setValue(b+1)


    def rgb(self):
        return [self.ui.sliderRed.value(),
               self.ui.sliderGreen.value(),
               self.ui.sliderBlue.value()]

    SignalizeImmediately = True

    def updateUi(self, *args):
        rgb = self.rgb()

        text = 'RGB {}-{}-{}'.format(*rgb)

        if False and self.sensor.wavelengthsDefined():
            text += ' ({} {})'.format(
                ','.join(['{:0.2f}'.format(self.sensor.wavelengths[b-1]) for b in rgb]),
                self.sensor.wavelengthUnits)
        self.ui.labelSummary.setText(text)

        if MapViewSensorSettings.SignalizeImmediately:
            self.sigSensorRendererChanged.emit(self.layerRenderer())

    def setLayerRenderer(self, renderer):
        ui = self.ui
        assert isinstance(renderer, QgsRasterRenderer)

        updated = False
        if isinstance(renderer, QgsMultiBandColorRenderer):
            self.ui.cbRenderType.setCurrentIndex(0)
            #self.ui.stackedWidget.setcurrentWidget(self.ui.pageMultiBand)

            for s in self.multiBandSliders:
                s.blockSignals(True)
            ui.sliderRed.setValue(renderer.redBand())
            ui.sliderGreen.setValue(renderer.greenBand())
            ui.sliderBlue.setValue(renderer.blueBand())
            for s in self.multiBandSliders:
                s.blockSignals(False)

            ceRed = renderer.redContrastEnhancement()
            ceGreen = renderer.greenContrastEnhancement()
            ceBlue = renderer.blueContrastEnhancement()

            for i, ce in enumerate([ceRed, ceGreen, ceBlue]):
                self.multiBandMinValues[i].setText(str(ce.minimumValue()))
                self.multiBandMaxValues[i].setText(str(ce.maximumValue()))

            idx = self.ceAlgs.values().index(ceRed.contrastEnhancementAlgorithm())
            ui.comboBoxContrastEnhancement.setCurrentIndex(idx)
            #self.updateUi()
            updated = True

        if isinstance(renderer, QgsSingleBandPseudoColorRenderer):
            self.ui.cbRenderType.setCurrentIndex(1)
            #self.ui.stackedWidget.setCurrentWidget(self.ui.pageSingleBand)

            self.ui.sliderSingleBand.setValue(renderer.band())
            shader = renderer.shader()
            cmin = shader.minimumValue()
            cmax = shader.maximumValue()
            self.ui.tbSingleBandMin.setText(str(cmin))
            self.ui.tbSingleBandMax.setText(str(cmax))

            shaderFunc = shader.rasterShaderFunction()
            self.ui.cbSingleBandColorRampType.setCurrentIndex(shaderFunc.colorRampType())
            updated = True

        self.updateUi()
        if updated and MapViewSensorSettings.SignalizeImmediately:
            self.sigSensorRendererChanged.emit(renderer.clone())

    def mimeDataStyle(self):
        r = self.layerRenderer()
        doc = QDomDocument()
        root = doc.createElement('qgis')

        return None

    def currentComboBoxItem(self, cb):
        d = cb.itemData(cb.currentIndex(), Qt.UserRole)
        return d

    def layerRenderer(self):
        ui = self.ui
        r = None
        if ui.stackedWidget.currentWidget() == ui.pageMultiBand:
            r = QgsMultiBandColorRenderer(None,
                ui.sliderRed.value(), ui.sliderGreen.value(), ui.sliderBlue.value())

            i = self.ui.comboBoxContrastEnhancement.currentIndex()
            alg = self.ui.comboBoxContrastEnhancement.itemData(i)

            if alg == QgsContrastEnhancement.NoEnhancement:
                r.setRedContrastEnhancement(None)
                r.setGreenContrastEnhancement(None)
                r.setBlueContrastEnhancement(None)
            else:
                rgbEnhancements = []
                for i in range(3):
                    e = QgsContrastEnhancement(self.sensor.bandDataType)
                    minmax = [float(self.multiBandMinValues[i].text()), float(self.multiBandMaxValues[i].text())]
                    cmin = min(minmax)
                    cmax = max(minmax)
                    e.setMinimumValue(cmin)
                    e.setMaximumValue(cmax)
                    e.setContrastEnhancementAlgorithm(alg)
                    rgbEnhancements.append(e)
                r.setRedContrastEnhancement(rgbEnhancements[0])
                r.setGreenContrastEnhancement(rgbEnhancements[1])
                r.setBlueContrastEnhancement(rgbEnhancements[2])

        if ui.stackedWidget.currentWidget() == ui.pageSingleBand:
            r = QgsSingleBandPseudoColorRenderer(None, ui.sliderSingleBand.value(), None)
            minmax = [float(ui.tbSingleBandMin.text()), float(ui.tbSingleBandMax.text())]
            cmin = min(minmax)
            cmax = max(minmax)
            r.setClassificationMin(cmin)
            r.setClassificationMax(cmax)
            colorRamp = self.ui.cbSingleBandColorRamp.currentColorRamp()

            # fix: QGIS 3.0 constructor
            shaderFunc = QgsColorRampShader(cmin, cmax)
            shaderFunc.setColorRampType(self.currentComboBoxItem(ui.cbSingleBandColorRampType))
            shaderFunc.setClip(True)
            nSteps = 10
            colorRampItems = []
            diff = cmax - cmin
            for i in range(nSteps + 1):
                f = float(i) / nSteps
                color = colorRamp.color(f)
                value = cmin + diff * f
                colorRampItems.append(QgsColorRampShader.ColorRampItem(value, color))
            shaderFunc.setColorRampItemList(colorRampItems)
            shader = QgsRasterShader()
            shader.setMaximumValue(cmax)
            shader.setMinimumValue(cmin)
            shader.setRasterShaderFunction(shaderFunc)
            r.setShader(shader)

            s = ""
        return r



class PropertyDialogUI(QDialog, loadUIFormClass(PATH_SETTINGSDIALOG_UI)):

    def __init__(self, parent=None):
        super(PropertyDialogUI, self).__init__(parent)
        self.setupUi(self)



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()

    #run tests
    #d = AboutDialogUI()
    #d.show()

    d = PropertyDialogUI()
    d.exec_()
    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
