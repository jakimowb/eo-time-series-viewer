from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QTextBrowser, QToolButton, QWidget
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.core import QgsFeature, QgsVectorLayer
from qgis.gui import QgsCodeEditorPython, QgsFeaturePickerWidget
from eotimeseriesviewer import DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi

path_ui = DIR_UI / 'pythoncodeeditordialog.ui'


class PythonExpressionDialog(QDialog):
    codeChanged = pyqtSignal(str)

    previewRequest = pyqtSignal(QgsFeature, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        loadUi(path_ui, self)
        self.setWindowTitle("Edit Python Expression")

        editor: QgsCodeEditorPython = self.mCodeEditor
        editor.textChanged.connect(lambda: self.codeChanged.emit(editor.text()))
        editor.textChanged.connect(self.requestPreview)

        featurePicker: QgsFeaturePickerWidget = self.mFeaturePickerWidget
        featurePicker.featureChanged.connect(self.requestPreview)

        self.mPreviewFunc: callable = None
        self.buttonBox().accepted.connect(self.accept)
        self.buttonBox().rejected.connect(self.reject)

    def featurePickerWidget(self) -> QgsFeaturePickerWidget:
        return self.mFeaturePickerWidget

    def requestPreview(self):
        feature: QgsFeature = self.featurePickerWidget().feature()

        self.previewRequest.emit(feature, self.code())

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

    def setCode(self, code: str):
        self.codeEditor().setText(code)

    def code(self) -> str:
        return self.codeEditor().text()

    def codeEditor(self) -> QgsCodeEditorPython:
        return self.mCodeEditor

    def buttonBox(self) -> QDialogButtonBox:
        return self.mButtonBox


class FieldPythonExpressionWidget(QWidget):
    expressionChanged = pyqtSignal(str)
    previewRequest = pyqtSignal()

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

    def openExpressionDialog(self):
        """Opens a dialog with QgsCodeEditorPython to edit the expression."""
        dialog = PythonExpressionDialog(self)
        dialog.previewRequest.connect(self.previewRequest)
        dialog.setWindowTitle("Edit Python Expression")
        dialog.setCode(self.expression())
        # Connect dialog buttons
        buttonBox = dialog.buttonBox()
        buttonBox.accepted.connect(lambda d=dialog: self.applyExpression(d))
        buttonBox.rejected.connect(dialog.reject)

        dialog.exec_()

    def applyExpression(self, dialog: PythonExpressionDialog):
        """Applies the expression from the code editor to the line edit."""
        self.lineEdit.setText(dialog.code())
        dialog.accept()

    def onExpressionChanged(self, text):
        """Emit signal when the expression changes."""
        self.expressionChanged.emit(text)

    def expression(self):
        """Returns the current expression in the QLineEdit."""
        return self.lineEdit.text()

    def setExpression(self, expression):
        """Sets the expression in the QLineEdit."""
        self.lineEdit.setText(expression)
