# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    stackedbandinput.py

    Sometimes time-series-data is written out as stacked band images, having one observation per band.
    This module helps to use such data as EOTS input.
    ---------------------
    Date                 : June 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import os
import copy
from osgeo import gdal
import numpy as np
from collections import OrderedDict
from xml.etree import ElementTree
from qgis.PyQt.QtCore import Qt, QModelIndex, QAbstractTableModel, QItemSelectionModel, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QHeaderView, QDialog, QDialogButtonBox, QFileDialog
from qgis.core import QgsRasterLayer, QgisInterface, QgsProviderRegistry, QgsProject
from qgis.gui import QgsFileWidget
import qgis.utils
from .utils import read_vsimem, loadUi
from .virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.dateparser import extractDateTimeGroup


def datesFromDataset(dataset: gdal.Dataset) -> list:
    nb = dataset.RasterCount

    def checkDates(dateList):
        if not len(dateList) == nb:
            return False
        for d in dateList:
            if not isinstance(d, np.datetime64):
                return False
        return True

    searchedKeysDataSet = []
    searchedKeysDataSet.append(re.compile('acquisition[ ]*dates$', re.I))
    searchedKeysDataSet.append(re.compile('observation[ ]*dates$', re.I))
    searchedKeysDataSet.append(re.compile('dates$', re.I))
    searchedKeysDataSet.append(re.compile('wavelength$', re.I))

    searchedKeysBand = []
    searchedKeysBand.append(re.compile('acquisition[ ]*date$', re.I))
    searchedKeysBand.append(re.compile('observation[ ]*date$', re.I))
    searchedKeysBand.append(re.compile('date$', re.I))
    searchedKeysBand.append(re.compile('wavelength$', re.I))

    # 1. Check Metadata
    for domain in dataset.GetMetadataDomainList():
        domainData = dataset.GetMetadata_Dict(domain)
        assert isinstance(domainData, dict)

        for key, values in domainData.items():
            for regex in searchedKeysDataSet:
                if regex.search(key.strip()):
                    values = re.sub(r'[{}]', '', values)
                    values = values.split(',')
                    dateValues = [extractDateTimeGroup(t) for t in values]
                    if checkDates(dateValues):
                        return dateValues

    # 2. Search in band metadata
    # 2.1. via GetDescription
    bandDates = [extractDateTimeGroup(dataset.GetRasterBand(b + 1).GetDescription()) for b in range(nb)]
    bandDates = [b for b in bandDates if isinstance(b, np.datetime64)]
    if checkDates(bandDates):
        return bandDates

    # 2.2 via Band Metadata
    bandDates = []
    for b in range(nb):
        band = dataset.GetRasterBand(b + 1)
        assert isinstance(band, gdal.Band)
        bandDate = None
        for domain in band.GetMetadataDomainList():

            md = band.GetMetadata_Dict(domain)

            candidates = []
            for k in md.keys():
                for rx in searchedKeysBand:
                    if rx.search(k):
                        candidates.append(k)

            for key in candidates:
                assert isinstance(key, str)
                DTG = extractDateTimeGroup(md[key])
                if isinstance(DTG, np.datetime64):
                    bandDate = DTG
                    break

            if isinstance(bandDate, np.datetime64):
                break

        if isinstance(bandDate, np.datetime64):
            bandDates.append(bandDate)

    if checkDates(bandDates):
        return bandDates

    return []


class InputStackInfo(object):

    def __init__(self, dataset):
        if isinstance(dataset, str):
            # test ENVI header first
            basename = os.path.splitext(dataset)[0]
            ds = None
            if os.path.isfile(basename + '.hdr'):
                ds = gdal.OpenEx(dataset, allowed_drivers=['ENVI'])
            if not isinstance(ds, gdal.Dataset):
                ds = gdal.Open(dataset)
            if not isinstance(ds, gdal.Dataset):
                raise Exception('Unable to open {}'.format(dataset))

            dataset = ds
            del ds

        assert isinstance(dataset, gdal.Dataset)

        self.mMetadataDomains = dataset.GetMetadataDomainList()
        self.mMetaData = OrderedDict()

        for domain in self.mMetadataDomains:
            self.mMetaData[domain] = dataset.GetMetadata_Dict(domain)

        self.ns = dataset.RasterXSize
        self.nl = dataset.RasterYSize
        self.nb = dataset.RasterCount

        self.wkt = dataset.GetProjection()
        self.gt = dataset.GetGeoTransform()

        self.colorTable = dataset.GetRasterBand(1).GetColorTable()
        self.classNames = dataset.GetRasterBand(1).GetCategoryNames()

        self.path = dataset.GetDescription()

        self.outputBandName = os.path.basename(self.path)
        if len(self.outputBandName) == 0:
            self.outputBandName = ''

        self.bandnames = []
        self.nodatavalues = []

        for b in range(self.nb):
            band = dataset.GetRasterBand(b + 1)
            assert isinstance(band, gdal.Band)
            self.bandnames.append(band.GetDescription())
            self.nodatavalues.append(band.GetNoDataValue())

        self.mDates = datesFromDataset(dataset)

    def __len__(self):
        return len(self.mDates)

    def dates(self) -> list:
        """Returns a list of dates"""
        return self.mDates

    def structure(self):
        return (self.ns, self.nl, self.nb, self.gt, self.wkt)

    def wavelength(self):
        return self.mMetaData[''].get('wavelength')

    def setWavelength(self, wl):
        self.mMetaData['']['wavelength'] = wl


class OutputVRTDescription(object):
    """
    Descrbies an output VRT
    """

    def __init__(self, path: str, date: np.datetime64):
        super(OutputVRTDescription, self).__init__()
        self.mPath = path
        self.mDate = date

    def setPath(self, path: str):
        self.mPath = path


class InputStackTableModel(QAbstractTableModel):

    def __init__(self, parent=None):

        super(InputStackTableModel, self).__init__(parent)
        self.mStackImages = []

        self.cn_source = 'Source'
        self.cn_dates = 'Dates'
        self.cn_crs = 'GT + CRS'
        self.cn_ns = 'ns'
        self.cn_nl = 'nl'
        self.cn_nb = 'nb'
        self.cn_name = 'Band Name'
        self.cn_wl = 'Wavelength'
        self.mColumnNames = [self.cn_source, self.cn_dates, self.cn_name, self.cn_wl, self.cn_ns, self.cn_nl,
                             self.cn_nb, self.cn_crs]

        self.mColumnTooltips = {}

        self.mColumnTooltips[self.cn_source] = 'Stack source uri / file path'
        self.mColumnTooltips[self.cn_crs] = 'Geo-Transformation + Coordinate Reference System'
        self.mColumnTooltips[self.cn_ns] = 'Number of samples / pixel in horizontal direction'
        self.mColumnTooltips[self.cn_nl] = 'Number of lines / pixel in vertical direction'
        self.mColumnTooltips[self.cn_nb] = 'Number of bands'
        self.mColumnTooltips[self.cn_name] = 'Prefix of band name in output image'
        self.mColumnTooltips[self.cn_wl] = 'Wavelength in output image'
        self.mColumnTooltips[self.cn_dates] = 'Identified dates'

    def __len__(self):
        return len(self.mStackImages)

    def __iter__(self):
        return iter(self.mStackImages)

    def columnName(self, i) -> str:
        if isinstance(i, QModelIndex):
            i = i.column()
        return self.mColumnNames[i]

    def dateInfo(self):
        """
        Returns a list with all extracted dates and a list of date in common between all datasets
        :return: [all dates], [dates in common]
        """
        if len(self) == 0:
            return [], []
        datesTotal = set()
        datesInCommon = None
        for i, f in enumerate(self.mStackImages):
            assert isinstance(f, InputStackInfo)

            dates = f.dates()
            if datesInCommon is None:
                datesInCommon = set(dates)
            else:
                datesInCommon = datesInCommon.intersection(dates)

            datesTotal = datesTotal.union(f.dates())

        return sorted(list(datesTotal)), sorted(list(datesInCommon))

    def flags(self, index):
        if index.isValid():
            columnName = self.columnName(index)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName in [self.cn_name, self.cn_wl]:  # allow check state
                flags = flags | Qt.ItemIsEditable

            return flags
            # return item.qt_flags(index.column())
        return None

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal:
            cname = self.mColumnNames[col]
            if role == Qt.DisplayRole:
                return cname
            elif role == Qt.ToolTipRole:
                return self.mColumnTooltips.get(cname)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def rowCount(self, parent=None):
        return len(self.mStackImages)

    def columnCount(self, parent: QModelIndex):
        return len(self.mColumnNames)

    def insertSources(self, paths, i=None):
        """
        Inserts new datasources
        :param paths: [list-of-datasources]
        :param i: index where to add the first datasource.
        """

        if i == None:
            i = self.rowCount()

        if not isinstance(paths, list):
            paths = [paths]

        infos = [InputStackInfo(p) for p in paths]
        if len(infos) > 0:

            self.beginInsertRows(QModelIndex(), i, i + len(infos) - 1)
            for j, info in enumerate(infos):
                assert isinstance(info, InputStackInfo)
                if len(info.outputBandName) == 0:
                    info.outputBandName = 'Band {}'.format(i + j + 1)
                self.mStackImages.insert(i + j, info)
            self.endInsertRows()

    def removeSources(self, stackInfos: list):

        for stackInfo in stackInfos:
            assert stackInfo in self.mStackImages

        for stackInfo in stackInfos:
            assert isinstance(stackInfo, InputStackInfo)

            idx = self.info2index(stackInfo)

            self.beginRemoveRows(QModelIndex(), idx.row(), idx.row())
            self.mStackImages.remove(stackInfo)
            self.endRemoveRows()

    def isValid(self):
        l = len(self.mStackImages)
        if l == 0:
            return False
        ref = self.mStackImages[0]
        assert isinstance(ref, InputStackInfo)

        # all input stacks need to have the same characteristic
        for stackInfo in self.mStackImages[1:]:
            assert isinstance(stackInfo, InputStackInfo)
            if not ref.dates() == stackInfo.dates():
                return False
            if not ref.structure() == stackInfo.structure():
                return False
        return True

    def index2info(self, index: QModelIndex) -> InputStackInfo:
        return self.mStackImages[index.row()]

    def info2index(self, info: InputStackInfo) -> QModelIndex:
        r = self.mStackImages.index(info)
        return self.createIndex(r, 0, info)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return None

        info = self.mStackImages[index.row()]
        assert isinstance(info, InputStackInfo)
        cname = self.columnName(index)

        if role in [Qt.DisplayRole, Qt.ToolTipRole]:
            if cname == self.cn_source:
                return info.path
            if cname == self.cn_dates:
                dates = info.dates()
                if role == Qt.DisplayRole:
                    return len(dates)
                if role == Qt.ToolTipRole:
                    if len(dates) == 0:
                        return 'No dates identified. Can not use this image as input'
                    else:
                        if len(dates) > 11:
                            dates = dates[0:10] + ['...']
                        return '\n'.join([str(d) for d in dates])

            if cname == self.cn_ns:
                return info.ns
            if cname == self.cn_nl:
                return info.nl
            if cname == self.cn_nb:
                return info.nb
            if cname == self.cn_crs:
                return '{} {}'.format(info.gt, info.wkt)
            elif cname == self.cn_wl:
                if '' in info.mMetaData.keys():
                    return info.mMetaData[''].get('wavelength')
                else:
                    return None
            elif cname == self.cn_name:
                return info.outputBandName

        if role == Qt.EditRole:
            if cname == self.cn_wl:
                if '' in info.mMetaData.keys():
                    return info.mMetaData[''].get('wavelength')
                else:
                    return None

            elif cname == self.cn_name:
                return info.outputBandName

        if role == Qt.BackgroundColorRole:
            if cname in [self.cn_name, self.cn_wl]:
                return QColor('yellow')

        return None

    def setData(self, index: QModelIndex, value, role: int):

        if not index.isValid():
            return None

        info = self.index2info(index)
        cname = self.columnName(index)

        changed = False
        if role == Qt.EditRole:
            if cname == self.cn_name:
                if isinstance(value, str) and len(value) > 0:
                    info.outputBandName = value
                    changed = True
            elif cname == self.cn_wl:
                info.setWavelength(value)
                changed = True
        if changed:
            self.dataChanged.emit(index, index)
        return changed


class OutputImageModel(QAbstractTableModel):

    def __init__(self, parent=None):
        super(OutputImageModel, self).__init__(parent)

        self.cn_uri = 'Path'
        self.cn_date = 'Date'
        self.mOutputImages = []

        self.mColumnNames = [self.cn_date, self.cn_uri]
        self.mColumnTooltips = {}
        self.mColumnTooltips[self.cn_uri] = 'Output location'
        self.masterVRT_DateLookup = {}
        self.masterVRT_SourceBandTemplates = {}
        self.masterVRT_InputStacks = None
        self.masterVRT_XML = None
        self.mOutputDir = '/vsimem/'
        self.mOutputPrefix = 'date'

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal:
            cname = self.mColumnNames[col]
            if role == Qt.DisplayRole:
                return cname
            elif role == Qt.ToolTipRole:
                return self.mColumnTooltips.get(cname)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def createVRTUri(self, date: np.datetime64):

        path = os.path.join(self.mOutputDir, self.mOutputPrefix)
        path = '{}{}.vrt'.format(path, date)

        return path

    def clearOutputs(self):
        self.beginRemoveRows(QModelIndex(), 0, self.rowCount() - 1)
        self.mOutputImages = []
        self.endRemoveRows()

    def setMultiStackSources(self, listOfInputStacks: list, dates: list):

        self.clearOutputs()

        if listOfInputStacks is None or len(listOfInputStacks) == 0:
            return
        if dates is None or len(dates) == 0:
            return
        for s in listOfInputStacks:
            assert isinstance(s, InputStackInfo)
        dates = sorted(dates)

        listOfInputStacks = [s for s in listOfInputStacks if len(s) > 0]
        numberOfOutputVRTBands = len(listOfInputStacks)
        self.masterVRT_DateLookup.clear()
        self.masterVRT_InputStacks = listOfInputStacks
        self.masterVRT_SourceBandTemplates.clear()
        # dates = set()
        # for s in listOfInputStacks:
        #    for d in s.dates():
        #        dates.add(d)
        # dates = sorted(list(dates))

        # create a LUT to get the stack indices for a related date (not each stack might contain a band for each date)

        for stackIndex, s in enumerate(listOfInputStacks):
            for bandIndex, bandDate in enumerate(s.dates()):
                if bandDate not in self.masterVRT_DateLookup.keys():
                    self.masterVRT_DateLookup[bandDate] = []
                self.masterVRT_DateLookup[bandDate].append((stackIndex, bandIndex))

        # create VRT Template XML
        VRT = VRTRaster()
        wavelength = []
        for stackIndex, stack in enumerate(listOfInputStacks):
            assert isinstance(stack, InputStackInfo)
            vrtBand = VRTRasterBand()
            vrtBand.setName(stack.outputBandName)
            vrtSrc = VRTRasterInputSourceBand(stack.path, 0)
            vrtBand.addSource(vrtSrc)
            wavelength.append(stack.wavelength())
            VRT.addVirtualBand(vrtBand)

        pathVSITmp = '/vsimem/temp.vrt'
        dsVRT = VRT.saveVRT(pathVSITmp)
        dsVRT.SetMetadataItem('acquisition date', 'XML_REPLACE_DATE')

        if None not in wavelength:
            dsVRT.SetMetadataItem('wavelength', ','.join(str(wl) for wl in wavelength))
            dsVRT.SetMetadataItem('wavelength units', 'Nanometers')

        for stackIndex, stack in enumerate(listOfInputStacks):
            band = dsVRT.GetRasterBand(stackIndex + 1)
            assert isinstance(band, gdal.Band)
            assert isinstance(stack, InputStackInfo)
            if isinstance(stack.colorTable, gdal.ColorTable) and stack.colorTable.GetCount() > 0:
                band.SetColorTable(stack.colorTable)
            if stack.classNames:
                band.SetCategoryNames(stack.classNames)

        dsVRT.FlushCache()
        drv = dsVRT.GetDriver()
        masterVRT_XML = read_vsimem(pathVSITmp).decode('utf-8')
        drv.Delete(pathVSITmp)
        outputVRTs = []

        eTree = ElementTree.fromstring(masterVRT_XML)
        for iBand, elemBand in enumerate(eTree.findall('VRTRasterBand')):
            sourceElements = elemBand.findall('ComplexSource') + elemBand.findall('SimpleSource')
            assert len(sourceElements) == 1
            self.masterVRT_SourceBandTemplates[iBand] = copy.deepcopy(sourceElements[0])
            elemBand.remove(sourceElements[0])

        for date in dates:
            assert isinstance(date, np.datetime64)
            path = self.createVRTUri(date)
            outputDescription = OutputVRTDescription(path, date)
            outputVRTs.append(outputDescription)

        self.masterVRT_XML = eTree

        self.beginInsertRows(QModelIndex(), 0, len(outputVRTs) - 1)
        self.mOutputImages = outputVRTs[:]
        self.endInsertRows()

    def setOutputDir(self, path: str):
        self.mOutputDir = path
        self.updateOutputURIs()

    def setOutputPrefix(self, basename: str):
        self.mOutputPrefix = basename
        self.updateOutputURIs()

    def updateOutputURIs(self):
        c = self.mColumnNames.index(self.cn_uri)
        ul = self.createIndex(0, c)
        lr = self.createIndex(self.rowCount() - 1, c)

        for outputVRT in self:
            assert isinstance(outputVRT, OutputVRTDescription)
            outputVRT.setPath(self.createVRTUri(outputVRT.mDate))
        self.dataChanged.emit(ul, lr)

    def __len__(self):
        return len(self.mOutputImages)

    def __iter__(self):
        return iter(self.mOutputImages)

    def rowCount(self, parent=None) -> int:
        return len(self.mOutputImages)

    def columnCount(self, parent=None) -> int:
        return len(self.mColumnNames)

    def columnName(self, i) -> str:
        if isinstance(i, QModelIndex):
            i = i.column()
        return self.mColumnNames[i]

    def columnIndex(self, columnName: str) -> QModelIndex:
        c = self.mColumnNames.index(columnName)
        return self.createIndex(0, c)

    def index2vrt(self, index: QModelIndex) -> OutputVRTDescription:
        return self.mOutputImages[index.row()]

    def vrt2index(self, vrt: OutputVRTDescription) -> QModelIndex:
        i = self.mOutputImages[vrt]
        return self.createIndex(i, 0, vrt)

    def data(self, index: QModelIndex, role: int):

        if not index.isValid():
            return None

        cname = self.columnName(index)
        vrt = self.index2vrt(index)
        if role in [Qt.DisplayRole, Qt.ToolTipRole]:
            if cname == self.cn_uri:
                return vrt.mPath
            if cname == self.cn_date:
                return str(vrt.mDate)

    def vrtXML(self, outputDefinition: OutputVRTDescription, asElementTree=False) -> str:
        """
        Create the VRT XML related to an outputDefinition
        :param outputDefinition:
        :return: str
        """

        # re.search(tmpXml, '<MDI key='>')

        # xml = copy.deepcopy(eTree)
        if self.masterVRT_XML is None:
            return None
        # xmlTree = ElementTree.fromstring(self.masterVRT_XML)
        xmlTree = copy.deepcopy(self.masterVRT_XML)

        # set metadata
        for elem in xmlTree.findall('Metadata/MDI'):
            if elem.attrib['key'] == 'acquisition date':
                elem.text = str(outputDefinition.mDate)

        # insert required rasterbands
        requiredBands = self.masterVRT_DateLookup[outputDefinition.mDate]

        xmlVRTBands = xmlTree.findall('VRTRasterBand')

        for t in requiredBands:
            stackIndex, stackBandIndex = t

            stackSourceXMLTemplate = copy.deepcopy(self.masterVRT_SourceBandTemplates[stackIndex])
            stackSourceXMLTemplate.find('SourceBand').text = str(stackBandIndex + 1)
            xmlVRTBands[stackIndex].append(stackSourceXMLTemplate)

        if asElementTree:
            return xmlTree
        else:
            return ElementTree.tostring(xmlTree).decode('utf-8')


class StackedBandInputDialog(QDialog):

    def __init__(self, parent=None):

        super(StackedBandInputDialog, self).__init__(parent=parent)
        loadUi(DIR_UI / 'stackedinputdatadialog.ui', self)
        self.setWindowTitle('Stacked Time Series Data Input')
        self.mWrittenFiles = []

        self.tableModelInputStacks = InputStackTableModel()
        self.tableModelInputStacks.rowsInserted.connect(self.updateOutputs)
        self.tableModelInputStacks.dataChanged.connect(self.updateOutputs)
        self.tableModelInputStacks.rowsRemoved.connect(self.updateOutputs)
        self.tableModelInputStacks.rowsInserted.connect(self.updateInputInfo)
        self.tableModelInputStacks.rowsRemoved.connect(self.updateInputInfo)
        self.tableViewSourceStacks.setModel(self.tableModelInputStacks)

        self.tableModelOutputImages = OutputImageModel()
        self.tableModelOutputImages.rowsInserted.connect(self.updateOutputInfo)
        self.tableModelOutputImages.rowsRemoved.connect(self.updateOutputInfo)
        self.tableModelOutputImages.dataChanged.connect(self.updateOutputInfo)
        self.tableViewOutputImages.setModel(self.tableModelOutputImages)
        self.tableViewOutputImages.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.buttonGroupDateMode.buttonClicked.connect(self.updateOutputs)
        self.buttonGroupOutputLocation.buttonClicked.connect(self.updateOutputs)

        self.cbOpenInQGIS.setEnabled(isinstance(qgis.utils.iface, QgisInterface))
        self.tbFilePrefix.textChanged.connect(self.tableModelOutputImages.setOutputPrefix)
        self.tbFilePrefix.setText('img')

        self.fileWidgetOutputDir.setStorageMode(QgsFileWidget.GetDirectory)
        self.fileWidgetOutputDir.fileChanged.connect(self.tableModelOutputImages.setOutputDir)

        sm = self.tableViewSourceStacks.selectionModel()
        assert isinstance(sm, QItemSelectionModel)
        sm.selectionChanged.connect(self.onSourceStackSelectionChanged)
        self.onSourceStackSelectionChanged([], [])

        sm = self.tableViewOutputImages.selectionModel()
        assert isinstance(sm, QItemSelectionModel)
        sm.selectionChanged.connect(self.onOutputImageSelectionChanged)

        self.initActions()

    def writtenFiles(self):
        """
        Returns the files written after pressing the "Save" button.
        :return: [list-of-written-file-paths]
        """
        return self.mWrittenFiles[:]

    def updateOutputs(self, *args):
        """
        Updates the output file information
        """
        self.tableModelOutputImages.clearOutputs()
        inputStacks = self.tableModelInputStacks.mStackImages
        datesTotal, datesIntersection = self.tableModelInputStacks.dateInfo()
        if self.rbDatesAll.isChecked():
            self.tableModelOutputImages.setMultiStackSources(inputStacks, datesTotal)
        elif self.rbDatesIntersection.isChecked():
            self.tableModelOutputImages.setMultiStackSources(inputStacks, datesIntersection)

        if self.rbSaveInMemory.isChecked():
            self.tableModelOutputImages.setOutputDir(r'/vsimem/')
        elif self.rbSaveInDirectory.isChecked():
            self.tableModelOutputImages.setOutputDir(self.fileWidgetOutputDir.filePath())

    def updateInputInfo(self):
        """
        Updates the input file information
        """

        n = len(self.tableModelInputStacks)
        datesTotal, datesInCommon = self.tableModelInputStacks.dateInfo()
        info = None
        if n > 0:
            nAll = len(datesTotal)
            nInt = len(datesInCommon)
            info = '{} Input Images with {} dates in total, {} in intersection'.format(n, nAll, nInt)

        self.tbInfoInputImages.setText(info)

    def updateOutputInfo(self):

        n = len(self.tableModelOutputImages)
        info = None
        if n > 0:
            nb = len(self.tableModelOutputImages.masterVRT_InputStacks)
            info = '{} output images with {} bands to {}'.format(n, nb, self.tableModelOutputImages.mOutputDir)
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(n > 0)
        self.tbInfoOutputImages.setText(info)

    def initActions(self):
        """
        Initializes QActions and what they trigger.
        """

        self.actionAddSourceStack.triggered.connect(self.onAddSource)
        self.actionRemoveSourceStack.triggered.connect(self.onRemoveSources)

        self.btnAddSourceStack.setDefaultAction(self.actionAddSourceStack)
        self.btnRemoveSourceStack.setDefaultAction(self.actionRemoveSourceStack)

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(self.accept)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.close)

    def onAddSource(self, *args):
        """
        Reacts on new added datasets
        """
        import eotimeseriesviewer.settings
        defDir = eotimeseriesviewer.settings.value(eotimeseriesviewer.settings.Keys.RasterSourceDirectory)
        filters = QgsProviderRegistry.instance().fileVectorFilters()
        files, filter = QFileDialog.getOpenFileNames(directory=defDir, filter=filters)

        if len(files) > 0:
            self.tableModelInputStacks.insertSources(files)
            defDir = os.path.dirname(files[0])
            eotimeseriesviewer.settings.setValue(eotimeseriesviewer.settings.Keys.RasterSourceDirectory, defDir)

    def addSources(self, paths):
        """
        Adds new datasources
        :param paths: [list-of-new-datasources]
        :return:
        """
        self.tableModelInputStacks.insertSources(paths)

    def onRemoveSources(self, *args):
        """
        :param args:
        """
        model = self.tableViewSourceStacks.selectionModel()
        assert isinstance(model, QItemSelectionModel)

        infos = [self.tableModelInputStacks.index2info(idx) for idx in model.selectedRows()]
        self.tableModelInputStacks.removeSources(infos)

    def onSourceStackSelectionChanged(self, selected, deselected):
        """
        :param selected:
        :param deselected:
        """
        self.actionRemoveSourceStack.setEnabled(len(selected) > 0)

    def onOutputImageSelectionChanged(self, selected, deselected):

        if len(selected) > 0:
            idx = selected.indexes()[0]

            vrtOutput = self.tableModelOutputImages.index2vrt(idx)
            assert isinstance(vrtOutput, OutputVRTDescription)
            xml = self.tableModelOutputImages.vrtXML(vrtOutput)
            self.tbXMLPreview.setPlainText(xml)
        else:
            self.tbXMLPreview.setPlainText(None)
            s = ""

    def saveImages(self):
        """
        Write the VRT images
        :return: [list-of-written-file-paths]
        """

        nTotal = len(self.tableModelOutputImages)
        writtenFiles = []
        if nTotal == 0:
            return writtenFiles

        self.progressBar.setValue(0)
        from eotimeseriesviewer.virtualrasters import write_vsimem, read_vsimem
        for i, outVRT in enumerate(self.tableModelOutputImages):
            assert isinstance(outVRT, OutputVRTDescription)
            xml = self.tableModelOutputImages.vrtXML(outVRT)

            if outVRT.mPath.startswith('/vsimem/'):
                write_vsimem(outVRT.mPath, xml)
            else:
                f = open(outVRT.mPath, 'w', encoding='utf-8')
                f.write(xml)
                f.flush()
                f.close()

            writtenFiles.append(outVRT.mPath)

            self.progressBar.setValue(int(100. * i / nTotal))

        QTimer.singleShot(500, lambda: self.progressBar.setValue(0))

        if self.cbOpenInQGIS.isEnabled() and self.cbOpenInQGIS.isChecked():
            mapLayers = [QgsRasterLayer(p) for p in writtenFiles]
            QgsProject.instance().addMapLayers(mapLayers, addToLegend=True)
        self.mWrittenFiles.extend(writtenFiles)
        return writtenFiles
