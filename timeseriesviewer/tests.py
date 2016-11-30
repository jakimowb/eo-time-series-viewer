from __future__ import absolute_import
import six, sys, os, gc, re, collections, site, inspect
from osgeo import gdal, ogr

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *


class PictureTest(QMainWindow):

    def __init__(self, parent=None, qImage=None):
        super(PictureTest,self).__init__(parent)
        self.setWindowTitle("Show Image with pyqt")
        self.imageLabel=QLabel()
        self.imageLabel.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored)
        self.setCentralWidget(self.imageLabel)

        self.cv_img = None

        if qImage:
            self.addImage(qImage)

    def addImage(self, qImage):
        pxmap = QPixmap.fromImage(qImage)
        self.addPixmap(pxmap)

    def addPixmap(self, pixmap):
        pxmap = pixmap.scaled(self.imageLabel.size(), Qt.KeepAspectRatio)
        self.imageLabel.setPixmap(pxmap)
        self.imageLabel.adjustSize()
        self.imageLabel.update()

    def addNumpy(self, data):


        img = Array2Image(data)
        self.addImage(img)

        #self.resize(img.width(), img.height())


def test_gui():
    from timeseriesviewer.main import TimeSeriesViewer
    S = TimeSeriesViewer(None)
    S.run()
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
