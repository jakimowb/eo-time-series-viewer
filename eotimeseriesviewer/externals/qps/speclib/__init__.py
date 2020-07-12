# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/__init__.py

    A python module to handle and visualize SpectralLibraries in QGIS
    ---------------------
    Beginning            : 2018-12-17
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

import enum
from qgis.core import *

from qgis.PyQt.QtCore import QSettings


EDITOR_WIDGET_REGISTRY_KEY = 'Spectral Profile'

class SpectralLibrarySettingsKey(enum.Enum):
    CURRENT_PROFILE_STYLE = 1
    DEFAULT_PROFILE_STYLE = 2
    BACKGROUND_COLOR = 3
    FOREGROUND_COLOR = 4
    INFO_COLOR = 5
    USE_VECTOR_RENDER_COLORS = 6
    SELECTION_COLOR = 7




def speclibSettings() -> QSettings:
    """
    Returns SpectralLibrary relevant QSettings
    :return: QSettings
    """
    return QgsSettings('HUB', 'speclib')

try:
    from ..speclib.io.envi import EnviSpectralLibraryIO
except:
    pass



