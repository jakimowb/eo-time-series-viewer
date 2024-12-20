import json
from typing import Dict, List, Optional, Union

from qgis.PyQt.QtWidgets import QApplication, QHeaderView, QMenu, QStyle, QStyledItemDelegate, QStyleOptionButton, \
    QStyleOptionViewItem, QTreeView, QWidget
from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QStandardItem, \
    QStandardItemModel
from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextGenerator, QgsExpressionContextScope, \
    QgsExpressionContextUtils, QgsField, QgsProperty, QgsPropertyDefinition, QgsVectorLayer

from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle, PlotStyleButton, \
    PlotStyleDialog, PlotStyleWidget
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, \
    PropertyItem, PropertyItemBase, PropertyItemGroup, QgsPropertyItem
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.temporalprofile.functions import ProfileValueExpressionFunction
from eotimeseriesviewer.timeseries import SensorInstrument, TimeSeries


class StyleItem(PlotStyleItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def heightHint(self) -> int:
        return 1


class PlotSymbolItem(StyleItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def createEditor(self, parent):
        # show editor without marker symbols
        w = PlotStyleButton(parent=parent)

        w.setMinimumSize(5, 5)
        w.setPlotStyle(self.plotStyle())
        F = PlotStyleWidget.VisibilityFlags
        w.setVisibilityFlags(F.SymbolPen | F.Symbol | F.Type | F.Color | F.Size | F.Preview)
        w.setVisibilityCheckboxVisible(False)
        w.setToolTip('Set plot symbol')
        return w

    def heightHint(self) -> int:
        style = self.plotStyle()
        h = 5
        if style.markerSymbol is not None:
            h += style.markerSize

            if style.markerPen.style() != Qt.NoPen:
                h += style.markerPen.width()
        return h


class LineStyleItem(StyleItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        # default line style
        self.mPlotStyle.setLinePen(QPen(QColor('green'), 0, Qt.SolidLine))

    def heightHint(self) -> int:
        style = self.plotStyle()
        h = 5

        if style.linePen.style() != Qt.NoPen:
            h += style.linePen.width()
        return h

    def createEditor(self, parent):
        # show editor without marker symbols
        w = PlotStyleButton(parent=parent)
        d: PlotStyleDialog = w.mDialog

        dw: PlotStyleWidget = d.plotStyleWidget()
        F = PlotStyleWidget.VisibilityFlags
        dw.setVisibilityFlags(F.Line | F.Color | F.Size | F.Type | F.Preview)

        w.setMinimumSize(5, 5)
        w.setPlotStyle(self.plotStyle())
        # w.setColorWidgetVisibility(self.mEditColors)
        # w.setVisibilityCheckboxVisible(False)
        w.setToolTip('Set line style')
        return w


class TPVisGroup(PropertyItemGroup):
    """
    Describes how to display am temporal profile with data from multiple sensors.
    """
    MIME_TYPE = 'application/eotsv/temporalprofiles/PropertyItems'

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mZValue = 2

        self.mModifiedText: Optional[str] = None

        self.setIcon(QIcon(':/eotimeseriesviewer/icons/mIconTemporalProfile.svg'))
        self.mFirstColumnSpanned = True
        self.setEditable(True)

        self.mPField = QgsPropertyItem('Field')
        self.mPField.setDefinition(QgsPropertyDefinition(
            'Field', 'Name of the field that stores the temporal profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPField.setProperty(QgsProperty.fromField('profiles', True))
        self.mPField.setIsProfileFieldProperty(True)
        self.mPField.label().setIcon(QIcon(':/images/themes/default/mSourceFields.svg'))

        self.mPLineStyle = LineStyleItem('Line')
        self.mPLineStyle.label().setIcon(QIcon(':/images/themes/default/propertyicons/stylepreset.svg'))

        self.mPLabel = QgsPropertyItem('Label')
        self.mPLabel.setDefinition(QgsPropertyDefinition(
            'Label', 'Text label to describe plotted temporal profiles.',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPLabel.setProperty(QgsProperty.fromExpression('$id'))
        self.mPLabel.label().setIcon(QIcon(':/images/themes/default/mActionLabeling.svg'))

        self.mPFilter = QgsPropertyItem('Filter')
        self.mPFilter.setDefinition(QgsPropertyDefinition(
            'Filter', 'Filter feature', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPFilter.setProperty(QgsProperty.fromExpression(''))
        self.mPFilter.label().setIcon(QIcon(':/images/themes/default/mActionFilter2.svg'))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLineStyle, self.mPLabel, self.mPFilter]:
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

    def update(self):

        # update the line-style item
        idx = self.mPLineStyle.index()
        self.model().dataChanged.emit(idx, idx)

        s = ""

    def sensorItems(self) -> List['TPVisSensor']:

        return list(self.mSensorItems.values())

    def createPixmap(self, size: QSize, hline: bool = True, bc: Optional[QColor] = None) -> QPixmap:
        """
        Create a preview of the plot
        :param size:
        :param hline:
        :param bc:
        :return:
        """
        print('# UPDATE PIXMAP')
        if bc is None:
            bc = QColor('black')
        else:
            bc = QColor(bc)

        sensorItems = [s for s in self.sensorItems()]
        ns = len(sensorItems)

        lineStyle: PlotStyle = self.mPLineStyle.plotStyle()

        pm = QPixmap(size)
        if self.isVisible():
            pm.fill(bc)

            p = QPainter(pm)
            # draw the line
            p.setPen(lineStyle.linePen)

            w, h = pm.width(), pm.height()
            path = QPainterPath()

            # show a line with ns + 2 data points
            xvec = [x / (ns + 1) for x in range(ns + 2)]
            yvec = [0.5 for _ in xvec]

            # path.moveTo(xvec[0] * w, yvec[0] * h)
            path.moveTo(xvec[0] * w, yvec[0] * h)
            for x, y in zip(xvec[1:], yvec[1:]):
                path.lineTo(x * w, y * h)

            p.drawPath(path)
            p.end()
            for i, sensorItem in enumerate(sensorItems):
                assert isinstance(sensorItem, TPVisSensor)
                if not sensorItem.checkState() == Qt.Checked:
                    continue

                symbolStyle = sensorItem.symbolStyle()

                p2 = QPainter(pm)
                p2.translate(xvec[i + 1] * w, yvec[i + 1] * h)

                drawSymbol(p2, symbolStyle.markerSymbol, symbolStyle.markerSize,
                           symbolStyle.markerPen, symbolStyle.markerBrush)
                p2.end()
            # p.end()
        else:
            # transparent background
            pm.fill(QColor(0, 255, 0, 0))
            p = QPainter(pm)
            # p.begin()
            p.setPen(QPen(QColor(100, 100, 100)))
            p.drawLine(0, 0, pm.width(), pm.height())
            p.drawLine(0, pm.height(), pm.width(), 0)
            # p.end()

        return pm

    def setField(self, field: Union[str, QgsField]):

        if isinstance(field, QgsField):
            field = field.name()

        p = self.mPField.property()
        p.setField(field)
        self.mPField.setProperty(p)

        self.updateText()

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mLayer, QgsVectorLayer):
            self.mLayer.featuresDeleted.disconnect(self.update)

        self.mLayer = layer
        self.mLayer.featuresDeleted.connect(self.update)
        self.mLayer.selectionChanged.connect(self.update)
        self.mLayer.featureAdded.connect(self.update)
        self.mLayer.attributeAdded.connect(self.update)
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

    def field(self) -> str:
        return self.mPField.text()

    def addSensors(self, sensors: Union[SensorInstrument, str, List[str], List[SensorInstrument]]):

        if isinstance(sensors, (str, SensorInstrument)):
            sensors = [sensors]

        items = []
        for sensor in sensors:
            if isinstance(sensor, SensorInstrument):
                sid = sensor.id()
                name = sensor.name()
            else:
                sid = sensor
                name = None

            if sid not in self.mSensorItems:
                item = TPVisSensor()
                item.setSensor(sid)
                item.setCheckState(Qt.Checked)
                self.mSensorItems[sid] = item
                if name:
                    item.setSensorName(name)

                items.append(item)

        if len(items) > 0:
            self.appendRows(items)
            for item in items:
                item.signals().dataChanged.connect(self.update)

    def settingsMap(self) -> dict:

        d = dict()
        lyr = self.layer()
        if isinstance(lyr, QgsVectorLayer):
            d['layer'] = {'name': lyr.name(),
                          'source': lyr.source(),
                          'id': lyr.id()}
        else:
            d['layer'] = None
        d['show'] = self.checkState() == Qt.Checked
        d['field'] = self.field()
        d['line_style'] = self.mPLineStyle.plotStyle().map()
        d['sensors'] = [s.settingsMap() for s in self.mSensorItems.values()]

        return d

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
        self.setIcon(QIcon(':/eotimeseriesviewer/icons/satellite.svg'))
        self.mSensorID: str = None
        self.mSensorAttributes: dict = None
        self.setEditable(True)
        self.setCheckable(True)
        self.mFirstColumnSpanned = True

        self.setText('<Sensor>')

        self.mSpeclib: QgsVectorLayer = None

        self.mPSymbol = PlotSymbolItem('Symbol')
        self.mPSymbol.label().setIcon(QIcon(':/images/themes/default/propertyicons/stylepreset.svg'))

        self.mPBand = QgsPropertyItem('Band')
        self.mPBand.setText('Band')
        # self.mPBand.label().setText('Band')

        items = [self.mPSymbol, self.mPBand]
        for item in items:
            self.appendRow(item.propertyRow())

    def symbolStyle(self) -> PlotStyle:
        return self.mPSymbol.plotStyle()

    def setSensor(self, sid: str, name: str = None):
        self.mSensorID = sid
        self.mSensorAttributes = json.loads(sid)

        if name is None:
            name = self.mSensorAttributes.get('name')

        if name is None:
            name = sid
            self.setToolTip(f'Sensor: {name} <br>ID: {sid}')
        else:
            self.setToolTip(f'Sensor ID: {sid} <br>')

        self.setText(name)

    def setSensorName(self, name: str):
        if name != self.text():
            self.setText(name)

    def sensorName(self) -> str:
        return self.text()

    def sensorId(self) -> str:
        return self.mSensorID

    def settingsMap(self) -> dict:

        band = self.mPBand.text()

        d = {'sensor_id': self.sensorId(),
             'sensor_name': self.sensorName(),
             'show': self.checkState() == Qt.Checked,
             'band': band,
             'symbol_style': self.mPSymbol.plotStyle().map(),
             }

        return d


class PlotSettingsTreeModel(QStandardItemModel):
    cName = 0
    cValue = 1

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
        self.mTimeSeries.sigSensorNameChanged.connect(self.onSensorNameChanged)
        self.addSensors(timeSeries.sensors())

    def timeSeries(self) -> TimeSeries:
        return self.mTimeSeries

    def addVisualizations(self, vis: Union[TPVisGroup, List[TPVisGroup]]):

        if isinstance(vis, TPVisGroup):
            vis = [vis]
        for v in vis:
            assert isinstance(v, TPVisGroup)

            self.mVisualizations.append(v)
            n = self.rowCount()
            self.insertRow(n, v)

    def removeVisualizations(self, vis: Union[TPVisGroup, List[TPVisGroup]]):
        if isinstance(vis, TPVisGroup):
            vis = [vis]
        for v in vis:
            assert isinstance(v, TPVisGroup)
            idx: QModelIndex = self.indexFromItem(v)
            if v in self.mVisualizations:
                self.mVisualizations.remove(v)
            if idx.isValid():
                self.removeRow(idx.row(), idx.parent())

    def sensorNodes(self, sid: Optional[str] = None) -> List[TPVisSensor]:
        nodes = []
        for vis in self.mVisualizations:
            nodes.extend([s for s in vis.mSensorItems.values()])
        if sid:
            nodes = [n for n in nodes if n.sensorId() == sid]
        return nodes

    def onSensorNameChanged(self, sensor: SensorInstrument):

        for node in self.sensorNodes(sid=sensor.id()):
            node: TPVisSensor
            node.setSensorName(sensor.name())
            s = ""

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

    def settingsJson(self) -> str:

        return json.dumps(self.settingsMap())

    def settingsMap(self) -> dict:
        """
        Collect all settings
        :return:
        """

        d = dict()

        d['visualizations'] = [v.settingsMap() for v in self.mVisualizations]

        return d


class PlotSettingsTreeViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: QTreeView, parent=None):
        assert isinstance(treeView, QTreeView)
        super().__init__(parent=parent)
        self.mTreeView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        #  return super().paint(painter, option, index)

        item: PropertyItem = index.data(Qt.UserRole)
        # bc = QColor(self.plotControl().generalSettings().backgroundColor())
        bc = QColor('black')
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

            elif isinstance(item, TPVisGroup):
                # super().paint(painter, option, index)
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                h = option.rect.height()

                if False:
                    pm = item.createPixmap(size=QSize(10 * h, h), bc=bc)
                    to_paint.append(pm)
                # if not item.isComplete():
                #    to_paint.append(QIcon(r':/images/themes/default/mIconWarning.svg'))
                data = item.data(Qt.DisplayRole)
                if data:
                    to_paint.append(data)

                x0 = option.rect.x() + 1
                y0 = option.rect.y()
                for p in to_paint:
                    if p is None:
                        s = ""
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

                        check_option = QStyleOptionButton()
                        check_option.state = o.state  # Checkbox is enabled

                        # Set the geometry of the checkbox within the item
                        check_option.rect = option.rect
                        QApplication.style().drawControl(QStyle.CE_CheckBox, check_option, painter)

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

            elif isinstance(item, LineStyleItem):
                # self.initStyleOption(option, index)
                parentItem = item.parent()
                if isinstance(parentItem, TPVisGroup) and total_h > 0 and total_w > 0:
                    px = parentItem.createPixmap(size=QSize(total_w, total_h), bc=bc)
                    painter.drawPixmap(option.rect, px)
            elif isinstance(item, PlotSymbolItem):
                symbolStyle: PlotStyle = item.plotStyle()
                px = symbolStyle.createPixmap(size=QSize(total_w, total_h), bc=bc)
                painter.drawPixmap(option.rect, px)
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

    def sizeHint(self, option, index):
        # Get the default size hint
        default_size = super().sizeHint(option, index)

        item = index.data(Qt.UserRole)
        if isinstance(item, StyleItem):
            y = max(default_size.height(), item.heightHint())
            return QSize(default_size.width(), y)
        else:
            # Default height for non-selected rows
            return default_size

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
        self.header().setSectionResizeMode(QHeaderView.ResizeToContents)

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
            if isinstance(item, PropertyItemGroup):
                self.onRowsInserted(idx, 0, item.rowCount())
            if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                self.setFirstColumnSpanned(r, idx.parent(), True)
            if isinstance(item, TPVisSensor):
                s = ""


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
