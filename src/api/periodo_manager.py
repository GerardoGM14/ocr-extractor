"""
Periodo Manager - Gestión de periodos
Responsabilidad: Gestionar periodos y sus archivos asociados usando archivos JSON
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


class PeriodoManager:
    """
    Gestor de periodos usando archivos JSON.
    
    Almacena periodos en un archivo JSON similar a processed_tracking.json
    """
    
    def __init__(self, tracking_file: Optional[Path] = None):
        """
        Inicializa el gestor de periodos.
        
        Args:
            tracking_file: Ruta al archivo JSON de tracking (default: ./periodos_tracking.json)
        """
        if tracking_file is None:
            tracking_file = Path("./periodos_tracking.json")
        
        self.tracking_file = tracking_file
        self._ensure_tracking_file()
    
    def _ensure_tracking_file(self):
        """Asegura que el archivo de tracking existe."""
        if not self.tracking_file.exists():
            self._save_periodos({"periodos": []})
    
    def _load_periodos(self) -> Dict[str, Any]:
        """Carga los periodos desde el archivo JSON."""
        try:
            if not self.tracking_file.exists():
                return {"periodos": []}
            
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando periodos: {e}")
            return {"periodos": []}
    
    def _save_periodos(self, data: Dict[str, Any]):
        """Guarda los periodos en el archivo JSON."""
        try:
            self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando periodos: {e}")
            raise
    
    def _generate_periodo_id(self, periodo: str, tipo: str) -> str:
        """
        Genera un ID único para un periodo.
        
        Args:
            periodo: Periodo en formato "MM/AAAA"
            tipo: "onshore" | "offshore"
            
        Returns:
            ID único (ej: "2025-10-offshore")
        """
        # Convertir "10/2025" a "2025-10"
        parts = periodo.split('/')
        if len(parts) == 2:
            mes, anio = parts
            return f"{anio}-{mes.zfill(2)}-{tipo.lower()}"
        else:
            # Si no tiene formato correcto, usar timestamp
            return f"{periodo.replace('/', '-')}-{tipo.lower()}-{uuid4().hex[:8]}"
    
    def create_periodo(self, periodo: str, tipo: str) -> Dict[str, Any]:
        """
        Crea un nuevo periodo.
        
        Args:
            periodo: Periodo en formato "MM/AAAA"
            tipo: "onshore" | "offshore"
            
        Returns:
            Diccionario con la información del periodo creado
        """
        periodo_id = self._generate_periodo_id(periodo, tipo)
        
        # Verificar si ya existe
        data = self._load_periodos()
        for p in data.get("periodos", []):
            if p.get("periodo_id") == periodo_id:
                raise ValueError(f"El periodo {periodo_id} ya existe")
        
        nuevo_periodo = {
            "periodo_id": periodo_id,
            "periodo": periodo,
            "tipo": tipo.lower(),
            "estado": "vacio",
            "registros": 0,
            "ultimo_procesamiento": None,
            "archivos_asociados": [],
            "created_at": datetime.now().isoformat()
        }
        
        data.setdefault("periodos", []).append(nuevo_periodo)
        self._save_periodos(data)
        
        logger.info(f"Periodo creado: {periodo_id}")
        return nuevo_periodo
    
    def get_periodo(self, periodo_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un periodo por su ID.
        Valida y corrige automáticamente si hay inconsistencia entre periodo_id y tipo.
        """
        data = self._load_periodos()
        for periodo in data.get("periodos", []):
            if periodo.get("periodo_id") == periodo_id:
                # Validar y corregir tipo si hay inconsistencia
                tipo_actual = periodo.get("tipo", "")
                # Extraer tipo del periodo_id (formato: "AAAA-MM-tipo")
                if "-" in periodo_id:
                    partes = periodo_id.split("-")
                    if len(partes) >= 3:
                        tipo_correcto = partes[-1].lower()
                        if tipo_correcto in ["onshore", "offshore"] and tipo_actual != tipo_correcto:
                            logger.warning(f"Corrigiendo tipo inconsistente en periodo {periodo_id}: '{tipo_actual}' -> '{tipo_correcto}'")
                            periodo["tipo"] = tipo_correcto
                            # Guardar corrección
                            self._save_periodos(data)
                return periodo
        return None
    
    def list_periodos(
        self, 
        tipo: Optional[str] = None,
        estado: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista periodos con filtros opcionales.
        Valida y corrige automáticamente inconsistencias entre periodo_id y tipo.
        
        Args:
            tipo: Filtrar por tipo ("onshore" | "offshore")
            estado: Filtrar por estado
            search: Buscar en periodo, periodo_id, etc.
            
        Returns:
            Lista de periodos
        """
        data = self._load_periodos()
        periodos = data.get("periodos", [])
        
        # Validar y corregir tipos inconsistentes
        needs_save = False
        for periodo in periodos:
            periodo_id = periodo.get("periodo_id", "")
            tipo_actual = periodo.get("tipo", "")
            
            # Extraer tipo del periodo_id (formato: "AAAA-MM-tipo")
            if "-" in periodo_id:
                partes = periodo_id.split("-")
                if len(partes) >= 3:
                    tipo_correcto = partes[-1].lower()
                    if tipo_correcto in ["onshore", "offshore"] and tipo_actual != tipo_correcto:
                        logger.warning(f"Corrigiendo tipo inconsistente en periodo {periodo_id}: '{tipo_actual}' -> '{tipo_correcto}'")
                        periodo["tipo"] = tipo_correcto
                        needs_save = True
        
        if needs_save:
            self._save_periodos(data)
        
        # Aplicar filtros
        if tipo:
            periodos = [p for p in periodos if p.get("tipo") == tipo.lower()]
        
        if estado:
            periodos = [p for p in periodos if p.get("estado") == estado.lower()]
        
        if search:
            search_lower = search.lower()
            periodos = [
                p for p in periodos
                if search_lower in p.get("periodo", "").lower()
                or search_lower in p.get("periodo_id", "").lower()
            ]
        
        # Ordenar por created_at (más reciente primero)
        periodos.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return periodos
    
    def update_periodo(self, periodo_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Actualiza un periodo.
        Valida que el tipo no sea inconsistente con el periodo_id.
        
        Args:
            periodo_id: ID del periodo
            updates: Diccionario con campos a actualizar
            
        Returns:
            Periodo actualizado o None si no existe
        """
        data = self._load_periodos()
        periodos = data.get("periodos", [])
        
        for i, periodo in enumerate(periodos):
            if periodo.get("periodo_id") == periodo_id:
                # Si se intenta actualizar el tipo, validar que sea consistente con periodo_id
                if "tipo" in updates:
                    # Extraer tipo del periodo_id (formato: "AAAA-MM-tipo")
                    if "-" in periodo_id:
                        partes = periodo_id.split("-")
                        if len(partes) >= 3:
                            tipo_correcto = partes[-1].lower()
                            if tipo_correcto in ["onshore", "offshore"]:
                                # Forzar el tipo correcto basado en periodo_id
                                if updates["tipo"].lower() != tipo_correcto:
                                    logger.warning(f"Tipo '{updates['tipo']}' no coincide con periodo_id '{periodo_id}'. Usando '{tipo_correcto}'")
                                    updates["tipo"] = tipo_correcto
                
                periodos[i].update(updates)
                self._save_periodos(data)
                logger.info(f"Periodo actualizado: {periodo_id}")
                return periodos[i]
        
        return None
    
    def delete_periodo(self, periodo_id: str) -> bool:
        """
        Elimina un periodo.
        
        Args:
            periodo_id: ID del periodo
            
        Returns:
            True si se eliminó, False si no existía
        """
        data = self._load_periodos()
        periodos = data.get("periodos", [])
        
        original_count = len(periodos)
        periodos = [p for p in periodos if p.get("periodo_id") != periodo_id]
        
        if len(periodos) < original_count:
            data["periodos"] = periodos
            self._save_periodos(data)
            logger.info(f"Periodo eliminado: {periodo_id}")
            return True
        
        return False
    
    def add_archivo_to_periodo(self, periodo_id: str, request_id: str) -> bool:
        """
        Asocia un archivo procesado (request_id) a un periodo.
        
        Args:
            periodo_id: ID del periodo
            request_id: ID del request de procesamiento
            
        Returns:
            True si se agregó, False si el periodo no existe
        """
        data = self._load_periodos()
        periodos = data.get("periodos", [])
        
        for periodo in periodos:
            if periodo.get("periodo_id") == periodo_id:
                archivos = periodo.get("archivos_asociados", [])
                if request_id not in archivos:
                    archivos.append(request_id)
                    periodo["archivos_asociados"] = archivos
                    # Actualizar estado y registros
                    periodo["registros"] = len(archivos)
                    if periodo["estado"] == "vacio":
                        periodo["estado"] = "pendiente"
                    periodo["ultimo_procesamiento"] = datetime.now().isoformat()
                    self._save_periodos(data)
                    logger.info(f"Archivo {request_id} agregado al periodo {periodo_id}")
                    return True
        
        return False
    
    def remove_archivo_from_periodo(self, periodo_id: str, request_id: str) -> bool:
        """
        Desasocia un archivo de un periodo.
        
        Args:
            periodo_id: ID del periodo
            request_id: ID del request
            
        Returns:
            True si se removió, False si no existía
        """
        data = self._load_periodos()
        periodos = data.get("periodos", [])
        
        for periodo in periodos:
            if periodo.get("periodo_id") == periodo_id:
                archivos = periodo.get("archivos_asociados", [])
                if request_id in archivos:
                    archivos.remove(request_id)
                    periodo["archivos_asociados"] = archivos
                    periodo["registros"] = len(archivos)
                    if len(archivos) == 0:
                        periodo["estado"] = "vacio"
                    self._save_periodos(data)
                    logger.info(f"Archivo {request_id} removido del periodo {periodo_id}")
                    return True
        
        return False
    
    def get_archivos_from_periodo(self, periodo_id: str) -> List[str]:
        """
        Obtiene la lista de request_ids asociados a un periodo.
        
        Args:
            periodo_id: ID del periodo
            
        Returns:
            Lista de request_ids
        """
        periodo = self.get_periodo(periodo_id)
        if periodo:
            return periodo.get("archivos_asociados", [])
        return []

