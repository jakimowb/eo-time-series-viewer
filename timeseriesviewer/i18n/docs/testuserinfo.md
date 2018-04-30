# Notes for test users of EO Time Series Viewer (TSV)

1.  Ensure that git is installed on your system. If necessary, download it
from [https://git-scm.com/download](https://git-scm.com/download)

    Git is installed, if the command `C:\Windows\system32>git` produces a meaningful output.

2. Create your personal "QGIS_Plugin" folder.

3. Clone this repository into your QGIS_Plugin folder and checkout the qgis_api branch with:

        git clone https://bitbucket.org/jakimowb/hub-timeseriesviewer.git
        cd hub-timeseriesviewer
        git fetch && git checkout develop

    The qgis_api branch source code should now appear within `QGIS_Plugin/hub-timeseriesviewer`.

4. Tell QGIS where to find this folder by adding QGIS_Plugin to the QGIS_PLUGINPATH variable.
Create it variable in case it does not exist.

    Settings > Options ... > System >

    ![Screenshot](img/qgis_pluginpath.png "Screenshot QGIS_PLUGINPATH")

5. Re-start QGIS. Activate the Plugin to add the TSV start button
to the QGIS toolbar.

    ![Screenshot Plugin Activation](img/qgis_plugin_activation.png "Screenshot Plugin Activation")

6. Get updates: switch to your `QGIS_Pluigin/hub-timeseriesviewer` folder and call

        git pull

    to get updates from the remote branch. Dont's forget to restart QGIS afterwards.

