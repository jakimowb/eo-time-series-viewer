#!/bin/bash

export QT_QPA_PLATFORM=offscreen
export CI=True
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
pytest --no-cov-on-fail --cov-config=.coveragec "$@"
coverage-badge -o coverage.svg -f -v
