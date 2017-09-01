# -*- coding: utf-8 -*-

"""
***************************************************************************
    __main__
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from __future__ import absolute_import
import sys, os, site


def run():
    from timeseriesviewer.main import TimeSeriesViewer
    from timeseriesviewer.utils import initQgisApplication
    from qgis.utils import iface
    qgisApp = initQgisApplication()
    tsv = TimeSeriesViewer(iface)
    tsv.run()
    qgisApp.exec_()


if __name__ == '__main__':
    thisDir = os.path.dirname(__file__)
    if thisDir in sys.path:
        sys.path.remove(thisDir)

    args = sys.argv[1:]

    run()