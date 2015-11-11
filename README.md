# README #

The SenseCarbon Time Series Viewer is a graphical user interface to visualize time series (TS) of remote sensing (RS) data.
Its major aims are (i) to allow for an interactive and GIS based labeling of TS data and (ii) to use the RS data 
"as is" and (iii) to allow for an easy installation on different plattforms using standard python packages shipped with [Quantum GIS (QGIS)](www.qgis.org) only.  



![Screenshot](Screenshot.png "Screenshot SenseCarbon Time Series Viewer")

### Installation ###


## Windows ##

1. Clone this repository to your local QGIS Python Plugin Folder

        cd %USERPROFILE%\.qgis2\python\plugins 
        git clone https://jakimowb@bitbucket.org/jakimowb/sensecarbontsviewer.git

2. Start QGIS, go to Plugins -> Manage and Install and enable the "SenseCarbon TSV" Plugin
3. Download updates if available

        cd %USERPROFILE%\.qgis2\python\plugins\sensecarbontsviewer
        git rebase origin/master 


### Features ###
+ RS data can be simply added to specify a time series. Observation dates are extracted automatically by evaluating the meta data, file base name or entire file path
+ spatial extends of image chips can be specified in QGIS by selection of single coodinate or rectangle
+ multiple band combination can be used to visualize the time series
+ color scaling is applied to the entire time series, e.g. to visualize and compare surface reflectance data
+ 
+ uses python packages shipped with the most-recent standard QGIS installation. I hope this way the SenseCarbon Time Series Viewer runs on different plattforms 
without too many complications.
+ uses the [Geospatial Data Abstraction Library (GDAL)](www.gdal.org) that supports up to 142 [raster image formats](http://www.gdal.org/formats_list.html)  

  
+ python2 and python 3 interoperability 

### Missing Features / ToDo's ###

A lot. 

Your feedback (wishes, comments, bugs, ...) is always welcome. You can add it to the [issue section](https://bitbucket.org/jakimowb/sensecarbontsviewer/issues)
or send me personally via [benjamin.jakimow@geo.hu-berlin.de](benjamin.jakimow@geo.hu-berlin.de).


### Licences and Use ###

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.
 

