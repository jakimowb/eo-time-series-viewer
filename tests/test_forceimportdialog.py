import os
import unittest
from pathlib import Path

from PyQt5.QtCore import QDate

from eotimeseriesviewer.forceinputs import find_tile_folders, FindFORCEProductsTask, FORCEProductImportDialog, \
    read_tileids, rx_FORCE_TILEFOLDER
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()

FORCE_ROOT = Path(os.environ.get('FORCE_ROOT', r'D:\EOTSV\FORCE_CUBE'))


class FORCEImportTestCases(EOTSVTestCase):

    def test_dialog(self):
        d = FORCEProductImportDialog()

        self.showGui(d)

    def test_read_tileids(self):
        text = ' X002_Y009; X001_Y003,\nX001_Y003; X01_Y00001;'
        self.assertEqual(read_tileids(text), ['X001_Y003', 'X002_Y009'])

        tile_ids = ['X002_Y002', 'X0003_Y0004']
        test_dir = self.createTestOutputDirectory()
        path_whilelist = test_dir / 'whitelist.txt'
        with open(path_whilelist, 'w') as f:
            f.write('\n'.join(tile_ids))

        d = FORCEProductImportDialog()
        d.setTileIDs(path_whilelist)
        ids = d.tileIds()
        self.assertEqual(set(tile_ids), set(ids))

    @unittest.skipIf(not FORCE_ROOT.is_dir(), 'Missing FORCE_ROOT')
    def test_read_files(self):

        tile_ids = ['X0044_Y0052', 'X0045_Y0050']
        dateMin = QDate(2019, 1, 1)
        dateMax = QDate(2020, 1, 3)
        task = FindFORCEProductsTask('BOA', FORCE_ROOT,
                                     tile_ids=tile_ids,
                                     dateMin=dateMin, dateMax=dateMax)
        task.run()

        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertTrue(f.parent.name in tile_ids)
            self.assertTrue(f.name.endswith('.tif'))

    @unittest.skipIf(not os.path.isdir(FORCE_ROOT / 'mosaic'), 'Missing FORCE_ROOT/mosaic folder')
    def test_read_mosaic_vrts(self):
        root = FORCE_ROOT / 'mosaic'
        self.assertTrue(root.is_dir())

        task = FindFORCEProductsTask('BOA', root)
        task.run()
        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertTrue(f.name.endswith('_BOA.vrt'))

    @unittest.skipIf(not FORCE_ROOT.is_dir(), 'Missing FORCE_ROOT')
    def test_find_tilefolders(self):
        root = FORCE_ROOT
        folders = find_tile_folders(root)
        for f in folders:
            self.assertIsInstance(f, Path)
            self.assertTrue(f.is_dir())
            self.assertTrue(rx_FORCE_TILEFOLDER.match(f.name))

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
        task = FindFORCEProductsTask('BOA', FORCE_ROOT)
        task.run()

        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertIsInstance(f, Path)
            self.assertTrue(f.is_file())
            self.assertTrue(f.name.endswith('BOA.tif'))


if __name__ == '__main__':
    unittest.main()
