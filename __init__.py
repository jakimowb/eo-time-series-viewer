# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EO Time Series Viewer


                             -------------------
        begin                : 2015-08-20
        copyright            : (C) 2015 by HU-Berlin
        email                : benjamin.jakimow[at]geo.hu-berlin.de
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
import pathlib
import site


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load the EO Time Series Viewer Plugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """

    d = pathlib.Path(__file__).parent
    site.addsitedir(d)

    from eotimeseriesviewer.eotimeseriesviewerplugin import EOTimeSeriesViewerPlugin
    return EOTimeSeriesViewerPlugin(iface)
