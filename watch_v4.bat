@echo off
rem Live progress of the v4 training (refreshes every 5 s). Closing this window does NOT stop training.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File results\v4\watch_training.ps1
