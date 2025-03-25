# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import sys
from typing import List, Union

from qgis.PyQt.QtGui import QColor
from qgis.gui import QgisInterface, QgsFontButton
from qgis.core import QgsFeature, QgsFeatureSink, QgsMapLayer, QgsMapLayerStyle, QgsVectorLayer
from qgis.core.additions.edit import edit
from qgis.PyQt.QtCore import QByteArray, QSettings, QTextStream
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QWidget
import qgis.utils


def qgisInstance():
    """
    If existent, returns the QGIS Instance.
    :return: QgisInterface | None
    """

    from eotimeseriesviewer.main import EOTimeSeriesViewer
    if isinstance(qgis.utils.iface, QgisInterface) and \
            not isinstance(qgis.utils.iface, EOTimeSeriesViewer):
        return qgis.utils.iface
    else:
        return None


def settings():
    return QSettings('HU-Berlin', 'EO Time Series Viewer')


def fixMenuButtons(w: QWidget):
    for toolButton in w.findChildren(QToolButton):
        assert isinstance(toolButton, QToolButton)
        if isinstance(toolButton.defaultAction(), QAction) and isinstance(toolButton.defaultAction().menu(), QMenu) \
                or isinstance(toolButton.menu(), QMenu):
            toolButton.setPopupMode(QToolButton.MenuButtonPopup)


def setFontButtonPreviewBackgroundColor(color: QColor, btn: QgsFontButton):
    fmt = btn.textFormat()
    fmt.setPreviewBackgroundColor(color)
    btn.setTextFormat(fmt)
    on = btn.objectName()
    css = f"""
    QgsFontButton#{on} {{
        background-color: {fmt.previewBackgroundColor().name()};
    }}
    QgsFontButton#{on}::menu-button {{
        background-color: palette(window);
        border: 1px solid gray;
        width: 16px;
    }}
    QgsFontButton#{on}::menu-indicator {{
        color: palette(window);
    }}
    QgsFontButton#{on}::menu-arrow  {{
        color: palette(window);
    }}"""

    btn.setStyleSheet(css)


def copyMapLayerStyle(styleXml: Union[QgsMapLayer, str],
                      layer: QgsMapLayer,
                      categories: QgsMapLayer.StyleCategories =
                      QgsMapLayer.StyleCategory.Symbology | QgsMapLayer.StyleCategory.Rendering
                      ):
    if isinstance(styleXml, QgsMapLayer):
        styleXml = layerStyleString(styleXml, categories=categories)
    assert isinstance(styleXml, str)

    oldStyle = layerStyleString(layer, categories=categories)
    if oldStyle != styleXml:
        setLayerStyleString(layer, styleXml, categories=categories)


def setLayerStyleString(layer: QgsMapLayer,
                        styleXml: Union[QDomDocument, str, QgsMapLayerStyle],
                        categories: QgsMapLayer.StyleCategory = QgsMapLayer.StyleCategory.AllStyleCategories) -> bool:
    """
    Applies a style to a map layer
    :param categories:
    :param layer:
    :param styleXml:
    :return:
    """
    assert isinstance(layer, QgsMapLayer)
    if isinstance(styleXml, str):
        doc = QDomDocument()
        doc.setContent(styleXml)
    elif isinstance(styleXml, QDomDocument):
        doc = styleXml
    else:
        raise Exception()

    assert isinstance(doc, QDomDocument)
    success, err = layer.importNamedStyle(doc, categories)
    if not success:
        print(f'setLayerStyleString: {err}', file=sys.stderr)
    return success


def layerStyleString(layer: QgsMapLayer,
                     categories: QgsMapLayer.StyleCategory =
                     QgsMapLayer.StyleCategory.Symbology | QgsMapLayer.StyleCategory.Rendering) -> str:
    doc = QDomDocument()
    err = layer.exportNamedStyle(doc, categories=categories)
    ba = QByteArray()
    stream = QTextStream(ba)
    stream.setCodec('utf-8')
    doc.documentElement().save(stream, 0)
    xmlData = str(ba, 'utf-8')
    return xmlData


def addFeatures(layer: QgsVectorLayer,
                features: List[QgsFeature],
                flags: Union[QgsFeatureSink.Flags, QgsFeatureSink.Flag] = QgsFeatureSink.Flags(),
                ) -> List[int]:
    """
    Adds features and returns the feature ids.
    :param layer: QgsVectorLayer
    :param features: list of QgsFeatures
    :param flags:
    :return: list of feature ids (int)
    """
    added_fids = []

    def onFeatureAdded(fid):
        added_fids.append(fid)

    layer.featureAdded.connect(onFeatureAdded)
    layer.addFeatures(features, flags=flags)
    layer.featureAdded.disconnect(onFeatureAdded)
    return added_fids


class doEdit(edit):

    def __init__(self, layer: QgsVectorLayer):

        super().__init__(layer)
        self.was_editable = False

    def __enter__(self):
        self.layer: QgsVectorLayer
        self.was_editable = self.layer.isEditable()
        if not self.was_editable:
            return super().__enter__()
        else:
            return self.layer

    def __exit__(self, ex_type, ex_value, traceback):
        if not self.was_editable:
            return super().__exit__(ex_type, ex_value, traceback)
        else:
            if ex_type:
                return False
