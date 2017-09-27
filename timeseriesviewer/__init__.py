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
VERSION = '0.3'
LICENSE = 'GNU GPL-3'
TITLE = 'HUB TimeSeriesViewer'
DESCRIPTION = 'A QGIS Plugin to visualize multi-sensor remote-sensing time-series data.'
WEBSITE = 'bitbucket.org/jakimowb/hub-timeseriesviewer'
REPOSITORY = 'bitbucket.org/jakimowb/hub-timeseriesviewer'
ABOUT = """
The HUB TimeSeriesViewer is developed at Humboldt-Universität zu Berlin. Born in the SenseCarbon project, it was funded by the German Aerospace Centre (DLR) and granted by the Federal Ministry of Education and Research (BMBF, grant no. 50EE1254). Since 2017 it is developed under contract by the German Research Centre for Geosciences (GFZ) as part of the EnMAP Core Science Team activities (www.enmap.org), funded by DLR and granted by the Federal Ministry of Economic Affairs and Energy (BMWi, grant no. 50EE1529).
"""

import os, sys, fnmatch, site, re
import six, logging
from qgis.core import *
from qgis.gui import *

logger = logging.getLogger(__name__)

from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QIcon



DEBUG = True

#initiate loggers for all pyfiles
import pkgutil
DIR = os.path.dirname(__file__)
names = []
for m, name, ispkg in pkgutil.walk_packages(path=__file__, prefix='timeseriesviewer.'):
    if name not in names:
        names.append(name)

for name in names:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    fh = logging.StreamHandler()
    fh_formatter = logging.Formatter('%(levelname)s %(lineno)d:%(filename)s%(module)s %(funcName)s \n\t%(message)s')
    fh.setFormatter(fh_formatter)
    fh.addFilter(logging.Filter(name))
    logger.addHandler(fh)


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
DEBUG = True

SETTINGS = QSettings(QSettings.UserScope, 'HU Geomatics', 'TimeSeriesViewer')


#print('BASE INIT SITE-packages')
site.addsitedir(DIR_SITE_PACKAGES)

OPENGL_AVAILABLE = False

try:
    import OpenGL
    OPENGL_AVAILABLE = True
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


    return QIcon(os.path.join(os.path.dirname(__file__), *['ui','icons','icon.png']))



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