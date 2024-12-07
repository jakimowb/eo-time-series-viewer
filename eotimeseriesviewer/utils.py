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
from typing import Union

from qgis.PyQt.QtCore import QByteArray, QSettings, QTextStream
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsMapLayer, QgsMapLayerStyle
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QWidget
from qgis.gui import QgisInterface
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
