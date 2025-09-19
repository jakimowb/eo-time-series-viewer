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
import enum
import sys
from typing import Any, List, Union

import qgis.utils
from qgis.PyQt.QtCore import QByteArray, QDateTime, QSettings, QSortFilterProxyModel, Qt, QTextStream
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QWidget
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsFeature, QgsFeatureSink, QgsMapLayer, QgsMapLayerStyle, QgsVectorLayer
from qgis.core.additions.edit import edit
from qgis.gui import QgisInterface, QgsAttributeTableView, QgsFontButton

from eotimeseriesviewer.dateparser import ImageDateUtils
from eotimeseriesviewer.qgispluginsupport.qps.layerproperties import AttributeTableWidget
from eotimeseriesviewer.timeseries.source import TimeSeriesDate, TimeSeriesSource
from eotimeseriesviewer.vectorlayertools import EOTSVVectorLayerTools


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
    layer.triggerRepaint()
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


class GotoFeatureOptions(enum.IntFlag):
    SelectFeature = 1
    PanToFeature = 2
    ZoomToFeature = 4
    FocusVisibility = 8


def gotoLayerFeature(fid: int, layer: QgsVectorLayer, tools: EOTSVVectorLayerTools, options: GotoFeatureOptions):
    if GotoFeatureOptions.SelectFeature in options:
        layer.selectByIds([fid])
    if GotoFeatureOptions.PanToFeature in options:
        tools.panToSelected(layer)
    if GotoFeatureOptions.ZoomToFeature in options:
        tools.zoomToSelected(layer)
    if GotoFeatureOptions.FocusVisibility in options:
        tools.focusVisibility()


def index_window(target_index: int, n_indices: int, window_size: int, mode: str = 'center') -> List[int]:
    if n_indices == 0 or window_size == 0:
        return []

    assert 0 <= target_index < n_indices
    assert mode in ['center', 'first', 'last', 'start', 'end']

    if mode == 'center':
        i0 = target_index - int(0.5 * window_size)
        i1 = target_index + int(0.5 * window_size)
        if window_size % 2 == 0:
            # even
            i1 -= 1
    elif mode in ['first', 'start']:
        i0 = target_index
        i1 = target_index + window_size - 1
        s = ""
    elif mode in ['last', 'end']:
        i1 = target_index
        i0 = target_index - window_size + 1
    else:
        raise NotImplementedError(f'Unknown mode: {mode}')

    if i0 < 0:
        i0 = 0
        i1 = min(n_indices - 1, window_size - 1)
    if i1 >= n_indices:
        i0 = max(0, n_indices - window_size)
        i1 = n_indices - 1

    return list(range(i0, i1 + 1))


def toDateTime(item: Union[TimeSeriesDate, TimeSeriesSource, Any]) -> QDateTime:
    if isinstance(item, (TimeSeriesDate, TimeSeriesSource)):
        return item.dtg()
    else:
        return ImageDateUtils.datetime(item)


def findNearestDateIndex(target_date, date_items: List, exact_match: bool = False) -> int:
    """Returns the index of the item in date_items, which is closest to the target_date item"""
    target_date = toDateTime(target_date)
    abs_diff = [abs(target_date.secsTo(toDateTime(item))) for item in date_items]

    closest = min(abs_diff)
    if exact_match:
        assert closest == 0
    return abs_diff.index(closest)


def gotoFeature(attributeTable: AttributeTableWidget,
                goDown: bool = True,
                options: GotoFeatureOptions = GotoFeatureOptions.SelectFeature

                ) -> int:
    assert isinstance(attributeTable, AttributeTableWidget)

    tv: QgsAttributeTableView = attributeTable.mMainView.tableView()
    model: QSortFilterProxyModel = tv.model()

    FID_ORDER = []

    for r in range(model.rowCount()):
        fid = model.data(model.index(r, 0), Qt.UserRole)
        FID_ORDER.append(fid)

    if len(FID_ORDER) > 0:
        sfids = tv.selectedFeaturesIds()
        if len(sfids) == 0:
            nextFID = FID_ORDER[0]
        elif goDown:
            row = FID_ORDER.index(sfids[-1])
            nextFID = model.data(model.index(row + 1, 0), Qt.UserRole)
            if nextFID is None:
                nextFID = FID_ORDER[-1]
        else:
            row = FID_ORDER.index(sfids[0])
            nextFID = model.data(model.index(row - 1, 0), Qt.UserRole)
            if nextFID is None:
                nextFID = FID_ORDER[0]

        if isinstance(nextFID, int):
            tv.scrollToFeature(nextFID)
        gotoLayerFeature(nextFID, attributeTable.mLayer, attributeTable.vectorLayerTools(), options)
        return nextFID
    return None
