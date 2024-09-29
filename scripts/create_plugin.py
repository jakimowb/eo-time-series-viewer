# -*- coding: utf-8 -*-

"""
***************************************************************************
    create_plugin.py
    Script to build the EO TimeSeriesViewer QGIS Plugin from Repository code
    ---------------------
    Date                 : April 2020
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.
                 *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

import argparse
import os
from pathlib import Path
import re
import shutil
import site
import textwrap
from typing import Iterator, Optional, Union

import git
import markdown

from qgis.core import QgsUserProfile, QgsUserProfileManager
from eotimeseriesviewer.qgispluginsupport.qps.make.deploy import QGISMetadataFileWriter, userProfileManager
from eotimeseriesviewer.qgispluginsupport.qps.utils import zipdir

site.addsitedir(Path(__file__).parents[1].as_posix())
import eotimeseriesviewer
from eotimeseriesviewer import DIR_REPO, PATH_CHANGELOG, PATH_ABOUT

print('DIR_REPO={}'.format(DIR_REPO))
CHECK_COMMITS = False

########## Config Section

MD = QGISMetadataFileWriter()
MD.mName = eotimeseriesviewer.TITLE
MD.mDescription = eotimeseriesviewer.DESCRIPTION
MD.mTags = ['remote sensing', 'raster', 'time series', 'landsat', 'sentinel']
MD.mCategory = 'Analysis'
MD.mAuthor = 'Benjamin Jakimow, Sebastian van der Linden, Patrick Hostert'
MD.mIcon = 'eotimeseriesviewer/icon.png'
MD.mHomepage = eotimeseriesviewer.HOMEPAGE
MD.mAbout = ''
MD.mTracker = eotimeseriesviewer.ISSUE_TRACKER
MD.mRepository = eotimeseriesviewer.REPOSITORY
MD.mQgisMinimumVersion = '3.34'
MD.mEmail = eotimeseriesviewer.MAIL
MD.mIsExperimental = True


########## End of config section


def scantree(path, pattern=re.compile(r'.$')) -> Iterator[Path]:
    """
    Recursively returns file paths in directory
    :param path: root directory to search in
    :param pattern: str with required file ending, e.g. ".py" to search for *.py files
    :return: pathlib.Path
    """
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path, pattern=pattern)
        elif entry.is_file and pattern.search(entry.path):
            yield Path(entry.path)


def create_plugin(include_testdata: bool = False,
                  include_qgisresources: bool = False,
                  create_zip: bool = True,
                  copy_to_profile: bool = False,
                  build_name: str = None) -> Optional[Path]:
    assert (DIR_REPO / '.git').is_dir()

    # BUILD_NAME = '{}.{}.{}'.format(__version__, timestamp, currentBranch)
    # BUILD_NAME = re.sub(r'[:-]', '', BUILD_NAME)
    # BUILD_NAME = re.sub(r'[\\/]', '_', BUILD_NAME)
    # PLUGIN_DIR = DIR_DEPLOY / 'timeseriesviewerplugin'

    DIR_DEPLOY_LOCAL = DIR_REPO / 'deploy'

    REPO = git.Repo(DIR_REPO)
    active_branch = REPO.active_branch.name
    from eotimeseriesviewer import __version__ as VERSION
    VERSION_SHA = REPO.active_branch.commit.hexsha
    lastCommitDate = REPO.active_branch.commit.authored_datetime
    timestamp = re.split(r'[.+]', lastCommitDate.isoformat())[0]

    if build_name is None:
        # we are on release branch
        if re.search(r'release_\d+\.\d+', active_branch):
            BUILD_NAME = VERSION
        else:
            BUILD_NAME = '{}.{}.{}'.format(VERSION, timestamp, active_branch)
            BUILD_NAME = re.sub(r'[:-]', '', BUILD_NAME)
            BUILD_NAME = re.sub(r'[\\/]', '_', BUILD_NAME)
    else:
        BUILD_NAME = build_name

    PLUGIN_DIR = DIR_DEPLOY_LOCAL / 'timeseriesviewerplugin'
    PLUGIN_ZIP = DIR_DEPLOY_LOCAL / 'timeseriesviewerplugin.{}.zip'.format(BUILD_NAME)

    if PLUGIN_DIR.is_dir():
        shutil.rmtree(PLUGIN_DIR)
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    PATH_METADATAFILE = PLUGIN_DIR / 'metadata.txt'
    MD.mVersion = BUILD_NAME
    MD.mAbout = markdown2html(PATH_ABOUT)
    MD.writeMetadataTxt(PATH_METADATAFILE)

    # 1. (re)-compile all resource files

    from scripts.compile_resourcefiles import compileEOTSVResourceFiles
    compileEOTSVResourceFiles()

    # copy python and other resource files
    pattern = re.compile(r'\.(py|svg|png|txt|ui|tif|qml|md|js|css|json)$')
    files = list(scantree(DIR_REPO / 'eotimeseriesviewer', pattern=pattern))
    # add unit tests
    files.extend(list(scantree(DIR_REPO / 'tests', pattern=re.compile(r'\.py$'))))
    files.extend(list(scantree(DIR_REPO / 'example', pattern=re.compile(r'\.(gpkg|csv|tif|xml|py)$'))))
    files.append(DIR_REPO / '__init__.py')
    files.append(DIR_REPO / 'CHANGELOG.md')
    files.append(DIR_REPO / 'ABOUT.md')
    files.append(DIR_REPO / 'CONTRIBUTORS.md')
    files.append(DIR_REPO / 'LICENSE.md')
    files.append(DIR_REPO / 'requirements.txt')
    files.append(DIR_REPO / 'requirements_dev.txt')

    # exclude
    files = [f for f in files
             if 'qgispluginsupport' not in f.as_posix()
             and 'pyqtgraph' not in f.as_posix()
             or (
                     'qgispluginsupport/qps/' in f.as_posix()
                     or 'pyqtgraph/pyqtgraph' in f.as_posix())
             ]

    for fileSrc in files:
        assert fileSrc.is_file()
        fileDst = PLUGIN_DIR / fileSrc.relative_to(DIR_REPO)
        os.makedirs(fileDst.parent, exist_ok=True)
        shutil.copy(fileSrc, fileDst.parent)

    # update metadata version

    f = open(DIR_REPO / 'eotimeseriesviewer' / '__init__.py')
    lines = f.read()
    f.close()
    lines = re.sub(r'(__version__\W*=\W*)([^\n]+)', r'__version__ = "{}"\n'.format(BUILD_NAME), lines)
    f = open(PLUGIN_DIR / 'eotimeseriesviewer' / '__init__.py', 'w')
    f.write(lines)
    f.flush()
    f.close()

    # include test data into test versions
    if include_testdata and not re.search(active_branch, 'master', re.I):
        if os.path.isdir(eotimeseriesviewer.DIR_TESTDATA):
            shutil.copytree(eotimeseriesviewer.DIR_TESTDATA, PLUGIN_DIR / 'example')

    if include_qgisresources and not re.search(active_branch, 'master', re.I):
        qgisresources = Path(DIR_REPO) / 'qgisresources'
        shutil.copytree(qgisresources, PLUGIN_DIR / 'qgisresources')

    createHTMLDocuments(PLUGIN_DIR)
    import scripts.update_docs
    scripts.update_docs.update_documentation()

    # copy license
    shutil.copy(PLUGIN_DIR / 'LICENSE.md', PLUGIN_DIR / 'LICENSE')

    # Copy to other deploy directory
    if copy_to_profile:
        profileManager: QgsUserProfileManager = userProfileManager()
        assert len(profileManager.allProfiles()) > 0
        if isinstance(copy_to_profile, str):
            profileName = copy_to_profile
        else:
            profileName = profileManager.lastProfileName()
        assert profileManager.profileExists(profileName), \
            f'QGIS profiles "{profileName}" does not exist in {profileManager.allProfiles()}'

        profileManager.setActiveUserProfile(profileName)
        profile: QgsUserProfile = profileManager.userProfile()

        DIR_QGIS_USERPROFILE = Path(profile.folder())
        if DIR_QGIS_USERPROFILE:
            os.makedirs(DIR_QGIS_USERPROFILE, exist_ok=True)
            if not DIR_QGIS_USERPROFILE.is_dir():
                raise f'QGIS profile directory "{profile.name()}" does not exists: {DIR_QGIS_USERPROFILE}'

            QGIS_PROFILE_DEPLOY = DIR_QGIS_USERPROFILE / 'python' / 'plugins' / PLUGIN_DIR.name
            # just in case the <profile>/python/plugins folder has not been created before
            os.makedirs(DIR_QGIS_USERPROFILE.parent, exist_ok=True)
            if QGIS_PROFILE_DEPLOY.is_dir():
                print(f'Copy plugin to {QGIS_PROFILE_DEPLOY}...')
                shutil.rmtree(QGIS_PROFILE_DEPLOY)
            shutil.copytree(PLUGIN_DIR, QGIS_PROFILE_DEPLOY)

    # 5. create a zip
    # Create a zip
    if create_zip:
        print('Create zipfile...')
        zipdir(PLUGIN_DIR, PLUGIN_ZIP)

        # 7. install the zip file into the local QGIS instance. You will need to restart QGIS!
        if True:
            info = []
            info.append(
                '\n### To update/install the EO Time Series Viewer, run this command on your QGIS Python shell:\n')
            info.append('from pyplugin_installer.installer import pluginInstaller')
            info.append('pluginInstaller.installFromZipFile(r"{}")'.format(PLUGIN_ZIP))
            info.append('#### Close (and restart manually)\n')
            # print('iface.mainWindow().close()\n')
            info.append('QProcess.startDetached(QgsApplication.arguments()[0], [])')
            info.append('QgsApplication.quit()\n')
            info.append('## press ENTER\n')

            print('\n'.join(info))

            # cb = QGuiApplication.clipboard()
            # if isinstance(cb, QClipboard):
            #    cb.setText('\n'.join(info))

    print('Finished')
    return PLUGIN_ZIP.as_posix()


def markdown2html(path: Union[str, Path]) -> str:
    path_md = Path(path)
    with open(path_md, 'r', encoding='utf-8') as f:
        md = f.read()
    return markdown.markdown(md)


def createHTMLDocuments(dirPlugin: Path):
    """
    Reads the CHANGELOG.md and creates the deploy/CHANGELOG (without extension!) for the QGIS Plugin Manager
    :return:
    """
    pathHTML = dirPlugin / 'CHANGELOG'
    # pathCL2 = DIR_REPO / 'CHANGELOG'
    os.makedirs(pathHTML.parent, exist_ok=True)

    # make html compact
    html = markdown2html(PATH_CHANGELOG).replace('\n', '')
    with open(pathHTML, 'w', encoding='utf-8') as f:
        f.write(''.join(html))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create EO Time Series Viewer Plugin')
    parser.add_argument('-q', '--qgisresources',
                        required=False,
                        default=False,
                        help='Add qgisresources directory to plugin zip. This is only required for test environments',
                        action='store_true')

    parser.add_argument('-z', '--skip_zip',
                        required=False,
                        default=False,
                        help='Skip zip file creation',
                        action='store_true')

    parser.add_argument('-b', '--build-name',
                        required=False,
                        default=None,
                        help=textwrap.dedent("""
                            The build name in "timeseriesviewerplugin.<build name>.zip"
                            Defaults:
                                <version> in case of a release.* branch
                                <version>.<timestamp>.<branch name> in case of any other branch.
                            """
                                             ))

    parser.add_argument('-p', '--profile',
                        nargs='?',
                        const=True,
                        default=False,
                        help=textwrap.dedent("""
                                Install the plugin into a QGIS user profile.
                                Requires that QGIS is closed. Use:
                                -p or --profile for installation into the active user profile
                                --profile=myProfile for installation install it into profile "myProfile"
                                """)
                        )
    args = parser.parse_args()

    path = create_plugin(include_qgisresources=args.qgisresources,
                         build_name=args.build_name,
                         create_zip=not args.skip_zip,
                         copy_to_profile=args.profile)
    print('EOTSV_ZIP={}'.format(path))
