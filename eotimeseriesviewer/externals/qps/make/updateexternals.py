# -*- coding: utf-8 -*-

"""
***************************************************************************
    updateexternals.py
    A script to update source code stored in external repositories, but to
    be part of the own.

    RemoteInfo.create(r'https://bitbucket.org/jakimowb/qgispluginsupport.git',
                  key='qps',
                  prefixLocal='site-packages/qps',
                  prefixRemote=r'qps',
                  remoteBranch='master')


    ---------------------
    Date                 : January 2019
    Copyright            : (C) 2019 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import os, sys, re, shutil, zipfile, datetime, pathlib
import git # install with: pip install gitpython
REMOTEINFOS = dict()

DIR_REPO = None
REPO = None

def setProjectRepository(path):
    """
    Sets the project root directory which contains the `.git` folder
    :param path: str
    """
    assert os.path.isdir(path)
    global DIR_REPO, REPO
    DIR_REPO = path
    REPO = git.Repo(DIR_REPO)




class RemoteInfo(object):
    @staticmethod
    def create(*args, **kwds):
        info = RemoteInfo(*args, **kwds)
        if not info.key in REMOTEINFOS.keys():
            REMOTEINFOS[info.key] = []
        REMOTEINFOS[info.key].append(info)

    def __init__(self, uri, key=None, prefixLocal=None, prefixRemote=None, remoteBranch='master', excluded=[],
                 postupdatehook=None):
        """
        Describes how a remote repository is connected to this repository
        :param uri: uri of remote repository. Needs to end with  '.git'
        :param key: name under which the remote repo will be knows.
            Defaults to remote-repo if uri is like ..remote-repo.git
        :param prefixLocal: local location. Defaults to <this-repo>/<key>
        :param prefixRemote: remote location behind <remoteBranch>,
            e.g. "subfolder" to get "<remoteBranch>:subfolder" only.
            Defaults to root of remote repository
        :param remoteBranch: the remote branch. Defaults to "master"
        """
        assert uri.endswith('.git')
        self.uri = uri
        self.key = key if key is not None else os.path.splitext(os.path.basename(self.uri))[0]
        assert prefixLocal != ''
        assert prefixRemote != ''
        self.prefixLocal = self.key if prefixLocal is None else prefixLocal
        self.prefixRemote = prefixRemote
        self.remoteBranch = remoteBranch
        self.excluded = excluded
        self.postupdatehook = None

    def __repr__(self):
        infos = ['RemoteInfo: "{}"'.format(os.path.basename(self.uri))]

        for attribute, value in self.__dict__.items():
            if not attribute.startswith('_'):
                infos.append('\t{}:{}'.format(attribute, value))

        return '\n'.join(infos)

    def remotePath(self):
        if self.prefixRemote is None or len(self.prefixRemote) == 0:
            return self.remoteBranch
        else:
            return self.remoteBranch + ':' + self.prefixRemote




def updateRemote(remoteInfo:RemoteInfo):
    """
    Updates the sources from the remote repository described in `remoteInfo`
    :param remoteInfo: RemoteInfo
    """
    if isinstance(remoteInfo, str):
        remoteInfos = REMOTEINFOS[remoteInfo]
    assert isinstance(remoteInfos, list)

    for info in remoteInfos:
        assert isinstance(info, RemoteInfo)

    # see https://stackoverflow.com/questions/23937436/add-subdirectory-of-remote-repo-with-git-subtree
    # see https://blisqu.wordpress.com/2012/09/08/merge-subdirectory-from-another-git-repository/
    for remoteInfo in remoteInfos:
        print('Update {}'.format(remoteInfo))
        assert isinstance(remoteInfo, RemoteInfo)
        remote = REPO.remote(remoteInfo.key)
        print('Fetch {}...'.format(remoteInfo.remoteBranch))
        remote.fetch(remoteInfo.remoteBranch)
        files = REPO.git.execute(
            ['git', 'ls-tree', '--name-only', '-r', 'HEAD', remoteInfo.prefixLocal]).split()
        if len(files) > 0:
            pass

        p = pathlib.Path(DIR_REPO) / pathlib.Path(remoteInfo.prefixLocal)
        if os.path.exists(p):
            print('Delete {}'.format(p))
            REPO.git.execute(['git', 'rm', '-f', '-r', remoteInfo.prefixLocal])
            if os.path.exists(p):
                shutil.rmtree(p)

        cmdArgs = ['git', 'read-tree', '--prefix', remoteInfo.prefixLocal,
                   '-u', '{}/{}'.format(remoteInfo.key, remoteInfo.remotePath())]

        files = REPO.git.execute(cmdArgs).split()

        # remove excluded files
        for e in remoteInfo.excluded:
            localPath = pathlib.Path(remoteInfo.prefixLocal) / e
            fullPath = pathlib.Path(DIR_REPO) / localPath
            if os.path.exists(fullPath):
                try:
                    info = ''.join([i for i in REPO.git.rm(localPath.as_posix(), r=True, f=True)])
                    print(info)
                except Exception as ex:
                    print(ex, file=sys.stderr)

        print('Update {} done'.format(remoteInfo.key))


def addRemote(remoteInfo):
    assert isinstance(remoteInfo, RemoteInfo)
    """
    :param name: Desired name of the remote
    :param url: URL which corresponds to the remote's name
    :param kwargs: Additional arguments to be passed to the git-remote add command
    :return: New Remote instance
    :raise GitCommandError: in case an origin with that name already exists
    """
    newRemote = REPO.create_remote(remoteInfo.key, remoteInfo.uri)
    newRemote.fetch(remoteInfo.remoteBranch)


def updateRemoteLocations(locationsToUpdate:list):
    if not isinstance(locationsToUpdate, list):
        locationsToUpdate = list(locationsToUpdate)

    for id in locationsToUpdate:
        assert isinstance(id, str)
        assert id in REMOTEINFOS.keys(), 'Unknown remote location key "{}"'.format(id)

    # check existing remotes
    print('Remotes:')
    existingRemoteNames = [r.name for r in REPO.remotes if r.name != 'origin']
    for rn in existingRemoteNames:
        if rn not in REMOTEINFOS.keys():
            print('Not described in RemoteInfos: {}'.format(rn))

    for rn in REMOTEINFOS.keys():
        if rn not in existingRemoteNames:
            print('Need to add {}'.format(rn))
            for info in REMOTEINFOS[rn]:
                try:
                    addRemote(info)
                except Exception as ex:
                    print(ex, file=sys.stderr)

    for p in locationsToUpdate:
        try:
            updateRemote(p)
        except Exception as ex:
            print(ex, file=sys.stderr)
    print('Updates finished')

