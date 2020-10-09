"""
***************************************************************************
    layerconfigwidget/rasterbands.py
        - A QgsMapLayerConfigWidget to select and change bands of QgsRasterRenderers
    -----------------------------------------------------------------------
    begin                : 2020-02-24
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

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
import typing
import pathlib
from qgis.core import *
from qgis.core import QgsRasterLayer, \
    QgsRasterRenderer, \
    QgsSingleBandGrayRenderer, \
    QgsSingleBandColorDataRenderer, \
    QgsSingleBandPseudoColorRenderer, \
    QgsMultiBandColorRenderer, \
    QgsPalettedRasterRenderer, \
    QgsColorRampShader, QgsRasterShaderFunction, QgsRasterShader
from qgis.gui import *
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsMapLayerConfigWidgetFactory, QgsRasterBandComboBox

from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import QIcon
import numpy as np
from ..layerconfigwidgets.core import QpsMapLayerConfigWidget
from ..utils import loadUi, parseWavelength, UnitLookup

class RasterBandConfigWidget(QpsMapLayerConfigWidget):

    @staticmethod
    def icon() -> QIcon:
        return QIcon(':/qps/ui/icons/rasterband_select.svg')

    def __init__(self, layer:QgsRasterLayer, canvas:QgsMapCanvas, parent:QWidget=None):

        super(RasterBandConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'rasterbandconfigwidget.ui'
        loadUi(pathUi, self)
        assert isinstance(layer, QgsRasterLayer)
        self.mCanvas = canvas
        self.mLayer = layer
        self.mLayer.rendererChanged.connect(self.syncToLayer)
        assert isinstance(self.cbSingleBand, QgsRasterBandComboBox)

        self.cbSingleBand.setLayer(self.mLayer)
        self.cbMultiBandRed.setLayer(self.mLayer)
        self.cbMultiBandGreen.setLayer(self.mLayer)
        self.cbMultiBandBlue.setLayer(self.mLayer)

        self.cbSingleBand.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandRed.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandGreen.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandBlue.bandChanged.connect(self.widgetChanged)

        assert isinstance(self.sliderSingleBand, QSlider)
        self.sliderSingleBand.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandRed.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandGreen.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandBlue.setRange(1, self.mLayer.bandCount())

        mWL, mWLUnit = parseWavelength(self.mLayer)
        if isinstance(mWL, list):
            mWL = np.asarray(mWL)

        if UnitLookup.isMetricUnit(mWLUnit):
            mWLUnit = UnitLookup.baseUnit(mWLUnit)
            # convert internally to nanometers
            if mWLUnit != 'nm':
                try:
                    mWL = UnitLookup.convertMetricUnit(mWL, mWLUnit, 'nm')
                    mWLUnit = 'nm'
                except:
                    mWL = None
                    mWLUnit = None

        self.mWL = mWL
        self.mWLUnit = mWLUnit

        hasWL = UnitLookup.isMetricUnit(self.mWLUnit)
        self.gbMultiBandWavelength.setEnabled(hasWL)
        self.gbSingleBandWavelength.setEnabled(hasWL)

        self.btnSetSBBand_B.clicked.connect(lambda: self.setWL(('B',)))
        self.btnSetSBBand_G.clicked.connect(lambda: self.setWL(('G',)))
        self.btnSetSBBand_R.clicked.connect(lambda: self.setWL(('R',)))
        self.btnSetSBBand_NIR.clicked.connect(lambda: self.setWL(('NIR',)))
        self.btnSetSBBand_SWIR1.clicked.connect(lambda: self.setWL(('SWIR1',)))
        self.btnSetSBBand_SWIR2.clicked.connect(lambda: self.setWL(('SWIR2',)))

        self.btnSetMBBands_RGB.clicked.connect(lambda: self.setWL(('R', 'G', 'B')))
        self.btnSetMBBands_NIRRG.clicked.connect(lambda: self.setWL(('NIR', 'R', 'G')))
        self.btnSetMBBands_SWIRNIRR.clicked.connect(lambda: self.setWL(('SWIR', 'NIR', 'R')))
        self.btnSetMBBands_NIRSWIRR.clicked.connect(lambda: self.setWL(('NIR', 'SWIR', 'R')))

        self.syncToLayer()

        self.setPanelTitle('Band Selection')

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        renderer = self.mLayer.renderer()
        self.setRenderer(renderer)

    def renderer(self) -> QgsRasterRenderer:
        oldRenderer = self.mLayer.renderer()
        newRenderer = None
        if isinstance(oldRenderer, QgsSingleBandGrayRenderer):
            newRenderer = oldRenderer.clone()
            newRenderer.setGrayBand(self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsSingleBandPseudoColorRenderer):
            # there is a bug when using the QgsSingleBandPseudoColorRenderer.setBand()
            # see https://github.com/qgis/QGIS/issues/31568
            # band = self.cbSingleBand.currentBand()
            vMin, vMax = oldRenderer.shader().minimumValue(), oldRenderer.shader().maximumValue()
            shader = QgsRasterShader(vMin, vMax)

            f = oldRenderer.shader().rasterShaderFunction()
            if isinstance(f, QgsColorRampShader):
                shaderFunction = QgsColorRampShader(f)
            else:
                shaderFunction = QgsRasterShaderFunction(f)

            shader.setRasterShaderFunction(shaderFunction)
            newRenderer = QgsSingleBandPseudoColorRenderer(oldRenderer.input(), self.cbSingleBand.currentBand(), shader)

        elif isinstance(oldRenderer, QgsPalettedRasterRenderer):
            newRenderer = QgsPalettedRasterRenderer(oldRenderer.input(), self.cbSingleBand.currentBand(),
                                                    oldRenderer.classes())

            # r.setBand(band)
        elif isinstance(oldRenderer, QgsSingleBandColorDataRenderer):
            newRenderer = QgsSingleBandColorDataRenderer(oldRenderer.input(), self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsMultiBandColorRenderer):
            newRenderer = oldRenderer.clone()
            newRenderer.setInput(oldRenderer.input())
            newRenderer.setRedBand(self.cbMultiBandRed.currentBand())
            newRenderer.setGreenBand(self.cbMultiBandGreen.currentBand())
            newRenderer.setBlueBand(self.cbMultiBandBlue.currentBand())
        return newRenderer

    def setRenderer(self, renderer: QgsRasterRenderer):
        if not isinstance(renderer, QgsRasterRenderer):
            return

        w = self.renderBandWidget
        assert isinstance(self.labelRenderType, QLabel)
        assert isinstance(w, QStackedWidget)
        self.labelRenderType.setText(str(renderer.type()))
        if isinstance(renderer, (
                QgsSingleBandGrayRenderer,
                QgsSingleBandColorDataRenderer,
                QgsSingleBandPseudoColorRenderer,
                QgsPalettedRasterRenderer)):
            w.setCurrentWidget(self.pageSingleBand)

            if isinstance(renderer, QgsSingleBandGrayRenderer):
                self.cbSingleBand.setBand(renderer.grayBand())

            elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                self.cbSingleBand.setBand(renderer.band())

            elif isinstance(renderer, QgsPalettedRasterRenderer):
                self.cbSingleBand.setBand(renderer.band())

            elif isinstance(renderer, QgsSingleBandColorDataRenderer):
                self.cbSingleBand.setBand(renderer.usesBands()[0])

        elif isinstance(renderer, QgsMultiBandColorRenderer):
            w.setCurrentWidget(self.pageMultiBand)
            self.cbMultiBandRed.setBand(renderer.redBand())
            self.cbMultiBandGreen.setBand(renderer.greenBand())
            self.cbMultiBandBlue.setBand(renderer.blueBand())

        else:
            w.setCurrentWidget(self.pageUnknown)

    def shouldTriggerLayerRepaint(self) -> bool:
        return True

    def apply(self):
        newRenderer = self.renderer()

        if isinstance(newRenderer, QgsRasterRenderer) and isinstance(self.mLayer, QgsRasterLayer):
            newRenderer.setInput(self.mLayer.dataProvider())
            self.mLayer.setRenderer(newRenderer)
            self.widgetChanged.emit()

    def wlBand(self, wlKey:str) -> int:
        """
        Returns the band number for a wavelength
        :param wlKey:
        :type wlKey:
        :return:
        :rtype:
        """
        from ..utils import LUT_WAVELENGTH
        if isinstance(self.mWL, np.ndarray):
            targetWL = float(LUT_WAVELENGTH[wlKey])
            return int(np.argmin(np.abs(self.mWL - targetWL)))+1
        else:
            return None

    def setWL(self, wlRegions:tuple):
        r = self.renderer().clone()
        if isinstance(r, (QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer, QgsSingleBandColorDataRenderer)):
            band = self.wlBand(wlRegions[0])
            self.cbSingleBand.setBand(band)
        elif isinstance(r, QgsMultiBandColorRenderer):
            bR = self.wlBand(wlRegions[0])
            bG = self.wlBand(wlRegions[1])
            bB = self.wlBand(wlRegions[2])

            self.cbMultiBandBlue.setBand(bB)
            self.cbMultiBandGreen.setBand(bG)
            self.cbMultiBandRed.setBand(bR)

        self.widgetChanged.emit()

    def setDockMode(self, dockMode:bool):
        pass

class RasterBandConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(RasterBandConfigWidgetFactory, self).__init__('Raster Band', RasterBandConfigWidget.icon())
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)
        self.setTitle('Band Selection')

    def supportsLayer(self, layer):
        if isinstance(layer, QgsRasterLayer):
            return True

        return False

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True

    def createWidget(self, layer, canvas, dockWidget=True, parent=None) -> QgsMapLayerConfigWidget:
        w = RasterBandConfigWidget(layer, canvas, parent=parent)
        return w

