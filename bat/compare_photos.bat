@echo off
rem v3 (left) vs v4 (right) on saved photos. Put pictures in the folder  test_photos  (in the repo root),
rem then double-click this file, or:  bat\compare_photos some\other\folder
rem One side-by-side picture per photo is saved to  results\compare\<folder>_v3_vs_v4\
cd /d "%~dp0.."
if not exist test_photos mkdir test_photos
set SRC=%1
if "%SRC%"=="" set SRC=test_photos
".venv\Scripts\python.exe" scripts\compare_side_by_side.py --source "%SRC%" --a models\yolo26n_v3.pt --b models\yolo26n_v4.pt
echo.
pause
