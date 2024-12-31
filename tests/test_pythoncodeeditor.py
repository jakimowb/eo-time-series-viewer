import unittest

from qgis._core import QgsFeature

from eotimeseriesviewer.temporalprofile.pythoncodeeditor import FieldPythonExpressionWidget, PythonExpressionDialog
from eotimeseriesviewer.tests import start_app, TestCase, TestObjects

start_app()


class PythonCodeEditorTestCases(TestCase):

    def test_dialog(self):
        lyr = TestObjects.createProfileLayer()

        w = PythonExpressionDialog()

        w.codeEditor().setText('# b(1)')

        # w.setCode('b(1)')

        # w.setHelpText('<h1>This is a help text</h1>')

        def onCodeChanged(feature: QgsFeature, code: str):
            print(f'Code changed: {code}')
            txt = f'<h1>Code changed: {code}</h1>'
            w.setPreviewText(txt)

        w.previewRequest.connect(onCodeChanged)
        w.setLayer(lyr)

        # epw.setExpressionText('b(1)')
        self.showGui(w)

    def test_button(self):
        w = FieldPythonExpressionWidget()
        w.expressionChanged.connect(lambda expr: print(f"Expression changed: {expr}"))

        self.showGui(w)


if __name__ == '__main__':
    unittest.main()
