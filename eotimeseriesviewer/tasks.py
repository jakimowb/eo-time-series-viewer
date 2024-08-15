from qgis.core import QgsTask


class EOTSVTask(QgsTask):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
