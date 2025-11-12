"""
File Manager Module - Gestión de carpetas y archivos
Responsabilidad: Manejo de carpetas de entrada, salida y temporales
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, List


class FileManager:
    """
    Gestor de archivos para el sistema de OCR.
    
    Responsabilidades:
    - Configuración de carpetas
    - Validación de rutas
    - Creación de carpetas si no existen
    """
    
    def __init__(self, config_path: str = "config/config.json"):
        """Inicializa el FileManager con configuración."""
        self.config_path = config_path
        self.config = self._load_config()
        self.project_root = self._get_project_root()
        self.config = self._resolve_relative_paths()
        self._validate_folders()
    
    def _load_config(self) -> Dict:
        """Carga la configuración desde JSON."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config: {e}")
    
    def _get_project_root(self) -> Path:
        """Encuentra la raíz del proyecto."""
        # Si config está en config/, raíz es el padre
        config_file = Path(self.config_path).resolve()
        if "config" in config_file.parts:
            return config_file.parent.parent
        return config_file.parent
    
    def _resolve_relative_paths(self) -> Dict:
        """Convierte rutas relativas a absolutas basadas en project_root."""
        config = self.config.copy()
        
        if "folders" in config:
            folders = config["folders"].copy()
            for key, path in folders.items():
                # Ignorar claves que empiezan con "_" (comentarios/documentación)
                if key.startswith("_"):
                    continue
                if path and not os.path.isabs(path):
                    # Convertir ruta relativa a absoluta
                    config["folders"][key] = str(self.project_root / path)
        
        if "settings" in config and "temp_folder" in config["settings"]:
            temp_path = config["settings"]["temp_folder"]
            if temp_path and not os.path.isabs(temp_path):
                config["settings"]["temp_folder"] = str(self.project_root / temp_path)
        
        return config
    
    def _validate_folders(self) -> None:
        """Valida y crea las carpetas necesarias."""
        folders = self.config.get("folders", {})
        
        required_folders = ["input_pdf", "processing_results", "output_json"]
        
        for folder_name in required_folders:
            folder_path = folders.get(folder_name)
            if not folder_path:
                continue  # Puede estar vacío inicialmente
            
            Path(folder_path).mkdir(parents=True, exist_ok=True)
    
    def get_input_folder(self) -> Optional[str]:
        """Retorna la carpeta de entrada de PDFs."""
        return self.config.get("folders", {}).get("input_pdf")
    
    def get_output_folder(self) -> Optional[str]:
        """Retorna la carpeta de salida de JSONs."""
        return self.config.get("folders", {}).get("output_json")
    
    def get_processing_folder(self) -> Optional[str]:
        """Retorna la carpeta de procesamiento."""
        return self.config.get("folders", {}).get("processing_results")
    
    def get_temp_folder(self) -> str:
        """Retorna la carpeta temporal."""
        return self.config.get("settings", {}).get("temp_folder", "./temp")
    
    def list_pdf_files(self) -> List[Path]:
        """Lista todos los archivos PDF en la carpeta de entrada."""
        input_folder = self.get_input_folder()
        
        if not input_folder or not os.path.exists(input_folder):
            return []
        
        pdf_path = Path(input_folder)
        # Buscar PDFs en minúsculas y mayúsculas, eliminar duplicados con set
        # (en Windows no distingue mayúsculas/minúsculas)
        pdf_files = set(pdf_path.glob("*.pdf")) | set(pdf_path.glob("*.PDF"))
        return sorted(list(pdf_files))  # Convertir a lista ordenada
    
    def save_json(self, data: Dict, filename: str, 
                  subfolder: str = "raw") -> Path:
        """
        Guarda un archivo JSON en la carpeta de salida.
        
        Args:
            data: Diccionario con datos a guardar
            filename: Nombre del archivo
            subfolder: Subcarpeta dentro de output
        """
        output_folder = self.get_output_folder() or "./output"
        
        subfolder_path = Path(output_folder) / subfolder
        subfolder_path.mkdir(parents=True, exist_ok=True)
        
        output_path = subfolder_path / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_path
    
    def create_temp_file(self, filename: str) -> Path:
        """Crea un archivo temporal en la carpeta temp."""
        temp_folder = Path(self.get_temp_folder())
        temp_folder.mkdir(parents=True, exist_ok=True)
        
        return temp_folder / filename
    
    def delete_temp_file(self, filepath: Path) -> bool:
        """Elimina un archivo temporal."""
        try:
            if filepath.exists():
                filepath.unlink()
                return True
            return False
        except Exception:
            return False
    
    def update_config(self, **kwargs) -> None:
        """Actualiza la configuración con nuevos valores."""
        for key, value in kwargs.items():
            if isinstance(key, str) and '.' in key:
                keys = key.split('.')
                conf = self.config
                for k in keys[:-1]:
                    conf = conf.setdefault(k, {})
                conf[keys[-1]] = value
        
        self._save_config()
    
    def _save_config(self) -> None:
        """Guarda la configuración en el archivo (con rutas relativas)."""
        # Convertir rutas absolutas de vuelta a relativas
        config_to_save = self._convert_to_relative_paths()
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    
    def _convert_to_relative_paths(self) -> Dict:
        """Convierte rutas absolutas a relativas para guardar."""
        config = self.config.copy()
        
        if "folders" in config:
            folders = config["folders"].copy()
            for key, path in folders.items():
                # Ignorar claves que empiezan con "_" (comentarios/documentación)
                if key.startswith("_"):
                    continue
                if path and os.path.isabs(path):
                    try:
                        # Intentar convertir a ruta relativa desde project_root
                        abs_path = Path(path)
                        rel_path = os.path.relpath(abs_path, self.project_root)
                        config["folders"][key] = rel_path
                    except (ValueError, TypeError):
                        # Si no se puede convertir, mantener la ruta original
                        pass
        
        if "settings" in config and "temp_folder" in config["settings"]:
            temp_path = config["settings"]["temp_folder"]
            if temp_path and os.path.isabs(temp_path):
                try:
                    abs_path = Path(temp_path)
                    rel_path = os.path.relpath(abs_path, self.project_root)
                    config["settings"]["temp_folder"] = rel_path
                except (ValueError, TypeError):
                    pass
        
        return config

