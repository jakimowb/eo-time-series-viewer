#!/usr/bin/env python
from pathlib import Path

thisDir = Path(__file__).parent
images = thisDir / 'Images'
# File path attributes:
# Vector files:
examplePoints = thisDir / 'example_points.geojson'
exampleTimeSeries = thisDir / 'ExampleTimeSeries.csv'
exampleNoDataImage = thisDir / '20140108_no_data.tif'
exampleRapidEye = images / 're_2014-06-25.tif'
exampleLandsat8 = images / '2014-01-15_LC82270652014015LGN00_BOA.tif'

del thisDir, images
