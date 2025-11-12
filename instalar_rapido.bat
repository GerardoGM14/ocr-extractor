@echo off
echo =====================================
echo Instalando ExtractorOCR v1.0
echo =====================================
echo.

REM Verificar si venv existe
if exist venv (
    echo OK: Entorno virtual encontrado
    echo.
) else (
    echo Creando entorno virtual...
    python -m venv venv
    echo.
)

echo Instalando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo =====================================
echo Instalacion completada!
echo =====================================
echo.
echo Ejecuta: .\run.bat
echo.
pause

