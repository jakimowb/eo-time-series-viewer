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
import sys, os


def run():
    pkg = os.path.dirname(__file__)
    repo = os.path.dirname(pkg)
    if repo not in sys.path:
        if __name__ == '__main__':
            sys.path.append(repo)
    #for p in sorted(sys.path): print(p)
    import timeseriesviewer.main
    timeseriesviewer.main.DEBUG = True
    timeseriesviewer.main.main()

if __name__ == '__main__':
    run()
