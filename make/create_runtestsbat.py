import os, sys, pathlib, re
from eotimeseriesviewer import DIR_REPO

DIR_REPO = pathlib.Path(DIR_REPO)
DIR_TESTS = DIR_REPO / 'tests'

assert os.path.isdir(DIR_TESTS)

PATH_RUNTESTS_BAT = DIR_REPO / 'runtests.bat'
PATH_RUNTESTS_SH = DIR_REPO / 'runtests.sh'

jUnitXML = r'nose2-junit.xml'

PREFACE_BAT = \
"""
:: use this script to run unit tests locally
::
set CI=True
python3 make/setuprepository.py
"""

PREFACE_SH = \
"""
#!/bin/bash
# use this script to run unit tests locally
#
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI
          
python3 make/setuprepository.py
"""

dirOut = 'test-reports/today'
linesBat = [PREFACE_BAT]
linesSh = [PREFACE_SH]
linesBat.append('mkdir {}'.format(dirOut.replace('/', '\\')))
linesSh.append('mkdir {}'.format(dirOut))


bnDirTests = os.path.basename(DIR_TESTS)
for file in os.scandir(DIR_TESTS):
    if file.is_file() and re.search(r'^test_.*\.py$', file.name):
        bn = os.path.basename(file)
        bn = os.path.splitext(bn)[0]
        lineBat = 'python3 -m nose2 -s {3} {0} & move {1} {2}/{0}.xml'.format(bn, jUnitXML, dirOut, bnDirTests)
        lineSh = 'python3 -m nose2 -s {3} {0} | mv {1} {2}/{0}.xml'.format(bn, jUnitXML, dirOut, bnDirTests)
        linesBat.append(lineBat)
        linesSh.append(lineSh)


with open(PATH_RUNTESTS_BAT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(linesBat))

with open(PATH_RUNTESTS_SH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(linesSh))

