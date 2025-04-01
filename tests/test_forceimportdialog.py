import csv
import datetime
import json
import os
import unittest
from pathlib import Path

from eotimeseriesviewer.forceinputs import find_tile_folders, FindFORCEProductsTask, FORCEProductImportDialog, \
    read_tileids, rx_FORCE_TILEFOLDER
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from qgis.PyQt.QtCore import QDate

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

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_load_eotsv(self):

        eotsv = EOTimeSeriesViewer()
        eotsv.ui.show()
        eotsv.loadFORCEProducts(force_cube=FORCE_CUBE, tile_ids='X0066_Y0058')
        self.showGui(eotsv.ui)

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    @unittest.skipIf(EOTSVTestCase.runsInCI(), 'Benchmark only')
    def test_benchmark_load_eotsv(self):

        path_results = self.createTestOutputDirectory() / 'benchmark_load_eotsv.json'
        path_csv = path_results.parent / (path_results.stem + '.csv')

        if not path_results.is_file():
            task = FindFORCEProductsTask('BOA', FORCE_CUBE, tile_ids=['X0066_Y0058'])
            task.run_task_manager()

            files = task.files()

            n_threads = [2, 4, 6]
            n_files = [50, 100, 200, 400, 800]
            n_files = [n for n in n_files if n < len(files)]
            results = dict()
            for nt in n_threads:
                for nf in n_files:
                    files_to_load = files[0:nf]
                    eotsv = EOTimeSeriesViewer()
                    eotsv.ui.show()
                    self.taskManagerProcessEvents()
                    t0 = datetime.datetime.now()
                    eotsv.addTimeSeriesImages(files_to_load)
                    self.taskManagerProcessEvents()
                    dt = datetime.datetime.now() - t0

                    k = f'{nt}_{nf}'
                    results[k] = {'n_threads': nt,
                                  'n_files': nf,
                                  'total_seconds': dt.total_seconds(),
                                  'total_seconds_per_file': dt.total_seconds() / len(files_to_load),
                                  }
                    print(results[k])
                    eotsv.close()

            with open(path_results, 'w') as f:
                json.dump(results, f, indent=3)
        else:
            with open(path_results, 'r') as f:
                results = json.load(f)
            print(f'Benchmark results: {path_results}')

            n_files = [d['n_files'] for d in results.values()]
            n_threads = [d['n_threads'] for d in results.values()]

            matrix_total = dict()
            matrix_per_file = dict()
            for d in results.values():
                matrix_total[(d['n_threads'], d['n_files'])] = str(datetime.timedelta(seconds=d['total_seconds']))
                matrix_per_file[(d['n_threads'], d['n_files'])] = str(
                    datetime.timedelta(seconds=d['total_seconds_per_file']))

            with open(path_csv, 'w', newline='') as f:
                writer = csv.writer(f, dialect='excel')
                writer.writerow(['Benchmark results FORCE File Reading'])

                header = ['n_files'] + n_threads + n_threads

                writer.writerow(['', 'Files'])
                writer.writerow(['n_threads'] + n_files)

                for nt in n_threads:
                    row = [nt] + [matrix_total.get((nt, nf), None) for nf in n_files]
                    writer.writerow(row)

            csv.writer()

            for (nt, nf), dt in results.items():
                print(f'threads={nt}, files={nf}: {dt}')


if __name__ == '__main__':
    unittest.main()
