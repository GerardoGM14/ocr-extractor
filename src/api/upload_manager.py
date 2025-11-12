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
    
    def mark_as_processed(self, file_id: str, zip_filename: str, download_url: str, request_id: str):
        """
        Marca un archivo como procesado y guarda información del ZIP.
        
        Args:
            file_id: ID del archivo procesado
            zip_filename: Nombre del archivo ZIP generado
            download_url: URL pública para descargar el ZIP
            request_id: ID de la request de procesamiento
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

