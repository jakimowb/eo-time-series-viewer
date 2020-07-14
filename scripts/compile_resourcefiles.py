# -*- coding: utf-8 -*-

import os
import pathlib
import site
site.addsitedir(pathlib.Path(__file__).parents[1])

from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.externals.qps.resources import compileResourceFiles


def compileEOTSVResourceFiles():

    dir1 = os.path.join(DIR_REPO, 'eotimeseriesviewer')
    #dir2 = os.path.join(DIR_REPO, 'site-packages')
    compileResourceFiles(dir1)


if __name__ == '__main__':

    compileEOTSVResourceFiles()
    print('Compiling finished')
    exit(0)
