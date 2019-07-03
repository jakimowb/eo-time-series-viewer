
import os, sys, re, pathlib, json
import csv as pycsv
from .spectrallibraries import *


class EcoSYSSpectralLibraryIO(object):
    """
    I/O Interface for the EcoSYS spectral library format.
    See https://ecosis.org for details.
    """
    @staticmethod
    def canRead(path):
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        return False

    @staticmethod
    def readFrom(path):
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """
        return None

    @staticmethod
    def write(speclib, path):
        """Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom"""
        assert isinstance(speclib, SpectralLibrary)
        return []

    @staticmethod
    def score(uri:str)->int:
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probalby thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        return 0

