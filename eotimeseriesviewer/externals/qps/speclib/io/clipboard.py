# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/clipboard.py

    Input/Output of SpectralLibrary data via the system clipboard
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

import typing
from ..core import *
from PyQt5.QtWidgets import QProgressDialog
import locale

class ClipboardIO(AbstractSpectralLibraryIO):
    """
    Reads and write SpectralLibrary from/to system clipboard.
    """
    FORMATS = [MIMEDATA_SPECLIB, MIMEDATA_XQT_WINDOWS_CSV]

    class WritingModes(object):

        ALL = 'ALL'
        ATTRIBUTES = 'ATTRIBUTES'
        VALUES = 'VALUES'

        def modes(self):
            return [a for a in dir(self) if not callable(getattr(self, a)) and not a.startswith("__")]

    @classmethod
    def canRead(cls, path=None) -> bool:
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        if isinstance(mimeData, QMimeData):
            for format in mimeData.formats():
                if format in ClipboardIO.FORMATS:
                    return True
        return False

    @classmethod
    def readFrom(cls, path=None,
                 progressDialog:typing.Union[QProgressDialog, ProgressHandler]=None) -> SpectralLibrary:

        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        if not isinstance(mimeData, QMimeData):
            return None

        if MIMEDATA_SPECLIB in mimeData.formats():
            b = mimeData.data(MIMEDATA_SPECLIB)
            speclib = pickle.loads(b)
            assert isinstance(speclib, SpectralLibrary)
            return speclib

        return None

    @classmethod
    def write(cls, speclib,
              path=None,
              mode=None,
              sep=None,
              newline=None,
              progressDialog:typing.Union[QProgressDialog, ProgressHandler]=None):

        if mode is None:
            mode = ClipboardIO.WritingModes.ALL
        assert isinstance(speclib, SpectralLibrary)

        mimeData = QMimeData()


        if not isinstance(sep, str):
            sep = '\t'

        if not isinstance(newline, str):
            newline = '\r\n'


        csvlines = []
        fields = speclib.fields()

        attributeIndices = [i for i, name in zip(fields.allAttributesList(), fields.names())]

        skipGeometry = mode == ClipboardIO.WritingModes.VALUES
        skipAttributes = mode == ClipboardIO.WritingModes.VALUES
        skipValues = mode == ClipboardIO.WritingModes.ATTRIBUTES

        for p in speclib.profiles():
            assert isinstance(p, SpectralProfile)
            line = []

            if not skipGeometry:
                x = ''
                y = ''
                if p.hasGeometry():
                    g = p.geometry().constGet()
                    if isinstance(g, QgsPoint):
                        x, y = g.x(), g.y()
                    else:
                        x = g.asWkt()

                line.extend([x, y])

            if not skipAttributes:
                line.extend([p.attributes()[i] for i in attributeIndices])

            if not skipValues:
                yValues = p.yValues()
                if isinstance(yValues, list):
                    line.extend(yValues)

            formatedLine = []
            excluded = [QVariant(), None]
            for value in line:
                if value in excluded:
                    formatedLine.append('')
                else:
                    if type(value) in [float, int]:
                        value = locale.str(value)
                    formatedLine.append(value)
            csvlines.append(sep.join(formatedLine))
        text = newline.join(csvlines)

        ba = QByteArray()
        ba.append(text)

        mimeData.setText(text)
        mimeData.setData(MIMEDATA_XQT_WINDOWS_CSV, ba)
        mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(speclib))
        QApplication.clipboard().setMimeData(mimeData)

        return []