.. include:: icon_links.rst

============
Installation
============


.. important:: The EO TSV plugin requires `QGIS Version 3.4 or higher <https://www.qgis.org/en/site/forusers/download.html>`_



QGIS 3 Plugin Installation
--------------------------

#. Open QGIS
#. In the menu bar go to :menuselection:`Plugins --> Manage and Install Plugins...`
#. Switch to the **All** tab and search for ``EO Time Series Viewer``

   .. figure:: img/install_plugin.png



#. Click on :guilabel:`Install Plugin` to start the installation
#. Start the EO Time Series Viewer via the |icon| icon or from the menu bar :menuselection:`Raster --> EO Time Series Viewer`

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

.. todo:: add detailed description how to setup an IDE to run the EO Time Series Viewer without QGIS

