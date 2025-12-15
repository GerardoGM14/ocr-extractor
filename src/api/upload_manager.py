"""
Upload Manager - Gestión de PDFs subidos
Responsabilidad: Guardar, recuperar y gestionar PDFs subidos con metadata
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class UploadManager:
    """
    Gestor de PDFs subidos para la API.
    
    Responsabilidades:
    - Guardar PDFs subidos con metadata
    - Recuperar PDFs por file_id
    - Gestionar carpeta de uploads
    """
    
    def __init__(self, uploads_folder: str = "uploads"):
        """
        Inicializa el gestor de uploads.
        
        Args:
            uploads_folder: Carpeta donde se guardan los PDFs subidos
        """
        self.uploads_folder = Path(uploads_folder)
        self.uploads_folder.mkdir(parents=True, exist_ok=True)
        
        # Subcarpeta para metadata
        self.metadata_folder = self.uploads_folder / "metadata"
        self.metadata_folder.mkdir(parents=True, exist_ok=True)
    
    def save_uploaded_pdf(self, pdf_content: bytes, filename: str, 
                         metadata: Dict[str, Any]) -> str:
        """
        Guarda un PDF subido con su metadata.
        
        Args:
            pdf_content: Contenido del PDF en bytes
            filename: Nombre original del archivo
            metadata: Metadata (email, year, month)
            
        Returns:
            file_id generado (UUID)
        """
        # Generar file_id único
        file_id = str(uuid.uuid4())
        
        # Guardar PDF
        pdf_path = self.uploads_folder / f"{file_id}.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)
        
        # Guardar metadata
        metadata_data = {
            "file_id": file_id,
            "filename": filename,
            "uploaded_at": datetime.now().isoformat(),
            "metadata": metadata,
            "file_size_bytes": len(pdf_content)
        }
        
        metadata_path = self.metadata_folder / f"{file_id}_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_data, f, ensure_ascii=False, indent=2)
        
        return file_id
    
    def get_uploaded_pdf_path(self, file_id: str) -> Optional[Path]:
        """
        Obtiene la ruta del PDF subido.
        
        Args:
            file_id: ID del archivo subido
            
        Returns:
            Path al PDF o None si no existe
        """
        pdf_path = self.uploads_folder / f"{file_id}.pdf"
        if pdf_path.exists():
            return pdf_path
        return None
    
    def get_uploaded_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la metadata del PDF subido.
        
        Args:
            file_id: ID del archivo subido
            
        Returns:
            Metadata o None si no existe
        """
        metadata_path = self.metadata_folder / f"{file_id}_metadata.json"
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def update_uploaded_metadata(self, file_id: str, updates: Dict[str, Any]) -> bool:
        """
        Actualiza la metadata de un PDF subido.
        
        Args:
            file_id: ID del archivo subido
            updates: Diccionario con campos a actualizar (se fusiona con metadata existente)
            
        Returns:
            True si se actualizó correctamente, False si el archivo no existe
        """
        metadata_path = self.metadata_folder / f"{file_id}_metadata.json"
        if not metadata_path.exists():
            return False
        
        try:
            # Leer metadata existente
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata_data = json.load(f)
            
            # Actualizar metadata (fusionar updates con metadata existente)
            if "metadata" not in metadata_data:
                metadata_data["metadata"] = {}
            
            # Fusionar updates en metadata
            metadata_data["metadata"].update(updates)
            
            # Guardar metadata actualizada
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"Error actualizando metadata de {file_id}: {e}")
            return False
    
    def remove_periodo_from_metadata(self, periodo_id: str, delete_files: bool = False) -> int:
        """
        Remueve el periodo_id de la metadata de todos los archivos asociados a un periodo.
        Si delete_files es True, también elimina los archivos PDF y sus metadatas.
        
        Args:
            periodo_id: ID del periodo a remover
            delete_files: Si es True, elimina los archivos físicos y metadatas
            
        Returns:
            Número de archivos actualizados/eliminados
        """
        updated_count = 0
        
        # Buscar todos los archivos de metadata
        if not self.metadata_folder.exists():
            return 0
        
        files_to_delete = []  # Lista de file_ids a eliminar si delete_files es True
        
        for metadata_file in self.metadata_folder.glob("*_metadata.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata_data = json.load(f)
                
                # Verificar si este archivo tiene el periodo_id
                file_metadata = metadata_data.get("metadata", {})
                if file_metadata.get("periodo_id") == periodo_id:
                    file_id = metadata_data.get("file_id")
                    
                    if delete_files:
                        # Agregar a la lista de archivos a eliminar
                        files_to_delete.append(file_id)
                    else:
                        # Solo remover periodo_id y onshore_offshore de la metadata
                        if "periodo_id" in file_metadata:
                            del file_metadata["periodo_id"]
                        if "onshore_offshore" in file_metadata:
                            del file_metadata["onshore_offshore"]
                        
                        # Guardar metadata actualizada
                        metadata_data["metadata"] = file_metadata
                        with open(metadata_file, 'w', encoding='utf-8') as f:
                            json.dump(metadata_data, f, ensure_ascii=False, indent=2)
                        
                        updated_count += 1
                        logger.info(f"Removido periodo_id {periodo_id} de metadata de {file_id}")
            except Exception as e:
                logger.warning(f"Error procesando {metadata_file}: {e}")
                continue
        
        # Eliminar archivos físicos y metadatas si se solicitó
        if delete_files:
            for file_id in files_to_delete:
                try:
                    deleted = self.delete_uploaded_pdf(file_id)
                    if deleted:
                        updated_count += 1
                        logger.info(f"Eliminado archivo {file_id} asociado al periodo {periodo_id}")
                except Exception as e:
                    logger.warning(f"Error eliminando archivo {file_id}: {e}")
        
        return updated_count
    
    def delete_uploaded_pdf(self, file_id: str) -> bool:
        """
        Elimina un PDF subido y su metadata.
        
        Args:
            file_id: ID del archivo a eliminar
            
        Returns:
            True si se eliminó correctamente
        """
        success = True
        
        # Eliminar PDF
        pdf_path = self.uploads_folder / f"{file_id}.pdf"
        if pdf_path.exists():
            try:
                pdf_path.unlink()
            except Exception:
                success = False
        
        # Eliminar metadata
        metadata_path = self.metadata_folder / f"{file_id}_metadata.json"
        if metadata_path.exists():
            try:
                metadata_path.unlink()
            except Exception:
                success = False
        
        return success
    
    def file_exists(self, file_id: str) -> bool:
        """
        Verifica si un file_id existe.
        
        Args:
            file_id: ID del archivo
            
        Returns:
            True si existe
        """
        pdf_path = self.uploads_folder / f"{file_id}.pdf"
        return pdf_path.exists()
    
    def mark_as_processed(self, file_id: str, zip_filename: str, download_url: str, request_id: str, 
                          excel_filename: Optional[str] = None, excel_download_url: Optional[str] = None):
        """
        Marca un archivo como procesado y guarda información del ZIP y Excel.
        
        Args:
            file_id: ID del archivo procesado
            zip_filename: Nombre del archivo ZIP generado
            download_url: URL pública para descargar el ZIP
            request_id: ID de la request de procesamiento
            excel_filename: Nombre del archivo Excel generado (opcional)
            excel_download_url: URL pública para descargar el Excel (opcional)
        """
        metadata = self.get_uploaded_metadata(file_id)
        if not metadata:
            return
        
        # Agregar información de procesamiento
        metadata["processed"] = True
        metadata["processed_at"] = datetime.now().isoformat()
        metadata["zip_filename"] = zip_filename
        metadata["download_url"] = download_url
        metadata["request_id"] = request_id
        
        # Agregar información del Excel si existe
        if excel_filename:
            metadata["excel_filename"] = excel_filename
        if excel_download_url:
            metadata["excel_download_url"] = excel_download_url
        
        # Guardar metadata actualizada
        metadata_path = self.metadata_folder / f"{file_id}_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def list_uploaded_files(self, processed: Optional[bool] = None) -> list:
        """
        Lista todos los archivos subidos.
        
        Args:
            processed: Si True, solo procesados. Si False, solo no procesados. Si None, todos.
            
        Returns:
            Lista de metadata de archivos
        """
        files = []
        
        if not self.metadata_folder.exists():
            return files
        
        for metadata_file in self.metadata_folder.glob("*_metadata.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                
                # Filtrar por estado de procesamiento
                is_processed = file_data.get("processed", False)
                if processed is None or is_processed == processed:
                    files.append(file_data)
            except Exception:
                continue
        
        # Ordenar por fecha de subida (más reciente primero)
        files.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        
        return files

