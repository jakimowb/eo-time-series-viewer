#!/bin/bash
# use this script to run unit tests locally
#
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI
          
python3 make/setuprepository.py

mkdir test-reports/today
python3 -m nose2 -s tests test_dummy #| mv nose2-junit.xml test-reports/today/test_dummy.xml
python3 -m nose2 -s tests test_fileFormatLoading #| mv nose2-junit.xml test-reports/today/test_fileFormatLoading.xml
python3 -m nose2 -s tests test_init #| mv nose2-junit.xml test-reports/today/test_init.xml
python3 -m nose2 -s tests test_inmemorydata #| mv nose2-junit.xml test-reports/today/test_inmemorydata.xml
python3 -m nose2 -s tests test_labeling #| mv nose2-junit.xml test-reports/today/test_labeling.xml
python3 -m nose2 -s tests test_layerproperties #| mv nose2-junit.xml test-reports/today/test_layerproperties.xml
python3 -m nose2 -s tests test_main #| mv nose2-junit.xml test-reports/today/test_main.xml
python3 -m nose2 -s tests test_mapcanvas #| mv nose2-junit.xml test-reports/today/test_mapcanvas.xml
python3 -m nose2 -s tests test_maptools #| mv nose2-junit.xml test-reports/today/test_maptools.xml
python3 -m nose2 -s tests test_mapvisualization #| mv nose2-junit.xml test-reports/today/test_mapvisualization.xml
python3 -m nose2 -s tests test_qgis_environment #| mv nose2-junit.xml test-reports/today/test_qgis_environment.xml
python3 -m nose2 -s tests test_qgis_interaction #| mv nose2-junit.xml test-reports/today/test_qgis_interaction.xml
python3 -m nose2 -s tests test_resources #| mv nose2-junit.xml test-reports/today/test_resources.xml
python3 -m nose2 -s tests test_sensorvisualization #| mv nose2-junit.xml test-reports/today/test_sensorvisualization.xml
python3 -m nose2 -s tests test_settings #| mv nose2-junit.xml test-reports/today/test_settings.xml
python3 -m nose2 -s tests test_stackedbandinput #| mv nose2-junit.xml test-reports/today/test_stackedbandinput.xml
python3 -m nose2 -s tests test_temporalprofiles #| mv nose2-junit.xml test-reports/today/test_temporalprofiles.xml
python3 -m nose2 -s tests test_timeseries #| mv nose2-junit.xml test-reports/today/test_timeseries.xml
python3 -m nose2 -s tests test_utils #| mv nose2-junit.xml test-reports/today/test_utils.xml