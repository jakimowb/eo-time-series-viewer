# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HUB Time Series Viewer
                                 A QGIS plugin

                             -------------------
        begin                : 2015-08-20
        copyright            : (C) 2015 by HU-Berlin
        email                : bj@geo.hu-berlin.de
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load SenseCarbon_TSV class from file sensecarbon_tsv.py.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from  timeseriesviewerplugin import TimeSeriesViewerPlugin
    return TimeSeriesViewerPlugin(iface)
