import os
import pathlib
import re
from typing import List

from qgis.PyQt.QtCore import pyqtSignal, QDir, QItemSelectionModel, QMimeData, QModelIndex, QRegExp, \
    QSortFilterProxyModel, \
    Qt, QUrl
from qgis.PyQt.QtGui import QContextMenuEvent, QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from qgis.PyQt.QtWidgets import QAbstractItemView, QAction, QHeaderView, QMainWindow, QMenu, QToolBar, QTreeView
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject
from qgis.gui import QgisInterface, QgsDockWidget
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi, SpatialExtent
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource
from eotimeseriesviewer.timeseries.timeseries import TimeSeries


class TimeSeriesTreeView(QTreeView):
    sigMoveToDate = pyqtSignal(TimeSeriesDate)
    sigMoveToSource = pyqtSignal(TimeSeriesSource)
    sigMoveToExtent = pyqtSignal(SpatialExtent)
    sigSetMapCrs = pyqtSignal(QgsCoordinateReferenceSystem)

    def __init__(self, parent=None):
        super(TimeSeriesTreeView, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        md: QMimeData = event.mimeData()
        for format in TimeSeriesSource.MIMEDATA_FORMATS:
            if format in md.formats():
                event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        md: QMimeData = event.mimeData()
        local_files = []
        local_ts_lists = []
        if md.hasUrls():
            for url in md.urls():
                url: QUrl
                if url.isLocalFile():
                    path = pathlib.Path(url.toLocalFile())
                    if re.search(r'\.(txt|csv)$', path.name):
                        local_ts_lists.append(path)
                    else:
                        local_files.append(path)
        event.acceptProposedAction()
        if len(local_files) > 0:
            self.timeseries().addSources(local_files)
        if len(local_ts_lists) > 0:
            for file in local_ts_lists:
                self.timeseries().loadFromFile(file)

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        idx = self.indexAt(event.pos())
        node = self.model().data(idx, role=Qt.UserRole)

        selectedTSDs = []
        selectedTSSs = []
        for idx in self.selectionModel().selectedRows():
            node = idx.data(Qt.UserRole)
            if isinstance(node, TimeSeriesDate):
                selectedTSDs.append(node)
                selectedTSSs.extend(node[:])
            if isinstance(node, TimeSeriesSource):
                selectedTSSs.append(node)
        selectedTSSs = sorted(set(selectedTSSs))

        menu = QMenu(self)

        a = menu.addAction('Copy path(s)')
        a.setEnabled(len(selectedTSSs) > 0)
        a.triggered.connect(lambda _, tss=selectedTSSs: self.setClipboardUris(tss))
        a.setToolTip('Copy path(s) to clipboard.')
        a = menu.addAction('Copy value(s)')
        a.triggered.connect(lambda: self.onCopyValues())
        menu.addSeparator()

        if isinstance(node, TimeSeriesDate):
            a = menu.addAction('Move to date {}'.format(node.dtgString()))
            a.setToolTip(f'Sets the current map date to {node.dtg()}.')
            a.triggered.connect(lambda *args, tsd=node: self.sigMoveToDate.emit(tsd))

            a = menu.addAction('Move to extent {}'.format(node.spatialExtent()))
            a.setToolTip('Sets the current map extent')
            a.triggered.connect(lambda *args, tsd=node: self.onMoveToExtent(tsd.spatialExtent()))

            menu.addSeparator()

        elif isinstance(node, TimeSeriesSource):

            a = menu.addAction('Show {}'.format(node.name()))
            a.setToolTip(
                f'Sets the current map date to {node.dtg()} and zooms\nto the spatial extent of {node.source()}')
            a.triggered.connect(lambda *args, tss=node: self.sigMoveToSource.emit(tss))

            a = menu.addAction(f'Set map CRS from {node.name()}')
            a.setToolTip(f'Sets the map projection to {node.crs().description()}')
            a.triggered.connect(lambda *args, crs=node.crs(): self.sigSetMapCrs.emit(crs))

            menu.addSeparator()

        a = menu.addAction('Set date(s) invisible')
        a.setToolTip('Hides the selected time series dates from being shown in a map.')
        a.triggered.connect(lambda *args, tsds=selectedTSDs: self.timeseries().showTSDs(tsds, False))
        a = menu.addAction('Set date(s) visible')
        a.setToolTip('Shows the selected time series dates in maps.')
        a.triggered.connect(lambda *args, tsds=selectedTSDs: self.timeseries().showTSDs(tsds, True))

        menu.addSeparator()

        a = menu.addAction('Open in QGIS')
        a.setToolTip('Adds the selected images to the QGIS map canvas')
        a.triggered.connect(lambda *args, tss=selectedTSSs: self.openInQGIS(tss))

        menu.popup(QCursor.pos())

    def onMoveToExtent(self, extent: SpatialExtent):
        if isinstance(extent, SpatialExtent):
            self.sigMoveToExtent.emit(extent)

    def openInQGIS(self, tssList: List[TimeSeriesSource]):
        import qgis.utils
        iface = qgis.utils.iface
        if isinstance(iface, QgisInterface):
            layers = [tss.asRasterLayer() for tss in tssList]
            QgsProject.instance().addMapLayers(layers, True)

    def setClipboardUris(self, tssList: List[TimeSeriesSource]):
        urls = []
        paths = []
        for tss in tssList:
            uri = tss.source()
            if os.path.isfile(uri):
                url = QUrl.fromLocalFile(uri)
                paths.append(QDir.toNativeSeparators(uri))
            else:
                url = QUrl(uri)
                paths.append(uri)
            urls.append(url)
        md = QMimeData()
        md.setText('\n'.join(paths))
        md.setUrls(urls)

        QgsApplication.clipboard().setMimeData(md)

    def timeseries(self) -> TimeSeries:
        return self.model().sourceModel()

    def onSetCheckState(self, tsds: List[TimeSeriesDate], checkState: Qt.CheckStateRole):
        """
        Sets a ChecState to all selected rows
        :param checkState: Qt.CheckState
        """

    def onCopyValues(self, delimiter='\t'):
        """
        Copies selected cell values to the clipboard
        """
        indices = self.selectionModel().selectedIndexes()
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            from collections import OrderedDict
            R = OrderedDict()
            for idx in indices:
                if not idx.row() in R.keys():
                    R[idx.row()] = []
                R[idx.row()].append(model.data(idx, Qt.DisplayRole))
            info = []
            for k, values in R.items():
                info.append(delimiter.join([str(v) for v in values]))
            info = '\n'.join(info)
            QgsApplication.clipboard().setText(info)


class TimeSeriesFilterModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setRecursiveFilteringEnabled(True)
        # self.setSortRole(Qt.EditRole)
        # self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        reg = self.filterRegExp()
        if reg.isEmpty():
            return True

        for c in range(self.sourceModel().columnCount()):
            idx = self.sourceModel().index(sourceRow, c, parent=sourceParent)
            value = idx.data(Qt.DisplayRole)
            value = str(value)
            if reg.indexIn(value) >= 0:
                return True

        return False


class TimeSeriesWidget(QMainWindow):
    sigTimeSeriesDatesSelected = pyqtSignal(bool)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(DIR_UI / 'timeserieswidget.ui', self)

        self.mTimeSeriesTreeView: TimeSeriesTreeView
        assert isinstance(self.mTimeSeriesTreeView, TimeSeriesTreeView)
        self.mTimeSeries: TimeSeries = None
        self.mTSProxyModel: TimeSeriesFilterModel = TimeSeriesFilterModel()
        self.mSelectionModel = None
        self.mLastDate: TimeSeriesDate = None
        self.optionFollowCurrentDate: QAction
        self.optionFollowCurrentDate.toggled.connect(lambda: self.setCurrentDate(self.mLastDate))
        self.optionUseRegex: QAction
        self.optionCaseSensitive: QAction
        self.btnUseRegex.setDefaultAction(self.optionUseRegex)
        self.btnCaseSensitive.setDefaultAction(self.optionCaseSensitive)
        self.optionCaseSensitive.toggled.connect(self.onFilterExpressionChanged)
        self.optionUseRegex.toggled.connect(self.onFilterExpressionChanged)
        self.tbFilterExpression.textChanged.connect(self.onFilterExpressionChanged)

    def onFilterExpressionChanged(self, *args):
        expression: str = self.tbFilterExpression.text()

        useRegex: bool = self.optionUseRegex.isChecked()

        if self.optionCaseSensitive.isChecked():
            sensitivity = Qt.CaseSensitive
        else:
            sensitivity = Qt.CaseInsensitive
        self.mTSProxyModel.setFilterCaseSensitivity(sensitivity)
        if useRegex:
            rx = QRegExp(expression, sensitivity)
            self.mTSProxyModel.setFilterRegExp(rx)
        else:
            self.mTSProxyModel.setFilterWildcard(expression)

    def toolBar(self) -> QToolBar:
        return self.mToolBar

    def setCurrentDate(self, tsd: TimeSeriesDate):
        """
        Checks if optionFollowCurrentDate is checked. If True, will call setTSD to focus on the TimeSeriesDate
        :param tsd: TimeSeriesDate
        :type tsd:
        :return:
        :rtype:
        """
        self.mLastDate = tsd
        if not isinstance(tsd, TimeSeriesDate):
            return
        if self.optionFollowCurrentDate.isChecked():
            self.moveToDate(tsd)

    def moveToDate(self, tsd: TimeSeriesDate):
        tstv = self.timeSeriesTreeView()
        assert isinstance(tstv, TimeSeriesTreeView)
        assert isinstance(self.mTSProxyModel, QSortFilterProxyModel)

        assert isinstance(self.mTimeSeries, TimeSeries)
        idxSrc = self.mTimeSeries.tsdToIdx(tsd)

        if isinstance(idxSrc, QModelIndex):
            idx2 = self.mTSProxyModel.mapFromSource(idxSrc)
            if isinstance(idx2, QModelIndex):
                tstv.setCurrentIndex(idx2)
                tstv.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

    def updateSummary(self):

        if isinstance(self.mTimeSeries, TimeSeries):
            if len(self.mTimeSeries) == 0:
                info = 'Empty TimeSeries. Please add source images.'
            else:
                nDates = self.mTimeSeries.rowCount()
                nSensors = len(self.mTimeSeries.sensors())
                nImages = len(list(self.mTimeSeries.sources()))

                info = '{} dates, {} sensors, {} source images'.format(nDates, nSensors, nImages)
        else:
            info = ''
        self.mStatusBar.showMessage(info, 0)

    def onSelectionChanged(self, *args):
        """
        Slot to react on user-driven changes of the selected TimeSeriesDate rows.
        """
        b = isinstance(self.mSelectionModel, QItemSelectionModel) and len(self.mSelectionModel.selectedRows()) > 0

        self.sigTimeSeriesDatesSelected.emit(b)

    def selectedTimeSeriesDates(self) -> list:
        """
        Returns the TimeSeriesDate selected by a user.
        :return: [list-of-TimeSeriesDate]
        """
        results = []
        if isinstance(self.mSelectionModel, QItemSelectionModel):
            for idx in self.mSelectionModel.selectedRows():
                tsd = self.mTSProxyModel.data(idx, Qt.UserRole)
                if isinstance(tsd, TimeSeriesSource):
                    tsd = tsd.timeSeriesDate()
                if isinstance(tsd, TimeSeriesDate) and tsd not in results:
                    results.append(tsd)
        return results

    def timeSeries(self) -> TimeSeries:
        """
        Returns the connected TimeSeries
        :return: TimeSeries
        """
        return self.mTimeSeries

    def setTimeSeries(self, TS: TimeSeries):
        """
        Sets the TimeSeries to be shown in the TimeSeriesDockUI
        :param TS: TimeSeries
        """
        if isinstance(TS, TimeSeries):
            self.mTimeSeries = TS
            self.mTSProxyModel.setSourceModel(self.mTimeSeries)
            self.mSelectionModel = QItemSelectionModel(self.mTSProxyModel)
            self.mSelectionModel.selectionChanged.connect(self.onSelectionChanged)

            tstv = self.timeSeriesTreeView()
            tstv.setModel(self.mTSProxyModel)
            tstv.setSelectionModel(self.mSelectionModel)
            tstv.sortByColumn(0, Qt.AscendingOrder)

            for c in range(self.mTSProxyModel.columnCount()):
                self.timeSeriesTreeView().header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.mTimeSeries.rowsInserted.connect(self.updateSummary)
            # self.mTimeSeries.dataChanged.connect(self.updateSummary)
            self.mTimeSeries.rowsRemoved.connect(self.updateSummary)
            # TS.sigLoadingProgress.connect(self.setProgressInfo)

        self.onSelectionChanged()

    def timeSeriesTreeView(self) -> TimeSeriesTreeView:
        return self.mTimeSeriesTreeView


class TimeSeriesDock(QgsDockWidget):
    """
    QgsDockWidget that wraps the TimeSeriesWidget
    """

    def __init__(self, parent=None):
        super(TimeSeriesDock, self).__init__(parent)
        self.setWindowTitle('Time Series')
        self.mTimeSeriesWidget = TimeSeriesWidget()
        self.setWidget(self.mTimeSeriesWidget)

    def timeSeriesWidget(self) -> TimeSeriesWidget:
        return self.mTimeSeriesWidget
