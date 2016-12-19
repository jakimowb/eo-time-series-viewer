from __future__ import absolute_import
import inspect
import os
import six
import traceback
import sys
import importlib
import re
import site

from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *


DIR_REPO = os.path.normpath(os.path.split(inspect.getfile(inspect.currentframe()))[0])
DIR_SITE_PACKAGES = None
class TSVPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.tsv = None



    def initGui(self):
        self.toolbarActions = []
        syspaths = [os.path.normpath(p) for p in sys.path]
        if DIR_REPO not in syspaths: sys.path.append(DIR_REPO)

        # add platform independent site-packages
        if DIR_SITE_PACKAGES:
            site.addsitedir(DIR_SITE_PACKAGES)

        from timeseriesviewer.main import TimeSeriesViewer

        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon = TimeSeriesViewer.icon()
        action = QAction(icon, self.tr(u'SenseCarbon Time Series Viewer'), self.iface.mainWindow())
        action.triggered.connect(self.run)
        self.toolbarActions.append(action)


        for action in self.toolbarActions:
            self.iface.addToolBarIcon(action)

    def run(self):
        from timeseriesviewer.main import TimeSeriesViewer
        # open QGIS python console. this is required to allow for print() statements in the source code.
        if isinstance(self.iface, QgisInterface):
            import console
            c = console.show_console()
            c.setVisible(True)

        self.tsv = TimeSeriesViewer(self.iface)
        self.tsv.run()

    def unload(self):
        from timeseriesviewer import dprint
        from timeseriesviewer.main import TimeSeriesViewer
        dprint('UNLOAD SenseCarbon TimeSeriesViewer Plugin')

        for action in self.toolbarActions:
            print(action)
            self.iface.removeToolBarIcon(action)

        if isinstance(self.tsv, TimeSeriesViewer):
            self.tsv.ui.close()
            self.tsv = None


    def tr(self, message):
        return QCoreApplication.translate('EnMAPBoxPlugin', message)