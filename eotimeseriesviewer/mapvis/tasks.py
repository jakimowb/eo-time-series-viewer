from pathlib import Path
from typing import Union, Optional, Tuple, Type, List, Dict

from qgis.core import QgsRasterLayer, QgsMapLayer, QgsVectorTileLayer, QgsVectorLayer, Qgis, QgsRasterFileWriter, \
    QgsVectorFileWriter

from eotimeseriesviewer.tasks import EOTSVTask

LAYER_CLASSES = dict()
for l in [QgsRasterLayer, QgsVectorLayer, QgsVectorTileLayer]:
    LAYER_CLASSES[l] = l
    LAYER_CLASSES[l.__name__] = l
LAYER_CLASSES[Qgis.LayerType.Vector] = QgsVectorLayer
LAYER_CLASSES[Qgis.LayerType.Raster] = QgsRasterLayer
LAYER_CLASSES[Qgis.LayerType.VectorTile] = QgsVectorTileLayer


class LoadMapCanvasLayers(EOTSVTask):
    # executed = pyqtSignal(bool, object)

    # a dictionary for supported map layer constructors

    tasks: List[EOTSVTask] = []

    @staticmethod
    def addTask(task: EOTSVTask):
        """
        Keeps a global reference on tasks
        """
        assert isinstance(task, LoadMapCanvasLayers)
        LoadMapCanvasLayers.tasks.append(task)

    @staticmethod
    def removeTask(task):
        if task in LoadMapCanvasLayers.tasks:
            LoadMapCanvasLayers.tasks.remove(task)

    def __init__(self, sources: List[dict], *args, **kwds):
        """
        Loads QgsMapLayers in a thread
        :param sources: dictionary of type {source id string: source description}
        :param args:
        :param kwds:
        """
        super().__init__()
        assert isinstance(sources, List)
        for s in sources:
            assert isinstance(s, dict)
        self.mSources: List[dict] = sources.copy()
        self.mResults: List[dict] = list()
        self.mErrors: Dict[str, str] = dict()

    def canCancel(self):
        return False

    def layerClass(self, source: Union[Path, str]) -> Optional[Type[QgsMapLayer]]:
        uri = str(source)
        lyrClass = None
        ext = Path(uri).suffix

        if ext in ['.geojson', '.gpkg']:
            lyrClass = QgsVectorLayer
        elif ext in ['.tif', '.bsq', '.bip', '.bil']:
            lyrClass = QgsRasterLayer
        elif ext in ['.pbf']:
            lyrClass = QgsVectorTileLayer
        elif QgsRasterFileWriter.driverForExtension(ext) != '':
            lyrClass = QgsRasterLayer
        elif QgsVectorFileWriter.driverForExtension(ext) != '':
            lyrClass = QgsVectorLayer
        return lyrClass

    def loadLayer(self, info: dict) -> Tuple[Optional[QgsMapLayer], Optional[str]]:
        uri = str(info['uri'])
        t = info.get('type', self.layerClass(uri))

        lyrClass = LAYER_CLASSES.get(t, None)

        customProperties = info.get('customProperties', {})

        # extract arguments that cannot be passed as keywords
        err = None
        # get layer options
        lyr = None

        if lyrClass is QgsRasterLayer:
            options = QgsRasterLayer.LayerOptions()
            options.loadDefaultStyle = info.get('loadDefaultStyle', False)
            lyr = QgsRasterLayer(uri, options=options)
        elif lyrClass is QgsVectorLayer:
            options = QgsVectorLayer.LayerOptions()
            options.loadDefaultStyle = info.get('loadDefaultStyle', True)
            lyr = QgsVectorLayer(uri, options=options)
        else:
            raise NotImplementedError(f'Unsupported layer type: {lyrClass}')

        if not isinstance(lyr, QgsMapLayer):
            return None, f'Unable to load {uri} as QgsMapLayer'
        if not lyr.isValid():
            return None, f'Unable to load {uri} as QgsMapLayer: {lyr.error()}'

        if 'layer_name' in info:
            lyr.setName(info['layer_name'])

        for k, v in customProperties.items():
            lyr.setCustomProperty(k, v)

        return lyr, None

    def run(self):

        for info in self.mSources:
            uri = info.get('uri')
            if uri is None:
                continue

            legend_layer_id = info.get('legend_layer')
            lyr = None
            try:
                lyr, err = self.loadLayer(info)
                if err:
                    self.mErrors[str(uri)] = err
                    continue
            except Exception as ex:
                self.mErrors[str(uri)] = f'Unable to load {uri} {ex}'.strip()
                continue
            if isinstance(lyr, QgsMapLayer):
                result = {'uri': uri, 'legend_layer': legend_layer_id, 'layer': lyr}
                self.mResults.append(result)

        # self.executed.emit(True, self)

        return True
