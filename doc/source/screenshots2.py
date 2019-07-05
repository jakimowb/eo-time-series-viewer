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



DIR_SCREENSHOTS = jp(DIR_REPO, 'doc/source/img/autogenerated2.{}'.format(sys.platform))

os.makedirs(DIR_SCREENSHOTS, exist_ok=True)

SIZE_GUI = QSize(1024, 800)
SIZE_MAPCANVAS = QSize(200, 150)

# reference dates for Landsat + RapidEye -> cloud-free observation to optimize band-stretch for
REF_DATE_LS = np.datetime64('2014-06-24')
REF_DATE_RE = np.datetime64('2014-06-25')

TEMPORAL_PROFILE_LOCATIONS = 5
TEMPORAL_PROFILE_LOCATIONS_PLOTTED = 2

TSV = TimeSeriesViewer()
TSV.show()
TSV.setMapSize(SIZE_MAPCANVAS)
QApplication.processEvents()

def widgetScreenshot(widget, path):
    assert isinstance(widget, QWidget)
    QApplication.processEvents()
    rect = widget.rect()
    pixmap = widget.grab()
    #pixmap = QPixmap(rect.size())
    #widget.render(pixmap, QPoint(), QRegion(rect))
    pixmap.save(path, quality=100)

def blankGUI(bn:str):
    path = jp(DIR_SCREENSHOTS, bn)
    widgetScreenshot(TSV.ui, path)

def mapProperties(bn:str):

    path = jp(DIR_SCREENSHOTS, bn)
    d = TSV.ui.dockMapViews
    assert isinstance(d, MapViewDock)
    d.toolBox.setCurrentIndex(0)
    d.setFloating(True)
    d.resize(QSize(250, 275))
    QApplication.processEvents()
    widgetScreenshot(TSV.ui.dockMapViews, path)

    d.setFloating(False)
    s = ""


def rasterLayerProperties(bn:str):
    from eotimeseriesviewer.externals.qps.layerproperties import RasterLayerProperties, VectorLayerProperties

    path = jp(DIR_SCREENSHOTS, bn)


    for l in TSV.mMapLayerStore.mapLayers().values():
        if isinstance(l, QgsRasterLayer):
            canvas = QgsMapCanvas()
            canvas.setDestinationCrs(l.crs())
            canvas.setExtent(l.extent())
            d = RasterLayerProperties(l, canvas)
            d.show()
            d.mOptionsListWidget.setCurrentRow(1)

            widgetScreenshot(d, path)
            break
    pass

def temporalProfiles(bn:str):

    w = TSV.ui.dockProfiles

    for i in range(w.listWidget.count()):
        w.listWidget.setCurrentRow(i)
        path = jp(DIR_SCREENSHOTS, re.sub(r'(\.[^.]+)$', r'.page{}\1'.format(i+1), bn))
        widgetScreenshot(w, path)
    s = ""
    pass

def mapViews(bn:str):

    path = jp(DIR_SCREENSHOTS, bn)
    widgetScreenshot(TSV.ui, path)

if __name__ == '__main__':
    blankGUI('blank_gui.png')

    TSV.ui.resize(SIZE_GUI)

    mapView1 = TSV.createMapView()
    mapView2 = TSV.createMapView()
    mapView1.setTitle('True Color')
    mapView2.setTitle('Near Infrared')

    TSV.loadExampleTimeSeries(loadAsync=False)

    extent = TSV.timeSeries()[0].spatialExtent().__copy__()
    extent.scale(0.35)
    TSV.setSpatialExtent(extent)

    TSV.ui.dockTimeSeries.setFloating(True)
    QApplication.processEvents()
    TSV.ui.dockTimeSeries.setFloating(False)

    QApplication.processEvents()
    TSV.ui.dockTimeSeries.setMaximumHeight(100)
    QApplication.processEvents()

    TSV.showTimeSeriesDate(TSV.timeSeries().tsd(REF_DATE_LS,  None))

    REF_TSD_LS =TSV.timeSeries().tsd(REF_DATE_LS, None)
    REF_TSD_RE = TSV.timeSeries().tsd(REF_DATE_RE, None)
    assert isinstance(REF_TSD_LS, TimeSeriesDate)
    assert isinstance(REF_TSD_RE, TimeSeriesDate)

    # set sensor names
    sensorLS = None
    sensorRE = None
    for sensor in TSV.timeSeries().sensors():
        assert isinstance(sensor, SensorInstrument)
        id = json.loads(sensor.id())
        if id[0:3] == [6, 30., 30.]:
            sensor.setName('Landsat')
            sensorLS = sensor
        elif id[0:3] == [5, 5., 5.]:
            sensor.setName('RapidEye')
            sensorRE = sensor

    # set vectorlayer style
    vectorLayers = [l for l in QgsProject.instance().mapLayers().values() if isinstance(l, QgsVectorLayer)]
    vlNames = [l.name() for l in vectorLayers]
    # make testdata "exampleEvents" polygon fill-color transparent
    vlEventPolygons = vectorLayers[0]
    vlPOIs = vectorLayers[1]

    assert isinstance(vlEventPolygons, QgsVectorLayer)
    symbolLayer = vlEventPolygons.renderer().symbol().symbolLayer(0)
    assert isinstance(symbolLayer, QgsFillSymbolLayer)
    symbolLayer.setBrushStyle(Qt.NoBrush)
    symbolLayer.setStrokeColor(QColor('yellow'))
    QApplication.processEvents()

    def setBandCombination(c:MapCanvas, r, g, b):
        c.timedRefresh()
        sensorLayer = [l for l in c.layers() if isinstance(l, SensorProxyLayer)][0]
        renderer = sensorLayer.renderer()
        assert isinstance(renderer, QgsMultiBandColorRenderer)
        renderer.setRedBand(r)
        renderer.setGreenBand(g)
        renderer.setBlueBand(b)
        sensorLayer.setRenderer(renderer.clone())
        c.stretchToExtent(SpatialExtent.fromLayer(sensorLayer), 'linear_minmax', p=0.05)
        c.timedRefresh()

    # optimize sensor-specific data stretch
    for c in mapView1.mapCanvases():
        assert isinstance(c, MapCanvas)
        if c.tsd() == REF_TSD_LS:
            setBandCombination(c, 3, 2, 1)
        elif c.tsd() == REF_TSD_RE:
            setBandCombination(c, 3, 2, 1)

    for c in mapView2.mapCanvases():
        assert isinstance(c, MapCanvas)
        if c.tsd() == REF_TSD_LS:
            setBandCombination(c, 4, 5, 3)
        elif c.tsd() == REF_TSD_RE:
            setBandCombination(c, 5, 4, 3)

    # load temporal profiles


    TSV.ui.dockProfiles.setFloating(False)
    TSV.ui.dockProfiles.resize(QSize(1000, 400))
    TSV.ui.dockProfiles.splitter2D.setSizes([75, 50])
    TSV.ui.dockProfiles.show()

    STV = TSV.spectralTemporalVis
    assert isinstance(STV, SpectralTemporalVisualization)
    # load temporal profiles for points
    STV.temporalProfileLayer().createTemporalProfiles(vlPOIs)

    styles = STV.plotStyles()
    for s in styles:
        STV.removePlotStyles2D(s)

    for i, tp in enumerate(STV.temporalProfileLayer()):
        if i >= TEMPORAL_PROFILE_LOCATIONS_PLOTTED:
            break
        for sensor in TSV.sensors():
            style = STV.createNewPlotStyle2D()
            assert isinstance(style, TemporalProfile2DPlotStyle)
            style.setSensor(sensor)
            style.setTemporalProfile(tp)

            style.markerSymbol = None

            if sensor == sensorLS:
                style.setExpression('(b4 - b3)/(b4 + b3)')
                style.linePen.setStyle(Qt.SolidLine)
            if sensor == sensorRE:
                style.setExpression('(b5 - b3)/(b5 + b3)')
                style.linePen.setStyle(Qt.DotLine)


    mapProperties('mapviewdock_map.png')
    mapViews('mapviews.png')
    rasterLayerProperties('rasterlayer_properties.png')
    temporalProfiles('temporal_profiles.png')


app.exec_()