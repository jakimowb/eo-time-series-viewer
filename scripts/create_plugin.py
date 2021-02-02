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
import datetime
import os
import pathlib
import re
import shutil
import typing
import site
import io
import docutils.core
from xml.dom import minidom
site.addsitedir(pathlib.Path(__file__).parents[1])
import eotimeseriesviewer
from eotimeseriesviewer import DIR_REPO, __version__
from eotimeseriesviewer.externals.qps.make.deploy import QGISMetadataFileWriter

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
MD.mQgisMinimumVersion = '3.14'
MD.mEmail = eotimeseriesviewer.MAIL



########## End of config section

def aboutText() -> str:
    with open(eotimeseriesviewer.PATH_ABOUT, 'r', encoding='utf-8') as f:
        aboutText = f.readlines()
        for i in range(1, len(aboutText)):
            aboutText[i] = '    ' + aboutText[i]
        aboutText = ''.join(aboutText)
    return aboutText


MD.mAbout = aboutText()


def scantree(path, pattern=re.compile(r'.$')) -> typing.Iterator[pathlib.Path]:
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
            yield pathlib.Path(entry.path)


def create_plugin(include_testdata: bool = False,
                  include_qgisresources: bool = False,
                  zipfilename: str = None,
                  latest: bool = False) -> str:
    assert (DIR_REPO / '.git').is_dir()
    DIR_DEPLOY = DIR_REPO / 'deploy'

    try:
        import git
        REPO = git.Repo(DIR_REPO)
        currentBranch = REPO.active_branch.name
    except Exception as ex:
        currentBranch = 'TEST'
        print('Unable to find git repo. Set currentBranch to "{}"'.format(currentBranch))

    timestamp = datetime.datetime.now().isoformat().split('.')[0]

    BUILD_NAME = '{}.{}.{}'.format(__version__, timestamp, currentBranch)
    BUILD_NAME = re.sub(r'[:-]', '', BUILD_NAME)
    BUILD_NAME = re.sub(r'[\\/]', '_', BUILD_NAME)
    PLUGIN_DIR = DIR_DEPLOY / 'timeseriesviewerplugin'

    if latest:

        branch = currentBranch
        branch = re.sub(r'[:-]', '', branch)
        branch = re.sub(r'[\\/]', '_', branch)
        PLUGIN_ZIP = DIR_DEPLOY / 'timeseriesviewerplugin.{}.latest.zip'.format(branch)
    else:
        if isinstance(zipfilename, str) and len(zipfilename) > 0:
            if not zipfilename.endswith('.zip'):
                zipfilename += '.zip'
            PLUGIN_ZIP = DIR_DEPLOY / zipfilename
        else:
            PLUGIN_ZIP = DIR_DEPLOY / 'timeseriesviewerplugin.{}.zip'.format(BUILD_NAME)

    if PLUGIN_DIR.is_dir():
        shutil.rmtree(PLUGIN_DIR)
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    PATH_METADATAFILE = PLUGIN_DIR / 'metadata.txt'
    MD.mVersion = BUILD_NAME
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
    files.append(DIR_REPO / 'CHANGELOG.rst')
    files.append(DIR_REPO / 'ABOUT.html')
    files.append(DIR_REPO / 'CONTRIBUTORS.rst')
    files.append(DIR_REPO / 'LICENSE.md')
    files.append(DIR_REPO / 'requirements.txt')
    files.append(DIR_REPO / 'requirements_dev.txt')

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
    if include_testdata and not re.search(currentBranch, 'master', re.I):
        if os.path.isdir(eotimeseriesviewer.DIR_TESTDATA):
            shutil.copytree(eotimeseriesviewer.DIR_TESTDATA, PLUGIN_DIR / 'example')

    if include_qgisresources and not re.search(currentBranch, 'master', re.I):
        qgisresources = pathlib.Path(DIR_REPO) / 'qgisresources'
        shutil.copytree(qgisresources, PLUGIN_DIR / 'qgisresources')

    createHTMLDocuments(PLUGIN_DIR)
    import scripts.update_docs
    scripts.update_docs.update_documentation()

    # 5. create a zip
    print('Create zipfile...')
    from eotimeseriesviewer.utils import zipdir
    zipdir(PLUGIN_DIR, PLUGIN_ZIP)

    # 7. install the zip file into the local QGIS instance. You will need to restart QGIS!
    if True:
        info = []
        info.append('\n### To update/install the EO Time Series Viewer, run this command on your QGIS Python shell:\n')
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


def rst2html(pathMD: pathlib.Path) -> str:
    """
    Convert a rst file to html
    """

    assert pathMD.is_file()

    overrides = {'stylesheet': None,
                 'embed_stylesheet': False,
                 'output_encoding': 'utf-8',
                 'dump_pseudo_xml': False,
                 }

    buffer = io.StringIO()
    html = docutils.core.publish_file(source_path=pathMD, writer_name='html5', settings_overrides=overrides, destination=buffer)

    xml = minidom.parseString(html)
    #  remove headline
    for i, node in enumerate(xml.getElementsByTagName('h1')):
        if i == 0:
            node.parentNode.removeChild(node)
        else:
            node.tagName = 'h4'

    for node in xml.getElementsByTagName('link'):
        node.parentNode.removeChild(node)

    for node in xml.getElementsByTagName('meta'):
        if node.getAttribute('name') == 'generator':
            node.parentNode.removeChild(node)

    xml = xml.getElementsByTagName('body')[0]
    html = xml.toxml()
    html_cleaned = []
    for line in html.split('\n'):
        # line to modify
        line = re.sub(r'class="[^"]*"', '', line)
        line = re.sub(r'id="[^"]*"', '', line)
        line = re.sub(r'<li><p>', '<li>', line)
        line = re.sub(r'</p></li>', '</li>', line)
        line = re.sub(r'</?(dd|dt|div|body)[ ]*>', '', line)
        line = line.strip()
        if line != '':
            html_cleaned.append(line)
    return html


def createHTMLDocuments(dirPlugin: pathlib.Path):
    """
    Reads the CHANGELOG.rst and creates the deploy/CHANGELOG (without extension!) for the QGIS Plugin Manager
    :return:
    """

    pathMD = DIR_REPO / 'CHANGELOG.rst'
    pathHTML = dirPlugin / 'CHANGELOG'
    # pathCL2 = DIR_REPO / 'CHANGELOG'
    os.makedirs(pathHTML.parent, exist_ok=True)

    # make html compact
    html_cleaned = rst2html(pathMD)
    with open(pathHTML, 'w', encoding='utf-8') as f:
        f.write(''.join(html_cleaned))

    pathMD = DIR_REPO / 'LICENSE.md'
    pathHTML = dirPlugin / 'LICENSE.html'
    html_cleaned = rst2html(pathMD)

    with open(pathHTML, 'w', encoding='utf-8') as f:
        f.write(''.join(html_cleaned))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create EO Time Series Viewer Plugin')
    parser.add_argument('-q', '--qgisresources',
                        required=False,
                        default=False,
                        help='Add qgisresources directory to plugin zip. This is only required for test environments',
                        action='store_true')
    parser.add_argument('-z', '--zipfilename',
                        required=False,
                        default=None,
                        type=str,
                        help='final path of generated zipfile')

    parser.add_argument('-l', '--latest',
                        required=False,
                        help='Name the output zip like timeseriesviewer.<branch name>.latest.zip,'
                             'e.g. for generic uploads',
                        default=None,
                        action='store_true')

    args = parser.parse_args()

    path = create_plugin(include_qgisresources=args.qgisresources,
                         zipfilename=args.zipfilename,
                         latest=args.latest)
    print('EOTSV_ZIP={}'.format(path))
    exit(0)
