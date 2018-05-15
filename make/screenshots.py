

#

from timeseriesviewer.utils import *
from timeseriesviewer.main import TimeSeriesViewer
from timeseriesviewer import DIR_REPO, DIR_QGIS_RESOURCES
DIR_SCREENSHOTS = jp(DIR_REPO, 'screenshots')
os.makedirs(DIR_SCREENSHOTS, exist_ok=True)

app = initQgisApplication(qgisResourceDir=DIR_QGIS_RESOURCES)

TS = TimeSeriesViewer(None)
TS.show()
TS.loadExampleTimeSeries()






app.exec_()

