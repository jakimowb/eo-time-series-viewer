import unittest

from eotimeseriesviewer.temporalprofile.pythoncodeeditor import FieldPythonExpressionWidget, PythonExpressionDialog
from eotimeseriesviewer.tests import EOTSVTestCase, start_app, TestObjects

start_app()


class PythonCodeEditorTestCases(EOTSVTestCase):

    def test_dialog(self):
        lyr = TestObjects.createProfileLayer()

        w = PythonExpressionDialog()

        w.codeEditor().setText('# b(1)')

        # w.setCode('b(1)')
        # w.setHelpText('<h1>This is a help text</h1>')
        txt = '<b><span style="color:red">code changed:</span></b>'
        tt = 'More info on code status'

        def onCodeChanged(d: dict):
            d['preview_text'] = txt + d['expression']
            d['preview_tooltip'] = tt

        w.validationRequest.connect(onCodeChanged)
        w.setLayer(lyr)

        # epw.setExpressionText('b(1)')
        self.showGui(w)

    def test_FieldPythonExpressionWidget(self):
        w = FieldPythonExpressionWidget()
        w.expressionChanged.connect(lambda expr: print(f"Expression changed: {expr}"))

        self.showGui(w)

    def test_validation(self):

        is_ok = ['foo', 'broken"python', '1+3']
        errMsg = 'MyError'

        def onValidateRequest(data: dict):

            expr = data.get('expression')
            self.assertIsInstance(expr, str)
            self.assertTrue(data['is_valid'] is None)
            self.assertTrue(data['error'] is None)

            data['is_valid'] = expr in is_ok
            if expr not in is_ok:
                data['error'] = errMsg

        w = FieldPythonExpressionWidget()
        w.validationRequest.connect(onValidateRequest)
        w.setExpression('1+3')
        b, err = w.isValidExpression()
        self.assertTrue(b and err is None)

        w.setExpression('foo"')
        b, err = w.isValidExpression()
        s = ""
        self.assertTrue(b is False and isinstance(err, str))

        w.setExpression('foo')

        for expr in ['foo', '1+2', 'broken"python']:
            w.setExpression(expr)
            b, err = w.isValidExpression()
            if expr in is_ok:
                self.assertTrue(b and err is None)
            else:
                self.assertTrue(b is False and err == errMsg)


if __name__ == '__main__':
    unittest.main()
