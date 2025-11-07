@echo off
setlocal
set "ROOT=%~dp0.."
set SUBMODULE=eotimeseriesviewer/qgispluginsupport
echo "Update $SUBMODULE"
cd /d %ROOT%\%SUBMODULE%
git checkout enmapbox_3.17
git fetch
git pull
cd /d %ROOT%
git add %SUBMODULE%
echo 'Submodule status:'
git submodule status %SUBMODULE%