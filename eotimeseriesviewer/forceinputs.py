import os.path
import re
from pathlib import Path
from typing import List, Union

from qgis.PyQt.QtCore import pyqtSignal, Qt
from eotimeseriesviewer.qgispluginsupport.qps.models import Option, OptionListModel
from eotimeseriesviewer.tasks import EOTSVTask
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QLabel
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, loadUi

FORCE_PRODUCTS = {
    'BOA': (r'.*BOA\.(vrt|tif|dat|hdr)$', 'Bottom of Atmosphere (BOA)'),
    'TOA': (r'.*TOA\.(vrt|tif|dat|hdr)$', 'Top-of-Atmosphere Reflectance (TOA)'),
    'QAI': (r'.*QAI\.(vrt|tif|dat|hdr)$', 'Quality Assurance Information (QAI)'),
    'AOD': (r'.*AOD\.(vrt|tif|dat|hdr)$', 'Aerosol Optical Depth (AOD)'),
    'DST': (r'.*DST\.(vrt|tif|dat|hdr)$', 'Cloud / Cloud shadow /Snow distance (DST)'),
    'WVP': (r'.*WVP\.(vrt|tif|dat|hdr)$', 'Water vapor (WVP)'),
    'VZN': (r'.*VZN\.(vrt|tif|dat|hdr)$', 'View zenith (VZN)'),
    'HOT': (r'.*HOT\.(vrt|tif|dat|hdr)$', 'Haze Optimized Transformation (HOT)'),
}

rx_FORCE_TILEID = re.compile(r'(X\d+)_(Y\d+)')
rx_FORCE_TILEFOLDER = re.compile(f'^{rx_FORCE_TILEID.pattern}$')


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


class FindFORCEProductsTask(EOTSVTask):
    taskInfo = pyqtSignal(str)

    def __init__(self, product: str, path, *args, tile_ids: List[str] = None, **kwds):
        super().__init__(*args, **kwds)

        self.mTileIDs: List[str] = tile_ids if tile_ids else []

        for tile_id in self.mTileIDs:
            assert rx_FORCE_TILEID.match(tile_id), f'Not a force tile_id: {tile_id}'

        assert product in FORCE_PRODUCTS.keys()
        path = Path(path)
        assert path.is_dir()

        self.mProduct = product
        self.mPath = path
        self.mRxProduct = re.compile(FORCE_PRODUCTS[product][0])
        self.setDescription(f'Search {self.mProduct} files in {self.mPath}')
        self.mFiles: List[Path] = []

    def files(self) -> List[Path]:
        return self.mFiles

    def run(self):

        self.taskInfo.emit(f'Search for {self.mProduct} files...')

        tile_folders = []
        if len(self.mTileIDs) == 0:
            tile_folders.append(self.mPath)
        else:
            for folder in file_search(self.mPath, rx_FORCE_TILEID, recursive=True, directories=True):
                tile_folders.append(Path(folder))

        n = 0
        for folder in tile_folders:
            for file in file_search(folder, self.mRxProduct, recursive=True):
                n += 1
                self.mFiles.append(file)

                if n % 50 == 0:
                    if self.isCanceled():
                        return False
                    self.taskInfo.emit(f'Found {n} {self.mProduct} files...')
        self.taskInfo.emit(f'Found {n} {self.mProduct} files')
        return True


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
        self.buttonBox: QDialogButtonBox
        self.labelInfos: QLabel
        self.fileWidget: QgsFileWidget
        self.cbProductType.setModel(self.mModel)
        self.cbProductType.currentIndexChanged.connect(self.updateInfo)
        self.fileWidget.fileChanged.connect(self.updateInfo)

    def setRootFolder(self, folder: Union[str, Path]):
        folder = Path(folder)

        if folder.is_dir():
            self.fileWidget.setFilePath(folder.as_posix())

    def setProductType(self, product: str):
        assert product in FORCE_PRODUCTS.keys()

        o = self.mModel.findOption(product)

        if isinstance(o, Option) and o != self.productType():
            self.labelInfos.setText('')
            r = self.mModel.mOptions.index(o)
            self.cbProductType.setCurrentIndex(r)

    def setTileIDs(self, text: Union[str, Path]):
        if isinstance(text, Path):
            text = str(text)
        self.mTileIDs.setFilePath(text)

    def productType(self) -> str:
        return self.cbProductType.currentData().value()

    def rootFolder(self) -> Path:
        return Path(self.fileWidget.filePath())

    def updateInfo(self):
        product = self.productType()
        path = self.rootFolder()
        tileIDs = self.tileIds()

        if product in FORCE_PRODUCTS.keys() and path.is_dir():
            task = FindFORCEProductsTask(product, path, tile_ids=tileIDs)
            task.taskInfo.connect(lambda info: self.labelInfos.setText(f'<i>{info}</i>'))
            task.run()

    def tileIds(self) -> List[str]:

        tile_file = self.mTileIDs.filePath()
        if os.path.isfile(tile_file):
            with open(tile_file, 'r') as f:
                tile_text = f.read()
        else:
            tile_text = tile_file

        return read_tileids(tile_text)
