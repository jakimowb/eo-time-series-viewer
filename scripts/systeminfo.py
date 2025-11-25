import platform
import sys

from qgis.core import Qgis

print(platform.platform())
print(platform.processor())
print(platform.python_implementation())
print(platform.python_version())
print(f'Sys exe: {sys.executable}')

print(f'QGIS: {Qgis.version()} {Qgis.devVersion()}')

print('Package locations:')
packages = ['osgeo.gdal', 'numpy', 'scipy', 'OpenGL',
            'matplotlib', 'pip', 'netCDF4']
for p in packages:
    try:
        pkg = __import__(p)
        version = 'unknown'
        if hasattr(pkg, '__version__'):
            version = pkg.__version__
        info = f'{p} version {version}: {pkg.__file__}'
        print(info)

    except Exception as ex:
        print(ex)
