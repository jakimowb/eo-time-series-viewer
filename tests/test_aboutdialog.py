import unittest

from qgis.PyQt.QtWidgets import QDialog
from eotimeseriesviewer.about import AboutDialogUI
from eotimeseriesviewer.tests import EOTSVTestCase, start_app

start_app()


class TestCasesAboutDialog(EOTSVTestCase):

    def test_AboutDialog(self):
        dialog = AboutDialogUI()

        self.assertIsInstance(dialog, QDialog)
        self.showGui(dialog)


if __name__ == '__main__':
    unittest.main()
