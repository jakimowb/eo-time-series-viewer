import os.path
import re
from pathlib import Path
from typing import Dict

from eotimeseriesviewer import icon
from eotimeseriesviewer.processing.algorithmhelp import AlgorithmHelp
from eotimeseriesviewer.qgispluginsupport.qps.fieldvalueconverter import GenericFieldValueConverter, \
    GenericPropertyTransformer
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from eotimeseriesviewer.timeseries.source import TimeSeriesSource
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from qgis.PyQt.QtCore import NULL, QMetaType, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsCoordinateTransform, QgsRasterLayer, QgsProject
from qgis.core import edit, Qgis, QgsApplication, QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsMapLayer, \
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingException, QgsProcessingFeedback, \
    QgsProcessingOutputVectorLayer, QgsProcessingParameterBoolean, QgsProcessingParameterCrs, \
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFieldMapping, QgsProcessingParameterFile, \
    QgsProcessingParameterNumber, QgsProcessingParameterString, QgsProcessingParameterVectorLayer, \
    QgsProcessingProvider, QgsProcessingRegistry, QgsProcessingUtils, QgsVectorFileWriter, QgsVectorLayer


class CreateEmptyTemporalProfileLayer(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    FIELD_NAMES = 'FIELD_NAMES'
    OTHER_FIELDS = 'OTHER_FIELDS'
    CRS = 'CRS'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._dest_id = None

    def initAlgorithm(self, config: Dict = None):
        # self.addParameter(
        #    QgsProcessingParameterGeometry(
        #        self.GEOMETRY,
        #        description="Geometry Type",
        #        defaultValue=Qgis.GeometryType.Point,
        #        geometryTypes=[Qgis.GeometryType.Point]
        #    )
        # )

        p1 = QgsProcessingParameterCrs(
            self.CRS,
            description="Coordinate Reference System",
            defaultValue='EPSG:4326'
        )
        p1.setHelp('Coordinate Reference System for the output layer.')

        p2 = QgsProcessingParameterString(
            self.FIELD_NAMES,
            description="Profile Field Name(s)",
            defaultValue="profiles")
        p2.setHelp(
            'Name of the field to store temporal profiles. '
            "To add multiple fields separate field names by ',' or whitespace")

        p4 = QgsProcessingParameterFieldMapping(
            self.OTHER_FIELDS,
            description='Other fields to add',
            optional=True,
        )
        p4.setHelp('Define other fields and their data types to be added.')

        p3 = QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            description="Output Vector Layer",
            type=Qgis.ProcessingSourceType.VectorPoint,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT,
            createByDefault=True)
        p3.setHelp('Path of output vector.')

        for p in [p1, p2, p3, p4]:
            self.addParameter(p)

    def processAlgorithm(self, parameters, context, feedback):
        # geom_type = self.parameterAsEnum(parameters, self.GEOMETRY, context)

        feedback.pushInfo(f"Parameters: {parameters}")
        geom_type = Qgis.WkbType.Point
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        field_names = self.parameterAsString(parameters, self.FIELD_NAMES, context)
        field_names = re.split(r'[,;: ]+', field_names)

        fields = QgsFields()
        other_fields: dict = parameters.get(self.OTHER_FIELDS, {})

        default_field_attributes = {
            'alias': None,
            'comment': None,
            'expression': None,
            'length': 0,
            'precision': 0,
            'sub_type': 0,
            'type': 10,
            'type_name': 'text'}

        # LUT between output QgsProcessingParameterFeatureSink and keywords of QgsField
        LUT_KW = {
            'name': 'name',
            'type': 'type',
            'type_name': 'typeName',
            'length': 'len',
            'precision': 'prec',
            'comment': 'comment',
            'sub_type': 'subType'
        }

        for fdef in other_fields:
            fdef: dict
            # replace QVariant() with None
            for k in fdef.keys():
                if fdef[k] in [QVariant(), NULL]:
                    fdef[k] = None

            if 'name' not in fdef:
                raise QgsProcessingException(f'{self.OTHER_FIELDS} description misses "name": {fdef}')
            fname = fdef['name']
            if fname in field_names:
                new_field = TemporalProfileUtils.createProfileField(fname)
                if 'comment' in fdef:
                    new_field.setComment(fdef['comment'])
            else:

                field_kw = default_field_attributes.copy()
                field_kw.update(fdef)
                field_kw = {LUT_KW[k]: v for k, v in field_kw.items() if k in LUT_KW}

                new_field = QgsField(**field_kw)
            if 'alias' in fdef:
                new_field.setAlias(fdef['alias'])
            fields.append(new_field)

        for fn in field_names:
            if fn not in fields.names():
                fields.append(TemporalProfileUtils.createProfileField(fn))

        profile_fields = [f.name() for f in fields if TemporalProfileUtils.isProfileField(f)]

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields=fields,
                                               geometryType=geom_type,
                                               crs=crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        if hasattr(sink, 'finalize'):
            sink.finalize()
        else:
            sink.flushBuffer()

        del sink
        lyr = QgsProcessingUtils.mapLayerFromString(dest_id, context)

        for f in profile_fields:
            i = lyr.fields().indexFromName(f)
            assert i >= 0, f'Failed to generate profile field "{f}"'
            lyr.setEditorWidgetSetup(i, TemporalProfileUtils.widgetSetup())
        lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback: QgsProcessingFeedback):

        result = {}
        if self._dest_id:
            lyr = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            assert isinstance(lyr, QgsVectorLayer)
            assert lyr.isValid()
            # lyr.setEditorWidgetSetup(self._field_id, TemporalProfileUtils.widgetSetup())
            lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
            assert TemporalProfileUtils.isProfileLayer(lyr)
            # context.project().addMapLayer(lyr)
            result[self.OUTPUT] = self._dest_id

        # context.project().addMapLayer(self._layer)
        return result

    def createInstance(self):
        return self.__class__()

    @classmethod
    def name(cls):
        return cls.__name__.lower()

    def displayName(self):
        return "Create Temporal Profile Layer"

    def shortHelpString(self):
        return AlgorithmHelp.shortHelpString(self,
                                             default='Create a new point layer with a field to store temporal profiles.')


class AddTemporalProfileField(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    FIELD_NAME = 'FIELD_NAME'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.Flag.FlagNoThreading

    def initAlgorithm(self, config: Dict = None):

        p1 = QgsProcessingParameterVectorLayer(
            self.INPUT,
            description="Vector Layer")
        p1.setHelp('The vector Layer to append a field for temporal profiles.')

        p2 = QgsProcessingParameterString(
            self.FIELD_NAME,
            description="Field Name",
            defaultValue="profiles")
        p2.setHelp(
            'Name of the field to store temporal profiles.')

        for p in [p1, p2]:
            self.addParameter(p)
        o1 = QgsProcessingOutputVectorLayer(self.INPUT, 'Modified layer')
        self.addOutput(o1)

    def prepareAlgorithm(self, parameters: dict, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        field_name = self.parameterAsString(parameters, self.FIELD_NAME, context)
        lyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        if not (isinstance(lyr, QgsVectorLayer) and lyr.isValid()):
            feedback.pushError(f"Unable to open {parameters[self.INPUT]} as a vector layer.")
            return False

        if field_name in lyr.fields().names():
            feedback.pushInfo(f'Field "{field_name}" already exists.')
            return False

        return True

    def processAlgorithm(self, parameters, context, feedback):
        # geom_type = self.parameterAsEnum(parameters, self.GEOMETRY, context)

        field_name = self.parameterAsString(parameters, self.FIELD_NAME, context)
        lyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)

        with edit(lyr):
            lyr.addAttribute(TemporalProfileUtils.createProfileField(field_name))
        i = lyr.fields().indexFromName(field_name)
        lyr.setEditorWidgetSetup(i, TemporalProfileUtils.widgetSetup())
        lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)

        return {self.INPUT: lyr}

    def createInstance(self):
        return self.__class__()

    @classmethod
    def name(cls):
        return cls.__name__.lower()

    def displayName(self):
        return "Add Temporal Profile field"

    def shortHelpString(self):
        return AlgorithmHelp.shortHelpString(self, default="Adds a field to store temporal profiles.")


class ReadTemporalProfiles(QgsProcessingAlgorithm):
    INPUT = 'LAYER'
    TIMESERIES = 'TIMESERIES'
    FIELD_NAME = 'FIELD_NAME'
    N_THREADS = 'N_THREADS'
    OUTPUT = 'OUTPUT'
    ADD_SOURCES = 'ADD_SOURCES'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self._n_threads = None
        self._layer = None
        self._sources = []
        self._field_name = None
        self._dest_id = None
        self._field_id = None

    def flags(self):
        return super().flags() | Qgis.ProcessingAlgorithmFlag.CanCancel

    def initAlgorithm(self, config: Dict = None):
        p1 = QgsProcessingParameterVectorLayer(
            self.INPUT,
            "Input Vector Layer",
            [QgsProcessing.TypeVectorPoint]
        )
        p1.setHelp('Point vector layer with coordinates to read temporal profiles from.')

        p2 = QgsProcessingParameterFile(
            self.TIMESERIES,
            description='Time Series',
            optional=True,
            defaultValue=None,
        )
        p2.setHelp('A text file (*.csv) with the time series raster sources to read profiles from. '
                   'If not set, the temporal profiles will be read from the time series '
                   'shown in the EO Time Series Viewer')

        p3 = QgsProcessingParameterString(
            self.FIELD_NAME,
            description="Temporal Profile Field",
            defaultValue='profiles',
            optional=True
        )
        p3.setHelp('The new field name to store the temporal profiles in.')

        p4 = QgsProcessingParameterNumber(
            self.N_THREADS,
            description="Number of threads used to read files",
            type=QgsProcessingParameterNumber.Integer,
            minValue=1,
            maxValue=16,
            defaultValue=4,
        )
        p4.setHelp('Number of threads to read raster sources in parallel. Can be a value between 1 and 16.')

        p5 = QgsProcessingParameterBoolean(
            self.ADD_SOURCES,
            description='Save source path in temporal profiles',
            defaultValue=False,
        )
        p5.setHelp('Set True to store the file path of each source image in the temporal profile json')

        p6 = QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            description="Calculated",
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT,
        )
        p6.setHelp('Name of the create vector layer with temporal profiles.')
        for p in [p1, p2, p3, p4, p5, p6]:
            self.addParameter(p)

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        input_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        if not isinstance(input_layer, QgsVectorLayer) or not input_layer.isValid():
            feedback.reportError(f"Invalid input layer {parameters[self.INPUT]}", True)
            return False

        crs = input_layer.crs()
        if not crs.isValid():
            feedback.reportError(f'Layer CRS is invalid: {parameters[self.INPUT]}\n{crs.description()}')
            return False

        time_series = self.parameterAsFile(parameters, self.TIMESERIES, context)
        if time_series == '':
            time_series = self.parameterAsFileList(parameters, self.TIMESERIES, context)
            time_series = [t for t in time_series if t != '']

        if time_series in ['', [], None]:
            # set to None and use from running EOTSV instance (see below)
            time_series = None

        profile_field = self.parameterAsStrings(parameters, self.FIELD_NAME, context)

        if not input_layer.wkbType() == Qgis.WkbType.Point:
            feedback.pushError("Input layer must be a point layer.")
            return False

        if not len(profile_field) == 1:
            feedback.pushError(f"Invalid field name {profile_field}")
            return False

        profile_field = profile_field[0]
        if profile_field in input_layer.fields().names():
            field = input_layer.fields()[profile_field]

            if not field.type() in [QMetaType.QString, QMetaType.QVariantMap]:
                feedback.pushError(f"Field {profile_field} does not support storing of temporal profiles.")
                return False

        sources = None
        if time_series is None:
            from eotimeseriesviewer.main import EOTimeSeriesViewer
            tsv = EOTimeSeriesViewer.instance()
            if isinstance(tsv, EOTimeSeriesViewer):
                sources = [s.source() for s in tsv.timeSeries().sources()]
        elif isinstance(time_series, list):
            sources = [str(l) for l in time_series]
        elif isinstance(time_series, str):
            sources = TimeSeries.sourcesFromFile(time_series)
            sources = [s.source() if isinstance(s, TimeSeriesSource) else s for s in sources]

        if not (isinstance(sources, list) and len(sources) > 0):
            feedback.pushError("No time series sources defined. Define CSV file with sources or "
                               "open EO Time Series Viewer with source files.")
            return False

        # test coordinate conversion on 1st raster
        options = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
        lyr1 = QgsRasterLayer(sources[0], options=options)
        trans = QgsCoordinateTransform(crs, lyr1.crs(), QgsProject.instance())
        if not trans.isValid():
            feedback.reportError(f'Unable to transform vector CRS to raster CRS: {crs.description()}')
            return False

        out_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if out_path.startswith('memory:'):
            out_driver = 'memory'
        elif out_path.startswith('ogr:') and '.gpkg' in out_path.lower():
            out_driver = 'GPKG'
        else:
            if os.path.isfile(out_path):
                Path(out_path).unlink()

            out_driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(out_path)[1])
            if out_driver in ['', None]:
                feedback.reportError(f'Unable to identify vector driver for output path: "{out_path}"', True)
                return False

        self._output_driver = out_driver
        self._n_threads = self.parameterAsInt(parameters, self.N_THREADS, context)
        self._field_name = profile_field
        self._sources = sources
        return True

    def processAlgorithm(self, parameters: dict, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> dict:

        # collect geometries
        input_layer: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        save_source_path: bool = self.parameterAsBoolean(parameters, self.ADD_SOURCES, context)
        points = []
        fids = []
        for f in input_layer.getFeatures():
            fids.append(f.id())
            points.append(f.geometry().asPoint())

        feedback.pushInfo(f'Load temporal profiles for {len(points)} points from up to {len(self._sources)} '
                          f'raster sources with {self._n_threads} threads.')
        task = LoadTemporalProfileTask(self._sources,
                                       points,
                                       input_layer.crs(),
                                       n_threads=self._n_threads,
                                       save_sources=save_source_path,
                                       description='Load temporal profiles')

        task.setDescription('Load Temporal Profile')

        def onProgress(progress: float):

            feedback.setProgress(progress)
            if feedback.isCanceled():
                task.cancel()

        task.progressChanged.connect(onProgress)
        try:
            task.run_task_manager()
        except Exception as ex:
            feedback.pushError(str(ex))
            return {}

        if feedback.isCanceled():
            feedback.pushInfo("Task canceled.")
            return {}

        points, profiles = task.profilePoints(), task.profiles()
        fn = self._field_name

        fields = QgsFields(input_layer.fields())

        if fn in fields.names():
            is_new = False
        else:
            fields.append(TemporalProfileUtils.createProfileField(fn))
            is_new = True
        self._field_id = fields.indexFromName(fn)

        fields = GenericFieldValueConverter.compatibleTargetFields(fields, self._output_driver)
        func = GenericPropertyTransformer.fieldValueTransformFunction(fields[self._field_id])

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            input_layer.wkbType(),
            input_layer.crs(),
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        for i, feat in enumerate(input_layer.getFeatures()):
            feat: QgsFeature
            if feedback.isCanceled():
                break

            attrs = feat.attributes()

            # set new profile field
            value = None
            if feat.id() in fids:
                i_profile = fids.index(feat.id())
                profile = profiles[i_profile]
                if profile:
                    value = func(profile)
                    s = ""
            # write features
            if is_new:
                attrs.append(value)
                feat.setAttributes(attrs)
            else:
                feat.setAttribute(self._field_id, value)
            sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)

        if hasattr(sink, 'finalize'):
            sink.finalize()
        else:
            sink.flushBuffer()
        # del sink

        # lyr = QgsProcessingUtils.mapLayerFromString(dest_id, context)
        # lyr.setEditorWidgetSetup(self._field_id, TemporalProfileUtils.widgetSetup())
        # lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
        # assert TemporalProfileUtils.isProfileLayer(lyr)
        context.feedback().setProgress(100)
        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        s = ""
        result = dict()
        assert self._dest_id
        if self._dest_id:
            lyr = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            assert isinstance(lyr, QgsVectorLayer)
            assert lyr.isValid()
            lyr.setEditorWidgetSetup(self._field_id, TemporalProfileUtils.widgetSetup())
            lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
            assert TemporalProfileUtils.isProfileLayer(lyr)
            result[self.OUTPUT] = self._dest_id
            self._layer = lyr

        return result

    def createInstance(self):
        return self.__class__()

    @classmethod
    def name(cls):
        return cls.__name__.lower()

    # def id(self):
    #    return self.name().lower()

    def displayName(self):
        return "Read Temporal Profiles"

    def shortHelpString(self):
        return AlgorithmHelp.shortHelpString(self,
                                             default="Adds a new field 'name' to the input vector layer "
                                                     "and populates it with extracted temporal profiles.")


class EOTSVProcessingProvider(QgsProcessingProvider):
    _INSTANCE = None

    @staticmethod
    def instance() -> 'EOTSVProcessingProvider':
        if EOTSVProcessingProvider._INSTANCE is None:
            EOTSVProcessingProvider._INSTANCE = EOTSVProcessingProvider()
        return EOTSVProcessingProvider._INSTANCE

    @staticmethod
    def registerProvider() -> bool:
        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        provider = registry.providerById(EOTSVProcessingProvider.id())
        if not isinstance(provider, EOTSVProcessingProvider):
            return registry.addProvider(EOTSVProcessingProvider.instance())
        return True

    @staticmethod
    def unregisterProvider() -> bool:
        registry: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        provider = registry.providerById(EOTSVProcessingProvider.id())
        if isinstance(provider, EOTSVProcessingProvider):
            if registry.removeProvider(provider):
                EOTSVProcessingProvider._INSTANCE = None
                return True
        return False

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._algs = []

    def load(self):
        self.refreshAlgorithms()
        return True

    def refreshAlgorithms(self):
        self._algs.clear()
        self.loadAlgorithms()

    def longName(self):
        return 'EO Time Series Viewer'

    @classmethod
    def id(cls) -> str:
        return 'eotsv'

    @classmethod
    def name(cls) -> str:
        return 'EO Time Series Viewer'

    def helpId(self):
        return self.id()

    def icon(self) -> QIcon:
        return icon()

    def svgIconPath(self):
        return r':/qps/ui/icons/profile_expression.svg'

    def loadAlgorithms(self):

        for a in [
            CreateEmptyTemporalProfileLayer(),
            AddTemporalProfileField(),
            ReadTemporalProfiles()
        ]:
            self.addAlgorithm(a)
            self._algs.append(a)

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True

    def addAlgorithm(self, algorithm: QgsProcessingAlgorithm, **kwargs) -> bool:
        result = super().addAlgorithm(algorithm)
        if result:
            # keep a reference

            self._algs.append(algorithm)
        return result
