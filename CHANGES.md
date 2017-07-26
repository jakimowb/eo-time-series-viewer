## Known issues ##

- changing the coordinate reference system to one that is obviously not suited for the data might cause system crashes

## Change History ##
## July 2017
- Sensor/Product names are now stored in system settings and will be restored after restart
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
