#!/bin/bash

REPO_ROOT=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )/..
cd $REPO_ROOT

export PYTHONPATH="${PYTHONPATH}"\
":$(pwd)"\
":/usr/share/qgis/python/plugins"

cd $REPO_ROOT
pwd
echo "Run flake8 in $(pwd) ..."
python3 -m flake8 "$@"
echo "Done"