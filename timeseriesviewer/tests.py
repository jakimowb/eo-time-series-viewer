from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *



def test_gui():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer import PATH_EXAMPLE_TIMESERIES
    S = TimeSeriesViewer(None)
    S.run()

    if False:
        from timeseriesviewer import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = file_search(searchDir, '*band4.img', recursive=True)

        #searchDir = r'O:\SenseCarbonProcessing\BJ_NOC\01_RasterData\01_UncutVRT'
        #files = file_search(searchDir, '*BOA.vrt', recursive=True)

        files = files[0:10]
        S.loadImageFiles(files)
    if False:
        S.spatialTemporalVis.MVC.createMapView()
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=1)
    if True:
        S.loadTimeSeries(path=PATH_EXAMPLE_TIMESERIES, n_max=1)
    pass

def test_component():

    pass

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()

    #run tests
    if True: test_gui()
    if False: test_component()


    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
