@echo off
setlocal
if not defined PSIP_QGIS_ROOT set "PSIP_QGIS_ROOT=C:\Program Files\QGIS 3.44.1"
if not exist "%PSIP_QGIS_ROOT%\bin\pythonw.exe" (
  echo Nie znaleziono bibliotek GIS. Ustaw PSIP_QGIS_ROOT na katalog instalacji QGIS.
  pause
  exit /b 1
)
call "%PSIP_QGIS_ROOT%\bin\o4w_env.bat"
set "PATH=%OSGEO4W_ROOT%\apps\qgis\bin;%PATH%"
set "QGIS_PREFIX_PATH=%OSGEO4W_ROOT:\=/%/apps/qgis"
set "QT_PLUGIN_PATH=%OSGEO4W_ROOT%\apps\qgis\qtplugins;%OSGEO4W_ROOT%\apps\qt5\plugins"
set "PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis\python;%PYTHONPATH%"
set "GDAL_FILENAME_IS_UTF8=YES"
if /I "%~1"=="--validate" goto validate
start "QGIS PRO" /MAX "%OSGEO4W_ROOT%\bin\pythonw.exe" "%~dp0app\desktop_main.py"
endlocal
exit /b 0

:validate
"%OSGEO4W_ROOT%\bin\python.exe" "%~dp0app\desktop_main.py" --validate
exit /b %ERRORLEVEL%
