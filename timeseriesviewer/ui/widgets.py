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

import os
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtXml import *
import PyQt4.QtWebKit


import sys, re, os, six

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
        self.tabifyDockWidget(self.dockNavigation, self.dockRendering)
        self.tabifyDockWidget(self.dockNavigation, self.dockLabeling)
        #area = Qt.RightDockWidgetArea


        area = Qt.BottomDockWidgetArea
        self.dockSensors = addDockWidget(docks.SensorDockUI(self))
        self.dockMapViews = addDockWidget(docks.MapViewDockUI(self))
        self.dockProfiles = addDockWidget(docks.ProfileViewDockUI(self))
        self.dockTimeSeries = addDockWidget(docks.TimeSeriesDockUI(self))
        self.tabifyDockWidget(self.dockTimeSeries, self.dockMapViews)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)

        for dock in self.findChildren(QDockWidget):
            if len(dock.actions()) > 0:
                s = ""
            self.menuPanels.addAction(dock.toggleViewAction())




        self.dockTimeSeries.raise_()
        self.dockNavigation.raise_()

        self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)

        #connect QPushButtons
        self.dockRendering.btnRefresh.clicked.connect(self.actionRedraw.trigger)



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
        self.gbSyncQgs.setEnabled(b)
        self.gbQgsVectorLayer.setEnabled(b)

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

class MapViewDefinitionUI(QGroupBox, loadUIFormClass(PATH_MAPVIEWDEFINITION_UI)):

    sigHideMapView = pyqtSignal()
    sigShowMapView = pyqtSignal()

    def __init__(self, mapViewDefinition,parent=None):
        super(MapViewDefinitionUI, self).__init__(parent)

        self.setupUi(self)
        self.mMapViewDefinition = mapViewDefinition
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnMapViewVisibility.setDefaultAction(self.actionToggleVisibility)
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)
        self.actionToggleVisibility.toggled.connect(lambda: self.setVisibility(not self.actionToggleVisibility.isChecked()))

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

        self.btnDefault.setDefaultAction(self.actionSetDefault)
        self.btnTrueColor.setDefaultAction(self.actionSetTrueColor)
        self.btnCIR.setDefaultAction(self.actionSetCIR)
        self.btn453.setDefaultAction(self.actionSet453)

        self.btnPasteStyle.setDefaultAction(self.actionPasteStyle)
        self.btnCopyStyle.setDefaultAction(self.actionCopyStyle)
        self.btnApplyStyle.setDefaultAction(self.actionApplyStyle)


class TsvMapCanvas(QgsMapCanvas):

    saveFileDirectories = dict()
    #sigRendererChanged = pyqtSignal(QgsRasterRenderer)

    def __init__(self, tsdView, mapView, parent=None):
        super(TsvMapCanvas, self).__init__(parent)
        from timeseriesviewer.main import TimeSeriesDatumView, MapView
        assert isinstance(tsdView, TimeSeriesDatumView)
        assert isinstance(mapView, MapView)

        #the canvas
        self.setCrsTransformEnabled(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCanvasColor(SETTINGS.value('CANVAS_BACKGROUND_COLOR', QColor(0, 0, 0)))
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self.qgsInteraction = QgisTsvBridge.instance()

        self.tsdView = tsdView
        self.mapView = mapView
        self.sensorView = self.mapView.sensorViews[self.tsdView.Sensor]
        self.mapView.sigMapViewVisibility.connect(self.setVisible)
        self.mapView.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        self.referenceLayer = QgsRasterLayer(self.tsdView.TSD.pathImg)
        QgsMapLayerRegistry.instance().addMapLayer(self.referenceLayer, False)

        self.MapCanvasLayers = [QgsMapCanvasLayer(self.referenceLayer)]
        self.setLayerSet(self.MapCanvasLayers)
        #todo: handle QGIS interaction

        #set raster layer style

        self.sensorView.sigSensorRendererChanged.connect(self.setRenderer)
        self.setRenderer(self.sensorView.layerRenderer())


        self.MAPTOOLS = dict()
        self.MAPTOOLS['zoomOut'] = QgsMapToolZoom(self, True)
        self.MAPTOOLS['zoomIn'] = QgsMapToolZoom(self, False)
        self.MAPTOOLS['pan'] = QgsMapToolPan(self)

    def setVisibilityFromCollections(self):
        b = self.mapView.visibility() and self.tsdView.TSD.isVisible()
        self.setVisible(b)

    def pixmap(self):
        """
        Returns the current map image as pixmap
        :return:
        """
        return QPixmap(self.map().contentImage().copy())

    def contextMenuEvent(self, event):
        menu = QMenu()
        # add general options
        menu.addSeparator()
        action = menu.addAction('Stretch using current Extent')
        action = menu.addAction('Zoom to Layer')
        action.triggered.connect(lambda : self.setExtent(SpatialExtent(self.referenceLayer.crs(),self.referenceLayer.extent())))
        menu.addSeparator()


        action = menu.addAction('Copy to Clipboard')
        action.triggered.connect(lambda: QApplication.clipboard().setPixmap(self.pixmap()))
        m = menu.addMenu('Save as...')
        action = m.addAction('PNG')
        action.triggered.connect(lambda : self.saveMapImageDialog('PNG'))
        action = m.addAction('JPEG')
        action.triggered.connect(lambda: self.saveMapImageDialog('JPG'))


        if self.qgsInteraction:
            assert isinstance(self.qgsInteraction, QgisTsvBridge)
            action = m.addAction('Add layer to QGIS')

            action = m.addAction('Import extent from QGIS')
            action = m.addAction('Export extent to QGIS')
            s = ""




        menu.addSeparator()
        TSD = self.tsdView.TSD
        action = menu.addAction('Hide date')
        action.triggered.connect(lambda : self.tsdView.TSD.setVisibility(False))
        action = menu.addAction('Remove date')
        action.triggered.connect(lambda: TSD.timeSeries.removeDates([TSD]))
        action = menu.addAction('Remove map view')
        action.triggered.connect(lambda: self.mapView.sigRemoveMapView.emit(self.mapView))
        action = menu.addAction('Hide map view')
        action.triggered.connect(lambda: self.mapView.sigHideMapView.emit())


        menu.exec_(event.globalPos())

    def activateMapTool(self, key):
        if key is None:
            self.setMapTool(None)
        else:
            self.setMapTool(self.MAPTOOLS[key])

    def saveMapImageDialog(self, fileType):
        lastDir = SETTINGS.value('CANVAS_SAVE_IMG_DIR', os.path.expanduser('~'))
        path = jp(lastDir, '{}.{}.{}'.format(self.tsdView.TSD.date, self.mapView.title(), fileType.lower()))

        path = QFileDialog.getSaveFileName(self, 'Save map as {}'.format(fileType), path)
        if len(path) > 0:
            self.saveAsImage(path, None, fileType)
            SETTINGS.setValue('CANVAS_SAVE_IMG_DIR', os.path.dirname(path))


    def setRenderer(self, renderer, targetLayerUri=None):
        if targetLayerUri is None:
            targetLayerUri = str(self.referenceLayer.source())

        lyrs = [mcl.layer() for mcl in self.MapCanvasLayers if str(mcl.layer().source()) == targetLayerUri]
        assert len(lyrs) <= 1
        for lyr in lyrs:
            r = renderer.clone()
            r.setInput(lyr.dataProvider())
            lyr.setRenderer(r)

        self.refresh()
        a = ""
        #self.refreshMap()


    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            self.blockSignals(True)
            self.setDestinationCrs(spatialExtent.crs())
            self.setExtent(spatialExtent)
            self.blockSignals(False)
            self.refreshMap()

    def spatialExtent(self):
        return SpatialExtent.fromMapCanvas(self)



class MapViewSensorSettings(QObject):
    """
    Describes the rendering of images of one Sensor
    """

    sigSensorRendererChanged = pyqtSignal(QgsRasterRenderer)

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(MapViewSensorSettings, self).__init__(parent)

        self.ui = MapViewRenderSettingsUI(parent)
        self.ui.create()

        self.ui.labelTitle.setText(sensor.sensorName)
        self.ui.bandNames = sensor.bandNames
        self.minValues = [self.ui.tbRedMin, self.ui.tbGreenMin, self.ui.tbBlueMin]
        self.maxValues = [self.ui.tbRedMax, self.ui.tbGreenMax, self.ui.tbBlueMax]
        self.sliders = [self.ui.sliderRed, self.ui.sliderGreen, self.ui.sliderBlue]

        for tb in self.minValues + self.maxValues:
            tb.setValidator(QDoubleValidator())
        for sl in self.sliders:
            sl.setMinimum(1)
            sl.setMaximum(sensor.nb)
            sl.valueChanged.connect(self.updateUi)

        self.ceAlgs = [("No enhancement", QgsContrastEnhancement.NoEnhancement),
                       ("Stretch to MinMax", QgsContrastEnhancement.StretchToMinimumMaximum),
                       ("Stretch and clip to MinMax",QgsContrastEnhancement.StretchAndClipToMinimumMaximum),
                       ("Clip to MinMax", QgsContrastEnhancement.ClipToMinimumMaximum)]
        for item in self.ceAlgs:
            self.ui.comboBoxContrastEnhancement.addItem(item[0], item[1])


        from timeseriesviewer.timeseries import SensorInstrument
        assert isinstance(sensor, SensorInstrument)
        self.sensor = sensor

        lyr = QgsRasterLayer(self.sensor.refUri)
        renderer = lyr.renderer()

        #todo: support singleband and other renderers
        if not isinstance(renderer, QgsMultiBandColorRenderer):
            renderer = QgsMultiBandColorRenderer(lyr.dataProvider(), 0, 0, 0)
            e = QgsContrastEnhancement(self.sensor.bandDataType)
            bandStats = lyr.dataProvider().bandStatistics(0)
            e.setMinimumValue(bandStats.Min)
            e.setMaximumValue(bandStats.Max)
            e.setContrastEnhancementAlgorithm(QgsContrastEnhancement.ClipToMinimumMaximum)
            renderer.setRedContrastEnhancement(QgsContrastEnhancement(e))
            renderer.setGreenContrastEnhancement(QgsContrastEnhancement(e))
            renderer.setBlueContrastEnhancement(QgsContrastEnhancement(e))

        self.setLayerRenderer(renderer)

        #provide default min max
        self.defaultRGB = [renderer.redBand(), renderer.greenBand(), renderer.blueBand()]
        self.ui.actionSetDefault.triggered.connect(lambda : self.setBandSelection('default'))
        self.ui.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('TrueColor'))
        self.ui.actionSetCIR.triggered.connect(lambda: self.setBandSelection('CIR'))
        self.ui.actionSet453.triggered.connect(lambda: self.setBandSelection('453'))


        self.ui.actionApplyStyle.triggered.connect(lambda : self.sigSensorRendererChanged.emit(self.layerRenderer()))
        #self.ui.actionCopyStyle.triggered.connect(lambda : QApplication.clipboard().setMimeData(self.mimeDataStyle()))
        self.ui.actionPasteStyle.triggered.connect(lambda : self.pasteStyleFromClipboard())
        if not self.sensor.wavelengthsDefined():
            self.ui.btnTrueColor.setEnabled(False)
            self.ui.btnCIR.setEnabled(False)
            self.ui.btn453.setEnabled(False)

        QApplication.clipboard().dataChanged.connect(self.onClipboardChange)
        self.onClipboardChange()

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

        if key == 'default':
            bands = self.defaultRGB
        else:
            if key == 'TrueColor':
                colors = ['R','G','B']
            elif key == 'CIR':
                colors = ['nIR', 'R', 'G']
            elif key == '453':
                colors = ['nIR','swIR', 'R']
            bands = [self.sensor.bandClosestToWavelength(c) for c in colors]

        for i, b in enumerate(bands):
            self.sliders[i].setValue(b)
            #slider value change emits signal -> no emit required here

    def rgb(self):
        return [self.ui.sliderRed.value(),
               self.ui.sliderGreen.value(),
               self.ui.sliderBlue.value()]

    SignalizeImmediately = False
    def updateUi(self, *args):
        rgb = self.rgb()

        text = 'RGB {}-{}-{}'.format(*rgb)
        if self.sensor.wavelengthsDefined():
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
            for s in self.sliders:
                s.blockSignals(True)
            ui.sliderRed.setValue(renderer.redBand())
            ui.sliderGreen.setValue(renderer.greenBand())
            ui.sliderBlue.setValue(renderer.blueBand())
            for s in self.sliders:
                s.blockSignals(False)

            ceRed = renderer.redContrastEnhancement()
            ceGreen = renderer.greenContrastEnhancement()
            ceBlue = renderer.blueContrastEnhancement()

            algs = [i[1] for i in self.ceAlgs]
            ui.comboBoxContrastEnhancement.setCurrentIndex(algs.index(ceRed.contrastEnhancementAlgorithm()))
            #self.updateUi()
            updated = True
        self.updateUi()
        if updated and MapViewSensorSettings.SignalizeImmediately:
            self.sigSensorRendererChanged.emit(renderer.clone())




    def layerRenderer(self):
        ui = self.ui
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
                e.setMinimumValue(float(self.minValues[i].text()))
                e.setMaximumValue(float(self.maxValues[i].text()))
                e.setContrastEnhancementAlgorithm(alg)
                rgbEnhancements.append(e)
            r.setRedContrastEnhancement(rgbEnhancements[0])
            r.setGreenContrastEnhancement(rgbEnhancements[1])
            r.setBlueContrastEnhancement(rgbEnhancements[2])
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
