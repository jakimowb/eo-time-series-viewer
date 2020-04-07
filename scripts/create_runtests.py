import os
import sys
import pathlib
import re
from eotimeseriesviewer.utils import file_search
from eotimeseriesviewer import DIR_REPO
def create_runtests():

    DIR_SCRIPTS = pathlib.Path(__file__).resolve().parent

    TEST_DIRECTORIES = [
        DIR_REPO / 'tests'
    ]

    assert DIR_REPO.is_dir()
    assert (DIR_REPO / '.git').is_dir()

    PATH_RUNTESTS_BAT = DIR_SCRIPTS / 'runtests.bat'
    PATH_RUNTESTS_SH = DIR_SCRIPTS / 'runtests.sh'
    PATH_YAML = DIR_REPO / 'bitbucket-pipelines.yml'

    PREFACE_BAT = \
"""
:: use this script to run unit tests locally
::
@echo off
set CI=True

WHERE python3 >nul 2>&1 && (
    echo Found "python3" command
    set PYTHON=python3
) || (
    echo Did not found "python3" command. use "python" instead
    set PYTHON=python
)

::start %PYTHON% scripts/setup_repository.py
"""

    PREFACE_SH = \
"""#!/bin/bash
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI

find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# python3 scripts/setup_repository.py
"""


    #dirOut = 'test-reports/today'
    linesBat = [PREFACE_BAT]
    linesSh = [PREFACE_SH]
    linesYAML = []
    #linesBat.append('mkdir {}'.format(dirOut.replace('/', '\\')))
    #linesSh.append('mkdir {}'.format(dirOut))

    n = 0
    for DIR_TESTS in TEST_DIRECTORIES:
        for i, file in enumerate(file_search(DIR_TESTS, 'test_*.py')):
            file = pathlib.Path(file)
            do_append = '' if n == 0 else '--append'
            pathTest = file.relative_to(DIR_REPO).as_posix()
            lineBat = '%PYTHON% -m coverage run --rcfile=.coveragec {}  {}'.format(do_append, pathTest)
            lineSh = 'python3 -m coverage run --rcfile=.coveragec {}  {}'.format(do_append, pathTest)
            linesBat.append(lineBat)
            linesSh.append(lineSh)
            linesYAML.append(lineSh)
            n += 1

    linesBat.append('%PYTHON% -m coverage report')
    linesSh.append('python3 -m coverage report')
    linesYAML.append('python3 -m coverage report')

    print('Write {}...'.format(PATH_RUNTESTS_BAT))
    with open(PATH_RUNTESTS_BAT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linesBat))

    print('Write {}...'.format(PATH_RUNTESTS_SH))
    with open(PATH_RUNTESTS_SH, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(linesSh))

    yamlLines = ['- {}\n'.format(l) for l in linesYAML]
    print(''.join(yamlLines))


if __name__ == "__main__":
    create_runtests()
    exit(0)