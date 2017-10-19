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
from __future__ import absolute_import
import sys

class run():

    # add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer.sandbox import initQgisApplication
    qgsApp = initQgisApplication()
    from timeseriesviewer.main import TimeSeriesViewer
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    from timeseriesviewer.main import main
    main()
