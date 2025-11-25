#!/usr/bin/env bash
#***************************************************************************
#***************************************************************************
#
#***************************************************************************
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU General Public License as published by  *
#*   the Free Software Foundation; either version 2 of the License, or     *
#*   (at your option) any later version.                                   *
#*                                                                         *
#***************************************************************************

set -e

# pushd /usr/src
# DEFAULT_PARAMS='-x -v'
# cd /usr/src
# REPO_ROOT=$(readlink -f "$0")

REPO_ROOT="$(realpath "$(dirname -- "${BASH_SOURCE[0]}")/..")"
echo $REPO_ROOT
# echo $SCRIPT_DIR

export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python3 $REPO_ROOT/scripts/setup_repository.py -r
python3 $REPO_ROOT/scripts/systeminfo.py
source $REPO_ROOT/scripts/runtests.sh "$@"
#popd