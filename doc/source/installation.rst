
.. |icon| image:: img/logo.png
   :width: 30px
   :height: 30px


============
Installation
============


.. warning:: EO Time Series Viewer requires QGIS Version 3.0 +

.. note:: If you have not installed QGIS yet, you can get it `here <https://www.qgis.org/en/site/forusers/download.html>`_.



Windows
-------

.. tip:: On windows we recommend to use the **OSGeo4W Network Installer**!

Standard QGIS 3 Plugin Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Download the most recent zip archive of the EO Time Series Viewer QGIS Plugin from https://bitbucket.org/jakimowb/eo-time-series-viewer/downloads

2. Start QGIS 3 and open *Plugins* > *Manage and Install Plugins* > *Install from ZIP*.

3. Select the downloaded *timeseriesviewerplugin.0.5.YYYYMMDDTHHMM.QGIS3.zip* and start *Install plugin*.

4. Start the EO Time Series Viewer via the |icon| icon. In case of missing requirements you should see an error message. Please install the requested packages.

Developers
~~~~~~~~~~

You really want to use `git <https://en.wikipedia.org/wiki/Git_%28software%29>`_ to install and update the viewer.

If git is not available in your shell, you can download it from `<https://git-scm.com/downloads>`_. You can install git without admin rights.

Larger binary files, e.g. for exemplary data, are distributed via the Git Large File Storage (lfs) extension `<https://git-lfs.github.com>`_.


1. Open your shell and clone the repository into a local QGIS Python Plugin Folder::

        cd %USERPROFILE%\.qgis2\python\plugins
        git clone https://bitbucket.org/jakimowb/hub-timeseriesviewer.git

2. Checkout the development branch (this might change with the fist stable master version)::

        git checkout development
        git lfs checkout


.. todo:: add detailed description hot to setup an IDE to run the EO Time Series Viewer without QGIS