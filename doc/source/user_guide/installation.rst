.. _installation:

============
Installation
============


.. important:: The EO Time Series Viewer plugin requires
               `QGIS >= 3.38 < 4 <https://www.qgis.org/download/>`_,
               GDAL >= 3.10, and Python >= 3.10

Install QGIS & Python Dependencies
=====================================


.. tabs::

   .. group-tab:: Windows

      1. Download and install the `OSGeo4W Network Installer <https://qgis.org/download/>`_

      2. Use the OSGeo4W installer to install:

        * the latest QGIS relase (LR, `qgis`) or QGIS long term release (LTR, `qgis-ltr`)
        * the `python3-pip` package

       .. figure:: /img/installation_osgeo4w.gif

        OSGeo4W Network Installer

      The OSGeo4W neotwork installer can be used to update QGIS and have
      different QGIS releases installed in parallel.

      3. If python-packages are missing:
        *  try installing them using the OSGeo4W installer first.
        *  If unavailable in the OSGeo4W installer, install them by running ``pip install <package>`` from the
           OSGeo4W shell

   .. group-tab:: Linux

     QGIS installation guides for different Linux distribitions can be found at
     https://qgis.org/resources/installation-guide/#debian--ubuntu.

     Some standard repositories, e.g. that for Ubuntu, are known to deliver outdated QGIS versions.
     Therefore it is recommended to install QGIS using Flatpak (https://flathub.org/en/apps/org.qgis.qgis),
     conda (see *Conda* tab) or docker (see *Docker* tab).


   .. group-tab:: MacOS

      .. note::

         As of June 2025, official *QGIS installers for macOS are currently outdated and do not reflect
         the latest QGIS versions* (see https://qgis.org/download/).

         For macOS it is recommended to install QGIS and all python dependencies either using
         conda (see *Conda* tab) or docker (see *Docker* tab).

   .. group-tab:: Conda

      .. _usr_installation_qgis_conda:

      Conda is a cross-platform package manager that allows to install software in separated environments.
      We recommend to install conda using `Miniforge <https://conda-forge.org/download>`_,
      a minimal installer which by default installs conda packages from the `conda-forge <https://conda-forge.org/>`_ channel.

      1. Install conda

        a) Linux / Unix / MacOS

           .. code-block:: bash

             # download install script
             curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"

             # run install script
             sh Miniforge3-$(uname)-$(uname -m).sh

        b) Windows

           Download and run the miniforge installer from
           https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe

      2. Install QGIS + Python dependencies

        Open a terminal with conda available and install a new python environment with
        QGIS and all required python packages:

        .. code-block:: bash

          conda install -n eotsv -f=https://raw.githubusercontent.com/jakimowb/eo-time-series-viewer/refs/heads/main/.conda/eotsv.yml


        Now activate the environment and start QGIS

        .. code-block:: bash

             conda activate eotsv
             qgis

   .. group-tab:: Docker

        1. Pull a QGIS image, e.g., `qgis/qgis:stable <https://hub.docker.com/layers/qgis/qgis/stable>`_

          .. code-block:: bash

            docker pull qgis/qgis:stable


        2. Download the QGIS start script created by David Frantz from https://github.com/davidfrantz/startup/blob/main/bash/qgis.sh
           into a local folder and allow executing it

          .. code-block:: bash

            cd ~
            wget https://raw.githubusercontent.com/davidfrantz/startup/refs/heads/main/bash/qgis.sh
            chmod +x qgis.sh

        3. Call the script to run QGIS from docker

          .. code-block:: bash

            ./qgis.sh -v stable




Install the EO Time Series Viewer plugin
===========================================


#. Open QGIS
#. In the menu bar go to :menuselection:`Plugins --> Manage and Install Plugins...`
#. Switch to the **All** tab and search for ``EO Time Series Viewer``
#. Click on :guilabel:`Install Plugin` to start the installation
#. Start the EO Time Series Viewer via the |icon| icon or from the menu bar :menuselection:`Raster --> EO Time Series Viewer`


   .. figure:: /img/installation_plugin.gif

        Installing the EO Time Series Viewer plugin

Developers
==========


1. Clone the eo-time-series-viewer repository and ensure that all submodules are checkout:

 .. code-block:: bash

    git clone --recurse-submodules git@github.com:jakimowb/eo-time-series-viewer.git
    cd eo-time-series-viewer
    git submodule update --init --recursive

2. Ensure that your python has the QGIS API available. You can use the the
   eotsv.yml conda environment to install QGIS and other required python packages:

 .. code-block:: bash

    conda env create -n eotsv --file=.conda/eotsv.yml
    conda activate eotsv

3. Run scripts/setup_repository.py to download and create qt resource files.

   This ensures icons to become visible even if the EOTSV is started from
   python instead of the QGIS GUI.

4. Call *timeseriesviewer/__main__.py* to start the EOTSV from python

 .. code-block:: bash

    python eotimeseriesviewer/__main__.py


 .. figure:: /img/installation_repo_main_gui.png

        The EOTSV GUI, as started from a python shell

.. AUTOGENERATED SUBSTITUTIONS - DO NOT EDIT PAST THIS LINE

.. |icon| image:: /icons/icon.png
   :width: 28px
