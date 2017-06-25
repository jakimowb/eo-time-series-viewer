
VERSION = '0.2'
DESCRIPTION = 'This software visualizes remote sensing time series data'
WEBSITE = 'https://bitbucket.org/jakimowb/hub-timeseriesviewer/wiki/Home'
REPOSITORY = 'https://bitbucket.org/jakimowb/hub-timeseriesviewer.git'


import os, sys, fnmatch, site
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

print('BASE INIT SITE-packages')
site.addsitedir(DIR_SITE_PACKAGES)

QGIS_TSV_BRIDGE = None

OPENGL_AVAILABLE = False

try:
    import OpenGL
    OPENGL_AVAILABLE = True
except:
    pass

def icon():
    return QIcon(':/timeseriesviewer/icons/icon.png')



def file_search(rootdir, wildcard, recursive=False, ignoreCase=False):
    assert rootdir is not None
    if not os.path.isdir(rootdir):
        six.print_("Path is not a directory:{}".format(rootdir), file=sys.stderr)

    results = []

    for root, dirs, files in os.walk(rootdir):
        for file in files:
            if (ignoreCase and fnmatch.fnmatch(file.lower(), wildcard.lower())) \
                    or fnmatch.fnmatch(file, wildcard):
                results.append(os.path.join(root, file))
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