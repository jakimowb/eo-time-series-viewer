from __future__ import absolute_import
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from osgeo import gdal

from timeseriesviewer.ui.docks import TsvDockWidgetBase, loadUi
from timeseriesviewer.classificationscheme import ClassificationSchemeWidget, ClassificationScheme, ClassInfo, getTextColorWithContrast

class LabelShortcutButton(QPushButton):

    def __init__(self, classInfo, parent=None):
        assert isinstance(classInfo, ClassInfo)
        super(LabelShortcutButton, self).__init__(parent)
        self.setMinimumWidth(20)
        self.setMaximumWidth(50)
        self.classInfo = classInfo
        self.classInfo.sigSettingsChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.setToolTip('{} {}'.format(self.classInfo.mLabel, self.classInfo.mName))
        self.setText(str(self.classInfo.mLabel))
        bc = self.classInfo.mColor
        style = 'LabelShortcutButton {'+ \
                'background-color: {}'.format(bc.name())+ \
                '; color: {}'.format(getTextColorWithContrast(bc).name()) + \
                '}'

        self.setStyleSheet(style)

class LabelingDockUI(TsvDockWidgetBase, loadUi('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDockUI, self).__init__(parent)
        self.setupUi(self)

        self.cbOutputTextfile.setChecked(False)
        self.cbOutputVectorLayer.setChecked(False)


        assert isinstance(self.classSchemeWidget, ClassificationSchemeWidget)
        self.classScheme = self.classSchemeWidget.classificationScheme()
        assert isinstance(self.classScheme, ClassificationScheme)
        self.LUTClassButtons = dict()
        self.classScheme.sigClassAdded.connect(self.addClassButton)
        self.classScheme.sigClassRemoved.connect(self.removeClassButton)
        self.refreshClassShortcutButtons()


    def resizeEvent(self, event):
        assert isinstance(event, QResizeEvent)

        self.refreshClassShortcutButtons()

    def addClassButton(self, classInfo):
        assert isinstance(classInfo, ClassInfo)
        btn = LabelShortcutButton(classInfo, self)
        btn.clicked.connect(lambda:self.labelCurrentFeatureSelection(classInfo))
        self.LUTClassButtons[classInfo] = btn
        self.refreshClassShortcutButtons()

    def refreshClassShortcutButtons(self, btnWidth = 25):
        l = self.btnBarClassShortcuts
        for i in reversed(range(l.layout().count())):
            item = l.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            else:
                s = ""

        classes = sorted(self.LUTClassButtons.keys(), key=lambda ci:ci.mLabel)

        width = 0
        col = 0
        row = 0
        for i, classInfo in enumerate(classes):
            btn = self.LUTClassButtons[classInfo]
            btn.refresh() #take care on internal updates
            btn.setMaximumWidth(btnWidth)
            self.btnBarClassShortcuts.addWidget(btn, row, col)
            width += btnWidth
            if width > self.width():
                row += 1
                col = width = 0
            else:
                col += 1

    def labelCurrentFeatureSelection(self, classInfo):
        print("SET LABEL {}".format(classInfo))
        pass

    def removeClassButton(self, classInfo):
        assert isinstance(classInfo, ClassInfo)

    def loadClassificationSchemeFromRaster(self, path):

        ds = gdal.Open(path)



if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import sandbox
    qgsApp = sandbox.initQgisEnvironment()

    pathClassImg = r'D:\Repositories\QGIS_Plugins\enmap-box\enmapbox\testdata\HymapBerlinA\HymapBerlinA_test.img'
    pathShp = r''

    classScheme = ClassificationScheme.fromRasterImage(pathClassImg)

    d = LabelingDockUI()
    for c in classScheme:
        d.classScheme.addClass(c)
    d.show()
    qgsApp.exec_()
    qgsApp.exitQgis()
