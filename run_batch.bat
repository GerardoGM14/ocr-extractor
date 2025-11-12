@echo off
REM Script para ejecutar ExtractorOCR en modo batch (automático)
REM Este script procesa TODAS las páginas de todos los PDFs automáticamente
REM leyendo la configuración del archivo config/config.json

cd /d %~dp0
call venv\Scripts\activate.bat
python main.py --batch
pause

