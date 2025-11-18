"""
Archive Manager - Gestión de archivos zip para descarga pública
Responsabilidad: Zipear carpetas y generar URLs públicas
"""

import zipfile
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import uuid


class ArchiveManager:
    """
    Gestor de archivos comprimidos para descarga pública.
    
    Responsabilidades:
    - Zipear carpetas de resultados
    - Generar nombres únicos para archivos zip
    - Guardar en carpeta pública
    - Generar URLs públicas
    """
    
    def __init__(self, public_folder: str = "public", base_url: str = "https://localhost:8000"):
        """
        Inicializa el gestor de archivos.
        
        Args:
            public_folder: Carpeta pública donde se guardan los zips
            base_url: URL base para generar URLs públicas
        """
        self.public_folder = Path(public_folder)
        self.public_folder.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip('/')
    
    def zip_folder(self, folder_path: Path, zip_filename: Optional[str] = None) -> Path:
        """
        Comprime una carpeta completa en un archivo zip.
        
        Args:
            folder_path: Ruta a la carpeta a comprimir
            zip_filename: Nombre del archivo zip (opcional, se genera automáticamente)
            
        Returns:
            Path al archivo zip creado
        """
        if not folder_path.exists() or not folder_path.is_dir():
            raise ValueError(f"Carpeta no existe o no es un directorio: {folder_path}")
        
        # Generar nombre único si no se proporciona
        if not zip_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            zip_filename = f"results_{timestamp}_{unique_id}.zip"
        
        zip_path = self.public_folder / zip_filename
        
        # Crear archivo zip
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Recorrer todos los archivos en la carpeta
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = Path(root) / file
                    # Calcular ruta relativa dentro del zip (manteniendo estructura)
                    # Si folder_path es "output/api", queremos "api/raw/archivo.json"
                    arcname = file_path.relative_to(folder_path.parent)
                    zipf.write(file_path, arcname)
        
        return zip_path
    
    def get_public_url(self, zip_path: Path) -> str:
        """
        Genera la URL pública para descargar un archivo zip.
        
        El ZIP debe estar en la carpeta public/ para poder ser descargado.
        Retorna una ruta relativa para que el frontend construya la URL completa
        según el servidor donde se monte.
        
        Args:
            zip_path: Path al archivo zip (debe estar en public/)
            
        Returns:
            Ruta relativa para descargar (ej: /public/archivo.zip)
        """
        # Verificar que el archivo está en la carpeta public
        if not zip_path.exists():
            raise ValueError(f"El archivo ZIP no existe: {zip_path}")
        
        # Nombre del archivo
        filename = zip_path.name
        
        # Generar ruta relativa (sin base_url, el frontend construye la URL completa)
        # Ejemplo: /public/archivo.zip
        public_url = f"/public/{filename}"
        
        return public_url
    
    def cleanup_old_zips(self, days: int = 7):
        """
        Limpia archivos zip antiguos (más de X días).
        
        Args:
            days: Días de antigüedad para considerar eliminación
        """
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        for zip_file in self.public_folder.glob("*.zip"):
            try:
                # Obtener fecha de modificación
                mtime = datetime.fromtimestamp(zip_file.stat().st_mtime)
                if mtime < cutoff_date:
                    zip_file.unlink()
            except Exception:
                pass

