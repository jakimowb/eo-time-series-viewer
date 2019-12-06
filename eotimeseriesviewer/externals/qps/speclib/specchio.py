
import os, sys, re, pathlib, json, collections
import csv as pycsv
from .spectrallibraries import *


class SPECCHIOSpectralLibraryIO(AbstractSpectralLibraryIO):
    """
    I/O Interface for the SPECCHIO spectral library .
    See https://ecosis.org for details.
    """
    @staticmethod
    def canRead(path)->bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """

        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if re.search(r'^\d+(\.\d+)?.+', line):
                    return True

        return False

    @staticmethod
    def readFrom(path, wlu='nm', delimiter=',', progressDialog:QProgressDialog=None)->SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """

        sl = SpectralLibrary()
        sl.startEditing()
        bn = os.path.basename(path)
        delimiter = ','
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            DATA = collections.OrderedDict()
            readMetaData = True
            regNumber = re.compile(r'^\d+(\.\d+)?$')
            nProfiles = 0
            for i, line in enumerate(lines):

                assert isinstance(line, str)
                line = line.strip()
                if len(line) == 0:
                    continue

                values = line.split(delimiter)
                if len(values) < 2:
                    continue

                try:
                    mdKey = values.pop(0).strip()
                    assert isinstance(mdKey, str)
                    if len(values) == 0:
                        continue

                    t = findTypeFromString(values[0])
                    values = [t(v) for v in values if len(v) > 0]
                    if len(values) > 0:
                        DATA[mdKey] = values
                    else:
                        s = ""
                except Exception as ex:
                    print(ex, file=sys.stderr)
                    print('Line {}:{}'.format(i+1, line), file=sys.stderr)

            numericValueKeys = []
            metadataKeys = []
            for k in DATA.keys():
                if regNumber.search(k):
                    numericValueKeys.append(k)
                else:
                    metadataKeys.append(k)

            numericValueKeys = sorted(numericValueKeys)
            xValues = [float(v) for v in numericValueKeys]
            nProfiles = len(DATA[numericValueKeys[0]])

            sl.beginEditCommand('Set metadata columns')
            for k in metadataKeys:
                if k in sl.fieldNames():
                    continue

                k2 = k.replace(' ', '_')
                qgsField = createQgsField(k, DATA[k][0])
                assert sl.addAttribute(qgsField)


            sl.endEditCommand()
            sl.commitChanges()
            sl.startEditing()
            profiles = []
            for i in range(nProfiles):
                profile = SpectralProfile(fields=sl.fields())
                # add profile name
                if FIELD_NAME in metadataKeys:
                    profile.setName(DATA[FIELD_NAME][i])
                else:
                    profile.setName('{}:{}'.format(bn, i+1))

                # add profile values
                yValues = [float(DATA[k][i]) for k in numericValueKeys]
                profile.setValues(x=xValues, y=yValues, xUnit=wlu)

                # add profile metadata
                for k in metadataKeys:
                    mdValues = DATA[k]
                    if len(mdValues) > i:
                        profile.setAttribute(k, mdValues[i])

                profiles.append(profile)

            sl.addProfiles(profiles, addMissingFields=True)
        sl.commitChanges()
        return sl

    @staticmethod
    def write(speclib:SpectralLibrary, path:str, progressDialog:QProgressDialog=None, delimiter:str=',')->list:
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom(...)
        :param speclib: SpectralLibrary
        :param path: str, path to library source
        :return: [str-list-of-written-files]
        """
        """
                Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
                """
        assert isinstance(speclib, SpectralLibrary)
        basePath, ext = os.path.splitext(path)
        s = ""

        writtenFiles = []
        fieldNames = [n for n in speclib.fields().names() if n not in [FIELD_VALUES, FIELD_FID]]
        groups = speclib.groupBySpectralProperties()
        for i, grp in enumerate(groups.keys()):
            # in-memory text buffer
            stream = io.StringIO()
            xValues, xUnit, yUnit = grp
            profiles = groups[grp]
            if i == 0:
                path = basePath + ext
            else:
                path = basePath + '{}{}'.format(i + 1, ext)

            # write metadata
            for fn in speclib.fields().names():
                assert isinstance(fn, str)
                if fn in [FIELD_FID, FIELD_VALUES]:
                    continue
                line = [fn]
                for p in profiles:
                    assert isinstance(p, SpectralProfile)
                    line.append(str(p.attribute(fn)))
                stream.write(delimiter.join(line) + '\n')
            #
            line = ['wavelength unit']
            for p in profiles:
                line.append(str(p.xUnit()))
            stream.write(delimiter.join(line) + '\n')

            # write values
            for i, xValue in enumerate(xValues):
                line = [str(xValue)]
                for p in profiles:
                    assert isinstance(p, SpectralProfile)
                    yValue = p.values()['y'][i]
                    line.append(str(yValue))
                stream.write(delimiter.join(line) + '\n')

            lines = stream.getvalue().replace('\r', '')

            with open(path, 'w', encoding='utf-8') as f:
                f.write(lines)
                writtenFiles.append(path)

        return writtenFiles

    @staticmethod
    def score(uri:str)->int:
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probalby thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        return 0


    @staticmethod
    def addExportActions(spectralLibrary:SpectralLibrary, menu:QMenu) -> list:

        def write(speclib: SpectralLibrary):

            path, filter = QFileDialog.getSaveFileName(caption='Write SPECCHIO CSV Spectral Library ',
                                                    filter='Textfile (*.csv)')
            if isinstance(path, str) and len(path) > 0:
                SPECCHIOSpectralLibraryIO.write(spectralLibrary, path)

        m = menu.addAction('SPECCHIO')
        m.setToolTip('Exports the profiles into the SPECCIO text file format.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))

    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='Read SPECCHIO CSV File',
                                               filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if os.path.isfile(path):

                sl = SPECCHIOSpectralLibraryIO.readFrom(path)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('SPECCHIO')
        m.setToolTip('Adds profiles stored in an SPECCHIO csv text file.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))