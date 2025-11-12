"""
Batch Processor Module - Procesamiento automático sin GUI
Responsabilidad: Procesar PDFs automáticamente leyendo configuración del JSON
Principios: Single Responsibility, Dependency Inversion
"""

import sys
from pathlib import Path
from typing import Optional, Callable
import time

from .file_manager import FileManager
from .ocr_extractor import OCRExtractor
from ..services.gemini_service import GeminiService
from ..services.data_mapper import DataMapper


class BatchProcessor:
    """
    Procesador batch para ejecución automática sin GUI.
    
    Responsabilidades:
    - Leer configuración del JSON
    - Procesar todos los PDFs en la carpeta de entrada
    - Procesar TODAS las páginas de cada PDF
    - Mostrar progreso en consola
    """
    
    def __init__(self, config_path: str = "config/config.json"):
        """
        Inicializa el procesador batch.
        
        Args:
            config_path: Ruta al archivo de configuración JSON
        """
        self.config_path = config_path
        self.file_manager = FileManager(config_path)
        self.gemini_service = None
        self.data_mapper = None
        self.ocr_extractor = None
        
        self._init_services()
    
    def _init_services(self):
        """Inicializa los servicios necesarios."""
        try:
            # Determinar ruta de gemini_config.json (misma carpeta que config.json)
            import os
            from pathlib import Path
            config_dir = Path(self.config_path).parent
            gemini_config_path = config_dir / "gemini_config.json"
            
            # Si existe variable de entorno, usarla (para .exe)
            if 'EXTRACTOR_GEMINI_CONFIG_PATH' in os.environ:
                gemini_config_path = os.environ['EXTRACTOR_GEMINI_CONFIG_PATH']
            
            self.gemini_service = GeminiService(str(gemini_config_path))
            self.data_mapper = DataMapper(self.gemini_service)
            self.ocr_extractor = OCRExtractor(
                self.gemini_service,
                self.data_mapper,
                max_workers=7  # Procesar hasta 7 páginas en paralelo
            )
            
            # Inicializar sistema de learning si está activado (opcional)
            self._init_learning_system()
            
        except Exception as e:
            print(f"[ERROR] No se pudo inicializar los servicios: {e}")
            sys.exit(1)
    
    def _init_learning_system(self):
        """
        Inicializa el sistema de aprendizaje si está activado en la configuración.
        Es completamente opcional y no afecta el funcionamiento si está desactivado.
        """
        try:
            # Verificar si learning está activado en la configuración
            learning_config = self.file_manager.config.get("learning", {})
            learning_enabled = learning_config.get("enabled", False)
            
            if not learning_enabled:
                # Learning desactivado - no hacer nada (comportamiento actual)
                return
            
            # Learning activado - inicializar módulos
            # Determinar carpeta de learning (relativa al proyecto)
            learning_folder = learning_config.get("folder", "learning")
            project_root = Path(self.config_path).parent.parent
            
            # Agregar project_root al path para imports
            import sys
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.learning.error_tracker import ErrorTracker
            from src.learning.prompt_manager import PromptManager
            from src.learning.learning_service import LearningService
            
            # Crear trackers y managers
            self.error_tracker = ErrorTracker(str(project_root / learning_folder))
            self.prompt_manager = PromptManager(
                str(project_root / learning_folder),
                default_prompt=None  # Usará el prompt por defecto del sistema
            )
            self.learning_service = LearningService(
                self.gemini_service,
                str(project_root / learning_folder)
            )
            
            # Conectar a servicios existentes
            self.gemini_service._prompt_manager = self.prompt_manager
            self.ocr_extractor._error_tracker = self.error_tracker
            
            print("[INFO] Sistema de aprendizaje activado")
            print(f"      - Errores se guardarán en: {project_root / learning_folder / 'errors'}")
            print(f"      - Prompts se guardarán en: {project_root / learning_folder / 'prompts'}")
            
        except ImportError as e:
            # Si no se pueden importar los módulos de learning, continuar sin ellos
            print(f"[INFO] Sistema de aprendizaje no disponible: {e}")
            print("      Continuando sin sistema de aprendizaje...")
        except Exception as e:
            # Si hay cualquier otro error, continuar sin learning (no crítico)
            print(f"[INFO] Error al inicializar sistema de aprendizaje: {e}")
            print("      Continuando sin sistema de aprendizaje...")
    
    def _print_progress(self, message: str, percentage: Optional[int] = None):
        """
        Imprime progreso en consola.
        
        Args:
            message: Mensaje a mostrar
            percentage: Porcentaje de progreso (opcional)
        """
        if percentage is not None:
            bar_length = 40
            filled = int(bar_length * percentage / 100)
            bar = "=" * filled + "-" * (bar_length - filled)
            print(f"\r[{bar}] {percentage}% - {message}", end="", flush=True)
        else:
            print(f"  → {message}")
    
    def _process_single_pdf(self, pdf_file: Path, current: int, total: int):
        """
        Procesa un PDF individual.
        
        Args:
            pdf_file: Archivo PDF a procesar
            current: Índice actual (para mostrar progreso)
            total: Total de archivos a procesar
        """
        pdf_name = pdf_file.stem
        
        print(f"\n[{current}/{total}] Procesando: {pdf_name}")
        
        def update_progress(message: str, percentage: Optional[int]):
            """Callback para actualizar progreso."""
            if message:
                self._print_progress(message, percentage)
            
            if percentage is not None:
                # Calcular progreso total considerando archivos anteriores
                base_progress = ((current - 1) / total) * 100
                current_file_progress = (percentage / total)
                total_progress = int(base_progress + current_file_progress)
                self._print_progress(f"{pdf_name} - {message}", total_progress)
        
        start_time = time.time()
        
        try:
            # Procesar TODAS las páginas (max_pages=None)
            results = self.ocr_extractor.process_pdf(
                str(pdf_file),
                progress_callback=update_progress,
                max_pages=None  # Procesar todas las páginas
            )
            
            if results:
                self._print_progress(f"Guardando resultados de: {pdf_name}")
                self.ocr_extractor.save_results(results, pdf_name)
                
                elapsed_time = time.time() - start_time
                print(f"\n  ✓ PDF procesado exitosamente: {pdf_name}")
                print(f"    Páginas procesadas: {len(results)}")
                print(f"    Tiempo: {elapsed_time:.2f} segundos")
            else:
                print(f"\n  ✗ [ERROR] Error procesando: {pdf_name}")
                
        except Exception as e:
            print(f"\n  ✗ [ERROR] Excepción procesando {pdf_name}: {e}")
    
    def process_all(self):
        """
        Procesa todos los PDFs encontrados en la carpeta de entrada.
        
        Returns:
            True si el procesamiento fue exitoso, False si hubo errores
        """
        print("=" * 60)
        print("ExtractorOCR v1.0 - Modo Batch")
        print("=" * 60)
        
        # Validar configuración
        input_folder = self.file_manager.get_input_folder()
        output_folder = self.file_manager.get_output_folder()
        processing_folder = self.file_manager.get_processing_folder()
        
        if not input_folder:
            print("[ERROR] Carpeta de entrada no configurada en config.json")
            return False
        
        if not Path(input_folder).exists():
            print(f"[ERROR] La carpeta de entrada no existe: {input_folder}")
            return False
        
        print(f"\nConfiguración:")
        print(f"  Carpeta de entrada: {input_folder}")
        print(f"  Carpeta de salida: {output_folder}")
        print(f"  Carpeta de procesamiento: {processing_folder}")
        print(f"  Modo: Procesar TODAS las páginas automáticamente\n")
        
        # Listar PDFs
        pdf_files = self.file_manager.list_pdf_files()
        
        if not pdf_files:
            print("[INFO] No se encontraron PDFs para procesar en la carpeta de entrada.")
            return True
        
        total_files = len(pdf_files)
        print(f"Encontrados {total_files} archivo(s) PDF.\n")
        
        # Mostrar lista de archivos a procesar
        print("Archivos a procesar:")
        for idx, pdf_file in enumerate(pdf_files, 1):
            print(f"  {idx}. {pdf_file.name}")
        print()
        
        # Procesar cada PDF
        start_total_time = time.time()
        success_count = 0
        error_count = 0
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            try:
                self._process_single_pdf(pdf_file, idx, total_files)
                success_count += 1
            except KeyboardInterrupt:
                print("\n\n[INTERRUMPIDO] Procesamiento cancelado por el usuario.")
                return False
            except Exception as e:
                print(f"\n  ✗ [ERROR] Error procesando {pdf_file.name}: {e}")
                error_count += 1
        
        # Resumen final
        total_time = time.time() - start_total_time
        print("\n" + "=" * 60)
        print("PROCESAMIENTO COMPLETADO")
        print("=" * 60)
        print(f"Total de archivos: {total_files}")
        print(f"Exitosos: {success_count}")
        print(f"Con errores: {error_count}")
        print(f"Tiempo total: {total_time:.2f} segundos ({total_time/60:.2f} minutos)")
        print("=" * 60)
        
        return error_count == 0


def run_batch_processing(config_path: str = "config/config.json") -> bool:
    """
    Función de conveniencia para ejecutar procesamiento batch.
    
    Args:
        config_path: Ruta al archivo de configuración JSON
        
    Returns:
        True si fue exitoso, False si hubo errores
    """
    processor = BatchProcessor(config_path)
    return processor.process_all()


if __name__ == "__main__":
    # Permite ejecutar directamente: python -m src.core.batch_processor
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/config.json"
    success = run_batch_processing(config_path)
    sys.exit(0 if success else 1)

