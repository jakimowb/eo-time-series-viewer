

import sys

from qgis.core import QgsProject

try:
    from .classification_resources import qInitResources
    qInitResources()
except Exception as ex:
    print('failed to initialize classification.classification_resources')

MAP_LAYER_STORES = set([QgsProject.instance()])