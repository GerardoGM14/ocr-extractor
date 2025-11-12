"""
API Server - Script de inicio para el servidor FastAPI
Ejecutar: python api_server.py
"""

import sys
import os
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from src.api.main import app

if __name__ == "__main__":
    print("=" * 60)
    print("ExtractorOCR API Server")
    print("=" * 60)
    print("\nServidor iniciando...")
    print("Documentación disponible en: http://localhost:8000/docs")
    print("API disponible en: http://localhost:8000/api/v1/")
    print("\nPresiona Ctrl+C para detener el servidor\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

