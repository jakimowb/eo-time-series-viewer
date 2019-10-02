# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    layerproperties.py
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


import collections
import os
import re
import typing
from osgeo import gdal, ogr, osr
import numpy as np
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import QDomDocument

from .utils import *
from .models import OptionListModel, Option
from .classification.classificationscheme import ClassificationScheme, ClassInfo

"""
class RasterLayerProperties(QgsOptionsDialogBase):
    def __init__(self, lyr, canvas, parent, fl=Qt.Widget):
        super(RasterLayerProperties, self).__init__("RasterLayerProperties", parent, fl)
        # self.setupUi(self)
        self.initOptionsBase(False)
        title = "Layer Properties - {}".format(lyr.name())
        self.restoreOptionsBaseUi(title)
"""


"""
    RASTERRENDERER_CREATE_FUNCTIONS['multibandcolor'] = MultiBandColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['multibandcolor (QGIS)'] = QgsMultiBandColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['paletted'] = 
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandgray'] = 
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandgray (QGIS)'] = QgsSingleBandGrayRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandpseudocolor'] = SingleBandPseudoColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandpseudocolor (QGIS)'] = QgsSingleBandPseudoColorRendererWidget.create
"""

RENDER_CLASSES = {}
RENDER_CLASSES['rasterrenderer'] = {
    'singlebandpseudocolor':QgsSingleBandPseudoColorRenderer,
    'singlebandgray': QgsSingleBandGrayRenderer,
    'paletted':QgsPalettedRasterRenderer,
    'multibandcolor': QgsMultiBandColorRenderer,
    'hillshade': QgsHillshadeRenderer
}
RENDER_CLASSES['renderer-v2'] = {
    'categorizedSymbol':QgsCategorizedSymbolRenderer,
    'singleSymbol':QgsSingleSymbolRenderer
}
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)


MDF_QGIS_LAYER_STYLE = 'application/qgis.style'
MDF_TEXT_PLAIN = 'text/plain'

def openRasterLayerSilent(uri, name, provider)->QgsRasterLayer:
    """
    Opens a QgsRasterLayer without asking for its CRS in case it is undefined.
    :param uri: path
    :param name: name of layer
    :param provider: provider string
    :return: QgsRasterLayer
    """
    key = '/Projections/defaultBehavior'
    v = QgsSettings().value(key)
    isPrompt = v == 'prompt'

    if isPrompt:
        # do not ask!
        QgsSettings().setValue(key, 'useProject')

    loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
    lyr = QgsRasterLayer(uri, name, provider, options=loptions)

    if isPrompt:
        QgsSettings().setValue(key, v)
    return lyr

class SubDataSetInputTableModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):
        super(SubDataSetInputTableModel, self).__init__(*args, **kwds)

        self.cnID = '#'
        self.cnName = 'name'
        self.cnPath = 'path'

        self.cnSamples = 'ns'
        self.cnLines = 'nl'
        self.cnBands = 'nb'

        self.mInputBands = []





    def setSourceDataSet(self, ds:gdal.Dataset):
        pass



class SubDataSetSelectionDialog(QDialog, loadUI('subdatasetselectiondialog.ui')):


    pass


def rendererFromXml(xml):
    """
    Reads a string `text` and returns the first QgsRasterRenderer or QgsFeatureRenderer (if defined).
    :param xml: QMimeData | QDomDocument
    :return:
    """

    if isinstance(xml, QMimeData):
        for format in [MDF_QGIS_LAYER_STYLE, MDF_TEXT_PLAIN]:
        #for format in ['application/qgis.style', 'text/plain']:
            if format in xml.formats():
                dom  = QDomDocument()
                dom.setContent(xml.data(format))
                return rendererFromXml(dom)
        return None

    elif isinstance(xml, str):
        dom = QDomDocument()
        dom.setContent(xml)
        return rendererFromXml(dom)

    assert isinstance(xml, QDomDocument)
    root = xml.documentElement()
    for baseClass, renderClasses in RENDER_CLASSES.items():
        elements = root.elementsByTagName(baseClass)
        if elements.count() > 0:
            elem = elements.item(0).toElement()
            typeName = elem.attributes().namedItem('type').nodeValue()
            if typeName in renderClasses.keys():
                rClass = renderClasses[typeName]
                if baseClass == 'rasterrenderer':

                    return rClass.create(elem, DUMMY_RASTERINTERFACE)
                elif baseClass == 'renderer-v2':
                    context = QgsReadWriteContext()
                    return rClass.load(elem, context)
            else:
                print(typeName)
                s =""
    return None

def defaultRasterRenderer(layer:QgsRasterLayer, bandIndices:list=None, sampleSize:int=256)->QgsRasterRenderer:
    """
    Returns a default Raster Renderer.
    See https://bitbucket.org/hu-geomatics/enmap-box/issues/166/default-raster-visualization
    :param layer: QgsRasterLayer
    :return: QgsRasterRenderer
    """
    assert isinstance(sampleSize, int) and sampleSize > 0
    renderer = None

    if not isinstance(layer, QgsRasterLayer):
        return None

    defaultRenderer = layer.renderer()

    nb = layer.bandCount()

    if isinstance(bandIndices, list):
        bandIndices = [b for b in bandIndices if b >=0 and b < nb]
        l = len(bandIndices)
        if l == 0:
            bandIndices = None
        if l >= 3:
            bandIndices = bandIndices[0:3]
        elif l < 3:
            bandIndices = bandIndices[0:1]

    if not isinstance(bandIndices, list):
        if nb >= 3:

            if isinstance(defaultRenderer, QgsMultiBandColorRenderer):
                bandIndices = defaultBands(layer)
            else:
                bandIndices = [2, 1, 0]
        else:
            bandIndices = [0]

    assert isinstance(bandIndices, list)

    # get band stats
    bandStats = [layer.dataProvider().bandStatistics(b + 1, stats=QgsRasterBandStats.Min | QgsRasterBandStats.Max, sampleSize=sampleSize) for b in bandIndices]
    dp = layer.dataProvider()
    assert isinstance(dp, QgsRasterDataProvider)

    # classification ? -> QgsPalettedRasterRenderer
    classes = ClassificationScheme.fromMapLayer(layer)
    if isinstance(classes, ClassificationScheme):
        r = classes.rasterRenderer(band=bandIndices[0] + 1)
        r.setInput(layer.dataProvider())
        return r

    # single-band / two bands -> QgsSingleBandGrayRenderer
    if len(bandStats) < 3:
        b = bandIndices[0]+1
        stats = bandStats[0]
        assert isinstance(stats, QgsRasterBandStats)
        dt = dp.dataType(b)
        ce = QgsContrastEnhancement(dt)

        assert isinstance(ce, QgsContrastEnhancement)
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)

        if dt == Qgis.Byte:
            if stats.minimumValue == 0 and stats.maximumValue == 1:
                # handle mask, stretch over larger range
                ce.setMinimumValue(stats.minimumValue)
                ce.setMaximumValue(stats.maximumValue)
            else:
                ce.setMinimumValue(0)
                ce.setMaximumValue(255)
        else:
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            ce.setMinimumValue(vmin)
            ce.setMaximumValue(vmax)

        r = QgsSingleBandGrayRenderer(layer.dataProvider(), b)
        r.setContrastEnhancement(ce)
        return r

    # 3 or more bands -> RGB
    if len(bandStats) >= 3:
        bands = [b+1 for b in bandIndices[0:3]]
        contrastEnhancements = [QgsContrastEnhancement(dp.dataType(b)) for b in bands]
        ceR, ceG, ceB = contrastEnhancements

        for i, b in enumerate(bands):
            dt = dp.dataType(b)
            ce = contrastEnhancements[i]

            assert isinstance(ce, QgsContrastEnhancement)
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            if dt == Qgis.Byte:
                #standard RGB photo?
                if False and layer.bandCount() == 3:
                    ce.setMinimumValue(0)
                    ce.setMaximumValue(255)
                else:
                    ce.setMinimumValue(vmin)
                    ce.setMaximumValue(vmax)
            else:
                ce.setMinimumValue(vmin)
                ce.setMaximumValue(vmax)
        R, G, B = bands
        r = QgsMultiBandColorRenderer(layer.dataProvider(), R,G,B, None, None, None)
        r.setRedContrastEnhancement(ceR)
        r.setGreenContrastEnhancement(ceG)
        r.setBlueContrastEnhancement(ceB)
        r.setRedBand(R)
        r.setGreenBand(G)
        r.setBlueBand(B)
        return r
    if nb >= 3:
        pass

    return defaultRenderer


def rendererToXml(layerOrRenderer, geomType:QgsWkbTypes=None):
    """
    Returns a renderer XML representation
    :param layerOrRenderer: QgsRasterRender | QgsFeatureRenderer
    :return: QDomDocument
    """
    doc = QDomDocument()
    err = ''
    if isinstance(layerOrRenderer, QgsRasterLayer):
        return rendererToXml(layerOrRenderer.renderer())
    elif isinstance(layerOrRenderer, QgsVectorLayer):
        geomType = layerOrRenderer.geometryType()
        return rendererToXml(layerOrRenderer.renderer(), geomType=geomType)
    elif isinstance(layerOrRenderer, QgsRasterRenderer):
        #create a dummy raster layer
        import uuid
        xml = """<VRTDataset rasterXSize="1" rasterYSize="1">
                  <GeoTransform>  0.0000000000000000e+00,  1.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00, -1.0000000000000000e+00</GeoTransform>
                  <VRTRasterBand dataType="Float32" band="1">
                    <Metadata>
                      <MDI key="STATISTICS_MAXIMUM">0</MDI>
                      <MDI key="STATISTICS_MEAN">0</MDI>
                      <MDI key="STATISTICS_MINIMUM">0</MDI>
                      <MDI key="STATISTICS_STDDEV">0</MDI>
                    </Metadata>
                    <Description>Band 1</Description>
                    <Histograms>
                      <HistItem>
                        <HistMin>0</HistMin>
                        <HistMax>0</HistMax>
                        <BucketCount>1</BucketCount>
                        <IncludeOutOfRange>0</IncludeOutOfRange>
                        <Approximate>0</Approximate>
                        <HistCounts>0</HistCounts>
                      </HistItem>
                    </Histograms>
                  </VRTRasterBand>
                </VRTDataset>
                """
        path = '/vsimem/{}.vrt'.format(uuid.uuid4())
        drv = gdal.GetDriverByName('VRT')
        assert isinstance(drv, gdal.Driver)
        write_vsimem(path, xml)
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        ds.FlushCache()
        lyr = QgsRasterLayer(path)
        assert lyr.isValid()
        lyr.setRenderer(layerOrRenderer.clone())
        err = lyr.exportNamedStyle(doc)
        #remove dummy raster layer
        lyr = None
        drv.Delete(path)

    elif isinstance(layerOrRenderer, QgsFeatureRenderer) and geomType is not None:
        #todo: distinguish vector type from requested renderer
        typeName = QgsWkbTypes.geometryDisplayString(geomType)
        lyr = QgsVectorLayer('{}?crs=epsg:4326&field=id:integer'.format(typeName), 'dummy', 'memory')
        lyr.setRenderer(layerOrRenderer.clone())
        err = lyr.exportNamedStyle(doc)
        lyr = None
    else:
        raise NotImplementedError()


    return doc

def pasteStyleToClipboard(layer: QgsMapLayer):

    xml = rendererToXml(layer)
    if isinstance(xml, QDomDocument):
        md = QMimeData()
        # ['application/qgis.style', 'text/plain']

        md.setData('application/qgis.style', xml.toByteArray())
        md.setData('text/plain', xml.toByteArray())
        QApplication.clipboard().setMimeData(md)

def pasteStyleFromClipboard(layer:QgsMapLayer):
    mimeData = QApplication.clipboard().mimeData()
    renderer = rendererFromXml(mimeData)
    if isinstance(renderer, QgsRasterRenderer) and isinstance(layer, QgsRasterLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    elif isinstance(renderer, QgsFeatureRenderer) and isinstance(layer, QgsVectorLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()


def subLayerDefinitions(mapLayer:QgsMapLayer)->typing.List[QgsSublayersDialog.LayerDefinition]:
    """

    :param mapLayer:QgsMapLayer
    :return: list of sublayer definitions
    """
    definitions = []
    dp = mapLayer.dataProvider()

    subLayers = dp.subLayers()
    if len(subLayers) == 0:
        return []

    for i, sub in enumerate(subLayers):
        ldef = QgsSublayersDialog.LayerDefinition()
        assert isinstance(ldef, QgsSublayersDialog.LayerDefinition)
        elements = sub.split(QgsDataProvider.SUBLAYER_SEPARATOR)


        if dp.name() == 'ogr':
            # <layer_index>:<name>:<feature_count>:<geom_type>
            if len(elements) < 4:
                continue

            ldef.layerId = int(elements[0])
            ldef.layerName = elements[1]
            ldef.count = int(elements[2])
            ldef.type = elements[3]

            definitions.append(ldef)

        elif dp.name() == 'gdal':
            ldef.layerId = i

            # remove driver name and file name
            name = elements[0]
            name = name.replace(mapLayer.source(), '')
            name = re.sub('^(netcdf|hdf):', '', name, flags=re.I)
            name = re.sub('^[:"]+', '', name)
            name = re.sub('[:"]+$', '', name)
            ldef.layerName = name

            definitions.append(ldef)

        else:
            s = ""

    return definitions

def subLayers(mapLayer:QgsMapLayer, subLayers:list=None)->typing.List[QgsMapLayer]:
    """
    Returns a list of QgsMapLayer instances extracted from the input QgsMapLayer.
    Returns the "parent" QgsMapLayer in case no sublayers can be extracted
    :param mapLayer: QgsMapLayer
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    dp = mapLayer.dataProvider()


    uriParts = QgsProviderRegistry.instance().decodeUri(mapLayer.providerType(), mapLayer.dataProvider().dataSourceUri())
    uri = uriParts['path']
    if subLayers is None:
        ldefs = subLayerDefinitions(mapLayer)
    else:
        ldefs = subLayers

    if len(ldefs) == 0:
        layers = [mapLayer]
    else:
        uniqueNames = len(set([d.layerName for d in ldefs])) == len(ldefs)
        options = QgsProject.instance().transformContext()
        options.loadDefaultStyle = False

        fileName = os.path.basename(uri)

        if dp.name() == 'ogr':

            for ldef in ldefs:
                assert isinstance(ldef, QgsSublayersDialog.LayerDefinition)
                if uniqueNames:
                    composedURI = '{}|layername={}'.format(uri, ldef.layerName)
                else:
                    composedURI = '{}|layerid={}'.format(uri, ldef.layerId)

                name = '{} {}'.format(fileName, ldef.layerName)

                lyr = QgsVectorLayer(composedURI, name, dp.name())
                layers.append(lyr)

        elif dp.name() == 'gdal':
            subLayers = dp.subLayers()
            for ldef in ldefs:
                name = '{} {}'.format(fileName, ldef.layerName)
                lyr = QgsRasterLayer(subLayers[ldef.layerId], name, dp.name())
                layers.append(lyr)

        else:
            layers.append(mapLayer)

    return layers


class LabelFieldModel(QgsFieldModel):
    """
    A model to show the QgsFields of an QgsVectorLayer.
    Inherits QgsFieldModel and allows to change the name of the 1st column.
    """
    def __init__(self, parent):
        """
        Constructor
        :param parent:
        """
        super(LabelFieldModel, self).__init__(parent)
        self.mColumnNames = ['Fields']

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        """
        Returns header data
        :param col: int
        :param orientation: Qt.Horizontal | Qt.Vertical
        :param role:
        :return: value
        """
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setHeaderData(self, col, orientation, value, role=Qt.EditRole):
        """
        Sets the header data.
        :param col: int
        :param orientation:
        :param value: any
        :param role:
        """
        result = False

        if role == Qt.EditRole:
            if orientation == Qt.Horizontal and col < len(self.mColumnNames) and isinstance(value, str):
                self.mColumnNames[col] = value
                result = True

        if result == True:
            self.headerDataChanged.emit(orientation, col, col)
        return result

class FieldConfigEditorWidget(QWidget):

    class ConfigInfo(QStandardItem):
        """
        Describes a QgsEditorWidgetFactory configuration.
        """
        def __init__(self, key:str, factory:QgsEditorWidgetFactory, configWidget:QgsEditorConfigWidget):
            super(FieldConfigEditorWidget.ConfigInfo, self).__init__()

            assert isinstance(key, str)
            assert isinstance(factory, QgsEditorWidgetFactory)
            assert isinstance(configWidget, QgsEditorConfigWidget)
            self.mKey = key
            self.mFactory = factory
            self.mConfigWidget = configWidget
            self.setText(factory.name())
            self.setToolTip(factory.name())
            self.mInitialConfig = dict(configWidget.config())


        def resetConfig(self):
            """
            Resets the widget to its initial values
            """
            self.mConfigWidget.setConfig(dict(self.mInitialConfig))

        def factoryKey(self)->str:
            """
            Returns the QgsEditorWidgetFactory key, e.g. "CheckBox"
            :return: str
            """
            return self.mKey

        def factoryName(self)->str:
            """
            Returns the QgsEditorWidgetFactory name, e.g. "Checkbox"
            :return: str
            """
            return self.factory().name()

        def config(self)->dict:
            """
            Returns the config dictionary
            :return: dict
            """
            return self.mConfigWidget.config()

        def configWidget(self)->QgsEditorConfigWidget:
            """
            Returns the QgsEditorConfigWidget
            :return: QgsEditorConfigWidget
            """
            return self.mConfigWidget

        def factory(self)->QgsEditorWidgetFactory:
            """
            Returns the QgsEditorWidgetFactory
            :return: QgsEditorWidgetFactory
            """
            return self.mFactory

        def editorWidgetSetup(self)->QgsEditorWidgetSetup:
            """
            Creates a QgsEditorWidgetSetup
            :return: QgsEditorWidgetSetup
            """
            return QgsEditorWidgetSetup(self.factoryKey(), self.config())


    sigChanged = pyqtSignal(object)

    def __init__(self, parent, layer:QgsVectorLayer, index:int):
        super(FieldConfigEditorWidget, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        assert isinstance(layer, QgsVectorLayer)
        assert isinstance(index, int)

        self.mLayer = layer
        self.mField = layer.fields().at(index)
        assert isinstance(self.mField, QgsField)
        self.mFieldIndex = index

        self.mFieldNameLabel = QLabel(parent)
        self.mFieldNameLabel.setText(self.mField.name())

        self.layout().addWidget(self.mFieldNameLabel)

        self.gbWidgetType = QgsCollapsibleGroupBox(self)
        self.gbWidgetType.setTitle('Widget Type')
        self.gbWidgetType.setLayout(QVBoxLayout())
        self.cbWidgetType = QComboBox(self.gbWidgetType)

        self.stackedWidget = QStackedWidget(self.gbWidgetType)
        self.gbWidgetType.layout().addWidget(self.cbWidgetType)
        self.gbWidgetType.layout().addWidget(self.stackedWidget)




        currentSetup = self.mLayer.editorWidgetSetup(self.mFieldIndex)
        #self.mInitialConf = currentSetup.config()
        refkey = currentSetup.type()
        if refkey == '':
            refkey = QgsGui.editorWidgetRegistry().findBest(self.mLayer, self.mField.name()).type()

        self.mItemModel = QStandardItemModel(parent=self.cbWidgetType)

        iCurrent = -1
        i = 0
        factories = QgsGui.editorWidgetRegistry().factories()
        for key, fac in factories.items():
            assert isinstance(key, str)
            assert isinstance(fac, QgsEditorWidgetFactory)
            score = fac.fieldScore(self.mLayer, self.mFieldIndex)
            configWidget = fac.configWidget(self.mLayer, self.mFieldIndex, self.stackedWidget)

            if isinstance(configWidget, QgsEditorConfigWidget):
                configWidget.changed.connect(lambda: self.sigChanged.emit(self))
                self.stackedWidget.addWidget(configWidget)
                confItem = FieldConfigEditorWidget.ConfigInfo(key, fac, configWidget)
                if key == refkey:
                    iCurrent = i
                confItem.setEnabled(score > 0)
                confItem.setData(self, role=Qt.UserRole)
                self.mItemModel.appendRow(confItem)

                i += 1

        self.cbWidgetType.setModel(self.mItemModel)
        self.cbWidgetType.currentIndexChanged.connect(self.updateConfigWidget)

        self.layout().addWidget(self.gbWidgetType)
        self.layout().addStretch()
        self.cbWidgetType.setCurrentIndex(iCurrent)


        conf = self.currentFieldConfig()
        if isinstance(conf, FieldConfigEditorWidget.ConfigInfo):
            self.mInitialFactoryKey = conf.factoryKey()
            self.mInitialConf = conf.config()
        else:
            s = ""


    def setFactory(self, factoryKey:str):
        """
        Shows the QgsEditorConfigWidget of QgsEditorWidgetFactory `factoryKey`
        :param factoryKey: str
        """
        for i in range(self.mItemModel.rowCount()):
            confItem = self.mItemModel.item(i)
            assert isinstance(confItem, FieldConfigEditorWidget.ConfigInfo)
            if confItem.factoryKey() == factoryKey:
                self.cbWidgetType.setCurrentIndex(i)
                break


    def changed(self)->bool:
        """
        Returns True if the QgsEditorWidgetFactory or its configuration has been changed
        :return: bool
        """
        w = self.currentEditorConfigWidget()
        assert isinstance(w, QgsEditorConfigWidget)

        recentConfigInfo = self.currentFieldConfig()

        if self.mInitialFactoryKey != recentConfigInfo.factoryKey():
            return True
        elif self.mInitialConf != recentConfigInfo.config():
            return True

        return False

    def apply(self):
        """
        Applies the
        :return:
        """
        if self.changed():
            configInfo = self.currentFieldConfig()
            self.mInitialConf = configInfo.config()
            self.mInitialFactoryKey = configInfo.factoryKey()
            setup = QgsEditorWidgetSetup(self.mInitialFactoryKey, self.mInitialConf)
            self.mLayer.setEditorWidgetSetup(self.mFieldIndex, setup)

    def reset(self):
        """
        Resets the widget to its initial status
        """
        if self.changed():

            self.setFactory(self.mInitialFactoryKey)
            self.currentEditorConfigWidget().setConfig(self.mInitialConf)

    def currentFieldConfig(self)->ConfigInfo:
        i = self.cbWidgetType.currentIndex()
        return self.mItemModel.item(i)

    def currentEditorConfigWidget(self)->QgsEditorConfigWidget:
        return self.currentFieldConfig().configWidget()


    def updateConfigWidget(self, index):
        self.stackedWidget.setCurrentIndex(index)
        fieldConfig = self.currentFieldConfig()
        if isinstance(fieldConfig, FieldConfigEditorWidget.ConfigInfo):

            self.sigChanged.emit(self)


class LayerFieldConfigEditorWidget(QWidget, loadUI('layerfieldconfigeditorwidget.ui')):
    """
    A widget to set QgsVetorLayer field settings
    """
    def __init__(self, parent, *args, **kwds):
        super(LayerFieldConfigEditorWidget, self).__init__(parent,  *args, **kwds)
        self.setupUi(self)

        self.scrollArea.resizeEvent = self.onScrollAreaResize
        self.mFieldModel = LabelFieldModel(self)
        self.treeView.setModel(self.mFieldModel)
        self.treeView.selectionModel().currentRowChanged.connect(self.onSelectedFieldChanged)

        self.btnApply = self.buttonBox.button(QDialogButtonBox.Apply)
        self.btnReset = self.buttonBox.button(QDialogButtonBox.Reset)
        self.btnApply.clicked.connect(self.onApply)
        self.btnReset.clicked.connect(self.onReset)

    def onSelectedFieldChanged(self, index1:QModelIndex, index2:QModelIndex):
        """
        Shows the widget for the selected QgsField
        :param index1:
        :param index2:
        """
        if isinstance(index1, QModelIndex) and index1.isValid():
            r = index1.row()
            if r < 0 or r >= self.stackedWidget.count():
                s = ""
            self.stackedWidget.setCurrentIndex(r)

    def onScrollAreaResize(self, resizeEvent:QResizeEvent):
        """
        Forces the stackedWidget's width to fit into the scrollAreas viewport
        :param resizeEvent: QResizeEvent
        """
        assert isinstance(resizeEvent, QResizeEvent)
        self.stackedWidget.setMaximumWidth(resizeEvent.size().width())
        s  =""

    def onReset(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.reset()
        self.onSettingsChanged()

    def onApply(self):
        """
        Applies all changes to the QgsVectorLayer
        :return:
        """

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.apply()
        self.onSettingsChanged()


    def setLayer(self, layer:QgsVectorLayer):
        """
        Sets the QgsVectorLayer
        :param layer:
        """
        self.mFieldModel.setLayer(layer)
        self.updateFieldWidgets()

    def layer(self)->QgsVectorLayer:
        """
        Returns the current QgsVectorLayer
        :return:
        """
        return self.mFieldModel.layer()

    def updateFieldWidgets(self):
        """
        Empties the stackedWidget and populates it with a FieldConfigEditor
        for each QgsVectorLayer field.
        """
        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)
        i = sw.count() - 1
        while i >= 0:
            w = sw.widget(i)
            w.setParent(None)
            i -= 1

        lyr = self.layer()
        if isinstance(lyr, QgsVectorLayer):
            for i in range(lyr.fields().count()):
                w = FieldConfigEditorWidget(sw, lyr, i)
                w.sigChanged.connect(self.onSettingsChanged)
                sw.addWidget(w)

        self.onSettingsChanged()

    def onSettingsChanged(self):
        """
        Enables/disables buttons
        :return:
        """
        b = False
        for i in range(self.stackedWidget.count()):
            w = self.stackedWidget.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            if w.changed():
                b = True
                break

        self.btnReset.setEnabled(b)
        self.btnApply.setEnabled(b)



class RendererWidgetModifications(object):


    def __init__(self):
        self.mBandComboBoxes = []

    def modifyGridLayout(self):
        gridLayoutOld = self.layout().children()[0]
        self.gridLayout = QGridLayout()
        while gridLayoutOld.count() > 0:
            w = gridLayoutOld.takeAt(0)
            w = w.widget()
            gridLayoutOld.removeWidget(w)
            w.setVisible(False)
            setattr(self, w.objectName(), w)
        self.layout().removeItem(gridLayoutOld)
        self.layout().insertItem(0, self.gridLayout)
        self.gridLayout.setSpacing(2)
        self.layout().addStretch()

    def connectSliderWithBandComboBox(self, slider, combobox):
        """
        Connects a band-selection slider with a band-selection combobox
        :param widget: QgsRasterRendererWidget
        :param slider: QSlider to show the band number
        :param combobox: QComboBox to show the band name
        :return:
        """
        assert isinstance(self, QgsRasterRendererWidget)
        assert isinstance(slider, QSlider)
        assert isinstance(combobox, QComboBox)

        # init the slider
        nb = self.rasterLayer().dataProvider().bandCount()
        slider.setTickPosition(QSlider.TicksAbove)
        slider.valueChanged.connect(combobox.setCurrentIndex)
        slider.setMinimum(1)
        slider.setMaximum(nb)
        intervals = [1, 2, 5, 10, 25, 50]
        for interval in intervals:
            if nb / interval < 10:
                break
        slider.setTickInterval(interval)
        slider.setPageStep(interval)

        def onBandValueChanged(self, idx, slider):
            assert isinstance(self, QgsRasterRendererWidget)
            assert isinstance(idx, int)
            assert isinstance(slider, QSlider)

            # i = slider.value()
            slider.blockSignals(True)
            slider.setValue(idx)
            slider.blockSignals(False)

            # self.minMaxWidget().setBands(myBands)
            # self.widgetChanged.emit()

        if self.comboBoxWithNotSetItem(combobox):
            combobox.currentIndexChanged[int].connect(lambda idx: onBandValueChanged(self, idx, slider))
        else:
            combobox.currentIndexChanged[int].connect(lambda idx: onBandValueChanged(self, idx + 1, slider))

    def comboBoxWithNotSetItem(self, cb):
        assert isinstance(cb, QComboBox)
        return cb.itemData(0, role=Qt.DisplayRole).lower() == 'not set'

    def setLayoutItemVisibility(self, grid, isVisible):
        assert isinstance(self, QgsRasterRendererWidget)
        for i in range(grid.count()):
            item = grid.itemAt(i)
            if isinstance(item, QLayout):
                s = ""
            elif isinstance(item, QWidgetItem):
                item.widget().setVisible(isVisible)
                item.widget().setParent(self)
            else:
                s = ""

    def setBandSelection(self, key):
        if key == 'default':
            bands = defaultBands(self.rasterLayer())
        else:
            colors = re.split('[ ,;:]', key)

            bands = [bandClosestToWavelength(self.rasterLayer(), c) for c in colors]

        n = min(len(bands), len(self.mBandComboBoxes))
        for i in range(n):
            cb = self.mBandComboBoxes[i]
            bandIndex = bands[i]
            if self.comboBoxWithNotSetItem(cb):
                cb.setCurrentIndex(bandIndex+1)
            else:
                cb.setCurrentIndex(bandIndex)


    def fixBandNames(self, comboBox):
        """
        Changes the QGIS default bandnames ("Band 001") to more meaning ful information including gdal.Dataset.Descriptions.
        :param widget:
        :param comboBox:
        """
        assert isinstance(self, QgsRasterRendererWidget)
        if type(comboBox) is QComboBox:
            bandNames = displayBandNames(self.rasterLayer())
            for i in range(comboBox.count()):
                # text = cb.itemText(i)
                if i > 0:
                    comboBox.setItemText(i, bandNames[i - 1])
        else:
            raise NotImplementedError()


class SingleBandGrayRendererWidget(QgsSingleBandGrayRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandGrayRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandGrayRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()
        self.mGrayBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mGrayBandComboBox)
        self.fixBandNames(self.mGrayBandComboBox)
        self.connectSliderWithBandComboBox(self.mGrayBandSlider, self.mGrayBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()

        self.gridLayout.addWidget(self.mGrayBandLabel, 0, 0)
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 4, Qt.AlignLeft)

        self.gridLayout.addWidget(self.mGrayBandSlider, 1, 1, 1, 2)
        self.gridLayout.addWidget(self.mGrayBandComboBox, 1, 3,1,2)

        self.gridLayout.addWidget(self.label, 2, 0)
        self.gridLayout.addWidget(self.mGradientComboBox, 2, 1, 1, 4)

        self.gridLayout.addWidget(self.mMinLabel, 3, 1)
        self.gridLayout.addWidget(self.mMinLineEdit, 3, 2)
        self.gridLayout.addWidget(self.mMaxLabel, 3, 3)
        self.gridLayout.addWidget(self.mMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementLabel, 4, 0)
        self.gridLayout.addWidget(self.mContrastEnhancementComboBox, 4, 1, 1 ,4)
        self.gridLayout.setSpacing(2)

        self.setLayoutItemVisibility(self.gridLayout, True)

        self.mDefaultRenderer = layer.renderer()


    def initActionButtons(self):
            wl, wlu = parseWavelength(self.rasterLayer())
            self.wavelengths = wl
            self.wavelengthUnit = wlu

            self.mBtnBar.setLayout(QHBoxLayout())
            self.mBtnBar.layout().addStretch()
            self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
            self.mBtnBar.layout().setSpacing(2)

            self.actionSetDefault = QAction('Default', None)
            self.actionSetRed = QAction('R', None)
            self.actionSetGreen = QAction('G', None)
            self.actionSetBlue = QAction('B', None)
            self.actionSetNIR = QAction('nIR', None)
            self.actionSetSWIR = QAction('swIR', None)

            self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
            self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
            self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
            self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
            self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
            self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


            def addBtnAction(action):

                btn = QToolButton()
                btn.setDefaultAction(action)
                self.mBtnBar.layout().addWidget(btn)
                self.insertAction(None, action)
                return btn

            self.btnDefault = addBtnAction(self.actionSetDefault)
            self.btnRed = addBtnAction(self.actionSetRed)
            self.btnGreen = addBtnAction(self.actionSetGreen)
            self.btnBlue = addBtnAction(self.actionSetRed)
            self.btnNIR = addBtnAction(self.actionSetNIR)
            self.btnSWIR = addBtnAction(self.actionSetSWIR)

            b = self.wavelengths is not None
            for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
                a.setEnabled(b)



class SingleBandPseudoColorRendererWidget(QgsSingleBandPseudoColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return SingleBandPseudoColorRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(SingleBandPseudoColorRendererWidget, self).__init__(layer, extent)

        self.gridLayout = self.layout().children()[0]
        assert isinstance(self.gridLayout, QGridLayout)
        for i in range(self.gridLayout.count()):
            w = self.gridLayout.itemAt(i)
            w = w.widget()
            if isinstance(w, QWidget):
                setattr(self, w.objectName(), w)

        toReplace = [self.mBandComboBox,self.mMinLabel,self.mMaxLabel, self.mMinLineEdit, self.mMaxLineEdit ]
        for w in toReplace:
            self.gridLayout.removeWidget(w)
            w.setVisible(False)
        self.mBandSlider = QSlider(Qt.Horizontal)
        self.mBandComboBoxes.append(self.mBandComboBox)
        self.fixBandNames(self.mBandComboBox)
        self.connectSliderWithBandComboBox(self.mBandSlider, self.mBandComboBox)

        self.mBtnBar = QFrame()
        self.initActionButtons()
        grid = QGridLayout()
        grid.addWidget(self.mBtnBar,0,0,1,4, Qt.AlignLeft)
        grid.addWidget(self.mBandSlider, 1,0, 1,2)
        grid.addWidget(self.mBandComboBox, 1,2, 1,2)
        grid.addWidget(self.mMinLabel, 2, 0)
        grid.addWidget(self.mMinLineEdit, 2, 1)
        grid.addWidget(self.mMaxLabel, 2, 2)
        grid.addWidget(self.mMaxLineEdit, 2, 3)
        #grid.setContentsMargins(2, 2, 2, 2, )
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 2)
        grid.setSpacing(2)
        self.gridLayout.addItem(grid, 0,1,2,4)
        self.gridLayout.setSpacing(2)
        self.setLayoutItemVisibility(grid, True)


    def initActionButtons(self):
            wl, wlu = parseWavelength(self.rasterLayer())
            self.wavelengths = wl
            self.wavelengthUnit = wlu

            self.mBtnBar.setLayout(QHBoxLayout())
            self.mBtnBar.layout().addStretch()
            self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
            self.mBtnBar.layout().setSpacing(2)

            self.actionSetDefault = QAction('Default', None)
            self.actionSetRed = QAction('R', None)
            self.actionSetGreen = QAction('G', None)
            self.actionSetBlue = QAction('B', None)
            self.actionSetNIR = QAction('nIR', None)
            self.actionSetSWIR = QAction('swIR', None)

            self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
            self.actionSetRed.triggered.connect(lambda: self.setBandSelection('R'))
            self.actionSetGreen.triggered.connect(lambda: self.setBandSelection('G'))
            self.actionSetBlue.triggered.connect(lambda: self.setBandSelection('B'))
            self.actionSetNIR.triggered.connect(lambda: self.setBandSelection('nIR'))
            self.actionSetSWIR.triggered.connect(lambda: self.setBandSelection('swIR'))


            def addBtnAction(action):
                btn = QToolButton()
                btn.setDefaultAction(action)
                self.mBtnBar.layout().addWidget(btn)
                self.insertAction(None, action)
                return btn

            self.btnDefault = addBtnAction(self.actionSetDefault)
            self.btnRed = addBtnAction(self.actionSetRed)
            self.btnGreen = addBtnAction(self.actionSetGreen)
            self.btnBlue = addBtnAction(self.actionSetRed)
            self.btnNIR = addBtnAction(self.actionSetNIR)
            self.btnSWIR = addBtnAction(self.actionSetSWIR)

            b = self.wavelengths is not None
            for a in [self.actionSetRed, self.actionSetGreen, self.actionSetBlue, self.actionSetNIR, self.actionSetSWIR]:
                a.setEnabled(b)




class MultiBandColorRendererWidget(QgsMultiBandColorRendererWidget, RendererWidgetModifications):
    @staticmethod
    def create(layer, extent):
        return MultiBandColorRendererWidget(layer, extent)

    def __init__(self, layer, extent):
        super(MultiBandColorRendererWidget, self).__init__(layer, extent)

        self.modifyGridLayout()

        self.mRedBandSlider = QSlider(Qt.Horizontal)
        self.mGreenBandSlider = QSlider(Qt.Horizontal)
        self.mBlueBandSlider = QSlider(Qt.Horizontal)

        self.mBandComboBoxes.extend([self.mRedBandComboBox, self.mGreenBandComboBox, self.mBlueBandComboBox])
        self.mSliders = [self.mRedBandSlider, self.mGreenBandSlider, self.mBlueBandSlider]
        nb = self.rasterLayer().dataProvider().bandCount()
        for cbox, slider in zip(self.mBandComboBoxes, self.mSliders):
            self.connectSliderWithBandComboBox(slider, cbox)


        self.fixBandNames(self.mRedBandComboBox)
        self.fixBandNames(self.mGreenBandComboBox)
        self.fixBandNames(self.mBlueBandComboBox)

        self.mBtnBar = QFrame()
        self.mBtnBar.setLayout(QHBoxLayout())
        self.initActionButtons()
        self.mBtnBar.layout().addStretch()
        self.mBtnBar.layout().setContentsMargins(0, 0, 0, 0)
        self.mBtnBar.layout().setSpacing(2)

        #self.gridLayout.deleteLater()
#        self.gridLayout = newGrid
        self.gridLayout.addWidget(self.mBtnBar, 0, 1, 1, 3)
        self.gridLayout.addWidget(self.mRedBandLabel, 1, 0)
        self.gridLayout.addWidget(self.mRedBandSlider, 1, 1)
        self.gridLayout.addWidget(self.mRedBandComboBox, 1, 2)
        self.gridLayout.addWidget(self.mRedMinLineEdit, 1, 3)
        self.gridLayout.addWidget(self.mRedMaxLineEdit, 1, 4)

        self.gridLayout.addWidget(self.mGreenBandLabel, 2, 0)
        self.gridLayout.addWidget(self.mGreenBandSlider, 2, 1)
        self.gridLayout.addWidget(self.mGreenBandComboBox, 2, 2)
        self.gridLayout.addWidget(self.mGreenMinLineEdit, 2, 3)
        self.gridLayout.addWidget(self.mGreenMaxLineEdit, 2, 4)

        self.gridLayout.addWidget(self.mBlueBandLabel, 3, 0)
        self.gridLayout.addWidget(self.mBlueBandSlider, 3, 1)
        self.gridLayout.addWidget(self.mBlueBandComboBox, 3, 2)
        self.gridLayout.addWidget(self.mBlueMinLineEdit, 3, 3)
        self.gridLayout.addWidget(self.mBlueMaxLineEdit, 3, 4)

        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmLabel, 4, 0, 1, 2)
        self.gridLayout.addWidget(self.mContrastEnhancementAlgorithmComboBox, 4, 2, 1, 3)

        self.setLayoutItemVisibility(self.gridLayout, True)


        self.mRedBandLabel.setText('R')
        self.mGreenBandLabel.setText('G')
        self.mBlueBandLabel.setText('B')

        self.mDefaultRenderer = layer.renderer()

        self.minMaxWidget().resizeEvent = self.onMinMaxResize

    def onMinMaxResize(self, resizeEvent:QResizeEvent):

        s = ""



    def initActionButtons(self):

        wl, wlu = parseWavelength(self.rasterLayer())
        self.wavelengths = wl
        self.wavelengthUnit = wlu

        self.actionSetDefault = QAction('Default', None)
        self.actionSetTrueColor = QAction('RGB', None)
        self.actionSetCIR = QAction('nIR', None)
        self.actionSet453 = QAction('swIR', None)

        self.actionSetDefault.triggered.connect(lambda: self.setBandSelection('default'))
        self.actionSetTrueColor.triggered.connect(lambda: self.setBandSelection('R,G,B'))
        self.actionSetCIR.triggered.connect(lambda: self.setBandSelection('nIR,R,G'))
        self.actionSet453.triggered.connect(lambda: self.setBandSelection('nIR,swIR,R'))


        def addBtnAction(action):
            btn = QToolButton()
            btn.setDefaultAction(action)
            self.mBtnBar.layout().addWidget(btn)
            self.insertAction(None, action)
            return btn

        self.btnDefault = addBtnAction(self.actionSetDefault)
        self.btnTrueColor = addBtnAction(self.actionSetTrueColor)
        self.btnCIR = addBtnAction(self.actionSetCIR)
        self.btn453 = addBtnAction(self.actionSet453)

        b = self.wavelengths is not None
        for a in [self.actionSetCIR, self.actionSet453, self.actionSetTrueColor]:
            a.setEnabled(b)



class MapLayerModel(QgsMapLayerModel):

    def __init__(self, *args, **kwds):
        super(MapLayerModel, self).__init__(*args, **kwds)

    def data(self, index, role):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            s = ""
        else:

            return super(MapLayerModel, self).data(index, role)


class RasterLayerProperties(QgsOptionsDialogBase, loadUI('rasterlayerpropertiesdialog.ui')):
    def __init__(self, lyr, canvas, parent=None):
        """Constructor."""
        title = 'RasterLayerProperties'
        super(RasterLayerProperties, self).__init__(title, parent, Qt.Dialog, settings=None)
        #super(RasterLayerProperties, self).__init__(parent, Qt.Dialog)

        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use auto connect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        #self.restoreOptionsBaseUi('TITLE')
        self.mRasterLayer = lyr
        self.mRendererWidget = None

        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas(self)
            canvas.setVisible(False)
            canvas.setLayers([lyr])
            canvas.setExtent(canvas.fullExtent())

        self.canvas = canvas

        self.oldStyle = self.mRasterLayer.styleManager().style(self.mRasterLayer.styleManager().currentStyle())

        self.accepted.connect(self.apply)
        self.rejected.connect(self.onCancel)
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        # connect controls
        self.initOptionsBase(False, title)
        self.initOptsGeneral()
        self.initOptsStyle()
        self.initOptsTransparency()
        self.initOptsMetadata()

    def setRendererWidget(self, rendererName:str):
        pass


    def initOptsGeneral(self):
        rl = self.mRasterLayer

        assert isinstance(rl, QgsRasterLayer)
        dp = rl.dataProvider()
        name = rl.name()
        if name == '':
            name = os.path.basename(rl.source())

        self.tb_layername.setText(name)
        self.tb_layersource.setText(rl.source())

        self.tb_columns.setText('{}'.format(dp.xSize()))
        self.tb_rows.setText('{}'.format(dp.ySize()))
        self.tb_bands.setText('{}'.format(dp.bandCount()))

        #mapUnits = ['m','km','ft','nmi','yd','mi','deg','ukn']
        #mapUnit = rl.crs().mapUnits()
        #mapUnit = mapUnits[mapUnit] if mapUnit < len(mapUnits) else 'ukn'
        mapUnit = QgsUnitTypes.toString(rl.crs().mapUnits())

        self.tb_pixelsize.setText('{0}{2} x {1}{2}'.format(rl.rasterUnitsPerPixelX(),rl.rasterUnitsPerPixelY(), mapUnit))
        self.tb_nodata.setText('{}'.format(dp.sourceNoDataValue(1)))


        se = SpatialExtent.fromLayer(rl)
        pt2str = lambda xy: '{} ; {}'.format(xy[0], xy[1])
        self.tb_upperLeft.setText(pt2str(se.upperLeft()))
        self.tb_upperRight.setText(pt2str(se.upperRight()))
        self.tb_lowerLeft.setText(pt2str(se.lowerLeft()))
        self.tb_lowerRight.setText(pt2str(se.lowerRight()))

        self.tb_width.setText('{} {}'.format(se.width(), mapUnit))
        self.tb_height.setText('{} {}'.format(se.height(), mapUnit))
        self.tb_center.setText(pt2str((se.center().x(), se.center().y())))

        self.mCrsSelector.setCrs(self.mRasterLayer.crs())
        s = ""


    def onCurrentRendererWidgetChanged(self, *args):
        self.mRendererStackedWidget
        assert isinstance(self.mRendererStackedWidget, QStackedWidget)
        cw = self.mRendererStackedWidget.currentWidget()

        assert isinstance(cw, QgsRasterRendererWidget)
        cw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cw.adjustSize()
        self.mRendererStackedWidget.adjustSize()



    def initOptsStyle(self):


        self.mRendererStackedWidget.currentChanged.connect(self.onCurrentRendererWidgetChanged)

        self.mRenderTypeComboBox.setModel(RASTERRENDERER_CREATE_FUNCTIONSV2)
        renderer = self.mRasterLayer.renderer()
        iCurrent = None
        for i, constructor in enumerate(RASTERRENDERER_CREATE_FUNCTIONSV2.optionValues()):
            extent = self.canvas.extent()
            w = constructor(self.mRasterLayer, extent)
            w.setMapCanvas(self.canvas)
            #w.sizePolicy().setVerticalPolicy(QSizePolicy.Maximum)
            assert isinstance(w, QgsRasterRendererWidget)
            w.setRasterLayer(self.mRasterLayer)
            minMaxWidget = w.minMaxWidget()
            if isinstance(minMaxWidget, QgsRasterMinMaxWidget):
                minMaxWidget.setCollapsed(False)
            w.setParent(self.mRendererStackedWidget)
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.mRendererStackedWidget.addWidget(w)

            if type(w.renderer()) == type(renderer):
                iCurrent = i

            try:
                w.setFromRenderer(renderer)

                if isinstance(w, QgsSingleBandPseudoColorRendererWidget) and isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                    w.setMin(renderer.classificationMin())
                    w.setMax(renderer.classificationMax())
                elif isinstance(w, QgsSingleBandPseudoColorRendererWidget) and isinstance(renderer, QgsSingleBandGrayRenderer):
                    pass

            except Exception as ex:
                s = ""

        if isinstance(iCurrent, int):
            self.mRenderTypeComboBox.setCurrentIndex(iCurrent)




    def initOptsTransparency(self):

        r = self.mRasterLayer.renderer()
        if isinstance(r, QgsRasterRenderer):
            self.sliderOpacity.setValue(r.opacity()*100)


        def updateOpactiyText():
            self.lblTransparencyPercent.setText(r'{}%'.format(self.sliderOpacity.value()))

        self.sliderOpacity.valueChanged.connect(updateOpactiyText)
        updateOpactiyText()

    def initOptsMetadata(self):

        s = ""



    def onCancel(self):
        #restore style
        if self.oldStyle.xmlData() != self.mRasterLayer.styleManager().style(
                self.mRasterLayer.styleManager().currentStyle()
        ).xmlData():

            s = ""
        self.setResult(QDialog.Rejected)

    def apply(self):

        mRendererWidget = self.mRendererStackedWidget.currentWidget()
        if isinstance(mRendererWidget, QgsRasterRendererWidget):
            mRendererWidget.doComputations()
            renderer = mRendererWidget.renderer()
            assert isinstance(renderer, QgsRasterRenderer)
            renderer.setOpacity(self.sliderOpacity.value() / 100.)
            self.mRasterLayer.setRenderer(renderer.clone())
            self.mRasterLayer.triggerRepaint()
            self.setResult(QDialog.Accepted)
        s = ""




class VectorLayerProperties(QgsOptionsDialogBase, loadUI('vectorlayerpropertiesdialog.ui')):

    def __init__(self, lyr:QgsVectorLayer, canvas:QgsMapCanvas, parent=None, fl=Qt.Widget):
        super(VectorLayerProperties, self).__init__("VectorLayerProperties", parent, fl)
        title = "Layer Properties - {}".format(lyr.name())
        #self.restoreOptionsBaseUi(title)
        self.setupUi(self)
        self.initOptionsBase(False, title)
        self.mRendererDialog = None

        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas(self)
            canvas.setVisible(False)
            canvas.setLayers([lyr])
            canvas.setExtent(canvas.fullExtent())

        assert isinstance(lyr, QgsVectorLayer)
        assert isinstance(canvas, QgsMapCanvas)
        self.mLayer = lyr
        self.mCanvas = canvas
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.syncToLayer)

        self.pbnQueryBuilder.clicked.connect(self.on_pbnQueryBuilder_clicked)

        self.accepted.connect(self.syncToLayer)
        self.rejected.connect(self.onCancel)

        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.syncToLayer)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)


        self.syncFromLayer()

    def onCancel(self):
        # todo: restore anything else?
        self.setResult(QDialog.Rejected)

    def syncFromLayer(self):
        lyr = self.mLayer
        if isinstance(lyr, QgsVectorLayer):
            self.mLayerOrigNameLineEdit.setText(lyr.name())
            self.txtLayerSource.setText(lyr.publicSource())
            gtype = ['Point','Line','Polygon','Unknown','Undefined'][lyr.geometryType()]
            self.txtGeometryType.setText(gtype)
            self.txtnFeatures.setText('{}'.format(self.mLayer.featureCount()))
            self.txtnFields.setText('{}'.format(self.mLayer.fields().count()))

            self.mCrsSelector.setCrs(lyr.crs())

            self.txtSubsetSQL.setText(self.mLayer.subsetString())
            self.txtSubsetSQL.setEnabled(False)


        self.updateSymbologyPage()

        self.mLayerFieldConfigEditorWidget.setLayer(lyr)
        pass


    def syncToLayer(self):

        if isinstance(self.mRendererDialog, QgsRendererPropertiesDialog):
            self.mRendererDialog.apply()

        if self.txtSubsetSQL.toPlainText() != self.mLayer.subsetString():
            self.mLayer.setSubsetString(self.txtSubsetSQL.toPlainText())

        if isinstance(self.mLayerFieldConfigEditorWidget, LayerFieldConfigEditorWidget):
            self.mLayerFieldConfigEditorWidget.onApply()

        if self.mLayerOrigNameLineEdit.text() != self.mLayer.name():
            self.mLayer.setName(self.mLayerOrigNameLineEdit.text())

        self.mLayer.triggerRepaint()
        pass

    def on_pbnQueryBuilder_clicked(self):
        qb = QgsQueryBuilder(self.mLayer, self)
        qb.setSql(self.txtSubsetSQL.toPlainText())

        if qb.exec_():
            self.txtSubsetSQL.setText(qb.sql())

    def updateSymbologyPage(self):

        while self.widgetStackRenderers.count() > 0:
            self.widgetStackRenderers.removeWidget(self.widgetStackRenderers.widget(0))

        self.mRendererDialog = None
        if self.mLayer.renderer():
            self.mRendererDialog = QgsRendererPropertiesDialog(self.mLayer, QgsStyle.defaultStyle(), True, self)
            self.mRendererDialog.setDockMode(False)
            self.mRendererDialog.setMapCanvas(self.mCanvas)

            self.mRendererDialog.layout().setContentsMargins(0, 0, 0, 0)
            self.widgetStackRenderers.addWidget(self.mRendererDialog)
            self.widgetStackRenderers.setCurrentWidget(self.mRendererDialog)

            self.mOptsPage_Style.setEnabled(True)
        else:
            self.mOptsPage_Style.setEnabled(False)


def showLayerPropertiesDialog(layer:QgsMapLayer,
                              canvas:QgsMapCanvas,
                              parent:QObject=None,
                              modal:bool=True,
                              useQGISDialog:bool=False)->QDialog.DialogCode:
    """
    Opens a dialog to adjust map layer settiongs.
    :param layer: QgsMapLayer of type QgsVectorLayer or QgsRasterLayer
    :param canvas: QgsMapCanvas
    :param parent:
    :param modal: bool
    :return: QDialog.DialogCode
    """
    dialog = None
    result = QDialog.Rejected
    from .utils import qgisAppQgisInterface
    iface = qgisAppQgisInterface()
    qgisUsed = False
    if useQGISDialog and isinstance(iface, QgisInterface):
        # try to use the QGIS vector layer properties dialog
        try:
            root = iface.layerTreeView().model().rootGroup()
            assert isinstance(root, QgsLayerTreeGroup)
            temporaryGroup = None
            lastActiveLayer = iface.activeLayer()

            if root.findLayer(layer) is None:

                temporaryGroup = root.addGroup('.')
                assert isinstance(temporaryGroup, QgsLayerTreeGroup)
                temporaryGroup.setItemVisibilityChecked(False)
                lyrNode = temporaryGroup.addLayer(layer)
                assert isinstance(lyrNode, QgsLayerTreeLayer)
            iface.setActiveLayer(layer)
            iface.showLayerProperties(layer)
            if isinstance(temporaryGroup, QgsLayerTreeGroup):
                root.removeChildNode(temporaryGroup)
            iface.setActiveLayer(lastActiveLayer)

            return QDialog.Accepted

        except Exception as ex:
            print(ex)

    if isinstance(layer, (QgsRasterLayer, QgsVectorLayer)):

        if canvas is None:
            canvas = QgsMapCanvas()
            canvas.setVisible(False)
            canvas.setDestinationCrs(layer.crs())
            canvas.setExtent(layer.extent())
            canvas.setLayers([layer])

        if isinstance(layer, QgsRasterLayer):
            dialog = RasterLayerProperties(layer, canvas, parent=parent)
        elif isinstance(layer, QgsVectorLayer):
            dialog = VectorLayerProperties(layer, canvas, parent=parent)
        else:
            raise NotImplementedError()

        if modal == True:
            dialog.setModal(True)
        else:
            dialog.setModal(False)

        result = dialog.exec_()
    return result



RASTERRENDERER_CREATE_FUNCTIONSV2 = OptionListModel()
#RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(MultiBandColorRendererWidget.create, name='multibandcolor'))
RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(QgsMultiBandColorRendererWidget, name='multibandcolor (QGIS)'))
RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(QgsPalettedRendererWidget, name='paletted'))
#RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(SingleBandGrayRendererWidget.create, name='singlegray'))
RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(QgsSingleBandGrayRendererWidget, name='singlegray (QGIS)'))
#RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(SingleBandPseudoColorRendererWidget.create, name='singlebandpseudocolor'))
RASTERRENDERER_CREATE_FUNCTIONSV2.addOption(Option(QgsSingleBandPseudoColorRendererWidget, name='singlebandpseudocolor (QGIS)'))

