from typing import Tuple

from qgis.PyQt.QtCore import pyqtSignal, QDateTime

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph import pyqtgraph as pg


class MapDateRangeItem(pg.LinearRegionItem):
    sigMapDateRequest = pyqtSignal(QDateTime, str)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mLastRegion = self.getRegion()
        self.sigRegionChangeFinished.connect(self.onRegionChangeFinished)

    def setRegion(self, rgn):
        self.mLastRegion = rgn
        super().setRegion(rgn)

    def onRegionChangeFinished(self, *args):

        new0, new1 = self.getRegion()
        old0, old1 = self.mLastRegion

        if old0 != new0 and old1 != new1:
            # both dates have changed / window was moved -> use average data
            tCenter = 0.5 * (new0 + new1)
            d = ImageDateUtils.datetime(tCenter)
            # print(f'# {d} center')
            self.sigMapDateRequest.emit(d, 'center')
        elif old0 == new0 and old1 != new1:
            # right bar changed
            d = ImageDateUtils.datetime(new1)
            # print(f'# {d} end')
            self.sigMapDateRequest.emit(d, 'end')
        elif old0 != new0 and old1 == new1:
            # left bar changed
            d = ImageDateUtils.datetime(new0)
            # print(f'# {d} start')
            self.sigMapDateRequest.emit(d, 'start')

    def setMapDateRange(self, date0: QDateTime, date1: QDateTime):
        d0 = min(date0, date1)
        d1 = max(date0, date1)

        # print(f'set {d0} {d1}')

        if (d0, d1) != self.mapDateRange():
            t0 = ImageDateUtils.timestamp(d0)
            t1 = ImageDateUtils.timestamp(d1)

            self.setRegion((t0, t1))

    def mapDateRange(self) -> Tuple[QDateTime, QDateTime]:

        t0, t1 = self.getRegion()
        d0 = ImageDateUtils.datetime(float(t0))
        d1 = ImageDateUtils.datetime(float(t1))

        return d0, d1
