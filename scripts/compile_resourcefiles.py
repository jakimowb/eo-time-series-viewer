# -*- coding: utf-8 -*-

import os, sys, fnmatch, six, subprocess, re

ROOT = os.path.dirname(os.path.dirname(__file__))

from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.externals.qps.resources import compileResourceFiles
from eotimeseriesviewer.utils import file_search



def compileEOTSVResourceFiles():

    dir1 = os.path.join(DIR_REPO, 'eotimeseriesviewer')
    #dir2 = os.path.join(DIR_REPO, 'site-packages')
    compileResourceFiles(dir1)


if __name__ == '__main__':

    compileEOTSVResourceFiles()
    print('Compiling finished')
    exit(0)

    exit(0)