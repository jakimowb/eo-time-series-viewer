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

import os, sys, re, shutil, datetime, requests
from requests.auth import HTTPBasicAuth
from http.client import responses
import xml.etree.ElementTree as ET
from xml.dom import minidom
from ..testing import initQgisApplication
qgisApp = initQgisApplication()
from ..utils import *

from qgis.PyQt.QtCore import *
import numpy as np
from pb_tool import pb_tool # install with: pip install pb_tool
import git



CHECK_COMMITS = False
DIR_REPO = findUpwardPath(__file__, '.git')

DIR_DEPLOY = jp(DIR_REPO, 'deploy')
PLUGIN_REPO_XML_REMOTE = os.path.join(DIR_DEPLOY, 'qgis_plugin_develop.xml')
PLUGIN_REPO_XML_LOCAL = os.path.join(DIR_DEPLOY, 'qgis_plugin_develop_local.xml')
URL_DOWNLOADS = r'https://bitbucket.org/hu-geomatics/enmap-box/downloads'
URL_WIKI = r'https://api.bitbucket.org/2.0/repositories/hu-geomatics/enmap-box/wiki/src'


########## End of config section



class QGISMetadataFileWriter(object):

    def __init__(self):
        self.mName = None

        self.mDescription = None
        self.mVersion = None
        self.mQgisMinimumVersion = '3.8'
        self.mQgisMaximumVersion = '3.99'
        self.mAuthor = None
        self.mAbout = None
        self.mEmail = None
        self.mHomepage = None
        self.mIcon = None
        self.mTracker = None
        self.mRepository = None
        self.mIsExperimental = False
        self.mTags = None
        self.mCategory = None
        self.mChangelog = ''

    def validate(self)->bool:

        return True

    def metadataString(self)->str:
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

        lines.append('homepage={}'.format(self.mHomepage))
        if self.mTracker:
            lines.append('tracker={}'.format(self.mTracker))
        if self.mRepository:
            lines.append('repository={}'.format(self.mRepository))
        if isinstance(self.mIsExperimental, bool):
            lines.append('experimental={}'.format(self.mIsExperimental))


        #lines.append('deprecated={}'.format(self.mIsDeprecated))
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

    def writeMetadataTxt(self, path:str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.metadataString())
        # read again and run checks
        import pyplugin_installer.installer_data

        # test if we could read the plugin
        import pyplugin_installer.installer_data
        P = pyplugin_installer.installer_data.Plugins()
        plugin = P.getInstalledPlugin(self.mName, os.path.dirname(path), True)

        #if hasattr(pyplugin_installer.installer_data, 'errorDetails'):
        #    raise Exception('plugin structure/metadata error:\n{}'.format(pyplugin_installer.installer_data.errorDetails))
        s = ""



def buildId()->str:
    """
    Returns an id string consisting of <pluginname
    :return:
    """
    assert os.path.isdir(DIR_REPO)
    try:
        REPO = git.Repo(DIR_REPO)
        currentBranch = REPO.active_branch.name
    except Exception as ex:
        print(ex, file=sys.stderr)
        print('use ')
    timestamp = ''.join(np.datetime64(datetime.datetime.now()).astype(str).split(':')[0:-1]).replace('-', '')
    buildID = '{}.{}.{}'.format(re.search(r'(\.?[^.]*){2}', __version__).group()
                                , timestamp,
                                re.sub(r'[\\/]', '_', currentBranch))


def build():

    # local pb_tool configuration file.
    pathCfg = jp(DIR_REPO, 'pb_tool.cfg')
    cfg = pb_tool.get_config(pathCfg)
    cdir = os.path.dirname(pathCfg)
    pluginname = cfg.get('plugin', 'name')
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    os.chdir(cdir)

    mkDir(DIR_DEPLOY)

    if os.path.isdir(dirPlugin):
        print('Remove old build folder...')
        shutil.rmtree(dirPlugin, ignore_errors=True)

    # required to choose andy DIR_DEPLOY of choice
    # issue tracker: https://github.com/g-sherman/plugin_build_tool/issues/4

    if True:
        # 1. clean an existing directory = the enmapboxplugin folder
        pb_tool.clean_deployment(ask_first=False)



        if currentBranch not in ["develop", "master"]:
            print('Skipped automatic version update because current branch is not "develop" or "master". ')
        else:
            # 2. set the version to all relevant files
            # r = REPO.git.execute(['git','diff', '--exit-code']).split()
            diffs = [r for r in REPO.index.diff(None) if 'deploy.py' not in str(r)]
            if CHECK_COMMITS and len(diffs) > 0:
                # there are diffs. we need to commit them first.
                # This should not be done automatically, as each commit should contain a proper commit message
                raise Exception('Please commit all changes first.')

        # 2. Compile. Basically call pyrcc to create the resources.rc file
        try:
            pb_tool.compile_files(cfg)
        except Exception as ex:
            print('Failed to compile resources')
            print(ex)

        # 3. Deploy = write the data to the new plugin folder
        pb_tool.deploy_files(pathCfg, DIR_DEPLOY, quick=True, confirm=False)

        # 4. As long as we can not specify in the pb_tool.cfg which file types are not to deploy,
        # we need to remove them afterwards.
        # issue: https://github.com/g-sherman/plugin_build_tool/issues/5
        print('Remove files...')

        if True:
            # delete help folder
            shutil.rmtree(os.path.join(dirPlugin, *['help']), ignore_errors=True)
        for f in file_search(DIR_DEPLOY, re.compile('(svg|pyc)$'), recursive=True):
            os.remove(f)

    #update metadata version
    if True:
        pathMetadata = jp(dirPlugin, 'metadata.txt')
        # update version number in metadata
        f = open(pathMetadata)
        lines = f.readlines()
        f.close()
        lines = re.sub('version=.*\n', 'version={}\n'.format(buildID), ''.join(lines))
        f = open(pathMetadata, 'w')
        f.write(lines)
        f.flush()
        f.close()

        pathPackageInit = jp(dirPlugin, *['enmapbox', '__init__.py'])
        f = open(pathPackageInit)
        lines = f.read()
        f.close()
        lines = re.sub(r'(__version__\W*=\W*)([^\n]+)', r'__version__ = "{}"\n'.format(buildID), lines)
        f = open(pathPackageInit, 'w')
        f.write(lines)
        f.flush()
        f.close()

    # 5. create a zip
    print('Create zipfile...')

    pluginname = cfg.get('plugin', 'name')
    pathZip = jp(DIR_DEPLOY, '{}.{}.zip'.format(pluginname, buildID))
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    zipdir(dirPlugin, pathZip)
    # os.chdir(dirPlugin)
    # shutil.make_archive(pathZip, 'zip', '..', dirPlugin)

    # 6. install the zip file into the local QGIS instance. You will need to restart QGIS!
    if True:
        print('\n### To update/install, run this command on your QGIS Python shell:\n')
        print('from pyplugin_installer.installer import pluginInstaller')
        print('pluginInstaller.installFromZipFile(r"{}")'.format(pathZip))
        print('#### Close (and restart manually)\n')
        #print('iface.mainWindow().close()\n')
        print('QProcess.startDetached(QgsApplication.arguments()[0], [])')
        print('QgsApplication.quit()\n')
        print('## press ENTER\n')

    print('Finished')


def updateRepositoryXML(path:str=None):
    """
    Creates two XML files:
        deploy/qgis_plugin_develop.xml - to be uploaded to the git repository
        deploy/qgis_plugin_develop_local.xml - can be used as local QGIS Repository source
    :param path: str, optional, path of local *.zip which has been build with build()
    :return:
    """
    #if not isinstance(path, str):
    #    zipFiles = file_search(DIR_DEPLOY, 'enmapbox*.zip')
    #    zipFiles.sort(key=lambda f:os.path.getctime(f))
    #    path = zipFiles[-1]

    assert isinstance(path, str)
    assert os.path.isfile(path)
    assert os.path.splitext(path)[1] == '.zip'

    os.makedirs(DIR_DEPLOY, exist_ok=True)
    bn = os.path.basename(path)
    version = re.search(r'^.*plugin\.(.*)\.zip$', bn).group(1)
    s = ""
    """
 <?xml-stylesheet type="text/xsl" href="plugins.xsl" ?>
<plugins>
   <pyqgis_plugin name="EnMAP-Box (develop version)" version="3.2.20180904T1723.DEVELOP">
        <description><![CDATA[EnMAP-Box development version]]></description>
        <about><![CDATA[EnMAP-Box Preview.]]></about>
        <version>3.2.20180904T1723.DEVELOP</version>
        <trusted>True</trusted>
        <qgis_minimum_version>3.2.0</qgis_minimum_version>
        <qgis_maximum_version>3.99.0</qgis_maximum_version>
        <homepage><![CDATA[https://bitbucket.org/hu-geomatics/enmap-box/]]></homepage>
        <file_name>enmapboxplugin.3.3.20180904T1723.develop.snapshot.zip</file_name>
        <icon></icon>
        <author_name><![CDATA[HU Geomatics]]></author_name>
        <download_url>https://bitbucket.org/hu-geomatics/enmap-box/downloads/enmapboxplugin.3.2.20180904T1723.develop.snapshot.zip</download_url>
        <uploaded_by><![CDATA[jakimowb]]></uploaded_by>
        <experimental>False</experimental>
        <deprecated>False</deprecated>
        <tracker><![CDATA[https://bitbucket.org/hu-geomatics/enmap-box/issues/]]></tracker>
        <repository><![CDATA[https://bitbucket.org/hu-geomatics/enmap-box/src]]></repository>
        <tags><![CDATA[Remote Sensing]]></tags>
        <downloads>0</downloads>
        <average_vote>0.0</average_vote>
        <rating_votes>0</rating_votes>
        <external_dependencies></external_dependencies>
        <server>True</server>
    </pyqgis_plugin>
</plugins>
    """
    download_url = URL_DOWNLOADS+'/'+bn

    root = ET.Element('plugins')
    plugin = ET.SubElement(root, 'pyqgis_plugin')
    plugin.attrib['name'] = "EnMAP-Box (develop version)"
    plugin.attrib['version'] = '{}'.format(version)
    ET.SubElement(plugin, 'description').text = r'EnMAP-Box development version'
    ET.SubElement(plugin, 'about').text = 'Preview'
    ET.SubElement(plugin, 'version').text = version
    ET.SubElement(plugin, 'qgis_minimum_version').text = '3.2'
    ET.SubElement(plugin, 'qgis_maximum_version').text = '3.99'
    ET.SubElement(plugin, 'homepage').text = enmapbox.HOMEPAGE
    ET.SubElement(plugin, 'file_name').text = bn
    ET.SubElement(plugin, 'icon').text = 'enmapbox.png'
    ET.SubElement(plugin, 'author_name').text = 'Andreas Rabe, Benjamin Jakimow, Fabian Thiel, Sebastian van der Linden'
    ET.SubElement(plugin, 'download_url').text = download_url
    ET.SubElement(plugin, 'deprecated').text = 'False'
    #is this a supported tag????
    #ET.SubElement(plugin, 'external_dependencies').text = ','.join(enmapbox.DEPENDENCIES)
    ET.SubElement(plugin, 'tracker').text = enmapbox.ISSUE_TRACKER
    ET.SubElement(plugin, 'repository').text = enmapbox.REPOSITORY
    ET.SubElement(plugin, 'tags').text = 'Remote Sensing, Raster'
    ET.SubElement(plugin, 'experimental').text = 'False'

    tree = ET.ElementTree(root)

    xml = ET.tostring(root)
    dom = minidom.parseString(xml)
    #<?xml version="1.0"?>
    #<?xml-stylesheet type="text/xsl" href="plugins.xsl" ?>
    #pi1 = dom.createProcessingInstruction('xml', 'version="1.0"')
    url_xsl = 'https://plugins.qgis.org/static/style/plugins.xsl'
    pi2 = dom.createProcessingInstruction('xml-stylesheet', 'type="text/xsl" href="{}"'.format(url_xsl))

    dom.insertBefore(pi2, dom.firstChild)

    xmlRemote = dom.toprettyxml(encoding='utf-8').decode('utf-8')

    with open(PLUGIN_REPO_XML_REMOTE, 'w') as f:
        f.write(xmlRemote)

    import pathlib
    uri = pathlib.Path(path).as_uri()
    xmlLocal = re.sub(r'<download_url>.*</download_url>', r'<download_url>{}</download_url>'.format(uri), xmlRemote)
    with open(PLUGIN_REPO_XML_LOCAL, 'w') as f:
        f.write(xmlLocal)

   # tree.write(pathXML, encoding='utf-8', pretty_print=True, xml_declaration=True)
    #https://bitbucket.org/hu-geomatics/enmap-box/raw/HEAD/qgis_plugin_develop.xml

def uploadDeveloperPlugin():
    urlDownloads = 'https://api.bitbucket.org/2.0/repositories/hu-geomatics/enmap-box/downloads'
    assert os.path.isfile(PLUGIN_REPO_XML_REMOTE)

    if True:
        #copy to head
        bnXML = os.path.basename(PLUGIN_REPO_XML_REMOTE)
        pathNew = os.path.join(DIR_REPO, bnXML)
        print('Copy {}\n\tto {}'.format(PLUGIN_REPO_XML_REMOTE, pathNew))
        shutil.copy(PLUGIN_REPO_XML_REMOTE, pathNew)
        import git
        REPO = git.Repo(DIR_REPO)
        for diff in REPO.index.diff(None):
            if diff.a_path == bnXML:
                REPO.git.execute(['git', 'commit', '-m', "'updated {}'".format(bnXML), bnXML])
        REPO.git.push()

    UPLOADS = {urlDownloads:[]}    #urlRepoXML:[PLUGIN_REPO_XML],
                #urlDownloads:[PLUGIN_REPO_XML]}
    doc = minidom.parse(PLUGIN_REPO_XML_REMOTE)
    for tag in doc.getElementsByTagName('file_name'):
        bn = tag.childNodes[0].nodeValue
        pathFile = os.path.join(DIR_DEPLOY, bn)
        assert os.path.isfile(pathFile)
        UPLOADS[urlDownloads].append(pathFile)

    for url, paths in UPLOADS.items():
        UPLOADS[url] = [p.replace('\\','/') for p in paths]

    skeyUsr = 'enmapbox-repo-username'
    settings = QSettings('HU Geomatics', 'enmabox-development-team')
    usr = settings.value(skeyUsr, '')
    pwd = ''
    auth = HTTPBasicAuth(usr, pwd)
    auth_success = False
    while not auth_success:
        try:
            if False: #print curl command(s) to be used in shell
                print('# CURL command(s) to upload enmapbox plugin build')
                for url, paths in UPLOADS.items():

                    cmd = ['curl']
                    if auth.username:
                        tmp = '-u {}'.format(auth.username)
                        if auth.password:
                            tmp += ':{}'.format(auth.password)
                        cmd.append(tmp)
                        del tmp
                    cmd.append('-X POST {}'.format(urlDownloads))
                    for f in paths:
                        cmd.append('-F files=@{}'.format(f))
                    cmd = ' '.join(cmd)

                    print(cmd)
                    print('# ')
            # files = {'file': ('test.csv', 'some,data,to,send\nanother,row,to,send\n')}

            if True: #upload

                session = requests.Session()
                session.auth = auth

                for url, paths in UPLOADS.items():
                    for path in paths:
                        print('Upload {} \n\t to {}...'.format(path, url))
                        #mimeType = mimetypes.MimeTypes().guess_type(path)[0]
                        #files = {'file': (open(path, 'rb'), mimeType)}
                        files = {'files':open(path, 'rb')}

                        r = session.post(url, auth=auth, files=files)
                        #r = requests.post(url, auth=auth, data = open(path, 'rb').read())
                        r.close()
                        assert isinstance(r, requests.models.Response)

                        for f in files.values():
                            if isinstance(f, tuple):
                                f = f[0]
                            f.close()

                        info = 'Status {} "{}"'.format(r.status_code, responses[r.status_code])
                        if r.status_code == 401:
                            print(info, file=sys.stderr)
                            from qgis.gui import QgsCredentialDialog
                            #from qgis.core import QgsCredentialsConsole

                            d = QgsCredentialDialog()
                            #d = QgsCredentialsConsole()
                            ok, usr, pwd = d.request(url, auth.username, auth.password)
                            if ok:
                                auth.username = usr
                                auth.password = pwd
                                session.auth = auth
                                continue
                            else:

                                raise Exception('Need credentials to access {}'.format(url))
                        elif not r.status_code in [200,201]:
                            print(info, file=sys.stderr)
                        else:
                            print(info)
                            auth_success = True

        except Exception as ex:
            pass

    if auth_success:
        settings.setValue(skeyUsr, session.auth.username)




