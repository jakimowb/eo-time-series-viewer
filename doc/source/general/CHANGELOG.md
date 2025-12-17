---
title: Changelog
hide-toc: false
---

# Changelog

## EOTSV 2.3 (2025-11-09)

* revision of TimeSeries model. Source images are now loaded and removed much faster (
  issues [27]https://github.com/jakimowb/eo-time-series-viewer/issues/27
  and [29](https://github.com/jakimowb/eo-time-series-viewer/issues/29))
* the default style of profile candidates can be set in the EOTSV settings
* plot styles activate antialias by default
* fixed loading of Sentinel-2 images and other datasets with sublayers (
  issue [46](https://github.com/jakimowb/eo-time-series-viewer/issues/46))
* EOTSV loads Tanager \*.h5 files

## EOTSV 2.2 (2025-09-25)

* multi-sensor time series can be saved as JSON. loading from
  the timeseries from a JSON file is rapid, as it avoids source files access
* faster and asynchronous loading of time series sources
  [issue #27](https://github.com/jakimowb/eo-time-series-viewer/issues/27)
* faster and asynchronous loading of time series raster images
  [issue #31](https://github.com/jakimowb/eo-time-series-viewer/issues/31)
* faster and asynchronous loading of temporal profiles
* the initial raster stretch is taken from the first sensor raster
* added `scripts/load_eotsv_profiles.py` to load temporal profiles
  without having the QGIS API installed
* some context menus got shorter names and better tooltips
* preview for python-code band index expressions
* (experimental) user functions allow creating additional profiles
  that are derived from temporal profiles
* antialias for spectral and temporal profile plots
* fixed a bug that could occur when selecting vector features in a map
* map layers that are not used in any legend (zombie layers) are now removed from the EOTSV project
  to not appear in layer selection widgets
* map canvas context menu option 'Copy > All Maps' now copies maps without other widget boundaries
  to the clipboard
* missing / inaccessible sources are highlighted in the time series view
* fixed minor issues related to the QGIS processing framework, e.g., with QGIS 3.44

## EOTSV 2.1 (2025-06-05)

* added a map region window to the temporal profile plot
* revised quick labeling tools
* revised documentation, added more animated GIFs
* temporal profile plot: fixed band matching, added quick label shortcuts

## EOTSV 2.0 (2025-04-19)

* revised map visualization
* faster image loading by using the QGIS task manager and parallel background threads

* revised of Temporal Profile (TP) Tool.
    * TPs now consist of full-spectrum time series, loaded in parallel background threads
    * TPs are stored in vector layer fields
    * TPs can be loaded for vector layer points using a QGIS processing algorithm
    * the TP tool visualizes TPs from different vector layers or layer fields
    * TP tool has shortcuts to visualize spectral indices
      from https://github.com/awesome-spectral-indices/awesome-spectral-indices

* revised of EO Time Series Viewer Settings
    * settings are now stored in the QGIS settings dialog
    * allows defining the number of parallel reading threads
    * it allows defining shortcuts to visualize spectral indices in the Temporal Profile tool

* revised of Quick Labeling
    * added customized quick label values that allow defining new values using a QGIS expression
    * the quick label editor widget allows defining a classification scheme
    * added quick-labeling shortcuts to the TP tool context menu


* FORCE product import allows filtering data by start and end date

## EOTSV 1.20 (2024-12-08)

* added FORCE Product Import
* restore / reload EOTSV workbench from QGIS Project, e.g.,
  time series sources, map layer styles (rendering plus symbology),
  map extent, crs and current date
* optimized map rendering
* background tasks can be canceled in the task manager.
* fixed a fatal crash related to a missing QgsRasterDataProvider python ref

## EOTSV 1.19 (2024-09-29)

* API fixes to run with QGIS 3.34–3.38
* updates Spectral Library Module
* enabled tooltips in MapCanvas context menu
* attribute table: next / previous feature buttons consider order as shown in the table
* fixed VRT building
* fixed context menu connection in QGIS environments with other languages than English
* maps can flash selected features
* spectral profiles are now extracted with context information

## EOTSV 1.18 (2023-04-07)

_Stability Update_

* removed several issues related to updates in QGIS and GDAL
* updated QPS library, which introduces several updates to the SpectralLibrary handling

## EOTSV 1.17 (2021-03-10)

* quick raster band selection and GDAL Metadata panel now appear in the QGIS layer properties dialog
* fixed smaller issues related to plugin loading and unloading
* added bulk loading from time series definition files
* fixes to run with QGIS 3.18+
* move to the next / previous observation with arrow right/left
* move to the next / previous observation window with CTRL + arrow right/left or A/D
* move to the last / first observation with End/Pos1 or ALT + A/D
* select the next / previous vector feature with arrow downs/up or S/W
* added option for exclusive visibility of map views
* show the next / previous map view with PageDown/PageUp or ALT + S/W
* set map center from/to QGIS with F1/ALT+F1
* set map extent from/to QGIS with F2/ALT+F2
* modified observation slider, slider shows a range of visible dates

## EOTSV 1.16 (2021-02-02)

* fixed smaller issues
* the forward / backward button to move in time now shifts by the number of opened observation dates/maps
* next / previous feature button offers to (i) move to the next feature and (ii)
  update the map dates according to the availability of raster sources for the new map extent
* faster updates of observation data visibility

## EOTSV 1.15 (2020-11-23)

* source files can be opened by drag and drop to the time series tree view
* maps can be organized in multiple rows per map view (rows x columns)
* map descriptions can be defined with QgsExpressions, e.g. '@map_date' to show the date
* quick labels: CTRL + right mouse button opens a map menu even when the feature-modified map tool is activated
* source visibility update can be run on the entire time series or (new and faster) for the next time steps only
* added the "follow current date" option to the time series table to keep focus on the map window date range
* added wildcard and regular expression filter to the time series table
* smaller bug fixes and improvements

## EOTSV 1.14 (2020-11-06)

* this version focuses on stability updates and improvements of the "quick label" system
* the map canvas menu is now available with a standard map tool (like zoom tool)
* introduces label groups to apply quick labeling shortcuts on different sets of vector fields
* attribute table allows selecting added features automatically
* optimized package imports
* improved SpectralLibrary tool
* fixed bugs

## EOTSV 1.13 (2020-07-23)

* time series and map settings can be stored to and reloaded from QGIS Projects
* refactored layer styling and default raster stretching
* fixed CRS translation bug and other smaller bugs
* quick labels can be used to write date / datetime data into vector fields of type QDate or QDateTime
* refactored context menus, e.g., in map view layer tree view, fixed #106

## EOTSV 1.12 (2020-04-09)

* TimeSeries tree view allows changing the visibility of single source images, e.g., to hide clouded observations
* several updates to the Spectral Library Widget, e.g., import / export of profiles from ASD, ARTMO, EcoSYS or SPECCHIO
* EOTSV allows opening images from sources with subdatasets, e.g., from Sentinel-2 or HDF images.

## EOTSV 1.11 (2020-01-23)

* revised unit tests for CI pipelines
* fixed smaller issues in SensorModel
* fixed #103: EOTSV crashed on Linux, caused by an attempt to store an unpickable QgsTextFormat to QSettings

## EOTSV 1.10 (2019-11-25)

* improved matching of source images to sensors: matching can be specified in the settings dialog. Sensor matching
  based on ground sampling distance + number of bands + data type and optionally wavelength and/or sensor name
* the settings dialog shows known sensor / product specification and allows modifying their default "sensor name"
* fixed copying of layer styles to maps of the same sensor and map view type
* improved speed of mapping and layer buffering
* failed image sources are logged in the EO Time Series Viewer log panel
* Spectral Library Viewer better handles large collections of spectral profiles

## EOTSV 1.9 (2019-10-02)

* includes several smaller updates
* fixed error 'shortcutVisibleInContextMenu' error that occurred with Qt < 5.10
* enhanced wavelength extraction from GDAL metadata: wavelength can be specified per band

## EOTSV 1.8 (2019-09-19)

* updated spectral library module
* fixed #104: error in case of a wrong spatial extent
* by default, CRS is properly shown in map view settings
* user-defined CRS visible

## EOTSV 1.7 (2019-08-06)

* increased contrast for default map view text
* improved reading of wavelength information, e.g., from Pleiades, Sentinel-2 and RapidEye data
* temporal profile plot: data gaps can be shown by breaks in the profile line, data source information is correctly
  shown for selected points only
* current extent can be copied via MapCanvas context menu
* fixed #102: move maps to the date of interest selected in a temporal profile plot

## EOTSV 1.6 (2019-07-16)

* re-design of map visualization: faster and more compact, the number of maps is fixed to n dates x m map views
* date, sensor or map view information can be plotted within each map and become available in screenshots
* releases map layers that are not required any more
* slider + buttons to navigate over time series
* fixed preview in the crosshair dialog

## EOTSV 1.5 (2019-07-07)

* closing the EO Time Series Viewer instance will release all of its resources
* added "Lock Map Panel" to avoid unwanted resizing of the central widget
* fixed missing updates of the time series tree view when adding / removing source images
* the map canvas context menu lists layers with a spatial extent intersecting the cursor position only
* fixes feature selection error
* added quick label source image to label the path of the raster layer

## EOTSV 1.4 (2019-07-02)

* adding vector layers with sub-layers will add all sub-layers
* map canvas context menu "Focus on Spatial Extent" will hide maps without time series data for the current spatial
  extent
* labeling dock allows iterating over vector features. the spatial map extent will be centered to each feature (#26)
* added several convenience functions to the TimeSeriesViewer object
* fixed a bug that did not allow creating new polygon features
* temporal profile visualization: fixed icons to preview selected plot style, coordinate described by "<fid> <name>",
  e.g. "42 Deforested" fixed plot style preview
* updated SpectralLibraryViewer
* fixed a spelling error in the stacked band input dialog
* MapViews can add raster layers that have been opened in QGIS, e.g., XYZ Tile with OpenStreetMap data

## EOTSV 1.3 (2019-06-12)

* fixed #99: opening example closes QGIS on linux
* fixed #96 and #99: docutils not installed error when showing rst/md content
* fixed #97: TSV does not start (Linux)

## EOTSV 1.2 (2019-05-31)

* added SaveAllMapsDialog and menu option to export all maps as image files.
* fixed #91: select Temporal Profile / Spectral Profile button activates the required map tools.
* fixed #92: map canvas context menu "copy to clipboard" options.

## EOTSV 1.1 (2019-05-24)

* dates and data sources of the TimeSeries are now shown in a TreeView instead of TableView
* observation dates of current visible map canvases are highlighted in the time series tree view
* sensor raster layer properties can be opened from MapView layer tree #87. Stats will be related to the center
  mapcanvas.
* fixed: StackedInputDialog, MapCanvas context menu, "Save Changes?" labeling dialog (#85),
* remove temporal profile (#86), draw new feature error (#84), Crosshair button status (#90) and more ...

## EOTSV 1.0 (2019-05-15)

* labeling tools to modify vector layers.
* quick labeling for time-labels information
* synchronization with QGIS Map canvas center
* SpectralLibrary can import SpectralProfiles from a raster image based on vector positions
* simplified MapView control dock, each MapView has its own layer tree.
* improved MapTool organization
* removed PyQtGraph from a list of required external python packages
* renamed the plugin folder from "timeseriesviewerplugin" to "EOTimeSeriesViewer".
* improved SpectraLibrary tool
* CI tests with bitbucket pipelines
* several bug fixes

## EOTSV 0.8 (2019-03-01)

* added labeling panel
* scheduled map canvas refreshes
* multiple images per observationdata & sensor
* fixed several bugs
* fixed bugs which were caused by CRS changes
* fixed macOS QGIS (3.4.1.) crashes caused by QgsMapCanvas constructor
* uses QgsTaskManager for background loading
* own QgsMapLayerStore to not mix-up with (main) QGIS layers
* fixed bugs related to changes in QGIS API

## EOTSV 0.7 (2018-06-20)

* Visualization of images with stacked temporal information (each band = one observation date)
* some bugfixes
* Speclib I/O as CSV or ENVI-Spectral Library + CSV table for attributes
* temporary VRTs are now created in-memory (gdal VSI mechanism) instead of a disk temp path
* Spectral Library: profile coordinate now in the center of the map pixel (issue #66)
* Save map canvas to clipboard
* The width of plot lines is now scale-independent (issue #64, QPen.setCosmetic(True))
* adding fields to a spectral library (issue #61)

## EOTSV 0.6 (2018-06-04)

SpectralLibrary Module

* now based on in-memory QgsVectorLayer
* Locations and values of spectral profile can be exported as vector data set
* Locations of spectral profiles can be rendered on MapCanvases

Temporal Profile Module

* now based on in-memory QgsVectorLayer
* Locations of temporal profiles can be exported as a vector data set
* Band values of temporal profiles can be exported as CSV file
* Locations of temporal profiles can be rendered on MapCanvases

## EOTSV 0.5 (2018-04-17)

* ported to QGIS 3, Qt5 and Python 3.6
* improvements in temporal profile visualization
* removed several bug
* visibility of vector and raster layers can be toggled per map view
* improved interaction between QGIS and EOTSV (Buttons to import/export a spatial extent of map canvas or center)
* improved definition of individual 2D / 3D charts per sensor and pixel-location
* added based OpenGL-based 3D plot features (axis, grids, labels)
* changed the name to "EO Time Series Viewer" (EOTSV)
* merged updates to temporal profile visualization, e.g.,
  save temporal profiles, compare 2D profiles between different locations, experimental 3D visualization

## EOTSV 0.3 (2018-01-31)

* added file filters for OpenFileDialog

## EOTSV 0.2 (2018-01-19)

* initialized Sphinx-based documentation
* improved map visualization + map settings

## EOTSV 0.2 (2017-05-21)

* many changes, done in development branch "develop",
* e.g.: QGIS MapCanvases for interactive maps, temporal profiles, ...

## EOTSV 0.1 (2017-02-14)

* first setup for test users in the recent development branch

