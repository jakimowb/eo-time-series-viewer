import datetime
import os.path
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from PyQt5.QtCore import QDate
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel
from qgis.core import QgsApplication, QgsTask
from qgis.gui import QgsFileWidget

from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.models import Option, OptionListModel
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, loadUi
from eotimeseriesviewer.tasks import EOTSVTask

FORCE_PRODUCTS = {
    'BOA': (r'.*_BOA\.(vrt|tif|dat|hdr)$', 'Bottom of Atmosphere (BOA)'),
    'TOA': (r'.*_TOA\.(vrt|tif|dat|hdr)$', 'Top-of-Atmosphere Reflectance (TOA)'),
    'QAI': (r'.*_QAI\.(vrt|tif|dat|hdr)$', 'Quality Assurance Information (QAI)'),
    'AOD': (r'.*_AOD\.(vrt|tif|dat|hdr)$', 'Aerosol Optical Depth (AOD)'),
    'DST': (r'.*_DST\.(vrt|tif|dat|hdr)$', 'Cloud / Cloud shadow /Snow distance (DST)'),
    'WVP': (r'.*_WVP\.(vrt|tif|dat|hdr)$', 'Water vapor (WVP)'),
    'VZN': (r'.*_VZN\.(vrt|tif|dat|hdr)$', 'View zenith (VZN)'),
    'HOT': (r'.*_HOT\.(vrt|tif|dat|hdr)$', 'Haze Optimized Transformation (HOT)'),
}

rx_FORCE_TILEID = re.compile(r'(X\d+)_(Y\d+)', re.MULTILINE)
rx_FORCE_TILEFOLDER = re.compile(f'^{rx_FORCE_TILEID.pattern}$')
rx_FORCE_L2_Product = re.compile(
    r'(?P<date>\d{8})_LEVEL2_(?P<sensor>[^_. ]+)_(?P<product>[^_. ]+)\.(?P<ext>tif|bsq|bil|bip|cog|vrt)$')


def read_tileids(text: str) -> List[str]:
    """
    Reads all FORCE tile-ids out of a string
    :param text:
    :return:
    """
    tile_ids = set()

    for match in rx_FORCE_TILEID.finditer(text):
        x, y = match.groups()
        if len(x) == len(y):
            tile_ids.add(match.group())
    return sorted(tile_ids)


def find_tile_folders(root: Union[str, Path]) -> List[Path]:
    root = Path(root)
    if rx_FORCE_TILEFOLDER.match(root.name):
        return root
    else:
        folders = []
        for f in file_search(root, rx_FORCE_TILEFOLDER, directories=True):
            folders.append(Path(f))

        return folders


class FindFORCEProductsTask(EOTSVTask):
    taskInfo = pyqtSignal(str)

    def __init__(self,
                 product: str, path,
                 *args,
                 tile_ids: List[str] = None,
                 dateMin: Optional[QDate] = None,
                 dateMax: Optional[QDate] = None,
                 **kwds):
        super().__init__(
            *args,
            flags=QgsTask.Silent | QgsTask.CanCancel | QgsTask.CancelWithoutPrompt,
            **kwds)

        self.mTileIDs: List[str] = tile_ids if tile_ids else []

        for tile_id in self.mTileIDs:
            assert rx_FORCE_TILEID.match(tile_id), f'Not a force tile_id: {tile_id}'

        assert product in FORCE_PRODUCTS.keys(), f'Unknown FORCE product: {product}'
        path = Path(path)
        assert path.is_dir()

        self.mProduct = product
        self.mPath = path
        self.mDateMin = dateMin
        self.mDateMax = dateMax
        self.mRxProduct = re.compile(FORCE_PRODUCTS[product][0])
        self.setDescription(f'Search {self.mProduct} in "../{self.mPath.name}"')
        self.mFiles: List[Path] = []
        self.mFileTiles: Set[str] = set()

    def searchId(self) -> str:
        return f'{self.mProduct}:{self.mPath}:{self.mTileIDs}:{self.mDateMin}:{self.mDateMax}'

    def canCancel(self) -> bool:
        return True

    def files(self) -> List[Path]:
        return self.mFiles

    def run(self):

        self.taskInfo.emit(f'Search for {self.mProduct} files...')

        tile_folders = []

        filter_tiles = len(self.mTileIDs) > 0
        if self.mPath.name == 'mosaic':
            tile_folders.append(self.mPath)
        else:
            for folder in find_tile_folders(self.mPath):

                if filter_tiles:
                    if folder.name in self.mTileIDs:
                        tile_folders.append(folder)
                else:
                    tile_folders.append(folder)

        if self.isCanceled():
            return False

        t0 = datetime.datetime.now()

        def info_check(progress: float = None):
            nonlocal t0
            t1 = datetime.datetime.now()
            dt = t1 - t0
            if dt.seconds > 1:
                t0 = t1
                self.taskInfo.emit(self.infoMessage() + '...')
                if progress:
                    self.setProgress(progress)

        n_folders = len(tile_folders) + 10
        for i_folder, folder in enumerate(tile_folders):

            for i, file in enumerate(file_search(folder, self.mRxProduct, recursive=False)):
                file = Path(file)

                if isinstance(self.mDateMin, QDate) or isinstance(self.mDateMax, QDate):
                    match = rx_FORCE_L2_Product.match(file.name)
                    if not match:
                        continue

                    image_date = QDate.fromString(match.group('date'), 'yyyyMMdd')
                    if self.mDateMin and image_date < self.mDateMin:
                        continue
                    if self.mDateMax and image_date > self.mDateMax:
                        continue

                if rx_FORCE_TILEFOLDER.match(file.parent.name) and file.parent.name not in self.mFileTiles:
                    self.mFileTiles.add(file.parent.name)

                self.mFiles.append(file)
                if i % 100:
                    if self.isCanceled():
                        return False
                    info_check(progress=100 * i_folder / n_folders)

        self.setProgress(100.0)
        self.taskInfo.emit(self.infoMessage() + '.')
        return True

    def infoMessage(self) -> str:
        msg = f'Found {len(self.mFiles)} "{self.mProduct}" files'
        n = len(self.mFileTiles)
        if n > 0:
            msg += f' in {n} tiles'
        return msg


class FORCEProductImportDialog(QDialog):
    # list force output files according to
    # https://force-eo.readthedocs.io/en/latest/components/lower-level/level2/format.html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        loadUi(DIR_UI / 'forceproductimportdialog.ui', self)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.mModel = OptionListModel()
        for p, (r, n) in FORCE_PRODUCTS.items():
            self.mModel.addOption(Option(p, name=n))

        self.mProductType.setModel(self.mModel)
        self.mProductType.currentIndexChanged.connect(self.updateInfo)
        self.mFileWidget.fileChanged.connect(self.updateInfo)
        self.mTileIdWidget.fileChanged.connect(self.updateInfo)
        self.mDateMin.dateChanged.connect(self.updateInfo)
        self.mDateMax.dateChanged.connect(self.updateInfo)
        self.mTasks: List[FindFORCEProductsTask] = []

        widgets = [self.fileWidget(), self.productTypeComboBox(), self.tileIdWidget()]
        self.defaultToolTips = {id(w): w.toolTip() for w in widgets}

        self.mLastSearchId: str = ''
        self.mLastSearchResults: Dict[str, List[Path]] = dict()

        self.finished.connect(self.onFinished)
        self.updateInfo()

    def minDate(self) -> Optional[QDate]:

        if self.mDateMin.isEnabled():
            return self.mDateMin.date()
        else:
            return None

    def maxDate(self) -> Optional[QDate]:
        if self.mDateMax.isEnabled():
            return self.mDateMax.date()
        else:
            return None

    def buttonBox(self) -> QDialogButtonBox:
        return self.mButtonBox

    def fileWidget(self) -> QgsFileWidget:
        return self.mFileWidget

    def tileIdWidget(self) -> QgsFileWidget:
        return self.mTileIdWidget

    def productTypeComboBox(self) -> QComboBox:
        return self.mProductType

    def infoLabel(self) -> QLabel:
        return self.mInfoLabel

    def setRootFolder(self, folder: Union[str, Path]):
        folder = Path(folder)

        if folder.is_dir():
            self.fileWidget().setFilePath(folder.as_posix())

    def setProductType(self, product: str):
        assert product in FORCE_PRODUCTS.keys()

        o = self.mModel.findOption(product)

        if isinstance(o, Option) and o != self.productType():
            r = self.mModel.mOptions.index(o)
            self.productTypeComboBox().setCurrentIndex(r)

    def setTileIDs(self, text: Union[str, Path]):
        if isinstance(text, Path):
            text = str(text)
        self.tileIdWidget().setFilePath(text)

    def productType(self) -> str:
        return self.productTypeComboBox().currentData().value()

    def rootFolder(self) -> Optional[Path]:
        path = self.fileWidget().filePath()
        if path in [None, '']:
            return None
        return Path(self.fileWidget().filePath())

    def setInfoText(self, text: str, color: Optional[QColor] = None):
        self.infoLabel().setText(text)
        if color:
            self.infoLabel().setStyleSheet(f'color:{color.name()};')
        else:
            self.infoLabel().setStyleSheet('')

    def updateInfo(self):
        product = self.productType()
        path = self.rootFolder()
        tileIDs = self.tileIds()

        dateMin = self.minDate()
        dateMax = self.maxDate()

        errors = []
        fw = self.fileWidget()

        if isinstance(path, Path) and path.is_dir():
            fw.lineEdit().setStyleSheet('')
            fw.lineEdit().setToolTip(self.defaultToolTips.get(id(fw)))
        else:
            fw.lineEdit().setStyleSheet('color:red;')
            error = f'Not a directory: "{path}"'
            fw.lineEdit().setToolTip(error)
            errors.append(error)

        w = self.tileIdWidget()
        tile_ids_test = w.filePath()
        if len(tile_ids_test) > 0 and len(self.tileIds()) == 0:
            error = f'Unable to extract tile IDs from "{tile_ids_test}"'
            w.lineEdit().setToolTip(error)
            w.lineEdit().setStyleSheet('color:red;')
            errors.append(error)
        else:
            w.lineEdit().setToolTip(self.defaultToolTips.get(id(w)))
            w.lineEdit().setStyleSheet('')

        cb = self.productTypeComboBox()
        if product not in FORCE_PRODUCTS.keys():
            error = f'Unknown product "{product}"'
            cb.setStyleSheet('color: red')
            errors.append(error)
        else:
            cb.setStyleSheet('')

        self.infoLabel().setText('')

        for t in self.mTasks:
            t.cancel()

        if len(errors) == 0:
            self.buttonBox().button(QDialogButtonBox.Ok).setEnabled(True)
            for t in self.mTasks:
                t.cancel()
            self.mTasks.clear()
            task = FindFORCEProductsTask(product, path, tile_ids=tileIDs, dateMin=dateMin, dateMax=dateMax)
            task.taskInfo.connect(lambda info: self.setInfoText(f'<i>{info}</i>'))
            task.taskCompleted.connect(self.onTaskCompleted)
            task.taskTerminated.connect(self.onTaskTerminated)
            self.mLastSearchId = task.searchId()
            self.mLastSearchResults.clear()
            self.mTasks.append(task)
            QgsApplication.taskManager().addTask(task)

        else:
            self.buttonBox().button(QDialogButtonBox.Ok).setEnabled(False)

        # print(self.mTasks)

    def files(self) -> Optional[List[Path]]:
        """
        Returns the file list returned by the last search task
        Only available if the last search task was not canceled.
        :return:
        """
        return self.mLastSearchResults.get(self.mLastSearchId)

    def onTaskTerminated(self):
        task = self.sender()
        if isinstance(task, FindFORCEProductsTask) and task in self.mTasks:
            self.mTasks.remove(task)

    def onTaskCompleted(self, *args):

        task = self.sender()
        if isinstance(task, FindFORCEProductsTask):
            self.mLastSearchResults[task.searchId()] = task.files()
            if task in self.mTasks:
                self.mTasks.remove(task)

        s = ""

    def tileIds(self) -> List[str]:

        tile_file = self.tileIdWidget().filePath()
        if os.path.isfile(tile_file):
            with open(tile_file, 'r') as f:
                tile_text = f.read()
        else:
            tile_text = tile_file

        return read_tileids(tile_text)

    def onFinished(self):
        # print('# FINISHED')
        for t in self.mTasks:
            t.cancel()
        self.mTasks.clear()
