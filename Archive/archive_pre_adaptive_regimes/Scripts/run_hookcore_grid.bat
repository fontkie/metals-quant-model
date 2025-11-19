@echo off
setlocal
cd /d C:\Code\Metals
call .venv\Scripts\activate
python src\experiments\hookcore_grid_v12.py
endlocal
