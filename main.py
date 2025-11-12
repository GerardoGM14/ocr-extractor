"""
ExtractorOCR v1.0 - Sistema de extraccion de datos de PDFs
Author: Soporte
Date: Octubre 2025

Modos de ejecución:
- Sin argumentos: Abre la GUI (modo interactivo)
- --batch o --auto: Ejecuta procesamiento automático leyendo config.json
"""

import sys
import os
import argparse
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def main():
    """Punto de entrada principal de la aplicación."""
    parser = argparse.ArgumentParser(
        description="ExtractorOCR v1.0 - Sistema de extracción de datos de PDFs con Gemini Vision API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python main.py                    # Ejecuta la GUI
  python main.py --batch            # Procesamiento automático (todas las páginas)
  python main.py --auto             # Procesamiento automático (todas las páginas)
  python main.py --batch --config config/config.json  # Con archivo de configuración personalizado
        """
    )
    
    parser.add_argument(
        '--batch', '--auto',
        dest='batch_mode',
        action='store_true',
        help='Ejecuta procesamiento automático leyendo las rutas del archivo config.json. Procesa TODAS las páginas automáticamente.'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/config.json',
        help='Ruta al archivo de configuración JSON (por defecto: config/config.json)'
    )
    
    args = parser.parse_args()
    
    # Modo batch/automático
    if args.batch_mode:
        try:
            from src.core.batch_processor import run_batch_processing
            
            print("Modo: Procesamiento Automático (Batch)")
            print("-" * 60)
            
            success = run_batch_processing(args.config)
            sys.exit(0 if success else 1)
            
        except KeyboardInterrupt:
            print("\n\nProcesamiento interrumpido por el usuario.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] Error en modo batch: {e}")
            sys.exit(1)
    
    # Modo GUI (por defecto)
    else:
        print("ExtractorOCR v1.0")
        print("Sistema de extraccion de datos de PDFs con Gemini Vision API")
        print("-" * 60)
        print("\nIniciando aplicacion en modo GUI...\n")
        
        try:
            from src.gui.main_window import MainWindow
            app = MainWindow()
            app.run()
        except KeyboardInterrupt:
            print("\nAplicación cerrada por el usuario.")
        except Exception as e:
            print(f"Error iniciando aplicacion: {e}")
            print("Cerrando aplicacion...")
            sys.exit(1)


if __name__ == "__main__":
    main()

