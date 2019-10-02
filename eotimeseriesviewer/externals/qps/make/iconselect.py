import sys, os, re
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from qgis.gui import QgsCollapsibleGroupBox
from qps.testing import initQgisApplication

STANDARD_ICONS = [
            'SP_ArrowBack',
            'SP_ArrowDown',
            'SP_ArrowForward',
            'SP_ArrowLeft',
            'SP_ArrowRight',
            'SP_ArrowUp',
            'SP_BrowserReload',
            'SP_BrowserStop',
            'SP_CommandLink',
            'SP_ComputerIcon',
            'SP_CustomBase',
            'SP_DesktopIcon',
            'SP_DialogApplyButton',
            'SP_DialogCancelButton',
            'SP_DialogCloseButton',
            'SP_DialogDiscardButton',
            'SP_DialogHelpButton',
            'SP_DialogNoButton',
            'SP_DialogOkButton',
            'SP_DialogOpenButton',
            'SP_DialogResetButton',
            'SP_DialogSaveButton',
            'SP_DialogYesButton',
            'SP_DirClosedIcon',
            'SP_DirHomeIcon',
            'SP_DirIcon',
            'SP_DirLinkIcon',
            'SP_DirOpenIcon',
            'SP_DockWidgetCloseButton',
            'SP_DriveCDIcon',
            'SP_DriveDVDIcon',
            'SP_DriveFDIcon',
            'SP_DriveHDIcon',
            'SP_DriveNetIcon',
            'SP_FileDialogBack',
            'SP_FileDialogContentsView',
            'SP_FileDialogDetailedView',
            'SP_FileDialogEnd',
            'SP_FileDialogInfoView',
            'SP_FileDialogListView',
            'SP_FileDialogNewFolder',
            'SP_FileDialogStart',
            'SP_FileDialogToParent',
            'SP_FileIcon',
            'SP_FileLinkIcon',
            'SP_MediaPause',
            'SP_MediaPlay',
            'SP_MediaSeekBackward',
            'SP_MediaSeekForward',
            'SP_MediaSkipBackward',
            'SP_MediaSkipForward',
            'SP_MediaStop',
            'SP_MediaVolume',
            'SP_MediaVolumeMuted',
            'SP_MessageBoxCritical',
            'SP_MessageBoxInformation',
            'SP_MessageBoxQuestion',
            'SP_MessageBoxWarning',
            'SP_TitleBarCloseButton',
            'SP_TitleBarContextHelpButton',
            'SP_TitleBarMaxButton',
            'SP_TitleBarMenuButton',
            'SP_TitleBarMinButton',
            'SP_TitleBarNormalButton',
            'SP_TitleBarShadeButton',
            'SP_TitleBarUnshadeButton',
            'SP_ToolBarHorizontalExtensionButton',
            'SP_ToolBarVerticalExtensionButton',
            'SP_TrashIcon',
            'SP_VistaShield'
        ]

class AvailableIcons(QWidget):
    def __init__(self, parent=None):
        super(AvailableIcons, self).__init__()
        self.setWindowTitle('Icons')

        self.colSize = 20
        self.buttonSize = QSize(25,25)

        self.setLayout(QVBoxLayout())

        self.scrollArea = QScrollArea(self)
        self.scrollAreaWidget = QWidget(self.scrollArea)
        self.scrollAreaWidget.setLayout(QVBoxLayout())
        self.scrollArea.setWidget(self.scrollAreaWidget)
        self.layout().addWidget(self.scrollArea)

        self.addButtonBox('Standard Buttons', self.standardIconButtons())

        resourceDirs = self.findResourceDirs(QResource(':'))
        for resourceDir in resourceDirs:
            self.addButtonBox(resourceDir, self.resourceDirButtons(QResource(resourceDir)))


        #finally
        totalWidth = 0
        totalHeight = 0
        for i, w in enumerate([w for w in self.scrollAreaWidget.children() if isinstance(w, QWidget)]):
            size = w.sizeHint()
            totalHeight = totalHeight + size.height()
            if i == 0:
                totalWidth = size.width()
            else:
                totalWidth = max(totalWidth, size.width())

        layout = self.scrollAreaWidget.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.addStretch(0)
        totalSize = QSize(totalWidth, int(totalHeight))
        self.scrollAreaWidget.setMinimumSize(totalSize)
        self.scrollAreaWidget.resize(totalSize)

        self.tbUri = QLineEdit()
        self.iconLabel = QLabel()
        self.iconLabel.setMinimumSize(126, 126)
        self.layout().addWidget(self.tbUri)
        # l.addWidget(self.iconLabel)


        count = 0

    def addButtonBox(self, name: str, buttons: list):
        if len(buttons) == 0:
            return
        grp = QgsCollapsibleGroupBox(name, self.scrollAreaWidget)
        gridLayout = QGridLayout()
        grp.setLayout(gridLayout)
        for count, btn in enumerate(buttons):
            btn.setParent(grp)
            gridLayout.addWidget(btn, count / self.colSize, count % self.colSize)

        #size = grp.sizeHint()

        #if size.height() < (self.buttonSize.height() * gridLayout.rowCount()*10):
        #   size.setHeight(self.buttonSize.height() * gridLayout.rowCount() *10)
        #grp.setMinimumSize(size)
        #grp.resize(size)

        self.scrollAreaWidget.layout().addWidget(grp)

    def findResourceDirs(self, resource:QResource)->list:
        dirs = []
        for path in resource.children():
            r = QResource(resource.fileName() + '/' + path)
            assert isinstance(r, QResource)
            if r.isDir():
                dirs.append(r.fileName())
                dirs.extend(self.findResourceDirs(r))
        return dirs


    def standardIconButtons(self)->list:
        buttons = []
        for name in STANDARD_ICONS:
            btn = QPushButton(None)
            btn.setIcon(self.style().standardIcon(getattr(QStyle, name)))
            btn.clicked.connect(lambda _, x=name: self.onClicked('self.style().standardIcon(getattr(QStyle, "{}"))'.format(name)))
            btn.setToolTip(name)
            btn.resize(self.buttonSize)
            buttons.append(btn)
        return buttons


    def resourceDirButtons(self, resource:QResource):
        assert isinstance(resource, QResource)
        assert resource.isDir()

        buttons = []

        files = []
        for child in resource.children():
            r = QResource(resource.fileName() + '/' + child)
            if r.isFile():
                files.append(r.fileName())

        for file in sorted(files, key=lambda f:os.path.basename(f)):
                if re.search(r'(svg|png|jpg|ico)$', file, re.I):
                    icon = QIcon(file)
                    if not icon.isNull():
                        btn = QPushButton(self)
                        btn.clicked.connect(lambda b, x=file:self.onClicked(x))
                        btn.setToolTip(file)
                        btn.setIcon(icon)
                        buttons.append(btn)
        return buttons


    def onClicked(self, uri:str):
        print(uri)
        QApplication.clipboard().setText(uri)
        self.tbUri.setText(uri)
        icon = QIcon(uri)
        self.iconLabel.setPixmap(icon.pixmap(self.iconLabel.size()))



def run():

    #app = QApplication(sys.argv)
    app = initQgisApplication()

    dialog = AvailableIcons()
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.show()

    app.exec_()
if __name__ == '__main__':
    run()