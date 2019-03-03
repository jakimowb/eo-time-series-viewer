# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2017-08-04
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import os, collections
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt import uic
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtXml import *


import sys, re, os, six
from timeseriesviewer import DIR_UI
from timeseriesviewer.utils import jp
# widgets defined without UI file

from timeseriesviewer.utils import loadUIFormClass


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




class AboutDialogUI(QDialog, loadUIFormClass(jp(DIR_UI, 'aboutdialog.ui'))):
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
        from timeseriesviewer import PATH_LICENSE, __version__, PATH_CHANGELOG, PATH_ABOUT
        self.labelVersion.setText('{}'.format(__version__))

        def readTextFile(path):
            if os.path.isfile(path):
                f = open(path, encoding='utf-8')
                txt = f.read()
                f.close()
            else:
                txt = 'unable to read {}'.format(path)
            return txt

        # page Changed
        self.tbAbout.setHtml(readTextFile(PATH_ABOUT))
        self.tbChanges.setText(readTextFile(PATH_CHANGELOG))
        self.tbLicense.setText(readTextFile(PATH_LICENSE))


    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)



