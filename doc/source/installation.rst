
.. |icon| image:: img/logo.png
   :width: 30px
   :height: 30px


============
Installation
============


.. note:: EO Time Series Viewer requires QGIS Version 3.0 +

.. note:: If you have not installed QGIS yet, you can get it `here <https://www.qgis.org/en/site/forusers/download.html>`_.


Standard QGIS 3 Plugin Installation
-----------------------------------

1. Download the most recent zip archive of the EO Time Series Viewer QGIS Plugin from https://bitbucket.org/jakimowb/eo-time-series-viewer/downloads

2. Start QGIS 3 and open *Plugins* > *Manage and Install Plugins* > *Install from ZIP*.

3. Select the downloaded *timeseriesviewerplugin.0.5.YYYYMMDDTHHMM.QGIS3.zip* and start *Install plugin*.

4. Start the EO Time Series Viewer via the |icon| icon. In case of missing requirements you should see an error message. Please install the requested packages.

Developers
----------

1. Please follow http://enmap-box.readthedocs.io/en/latest/dev_section/dev_installation.html to set up your IDE for developing a QGIS python application and ensure that git and git-lfs is installed.

2. Clone the eo-time-series-viewer repository and checkout the development branch::

        git clone https://bitbucket.org/jakimowb/eo-time-series-viewer.git
        git checkout develop
        git lfs checkout

3. Make the repository *eo-time-series-viewer* folder accessible to your python project

4. Call *timeseriesviewer/main.py* or the folliwing code to start the EO Time Series Viewer::

    from timeseriesviewer.utils import initQgisApplication
    qgsApp = initQgisApplication()
    ts = TimeSeriesViewer(None)
    ts.run()
    qgsApp.exec_()
    qgsApp.exitQgis()



.. todo:: add detailed description hot to setup an IDE to run the EO Time Series Viewer without QGIS