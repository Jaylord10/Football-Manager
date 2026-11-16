@echo off
rem The 3D view of a match (a prototype, separate from the game - the game itself is unchanged).
rem First time, it installs what the 3D view needs (Panda3D), which takes a minute or two.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% -c "import panda3d, gltf, numpy, PIL" >nul 2>nul
if errorlevel 1 (
  echo Installing what the 3D view needs - one time only...
  %PY% -m pip install panda3d panda3d-gltf numpy pillow
)
echo Starting the 3D view...  (space = pause, left / right = back / on 10 seconds, 1 = TV camera, 2 = close camera, Esc = quit)
%PY% broadcast3d\viewer.py 5600 --live > broadcast3d\last_run.log 2>&1
if errorlevel 1 (
  echo.
  echo Something went wrong - tell Claude, the details are saved in broadcast3d\last_run.log
  pause
)
