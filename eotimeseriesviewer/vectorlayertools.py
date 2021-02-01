

from qgis.PyQt.QtCore import pyqtSignal
from .externals.qps.vectorlayertools import VectorLayerTools

class EOTSVVectorLayerTools(VectorLayerTools):

    sigFocusVisibility = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(EOTSVVectorLayerTools, self).__init__(*args, **kwds)

    def focusVisibility(self):
        self.sigFocusVisibility.emit()