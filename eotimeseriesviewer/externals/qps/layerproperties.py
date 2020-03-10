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
import typing, enum
from osgeo import gdal, ogr, osr
import numpy as np
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import QDomDocument
from . import DIR_UI_FILES
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


class AddAttributeDialog(QDialog):
    """
    A dialog to set up a new QgsField.
    """
    def __init__(self, layer, parent=None, case_sensitive: bool = False):
        assert isinstance(layer, QgsVectorLayer)
        super(AddAttributeDialog, self).__init__(parent)

        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.mCaseSensitive = case_sensitive
        self.setWindowTitle('Add Field')
        l = QGridLayout()

        self.tbName = QLineEdit('Name')
        self.tbName.setPlaceholderText('Name')
        self.tbName.textChanged.connect(self.validate)

        l.addWidget(QLabel('Name'), 0,0)
        l.addWidget(self.tbName, 0, 1)

        self.tbComment = QLineEdit()
        self.tbComment.setPlaceholderText('Comment')
        l.addWidget(QLabel('Comment'), 1, 0)
        l.addWidget(self.tbComment, 1, 1)

        self.cbType = QComboBox()
        self.typeModel = OptionListModel()

        for ntype in self.mLayer.dataProvider().nativeTypes():
            assert isinstance(ntype, QgsVectorDataProvider.NativeType)
            o = Option(ntype, name=ntype.mTypeName, toolTip=ntype.mTypeDesc)
            self.typeModel.addOption(o)
        self.cbType.setModel(self.typeModel)
        self.cbType.currentIndexChanged.connect(self.onTypeChanged)
        l.addWidget(QLabel('Type'), 2, 0)
        l.addWidget(self.cbType, 2, 1)

        self.sbLength = QSpinBox()
        self.sbLength.setRange(0, 99)
        self.sbLength.valueChanged.connect(lambda : self.setPrecisionMinMax())
        self.lengthLabel = QLabel('Length')
        l.addWidget(self.lengthLabel, 3, 0)
        l.addWidget(self.sbLength, 3, 1)

        self.sbPrecision = QSpinBox()
        self.sbPrecision.setRange(0, 99)
        self.precisionLabel = QLabel('Precision')
        l.addWidget(self.precisionLabel, 4, 0)
        l.addWidget(self.sbPrecision, 4, 1)

        self.tbValidationInfo = QLabel()
        self.tbValidationInfo.setStyleSheet("QLabel { color : red}")
        l.addWidget(self.tbValidationInfo, 5, 0, 1, 2)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttons.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        l.addWidget(self.buttons, 6, 1)
        self.setLayout(l)
        self.mLayer = layer
        self.onTypeChanged()

        self.validate()

    def setCaseSensitive(self, is_sensitive: bool):
        assert isinstance(is_sensitive, bool)
        self.mCaseSensitive = is_sensitive
        self.validate()

    def setName(self, name: str):
        """
        Sets the field name
        """
        self.tbName.setText(name)

    def name(self) -> str:
        """
        Returns the field name
        :return: str
        """
        return self.tbName.text()

    def accept(self):
        isValid, msg = self.validate()
        if isValid:
            super(AddAttributeDialog, self).accept()
        else:
            QMessageBox.warning(self, "Add Field", msg)


    def field(self):
        """
        Returns the new QgsField
        :return:
        """
        ntype = self.currentNativeType()
        return QgsField(name=self.tbName.text(),
                        type=QVariant(ntype.mType).type(),
                        typeName=ntype.mTypeName,
                        len=self.sbLength.value(),
                        prec=self.sbPrecision.value(),
                        comment=self.tbComment.text())

    def currentNativeType(self):
        return self.cbType.currentData().value()

    def onTypeChanged(self, *args):
        ntype = self.currentNativeType()
        vMin , vMax = ntype.mMinLen, ntype.mMaxLen
        assert isinstance(ntype, QgsVectorDataProvider.NativeType)

        isVisible = vMin < vMax
        self.sbLength.setVisible(isVisible)
        self.lengthLabel.setVisible(isVisible)
        self.setSpinBoxMinMax(self.sbLength, vMin , vMax)
        self.setPrecisionMinMax()

    def setPrecisionMinMax(self):
        ntype = self.currentNativeType()
        vMin, vMax = ntype.mMinPrec, ntype.mMaxPrec
        isVisible = vMin < vMax
        self.sbPrecision.setVisible(isVisible)
        self.precisionLabel.setVisible(isVisible)

        vMax = max(ntype.mMinPrec, min(ntype.mMaxPrec, self.sbLength.value()))
        self.setSpinBoxMinMax(self.sbPrecision, vMin, vMax)

    def setSpinBoxMinMax(self, sb, vMin, vMax):
        assert isinstance(sb, QSpinBox)
        value = sb.value()
        sb.setRange(vMin, vMax)

        if value > vMax:
            sb.setValue(vMax)
        elif value < vMin:
            sb.setValue(vMin)

    def validate(self, *args) -> typing.Union[bool, str]:
        """
        Validates the inputs
        :return: (bool, str with error message(s))
        """
        errors = []
        name = self.tbName.text()
        existing_names = self.mLayer.fields().names()
        if self.mCaseSensitive and name in existing_names or \
           not self.mCaseSensitive and name.lower() in [n.lower() for n in existing_names]:
            errors.append('Field name "{}" already exists.'.format(name))
        elif name == '':
            errors.append('Missing field name')
        elif name == 'shape':
            errors.append('Field name "{}" already reserved.'.format(name))
        errors = '\n'.join(errors)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(len(errors) == 0)
        self.tbValidationInfo.setText(errors)

        return len(errors) == 0, errors


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
                #print(typeName)
                s =""
    return None

def defaultRasterRenderer(layer:QgsRasterLayer, bandIndices:list=None, sampleSize:int=256, readQml:bool=True)->QgsRasterRenderer:
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

    # band names are defined explicitley
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

        # check for *.qml file with default styling information
        if readQml:
            qmlUri = pathlib.Path(layer.styleURI())
            is_file = False
            try:
                is_file = qmlUri.is_file()
            except OSError:
                is_file = False

            if is_file and re.search(r'\.(qml)$', qmlUri.name):
                msg, success = layer.loadDefaultStyle()
                if success:
                    r = layer.renderer().clone()
                    r.setInput(layer.dataProvider())
                    return r
                else:
                    print(msg, file=sys.stderr)

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

class LayerPropertiesDialog(QgsOptionsDialogBase):

    @staticmethod
    def defaultFactories()->typing.List[QgsMapLayerConfigWidgetFactory]:
        """
        Returns a list of default QgsMapLayerConfigWidgetFactory
        """
        from .layerconfigwidgets.core import \
            MetadataConfigWidgetFactory, \
            SourceConfigWidgetFactory, \
            SymbologyConfigWidgetFactory, \
            TransparencyConfigWidgetFactory, \
            RenderingConfigWidgetFactory, LegendConfigWidgetFactory
        from .layerconfigwidgets.vectorlabeling import LabelingConfigWidgetFactory
        from .layerconfigwidgets.rasterbands import RasterBandConfigWidgetFactory
        from .layerconfigwidgets.gdalmetadata import GDALMetadataConfigWidgetFactory
        from .layerconfigwidgets.vectorlayerfields import \
            LayerAttributeFormConfigWidgetFactory, \
            LayerFieldsConfigWidgetFactory
        factories = [
            MetadataConfigWidgetFactory(),
            SourceConfigWidgetFactory(),
            SymbologyConfigWidgetFactory(),
            RasterBandConfigWidgetFactory(),
            LabelingConfigWidgetFactory(),
            TransparencyConfigWidgetFactory(),
            RenderingConfigWidgetFactory(),
            GDALMetadataConfigWidgetFactory(),
            LayerFieldsConfigWidgetFactory(),
            LayerAttributeFormConfigWidgetFactory(),
            LegendConfigWidgetFactory()
        ]
        return factories

    def __init__(self,
                 lyr:typing.Union[QgsRasterLayer, QgsVectorLayer],
                 canvas:QgsMapCanvas=None,
                 parent=None,
                 mapLayerConfigFactories:typing.List[QgsMapLayerConfigWidgetFactory] = None):

        super(QgsOptionsDialogBase, self).__init__('QPS_LAYER_PROPERTIES', parent, Qt.Dialog, settings=None)
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'layerpropertiesdialog.ui'
        loadUi(pathUi.as_posix(), self)
        self.initOptionsBase(False, 'Layer Properties - {}'.format(lyr.name()))
        self.mOptionsListWidget: QListWidget
        self.mOptionsStackedWidget : QStackedWidget
        assert isinstance(self.mOptionsListWidget, QListWidget)
        assert isinstance(self.mOptionsStackedWidget, QStackedWidget)
        assert isinstance(lyr, QgsMapLayer)
        self.btnConfigWidgetMenu: QPushButton = QPushButton('<menu>')
        assert isinstance(self.btnConfigWidgetMenu, QPushButton)
        self.mOptionsListWidget.currentRowChanged.connect(self.onPageChanged)
        self.mLayer: QgsMapLayer = lyr

        assert isinstance(self.btnConfigWidgetMenu, QPushButton)
        self.buttonBox: QDialogButtonBox

        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas()
            canvas.setDestinationCrs(lyr.crs())
            canvas.setExtent(lyr.extent())
            canvas.setLayers([lyr])

        self.mCanvas: QgsMapCanvas
        self.mCanvas = canvas

        self.buttonBox.layout().insertWidget(0, self.btnConfigWidgetMenu)

        self.btnApply: QPushButton = self.buttonBox.button(QDialogButtonBox.Apply)
        self.btnCancel: QPushButton = self.buttonBox.button(QDialogButtonBox.Cancel)
        self.btnOk: QPushButton = self.buttonBox.button(QDialogButtonBox.Ok)

        s = ""

        assert isinstance(self.mOptionsListWidget, QListWidget)

        if mapLayerConfigFactories is None:
            mapLayerConfigFactories = LayerPropertiesDialog.defaultFactories()

        for f in mapLayerConfigFactories:
            assert isinstance(f, QgsMapLayerConfigWidgetFactory)
            if f.supportsLayer(self.mapLayer()) and f.supportLayerPropertiesDialog():
                pageWidget = f.createWidget(self.mapLayer(), self.canvas(), dockWidget=False)
                assert isinstance(pageWidget, QgsMapLayerConfigWidget)
                title = f.title()
                icon = f.icon()
                pageItem = QListWidgetItem(icon, title)
                assert isinstance(pageItem, QListWidgetItem)
                pageItem.setToolTip(pageWidget.toolTip())
                self.mOptionsListWidget.addItem(pageItem)
                self.mOptionsStackedWidget.addWidget(pageWidget)


        self.btnApply.clicked.connect(self.apply)
        self.btnOk.clicked.connect(self.onOk)
        self.btnCancel.clicked.connect(self.onCancel)

        # select the first item
        self.mOptionsListWidget.setCurrentRow(0)

    def onPageChanged(self, row):
        page = self.currentPage()
        menu = None

        if isinstance(page, QgsMapLayerConfigWidget):
            # comes with QIS 3.12

            if hasattr(page, 'menuButtonMenu'):
                menu = page.menuButtonMenu()

            if hasattr(page, 'menuButtonToolTip'):
                self.btnConfigWidgetMenu.setToolTip(page.menuButtonToolTip())

        self.btnConfigWidgetMenu.setMenu(menu)
        if isinstance(menu, QMenu):
            self.btnConfigWidgetMenu.setVisible(True)
            self.btnConfigWidgetMenu.setText(menu.title())
        else:
            self.btnConfigWidgetMenu.setVisible(False)
            self.btnConfigWidgetMenu.setText('<empty>')






    def onOk(self):
        self.apply()
        self.accept()

    def onCancel(self):
        # do restore previous settings?

        #self.setResult(QDialog.Rejected)
        self.reject()


    def currentPage(self)->QWidget:
        return self.mOptionsStackedWidget.currentWidget()

    def apply(self):

        page = self.currentPage()
        if isinstance(page, QgsMapLayerConfigWidget) and hasattr(page, 'apply'):
            page.apply()
        else:

            s = ""

        self.mapLayer().triggerRepaint()
        self.sync()


    def setPage(self, page:typing.Union[QgsMapLayerConfigWidget, int]):
        if isinstance(page, QgsMapLayerConfigWidget):
            pages = list(self.pages())
            assert page in pages
            i = pages.index(page)
            self.setPage(i)
        else:
            assert isinstance(page, int) and page >= 0 and page < self.mOptionsListWidget.count()
            self.mOptionsListWidget.setCurrentRow(page)

    def pages(self)->typing.List[QgsMapLayerConfigWidget]:
        for i in range(self.mOptionsStackedWidget.count()):
            w = self.mOptionsStackedWidget.widget(i)
            if isinstance(w, QgsMapLayerConfigWidget):
                yield w

    def canvas(self)->QgsMapCanvas:
        return self.mCanvas

    def mapLayer(self)->QgsMapLayer:
        """
        Returns the QgsMapLayer
        :return:
        :rtype:
        """
        return self.mLayer

    def sync(self):
        """
        Call to reload properties
        """
        lyr = self.mapLayer()
        w = self.currentPage()

        if isinstance(w, QgsMapLayerConfigWidget) and hasattr(w, 'syncToLayer'):
            w.syncToLayer()

        for page in self.pages():
            if page != w:
                if hasattr(w, 'syncToLayer'):
                    page.syncToLayer()

        s =""


def showLayerPropertiesDialog(layer:QgsMapLayer,
                              canvas:QgsMapCanvas=None,
                              parent:QObject=None,
                              modal:bool=True,
                              useQGISDialog:bool=False)->typing.Union[QDialog.DialogCode, QDialog]:
    """
    Opens a dialog to adjust map layer settings.
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
            print(ex, file=sys.stderr)

    else:

        dialog = LayerPropertiesDialog(layer, canvas=canvas)

        if modal == True:
            dialog.setModal(True)
            return dialog.exec_()
        else:
            dialog.setModal(False)
            dialog.show()
            return dialog

    return None



