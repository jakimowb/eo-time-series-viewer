import datetime
import json
import os
import unittest
from pathlib import Path
from typing import Union

from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from qgis import processing
from qgis.core import QgsApplication, QgsProcessingAlgRunnerTask, QgsProject, QgsRasterLayer, QgsTaskManager
from eotimeseriesviewer.force import FORCEUtils
from eotimeseriesviewer.forceinputs import FindFORCEProductsTask
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.processingalgorithms import ReadTemporalProfiles
from eotimeseriesviewer.tests import EOTSVTestCase, start_app
from eotimeseriesviewer import initAll

start_app()
initAll()

FORCE_CUBE = Path(os.environ.get('FORCE_CUBE', '-'))


def get_workbook(path_xlsx: Union[str, Path]) -> Workbook:
    path_xlsx = Path(path_xlsx)
    if path_xlsx.is_file():
        book = load_workbook(filename=path_xlsx.as_posix())
    else:
        book = Workbook()
    for s in book.sheetnames[:]:
        del book[s]
    return book


def get_sheet(name: str, book: Workbook) -> Worksheet:
    if name in book.sheetnames:
        sheet = book[name]
        sheet.delete_cols(1, sheet.max_column)
    else:
        sheet = book.create_sheet(name)
    return sheet


@unittest.skipIf(EOTSVTestCase.runsInCI(), 'Benchmark Tests. Not to run in CI')
class BenchmarkTestCase(EOTSVTestCase):

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_benchmark_load_eotsv(self):

        path_results = self.createTestOutputDirectory() / 'benchmark_load_eotsv.json'

        if not path_results.is_file():

            tile_ids = [self.get_example_tiledir()]

            task = FindFORCEProductsTask('BOA', FORCE_CUBE, tile_ids=tile_ids)
            task.run_task_manager()

            files = task.files()

            n_threads = [2, 4, 6]
            n_files = [50, 100, 200, 400, 800]
            n_files = [n for n in n_files if n < len(files)]
            results = {'force_cube': str(FORCE_CUBE),
                       'tile_ids': tile_ids,
                       'results': []
                       }
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
                    d_result = {'n_threads': nt,
                                'n_files': nf,
                                'seconds': dt.total_seconds()}

                    results['results'].append(d_result)
                    print(d_result)
                    eotsv.close()
                    with open(path_results, 'w') as f:
                        json.dump(results, f, indent=2)
        else:
            with open(path_results, 'r') as f:
                results = json.load(f)
            print(f'Benchmark results: {path_results}')
            for (nt, nf), dt in results.items():
                print(f'threads={nt}, files={nf}: {dt}')

    def get_example_tiledir(self):

        tiles = [d.name for d in FORCEUtils.tileDirs(FORCE_CUBE)]
        assert len(tiles) > 0
        if 'X0066_Y0058' in tiles:
            tile_id = 'X0066_Y0058'
        else:
            tile_id = tiles[0]
        return tile_id

    @unittest.skipIf(not FORCE_CUBE.is_dir(), 'Missing FORCE_CUBE')
    def test_load_force_processingalgorithm_benchmark(self):

        tile_id = self.get_example_tiledir()

        thin_bottom_border = Border(bottom=Side(style='thin'))
        bold_font = Font(bold=True)
        top_alignment = Alignment(vertical="top")

        task = FindFORCEProductsTask('BOA', FORCE_CUBE, tile_ids=[tile_id])
        task.run_task_manager()
        all_files = task.files()

        assert len(all_files) > 0

        dir_outputs = self.createTestOutputDirectory()

        project = QgsProject()

        path_results = dir_outputs / 'benchmark.json'

        if not path_results.is_file():
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
                                   context=context, feedback=feedback)

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

                        d_result = {'n_files': nf,
                                    'n_threads': nt,
                                    'n_points': npts,
                                    'seconds': dt.total_seconds()}

                        results.append(d_result)
                        print(d_result)
                        with open(path_results, 'w') as f:
                            json.dump(results, f, indent=4)
        else:
            with open(path_results, 'r') as f:
                results = json.load(f)

            path_xlsx = path_results.parent / (path_results.stem + '.xlsx')

            wb = get_workbook(path_xlsx)
            sheet = get_sheet('benchmark', wb)
            sheet.cell(1, 1, f'Benchmark {path_results}')
            sheet.cell(2, 1)
            matrix = dict()
            for e in results:
                nf = e['n_files']
                nt = e['n_threads']
                np = e['n_points']
                k = (nf, nt, np)
                matrix[k] = e['seconds']

            n_files = sorted(set([k[0] for k in matrix.keys()]))
            n_threads = sorted(set([k[1] for k in matrix.keys()]))
            n_points = sorted(set([k[2] for k in matrix.keys()]))

            wb.save(path_xlsx.as_posix())


if __name__ == '__main__':
    unittest.main()
