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
REPO_ROOT=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )/..
cd $REPO_ROOT

# cd $REPO_ROOT
pwd

# REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)
# echo $REPO_ROOT

export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python3 scripts/setup_repository.py -r
source scripts/runtests.sh "$@"
#popd