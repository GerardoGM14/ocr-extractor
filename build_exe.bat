@echo off
REM Script para construir el ejecutable .exe del procesador batch
REM Genera un .exe standalone que puede ejecutarse en cualquier PC

echo ========================================
echo Construyendo ExtractorOCR Batch .exe
echo ========================================
echo.

cd /d %~dp0

REM Activar entorno virtual
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] No se encuentra el entorno virtual.
    echo Por favor, ejecuta primero: python -m venv venv
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Verificar que PyInstaller esté instalado
echo Verificando PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Instalando PyInstaller...
    pip install pyinstaller
)

REM Crear carpeta de salida si no existe
if not exist "dist" mkdir dist
if not exist "build" mkdir build

echo.
echo Compilando ejecutable...
echo.

REM Construir el .exe usando el archivo .spec (más confiable)
pyinstaller ExtractorOCR_Batch.spec

REM Si prefieres usar comandos directos, descomenta esto y comenta la línea anterior:
REM pyinstaller --onefile ^
REM     --name "ExtractorOCR_Batch" ^
REM     --console ^
REM     --add-data "src;src" ^
REM     --hidden-import google.generativeai ^
REM     --hidden-import PIL ^
REM     --hidden-import fitz ^
REM     --hidden-import google.api_core ^
REM     --hidden-import google.generativeai.types ^
REM     --hidden-import pymupdf ^
REM     --collect-all google.generativeai ^
REM     --collect-all PIL ^
REM     --collect-all fitz ^
REM     batch_entry.py

if errorlevel 1 (
    echo.
    echo [ERROR] Error al construir el .exe
    pause
    exit /b 1
)

echo.
echo ========================================
echo ¡Compilación exitosa!
echo ========================================
echo.
echo El ejecutable se encuentra en: dist\ExtractorOCR_Batch.exe
echo.
echo IMPORTANTE: Para usar el .exe en otra PC, necesitas copiar:
echo   1. dist\ExtractorOCR_Batch.exe
echo   2. La carpeta 'config' completa (con config.json y gemini_config.json)
echo   3. Crear las carpetas necesarias según config.json
echo.
pause

