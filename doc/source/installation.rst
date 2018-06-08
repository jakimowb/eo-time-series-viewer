
.. |icon| image:: img/logo.png
   :width: 30px
   :height: 30px


============
Installation
============


.. note:: * The EO TSV plugin requires QGIS Version 3.0 or higher
          * You can get QGIS `here <https://www.qgis.org/en/site/forusers/download.html>`_

.. important:: :ref:`Additional python packages <Additional python dependencies>` are needed and some of them are not delivered with the
               standard QGIS python environment, hence they have to be installed. Follow platform-specific advices below.


Standard QGIS 3 Plugin Installation
-----------------------------------

1. Download the most recent zip archive of the EO Time Series Viewer QGIS Plugin from https://bitbucket.org/jakimowb/eo-time-series-viewer/downloads

2. Start QGIS 3 and open *Plugins* > *Manage and Install Plugins* > *Install from ZIP*.

3. Select the downloaded *timeseriesviewerplugin.0.5.YYYYMMDDTHHMM.QGIS3.zip* and start *Install plugin*.

4. Start the EO Time Series Viewer via the |icon| icon. In case of missing requirements you should see an error message. Please :ref:`install <Additional python dependencies>` the requested packages.

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

Additional python dependencies
------------------------------

The EO Time Series Viewer requires the following packages:

    * pyqtgraph
    * pyopengl



On **Windows**, open the *OSGeo4W Shell* and install the packages via pip:

.. code-block:: shell

    call py3_env.bat
    python3 -m pip install pyqtgraph
    python3 -m pip install pyopengl

On **Linux** or **Mac** you should be able to use the same commands in the terminal, as long as `pip <https://pip.pypa.io/en/stable/installing/>`_
is available, i.e.

.. code-block:: shell

    python3 -m pip install pyqtgraph
    python3 -m pip install pyopengl

....

In case pip is not available in the OSGeo4W Shell, enter

    .. code-block:: batch

        setup

   in the shell, which will start the OSGeo4W installer. Then navigate through

   :menuselection:`Advanced Installation --> Installation from Internet --> default OSGeo4W root directory --> local temp directory --> direct connection --> Select downloadsite --> http://download.osgeo.ogr`


    Now use the textbox to filter, select and finally install the following package:

    .. code-block:: batch

                  python-pip