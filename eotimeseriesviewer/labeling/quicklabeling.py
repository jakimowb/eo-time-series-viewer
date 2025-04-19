import os.path
from typing import Dict, List, Optional, Tuple, Union

from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsCategorizedSymbolRenderer, QgsEditorWidgetSetup, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextScope, QgsExpressionContextUtils, QgsFeature, QgsField, QgsFields, QgsIconUtils, QgsMapLayer, \
    QgsProject, QgsRendererCategory, QgsSymbol, QgsVectorLayer
from qgis.PyQt.QtCore import QDateTime, QMetaType
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.labeling.editorconfig import EDITOR_WIDGET_REGISTRY_KEY, LabelConfigurationKey, \
    LabelShortcutType
from eotimeseriesviewer.qgispluginsupport.qps.classification.classificationscheme import ClassificationScheme, \
    ClassInfo, classSchemeFromConfig, EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
from eotimeseriesviewer.qgispluginsupport.qps.fieldvalueconverter import GenericPropertyTransformer
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource


def addQuickLabelMenu(menu: QMenu, layers, source):
    m: QMenu = menu.addMenu('Quick Labels')
    m.setToolTipsVisible(True)

    quick_label_layers = [l for l in layers if isQuickLabelLayer(l)]
    selected_quick_label_layer = [l for l in quick_label_layers if l.selectedFeatureCount() > 0]

    nQuickLabelLayers = len(selected_quick_label_layer)
    m.setEnabled(nQuickLabelLayers > 0)
    if nQuickLabelLayers == 0:
        m.setToolTip(
            'Add (i) vector layers with quick label fields<br>and (ii) select features to enable quick labeling.')
    else:
        # add shortcuts for automatically derived attributes per label group
        quick_label_groups = quickLayerGroups(quick_label_layers)
        for grp, lyr_fields in quick_label_groups.items():
            grp_layers = []
            for (lyr, field) in lyr_fields:
                if lyr not in grp_layers:
                    grp_layers.append(lyr)

            if grp == '':
                grp_info = ''
            else:
                grp_info = f'"{grp}"'

            a = m.addAction(f'Set quick labels {grp_info}'.strip())
            layerNames = [lyr.name() for lyr in grp_layers if lyr.selectedFeatureCount() > 0]
            if len(layerNames) > 0:
                tt = ['Writes quick label values to:']
                for lyr in grp_layers:
                    tt.append(f'"{lyr.name()}" {lyr.source()}')
                a.setToolTip('<br>'.join(tt))
                a.triggered.connect(lambda *args, layer_group=grp, _src=source:
                                    setAllQuickLabels(grp_layers, _src, label_group=layer_group))
            else:
                a.setEnabled(False)
                a.setToolTip('No features selected')

        for layer in quick_label_layers:
            assert isinstance(layer, QgsVectorLayer)
            csf = quickLabelClassSchemes(layer)
            if len(csf) > 0:
                a: QAction = m.addSection(layer.name())
                a.setToolTip(f'"{layer.name()}" {layer.source()}')
                a.setIcon(QgsIconUtils.iconForLayer(layer))
                for fieldname, cs in csf.items():
                    assert isinstance(cs, ClassificationScheme)
                    field: QgsField = layer.fields()[fieldname]
                    assert isinstance(field, QgsField)
                    classMenu = m.addMenu('{} [{}]'.format(fieldname, field.typeName()))
                    classMenu.setIcon(
                        QgsFields.iconForFieldType(field.type(), field.subType(), field.typeName()))
                    for classInfo in cs:
                        assert isinstance(classInfo, ClassInfo)
                        a = classMenu.addAction('{} "{}"'.format(classInfo.label(), classInfo.name()))
                        a.setIcon(classInfo.icon())
                        a.triggered.connect(
                            lambda _, vl=layer, f=field, c=classInfo: setQuickClassInfo(vl, f, c))


def isQuickLabelLayer(layer: QgsVectorLayer) -> bool:
    """
    Returns True if the layer contains any quick-label field
    :param layer: QgsVectorLayer
    :return: bool
    """
    if not (isinstance(layer, QgsVectorLayer) and layer.isValid()):
        return False
    for field in layer.fields():
        if isQuickLabelField(field):
            return True
    return False


def isQuickLabelField(field: QgsField) -> bool:
    setup: QgsEditorWidgetSetup = field.editorWidgetSetup()
    return setup.type() == EDITOR_WIDGET_REGISTRY_KEY


def isQuickClassificationField(field: QgsField) -> bool:
    """
    Returns True if the QgsField is used to describe a classification
    :param field:
    :return:
    """
    setup: QgsEditorWidgetSetup = field.editorWidgetSetup()
    if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
        return LabelShortcutType.fromConfig(setup.config()) == LabelShortcutType.Classification
    else:
        # other supported classification descriptions
        return setup.type() in [CS_KEY, 'Classification']


def quickLabelLayers(project: Optional[QgsProject] = None) -> List[QgsVectorLayer]:
    """
    Returns a list of known QgsVectorLayers with at least one LabelShortcutEditWidget
    :return: [list-of-QgsVectorLayer]
    """
    if project is None:
        project = QgsProject.instance()

    layers = []
    for layer in project.mapLayers().values():
        if isQuickLabelLayer(layer):
            layers.append(layer)
    return layers


def quickLayerGroups(layers: Union[List[QgsMapLayer], QgsMapLayer]) -> Dict[str, List[Tuple[QgsVectorLayer, str]]]:
    """
    Returns existing quick label groups and related vector layers + fields
    :param layers: list of vector layers
    :return:
    """
    if isinstance(layers, QgsMapLayer):
        layers = [layers]
    layers = [lyr for lyr in layers if isinstance(lyr, QgsVectorLayer)]

    groups = dict()
    for lyr in layers:
        for i, field in enumerate(lyr.fields()):
            setup = lyr.editorWidgetSetup(i)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                group = setup.config().get(LabelConfigurationKey.LabelGroup, '')
                groups[group] = groups.get(group, []) + [(lyr, field.name())]
    return groups


def setQuickClassInfo(vectorLayer: QgsVectorLayer,
                      field: Union[int, str, QgsField],
                      class_value: Union[int, str, ClassInfo]) -> List[int]:
    """
    Sets the ClassInfo value or label to selected features
    :param vectorLayer: QgsVectorLayer
    :param field: QgsField or int with field index
    :param class_value: ClassInfo
    """
    assert isinstance(vectorLayer, QgsVectorLayer)
    if not vectorLayer.isEditable():
        vectorLayer.startEditing()

    if isinstance(field, QgsField):
        iField = vectorLayer.fields().lookupField(field.name())
    elif isinstance(field, int):
        iField = field
        field = vectorLayer.fields().at(iField)

    elif isinstance(field, str):
        field = vectorLayer.fields()[field]
        iField = vectorLayer.fields().lookupField(field.name())

    assert isinstance(iField, int)
    assert isinstance(field, QgsField)

    changed_ids = []

    setup = field.editorWidgetSetup()
    cs: Optional[ClassificationScheme] = None

    if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
        config = setup.config()
        assert LabelConfigurationKey.LabelClassification in config
        cs = ClassificationScheme.fromMap(config[LabelConfigurationKey.LabelClassification])
    elif setup.type() == CS_KEY:
        cs = classSchemeFromConfig(setup.config())

    elif setup.type() == 'Classification':
        cs = ClassificationScheme.fromFeatureRenderer(vectorLayer.renderer())

    if isinstance(cs, ClassificationScheme):

        if isinstance(class_value, float):
            class_value = int(class_value)

        classInfo: Optional[ClassInfo] = None
        if isinstance(class_value, ClassInfo):
            classInfo = class_value
        else:
            for i, c in enumerate(cs.classInfos()):
                c: ClassInfo
                if class_value in [c, c.label(), c.name()]:
                    classInfo = c
                    break

        if isinstance(classInfo, ClassInfo):
            value = None
            if field.type() == QMetaType.QString:
                value = str(classInfo.name())
            elif field.type() in [QMetaType.Int, QMetaType.Long, QMetaType.LongLong,
                                  QMetaType.UInt, QMetaType.ULong, QMetaType.ULongLong]:
                value = classInfo.label()

            if value is not None:
                vectorLayer.beginEditCommand(f'Set class info "{field.name()}"')
                for feature in vectorLayer.selectedFeatures():
                    assert isinstance(feature, QgsFeature)
                    if vectorLayer.changeAttributeValue(feature.id(), iField, value):
                        changed_ids.append(feature.id())
                vectorLayer.endEditCommand()

    return changed_ids


def setAllQuickLabels(layers: List[QgsMapLayer],
                      source: Union[QDateTime, TimeSeriesDate, TimeSeriesSource],
                      label_group: str = ''):
    for lyr in layers:
        if isinstance(lyr, QgsVectorLayer) and lyr.selectedFeatureCount() > 0:
            setQuickLabels(lyr, source, label_group=label_group)


def setQuickLabels(vectorLayer: QgsVectorLayer,
                   source: Union[QDateTime, TimeSeriesDate, TimeSeriesSource, dict],
                   label_group: str = ''):
    """
    Labels selected features with information related to TimeSeriesDate "tsd", according to
    the settings specified in this model.

    Note: this does not add any ClassInfo. Use setQuickClassInfo instead.

    :param source: the information source to extract quick label information from
    :param label_group:
    :param vectorLayer:
    """

    assert isinstance(vectorLayer, QgsVectorLayer)
    if not vectorLayer.isEditable():
        vectorLayer.startEditing()

    vectorLayer.beginEditCommand('Set quick labels')

    context = QgsExpressionContext()
    context.appendScope(QgsExpressionContextUtils.globalScope())
    context.appendScope(QgsExpressionContextUtils.layerScope(vectorLayer))
    context.appendScope(quickLabelExpressionContextScope(source))

    quickLabelFieldInfos = []
    for field in vectorLayer.fields():
        if isQuickLabelField(field):
            config = field.editorWidgetSetup().config()
            labelType = LabelShortcutType.fromConfig(config)

            if labelType in LabelShortcutType.Autogenerated and config.get(LabelConfigurationKey.LabelGroup,
                                                                           '') == label_group:
                expr = quickLabelExpression(field)
                if expr != '':
                    info = {'field': field,
                            'iField': vectorLayer.fields().lookupField(field.name()),
                            'config': config,
                            'expr': expr,
                            'transformer': GenericPropertyTransformer(field)}
                    quickLabelFieldInfos.append(info)

    CHANGES: Dict[int, List[int]] = dict()
    for feature in vectorLayer.selectedFeatures():
        feature: QgsFeature
        fid = feature.id()
        featureContext = QgsExpressionContext(context)
        featureContext.setFeature(feature)
        featureContext.setGeometry(feature.geometry())

        for info in quickLabelFieldInfos:
            expr = QgsExpression(info['expr'])
            value = expr.evaluate(featureContext)
            # transform expression result into field data type
            value2 = info['transformer'].transform(featureContext, value)
            if vectorLayer.changeAttributeValue(fid, info['iField'], value2):
                ids = CHANGES.get(fid, [])
                ids.append(info['iField'])
                CHANGES[feature.id()] = ids

    vectorLayer.endEditCommand()

    return CHANGES


def quickLabelExpressionContextScope(
        source: Union[TimeSeriesSource, TimeSeriesDate, QDateTime, dict]) -> QgsExpressionContextScope:
    """
    Returns a QgsExpressionContextScope that describes the source
    :param source:
    :return: QgsExpressionContextScope
    """
    scope = QgsExpressionContextScope('eotsv_quicklabel')
    dtg = None
    sensor = None
    uri = None
    if isinstance(source, TimeSeriesDate):
        dtg = source.dtg()
        sensor = source.sensor()
    elif isinstance(source, TimeSeriesSource):
        dtg = source.dtg()
        uri = source.source()
        tsd = source.timeSeriesDate()
        if tsd:
            sensor = source.timeSeriesDate().sensor()
    elif isinstance(source, QDateTime):
        dtg = source

    elif isinstance(source, dict):
        dtg = source.get('dtg')
        if dtg:
            dtg = ImageDateUtils.datetime(dtg)
        sensor = source.get('sensor')
        uri = source.get('uri')

    if isinstance(dtg, QDateTime):
        scope.setVariable('datetime', dtg)
        scope.setVariable('date', dtg.date())
        scope.setVariable('time', dtg.time())
        scope.setVariable('decimal_year', ImageDateUtils.decimalYear(dtg))
        scope.setVariable('doy', ImageDateUtils.doiFromDateTime(dtg))

    if isinstance(uri, str):
        scope.setVariable('source_path', uri)
        scope.setVariable('source_name', os.path.basename(uri))

    if isinstance(sensor, SensorInstrument):
        scope.setVariable('sensor_name', sensor.name())
        scope.setVariable('sensor_id', sensor.id())
        scope.setVariable('sensor_nb', sensor.nb)
        # scope.setVariable('sensor_wl', sensor.wl)
    return scope


QUICK_LABEL_EXPRESSION_VARIABLES = {
    LabelShortcutType.DateTime: 'datetime',
    LabelShortcutType.Date: 'date',
    LabelShortcutType.Time: 'time',
    LabelShortcutType.DOY: 'doy',
    LabelShortcutType.DecimalYear: 'decimal_year',
    LabelShortcutType.SourceImage: 'source_path',
    LabelShortcutType.Sensor: 'sensor_name'
}


def quickLabelExpression(field: QgsField) -> Optional[str]:
    """
    Returns an expression string to calculate the requested quick label value for a QgsField
    :param field: QgsField
    :return: str
    """
    assert isinstance(field, QgsField)
    if not isQuickLabelField(field):
        return None

    config = field.editorWidgetSetup().config()

    typeValue = config.get(LabelConfigurationKey.LabelType, None)
    labelType = LabelShortcutType.fromValue(typeValue)

    if labelType == LabelShortcutType.Customized:
        return config.get(LabelConfigurationKey.LabelExpression)
    elif labelType in QUICK_LABEL_EXPRESSION_VARIABLES:
        return f'@{QUICK_LABEL_EXPRESSION_VARIABLES[labelType]}'
    else:
        return None


def quickLabelClassSchemes(layer: QgsVectorLayer) -> Dict[str, ClassificationScheme]:
    """
    Returns a list of (ClassificationScheme, QgsField) for all QgsFields with QgsEditorWidget
    being QgsClassificationWidgetWrapper, RasterClassification or EOTSV Quick Label with classification..
    :param layer: QgsVectorLayer
    :return: list [(ClassificationScheme, QgsField), ...]
    """
    assert isinstance(layer, QgsVectorLayer)
    from eotimeseriesviewer.qgispluginsupport.qps.classification.classificationscheme import \
        EDITOR_WIDGET_REGISTRY_KEY as CS_KEY
    from eotimeseriesviewer.qgispluginsupport.qps.classification.classificationscheme import classSchemeFromConfig

    schemes: Dict[str, ClassificationScheme] = dict()

    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        field: QgsField = layer.fields().at(i)

        assert isinstance(field, QgsField)
        assert isinstance(setup, QgsEditorWidgetSetup)

        field_name: str = field.name()

        cs = None

        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            config = setup.config()
            if LabelConfigurationKey.LabelClassification in config:
                cs = ClassificationScheme.fromMap(config[LabelConfigurationKey.LabelClassification])

        if setup.type() == CS_KEY:
            cs = classSchemeFromConfig(setup.config())

        elif setup.type() == 'Classification' and isinstance(layer.renderer(), QgsCategorizedSymbolRenderer):
            renderer = layer.renderer()
            cs = ClassificationScheme()
            for l, cat in enumerate(renderer.categories()):
                assert isinstance(cat, QgsRendererCategory)
                symbol = cat.symbol()
                assert isinstance(symbol, QgsSymbol)
                cs.insertClass(ClassInfo(l, name=cat.value(), color=symbol.color()))

        if isinstance(cs, ClassificationScheme) and len(cs) > 0:
            schemes[field_name] = cs
    return schemes


def labelShortcutLayerClassificationSchemes(layer: QgsVectorLayer):
    """
    Returns the ClassificationSchemes + QgsField used for labeling shortcuts
    :param layer: QgsVectorLayer
    :return: [(ClassificationScheme, QgsField), (ClassificationScheme, QgsField), ...]
    """
    classSchemes = []
    assert isinstance(layer, QgsVectorLayer)
    for i in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(i)
        assert isinstance(setup, QgsEditorWidgetSetup)
        if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
            conf = setup.config()
            ci = conf.get(LabelConfigurationKey.ClassificationScheme.value)
            if isinstance(ci, ClassificationScheme) and ci not in classSchemes:
                classSchemes.append((ci, layer.fields().at(i)))

    return classSchemes
