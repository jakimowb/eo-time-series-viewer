import itertools
import json
from typing import Any, Dict, List, Optional, Union

from qgis.core import QgsExpressionContext, QgsExpressionContextGenerator, QgsExpressionContextScope, \
    QgsExpressionContextUtils, QgsFeature, QgsField, QgsFieldModel, QgsGeometry, QgsProject, QgsProperty, \
    QgsPropertyDefinition, QgsVectorLayer
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QFontMetrics, QIcon, QPainter, QPainterPath, QPalette, QPen, \
    QPixmap, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAction, QApplication, QComboBox, QHeaderView, QMenu, QStyle, QStyledItemDelegate, \
    QStyleOptionButton, QStyleOptionViewItem, QTreeView, QWidget
from qgis.gui import QgsFieldExpressionWidget
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt
from eotimeseriesviewer.temporalprofile.spectralindices import spectral_indices
from eotimeseriesviewer.temporalprofile.temporalprofile import TemporalProfileLayerFieldComboBox, TemporalProfileUtils
from eotimeseriesviewer.temporalprofile.pythoncodeeditor import FieldPythonExpressionWidget
from eotimeseriesviewer.qgispluginsupport.qps.plotstyling.plotstyling import PlotStyle, PlotStyleButton, \
    PlotStyleDialog, PlotStyleWidget
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol
from eotimeseriesviewer.qgispluginsupport.qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, \
    PropertyItem, PropertyItemBase, PropertyItemGroup, PropertyLabel, QgsPropertyItem
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotWidget
from eotimeseriesviewer.timeseries import SensorInstrument, TimeSeries


class StyleItem(PlotStyleItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def heightHint(self) -> int:
        return 1


class LayerProfileFieldItem(PropertyItem):

    def __init__(self, *args, **kwds):
        self.mField: Optional[str] = None
        self.mLayer: Optional[str] = None

        super().__init__(*args, **kwds)
        self.isEditable(True)

    def createEditor(self, parent):
        cb = QComboBox(parent)
        cb.setModel()


class ProfileFieldItem(PropertyItem):

    def __init__(self, *args, **kwds):
        self.mField: Optional[str] = None
        super().__init__(*args, **kwds)

        self.setEditable(True)

        self.mFieldModel = QgsFieldModel()

    def createEditor(self, parent):
        cb = QComboBox(parent)
        cb.setModel(self.mFieldModel)
        return cb

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        parentItem = self.parent()
        if isinstance(parentItem, TPVisGroup):
            layer = parentItem.layer()
            if isinstance(layer, QgsVectorLayer):
                profile_fields = TemporalProfileUtils.profileFields(layer)
                self.mFieldModel.setFields(profile_fields)

    def setModelData(self, editor: QWidget, bridge, index: QModelIndex):

        if isinstance(editor, QComboBox):
            fieldName = editor.currentData(QgsFieldModel.CustomRole.FieldName)
            self.mField = fieldName

    def setField(self, field: str):
        if field != self.mField:
            self.mField = field
            self.emitDataChanged()

    def field(self) -> Optional[str]:
        return self.mField

    def data(self, role: int = ...) -> Any:

        field = self.field()
        missing_field = field in ['', None]
        if role == Qt.DisplayRole:

            if missing_field:
                return '<select field>'
            else:
                return self.mField

        if role == Qt.ForegroundRole:

            if missing_field:
                return QColor('red')

        return super().data(role)


class PythonCodeItem(PropertyItem):
    class Signals(PropertyItem.Signals):
        validationRequest = pyqtSignal(dict)

        def __init__(self, *args, **kwds):
            super().__init__(*args, **kwds)

    def __init__(self, *args, signals=None, **kwds):
        if signals is None:
            signals = PythonCodeItem.Signals()

        super().__init__(*args, signals=signals, **kwds)

        self.setEditable(True)
        self.mPythonExpression = 'b(1)'
        self.mIsValid: bool = True

    def createEditor(self, parent):
        w = FieldPythonExpressionWidget(parent=parent)
        w.setExpression(self.mPythonExpression)
        w.validationRequest.connect(self.signals().validationRequest)
        return w

    def data(self, role: int = ...) -> Any:

        if role == Qt.DisplayRole:
            return self.mPythonExpression

        if role == Qt.ToolTipRole:
            return self.mPythonExpression

        if role == Qt.ForegroundRole:
            if not self.mIsValid:
                return QColor('red')

        return super().data(role)

    def setModelData(self, editor: FieldPythonExpressionWidget, model: QAbstractItemModel, index: QModelIndex):
        index.data()
        expr_new = editor.expression()
        is_valid, err = editor.isValidExpression()
        if is_valid:
            self.setExpression(expr_new)

    def setExpression(self, code: str):
        assert isinstance(code, str)
        expr_old = self.mPythonExpression
        if code != expr_old:
            self.mPythonExpression = code
            self.emitDataChanged()

    def setEditorData(self, editor: FieldPythonExpressionWidget, index: QModelIndex):
        editor.setExpression(self.mPythonExpression)

    def heightHint(self) -> int:
        h = 10
        return h


class PlotSymbolItem(StyleItem):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        # self.mPlotStyle.markerPen.setColor(QColor('white'))
        self.mPlotStyle.setMarkerColor(QColor('white'))

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
        self.mPlotStyle.setLinePen(QPen(QColor('white'), 0, Qt.SolidLine))

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


class TPVisSettings(PropertyItemGroup):
    """
    Defines how profile candidates should be displayed
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setIcon(QIcon(':/images/themes/default/propertyicons/settings.svg'))
        self.mFirstColumnSpanned = True
        self.setEditable(False)
        self.setEnabled(True)
        self.setSelectable(True)
        # self.setVisible(True)
        self.setText('Settings')
        self.mZValue = 999

        self.mCandidateLayer = None
        self.mCandidateField = None
        self.mCandidateLineStyle = LineStyleItem('candidate_style')
        self.mCandidateLineStyle.label().setText('Candidates')
        self.mCandidateLineStyle.setToolTip('Style of profile candidates')
        self.mCandidateLineStyle.label().setIcon(QIcon(':/images/themes/default/propertyicons/stylepreset.svg'))

        self.mThreads = QgsPropertyItem('n_threads')
        self.mThreads.setDefinition(QgsPropertyDefinition(
            'Threads', 'Number of threads to use when loading profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositiveGreaterZero))
        self.mThreads.setProperty(QgsProperty.fromValue(4))

        for pItem in [self.mCandidateLineStyle, self.mThreads]:
            self.appendRow(pItem.propertyRow())

        self.setDropEnabled(False)
        self.setDragEnabled(False)

    def settingsMap(self, context: QgsExpressionContext = None) -> dict:
        d = dict()
        if context is None:
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.globalScope())
            context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))

        d['candidate_add'] = True
        d['candidate_target'] = (None, None)
        d['candidate_line_style'] = self.mCandidateLineStyle.plotStyle().map()
        d['n_threads'] = self.mThreads.value(context, 4)
        return d

    def createProfileCandidatePixmap(self, size: QSize, hline: bool = True, bc: Optional[QColor] = None) -> QPixmap:
        """
        Create a preview of the profile candidate plot.
        :param size:
        :param hline:
        :param bc:
        :return:
        """
        if bc is None:
            bc = QColor('black')
        else:
            bc = QColor(bc)

        # sensorItems = [s for s in self.sensorItems()]
        # ns = len(sensorItems)
        # ns = 2
        lineStyle: PlotStyle = self.mCandidateLineStyle.plotStyle()
        return lineStyle.createPixmap(size, hline=hline, bc=bc)
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


class TPVisGroup(PropertyItemGroup):
    """
    Describes how to display am temporal profile with data from multiple sensors.
    """
    MIME_TYPE = 'application/eotsv/temporalprofiles/PropertyItems'

    sensorNameChanged = pyqtSignal(str, str)

    class ContextGenerator(QgsExpressionContextGenerator):

        def __init__(self, vis_group):
            super().__init__()
            assert isinstance(vis_group, TPVisGroup)
            self.mVisGroup: TPVisGroup = vis_group

        def createExpressionContext(self) -> QgsExpressionContext:
            if self.mVisGroup:
                return self.mVisGroup.createExpressionContext()
            else:
                return QgsExpressionContext()

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        QgsExpressionContextGenerator.__init__(self)
        self.mZValue = 2
        self.mContextGenerator = self.ContextGenerator(self)
        self.mModifiedText: Optional[str] = None

        self.mTimeSeries: Optional[TimeSeries] = None
        self.mLastLayerFields: Dict[str, str] = dict()

        self.setIcon(QIcon(':/eotimeseriesviewer/icons/mIconTemporalProfile.svg'))
        self.mFirstColumnSpanned = True
        self.setEditable(True)
        self.setSelectable(True)

        self.mPField = ProfileFieldItem('Field')
        self.mPField.setToolTip('Field that contains temporal profiles.')

        # self.mPField.label().setIcon(QIcon(':/images/themes/default/mSourceFields.svg'))

        self.mPLineStyle = LineStyleItem('Line')
        self.mPLineStyle.label().setIcon(QIcon(':/images/themes/default/propertyicons/stylepreset.svg'))

        self.mPName = QgsPropertyItem('Name')
        self.mPName.setDefinition(QgsPropertyDefinition(
            'Name', 'Name of the temporal profile.',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPName.setProperty(QgsProperty.fromExpression(''))
        self.mPName.label().setIcon(QIcon(':/images/themes/default/mActionLabeling.svg'))

        self.mPFilter = QgsPropertyItem('Filter')
        self.mPFilter.setDefinition(QgsPropertyDefinition(
            'Filter', 'Filter feature', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPFilter.setProperty(QgsProperty.fromExpression(''))
        self.mPFilter.label().setIcon(QIcon(':/images/themes/default/mActionFilter2.svg'))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLineStyle, self.mPName, self.mPFilter]:
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
        model = self.model()
        if isinstance(model, QAbstractItemModel):
            model.dataChanged.emit(idx, idx)

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

    def setTimeSeries(self, timeseries: TimeSeries):
        self.mTimeSeries = timeseries

        for s in self.sensorItems():
            s.setTimeSeries(timeseries)

    def setField(self, field: Union[str, QgsField, None]):

        if isinstance(field, QgsField):
            field = field.name()
        self.mPField.setField(field)

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer)

        if isinstance(self.mLayer, QgsVectorLayer):
            self.mLastLayerFields[self.mLayer.id()] = self.field()
            self.mLayer.featuresDeleted.disconnect(self.update)

        self.mLayer = layer
        self.mLayer.featuresDeleted.connect(self.update)
        self.mLayer.selectionChanged.connect(self.update)
        self.mLayer.featureAdded.connect(self.update)
        self.mLayer.attributeAdded.connect(self.update)

        if not self.field() in layer.fields().names():
            self.setField(self.mLastLayerFields.get(layer.id()))

    def layer(self) -> Optional[QgsVectorLayer]:
        return self.mLayer

    def createExpressionContext(self) -> QgsExpressionContext:
        """
        Creates the QgsExpressionContext for the QgsVectorLayer related to this Visualization
        :return:
        """
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        if isinstance(self.mLayer, QgsVectorLayer):
            context.appendScope(QgsExpressionContextUtils.layerScope(self.mLayer))
            for f in self.mLayer.getFeatures():
                context.setFeature(f)
                context.setGeometry(QgsGeometry(f.geometry()))
                break
        return context

    def data(self, role: int = ...) -> Any:

        if role in [Qt.DisplayRole, Qt.ToolTipRole, Qt.ForegroundRole]:
            lyr = self.layer()
            is_vector = isinstance(lyr, QgsVectorLayer)
            is_tp_layer = is_vector and TemporalProfileUtils.isProfileLayer(lyr)

            if role == Qt.DisplayRole:
                if is_vector:
                    return lyr.name()
                else:
                    return '<select layer>'

            if role == Qt.ToolTipRole:
                text = []

                if is_vector:
                    if not is_tp_layer:
                        text.append(f'<b>Layer "{lyr.name()}" has no field for temporal profiles!</b>')
                    text.append(lyr.name())
                    text.append(lyr.id())
                else:
                    text.append('Missing vector layer. Select vector layer with field for temporal profiles')
                return '<br>'.join(text)

            if role == Qt.ForegroundRole:
                if not is_tp_layer:
                    return QColor('red')

        return super().data(role)

    def field(self) -> str:
        return self.mPField.field()

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
                if self.mTimeSeries:
                    item.setTimeSeries(self.mTimeSeries)
                item.setCheckState(Qt.Checked)
                self.mSensorItems[sid] = item

                if name:
                    item.setText(name)

                items.append(item)

        if len(items) > 0:
            self.appendRows(items)
            for item in items:
                item.signals().dataChanged.connect(self.update)

    def settingsMap(self, context: QgsExpressionContext = None) -> dict:

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
        d['filter'] = self.mPFilter.mProperty.asExpression().strip()
        d['label'] = self.mPName.mProperty.asExpression().strip()

        return d

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
        self.mSensorName: str = None
        self.mSensorAttributes: dict = None
        self.setEditable(True)
        self.setCheckable(True)
        self.mFirstColumnSpanned = True

        self.setText('<Sensor>')

        self.mTimeSeries: Optional[TimeSeries] = None
        self.mSpeclib: QgsVectorLayer = None

        self.mPSymbol = PlotSymbolItem('Symbol')
        self.mPSymbol.label().setIcon(QIcon(':/images/themes/default/propertyicons/stylepreset.svg'))

        self.mPBand = PythonCodeItem('Band')
        self.mPBand.setToolTip('Band or spectral index to display.')
        self.mPBand.setText('b(1)')
        self.mPBand.setEditable(True)
        self.mPBand.signals().validationRequest.connect(self.validate_sensor_band)
        # self.mPBand.label().setText('Band')

        items = [self.mPSymbol, self.mPBand]
        for item in items:
            self.appendRow(item.propertyRow())

    def setTimeSeries(self, timeseries: TimeSeries):
        assert isinstance(timeseries, TimeSeries)
        self.mTimeSeries = timeseries

    def validate_sensor_band(self, d: dict):

        visGroup = self.parent()
        if not isinstance(visGroup, TPVisGroup):
            return

        expr = d.get('expression')
        feature = d.get('feature')
        code, error = TemporalProfileUtils.prepareBandExpression(expr)
        d['error'] = error

        if error:
            d['preview_text'] = f'<span style="color:red">{error}</span>'
            d['preview_tooltip'] = error
            d['is_valid'] = False
        else:
            sid = self.sensorId()
            field: str = visGroup.field()

            if isinstance(feature, QgsFeature) and field in feature.fields().names():

                tpData = TemporalProfileUtils.profileDict(feature.attribute(field))
                if TemporalProfileUtils.isProfileDict(tpData):
                    sensor_expressions = {sid: expr}

                    if sid in tpData[TemporalProfileUtils.SensorIDs]:
                        results = TemporalProfileUtils.applyExpressions(tpData, feature, sensor_expressions)
                        errors = results['errors']

                        if len(errors) > 0:
                            d['is_valid'] = False
                            d['preview_tooltip'] = '\n'.join(errors)
                            d['preview_text'] = '<span style="color:red">Errors</span>'
                        else:
                            d['is_valid'] = True
                            d['preview_tooltip'] = d['preview_text'] = str(results['y'])
                        s = ""

    def symbolStyle(self) -> PlotStyle:
        return self.mPSymbol.plotStyle()

    def setSensor(self, sid: str, name: str = None):
        self.mSensorID = sid
        self.mSensorAttributes = json.loads(sid)

    def data(self, role: int = ...) -> Any:

        if role in [Qt.DisplayRole, Qt.ToolTipRole, Qt.EditRole]:
            sid = self.mSensorID
            name = None
            if isinstance(self.mTimeSeries, TimeSeries):
                sensor = self.mTimeSeries.sensor(sid)
                if isinstance(sensor, SensorInstrument):
                    name = sensor.name()

            if name is None:
                name = self.mSensorAttributes.get('name')

            if name is None:
                name = self.mSensorName

            if name in [None, '']:
                name = sid

            if role in [Qt.DisplayRole, Qt.EditRole]:
                return name

            if role == Qt.ToolTipRole:
                if name:
                    return f'Sensor: {name} <br>ID: {sid}'
                else:
                    return f'Sensor ID: {sid} <br>'

        return super().data(role)

    def setSensorName(self, name: str):
        if name != self.text():
            self.setText(name)

    def sensorName(self) -> str:
        return self.data(Qt.DisplayRole)

    def layer(self) -> Optional[QgsVectorLayer]:
        parent = self.parent()
        if isinstance(parent, TPVisGroup):
            return parent.layer()
        return None

    def field(self) -> Optional[str]:
        parent = self.parent()
        if isinstance(parent, TPVisGroup):
            return parent.field()
        return None

    def sensorId(self) -> str:
        return self.mSensorID

    def settingsMap(self, context: QgsExpressionContext = None) -> dict:

        band = self.mPBand.text()

        d = {'sensor_id': self.sensorId(),
             'sensor_name': self.sensorName(),
             'show': self.checkState() == Qt.Checked,
             'expression': band,
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

        self.mProject: QgsProject = QgsProject.instance()

        self.mSettingsNode = TPVisSettings()
        self.insertRow(0, self.mSettingsNode)

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project

    def project(self) -> QgsProject:
        return self.mProject

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

    def visualizations(self) -> List[TPVisGroup]:
        return [v for v in self.mVisualizations if isinstance(v, TPVisGroup)]

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

    def setData(self, index, value, role=None) -> bool:

        if role == Qt.EditRole:
            item = index.data(Qt.UserRole)
            c = index.column()
            # change the name of a sensor directly as the SensorInstrument, if available
            if c == self.cName and isinstance(item, TPVisSensor):
                sensor = self.mSensors.get(item.sensorId())
                if isinstance(sensor, SensorInstrument) and value != sensor.name():
                    sensor.setName(value)
                    return True

        return super().setData(index, value, role)

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
            node.emitDataChanged()

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

    def settingsMap(self, context: QgsExpressionContext = None) -> dict:
        """
        Collect all settings
        :return:
        """
        if context is None:
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.globalScope())
            context.appendScope(QgsExpressionContextUtils.projectScope(self.project()))

        d = dict()
        d['candidates'] = self.mSettingsNode.settingsMap(context=context)
        d['visualizations'] = [v.settingsMap(context=context) for v in self.mVisualizations]
        return d


class PlotSettingsTreeView(QTreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mProject: QgsProject = QgsProject.instance()

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project

    def project(self) -> QgsProject:
        return self.mProject

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

    @classmethod
    def createSpectralIndexMenu(cls, menu: QMenu) -> QMenu:
        indices = spectral_indices()
        pass

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        selected_indices = self.selectionModel().selectedRows()
        for idx in selected_indices:
            item = idx.data(Qt.UserRole)
            if isinstance(item, PropertyLabel):
                item = item.propertyItem()

            parentItem = item.parent()

            sensorItems = []
            if isinstance(item, TPVisSensor):
                sensorItems.append(item)
            elif isinstance(item, TPVisGroup):
                sensorItems.extend(item.sensorItems())
            elif isinstance(parentItem, TPVisSensor):
                sensorItems.append(parentItem)
            elif isinstance(parentItem, TPVisGroup):
                sensorItems.extend(parentItem.sensorItems())

            if len(sensorItems) > 0:
                code_items = [s.mPBand for s in sensorItems]
                self.addSpectralIndexMenu(menu, code_items)

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def addSpectralIndexMenu(self, menu: QMenu, code_items: List[PythonCodeItem]) -> QMenu:
        assert isinstance(menu, QMenu)
        for i in code_items:
            assert isinstance(i, PythonCodeItem)

        m: QMenu = menu.addMenu('Spectral Index')
        indices = spectral_indices()
        DOMAINS = dict()
        for idx in indices.values():
            d = idx['application_domain']
            if d not in ['kernel']:
                DOMAINS[d] = DOMAINS.get(d, []) + [idx]
        for d in sorted(DOMAINS.keys()):
            d: str
            mDomain: QMenu = m.addMenu(d.title())
            mDomain.setToolTipsVisible(True)
            indices = DOMAINS[d]
            for batch in itertools.batched(indices, 10):
                mBatch: QMenu = mDomain.addMenu(f'{batch[0]['short_name']} - {batch[-1]['short_name']}')
                mBatch.setToolTipsVisible(True)
                for idx in batch:
                    a: QAction = mBatch.addAction(idx['short_name'])
                    ln = idx['long_name']
                    sn = idx['short_name']
                    link = idx.get('reference')
                    tt = f'{idx['long_name']}<br>{idx['formula']}<br><a href="{link}">{link}</a>'
                    a.setText(f'{sn} - {ln}')
                    a.setToolTip(tt)

                    a.setData(idx['formula'])
                    a.triggered.connect(lambda *args, _a=a, _i=code_items: self.setSpectralIndex(_a, _i))

        return m

    def setSpectralIndex(self, a: QAction, items: List[PythonCodeItem]):
        expr = a.data()
        for item in items:
            item.setExpression(expr)


class PlotSettingsTreeViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: PlotSettingsTreeView, parent=None):
        assert isinstance(treeView, PlotSettingsTreeView)
        super().__init__(parent=parent)
        self.mTreeView = treeView

    def project(self) -> QgsProject:
        return self.mTreeView.project()

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
                if option.state & QStyle.State_Selected:
                    # Set the background color to blue for selected items
                    # painter.save()
                    selection_color = option.palette.highlight().color()
                    painter.fillRect(option.rect, selection_color)
                    # painter.restore()
                    pass
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                if item.icon():
                    to_paint.append(item.icon())

                h = option.rect.height()

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
                if total_h > 0 and total_w > 0:
                    px = None
                    size = QSize(total_w, total_h)
                    if isinstance(parentItem, TPVisGroup):
                        px = parentItem.createPixmap(size=size, bc=bc)
                    elif isinstance(parentItem, TPVisSettings):
                        px = parentItem.createProfileCandidatePixmap(size=size, bc=bc)

                    if isinstance(px, QPixmap):
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
            item: QStandardItem = index.data(Qt.UserRole)

            # default
            if isinstance(item, PropertyItem):
                editor = item.createEditor(parent)
                parentItem = item.parent()
                if isinstance(parentItem, TPVisGroup) and isinstance(editor, QgsFieldExpressionWidget):
                    editor.registerExpressionContextGenerator(parentItem.mContextGenerator)
                    lyr = parentItem.layer()
                    if isinstance(lyr, QgsVectorLayer):
                        editor.setLayer(lyr)

                if isinstance(parentItem, TPVisSensor) and isinstance(editor, FieldPythonExpressionWidget):
                    # editor.previewRequest.connect()
                    pass

            if isinstance(item, TPVisGroup):
                # editor = TemporalProfileLayerComboBox(parent=parent)
                editor = TemporalProfileLayerFieldComboBox(parent=parent, project=self.project())

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

            parentItem = item.parent()

            if isinstance(item, PythonCodeItem) and isinstance(parentItem, TPVisSensor):
                if isinstance(editor, FieldPythonExpressionWidget):
                    lyr = parentItem.layer()
                    field = parentItem.field()
                    if isinstance(lyr, QgsVectorLayer):
                        editor.setLayer(lyr)
                s = ""
        elif isinstance(item, TPVisGroup):

            if isinstance(editor, TemporalProfileLayerFieldComboBox):
                editor.setProject(self.project())

                layer = item.layer()
                field = item.field()

                editor.setLayerField(layer, field)
        else:
            super().setEditorData(editor, index)
        return

    def setModelData(self, w: QWidget, model: QAbstractItemModel, index: QModelIndex):

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setModelData(w, model, index)
        elif isinstance(item, TPVisGroup) and isinstance(w, TemporalProfileLayerFieldComboBox):
            icon = w.currentData(Qt.DecorationRole)
            w: TemporalProfileLayerFieldComboBox
            lyr, field = w.layerField()
            if isinstance(lyr, QgsVectorLayer) and field:
                item.setLayer(lyr)
                item.setField(field)
                item.setIcon(icon)

        else:
            super().setModelData(w, model, index)


class PlotSettingsProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)  # search filter uses all columns

    def filterAcceptsRow(self, row: int, parent: QModelIndex):
        index = self.sourceModel().index(row, 0, parent)
        if super().filterAcceptsRow(row, parent):
            return True

        # Check if any child rows match the filter
        child_count = self.sourceModel().rowCount(index)
        for child_row in range(child_count):
            if self.filterAcceptsRow(child_row, index):
                return True

        return False


class PlotSettingsContextGenerator(QgsExpressionContextGenerator):

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
