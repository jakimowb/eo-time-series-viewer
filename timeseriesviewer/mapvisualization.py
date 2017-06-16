import os, sys, re, fnmatch, collections, copy, traceback, six, bisect
from future import *
import logging
logger = logging.getLogger(__name__)
from qgis.core import *
from PyQt4.QtXml import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import numpy as np
from timeseriesviewer.utils import *
from timeseriesviewer.main import TimeSeriesViewer
from timeseriesviewer.timeseries import SensorInstrument, TimeSeriesDatum
from timeseriesviewer.ui.docks import TsvDockWidgetBase, load
from timeseriesviewer.ui.widgets import TsvMimeDataUtils, maxWidgetSizes



class MapView(QObject):

    sigRemoveMapView = pyqtSignal(object)
    sigMapViewVisibility = pyqtSignal(bool)
    sigVectorVisibility = pyqtSignal(bool)

    sigTitleChanged = pyqtSignal(str)
    sigSensorRendererChanged = pyqtSignal(SensorInstrument, QgsRasterRenderer)
    from timeseriesviewer.crosshair import CrosshairStyle
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)
    sigShowCrosshair = pyqtSignal(bool)
    sigVectorLayerChanged = pyqtSignal()

    sigShowProfiles = pyqtSignal(SpatialPoint)

    def __init__(self, mapViewCollection, recommended_bands=None, parent=None):
        super(MapView, self).__init__()
        assert isinstance(mapViewCollection, MapViewCollection)
        self.mapViewCollection = mapViewCollection
        self.spatTempVis = mapViewCollection.spatTempVis
        self.ui = MapViewDefinitionUI(self, parent=parent)
        self.ui.create()

        self.mMapCanvases = []
        self.setVisibility(True)

        self.vectorLayer = None
        self.setVectorLayer(None)

        #forward actions with reference to this band view
        self.ui.actionRemoveMapView.triggered.connect(lambda: self.sigRemoveMapView.emit(self))
        self.ui.actionApplyStyles.triggered.connect(self.applyStyles)
        self.ui.actionShowCrosshair.toggled.connect(self.setShowCrosshair)
        self.ui.sigShowMapView.connect(lambda: self.sigMapViewVisibility.emit(True))
        self.ui.sigHideMapView.connect(lambda: self.sigMapViewVisibility.emit(False))
        self.ui.sigVectorVisibility.connect(self.sigVectorVisibility.emit)
        self.sensorViews = collections.OrderedDict()


    def setVectorLayer(self, lyr):
        if isinstance(lyr, QgsVectorLayer):
            self.vectorLayer = lyr
            self.vectorLayer.rendererChanged.connect(self.sigVectorLayerChanged)
            self.ui.btnVectorOverlayVisibility.setEnabled(True)


        else:
            self.vectorLayer = None
            self.ui.btnVectorOverlayVisibility.setEnabled(False)

        self.sigVectorLayerChanged.emit()

    def applyStyles(self):
        for sensorView in self.sensorViews.values():
            sensorView.applyStyle()
        s = ""


    def setVisibility(self, isVisible):
        self.ui.setVisibility(isVisible)

    def visibility(self):
        return self.ui.visibility()

    def visibleVectorOverlay(self):
        return isinstance(self.vectorLayer, QgsVectorLayer) and \
            self.ui.btnVectorOverlayVisibility.isChecked()



    def setTitle(self, title):
        self.mTitle = title
        #self.ui.setTitle('Map View' + title)
        self.sigTitleChanged.emit(self.mTitle)

    def title(self):
        return self.mTitle

    def setCrosshairStyle(self, crosshairStyle):
        self.sigCrosshairStyleChanged.emit(crosshairStyle)
    def setShowCrosshair(self, b):
        self.sigShowCrosshair.emit(b)

    def removeSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        if sensor in self.sensorViews.keys():
            w = self.sensorViews.pop(sensor)
            from timeseriesviewer.ui.widgets import MapViewSensorSettings
            assert isinstance(w, MapViewSensorSettings)
            l = self.ui.sensorList
            l.removeWidget(w.ui)
            w.ui.close()
            self.ui.adjustSize()
            return True
        else:
            return False

    def hasSensor(self, sensor):
        assert type(sensor) is SensorInstrument
        return sensor in self.sensorViews.keys()

    def registerMapCanvas(self, sensor, mapCanvas):
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        assert isinstance(sensor, SensorInstrument)

        #set basic settings
        sensorView = self.sensorViews[sensor]
        mapCanvas.setRenderer(sensorView.layerRenderer())

        #register signals
        sensorView.sigSensorRendererChanged.connect(mapCanvas.setRenderer)
        self.sigMapViewVisibility.connect(mapCanvas.refresh)
        self.sigCrosshairStyleChanged.connect(mapCanvas.setCrosshairStyle)
        self.sigShowCrosshair.connect(mapCanvas.setShowCrosshair)
        self.sigVectorLayerChanged.connect(mapCanvas.refresh)
        self.sigVectorVisibility.connect(mapCanvas.refresh)
        self.mMapCanvases.append(mapCanvas)



    def addSensor(self, sensor):
        """
        :param sensor:
        :return:
        """
        assert type(sensor) is SensorInstrument
        assert sensor not in self.sensorViews.keys()

        w = MapViewSensorSettings(sensor)

        #w.showSensorName(False)
        self.sensorViews[sensor] = w
        l = self.ui.sensorList
        i = l.count()
        l.addWidget(w.ui)
        self.ui.resize(self.ui.sizeHint())

    def getSensorWidget(self, sensor):
        assert type(sensor) is SensorInstrument
        return self.sensorViews[sensor]



class MapViewRenderSettingsUI(QGroupBox, load('mapviewrendersettings.ui')):

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



class DatumView(QObject):

    sigRenderProgress = pyqtSignal(int,int)
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigVisibilityChanged = pyqtSignal(bool)

    def __init__(self, timeSeriesDatum, timeSeriesDateViewCollection, mapViewCollection, parent=None):
        assert isinstance(timeSeriesDatum, TimeSeriesDatum)
        assert isinstance(timeSeriesDateViewCollection, DateViewCollection)
        assert isinstance(mapViewCollection, MapViewCollection)

        super(DatumView, self).__init__()
        from timeseriesviewer.ui.widgets import TimeSeriesDatumViewUI
        self.ui = TimeSeriesDatumViewUI(parent=parent)
        self.ui.create()

        self.L = self.ui.layout()
        self.wOffset = self.L.count()-1
        self.minHeight = self.ui.height()
        self.minWidth = 50
        self.renderProgress = dict()

        assert isinstance(mapViewCollection.spatTempVis, SpatialTemporalVisualization)
        self.STV = mapViewCollection.spatTempVis

        self.TSD = timeSeriesDatum
        self.scrollArea = timeSeriesDateViewCollection.scrollArea
        self.Sensor = self.TSD.sensor
        self.Sensor.sigNameChanged.connect(lambda :self.setColumnInfo())
        self.TSD.sigVisibilityChanged.connect(self.setVisibility)
        self.setColumnInfo()
        self.MVC = mapViewCollection
        self.DVC = timeSeriesDateViewCollection
        self.mapCanvases = dict()

    def setColumnInfo(self):

        labelTxt = '{}\n{}'.format(str(self.TSD.date), self.TSD.sensor.name())
        tooltip = '{}'.format(self.TSD.pathImg)

        self.ui.labelTitle.setText(labelTxt)
        self.ui.labelTitle.setToolTip(tooltip)

    def setVisibility(self, b):
        self.ui.setVisible(b)
        self.sigVisibilityChanged.emit(b)


    def setMapViewVisibility(self, bandView, isVisible):
        self.mapCanvases[bandView].setVisible(isVisible)

    def sizeHint(self):

        if not self.ui.isVisible():
            return QSize(0,0)

        l = len(self.mapCanvases)
        if l == 0:
            self.ui.sizeHint()
        else:
            baseSize = self.mapCanvases.values()[0].size()
            return QSize(baseSize.width(), l*baseSize.height())


    def removeMapView(self, mapView):
        canvas = self.mapCanvases.pop(mapView)
        self.L.removeWidget(canvas)
        canvas.close()
        self.adjustBaseMinSize()

    def refresh(self):
        if self.ui.isVisible():
            for c in self.mapCanvases.values():
                if c.isVisible():
                    c.refreshAllLayers()

    def insertMapView(self, mapView):
        assert isinstance(mapView, MapView)
        from timeseriesviewer.mapcanvas import MapCanvas

        mapCanvas = MapCanvas(self.ui)
        mapCanvas.blockSignals(True)
        self.registerMapCanvas(mapView, mapCanvas)

        # register MapCanvas on MV level
        mapView.registerMapCanvas(self.Sensor, mapCanvas)
        # register MapCanvas on STV level
        self.STV.registerMapCanvas(mapCanvas)
        mapCanvas.blockSignals(False)
        mapCanvas.refreshAllLayers()
        mapCanvas.refresh()

    def registerMapCanvas(self, mapView, mapCanvas):
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)
        self.mapCanvases[mapView] = mapCanvas
        rasterLyr = QgsRasterLayer(self.TSD.pathImg)
        QgsMapLayerRegistry.instance().addMapLayer(rasterLyr)
        mapCanvas.mLayers.append(rasterLyr)

        self.L.insertWidget(self.wOffset + len(self.mapCanvases), mapCanvas)
        self.ui.update()

        #register signals handled on (this) DV level
        mapCanvas.renderStarting.connect(lambda: self.sigLoadingStarted.emit(mapView, self.TSD))
        mapCanvas.mapCanvasRefreshed.connect(lambda: self.sigLoadingFinished.emit(mapView, self.TSD))
        mapCanvas.sigShowProfiles.connect(mapView.sigShowProfiles.emit)





        pass

    def __lt__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD < other.TSD

    def __eq__(self, other):
        assert isinstance(other, DatumView)
        return self.TSD == other.TSD

class SpatialTemporalVisualization(QObject):
    """

    """
    sigLoadingStarted = pyqtSignal(DatumView, MapView)
    sigLoadingFinished = pyqtSignal(DatumView, MapView)
    sigShowProfiles = pyqtSignal(SpatialPoint)
    sigShowMapLayerInfo = pyqtSignal(dict)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)
    sigMapSizeChanged = pyqtSignal(QSize)
    sigCRSChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigActivateMapTool = pyqtSignal(str)

    def __init__(self, timeSeriesViewer):
        super(SpatialTemporalVisualization, self).__init__()
        #assert isinstance(timeSeriesViewer, TimeSeriesViewer), timeSeriesViewer

        #default map settings
        self.mBlockCanvasSignals = False
        self.mSpatialExtent = SpatialExtent.world()
        self.mCRS = self.mSpatialExtent.crs()
        self.mSize = QSize(200,200)
        self.mColor = Qt.black
        self.mMapCanvases = []
        self.ui = timeSeriesViewer.ui
        self.scrollArea = self.ui.scrollAreaSubsets
        self.TSV = timeSeriesViewer
        self.TS = timeSeriesViewer.TS
        self.targetLayout = self.ui.scrollAreaSubsetContent.layout()
        self.dockMapViews = self.ui.dockMapViews
        self.MVC = MapViewCollection(self)
        self.MVC.sigShowProfiles.connect(self.sigShowProfiles.emit)

        self.vectorOverlay = None

        self.DVC = DateViewCollection(self)
        self.DVC.sigResizeRequired.connect(self.adjustScrollArea)
        self.DVC.sigLoadingStarted.connect(self.ui.dockRendering.addStartedWork)
        self.DVC.sigLoadingFinished.connect(self.ui.dockRendering.addFinishedWork)
        #self.timeSeriesDateViewCollection.sigSpatialExtentChanged.connect(self.setSpatialExtent)
        self.TS.sigTimeSeriesDatesAdded.connect(self.DVC.addDates)
        self.TS.sigTimeSeriesDatesRemoved.connect(self.DVC.removeDates)
        #add dates, if already existing
        self.DVC.addDates(self.TS[:])
        if len(self.TS) > 0:
            self.setSpatialExtent(self.TS.getMaxSpatialExtent())
        #self.setSubsetSize(QSize(100,50))

    def registerMapCanvas(self, mapCanvas):
        from timeseriesviewer.mapcanvas import MapCanvas
        assert isinstance(mapCanvas, MapCanvas)

        self.mMapCanvases.append(mapCanvas)

        #set general canvas properties
        mapCanvas.setFixedSize(self.mSize)
        mapCanvas.setCrs(self.mCRS)
        mapCanvas.setSpatialExtent(self.mSpatialExtent)


        #register on map canvas signals
        mapCanvas.sigSpatialExtentChanged.connect(lambda e: self.setSpatialExtent(e, mapCanvas))

        from timeseriesviewer.ui.widgets import TsvScrollArea
        assert isinstance(self.scrollArea, TsvScrollArea)
        self.scrollArea.sigResized.connect(mapCanvas.setRenderMe)
        self.scrollArea.horizontalScrollBar().valueChanged.connect(mapCanvas.setRenderMe)




    def setCrosshairStyle(self, crosshairStyle):
        from timeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setCrosshairStyle(crosshairStyle)

        #self.MVC.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        self.MVC.setShowCrosshair(b)

    def setVectorLayer(self, lyr):
        self.MVC.setVectorLayer(lyr)

    def createMapView(self):
        self.MVC.createMapView()

    def activateMapTool(self, key):
        from timeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.activateMapTool(key)

    def setMapSize(self, size):
        assert isinstance(size, QSize)
        self.mSize = size
        from timeseriesviewer.mapcanvas import MapCanvas
        for mapCanvas in self.mMapCanvases:
            assert isinstance(mapCanvas, MapCanvas)
            mapCanvas.setFixedSize(size)
        self.sigMapSizeChanged.emit(self.mSize)
        self.adjustScrollArea()

    def subsetSize(self):
        return QSize(self.mSize)

    def refresh(self):
        for tsdView in self.DVC:
            tsdView.refresh()


    def adjustScrollArea(self):
        #adjust scroll area widget to fit all visible widgets
        m = self.targetLayout.contentsMargins()
        n = len(self.DVC)
        w = h = 0

        s = QSize()
        r = None
        for TSDView in [v for v in self.DVC if v.ui.isVisible()]:
            s = s + TSDView.sizeHint()
            if r is None:
                r = TSDView.sizeHint()
        if r:
            if isinstance(self.targetLayout, QHBoxLayout):

                s = QSize(s.width(), r.height())
            else:
                s = QSize(r.width(), s.height())

            s = s + QSize(m.left() + m.right(), m.top() + m.bottom())
            self.targetLayout.parentWidget().setFixedSize(s)




    def setMaxTSDViews(self, n=-1):
        self.nMaxTSDViews = n
        #todo: remove views

    def setSpatialExtent(self, extent, mapCanvas0=None):
        if self.mBlockCanvasSignals:
            return True

        assert isinstance(extent, SpatialExtent)
        extent = extent.toCrs(self.mCRS)
        if not isinstance(extent, SpatialExtent) \
            or extent.isEmpty() or not extent.isFinite() \
            or extent.width() <= 0 \
            or extent.height() <= 0 \
            or extent == self.mSpatialExtent:
            return

        self.mBlockCanvasSignals = True
        self.mSpatialExtent = extent
        for mapCanvas in self.mMapCanvases:
            print('STV set EXTENT', str(mapCanvas))
            if mapCanvas != mapCanvas0:
                oldState = mapCanvas.blockSignals(True)
                mapCanvas.setExtent(extent)
                mapCanvas.blockSignals(oldState)
        self.mBlockCanvasSignals = False
        self.sigSpatialExtentChanged.emit(extent)

    def setBackgroundColor(self, color):
        assert isinstance(color, QColor)
        self.mColor = color

    def backgroundColor(self):
        return self.mColor


    def mapCanvasIterator(self):
        return self.mMapCanvases[:]

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if self.mCRS != crs:
            from timeseriesviewer.utils import saveTransform
            if saveTransform(self.mSpatialExtent, self.mCRS, crs):
                self.mCRS = crs
                for mapCanvas in self.mapCanvasIterator():
                    print(('STV set CRS {} {}', str(mapCanvas), self.mCRS.description()))
                    mapCanvas.setCrs(crs)
            else:
                pass
            self.sigCRSChanged.emit(self.mCRS)


    def crs(self):
        return self.mCRS

    def spatialExtent(self):
        return self.mSpatialExtent



    def navigateToTSD(self, TSD):
        assert isinstance(TSD, TimeSeriesDatum)
        #get widget related to TSD
        tsdv = self.DVC.tsdView(TSD)
        assert isinstance(self.scrollArea, QScrollArea)
        self.scrollArea.ensureWidgetVisible(tsdv.ui)

    def setMapViewVisibility(self, bandView, isVisible):
        assert isinstance(bandView, MapView)
        assert isinstance(isVisible, bool)

        for tsdv in self.TSDViews:
            tsdv.setMapViewVisibility(bandView, isVisible)


class DateViewCollection(QObject):

    sigResizeRequired = pyqtSignal()
    sigLoadingStarted = pyqtSignal(MapView, TimeSeriesDatum)
    sigLoadingFinished = pyqtSignal(MapView, TimeSeriesDatum)
    sigShowProfiles = pyqtSignal(SpatialPoint)
    sigSpatialExtentChanged = pyqtSignal(SpatialExtent)

    def __init__(self, STViz):
        assert isinstance(STViz, SpatialTemporalVisualization)
        super(DateViewCollection, self).__init__()
        #self.tsv = tsv
        #self.timeSeries = tsv.TS

        self.views = list()
        self.STV = STViz
        self.ui = self.STV.targetLayout.parentWidget()
        self.scrollArea = self.ui.parentWidget().parentWidget()
        #potentially there are many more dates than views.
        #therefore we implement the addinng/removing of mapviews here
        #we reduce the number of layout refresh calls by
        #suspending signals, adding the new map view canvases, and sending sigResizeRequired

        self.STV.MVC.sigMapViewAdded.connect(self.addMapView)
        self.STV.MVC.sigMapViewRemoved.connect(self.removeMapView)

        self.setFocusView(None)



    def tsdView(self, tsd):
        r = [v for v in self.views if v.TSD == tsd]
        if len(r) == 1:
            return r[0]
        else:
            raise Exception('TSD not in list')

    def addMapView(self, mapView):
        assert isinstance(mapView, MapView)
        w = self.ui
        w.setUpdatesEnabled(False)
        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(False)

        for tsdv in self.views:
            tsdv.insertMapView(mapView)

        for tsdv in self.views:
            tsdv.ui.setUpdatesEnabled(True)

        #mapView.sigSensorRendererChanged.connect(lambda *args : self.setRasterRenderer(mapView, *args))
        w.setUpdatesEnabled(True)
        self.sigResizeRequired.emit()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        for tsdv in self.views:
            tsdv.removeMapView(mapView)
        self.sigResizeRequired.emit()


    def setFocusView(self, tsd):
        self.focusView = tsd

    def orderedViews(self):
        #returns the
        if self.focusView is not None:
            assert isinstance(self.focusView, DatumView)
            return sorted(self.views,key=lambda v: np.abs(v.TSD.date - self.focusView.TSD.date))
        else:
            return self.views

    """
    def setSubsetSize(self, size):
        assert isinstance(size, QSize)
        self.subsetSize = size

        for tsdView in self.orderedViews():
            tsdView.blockSignals(True)

        for tsdView in self.orderedViews():
            tsdView.setSubsetSize(size)

        for tsdView in self.orderedViews():
            tsdView.blockSignals(False)
    """


    def addDates(self, tsdList):
        """
        Create a new TSDView
        :param tsdList:
        :return:
        """
        for tsd in tsdList:
            assert isinstance(tsd, TimeSeriesDatum)
            DV = DatumView(tsd, self, self.STV.MVC, parent=self.ui)
            #tsdView.setSubsetSize(self.subsetSize)
            DV.sigLoadingStarted.connect(self.sigLoadingStarted.emit)
            DV.sigLoadingFinished.connect(self.sigLoadingFinished.emit)
            DV.sigVisibilityChanged.connect(lambda: self.STV.adjustScrollArea())


            for i, mapView in enumerate(self.STV.MVC):
                DV.insertMapView(mapView)

            bisect.insort(self.views, DV)
            i = self.views.index(DV)

            DV.ui.setParent(self.STV.targetLayout.parentWidget())
            self.STV.targetLayout.insertWidget(i, DV.ui)
            DV.ui.show()

        if len(tsdList) > 0:
            self.sigResizeRequired.emit()

    def removeDates(self, tsdList):
        toRemove = [v for v in self.views if v.TSD in tsdList]
        removedDates = []
        for DV in toRemove:
            self.views.remove(DV)
            DV.ui.parent().layout().removeWidget(DV.ui)
            DV.ui.hide()
            DV.ui.close()
            removedDates.append(DV.TSD)
            del DV

        if len(removedDates) > 0:
            self.sigResizeRequired.emit()

    def __len__(self):
        return len(self.views)

    def __iter__(self):
        return iter(self.views)

    def __getitem__(self, slice):
        return self.views[slice]

    def __delitem__(self, slice):
        self.removeDates(self.views[slice])

class MapViewCollection(QObject):

    sigMapViewAdded = pyqtSignal(MapView)
    sigMapViewRemoved = pyqtSignal(MapView)
    sigSetMapViewVisibility = pyqtSignal(MapView, bool)
    sigShowProfiles = pyqtSignal(SpatialPoint)

    def __init__(self, spatialTemporalVisualization):
        assert isinstance(spatialTemporalVisualization, SpatialTemporalVisualization)
        super(MapViewCollection, self).__init__()
        self.spatTempVis = spatialTemporalVisualization
        self.spatTempVis.dockMapViews.actionApplyStyles.triggered.connect(self.applyStyles)
        self.spatTempVis.TS.sigSensorAdded.connect(self.addSensor)
        self.spatTempVis.TS.sigSensorRemoved.connect(self.removeSensor)
        self.ui = spatialTemporalVisualization.dockMapViews
        self.btnList = spatialTemporalVisualization.dockMapViews.BVButtonList
        self.scrollArea = spatialTemporalVisualization.dockMapViews.scrollAreaMapViews
        self.scrollAreaContent = spatialTemporalVisualization.dockMapViews.scrollAreaMapsViewDockContent
        self.mapViewsDefinitions = []
        self.mapViewButtons = dict()
        self.adjustScrollArea()

    def applyStyles(self):
        for mapView in self.mapViewsDefinitions:
            mapView.applyStyles()

    def setCrosshairStyle(self, crosshairStyle):
        for mapView in self.mapViewsDefinitions:
            mapView.setCrosshairStyle(crosshairStyle)

    def setShowCrosshair(self, b):
        for mapView in self.mapViewsDefinitions:
            mapView.setShowCrosshair(b)

    def index(self, mapView):
        assert isinstance(mapView, MapView)
        return self.mapViewsDefinitions.index(mapView)

    def adjustScrollArea(self):
        #adjust scroll area widget to fit all visible widgets
        l = self.scrollAreaContent.layout()
        from timeseriesviewer.ui.widgets import maxWidgetSizes
        newSize = maxWidgetSizes(l)
        #print(newSize)
        #newSize = self.scrollAreaContent.sizeHint()
        self.scrollAreaContent.setFixedSize(newSize)

    def setVectorLayer(self, lyr):
        for mapView in self.mapViewsDefinitions:
            assert isinstance(mapView, MapView)
            mapView.setVectorLayer(lyr)

    def addSensor(self, sensor):
        for mapView in self.mapViewsDefinitions:
            mapView.addSensor(sensor)
        self.adjustScrollArea()

    def removeSensor(self, sensor):
        for mapView in self.mapViewsDefinitions:
            mapView.removeSensor(sensor)

    def createMapView(self):

        btn = QToolButton(self.btnList)
        self.btnList.layout().insertWidget(self.btnList.layout().count() - 1, btn)

        mapView = MapView(self, parent=self.scrollArea)
        mapView.sigRemoveMapView.connect(self.removeMapView)
        mapView.sigShowProfiles.connect(self.sigShowProfiles.emit)

        for sensor in self.spatTempVis.TS.Sensors:
            mapView.addSensor(sensor)

        self.mapViewButtons[mapView] = btn
        self.mapViewsDefinitions.append(mapView)


        btn.clicked.connect(lambda : self.showMapViewDefinition(mapView))
        self.refreshMapViewTitles()
        if len(self) == 1:
            self.showMapViewDefinition(mapView)
        self.sigMapViewAdded.emit(mapView)
        self.adjustScrollArea()

    def removeMapView(self, mapView):
        assert isinstance(mapView, MapView)
        btn = self.mapViewButtons[mapView]

        idx = self.mapViewsDefinitions.index(mapView)

        self.mapViewsDefinitions.remove(mapView)
        self.mapViewButtons.pop(mapView)

        mapView.ui.setVisible(False)
        btn.setVisible(False)
        self.btnList.layout().removeWidget(btn)
        l = self.scrollAreaContent.layout()

        for d in self.recentMapViewDefinitions():
            d.ui.setVisible(False)
            l.removeWidget(d.ui)
        l.removeWidget(mapView.ui)
        mapView.ui.close()
        btn.close()
        self.refreshMapViewTitles()
        self.sigMapViewRemoved.emit(mapView)
        if len(self) > 0:
            #show previous mapViewDefinition
            idxNext = max([idx-1, 0])
            self.showMapViewDefinition(self.mapViewsDefinitions[idxNext])

    def refreshMapViewTitles(self):

        for i, mapView in enumerate(self.mapViewsDefinitions):
            number = i+1
            title = '#{}'.format(number)
            mapView.setTitle(title)
            btn = self.mapViewButtons[mapView]
            btn.setText('{}'.format(number))
            btn.setToolTip('Show definition for map view {}'.format(number))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)



    def showMapViewDefinition(self, mapViewDefinition):
        assert mapViewDefinition in self.mapViewsDefinitions
        assert isinstance(mapViewDefinition, MapView)
        l = self.scrollAreaContent.layout()

        for d in self.recentMapViewDefinitions():
            d.ui.setVisible(False)
            l.removeWidget(d.ui)

        l.insertWidget(l.count() - 1, mapViewDefinition.ui)
        mapViewDefinition.ui.setVisible(True)
        self.ui.setWindowTitle(self.ui.baseTitle + '|'+mapViewDefinition.title())

    def recentMapViewDefinitions(self):
        parent = self.scrollAreaContent
        return [ui.mapViewDefinition() for ui in parent.findChildren(MapViewDefinitionUI)]


    def setMapViewVisibility(self, bandView, isVisible):
        assert isinstance(bandView, MapView)
        assert isinstance(isVisible, bool)





    def __len__(self):
        return len(self.mapViewsDefinitions)

    def __iter__(self):
        return iter(self.mapViewsDefinitions)

    def __getitem__(self, key):
        return self.mapViewsDefinitions[key]

    def __contains__(self, mapView):
        return mapView in self.mapViewsDefinitions



class MapViewDefinitionUI(QGroupBox, load('mapviewdefinition.ui')):

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
        self.btnShowCrosshair.setDefaultAction(self.actionShowCrosshair)


        self.actionToggleVisibility.toggled.connect(lambda: self.setVisibility(not self.actionToggleVisibility.isChecked()))
        self.actionToggleVectorVisibility.toggled.connect(lambda : self.sigVectorVisibility.emit(self.actionToggleVectorVisibility.isChecked()))

    def sizeHint(self):

        #m = self.layout().contentsMargins()
        #sl = maxWidgetSizes(self.sensorList)
        #sm = self.buttonList.size()
        #w = sl.width() + m.left()+ m.right() + sm.width()
        #h = sl.height() + m.top() + m.bottom() + sm.height()
        return maxWidgetSizes(self.sensorList)
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


class MapViewDockUI(TsvDockWidgetBase, load('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.baseTitle = self.windowTitle()
        self.btnApplyStyles.setDefaultAction(self.actionApplyStyles)

        #self.dockLocationChanged.connect(self.adjustLayouts)

    def toggleLayout(self, p):
        newLayout = None
        l = p.layout()
        print('toggle layout {}'.format(str(p.objectName())))
        tmp = QWidget()
        tmp.setLayout(l)
        sMax = p.maximumSize()
        sMax.transpose()
        sMin = p.minimumSize()
        sMin.transpose()
        p.setMaximumSize(sMax)
        p.setMinimumSize(sMin)
        if isinstance(l, QVBoxLayout):
            newLayout = QHBoxLayout()
        else:
            newLayout = QVBoxLayout()
        print(l, '->', newLayout)

        while l.count() > 0:
            item = l.itemAt(0)
            l.removeItem(item)

            newLayout.addItem(item)


        p.setLayout(newLayout)
        return newLayout

    def adjustLayouts(self, area):
        return
        lOld = self.scrollAreaMapsViewDockContent.layout()
        if area in [Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea] \
            and isinstance(lOld, QVBoxLayout) or \
        area in [Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea] \
                        and isinstance(lOld, QHBoxLayout):

            #self.toogleLayout(self.scrollAreaMapsViewDockContent)
            self.toggleLayout(self.BVButtonList)
