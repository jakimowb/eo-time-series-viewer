from typing import Iterator, List, Optional, Union

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QContextMenuEvent, QCursor, QPainter, QPalette
from qgis.PyQt.QtWidgets import QLabel, QMenu, QStyledItemDelegate, QStyleOptionViewItem, QTableView
from qgis.core import QgsExpression, QgsVectorLayer
from qgis.gui import QgsFieldExpressionWidget

from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle, PlotStyleButton, PlotStyleDialog
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.plotsettings import PlotSettingsContextGenerator
from eotimeseriesviewer.temporalprofile.plotstyle import TemporalProfilePlotStyle
from eotimeseriesviewer.timeseries import TimeSeries
from eotimeseriesviewer.sensors import SensorInstrument


class PlotSettingsTableModel(QAbstractTableModel):
    cSensor = 0
    cExpression = 1
    cStyle = 2
    cFilter = 3
    cLabel = 4

    def __init__(self, layer: QgsVectorLayer = None, timeSeries: TimeSeries = None, parent=None, *args):
        super(PlotSettingsTableModel, self).__init__(parent=parent)

        # self.mTemporalProfileLayer.featureAdded.connect(self.onTemporalProfilesAdded)
        # self.mTemporalProfileLayer.featuresDeleted.connect(self.onTemporalProfilesDeleted)
        # self.mTemporalProfileLayer.sigTemporalProfilesUpdated.connect(self.onTemporalProfilesUpdated)
        self.columnNames = {self.cSensor: 'Sensor',
                            self.cExpression: 'Expression',
                            self.cStyle: 'Style',
                            }

        self.mPlotStyles: List[TemporalProfilePlotStyle] = []
        self.mIconSize = QSize(25, 25)
        self.mTemporalProfileLayer: Optional[QgsVectorLayer] = None
        self.mTimeSeries: Optional[TimeSeries] = None

        if timeSeries:
            self.setTimeSeries(timeSeries)

        if layer:
            self.setLayer(layer)

        self.mPlotWidget: DateTimePlotWidget = None

    def profileStyles(self) -> List[TemporalProfilePlotStyle]:
        return [s for s in self.mPlotStyles if s.isVisible()]

    def setPlotWidget(self, plotWidget: DateTimePlotWidget):
        self.mPlotWidget = plotWidget

    def plotWidget(self) -> DateTimePlotWidget:
        return self.mPlotWidget

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mTemporalProfileLayer, QgsVectorLayer):
            # disconnect signals
            pass

        self.mTemporalProfileLayer = layer

    def updatePlot(self):

        pw = self.plotWidget()
        pw.plotItem.clear()

        style = self.multiSensorProfilePlotStyle()

        for feature in self.mModel.temporalProfileLayer().getFeatures():

            for style in styles:
                exp = QgsExpression(style.expression())

    def setTimeSeries(self, timeSeries: TimeSeries):

        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensors)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensors)
        self.addSensors(timeSeries.sensors())

    def addSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):
        """
        Create a new plotstyle for this sensor
        :param sensor:
        :return:
        """

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        sensors = [s for s in sensors if s.id() not in self.sensorIds()]

        if len(sensors) == 0:
            return

        styles = [MultiSensorProfileStyle.defaultSensorStyle(s) for s in sensors]
        parent = QModelIndex()
        row0 = len(self.mPlotStyles)
        rowN = row0 + len(styles) - 1
        self.beginInsertRows(parent, row0, rowN)
        self.mPlotStyles.extend(styles)
        self.endInsertRows()

    def sensorIds(self) -> List[str]:
        """
        Returns the sensor ids for which plot styles exists
        :return:
        """
        return [s.sensor().id() for s in self.mPlotStyles]

    def removeSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        sensors = [s for s in sensors if s.id() in self.sensorIds()]
        for sensor in sensors:
            sid = sensor.id()
            while sid in (sids := self.sensorIds()):
                row = sids.index(sid)
                parent = QModelIndex()
                self.beginRemoveRows(parent, row, row)
                self.mTemporalProfileLayer.remove(row)
                self.endRemoveRows()

    def timeSeries(self) -> TimeSeries:
        return self.mTimeSeries

    def temporalProfileLayer(self) -> QgsVectorLayer:
        return self.mTemporalProfileLayer

    def temporalProfileStyles(self) -> List[TemporalProfilePlotStyle]:
        return self.mPlotStyles[:]

    def __len__(self):
        return len(self.mPlotStyles)

    def __iter__(self) -> Iterator[TemporalProfilePlotStyle]:
        return iter(self.mPlotStyles)

    def __getitem__(self, slice):
        return self.mPlotStyles[slice]

    def __contains__(self, item):
        return item in self.mPlotStyles

    def columnIndex(self, name: str) -> int:
        return self.columnNames.index(name)

    def onStyleUpdated(self, style: TemporalProfilePlotStyle):

        idx = self.plotStyle2idx(style)
        r = idx.row()
        self.dataChanged.emit(self.createIndex(r, 0), self.createIndex(r, self.columnCount()))

    def rowCount(self, parent=QModelIndex()):
        return len(self.mPlotStyles)

    def plotStyle2idx(self, plotStyle):

        assert isinstance(plotStyle, TemporalProfilePlotStyle)

        if plotStyle in self.mPlotStyles:
            i = self.mPlotStyles.index(plotStyle)
            return self.createIndex(i, 0)
        else:
            return QModelIndex()

    def idx2plotStyle(self, index) -> TemporalProfilePlotStyle:
        if index.isValid() and index.row() < self.rowCount():
            return self.mPlotStyles[index.row()]
        return None

    def columnCount(self, parent=QModelIndex()):
        return len(self.columnNames)

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        return self.createIndex(row, column, self.mPlotStyles[row])

    def data(self, index: QModelIndex, role: Qt.ItemDataRole):
        if not index.isValid():
            return None

        col = index.column()

        plotStyle: TemporalProfilePlotStyle = self.mPlotStyles[index.row()]

        if isinstance(plotStyle, TemporalProfilePlotStyle):
            sensor = plotStyle.sensor()

            if role == Qt.DisplayRole:
                if col == self.cSensor:
                    if isinstance(sensor, SensorInstrument):
                        return sensor.name()
                    else:
                        return '<Select Sensor>'
                elif col == self.cExpression:
                    return plotStyle.expression()

            elif role == Qt.CheckStateRole:
                if col == self.cSensor:
                    return Qt.Checked if plotStyle.isVisible() else Qt.Unchecked

            elif role == Qt.UserRole:
                return plotStyle
        return None

    def setData(self, index, value, role=None) -> bool:
        if not index.isValid():
            return False

        col = index.column()

        result = False
        plotStyle: TemporalProfilePlotStyle = index.data(Qt.UserRole)

        if isinstance(plotStyle, TemporalProfilePlotStyle):
            if role == Qt.CheckStateRole:
                if col == self.cSensor:
                    plotStyle.setVisibility(value == Qt.Checked)
                    result = True

            if role == Qt.EditRole:
                if col == self.cExpression:
                    plotStyle.setExpression(value)
                    result = True

                elif col == self.cStyle:
                    plotStyle.copyFrom(value)
                    result = True

                elif col == self.cSensor:
                    plotStyle.setSensor(value)
                    result = True

        if result:
            # self.savePlotSettings(plotStyle, index='DEFAULT')
            self.dataChanged.emit(index, index, [role, Qt.DisplayRole])

        return result

    def savePlotSettings(self, sensorPlotSettings, index='DEFAULT'):
        return

    def restorePlotSettings(self, sensor, index='DEFAULT'):
        return None

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if c in [self.cSensor]:
                flags = flags | Qt.ItemIsUserCheckable
            if c in [self.cExpression, self.cStyle]:  # allow check state
                flags = flags | Qt.ItemIsEditable
            return flags
            # return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(col)
        return None


class PlotSettingsTableView(QTableView):

    def __init__(self, *args, **kwds):
        super(PlotSettingsTableView, self).__init__(*args, **kwds)

        pal = self.palette()
        cSelected = pal.color(QPalette.Active, QPalette.Highlight)
        pal.setColor(QPalette.Inactive, QPalette.Highlight, cSelected)
        self.setPalette(pal)

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates and shows the QMenu
        :param event: QContextMenuEvent
        """

        indices = self.selectionModel().selectedIndexes()

        if len(indices) > 0:
            refIndex = indices[0]
            assert isinstance(refIndex, QModelIndex)

            menu = QMenu(self)
            menu.setToolTipsVisible(True)

            menu.popup(QCursor.pos())

    def plotSettingsModel(self) -> PlotSettingsTableModel:
        return self.model().sourceModel()

    def onSetStyle(self, indices):

        m = self.plotSettingsModel()
        for col in range(self.model().columnCount()):
            if self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole) == m.cnStyle:
                break

        if len(indices) > 0:
            refStyle = indices[0].data(Qt.UserRole)
            assert isinstance(refStyle, TemporalProfilePlotStyle)
            newStyle = PlotStyleDialog.getPlotStyle(plotStyle=refStyle)
            if isinstance(newStyle, PlotStyle):
                for idx in indices:
                    assert isinstance(idx, QModelIndex)
                    idx2 = self.model().index(idx.row(), col)
                    self.model().setData(idx2, newStyle, role=Qt.EditRole)


class PlotSettingsTableViewWidgetDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, tableView, parent=None):
        assert isinstance(tableView, PlotSettingsTableView)
        super(PlotSettingsTableViewWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.mTableView = tableView
        self.mPlotSettingsContextGenerator = PlotSettingsContextGenerator()

    def plotSettingsModel(self) -> PlotSettingsTableModel:

        model = self.mTableView.model()

        while isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        return model

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QModelIndex):
        if index.column() == 2:
            style: TemporalProfilePlotStyle = index.data(Qt.UserRole)

            h = self.mTableView.verticalHeader().sectionSize(index.row())
            w = self.mTableView.horizontalHeader().sectionSize(index.column())

            if h > 0 and w > 0:
                px = style.createPixmap(size=QSize(w, h))
                label = QLabel()
                label.setPixmap(px)
                painter.drawPixmap(option.rect, px)
                # QApplication.style().drawControl(QStyle.CE_CustomBase, label, painter)
            else:
                super(PlotSettingsTableViewWidgetDelegate, self).paint(painter, option, index)
        else:
            super(PlotSettingsTableViewWidgetDelegate, self).paint(painter, option, index)

    def setItemDelegates(self, tableView):
        assert isinstance(tableView, QTableView)

        for c in [PlotSettingsTableModel.cStyle, PlotSettingsTableModel.cExpression]:
            tableView.setItemDelegateForColumn(c, self)

    """
    def sizeHint(self, options, index):
        s = super(ExpressionDelegate, self).sizeHint(options, index)
        exprString = self.tableView.model().data(index)
        l = QLabel()
        l.setText(exprString)
        x = l.sizeHint().width() + 100
        s = QSize(x, s.height())
        return self._preferedSize
    """

    def createEditor(self, parent, option, index: QModelIndex):

        if not index.isValid():
            return

        w = None
        c = index.column()
        plotStyle = index.data(Qt.UserRole)
        model = self.plotSettingsModel()
        self.mPlotSettingsContextGenerator.setLayer(model.temporalProfileLayer())
        if isinstance(plotStyle, TemporalProfilePlotStyle):
            if c == PlotSettingsTableModel.cExpression:
                w = QgsFieldExpressionWidget(parent=parent)
                w.setExpressionDialogTitle('Values')
                w.setToolTip('Set an expression to specify the image band or calculate a spectral index.')
                # w.fieldChanged[str, bool].connect(lambda n, b: self.checkData(index, w, w.expression()))

                w.registerExpressionContextGenerator(self.mPlotSettingsContextGenerator)

                model = self.plotSettingsModel()
                layer = model.temporalProfileLayer()
                if isinstance(layer, QgsVectorLayer):
                    w.setLayer(layer)
                # w.setRow(0)
                w.setExpression(plotStyle.expression())

            elif c == PlotSettingsTableModel.cStyle:
                w = PlotStyleButton(parent=parent)
                w.setPlotStyle(plotStyle)
                w.setToolTip('Set style.')
                # w.sigPlotStyleChanged.connect(lambda ps: self.checkData(index, w, ps))

            else:
                raise NotImplementedError()
        return w

    def checkData(self, index, w, value):
        assert isinstance(index, QModelIndex)
        if index.isValid():
            plotStyle = index.data(Qt.UserRole)
            assert isinstance(plotStyle, TemporalProfilePlotStyle)
            if isinstance(w, QgsFieldExpressionWidget):
                assert value == w.expression()
                assert w.isExpressionValid(value) == w.isValidExpression()

                if w.isValidExpression():
                    self.commitData.emit(w)
                else:
                    s = ""
                    # print(('Delegate commit failed',w.asExpression()))
            if isinstance(w, PlotStyleButton):
                self.commitData.emit(w)

    def setEditorData(self, editor, index: QModelIndex):
        if not index.isValid():
            return

        w = None
        style = index.data(Qt.UserRole)
        assert isinstance(style, TemporalProfilePlotStyle)
        c = index.column()
        if c == PlotSettingsTableModel.cExpression:
            lastExpr = index.data(Qt.DisplayRole)
            assert isinstance(editor, QgsFieldExpressionWidget)
            editor.setProperty('lastexpr', lastExpr)
            editor.setField(lastExpr)

        elif c == PlotSettingsTableModel.cStyle:
            assert isinstance(editor, PlotStyleButton)
            editor.setPlotStyle(style)

        else:
            raise NotImplementedError()

    def setModelData(self, w, model, index: QModelIndex):
        c = index.column()
        # model = self.plotSettingsModel()

        if index.isValid():
            if c == PlotSettingsTableModel.cExpression:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = model.data(index, Qt.DisplayRole)

                if w.isValidExpression():
                    if expr != exprLast:
                        model.setData(index, w.asExpression(), Qt.EditRole)
                else:
                    w
            elif c == PlotSettingsTableModel.cStyle:
                if isinstance(w, PlotStyleButton):
                    style = w.plotStyle()
                    model.setData(index, style, Qt.EditRole)

            else:
                raise NotImplementedError()
