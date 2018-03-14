# -*- coding: utf-8 -*-

"""
***************************************************************************
    deploy.py
    Script to build the HUB-TimeSeriesViewer from Repository code
    ---------------------
    Date                 : September 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""



import os, sys, re, shutil, zipfile, datetime
import numpy as np
from pb_tool import pb_tool
from timeseriesviewer import DIR_REPO, jp, file_search
import timeseriesviewer
DIR_BUILD = jp(DIR_REPO, 'build')
DIR_DEPLOY = jp(DIR_REPO, 'deploy')




#list of deploy options:
# ZIP - add zipped plugin to DIR_DEPLOY
# UNZIPPED - add the non-zipped plugin to DIR_DEPLOY
DEPLOY_OPTIONS = ['ZIP', 'UNZIPPED']
ADD_TESTDATA = True

#directories below the <enmapbox-repository> folder whose content is to be copied without filtering
PLAIN_COPY_SUBDIRS = ['site-packages']

########## End of config section
timestamp = ''.join(np.datetime64(datetime.datetime.now()).astype(str).split(':')[0:-1])
buildID = '{}.{}'.format(timeseriesviewer.VERSION, timestamp)
dirBuildPlugin = jp(DIR_BUILD, 'timeseriesviewerplugin')

def rm(p):
    """
    Remove files or directory 'p'
    :param p: path of file or directory to be removed.
    """
    if os.path.isfile(p):
        os.remove(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)

def cleanDir(d):
    """
    Remove content from directory 'd'
    :param d: directory to be cleaned.
    """
    assert os.path.isdir(d)
    for root, dirs, files in os.walk(d):
        for p in dirs + files: rm(jp(root,p))
        break

def mkDir(d, delete=False):
    """
    Make directory.
    :param d: path of directory to be created
    :param delete: set on True to delete the directory contents, in case the directory already existed.
    """
    if delete and os.path.isdir(d):
        cleanDir(d)
    if not os.path.isdir(d):
        os.makedirs(d)

def patch_pb_tool(DIR_DEPLOY):

    #local pb_tool configuration file.
    pathCfg = jp(DIR_REPO, 'pb_tool.cfg')

    #required to choose andy DIR_DEPLOY of choice
    #issue tracker: https://github.com/g-sherman/plugin_build_tool/issues/4
    pb_tool.get_plugin_directory = lambda : DIR_DEPLOY
   #pb_tool.cli.command = lambda f:f
    #Issue 1.: set pb_tool.cfg directly and do not expect current WDir
    def config():
        import ConfigParser
        cfg = ConfigParser.ConfigParser()
        cfg.read(pathCfg)
        return cfg
    pb_tool.config = config

    #issue 2: do not expect compiled resource files to end on '_rc.py'
    def compiled_resource():
        return []
        import ConfigParser
        cfg = config()
        try:
            res_files = cfg.get('files', 'resource_files').split()
            compiled = []
            for res in res_files:
                (base, ext) = os.path.splitext(res)

                #CHANGED!!!! no '_rc.py'
                compiled.append('{}.py'.format(base))
            # print "Compiled resource files: {}".format(compiled)
            return compiled
        except ConfigParser.NoSectionError as oops:
            print oops.message
            sys.exit(1)
    pb_tool.compiled_resource = compiled_resource

    #Issues:
    #def compiled_ui():
    #    return []
    #    files = file_search(jp(DIR_REPO,'timeseriesviewer'), '*.ui', recursive=True)
    #    return files
    #pb_tool.compiled_ui = compiled_ui

    #Issues:
    _deployOld = pb_tool.deploy
    def deploy():
        #create target directories
        plugin_dir = os.path.join(pb_tool.get_plugin_directory(), pb_tool.config().get('plugin', 'name'))
        install_files = pb_tool.get_install_files()

        for file in install_files:
            d = os.path.dirname(jp(plugin_dir,file))
            if not os.path.exists(d):
                os.makedirs(d)
        _deployOld()
    pb_tool.deploy = deploy


    #Issue: my 'help' dir is called 'doc'
    def build_docs():
        """ Build the docs using sphinx"""
        import subprocess
        helpDir = jp(DIR_REPO, 'doc')
        #if os.path.exists('help'):

        if os.path.exists(helpDir):
            if sys.platform == 'win32':
                makeprg = 'make.bat'
            else:
                makeprg = 'make'
            cwd = os.getcwd()
            os.chdir(helpDir)
            subprocess.check_call([makeprg, 'html'])
            os.chdir(cwd)
        else:
            print "No help directory exists in the current directory"
    pb_tool.build_docs = build_docs

if __name__ == "__main__":


    #the directory to build the "enmapboxplugin" folder
    DIR_DEPLOY = jp(DIR_REPO, 'deploy')
    mkDir(DIR_DEPLOY)

    import pb_tool

    # DIR_DEPLOY = r'E:\_EnMAP\temp\temp_bj\enmapbox_deploys\most_recent_version'

    patch_pb_tool(DIR_DEPLOY)
    pathCfg = jp(DIR_REPO, 'pb_tool.cfg')
    cfg = pb_tool.config()
    pluginname = cfg.get('plugin', 'name')


    if True:
        #1. clean an existing directory = the timeseriesviewer folder
        pb_tool.clean_deployment(ask_first=False)

        #2. Compile. Basically call pyrcc to create the resources.rc file
        #I don't know how to call this from pure python
        if False:
            import subprocess
            import make

            os.chdir(DIR_REPO)
            subprocess.call(['pb_tool', 'compile'])
            make.compile_rc_files(DIR_REPO)

        else:
            pb_tool.compile_files()


        #3. Deploy = write the data to the new enmapboxplugin folder
        os.chdir(os.path.dirname(pathCfg))
        pb_tool.deploy()

        #4. As long as we can not specify in the pb_tool.cfg which file types are not to deploy,
        # we need to remove them afterwards.
        # issue: https://github.com/g-sherman/plugin_build_tool/issues/5
        print('Remove files...')

        for f in file_search(DIR_DEPLOY, re.compile('(svg|pyc)$'), recursive=True):
            os.remove(f)

    #5. create a zip
    print('Create zipfile...')
    from timeseriesviewer.utils import zipdir


    pathZip = jp(DIR_DEPLOY, '{}.{}.zip'.format(pluginname,timestamp))
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    zipdir(dirPlugin, pathZip)
    #os.chdir(dirPlugin)
    #shutil.make_archive(pathZip, 'zip', '..', dirPlugin)

    # 6. copy to local QGIS user DIR
    if True:
        import shutil

        from os.path import expanduser

        pathQGIS = os.path.join(expanduser("~"), *['.qgis2', 'python', 'plugins'])

        assert os.path.isdir(pathQGIS)
        pathDst = os.path.join(pathQGIS, os.path.basename(dirPlugin))
        rm(pathDst)
        shutil.copytree(dirPlugin, pathDst)
        s = ""

    print('Finished')
