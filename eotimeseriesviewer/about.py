import os
import re
import webbrowser

from eotimeseriesviewer import DIR_UI, PATH_CONTRIBUTORS
from eotimeseriesviewer.qgispluginsupport.qps.utils import loadUi
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import QDialog


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

        self.labelLogoEOTSV.setPixmap(QPixmap(str(DIR_UI / 'icons' / 'icon.svg')))
        self.labelLogoHUB.setPixmap(QPixmap(str(DIR_UI / 'icons' / 'logo_hub.svg')))

        self.tbAbout.anchorClicked.connect(anchorClicked)
        self.tbChanges.anchorClicked.connect(anchorClicked)
        self.tbContributors.anchorClicked.connect(anchorClicked)
        self.tbLicense.anchorClicked.connect(anchorClicked)

        # page About
        from eotimeseriesviewer import (PATH_LICENSE, __version__, __version_sha__,
                                        PATH_CHANGELOG, PATH_ABOUT)
        txt = f'Version {__version__} ({__version_sha__[0:8]})'
        tt = f'EO Time Series Viewer\nVersion: {__version__}\nCommit: {__version_sha__}'
        self.labelVersion.setText(txt)
        self.labelVersion.setToolTip(tt)

        def readMD(path):
            if os.path.isfile(path):
                f = open(path, encoding='utf-8')
                txt = f.read()
                # increase headline level to make them looking smaller
                txt = re.sub(r'^(#+)', r'\1#', txt, flags=re.M)
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
