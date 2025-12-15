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
                "tJsonTraducido": hoja_data.get("tJsonTraducido"),  # Usar traducción de hoja_data
                "lFormato": hoja_data.get("lFormato"),
                "iMIdioma": hoja_data.get("iMIdioma"),
                "iMDocumentoTipo": hoja_data.get("iMDocumentoTipo"),
                "tSequentialNumber": hoja_data.get("tSequentialNumber")
            }
        }
        
        # Tablas principales (datos de transacción) - irán al nivel raíz
        default_tables = {
            "mresumen": [],
            "mcomprobante": [],
            "mcomprobante_detalle": [],
            "mjornada": [],
            "mjornada_empleado": [],
            "mproveedor": [],
            "mmaquinaria_equipos": []
        }
        
        # Tablas ancla (catálogos/referencia) - se usarán para agregar a mcomprobante_detalle
        catalog_keys = [
            "marchivo_tipo",
            "mdivisa",
            "mdocumento_tipo",
            "midioma",
            "mnaturaleza",
            "munidad_medida",
            "mdepartamento",
            "mdisciplina"
        ]
        
        # Extraer catálogos de additional_data si existen
        catalogos = {}
        if additional_data:
            for catalog_key in catalog_keys:
                if catalog_key in additional_data:
                    catalogos[catalog_key] = additional_data[catalog_key]
        
        # Si hay datos adicionales, fusionarlos directamente en el nivel raíz (sin additional_data)
        if additional_data:
            for key, value in additional_data.items():
                # Solo agregar tablas principales, no catálogos (ya los extrajimos arriba)
                if key not in catalog_keys:
                    json_2[key] = value
        
        # Asegurar que todas las tablas principales estén presentes (incluso si vacías)
        for table_name, default_value in default_tables.items():
            if table_name not in json_2:
                json_2[table_name] = default_value
        
        # CRITICAL: Agregar catálogos dentro de cada mcomprobante_detalle
        if "mcomprobante_detalle" in json_2 and isinstance(json_2["mcomprobante_detalle"], list):
            for item in json_2["mcomprobante_detalle"]:
                if isinstance(item, dict):
                    # Agregar objeto catalogos dentro de cada item
                    item["catalogos"] = catalogos.copy() if catalogos else {}
        
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

