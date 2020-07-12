# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/qgsfunctions.py
    qgsfunctions to be used in QgsExpressions to access SpectralLibrary data
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
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
import pickle

from qgis.core import *

from .core import FIELD_VALUES, decodeProfileValueDict

QGS_FUNCTION_GROUP = "Spectral Libraries"

@qgsfunction(0, QGS_FUNCTION_GROUP)
def spectralValues(values, feature, parent):
    """
    Returns the spectral values dictionary
    :param values:
    :param feature:
    :param parent:
    :return: dict
    """
    if isinstance(feature, QgsFeature):
        i = feature.fieldNameIndex(FIELD_VALUES)
        if i >= 0:
            values = decodeProfileValueDict(feature.attribute(i))
            return values
    return None


def registerQgsExpressionFunctions():
    """
    Registers functions to support SpectraLibrary handling with QgsExpressions
    """
    #QgsExpression.registerFunction(plotStyleSymbolFillColor)
    #QgsExpression.registerFunction(plotStyleSymbol)
    #QgsExpression.registerFunction(plotStyleSymbolSize)
    QgsExpression.registerFunction(spectralValues)
