# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/vectorlayertools.py

    A QgsVectorLayerTools implementation to track, react or start
    modifications of QgsVectorLayers in QGIS applications.
    ---------------------
    Beginning            : 2020-03-25
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
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
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import *

from qgis.core import \
    QgsVectorLayerTools, QgsVectorLayer, Qgis, \
    QgsSettings, \
    QgsVectorDataProvider, \
    QgsFeature, QgsGeometry

from qgis.gui import QgisInterface

from .utils import SpatialExtent, SpatialPoint
class VectorLayerTools(QgsVectorLayerTools):
    """
    Implements QgsVectorLayerTools with some additional routines
    """
    sigMessage = pyqtSignal(str, str, Qgis.MessageLevel)
    sigEditingStarted = pyqtSignal(QgsVectorLayer)
    sigEditingStopped = pyqtSignal(QgsVectorLayer)
    sigFreezeCanvases = pyqtSignal(bool)
    sigZoomRequest = pyqtSignal(SpatialExtent)
    sigPanRequest = pyqtSignal(SpatialPoint)

    def __init__(self, *args, **kwds):
        super(VectorLayerTools, self).__init__(*args, **kwds)
        pass

    def addFeature(self, layer: QgsVectorLayer,
                   defaultValues: dict = dict(),
                   defaultGeometry: QgsGeometry = None,
                   f: QgsFeature = QgsFeature(),
                   action_name: str = "Add feature") -> bool:
        """
        This method should/will be called, whenever a new feature will be added to the layer.
        """
        from .maptools import QgsFeatureAction
        a = QgsFeatureAction(action_name, f, layer, None, None)
        return a.addFeature(defaultValues)

    def startEditing(self, layer:QgsVectorLayer ) -> bool:
        """
        This will be called, whenever a vector layer should be switched to edit mode.
        """
        if not isinstance(layer, QgsVectorLayer):
            return False

        if not layer.isEditable() and not layer.readOnly():

            if not (layer.dataProvider().capabilities() & QgsVectorDataProvider.EditingCapabilities ):
                title = "Start editing failed"
                msg = "Provider cannot be opened for editing"
                self.sigMessage.emit(title, msg, Qgis.Information)
                return False
            layer.startEditing()
            if layer.isEditable():
                self.sigEditingStarted.emit(layer)
        return layer.isEditable()

    def cutSelectionToClipboard(self, layer: QgsVectorLayer):
        import qgis.utils
        if isinstance(layer, QgsVectorLayer) and layer.isEditable() and isinstance(qgis.utils.iface, QgisInterface):
            self.copySelectionToClipboard(layer)
            self.deleteSelection(layer)

    def copySelectionToClipboard(self, layer: QgsVectorLayer, attributes:list=None, featureIds:list=None):
        """
        Copies selected features to the clipboard
        """
        import qgis.utils

        if isinstance(layer, QgsVectorLayer) and isinstance(qgis.utils.iface, QgisInterface):
            qgis.utils.iface.copySelectionToClipboard(layer)

    def pasteFromClipboard(self, layer: QgsVectorLayer):
        import qgis.utils
        if isinstance(layer, QgsVectorLayer) \
                and layer.isEditable() \
                and isinstance(qgis.utils.iface, QgisInterface):
                qgis.utils.iface.pasteFromClipboard(layer)

    def invertSelection(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer):
            layer.invertSelection()

    def removeSelection(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer):
            layer.removeSelection()

    def selectAll(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer):
            layer.selectAll()

    def deleteSelection(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            layer.deleteSelectedFeatures()

    def toggleEditing(self, vlayer: QgsVectorLayer, allowCancel: bool = True) -> bool:
        """
        Changes the editing state. Returns True if the change was successful.
        """
        if not isinstance(vlayer, QgsVectorLayer):
            return False

        res: bool = True
        isEditable = vlayer.isEditable()
        isModified = vlayer.isModified()

        if isEditable:
            return self.stopEditing(vlayer, allowCancel=allowCancel)
        else:
            if not self.startEditing(vlayer):
                return False
            settings = QgsSettings()
            markerType = str(settings.value("qgis/digitizing/marker_style", "Cross"))
            markSelectedOnly = bool(settings.value("qgis/digitizing/marker_only_for_selected", True))

            #// redraw only if markers will be drawn
            if not markSelectedOnly or (vlayer.selectedFeatureCount() > 0 and \
                 (markerType == "Cross" or markerType == "SemiTransparentCircle")):
              vlayer.triggerRepaint()

            return True


    def zoomToSelected(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer) and layer.selectedFeatureCount() > 0:
            bbox = layer.boundingBoxOfSelected()
            ext = SpatialExtent(layer.crs(), bbox)
            self.sigZoomRequest.emit(ext)


    def panToSelected(self, layer: QgsVectorLayer):
        if isinstance(layer, QgsVectorLayer) and layer.selectedFeatureCount() > 0:
            bbox = layer.boundingBoxOfSelected()
            pt = SpatialPoint(layer.crs(), bbox.center())
            self.sigPanRequest.emit(pt)

    def rollBackEdits(self, layer: QgsVectorLayer, leave_editable: bool = True, trigger_repaint: bool = False) -> bool:
        self.sigFreezeCanvases.emit(True)
        if not layer.rollBack():
            title = 'Error'
            text = 'Problems during rollback'
            result = False
            self.sigMessage.emit(title, text, Qgis.Critical)
        else:
            result = True
        self.sigFreezeCanvases.emit(False)
        if trigger_repaint:
            layer.triggerRepaint()
        return result

    def saveEdits(self, layer: QgsVectorLayer, leave_editable: bool = True, trigger_repaint: bool = False) -> bool:
        """
        Should be called, when the features should be committed but the editing session is not ended.
        """
        if not isinstance(layer, QgsVectorLayer):
            return False

        result = True
        if layer.isModified():
            if not layer.commitChanges():
                self.commitError(layer)
                result = False

            if trigger_repaint:
                layer.triggerRepaint()

        if leave_editable:
            layer.startEditing()

        return result

    def stopEditing(self, layer: QgsVectorLayer, allowCancel:bool) -> bool:
        """
        Will be called, when an editing session is ended and the features should be committed.
        Returns True if the layers edit state was finished
        """
        if not isinstance(layer, QgsVectorLayer):
            return False

        if layer.isModified():
            buttons = QMessageBox.Yes | QMessageBox.No
            if allowCancel:
                buttons = buttons | QMessageBox.Abort

            button = QMessageBox.question(None,
                                          'Stop Editing',
                                          'Do you want to save the changes to layer {}'.format(layer.name()),
                                          buttons)

            if button == QMessageBox.Abort:
                return False
            elif button == QMessageBox.Yes:
                self.saveEdits(layer, leave_editable=False, trigger_repaint=True)
            elif button == QMessageBox.No:
                self.rollBackEdits(layer, leave_editable=False, trigger_repaint=True)
        else:
            layer.commitChanges()
        if not layer.isEditable():
            self.sigEditingStopped.emit(layer)
        return not layer.isEditable()

    def commitError(self, layer: QgsVectorLayer):
        """
        collects the layer's commit errors and emits the sigMessage with a warning.
        """
        title = 'Commit Errors'

        info = "Could not commit changes to layer {}".format(layer.name())
        info += "\n\n{}".format('\n '.join(layer.commitErrors()))

        self.sigMessage.emit(title, info, Qgis.Warning)

