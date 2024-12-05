import unittest
from pathlib import Path

from eotimeseriesviewer.forceinputs import FORCEProductImportDialog
from eotimeseriesviewer.tests import start_app, TestCase

start_app()

FORCE_ROOT = Path(r'D:\EOTSV\FORCE_CUBE')


class FORCEImportTestCases(TestCase):

    def test_dialog(self):
        d = FORCEProductImportDialog()

        self.showGui(d)

    @unittest.skipIf(not FORCE_ROOT.is_dir(), 'Missing FORCE_ROOT')
    def test_data_loading(self):
        d = FORCEProductImportDialog()
        d.setRootFolder(FORCE_ROOT)
        d.setProductType('VZN')

        self.showGui(d)


if __name__ == '__main__':
    unittest.main()
