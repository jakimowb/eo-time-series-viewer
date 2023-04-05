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
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QToolButton, QWidget, QAction, QMenu
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
