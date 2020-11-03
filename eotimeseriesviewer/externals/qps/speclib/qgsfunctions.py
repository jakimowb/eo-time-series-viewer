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
import typing
import string
import pathlib
import json
import sys
import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsExpression, QgsFeature, qgsfunction, QgsFeatureRequest, QgsExpressionFunction, \
    QgsMessageLog, Qgis, QgsExpressionContext
from qgis.PyQt.QtCore import QByteArray, QVariant, NULL
from .core import FIELD_VALUES, decodeProfileValueDict, SpectralProfile, encodeProfileValueDict

QGS_FUNCTION_GROUP = "Spectral Libraries"

QGIS_FUNCTION_INSTANCES = dict()


class HelpStringMaker(object):

    def __init__(self):

        helpDir = pathlib.Path(__file__).parent / 'function_help'
        self.mHELP = dict()

        assert helpDir.is_dir()

        for e in os.scandir(helpDir):
            if e.is_file() and e.name.endswith('.json'):
                with open(e.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'name' in data.keys():
                        self.mHELP[data['name']] = data

    def helpText(self, name: str,
                 parameters: typing.List[QgsExpressionFunction.Parameter] = []) -> str:
        """
        re-implementation of QString QgsExpression::helpText( QString name )
        to generate similar help strings
        :param name:
        :param args:
        :return:
        """
        html = [f'<h3>{name}</h3>']
        LUT_PARAMETERS = dict()
        for p in parameters:
            LUT_PARAMETERS[p.name()] = p

        JSON = self.mHELP.get(name, None)
        ARGUMENT_DESCRIPTIONS = {}
        ARGUMENT_NAMES = []
        if isinstance(JSON, dict):
            for D in JSON.get('arguments', []):
                if isinstance(D, dict) and 'arg' in D:
                    ARGUMENT_NAMES.append(D['arg'])
                    ARGUMENT_DESCRIPTIONS[D['arg']] = D.get('description', '')

        if not isinstance(JSON, dict):
            print(f'No help found for {name}', file=sys.stderr)
            return '\n'.join(html)

        description = JSON.get('description', None)
        if description:
            html.append(f'<div class="description"><p>{description}</p></div>')

        arguments = JSON.get('arguments', None)
        if arguments:
            hasOptionalArgs: bool = False
            html.append(f'<h4>Syntax</h4>')
            syntax = f'<div class="syntax">\n<code>{name}('

            if len(parameters) > 0:
                delim = ''
                syntaxParameters = set()
                for P in parameters:
                    assert isinstance(P, QgsExpressionFunction.Parameter)
                    syntaxParameters.add(P.name())
                    optional: bool = P.optional()
                    if optional:
                        hasOptionalArgs = True
                        syntax += '['
                    syntax += delim
                    syntax += f'<span class="argument">{P.name()}'
                    defaultValue = P.defaultValue()
                    if isinstance(defaultValue, str):
                        defaultValue = f"'{defaultValue}'"
                    if defaultValue not in [None, QVariant()]:
                        syntax += f'={defaultValue}'

                    syntax += '</span>'
                    if optional:
                        syntax += ']'
                    delim = ','
                # add other optional arguments from help file
                for a in ARGUMENT_NAMES:
                    if a not in syntaxParameters:
                        pass

            syntax += ')</code>'

            if hasOptionalArgs:
                syntax += '<br/><br/>[ ] marks optional components'
            syntax += '</div>'
            html.append(syntax)

            if len(parameters) > 0:
                html.append(f'<h4>Arguments</h4>')
                html.append(f'<div class="arguments"><table>')

                for P in parameters:
                    assert isinstance(P, QgsExpressionFunction.Parameter)

                    description = ARGUMENT_DESCRIPTIONS.get(P.name(), '')
                    html.append(f'<tr><td class="argument">{P.name()}</td><td>{description}</td></tr>')

            html.append(f'</table></div>')

        return '\n'.join(html)


HM = HelpStringMaker()

"""
@qgsfunction(args='auto', group='String')
def format_py(fmt: str, *args):
    assert isinstance(fmt, str)
    fmtArgs = args[0:-2]
    feature, parent = args[-2:]

    return fmt.format(*fmtArgs)
"""
class Format_Py(QgsExpressionFunction):

    def __init__(self):
        group = 'String'
        name = 'format_py'

        args = [
            QgsExpressionFunction.Parameter('fmt', optional=False, defaultValue=FIELD_VALUES),
            QgsExpressionFunction.Parameter('arg1', optional=True),
            QgsExpressionFunction.Parameter('arg2', optional=True),
            QgsExpressionFunction.Parameter('argN', optional=True),
        ]
        helptext = HM.helpText(name, args)
        super(Format_Py, self).__init__(name, -1, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):
        if len(values) == 0 or values[0] in (None, NULL):
            return None
        assert isinstance(values[0], str)
        fmt: str = values[0]
        fmtArgs = values[1:]
        try:
            return fmt.format(*fmtArgs)
        except:
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class SpectralData(QgsExpressionFunction):
    def __init__(self):
        group = QGS_FUNCTION_GROUP
        name = 'spectralData'

        args = [
            QgsExpressionFunction.Parameter('field', optional=True, defaultValue=FIELD_VALUES)
        ]

        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):

        value_field = values[0]
        feature = None
        if context:
            feature = context.feature()
        if not isinstance(feature, QgsFeature):
            return None
        try:
            profile = SpectralProfile.fromQgsFeature(feature, value_field=value_field)
            assert isinstance(profile, SpectralProfile)
            return profile.values()
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return False


class SpectralMath(QgsExpressionFunction):

    def __init__(self):
        group = QGS_FUNCTION_GROUP
        name = 'spectralMath'

        args = [
            QgsExpressionFunction.Parameter('expression', optional=False, isSubExpression=True),
            QgsExpressionFunction.Parameter('field', optional=True, defaultValue=FIELD_VALUES)
        ]
        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):

        expression, value_field = values
        feature = None
        if context:
            feature = context.feature()
        if not isinstance(feature, QgsFeature):
            return None
        try:
            profile = SpectralProfile.fromQgsFeature(feature, value_field=value_field)
            assert isinstance(profile, SpectralProfile)
            values = profile.values()
            exec(expression, values)

            newProfile = SpectralProfile(values=values)
            return newProfile.attribute(profile.mValueField)
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


def registerQgsExpressionFunctions():
    """
    Registers functions to support SpectraLibrary handling with QgsExpressions
    """
    global QGIS_FUNCTION_INSTANCES
    for func in [Format_Py(), SpectralMath(), SpectralData()]:
        QGIS_FUNCTION_INSTANCES[func.name()] = func
        if QgsExpression.isFunctionName(func.name()):
            if not QgsExpression.unregisterFunction(func.name()):
                msgtitle = QCoreApplication.translate("UserExpressions", "User expressions")
                msg = QCoreApplication.translate("UserExpressions",
                                                 "The user expression {0} already exists and could not be unregistered.").format(
                    func.name)
                QgsMessageLog.logMessage(msg + "\n", msgtitle, Qgis.Warning)
                return None
        else:
            QgsExpression.registerFunction(func)
