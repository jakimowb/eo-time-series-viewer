# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    __init__.py
    speclib module definition
    -------------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This file is part of the EnMAP-Box.                                   *
*                                                                         *
*   The EnMAP-Box is free software; you can redistribute it and/or modify *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
*   The EnMAP-Box is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          *
*   GNU General Public License for more details.                          *
*                                                                         *
*   You should have received a copy of the GNU General Public License     *
*   along with the EnMAP-Box. If not, see <http://www.gnu.org/licenses/>. *
*                                                                         *
***************************************************************************
"""
import sys, enum
from qgis.core import *
from qgis.gui import *

from qgis.PyQt.QtCore import QSettings

class SpectralLibrarySettingsKey(enum.Enum):
    CURRENT_PROFILE_STYLE = 1
    DEFAULT_PROFILE_STYLE = 2
    BACKGROUND_COLOR = 3
    FOREGROUND_COLOR = 4
    INFO_COLOR = 5
    USE_VECTOR_RENDER_COLORS = 6




def speclibSettings()->QSettings:
    """
    Returns SpectralLibrary relevant QSettings
    :return: QSettings
    """
    return QgsSettings('HUB', 'speclib')

try:
    from .envi import EnviSpectralLibraryIO
except:
    pass



