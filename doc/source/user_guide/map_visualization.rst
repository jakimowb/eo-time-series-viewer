.. _map_visualization:

=================
Map Visualization
=================

The EO Time Series Viewer visualizes a temporal subset of a raster time series
using a predefined number of map canvases. Each map belongs to an *observation date* and
a *Map View*. Using multiple map views allows visualizing different band combinations at the same time.

.. figure:: /img/mapview_concept.png

    Visualization of raster time series in different band combinations.


Map Properties
==============

The map properties box is used to specify the:

* number of maps per map view in horizontal and vertical direction,
* width and height of each map
* coordinate reference system (CRS)
* map background color
* the style how overlaid text will be styled


Click `Apply` to apply changes that affect the map size, number of maps and layout.
By default the `keep ratio` option is |cbc| checked, i.e. height will increase/decrease
as width.

.. figure:: /img/mapview_concept_2x6x2.png
    :width: 75%

    The two map views, using a 6x2 map layout per map view.



.. * :guilabel:`Set Center` center the QGIS Map View to the same coordinate as the EO TSV Map View
.. * :guilabel:`Get Center` center the EO TSV Map View to the same coordinate as the QGIS Map View
.. * :guilabel:`Set Extent` zoom the QGIS Map View to the same extent as the EO TSV Map View
.. * :guilabel:`Get Extent` zoom the EO TSV Map View to the same extent as the QGIS Map View
.. * ``Load center profile``, when checked |cbc|, the temporal profile of the center pixel will automatically be displayed and updated in the :ref:`Profile View` tab.

Map Canvas
==========

Maps in the |eotsv| can be used similar as known from the QGIS map canvas.
The :ref:`toolbar <gui_toolbar>` is used allows to activate tools to:

* |mActionPan| pan
* |mActionZoomIn| zoom in |mActionZoomOut| and out ,
* |mActionZoomActual| set the zoom to the raster pixel scale ,
* |mActionZoomActual| or the map extent to that of the entire time series .

The identify tool |select_location| can be used with the options to:

* |mActionPropertiesWidget| extract information for single pixels and vector features,
* |profile| to load pixel profiles into a :ref:`spectral library <gui_spectral_profile_view>`, or
* |mIconTemporalProfile| to load temporal profiles into the
  :ref:`temporal profile view <gui_temporal_profile_view>`.

If a vector layer is selected in the :ref:`map view <mapvis_mapviews>` layer tree,
vector features can be edited, added or removed.

The context menu offers various shortcuts, e.g. to optimize the raster color
stretch with respect to the current spatial extent, or to copy attributes related to map canvas
and its observation date.

.. figure:: /img/mapvis_map_context_menu.png

    The map context menu with shortcuts to optimize the color stretch


.. _mapvis_mapviews:

Map Views
=========

A map view controls how the raster and vector data is visualized along the
observation dates. Images linked to the same sensor are visualized
with the same band combination and contrast settings. This means, optimizing the
color stretch for a single raster layer will apply these settings to all
other layers that belong to the same map view and sensor.

Each map view has its own layer tree, consisting of a raster layer for each sensor derived from them
time series, as additional raster or vector layers.

* You can *add new Map Views* using the |mActionAddMapView| button. This will create a new row of map canvases.
  Remove a map view with the |mActionRemoveMapView| button.
* In case the Map View does not refresh correctly, you can 'force' the refresh using the |mActionRefresh| button (which will also apply all the render settings).
* Access the settings for individual Map Views by clicking in the mapview |mapviewbutton|
* You can use the |questionmark| button to highlight the current Map View selected in the dropdown menu (respective image chips will show red margin for a few seconds).


For every Map View you can alter the following settings:

* *Hide/Unhide* the Map View via the |mapviewHidden| button.

* *Activate/Deactivate Crosshair* via the |crosshair| button. Press the arrow button next to it to enter
  the *Crosshair specifications* |symbology| , where you can customize e.g. color, opacity, thickness, size and further options.

* You may rename the Map View by altering the text in the `Name` field.


Layer representation
====================


Similar to QGIS, you can change the layer representation in the layer properties dialog. It
can be opened from the layer tree or the map canvas context menu.

  .. figure:: /img/layerproperties_contextmenu.png

    The layer properties can be opened from either the layer tree (left) or a map canvas (right).

  .. figure:: /img/layerproperties_dialog.png

    The layer properties dialog.


Source Visibility
=================

Earth observation time series often have gaps. For example, clouds may have been masked,
the sensor did not cover the area that is currently visualized in the maps, or you just panned
your maps outside the sensor swath.

.. figure:: /img/mapvis_nodata_areas.png

In the time series panel, you can use the checkboxes |cbu| to hide the
raster sources and observation dates which does not contain data for the given map extent.

Furthermore, the map context menu offers the *Update visibility* function.
It checks for the entire time series, if the raster intersects with the map extent and contains
valid pixel, i.e. pixel that are not set to any no-data value.
Raster without valid pixels for the given extent will be unchecked, so that
only maps and observation dates are shown for which valid raster pixel can be shown.

.. figure:: /img/mapvis_update_visibility.gif

    The *Update visibility* function hides observations without
    valid pixels for the current map extent.

.. note::

    To keep the time that needed to run the *update visibility* test for the entire time series short,
    it is carried out on 25 points, regularly sampled from the current map extent.
    Theoretically it's possible, that none of the 25 points touches a valid pixel, while still the
    extent contains valid pixel inside the map extent. In that case the *update visibility* test
    might hide observations that still could provide useful information for a visual interpretation.

    If in doubt, you can increase the number of points in the |eotsv| settings
    (*Others > Settings*) - of course at the expense of speed.

    Furthermore, if the test runs too long, you can always cancel it in the task manager.
    Test results available until then are applied to the visibility of the sources.


.. AUTOGENERATED SUBSTITUTIONS - DO NOT EDIT PAST THIS LINE

.. |cbc| image:: /img/checkbox_checked.png
.. |cbu| image:: /img/checkbox_unchecked.png
.. |crosshair| image:: /icons/crosshair.png
   :width: 28px
.. |eotsv| replace:: EO Time Series Viewer
.. |mActionAddMapView| image:: /icons/mActionAddMapView.png
   :width: 28px
.. |mActionPan| image:: /icons/mActionPan.png
   :width: 28px
.. |mActionPropertiesWidget| image:: /icons/mActionPropertiesWidget.png
   :width: 28px
.. |mActionRefresh| image:: /icons/mActionRefresh.png
   :width: 28px
.. |mActionRemoveMapView| image:: /icons/mActionRemoveMapView.png
   :width: 28px
.. |mActionZoomActual| image:: /icons/mActionZoomActual.png
   :width: 28px
.. |mActionZoomIn| image:: /icons/mActionZoomIn.png
   :width: 28px
.. |mActionZoomOut| image:: /icons/mActionZoomOut.png
   :width: 28px
.. |mIconTemporalProfile| image:: /icons/mIconTemporalProfile.png
   :width: 28px
.. |mapviewHidden| image:: /icons/mapviewHidden.png
   :width: 28px
.. |mapviewbutton| image:: /img/mapviewbutton.png
.. |profile| image:: /icons/profile.png
   :width: 28px
.. |questionmark| image:: /img/questionmark.png
.. |select_location| image:: /icons/select_location.png
   :width: 28px
.. |symbology| image:: /icons/symbology.png
   :width: 28px
