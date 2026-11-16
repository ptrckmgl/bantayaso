@echo off
rem Live test with the backup model v3 (models\yolo26n_v3.pt). Press q in the video window to stop.
rem   bat\webcam_v3                                         laptop webcam
rem   bat\webcam_v3 --source http://PHONE-IP:8080/video     phone running the IP Webcam app (same Wi-Fi)
rem   bat\webcam_v3 --conf 0.25                             extra options are passed on to 07_detect_stream.py
rem   (--suppress-dog-in-person 0.6 is on: dog boxes mostly inside a person box, or under a person's head, are ignored)
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\07_detect_stream.py --source 0 --show --heartbeat 5 --weights models\yolo26n_v3.pt --conf 0.35 --person-conf 0.20 --person-memory 2 --stray-confirm 3 --suppress-dog-in-person 0.6 --out results\v3\events_webcam.jsonl %*
