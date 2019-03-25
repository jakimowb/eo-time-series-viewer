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


__version__ = '0.8'  # sub-subversion number is added automatically
LICENSE = 'GNU GPL-3'
TITLE = 'EO Time Series Viewer'
DESCRIPTION = 'Visualization of multi-sensor Earth observation time series data.'
HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
DOCUMENTATION = 'http://eo-time-series-viewer.readthedocs.io/en/latest/'
REPOSITORY = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'

HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
ISSUE_TRACKER = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues'
CREATE_ISSUE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/new'
DEPENDENCIES = ['numpy', 'pyqtgraph', 'gdal']
URL_TESTDATA = r''


import os, sys, fnmatch, site, re, site
jp = os.path.join
dn = os.path.dirname
from qgis.core import QgsApplication, Qgis
from qgis.PyQt.QtGui import QIcon

mkdir = lambda p: os.makedirs(p, exist_ok=True)



DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_UI = jp(DIR, *['ui'])
DIR_DOCS = jp(DIR, 'docs')
DIR_EXAMPLES = jp(DIR_REPO, 'example')
PATH_EXAMPLE_TIMESERIES = jp(DIR_EXAMPLES,'ExampleTimeSeries.csv')
PATH_LICENSE = jp(DIR_REPO, 'LICENSE.txt')
PATH_CHANGELOG = jp(DIR_REPO, 'CHANGES.txt')
PATH_ABOUT = jp(DIR_REPO, 'ABOUT.html')
DIR_QGIS_RESOURCES = jp(DIR_REPO, 'qgisresources')

DIR_SITE_PACKAGES = jp(DIR_REPO, 'site-packages')

OPENGL_AVAILABLE = False

try:
    import OpenGL

    OPENGL_AVAILABLE = True
except:
    pass


try:
    import qps
except Exception as ex:
    sys.path.append(DIR_SITE_PACKAGES)
    import qps



import qps.utils
qps.utils.UI_DIRECTORIES.append(DIR_UI)

# import QPS modules

from qps.crosshair.crosshair import CrosshairStyle, CrosshairWidget, CrosshairMapCanvasItem, CrosshairDialog, getCrosshairStyle
from qps.plotstyling.plotstyling import PlotStyle, PlotStyleDialog, PlotStyleButton, PlotStyleWidget
from qps.classification.classificationscheme import ClassificationScheme, ClassInfo, ClassificationSchemeComboBox, ClassificationSchemeWidget, ClassificationSchemeDialog, hasClassification
from qps.models import Option, OptionListModel, TreeNode, TreeModel, TreeView
from qps.speclib.spectrallibraries import SpectralLibrary, SpectralProfile
from qps.maptools import *


def messageLog(msg, level=None):
    """
    Writes a log message to the QGIS EO TimeSeriesViewer log
    :param msg: log message string
    :param level: QgsMessageLog::MessageLevel with MessageLevel =[INFO |  ALL | WARNING | CRITICAL | NONE]
    """

    if level is None:
        level = Qgis.Warning

        QgsApplication.instance().messageLog().logMessage(msg, 'EO TSV', level)

def initResources():
    """
    Loads (or reloads) required Qt resources
    :return:
    """
    try:
        import timeseriesviewer.ui.resources
        timeseriesviewer.ui.resources.qInitResources()
    except:
        print('Unable to initialize EO Time Series Viewer ressources', file=sys.stderr)

    try:
        import qps.qpsresources
        qps.qpsresources.qInitResources()
    except Exception as ex:
        print('Unable to import qps.resources', file=sys.stderr)

def initEditorWidgets():
    """
    Initialises QgsEditorWidgets
    """
    import qps
    qps.registerEditorWidgets()

def initAll():
    """
    Calls all required init routines
    :return:
    """
    initResources()
    initEditorWidgets()

def icon()->QIcon:
    """
    Returns the EO Time Series Viewer icon
    :return: QIcon
    """
    path = os.path.join(os.path.dirname(__file__), 'icon.png')
    return QIcon(path)
