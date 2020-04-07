#!/bin/bash
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI

find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# python3 scripts/setup_repository.py

python3 -m coverage run --rcfile=.coveragec   tests/test_fileFormatLoading.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_inmemorydata.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_labeling.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_layerproperties.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_main.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_mapcanvas.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_maptools.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_mapvisualization.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_qgis_environment.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_qgis_interaction.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_resources.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_settings.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_stackedbandinput.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_temporalprofiles.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_timeseries.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_utils.py
python3 -m coverage report