
:: use this script to run unit tests locally
::
set CI=True
python3 make/setuprepository.py

mkdir test-reports\today
python3 -m nose2 -s tests test_fileFormatLoading & move nose2-junit.xml test-reports/today/test_fileFormatLoading.xml
python3 -m nose2 -s tests test_init & move nose2-junit.xml test-reports/today/test_init.xml
python3 -m nose2 -s tests test_inmemorydata & move nose2-junit.xml test-reports/today/test_inmemorydata.xml
python3 -m nose2 -s tests test_labeling & move nose2-junit.xml test-reports/today/test_labeling.xml
python3 -m nose2 -s tests test_layerproperties & move nose2-junit.xml test-reports/today/test_layerproperties.xml
python3 -m nose2 -s tests test_main & move nose2-junit.xml test-reports/today/test_main.xml
python3 -m nose2 -s tests test_mapcanvas & move nose2-junit.xml test-reports/today/test_mapcanvas.xml
python3 -m nose2 -s tests test_maptools & move nose2-junit.xml test-reports/today/test_maptools.xml
python3 -m nose2 -s tests test_mapvisualization & move nose2-junit.xml test-reports/today/test_mapvisualization.xml
python3 -m nose2 -s tests test_qgis_environment & move nose2-junit.xml test-reports/today/test_qgis_environment.xml
python3 -m nose2 -s tests test_qgis_interaction & move nose2-junit.xml test-reports/today/test_qgis_interaction.xml
python3 -m nose2 -s tests test_resources & move nose2-junit.xml test-reports/today/test_resources.xml
python3 -m nose2 -s tests test_sensorvisualization & move nose2-junit.xml test-reports/today/test_sensorvisualization.xml
python3 -m nose2 -s tests test_settings & move nose2-junit.xml test-reports/today/test_settings.xml
python3 -m nose2 -s tests test_stackedbandinput & move nose2-junit.xml test-reports/today/test_stackedbandinput.xml
python3 -m nose2 -s tests test_temporalprofiles & move nose2-junit.xml test-reports/today/test_temporalprofiles.xml
python3 -m nose2 -s tests test_timeseries & move nose2-junit.xml test-reports/today/test_timeseries.xml
python3 -m nose2 -s tests test_utils & move nose2-junit.xml test-reports/today/test_utils.xml