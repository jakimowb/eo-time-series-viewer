# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    clipboard.py
    SpectralLibrary I/O with clipboard data
    ---------------------
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

from .spectrallibraries import *

class ClipboardIO(AbstractSpectralLibraryIO):
    """
    Reads and write SpectralLibrary from/to system clipboard.
    """
    FORMATS = [MIMEDATA_SPECLIB, MIMEDATA_XQT_WINDOWS_CSV, MIMEDATA_TEXT]

    class WritingModes(object):

        ALL = 'ALL'
        ATTRIBUTES = 'ATTRIBUTES'
        VALUES = 'VALUES'

        def modes(self):
            return [a for a in dir(self) if not callable(getattr(self, a)) and not a.startswith("__")]

    @staticmethod
    def canRead(path=None):
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        assert isinstance(mimeData, QMimeData)
        for format in mimeData.formats():
            if format in ClipboardIO.FORMATS:
                return True
        return False

    @staticmethod
    def readFrom(path=None, progressDialog:QProgressDialog=None):
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        assert isinstance(mimeData, QMimeData)

        if MIMEDATA_SPECLIB in mimeData.formats():
            b = mimeData.data(MIMEDATA_SPECLIB)
            speclib = pickle.loads(b)
            assert isinstance(speclib, SpectralLibrary)
            return speclib

        return SpectralLibrary()

    @staticmethod
    def write(speclib, path=None, mode=None, sep=None, newline=None, progressDialog:QProgressDialog):
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

        attributeIndices = [i for i, name in zip(fields.allAttributesList(), fields.names())
                            if not name.startswith(HIDDEN_ATTRIBUTE_PREFIX)]

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