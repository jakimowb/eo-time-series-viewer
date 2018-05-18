

#
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from timeseriesviewer.utils import *
from timeseriesviewer.main import TimeSeriesViewer
from timeseriesviewer.mapvisualization import *
from timeseriesviewer.profilevisualization import *
from timeseriesviewer.timeseries import *
from timeseriesviewer import DIR_REPO, DIR_QGIS_RESOURCES

#DIR_SCREENSHOTS = jp(DIR_REPO, 'screenshots')
DIR_SCREENSHOTS = jp(DIR_REPO, 'doc/source/img/autogenerated')

os.makedirs(DIR_SCREENSHOTS, exist_ok=True)

app = initQgisApplication(qgisResourceDir=DIR_QGIS_RESOURCES)

TSV = TimeSeriesViewer(None)
TSV.show()

#set up example settings
from example.Images import Img_2014_04_21_LC82270652014111LGN00_BOA, re_2014_06_25
TSV.loadExampleTimeSeries()
#TS.loadImageFiles([Img_2014_04_21_LC82270652014111LGN00_BOA, re_2014_06_25])



sensorLS = None
sensorRE = None
for sensor in TSV.TS.sensors():
    assert isinstance(sensor, SensorInstrument)

    if sensor.id() == '6b30.0m0.49;0.56;0.66;0.84;1.65;2.2um':
        sensor.setName('Landsat')
        sensorLS = sensor
    if sensor.id() == '5b5.0m':
        sensor.setName('RapidEye')
        sensorRE = sensor

assert isinstance(sensorLS, SensorInstrument)
assert isinstance(sensorRE, SensorInstrument)


#add second MapView
TSV.createMapView()

mv1 = TSV.mapViews()[0]
mv2 = TSV.mapViews()[1]
assert isinstance(mv1, MapView)
assert isinstance(mv2, MapView)
mv1.setTitle('True Color')
mv2.setTitle('Short-Wave IR')

#set True Color Bands
for sensor in [sensorLS, sensorRE]:
    rendering = mv1.sensorWidget(sensor)
    assert isinstance(rendering, MapViewRenderSettings)
    renderer = rendering.rasterRenderer()
    assert isinstance(renderer, QgsMultiBandColorRenderer)
    renderer.setRedBand(3)
    renderer.setGreenBand(2)
    renderer.setBlueBand(1)
    rendering.setRasterRenderer(renderer)

#set swIR-nIR-R Bands
rendering = mv2.sensorWidget(sensorLS)
assert isinstance(rendering, MapViewRenderSettings)
renderer = rendering.rasterRenderer()
assert isinstance(renderer, QgsMultiBandColorRenderer)
renderer.setRedBand(4)
renderer.setGreenBand(5)
renderer.setBlueBand(3)
rendering.setRasterRenderer(renderer)

rendering = mv2.sensorWidget(sensorRE)
assert isinstance(rendering, MapViewRenderSettings)
renderer = rendering.rasterRenderer()
assert isinstance(renderer, QgsMultiBandColorRenderer)
renderer.setRedBand(5)
renderer.setGreenBand(4)
renderer.setBlueBand(3)
rendering.setRasterRenderer(renderer)

center = TSV.TS.getMaxSpatialExtent().spatialCenter()
from timeseriesviewer.mapcanvas import MapTools

TSV.onShowProfile(center, mv1.mapCanvases()[0], MapTools.CursorLocation)
#load data from other locations

TSV.ui.dockSpectralLibrary.setAddCurrentSpectraToSpeclibMode(True)

#collect exemplary profiles
for i, mc in enumerate(mv1.mapCanvases()):

    TSV.onShowProfile(center, mc, MapTools.SpectralProfile)
    if i == 10:
        break


ps2D_LS_NDVI = TSV.spectralTemporalVis.createNewPlotStyle2D()
ps2D_RE_NDVI = TSV.spectralTemporalVis.createNewPlotStyle2D()


for dx in range(-120, 120, 60):
    location = SpatialPoint(center.crs(), center.x() + dx, center.y())
    TSV.onShowProfile(location, mv1.mapCanvases()[0], MapTools.TemporalProfile)

TSV.spectralTemporalVis.loadMissingData(backgroundProcess=False)

TP = TSV.spectralTemporalVis.tpCollection[0]
ps2D_LS_NDVI.setSensor(sensorLS)
ps2D_LS_NDVI.setExpression('(b4-b3)/(b4+b3)')
ps2D_LS_NDVI.setTemporalProfile(TP)

ps2D_RE_NDVI.setSensor(sensorRE)
ps2D_RE_NDVI.setTemporalProfile(TP)
ps2D_RE_NDVI.setExpression('(b5-b3)/(b5+b3)')


TSV.spectralTemporalVis.updatePlot2D()
s = ""


def widgetScreenshot(widget, path):
    assert isinstance(widget, QWidget)
    rect = widget.rect()
    pixmap = QPixmap(rect.size())
    widget.render(pixmap, QPoint(), QRegion(rect))
    pixmap.save(path, quality=100)

def makePNG(widget, name):
    path = jp(DIR_SCREENSHOTS, name+'.png')
    widgetScreenshot(widget, path)

# makePNG(TS.ui, 'mainGUI')

for dockWidget in TSV.ui.findChildren(QDockWidget):
    assert isinstance(dockWidget, QDockWidget)
    #dockWidget.setFloating(True)
    name = dockWidget.objectName()
    dSize = dockWidget.size()
    #change sizes
    if name == 'cursorLocationInfoPanel':
        dockWidget.reloadCursorLocation()
        dockWidget.resize(QSize(300, 300))
        dockWidget.update()

    if name == 'mapViewPanel':
        dockWidget.setCurrentMapView(mv1)
        dockWidget.gbMapProperties.setCollapsed(True)
        dockWidget.gbMapProperties.update()
        mv1.ui.gbVectorRendering.setCollapsed(True)
        mv1.ui.gbVectorRendering.setChecked(False)
        mv1.ui.update()
        dockWidget.resize(QSize(300, 600))
        dockWidget.update()

    if name == 'sensorPanel':
        #dockWidget.setFixedHeight(200)
        dockWidget.setFixedSize(QSize(550, 100))
    if name == 'systemInfoPanel':
        dockWidget.setFixedHeight(400)

    if name == 'spectralLibraryPanel':
        dockWidget.setFixedSize(QSize(800, 250))
    if name == 'temporalProfilePanel':
        dockWidget.setFixedSize(QSize(800, 250))
    if name == 'timeseriesPanel':
        dockWidget.setFixedSize(QSize(800, 250))

    makePNG(dockWidget, name)
    #dockWidget.setFloating(False)


app.exec_()
#print('Done')
