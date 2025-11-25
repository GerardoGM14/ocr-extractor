"""
Database Service - Servicio para guardar datos en SQL Server
Responsabilidad: Guardar datos estructurados en base de datos antes de eliminar JSONs
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Servicio para guardar datos en SQL Server.
    
    Por ahora es un stub que prepara la estructura.
    Cuando tengas conexión a BD, implementa los métodos reales.
    """
    
    def __init__(self, enabled: bool = False):
        """
        Inicializa el servicio de base de datos.
        
        Args:
            enabled: Si está habilitado, intentará guardar en BD. Si False, solo loguea.
        """
        self.enabled = enabled
        self.connection_string = None  # Se configurará cuando tengas BD
    
    def is_enabled(self) -> bool:
        """Verifica si el servicio está habilitado."""
        return self.enabled
    
    def save_structured_data(self, request_id: str, json_files: List[Path]) -> bool:
        """
        Guarda los datos estructurados de los JSONs en la base de datos.
        
        Args:
            request_id: ID de la request de procesamiento
            json_files: Lista de paths a los JSONs structured a guardar
            
        Returns:
            True si se guardó exitosamente, False si hubo error o está deshabilitado
        """
        if not self.enabled:
            logger.info(f"[{request_id}] BD deshabilitada, saltando guardado en BD")
            return True  # No es un error si está deshabilitado
        
        try:
            logger.info(f"[{request_id}] Iniciando guardado en BD de {len(json_files)} archivos JSON...")
            
            # Leer y procesar cada JSON structured
            saved_count = 0
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    # Extraer datos estructurados
                    metadata = json_data.get("metadata", {})
                    hoja_data = json_data.get("hoja", {})
                    additional_data = json_data.get("additional_data", {})
                    
                    # TODO: Cuando tengas conexión a BD, implementar:
                    # 1. Guardar en MARCHIVO (si no existe)
                    # 2. Guardar en MHOJA
                    # 3. Guardar en MCOMPROBANTE, MJORNADA, MPROVEEDOR, etc.
                    # 4. Manejar relaciones y foreign keys
                    
                    # Por ahora, solo loguear que se procesaría
                    logger.debug(
                        f"[{request_id}] Procesando JSON: {json_file.name} "
                        f"(page: {metadata.get('page_number', 'N/A')})"
                    )
                    
                    # Simular guardado exitoso
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"[{request_id}] Error procesando {json_file.name}: {e}")
                    # Continuar con los demás archivos
                    continue
            
            if saved_count == len(json_files):
                logger.info(f"[{request_id}] ✓ Datos guardados en BD: {saved_count}/{len(json_files)} archivos")
                print(f"[{request_id[:8]}] ✓ Datos guardados en BD: {saved_count} archivos")
                return True
            else:
                logger.warning(
                    f"[{request_id}] ⚠ Guardado parcial en BD: "
                    f"{saved_count}/{len(json_files)} archivos"
                )
                print(f"[{request_id[:8]}] ⚠ Guardado parcial en BD: {saved_count}/{len(json_files)}")
                # Retornar False si no se guardaron todos
                return saved_count > 0  # Al menos algunos se guardaron
        
        except Exception as e:
            logger.exception(f"[{request_id}] Error guardando en BD: {e}")
            print(f"[{request_id[:8]}] ✗ Error guardando en BD: {e}")
            return False
    
    def _save_marchivo(self, metadata: Dict) -> Optional[int]:
        """
        Guarda o actualiza registro en MARCHIVO.
        
        Returns:
            iMArchivo (ID del archivo) o None si hay error
        """
        # TODO: Implementar cuando tengas conexión
        # INSERT INTO MARCHIVO (tNombre, tRuta, iMArchivoTipo, fRegistro)
        # VALUES (...)
        # RETURNING iMArchivo
        pass
    
    def _save_mhoja(self, hoja_data: Dict, i_marchivo: int) -> Optional[int]:
        """
        Guarda registro en MHOJA.
        
        Returns:
            iMHoja (ID de la hoja) o None si hay error
        """
        # TODO: Implementar cuando tengas conexión
        # INSERT INTO MHOJA (...)
        # VALUES (...)
        # RETURNING iMHoja
        pass
    
    def _save_mcomprobante(self, comprobantes: List[Dict], i_mhoja: int) -> bool:
        """Guarda registros en MCOMPROBANTE."""
        # TODO: Implementar cuando tengas conexión
        pass
    
    def _save_mjornada(self, jornadas: List[Dict], i_mhoja: int) -> bool:
        """Guarda registros en MJORNADA."""
        # TODO: Implementar cuando tengas conexión
        pass
    
    def _save_mproveedor(self, proveedores: List[Dict]) -> Dict[str, int]:
        """
        Guarda registros en MPROVEEDOR.
        
        Returns:
            Dict con RUC -> iMProveedor para reutilizar
        """
        # TODO: Implementar cuando tengas conexión
        pass
    
    def verify_password_from_db(self, email: str, provided_password: str) -> bool:
        """
        Verifica una contraseña leyendo desde la base de datos.
        
        TEMPORAL: Solo para pruebas. Después volveremos a usar JSON.
        
        Args:
            email: Email del usuario
            provided_password: Contraseña proporcionada
            
        Returns:
            True si la contraseña es correcta, False en caso contrario
        """
        if not self.enabled:
            return False
        
        try:
            try:
                import pyodbc
            except ImportError:
                logger.warning("pyodbc no está instalado. No se puede validar desde BD.")
                return False
            
            # Obtener connection string
            if not self.connection_string:
                config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        db_config = config.get("database", {})
                        server = db_config.get("server", "localhost")
                        database = db_config.get("database", "BD_NEWMONT_OCR_PDF")
                        username = db_config.get("username")
                        password_db = db_config.get("password")
                        
                        if username and password_db:
                            self.connection_string = (
                                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                                f"SERVER={server};"
                                f"DATABASE={database};"
                                f"UID={username};"
                                f"PWD={password_db}"
                            )
                        else:
                            self.connection_string = (
                                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                                f"SERVER={server};"
                                f"DATABASE={database};"
                                f"Trusted_Connection=yes;"
                            )
                    except Exception as e:
                        logger.warning(f"No se pudo leer configuración de BD: {e}")
                        return False
            
            if not self.connection_string:
                return False
            
            # Ejecutar procedimiento almacenado ValidarLogin
            with pyodbc.connect(self.connection_string) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "EXEC dbo.ValidarLogin @email=?, @password=?",
                    (email.lower().strip(), provided_password)
                )
                
                # Leer resultado
                row = cursor.fetchone()
                if row:
                    resultado = row[0] if len(row) > 0 else None
                    if resultado == 'success':
                        logger.info(f"✓ [BD] Contraseña validada desde BASE DE DATOS para: {email}")
                        print(f"✓ [BD] Validación exitosa desde BASE DE DATOS para: {email}")
                        return True
                    else:
                        logger.info(f"✗ [BD] Contraseña incorrecta en BASE DE DATOS para: {email}")
                        print(f"✗ [BD] Contraseña incorrecta en BASE DE DATOS para: {email}")
                
                return False
                
        except Exception as e:
            logger.warning(f"Error validando contraseña desde BD (no crítico): {e}")
            return False
    
    def sync_usuario_to_db(self, email: str, password: str, nombre: str = None) -> bool:
        """
        Sincroniza un usuario desde JSON a la base de datos (backup).
        
        Este método guarda una copia del usuario en la BD cuando se actualiza en JSON.
        La BD actúa como respaldo, el JSON sigue siendo la fuente de verdad.
        
        Args:
            email: Email del usuario
            password: Contraseña en texto plano (se hasheará en BD)
            nombre: Nombre del usuario (opcional)
            
        Returns:
            True si se sincronizó exitosamente, False si hubo error o está deshabilitado
        """
        if not self.enabled:
            # Si BD está deshabilitada, no es un error, solo no sincroniza
            return True
        
        try:
            # Intentar importar pyodbc para conexión a SQL Server
            try:
                import pyodbc
            except ImportError:
                logger.warning("pyodbc no está instalado. No se puede sincronizar usuario a BD.")
                return True  # No es un error crítico, solo no sincroniza
            
            # Obtener connection string desde configuración
            if not self.connection_string:
                # Intentar leer desde config.json
                config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        db_config = config.get("database", {})
                        server = db_config.get("server", "localhost")
                        database = db_config.get("database", "BD_NEWMONT_OCR_PDF")
                        username = db_config.get("username")
                        password_db = db_config.get("password")
                        
                        if username and password_db:
                            self.connection_string = (
                                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                                f"SERVER={server};"
                                f"DATABASE={database};"
                                f"UID={username};"
                                f"PWD={password_db}"
                            )
                        else:
                            # Usar autenticación de Windows
                            self.connection_string = (
                                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                                f"SERVER={server};"
                                f"DATABASE={database};"
                                f"Trusted_Connection=yes;"
                            )
                    except Exception as e:
                        logger.warning(f"No se pudo leer configuración de BD: {e}")
                        return True  # No es crítico, solo no sincroniza
            
            if not self.connection_string:
                logger.debug("No hay connection string configurado. Saltando sincronización a BD.")
                return True  # No es crítico
            
            # Conectar y ejecutar procedimiento almacenado
            with pyodbc.connect(self.connection_string) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "EXEC dbo.SyncUsuarioFromJSON @email=?, @password=?, @nombre=?",
                    (email.lower().strip(), password, nombre)
                )
                conn.commit()
                logger.debug(f"Usuario sincronizado a BD: {email}")
                return True
                
        except Exception as e:
            # No es crítico si falla, solo loguear
            logger.warning(f"Error sincronizando usuario {email} a BD (no crítico): {e}")
            return True  # Retornar True para no interrumpir el flujo principal

