# NAME: user function 2
import numpy as np

from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen, PlotDataItem

global x, y
assert isinstance(x, np.ndarray)
assert isinstance(y, np.ndarray)
# x = time stamps used for plotting, float
# y = profile values, e.g., calculated NDVI values
# dates = the time as numpy np.ndarray

# this example returns two segments
i = int(len(x) / 2)
results = [
    PlotDataItem(x=x[:i], y=y[:i] + 2, pen=mkPen('green')),
    PlotDataItem(x=x[i:], y=y[i:] - 1, pen=mkPen('red'))
]

# `results` can be:
#   a) a dictionary with values to create a PyQtGraph PlotDataItem,
#      required:
#       'x' - the new time stamps, or
#       'y' - the time stamps to be plotted on the y axis, or
#       'dates' - an array of datetime values. Will be converted into time stamps
#      optional:
#       # Line-Style properties:
#       'pen' - pen color
#       '
#       # Symbol-Style properties:
#       'symbol' - the plot symbol
#       'symbolPen' - outline pen for drawing points
#       'symbolSize' -
#      see https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html
#      for the full list of options
#
#   b) a PyQtGraph PlotDataItem or derived class, e.g.,
#      ``from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotDataItem``
#
#   c) A list of (a) or (b). This allows returning multiple plot data items,
#      e.g., to plot temporal segments
