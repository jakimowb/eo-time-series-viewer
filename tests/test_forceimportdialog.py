import os
import unittest
from pathlib import Path

from eotimeseriesviewer.forceinputs import FindFORCEProductsTask, FORCEProductImportDialog, read_tileids
from eotimeseriesviewer.tests import start_app, TestCase

start_app()

FORCE_ROOT = Path(os.environ.get('FORCE_ROOT', r'D:\EOTSV\FORCE_CUBE'))


class FORCEImportTestCases(TestCase):

    def test_dialog(self):
        d = FORCEProductImportDialog()

        self.showGui(d)

    def test_read_tileids(self):
        text = ' X002_Y009; X001_Y003, X001_Y003; X01_Y00001;'
        self.assertEqual(read_tileids(text), ['X001_Y003', 'X002_Y009'])

    @unittest.skipIf(not FORCE_ROOT.is_dir(), 'Missing FORCE_ROOT')
    def test_data_loading(self):
        d = FORCEProductImportDialog()
        d.setRootFolder(FORCE_ROOT)
        d.setProductType('VZN')
        d.setTileIDs('X0001_Y0001,  X0001_Y0001')

        tiles = d.tileIds()
        self.assertEqual(tiles, ['X0001_Y0001'])
        self.showGui(d)

    @unittest.skipIf(not FORCE_ROOT.is_dir(), 'Missing FORCE_ROOT')
    def test_find_products(self):
        task = FindFORCEProductsTask(FORCE_ROOT, 'BOA')
        task.run()

        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertIsInstance(f, Path)
            self.assertTrue(f.is_file())
            self.assertTrue(f.name.endswith('BOA.tif'))


if __name__ == '__main__':
    unittest.main()
