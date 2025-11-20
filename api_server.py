"""
API Server - Script de inicio para el servidor FastAPI
Ejecutar: python api_server.py
"""

import sys
import os
import json
import asyncio
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Configurar asyncio para Windows (evita errores de ProactorEventLoop)
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from src.api.main import app

def load_config():
    """Carga la configuración desde config.json"""
    config_path = Path("config/config.json")
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def get_ssl_config():
    """Obtiene la configuración SSL desde config.json"""
    config = load_config()
    api_config = config.get("api", {})
    ssl_config = api_config.get("ssl", {})
    
    if not ssl_config.get("enabled", False):
        return None, None
    
    cert_file = ssl_config.get("cert_file", "ssl_certs/cert.pem")
    key_file = ssl_config.get("key_file", "ssl_certs/key.pem")
    
    cert_path = Path(cert_file)
    key_path = Path(key_file)
    
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)
    
    return None, None

if __name__ == "__main__":
    print("=" * 60)
    print("ExtractorOCR API Server")
    print("=" * 60)
    
    # Verificar configuración SSL
    cert_path, key_path = get_ssl_config()
    use_https = cert_path and key_path
    
    if use_https:
        print("\nServidor iniciando con HTTPS...")
        print("Documentación disponible en: https://localhost:8000/docs")
        print("API disponible en: https://localhost:8000/api/v1/")
        print(f"Certificado SSL: {cert_path}")
    else:
        print("\nServidor iniciando con HTTP...")
        print("Documentación disponible en: http://localhost:8000/docs")
        print("API disponible en: http://localhost:8000/api/v1/")
        print("\nNOTA: Para habilitar HTTPS, configura 'api.ssl.enabled: true' en config.json")
        print("      y coloca los certificados en las rutas especificadas.")
    
    print("\nPresiona Ctrl+C para detener el servidor\n")
    
    # Configurar uvicorn
    uvicorn_config = {
        "app": app,
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": "info",
        "access_log": True,
        "timeout_keep_alive": 5
    }
    
    if use_https:
        uvicorn_config["ssl_keyfile"] = key_path
        uvicorn_config["ssl_certfile"] = cert_path
    
    try:
        uvicorn.run(**uvicorn_config)
    except KeyboardInterrupt:
        print("\n\nServidor detenido por el usuario.")
        # Dar tiempo para cerrar conexiones
        import time
        time.sleep(0.5)
    except Exception as e:
        print(f"\n\nError al iniciar el servidor: {e}")
        import traceback
        traceback.print_exc()

