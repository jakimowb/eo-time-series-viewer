import os
from osgeo import gdal
import numpy as np

directory = r'O:\ST19_MSc-EO\S08\data\ts_stacks'
pathCSV = os.path.join(directory, 'Landsat_2010_Sensor_Date.csv')

with open(pathCSV, 'r') as f:
    lines = f.readlines()
lines = lines[1:]

dates = []
sensors = []
for line in lines:
    dtg, sensor = line.split(';')
    dtg = '{}-{}-{}'.format(dtg[0:4], dtg[4:6], dtg[6:8])
    dates.append(dtg)
    sensors.append(sensor)

for name in ['TCB_stack.tif', 'TCG_stack.tif', 'TCW_stack.tif' ]:

    path = os.path.join(directory, name)
    assert os.path.isfile(path)

    ds = gdal.Open(path, gdal.GA_Update)
    assert isinstance(ds, gdal.Dataset)
    assert len(lines) == ds.RasterCount

    ds.SetMetadataItem('observation dates', ','.join(dates))

    for b in range(ds.RasterCount):
        band = ds.GetRasterBand(b+1)
        assert isinstance(band, gdal.Band)
        band.SetDescription(sensors[b])

    ds.FlushCache()
    ds = None

print('Done')


