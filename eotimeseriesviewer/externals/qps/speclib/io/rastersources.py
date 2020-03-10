
import os, sys, re, pathlib, json, io, re, linecache, typing
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *
from qgis.PyQt import sip


from ..core import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, FIELD_FID, FIELD_VALUES, \
    FIELD_NAME, findTypeFromString, createQgsField, OGR_EXTENSION2DRIVER, ProgressHandler
from ...utils import SelectMapLayersDialog

class SpectralProfileLoadingTask(QgsTask):

    def __init__(self, path_vector, path_raster, all_touched=True):
        super().__init__('Load spectral profiles', QgsTask.CanCancel)
        assert isinstance(path_vector, str)
        assert isinstance(path_raster, str)

        self.path_vector = path_vector
        self.path_raster = path_raster
        self.all_toched = all_touched
        self.exception = None
        self.profiles = None
        from ..gui import ProgressHandler
        self.progress_handler = ProgressHandler()

    def run(self):

        self.progress_handler.progressChanged[int, int, int].connect(self.onProgressChanged)
        try:
            vector = QgsVectorLayer(self.path_vector)
            raster = QgsRasterLayer(self.path_raster)
            profiles = SpectralLibrary.readFromVector(vector,
                                                  raster,
                                                  all_touched=self.all_toched,
                                                  progressDialog=self.progress_handler,
                                                  returnProfileList=True)
            self.profiles = profiles
        except Exception as ex:
            self.exception = ex
            return False

        return True

    def onProgressChanged(self, vMin, vMax, vValue):
        if vValue <= 0:
            self.progressChanged.emit(0)
        else:
            self.progressChanged.emit(100. * vValue / (vMax - vMin))

    def cancel(self):
        self.progress_handler.cancel()
        super().cancel()

    def finished(self, result):
        if result == True:
            s = ""
        elif result == False:

            if isinstance(self.exception, Exception):
                print(self.exception, file=sys.stderr)
            else:
                s = ""
        pass


class SpectralProfileImportPointsDialog(SelectMapLayersDialog):

    def __init__(self, parent=None, f:Qt.WindowFlags=None):
        super(SpectralProfileImportPointsDialog, self).__init__()

        self.setWindowTitle('Read Spectral Profiles')
        self.addLayerDescription('Raster Layer', QgsMapLayerProxyModel.RasterLayer)
        cb = self.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        cb.layerChanged.connect(self.onVectorLayerChanged)

        self.mProfiles = []

        self.mCbTouched = QCheckBox(self)
        self.mCbTouched.setText('All touched')
        self.mCbTouched.setToolTip('Activate to extract all touched pixels, not only thoose entirel covered by a geometry.')
        i = self.mGrid.rowCount()
        self.mGrid.addWidget(self.mCbTouched, i, 1)

        self.mProgressBar = QProgressBar(self)
        self.mProgressBar.setRange(0, 100)
        self.mGrid.addWidget(self.mProgressBar, self.mGrid.rowCount(), 0, 1, self.mGrid.columnCount())
        self.buttonBox().button(QDialogButtonBox.Ok).clicked.disconnect()
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.disconnect()
        self.buttonBox().button(QDialogButtonBox.Ok).clicked.connect(self.run)
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.connect(self.onCancel)

        self.onVectorLayerChanged(cb.currentLayer())

        self.mTasks = dict()
        self.mIsFinished = False

    def onCancel(self):
        for t in self.mTasks.items():
            if isinstance(t, QgsTask) and t.canCancel():
                t.cancel()
        self.mIsFinished = True
        self.reject()

    def onVectorLayerChanged(self, layer:QgsVectorLayer):
        self.mCbTouched.setEnabled(isinstance(layer, QgsVectorLayer) and
                                   QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry)

    def profiles(self)->typing.List[SpectralProfile]:
        return self.mProfiles[:]

    def speclib(self)->SpectralLibrary:
        slib = SpectralLibrary()
        slib.startEditing()
        if len(self.mProfiles) > 0:
            slib.addMissingFields(self.mProfiles[0].fields())

        slib.addProfiles(self.mProfiles, addMissingFields=False)
        slib.commitChanges()
        return slib

    def setRasterSource(self, lyr):
        if isinstance(lyr, str):
            lyr = QgsRasterLayer(lyr)
        assert isinstance(lyr, QgsRasterLayer)
        self.selectMapLayer(0, lyr)

    def setVectorSource(self, lyr):
        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr)
        assert isinstance(lyr, QgsVectorLayer)
        self.selectMapLayer(1, lyr)

    def onProgressChanged(self, progress):
        self.mProgressBar.setValue(int(progress))

    def onCompleted(self, task:SpectralProfileLoadingTask):
        if isinstance(task, SpectralProfileLoadingTask) and not sip.isdeleted(task):
            self.mProfiles = task.profiles[:]
            self.mTasks.clear()
            self.setResult(QDialog.Accepted)
            self.mIsFinished = True
            self.accept()

    def isFinished(self)->bool:
        return self.mIsFinished


    def onTerminated(self, *args):
        s  =""
        self.setResult(QDialog.Rejected)
        self.mIsFinished = True
        self.reject()

    def run(self):

        task = SpectralProfileLoadingTask(self.vectorSource().source(), self.rasterSource().source(),
                                          all_touched=self.allTouched())

        mgr = QgsApplication.taskManager()
        assert isinstance(mgr, QgsTaskManager)
        id = mgr.addTask(task)
        self.mTasks[id] = task
        task.progressChanged.connect(self.onProgressChanged)
        task.taskCompleted.connect(lambda task=task: self.onCompleted(task))
        task.taskTerminated.connect(lambda task=task: self.onTerminated(task))

        QgsApplication.taskManager().addTask(task)


    def allTouched(self)->bool:
        return self.mCbTouched.isEnabled() and self.mCbTouched.isChecked()

    def rasterSource(self)->QgsVectorLayer:
        return self.mapLayers()[0]

    def vectorSource(self)->QgsVectorLayer:
        return self.mapLayers()[1]
