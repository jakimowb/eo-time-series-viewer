import os, sys, pathlib

def compileQPSResources():
    pathQPSDir = os.path.dirname(__file__)
    pathQPSRoot = os.path.dirname(pathQPSDir)

    addSysPath = pathQPSRoot not in sys.path
    if addSysPath:
        sys.path.append(pathQPSRoot)

    from .make.make import compileResourceFiles, compileQGISResourceFiles
    compileResourceFiles(pathQPSDir)

    if addSysPath:
        sys.path.remove(pathQPSRoot)

if __name__ == "__main__":
    compileQPSResources()


