.. _gui:

========================
Graphical User Interface
========================

Overview
========

This is how the EO Time Series Viewer's interface looks after opening the
example data (*Files > Add Example*).

You can use the mouse cursor to highlight different GUI parts and jump
to its linked descriptions.

.. raw:: html

    <svg width="1200" height="800" style="display: block; position: relative;">
      <defs>
        <filter x="0" y="0" width="1" height="1" id="text_bg">
          <feFlood flood-color="white" result="bg" />
          <feMerge>
            <feMergeNode in="bg"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

        <image href="../_static/img/gui_overview.png" x="0" y="0"
            width="1085" height="682" />

          <g class="svg-hover-group">
            <a href="gui.html#menu-bar">
                <title>Menu Bar</title>
                <rect x="1" y="32" width="1084" height="20" />
                <text filter="url(#text_bg)" x="275" y="47">Menu Bar</text>
            </a>

            </g>

          <g class="svg-hover-group">
            <a href="gui.html#tool-bar">
                <title>Tool Bar</title>
                <rect x="1" y="50" width="1084" height="37" />
                <text filter="url(#text_bg)"
                      x="300" y="75">Tool Bar</text>
            </a></g>

          <g class="svg-hover-group">
            <a href="gui.html#map-visualization">
                <title>Mapping Panel</title>
                <text filter="url(#text_bg)"
                x="25" y="370">Mapping Panel</text>
                <rect x="2" y="90" width="225" height="331" />
            </a></g>

          <g class="svg-hover-group">
            <a href="gui.html#map-visualization">
                <title>Map Views</title>
                <text filter="url(#text_bg)"
                    x="456" y="200">Map Views</text>
                <rect x="230" y="90" width="614" height="331" />
            </a></g>

          <g class="svg-hover-group">
            <a href="gui.html#sensors-products-panel">
                <title>Sensor/Product Panel</title>
                <text filter="url(#text_bg)" x="875" y="245">Sensor/Products</text>
                <rect x="848" y="90" width="237" height="307" />
            </a></g>

          <g class="svg-hover-group">
            <a href="gui.html#time-series-panel">
                <title>Time Series Panel</title>
                <text filter="url(#text_bg)"
                    x="25" y="550">Time Series Panel</text>
                <rect x="2" y="424" width="223" height="256" />
            </a></g>

            <g class="svg-hover-group">
            <a href="gui.html#temporal-profile-view">
                <title>Temporal Profile Viewer</title>
                <text filter="url(#text_bg)"
                    x="450" y="550">Temporal Profile Viewer</text>
                <rect x="228" y="424" width="549"   height="256" />
            </a></g>

          <g class="svg-hover-group">
            <a href="gui.html#attribute-table">
                <title>Attribute Table</title>
                <text filter="url(#text_bg)"
                    x="837" y="550">Attribute Table</text>
                <rect x="780" y="424" width="305" height="256" />
            </a></g>

    </svg>

.. note::
    Just like in QGIS, many parts of the GUI are adjustable panels. You can arrange them as tabbed, stacked or separate windows.

    You can activate/deactivate panels under :menuselection:`View --> Panels`

.. _gui_menu_bar:

Menu Bar
========

The menu bar give access to methods for handling data and visualization settings.

.. figure:: /_static/img/gui_menubar.gif

    Screencast of the menu bar


The `Files` menu allows to add new raster sources to the time series, and other raster
and vector sources to overlay the time series data displayed in the map views.
You can also start specialized import dialogs, e.g. to load raster data
created with the FORCE processing framework.

The `View` menu can be used to show or hide the different panels and to add a new `map view` to the
map widget.

.. figure:: /img/menu_view_panels.png

    The `View` menu allows to show or hide different panels.

The `Navigation` menu allows to select map tools for navigation to different spatial extents.
It can also be used to copy the spatial extent from or to the map canvas of the main QGIS gui.

The `Tools` menu allows to start processing algorithms, e.g. to create a new temporal profile layer.



.. _gui_toolbar:

Tool Bar
========

In the tool bar you find tools to add and modify data and to adjust the data visualization.

.. csv-table:: Toolbar buttons and what they trigger
   :header: "Button", "Function"

   |mActionAddRasterLayer|, Add raster source to time series
   |mActionAddTS|, Add Time Series from CSV
   |mActionRemoveTS|, Remove all images from Time Series
   |mActionSaveTS|, Save Time Series as CSV file
   |mActionAddOgrLayer|, Add vector data file
   |qgsMapCenter|, Synchronize with QGIS map canvas
   |mActionAddMapView|, Add maps that show a specified band selection
   |mActionRefresh|, Refresh maps
   |mActionPan|, Pan map
   |mActionZoomIn|, Zoom into map
   |mActionZoomOut|, Zoom out
   |mActionZoomActual|, Zoom to pixel scale
   |mActionZoomFullExtent|, Zoom to maximum extent of time series
   |select_location|, Identify Pixels and Features
   |pan_center|, Center map on clicked locations
   |mActionPropertiesWidget|, Identify cursor location values
   |profile|, Identify raster profiles to be shown in a Spectral Library
   |mIconTemporalProfile|, Identify pixel time series for specific coordinate
   |mActionSelectRectangle|, Select Features
   |mActionToggleEditing|, Start Editing Mode
   |mActionSaveEdits|, Save Edits
   |mActionCapturePolygon|, Draw a new Feature


.. note::

   Only after |select_location| :sup:`Identify Pixels and Features` is activated you can select the other identify tools
   (|mActionPropertiesWidget|, |profile|, |mIconTemporalProfile|). You can activate them all at once as well as  of them,
   in case of the latter variant clicking in the map has no direct effect (other than moving the crosshair, when activated)


.. _gui_map_visualization:

Map Visualization
=================

The *Map Views* widget contains map canvases to visualize the observations of the raster time series.
The slider on the bottom allows to change the temporal window of observation dates that is shown.

Each canvas relates to a *Map View*, in which all raster images of the same sensor are
visualized with the same band combination and color stretch.
Using multiple map views allows to visualize different band combinations of the same raster
observation in parallel.

The *Mapping* panel allows to add or remove map views, change the canvas size and how canvases
are displayed within a map view.

A detailed overview on the map visualization options is described in :ref:`here <map_visualization>`

.. figure:: /img/map_visualization1.gif

    Screencast of map visualization

.. _gui_sensor_panel:

Sensors / Products Panel
========================

This panel show details on the *sensors* or *image product* types the time series
consists of, e.g. the number of bands and the spatial resolution.

For better handling, the *sensor names* can be changed.

.. figure:: /img/sensor_panel.gif

    The sensor panel show sensor details and allows to change their names


* ``name`` is automatically generated from the resolution and number of bands (e.g. *6bands@30.m*). This field is adjustable,
  i.e. you can change the name by double-clicking into the field. The here defined name will be also displayed in the Map View and the Time Series table.
* ``n images``: number of images within the time series attributed to the according sensor
* ``wl``: comma separated string of the (center) wavelength of every band and [unit]
* ``id``: string identifying number of bands, geometric resolution and wavelengths (primary for internal use)


.. _gui_cursor_location_panel:

Cursor Location Panel
=====================

This panel lets you inspect the values of a layer or multiple layers at the location where you click in the map view.
To load these layer details, activate the *identify cursor location value* tool
|select_location| with option |mActionPropertiesWidget| and use the mouse to click on the
location of interest.

* The Cursor Location Value panel should open automatically and list the information for a selected location. The layers will be listed in the order they appear in the Map View.
  In case you do not see the panel, you can open it via :menuselection:`View --> Panels --> Cursor Location Values`.

  .. figure:: /img/cursorlocationvalues.png

    The cursor location value panel

* By default, raster layer information will only be shown for the bands which are mapped to RGB. If you want to view all bands, change the :guilabel:`Visible` setting
  to :guilabel:`All` (right dropdown menu). Also, the first information is always the pixel coordinate (column, row).
* You can select whether location information should be gathered for :guilabel:`All layers` or only the :guilabel:`Top layer`. You can further
  define whether you want to consider :guilabel:`Raster and Vector` layers, or :guilabel:`Vector only` and :guilabel:`Raster only`, respectively.
* Coordinates of the selected location are shown in the :guilabel:`x` and :guilabel:`y` fields. You may change the coordinate system of the displayed
  coordinates via the |mActionSetProjection| :superscript:`Select CRS` button (e.g. for switching to lat/long coordinates).

.. figure:: /img/cursor_location_panel.gif

    Screencast showing how to use *cursor location info* tool to show pixel and vector object values


.. _gui_task_manager_panel:

Task Manager Panel
==================

The *Task Manager* panel shows the progress of `QGIS tasks <https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/tasks.html>`_
which have been started from the EO Time Series Viewer.
For example, to set the visibility of the individual raster sources,
whether the source even contains valid raster pixels for the current displayed spatial map extent.

.. figure:: /img/task_manager_update_visibility.gif

    The progress of the "update visibility" task is shown in the task manager panel (right).

.. _gui_timeseries_panel:

Time Series Panel
=================

The Time Series Panel show all raster sources that have been loaded into the time series.
Each source can be enabled to disabled, so that is will be not be shown in the map views.
Sources with a yellow background are currently displayed in a map canvas.
The panel can be used to add additional sources, save the current sources into a
CSV file, or remove sources from the time series.

.. figure:: /img/timeseries_panel.gif

    Showing and hiding of single observations sources in the time series panel.

.. _gui_temporal_profile_view:

Temporal Profile View
=====================

Here you can visualize temporal profiles that have been loaded for point coordinates.

To load a temporal profile, activate the *identify cursor location value* tool
|select_location| with option *collect tempral profiles* |mIconTemporalProfile| and click with the mouse
on a location of interest.

The temporal profile view allows profiles from different vector layers to be shown together.
A detailed description can be found in the :ref:`Temporal Profiles section <temporal_profiles>`.

.. figure:: /img/temporal_profile_panel.gif

    Collecting temporal profiles.


.. _gui_spectral_profile_view:

Spectral Profile View
=====================

This panel is used to visualize the spectral profiles.
To load a spectral profile from a raster image, activate the *identify cursor location value* tool
|select_location| with option *collect spectral profiles* |profile| and click with the mouse
on a location of interest.

The spectral profile view panel is the same as used in the EnMAP-Box_.
For details, please visit the EnMAP-Box documentation for
`using spectral libraries <https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual/gui.html#spectral-library-view>`_.

.. figure:: /img/spectral_profile_view.gif

    Collecting spectral profiles


.. _gui_attribute_table:

Attribute Table
===============

The attribute table can be used to show and edit vector layer attributes.
In addition to many tools that are already known from the QGIS attribute table,
the EO Time Series Viewer adds some shortcuts for a faster navigation and
:ref:`quick labeling <quick_labeling>`.

* use the |mActionArrowDown| or |mActionArrowUp| button to select the next or previous feature
* activate the |mActionPanToSelected| option to automatically pan the maps to selected feature(s)
* activate the |mapview| option to automatically update the
  :ref:`source visibility <mapvis_source_visibility>` of the new map extent


.. figure:: /img/attribute_table_nextfeatureoptions.png

    Shortcut buttons to select the next or previous feature and options to updates the map visualization.

.. figure:: /img/attribute_table.gif

    Attribute panel and map visualization can be linked for panning the
    map extent automatically to selected vector features.


.. AUTOGENERATED SUBSTITUTIONS - DO NOT EDIT PAST THIS LINE

.. _EnMAP-Box: https://enmap-box.readthedocs.io>
.. |mActionAddMapView| image:: /icons/mActionAddMapView.png
   :width: 28px
.. |mActionAddOgrLayer| image:: /icons/mActionAddOgrLayer.png
   :width: 28px
.. |mActionAddRasterLayer| image:: /icons/mActionAddRasterLayer.png
   :width: 28px
.. |mActionAddTS| image:: /icons/mActionAddTS.png
   :width: 28px
.. |mActionArrowDown| image:: /icons/mActionArrowDown.png
   :width: 28px
.. |mActionArrowUp| image:: /icons/mActionArrowUp.png
   :width: 28px
.. |mActionCapturePolygon| image:: /icons/mActionCapturePolygon.png
   :width: 28px
.. |mActionPan| image:: /icons/mActionPan.png
   :width: 28px
.. |mActionPanToSelected| image:: /icons/mActionPanToSelected.png
   :width: 28px
.. |mActionPropertiesWidget| image:: /icons/mActionPropertiesWidget.png
   :width: 28px
.. |mActionRefresh| image:: /icons/mActionRefresh.png
   :width: 28px
.. |mActionRemoveTS| image:: /icons/mActionRemoveTS.png
   :width: 28px
.. |mActionSaveEdits| image:: /icons/mActionSaveEdits.png
   :width: 28px
.. |mActionSaveTS| image:: /icons/mActionSaveTS.png
   :width: 28px
.. |mActionSelectRectangle| image:: /icons/mActionSelectRectangle.png
   :width: 28px
.. |mActionSetProjection| image:: /icons/mActionSetProjection.png
   :width: 28px
.. |mActionToggleEditing| image:: /icons/mActionToggleEditing.png
   :width: 28px
.. |mActionZoomActual| image:: /icons/mActionZoomActual.png
   :width: 28px
.. |mActionZoomFullExtent| image:: /icons/mActionZoomFullExtent.png
   :width: 28px
.. |mActionZoomIn| image:: /icons/mActionZoomIn.png
   :width: 28px
.. |mActionZoomOut| image:: /icons/mActionZoomOut.png
   :width: 28px
.. |mIconTemporalProfile| image:: /icons/mIconTemporalProfile.png
   :width: 28px
.. |mapview| image:: /icons/mapview.png
   :width: 28px
.. |pan_center| image:: /icons/pan_center.png
   :width: 28px
.. |profile| image:: /icons/profile.png
   :width: 28px
.. |qgsMapCenter| image:: /icons/qgsMapCenter.png
   :width: 28px
.. |select_location| image:: /icons/select_location.png
   :width: 28px
