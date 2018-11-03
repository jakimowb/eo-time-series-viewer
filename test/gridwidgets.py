
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from timeseriesviewer.utils import *

viewModes = ['timeXmapview', 'mapviewXtime', 'time2Xmapview']
class MapViewGridLayout(QGridLayout):

    def __init__(self):
        pass

    def setViewMode(self, viewMode=str):
        assert viewMode in viewModes





if __name__ == '__main__':

    app = initQgisApplication()

    w = QWidget()
    l = MapViewGridLayout()
    w.setLayout(l)
    w.show()
    w.resize(QSize(300,200))

    app.exec_()