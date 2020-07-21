"""
***************************************************************************
    layerconfigwidget/core.py - Helpers and emulations for QgsMapLayerConfigWidgets
    -----------------------------------------------------------------------
    begin                : <month and year of creation>
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

import typing
import os
import pathlib
import enum
import re
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsFileUtils, QgsSettings, QgsStyle, QgsApplication
from qgis.gui import QgsRasterHistogramWidget, QgsMapCanvas, QgsMapLayerConfigWidget, \
    QgsLayerTreeEmbeddedConfigWidget, QgsMapLayerConfigWidgetFactory, QgsRendererRasterPropertiesWidget, \
    QgsRendererPropertiesDialog, QgsRasterTransparencyWidget, QgsProjectionSelectionWidget
#
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import QIcon
from ..utils import loadUi


def configWidgetUi(name: str) -> str:
    """
    Returns the full path to a '*.ui' file
    :param name:
    :type name:
    :return:
    :rtype:
    """
    path = pathlib.Path(__file__).parents[1] / 'ui' / name
    return path.as_posix()


class QpsMapLayerConfigWidget(QgsMapLayerConfigWidget):

    def __init__(self, mapLayer: QgsMapLayer, canvas: QgsMapCanvas, *args, **kwds):
        assert isinstance(mapLayer, QgsMapLayer)
        assert isinstance(canvas, QgsMapCanvas)
        super().__init__(mapLayer, canvas, *args, **kwds)
        self.mMapLayer = mapLayer
        self.mCanvas = canvas

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the QgsMapCanvas
        """
        return self.mCanvas

    def mapLayer(self) -> QgsMapLayer:
        """
        Returns the map layer
        """
        return self.mMapLayer

    def menuButtonMenu(self) -> QMenu:
        return None

    def menuButtonToolTip(self):
        return ''

    def syncToLayer(self, mapLayer: QgsMapLayer = None):
        """
        Implement this method to take up changes from the underlying map layer.
        """
        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer

    def reset(self):
        """
        Implement this method to reset values
        """

    def apply(self):
        """
        Implement this method to apply changes to the underlying map layer.
        """
        pass


class MetadataConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Information" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        self.setLayout(QVBoxLayout())
        self.textBrowser: QTextBrowser = QTextBrowser()
        self.layout().addWidget(self.textBrowser)

        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        if isinstance(lyr, QgsMapLayer):
            style = QgsApplication.reportStyleSheet(QgsApplication.WebBrowser)
            md = lyr.htmlMetadata()
            md = md.replace('<head>', '<head><style type="text/css">{}</style>'.format(style))
            self.textBrowser.setHtml(md)
        else:
            self.textBrowser.setHtml('')


class MetadataConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Information', icon=QIcon(':/images/themes/default/mActionPropertiesWidget.svg')):
        super(MetadataConfigWidgetFactory, self).__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return MetadataConfigWidget(layer, canvas, parent=parent)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


class SourceConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Source" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        loadUi(configWidgetUi('sourceconfigwidget.ui'), self)
        assert isinstance(self.tbLayerName, QLineEdit)
        assert isinstance(self.tbLayerDisplayName, QLineEdit)
        assert isinstance(self.mCRS, QgsProjectionSelectionWidget)
        self.tbLayerName.textChanged.connect(lambda txt: self.tbLayerDisplayName.setText(layer.formatLayerName(txt)))
        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        if isinstance(lyr, QgsMapLayer):
            self.tbLayerName.setText(lyr.name())
            self.mCRS.setCrs(lyr.crs())
        else:
            self.tbLayerName.setText('')
            self.tbLayerDisplayName.setText('')
            self.mCRS.setCrs(None)

    def apply(self):
        lyr = self.mapLayer()
        if isinstance(lyr, QgsMapLayer):
            lyr.setName(self.tbLayerName.text())
            lyr.setCrs(self.mCRS.crs())


class SourceConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Source', icon=QIcon(':/images/themes/default/propertyicons/system.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return SourceConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer) -> bool:
        return isinstance(layer, QgsMapLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


class SymbologyConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Source" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, style: QgsStyle = QgsStyle(), parent=None):
        super().__init__(layer, canvas, parent=parent)
        loadUi(configWidgetUi('symbologyconfigwidget.ui'), self)
        self.mSymbologyWidget = None
        self.mStyle: QgsStyle = style
        self.mDefaultRenderer = None
        if isinstance(layer, (QgsRasterLayer, QgsVectorLayer)):
            self.mDefaultRenderer = layer.renderer().clone()

        self.syncToLayer()

    def symbologyWidget(self) -> typing.Union[QgsRendererRasterPropertiesWidget, QgsRendererPropertiesDialog]:
        return self.scrollArea.widget()

    def style(self) -> QgsStyle:
        return self.mStyle

    def menuButtonMenu(self) -> QMenu:
        m = QMenu('Style')

        a = m.addAction('Load Style...')
        a.triggered.connect(lambda: self.loadStyle(None))
        a = m.addAction('Save Style...')
        a.triggered.connect(lambda: self.saveStyle(None))
        m.addSeparator()
        a = m.addAction('Save as Default')
        a.triggered.connect(self.saveStyleAsDefault)
        a = m.addAction('Restore Default')
        a.triggered.connect(self.loadDefaultStyle)
        m.addSeparator()

        m.addSeparator()
        a = m.addAction('Reset')
        a.triggered.connect(self.reset)

        return m

    def loadStyle(self, fileName: str = None):
        lastUsedDir = QgsSettings().value("style/lastStyleDir")

        if isinstance(fileName, pathlib.Path):
            fileName = str(fileName.resolve())

        if fileName is None:
            fileName = QFileDialog.getOpenFileName(self,
                                                   'Load layer properties from style file',
                                                   lastUsedDir,
                                                   'QGIS Layer Style file (*.qml)')
        if len(fileName) == 0:
            return
        if not re.search(r'\.qml$', fileName, re.I):
            fileName += '.qml'

        oldStyle = self.mapLayer().styleManager().style(self.mapLayer().styleManager().currentStyle())
        msg, success = self.mapLayer().loadNamedStyle(fileName)

        if success:
            self.syncToLayer()
            QgsSettings().setValue('style/lastStyleDir', os.path.dirname(fileName))
        else:
            QMessageBox.information(self, 'Load Style', msg)

    def saveStyle(self, fileName: str = None):
        lastUsedDir = QgsSettings().value("style/lastStyleDir")

        if isinstance(fileName, pathlib.Path):
            fileName = str(fileName.resolve())

        if fileName is None:
            fileName = QFileDialog.getSaveFileName(self,
                                                   'Save layer properties as style file',
                                                   lastUsedDir,
                                                   'QGIS Layer Style file (*.qml);;Styled Layer Descriptor (*.sld)'
                                                   )
        if len(fileName) == 0:
            return

        styleType = 'QML'
        if re.search(r'\.sld$', fileName, re.I):
            styleType = 'SLD'
        else:
            fileName = QgsFileUtils.ensureFileNameHasExtension(fileName, ['qml'])

        self.apply()

    def loadStyle(self, fileName: str = None):
        lastUsedDir = QgsSettings().value("style/lastStyleDir")

        if isinstance(fileName, pathlib.Path):
            fileName = str(fileName.resolve())

        if fileName is None:
            fileName, filter = QFileDialog.getOpenFileName(self,
                                                           'Load layer properties from style file',
                                                           lastUsedDir,
                                                           'QGIS Layer Style file (*.qml)')
        if len(fileName) == 0:
            return
        if not re.search(r'\.qml$', fileName, re.I):
            fileName += '.qml'

        oldStyle = self.mapLayer().styleManager().style(self.mapLayer().styleManager().currentStyle())
        msg, success = self.mapLayer().loadNamedStyle(fileName)

        if success:
            self.syncToLayer()
            QgsSettings().setValue('style/lastStyleDir', os.path.dirname(fileName))
        else:
            QMessageBox.information(self, 'Load Style', msg)

    def saveStyle(self, fileName: str = None):
        lastUsedDir = QgsSettings().value("style/lastStyleDir")

        if isinstance(fileName, pathlib.Path):
            fileName = str(fileName.resolve())

        if fileName is None:
            fileName, filter = QFileDialog.getSaveFileName(self,
                                                           'Save layer properties as style file',
                                                           lastUsedDir,
                                                           'QGIS Layer Style file (*.qml);;Styled Layer Descriptor (*.sld)'
                                                           )
        if len(fileName) == 0:
            return

        styleType = 'QML'
        if re.search(r'\.sld$', fileName, re.I):
            styleType = 'SLD'
        else:
            fileName = QgsFileUtils.ensureFileNameHasExtension(fileName, ['qml'])

        self.apply()

        fileName = pathlib.Path(fileName).resolve().as_posix()
        if styleType == 'QML':
            flag, msg = self.mapLayer().saveNamedStyle(fileName)
        elif styleType == 'SLD':
            flag, msg = self.mapLayer().saveSldStyle(fileName)

        if flag:
            QgsSettings().value("style/lastStyleDir", fileName)
        else:
            QMessageBox.information(self, 'Save Style', msg)

    def saveStyleAsDefault(self):
        self.apply()

        msg, success = self.mapLayer().saveDefaultStyle()
        if not success:
            QMessageBox.information(self, 'Save Default Style', msg)

    def loadDefaultStyle(self):
        msg, success = self.mapLayer().loadDefaultStyle()
        if success:
            self.syncToLayer()
        else:
            QMessageBox.information(self, 'Load Default Style', msg)

    def setSymbologyWidget(self, w):
        wOld = self.scrollArea.widget()
        if w != wOld:
            if isinstance(wOld, QWidget):
                wOld.setParent(None)
            if isinstance(w, QWidget):
                self.scrollArea.setWidget(w)
            self.mSymbologyWidget = w

    def syncToLayer(self, *args):
        super().syncToLayer(*args)

        w = self.symbologyWidget()
        lyr = self.mapLayer()
        if isinstance(lyr, QgsRasterLayer):
            r = lyr.renderer()
            if isinstance(w, QgsRendererRasterPropertiesWidget):
                rOld = w.currentRenderWidget().renderer()
                if r.usesBands() != rOld.usesBands():
                    # see https://github.com/qgis/QGIS/issues/34602
                    w = None

            if not isinstance(w, QgsRendererRasterPropertiesWidget):
                w = QgsRendererRasterPropertiesWidget(lyr, self.canvas(), None)
                self.setSymbologyWidget(w)

        elif isinstance(lyr, QgsVectorLayer):
            if not isinstance(w, QgsRendererPropertiesDialog):
                w = QgsRendererPropertiesDialog(lyr, self.style(), embedded=True)
                self.setSymbologyWidget(w)
            else:
                s = ""
                pass

        else:
            self.setSymbologyWidget(QWidget())

    def apply(self):
        lyr = self.mapLayer()
        w = self.symbologyWidget()

        if isinstance(lyr, QgsRasterLayer) and isinstance(w, QgsRendererRasterPropertiesWidget):
            w.apply()
            """
            renderer = w.currentRenderWidget().renderer()
            if isinstance(renderer, QgsRasterRenderer):
                renderer = renderer.clone()
                renderer.setInput(lyr.dataProvider())
                lyr.setRenderer(renderer)
            """
        elif isinstance(lyr, QgsVectorLayer) and isinstance(w, QgsRendererPropertiesDialog):
            w.apply()
        pass


class SymbologyConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self, title='Symbology', icon=QIcon(':/images/themes/default/propertyicons/symbology.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return SymbologyConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, (QgsVectorLayer, QgsRasterLayer))

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True


class TransparencyConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    """
    """

    def __init__(self, title='Transparency', icon=QIcon(':/images/themes/default/propertyicons/transparency.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return QgsRasterTransparencyWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsRasterLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True


class HistogramConfigWidget(QpsMapLayerConfigWidget):

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        self.setLayout(QVBoxLayout())

        self.mScrollArea = QScrollArea()
        self.layout().addWidget(self.mScrollArea)

        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        if isinstance(lyr, QgsRasterLayer):
            w = self.mScrollArea.widget()
            if not isinstance(w, QgsRasterHistogramWidget):
                w = QgsRasterHistogramWidget(lyr, None)
                self.histogramScrollArea.setWidget(w)


class HistogramConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    """
    """

    def __init__(self, title='Transparency', icon=QIcon(':/images/themes/default/propertyicons/histogram.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return HistogramConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsRasterLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


class PyramidsConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Pyramids" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        loadUi(configWidgetUi('pyramidsconfigwidget.ui'), self)
        self.syncToLayer()


class PyramidsConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    """
    """

    def __init__(self, title='Pyramids', icon=QIcon(':/images/themes/default/propertyicons/pyramids.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return QgsRasterHistogramWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsRasterLayer)


class LegendConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Pyramids" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=None)
        self.setLayout(QVBoxLayout())
        self.mEmbeddedConfigWidget = QgsLayerTreeEmbeddedConfigWidget()
        self.layout().addWidget(self.mEmbeddedConfigWidget)
        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        self.mEmbeddedConfigWidget.setLayer(self.mapLayer())

    def apply(self):
        self.mEmbeddedConfigWidget.applyToLayer()

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


class LegendConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    """
    """

    def __init__(self, title='Legend', icon=QIcon(':/images/themes/default/legend.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return LegendConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsMapLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False


class RenderingConfigWidget(QpsMapLayerConfigWidget):
    """
    Emulates the QGS Layer Property Dialogs "Pyramids" page
    """

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent=None):
        super().__init__(layer, canvas, parent=parent)
        loadUi(configWidgetUi('renderingconfigwidget.ui'), self)
        self.syncToLayer()

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        if isinstance(lyr, QgsMapLayer):
            self.gbRenderingScale.setChecked(lyr.hasScaleBasedVisibility())
            self.mScaleRangeWidget.setScaleRange(lyr.minimumScale(), lyr.maximumScale())

    def apply(self):
        lyr = self.mapLayer()
        if isinstance(lyr, QgsMapLayer):
            lyr.setScaleBasedVisibility(self.gbRenderingScale.isChecked())
            if self.gbRenderingScale.isChecked():
                lyr.setMaximumScale(self.mScaleRangeWidget.maximumScale())
                lyr.setMinimumScale(self.mScaleRangeWidget.minimumScale())


class RenderingConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    """
    """

    def __init__(self, title='Rendering', icon=QIcon(':/images/themes/default/propertyicons/rendering.svg')):
        super().__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(False)

    def createWidget(self, layer, canvas, dockWidget=False, parent=None):
        return RenderingConfigWidget(layer, canvas, parent=parent)

    def supportsLayer(self, layer):
        return isinstance(layer, QgsMapLayer)

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True
