==============
Changelog
==============

2020-04-09 (version 1.12):
    * TimeSeries tree view allows to change the visibility of single source images, e.g. to hide clouded observations
    * several updates to the Spectral Library Widget, e.g. import / export of profiles from ASD, ARTMO, EcoSYS or SPECCHIO
    * EOTSV allows to open images from sources with subdatasets, e.g. from Sentinel-2 or HDF images.

2020-01-23 (version 1.11):
    * revised unit tests for CI pipelines
    * fixed smaller issues in SensorModel
    * fixed #103: EOTSV crashed on Linux, caused by an attempt to storing a unpickable QgsTextFormat to QSettings

2019-11-25 (version 1.10):
    * improved matching of source images to sensors: matching can be specified in the settings dialog. Sensor matching
      based on ground sampling distance + number of bands + data type and optionally wavelength and/or sensor name
    * settings dialog shows known sensor / product specification and allows to modify their default "sensor name"
    * fixed copying of layer styles to maps of same sensor and map view type
    * improved speed of mapping and layer buffering
    * failed image sources are logged in the EO Time Series Viewer log panel
    * Spectral Library Viewer better handles large collections of spectral profiles

2019-10-02 (version 1.9):
    * includes several smaller updates
    * fixed error 'shortcutVisibleInContextMenu' error that occurred with Qt < 5.10
    * enhanced wavelength extraction from GDAL metadata: wavelength can be specified per band

2019-09-19 (version 1.8):
    * updated spectral library module
    * fixed #104: error in case of wrong spatial extent
    * default CRS properly shown in map view settings
    * user-defined CRS visible

2019-08-06 (version 1.7):
    * increased contrast for default map view text
    * improved reading of wavelength information, e.g. from Pleiades, Sentinel-2 and RapidEye data
    * temporal profile plot: data gaps can be shown by breaks in the profile line, data source information is correctly shown for selected points only
    * current extent can be copied via MapCanvas context menu
    * fixed #102: move maps to date of interest selected in a temporal profile plot

2019-07-16 (version 1.6):
    * re-design of map visualization: faster and more compact, the number of maps is fixed to n dates x m map views
    * date, sensor or map view information can be plotted within each map and become available in screenshots
    * releases map layers that are not required any more
    * slider + buttons to navigate over time series
    * fixed preview in crosshair dialog

2019-07-07 (version 1.5):
    * closing the EO Time Series Viewer instance will release all of its resources
    * added "Lock Map Panel" to avoid unwanted resizing of central widget
    * fixed missing updates of time series tree view when adding / removing source images
    * map canvas context menu lists layers with spatial extent intersecting the cursor position only
    * fixes feature selection error
    * added quick label source image to label the path of raster layer

2019-07-02 (version 1.4):
    * adding vector layers with sublayers will add all sublayers
    * map canvas context menu "Focus on Spatial Extent" will hide maps without time series data for the current spatial extent
    * labeling dock allows to iterate over vector features. the spatial map extent will be centered to each feature (#26)
    * added several convenience function to TimeSeriesViewer object
    * fixed a bug that did not allow to create new polygon features
    * temporal profile visualization: fixed icons to preview selected plot style, coordinate described by "<fid> <name>", e.g. "42 Deforested", fixed plot style preview
    * updated SpectralLibraryViewer
    * fixed spelling error in stacked band input dialog
    * MapViews can add raster layers that have been opened in QGIS, e.g. XYZ Tile with OpenStreetMap data

2019-06-12 (version 1.3):
    * fixed #99: opening example closes QGIS on linux
    * fixed #96 and #99 : docutils not installed error when showing rst/md content
    * fixed #97: TSV does not start (Linux)

2019-05-31 (version 1.2):
    * added SaveAllMapsDialog and menu option to export all maps as image files.
    * fixed #91: select Temporal Profile / Spectral Profile button activates the required map tools.
    * fixed #92: map canvas context menu "copy to clipboard" options.

2019-05-24 (version 1.1):
    * dates and data sources of the TimeSeries are now shown in a TreeView instead TableView
    * observation dates of current visible map canvases are highlighted in the time series tree view
    * sensor raster layer properties can be opened from MapView layer tree #87. Stats will be related to center mapcanvas.
    * fixed: StackedInputDialog, MapCanvas context menu, "Save Changes?" labeling dialog (#85), remove temporal profile (#86), draw new feature error (#84), Crosshair button status (#90), and some more

2019-05-15 (version 1.0, major update):

    * labeling tools to modify vector layers.
    * quick labeling for time-labels information
    * synchronization with QGIS Map canvas center
    * SpectralLibrary can import SpectralProfiles from a raster image based on vector positions
    * simplified MapView control dock, each MapView has it's own layer tree.
    * improved MapTool organization
    * removed PyQtGraph from list of required external python packages

2019-03-29:
    * renamed plugin folder from "timeseriesviewerplugin" to "EOTimeSeriesViewer".
    * improved SpectraLibrary tool
    * CI tests with bitbucket pipelines
    * several bug fixes

2019-03-01 (version 0.8):
    * added labeling panel
    * scheduled map canvas refreshes
    * multiple images per observationdata & sensor
    * fixed several bugs

2018-11-13:
    * fixed bugs which where caused by CRS changes
    * fixed macOS QGIS (3.4.1.) crashes caused by QgsMapCanvas constructor

2018-11-09:
    * uses QgsTaskManager for background loading
    * own QgsMapLayerStore to not mix-up with (main) QGIS layers
    * fixed bugs related to changes in QGIS API

2018-06-20 (version 0.7):
    * Visualization of images with stacked temporal information (each band = one observation date)
    * some bugfixes

2018-06-12:
    * Speclib I/O as CSV or ENVI-Spectral Library + CSV table for attributes
    * temporary VRTs now created in-memory (gdal VSI mechanism) instead in a disk temp path
    * Spectral Library: profile coordinate now in center of map pixel (issue #66)
    * Save map canvas to clipboard
    * Width of plot lines now scale-independent (issue #64, QPen.setCosmetic(True))
    * adding fields to spectral library (issue #61)

2018-06-04 (version 0.6):
    SpectralLibrary Module
        * now based on in-memory QgsVectorLayer
        * Locations and values of spectral profile can be exported as vector data set
        * Locations of spectral profiles can be rendered on MapCanvases

    Temporal Profile Module
        * now based on in-memory QgsVectorLayer
        * Locations of temporal profiles can be exported as vector data set
        * Band values of temporal profiles can be exported as CSV file
        * Locations of temporal profiles can be rendered on MapCanvases

2018-04-17 (version 0.5):
    * ported to QGIS 3, Qt5 and Python 3.6
    * improvements in temporal profile visualization
    * removed several bug
    * visibility of vector and raster layers can be toggled per map view
    * improved interaction between QGIS and EOTSV (Buttons to import/export spatial extent of map canvas or center)

2018-03-29:
    * improved definition of individual 2D / 3D charts per sensor & pixel-location
    * added based OpenGL based 3D plot features (axis, grids, labels)
    * changed name to "EO Time Series Viewer" (EOTSV)

2018-02-11:
    * merged updates to temporal profile visualization, e.g.
      save temporal profiles, compare 2D profiles between different location, experimental 3D visualization

2018-01-31:
    * added file filters for OpenFileDialog

2018-01-19:
    * initialized Sphinx-based documentation
    * improved map visualization + map settings

2017-05-21:
    * many changes, done in development branch "develop",
    * e.g: QGIS MapCanvases for interactive maps, temporal profiles, ...

2017-02-14:
    * first setup for test users in the recent development branch

