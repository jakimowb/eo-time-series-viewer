import csv
import datetime
import json
import os
import os
import unittest
from pathlib import Path

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QDate

from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.forceinputs import find_tile_folders, FindFORCEProductsTask, FORCEProductImportDialog, \
    read_tileids, rx_FORCE_TILEFOLDER
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()

FORCE_CUBE = Path(os.environ.get('FORCE_CUBE', '-'))


@unittest.skipIf(not FORCE_CUBE.is_dir(), 'FORCE_CUBE undefined / not a directory')
class FORCEImportTestCases(EOTSVTestCase):

    def force_tiles(self):

        tile_names = []

        with os.scandir(FORCE_CUBE) as scan:
            for e in scan:
                if rx_FORCE_TILEFOLDER.match(e.name):
                    tile_names.append(e.name)
        return tile_names

    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Blocking dialog')
    def test_dialog(self):
        d = FORCEProductImportDialog()

        self.showGui(d)

    def test_read_tileids(self):
        tile_ids = self.force_tiles()
        # construct string with duplications and different separators
        seps = [' ', '\n\t']
        text = []
        for sep in seps:
            text.append(sep.join(tile_ids))
        text = ';'.join(text)
        self.assertEqual(read_tileids(text), tile_ids)

        tile_ids = ['X002_Y002', 'X0003_Y0004']
        test_dir = self.createTestOutputDirectory()
        path_whilelist = test_dir / 'whitelist.txt'
        with open(path_whilelist, 'w') as f:
            f.write('\n'.join(tile_ids))

        d = FORCEProductImportDialog()
        d.setTileIDs(path_whilelist)
        ids = d.tileIds()
        self.assertEqual(set(tile_ids), set(ids))

    def test_read_files(self):

        tile_ids = self.force_tiles()
        dateMin = QDate(2019, 1, 1)
        dateMax = QDate(2020, 1, 3)
        task = FindFORCEProductsTask('BOA', FORCE_CUBE,
                                     tile_ids=tile_ids,
                                     dateMin=dateMin, dateMax=dateMax)
        task.run()

        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertTrue(f.parent.name in tile_ids)
            self.assertTrue(f.name.endswith('.tif'))

    @unittest.skipIf(not FORCE_CUBE.is_dir() and (FORCE_CUBE / 'mosaic').is_dir(), 'Missing FORCE_CUBE/mosaic folder')
    def test_read_mosaic_vrts(self):
        root = FORCE_CUBE / 'mosaic'
        self.assertTrue(root.is_dir())

        task = FindFORCEProductsTask('BOA', root)
        task.run()
        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertTrue(f.name.endswith('_BOA.vrt'))

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_find_tilefolders(self):
        root = FORCE_CUBE
        folders = find_tile_folders(root)
        for f in folders:
            self.assertIsInstance(f, Path)
            self.assertTrue(f.is_dir())
            self.assertTrue(rx_FORCE_TILEFOLDER.match(f.name))

    @unittest.skipIf(not EOTSVTestCase.runsInCI(), 'Blocking dialogs')
    def test_data_loading(self):
        d = FORCEProductImportDialog()
        d.setRootFolder(FORCE_CUBE)
        d.setProductType('VZN')

        tile_id = self.force_tiles()[0]

        d.setTileIDs(f'{tile_id},  {tile_id}')

        tiles = d.tileIds()
        self.assertEqual(tiles, [tile_id])
        self.showGui(d)

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_find_products(self):
        task = FindFORCEProductsTask('BOA', FORCE_CUBE)
        task.run()

        self.assertTrue(len(task.files()) > 0)
        for f in task.files():
            self.assertIsInstance(f, Path)
            self.assertTrue(f.is_file())
            self.assertTrue(f.name.endswith('BOA.tif'))

    def get_example_tiledir(self) -> str:

        tiles = [d.name for d in FORCEUtils.tileDirs(FORCE_CUBE)]
        assert len(tiles) > 0
        if 'X0066_Y0058' in tiles:
            tile_id = 'X0066_Y0058'
        else:
            tile_id = tiles[0]
        return tile_id

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_load_eotsv(self):

        eotsv = EOTimeSeriesViewer()
        eotsv.ui.show()
        tile_id = self.get_example_tiledir()
        eotsv.loadFORCEProducts(force_cube=FORCE_CUBE, tile_ids=tile_id)
        self.showGui(eotsv.ui)

    def test_crs_check(self):
        tile_id = self.get_example_tiledir()

        p = QgsProject.instance()
        for path in FORCEUtils.productFiles(FORCE_CUBE / tile_id, 'BOA'):
            lyr = QgsRasterLayer(path.as_posix())

            crs = QgsCoordinateReferenceSystem('EPSG:4326')

            trans = QgsCoordinateTransform()
            trans.setSourceCrs(lyr.crs())
            trans.setDestinationCrs(crs)

            self.assertTrue(trans.isValid())

            ext2 = trans.transformBoundingBox(lyr.extent())
            self.assertTrue(ext2.isFinite())
            break


if __name__ == '__main__':
    unittest.main()
