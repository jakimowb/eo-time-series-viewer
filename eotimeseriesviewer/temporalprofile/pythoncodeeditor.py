from typing import Optional, Tuple

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QTextBrowser, QToolButton, QWidget
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.core import QgsVectorLayer
from qgis.gui import QgsCodeEditorPython, QgsFeaturePickerWidget
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi

path_ui = DIR_UI / 'pythoncodeeditordialog.ui'


def create_pythoncode_validation_request(expression: str) -> dict:
    d = {'expression': expression,
         'error': None}

    return d


class PythonExpressionDialog(QDialog):
    validationRequest = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        loadUi(path_ui, self)
        self.setWindowTitle("Edit Python Expression")

        editor: QgsCodeEditorPython = self.mCodeEditor
        editor.textChanged.connect(self.updatePreview)

        featurePicker: QgsFeaturePickerWidget = self.mFeaturePickerWidget
        featurePicker.featureChanged.connect(self.updatePreview)

        self.buttonBox().accepted.connect(self.accept)
        self.buttonBox().rejected.connect(self.reject)

    def featurePickerWidget(self) -> QgsFeaturePickerWidget:
        return self.mFeaturePickerWidget

    def updatePreview(self):
        d = create_pythoncode_validation_request(self.expression())
        d['feature'] = self.featurePickerWidget().feature()
        d['preview_text'] = None
        d['preview_tooltip'] = None
        self.validationRequest.emit(d)

        text = d.get('preview_text', '')
        tt = d.get('preview_tooltip', '')

        if isinstance(text, str):
            self.tbPreview.setText(text)

        if isinstance(tt, str):
            self.tbPreview.setToolTip(tt)

    def setLayer(self, layer: QgsVectorLayer):
        self.mFeaturePickerWidget.setLayer(layer)

    def setPreviewText(self, text: str):
        self.tbPreview.setText(text)

    def previewText(self) -> str:
        return self.tbPreview.toPlainText()

    def helpTextBrowser(self) -> QTextBrowser:
        return self.mHelpTextBrowser

    def setHelpText(self, text: str):
        self.helpTextBrowser().setText(text)

    def setExpression(self, code: str):
        self.codeEditor().setText(code)

    def expression(self) -> str:
        return self.codeEditor().text()

    def codeEditor(self) -> QgsCodeEditorPython:
        return self.mCodeEditor

    def buttonBox(self) -> QDialogButtonBox:
        return self.mButtonBox


class FieldPythonExpressionWidget(QWidget):
    expressionChanged = pyqtSignal(str)
    validationRequest = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create main components
        self.lineEdit = QLineEdit(self)
        self.editButton = QToolButton(self)
        self.editButton.setIcon(QIcon(":/images/themes/default/mIconPythonFile.svg"))

        # Layout for the main widget
        layout = QHBoxLayout(self)
        layout.addWidget(self.lineEdit)
        layout.addWidget(self.editButton)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        # Connect button click to open the dialog
        self.editButton.clicked.connect(self.openExpressionDialog)

        # Signal to track changes in the QLineEdit
        self.lineEdit.textChanged.connect(self.onExpressionChanged)
        self.lineEdit.textEdited.connect(lambda: self.doValidationRequest())

        self.mLayer: Optional[QgsVectorLayer] = None

        self.mIsValid: bool = None

    def openExpressionDialog(self):
        """Opens a dialog with QgsCodeEditorPython to edit the expression."""
        dialog = PythonExpressionDialog(self)
        dialog.validationRequest.connect(self.doValidationRequest)
        dialog.setWindowTitle("Edit Python Expression")
        dialog.setExpression(self.expression())
        # Connect dialog buttons
        buttonBox = dialog.buttonBox()
        buttonBox.accepted.connect(lambda d=dialog: self.applyExpression(d))
        buttonBox.rejected.connect(dialog.reject)

        if self.mLayer:
            dialog.setLayer(self.mLayer)

        dialog.exec_()

    def doValidationRequest(self, data: dict = None):
        if data is None:
            data = create_pythoncode_validation_request(self.expression())
        self.validationRequest.emit(data)

        error = data.get('error', None)
        if isinstance(error, str):
            self.lineEdit.setStyleSheet('color:red;')
        else:
            self.lineEdit.setStyleSheet('')

    def applyExpression(self, dialog: PythonExpressionDialog):
        """Applies the expression from the code editor to the line edit."""

        self.lineEdit.setText(dialog.expression())
        dialog.accept()

    def onExpressionChanged(self, text):
        """Emit signal when the expression changes."""
        self.expressionChanged.emit(text)
        self.doValidationRequest()

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer) and layer.isValid()
        self.mLayer = layer

    def layer(self) -> Optional[QgsVectorLayer]:
        return self.mLayer

    def expression(self):
        """Returns the current expression in the QLineEdit."""
        return self.lineEdit.text()

    def setExpression(self, expression):
        """Sets the expression in the QLineEdit."""
        self.lineEdit.setText(expression)

        self.doValidationRequest()

    def isValidExpression(self) -> Tuple[bool, Optional[str]]:

        d = create_pythoncode_validation_request(self.expression())
        self.validationRequest.emit(d)

        error = d.get('error', None)

        return not isinstance(error, str), error
