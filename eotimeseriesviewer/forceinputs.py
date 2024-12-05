import re
from pathlib import Path
from typing import List, Union

from qgis.PyQt.QtCore import pyqtSignal
from eotimeseriesviewer.qgispluginsupport.qps.models import Option, OptionListModel
from eotimeseriesviewer.tasks import EOTSVTask
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QLabel
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, loadUi

FORCE_PRODUCTS = {
    'BOA': (r'.*BOA\.(tif|dat|hdr)$', 'Bottom of Atmosphere (BOA)'),
    'TOA': (r'.*TOA\.(tif|dat|hdr)$', 'Top-of-Atmosphere Reflectance (TOA)'),
    'QAI': (r'.*QAI\.(tif|dat|hdr)$', 'Quality Assurance Information (QAI)'),
    'AOD': (r'.*AOD\.(tif|dat|hdr)$', 'Aerosol Optical Depth (AOD)'),
    'DST': (r'.*DST\.(tif|dat|hdr)$', 'Cloud / Cloud shadow /Snow distance (DST)'),
    'WVP': (r'.*WVP\.(tif|dat|hdr)$', 'Water vapor (WVP)'),
    'VZN': (r'.*VZN\.(tif|dat|hdr)$', 'View zenith (VZN)'),
    'HOT': (r'.*HOT\.(tif|dat|hdr)$', 'Haze Optimized Transformation (HOT)'),
}


class FindFORCEProductsTask(EOTSVTask):
    taskInfo = pyqtSignal(str)

    def __init__(self, product: str, path, *args, **kwds):
        super().__init__(*args, **kwds)

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
        rx_FORCE_DIR = re.compile(r'X\d+_Y\d+')
        self.taskInfo.emit(f'Search for {self.mProduct} files...')

        n = 0
        for file in file_search(self.mPath, self.mRxProduct, recursive=True):
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

    def productType(self) -> str:
        return self.cbProductType.currentData().value()

    def rootFolder(self) -> Path:
        return Path(self.fileWidget.filePath())

    def updateInfo(self):
        product = self.productType()
        path = self.rootFolder()

        if product in FORCE_PRODUCTS.keys() and path.is_dir():
            task = FindFORCEProductsTask(product, path)
            task.taskInfo.connect(lambda info: self.labelInfos.setText(f'<i>{info}</i>'))
            task.run()
