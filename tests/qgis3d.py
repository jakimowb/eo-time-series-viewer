
from eotimeseriesviewer.tests import initQgisApplication

app = initQgisApplication()

from qgis._3d import *

engine = QgsWindow3DEngine()

w = engine.window()
w.show()

app.exec_()
app.quit()