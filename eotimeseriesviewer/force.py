import os
import re
from typing import Iterator, List, Union
from pathlib import Path

rxFORCE_TILE = re.compile(r'^X\d+_Y\d+$')


class FORCEUtils(object):
    """
    Helpers to handle FORCE data cube data
    """

    @staticmethod
    def tileDirs(root: Union[str, Path]) -> Iterator[Path]:
        root = Path(root)
        if rxFORCE_TILE.match(root.name):
            yield root
        else:
            for d in os.scandir(root):
                if d.is_dir() and rxFORCE_TILE.match(d.name):
                    yield Path(d.path)

    @staticmethod
    def productFiles(tileDir: Union[str, Path], product: str) -> List[Path]:
        assert isinstance(product, str) and len(product) > 0

        productFiles = []
        for f in os.scandir(tileDir):
            if f.is_file():
                bn, ext = os.path.splitext(f.name)
                if bn.endswith('_' + product) and ext in ['.tif', '.bsq']:
                    productFiles.append(Path(f.path))

        return sorted(productFiles)
