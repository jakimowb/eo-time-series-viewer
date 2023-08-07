from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolBar
from qgis.core import QgsVectorLayer, QgsVectorLayerTools
from qgis.gui import QgsDockWidget
from eotimeseriesviewer.labeling import LabelWidget, gotoFeature
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibrarywidget import SpectralLibraryPanel, \
    SpectralLibraryWidget


class SpectralLibraryDockWidget(SpectralLibraryPanel):
    def __init__(self, speclib: QgsVectorLayer, *args, **kwds):
        super().__init__(*args, speclib=speclib, **kwds)
        assert isinstance(self.SLW, SpectralLibraryWidget)
        self.mActionNextFeature = QAction('Next Feature', parent=self)
        self.mActionNextFeature.setIcon(QIcon(':/images/themes/default/mActionAtlasNext.svg'))
        self.mActionNextFeature.triggered.connect(self.onGotoNextFeature)

        self.mActionPreviousFeature = QAction('Previous Feature', parent=self)
        self.mActionPreviousFeature.setIcon(QIcon(':/images/themes/default/mActionAtlasPrev.svg'))
        self.mActionPreviousFeature.triggered.connect(self.onGotoPreviousFeature)

        self.SLW.mToolbar: QToolBar
        self.SLW.mToolbar.insertActions(self.SLW.mActionToggleEditing,
                                        [self.mActionPreviousFeature, self.mActionNextFeature])
        self.SLW.mToolbar.insertSeparator(self.SLW.mActionToggleEditing)

    def onGotoNextFeature(self, *arg):
        gotoFeature(self.SLW, goDown=True)

    def onGotoPreviousFeature(self, *args):
        gotoFeature(self.SLW, goDown=False)

    def setVectorLayerTools(self, tools: QgsVectorLayerTools):
        self.SLW.setVectorLayerTools(tools)

    def spectralLibrary(self) -> QgsVectorLayer:
        return self.SLW.spectralLibrary()


class LabelDockWidget(QgsDockWidget):

    def __init__(self, layer, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mLabelWidget = LabelWidget(layer)
        self.setWidget(self.mLabelWidget)
        self.setWindowTitle(self.mLabelWidget.windowTitle())
        self.mLabelWidget.windowTitleChanged.connect(self.setWindowTitle)

    def setVectorLayerTools(self, tools: QgsVectorLayerTools):
        self.mLabelWidget.setVectorLayerTools(tools)

    def vectorLayer(self) -> QgsVectorLayer:
        if isinstance(self.mLabelWidget.mLayer, QgsVectorLayer):
            return self.mLabelWidget.mLayer
        return None
