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


def run():
    # add site-packages to sys.path
    from timeseriesviewer.tests import initQgisApplication
    qgsApp = initQgisApplication()

    from timeseriesviewer.main import TimeSeriesViewer
    ts = TimeSeriesViewer(None)
    ts.run()
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    run()
