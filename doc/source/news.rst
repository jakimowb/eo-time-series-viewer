====
News
====


2019-05-31:

    * increased version to 1.2
    * Added menu option to export all maps as image files.

2019-05-24

    * increased version to 1.1
    * dates of visible map canvases are highlighted in the time series tree

2019-05-15:

    * Major update: released version 1.0 with many new features:
    * labeling tools to modify vector layers.
    * quick labeling for time-labels information
    * synchronization with QGIS Map canvas center
    * SpectralLibrary can import SpectralProfiles from a raster image based on vector positions
    * simplified MapView control dock, each MapView has it's own layer tree.
    * improved MapTool organization
    * removed PyQtGraph from list of required external python packages, no need to run a pip installation first

2019-03-01:

    * increased version to 0.8
    * several bug fixes
    * ready for QGIS 3.6 (at least for windows versions)


2018-06-04:
    * increased version to 0.6
    * SpectralLibrary Module

        - now based on in-memory QgsVectorLayer
        - Locations and values of spectral profile can be exported as vector data set
        - Locations of spectral profiles can be rendered on MapCanvases

    * Temporal Profile Module

        - now based on in-memory QgsVectorLayer
        - Locations of temporal profiles can be exported as vector data set
        - Band values of temporal profiles can be exported as CSV file
        - Locations of temporal profiles can be rendered on MapCanvases
    * several bug fixes

2018-04-17:
    * Increased version to 0.5, ported to QGIS 3, Qt5 and Python 3.6.
    * Improvements in temporal profile visualization.
    * Removed several bugs.
    * Visibility of vector and raster layers can be toggled per map view.
    * Improved interaction between QGIS and EOTSV (Buttons to import/export spatial extent of map canvas or center)

**2018-03-29:** Improved definition of individual 2D / 3D charts per sensor & pixel-location added based OpenGL based 3D
plot features (axis, grids, labels) changed name to "EO Time Series Viewer" (EOTSV)

**2018-02-11:** Merged updates to temporal profile visualization, e.g. save temporal profiles, compare 2D profiles between
different location, experimental 3D visualization.

**2018-01-19:** Re-written dialog to configure map visualizations ("Map Views"), Vector & Raster layers can be hidden.
Initialized Sphinx-based documentation.

**2017-06-27:** `Poster <https://bitbucket.org/jakimowb/eo-time-series-viewer/downloads/Jakimow.et.al.TimeSeriesViewer.pdf>`_ & demonstration at `Multitemp 2017, Brugges, Belgium <https://multitemp2017.vito.be>`_.

**2017-05-21:** many changes, done in development branch "develop", e.g. QGIS MapCanvases for interactive maps, temporal profiles and more.

**2017-02-14:** first setup for test users in the recent development branch qgis_apo

**2016-12-02:** Work on this project continued. During the last months I focused on the `EnMAP-Box <https://bitbucket.org/hu-geomatics/enmap-box>`_ where I gained a lot of experience in using Qt and QGIS API.