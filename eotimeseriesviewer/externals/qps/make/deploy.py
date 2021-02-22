# -*- coding: utf-8 -*-

"""
***************************************************************************
    deploy.py
    Script to deploy a QGIS Python Plugin
    ---------------------
    Date                 : August 2017
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
# noinspection PyPep8Naming
import re
import typing


class QGISMetadataFileWriter(object):
    """
    A class to store and write the QGIS plugin metadata.txt
    For details see:
    https://docs.qgis.org/3.16/en/docs/pyqgis_developer_cookbook/plugins/plugins.html#plugin-metadata-table
    """

    def __init__(self):
        self.mName = ''
        self.mDescription = ''
        self.mVersion = ''
        self.mQgisMinimumVersion = '3.8'
        self.mQgisMaximumVersion = '3.99'
        self.mAuthor = ''
        self.mAbout = ''
        self.mEmail = ''
        self.mHomepage = ''
        self.mIcon = ''
        self.mTracker = ''
        self.mRepository = ''
        self.mIsExperimental = ''
        self.mHasProcessingProvider: bool = False
        self.mTags: typing.List[str] = []
        self.mCategory: str = ''
        self.mChangelog: str = ''
        self.mPlugin_dependencies: typing.List[str] = []

    def validate(self) -> bool:

        return True

    def metadataString(self) -> str:
        assert self.validate()

        lines = ['[general]']
        lines.append('name={}'.format(self.mName))
        lines.append('author={}'.format(self.mAuthor))
        if self.mEmail:
            lines.append('email={}'.format(self.mEmail))

        lines.append('description={}'.format(self.mDescription))
        lines.append('version={}'.format(self.mVersion))
        lines.append('qgisMinimumVersion={}'.format(self.mQgisMinimumVersion))
        lines.append('qgisMaximumVersion={}'.format(self.mQgisMaximumVersion))
        lines.append('about={}'.format(re.sub('\n', '', self.mAbout)))

        lines.append('icon={}'.format(self.mIcon))

        lines.append('tags={}'.format(', '.join(self.mTags)))
        lines.append('category={}'.format(self.mRepository))
        if self.mHasProcessingProvider:
            lines.append(f'hasProcessingProvider=yes')
        else:
            lines.append(f'hasProcessingProvider=no')
        lines.append('homepage={}'.format(self.mHomepage))
        if self.mTracker:
            lines.append('tracker={}'.format(self.mTracker))
        if self.mRepository:
            lines.append('repository={}'.format(self.mRepository))
        if isinstance(self.mIsExperimental, bool):
            lines.append('experimental={}'.format(self.mIsExperimental))

        if len(self.mPlugin_dependencies) > 0:
            lines.append(f'plugin_dependencies={",".join(self.mPlugin_dependencies)}')
        # lines.append('deprecated={}'.format(self.mIsDeprecated))
        lines.append('')
        lines.append('changelog={}'.format(self.mChangelog))

        return '\n'.join(lines)

    """
    [general]
    name=dummy
    description=dummy
    version=dummy
    qgisMinimumVersion=dummy
    qgisMaximumVersion=dummy
    author=dummy
    about=dummy
    email=dummy
    icon=dummy
    homepage=dummy
    tracker=dummy
    repository=dummy
    experimental=False
    deprecated=False
    tags=remote sensing, raster, time series, data cube, landsat, sentinel
    category=Raster
    """

    def writeMetadataTxt(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.metadataString())
