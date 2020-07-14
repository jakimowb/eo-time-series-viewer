"""
Initial setup of the EOTSV repository.
Run this script after you have cloned the EOTSV repository
"""
import pathlib
import requests
import zipfile
import os
import shutil
import io
import site
site.addsitedir(pathlib.Path(__file__).parents[1])




from eotimeseriesviewer import DIR_REPO, URL_QGIS_RESOURCES

def install_zipfile(url: str, localPath: pathlib.Path, zip_root: str = None):
    assert isinstance(localPath, pathlib.Path)
    localPath = localPath.resolve()

    print('Download {} \nto {}'.format(url, localPath))

    response = requests.get(url, stream=True)

    z = zipfile.ZipFile(io.BytesIO(response.content))
    os.makedirs(localPath, exist_ok=True)
    for src in z.namelist():
        srcPath = pathlib.Path(src)
        if isinstance(zip_root, str):
            if zip_root not in srcPath.parts:
                continue
            i = srcPath.parts.index(zip_root)
            dst = localPath / pathlib.Path(*srcPath.parts[i + 1:])
        else:
            dst = localPath / pathlib.Path(*srcPath.parts)
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

    #z.extractall(path=localPath, members=to_extract)
    del response

def install_qgisresources():
    localpath = DIR_REPO / 'qgisresources'
    install_zipfile(URL_QGIS_RESOURCES, localpath)

def setup_eotsv_repository():
    # specify the local path to the cloned QGIS repository
    site.addsitedir(DIR_REPO)

    DIR_SITEPACKAGES = DIR_REPO / 'site-packages'
    DIR_QGISRESOURCES = DIR_REPO / 'qgisresources'


    from scripts.compile_resourcefiles import compileEOTSVResourceFiles
    print('Compile EOTSV resource files')
    compileEOTSVResourceFiles()
    print('Install QGIS resource files')
    install_qgisresources()
    print('EO Time Series Viewer repository setup finished')


if __name__ == "__main__":
    print('setup repository')
    setup_eotsv_repository()
    exit(0)
