@echo off
rem Live test with the v4 model (clean camera-based split, repeated frames thinned, 50 epochs). Press q in the video window to stop.
rem   webcam_v4                                         laptop webcam
rem   webcam_v4 --source http://PHONE-IP:8080/video     phone running the IP Webcam app (same Wi-Fi)
rem   (--suppress-dog-in-person 0.6 is on: dog boxes mostly inside a person box, or under a person's head, are ignored)
rem   webcam_v4 --conf 0.25                            extra options are passed on to 07_detect_stream.py
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\07_detect_stream.py --source 0 --show --heartbeat 5 --weights runs\train\yolo26n_v4\weights\best.pt --conf 0.35 --person-conf 0.20 --person-memory 2 --stray-confirm 3 --suppress-dog-in-person 0.6 --out results\v4\events_webcam.jsonl %*
