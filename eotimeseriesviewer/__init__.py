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
import inspect
import os
import pathlib

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtGui import QIcon

__version__ = '2.0'  # sub-subversion number is added automatically

LICENSE = 'GNU GPL-3'
TITLE = 'EO Time Series Viewer'
LOG_MESSAGE_TAG = TITLE
DESCRIPTION = 'Visualization of multi-sensor Earth observation time series data.'
HOMEPAGE = 'https://eo-time-series-viewer.readthedocs.io'
DOCUMENTATION = 'http://eo-time-series-viewer.readthedocs.io/en/latest/'
REPOSITORY = 'https://github.com/jakimowb/eo-time-series-viewer'
AUTHOR = 'Benjamin Jakimow'
MAIL = 'benjamin.jakimow@geo.hu-berlin.de'
ISSUE_TRACKER = 'https://github.com/jakimowb/eo-time-series-viewer/issues'
CREATE_ISSUE = 'https://github.com/jakimowb/eo-time-series-viewer/issues/new'
DEPENDENCIES = ['numpy', 'osgeo.gdal']
URL_TESTDATA = r''

DEBUG: bool = str(os.environ.get('DEBUG', '1')).lower() in ['true', '1', 'yes']

DIR = pathlib.Path(__file__).parent
DIR_REPO = DIR.parent
DIR_UI = DIR / 'ui'
DIR_DOCS = DIR_REPO / 'doc'
DIR_EXAMPLES = DIR_REPO / 'example'
PATH_EXAMPLE_TIMESERIES = DIR_EXAMPLES / 'ExampleTimeSeries.csv'
PATH_LICENSE = DIR_REPO / 'LICENSE.md'
PATH_CHANGELOG = DIR_REPO / 'CHANGELOG.md'
PATH_CONTRIBUTORS = DIR_REPO / 'CONTRIBUTORS.md'
PATH_ABOUT = DIR_REPO / 'ABOUT.md'

DIR_QGIS_RESOURCES = DIR_REPO / 'qgisresources'
URL_QGIS_RESOURCES = r'https://box.hu-berlin.de/f/6949ab1099044018a5e4/?dl=1'


def debugLog(msg: str = '', skip_prefix: bool = False):
    """
    """
    if str(os.environ.get('DEBUG')).lower() in ['true', '1', 'yes']:
        if skip_prefix:
            prefix = ''
        else:
            curFrame = inspect.currentframe()
            outerFrames = inspect.getouterframes(curFrame)
            FOI = outerFrames[1]
            stack = inspect.stack()
            if "self" in stack[1][0].f_locals.keys():
                stack_class = stack[1][0].f_locals["self"].__class__.__name__
            elif '__file__' in stack[1][0].f_locals.keys():
                stack_class = stack[1][0].f_locals['__file__']
            else:
                stack_class = ''
            stack_method = stack[1][0].f_code.co_name
            prefix = f'{stack_class}.{FOI.function}: {os.path.basename(FOI.filename)}:{FOI.lineno}:'

        msg = f'DEBUG::{prefix}{msg}'
        QgsApplication.messageLog().logMessage(msg, tag=LOG_MESSAGE_TAG, level=Qgis.Info)


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
    from eotimeseriesviewer.qgispluginsupport.qps.resources import initQtResources
    initQtResources(pathlib.Path(__file__).parent)


def initAll():
    """
    Calls all required init routines
    :return:
    """
    # resources first, as we need the icon resource paths!
    initResources()
    from eotimeseriesviewer.qgispluginsupport.qps import initAll as initAllQps
    initAllQps()

    from .labeling import registerLabelShortcutEditorWidget
    registerLabelShortcutEditorWidget()

    from eotimeseriesviewer.timeseries import registerDataProvider
    registerDataProvider()
    registerProcessingProvider()
    registerOptionsWidgetFactory()


def registerProcessingProvider():
    from eotimeseriesviewer.processingalgorithms import EOTSVProcessingProvider
    EOTSVProcessingProvider.registerProvider()


def unregisterProcessingProvider():
    from eotimeseriesviewer.processingalgorithms import EOTSVProcessingProvider
    EOTSVProcessingProvider.unregisterProvider()


def registerOptionsWidgetFactory():
    from eotimeseriesviewer.settings.widget import EOTSVSettingsWidgetFactory
    from qgis.utils import iface
    iface.registerOptionsWidgetFactory(EOTSVSettingsWidgetFactory.instance())


def unregisterOptionsWidgetFactory():
    from eotimeseriesviewer.settings.widget import EOTSVSettingsWidgetFactory
    from qgis.utils import iface
    iface.unregisterOptionsWidgetFactory(EOTSVSettingsWidgetFactory.instance())


def unloadAll():
    from eotimeseriesviewer.qgispluginsupport.qps import unregisterEditorWidgets, unregisterExpressionFunctions, \
        unregisterMapLayerConfigWidgetFactories
    unregisterEditorWidgets()
    unregisterExpressionFunctions()
    unregisterMapLayerConfigWidgetFactories()
    unregisterProcessingProvider()
    unregisterOptionsWidgetFactory()


def icon() -> QIcon:
    """
    Returns the EO Time Series Viewer icon
    :return: QIcon
    """
    path = os.path.join(os.path.dirname(__file__), 'icon.png')
    return QIcon(path)
