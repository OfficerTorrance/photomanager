@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
 set "PYCMD=py -3"
) else (
 set "PYCMD=python"
)
%PYCMD% -c "import PIL, pillow_heif" >nul 2>&1
if errorlevel 1 (
 echo Installing required Python packages...
 %PYCMD% -m pip install -r requirements.txt
 if errorlevel 1 (
  echo Installation failed. Please check Python and your internet connection.
  pause
  exit /b 1
 )
)
%PYCMD% PhotoManager.py
if errorlevel 1 pause
