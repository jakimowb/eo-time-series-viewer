import json
from typing import Dict, List, Optional, Union

from PyQt5.QtCore import pyqtSignal, QAbstractItemModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt
from PyQt5.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QMenu, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeView, QWidget
from qgis._core import QgsExpression, QgsExpressionContext, QgsExpressionContextGenerator, QgsExpressionContextScope, \
    QgsExpressionContextUtils, QgsFeatureRequest, QgsField, QgsProperty, QgsPropertyDefinition, QgsVectorLayer

from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, \
    PropertyItem, PropertyItemBase, PropertyItemGroup, QgsPropertyItem
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.functions import ProfileValueExpressionFunction
from eotimeseriesviewer.timeseries import SensorInstrument, TimeSeries


class TPVisGroup(PropertyItemGroup):
    """
    Describes how to display am temporal profile with data from multiple sensors.
    """
    MIME_TYPE = 'application/eotsv/temporalprofiles/PropertyItems'

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mZValue = 2

        self.mModifiedText: Optional[str] = None

        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = True
        self.setEditable(True)

        self.mPField = QgsPropertyItem('Field')
        self.mPField.setDefinition(QgsPropertyDefinition(
            'Field', 'Name of the field that stores the temporal profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPField.setProperty(QgsProperty.fromField('profiles', True))
        self.mPField.setIsProfileFieldProperty(True)

        self.mPStyle = PlotStyleItem('Style')
        self.mPStyle.setEditColors(False)
        self.mPLabel = QgsPropertyItem('Label')
        self.mPLabel.setDefinition(QgsPropertyDefinition(
            'Label', 'Text label to describe plotted temporal profiles.',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPLabel.setProperty(QgsProperty.fromExpression('$id'))

        self.mPFilter = QgsPropertyItem('Filter')
        self.mPFilter.setDefinition(QgsPropertyDefinition(
            'Filter', 'Filter feature', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPFilter.setProperty(QgsProperty.fromExpression(''))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLabel, self.mPFilter, self.mPStyle]:
            self.appendRow(pItem.propertyRow())

        self.mSensorItems: Dict[str, TPVisSensor] = dict()

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        # connect requestPlotUpdate signal
        for propertyItem in self.propertyItems():
            propertyItem: PropertyItem
            propertyItem.signals().dataChanged.connect(self.signals().dataChanged.emit)
        self.signals().dataChanged.connect(self.update)
        # self.initBasicSettings()

        self.mLayer: QgsVectorLayer = None

    def setField(self, field: Union[str, QgsField]):

        if isinstance(field, QgsField):
            field = field.name()

        p = self.mPField.property()
        p.setField(field)
        self.mPField.setProperty(p)

        self.updateText()

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.updateText()

    def layer(self) -> Optional[QgsVectorLayer]:
        return self.mLayer

    def updateText(self):

        if isinstance(self.mModifiedText, str):
            self.setText(self.mModifiedText)
            self.setToolTip(self.mModifiedText)
        else:

            text = []
            tt = []

            lyr = self.layer()
            if isinstance(lyr, QgsVectorLayer):
                text.append(lyr.name())
                tt.extend([f'Layer: {lyr.name()}'
                           f'ID: {lyr.id()}'])

            else:
                text.append('<Missing layer>')
                tt.append('Missing Layer')

            field = self.field()
            if isinstance(field, str):
                text.append(f'"{field}"')
                tt.append(f'Field: "{field}"')
            else:
                text.append('<Missing field>')
                tt.append('<Missing field>')

            self.setText(' '.join(text))
            self.setToolTip('<br>'.join(tt))

    def __disconnect_layer(self):
        self.mLayer = None

    def field(self) -> str:
        return self.mPField.text()

    def addSensors(self, sensor_ids: Union[str, List[str]]):

        if isinstance(sensor_ids, str):
            sensor_ids = [sensor_ids]
        items = []
        for sid in sensor_ids:
            if sid not in self.mSensorItems:
                item = TPVisSensor()
                item.setSensor(sid)
                self.mSensorItems[sid] = item
                items.append(item)

        if len(items) > 0:
            self.appendRows(items)

    def updateSensorNames(self, sensors: List[SensorInstrument]):

        for sensor in sensors:
            item = self.mSensorItems.get(sensor.id())
            if isinstance(item, TPVisSensor):
                item.setText(item)

    def removeSensors(self, sensor_ids: Union[str, List[str]]):

        if isinstance(sensor_ids, str):
            sensor_ids = [sensor_ids]


class TPVisProfileColorPropertyItem(QgsPropertyItem):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

    def populateContextMenu(self, menu: QMenu):

        if self.isColorProperty():
            a = menu.addAction('Use vector symbol color')
            a.setToolTip('Use map vector symbol colors as profile color.')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
            a.triggered.connect(self.setToSymbolColor)

    def setToSymbolColor(self, *args):
        if self.isColorProperty():
            self.setProperty(QgsProperty.fromExpression('@symbol_color'))


class TPVisSensor(PropertyItemGroup):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mZValue = 2

        self.mSensorID: str = None
        self.mSensorAttributes: dict = None
        self.setEditable(True)
        self.setCheckable(True)
        self.mFirstColumnSpanned = True

        self.setText('<Sensor>')
        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = False
        self.mSpeclib: QgsVectorLayer = None

        self.mPColor = TPVisProfileColorPropertyItem('Color')
        self.mPColor.setDefinition(QgsPropertyDefinition(
            'Color',
            'Color of temporal profile values', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mPColor.setProperty(QgsProperty.fromValue(QColor('white')))

        items = [self.mPColor]
        self.appendRows(items)

    def setSensor(self, sid: str):
        self.mSensorAttributes = json.loads(sid)

        name = self.mSensorAttributes.get('name')
        if name is None:
            name = sid
        self.setText(name)
        s = ""

    def sensor(self) -> str:
        return self.mSensorID


class PlotSettingsTreeModel(QStandardItemModel):
    cName = 0
    cValue = 1

    sigProgressChanged = pyqtSignal(float)
    sigPlotWidgetStyleChanged = pyqtSignal()
    sigMaxProfilesExceeded = pyqtSignal()
    NOT_INITIALIZED = -1

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mModelItems: List[PropertyItemGroup] = []
        # # workaround https://github.com/qgis/QGIS/issues/45228

        hdr0 = QStandardItem('Setting')
        hdr0.setToolTip('Visualization setting')
        hdr1 = QStandardItem('Value')
        hdr1.setToolTip('Visualization setting value')
        self.setHorizontalHeaderItem(0, hdr0)
        self.setHorizontalHeaderItem(1, hdr1)

        self.mPlotWidget: DateTimePlotWidget = None
        self.mTimeSeries: TimeSeries = None
        self.mLayer: QgsVectorLayer = None

        self.mSensors: Dict[str, SensorInstrument] = dict()

        self.mVisualizations: List[TPVisGroup] = []

    def setPlotWidget(self, plotWidget: DateTimePlotWidget):
        self.mPlotWidget = plotWidget

    def setTimeSeries(self, timeSeries: TimeSeries):

        self.mTimeSeries = timeSeries
        self.mTimeSeries.sigSensorAdded.connect(self.addSensors)
        self.mTimeSeries.sigSensorRemoved.connect(self.removeSensors)
        self.addSensors(timeSeries.sensors())

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mLayer, QgsVectorLayer):
            # disconnect signals
            pass

        self.mLayer = layer

    def addVisualization(self, vis: TPVisGroup):
        assert isinstance(vis, TPVisGroup)

        self.mVisualizations.append(vis)

        n = self.rowCount()
        self.insertRow(n, vis)
        s = ""
        pass

    def addSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):
        """
        Create a new plotstyle for this sensor
        :param sensor:
        :return:
        """

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        for s in sensors:
            s: SensorInstrument
            if s.id() not in self.mSensors:
                self.mSensors[s.id()] = s

    def removeSensors(self, sensors: Union[SensorInstrument, List[SensorInstrument]]):

        if isinstance(sensors, SensorInstrument):
            sensors = [sensors]

        to_remove = []
        for sensor in sensors:
            sid = sensor.id()
            if sid in self.mSensors:
                self.mSensors.pop(sid)
                to_remove.append(sid)

    def plotWidget(self) -> DateTimePlotWidget:
        return self.mPlotWidget

    def updatePlot(self):

        pw = self.plotWidget()
        pw.plotItem.clear()

        request = QgsFeatureRequest()

        selected_fids = self.mLayer.selectedFeatureIds()

        for feature in self.mLayer.getFeatures(request):
            pass


class PlotSettingsTreeViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: QTreeView, parent=None):
        assert isinstance(treeView, QTreeView)
        super().__init__(parent=parent)
        self.mTreeView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: PropertyItem = index.data(Qt.UserRole)
        bc = QColor(self.plotControl().generalSettings().backgroundColor())
        total_h = self.mTreeView.rowHeight(index)
        total_w = self.mTreeView.columnWidth(index.column())
        style: QStyle = option.styleObject.style()
        margin = 3  # px
        if isinstance(item, PropertyItemBase):
            if item.hasPixmap():
                super().paint(painter, option, index)
                rect = option.rect
                size = QSize(rect.width(), rect.height())
                pixmap = item.previewPixmap(size)
                if isinstance(pixmap, QPixmap):
                    painter.drawPixmap(rect, pixmap)

            elif isinstance(item, PropertyItemGroup):
                # super().paint(painter, option, index)
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                h = option.rect.height()
                plot_style: PlotStyle = item.mPStyle.plotStyle()
                # add pixmap
                pm = plot_style.createPixmap(size=QSize(h, h), hline=True, bc=bc)
                to_paint.append(pm)
                if not item.isComplete():
                    to_paint.append(QIcon(r':/images/themes/default/mIconWarning.svg'))
                to_paint.append(item.data(Qt.DisplayRole))

                x0 = option.rect.x() + 1
                y0 = option.rect.y()
                for p in to_paint:
                    o: QStyleOptionViewItem = QStyleOptionViewItem(option)
                    self.initStyleOption(o, index)
                    o.styleObject = option.styleObject
                    o.palette = QPalette(option.palette)

                    if isinstance(p, Qt.CheckState):
                        # size = style.sizeFromContents(QStyle.PE_IndicatorCheckBox, o, QSize(), None)
                        o.rect = QRect(x0, y0, h, h)
                        o.state = {Qt.Unchecked: QStyle.State_Off,
                                   Qt.Checked: QStyle.State_On,
                                   Qt.PartiallyChecked: QStyle.State_NoChange}[p]
                        o.state = o.state | QStyle.State_Enabled

                        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, o, painter, self.mTreeView)

                    elif isinstance(p, QPixmap):
                        o.rect = QRect(x0, y0, h, h)
                        painter.drawPixmap(o.rect, p)

                    elif isinstance(p, QIcon):
                        o.rect = QRect(x0, y0, h, h)
                        p.paint(painter, o.rect)
                    elif isinstance(p, str):
                        font_metrics = QFontMetrics(self.mTreeView.font())
                        w = font_metrics.horizontalAdvance(p)
                        o.rect = QRect(x0 + margin, y0, x0 + margin + w, h)
                        palette = style.standardPalette()
                        enabled = True
                        textRole = QPalette.Foreground
                        style.drawItemText(painter, o.rect, Qt.AlignLeft, palette, enabled, p, textRole=textRole)

                    else:
                        raise NotImplementedError(f'Does not support painting of "{p}"')
                    x0 = o.rect.x() + margin + o.rect.width()

            elif isinstance(item, PlotStyleItem):
                # self.initStyleOption(option, index)
                plot_style: PlotStyle = item.plotStyle()

                if total_h > 0 and total_w > 0:
                    px = plot_style.createPixmap(size=QSize(total_w, total_h), bc=bc)
                    painter.drawPixmap(option.rect, px)
                else:
                    super().paint(painter, option, index)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def setItemDelegates(self, treeView: QTreeView):
        for c in range(treeView.model().columnCount()):
            treeView.setItemDelegateForColumn(c, self)

    def onRowsInserted(self, parent, idx0, idx1):
        nameStyleColumn = self.bridge().cnPlotStyle

        for c in range(self.mTreeView.model().columnCount()):
            cname = self.mTreeView.model().headerData(c, Qt.Horizontal, Qt.DisplayRole)
            if cname == nameStyleColumn:
                for r in range(idx0, idx1 + 1):
                    idx = self.mTreeView.model().index(r, c, parent=parent)
                    self.mTreeView.openPersistentEditor(idx)

    def plotControl(self) -> PlotSettingsTreeModel:
        return self.mTreeView.model().sourceModel()

    def createEditor(self, parent, option, index):
        w = None
        editor = None
        if index.isValid():
            item = index.data(Qt.UserRole)
            if isinstance(item, PropertyItem):
                editor = item.createEditor(parent)
        if isinstance(editor, QWidget):
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        if not index.isValid():
            return

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setEditorData(editor, index)
        else:
            super().setEditorData(editor, index)

        return

    def setModelData(self, w, model, index):

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setModelData(w, model, index)
        else:
            super().setModelData(w, model, index)


class PlotSettingsTreeView(QTreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def setModel(self, model: Optional[QAbstractItemModel]) -> None:
        super().setModel(model)
        if isinstance(model, QAbstractItemModel):
            model.rowsInserted.connect(self.onRowsInserted)

            for r in range(0, model.rowCount()):
                idx = model.index(r, 0)
                item = idx.data(Qt.UserRole)
                if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                    self.setFirstColumnSpanned(r, idx.parent(), True)

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        for r in range(first, last + 1):
            idx = self.model().index(r, 0, parent=parent)
            item = idx.data(Qt.UserRole)
            if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                self.setFirstColumnSpanned(r, idx.parent(), True)


class PlotSettingsProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class PlotSettingsContextGenerator(QgsExpressionContextGenerator):
    mFunc = ProfileValueExpressionFunction()
    QgsExpression.registerFunction(mFunc)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mLayer = None

    def setLayer(self, layer: QgsVectorLayer):
        self.mLayer = layer

    def setDate(self):
        pass

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()
        if isinstance(self.mLayer, QgsVectorLayer):
            context.appendScope(QgsExpressionContextUtils.layerScope(self.mLayer))

        dateScope = QgsExpressionContextScope('date')
        var = QgsExpressionContextScope.StaticVariable('date')
        var.value = 'today'
        dateScope.addVariable(var)
        dateScope.addFunction(self.mFunc.name(), self.mFunc.clone())
        context.appendScope(dateScope)
        return context
