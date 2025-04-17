from typing import Dict

from qgis.core import QgsCategorizedSymbolRenderer, QgsEditorWidgetSetup, QgsField, QgsRendererCategory, QgsSymbol, \
    QgsVectorLayer

from eotimeseriesviewer.qgispluginsupport.qps.classification.classificationscheme import ClassificationScheme, ClassInfo


def layerClassSchemes(layer: QgsVectorLayer) -> Dict[str, ClassificationScheme]:
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

        if setup.type() == CS_KEY:
            cs = classSchemeFromConfig(setup.config())
            if isinstance(cs, ClassificationScheme) and len(cs) > 0:
                schemes[field_name] = cs

        elif setup.type() == 'Classification' and isinstance(layer.renderer(), QgsCategorizedSymbolRenderer):
            renderer = layer.renderer()
            cs = ClassificationScheme()
            for l, cat in enumerate(renderer.categories()):
                assert isinstance(cat, QgsRendererCategory)
                symbol = cat.symbol()
                assert isinstance(symbol, QgsSymbol)
                cs.insertClass(ClassInfo(l, name=cat.value(), color=symbol.color()))
            if len(cs) > 0:
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
