import json
from pathlib import Path
from typing import Optional, Union

from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterDefinition

path_json = Path(__file__)
path_json = path_json.parent / (path_json.stem + '.json')


class AlgorithmHelp(object):
    with open(path_json, 'r') as f:
        JSON = json.load(f)
        JSON = {j['name']: j for j in JSON}

    @classmethod
    def alg_name(cls, alg: Union[QgsProcessingAlgorithm, str]):
        if isinstance(alg, QgsProcessingAlgorithm):
            alg = alg.__class__.__name__
        if alg not in cls.JSON:
            alg = alg.lower()

        assert isinstance(alg, str)
        return alg

    @classmethod
    def shortHelpString(cls, alg: QgsProcessingAlgorithm, default: Optional[str] = None) -> str:
        an = cls.alg_name(alg)
        data: dict = cls.JSON.get(an, {})

        info = [f'<p>{data.get('shortHelpString', default)}</p>']

        for p in alg.parameterDefinitions():
            p: QgsProcessingParameterDefinition
            info += ['<p>']
            info += [f'<b>{p.description()}</b> {p.help()}']
            info += [f"Python identifier: <i>'{p.name()}'</i>"]
            if p.defaultValue() not in ['', None]:
                info += [f'<i>default value: {p.defaultValue()}</i>']
            info += ['</p>']
        return '\n'.join(info)
