from pathlib import Path
from typing import Union, Optional, Tuple, Dict, Type

from PyQt5.QtCore import pyqtSignal
from qgis._core import QgsRasterLayer, QgsMapLayer, QgsVectorTileLayer, QgsVectorLayer, Qgis, QgsRasterFileWriter, \
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
    executed = pyqtSignal(bool, object)

    # a dictionary for supported map layer constructors

    def __init__(self, sources: Dict[str, Union[None, str, dict]], *args, **kwds):
        """
        Loads QgsMapLayers in a thread
        :param sources: dictionary of type {source id string: source description}
        :param args:
        :param kwds:
        """
        super().__init__()
        if isinstance(sources, list):
            sources = {s: None for s in sources}

        assert isinstance(sources, dict)

        for k, v in sources.items():
            assert isinstance(k, str)
            assert v is None or isinstance(v, (str, dict))

        self.mSources: Dict[str, Union[None, str, dict]] = sources.copy()
        self.mResults: Dict[str, QgsMapLayer] = dict()
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

    def loadLayer(self, source) -> Tuple[Optional[QgsMapLayer], Optional[str]]:
        uri = lyr = err = None
        lyrClass = None

        kwds = dict()
        args = []
        customProperties: dict = dict()

        if isinstance(source, (Path, str)):
            lyrClass = self.layerClass(source)
            args = [str(source)]

        elif isinstance(source, dict):
            kwds = source.copy()
            if 'type' in source:
                t = kwds.pop('type')
                if t not in LAYER_CLASSES:
                    return None, f'Unknown layer type: {t}'
                lyrClass = LAYER_CLASSES[t]
            if 'customProperties' in kwds:
                customProperties.update(kwds.pop('customProperties'))

        if lyrClass is None:
            return None, f'Unable to identify layer type for {source}'

        # extract arguments that cannot be passed as keywords

        # get layer options
        options = lyrClass.LayerOptions()
        if 'loadDefaultStyle' in kwds:
            options.loadDefaultStyle = kwds.pop('loadDefaultStyle')

        kwds['options'] = options

        if lyrClass is QgsRasterLayer:
            if 'uri' in kwds:
                args.append(kwds.pop('uri'))

        lyr = lyrClass(*args, **kwds)
        if not isinstance(lyr, QgsMapLayer):
            return None, f'Unable to load {source} as QgsMapLayer'
        if not lyr.isValid():
            return None, f'Unable to load {source} as QgsMapLayer: {lyr.error()}'

        for k, v in customProperties.items():
            lyr.setCustomProperty(k, v)

        return lyr, err

    def run(self):

        for sourceId, source in self.mSources.items():
            if source is None:
                source = sourceId
            try:
                lyr, err = self.loadLayer(source)
            except Exception as ex:
                self.mErrors[sourceId] = f'Unable to load {sourceId} {ex}'.strip()
                continue

            if isinstance(lyr, QgsMapLayer):
                if lyr.isValid():
                    self.mResults[sourceId] = lyr
                else:
                    self.mErrors[sourceId] = f'Unable to load {sourceId} {lyr.error()}'.strip()

            if err:
                self.mErrors[sourceId] = str(err)

        self.executed.emit(True, self)

        return True
