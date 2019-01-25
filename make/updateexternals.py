
import os, sys, re, shutil, zipfile, datetime
from qps.make import updateexternals
from qps.make.updateexternals import RemoteInfo
from timeseriesviewer import DIR_REPO
import git # install with: pip install gitpython

updateexternals.setProjectRepository(DIR_REPO)


RemoteInfo.create(r'https://bitbucket.org/jakimowb/qgispluginsupport.git',
                  key='qps',
                  prefixLocal='site-packages/qps',
                  prefixRemote=r'qps',
                  remoteBranch='master')


if __name__ == "__main__":

    # update remotes source-code sources

    to_update = ['qps']
    import qps.make.updateexternals
    qps.make.updateexternals.updateRemoteLocations(to_update)
    exit()