@echo off
REM Script de prueba para el sistema de aprendizaje
REM Ejecutar después de iniciar la API

echo ========================================
echo Test Sistema de Aprendizaje - API
echo ========================================
echo.

set API_URL=http://localhost:8000

echo [1/4] Verificando que la API esté corriendo...
curl -s %API_URL%/health > nul
if errorlevel 1 (
    echo [ERROR] La API no está corriendo. Ejecuta: run_api.bat
    pause
    exit /b 1
)
echo [OK] API está corriendo
echo.

echo [2/4] Ver resumen de errores...
echo GET %API_URL%/api/v1/learning/errors/summary
curl -s %API_URL%/api/v1/learning/errors/summary
echo.
echo.

echo [3/4] Analizar errores (esto puede tardar unos segundos)...
echo POST %API_URL%/api/v1/learning/analyze?limit=20
curl -s -X POST "%API_URL%/api/v1/learning/analyze?limit=20"
echo.
echo.

echo [4/4] Ver sugerencias generadas...
echo GET %API_URL%/api/v1/learning/suggestions
curl -s %API_URL%/api/v1/learning/suggestions
echo.
echo.

echo ========================================
echo Test completado
echo ========================================
echo.
echo Para ver más detalles, abre en el navegador:
echo %API_URL%/docs
echo.
pause

