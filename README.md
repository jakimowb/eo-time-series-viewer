# README #

The SenseCarbon Time Series Viewer is a graphical user interface to visualize time series (TS) of remote sensing data.
Major aims are 

(i) to support a [Quantum GIS (QGIS)](www.qgis.org) based labeling of TS data, 

(ii) to use remote sensing data "as is" and 

(iii) to avoid a complicated installation process.


The viewer requires runs with python packages that are also part of a standard [Quantum GIS (QGIS)](www.qgis.org) installation. Basically only [PyQt](https://riverbankcomputing.com/software/pyqt/download) is required additionally to the standard python libraries.

![Screenshot](Screenshot.png "Screenshot SenseCarbon Time Series Viewer")

## Installation ##
You really want to use [git](https://en.wikipedia.org/wiki/Git_%28software%29) to install and update the viewer. 

If git is not available in your shell, you can download it from [https://git-scm.com/downloads](https://git-scm.com/downloads). You can install git without admin rights.


### Windows ###

1. Open your command line and clone this repository to your local QGIS Python Plugin Folder

        cd %USERPROFILE%\.qgis2\python\plugins 
        git clone https://jakimowb@bitbucket.org/jakimowb/sensecarbontsviewer.git

2. Start QGIS, go to Plugins -> Manage and Install and enable the "SenseCarbon TSV" Plugin
3. Download updates if available

        cd %USERPROFILE%\.qgis2\python\plugins\sensecarbontsviewer
        git pull


## Features ##
+ RS data can be simply added to specify a time series. Observation dates are extracted automatically by evaluating the meta data, file base name or entire file path
+ spatial extends of image chips can be specified in QGIS by selection of single coodinate or rectangle
+ multiple band combination can be used to visualize the time series
+ color scaling is applied to the entire time series, e.g. to visualize and compare surface reflectance data
+ uses python packages shipped with the most-recent standard QGIS installation. I hope this way the SenseCarbon Time Series Viewer runs on different plattforms 
without too many complications.
+ uses the [Geospatial Data Abstraction Library (GDAL)](www.gdal.org) that supports up to 142 [raster image formats](http://www.gdal.org/formats_list.html)  
+ python2 and python 3 interoperability 

## Missing Features / ToDo's ##

Many. 

Your feedback (wishes, comments, bugs, ...) is always welcome. Write it into  the [issue section](https://bitbucket.org/jakimowb/sensecarbontsviewer/issues)
or send me personally to [benjamin.jakimow@geo.hu-berlin.de](benjamin.jakimow@geo.hu-berlin.de).


## Licence and Use ##

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.