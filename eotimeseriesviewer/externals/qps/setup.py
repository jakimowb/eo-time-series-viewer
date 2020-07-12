# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/setup.py

    Setup of QPS repository
    ---------------------
    Beginning            : 2019-09-19
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import os, sys, pathlib

def compileQPSResources():
    pathQPSDir = os.path.dirname(__file__)
    pathQPSRoot = os.path.dirname(pathQPSDir)

    addSysPath = pathQPSRoot not in sys.path
    if addSysPath:
        sys.path.append(pathQPSRoot)

    from .resources import compileResourceFiles
    compileResourceFiles(pathQPSDir)

    if addSysPath:
        sys.path.remove(pathQPSRoot)

if __name__ == "__main__":
    compileQPSResources()


