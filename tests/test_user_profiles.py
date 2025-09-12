import unittest

import numpy as np

from eotimeseriesviewer import DIR_REPO
from eotimeseriesviewer import initAll
from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.derivedplotdataitems.dpdicontroller import DPDIController, DPDIControllerSettingsDialog, \
    DPDIControllerModel
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import mkPen, PlotDataItem
from eotimeseriesviewer.temporalprofile.datetimeplot import DateTimePlotDataItem, DateTimePlotWidget
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects
from qgis.PyQt.QtWidgets import QDialog

start_app()
initAll()


class UserFunctionTests(TestCase):

    def test_DateTimeDerivationDataItem(self):
        path_ufunc_example = DIR_REPO / 'eotimeseriesviewer/temporalprofile/userfunctions/user_function_example.py'
        assert path_ufunc_example.is_file()
        with open(path_ufunc_example, 'r') as f:
            code = f.read()
        code_obj = compile(code, path_ufunc_example.name, 'exec')
        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = np.asarray([ImageDateUtils.timestamp(d) for d in dates])

        pdi1 = DateTimePlotDataItem(x=x, y=ndvi_values, pen=mkPen('white'), name='Profile A')
        pdi2 = DateTimePlotDataItem(x=x + 0.5, y=ndvi_values * 0.5, pen=mkPen('white'), name='Profile B')
        pdi2.setSelected(True)
        w = DateTimePlotWidget()

        controller = DPDIController(w.plotItem)
        controller.setFunction(code_obj)

        w.plotItem.addItem(pdi1)
        w.plotItem.mPlotDataControllerModel.addController(controller)
        w.plotItem.addItem(pdi2)
        w.plotItem.updateDerivedItems()

        self.showGui(w)

    @unittest.skipIf(TestCase.runsInCI(), 'GUI testing only')
    def test_in_eotsv(self):
        eotsv = EOTimeSeriesViewer()
        eotsv.loadExampleTimeSeries(loadAsync=False)
        eotsv.activateIdentifyTemporalProfileMapTool()
        eotsv.loadCurrentTemporalProfile(eotsv.spatialCenter())
        self.showGui(eotsv.ui)

    def test_controller_model(self):

        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = np.asarray([ImageDateUtils.timestamp(d) for d in dates])

        pdi1 = DateTimePlotDataItem(x=x, y=ndvi_values, pen=mkPen('white'), name='Profile A')
        w = DateTimePlotWidget()

        pi = w.plotItem
        model = pi.mPlotDataControllerModel
        assert isinstance(model, DPDIControllerModel)

        c = DPDIController()
        c.setName('My controller')
        code = """
import numpy as np

coefficients = np.polyfit(x, y, deg=1)
y2 = np.polyval(coefficients, x)
results = {'y':y2, 'x':x, 'pen': 'red', 'name':'linear'}"""

        assert c.setFunction(code), c.error()

        model.addController(c)

        pi.addItem(pdi1)
        items = list(pi.dateTimePlotDataItems())
        derivedItems = model.createDerivedItems(items)

        assert len(derivedItems) > 0
        for i in derivedItems:
            assert isinstance(i, PlotDataItem)

        if not TestCase.runsInCI():
            model.showControllerSettingsDialog()

        self.showGui(w)

    def test_derived_function_dialog(self):

        dates, ndvi_values = TestObjects.generate_seasonal_ndvi_dates()
        x = np.asarray([ImageDateUtils.timestamp(d) for d in dates])

        pdi1 = DateTimePlotDataItem(x=x, y=ndvi_values, pen=mkPen('white'), name='Profile A')
        w = DateTimePlotWidget()

        dpdiModel = w.plotItem.mPlotDataControllerModel
        w.plotItem.addItem(pdi1)
        w.plotItem.updateDerivedItems()

        d = DPDIControllerSettingsDialog(dpdiModel)

        self.assertIsInstance(d.showSelectedOnly(), bool)
        d.updateModel()

        def onValidationRequest(data):

            code = data.get('code')
            try:
                func = compile(code, f'<user_code: "{code}">', 'exec')
                kwds = {'x': np.asarray([1, 2, 3]),
                        'y': np.asarray([1, 1, 1])}
                exec(func, kwds)
                data['success'] = True
                data['error'] = None
            except Exception as ex:
                data['success'] = False
                data['error'] = str(ex)

        def onControllerChanged():
            print('# update model')
            d.updateModel(dpdiModel)

        d.validationRequest.connect(onValidationRequest)
        d.controllerChanged.connect(onControllerChanged)

        udf_folder = DIR_REPO / 'eotimeseriesviewer/temporalprofile/userfunctions'
        d.setUDFFolder(udf_folder)

        w.show()

        if TestCase.runsInCI():
            d.show()
        else:
            if d.exec_() == QDialog.Accepted:
                d.updateModel(dpdiModel)

        self.showGui(w)
