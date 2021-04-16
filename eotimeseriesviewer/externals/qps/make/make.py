# -*- coding: utf-8 -*-

"""
***************************************************************************
    make.py
    ---------------------
    Date                 : 2019-01-17
    Copyright            : (C) 2017 by Benjamin Jakimow
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
from osgeo import gdal, ogr, osr
import warnings

from .. import resources
def compileResourceFiles(*args, **kwds):
    warnings.warn('Use qps.resources.compileResourceFiles() instead', DeprecationWarning, stacklevel=2)
    return resources.compileResourceFiles(*args, **kwds)

def compileResourceFile(*args, **kwds):
    warnings.warn('Use qps.resources.compileResourceFile() instead', DeprecationWarning, stacklevel=2)
    return resources.compileResourceFile(*args, **kwds)

