@echo off
REM Script para ejecutar ExtractorOCR con el entorno virtual (modo GUI)
REM Para ejecutar en modo batch automático, usa: run_batch.bat
cd /d %~dp0
call venv\Scripts\activate.bat
python main.py

