import inspect
import os
import six
import traceback
import sys
import importlib
import re
import site
import logging
logger = logging.getLogger(__name__)
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *


DIR_REPO = os.path.normpath(os.path.split(inspect.getfile(inspect.currentframe()))[0])
DIR_SITE_PACKAGES = None
class TimeSeriesViewerPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.tsv = None
        import console.console as CONSOLE
        if CONSOLE._console is None:
            CONSOLE._console = CONSOLE.PythonConsole(iface.mainWindow())
            QTimer.singleShot(0, CONSOLE._console.activate)


    def initGui(self):
        self.toolbarActions = []
        syspaths = [os.path.normpath(p) for p in sys.path]
        if DIR_REPO not in syspaths: sys.path.append(DIR_REPO)

        import timeseriesviewer.ui.resources_py2
        timeseriesviewer.ui.resources_py2.qInitResources()
        # add platform independent site-packages
        if DIR_SITE_PACKAGES:
            site.addsitedir(DIR_SITE_PACKAGES)

        import timeseriesviewer
        # init main UI
        from timeseriesviewer import DIR_UI, jp
        icon = QIcon(jp(DIR_UI, *['icons', 'icon.png']))
        action = QAction(icon, 'HUB Time Series Viewer', self.iface)
        action.triggered.connect(self.run)
        self.toolbarActions.append(action)


        for action in self.toolbarActions:
            self.iface.addToolBarIcon(action)

    def run(self):
        from timeseriesviewer.main import TimeSeriesViewer
        # open QGIS python console. this is required to allow for print() statements in the source code.

        if self.tsv is None:
            self.tsv = TimeSeriesViewer(self.iface)
            self.tsv.run()
        self.tsv.ui.show()


    def unload(self):
        from timeseriesviewer.main import TimeSeriesViewer

        #print('Unload plugin')
        for action in self.toolbarActions:
            print(action)
            self.iface.removeToolBarIcon(action)

        if isinstance(self.tsv, TimeSeriesViewer):
            self.tsv.ui.close()
            self.tsv = None


    def tr(self, message):
        return QCoreApplication.translate('TimeSeriesViewerPlugin', message)