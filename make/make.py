# -*- coding: utf-8 -*-

import os, sys, fnmatch, six, subprocess, re

ROOT = os.path.dirname(os.path.dirname(__file__))

from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.externals.qps.make.make import compileResourceFile, compileQGISResourceFiles
from eotimeseriesviewer.utils import file_search



def compileResourceFiles():

    dir1 = os.path.join(DIR_REPO, 'eotimeseriesviewer')
    #dir2 = os.path.join(DIR_REPO, 'site-packages')

    qrcFiles = []
    for pathDir in [dir1]:
        qrcFiles += list(file_search(pathDir, '*.qrc', recursive=True))

    for file in qrcFiles:
        print('Compile {}...'.format(file))
        compileResourceFile(file)

def deleteCompiledResourceFiles():

    dir1 = os.path.join(DIR_REPO, 'eotimeseriesviewer')
    # dir2 = os.path.join(DIR_REPO, 'site-packages')

    qrcFiles = []
    for pathDir in [dir1]:
        qrcFiles += list(file_search(pathDir, '*.qrc', recursive=True))
    for p in qrcFiles:
        p2 = os.path.splitext(p)[0] + '.py'

        if os.path.isfile(p2):
            print('Remove {}'.format(p2))
            os.remove(p2)



if __name__ == '__main__':

    compileResourceFiles()
    print('Compiling finished')
    deleteCompiledResourceFiles()
    exit(0)