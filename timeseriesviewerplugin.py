# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              HUB TimeSeriesViewer
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
from __future__ import absolute_import
import os, sys, site
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *



class TimeSeriesViewerPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.tsv = None
        import console.console as CONSOLE
        if CONSOLE._console is None:
            CONSOLE._console = CONSOLE.PythonConsole(iface.mainWindow())
            QTimer.singleShot(0, CONSOLE._console.activate)


        dirPlugin = os.path.dirname(__file__)
        site.addsitedir(dirPlugin)

        #run a dependency check
        self.initialDependencyCheck()

    def initGui(self):
        self.toolbarActions = []

        dir_repo = os.path.dirname(__file__)
        site.addsitedir(dir_repo)
        site.addsitedir(os.path.join(dir_repo, 'site-packages'))

        assert isinstance(self.iface, QgisInterface)

        import timeseriesviewer
        # init main UI
        from timeseriesviewer import DIR_UI, jp, TITLE
        icon = timeseriesviewer.icon()
        action = QAction(icon, TITLE, self.iface)
        action.triggered.connect(self.run)
        self.toolbarActions.append(action)


        for action in self.toolbarActions:
            self.iface.addToolBarIcon(action)
            self.iface.addPluginToRasterMenu(TITLE, action)


    def initialDependencyCheck(self):
        """
        Runs a check for availability of package dependencies and give an readible error message
        :return:
        """

        missing = []
        from timeseriesviewer import DEPENDENCIES, messageLog
        for package in DEPENDENCIES:
            try:
                __import__(package)

            except Exception as ex:
                missing.append(package)
        if len(missing) > 0:

            n = len(missing)

            longText = ['Unable to import the following package(s):']
            longText.append('<b>{}</b>'.format(', '.join(missing)))
            longText.append('<p>Please run your local package manager(s) with root rights to install them.')
            #longText.append('More information is available under:')
            #longText.append('<a href="http://enmap-box.readthedocs.io/en/latest/Installation.html">http://enmap-box.readthedocs.io/en/latest/Installation.html</a> </p>')

            longText.append('This Python:')
            longText.append('Executable: {}'.format(sys.executable))
            longText.append('ENVIRON:')
            for k in sorted(os.environ.keys()):
                longText.append('\t{} ={}'.format(k, os.environ[k]))

            longText = '<br/>\n'.join(longText)
            messageLog(longText)
            raise Exception(longText)



    def run(self):
        from timeseriesviewer.main import TimeSeriesViewer
        self.tsv = TimeSeriesViewer(self.iface)
        self.tsv.run()


    def unload(self):
        from timeseriesviewer.main import TimeSeriesViewer

        for action in self.toolbarActions:
            self.iface.removeToolBarIcon(action)

        if isinstance(self.tsv, TimeSeriesViewer):
            self.tsv.ui.close()
            self.tsv = None


    def tr(self, message):
        return QCoreApplication.translate('TimeSeriesViewerPlugin', message)