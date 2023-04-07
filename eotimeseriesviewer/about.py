import os
import webbrowser

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtWidgets import QDialog

from eotimeseriesviewer import DIR_UI, PATH_CONTRIBUTORS
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi


def anchorClicked(url: QUrl):
    """Opens a URL in local browser / mail client"""
    assert isinstance(url, QUrl)
    webbrowser.open(url.url())


class AboutDialogUI(QDialog):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialogUI, self).__init__(parent)
        loadUi(DIR_UI / 'aboutdialog.ui', self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.init()

    def init(self):
        self.mTitle = self.windowTitle()
        self.listWidget.currentItemChanged.connect(lambda: self.setAboutTitle())
        self.setAboutTitle()

        self.tbAbout.anchorClicked.connect(anchorClicked)
        self.tbChanges.anchorClicked.connect(anchorClicked)
        self.tbContributors.anchorClicked.connect(anchorClicked)
        self.tbLicense.anchorClicked.connect(anchorClicked)

        # page About
        from eotimeseriesviewer import PATH_LICENSE, __version__, PATH_CHANGELOG, PATH_ABOUT
        self.labelVersion.setText('{}'.format(__version__))

        def readMD(path):
            if os.path.isfile(path):
                f = open(path, encoding='utf-8')
                txt = f.read()
                f.close()
            else:
                txt = 'unable to read {}'.format(path)
            return txt

        # page Changed
        self.tbAbout.setMarkdown(readMD(PATH_ABOUT))
        self.tbChanges.setMarkdown(readMD(PATH_CHANGELOG))
        self.tbContributors.setMarkdown(readMD(PATH_CONTRIBUTORS))
        self.tbLicense.setMarkdown(readMD(PATH_LICENSE))

    def setAboutTitle(self, suffix=None):
        item = self.listWidget.currentItem()

        if item:
            title = '{} | {}'.format(self.mTitle, item.text())
        else:
            title = self.mTitle
        if suffix:
            title += ' ' + suffix
        self.setWindowTitle(title)
