import datetime
import json
import os
import unittest
from pathlib import Path

from qgis._core import QgsApplication, QgsProcessingAlgRunnerTask, QgsProject, QgsRasterLayer, QgsTaskManager

from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.forceinputs import find_tile_folders, FindFORCEProductsTask, FORCEProductImportDialog, \
    read_tileids, rx_FORCE_TILEFOLDER
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.processingalgorithms import ReadTemporalProfiles
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from qgis import processing
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
                    results[(nt, nf)] = str(dt)

                    dt_image = dt / len(files_to_load)
                    print(f'threads={nt}, files={nf}: {dt} -> per file: {dt_image}')
                    eotsv.close()
            with open(path_results, 'w') as f:
                json.dump(results, f, indent=3)
        else:
            with open(path_results, 'r') as f:
                results = json.load(f)
            print(f'Benchmark results: {path_results}')
            for (nt, nf), dt in results.items():
                print(f'threads={nt}, files={nf}: {dt}')

    def test_load_force_processingalgorithm_benchmark(self):

        tiles = [d.name for d in FORCEUtils.tileDirs(FORCE_CUBE)]
        assert len(tiles) > 0
        if 'X0066_Y0058' in tiles:
            tile_id = 'X0066_Y0058'
        else:
            tile_id = tiles[0]

        task = FindFORCEProductsTask('BOA', FORCE_CUBE, tile_ids=[tile_id])
        task.run_task_manager()
        all_files = task.files()

        assert len(all_files) > 0

        dir_outputs = self.createTestOutputDirectory()

        project = QgsProject()

        path_results = dir_outputs / 'benchmark.json'

        n_threads = [2, 4, 6, 8]
        n_files = [1, 25, 50, 100, 150, 200, 250, 300]
        n_files = [n for n in n_files if n < len(all_files)]
        n_points = [1, 5, 10, 50]

        results = []

        for npts in n_points:
            path_random_points = dir_outputs / f'random_points_{npts}.geojson'
            path_random_points.unlink(missing_ok=True)

            for f in all_files:
                lyr = QgsRasterLayer(f.as_posix())
                project.addMapLayer(lyr)

                context, feedback = self.createProcessingContextFeedback()
                context.setProject(project)

                assert lyr.isValid()
                processing.run("native:randompointsinextent", {
                    'EXTENT': lyr.extent(),
                    'POINTS_NUMBER': npts,
                    'MIN_DISTANCE': 30,
                    'TARGET_CRS': lyr.crs(),
                    'MAX_ATTEMPTS': 200,
                    'OUTPUT': str(path_random_points)},
                               context=context, feedback=feedback
                               )

                break

            for nf in n_files:
                for nt in n_threads:
                    path_output = dir_outputs / f'files_{nf}_threads_{nt}.geojson'
                    path_output.unlink(missing_ok=True)

                    alg = ReadTemporalProfiles()
                    conf = {}
                    alg.initAlgorithm(conf)
                    files = [str(f) for f in all_files[0: nf]]
                    param = {
                        alg.INPUT: path_random_points.as_posix(),
                        alg.TIMESERIES: files,
                        alg.N_THREADS: nt,
                        alg.FIELD_NAME: 'tp',
                        alg.OUTPUT: path_output.as_posix(),
                    }

                    context, feedback = self.createProcessingContextFeedback()
                    context.setProject(project)

                    task = QgsProcessingAlgRunnerTask(alg, param, context, feedback)
                    self.assertTrue(task.canCancel())
                    tm: QgsTaskManager = QgsApplication.taskManager()

                    t0 = datetime.datetime.now()
                    tm.addTask(task)
                    self.taskManagerProcessEvents()
                    dt = datetime.datetime.now() - t0

                    results.append(
                        {'n_files': nf,
                         'n_threads': nt,
                         'n_points': npts,
                         'seconds': dt.total_seconds()}
                    )
                    with open(path_results, 'w') as f:
                        json.dump(results, f, indent=4)


if __name__ == '__main__':
    unittest.main()
