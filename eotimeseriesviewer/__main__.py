# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 10.08.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import pathlib
import sys
from qgis.gui import QgisInterface


def run():
    # add site-packages to sys.path
    pluginDir = pathlib.Path(__file__).parents[1]
    sys.path.append(pluginDir.as_posix())
    print(pluginDir)
    from eotimeseriesviewer.tests import start_app
    import qgis.utils

    qgisIface = isinstance(qgis.utils.iface, QgisInterface)

    if not qgisIface:
        qgsApp = start_app()

    from eotimeseriesviewer import initAll
    initAll()

    from eotimeseriesviewer.main import EOTimeSeriesViewer

    ts = EOTimeSeriesViewer()
    ts.show()

    if not qgisIface:
        qgsApp.exec_()
        qgsApp.exitQgis()


if __name__ == '__main__':

    run()
