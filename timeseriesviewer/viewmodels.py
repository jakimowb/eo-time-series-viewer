import sys, os
from qgis.core import *
from PyQt4.QtCore import *
from timeseriesviewer import *

import numpy as np
import pyqtgraph as pg
from timeseriesviewer.ui.widgets import *
from timeseriesviewer.timeseries import TimeSeries, TimeSeriesDatum, SensorInstrument






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

    #add component tests here:



    pixelData = dict()
    pixelData['geo_x'] = 1000
    pixelData['geo_y'] = 2000

    px = PixelCollection()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
