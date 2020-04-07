
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

%PYTHON% -m coverage run --rcfile=.coveragec   tests/test_fileFormatLoading.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_inmemorydata.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_labeling.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_layerproperties.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_main.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_mapcanvas.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_maptools.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_mapvisualization.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_qgis_environment.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_qgis_interaction.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_resources.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_settings.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_stackedbandinput.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_temporalprofiles.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_timeseries.py
%PYTHON% -m coverage run --rcfile=.coveragec --append  tests/test_utils.py
%PYTHON% -m coverage report