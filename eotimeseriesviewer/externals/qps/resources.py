
import sys, os, pathlib, typing, re
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *
from qgis.PyQt.QtSvg import QGraphicsSvgItem

from .utils import file_search, findUpwardPath
REGEX_FILEXTENSION_IMAGE = re.compile(r'\.([^.]+)$')


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values



def compileResourceFiles(dirRoot:str, targetDir:str=None, suffix:str= '_rc.py'):
    """
    Searches for *.ui files and compiles the *.qrc files they use.
    :param dirRoot: str, root directory, in which to search for *.qrc files or a list of *.ui file paths.
    :param targetDir: str, output directory to write the compiled *.py files to.
           Defaults to the *.qrc's directory
    """
    # find ui files
    if not isinstance(dirRoot, pathlib.Path):
        dirRoot = pathlib.Path(dirRoot)
    assert dirRoot.is_dir(), '"dirRoot" is not a directory: {}'.format(dirRoot)
    dirRoot = dirRoot.resolve()

    ui_files = list(file_search(dirRoot, '*.ui', recursive=True))

    qrc_files = []
    qrc_files_skipped = []
    doc = QDomDocument()

    for ui_file in ui_files:
        qrc_dir = pathlib.Path(ui_file).parent
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                location = attr['location']
                qrc_path = (qrc_dir / pathlib.Path(location)).resolve()
                if not qrc_path.exists():
                    info = ['Broken *.qrc location in {}'.format(ui_file),
                            ' `location="{}"`'.format(location)]
                    print('\n'.join(info), file=sys.stderr)
                    continue

                elif not qrc_path.as_posix().startswith(dirRoot.as_posix()):
                    # skip resource files out of the root directory
                    if not qrc_path in qrc_files_skipped:
                        qrc_files_skipped.append(qrc_path)

                    continue
                elif qrc_path not in qrc_files:
                    qrc_files.append(qrc_path)

    for file in file_search(dirRoot, '*.qrc', recursive=True):
        file = pathlib.Path(file)
        if file not in qrc_files:
            qrc_files.append(file)

    if len(qrc_files) == 0:
        print('Did not find any *.qrc files in {}'.format(dirRoot), file=sys.stderr)
        return

    print('Compile {} *.qrc files:'.format(len(qrc_files)))
    targetDirOutputNames = []
    for qrcFile in qrc_files:
        assert isinstance(qrcFile, pathlib.Path)
        # in case of similar base names, use different output names
        # e.g. make
        #  src/images.qrc
        #  src/sub/images.qrc
        # to
        #  targetDir/images_rc.py
        #  targetDir/images2_rc.py
        bn = os.path.splitext(qrcFile.name)[0]
        s = suffix
        i = 1
        outName = '{}{}'.format(bn, s)
        while outName in targetDirOutputNames:
            i += 1
            s = '{}{}'.format(i, suffix)
            outName = '{}{}'.format(bn, s)

        compileResourceFile(qrcFile, targetDir=targetDir, suffix=s)
        targetDirOutputNames.append(outName)

    if len(qrc_files_skipped) > 0:
        print('Skipped *.qrc files (out of root directory):')
        for qrcFile in qrc_files_skipped:
            print(qrcFile.as_posix())

def compileResourceFile(pathQrc, targetDir=None, suffix:str='_rc.py', compressLevel=7, compressThreshold=100):
    """
    Compiles a *.qrc file
    :param pathQrc:
    :return:
    """
    if not isinstance(pathQrc, pathlib.Path):
        pathQrc = pathlib.Path(pathQrc)

    assert isinstance(pathQrc, pathlib.Path)
    assert pathQrc.name.endswith('.qrc')
    print('Compile {}...'.format(pathQrc))
    if targetDir is None:
        targetDir = pathQrc.parent
    elif not isinstance(targetDir, pathlib.Path):
        targetDir = pathlib.Path(targetDir)

    assert isinstance(targetDir, pathlib.Path)
    targetDir = targetDir.resolve()


    cwd = pathlib.Path(pathQrc).parent

    pathPy = targetDir / (os.path.splitext(pathQrc.name)[0] + suffix)

    last_cwd = os.getcwd()
    os.chdir(cwd)

    cmd = 'pyrcc5 -compress {} -o {} {}'.format(compressLevel, pathPy, pathQrc)
    cmd2 = 'pyrcc5 -no-compress -o {} {}'.format(pathPy.as_posix(), pathQrc.name)
    #print(cmd)

    import PyQt5.pyrcc_main

    if True:
        last_level = PyQt5.pyrcc_main.compressLevel
        last_threshold = PyQt5.pyrcc_main.compressThreshold

        # increase compression level and move to *.qrc's directory
        PyQt5.pyrcc_main.compressLevel = compressLevel
        PyQt5.pyrcc_main.compressThreshold = compressThreshold

        assert PyQt5.pyrcc_main.processResourceFile([pathQrc.name], pathPy.as_posix(), False)

        # restore previous settings
        PyQt5.pyrcc_main.compressLevel = last_level
        PyQt5.pyrcc_main.compressThreshold = last_threshold
    else:
        print(cmd2)
        os.system(cmd2)

    os.chdir(last_cwd)


def compileQGISResourceFiles(qgis_repo:str, target:str=None):
    """
    Searches for *.qrc files in the QGIS repository and compile them to <target>

    :param qgis_repo: str, path to local QGIS repository.
    :param target: str, path to directory that contains the compiled QGIS resources. By default it will be
            `<REPOSITORY_ROOT>/qgisresources`.
    """

    if qgis_repo is None:
        for k in ['QGIS_REPO', 'QGIS_REPOSITORY']:
            if k in os.environ.keys():
                qgis_repo = pathlib.Path(os.environ[k])
                break

    if qgis_repo is None:
        print('QGIS_REPO location undefined', file=sys.stderr)
        return

    if not isinstance(qgis_repo, pathlib.Path):
        qgis_repo = pathlib.Path(qgis_repo)
    assert isinstance(qgis_repo, pathlib.Path)
    assert qgis_repo.is_dir()
    assert (qgis_repo / 'images' /'images.qrc').is_file(), '{} is not the QGIS repository root'.format(qgis_repo.as_posix())

    if target is None:
        DIR_REPO = findUpwardPath(__file__, '.git')
        target = DIR_REPO / 'qgisresources'

    if not isinstance(target, pathlib.Path):
        target = pathlib.Path(target)

    os.makedirs(target, exist_ok=True)
    compileResourceFiles(qgis_repo / 'src', targetDir=target)
    compileResourceFiles(qgis_repo / 'images', targetDir=target)


def initQtResources(roots: list = []):
    """
    Searches recursively for `*_rc.py` files and loads them into the QApplications resources system
    :param roots: list of root folders to search within
    :type roots:
    :return:
    :rtype:
    """
    if not isinstance(roots, list):
        roots = [roots]

    if len(roots) == 0:
        p = pathlib.Path(__file__).parent
        roots.append(p.parent)

    rc_files = []
    for rootDir in roots:
        for r, dirs, files in os.walk(rootDir):
            root = pathlib.Path(r)
            for f in files:
                if f.endswith('_rc.py'):
                    path = root / f
                    if path not in rc_files:
                        rc_files.append(path)

    for path in rc_files:
        print('load {}'.format(path))
        initResourceFile(path)


def initResourceFile(path):
    """
    Loads a '*_rc.py' file into the QApplication's resource system
    """
    if not isinstance(path, pathlib.Path):
        path = pathlib.Path(path)
    f = path.name
    name = f[:-3]
    add_path = path.parent.as_posix() not in sys.path
    if add_path:
        sys.path.append(path.parent.as_posix())
    try:
        __import__(name)
        # spec = importlib.util.spec_from_file_location(name, path)
        #rcModule = importlib.util.module_from_spec(spec)
        #spec.loader.exec_module(rcModule)
        #rcModule.qInitResources()

    except Exception as ex:
        print(ex, file=sys.stderr)

    if add_path:
        sys.path.remove(path.parent.as_posix())

def findQGISResourceFiles():
    """
    Tries to find a folder 'qgisresources'.
    See snippets/create_qgisresourcefilearchive.py to create the 'qgisresources' folder.
    """
    results = []
    root = None
    if 'QPS_QGIS_RESOURCES' in os.environ.keys():
        root = os.environ.keys()
    else:
        d = pathlib.Path(__file__)

        while d != pathlib.Path('.'):
            if (d / 'qgisresources').is_dir():
                root = (d / 'qgisresources')
                break
            else:
                d = d.parent
            if len(d.parts) == 1:
                break

    if isinstance(root, pathlib.Path):
        for root, dirs, files in os.walk(root):
            for rc_file_name in [f for f in files if f.endswith('_rc.py')]:
                path = pathlib.Path(root) / rc_file_name
                if path.is_file():
                    results.append(path)
    return results


def scanResources(path=':')->str:
    """Recursively returns file paths in directory"""
    D = QDirIterator(path)
    while D.hasNext():
        entry = D.next()
        if D.fileInfo().isDir():
            yield from scanResources(path=entry)
        elif D.fileInfo().isFile():
            yield D.filePath()

def printResources():
    print('Available resources:')
    res = sorted(list(scanResources()))
    for r in res:
        print(r)



class ResourceTableModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.cnUri = 'Path'
        self.cnIcon = 'Resource'
        self.RESOURCES = []
        self.reloadResources()

    def reloadResources(self):

        self.beginResetModel()
        self.RESOURCES.clear()
        self.RESOURCES.extend(list(scanResources()))
        self.endResetModel()

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 2

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.RESOURCES)

    def columnNames(self)->typing.List[str]:
        return [self.cnUri, self.cnIcon]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.columnNames()[section]

        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        uri = self.RESOURCES[index.row()]
        cn = self.columnNames()[index.column()]

        if role == Qt.DisplayRole:
            if cn == self.cnUri:
                return uri
            else:
                return os.path.basename(uri)
        if role == Qt.DecorationRole:
            if cn == self.cnIcon:
                return QIcon(uri)

        if role == Qt.ToolTipRole:
            if cn == self.cnUri:
                return uri

        if role == Qt.UserRole:
            return uri

        return None


class ResourceTableView(QTableView):

    def __init__(self, *args, **kwds):
        super().__init__(*args ,**kwds)


    def contextMenuEvent(self, event: QContextMenuEvent) -> None:

        idx = self.indexAt(event.pos())
        if isinstance(idx, QModelIndex) and idx.isValid():

            uri = idx.data(Qt.UserRole)
            m = QMenu()
            a = m.addAction('Copy Name')
            a.triggered.connect(lambda *args, n=os.path.basename(uri): QApplication.clipboard().setText(n))
            a = m.addAction('Copy Path')
            a.triggered.connect(lambda *args, n=uri: QApplication.clipboard().setText(n))
            a = m.addAction('Copy Icon')
            a.triggered.connect(lambda *args, n=uri: QApplication.clipboard().setPixmap(QPixmap(n)))

            m.exec_(event.globalPos())

        pass


class ResourceBrowser(QWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        from .utils import loadUi
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'qpsresourcebrowser.ui'
        loadUi(pathUi, self)
        self.setWindowTitle('QPS Resource Browser')
        self.actionReload: QAction
        self.optionUseRegex: QAction
        self.tbFilter: QLineEdit
        self.tableView: ResourceTableView
        self.btnUseRegex: QToolButton
        self.btnReload: QToolButton
        self.preview: QLabel

        self.graphicsView:QGraphicsView
        self.graphicsScene = QGraphicsScene()
        self.graphicsView.setScene(self.graphicsScene)

        self.textBrowser: QTextBrowser

        self.resourceModel: ResourceTableModel = ResourceTableModel()
        self.resourceProxyModel = QSortFilterProxyModel()
        self.resourceProxyModel.setFilterKeyColumn(0)
        self.resourceProxyModel.setFilterRole(Qt.UserRole)
        self.resourceProxyModel.setSourceModel(self.resourceModel)

        self.tableView.setSortingEnabled(True)
        self.tableView.setModel(self.resourceProxyModel)
        self.tableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

        self.btnReload.setDefaultAction(self.actionReload)
        self.btnUseRegex.setDefaultAction(self.optionUseRegex)
        self.actionReload.triggered.connect(self.resourceModel.reloadResources)

        self.optionUseRegex.toggled.connect(self.updateFilter)
        self.tbFilter.textChanged.connect(self.updateFilter)

    def updateFilter(self):

        txt = self.tbFilter.text()

        expr = QRegExp(txt)

        if self.optionUseRegex.isChecked():
            expr.setPatternSyntax(QRegExp.RegExp)
        else:
            expr.setPatternSyntax(QRegExp.Wildcard)
        if expr.isValid():
            self.resourceProxyModel.setFilterRegExp(expr)
            self.info.setText('')
        else:
            self.resourceProxyModel.setFilterRegExp(None)
            self.info.setText(expr.errorString())



    def onSelectionChanged(self, selected, deselected):

        selectedIdx = selected.indexes()
        if len(selectedIdx) == 0:
            self.updatePreview(None)
        else:
            idx1 = selectedIdx[0]
            assert isinstance(idx1, QModelIndex)

            uri = idx1.data(Qt.UserRole)
            self.updatePreview(uri)

    def updatePreview(self, uri:str):

        hasImage = False
        hasText = False
        self.textBrowser.clear()
        self.graphicsScene.clear()

        if isinstance(uri, str) and '.' in uri:
            ext = os.path.splitext(uri)[1]

            item = None
            if ext == '.svg':
                item = QGraphicsSvgItem(uri)
            else:
                pm = QPixmap(uri)
                if not pm.isNull():
                    item = QGraphicsPixmapItem(pm)

            if item:
                hasImage = True
                self.graphicsScene.addItem(item)
                self.graphicsView.fitInView(item, Qt.KeepAspectRatio)

            if re.search(r'\.(svg|html|xml|txt)$', uri, re.I) is not None:
                file = QFile(uri)
                if file.open(QFile.ReadOnly | QFile.Text):
                    stream = QTextStream(file)
                    stream.setAutoDetectUnicode(True)
                    txt = stream.readAll()
                    self.textBrowser.setPlainText(txt)
                    hasText = True
                    file.close()

        self.tabWidget.setTabEnabled(self.tabWidget.indexOf(self.pageImage), hasImage)
        self.tabWidget.setTabEnabled(self.tabWidget.indexOf(self.pageText), hasText)



    def useFilterRegex(self)->bool:
        return self.optionUseRegex.isChecked()



def showResources()->ResourceBrowser:
    """
    A simple way to list available Qt resources
    :return:
    :rtype:
    """
    needQApp = not isinstance(QApplication.instance(), QApplication)
    if needQApp:
        app = QApplication([])
    browser = ResourceBrowser()
    browser.show()
    if needQApp:
        QApplication.instance().exec_()
    return browser