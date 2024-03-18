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

from eotimeseriesviewer.tests import start_app
from qgis.core import QgsApplication

start_app()

s = ""


def run():
    from eotimeseriesviewer import initAll
    initAll()

    from eotimeseriesviewer.main import EOTimeSeriesViewer

    ts = EOTimeSeriesViewer()
    ts.show()


if __name__ == '__main__':
    run()
    QgsApplication.instance().exec_()
