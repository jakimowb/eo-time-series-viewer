import os, sys

DIR_QGIS_REPO = os.environ.get('DIR_QGIS_REPO')

def compileQPSResources():
    pathQPSDir = os.path.dirname(__file__)
    pathQPSRoot = os.path.dirname(pathQPSDir)

    addSysPath = pathQPSRoot not in sys.path
    if addSysPath:
        sys.path.append(pathQPSRoot)

    from qps.make.make import searchAndCompileResourceFiles, compileQGISResourceFiles
    searchAndCompileResourceFiles(pathQPSDir)
    if os.path.isdir(DIR_QGIS_REPO):
        compileQGISResourceFiles(DIR_QGIS_REPO, None)

    if addSysPath:
        sys.path.remove(pathQPSRoot)



if __name__ == "__main__":
    compileQPSResources()


