from typing import List, Optional

from eotimeseriesviewer.labeling.attributetable import QuickLabelAttributeTableWidget
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qgis.core import QgsVectorLayer, QgsVectorLayerTools, QgsProject
from qgis.gui import QgsDockWidget


class SpectralLibraryDockWidget(QgsDockWidget):
    def __init__(self, *args,
                 speclib: Optional[QgsVectorLayer] = None,
                 project: Optional[QgsProject] = None,
                 **kwds):
        super().__init__(*args, **kwds)

        self.SLW = SpectralLibraryWidget(speclib=speclib, project=project, parent=self)
        self.setWidget(self.SLW)
        self.setWindowTitle(self.SLW.windowTitle())
        self.SLW.windowTitleChanged.connect(self.setWindowTitle)

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        return self.SLW.spectralLibraries()

    def close(self):
        m = self.SLW.plotModel()
        vis = m.visualizations()
        m.removePropertyItemGroups(vis)
        super().close()


class LabelDockWidget(QgsDockWidget):

    def __init__(self, layer, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mLabelWidget = QuickLabelAttributeTableWidget(layer)
        self.setWidget(self.mLabelWidget)
        self.setWindowTitle(self.mLabelWidget.windowTitle())
        self.mLabelWidget.windowTitleChanged.connect(self.setWindowTitle)

    def setVectorLayerTools(self, tools: QgsVectorLayerTools):
        self.mLabelWidget.setVectorLayerTools(tools)

    def vectorLayer(self) -> Optional[QgsVectorLayer]:
        if isinstance(self.mLabelWidget.mLayer, QgsVectorLayer):
            return self.mLabelWidget.mLayer
        return None
