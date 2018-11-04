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

import os, sys, fnmatch, site, re, site


__version__ = '0.7.<replaced_by_build>'
LICENSE = 'GNU GPL-3'
TITLE = 'EO Time Series Viewer'
DESCRIPTION = 'Visualization of multi-sensor Earth observation time series data.'
HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
DOCUMENTATION = 'http://eo-time-series-viewer.readthedocs.io/en/latest/'
REPOSITORY = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'

HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
ISSUE_TRACKER = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues'
CREATE_ISSUE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/new'
DEPENDENCIES = ['numpy','pyqtgraph','gdal']

URL_TESTDATA = r''



ABOUT = os.path.join(os.path.dirname(__file__), 'ABOUT.txt')
if os.path.isfile(ABOUT):
    f = open(ABOUT, 'r', encoding='utf-8')
    ABOUT = f.read()
    f.close()
    del f
else:
    ABOUT = "The EO Time Series Viewer"


DEBUG = True

DEPENDENCIES = ['pyqtgraph']


from qgis.core import QgsApplication, Qgis
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QIcon

jp = os.path.join
dn = os.path.dirname
mkdir = lambda p: os.makedirs(p, exist_ok=True)

DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_SITE_PACKAGES = jp(DIR_REPO, 'site-packages')
DIR_UI = jp(DIR,*['ui'])
DIR_DOCS = jp(DIR,'docs')
DIR_EXAMPLES = jp(DIR_REPO, 'example')
PATH_EXAMPLE_TIMESERIES = jp(DIR_EXAMPLES,'ExampleTimeSeries.csv')
PATH_LICENSE = jp(DIR_REPO, 'LICENSE.txt')
PATH_CHANGELOG = jp(DIR_REPO, 'CHANGES.txt')
PATH_ABOUT = jp(DIR_REPO, 'ABOUT.html')
SETTINGS = QSettings(QSettings.UserScope, 'HU-Berlin', 'EO Time Series Viewer')


DIR_QGIS_RESOURCES = jp(DIR_REPO, 'qgisresources')

site.addsitedir(DIR_SITE_PACKAGES)
OPENGL_AVAILABLE = False

try:
    import OpenGL
    OPENGL_AVAILABLE = True
except:
    pass

def messageLog(msg, level=None):
    """
    Writes a log message to the QGIS EO TimeSeriesViewer log
    :param msg: log message string
    :param level: QgsMessageLog::MessageLevel with MessageLevel =[INFO |  ALL | WARNING | CRITICAL | NONE]
    """

    if level is None:
        level = Qgis.Warning

        QgsApplication.instance().messageLog().logMessage(msg, 'EO TSV', level)

try:
    import timeseriesviewer.ui.resources
    timeseriesviewer.ui.resources.qInitResources()
except:
    pass

def initSettings():
    def setIfNone(key, value):
        if SETTINGS.value(key) is None:
            SETTINGS.setValue(key, value)

    setIfNone('n_processes', 3)
    setIfNone('n_timer', 500)
    setIfNone('max_temporalprofiles', 64)

    import pathlib

    setIfNone('dir_datasources', str(pathlib.Path.home()))
    setIfNone('file_ts_definition', os.path.join(DIR_EXAMPLES, 'ExampleTimeSeries.csv'))

initSettings()

def icon():
    path = os.path.join(os.path.dirname(__file__), 'icon.png')
    return QIcon(path)

def getFileAndAttributes(file):
    """
    splits a GDAL valid file path into
    :param file:
    :return:
    """
    dn = os.path.dirname(file)
    bn = os.path.basename(file)
    bnSplit = bn.split(':')
    return os.path.join(dn,bnSplit[0]), ':'.join(bnSplit[1:])


