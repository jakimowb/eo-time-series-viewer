## Known issues ##

- changing the map coordinate reference system (CRS) to one that is obviously not suited for
the data might cause system crashes


## Change History ##
### November 2017
- Map Visualization
    - re-design of Map View Settings pane, which now has a vertical layout
    - map views can be named with own titles, like "True Color" and "Short Wave Infrared"
    - added "identify map view" button, which will highlight the respective map canvas for 1 second


### August 2017
- Temporal Profile Visualization:
    - sensor/product plot settings like the band/spectral index, plot symbol and colors are restored after restart
    - profile loading speed increased by loading required bands only
    - profile values are loaded in a parallel process

### July 2017
- Map Visualization: progress bars indicate if map data is loaded in background
- Sensor/product names are restored after restart
- Pixel profiles are now loaded in a parallel process that will not block the UI (required because of python GIL.)


### June 2017
- improved QGIS-TimeSeriesViewer integration
- synchronizes map extent or map center, either from QGIS to TSV or the other direction
- TSV can overlay a vector layer that is opened in QGIS on top of TSV maps. Renderstyle is the same as in QGIS.
- fixed several bugs


### May 2017
- crosshairs
- temporal pixel profiles with sensor-specific scaling and visualization

### December 2016###
- handling of VRT without memory leakage (VRT_SHARED_SOURCE = 0)
- test data (Landsat + RapidEye)
- refactoring of GUI and class names

### June 2015 ###
- extraction of image chips for AOI selected in QGIS
- gdal based IO
