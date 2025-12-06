#!/bin/bash


export CI=True
export PYQTGRAPH_QT_LIB=PyQt5
export QT_QPA_PLATFORM=offscreen
# export QT_DEBUG_PLUGINS=True
# export QT_FATAL_WARNINGS=True
export QGIS_CONTINUOUS_INTEGRATION_RUN=true

REPO_ROOT=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )/..
cd $REPO_ROOT

export PYTHONPATH="${PYTHONPATH}"\
":$(pwd)"\
":/usr/share/qgis/python/plugins"

cd $REPO_ROOT
pwd
rm -Rf test-outputs
rm -Rf test-reports
echo "Run pytest in $(pwd)"
# not working seeds:
# python -X faulthandler -m pytest -p no:faulthandler --random-order-seed=397945 --no-cov-on-fail --cov-config=.coveragec "$@"
python3 -m pytest --no-cov-on-fail "$@"
# gdb --args python -m pytest  --no-cov-on-fail --cov-config=.coveragec "$@"
## in gbd -> run
#     run
#     bt to show stacktrace after error
# coverage-badge -o coverage.svg -f -v
