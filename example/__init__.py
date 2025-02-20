#!/usr/bin/env python
from pathlib import Path

thisDir = Path(__file__).parent
images = thisDir / 'Images'
# File path attributes:
# Vector files:
exampleGPKG = thisDir / r'exampleEvents.gpkg'
exampleEvents = exampleGPKG.as_posix() + '|layername=exampleEvents'
examplePoints = exampleGPKG.as_posix() + '|layername=pointsOfInterest'
exampleTimeSeries = thisDir / 'ExampleTimeSeries.csv'
exampleNoDataImage = thisDir / '20140108_no_data.tif'
exampleRapidEye = images / 're_2014-06-25.tif'
exampleLandsat8 = images / '2014-01-15_LC82270652014015LGN00_BOA.tif'

del thisDir, images
