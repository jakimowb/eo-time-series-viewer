

#
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from eotimeseriesviewer.tests import initQgisApplication
app = initQgisApplication()
from eotimeseriesviewer.utils import *
from eotimeseriesviewer.main import TimeSeriesViewer
from eotimeseriesviewer.mapvisualization import *
from eotimeseriesviewer.profilevisualization import *
from eotimeseriesviewer.timeseries import *
from eotimeseriesviewer import DIR_REPO, DIR_QGIS_RESOURCES

#DIR_SCREENSHOTS = jp(DIR_REPO, 'screenshots')

DIR_SCREENSHOTS = jp(DIR_REPO, 'doc/source/img/autogenerated.{}'.format(sys.platform))

os.makedirs(DIR_SCREENSHOTS, exist_ok=True)

DATE_OF_INTEREST = np.datetime64('2014-07-02')

TSV = TimeSeriesViewer()
TSV.show()
TSV.spatialTemporalVis.setMapSize(QSize(300, 150))
QApplication.processEvents()


#set up example settings
from example.Images import Img_2014_04_21_LC82270652014111LGN00_BOA, re_2014_06_25
if True:
    TSV.loadExampleTimeSeries()
    center = TSV.mTimeSeries.maxSpatialExtent().spatialCenter()
else:
    dirTestData = r'F:\TSData'
    files = list(file_search(dirTestData, re.compile('\.tif$')))
    assert len(files) > 0
    TSV.loadImageFiles(files)

    dirTestData = r'Y:\Pleiades'
    files = file_search(dirTestData, re.compile('\.JP2$'), recursive=True)
    assert len(files) > 0
    TSV.loadImageFiles(files)

    center = TSV.TS.maxSpatialExtent().spatialCenter()
    #x = 682430.2823150387
    #y = -751432.9531412527
    x = 682459.8471361337
    y = -751853.6488464196
    center = SpatialPoint(center.crs(), x, y)



dx = 500
#extent = SpatialExtent(center.crs(), center.x()-dx, center.y()-dx, center.x()+dx, center.y() + dx)
#extent = SpatialExtent(center.crs(), 681519.46197612234391272, -752814.23602663306519389, 683369.92926584207452834, -750963.76873691333457828)

extent = TSV.timeSeries()[0].spatialExtent()

date = np.datetime64('2014-08-01')
TSV.spatialTemporalVis.setSpatialExtent(extent)
dt = np.asarray([np.abs(tsd.date() - date) for tsd in TSV.timeSeries()])
i = np.argmin(dt)
TSV.spatialTemporalVis.navigateToTSD(TSV.timeSeries()[i])

QApplication.processEvents()

# TS.loadImageFiles([Img_2014_04_21_LC82270652014111LGN00_BOA, re_2014_06_25])

toHide = ['2014-07-18', '2014-08-08', '2014-08-10', '2014-08-23', '2014-08-25', '2014-08-03', '2014-07-26', '2014-07-10']
for tsd in TSV.timeSeries():
    assert isinstance(tsd, TimeSeriesDate)
    if str(tsd.date()) in toHide:
        tsd.setVisibility(False)

sensorLS = None
sensorRE = None
sensorPL = None
for sensor in TSV.mTimeSeries.sensors():
    assert isinstance(sensor, SensorInstrument)

    if sensor.id() == '[6, 30.0, 30.0, 3, [0.49, 0.56, 0.66, 0.84, 1.65, 2.2], "um"]':
        sensor.setName('Landsat')
        sensorLS = sensor
        continue
    if sensor.id() == '[5, 5.0, 5.0, 2, null, null]':
        sensor.setName('RapidEye')
        sensorRE = sensor
        continue
    if sensor.id() == '4b0.5m':
        sensor.setName('Pléiades')
        sensorPL = sensor
        continue
    else:
        s = ""

assert isinstance(sensorLS, SensorInstrument)
assert isinstance(sensorRE, SensorInstrument)

QApplication.processEvents()

#add second MapView
TSV.createMapView()

mv1 = TSV.mapViews()[0]
mv2 = TSV.mapViews()[1]
assert isinstance(mv1, MapView)
assert isinstance(mv2, MapView)
mv1.setTitle('True Color')
mv2.setTitle('Short-Wave IR')
TSV.spatialTemporalVis.adjustScrollArea()

if True:
    # set True Color Bands
    for sensor in TSV.timeSeries().sensors():
        lyr = mv1.sensorProxyLayer(sensor)
        assert isinstance(lyr, SensorProxyLayer)
        renderer = lyr.renderer().clone()
        assert isinstance(renderer, QgsMultiBandColorRenderer)
        renderer.setRedBand(3)
        renderer.setGreenBand(2)
        renderer.setBlueBand(1)
        lyr.setRenderer(renderer)

if True:
    # set swIR-nIR-R Bands
    for sensor in TSV.timeSeries().sensors():
        assert isinstance(sensor, SensorInstrument)
        lyr = mv2.sensorProxyLayer(sensor)
        if isinstance(lyr, SensorProxyLayer):
            renderer = lyr.renderer().clone()
            assert isinstance(renderer, QgsMultiBandColorRenderer)

            if lyr.sensor() == sensorLS:
                renderer.setRedBand(4)
                renderer.setGreenBand(5)
                renderer.setBlueBand(3)
            elif lyr.sensor() == sensorRE:
                renderer.setRedBand(5)
                renderer.setGreenBand(4)
                renderer.setBlueBand(3)

            lyr.setRenderer(renderer)


tsd = [tsd for tsd in TSV.timeSeries() if tsd.date() == DATE_OF_INTEREST][0]
TSV.setCurrentDate(tsd)

for c in TSV.mapCanvases():
    assert isinstance(c, MapCanvas)
    c.timedRefresh()
    c.waitWhileRendering()



# activate Crosshair
TSV.spatialTemporalVis.setCrosshairVisibility(True)

from eotimeseriesviewer.mapcanvas import MapTools

TSV.onShowProfile(center, mv1.mapCanvases()[0], MapTools.CursorLocation)
# load data from other locations

TSV.activateIdentifySpectralProfileMapTool()
TSV.activateIdentifyTemporalProfileMapTool()



#QApplication.processEvents()
#TSV.spatialTemporalVis.timedCanvasRefresh(force=True)


# collect exemplary profiles

import random
n = len(mv1.mapCanvases())
n = 20
dx = random.sample(range(-500, 500, 30), n)
dy = random.sample(range(-500, 500, 20), n)
for i, mc in enumerate(mv1.mapCanvases()):


    coordinate = SpatialPoint(center.crs(), center.x()+dx[i], center.y() + dy[i])
    TSV.onShowProfile(center, mc, MapTools.SpectralProfile)
    if i == 10:
        break

ps2D_LS_NDVI = TSV.spectralTemporalVis.createNewPlotStyle2D()
ps2D_RE_NDVI = TSV.spectralTemporalVis.createNewPlotStyle2D()


for dx in range(-120, 120, 60):
    location = SpatialPoint(center.crs(), center.x() + dx, center.y())
    TSV.onShowProfile(location, mv1.mapCanvases()[0], MapTools.TemporalProfile)

TSV.spectralTemporalVis.loadMissingData(backgroundProcess=False)

TP = TSV.spectralTemporalVis.mTemporalProfileLayer[0]
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
    pixmap = widget.grab()
    #pixmap = QPixmap(rect.size())
    #widget.render(pixmap, QPoint(), QRegion(rect))
    pixmap.save(path, quality=100)

def makePNG(widget, name):
    path = jp(DIR_SCREENSHOTS, name+'.png')
    widgetScreenshot(widget, path)

# makePNG(TS.ui, 'mainGUI')

TSV.ui.resize(QSize(1000, 600))

QApplication.processEvents()

widget = TSV.ui
makePNG(widget, 'maingui')

widget = TSV.spatialTemporalVis.scrollArea.viewport()
makePNG(widget, 'mapViews')


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
        makePNG(dockWidget, name)

    if name == 'mapViewPanel':
        dockWidget.setCurrentMapView(mv1)
        #dockWidget.resize(QSize(300, 600))
        dockWidget.update()
        makePNG(dockWidget, name)

    if name == 'sensorPanel':
        #dockWidget.setFixedHeight(200)
        dockWidget.resize(QSize(330, 125))
        makePNG(dockWidget, name)

    if name == 'systemInfoPanel':
        dockWidget.setFixedHeight(400)
        makePNG(dockWidget, name)

    if name == 'spectralLibraryPanel':
        dockWidget.resize(QSize(800, 250))

        makePNG(dockWidget, name)

    if name == 'temporalProfilePanel':
        dockWidget.resize(QSize(800, 250))
        for i in range(dockWidget.listWidget.count()):
            assert isinstance(dockWidget.listWidget, QListWidget)
            dockWidget.listWidget.setCurrentRow(i)
            page = dockWidget.stackedWidget.currentWidget()
            pageName = page.objectName()
            page.update()

            if pageName == 'page2D':
                dockWidget.plotWidget2D.update()
            elif pageName == 'page3D' and dockWidget.plotWidget3D is not None:

                dockWidget.plotWidget3D.update()
                dockWidget.plotWidget3D.paintGL()
                #dockWidget.plotWidget3D.repaint()
            dockWidget.repaint()
            makePNG(dockWidget, '{}.{}'.format(name, pageName))

    if name == 'timeseriesPanel':
        dockWidget.resize(QSize(800, 250))
        makePNG(dockWidget, name)

    #dockWidget.setFloating(False)


app.exec_()
#print('Done')
