# README #

The SenseCarbon Time Series Viewer is a small improvised viewer for remote sensing time series data.

![Screenshot](Screenshot.png "Screenshot SenseCarbon Time Series Viewer")


### Features ###

+ uses the python packages shipped with standard QGIS installation
+ reads all image formats supported by gdal (www.gdal.org)
+ the spatial extend shown as image chip for each time series observation can be defined via QGIS 
+ tbd.


### How do I get this plugin? ###

## Windows ##

1. Clone this repository to your local QGIS Python Plugin Folder

        cd %USERPROFILE%\.qgis2\python\plugins 
        git clone https://jakimowb@bitbucket.org/jakimowb/sensecarbontsviewer.git

2. Start QGIS, go to Plugins -> Manage and Install and enable the "SenseCarbon TSV" Plugin
3. Download updates if available

        cd %USERPROFILE%\.qgis2\python\plugins\sensecarbontsviewer
        git rebase origin/master 


### Contribution guidelines ###

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.
 


### Who do I talk to? ###

Comments, bug, hints etc. are welcome in the [issue section](https://bitbucket.org/jakimowb/sensecarbontsviewer/issues)
or via [benjamin.jakimow@geo.hu-berlin.de](benjamin.jakimow@geo.hu-berlin.de).



