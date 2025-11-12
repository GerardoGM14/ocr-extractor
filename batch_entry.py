"""
Punto de entrada para el ejecutable .exe en modo batch
Este archivo se empaqueta en el .exe y busca config.json en la misma carpeta
"""

import sys
import os
import time
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Determinar la carpeta del ejecutable
if getattr(sys, 'frozen', False):
    # Si está empaquetado como .exe
    EXE_DIR = Path(sys.executable).parent
else:
    # Si se ejecuta como script Python
    EXE_DIR = Path(__file__).parent

# Agregar src al path
# Cuando está empaquetado, PyInstaller maneja los imports automáticamente
# Pero necesitamos agregar la ruta si ejecutamos como script
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(EXE_DIR / "src"))
else:
    # Cuando está empaquetado, PyInstaller crea una carpeta temporal
    # y los módulos están disponibles directamente
    sys.path.insert(0, str(EXE_DIR))

# Buscar config.json en la misma carpeta del .exe
CONFIG_PATH = EXE_DIR / "config" / "config.json"


def _countdown_and_exit(seconds: int, exit_code: int = 0):
    """
    Muestra un conteo regresivo y cierra la aplicación.
    
    Args:
        seconds: Segundos a esperar antes de cerrar
        exit_code: Código de salida
    """
    print(f"\nCerrando en {seconds} segundos...", end="", flush=True)
    for i in range(seconds, 0, -1):
        time.sleep(1)
        print(f"\rCerrando en {i} segundos...", end="", flush=True)
    print("\rCerrando...                                    ")
    sys.exit(exit_code)


def main():
    """Punto de entrada para el .exe en modo batch."""
    print("=" * 60)
    print("ExtractorOCR v1.0 - Procesamiento Automático")
    print("=" * 60)
    
    # Verificar que existe config.json
    if not CONFIG_PATH.exists():
        print(f"\n[ERROR] No se encontró el archivo de configuración:")
        print(f"  {CONFIG_PATH}")
        print(f"\nPor favor, asegúrate de que existe 'config/config.json' en la misma")
        print(f"carpeta donde está este ejecutable.\n")
        _countdown_and_exit(5, exit_code=1)
    
    # Verificar que existe gemini_config.json
    GEMINI_CONFIG_PATH = EXE_DIR / "config" / "gemini_config.json"
    if not GEMINI_CONFIG_PATH.exists():
        print(f"\n[ERROR] No se encontró el archivo de configuración de Gemini:")
        print(f"  {GEMINI_CONFIG_PATH}")
        print(f"\nPor favor, asegúrate de que existe 'config/gemini_config.json'.\n")
        _countdown_and_exit(5, exit_code=1)
    
    try:
        # Configurar variable de entorno para que BatchProcessor use la ruta correcta
        import os
        os.environ['EXTRACTOR_GEMINI_CONFIG_PATH'] = str(GEMINI_CONFIG_PATH)
        
        from src.core.batch_processor import run_batch_processing
        
        # Ejecutar procesamiento batch
        success = run_batch_processing(str(CONFIG_PATH))
        
        if not success:
            print("\n[ERROR] El procesamiento tuvo errores.")
            _countdown_and_exit(5, exit_code=1)
        
        print("\n¡Procesamiento completado exitosamente!")
        _countdown_and_exit(5, exit_code=0)
        
    except KeyboardInterrupt:
        print("\n\n[INTERRUMPIDO] Procesamiento cancelado por el usuario.")
        _countdown_and_exit(5, exit_code=1)
    except Exception as e:
        print(f"\n[ERROR] Error en procesamiento: {e}")
        import traceback
        traceback.print_exc()
        _countdown_and_exit(5, exit_code=1)


if __name__ == "__main__":
    main()

