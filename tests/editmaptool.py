
from qgis.core import *
from qgis.gui import *
from eotimeseriesviewer.tests import initQgisApplication, TestObjects


app = initQgisApplication()

lyr = TestObjects.createRasterLayer()
QgsProject.instance().addMapLayer(lyr)
c = QgsMapCanvas()
c.setLayers([lyr])
c.setDestinationCrs(lyr.crs())
c.setExtent(c.fullExtent())
c.show()

d = QgsAdvancedDigitizingDockWidget(c)
d.show()
mapTool = QgsMapToolCapture(c, d, QgsMapToolCapture.CapturePolygon)
c.setMapTool(mapTool)
mapTool.activate()
app.exec_()