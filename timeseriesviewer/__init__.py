import os, sys, fnmatch
import six
from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QIcon
jp = os.path.join
dn = os.path.dirname
mkdir = lambda p: os.makedirs(p, exist_ok=True)
VERSION = '0.2'
DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_SITE_PACKAGES = jp(DIR_REPO, 'site-packages')
DIR_UI = jp(DIR,*['ui'])
DIR_DOCS = jp(DIR,'docs')
DIR_EXAMPLES = jp(DIR_REPO, 'example')
PATH_EXAMPLE_TIMESERIES = jp(DIR_EXAMPLES,'ExampleTimeSeries.csv')
PATH_LICENSE = jp(DIR_REPO, 'GPL-3.0.txt')
DEBUG = True

SETTINGS = QSettings(QSettings.UserScope, 'HU Geomatics', 'TimeSeriesViewer')

QGIS_TSV_BRIDGE = None

OPENGL_AVAILABLE = False
try:
    import OpenGL
    OPENGL_AVAILABLE = True
except:
    pass

def icon():
    return QIcon(':/timeseriesviewer/icons/icon.png')


def dprint(text, file=None):
    if DEBUG:
        six._print('DEBUG::{}'.format(text), file=file)


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


def findAbsolutePath(file):
    if os.path.exists(file): return file
    possibleRoots = [DIR_EXAMPLES, DIR_REPO, os.getcwd()]
    for root in possibleRoots:
        tmp = jp(root, file)
        if os.path.exists(tmp):
            return tmp
    return None