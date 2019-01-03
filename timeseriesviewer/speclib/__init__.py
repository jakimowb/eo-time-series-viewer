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
import sys
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import QSettings


from . import speclibresources
speclibresources.qInitResources()
print('DEGUB: init resources')
if not 'speclibresources' in list(sys.modules.keys()):
    sys.modules['speclibresources'] = speclibresources

from timeseriesviewer.plotstyling import PlotStyleEditorWidgetFactory, registerPlotStyleEditorWidget
#register Editor widgets, if not done before
reg = QgsGui.editorWidgetRegistry()
if len(reg.factories()) == 0:
    reg.initEditors()


def speclibSettings()->QSettings:
    """
    Returns SPECLIB relevant QSettings
    :return: QSettings
    """
    import timeseriesviewer.settings
    return timeseriesviewer.settings.settings()



registerPlotStyleEditorWidget()

from .spectrallibraries import registerSpectralProfileEditorWidget
registerSpectralProfileEditorWidget()

from .qgsfunctions import registerQgsExpressionFunctions
registerQgsExpressionFunctions()

try:
    from .envi import EnviSpectralLibraryIO
except:
    pass



