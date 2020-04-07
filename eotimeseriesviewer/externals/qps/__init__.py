import sys, importlib, site, os, pathlib, typing
from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsMapLayerConfigWidgetFactory
__version__ = '0.3'

DIR_UI_FILES = pathlib.Path(__file__).parent / 'ui'
DIR_ICONS = DIR_UI_FILES / 'icons'
QPS_RESOURCE_FILE = pathlib.Path(__file__).parent / 'qpsresources_rc.py'


MAPLAYER_CONFIGWIDGET_FACTORIES = list()

def registerMapLayerConfigWidgetFactory(factory:QgsMapLayerConfigWidgetFactory):
    """
    Register a new tab in the map layer properties dialog.
    :param factory: QgsMapLayerConfigWidgetFactory
    :type factory:
    :return:
    :rtype:
    """
    assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
    if factory not in MAPLAYER_CONFIGWIDGET_FACTORIES:
        MAPLAYER_CONFIGWIDGET_FACTORIES.append(factory)

def unregisterMapLayerConfigWidgetFactory(factory:QgsMapLayerConfigWidgetFactory):
    """
    Unregister a previously registered tab in the map layer properties dialog.
    :param factory:
    :type factory:
    :return:
    :rtype:
    """
    assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
    while factory in MAPLAYER_CONFIGWIDGET_FACTORIES:
        MAPLAYER_CONFIGWIDGET_FACTORIES.remove(factory)

def mapLayerConfigWidgetFactories()->typing.List[QgsMapLayerConfigWidgetFactory]:
    """
    Returns registered QgsMapLayerConfigWidgetFactories
    :return: list of QgsMapLayerConfigWidgetFactories
    :rtype:
    """
    return MAPLAYER_CONFIGWIDGET_FACTORIES[:]

def registerEditorWidgets():
    """
    Call this function to register QgsEditorwidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'

    try:
        from .speclib.gui import registerSpectralProfileEditorWidget
        registerSpectralProfileEditorWidget()
    except Exception as ex:
        print('Failed to call qps.speclib.core.registerSpectralProfileEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .speclib.qgsfunctions import registerQgsExpressionFunctions
        registerQgsExpressionFunctions()
    except Exception as ex:
        print('Failed to call qps.speclib.qgsfunctions.registerQgsExpressionFunctions()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .classification.classificationscheme import registerClassificationSchemeEditorWidget
        registerClassificationSchemeEditorWidget()
    except Exception as ex:
        print('Failed to call qps.classification.classificationscheme.registerClassificationSchemeEditorWidget()',
              file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .plotstyling.plotstyling import registerPlotStyleEditorWidget
        registerPlotStyleEditorWidget()
    except Exception as ex:
        print('Failed to call qps.plotstyling.plotstyling.registerPlotStyleEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)


def registerMapLayerConfigWidgetFactories():
    from .layerconfigwidgets.rasterbands import RasterBandConfigWidgetFactory
    from .layerconfigwidgets.gdalmetadata import GDALMetadataConfigWidgetFactory

    registerMapLayerConfigWidgetFactory(RasterBandConfigWidgetFactory())
    registerMapLayerConfigWidgetFactory(GDALMetadataConfigWidgetFactory())

def initResources():
    from .testing import initResourceFile
    initResourceFile(QPS_RESOURCE_FILE)

def initAll():
    initResources()
    registerEditorWidgets()
    registerMapLayerConfigWidgetFactories()

