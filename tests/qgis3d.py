
from eotimeseriesviewer.tests import start_app

app = start_app()

from qgis._3d import *

engine = QgsWindow3DEngine()

w = engine.window()
w.show()

app.exec_()
app.quit()