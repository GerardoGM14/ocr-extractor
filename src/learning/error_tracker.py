"""
Error Tracker Module - Registro de errores durante procesamiento
Responsabilidad: Registrar errores con contexto para análisis posterior
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class ErrorTracker:
    """
    Rastrea y registra errores durante el procesamiento OCR.
    
    Responsabilidades:
    - Registrar errores con contexto completo
    - Categorizar errores por tipo
    - Almacenar errores en JSON para análisis posterior
    """
    
    def __init__(self, learning_folder: str = "learning"):
        """
        Inicializa el tracker de errores.
        
        Args:
            learning_folder: Carpeta base para almacenar datos de learning
        """
        self.learning_folder = Path(learning_folder)
        self.errors_folder = self.learning_folder / "errors"
        self.errors_folder.mkdir(parents=True, exist_ok=True)
        
        self.error_counter = 0
        self.errors_buffer = []
    
    def record_error(self, 
                    pdf_name: str,
                    page_num: int,
                    error_type: str,
                    error_message: str,
                    context: Optional[Dict[str, Any]] = None,
                    extracted_data: Optional[Dict[str, Any]] = None,
                    ocr_text: Optional[str] = None) -> str:
        """
        Registra un error con contexto completo.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            error_type: Tipo de error (ej: "missing_field", "incorrect_value", "parse_error")
            error_message: Mensaje descriptivo del error
            context: Contexto adicional (opcional)
            extracted_data: Datos extraídos hasta el momento (opcional)
            ocr_text: Texto OCR completo (opcional, puede ser largo)
            
        Returns:
            ID del error registrado
        """
        self.error_counter += 1
        error_id = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.error_counter:04d}"
        
        error_data = {
            "error_id": error_id,
            "timestamp": datetime.now().isoformat(),
            "pdf_name": pdf_name,
            "page_number": page_num,
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {},
            "extracted_data": extracted_data or {},
            "ocr_text_length": len(ocr_text) if ocr_text else 0,
            "ocr_text_preview": ocr_text[:500] if ocr_text else None  # Solo primeros 500 chars
        }
        
        # Agregar texto OCR completo si está disponible (en archivo separado si es muy largo)
        if ocr_text and len(ocr_text) > 1000:
            ocr_file = self.errors_folder / f"{error_id}_ocr_text.txt"
            with open(ocr_file, 'w', encoding='utf-8') as f:
                f.write(ocr_text)
            error_data["ocr_text_file"] = str(ocr_file)
        elif ocr_text:
            error_data["ocr_text"] = ocr_text
        
        # Guardar error en archivo JSON
        error_file = self.errors_folder / f"{error_id}.json"
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)
        
        # Agregar a buffer para análisis rápido
        self.errors_buffer.append(error_data)
        
        return error_id
    
    def record_missing_field(self,
                           pdf_name: str,
                           page_num: int,
                           field_name: str,
                           expected_value: Optional[str] = None,
                           ocr_text: Optional[str] = None,
                           extracted_data: Optional[Dict] = None) -> str:
        """
        Registra un campo faltante.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            field_name: Nombre del campo faltante
            expected_value: Valor esperado (opcional)
            ocr_text: Texto OCR (opcional)
            extracted_data: Datos extraídos (opcional)
            
        Returns:
            ID del error registrado
        """
        return self.record_error(
            pdf_name=pdf_name,
            page_num=page_num,
            error_type="missing_field",
            error_message=f"Campo '{field_name}' está vacío o no se pudo extraer",
            context={
                "field_name": field_name,
                "expected_value": expected_value
            },
            extracted_data=extracted_data,
            ocr_text=ocr_text
        )
    
    def record_incorrect_value(self,
                              pdf_name: str,
                              page_num: int,
                              field_name: str,
                              extracted_value: Any,
                              expected_value: Optional[Any] = None,
                              reason: Optional[str] = None,
                              ocr_text: Optional[str] = None,
                              extracted_data: Optional[Dict] = None) -> str:
        """
        Registra un valor incorrecto.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            field_name: Nombre del campo
            extracted_value: Valor extraído (incorrecto)
            expected_value: Valor esperado (opcional)
            reason: Razón del error (opcional)
            ocr_text: Texto OCR (opcional)
            extracted_data: Datos extraídos (opcional)
            
        Returns:
            ID del error registrado
        """
        return self.record_error(
            pdf_name=pdf_name,
            page_num=page_num,
            error_type="incorrect_value",
            error_message=f"Campo '{field_name}' tiene valor incorrecto: {extracted_value}",
            context={
                "field_name": field_name,
                "extracted_value": str(extracted_value),
                "expected_value": str(expected_value) if expected_value else None,
                "reason": reason
            },
            extracted_data=extracted_data,
            ocr_text=ocr_text
        )
    
    def record_parse_error(self,
                          pdf_name: str,
                          page_num: int,
                          error_message: str,
                          exception: Optional[Exception] = None,
                          ocr_text: Optional[str] = None) -> str:
        """
        Registra un error de parsing.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            error_message: Mensaje del error
            exception: Excepción capturada (opcional)
            ocr_text: Texto OCR (opcional)
            
        Returns:
            ID del error registrado
        """
        return self.record_error(
            pdf_name=pdf_name,
            page_num=page_num,
            error_type="parse_error",
            error_message=error_message,
            context={
                "exception_type": type(exception).__name__ if exception else None,
                "exception_message": str(exception) if exception else None
            },
            ocr_text=ocr_text
        )
    
    def get_recent_errors(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene errores recientes.
        
        Args:
            limit: Número máximo de errores a retornar
            
        Returns:
            Lista de errores recientes
        """
        # Cargar errores de archivos si el buffer está vacío
        if not self.errors_buffer:
            self._load_recent_errors(limit)
        
        return self.errors_buffer[-limit:]
    
    def _load_recent_errors(self, limit: int):
        """Carga errores recientes desde archivos."""
        if not self.errors_folder.exists():
            return
        
        error_files = sorted(self.errors_folder.glob("error_*.json"), reverse=True)
        
        for error_file in error_files[:limit]:
            try:
                with open(error_file, 'r', encoding='utf-8') as f:
                    error_data = json.load(f)
                    self.errors_buffer.append(error_data)
            except Exception:
                continue
    
    def get_errors_summary(self) -> Dict[str, Any]:
        """
        Obtiene un resumen de errores.
        
        Returns:
            Diccionario con estadísticas de errores
        """
        errors = self.get_recent_errors(limit=1000)
        
        if not errors:
            return {
                "total_errors": 0,
                "error_types": {},
                "most_common_fields": {},
                "recent_errors": []
            }
        
        # Contar por tipo
        error_types = {}
        field_errors = {}
        
        for error in errors:
            error_type = error.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
            # Si es error de campo, contar el campo
            if error_type in ["missing_field", "incorrect_value"]:
                field_name = error.get("context", {}).get("field_name", "unknown")
                field_errors[field_name] = field_errors.get(field_name, 0) + 1
        
        return {
            "total_errors": len(errors),
            "error_types": error_types,
            "most_common_fields": dict(sorted(field_errors.items(), key=lambda x: x[1], reverse=True)[:10]),
            "recent_errors": errors[-10:]  # Últimos 10 errores
        }
    
    def clear_old_errors(self, days: int = 30):
        """
        Limpia errores antiguos.
        
        Args:
            days: Número de días para conservar errores
        """
        if not self.errors_folder.exists():
            return
        
        cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
        
        for error_file in self.errors_folder.glob("error_*.json"):
            try:
                file_time = error_file.stat().st_mtime
                if file_time < cutoff_date:
                    error_file.unlink()
                    
                    # Eliminar archivo OCR asociado si existe
                    ocr_file = error_file.with_suffix('.txt')
                    if ocr_file.exists():
                        ocr_file.unlink()
            except Exception:
                continue

