
import typing
from qgis.PyQt.QtCore import *

from .core import SpectralLibrary, SpectralProfile


class AbstractSpectralMathFunction(QObject):

    def __init__(self, profile: SpectralProfile):
        pass