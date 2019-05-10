
import os, sys, re, shutil, zipfile, datetime
from eotimeseriesviewer.externals.qps.make import updateexternals
from eotimeseriesviewer.externals.qps.make.updateexternals import RemoteInfo, updateRemoteLocations
from eotimeseriesviewer import DIR_REPO
import git # install with: pip install gitpython

updateexternals.setProjectRepository(DIR_REPO)


RemoteInfo.create(r'https://bitbucket.org/jakimowb/qgispluginsupport.git',
                  key='qps',
                  #prefixLocal='site-packages/qps',
                  prefixLocal='eotimeseriesviewer/externals/qps',
                  prefixRemote=r'qps',
                  remoteBranch='master')

def updateRemotes(remoteLocations):
    """
    Shortcut to update from terminal
    :param remoteLocations: str or list of str with remote location keys to update.
    """

    if isinstance(remoteLocations, str):
        remoteLocations = [remoteLocations]
    updateexternals.updateRemoteLocations(remoteLocations)

def run():

    updateRemotes('qps')

if __name__ == "__main__":

    # update remotes source-code sources

    to_update = ['qps']

    updateRemotes(to_update)

    if 'qps' in to_update:
        import make
        path = os.path.join(DIR_REPO, r'eotimeseriesviewer/externals/qps/qpsresources.qrc')
        make.compileResourceFile(path)

    exit()