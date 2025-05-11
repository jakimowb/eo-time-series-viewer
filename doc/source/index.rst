======================
EO Time Series Viewer
======================

The Earth Observation Time Series Viewer (EOTSV) is a free-and-open source QGIS Plugin to visualize and label
raster-based earth observation time series data.

.. image:: /img/screenshot_2.0.1.png




.. table::

   ==================== ================================================================================================
   Online documentation https://eo-time-series-viewer.readthedocs.io
   Source Code          https://github.com/jakimowb/eo-time-series-viewer
   Issue tracker        https://github.com/jakimowb/eo-time-series-viewer/issues
   ==================== ================================================================================================


Key Features
------------

* Raster images can be added to the time series without homogenisation of spatial extent or
  coordinate reference system. Time stamps are extracted automatically from (i) image meta data
  ("acquisition date"), (ii) the file name or (iii) the file directory path.
* Raster IO uses the `Geospatial Data Abstraction Library (GDAL) <http://www.gdal.org>`_,
  which supports more than 150 `raster formats <http://www.gdal.org/formats_list.html>`_.
* Distinguishes sensors by pixel size and number of bands and, if available,
  band wavelength information and sensor name.
* Spatial-temporal ("maps") visualisation allows to show multiples
  band combinations in parallel, e.g. True Color and coloured infrared.
* Color stretches are applied to all raster images of same sensor and band combination.
  This helps to optimise color stretches for multiple images in a minimum of time.
* Spectral-temporal ("time profile") visualisation shows raw or scaled, sensor specific band values.


.. seealso::
   `Virtual Raster Builder <https://virtual-raster-builder.readthedocs.io/en/latest/>`_ - A QGIS Plugin to create Virtual Raster images.

   `EnMAP Box 3 <https://enmap-box.readthedocs.io/en/latest/>`_ - A QGIS Plugin to visualize and process Multi- and Hyperspectral raster images.


License and Use
---------------

This program is free software; you can redistribute it and/or modify it under the terms of the
`GNU General Public License Version 3 (GNU GPL-3) <https://www.gnu.org/licenses/gpl-3.0.en.html>`_ ,
as published by the Free Software Foundation. See also :ref:`license`.


..  toctree::
    :maxdepth: 3
    :caption: General

    About <general/ABOUT.md>
    Contributors <general/CONTRIBUTORS.md>
    Changelog <general/CHANGELOG.md>
    Gallery <general/gallery.rst>
    License <general/license.rst>

..  toctree::
    :maxdepth: 3
    :numbered:
    :caption: User Guide

    Installation <user_guide/installation.rst>
    Quick Start <user_guide/quick_start.rst>
    GUI <user_guide/gui.rst>
    Time Series Model <user_guide/timeseries.rst>
    Map Visualization <user_guide/map_visualization.rst>
    Temporal Profiles <user_guide/temporal_profiles.rst>
    Spectral Profiles <user_guide/spectral_profiles.rst>
    Quick Labeling <user_guide/quick_labeling.rst>
    Processing Algorithms <user_guide/processing_algorithms.rst>
    Shortcuts <user_guide/shortcuts.rst>


Indices and tables
==================

    * :ref:`genindex`
    * :ref:`modindex`
    * :ref:`search`
