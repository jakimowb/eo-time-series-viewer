
from osgeo import gdal, ogr, osr
import warnings

from .. import resources
def compileResourceFiles(*args, **kwds):
    warnings.warn('Use qps.resources.compileResourceFiles() instead', DeprecationWarning)
    return resources.compileResourceFiles(*args, **kwds)

def compileResourceFile(*args, **kwds):
    warnings.warn('Use qps.resources.compileResourceFile() instead', DeprecationWarning)
    return resources.compileResourceFile(*args, **kwds)

