"""
***************************************************************************
    layerconfigwidget/rasterbands.py
        - A basic python reconstruction of the QGIS App qgslabelingwidget.cpp
    -----------------------------------------------------------------------
    begin                : 2020-02-25
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import typing, pathlib, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import QIcon
from ..utils import loadUi
from .core import QpsMapLayerConfigWidget, configWidgetUi

class LabelingConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Labels" page and basically reimplements the qgslabelingwidget.cpp from the
    QGIS APP
    """
    class Mode(enum.IntEnum):
        NoLabels = enum.auto()
        Single = enum.auto()
        RuleBased = enum.auto()
        Blocking = enum.auto()

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        loadUi(configWidgetUi('labelsconfigwidget.ui'), self)

        self.pageNoLabels: QWidget
        self.pageSingleLabels: QWidget
        self.pageRulebasedLabels: QWidget
        self.pageBlockingLabels: QWidget

        self.mOldSettings : QgsAbstractVectorLayerLabeling = None
        self.mSimpleSettings : QgsPalLayerSettings = QgsPalLayerSettings()
        self.mOldLabelsEnabled: bool = False
        assert isinstance(self.stackedWidget, QStackedWidget)
        self.comboBox.addItem(QgsApplication.getThemeIcon('labelingNone.svg'), 'No Labels', LabelingConfigWidget.Mode.NoLabels)
        self.comboBox.addItem(QgsApplication.getThemeIcon('labelingSingle.svg'), 'Single Labels', LabelingConfigWidget.Mode.Single)
        self.comboBox.addItem(QgsApplication.getThemeIcon('labelingRuleBased.svg'), 'Rule-based Labeling', LabelingConfigWidget.Mode.RuleBased)
        self.comboBox.addItem(QgsApplication.getThemeIcon('labelingObstacle.svg'), 'Blocking', LabelingConfigWidget.Mode.Blocking)

        textFormat = QgsTextFormat()
        self.mFieldExpressionWidget.setLayer(layer)
        self.panelSingleLabels = QgsTextFormatPanelWidget(textFormat, canvas, None, layer)
        self.pageSingleLabels.layout().insertWidget(1, self.panelSingleLabels)
        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        self.setLayer(self.mapLayer())

    def setLayer(self, layer):
        if not (isinstance(layer, QgsVectorLayer) and layer.isValid()):
            self.setEnabled(False)
            return
        else:
            self.setEnabled(True)
            if layer.labeling():
                self.mOldSettings = layer.labeling().clone()
            else:
                self.mOldSettings = None
            self.mOldLabelsEnabled = layer.labelsEnabled()
            self.adaptToLayer()

    def adaptToLayer(self):
        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return
        else:
            if lyr.labelsEnabled():
                self.setLabeling(lyr.labeling())
            else:
                self.setLabeling(None)

    def labelingGui(self) -> QWidget:
        return self.stackedWidget.currentWidget()



    def labeling(self) -> QgsAbstractVectorLayerLabeling:
        page = self.labelingGui()
        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return
        assert isinstance(lyr, QgsVectorLayer)
        labeling = None
        page = self.labelingGui()
        if page == self.pageSingleLabels:
            labeling = self.labeling_single()
        elif page == self.pageRulebasedLabels:
            labeling = self.labeling_rulebased()
        elif page == self.pageBlockingLabels:
            labeling = self.labeling_blocking()

        return labeling

    def setLabeling(self, labeling: QgsAbstractVectorLayerLabeling):
        if labeling is None:
            mode = LabelingConfigWidget.Mode.NoLabels
        else:
            assert isinstance(labeling, QgsAbstractVectorLayerLabeling)
            labelType = labeling.type()
            if labelType == 'rule-based':

                mode = LabelingConfigWidget.Mode.RuleBased
                self.set_labeling_rulebased(labeling)

            elif labelType == 'simple':
                settings = labeling.settings()
                if isinstance(settings, QgsPalLayerSettings):
                    if settings.drawLabels:
                        mode = LabelingConfigWidget.Mode.Single
                        self.set_labeling_single(labeling)
                    else:
                        mode = LabelingConfigWidget.Mode.Blocking
                        self.set_labeling_blocking(labeling)

        self.comboBox.setCurrentIndex(self.comboBox.findData(mode))

    def labeling_single(self) -> QgsVectorLayerSimpleLabeling:
        p = self.panelSingleLabels
        assert isinstance(p, QgsTextFormatPanelWidget)
        settings = QgsPalLayerSettings()
        settings.drawLabels = True
        settings.fieldName, settings.isExpression, isValid = self.mFieldExpressionWidget.currentField()
        settings.dist = 0
        settings.placementFlags = 0
        settings.setFormat(self.panelSingleLabels.format())
        settings.layerType = self.mapLayer().type()

        return QgsVectorLayerSimpleLabeling(settings)

    def set_labeling_single(self, labeling: QgsVectorLayerSimpleLabeling):
        assert isinstance(labeling, QgsVectorLayerSimpleLabeling)
        assert labeling.type() == 'simple'

        page = self.pageSingleLabels

        self.panelSingleLabels.setParent(None)
        page.layout().removeWidget(self.panelSingleLabels)
        self.panelSingleLabels.deleteLater()

        settings = labeling.settings()

        if settings.isExpression:
            self.mFieldExpressionWidget.setExpression(settings.getLabelExpression().expression())
        else:
            self.mFieldExpressionWidget.setField(settings.fieldName)

        self.panelSingleLabels = QgsTextFormatPanelWidget(settings.format(), self.canvas(), None, self.mapLayer())
        self.pageSingleLabels.layout().insertWidget(1, self.panelSingleLabels)


        s = ""


    def labeling_rulebased(self) -> QgsRuleBasedLabeling:
        return None

    def set_labeling_rulebased(self, labeling:QgsRuleBasedLabeling):
        pass

    def labeling_blocking(self) -> QgsVectorLayerSimpleLabeling:
        return None

    def set_labeling_blocking(self, labeling:QgsVectorLayerSimpleLabeling):
        pass

    def writeSettingsToLayer(self):
        lyr = self.mapLayer()
        if not isinstance(lyr, QgsVectorLayer):
            return

        labeling = self.labeling()
        if isinstance(labeling, QgsAbstractVectorLayerLabeling):
            lyr.setLabelsEnabled(True)
            lyr.setLabeling(labeling)
        else:
            lyr.setLabelsEnabled(False)
            lyr.setLabeling(None)

    def apply(self):
        self.writeSettingsToLayer()
        self.mapLayer().triggerRepaint()

    def reset(self):
        pass


class LabelingConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Labels', icon=QIcon(':/images/themes/default/mActionLabeling.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return LabelingConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsVectorLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True