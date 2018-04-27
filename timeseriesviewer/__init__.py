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

import os, sys, fnmatch, site, re, site


VERSION = '0.5'
LICENSE = 'GNU GPL-3'
TITLE = 'EO Time Series Viewer'
DESCRIPTION = 'A QGIS Plugin to visualize multi-sensor remote-sensing time-series data.'
WEBSITE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
REPOSITORY = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
ABOUT = """
The HUB TimeSeriesViewer is developed at Humboldt-Universität zu Berlin. Born in the SenseCarbon project, it was funded by the German Aerospace Centre (DLR) and granted by the Federal Ministry of Education and Research (BMBF, grant no. 50EE1254). Since 2017 it is developed under contract by the German Research Centre for Geosciences (GFZ) as part of the EnMAP Core Science Team activities (www.enmap.org), funded by DLR and granted by the Federal Ministry of Economic Affairs and Energy (BMWi, grant no. 50EE1529).
"""
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
SETTINGS = QSettings(QSettings.UserScope, 'HU Geomatics', 'TimeSeriesViewer')


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

    pass
initSettings()

def icon():
    return QIcon(':/timeseriesviewer/icons/IconTimeSeries.svg')


def file_search(rootdir, pattern, recursive=False, ignoreCase=False):
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))
    results = []

    for root, dirs, files in os.walk(rootdir):
        for file in files:
            if isinstance(pattern, regType):
                if pattern.search(file):
                    path = os.path.join(root, file)
                    results.append(path)

            elif (ignoreCase and fnmatch.fnmatch(file.lower(), pattern.lower())) \
                    or fnmatch.fnmatch(file, pattern):

                path = os.path.join(root, file)
                results.append(path)
        if not recursive:
            break
            pass

    return results



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


