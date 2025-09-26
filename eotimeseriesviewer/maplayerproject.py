from typing import Iterable, List, Union

from qgis.core import QgsMapLayer, QgsProject


class EOTimeSeriesViewerProject(QgsProject):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setTitle('EOTimeSeriesViewer')
        self.mLayerRefs: list[QgsMapLayer] = []

    def __repr__(self):
        return f'<{self.__class__.__name__}: "{self.title()}">'

    def removeAllMapLayers(self):
        self.mLayerRefs.clear()
        super().removeAllMapLayers()
        self.mLayerRefs.clear()

    def addMapLayer(self, mapLayer: QgsMapLayer, *args, **kwds) -> QgsMapLayer:
        # self.debugPrint('addMapLayer')
        lyr = super().addMapLayer(mapLayer, *args, **kwds)
        if isinstance(lyr, QgsMapLayer) and lyr not in self.mLayerRefs:
            self.mLayerRefs.append(lyr)
        return lyr

    def addMapLayers(self, mapLayers: Iterable[QgsMapLayer], *args, **kwargs):
        # self.debugPrint(f'addMapLayers {mapLayers}')
        added_layers = super().addMapLayers(mapLayers)
        for lyr in added_layers:
            if lyr not in self.mLayerRefs:
                self.mLayerRefs.append(lyr)
        return added_layers

    def removeMapLayers(self, layers: List[Union[str, QgsMapLayer]]):

        result = super().removeMapLayers([lyr.id() if isinstance(lyr, QgsMapLayer) else lyr for lyr in layers])

        for lyr in layers:
            if isinstance(lyr, str):
                lyr = self.mapLayer(lyr)
            if lyr in self.mLayerRefs:
                self.mLayerRefs.remove(lyr)
        return result

    def takeMapLayer(self, layer: QgsMapLayer, **kwargs) -> QgsMapLayer:
        if layer in self.mLayerRefs:
            self.mLayerRefs.remove(layer)
        return super().takeMapLayer(layer)

    def debugPrint(self, msg: str = ''):

        keysE = list(self.mapLayers().keys())
        if len(keysE) != len(self.mLayerRefs):
            print('Warning: differing layer refs')
        keysQ = list(QgsProject.instance().mapLayers().keys())

        rows = [['EOTSV', 'QGIS', 'Layer ID']]
        for k in sorted(set(keysE + keysQ)):
            rows.append([str(k in keysE), str(k in keysQ), k])
        info = '\n'.join([msg] + ['{:<8}\t{:<4}\t{}'.format(*row) for row in rows])
        if len(rows) == 1:
            info += '\t - no map layers -'
        print(info, flush=True)
