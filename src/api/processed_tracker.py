"""
Processed Tracker - Tracking de archivos procesados sin file_id
Responsabilidad: Rastrear archivos procesados directamente (sin upload previo)
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


class ProcessedTracker:
    """
    Rastrea archivos procesados que no fueron subidos previamente.
    
    Útil para archivos procesados directamente sin pasar por upload-pdf.
    """
    
    def __init__(self, tracking_file: str = "processed_tracking.json"):
        """
        Inicializa el tracker.
        
        Args:
            tracking_file: Archivo JSON donde se guarda el tracking
        """
        self.tracking_file = Path(tracking_file)
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
    
    def add_processed_file(self, request_id: str, filename: str, zip_filename: str, 
                          download_url: str, metadata: Dict[str, Any]):
        """
        Agrega un archivo procesado al tracking.
        
        Args:
            request_id: ID de la request
            filename: Nombre del archivo original
            zip_filename: Nombre del ZIP generado
            download_url: URL de descarga
            metadata: Metadata (email, year, month)
        """
        tracking_data = self._load_tracking()
        
        entry = {
            "request_id": request_id,
            "filename": filename,
            "zip_filename": zip_filename,
            "download_url": download_url,
            "metadata": metadata,
            "processed_at": datetime.now().isoformat()
        }
        
        tracking_data[request_id] = entry
        
        self._save_tracking(tracking_data)
    
    def get_processed_files(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los archivos procesados.
        
        Returns:
            Lista de archivos procesados
        """
        tracking_data = self._load_tracking()
        files = list(tracking_data.values())
        
        # Ordenar por fecha (más reciente primero)
        files.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
        
        return files
    
    def _load_tracking(self) -> Dict[str, Any]:
        """Carga el archivo de tracking."""
        if not self.tracking_file.exists():
            return {}
        
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_tracking(self, data: Dict[str, Any]):
        """Guarda el archivo de tracking."""
        with open(self.tracking_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

