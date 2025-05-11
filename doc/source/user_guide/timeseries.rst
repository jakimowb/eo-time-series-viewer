===========
Time Series
===========

The |eotsv| visualizes a time series of raster images which is shown in the time series panel.
It can consist of raster sources that originate from different EO sensors, or products
derived from such sensors.
Each *Time Series Sources* linked to an *Time Series Date*. The time series panel can be used
to control the visibility of single sources or entire time series date in the map visualization.


.. figure:: /img/timeseries_dates_and_sources.png
    :width: 731px

    Time series panel, showing a time series with raster sources from two different sensors.

.. _timeseries_sources:

Time Series Sources
===================

A *Time Series Source* can be any raster images that (i) is readable by QGIS/GDAL and
(ii) provides a timestamp.
The |eotsv| searches different locations until it finds a usable time stamp.


.. list-table:: Possible time stamps locations
    :header-rows: 1

    * - Location
      - Description
    * - QGIS Layer Properties
      - Temporal properties, *Fixed time range > Start date*, see `QGIS Raster Layer Properties <https://docs.qgis.org/latest/en/docs/user_manual/working_with_raster/raster_properties.html#temporal-properties>`_
    * - GDAL metadata
      - ``ACQUISITIONDATETIME`` item in GDAL ``IMAGERY`` domain, see `GDAL Data Model <https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing>`_
    * - ENVI header file (`*.hdr`)
      - ``acquisition time`` item, see `ENVI header file specification <https://www.nv5geospatialsoftware.com/docs/ENVIHeaderFiles.html>`_
    * - Filename
      - Examples: ``2014-03-20`` or ``LC82270652014079LGN00_BOA.tif``
    * - Parent directory name
      - Examples: ``2014-03-20/image.tif`` or ``LC82270652014079LGN00/image.tif``


If none of the described options works, it is often easiest to add an
`ISO 8601 <https://en.wikipedia.org/wiki/ISO_8601>`_ timestamp either (i) to the
file- or folder name, or use a small script like the following to add it to the GDAL metadata.

.. code-block:: python

    # set timestamp to image
    from osgeo import gdal
    path = '/data/myimage.tif'
    ds = gdal.Open(path)
    assert isinstance(ds, gdal.Dataset)
    ds.SetMetadataItem('ACQUISITIONDATETIME', '2024-03-02', 'IMAGERY')
    ds.FlushCache()
    del ds

    # test if we can read the time stamp
    from qgis.PyQt.QtCore import QDateTime, Qt
    from eotimeseriesviewer.dateparser import ImageDateUtils
    dtg = ImageDateUtils.dateTimeFromLayer(path)
    assert isinstance(dtg, QDateTime)
    print(dtg.toString(Qt.ISODate))



.. _timeseries_sensors:

Sensors/Products
================

The |eotsv| assumes that images with the same spectral properties and pixel size
have been created by the same sensor and therefore should be handled in the same way.
For example, if you change the band combination and color stretch for a single Landsat image,
you like to do this for all other Landsat observations as well, to allow for a comparison.

Therefore, each source image is automatically linked to a *sensor*, or more general spoken,
an *image product, e.g, *Landsat 8*, *Sentinel-2* or a one-band *NDVI* image derived from.

A *sensor/product* is characterized by the following attributes

.. list-table:: Sensor/Product attributes
    :header-rows: 1

    * - Attribute
      - Description
    * - ``nb``
      - number of bands
    * - ``px_size_x``
      - pixel size in image x direction
    * - ``px_size_y``
      - pixel size in image y direction
    * - ``wl``
      - optional, list of wavelength, one for each band
    * - ``wlu``
      - optional, the wavelength unit, e.g. ``nm``
    * - ``name``
      - the sensor/product name. can be changed

The sensors of the time series and their attributes are listed in the
:ref:`Sensor/Products panel <gui_sensor_panel>`, which also summarizes
how many *time series dates* and *time series sources* relate to each sensor.

.. figure:: /img/sensordock.png

    Sensor/Products panel.

.. _timeseries_dates:

Time Series Dates
=================

A *time series date* is a group source images that (i) belong to the same sensor,
and, for the sake of visualization, (ii) have the same observation date.

Often source images have different time stamps, but we want to handle them as if they had the
same timestamp. For example, the Sentinel-2 observations that have been recorded on the same
day and the same orbit overpass may show a progressive increase in their time stamps.
Using the |eotsv| with a Date-Time Precission of a "Day",
all observations from the same day will be linked to the same *time series date* and
visualized in the same :ref:`map canvas <mapvis_canvas>`.

.. _timeseries_panel:

Time Series Panel
=================

The *Time Series Panel* lists the individual *time series dates* and their *time series sources*.

.. figure:: /img/timeseries_panel.gif

* **Date** corresponds to the image acquisition date as automatically derived by the EO TSV from the file name. Checking |cbc| or unchecking |cbu| the box in the date field will include or exclude the respective image from the display
* **Sensor** shows the name of the sensor as defined in the :ref:` <>` tab
* **ns**: number of samples (pixels in x direction)
* **nl**: number of lines (pixels in y direction)
* **nb**: number of bands
* **image**: path to the raster file

You can add new rasters to the time series by clicking |mActionAddRasterLayer| :superscript:`Add image to time series`.
Remove them by selecting the desired rows in the table (click on the row number) and pressing the |mActionRemoveTSD| :superscript:`Remove image from time series` button.

.. tip::

   If you have your time series available as one large raster stack, you can import this file via :menuselection:`Files --> Add images from time stack`


.. tip:: Click :menuselection:`Files --> Add example` to load a small example time series.


.. AUTOGENERATED SUBSTITUTIONS - DO NOT EDIT PAST THIS LINE

.. |cbc| image:: /img/checkbox_checked.png
.. |cbu| image:: /img/checkbox_unchecked.png
.. |eotsv| replace:: EO Time Series Viewer
.. |mActionAddRasterLayer| image:: /icons/mActionAddRasterLayer.png
   :width: 28px
.. |mActionRemoveTSD| image:: /icons/mActionRemoveTSD.png
   :width: 28px
