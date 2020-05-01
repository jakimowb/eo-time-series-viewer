#!/usr/bin/env python
import sys
import os
import pathlib
thisDir = os.path.dirname(__file__)
# File path attributes:
# Vector files:
exampleGPKG = os.path.join(thisDir, r'exampleEvents.gpkg')
exampleEvents = exampleGPKG + '|layername=exampleEvents'
exampleTimeSeries = os.path.join(thisDir, 'ExampleTimeSeries.csv')
exampleNoDataImage = os.path.join(thisDir, '20140108_no_data.tif')