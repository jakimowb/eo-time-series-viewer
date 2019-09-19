import os, sys

def compileQPSResources():
    pathQPSDir = os.path.dirname(__file__)
    pathQPSRoot = os.path.dirname(pathQPSDir)

    addSysPath = pathQPSRoot not in sys.path
    if addSysPath:
        sys.path.append(pathQPSRoot)

    from qps.make.make import searchAndCompileResourceFiles
    searchAndCompileResourceFiles(pathQPSDir)

    if addSysPath:
        sys.path.remove(pathQPSRoot)



if __name__ == "__main__":
    compileQPSResources()


