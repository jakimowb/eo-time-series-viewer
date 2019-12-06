# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    asd.py
    Reading Spectral Profiles from ASD data
    ---------------------
    Date                 : Aug 2019
    Copyright            : (C) 2019 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
"""

import os, sys, re, pathlib, json, enum, struct, time, datetime, typing, collections
import numpy as np
import csv as pycsv
from .spectrallibraries import *


"""

Offset Size Type Description Comment
3 char co[3]; // File Version - as6
3 157 char comments[157]; // comment field
160 18 struct tm when; // time when spectrum was saved
178 1 byte program_version; // ver. of the programcreatinf this file.
// major ver in upper nibble, min in lower
179 1 byte file_version; // spectrum file format version
180 1 byte itime; // Not used after v2.00
181 1 byte dc_corr; // 1 if DC subtracted, 0 if not
182 4 time_t (==long) dc_time; // Time of last dc, seconds since 1/1/1970
186 1 byte data_type; // see *_TYPE below
187 4 time_t (==long) ref_time; // Time of last wr, seconds since 1/1/1970
191 4 float ch1_wavel; // calibrated starting wavelength in nm
195 4 float wavel_step; // calibrated wavelength step in nm
199 1 byte data_format; // format of spectrum.
200 1 byte old_dc_count; // Num of DC measurements in the avg
201 1 byte old_ref_count; // Num of WR in the average
202 1 byte old_sample_count; // Num of spec samples in the avg
203 1 byte application; // Which application created APP_DATA
204 2 ushort channels; // Num of channels in the detector
206 128 APP_DATA app_data; // Application-specific data
334 56 GPS_DATA gps_data; // GPS position, course, etc.
390 4 ulong it; // The actual integration time in ms
394 2 int fo; // The fo attachment's view in degrees
396 2 int dcc; // The dark current correction value
398 2 uint calibration; // calibration series
400 2 uint instrument_num; // instrument number
402 4 float ymin; // setting of the y axis' min value
406 4 float ymax; // setting of the y axis' max value
410 4 float xmin; // setting of the x axis' min value
414 4 float xmax; // setting of the x axis' max value
418 2 uint ip_numbits; // instrument's dynamic range
420 1 byte xmode; // x axis mode. See *_XMODE
421 4 byte flags[4]; // flags(0) = AVGFIX'ed
// flags(1) see below
425 2 unsigned dc_count; // Num of DC measurements in the avg
427 2 unsigned ref_count; // Num of WR in the average
429 2 unsigned sample_count; // Num of spec samples in the avg
431 1 byte instrument; // Instrument type. See defs below
432 4 ulong bulb; // The id number of the cal bulb
436 2 uint swir1_gain; // gain setting for swir 1
438 2 uint swir2_gain; // gain setting for swir 2
440 2 uint swir1_offset; // offset setting for swir 1
442 2 uint swir2_offset; // offset setting for swir 2
444 4 float splice1_wavelength; // wavelength of VNIR and SWIR1 splice
448 4 float splice2_wavelength; // wavelength of SWIR1 and SWIR2 splice
452 27 float SmartDetectorType // Data from OL731 device
479 5 byte spare[5]; // fill to 484 bytes
"""

ASD_VERSIONS = ['ASD', 'asd', 'as6', 'as7', 'as8']


class SpectrumDataType(enum.IntEnum):

    RAW_TYPE = 0
    REF_TYPE = 1
    RAD_TYPE = 2
    NOUNITS_TYPE = 3
    IRRAD_TYPE = 4
    QI_TYPE = 5
    TRANS_TYPE = 6
    UNKNOWN_TYPE = 7
    ABS_TYPE = 8



class SpectrumDataFormat(enum.Enum):

    FLOAT_FORMAT = 0
    INTEGER_FORMAT = 1
    DOUBLE_FORMAT = 2
    UNKOWN_FORMAT = 3

class InstrumentType(enum.Enum):

    UNKOWN_INSTRUMENT = 0
    PSII_INSTRUMENT = 1
    LSVNIR_INSTRUMENT = 2
    FSVNIR_INSTRUMENT = 3
    FSFR_INSTRUMENT = 4
    FSNIR_INSTRUMENT = 5
    CHEM__INSTRUMENT = 6
    FSFR_UNATTENDED_INSTRUMENT = 7

class GPS_DATA(object):

    def __init__(self, DATA):
        ASD_GPS_DATA = struct.Struct("= 5d 2b cl 2b 5B 2c").unpack(DATA)


        self.true_heading = self.speed = self.latitude = self.longitude = self.altitude = ASD_GPS_DATA[0:5]
        self.flags = ASD_GPS_DATA[5:7]
        self.hardware_mode = ASD_GPS_DATA[7]
        self.timestamp = np.datetime64('1970-01-01') + np.timedelta64(ASD_GPS_DATA[8],'s')

class SmartDetectorType(object):

    def __init__(self, DATA):
        """

        :param DATA:
        """
        # 27 byte struct
        # 1 i int   4           4
        # 3 f float 12         16
        # 1 h short 2          18
        # 1 b byte  1          19
        # 2 f float 8          27

        if DATA is not None:
            DETECTOR = struct.Struct('= 1i 3f 1h 1b 2f').unpack(DATA)
        else:
            DETECTOR = [None, None, None, None, None, None, None, None]
        self.serial_number, self.Signal, self.dark, self.ref, self.Status, self.avg, self.humid, self.temp = DETECTOR




class TM_STRUCT(object):

    def __init__(self, DATA):
        self.tm_sec, self.tm_min, self.tm_hour, self.tm_mday, \
        self.tm_mon, self.tm_year, self.tm_wday, \
        self.tm_yday, self.tm_isdst = struct.Struct("= 9h").unpack(DATA)

    def date(self):
        return datetime.date(self.year(), self.month(), self.day())

    def datetime(self):
        return datetime.datetime(self.year(), self.month(), self.day(), hour=self.tm_hour, minute=self.tm_min, second=self.tm_sec)

    def time(self):
        return datetime.time(hour=self.tm_hour, minute=self.tm_min, second=self.tm_sec)

    def datetime64(self)->np.datetime64:
        return np.datetime64('{:04}-{:02}-{:02}T{:02}:{:02}:{:02}'.format(self.year(), self.month(), self.day(), self.tm_hour, self.tm_min, self.tm_sec))

    def doy(self)->int:
        return self.tm_yday

    def day(self)->int:
        return self.tm_mday

    def month(self)->int:
        return self.tm_mon + 1

    def year(self)->int:
        return self.tm_year + 1900


class ASDBinaryFile(object):
    """
    Wrapper class to access a ASD File Format binary file.
    See ASD File Format, version 8, revision B, ASD Inc., a PANalytical company, 2555 55th Street, Suite 100 Boulder, CO 80301.
    """


    def __init__(self):
        super(ASDBinaryFile, self).__init__()

        # initialize all variables in the ASD Binary file header
        self.co = None
        self.comments = None
        self.when = None
        self.program_version = None
        self.file_version = None
        self.itime = None
        self.dc_corr = None
        self.dc_time = None
        self.data_type = None
        self.ref_time = None
        self.ch1_wavel = None
        self.wavel_step = None
        self.data_format = None
        self.old_dc_count = None
        self.old_ref_count = None
        self.old_sample_count = None
        self.application = None
        self.channels = None
        self.app_data = None
        self.gps_data = None
        self.it = None
        self.fo = None
        self.dcc = None
        self.calibration = None
        self.instrument_num = None
        self.ymin = None
        self.ymax = None
        self.xmin = None
        self.ymax = None
        self.ip_numbits = None
        self.xmode = None
        self.flags = None
        self.dc_count = None
        self.ref_count = None
        self.sample_count = None
        self.instrument = None
        self.bulb = None
        self.swir1_gain = None
        self.swir2_gain = None
        self.swir1_offset = None
        self.swir2_offset = None
        self.splice1_wavelength = None
        self.splice2_wavelength = None
        self.SmartDetectorType = None
        self.spare = None


        self.Spectrum = None
        self.ReferenceFlag = None
        self.ReferenceTime = None
        self.SpectrumTime = None
        self.SpectrumDescription = None
        self.Reference = None


    def xValues(self)->np.ndarray:
        values = np.linspace(self.ch1_wavel, self.ch1_wavel + self.channels * self.wavel_step - 1, self.channels)
        return values


    def yValues(self)->np.ndarray:
        return self.Spectrum


    def readFromBinaryFile(self, path: str):
        with open(path, 'rb') as f:

            DATA = f.read()

            def sub(start, len):
                return DATA[start:start + len]


            self.co = DATA[0:3].decode('utf-8')
            self.comments = DATA[3:(3 + 157)].decode('utf-8')

            self.when = TM_STRUCT(DATA[160:(160 + 18)])
            self.program_version = DATA[178]
            self.file_version = DATA[179]
            self.itime = DATA[180]
            self.dc_corr = DATA[181]
            self.dc_time = np.datetime64('1970-01-01') + np.timedelta64(struct.unpack('l', DATA[182:182 + 4])[0], 's')
            self.data_type = SpectrumDataType(DATA[186])
            self.ref_time = np.datetime64('1970-01-01') + np.timedelta64(struct.unpack('l', DATA[182:182 + 4])[0], 's')
            self.ch1_wavel = struct.unpack('f', sub(191, 4))[0]
            self.wavel_step = struct.unpack('f', sub(195, 4))[0]
            self.data_format = SpectrumDataFormat(DATA[199])
            self.old_dc_count = DATA[200]
            self.old_ref_count = DATA[201]
            self.old_sample_count = DATA[202]
            self.application = DATA[203]

            self.channels = struct.unpack('H', sub(204, 2))[0]

            self.app_data = sub(206, 128)
            self.gps_data = GPS_DATA(sub(334, 56))

            self.it = struct.unpack('L', sub(390, 4))[0]
            self.fo = struct.unpack('h', sub(394, 2))[0]
            self.dcc = struct.unpack('h', sub(396, 2))[0]

            self.calibration = struct.unpack('H', sub(398, 2))[0]
            self.instrument_num = struct.unpack('H', sub(400, 2))[0]

            self.ymin, self.ymax, self.xmin, self.ymax = struct.unpack('4f', sub(402, 4 * 4))

            self.ip_numbits = struct.unpack('H', sub(418, 2))[0]
            self.xmode = struct.unpack('b', sub(420, 1))[0]
            self.flags = struct.unpack('4b', sub(421, 4))

            self.dc_count, self.ref_count, self.sample_count = struct.unpack('3H', sub(425, 2 * 3))

            self.instrument = sub(431, 1)
            self.bulb = struct.unpack('L', sub(432, 4))
            self.swir1_gain, self.swir2_gain, self.swir1_offset, self.swir2_offset = struct.unpack('4H', sub(436, 2 * 4))

            self.splice1_wavelength, self.splice2_wavelength = struct.unpack('2f', sub(444, 2 * 4))

            self.SmartDetectorType = SmartDetectorType(sub(452, 27))
            self.spare = sub(479, 5)

            if self.data_format == SpectrumDataFormat.FLOAT_FORMAT:
                size = 4 * self.channels
                fmt = '{}f'.format(self.channels)

            elif self.data_format == SpectrumDataFormat.DOUBLE_FORMAT:
                size = 8 * self.channels
                fmt = '{}d'.format(self.channels)
            elif self.data_format == SpectrumDataFormat.INTEGER_FORMAT:
                size = 4 * self.channels
                fmt = '{}i'.format(self.channels)
            else:
                raise Exception()

            self.Spectrum = np.array(struct.unpack(fmt, sub(484, size)))

        return self


class ASDSpectralLibraryIO(AbstractSpectralLibraryIO):


    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            pathes, filter = QFileDialog.getOpenFileNames(caption='ASD FilesCSV File',
                                               filter='All type (*.*);;Text files (*.txt);; CSV (*.csv);;ASD (*.asd)')

            if len(pathes) > 0:
                sl = ASDSpectralLibraryIO.readFrom(pathes)
                if isinstance(sl, SpectralLibrary):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add ASD profiles')
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        a = menu.addAction('ASD')
        a.setToolTip('Loads ASD FieldSpec files (binary or text)')
        a.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))


    @staticmethod
    def canRead(path, binary:bool=None)->bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        if not os.path.isfile(path):
            return False


        if isinstance(binary, bool):
            if binary:
                st = os.stat(path)

                if st.st_size < 484 + 1 or st.st_size > 2 ** 20:
                    return False

                with open(path, 'rb') as f:
                    DATA = f.read(3)
                    co = DATA[0:3].decode('utf-8')
                    if co not in ASD_VERSIONS:
                        return False
                    else:
                        return True

                return False
            else:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = []
                        for line in f:
                            if len(lines) >= 2:
                                break
                            line = line.strip()
                            if len(line) > 0:
                                lines.append(line)

                        if len(lines) == 2:
                            return re.search(r'^wavelength[;]', lines[0], re.I) is not None \
                                   and re.search(r'^\d+(\.\d+)?[;]', lines[1]) is not None

                        return False
                except Exception as ex:
                    return False

        else:
            if ASDSpectralLibraryIO.canRead(path, binary=True):
                return True
            else:
                return ASDSpectralLibraryIO.canRead(path, binary=False)



    @staticmethod
    def readFrom(pathes:typing.Union[str, list], asdFields:typing.Iterable[str] = None, progressDialog:QProgressDialog=None)->SpectralLibrary:
        """
        :param pathes: list of source paths
        :param asdFields: list of header information to be extracted from ASD binary files
        :return: SpectralLibrary
        """
        if asdFields is None:
            #default fields to add as meta data
            asdFields = ['when', 'ref_time', 'dc_time', 'dc_corr', 'it', 'sample_count', 'instrument_num', 'spec_type']

        if not isinstance(pathes, list):
            pathes = [pathes]

        sl = SpectralLibrary()

        profiles = []
        asddFieldsInitialized = False

        for filePath in pathes:
            bn = os.path.basename(filePath)

            if ASDSpectralLibraryIO.canRead(filePath, binary=True):
                asd = ASDBinaryFile().readFromBinaryFile(filePath)
                if isinstance(asd, ASDBinaryFile):

                    if not asddFieldsInitialized:
                        sl.startEditing()

                        asdFields = [n for n in asdFields if n not in sl.fieldNames() and n in asd.__dict__.keys()]
                        for n in asdFields:
                            v = asd.__dict__[n]
                            if isinstance(v, TM_STRUCT):
                                sl.addAttribute(createQgsField(n, '')) # TM struct will use a VARCHAR field to express the time stamp
                            else:
                                sl.addAttribute(createQgsField(n, v))

                        asddFieldsInitialized = True
                        sl.commitChanges()
                        sl.startEditing()

                    p = SpectralProfile(fields=sl.fields())
                    p.setName(bn)

                    for n in asdFields:
                        value = asd.__dict__[n]
                        if isinstance(value, np.datetime64):
                            value = str(value)
                        elif isinstance(value, TM_STRUCT):
                            value = str(value.datetime64())
                        p.setAttribute(n, value)

                    p.setValues(asd.xValues(), asd.yValues(), xUnit='nm')
                    profiles.append(p)
            elif ASDSpectralLibraryIO.canRead(filePath, binary=False):


                with open(filePath, 'r', encoding='utf-8') as f:
                    profiles = []
                    lines = f.readlines()
                    delimiter = ';'
                    if len(lines) >= 2:

                        hdrLine = lines[0].strip().split(delimiter)
                        if len(hdrLine) >= 2:
                            profileNames = hdrLine[1:]

                            xValues = []
                            DATA = dict()
                            for line in lines[1:]:
                                line = line.split(delimiter)
                                wl = float(line[0])
                                xValues.append(wl)
                                DATA[wl] = [float(v) for v in line[1:]]

                            for i, name in enumerate(profileNames):

                                yValues = [DATA[wl][i] for wl in xValues]
                                xUnit = 'nm'
                                profile = SpectralProfile(fields=sl.fields())
                                profile.setName(name)
                                profile.setValues(x=xValues, y=yValues, xUnit=xUnit)

                                profiles.append(profile)
                    if len(profiles) > 0:
                        sl.startEditing()
                        sl.addProfiles(profiles)
                        profiles.clear()
                        sl.commitChanges()
                        sl.startEditing()


            else:
                print('Unable to read {}'.format(filePath), file=sys.stderr)

        sl.startEditing()
        sl.addProfiles(profiles, addMissingFields=False)
        sl.commitChanges()
        return sl



