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
import os
import pathlib
from qgis.core import QgsApplication, Qgis
from qgis.PyQt.QtGui import QIcon

__version__ = '1.17'  # sub-subversion number is added automatically
LICENSE = 'GNU GPL-3'
TITLE = 'EO Time Series Viewer'
LOG_MESSAGE_TAG = TITLE
DESCRIPTION = 'Visualization of multi-sensor Earth observation time series data.'
HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
DOCUMENTATION = 'http://eo-time-series-viewer.readthedocs.io/en/latest/'
REPOSITORY = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
AUTHOR = 'Benjamin Jakimow'
MAIL = 'benjamin.jakimow@geo.hu-berlin.de'
HOMEPAGE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer'
ISSUE_TRACKER = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues'
CREATE_ISSUE = 'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/new'
DEPENDENCIES = ['numpy', 'osgeo.gdal']
URL_TESTDATA = r''

DEBUG: bool = bool(os.environ.get('EOTSV_DEBUG', False))

DIR = pathlib.Path(__file__).parent
DIR_REPO = DIR.parent
DIR_UI = DIR / 'ui'
DIR_DOCS = DIR_REPO / 'doc'
DIR_EXAMPLES = DIR_REPO / 'example'
PATH_EXAMPLE_TIMESERIES = DIR_EXAMPLES / 'ExampleTimeSeries.csv'
PATH_LICENSE = DIR_REPO / 'LICENSE.html'
PATH_CHANGELOG = DIR_REPO / 'CHANGELOG'
PATH_ABOUT = DIR_REPO / 'ABOUT.html'
DIR_QGIS_RESOURCES = DIR_REPO / 'qgisresources'
URL_QGIS_RESOURCES = r'https://bitbucket.org/jakimowb/qgispluginsupport/downloads/qgisresources.zip'


def debugLog(msg: str):
    if DEBUG:
        print('DEBUG:' + msg, flush=True)


# import QPS modules
# skip imports when on RTD, as we can not install the full QGIS environment as required
# https://docs.readthedocs.io/en/stable/builds.html

if True and not os.environ.get('READTHEDOCS') in ['True', 'TRUE', True]:
    debugLog('load crosshair')
    from .externals.qps.crosshair.crosshair import CrosshairStyle, CrosshairWidget, CrosshairMapCanvasItem, \
        CrosshairDialog, getCrosshairStyle

    debugLog('load plotstyling')
    from .externals.qps.plotstyling.plotstyling import PlotStyle, PlotStyleDialog, PlotStyleButton, PlotStyleWidget

    debugLog('load classification')
    from .externals.qps.classification.classificationscheme import ClassificationScheme, ClassInfo, \
        ClassificationSchemeComboBox, ClassificationSchemeWidget, ClassificationSchemeDialog, hasClassification

    debugLog('load models')
    from .externals.qps.models import Option, OptionListModel, TreeNode, TreeModel, TreeView

    debugLog('load speclib')
    from .externals.qps.speclib.core import SpectralLibrary, SpectralProfile
    from .externals.qps.speclib.gui import SpectralLibraryPanel, SpectralLibraryWidget

    debugLog('load layer config')
    from .externals.qps.layerconfigwidgets.vectorlayerfields import LayerFieldsConfigWidget

    debugLog('load maptools')
    from .externals.qps.maptools import *

    debugLog('load utils')
    from .externals.qps.utils import *


def messageLog(msg, level=Qgis.Info):
    """
    Writes a log message to the QGIS EO TimeSeriesViewer log
    :param msg: log message string
    :param level: QgsMessageLog::MessageLevel with MessageLevel =[INFO |  ALL | WARNING | CRITICAL | NONE]
    """
    QgsApplication.instance().messageLog().logMessage(msg, LOG_MESSAGE_TAG, level)

def initResources():
    """
    Loads (or reloads) required Qt resources
    :return:
    """
    debugLog('initResources')
    from eotimeseriesviewer.externals.qps.resources import initQtResources
    initQtResources(pathlib.Path(__file__).parent)


def initAll():
    """
    Calls all required init routines
    :return:
    """
    # resources first, as we need the icon resource paths!
    initResources()

    from .externals.qps import registerEditorWidgets, registerMapLayerConfigWidgetFactories
    registerEditorWidgets()
    registerMapLayerConfigWidgetFactories()

    from .labeling import registerLabelShortcutEditorWidget
    registerLabelShortcutEditorWidget()


def icon() -> QIcon:
    """
    Returns the EO Time Series Viewer icon
    :return: QIcon
    """
    path = os.path.join(os.path.dirname(__file__), 'icon.png')
    return QIcon(path)
