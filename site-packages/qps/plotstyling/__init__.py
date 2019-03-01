

#see https://github.com/pyqtgraph/pyqtgraph/issues/774
WORKAROUND_PYTGRAPH_ISSUE_774 = True
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QGraphicsItem

#from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
#go = GraphicsObject()
#go.itemChange(QGraphicsItem.ItemSceneChange, QVariant(None))

import qgis.PyQt.QtGui
if WORKAROUND_PYTGRAPH_ISSUE_774:
    from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
    from PyQt5.QtCore import QVariant
    untouched = GraphicsObject.itemChange
    def newFunc(cls, change, value):
        return untouched(cls, change, value if value != QVariant(None) else None)
    GraphicsObject.itemChange = newFunc

