"""
JSON Parser Module - Generación de JSON 1 y JSON 2
Responsabilidad: Crear JSON crudo y estructurado
"""

from typing import Dict, List, Any
from datetime import datetime


class JSONParser:
    """
    Parser para generar JSON de salida.
    
    Responsabilidades:
    - Crear JSON 1 (Raw OCR)
    - Crear JSON 2 (Estructurado)
    """
    
    def __init__(self):
        """Inicializa el parser JSON."""
        self.metadata = self._initialize_metadata()
    
    def _initialize_metadata(self) -> Dict:
        """Inicializa metadatos del parser."""
        return {
            "version": "1.0.0",
            "parser": "ExtractorOCR"
        }
    
    def create_raw_json(self, ocr_result: Dict, page_num: int, 
                       pdf_name: str) -> Dict[str, Any]:
        """
        Crea JSON 1: Información cruda extraída.
        
        Args:
            ocr_result: Resultado del OCR de Gemini
            page_num: Número de página
            pdf_name: Nombre del PDF
            
        Returns:
            JSON 1 con datos crudos
        """
        return {
            "metadata": {
                **self.metadata,
                "pdf_name": pdf_name,
                "page_number": page_num,
                "extraction_date": datetime.now().isoformat(),
                "type": "raw"
            },
            "ocr_data": {
                "success": ocr_result.get("success", False),
                "text": ocr_result.get("text", ""),
                "model": ocr_result.get("model", ""),
                "error": ocr_result.get("error")
            },
            "raw_text": ocr_result.get("text", "")
        }
    
    def create_structured_json(self, hoja_data: Dict, 
                              additional_data: Dict = None) -> Dict[str, Any]:
        """
        Crea JSON 2: Información estructurada para BD.
        
        Args:
            hoja_data: Datos de MHOJA
            additional_data: Datos adicionales (comprobante, resumen, etc.)
            
        Returns:
            JSON 2 estructurado
        """
        json_2 = {
            "metadata": {
                **self.metadata,
                "extraction_date": datetime.now().isoformat(),
                "type": "structured"
            },
            "hoja": {
                "tJson": hoja_data.get("tJson"),
                "tJsonTraducido": None,  # Se completará con traducción
                "lFormato": hoja_data.get("lFormato"),
                "iMIdioma": hoja_data.get("iMIdioma"),
                "iMDocumentoTipo": hoja_data.get("iMDocumentoTipo"),
                "tSequentialNumber": hoja_data.get("tSequentialNumber")
            }
        }
        
        # Inicializar estructura completa de tablas
        if not json_2.get("additional_data"):
            json_2["additional_data"] = {}
        
        # Asegurar que todas las tablas estén presentes (incluso si vacías)
        # Tablas principales (datos de transacción)
        default_tables = {
            "mresumen": [],
            "mcomprobante": [],
            "mcomprobante_detalle": [],
            "mjornada": [],
            "mjornada_empleado": [],
            "mproveedor": []
        }
        
        # Tablas ancla (catálogos/referencia) - identificadores por índices
        default_catalog_tables = {
            "marchivo_tipo": [],  # Tipos de archivo
            "mdivisa": [],  # Divisas (USD, PEN, EUR, etc.)
            "mdocumento_tipo": [],  # Tipos de documento (comprobante, resumen, jornada)
            "midioma": [],  # Idiomas (Español, Inglés, etc.)
            "mnaturaleza": [],  # Naturaleza del comprobante
            "munidad_medida": []  # Unidades de medida
        }
        
        # Si hay datos adicionales, fusionarlos con la estructura completa
        if additional_data:
            for key, value in additional_data.items():
                json_2["additional_data"][key] = value
        
        # Asegurar que todas las tablas principales estén presentes
        for table_name, default_value in default_tables.items():
            if table_name not in json_2["additional_data"]:
                json_2["additional_data"][table_name] = default_value
        
        # Asegurar que todas las tablas ancla estén presentes
        for table_name, default_value in default_catalog_tables.items():
            if table_name not in json_2["additional_data"]:
                json_2["additional_data"][table_name] = default_value
        
        return json_2
    
    def create_page_json(self, pdf_name: str, page_num: int,
                        raw_json: Dict, structured_json: Dict) -> Dict[str, Any]:
        """
        Crea JSON completo por página.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            raw_json: JSON 1
            structured_json: JSON 2
            
        Returns:
            JSON combinado por página
        """
        return {
            "pdf_name": pdf_name,
            "page_number": page_num,
            "json_1_raw": raw_json,
            "json_2_structured": structured_json
        }
    
    def translate_json(self, ocr_text: str) -> str:
        """
        Traduce el texto del OCR (placeholder para traducción).
        
        Args:
            ocr_text: Texto en idioma original
            
        Returns:
            Texto traducido (implementación futura)
        """
        # TODO: Implementar traducción con Gemini o servicio externo
        return ocr_text
    
    def add_translation_to_structured(self, structured_json: Dict, 
                                     translated_text: str) -> Dict:
        """
        Agrega traducción al JSON estructurado.
        
        Args:
            structured_json: JSON 2 sin traducción
            translated_text: Texto traducido
            
        Returns:
            JSON 2 con traducción
        """
        if "hoja" in structured_json:
            structured_json["hoja"]["tJsonTraducido"] = translated_text
        
        return structured_json

