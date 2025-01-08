from qgis.core import QgsTask


class EOTSVTask(QgsTask):
    def __init__(self, *args, callback=None, **kwds):
        super().__init__(*args, **kwds)

        self.mCallback = callback

    def finished(self, result):
        if self.mCallback is not None:
            self.mCallback(result, self)
