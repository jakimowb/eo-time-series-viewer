# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'imagechipviewsettings_widget_base.ui'
#
# Created: Mon Oct 26 16:10:40 2015
#      by: PyQt4 UI code generator 4.10.2
#
# WARNING! All changes made in this file will be lost!

'''
/***************************************************************************
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 ***************************************************************************/
'''

import os, collections
from qgis.core import *
from qgis.gui import *
from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtXml import *
import PyQt4.QtWebKit


import sys, re, os, six

#widgets defined without UI file
class TsvScrollArea(QScrollArea):

    sigResized = pyqtSignal()
    def __init__(self, *args, **kwds):
        super(TsvScrollArea, self).__init__(*args, **kwds)

    def resizeEvent(self, event):
        super(TsvScrollArea, self).resizeEvent(event)
        self.sigResized.emit()


class VerticalLabel(QLabel):
    def __init__(self, text, orientation='vertical', forceWidth=True):
        QLabel.__init__(self, text)
        self.forceWidth = forceWidth
        self.orientation = None
        self.setOrientation(orientation)

    def setOrientation(self, o):
        if self.orientation == o:
            return
        self.orientation = o
        self.update()
        self.updateGeometry()

    def paintEvent(self, ev):
        p = QPainter(self)
        # p.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 200)))
        # p.setPen(QtGui.QPen(QtGui.QColor(50, 50, 100)))
        # p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))

        if self.orientation == 'vertical':
            p.rotate(-90)
            rgn = QRect(-self.height(), 0, self.height(), self.width())
        else:
            rgn = self.contentsRect()
        align = self.alignment()
        # align  = QtCore.Qt.AlignTop|QtCore.Qt.AlignHCenter

        self.hint = p.drawText(rgn, align, self.text())
        p.end()

        if self.orientation == 'vertical':
            self.setMaximumWidth(self.hint.height())
            self.setMinimumWidth(0)
            self.setMaximumHeight(16777215)
            if self.forceWidth:
                self.setMinimumHeight(self.hint.width())
            else:
                self.setMinimumHeight(0)
        else:
            self.setMaximumHeight(self.hint.height())
            self.setMinimumHeight(0)
            self.setMaximumWidth(16777215)
            if self.forceWidth:
                self.setMinimumWidth(self.hint.width())
            else:
                self.setMinimumWidth(0)

    def sizeHint(self):
        if self.orientation == 'vertical':
            if hasattr(self, 'hint'):
                return QSize(self.hint.height(), self.hint.width())
            else:
                return QSize(19, 50)
        else:
            if hasattr(self, 'hint'):
                return QSize(self.hint.width(), self.hint.height())
            else:
                return QSize(50, 19)




from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.utils import loadUIFormClass, DIR_UI, loadUi
from timeseriesviewer.main import SpatialExtent, QgisTsvBridge, TsvMimeDataUtils

"""
PATH_MAIN_UI = jp(DIR_UI, 'timeseriesviewer.ui')
PATH_MAPVIEWSETTINGS_UI = jp(DIR_UI, 'mapviewsettings.ui')
PATH_MAPVIEWRENDERSETTINGS_UI = jp(DIR_UI, 'mapviewrendersettings.ui')
PATH_MAPVIEWDEFINITION_UI = jp(DIR_UI, 'mapviewdefinition.ui')
PATH_TSDVIEW_UI = jp(DIR_UI, 'timeseriesdatumview.ui')
PATH_ABOUTDIALOG_UI = jp(DIR_UI, 'aboutdialog.ui')
PATH_SETTINGSDIALOG_UI = jp(DIR_UI, 'settingsdialog.ui')

PATH_PROFILEVIEWDOCK_UI = jp(DIR_UI, 'profileviewdock.ui')
PATH_RENDERINGDOCK_UI = jp(DIR_UI, 'renderingdock.ui')
"""



def maxWidgetSizes(layout, onHint=True):
    assert isinstance(layout, QBoxLayout)

    p = layout.parentWidget()
    m = layout.contentsMargins()

    sizeX = 0
    sizeY = 0
    horizontal = isinstance(layout, QHBoxLayout)

    for item in [layout.itemAt(i) for i in range(layout.count())]:
        wid = item.widget()
        ly = item.layout()
        if wid:
            if onHint:
                s = wid.sizeHint()
            else:
                s = wid.size()
        elif ly:
            continue
        else:
            continue
        if horizontal:
            sizeX += s.width() + layout.spacing()
            sizeY = max([sizeY, s.height()])  + layout.spacing()
        else:
            sizeX = max([sizeX, s.width()])  + layout.spacing()
            sizeY += s.height()  + layout.spacing()


    return QSize(sizeX + m.left()+ m.right(),
                 sizeY + m.top() + m.bottom())




class AboutDialogUI(QDialog,
                    loadUi('aboutdialog.ui')):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialogUI, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.init()

    def init(self):
        self.mTitle = self.windowTitle()
        self.listWidget.currentItemChanged.connect(lambda: self.setAboutTitle())
        self.setAboutTitle()

        # page About
        from timeseriesviewer import PATH_LICENSE, VERSION, DIR_DOCS, DESCRIPTION, WEBSITE, REPOSITORY
        import pyqtgraph
        self.labelAboutText.setText(
            """
            <html><head/><body>
            <p align="center">Version {version}
            </p>
            <p align="center">{description}
            </p>
            <p align="center">Website<br/>
            <a href="{website}"><span style=" text-decoration: underline; color:#0000ff;">{website}</span></a>
            </p>
            <p align="center">Repository<br/>
            <a href="{repo}"><span style=" text-decoration: underline; color:#0000ff;">{repo}</span></a>
            </p>
            
            <p align="center">Licenced under the GNU General Public Licence<br/>
            <a href="http://www.gnu.org/licenses/">
            <span style=" text-decoration: underline; color:#0000ff;">http://www.gnu.org/licenses/</span></a>
            </p>
            
            </body></html>
            """.format(description=DESCRIPTION, version=VERSION, website=WEBSITE, repo=REPOSITORY)
        )

        lf = lambda p: str(open(p).read())
        # page Changed
        self.tbChanges.setText(lf(jp(DIR_DOCS, 'CHANGES.html')))

        # page Credits
        self.CREDITS = dict()
        self.CREDITS['QGIS'] = lf(jp(DIR_DOCS, 'README_QGIS.html'))
        self.CREDITS['PYQTGRAPH'] = lf(jp(DIR_DOCS, 'README_PyQtGraph.html'))
        self.webViewCredits.setHtml(self.CREDITS['QGIS'])
        self.btnPyQtGraph.clicked.connect(lambda: self.showCredits('PYQTGRAPH'))
        self.btnQGIS.clicked.connect(lambda: self.showCredits('QGIS'))

        # page License
        self.tbLicense.setText(lf(PATH_LICENSE))


    def showCredits(self, key):
        self.webViewCredits.setHtml(self.CREDITS[key])
        self.setAboutTitle(key)

    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)


class TimeSeriesDatumViewUI(QFrame, loadUi('timeseriesdatumview.ui')):

    def __init__(self, title='<#>', parent=None):
        super(TimeSeriesDatumViewUI, self).__init__(parent)
        self.setupUi(self)

    def sizeHint(self):
        m = self.layout().contentsMargins()

        s = QSize(0, 0)

        for w in [self.layout().itemAt(i).widget() for i in range(self.layout().count())]:
            if w:
                s = s + w.size()

        if isinstance(self.layout(), QVBoxLayout):
            s = QSize(self.line.width() + m.left() + m.right(),
                      s.height() + m.top() + m.bottom())
        else:
            s = QSize(self.line.heigth() + m.top() + m.bottom(),
                      s.width() + m.left() + m.right())

        return s





class PropertyDialogUI(QDialog, loadUi('settingsdialog.ui')):

    def __init__(self, parent=None):
        super(PropertyDialogUI, self).__init__(parent)
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
    d = AboutDialogUI()
    d.show()

    d = PropertyDialogUI()
    d.exec_()
    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()
