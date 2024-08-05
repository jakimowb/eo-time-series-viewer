"""
Initial setup of the EOTSV repository.
Run this script after you have cloned the EOTSV repository
"""
import argparse
import io
import os
import shutil
import site
import zipfile
from pathlib import Path

import requests

site.addsitedir(Path(__file__).parents[1].as_posix())

from scripts.compile_resourcefiles import compileEOTSVResourceFiles
from eotimeseriesviewer import DIR_REPO, URL_QGIS_RESOURCES


def install_zipfile(url: str, localPath: Path, zip_root: str = None):
    assert isinstance(localPath, Path)
    localPath = localPath.resolve()

    print('Download {} \nto {}'.format(url, localPath))

    response = requests.get(url, stream=True)

    z = zipfile.ZipFile(io.BytesIO(response.content))
    os.makedirs(localPath, exist_ok=True)
    for src in z.namelist():
        srcPath = Path(src)
        if isinstance(zip_root, str):
            if zip_root not in srcPath.parts:
                continue
            i = srcPath.parts.index(zip_root)
            dst = localPath / Path(*srcPath.parts[i + 1:])
        else:
            dst = localPath / Path(*srcPath.parts)
        info = z.getinfo(src)
        if info.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            os.makedirs(dst, exist_ok=True)
        else:
            if dst.exists():
                os.remove(dst)
            with open(dst, "wb") as f:
                f.write(z.read(src))

    # z.extractall(path=localPath, members=to_extract)
    del response


def install_qgisresources():
    localpath = DIR_REPO / 'qgisresources'
    install_zipfile(URL_QGIS_RESOURCES, localpath)


def setup_eotsv_repository(resources: bool = True,
                           qgis_resources: bool = False):
    # specify the local path to the cloned QGIS repository
    site.addsitedir(DIR_REPO)

    DIR_SITEPACKAGES = DIR_REPO / 'site-packages'
    DIR_QGISRESOURCES = DIR_REPO / 'qgisresources'

    if resources:
        print('Compile EOTSV resource files')
        compileEOTSVResourceFiles()
    if qgis_resources:
        print('Install QGIS resource files')
        install_qgisresources()
    print('EO Time Series Viewer repository setup finished')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Setup Repository. Run this after you have cloned the '
                                                 'EO Time Series Viewer repository')
    parser.add_argument('-r', '--resources',
                        required=False,
                        default=False,
                        help='Create *_rc.py resource file modules from *.qrc files',
                        action='store_true'
                        )

    parser.add_argument('-q', '--qgisresources',
                        required=False,
                        default=False,
                        action='store_true',
                        help='Download and install QGIS resource files compiled as *_rc.py modules',
                        )

    args = parser.parse_args()

    if not any([args.resources,
                args.qgisresources]):
        args.resources = True
        args.qgisresources = True

    print('Setup repository')
    setup_eotsv_repository(resources=args.resources,
                           qgis_resources=args.qgisresources)
    print('EO Time Series Viewer repository setup finished')
