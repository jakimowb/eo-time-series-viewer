import sys
from qgis.core import QgsApplication

try:
    import qps.qpsresources
    qpsresources.qInitResources()
except Exception as ex:

    print(ex, file=sys.stderr)
    print('It might be required to compile the qps/resources.py first', file=sys.stderr)



def registerEditorWidgets():
    """
    Call this function to register QgsEditorwidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'

    try:
        import qps.speclib.spectrallibraries
        qps.speclib.spectrallibraries.registerSpectralProfileEditorWidget()
    except Exception as ex:
        print('Failed to call qps.speclib.spectrallibraries.registerSpectralProfileEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        import qps.speclib.qgsfunctions
        qps.speclib.qgsfunctions.registerQgsExpressionFunctions()
    except Exception as ex:
        print('Failed to call qps.speclib.qgsfunctions.registerQgsExpressionFunctions()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        import qps.classification.classificationscheme
        qps.classification.classificationscheme.registerClassificationSchemeEditorWidget()
    except Exception as ex:
        print('Failed to call qps.classification.classificationscheme.registerClassificationSchemeEditorWidget()',
              file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        import qps.plotstyling.plotstyling
        qps.plotstyling.plotstyling.registerPlotStyleEditorWidget()
    except Exception as ex:
        print('Failed to call qps.plotstyling.plotstyling.registerPlotStyleEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)


