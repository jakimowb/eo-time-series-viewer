
import os, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *

from timeseriesviewer import *
from timeseriesviewer.utils import *

class SettingsDialog(QDialog, loadUI('settingsdialog.ui')):
    """
    A widget to change settings
    """

    def __init__(self, title='<#>', parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setupUi(self)

        from timeseriesviewer.timeseries import DateTimePrecision

        assert isinstance(self.cbDateTimePrecission, QComboBox)
        for e in DateTimePrecision:
            assert isinstance(e, enum.Enum)
            self.cbDateTimePrecission.addItem(e.name, e)

        self.cbDateTimePrecission.currentIndexChanged.connect(self.validate)
        self.sbMapSizeX.valueChanged.connect(self.validate)
        self.sbMapSizeY.valueChanged.connect(self.validate)
        self.sbMapRefreshIntervall.valueChanged.connect(self.validate)

    def readValues(self)->dict:

        pass

    def setValues(self, values:dict):
        assert isinstance(values, dict)


    def defaultValues(self)->dict:

        pass


    def validate(*args):

            pass

    def loadFromSettings(self):

        pass

    def settings(self)->QSettings:

        pass

    def saveSettings(self):

        pass


