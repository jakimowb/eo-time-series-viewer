from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotDataItem, DateTimePlotWidget, \
    DerivedPlotDataItemController
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects

start_app()


class UserFunctionTests(TestCase):

    def test_DateTimeDerivationDataItem(self):
        path_ufunc_example = DIR_REPO / 'eotimeseriesviewer/temporalprofile/userfunctions/user_function_example.py'
        assert path_ufunc_example.is_file()
        with open(path_ufunc_example, 'r') as f:
            code = f.read()
        code_obj = compile(code, path_ufunc_example.name, 'exec')
        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = [ImageDateUtils.timestamp(d) for d in dates]
        pdi = DateTimePlotDataItem(x=x, y=ndvi_values, pen=mkPen('white'))

        w = DateTimePlotWidget()
        controller = DerivedPlotDataItemController(w.plotItem)
        controller.setFunction(code)

        w.plotItem.addItem(pdi)

        self.showGui(w)
