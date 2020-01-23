
:: use this script to run unit tests locally
::
set CI=True
python3 make/setuprepository.py

mkdir test-reports\today
python -m nose2 -s tests test_fileFormatLoading #& move nose2-junit.xml test-reports/today/test_fileFormatLoading.xml
python -m nose2 -s tests test_inmemorydata #& move nose2-junit.xml test-reports/today/test_inmemorydata.xml
python -m nose2 -s tests test_labeling #& move nose2-junit.xml test-reports/today/test_labeling.xml
python -m nose2 -s tests test_layerproperties #& move nose2-junit.xml test-reports/today/test_layerproperties.xml
python -m nose2 -s tests test_main #& move nose2-junit.xml test-reports/today/test_main.xml
python -m nose2 -s tests test_mapcanvas #& move nose2-junit.xml test-reports/today/test_mapcanvas.xml
python -m nose2 -s tests test_maptools #& move nose2-junit.xml test-reports/today/test_maptools.xml
python -m nose2 -s tests test_mapvisualization #& move nose2-junit.xml test-reports/today/test_mapvisualization.xml
python -m nose2 -s tests test_qgis_environment #& move nose2-junit.xml test-reports/today/test_qgis_environment.xml
python -m nose2 -s tests test_qgis_interaction #& move nose2-junit.xml test-reports/today/test_qgis_interaction.xml
python -m nose2 -s tests test_resources #& move nose2-junit.xml test-reports/today/test_resources.xml
python -m nose2 -s tests test_settings #& move nose2-junit.xml test-reports/today/test_settings.xml
python -m nose2 -s tests test_stackedbandinput #& move nose2-junit.xml test-reports/today/test_stackedbandinput.xml
python -m nose2 -s tests test_temporalprofiles #& move nose2-junit.xml test-reports/today/test_temporalprofiles.xml
python -m nose2 -s tests test_timeseries #& move nose2-junit.xml test-reports/today/test_timeseries.xml
python -m nose2 -s tests test_utils #& move nose2-junit.xml test-reports/today/test_utils.xml