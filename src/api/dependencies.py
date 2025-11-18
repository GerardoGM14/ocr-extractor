"""
API Dependencies - Inyección de dependencias para servicios
Responsabilidad: Inicializar y proporcionar servicios reutilizables
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

from ..services.gemini_service import GeminiService
from ..services.data_mapper import DataMapper
from ..services.database_service import DatabaseService
from ..core.ocr_extractor import OCRExtractor
from ..core.file_manager import FileManager
from .upload_manager import UploadManager
from .archive_manager import ArchiveManager
from .processed_tracker import ProcessedTracker
from .periodo_manager import PeriodoManager

logger = logging.getLogger(__name__)


# Cache global para servicios (singleton)
_service_cache: Optional[dict] = None


def get_gemini_service() -> GeminiService:
    """
    Obtiene instancia de GeminiService (singleton).
    
    Returns:
        Instancia configurada de GeminiService
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "gemini_service" not in _service_cache:
        # Buscar config de Gemini
        config_path = _find_gemini_config()
        _service_cache["gemini_service"] = GeminiService(config_path)
    
    return _service_cache["gemini_service"]


def get_data_mapper() -> DataMapper:
    """
    Obtiene instancia de DataMapper (singleton).
    
    Returns:
        Instancia configurada de DataMapper
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "data_mapper" not in _service_cache:
        gemini_service = get_gemini_service()
        _service_cache["data_mapper"] = DataMapper(gemini_service)
    
    return _service_cache["data_mapper"]


def get_ocr_extractor() -> OCRExtractor:
    """
    Obtiene instancia de OCRExtractor (singleton).
    
    Returns:
        Instancia configurada de OCRExtractor
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "ocr_extractor" not in _service_cache:
        gemini_service = get_gemini_service()
        data_mapper = get_data_mapper()
        # Procesar hasta 7 páginas en paralelo (igual que batch)
        ocr_extractor = OCRExtractor(
            gemini_service,
            data_mapper,
            max_workers=7
        )
        
        # Inicializar sistema de learning si está activado (opcional)
        _init_learning_system_if_enabled(ocr_extractor, gemini_service)
        
        _service_cache["ocr_extractor"] = ocr_extractor
    
    return _service_cache["ocr_extractor"]


def _init_learning_system_if_enabled(ocr_extractor: OCRExtractor, gemini_service: GeminiService):
    """
    Inicializa el sistema de aprendizaje si está activado en la configuración.
    Es completamente opcional y no afecta el funcionamiento si está desactivado.
    """
    try:
        # Buscar configuración
        config_path = _find_config_json()
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Verificar si learning está activado
        learning_config = config.get("learning", {})
        learning_enabled = learning_config.get("enabled", False)
        
        if not learning_enabled:
            # Learning desactivado - no hacer nada
            return
        
        # Learning activado - inicializar módulos
        learning_folder = learning_config.get("folder", "learning")
        project_root = Path(config_path).parent.parent
        
        # Agregar project_root al path para imports
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from src.learning.error_tracker import ErrorTracker
        from src.learning.prompt_manager import PromptManager
        from src.learning.learning_service import LearningService
        
        # Crear trackers y managers
        error_tracker = ErrorTracker(str(project_root / learning_folder))
        prompt_manager = PromptManager(
            str(project_root / learning_folder),
            default_prompt=None
        )
        learning_service = LearningService(
            gemini_service,
            str(project_root / learning_folder)
        )
        
        # Conectar a servicios existentes
        gemini_service._prompt_manager = prompt_manager
        ocr_extractor._error_tracker = error_tracker
        
        logger.info("Sistema de aprendizaje activado en API")
        
    except ImportError:
        # Si no se pueden importar los módulos, continuar sin ellos
        pass
    except Exception:
        # Si hay cualquier error, continuar sin learning (no crítico)
        pass


def get_file_manager() -> FileManager:
    """
    Obtiene instancia de FileManager (singleton).
    
    Returns:
        Instancia configurada de FileManager
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "file_manager" not in _service_cache:
        config_path = _find_config_json()
        _service_cache["file_manager"] = FileManager(config_path)
    
    return _service_cache["file_manager"]


def _find_gemini_config() -> str:
    """
    Busca el archivo de configuración de Gemini.
    
    Returns:
        Ruta al archivo gemini_config.json
    """
    # Buscar en varias ubicaciones posibles
    possible_paths = [
        "config/gemini_config.json",
        "./config/gemini_config.json",
        Path(__file__).parent.parent.parent / "config" / "gemini_config.json"
    ]
    
    for path in possible_paths:
        path_obj = Path(path) if isinstance(path, str) else path
        if path_obj.exists():
            return str(path_obj.resolve())
    
    raise FileNotFoundError(
        "No se encontró gemini_config.json. "
        "Asegúrate de que existe en config/gemini_config.json"
    )


def _find_config_json() -> str:
    """
    Busca el archivo de configuración principal.
    
    Returns:
        Ruta al archivo config.json
    """
    possible_paths = [
        "config/config.json",
        "./config/config.json",
        Path(__file__).parent.parent.parent / "config" / "config.json"
    ]
    
    for path in possible_paths:
        path_obj = Path(path) if isinstance(path, str) else path
        if path_obj.exists():
            return str(path_obj.resolve())
    
    # Si no existe, usar una configuración por defecto
    return "config/config.json"


def get_upload_manager() -> UploadManager:
    """
    Obtiene instancia de UploadManager (singleton).
    
    Returns:
        Instancia configurada de UploadManager
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "upload_manager" not in _service_cache:
        # Buscar carpeta de uploads en config
        config_path = _find_config_json()
        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Obtener carpeta de uploads desde config, o usar default
            uploads_folder = config.get("api", {}).get("uploads_folder", "uploads")
        except Exception:
            # Si hay error, usar default
            uploads_folder = "uploads"
        
        _service_cache["upload_manager"] = UploadManager(uploads_folder)
    
    return _service_cache["upload_manager"]


def get_archive_manager() -> ArchiveManager:
    """
    Obtiene instancia de ArchiveManager (singleton).
    
    Returns:
        Instancia configurada de ArchiveManager
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "archive_manager" not in _service_cache:
        # Buscar configuración de carpeta pública
        config_path = _find_config_json()
        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Obtener carpeta pública y URL base desde config
            api_config = config.get("api", {})
            public_folder = api_config.get("public_folder", "public")
            base_url = api_config.get("base_url", "http://localhost:8000")
        except Exception:
            # Si hay error, usar defaults
            public_folder = "public"
            base_url = "http://localhost:8000"
        
        _service_cache["archive_manager"] = ArchiveManager(public_folder, base_url)
    
    return _service_cache["archive_manager"]


def get_processed_tracker() -> ProcessedTracker:
    """
    Obtiene instancia de ProcessedTracker (singleton).
    
    Returns:
        Instancia configurada de ProcessedTracker
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "processed_tracker" not in _service_cache:
        _service_cache["processed_tracker"] = ProcessedTracker()
    
    return _service_cache["processed_tracker"]


def get_periodo_manager() -> PeriodoManager:
    """
    Obtiene instancia de PeriodoManager (singleton).
    
    Returns:
        Instancia configurada de PeriodoManager
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "periodo_manager" not in _service_cache:
        _service_cache["periodo_manager"] = PeriodoManager()
    
    return _service_cache["periodo_manager"]


def get_database_service() -> DatabaseService:
    """
    Obtiene instancia de DatabaseService (singleton).
    
    Returns:
        Instancia configurada de DatabaseService
    """
    global _service_cache
    
    if _service_cache is None:
        _service_cache = {}
    
    if "database_service" not in _service_cache:
        # Leer configuración de BD desde config.json
        config_path = _find_config_json()
        db_enabled = False
        
        if config_path and Path(config_path).exists():
            try:
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                db_config = config.get("database", {})
                db_enabled = db_config.get("enabled", False)
            except Exception as e:
                logger.warning(f"No se pudo leer configuración de BD: {e}")
        
        _service_cache["database_service"] = DatabaseService(enabled=db_enabled)
    
    return _service_cache["database_service"]


def clear_service_cache():
    """
    Limpia el cache de servicios (útil para testing o reconfiguración).
    """
    global _service_cache
    _service_cache = None


# Cache para lista de correos autorizados
_allowed_emails_cache: Optional[list] = None


def get_allowed_emails() -> list:
    """
    Obtiene la lista de correos autorizados desde config/allowed_emails.json.
    
    Returns:
        Lista de correos autorizados (emails en minúsculas)
    """
    global _allowed_emails_cache
    
    if _allowed_emails_cache is not None:
        return _allowed_emails_cache
    
    # Buscar archivo de configuración
    possible_paths = [
        "config/allowed_emails.json",
        "./config/allowed_emails.json",
        Path(__file__).parent.parent.parent / "config" / "allowed_emails.json"
    ]
    
    allowed_emails = []
    
    for path in possible_paths:
        path_obj = Path(path) if isinstance(path, str) else path
        if path_obj.exists():
            try:
                import json
                with open(path_obj, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    allowed_emails = config.get("allowed_emails", [])
                    # Normalizar a minúsculas para comparación case-insensitive
                    allowed_emails = [email.lower().strip() for email in allowed_emails if email]
                    break
            except Exception:
                # Si hay error leyendo, continuar buscando en otras rutas
                continue
    
    # Cachear resultado
    _allowed_emails_cache = allowed_emails
    
    return allowed_emails


def is_email_allowed(email: str) -> bool:
    """
    Verifica si un correo está en la lista de correos autorizados.
    
    Args:
        email: Correo a verificar
        
    Returns:
        True si está autorizado, False si no
    """
    if not email:
        return False
    
    allowed_emails = get_allowed_emails()
    email_normalized = email.lower().strip()
    
    return email_normalized in allowed_emails


def clear_allowed_emails_cache():
    """
    Limpia el cache de correos autorizados (útil para recargar configuración).
    """
    global _allowed_emails_cache
    _allowed_emails_cache = None


# ===== Learning System Dependencies =====

def get_learning_system():
    """
    Obtiene el sistema de aprendizaje si está disponible.
    
    Returns:
        Tupla (error_tracker, prompt_manager, learning_service) o (None, None, None) si no está disponible
    """
    try:
        # Verificar si learning está activado
        config_path = _find_config_json()
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        learning_config = config.get("learning", {})
        learning_enabled = learning_config.get("enabled", False)
        
        if not learning_enabled:
            return None, None, None
        
        # Obtener servicios de learning
        learning_folder = learning_config.get("folder", "learning")
        project_root = Path(config_path).parent.parent
        
        # Agregar project_root al path para imports
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from src.learning.error_tracker import ErrorTracker
        from src.learning.prompt_manager import PromptManager
        from src.learning.learning_service import LearningService
        
        gemini_service = get_gemini_service()
        
        error_tracker = ErrorTracker(str(project_root / learning_folder))
        prompt_manager = PromptManager(
            str(project_root / learning_folder),
            default_prompt=None
        )
        learning_service = LearningService(
            gemini_service,
            str(project_root / learning_folder)
        )
        
        return error_tracker, prompt_manager, learning_service
        
    except Exception as e:
        logger.warning(f"Learning system not available: {e}")
        return None, None, None

