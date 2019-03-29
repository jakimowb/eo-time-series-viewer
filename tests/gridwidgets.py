
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from eotimeseriesviewer.utils import *

viewModes = ['timeXmapview', 'mapviewXtime', 'time2Xmapview']
class MapViewGridLayout(QGridLayout):

    def __init__(self):
        pass

    def setViewMode(self, viewMode=str):
        assert viewMode in viewModes




