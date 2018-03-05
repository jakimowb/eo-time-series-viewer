# coding=utf-8
"""Common functionality used by regression tests."""

import sys, os
import logging


LOGGER = logging.getLogger('QGIS')
QGIS_APP = None  # Static variable used to hold hand to running QGIS app
CANVAS = None
PARENT = None
IFACE = None


def get_qgis_app():
    """ Start one QGIS application to test against.

    :returns: Handle to QGIS app, canvas, iface and parent. If there are any
        errors the tuple members will be returned as None.
    :rtype: (QgsApplication, CANVAS, IFACE, PARENT)

    If QGIS is already running the handle to that app will be returned.
    """

    try:
        from qgis.core import QgsApplication
        from qgis.gui import QgsMapCanvas
        from qgis_interface import QgisInterface
        from PyQt5 import QtGui, QtCore
        from PyQt5.QtGui import QApplication

    except ImportError:
        return None, None, None, None

    global QGIS_APP  # pylint: disable=W0603

    if QGIS_APP is None:
        if sys.platform == 'darwin':
            PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
            os.environ['GDAL_DATA'] = r'/Library/Frameworks/GDAL.framework/Versions/2.1/Resources/gdal'
            QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
            QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
        else:
            # assume OSGeo4W startup
            PATH_QGS = os.environ['QGIS_PREFIX_PATH']

        gui_flag = True  # All test will run qgis in gui mode
        #noinspection PyPep8Naming
        QGIS_APP = QgsApplication(sys.argv, gui_flag)
        QGIS_APP.setPrefixPath(PATH_QGS, True)
        # Make sure QGIS_PREFIX_PATH is set in your env if needed!
        QGIS_APP.initQgis()
        s = QGIS_APP.showSettings()
        LOGGER.debug(s)

    global PARENT  # pylint: disable=W0603
    if PARENT is None:
        #noinspection PyPep8Naming
        PARENT = QtGui.QWidget()

    global CANVAS  # pylint: disable=W0603
    if CANVAS is None:
        #noinspection PyPep8Naming
        CANVAS = QgsMapCanvas(PARENT)
        CANVAS.resize(QtCore.QSize(400, 400))

    global IFACE  # pylint: disable=W0603
    if IFACE is None:
        # QgisInterface is a stub implementation of the QGIS plugin interface
        #noinspection PyPep8Naming
        IFACE = QgisInterface(CANVAS)

    return QGIS_APP, CANVAS, IFACE, PARENT
