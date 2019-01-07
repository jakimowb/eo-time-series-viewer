
import numpy as np
import time

from timeseriesviewer.main import TimeSeriesViewer
from timeseriesviewer.utils import file_search
pathSrc = r''
files = file_search(pathSrc, recursive=True, '*BOA.bsq')


t_start = time.time()
EOTSV = TimeSeriesViewer()
EOTSV.show()
t_start = time.time() - t_start
print('Start & show EOTSV: {}'.format(t_start))

t_addImages = time.time()
EOTSV.addTimeSeriesImages()
t_addImages = time.time() - t_addImages()
print('Add {} images: {}'.format(len(files), t_start))

EOTSV.spatialTemporalVis.setMapSize(QSize(200,200))
t_load200px = time.time()
EOTSV.spatialTemporalVis.timedCanvasRefresh()
t_load200px = time.time() - t_load200px




