import os
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import PyQt4.QtWebKit

import sys, re, os, six

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.ui import loadUIFormClass, DIR_UI



load = lambda p : loadUIFormClass(jp(DIR_UI,p))

class ProfileViewDockUI(QgsDockWidget, load('profileviewdock.ui')):
    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)

class SensorDockUI(QgsDockWidget, load('sensordock.ui')):
    def __init__(self, parent=None):
        super(SensorDockUI, self).__init__(parent)
        self.setupUi(self)

class RenderingDockUI(QgsDockWidget, load('renderingdock.ui')):
    def __init__(self, parent=None):
        super(RenderingDockUI, self).__init__(parent)
        self.setupUi(self)

class NavigationDockUI(QgsDockWidget, load('navigationdock.ui')):
    def __init__(self, parent=None):
        super(NavigationDockUI, self).__init__(parent)
        self.setupUi(self)

class TimeSeriesDockUI(QgsDockWidget, load('timeseriesdock.ui')):
    def __init__(self, parent=None):
        super(TimeSeriesDockUI, self).__init__(parent)
        self.setupUi(self)

class MapViewDockUI(QgsDockWidget, load('mapviewdock.ui')):
    def __init__(self, parent=None):
        super(MapViewDockUI, self).__init__(parent)
        self.setupUi(self)

        self.dockLocationChanged.connect(self.adjustLayouts)

    def toogleLayout(self, p):
        newLayout = None
        l = p.layout()
        print('toggle layout {}'.format(str(p.objectName())))
        tmp = QWidget()
        tmp.setLayout(l)
        sMax = p.maximumSize()
        sMax.transpose()
        sMin = p.minimumSize()
        sMin.transpose()
        p.setMaximumSize(sMax)
        p.setMinimumSize(sMin)
        if isinstance(l, QVBoxLayout):
            newLayout = QHBoxLayout()
        else:
            newLayout = QVBoxLayout()
        print(l, '->', newLayout)

        while l.count() > 0:
            item = l.itemAt(0)
            l.removeItem(item)

            newLayout.addItem(item)


        p.setLayout(newLayout)
        return newLayout

    def adjustLayouts(self, area):
        return
        lOld = self.scrollAreaMapsViewDockContent.layout()
        if area in [Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea] \
            and isinstance(lOld, QVBoxLayout) or \
        area in [Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea] \
                        and isinstance(lOld, QHBoxLayout):

            #self.toogleLayout(self.scrollAreaMapsViewDockContent)
            self.toogleLayout(self.BVButtonList)

class LabelingDockUI(QgsDockWidget, load('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDockUI, self).__init__(parent)
        self.setupUi(self)


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
    #d = AboutDialogUI()
    #d.show()

    d = ProfileDockUI()
    d.show()
    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
