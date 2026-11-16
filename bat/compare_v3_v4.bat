@echo off
rem Side-by-side: v3 (left) vs v4 (right) on the same frames. Press q in the video window to stop.
rem   bat\compare_v3_v4                                         laptop webcam
rem   bat\compare_v3_v4 --source clip.mp4                       a video file (also saved to results\compare\)
rem   bat\compare_v3_v4 --source http://PHONE-IP:8080/video     phone running the IP Webcam app
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\compare_side_by_side.py --show --source 0 --a models\yolo26n_v3.pt --b models\yolo26n_v4.pt %*
