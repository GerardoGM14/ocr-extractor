@echo off
REM Script para ejecutar el servidor API de ExtractorOCR
REM Ejecutar: run_api.bat

echo ========================================
echo ExtractorOCR API Server
echo ========================================
echo.

cd /d %~dp0

REM Activar entorno virtual
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] No se encuentra el entorno virtual.
    echo Por favor, ejecuta primero: python -m venv venv
    echo Y luego: pip install -r requirements.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Verificar que uvicorn esté instalado
python -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo [ERROR] uvicorn no está instalado.
    echo Instalando uvicorn...
    pip install uvicorn[standard]
)

echo.
echo Iniciando servidor API...
echo.
echo Servidor disponible en: http://localhost:8000
echo Documentación disponible en: http://localhost:8000/docs
echo API disponible en: http://localhost:8000/api/v1/
echo.
echo Presiona Ctrl+C para detener el servidor
echo.

REM Ejecutar servidor
python api_server.py

pause

