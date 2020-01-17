import sys, importlib, site, os
from qgis.core import QgsApplication
from qgis.gui import QgisInterface
__version__ = '0.2'

def initResources():
    """
    Initializes compiled Qt resources
    """
    try:
        from .qpsresources import qInitResources
        qInitResources()
    except Exception as ex:
        print(ex, file=sys.stderr)
        print('It might be required to compile the qps/resources.py first', file=sys.stderr)


# make required modules available in case they are not part of the core-python installation
# if importlib.util.find_spec('pyqtgraph') is None:
#    path = os.path.join(os.path.dirname(__file__), *['externals', 'ext-pyqtgraph'])
#    site.addsitedir(path)
"""
try:
    import pyqtgraph
except:
    print('PyQtGraph is not installed. Use qps.externals.pyqtgraph instead.')
    import qps.externals.pyqtgraph
    sys.modules['pyqtgraph'] = qps.externals.pyqtgraph
"""

def registerEditorWidgets():
    """
    Call this function to register QgsEditorwidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'

    try:
        from .speclib.spectrallibraries import registerSpectralProfileEditorWidget
        registerSpectralProfileEditorWidget()
    except Exception as ex:
        print('Failed to call qps.speclib.spectrallibraries.registerSpectralProfileEditorWidget()', file=sys.stderr)
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



def initAll():

    initResources()
    registerEditorWidgets()