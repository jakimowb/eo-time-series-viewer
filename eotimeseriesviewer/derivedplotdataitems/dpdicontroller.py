import os
import re
import types
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import numpy as np

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotDataItem
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi
from qgis.PyQt.QtCore import pyqtSignal, QObject, Qt
from qgis.PyQt.QtGui import QAction
from qgis.PyQt.QtWidgets import QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QTabWidget, \
    QVBoxLayout, QWidget, QDialogButtonBox
from qgis.PyQt.QtWidgets import QToolButton
from qgis.gui import QgsCodeEditorPython, QgsMessageBar


def dpdiInputData(pdi: PlotDataItem) -> dict[str, Any]:
    x, y = pdi.xData, pdi.yData
    dates = [ImageDateUtils.datetime(d) for d in x]
    kwds = {
        'x': x,
        'y': y,
        'dates': dates,
        'name': pdi.name(),
        '_item_': pdi
    }
    return kwds


class DPDIController(QObject):
    """
    Creates, updates and removes PlotDataItems which are derived from a parent PlotDataItem
    """
    visibilityChanged = pyqtSignal(bool)

    def __init__(self,
                 messageBar: QgsMessageBar = None,
                 name: str = 'Profile Function',
                 show: bool = True):
        super().__init__()

        self.mShow: bool = show
        self.mName = name
        self.mError: Optional[str] = None
        self.mFunc: Optional[types.CodeType] = None
        self.mCode: Optional[str] = ''
        self.mFile: Optional[Path] = None

        self.mDerivedCurves: Dict[PlotDataItem, List[PlotDataItem]] = dict()
        self.mMessageBar: Optional[QgsMessageBar] = messageBar

    def setMessageBar(self, messageBar: QgsMessageBar):
        self.mMessageBar = messageBar

    def isVisible(self) -> bool:
        return self.mShow

    def name(self) -> str:
        return self.mName

    def setName(self, name: str):
        self.mName = name

    def setVisible(self, visible: bool):

        if self.mShow != visible:
            self.mShow = visible
            self.visibilityChanged.emit(self.mShow)

    def createDerivedPlotDataItems(self, pdi: PlotDataItem) -> List[PlotDataItem]:
        assert isinstance(pdi, PlotDataItem)
        """
        Creates one (or more) PlotDataItems relating to the input PlotDataItem ``pdi``,
        using the function set by `setFunction(func)`
        :param pdi: PlotDataItem
        :return: list of derived plot data items
        """
        if pdi in self.mDerivedCurves:
            # already exits
            return self.derivedPlotDataItems(pdi)

        kwds = dpdiInputData(pdi)

        try:
            exec(self.mFunc, kwds)
            results = kwds['results']

        except Exception as ex:
            results = None

        derived_items = []
        if results:

            if isinstance(results, dict):
                results = [results]

            if isinstance(results, list):
                for data in results:
                    if isinstance(data, dict):
                        item = PlotDataItem(**data)
                        derived_items.append(item)
                    elif isinstance(data, PlotDataItem):
                        derived_items.append(data)

            self.mDerivedCurves[pdi] = derived_items

        return derived_items

    def derivedPlotDataItems(self, pdi: Union[str, PlotDataItem]) -> List[PlotDataItem]:
        """
        Returns all DerivedPlotDataItems that relate to the PlotDataItem
        :param pdi: PlotDataItem to get derived items for or string 'all'
        :return: list of derived plot data items
        """
        if isinstance(pdi, str):
            results = []
            if pdi == 'all':
                for v in self.mDerivedCurves.values():
                    results.extend(v)
            return results
        else:
            return self.mDerivedCurves.get(pdi, [])

    def populateContextMenu(self, menu: QMenu):

        a: QAction = menu.addAction(f'Show {self.mName}')
        a.setChecked(self.mShow)

    def evaluateFunction(self, func) -> Tuple[bool, Optional[str]]:
        """
        Tests if a given function returns valid output for test data
        :param func: types.CodeType
        :return: bool [, str]
        """

        if not isinstance(func, types.CodeType):
            return False, f'Wrong type:{func} is not a precompiled code type'

        # set test arguments
        _globals = {'x': np.asarray([1, 2, 3]),
                    'y': np.asarray([1, 2, 3]),
                    }

        try:
            exec(func, _globals)
            results = _globals['results']
        except Exception as ex:
            return False, str(ex)
        return True, None

    def prepareFunction(self, code: str) -> Tuple[Optional[types.CodeType], Optional[str]]:
        assert isinstance(code, str)

        error = None
        compiled_code = None
        try:
            compiled_code = compile(code, f'<user_code: "{code}">', 'exec')
        except Exception as ex:
            error = str(ex)

        return compiled_code, error

    def code(self) -> str:
        return self.mCode

    def error(self) -> Optional[str]:
        return self.mError

    def setFunction(self,
                    func: Union[types.FunctionType, str],
                    description: str = None) -> bool:
        """
        Set the user-defined function to generate derived plot data items
        :param func:
        :return:
        """
        if isinstance(func, str):
            # compile the code
            self.mCode = func
            func, error = self.prepareFunction(func)
            if error:
                self.mError = error
                return False

        if func != self.mFunc:
            self.clear()

        success, error = self.evaluateFunction(func)
        if not success:
            if self.mMessageBar:
                self.mMessageBar.pushCritical('Failed test', error)
            self.mError = error
            return False

        self.mError = None
        self.mFunc = func
        return True

    def clear(self):
        """Removes all derived plot data items"""
        self.mDerivedCurves.clear()


class DPDIControllerModel(QObject):
    """
    A model to manage a collection of item controllers
    and return derived plot data items
    """
    controllerAdded = pyqtSignal(object)
    controllerRemoved = pyqtSignal(object)
    modelUpdated = pyqtSignal()
    itemsRemoved = pyqtSignal(list)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mController: List[DPDIController] = []
        self.mShowSelectedOnly: bool = True

        self.mExampleFolder: Optional[Path] = None
        self.mExamplePDI: Optional[PlotDataItem] = None

    def setPlotDataItemExample(self, pdi: PlotDataItem):
        self.mExamplePDI = pdi

    def createDerivedItems(self, items: List[PlotDataItem]) -> List[PlotDataItem]:
        """
        Gets a list of items and create a list of derived items according to the controller settings.
        :return:
        """

        controllers_to_show = []

        # print(f'N1 {len(self.items)}')
        for controller in self.controllers():
            controller.clear()
            if controller.isVisible():
                controllers_to_show.append(controller)

        new_items = []
        for item in items:
            for controller in controllers_to_show:
                new_items.extend(controller.createDerivedPlotDataItems(item))

        return new_items

    def showControllerSettingsDialog(self):

        d = DPDIControllerSettingsDialog(self)
        d.validationRequest.connect(self.validateControllerSettings)
        d.controllerChanged.connect(lambda *args: d.updateModel(self))
        if isinstance(self.mExampleFolder, Path):
            d.setExampleFolder(self.mExampleFolder)

        if d.exec_() == QDialog.Accepted:
            d.updateModel(self)

    def setExampleFolder(self, path: Union[str, Path]):
        """
        Sets a folder with *.py files that contain example user-defined functions
        """
        path = Path(path)
        if path.is_dir():
            self.mExampleFolder = path
            return True
        else:
            self.mExampleFolder = None
            return False

    def validateControllerSettings(self, data: dict):
        """
        Validates the content provided by the DPDIControllerSettingsDialog
        and returns result to be shown in the dialog
        :param data: dict with keys 'code'
        :return: dict: data dict with values for 'success' (bool) and 'error' (None or str)
        """
        code = data.get('code')
        if isinstance(self.mExamplePDI, PlotDataItem):
            pdi = self.mExamplePDI

            code = data.get('code')
            try:
                func = compile(code, f'<user_code: "{code}">', 'exec')
                kwds = dpdiInputData(pdi)
                exec(func, kwds)
                data['success'] = True
                data['error'] = None
            except Exception as ex:
                data['success'] = False
                data['error'] = str(ex)

    def populateContextMenu(self, menu: QMenu):

        m = menu.addMenu('User functions')
        m.setToolTipsVisible(True)
        a = m.addAction('Selected Only')
        a.setToolTip('Show for selected profiles only')
        a.setCheckable(True)
        a.setChecked(self.showSelectedOnly())
        a.toggled.connect(self.setShowSelectedOnly)

        a = m.addAction('Settings')
        a.triggered.connect(self.showControllerSettingsDialog)

        if len(self.mController) > 0:
            m.addSeparator()
            for c in self.mController:
                c: DPDIController
                a: QAction = m.addAction(f'{c.mName}')
                a.setCheckable(True)
                a.setChecked(c.mShow)
                a.toggled.connect(lambda b: c.setVisible(b))

    def clearControllerItems(self):
        """
        Removes all derived items.
        :return: list of remove items
        """
        items = []
        for c in self.mController[:]:
            items.extend(self.removeControllerItems(c))
        return items

    def clearController(self):
        """Remove all controllers from this model"""
        for c in self.mController[:]:
            self.removeController(c)

    def setShowSelectedOnly(self, showSelectedOnly: bool):
        if self.mShowSelectedOnly != showSelectedOnly:
            self.mShowSelectedOnly = showSelectedOnly
            self.modelUpdated.emit()

    def showSelectedOnly(self) -> bool:
        return self.mShowSelectedOnly

    def controllers(self) -> List[DPDIController]:
        return self.mController[:]

    def addController(self, c: DPDIController):

        if c not in self.mController:
            self.mController.append(c)
            c.visibilityChanged.connect(self.onVisibilityChanged)
            self.controllerAdded.emit(c)

    def onVisibilityChanged(self, *args):
        c = self.sender()
        if isinstance(c, DPDIController):
            b = c.isVisible()
            for pdi in c.derivedPlotDataItems('all'):
                pdi.setVisible(b)

    def removeControllerItems(self, c: DPDIController) -> List[PlotDataItem]:
        """
        Removes all PLotDataItems owned by a controller.
        :param c: DPDIController
        :return: list of removed PlotDataItems
        """
        derived_items = c.derivedPlotDataItems('all')
        c.clear()
        return derived_items

    def removeController(self, c: DPDIController):
        if c in self.mController:
            i = self.mController.index(c)
            self.mController.remove(c)
            derived_items = self.removeControllerItems(c)
            self.controllerRemoved.emit(c)
            self.itemsRemoved.emit(derived_items)


DEFAULT_CODE = \
    """
import numpy as np

global x, y
assert isinstance(x, np.ndarray)
assert isinstance(y, np.ndarray)
# x = time stamps (float) used for plotting
# y = profile values, e.g., calculated NDVI values
# dates = the time as numpy np.ndarray

# return the results to be plotted
results = {
    'x': x,
    'y': y,
    'pen': 'red',
}
    """


class DPDIControllerSettingsWidget(QWidget):
    nameChanged = pyqtSignal(str)
    validationRequest = pyqtSignal(dict)

    def __init__(self, *args, name: str = 'User Function', **kwds):
        super().__init__(*args, **kwds)
        self.mFilePath: str = ''
        self.tbTitle = QLineEdit()
        self.tbTitle.setText(name)
        self.tbTitle.textChanged.connect(self.nameChanged)
        self.codeEditor = QgsCodeEditorPython()
        self.cbShow = QCheckBox('Show')
        self.cbShow.setChecked(True)
        self.cbShow.setToolTip('Show/hide in plot')
        self.messageBar: QgsMessageBar = QgsMessageBar(parent=self)

        l = QHBoxLayout()
        l.addWidget(self.cbShow)
        l.addWidget(QLabel('Name'))
        l.addWidget(self.tbTitle)

        v = QVBoxLayout()
        v.addLayout(l)
        v.addWidget(self.messageBar)
        v.addWidget(self.codeEditor)
        self.setLayout(v)

    def initFromController(self, c: DPDIController):
        """
        Initializes the widget from a DPDIController object
        :param c: DPDIController
        """
        self.setName(c.name())
        self.setCode(c.code())
        self.cbShow.setChecked(c.isVisible())

    def controller(self) -> DPDIController:
        """
        Returns a DPDIController object based on the settings of this widget
        :return: DPDIController
        """
        c = DPDIController()
        c.setName(self.name())
        c.setFunction(self.code())
        c.setVisible(self.showItems())
        return c

    def setFile(self, path):
        self.mFilePath = path

    def file(self) -> str:
        return self.mFilePath

    def name(self) -> str:
        return self.tbTitle.text()

    def setName(self, name: str):
        self.tbTitle.setText(name)

    def code(self) -> str:
        return self.codeEditor.text()

    def setCode(self, code: str):
        self.codeEditor.setText(code)

    def showItems(self) -> bool:
        return self.cbShow.isChecked()

    def validate(self) -> bool:
        """
        Code validation. Tries to compile the code and run it with example data
        :return:
        """
        if self.codeEditor.checkSyntax():

            data = {'code': self.code()}
            error = None
            success = False
            try:
                self.validationRequest.emit(data)
                error = data.get('error', None)
                success = data.get('success', True)
            except Exception as ex:
                success = False
                error = str(ex)

            self.messageBar.clearWidgets()
            if not success:
                title = 'Error'
                self.messageBar.pushWarning(title, error)
                return False
            else:
                return True
        return False


class DPDIControllerSettingsDialog(QDialog):
    """
    Provides a GUI to a controller model. Allows users to
    add, modify, and remove derived plot data item controllers
    """
    LAST_DIR: Optional[str] = None

    controllerChanged = pyqtSignal()
    validationRequest = pyqtSignal(dict)

    def __init__(self, model: DPDIControllerModel, udf_folder: Union[str, Path, None] = None, parent=None):
        super().__init__(parent)

        assert isinstance(model, DPDIControllerModel)

        UI_DIR = Path(__file__).parent

        loadUi(UI_DIR / 'dpdicontrollersettingsdialog.ui', self)
        self.setWindowTitle('Derived Plot Data Item Settings')
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        path_help = UI_DIR / 'controllerhelp.md'
        if path_help.is_file():
            with open(path_help, 'r', encoding='utf8') as f:
                self.textBrowser.setMarkdown(f.read())

        self.mModel: DPDIControllerModel = model

        self.btnAddUDF.setDefaultAction(self.actionAddUDF)
        self.btnRemoveUDF.setDefaultAction(self.actionRemoveUDF)
        self.btnLoadUDF.setDefaultAction(self.actionLoadUDF)
        self.btnSaveUDF.setDefaultAction(self.actionSaveUDF)

        self.actionAddUDF.triggered.connect(self.onAddUDF)
        self.actionRemoveUDF.triggered.connect(self.removeUDF)
        self.actionLoadUDF.triggered.connect(lambda *args: self.loadUDF())
        self.actionSaveUDF.triggered.connect(self.saveUDF)

        self.mTabWidget: QTabWidget
        assert isinstance(self.mTabWidget, QTabWidget)
        self.mUDFFolder: Optional[Path] = None
        self.mCodeWidgets: List[DPDIControllerSettingsWidget] = []

        if udf_folder:
            self.setExampleFolder(udf_folder)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.controllerChanged)

        self.connectControllerModel(model)

    def validate(self):

        # enables / disables widgets
        b = isinstance(self.currentUDFWidget(), DPDIControllerSettingsWidget)
        self.actionRemoveUDF.setEnabled(b)

    def showSelectedOnly(self) -> bool:
        return self.cbShowSelectedOnly.isChecked()

    def onAddUDF(self):

        # create a new empty UDF
        name = 'User Function'
        existing_names = list(self.udfNames())
        i = 0
        while name in existing_names:
            i += 1
            name = f'User Function {i}'

        self.addUDF(name)

    def udfNames(self) -> Generator[str, Any, None]:

        for i in range(self.mTabWidget.count()):
            w = self.mTabWidget.widget(i)
            if isinstance(w, DPDIControllerSettingsWidget):
                yield w.name()

    def onUDFFileSelected(self, index: int):

        path = Path(self.cbUDFFolder.itemData(index))
        if os.path.isfile(path) and path.name.endswith('.py'):
            self.loadUDF(path)

    def setExampleFolder(self, path: Union[str, Path]):
        """
        Defines a folder stores exemplary user-defined functions
        :param path:
        """

        self.mUDFFolder = Path(path)
        self.onUDFFolderChanged()

    def udfFolder(self) -> Optional[Path]:
        return self.mUDFFolder

    def onUDFFolderChanged(self):
        """
        Populates the menu to open example files
        """
        folder = self.mUDFFolder

        udf_files: List[Path] = []
        if isinstance(folder, Path) and folder.is_dir():
            for e in os.scandir(folder):
                if e.is_file() and e.name.endswith('.py'):
                    udf_files.append(Path(e.path))

        if len(udf_files) > 0:
            menu = QMenu(self.btnLoadUDF)
            menu.setToolTipsVisible(True)

            for udf_file in udf_files:
                # create a load action
                a: QAction = menu.addAction(udf_file.name)
                a.setToolTip(f'Load {udf_file}')
                a.triggered.connect(lambda *args, f=udf_file: self.loadUDF(f))
            self.btnLoadUDF.setPopupMode(QToolButton.MenuButtonPopup)
            self.btnLoadUDF.setMenu(menu)
        else:
            self.btnLoadUDF.setPopupMode(QToolButton.DelayedPopup)

    def currentUDFWidget(self) -> Optional[DPDIControllerSettingsWidget]:
        w = self.mTabWidget.currentWidget()
        if isinstance(w, DPDIControllerSettingsWidget):
            return w
        else:
            return None

    def currentUDF(self) -> Optional[str]:
        w = self.currentUDFWidget()
        if isinstance(w, DPDIControllerSettingsWidget):
            return w.code()
        else:
            return None

    def saveUDF(self, *args):
        w = self.currentUDFWidget()
        if isinstance(w, DPDIControllerSettingsWidget):
            last_path = w.file()
            if not last_path or last_path == '' and self.udfFolder():
                last_dir = self.udfFolder().as_posix()
            else:
                last_dir = os.path.dirname(last_path)
            path, filter = QFileDialog.getSaveFileName(parent=self,
                                                       caption='Save file',
                                                       directory=last_dir,
                                                       filter='Python files (*.py);;All files (*.*)')
            if path not in [None, '']:
                code = w.code()
                with open(path, 'w', encoding='utf8') as f:
                    f.write(code)
                self.LAST_DIR = os.path.dirname(path)

    def updateModel(self, model: Optional[DPDIControllerModel] = None):
        if model is None:
            model = self.mModel
        assert isinstance(model, DPDIControllerModel)
        model.clearController()
        model.setShowSelectedOnly(self.showSelectedOnly())

        for w in self.controllerSettingsWidgets():
            if w.validate():
                c = w.controller()
                model.addController(c)
        model.modelUpdated.emit()

    def loadUDF(self, path: Union[None, Path, str] = None, *args):
        """
        Loads a user-defined function from a *.py file
        :param path: path of *.py file. If None, a file dialog is shown
        :param args:
        :return:
        """
        if path is None:
            path, filter = QFileDialog.getOpenFileName(parent=self,
                                                       caption='Open file',
                                                       directory=self.LAST_DIR,
                                                       filter='Python files (*.py);;All files (*.*)')

        if path != '' and os.path.isfile(path):
            with open(path, 'r') as f:
                code = f.read()

            match = re.search(r'#\sNAME:(.+)$', code, re.MULTILINE)
            if match:
                name = match.group(1).strip()
            else:
                name = Path(path).stem
            w = DPDIControllerSettingsWidget()
            w.setName(name)
            w.setCode(code)
            self.addControllerSettingsWidget(w)
            self.LAST_DIR = os.path.dirname(path)

    def connectControllerModel(self, model: DPDIControllerModel):
        self.cbShowSelectedOnly.setChecked(model.showSelectedOnly())
        for c in model.controllers():
            w = DPDIControllerSettingsWidget()
            w.initFromController(c)
            self.addControllerSettingsWidget(w)

    def addControllerSettingsWidget(self, w: DPDIControllerSettingsWidget):
        assert isinstance(w, DPDIControllerSettingsWidget)
        w.nameChanged.connect(self.onNameChanged)
        idx = self.mTabWidget.addTab(w, w.name())
        self.mCodeWidgets.append(w)
        self.mTabWidget.setCurrentIndex(idx)
        w.validationRequest.connect(self.validationRequest)
        self.validate()

    def controller(self) -> List[DPDIController]:

        results = []
        for w in self.controllerSettingsWidgets():
            c = DPDIController(name=w.name(), show=w.showItems())
            results.append(c)
        return results

    def controllerSettingsWidgets(self) -> List[DPDIControllerSettingsWidget]:
        return self.mCodeWidgets[:]

    def addUDF(self, *args) -> DPDIControllerSettingsWidget:

        w = DPDIControllerSettingsWidget()

        n = w.name()
        names = self.udfNames()
        i = 0
        while n in names:
            i += 1
            n = f'{w.name()} ({i})'
        w.setName(n)
        w.setCode(f'# NAME: {n}\n' + DEFAULT_CODE)
        self.addControllerSettingsWidget(w)
        return w

    def onNameChanged(self, text: str):
        w = self.sender()
        if isinstance(w, QWidget):
            tb: QTabWidget = self.mTabWidget
            for i in range(tb.count()):
                tw = tb.widget(i)

                if w == tw:
                    tb.setTabText(i, text)
                    break

    def removeUDF(self, *args):
        """
        Removes the currently selected UDF widget
        :param args:
        """
        w = self.currentUDFWidget()
        if isinstance(w, DPDIControllerSettingsWidget):
            self.removeControllerSettingsWidget(w)

    def removeControllerSettingsWidget(self, w: DPDIControllerSettingsWidget):
        """
        Removes a DPDIControllerSettingsWidget from the dialog
        :param w:
        :return:
        """
        assert isinstance(w, DPDIControllerSettingsWidget)
        if w in self.mCodeWidgets:
            self.mTabWidget.removeTab(self.mTabWidget.indexOf(w))
            self.mCodeWidgets.remove(w)
        self.validate()
