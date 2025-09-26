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
import logging
import os
import site
import sys
from typing import List

from eotimeseriesviewer import TITLE
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QApplication
from qgis.gui import QgisInterface

logger = logging.getLogger(__name__)


class EOTimeSeriesViewerPlugin:

    def __init__(self, iface):

        self.mEOTSV = None
        self.iface = iface
        dirPlugin = os.path.dirname(__file__)
        site.addsitedir(dirPlugin)

        import eotimeseriesviewer
        logger.debug('initial Dependency Check')
        # run a dependency check
        self.initialDependencyCheck()

        # initialize required settings
        logger.debug('init all')

        eotimeseriesviewer.initAll()

    def initGui(self):
        self.mToolbarActions: List[QAction] = []
        from qgis.utils import iface
        assert isinstance(self.iface, QgisInterface)

        import eotimeseriesviewer

        # init main UI
        icon = eotimeseriesviewer.icon()
        action = QAction(icon, TITLE, iface)
        action.triggered.connect(self.run)
        self.mToolbarActions.append(action)

        for action in self.mToolbarActions:
            iface.addToolBarIcon(action)
            iface.addPluginToRasterMenu(TITLE, action)

    def initProcessing(self):
        """
        dummy
        """
        from eotimeseriesviewer import registerProcessingProvider
        registerProcessingProvider()
        pass

    def initialDependencyCheck(self):
        """
        Runs a check for availability of package dependencies and give an readible error message
        :return:
        """

        missing = []
        from eotimeseriesviewer import DEPENDENCIES, messageLog
        for package in DEPENDENCIES:
            try:
                __import__(package)

            except Exception as ex:
                missing.append(package)
        if len(missing) > 0:

            n = len(missing)

            longText = ['Unable to import the following package(s):', '<b>{}</b>'.format(', '.join(missing)),
                        '<p>Please run your local package manager(s) with root rights to install them.', 'This Python:',
                        'Executable: {}'.format(sys.executable), 'ENVIRON:']
            # longText.append('More information is available under:')
            # longText.append('<a href="http://enmap-box.readthedocs.io/en/latest/Installation.html">http://enmap-box.readthedocs.io/en/latest/Installation.html</a> </p>')

            for k in sorted(os.environ.keys()):
                longText.append('\t{} ={}'.format(k, os.environ[k]))

            longText = '<br/>\n'.join(longText)
            messageLog(longText)
            raise Exception(longText)

    def run(self):
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        eotsv = EOTimeSeriesViewer.instance()
        if isinstance(eotsv, EOTimeSeriesViewer):
            eotsv.ui.show()
        else:
            self.mEOTSV = EOTimeSeriesViewer()
            self.mEOTSV.ui.sigAboutToBeClosed.connect(self.onUiClosed)

            from eotimeseriesviewer.settings.settings import EOTSVSettingsManager
            settings = EOTSVSettingsManager.settings()
            if settings.restoreProjectSettings:
                self.mEOTSV.reloadProject()

            self.mEOTSV.show()

    def onUiClosed(self):
        self.mEOTSV = None
        from eotimeseriesviewer.main import EOTimeSeriesViewer
        EOTimeSeriesViewer._instance = None

    def unload(self):

        if isinstance(self.iface, QgisInterface):
            try:
                from eotimeseriesviewer.main import EOTimeSeriesViewer
                eotsv = EOTimeSeriesViewer.instance()
                if isinstance(eotsv, EOTimeSeriesViewer):
                    eotsv.close()
                    QApplication.processEvents()

                for action in self.mToolbarActions:
                    self.iface.removeToolBarIcon(action)
            except Exception as ex:
                print(f'Failed to unload EOTimeSeriesViewer:\n{ex}')

        from eotimeseriesviewer import unloadAll
        unloadAll()

    @staticmethod
    def tr(message):
        return QCoreApplication.translate('EOTimeSeriesViewerPlugin', message)
