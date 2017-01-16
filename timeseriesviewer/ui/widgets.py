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
import PyQt4.QtWebKit

import sys, re, os, six

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.ui import loadUIFormClass, DIR_UI
from timeseriesviewer.main import SpatialExtent

PATH_MAIN_UI = jp(DIR_UI, 'timeseriesviewer.ui')
PATH_MAPVIEWSETTINGS_UI = jp(DIR_UI, 'mapviewsettings.ui')
PATH_MAPVIEWRENDERSETTINGS_UI = jp(DIR_UI, 'mapviewrendersettings.ui')
PATH_MAPVIEWDEFINITION_UI = jp(DIR_UI, 'mapviewdefinition.ui')
PATH_TSDVIEW_UI = jp(DIR_UI, 'timeseriesdatumview.ui')
PATH_ABOUTDIALOG_UI = jp(DIR_UI, 'aboutdialog.ui')
PATH_SETTINGSDIALOG_UI = jp(DIR_UI, 'settingsdialog.ui')

PATH_PROFILEVIEWDOCK_UI = jp(DIR_UI, 'profileviewdock.ui')
PATH_RENDERINGDOCK_UI = jp(DIR_UI, 'renderingdock.ui')





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
        self.mCrs = None

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
        self.dockSensors = addDockWidget(docks.SensorDockUI(self))

        area = Qt.RightDockWidgetArea
        self.dockProfiles = addDockWidget(docks.ProfileViewDockUI(self))

        area = Qt.BottomDockWidgetArea
        self.dockMapViews = addDockWidget(docks.MapViewDockUI(self))

        for dock in self.findChildren(QDockWidget):
            self.menuPanels.addAction(dock.toggleViewAction())

        self.tabifyDockWidget(self.dockNavigation, self.dockRendering)
        self.tabifyDockWidget(self.dockNavigation, self.dockLabeling)

        self.tabifyDockWidget(self.dockTimeSeries, self.dockMapViews)
        self.tabifyDockWidget(self.dockTimeSeries, self.dockProfiles)

        self.dockTimeSeries.raise_()
        self.dockNavigation.raise_()


        self.btnNavToFirstTSD.setDefaultAction(self.actionFirstTSD)
        self.btnNavToLastTSD.setDefaultAction(self.actionLastTSD)
        self.btnNavToPreviousTSD.setDefaultAction(self.actionPreviousTSD)
        self.btnNavToNextTSD.setDefaultAction(self.actionNextTSD)

        self.btnAddTSD.setDefaultAction(self.actionAddTSD)
        self.btnRemoveTSD.setDefaultAction(self.actionRemoveTSD)
        self.btnLoadTS.setDefaultAction(self.actionLoadTS)
        self.btnSaveTS.setDefaultAction(self.actionSaveTS)
        self.btnClearTS.setDefaultAction(self.actionClearTS)
        self.dockMapViews.btnAddMapView.setDefaultAction(self.actionAddMapView)

        #connect QPushButtons
        self.btnRefresh.clicked.connect(self.actionRedraw.trigger)


        self.cbSyncQgsMapExtent.clicked.connect(self.syncExtent)
        self.cbSyncQgsMapCenter.clicked.connect(self.qgsSyncStateChanged)
        self.cbSyncQgsCRS.clicked.connect(self.qgsSyncStateChanged)

        self.cbQgsVectorLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)

        #define subset-size behaviour
        self.spinBoxSubsetSizeX.valueChanged.connect(lambda: self.onSubsetValueChanged('X'))
        self.spinBoxSubsetSizeY.valueChanged.connect(lambda: self.onSubsetValueChanged('Y'))


        self.subsetRatio = None
        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()




        self.subsetSizeWidgets    = [self.spinBoxSubsetSizeX, self.spinBoxSubsetSizeY]
        self.spatialExtentWidgets = [self.spinBoxExtentCenterX, self.spinBoxExtentCenterY,
                                     self.spinBoxExtentWidth, self.spinBoxExtentHeight]


        self.restoreSettings()




    def syncExtent(self, isChecked):
        if isChecked:
            self.cbSyncQgsMapCenter.setEnabled(False)
            self.cbSyncQgsMapCenter.blockSignals(True)
            self.cbSyncQgsMapCenter.setChecked(True)
            self.cbSyncQgsMapCenter.blockSignals(False)
        else:
            self.cbSyncQgsMapCenter.setEnabled(True)
        self.qgsSyncStateChanged()

    def qgsSyncState(self):
        return (self.cbSyncQgsMapCenter.isChecked(),
                self.cbSyncQgsMapExtent.isChecked(),
                self.cbSyncQgsCRS.isChecked())

    def qgsSyncStateChanged(self, *args):
        s = self.qgsSyncState()
        self.sigQgsSyncChanged.emit(s[0], s[1], s[2])

    def restoreSettings(self):
        from timeseriesviewer import SETTINGS

        #set last CRS
        self.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        s = ""


    def setQgsLinkWidgets(self):
        #enable/disable widgets that rely on QGIS instance interaction
        from timeseriesviewer import QGIS_TSV_BRIDGE
        from timeseriesviewer.main import QgsInstanceInteraction
        b = isinstance(QGIS_TSV_BRIDGE, QgsInstanceInteraction)
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



    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        old = self.mCrs
        self.mCrs = crs
        self.textBoxCRSInfo.setPlainText(crs.toWkt())
        if self.mCrs != old:
            self.sigCrsChanged.emit(crs)

    def crs(self):
        return self.mCrs

    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def spatialExtent(self):
        crs = self.crs()
        if not crs:
            return None
        width = QgsVector(self.spinBoxExtentWidth.value(), 0.0)
        height = QgsVector(0.0, self.spinBoxExtentHeight.value())

        Center = QgsPoint(self.spinBoxExtentCenterX.value(), self.spinBoxExtentCenterY.value())
        UL = Center - (width * 0.5) + (height * 0.5)
        LR = Center + (width * 0.5) - (height * 0.5)

        from timeseriesviewer.main import SpatialExtent
        return SpatialExtent(self.crs(), UL, LR)

    def setSpatialExtent(self, extent):
        old = self.spatialExtent()
        from timeseriesviewer.main import SpatialExtent
        assert isinstance(extent, SpatialExtent)
        center = extent.center()



        states = self._blockSignals(self.spatialExtentWidgets, True)

        self.spinBoxExtentCenterX.setValue(center.x())
        self.spinBoxExtentCenterY.setValue(center.y())
        self.spinBoxExtentWidth.setValue(extent.width())
        self.spinBoxExtentHeight.setValue(extent.height())
        self.setCrs(extent.crs())
        self._blockSignals(states)

        if extent != old:
            self.sigSpatialExtentChanged.emit(extent)




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

    def subsetSize(self):
        return QSize(self.spinBoxSubsetSizeX.value(),
                     self.spinBoxSubsetSizeY.value())


    def setProgress(self, value, valueMax=None, valueMin=0):
        p = self.progressBar
        if valueMin is not None and valueMin != self.progessBar.minimum():
            p.setMinimum(valueMin)
        if valueMax is not None and valueMax != self.progessBar.maximum():
            p.setMaximum(valueMax)
        self.progressBar.setValue(value)


    def onSubsetValueChanged(self, key):
        if self.checkBoxKeepSubsetAspectRatio.isChecked():

            if key == 'X':
                v_old = self.lastSubsetSizeX
                v_new = self.spinBoxSubsetSizeX.value()
                s = self.spinBoxSubsetSizeY
            elif key == 'Y':
                v_old = self.lastSubsetSizeY
                v_new = self.spinBoxSubsetSizeY.value()
                s = self.spinBoxSubsetSizeX

            oldState = s.blockSignals(True)
            s.setValue(int(round(float(v_new) / v_old * s.value())))
            s.blockSignals(oldState)

        self.lastSubsetSizeX = self.spinBoxSubsetSizeX.value()
        self.lastSubsetSizeY = self.spinBoxSubsetSizeY.value()

        self.actionSetSubsetSize.activate(QAction.Trigger)





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

class MapViewDefinitionUI(QFrame, loadUIFormClass(PATH_MAPVIEWDEFINITION_UI)):

    sigHideMapView = pyqtSignal()
    sigShowMapView = pyqtSignal()

    def __init__(self, mapViewDefinition,parent=None):
        super(MapViewDefinitionUI, self).__init__(parent)

        self.setupUi(self)
        self.mMapViewDefinition = mapViewDefinition
        self.btnRemoveMapView.setDefaultAction(self.actionRemoveMapView)
        self.btnMapViewVisibility.setDefaultAction(self.actionToggleVisibility)
        self.actionToggleVisibility.toggled.connect(lambda: self.setVisibility(not self.actionToggleVisibility.isChecked()))

    def mapViewDefinition(self):
        return self.mMapViewDefinition

    def setVisibility(self, isVisible):
        print(('Set to',isVisible))
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

        self.emptyHeight = self.height()
        self.setupUi(self)

    def sizeHint(self):

        w = self.minimumWidth()
        canvases = self.findChildren(MapViewMapCanvas)
        h = self.emptyHeight + len(canvases) * w
        return QSize(w,h)


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


class MapViewMapCanvas(QgsMapCanvas):

    def __init__(self, parent=None):
        super(MapViewMapCanvas, self).__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lyr = None
        self.renderer = None
        self.registry = QgsMapLayerRegistry.instance()

        self.setCanvasColor(SETTINGS.value('CANVAS_BACKGROUND_COLOR', QColor(0,0,0)))


        self.MAPTOOLS = dict()
        self.MAPTOOLS['zoomOut'] = QgsMapToolZoom(self, True)
        self.MAPTOOLS['zoomIn'] = QgsMapToolZoom(self, False)
        self.MAPTOOLS['pan'] = QgsMapToolPan(self)

    def activateMapTool(self, key):
        if key is None:
            self.setMapTool(None)
        else:
            self.setMapTool(self.MAPTOOLS[key])


    def setLayer(self, uri):
        assert isinstance(uri, str)
        self.setLayerSet([])
        if self.lyr is not None:
            #de-register layer
            self.registry.removeMapLayer(self.lyr)

        self.lyr = QgsRasterLayer(uri)
        self.lyr.setRenderer(self.renderer)
        self.registry.addMapLayer(self.lyr, False)
        lset = [QgsMapCanvasLayer(self.lyr)]

        from timeseriesviewer import QGIS_TSV_BRIDGE

        if QGIS_TSV_BRIDGE:
            lyrVec = QGIS_TSV_BRIDGE.getVectorLayerRepresentation()
            if lyrVec:
                self.registry.addMapLayer(lyrVec, False)
                lset.append(QgsMapCanvasLayer(self.lyr))
        lset = list(reversed(lset))
        self.setLayerSet(lset)

    def setRenderer(self, renderer):
        self.renderer = renderer.clone()

    def setSpatialExtent(self, spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        if self.spatialExtent() != spatialExtent:
            self.blockSignals(True)
            self.setDestinationCrs(spatialExtent.crs())
            self.setExtent(spatialExtent)
            self.blockSignals(False)
            self.refresh()

    def spatialExtent(self):
        return SpatialExtent.fromMapCanvas(self)



class MapViewRenderSettings(QObject):

    #define signals

    sigMapViewVisibility = pyqtSignal(bool)
    sigRendererChanged = pyqtSignal(QgsRasterRenderer)
    sigRemoveView = pyqtSignal()

    def __init__(self, sensor, parent=None):
        """Constructor."""
        super(MapViewRenderSettings, self).__init__(parent)

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
            sl.valueChanged.connect(self.layerRendererChanged)

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
        self.setLayerRenderer(renderer)

        #provide default min max
        self.defaultRGB = [renderer.redBand(), renderer.greenBand(), renderer.blueBand()]
        self.ui.actionSetDefault.triggered.connect(lambda : self.setBandSelection('default'))
        self.ui.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('TrueColor'))
        self.ui.actionSetCIR.triggered.connect(lambda: self.setBandSelection('CIR'))
        self.ui.actionSet453.triggered.connect(lambda: self.setBandSelection('453'))

        if not self.sensor.wavelengthsDefined():
            self.ui.btnTrueColor.setEnabled(False)
            self.ui.btnCIR.setEnabled(False)
            self.ui.btn453.setEnabled(False)


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

    def setRenderInfo(self, *args):
        rgb = self.rgb()

        text = 'RGB {}-{}-{}'.format(*rgb)
        if self.sensor.wavelengthsDefined():
            text += ' ({} {})'.format(
                ','.join(['{:0.2f}'.format(self.sensor.wavelengths[b-1]) for b in rgb]),
                self.sensor.wavelengthUnits)
        self.ui.labelSummary.setText(text)

    def setLayerRenderer(self, renderer):
        ui = self.ui
        assert isinstance(renderer, QgsRasterRenderer)

        if isinstance(renderer, QgsMultiBandColorRenderer):
            ui.sliderRed.setValue(renderer.redBand())
            ui.sliderGreen.setValue(renderer.greenBand())
            ui.sliderBlue.setValue(renderer.blueBand())

            ceRed = renderer.redContrastEnhancement()
            ceGreen = renderer.greenContrastEnhancement()
            ceBlue = renderer.blueContrastEnhancement()

            algs = [i[1] for i in self.ceAlgs]
            ui.comboBoxContrastEnhancement.setCurrentIndex(algs.index(ceRed.contrastEnhancementAlgorithm()))
            self.layerRendererChanged()

    def layerRendererChanged(self):
        self.setRenderInfo()
        self.sigRendererChanged.emit(self.layerRenderer())

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


        s = ""

    def contextMenuEvent(self, event):
        menu = QMenu()

        #add general options
        action = menu.addAction('Remove Band View')
        action.setToolTip('Removes this band view')
        action.triggered.connect(lambda : self.sigRemoveView.emit())
        #add QGIS specific options
        txt = QApplication.clipboard().text()
        if re.search('<!DOCTYPE(.|\n)*rasterrenderer.*type="multibandcolor"', txt) is not None:
            import qgis_add_ins
            action = menu.addAction('Paste style')
            action.setToolTip('Uses the QGIS raster layer style to specify band selection and band value ranges.')
            action.triggered.connect(lambda : self.setLayerRenderer(qgis_add_ins.paste_band_settings(txt)))


        menu.exec_(event.globalPos())

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
