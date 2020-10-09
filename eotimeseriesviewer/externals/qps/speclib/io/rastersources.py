# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/rastersources.py


    ---------------------
    Beginning            : 2018-12-17
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import os
import sys
import typing
from osgeo import gdal
import numpy as np
from qgis.PyQt import sip
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.core import QgsTask, QgsMapLayer, QgsVectorLayer, QgsRasterLayer, QgsWkbTypes, \
    QgsTaskManager, QgsMapLayerProxyModel, QgsApplication, QgsFileUtils
from ..core import SpectralProfile, SpectralLibrary, AbstractSpectralLibraryIO, ProgressHandler
from ...utils import SelectMapLayersDialog, gdalDataset, parseWavelength, parseFWHM, parseBadBandList

PIXEL_LIMIT = 100*100

class SpectralProfileLoadingTask(QgsTask):

    def __init__(self, path_vector: str, path_raster: str, all_touched: bool = True, copy_attributes: bool = False):
        super().__init__('Load spectral profiles', QgsTask.CanCancel)
        assert isinstance(path_vector, str)
        assert isinstance(path_raster, str)

        self.path_vector = path_vector
        self.path_raster = path_raster
        self.all_touched = all_touched
        self.copy_attributes = copy_attributes
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
                                                      all_touched=self.all_touched,
                                                      copy_attributes=self.copy_attributes,
                                                      progress_handler=self.progress_handler,
                                                      return_profile_list=True)
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

    def __init__(self, parent=None, f: Qt.WindowFlags = None):
        super(SpectralProfileImportPointsDialog, self).__init__()

        self.setWindowTitle('Read Spectral Profiles')
        self.addLayerDescription('Raster Layer', QgsMapLayerProxyModel.RasterLayer)
        cb = self.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        cb.layerChanged.connect(self.onVectorLayerChanged)

        self.mProfiles = []

        self.mCbTouched = QCheckBox(self)
        self.mCbTouched.setText('All touched')
        self.mCbTouched.setToolTip(
            'Activate to extract all touched pixels, not only those entirely covered by a geometry.')

        self.mCbAllAttributes = QCheckBox(self)
        self.mCbAllAttributes.setText('Copy Attributes')
        self.mCbAllAttributes.setToolTip(
            'Activate to copy vector attributes into the Spectral Library'
        )

        l = QHBoxLayout()
        l.addWidget(self.mCbTouched)
        l.addWidget(self.mCbAllAttributes)
        i = self.mGrid.rowCount()
        self.mGrid.addLayout(l, i, 1)

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

    def onVectorLayerChanged(self, layer: QgsVectorLayer):
        self.mCbTouched.setEnabled(isinstance(layer, QgsVectorLayer) and
                                   QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry)

    def profiles(self) -> typing.List[SpectralProfile]:
        return self.mProfiles[:]

    def speclib(self) -> SpectralLibrary:
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

    def onCompleted(self, task: SpectralProfileLoadingTask):
        if isinstance(task, SpectralProfileLoadingTask) and not sip.isdeleted(task):
            self.mProfiles = task.profiles[:]
            self.mTasks.clear()
            self.setResult(QDialog.Accepted)
            self.mIsFinished = True
            self.accept()

    def isFinished(self) -> bool:
        return self.mIsFinished

    def onTerminated(self, *args):
        s = ""
        self.setResult(QDialog.Rejected)
        self.mIsFinished = True
        self.reject()

    def run(self):
        """
        Call this to start loading the profiles in a background process
        """
        task = SpectralProfileLoadingTask(self.vectorSource().source(),
                                          self.rasterSource().source(),
                                          all_touched=self.allTouched(),
                                          copy_attributes=self.allAttributes()
                                          )

        mgr = QgsApplication.taskManager()
        assert isinstance(mgr, QgsTaskManager)
        id = mgr.addTask(task)
        self.mTasks[id] = task
        task.progressChanged.connect(self.onProgressChanged)
        task.taskCompleted.connect(lambda task=task: self.onCompleted(task))
        task.taskTerminated.connect(lambda task=task: self.onTerminated(task))

        QgsApplication.taskManager().addTask(task)

    def allAttributes(self) -> bool:
        """
        Returns True if the "All Attributes" combo box is enabled and checked.
        :return: bool
        """
        return self.mCbAllAttributes.isEnabled() and self.mCbAllAttributes.isChecked()

    def allTouched(self) -> bool:
        """
        Returns True if the "All Touched" combo box is enabled and checked.
        :return: bool
        """
        return self.mCbTouched.isEnabled() and self.mCbTouched.isChecked()

    def rasterSource(self) -> QgsRasterLayer:
        """
        Returns the selected QgsRasterLayer
        :return: QgsRasterLayer
        """
        return self.mapLayers()[0]

    def vectorSource(self) -> QgsVectorLayer:
        """
        Returns the selected QgsVectorLayer
        :return: QgsVectorLayer
        """
        return self.mapLayers()[1]


class RasterSourceSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for Raster files.
    """

    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        path = str(path)
        try:
            ds = gdalDataset(path)
            return True
        except:
            return False
        return False

    @classmethod
    def readFrom(cls, path,
                 progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None,
                 addAttributes: bool = True) -> SpectralLibrary:

        ds: gdal.Dataset = gdalDataset(path)
        if not isinstance(ds, gdal.Dataset):
            return None

        speclib = SpectralLibrary()
        assert isinstance(speclib, SpectralLibrary)
        sourcepath = ds.GetDescription()
        basename = os.path.basename(ds.GetDescription())
        speclib.setName(basename)
        assert speclib.startEditing()

        wl, wlu = parseWavelength(ds)
        fwhm = parseFWHM(ds)
        bbl = parseBadBandList(ds)

        # each none-masked pixel is a profile
        array = ds.ReadAsArray()

        ref_band: gdal.Band = ds.GetRasterBand(1)
        no_data = ref_band.GetNoDataValue()
        valid = np.isfinite(array[0, :])
        if no_data:
            valid = valid * (array[0, :] != no_data)
        valid = np.where(valid)

        n_profiles = len(valid[0])
        if n_profiles > PIXEL_LIMIT:
            raise Exception(f'Number of raster image pixels {n_profiles} exceeds PIXEL_LIMIT {PIXEL_LIMIT}')

        if wl is not None:
            xvalues = wl.tolist()
        else:
            xvalues = (np.arange(ds.RasterCount) + 1).tolist()

        profiles = []
        for y, x in zip(*valid):
            yvalues = array[:, y, x]
            p = SpectralProfile(fields=speclib.fields())
            p.setName(f'Profile {x},{y}')
            p.setSource(basename)
            p.setValues(xvalues, yvalues, xUnit=wlu)
            profiles.append(p)
        speclib.addProfiles(profiles)
        speclib.commitChanges()
        return speclib

    @classmethod
    def write(cls, speclib: SpectralLibrary,
              path: str,
              progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None):
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
        """
        speclib.writeRasterImages(path)

        return [path]

    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='Raster Image',
                                                       filter='All types (*.*)')
            if os.path.isfile(path):

                if not RasterSourceSpectralLibraryIO.canRead(path):
                    QMessageBox.critical(None, 'Raster image as SpectralLibrary', f'Unable to reads {path}')

                try:
                    sl = RasterSourceSpectralLibraryIO.readFrom(path)
                    if isinstance(sl, SpectralLibrary):
                        speclib.startEditing()
                        speclib.beginEditCommand('Add Spectral Library from {}'.format(path))
                        speclib.addSpeclib(sl, addMissingFields=True)
                        speclib.endEditCommand()
                        speclib.commitChanges()
                except Exception as ex:
                    QMessageBox.critical(None, 'Raster image as SpectralLibrary', str(ex))
                    return
        m = menu.addAction('Raster Image')
        m.setToolTip('Import all pixels as spectral profiles which are not masked. '
                     'Use careful and not with large images!')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))

    @classmethod
    def addExportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def write(speclib: SpectralLibrary):
            # https://gdal.org/drivers/vector/index.html
            LUT_Files = {'GeoTiff (*.tif)': 'GTiff',
                         'ENVI Raster (*.bsq)': 'ENVI',
                        }

            path, filter = QFileDialog.getSaveFileName(caption='Write as raster image',
                                                       filter=';;'.join(LUT_Files.keys()),
                                                       directory=QgsFileUtils.stringToSafeFilename(speclib.name()))
            if isinstance(path, str) and len(path) > 0:
                speclib.writeRasterImages(path, drv=LUT_Files.get(filter, 'GTiff'))

        a = menu.addAction('Raster Image')
        a.setToolTip('Write profiles as raster image(s), grouped by wavelengths.')
        a.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))
