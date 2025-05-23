import unittest

from eotimeseriesviewer.tests import EOTSVTestCase, start_app

EE_Available = False
try:
    ee = __import__('ee')
    EE_Available = True
except ModuleNotFoundError:
    EE_Available = False

start_app()


# @unittest.skipIf(not EE_Available, 'GEE not available')
@unittest.skipIf(True, 'GEE not available')
class TestLabeling(EOTSVTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ee.Initialize()
        import provider
        provider.register_data_provider()

    def test_access(self):
        s = ""
        l8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA')
        s = ""
        s = ""


if __name__ == "__main__":
    unittest.main(buffer=False)
