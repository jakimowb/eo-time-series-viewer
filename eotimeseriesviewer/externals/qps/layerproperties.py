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

from qgis.PyQt.QtWidgets import *
# auto-generated file.
from qgis.core import \
    Qgis, \
    QgsAction, \
    QgsApplication, \
    QgsCategorizedSymbolRenderer, \
    QgsContrastEnhancement, \
    QgsDataProvider, \
    QgsDistanceArea, \
    QgsEditFormConfig, \
    QgsExpression, \
    QgsExpressionContext, \
    QgsExpressionContextGenerator, \
    QgsExpressionContextScope, \
    QgsExpressionContextUtils, \
    QgsFeature, \
    QgsFeatureRenderer, \
    QgsFeatureRequest, \
    QgsField, \
    QgsFieldProxyModel, \
    QgsHillshadeRenderer, \
    QgsLayerTreeGroup, \
    QgsLayerTreeLayer, \
    QgsMapLayer, \
    QgsMapLayerStyle, \
    QgsMultiBandColorRenderer, \
    QgsPalettedRasterRenderer, \
    QgsProject, \
    QgsProviderRegistry, \
    QgsRasterBandStats, \
    QgsRasterDataProvider, \
    QgsRasterLayer, \
    QgsRasterRenderer, \
    QgsReadWriteContext, \
    QgsRectangle, \
    QgsScopedProxyProgressTask, \
    QgsSettings, \
    QgsSingleBandGrayRenderer, \
    QgsSingleBandPseudoColorRenderer, \
    QgsSingleSymbolRenderer, \
    QgsVectorDataProvider, \
    QgsVectorLayer, \
    QgsWkbTypes

from qgis.gui import \
    QgisInterface, \
    QgsActionMenu, \
    QgsAttributeEditorContext, \
    QgsAttributeForm, \
    QgsAttributeTableFilterModel, \
    QgsAttributeTableModel, \
    QgsDockWidget, \
    QgsDualView, \
    QgsExpressionSelectionDialog, \
    QgsMapCanvas, \
    QgsMapLayerConfigWidget, \
    QgsMapLayerConfigWidgetFactory, \
    QgsMessageBar, \
    QgsOptionsDialogBase, \
    QgsRasterTransparencyWidget, \
    QgsSublayersDialog, \
    QgsFilterLineEdit, \
    QgsExpressionBuilderDialog

from .classification.classificationscheme import ClassificationScheme
from .models import OptionListModel, Option
from .utils import *
from .vectorlayertools import VectorLayerTools

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
    'singlebandpseudocolor': QgsSingleBandPseudoColorRenderer,
    'singlebandgray': QgsSingleBandGrayRenderer,
    'paletted': QgsPalettedRasterRenderer,
    'multibandcolor': QgsMultiBandColorRenderer,
    'hillshade': QgsHillshadeRenderer
}
RENDER_CLASSES['renderer-v2'] = {
    'categorizedSymbol': QgsCategorizedSymbolRenderer,
    'singleSymbol': QgsSingleSymbolRenderer
}
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)

MDF_QGIS_LAYER_STYLE = 'application/qgis.style'
MDF_TEXT_PLAIN = 'text/plain'


class FieldListModel(QAbstractListModel):

    def __init__(self, *args, layer:QgsVectorLayer=None, **kwds):

        super().__init__(*args, **kwds)

    def setLayer(self, layer:QgsVectorLayer):

        self.mLayer = layer

    def flags(self, index:QModelIndex):
        pass



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

        l.addWidget(QLabel('Name'), 0, 0)
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
        self.sbLength.valueChanged.connect(lambda: self.setPrecisionMinMax())
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
        vMin, vMax = ntype.mMinLen, ntype.mMaxLen
        assert isinstance(ntype, QgsVectorDataProvider.NativeType)

        isVisible = vMin < vMax
        self.sbLength.setVisible(isVisible)
        self.lengthLabel.setVisible(isVisible)
        self.setSpinBoxMinMax(self.sbLength, vMin, vMax)
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


class RemoveAttributeDialog(QDialog):

    def __init__(self, layer: QgsVectorLayer, *args, fieldNames=None, **kwds):
        super().__init__(*args, **kwds)
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.setWindowTitle('Remove Field')

        from .layerconfigwidgets.vectorlayerfields import LayerFieldsListModel
        self.fieldModel = LayerFieldsListModel()
        self.fieldModel.setLayer(self.mLayer)
        self.fieldModel.setAllowEmptyFieldName(False)
        self.fieldModel.setAllowExpression(False)

        self.tvFieldNames = QTableView()
        self.tvFieldNames.setModel(self.fieldModel)

        self.btnBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self.btnBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.btnBox.button(QDialogButtonBox.Ok).clicked.connect(self.accept)

        self.label = QLabel('Select')

        l = QVBoxLayout()
        l.addWidget(self.label)
        l.addWidget(self.tvFieldNames)
        l.addWidget(self.btnBox)
        self.setLayout(l)

    def fields(self) -> typing.List[QgsField]:
        """
        Returns the selected QgsFields
        """
        fields = []
        for idx in self.tvFieldNames.selectionModel().selectedRows():
            i = idx.data(Qt.UserRole + 2)
            fields.append(self.mLayer.fields().at(i))

        return fields

    def fieldIndices(self) -> typing.List[int]:
        return [self.mLayer.fields().lookupField(f.name()) for f in self.fields()]

    def fieldNames(self) -> typing.List[str]:
        return [f.name() for f in self.fields()]


def openRasterLayerSilent(uri, name, provider) -> QgsRasterLayer:
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
            # for format in ['application/qgis.style', 'text/plain']:
            if format in xml.formats():
                dom = QDomDocument()
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
                # print(typeName)
                s = ""
    return None


def defaultRasterRenderer(layer: QgsRasterLayer, bandIndices: list = None, sampleSize: int = 256,
                          readQml: bool = True) -> QgsRasterRenderer:
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
        bandIndices = [b for b in bandIndices if b >= 0 and b < nb]
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
    bandStats = [layer.dataProvider().bandStatistics(b + 1, stats=QgsRasterBandStats.Min | QgsRasterBandStats.Max,
                                                     sampleSize=sampleSize) for b in bandIndices]
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
        b = bandIndices[0] + 1
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
        bands = [b + 1 for b in bandIndices[0:3]]
        contrastEnhancements = [QgsContrastEnhancement(dp.dataType(b)) for b in bands]
        ceR, ceG, ceB = contrastEnhancements

        for i, b in enumerate(bands):
            dt = dp.dataType(b)
            ce = contrastEnhancements[i]

            assert isinstance(ce, QgsContrastEnhancement)
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            if dt == Qgis.Byte:
                # standard RGB photo?
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
        r = QgsMultiBandColorRenderer(layer.dataProvider(), R, G, B, None, None, None)
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


def rendererToXml(layerOrRenderer, geomType: QgsWkbTypes = None):
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
        # create a dummy raster layer
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
        # remove dummy raster layer
        lyr = None
        drv.Delete(path)

    elif isinstance(layerOrRenderer, QgsFeatureRenderer) and geomType is not None:
        # todo: distinguish vector type from requested renderer
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


def pasteStyleFromClipboard(layer: QgsMapLayer):
    mimeData = QApplication.clipboard().mimeData()
    renderer = rendererFromXml(mimeData)
    if isinstance(renderer, QgsRasterRenderer) and isinstance(layer, QgsRasterLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    elif isinstance(renderer, QgsFeatureRenderer) and isinstance(layer, QgsVectorLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()


def equal_styles(lyr1: QgsMapLayer, lyr2: QgsMapLayer) -> bool:
    if lyr1 == lyr2:
        return True
    if isinstance(lyr1, QgsRasterLayer) and not isinstance(lyr2, QgsRasterLayer):
        return False
    if isinstance(lyr2, QgsVectorLayer) and not isinstance(lyr2, QgsVectorLayer):
        return False

    style1 = QgsMapLayerStyle()
    style2 = QgsMapLayerStyle()
    style1.readFromLayer(lyr1)
    style2.readFromLayer(lyr2)

    return style1.xmlData() == style2.xmlData()


def subLayerDefinitions(mapLayer: QgsMapLayer) -> typing.List[QgsSublayersDialog.LayerDefinition]:
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


def subLayers(mapLayer: QgsMapLayer, subLayers: list = None) -> typing.List[QgsMapLayer]:
    """
    Returns a list of QgsMapLayer instances extracted from the input QgsMapLayer.
    Returns the "parent" QgsMapLayer in case no sublayers can be extracted
    :param mapLayer: QgsMapLayer
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    dp = mapLayer.dataProvider()

    uriParts = QgsProviderRegistry.instance().decodeUri(mapLayer.providerType(),
                                                        mapLayer.dataProvider().dataSourceUri())
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
    def defaultFactories() -> typing.List[QgsMapLayerConfigWidgetFactory]:
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
                 lyr: typing.Union[QgsRasterLayer, QgsVectorLayer],
                 canvas: QgsMapCanvas = None,
                 parent=None,
                 mapLayerConfigFactories: typing.List[QgsMapLayerConfigWidgetFactory] = None):

        super(QgsOptionsDialogBase, self).__init__('QPS_LAYER_PROPERTIES', parent, Qt.Dialog, settings=None)
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'layerpropertiesdialog.ui'
        loadUi(pathUi.as_posix(), self)
        self.initOptionsBase(False, 'Layer Properties - {}'.format(lyr.name()))
        self.mOptionsListWidget: QListWidget
        self.mOptionsStackedWidget: QStackedWidget
        assert isinstance(self.mOptionsListWidget, QListWidget)
        assert isinstance(self.mOptionsStackedWidget, QStackedWidget)
        assert isinstance(lyr, QgsMapLayer)
        self.btnConfigWidgetMenu: QPushButton = QPushButton('<menu>')
        self.btnConfigWidgetMenu.setVisible(False)
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

        self.btnHelp: QPushButton = self.buttonBox.button(QDialogButtonBox.Help)
        # not connected
        self.btnHelp.setVisible(False)
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
            # comes with QGIS 3.12

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

        # self.setResult(QDialog.Rejected)
        self.reject()

    def currentPage(self) -> QWidget:
        return self.mOptionsStackedWidget.currentWidget()

    def apply(self):

        page = self.currentPage()
        if isinstance(page, QgsMapLayerConfigWidget) and hasattr(page, 'apply'):
            page.apply()
        else:

            s = ""

        self.mapLayer().triggerRepaint()
        self.sync()

    def setPage(self, page: typing.Union[QgsMapLayerConfigWidget, int]):
        if isinstance(page, QgsMapLayerConfigWidget):
            pages = list(self.pages())
            assert page in pages
            i = pages.index(page)
            self.setPage(i)
        else:
            assert isinstance(page, int) and page >= 0 and page < self.mOptionsListWidget.count()
            self.mOptionsListWidget.setCurrentRow(page)

    def pages(self) -> typing.List[QgsMapLayerConfigWidget]:
        for i in range(self.mOptionsStackedWidget.count()):
            w = self.mOptionsStackedWidget.widget(i)
            if isinstance(w, QgsMapLayerConfigWidget):
                yield w

    def canvas(self) -> QgsMapCanvas:
        return self.mCanvas

    def mapLayer(self) -> QgsMapLayer:
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
            if isinstance(w, QgsRasterTransparencyWidget):
                # skip, until this issue is solved in QGIS https://github.com/qgis/QGIS/pull/34969
                # w.syncToLayer()
                pass
            else:
                w.syncToLayer()

        for page in self.pages():
            if page != w:
                if hasattr(w, 'syncToLayer'):
                    page.syncToLayer()

        s = ""


def showLayerPropertiesDialog(layer: QgsMapLayer,
                              canvas: QgsMapCanvas = None,
                              parent: QObject = None,
                              modal: bool = True,
                              useQGISDialog: bool = False) -> typing.Union[QDialog.DialogCode, QDialog]:
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
            root = iface.layerTreeView().layerTreeModel().rootGroup()
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
        dialog = None
        if False:
            if isinstance(layer, QgsVectorLayer):
                dialog = QgsVectorLayerProperties(layer, canvas)
            elif isinstance(layer, QgsRasterLayer):
                dialog = QgsRasterLayerProperties(layer, canvas)
        else:
            dialog = LayerPropertiesDialog(layer, canvas=canvas)
        if dialog:
            if modal == True:
                dialog.setModal(True)
                return dialog.exec_()
            else:
                dialog.setModal(False)
                dialog.show()
                return dialog

    return None


def tr(t: str) -> str:
    return t


class AttributeTableWidget(QMainWindow, QgsExpressionContextGenerator):

    def __init__(self, mLayer: QgsVectorLayer, *args,
                 initialMode: QgsAttributeTableFilterModel.FilterMode = QgsAttributeTableFilterModel.ShowVisible,
                 **kwds):
        super().__init__(*args, **kwds)
        loadUi(pathlib.Path(DIR_UI_FILES) / 'attributetablewidget.ui', self)

        self.widgetLeft.setVisible(False)
        self.widgetRight.setVisible(False)

        settings = QgsSettings()

        self.mActionCutSelectedRows.triggered.connect(self.mActionCutSelectedRows_triggered)
        self.mActionCopySelectedRows.triggered.connect(self.mActionCopySelectedRows_triggered)
        self.mActionPasteFeatures.triggered.connect(self.mActionPasteFeatures_triggered)
        self.mActionToggleEditing.toggled.connect(self.mActionToggleEditing_toggled)
        self.mActionSaveEdits.triggered.connect(self.mActionSaveEdits_triggered)
        self.mActionReload.triggered.connect(self.mActionReload_triggered)
        self.mActionInvertSelection.triggered.connect(self.mActionInvertSelection_triggered)
        self.mActionRemoveSelection.triggered.connect(self.mActionRemoveSelection_triggered)
        self.mActionSelectAll.triggered.connect(self.mActionSelectAll_triggered)
        self.mActionZoomMapToSelectedRows.triggered.connect(self.mActionZoomMapToSelectedRows_triggered)
        self.mActionPanMapToSelectedRows.triggered.connect(self.mActionPanMapToSelectedRows_triggered)
        self.mActionSelectedToTop.toggled.connect(self.mMainView.setSelectedOnTop)
        self.mActionAddAttribute.triggered.connect(self.mActionAddAttribute_triggered)
        self.mActionRemoveAttribute.triggered.connect(self.mActionRemoveAttribute_triggered)
        # self.mActionOpenFieldCalculator.triggered.connect(self.mActionOpenFieldCalculator_triggered)
        self.mActionDeleteSelected.triggered.connect(self.mActionDeleteSelected_triggered)
        self.mMainView.currentChanged.connect(self.mMainView_currentChanged)
        self.mActionAddFeature.triggered.connect(self.mActionAddFeature_triggered)
        self.mActionExpressionSelect.triggered.connect(self.mActionExpressionSelect_triggered)
        self.mMainView.showContextMenuExternally.connect(self.showContextMenu)

        assert isinstance(self.mMainView, QgsDualView)
        pal = self.mMainView.tableView().palette()
        css = r"""QTableView {{
                       selection-background-color: {};
                       selection-color: {};
                        }}""".format(pal.highlight().color().name(),
                                     pal.highlightedText().color().name())
        self.mMainView.setStyleSheet(css)
        self.mDock: QgsDockWidget = None
        self.mEditorContext = QgsAttributeEditorContext()
        self.mLayer: QgsVectorLayer = mLayer
        self.mLayer.nameChanged.connect(self.updateTitle)

        self.mMapCanvas = QgsMapCanvas()
        self.mMapCanvas.setLayers([self.mLayer])
        # Initialize the window geometry
        # geom = settings.value("Windows/BetterAttributeTable/geometry")
        # self.restoreGeometry(geom)

        da = QgsDistanceArea()
        da.setSourceCrs(mLayer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())

        self.mEditorContext.setDistanceArea(da)
        self.mVectorLayerTools: VectorLayerTools = None
        self.setVectorLayerTools(VectorLayerTools())

        r = QgsFeatureRequest()
        needsGeom = False
        if mLayer.geometryType() != QgsWkbTypes.NullGeometry and \
                initialMode == QgsAttributeTableFilterModel.ShowVisible:
            mc = self.mMapCanvas
            extent = QgsRectangle(mc.mapSettings().mapToLayerCoordinates(mLayer, mc.extent()))
            r.setFilterRect(extent)
            needsGeom = True
        elif initialMode == QgsAttributeTableFilterModel.ShowSelected:

            r.setFilterFids(mLayer.selectedFeatureIds())

        if not needsGeom:
            r.setFlags(QgsFeatureRequest.NoGeometry)

        # Initialize dual view
        # self.mMainView.init(mLayer, self.mMapCanvas, r, self.mEditorContext, False)
        self.mMainView.init(mLayer, self.mMapCanvas)

        config = mLayer.attributeTableConfig()
        self.mMainView.setAttributeTableConfig(config)

        # workaround for missing filter widget
        self.mMessageTimeOut = 5
        # self.mFeatureFilterWidget.init(mLayer, self.mEditorContext, self.mMainView, None, QgisApp.instance().messageTimeout())
        self.mApplyFilterButton.setDefaultAction(self.mActionApplyFilter)
        self.mSetFilterButton.setDefaultAction(self.mActionSetFilter)
        self.mActionApplyFilter.triggered.connect(self._filterQueryAccepted)
        self.mActionSetFilter.triggered.connect(self._filterExpressionBuilder)

        self.mActionFeatureActions = QToolButton()
        self.mActionFeatureActions.setAutoRaise(False)
        self.mActionFeatureActions.setPopupMode(QToolButton.InstantPopup)
        self.mActionFeatureActions.setIcon(QgsApplication.getThemeIcon("/mAction.svg"))
        self.mActionFeatureActions.setText(tr("Actions"))
        self.mActionFeatureActions.setToolTip(tr("Actions"))

        self.mToolbar.addWidget(self.mActionFeatureActions)
        self.mActionSetStyles.triggered.connect(self.openConditionalStyles)

        # info from layer to table
        mLayer.editingStarted.connect(self.editingToggled)
        mLayer.editingStopped.connect(self.editingToggled)
        mLayer.destroyed.connect(self.mMainView.cancelProgress)
        mLayer.selectionChanged.connect(self.updateTitle)
        mLayer.featureAdded.connect(self.scheduleTitleUpdate)
        mLayer.featuresDeleted.connect(self.updateTitle)
        mLayer.editingStopped.connect(self.updateTitle)
        mLayer.readOnlyChanged.connect(self.editingToggled)

        self.mUpdateTrigger: QTimer = QTimer()
        self.mUpdateTrigger.setInterval(2000)
        self.mUpdateTrigger.timeout.connect(self.updateTitle)

        # connect table info to window
        self.mMainView.filterChanged.connect(self.updateTitle)
        self.mMainView.filterExpressionSet.connect(self.formFilterSet)
        self.mMainView.formModeChanged.connect(self.viewModeChanged)

        # info from table to application
        # self.saveEdits.connect(QgisApp::instance() -> saveEdits() })

        """
        dockTable: bool = bool(settings.value("qgis/dockAttributeTable" , False )
        if dockTable:
            self.mDock = new QgsAttributeTableDock( QString(), QgisApp::instance() );
            mDock->setWidget( this );
            connect( this, &QObject::destroyed, mDock, &QWidget::close );
            QgisApp::instance() -> addDockWidget( Qt::BottomDockWidgetArea, mDock );
        mActionDockUndock->setChecked( dockTable );
        connect( mActionDockUndock, &QAction::toggled, this, &QgsAttributeTableDialog::toggleDockMode );
        installEventFilter( this );
        """

        self.updateTitle()

        # set icons
        self.mActionRemoveSelection.setIcon(QgsApplication.getThemeIcon("/mActionDeselectAll.svg"))
        self.mActionSelectAll.setIcon(QgsApplication.getThemeIcon("/mActionSelectAll.svg"))
        self.mActionSelectedToTop.setIcon(QgsApplication.getThemeIcon("/mActionSelectedToTop.svg"))
        self.mActionCopySelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionEditCopy.svg"))
        self.mActionPasteFeatures.setIcon(QgsApplication.getThemeIcon("/mActionEditPaste.svg"))
        self.mActionZoomMapToSelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionZoomToSelected.svg"))
        self.mActionPanMapToSelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionPanToSelected.svg"))
        self.mActionInvertSelection.setIcon(QgsApplication.getThemeIcon("/mActionInvertSelection.svg"))
        self.mActionToggleEditing.setIcon(QgsApplication.getThemeIcon("/mActionToggleEditing.svg"))
        self.mActionSaveEdits.setIcon(QgsApplication.getThemeIcon("/mActionSaveEdits.svg"))
        self.mActionDeleteSelected.setIcon(QgsApplication.getThemeIcon("/mActionDeleteSelectedFeatures.svg"))
        self.mActionOpenFieldCalculator.setIcon(QgsApplication.getThemeIcon("/mActionCalculateField.svg"))
        self.mActionAddAttribute.setIcon(QgsApplication.getThemeIcon("/mActionNewAttribute.svg"))
        self.mActionRemoveAttribute.setIcon(QgsApplication.getThemeIcon("/mActionDeleteAttribute.svg"))
        self.mTableViewButton.setIcon(QgsApplication.getThemeIcon("/mActionOpenTable.svg"))
        self.mAttributeViewButton.setIcon(QgsApplication.getThemeIcon("/mActionFormView.svg"))
        self.mActionExpressionSelect.setIcon(QgsApplication.getThemeIcon("/mIconExpressionSelect.svg"))
        self.mActionAddFeature.setIcon(QgsApplication.getThemeIcon("/mActionNewTableRow.svg"))
        self.mActionFeatureActions.setIcon(QgsApplication.getThemeIcon("/mAction.svg"))

        # toggle editing
        canChangeAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.ChangeAttributeValues
        canDeleteFeatures = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        canAddAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddAttributes
        canDeleteAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteAttributes
        canAddFeatures = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures

        self.mActionToggleEditing.blockSignals(True)
        self.mActionToggleEditing.setCheckable(True)
        self.mActionToggleEditing.setChecked(mLayer.isEditable())
        self.mActionToggleEditing.blockSignals(False)

        self.mActionSaveEdits.setEnabled(self.mActionToggleEditing.isEnabled() and mLayer.isEditable())
        self.mActionReload.setEnabled(not mLayer.isEditable())
        self.mActionAddAttribute.setEnabled((canChangeAttributes or canAddAttributes) and mLayer.isEditable())
        self.mActionRemoveAttribute.setEnabled(canDeleteAttributes and mLayer.isEditable())
        if not canDeleteFeatures:
            self.mToolbar.removeAction(self.mActionDeleteSelected)
            self.mToolbar.removeAction(self.mActionCutSelectedRows)

        self.mActionAddFeature.setEnabled(canAddFeatures and mLayer.isEditable())
        self.mActionPasteFeatures.setEnabled(canAddFeatures and mLayer.isEditable())
        if not canAddFeatures:
            self.mToolbar.removeAction(self.mActionAddFeature)
            self.mToolbar.removeAction(self.mActionPasteFeatures)

        assert isinstance(self.mMainViewButtonGroup, QButtonGroup)
        self.mMainViewButtonGroup.setId(self.mTableViewButton, QgsDualView.AttributeTable)
        self.mMainViewButtonGroup.setId(self.mAttributeViewButton, QgsDualView.AttributeEditor)
        self.mTableViewButton.clicked.connect(lambda: self.setViewMode(QgsDualView.AttributeTable))
        self.mAttributeViewButton.clicked.connect(lambda: self.setViewMode(QgsDualView.AttributeEditor))

        self.setFilterMode(initialMode)

        if isinstance(mLayer, QgsVectorLayer) and mLayer.isValid():

            # self.mUpdateExpressionText.registerExpressionContextGenerator(self)
            self.mFieldCombo.setFilters(QgsFieldProxyModel.AllTypes | QgsFieldProxyModel.HideReadOnly)
            self.mFieldCombo.setLayer(mLayer)

            self.mRunFieldCalc.clicked.connect(self.updateFieldFromExpression)
            self.mRunFieldCalcSelected.clicked.connect(self.updateFieldFromExpressionSelected)
            self.mUpdateExpressionText.fieldChanged.connect(lambda fieldName: self.updateButtonStatus(fieldName, True))
            self.mUpdateExpressionText.setLayer(mLayer)
            self.mUpdateExpressionText.setLeftHandButtonStyle(True)

            initialView = int(settings.value("qgis/attributeTableView", -1))
            if initialView < 0:
                initialView = int(settings.value("qgis/attributeTableLastView", int(QgsDualView.AttributeTable)))
            for m in [QgsDualView.AttributeTable, QgsDualView.AttributeEditor]:
                if initialView == int(m):
                    self.setViewMode(m)

            self.mActionToggleMultiEdit.toggled.connect(self.mMainView.setMultiEditEnabled)
            self.mActionSearchForm.toggled.connect(self.mMainView.toggleSearchMode)
            self.updateMultiEditButtonState()

            if mLayer.editFormConfig().layout() == QgsEditFormConfig.UiFileLayout:
                # not supported with custom UI
                self.mActionToggleMultiEdit.setEnabled(False)
                self.mActionToggleMultiEdit.setToolTip(tr("Multi-edit is not supported when using custom UI forms"))
                self.mActionSearchForm.setEnabled(False)
                self.mActionSearchForm.setToolTip(tr("Search is not supported when using custom UI forms"))

            self.editingToggled()

        self._hide_unconnected_widgets()

    def setVectorLayerTools(self, tools: VectorLayerTools):
        assert isinstance(tools, VectorLayerTools)
        self.mVectorLayerTools = tools

        self.mEditorContext.setVectorLayerTools(tools)

    def vectorLayerTools(self) -> VectorLayerTools:
        return self.mVectorLayerTools
        # return self.mEditorContext.vectorLayerTools()

    def setMapCanvas(self, canvas: QgsMapCanvas):
        self.mEditorContext.setMapCanvas(canvas)

    def createExpressionContext(self) -> QgsExpressionContext:
        return QgsExpressionContext()

    def updateButtonStatus(self, fieldName: str, isValid: bool):
        self.mRunFieldCalc.setEnabled(isValid)

    def updateMultiEditButtonState(self):
        if not isinstance(self.mLayer, QgsVectorLayer) or \
                (self.mLayer.editFormConfig().layout() == QgsEditFormConfig.UiFileLayout):
            return

        self.mActionToggleMultiEdit.setEnabled(self.mLayer.isEditable())

        if not self.mLayer.isEditable() or \
                (self.mLayer.isEditable() and self.mMainView.view() != QgsDualView.AttributeEditor):
            self.mActionToggleMultiEdit.setChecked(False)

    def openConditionalStyles(self):
        self.mMainView.openConditionalStyles()

    def mActionCutSelectedRows_triggered(self):
        self.vectorLayerTools().cutSelectionToClipboard(self.mLayer)

    def mActionCopySelectedRows_triggered(self):
        self.vectorLayerTools().copySelectionToClipboard(self.mLayer)

    def setMainMessageBar(self, messageBar: QgsMessageBar):
        self.mEditorContext.setMainMessageBar(messageBar)

    def mainMessageBar(self) -> QgsMessageBar:
        return self.mEditorContext.mainMessageBar()

    def updateFieldFromExpression(self):

        filtered = self.mMainView.filterMode() != QgsAttributeTableFilterModel.ShowAll
        filteredIds = self.mMainView.filteredFeatures() if filtered else []
        self.runFieldCalculation(self.mLayer, self.mFieldCombo.currentField(),
                                 self.mUpdateExpressionText.asExpression(), filteredIds)

    def updateFieldFromExpressionSelected(self):

        filteredIds = self.mLayer.selectedFeatureIds()
        self.runFieldCalculation(self.mLayer, self.mFieldCombo.currentField(),
                                 self.mUpdateExpressionText.asExpression(), filteredIds)

    def _filterExpressionBuilder(self):
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.mLayer))

        # taken from qgsfeaturefilterwidget.cpp : void QgsFeatureFilterWidget::filterExpressionBuilder()
        dlg = QgsExpressionBuilderDialog(self.mLayer, self.mFilterQuery.text(),
                                                                    self,
                                                                    'generic', context)
        dlg.setWindowTitle('Expression Based Filter')
        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        dlg.setGeomCalculator(myDa)

        if dlg.exec() == QDialog.Accepted:
            self.setFilterExpression(dlg.expressionText(), QgsAttributeForm.ReplaceFilter, True)

    def _filterQueryAccepted(self):
        if self.mFilterQuery.text().strip() == '':
            self._filterShowAll()
        else:
            self._filterQueryChanged(self.mFilterQuery.text())

    def _filterShowAll(self):
        self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowAll)

    def _filterQueryChanged(self, query):
        self.setFilterExpression(query)

    def runFieldCalculation(self, layer: QgsVectorLayer,
                            fieldName: str,
                            expression: str,
                            filteredIds: list):
        fieldindex = layer.fields().indexFromName(fieldName)
        if fieldindex < 0:
            # // this shouldn't happen... but it did. There's probably some deeper underlying issue
            # // but we may as well play it safe here.
            QMessageBox.critical(None, tr("Update Attributes"),
                                 "An error occurred while trying to update the field {}".format(fieldName))
            return

        # cursorOverride = QgsTemporaryCursorOverride(Qt.WaitCursor)
        self.mLayer.beginEditCommand("Field calculator")

        calculationSuccess = True
        error = None

        exp = QgsExpression(expression)
        da = QgsDistanceArea()
        da.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        exp.setGeomCalculator(da)
        exp.setDistanceUnits(QgsProject.instance().distanceUnits())
        exp.setAreaUnits(QgsProject.instance().areaUnits())
        useGeometry: bool = exp.needsGeometry()

        request = QgsFeatureRequest(self.mMainView.masterModel().request())
        useGeometry = useGeometry or not request.filterRect().isNull()
        request.setFlags(QgsFeatureRequest.NoFlags if useGeometry else QgsFeatureRequest.NoGeometry)

        rownum = 1

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        exp.prepare(context)

        fld: QgsField = layer.fields().at(fieldindex)

        referencedColumns = exp.referencedColumns()
        referencedColumns.add(
            fld.name())  # need existing column value to store old attribute when changing field values
        request.setSubsetOfAttributes(referencedColumns, layer.fields())

        task = QgsScopedProxyProgressTask(tr("Calculating field"))

        count = len(filteredIds) if len(filteredIds) > 0 else layer.featureCount()
        i = 0

        for feature in layer.getFeatures(request):

            if len(filteredIds) > 0 and feature.id() not in filteredIds:
                continue

            i += 1
            task.setProgress(i / count * 100)
            context.setFeature(feature)
            context.lastScope().addVariable(QgsExpressionContextScope.StaticVariable("row_number", rownum, True))

            value = exp.evaluate(context)
            convertError = None
            try:
                value = fld.convertCompatible(value)
            except SystemError as ex:
                error = 'Unable to convert "{}" to type {}'.format(value, fld.typeName())
            # Bail if we have a update error
            if exp.hasEvalError():
                calculationSuccess = False
                error = exp.evalErrorString()
                break
            elif isinstance(error, str):
                calculationSuccess = False
                break
            else:
                oldvalue = feature.attributes()[fieldindex]
                self.mLayer.changeAttributeValue(feature.id(), fieldindex, value, oldvalue)
            rownum += 1

        # cursorOverride.release()
        # task.reset()

        if not calculationSuccess:
            QMessageBox.critical(None,
                                 tr("Update Attributes"),
                                 "An error occurred while evaluating the calculation string:\n{}".format(error))
            self.mLayer.destroyEditCommand()

        else:
            self.mLayer.endEditCommand()

            # refresh table with updated values
            # fixes https:#github.com/qgis/QGIS/issues/25210
            masterModel: QgsAttributeTableModel = self.mMainView.masterModel()
            modelColumn: int = masterModel.fieldCol(fieldindex)
            masterModel.reload(masterModel.index(0, modelColumn),
                               masterModel.index(masterModel.rowCount() - 1, modelColumn))

    def layerActionTriggered(self):
        action = self.sender()
        if isinstance(action, QAction):
            action: QgsAction = action.data()

            context: QgsExpressionContext = self.mLayer.createExpressionContext()
            scope = QgsExpressionContextScope()
            scope.addVariable(QgsExpressionContextScope.StaticVariable("action_scope", "AttributeTable"))
            context.appendScope(scope)
            action.run(context)

    def formFilterSet(self, filter: str, filterType: QgsAttributeForm.FilterType):
        self.setFilterExpression(filter, filterType, True)

    def setFilterExpression(self,
                            filterString: str,
                            filterType: QgsAttributeForm.FilterType = QgsAttributeForm.ReplaceFilter,
                            alwaysShowFilter: bool = False):

        # as long we have no filter widget implementation
        if filterString is None:
            filterString = ''

        messageBar: QgsMessageBar = self.mainMessageBar()

        assert isinstance(self.mFilterQuery, QgsFilterLineEdit)
        filter = self.mFilterQuery.text()
        if filter != '' and filterString != '':
            if filterType == QgsAttributeForm.ReplaceFilter:
                filter = filterString
            elif filterType == QgsAttributeForm.FilterAnd:
                filter = f'({filter}) AND ({filterString})'
            elif filterType == QgsAttributeForm.FilterOr:
                filter = f'({filter}) OR ({filterString})'
        elif len(filterString) > 0:
            filter = filterString
        else:
            self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowAll)
            return
        self.mFilterQuery.setText(filter)

        filterExpression: QgsExpression = QgsExpression(filter)
        context: QgsExpressionContext = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.mLayer))
        fetchGeom: bool = filterExpression.needsGeometry()

        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        filterExpression.setGeomCalculator(myDa)
        filterExpression.setDistanceUnits(QgsProject.instance().distanceUnits())
        filterExpression.setAreaUnits(QgsProject.instance().areaUnits())

        if filterExpression.hasParserError():
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Parsing error', filterExpression.parserErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Parsing errors: {filterExpression.parserErrorString()}', file=sys.stderr)

        if not filterExpression.prepare(context):
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Evaluation error', filterExpression.evalErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Evaluation error {filterExpression.evalErrorString()}', file=sys.stderr)
            return

        filteredFeatures = []

        request = self.mMainView.masterModel().request()
        request.setSubsetOfAttributes(filterExpression.referencedColumns(), self.mLayer.fields())
        if not fetchGeom:
            request.setFlags(QgsFeatureRequest.NoGeometry)
        else:
            request.setFlags(request.flags() & QgsFeatureRequest.NoGeometry)

        for f in self.mLayer.getFeatures(request):
            context.setFeature(f)
            if filterExpression.evaluate(context) != 0:
                filteredFeatures.append(f.id())
            if filterExpression.hasEvalError():
                break

        self.mMainView.setFilteredFeatures(filteredFeatures)

        if filterExpression.hasEvalError():
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Error filtering', filterExpression.evalErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Error filtering: {filterExpression.evalErrorString()}', file=sys.stderr)
            return
        self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowFilteredList)


    def viewModeChanged(self, mode: QgsAttributeEditorContext.Mode):
        if mode != QgsAttributeEditorContext.SearchMode:
            self.mActionSearchForm.setChecked(False)

    def scheduleTitleUpdate(self):

        self.mUpdateTrigger.start(2000)
        s = ""

    def updateTitle(self):
        self.mUpdateTrigger.stop()
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        w = self.mDock if isinstance(self.mDock, QWidget) else self
        w.setWindowTitle(" {0} :: Features Total: {1} Filtered: {2}, Selected: {3}".format(
            self.mLayer.name(),
            max(self.mMainView.featureCount(), self.mLayer.featureCount()),
            self.mMainView.filteredFeatureCount(),
            self.mLayer.selectedFeatureCount())
        )

        if self.mMainView.filterMode() == QgsAttributeTableFilterModel.ShowAll:
            self.mRunFieldCalc.setText(tr("Update All"))
        else:
            self.mRunFieldCalc.setText(tr("Update Filtered"))

        canDeleteFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        enabled = self.mLayer.selectedFeatureCount() > 0
        self.mRunFieldCalcSelected.setEnabled(enabled)
        self.mActionDeleteSelected.setEnabled(canDeleteFeatures and self.mLayer.isEditable() and enabled)
        self.mActionCutSelectedRows.setEnabled(canDeleteFeatures and self.mLayer.isEditable() and enabled)
        self.mActionCopySelectedRows.setEnabled(enabled)

    def editingToggled(self):
        self.mActionToggleEditing.blockSignals(True)
        self.mActionToggleEditing.setChecked(self.mLayer.isEditable())
        self.mActionSaveEdits.setEnabled(self.mLayer.isEditable())
        self.mActionReload.setEnabled(not self.mLayer.isEditable())
        self.updateMultiEditButtonState()
        if self.mLayer.isEditable():
            self.mActionSearchForm.setChecked(False)

        self.mActionToggleEditing.blockSignals(False)

        canChangeAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.ChangeAttributeValues
        canDeleteFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        canAddAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddAttributes
        canDeleteAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteAttributes
        canAddFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures
        self.mActionAddAttribute.setEnabled((canChangeAttributes or canAddAttributes) and self.mLayer.isEditable())
        self.mActionRemoveAttribute.setEnabled(canDeleteAttributes and self.mLayer.isEditable())
        self.mActionDeleteSelected.setEnabled(
            canDeleteFeatures and self.mLayer.isEditable() and self.mLayer.selectedFeatureCount() > 0)
        self.mActionCutSelectedRows.setEnabled(
            canDeleteFeatures and self.mLayer.isEditable() and self.mLayer.selectedFeatureCount() > 0)
        self.mActionAddFeature.setEnabled(canAddFeatures and self.mLayer.isEditable())
        self.mActionPasteFeatures.setEnabled(canAddFeatures and self.mLayer.isEditable())
        self.mActionToggleEditing.setEnabled((canChangeAttributes or
                                              canDeleteFeatures or
                                              canAddAttributes or
                                              canDeleteAttributes or
                                              canAddFeatures) and not self.mLayer.readOnly())

        self.mUpdateExpressionBox.setVisible(self.mLayer.isEditable())
        if self.mLayer.isEditable() and self.mFieldCombo.currentIndex() == -1:
            self.mFieldCombo.setCurrentIndex(0)

        # not necessary to set table read only if layer is not editable
        # because model always reflects actual state when returning item flags
        actions = self.mLayer.actions().actions("Layer")

        if len(actions) == 0:
            self.mActionFeatureActions.setVisible(True)
        else:
            actionMenu = QMenu()
            constActions = actions
            for action in constActions:

                if not self.mLayer.isEditable() and action.isEnabledOnlyWhenEditable():
                    continue

                    qAction: QAction = actionMenu.addAction(action.icon(), action.shortTitle())
                    qAction.setToolTip(action.name())
                    qAction.setData(QVariant.fromValue < QgsAction > (action))
                    qAction.triggered.connect(selflayerActionTriggered)

            self.mActionFeatureActions.setMenu(actionMenu)

    def setCadDockWidget(self, cadDockWidget):
        self.mEditorContext.setCadDockWidget(cadDockWidget)

    def mActionPasteFeatures_triggered(self):
        self.vectorLayerTools().pasteFromClipboard(self.mLayer)

    def mActionReload_triggered(self):
        self.mMainView.masterModel().layer().dataProvider().reloadData()

    def mActionInvertSelection_triggered(self):
        self.vectorLayerTools().invertSelection(self.mLayer)

    def mActionRemoveSelection_triggered(self):
        self.vectorLayerTools().removeSelection(self.mLayer)

    def mActionSelectAll_triggered(self):
        self.vectorLayerTools().selectAll(self.mLayer)

    def mActionZoomMapToSelectedRows_triggered(self):
        self.vectorLayerTools().zoomToSelected(self.mLayer)

    def mActionPanMapToSelectedRows_triggered(self):
        self.vectorLayerTools().panToSelected(self.mLayer)

    def mActionDeleteSelected_triggered(self):
        self.vectorLayerTools().deleteSelection(self.mLayer)

    def reloadModel(self):
        """
        Reloads the table model
        """
        masterModel = self.mMainView.masterModel()
        # // update model - a field has been added or updated
        masterModel.reload(masterModel.index(0, 0),
                           masterModel.index(masterModel.rowCount() - 1,
                                             masterModel.columnCount() - 1))

    def mActionAddAttribute_triggered(self):
        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable():
            d = AddAttributeDialog(self.mLayer)
            d.exec_()
            if d.result() == QDialog.Accepted:
                field = d.field()
                self.mLayer.addAttribute(field)
                self.reloadModel()

    def mActionRemoveAttribute_triggered(self):
        if not (isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable()):
            return

        d = RemoveAttributeDialog(self.mLayer)

        if d.exec_() == QDialog.Accepted:
            fieldIndices = d.fieldIndices()
            self.mLayer.beginEditCommand('Delete attributes')
            if self.mLayer.deleteAttributes(fieldIndices):
                self.mLayer.endEditCommand()
            else:
                self.mainMessageBar().pushMessage(tr("Attribute error"),
                                                  tr("The attribute(s) could not be deleted"),
                                                  Qgis.Warning)
            self.reloadModel()

    def mMainView_currentChanged(self, viewMode: QgsDualView.ViewMode):
        if isinstance(viewMode, int):
            for m in [QgsDualView.AttributeTable, QgsDualView.AttributeEditor]:
                if int(m) == viewMode:
                    viewMode = m
                    break

        assert isinstance(viewMode, QgsDualView.ViewMode)
        self.mMainViewButtonGroup.button(viewMode).click()
        self.updateMultiEditButtonState()

        if viewMode == QgsDualView.AttributeTable:
            self.mActionSearchForm.setChecked(False)

        s = QgsSettings()
        s.setValue("/qgis/attributeTableLastView", int(viewMode))

    def showContextMenu(self, menu: QgsActionMenu, fid: int):
        if self.mLayer.isEditable():
            qAction = menu.addAction(QgsApplication.getThemeIcon("/mActionDeleteSelectedFeatures.svg"),
                                     tr("Delete Feature"))
            qAction.triggered.connect(lambda *args, f=fid: self.deleteFeature(fid))

    def deleteFeature(self, fid: int):
        self.mLayer.deleteFeature(fid)

    def mActionAddFeature_triggered(self):

        if not self.mLayer.isEditable():
            return

        masterModel = self.mMainView.masterModel()
        f = QgsFeature(self.mLayer.fields())
        if self.vectorLayerTools().addFeature(
                self.mLayer,
                f=f
        ):
            masterModel.reload(masterModel.index(0, 0), masterModel.index(
                masterModel.rowCount() - 1, masterModel.columnCount() - 1))

    def mActionExpressionSelect_triggered(self):
        dlg = QgsExpressionSelectionDialog(self.mLayer)
        dlg.setMessageBar(self.mainMessageBar())
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.exec_()

    def mActionCutSelectedRows_triggered(self):
        self.vectorLayerTools().cutSelectionToClipboard(self.mLayer)

    def mActionToggleEditing_toggled(self, b: bool):
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        # this has to be done, because in case only one cell has been changed and is still enabled, the change
        # would not be added to the mEditBuffer. By disabling, it looses focus and the change will be stored.
        s = ""
        if self.mLayer.isEditable() and \
                self.mMainView.tableView().indexWidget(self.mMainView.tableView().currentIndex()) is not None:
            self.mMainView.tableView().indexWidget(self.mMainView.tableView().currentIndex()).setEnabled(False)

        self.vectorLayerTools().toggleEditing(self.mLayer)
        self.editingToggled()

    def mActionSaveEdits_triggered(self):
        self.vectorLayerTools().saveEdits(self.mLayer, leave_editable=True, trigger_repaint=True)

    def setViewMode(self, mode: QgsDualView.ViewMode):
        assert isinstance(mode, QgsDualView.ViewMode)
        self.mMainView.setView(mode)
        for m in [QgsDualView.AttributeEditor, QgsDualView.AttributeTable]:
            self.mMainViewButtonGroup.button(m).setChecked(m == mode)

    def setFilterMode(self, mode: QgsAttributeTableFilterModel.FilterMode):

        return
        # todo: re-implement QgsFeatureFilterWidget

        if mode == QgsAttributeTableFilterModel.ShowVisible:
            self.mFeatureFilterWidget.filterVisible()
        elif mode == QgsAttributeTableFilterModel.ShowSelected:
            self.mFeatureFilterWidget.filterSelected()
        else:
            self.mFeatureFilterWidget.filterShowAll()

    def _hide_unconnected_widgets(self):
        self.mActionOpenFieldCalculator.setVisible(False)
        self.mActionDockUndock.setVisible(False)
