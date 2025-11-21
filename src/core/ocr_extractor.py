"""
OCR Extractor Module - Coordinador principal
Responsabilidad: Orquestar el proceso completo de OCR
"""

from typing import List, Dict, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

from .pdf_processor import PDFProcessor
from .file_manager import FileManager
from .json_parser import JSONParser


class OCRExtractor:
    """
    Extractor principal de OCR.
    
    Responsabilidades:
    - Coordinar PDF → Imágenes → OCR → JSON
    - Orquestar todos los módulos core
    """
    
    def __init__(self, gemini_service, data_mapper, max_workers: int = 7):
        """
        Inicializa el extractor OCR.
        
        Args:
            gemini_service: Servicio de Gemini
            data_mapper: Mapeador de datos
            max_workers: Número de hilos para procesamiento paralelo (por defecto 7)
        """
        self.gemini_service = gemini_service
        self.data_mapper = data_mapper
        self.max_workers = max_workers
        
        self.pdf_processor = PDFProcessor()
        self.file_manager = FileManager()
        self.json_parser = JSONParser()
        
        self._progress_lock = threading.Lock()
        self._completed_pages = 0
    
    def process_pdf(self, pdf_path: str, progress_callback=None, max_pages: int = None) -> List[Dict[str, Any]]:
        """
        Procesa un PDF completo generando JSON por página.
        
        Args:
            pdf_path: Ruta al PDF
            progress_callback: Función para actualizar progreso (message, percentage)
            max_pages: Número máximo de páginas a procesar (None = todas)
            
        Returns:
            Lista de JSON por página
        """
        # 1. Dividir PDF en imágenes
        if progress_callback:
            msg = f"Dividiendo PDF en páginas..." + (f" (max: {max_pages})" if max_pages else "")
            progress_callback(msg, 0)
        
        temp_folder = self.file_manager.get_temp_folder()
        pages = self.pdf_processor.process_pdf_to_images(pdf_path, temp_folder, max_pages)
        
        total_pages = len(pages)
        pdf_name = Path(pdf_path).stem
        
        if progress_callback:
            progress_callback(f"PDF dividido en {total_pages} página(s)", 5)
        
        # 2. Procesar páginas en paralelo con ThreadPoolExecutor
        self._completed_pages = 0
        results = []
        
        # Usar diccionario para mantener orden de resultados
        result_dict = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Enviar todas las tareas al pool
            future_to_page = {
                executor.submit(self._process_single_page, img_path, page_num, pdf_name): (page_num, img_path)
                for page_num, img_path in pages
            }
            
            # Procesar resultados conforme van completándose
            for future in as_completed(future_to_page):
                page_num, img_path = future_to_page[future]
                
                try:
                    page_result = future.result()
                    
                    if page_result:
                        result_dict[page_num] = page_result
                    
                    # Actualizar progreso
                    with self._progress_lock:
                        self._completed_pages += 1
                        
                        if progress_callback:
                            percentage = 10 + (self._completed_pages * 80 // total_pages)
                            progress_callback(
                                f"Página {page_num} completada ({self._completed_pages}/{total_pages})",
                                percentage
                            )
                    
                    # Limpiar imagen temporal
                    self.file_manager.delete_temp_file(img_path)
                    
                except Exception as e:
                    print(f"Error procesando página {page_num}: {e}")
                    self.file_manager.delete_temp_file(img_path)
        
        # Ordenar resultados por número de página
        for page_num in sorted(result_dict.keys()):
            results.append(result_dict[page_num])
        
        if progress_callback:
            progress_callback(f"Procesamiento completado: {len(results)} páginas procesadas", 100)
        
        return results
    
    def _process_single_page(self, img_path: Path, 
                            page_num: int, pdf_name: str) -> Optional[Dict]:
        """
        Procesa una sola página.
        
        Args:
            img_path: Ruta a la imagen
            page_num: Número de página
            pdf_name: Nombre del PDF
            
        Returns:
            JSON de la página o None si hay error
        """
        try:
            # NUEVO ENFOQUE: Intentar extracción estructurada directa desde imagen
            # Si falla, usar método tradicional como fallback
            # Leer configuración desde config.json
            use_structured_extraction = True  # Por defecto habilitado
            try:
                import json
                from pathlib import Path
                config_path = Path("config/config.json")
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    gemini_config = config.get("gemini", {})
                    use_structured_extraction = gemini_config.get("use_structured_extraction", True)
            except Exception:
                pass  # Si falla la lectura, usar valor por defecto
            
            if use_structured_extraction and hasattr(self.gemini_service, 'extract_structured_data_from_image'):
                try:
                    # 1. Extracción estructurada directa (OCR + estructuración en una llamada)
                    structured_result = self.gemini_service.extract_structured_data_from_image(
                        str(img_path)
                    )
                    
                    if structured_result and structured_result.get("success"):
                        # Extraer datos del resultado estructurado
                        ocr_text = structured_result.get("text", "")
                        translated_text = structured_result.get("translated_text", ocr_text)  # Texto traducido de Gemini
                        document_type = structured_result.get("document_type", "unknown")
                        gemini_structured_data = structured_result.get("structured_data", {})
                        
                        # Crear resultado OCR compatible con formato anterior
                        ocr_result = {
                            "success": True,
                            "text": ocr_text,
                            "model": structured_result.get("model", self.gemini_service.model_name),
                            "timestamp": structured_result.get("timestamp", time.time())
                        }
                        
                        # 2. Crear JSON 1 (Raw)
                        raw_json = self.json_parser.create_raw_json(
                            ocr_result, page_num, pdf_name
                        )
                        
                        # 3. Mapear a estructura usando data_mapper (para validación y limpieza)
                        hoja_data = self.data_mapper.map_to_hoja_structure(ocr_result)
                        
                        # 4. Combinar datos estructurados de Gemini con validación de data_mapper
                        # El data_mapper ahora actúa como validador/limpiador
                        additional_data = self.data_mapper.validate_and_enhance_structured_data(
                            gemini_structured_data, ocr_text, document_type
                        )
                        
                        if additional_data is None:
                            additional_data = {}
                        
                        # 5. Usar texto traducido de Gemini (ya viene traducido si era necesario)
                        # Gemini ya tradujo el texto si no era inglés/español
                        hoja_data["tJsonTraducido"] = translated_text
                        
                        # Saltar al flujo común (pero ya tenemos la traducción)
                        # No ejecutar el método tradicional
                        
                    else:
                        # Si falla la extracción estructurada, usar método tradicional
                        print(f"Advertencia: Extracción estructurada falló para página {page_num}, usando método tradicional")
                        use_structured_extraction = False
                        
                except Exception as e:
                    # Si hay error, usar método tradicional
                    print(f"Advertencia: Error en extracción estructurada para página {page_num}: {e}. Usando método tradicional.")
                    use_structured_extraction = False
            
            # MÉTODO TRADICIONAL (fallback o si está deshabilitado)
            if not use_structured_extraction:
                # 1. OCR con Gemini
                ocr_result = self.gemini_service.process_image_with_retry(
                    str(img_path)
                )
                
                # Si el OCR falla, crear un resultado vacío pero válido
                if not ocr_result or not ocr_result.get("success"):
                    print(f"Advertencia: OCR falló para página {page_num}, generando JSON vacío")
                    # Crear resultado OCR vacío pero válido
                    ocr_result = {
                        "success": False,
                        "text": "",
                        "model": self.gemini_service.model_name if hasattr(self.gemini_service, 'model_name') else "unknown",
                        "error": ocr_result.get("error") if ocr_result else "OCR failed"
                    }
                
                # 2. Crear JSON 1 (Raw) - siempre se crea, aunque esté vacío
                raw_json = self.json_parser.create_raw_json(
                    ocr_result, page_num, pdf_name
                )
                
                # 3. Mapear a estructura - siempre se mapea, aunque el texto esté vacío
                hoja_data = self.data_mapper.map_to_hoja_structure(ocr_result)
                
                # 4. Extraer datos estructurados según tipo - siempre retorna dict (puede estar vacío)
                ocr_text = ocr_result.get("text", "")
                document_type = self.data_mapper.identify_document_type(ocr_text)
                additional_data = self.data_mapper.extract_structured_data(ocr_text, document_type)
                # Asegurar que additional_data nunca sea None
                if additional_data is None:
                    additional_data = {}
            
            # 5. Traducir si es necesario (solo si NO es español ni inglés)
            # NOTA: Si usamos extracción estructurada, la traducción ya viene de Gemini
            # Solo traducir si usamos el método tradicional
            if "tJsonTraducido" not in hoja_data:
                language_code = hoja_data.get("_language_code", "en")
                translated_text = None
                
                if language_code not in ['es', 'en'] and ocr_text:
                    try:
                        translated_text = self.gemini_service.translate_text(ocr_text, language_code)
                        hoja_data["tJsonTraducido"] = translated_text if translated_text else ocr_text
                    except Exception:
                        # Si falla la traducción, usar texto original
                        hoja_data["tJsonTraducido"] = ocr_text
                else:
                    # Español e inglés no se traducen, se mantienen igual
                    hoja_data["tJsonTraducido"] = ocr_text
            
            # 6. Limpiar campo temporal antes de crear JSON
            if "_language_code" in hoja_data:
                del hoja_data["_language_code"]
            
            # 7. Crear JSON 2 (Structured) - siempre se crea, aunque esté vacío
            structured_json = self.json_parser.create_structured_json(hoja_data, additional_data)
            
            # 8. Validar y registrar errores si learning está activo
            if hasattr(self, '_error_tracker') and self._error_tracker:
                try:
                    self._validate_and_record_errors(
                        pdf_name, page_num, ocr_text, structured_json, additional_data
                    )
                except Exception:
                    pass  # Si falla el registro, continuar normalmente
            
            # 9. JSON completo por página - siempre se retorna
            page_json = self.json_parser.create_page_json(
                pdf_name, page_num, raw_json, structured_json
            )
            
            return page_json
            
        except Exception as e:
            print(f"Error procesando página {page_num}: {e}")
            
            # Registrar error de parsing si learning está activo
            try:
                if hasattr(self, '_error_tracker') and self._error_tracker:
                    self._error_tracker.record_parse_error(
                        pdf_name=pdf_name,
                        page_num=page_num,
                        error_message=str(e),
                        exception=e,
                        ocr_text=None
                    )
            except Exception:
                pass  # Si falla el registro, continuar normalmente
            
            # IMPORTANTE: Aunque haya error, generar JSON vacío en lugar de None
            try:
                # Crear resultado OCR vacío para error
                ocr_result_error = {
                    "success": False,
                    "text": "",
                    "model": self.gemini_service.model_name if hasattr(self.gemini_service, 'model_name') else "unknown",
                    "error": str(e)
                }
                
                # Crear JSON 1 (Raw) vacío
                raw_json = self.json_parser.create_raw_json(
                    ocr_result_error, page_num, pdf_name
                )
                
                # Crear estructura hoja vacía
                hoja_data = self.data_mapper.map_to_hoja_structure(ocr_result_error)
                hoja_data["tJsonTraducido"] = ""
                
                # Limpiar campo temporal
                if "_language_code" in hoja_data:
                    del hoja_data["_language_code"]
                
                # Crear JSON 2 (Structured) vacío
                structured_json = self.json_parser.create_structured_json(hoja_data, {})
                
                # Retornar JSON completo (aunque vacío)
                page_json = self.json_parser.create_page_json(
                    pdf_name, page_num, raw_json, structured_json
                )
                
                return page_json
            except Exception as inner_e:
                # Si incluso la generación de JSON vacío falla, retornar None como último recurso
                print(f"Error crítico generando JSON vacío para página {page_num}: {inner_e}")
                return None
    
    def _validate_and_record_errors(self,
                                   pdf_name: str,
                                   page_num: int,
                                   ocr_text: str,
                                   structured_json: Dict,
                                   additional_data: Optional[Dict]):
        """
        Valida los datos extraídos y registra errores si learning está activo.
        
        Args:
            pdf_name: Nombre del PDF
            page_num: Número de página
            ocr_text: Texto OCR extraído
            structured_json: JSON estructurado
            additional_data: Datos adicionales extraídos
        """
        if not hasattr(self, '_error_tracker') or not self._error_tracker:
            return
        
        try:
            # Validar campos principales en hoja
            hoja = structured_json.get("hoja", {})
            
            # Validar tSequentialNumber (debería estar si hay stamp)
            if not hoja.get("tSequentialNumber"):
                # Solo registrar si hay texto que sugiere que debería haber un sequential number
                if ocr_text and any(stamp in ocr_text.upper() for stamp in ['BSQE', 'OTEM', 'OTRE', 'OTRU']):
                    self._error_tracker.record_missing_field(
                        pdf_name=pdf_name,
                        page_num=page_num,
                        field_name="tSequentialNumber",
                        expected_value=None,
                        ocr_text=ocr_text,
                        extracted_data={"hoja": hoja}
                    )
            
            # Validar datos adicionales según tipo de documento
            if additional_data:
                document_type_id = hoja.get("iMDocumentoTipo", 0)
                
                # Validar comprobante
                if document_type_id == 1:  # Comprobante
                    comprobante_list = additional_data.get("mcomprobante", [])
                    if comprobante_list:
                        comprobante = comprobante_list[0]
                        
                        # Validar tNumero
                        if not comprobante.get("tNumero"):
                            self._error_tracker.record_missing_field(
                                pdf_name=pdf_name,
                                page_num=page_num,
                                field_name="tNumero",
                                expected_value=None,
                                ocr_text=ocr_text,
                                extracted_data={"comprobante": comprobante}
                            )
                        
                        # Validar nPrecioTotal (debería existir y ser razonable)
                        precio_total = comprobante.get("nPrecioTotal")
                        if precio_total is not None:
                            # Valores sospechosamente bajos pueden indicar error de parsing
                            if precio_total < 0.01:
                                self._error_tracker.record_incorrect_value(
                                    pdf_name=pdf_name,
                                    page_num=page_num,
                                    field_name="nPrecioTotal",
                                    extracted_value=precio_total,
                                    expected_value=None,
                                    reason="Valor sospechosamente bajo (< 0.01)",
                                    ocr_text=ocr_text,
                                    extracted_data={"comprobante": comprobante}
                                )
                        
                        # Validar mcomprobante_detalle (debería tener items si es comprobante)
                        detalles = additional_data.get("mcomprobante_detalle", [])
                        if not detalles and precio_total and precio_total > 10:
                            # Si hay un total pero no hay detalles, puede ser un error
                            self._error_tracker.record_missing_field(
                                pdf_name=pdf_name,
                                page_num=page_num,
                                field_name="mcomprobante_detalle",
                                expected_value="Lista de items",
                                ocr_text=ocr_text,
                                extracted_data={"comprobante": comprobante}
                            )
                
                # Validar resumen
                elif document_type_id == 2:  # Resumen
                    resumen_list = additional_data.get("mresumen", [])
                    if not resumen_list:
                        # Si es resumen pero no hay items, puede ser error
                        self._error_tracker.record_missing_field(
                            pdf_name=pdf_name,
                            page_num=page_num,
                            field_name="mresumen",
                            expected_value="Lista de items de resumen",
                            ocr_text=ocr_text,
                            extracted_data=additional_data
                        )
                
                # Validar divisa
                divisas = additional_data.get("mdivisa", [])
                if not divisas:
                    # Si hay montos pero no hay divisa, puede ser error
                    if ocr_text and any(keyword in ocr_text.upper() for keyword in ['TOTAL', 'AMOUNT', 'PRICE', 'COST']):
                        self._error_tracker.record_missing_field(
                            pdf_name=pdf_name,
                            page_num=page_num,
                            field_name="mdivisa",
                            expected_value="USD, PEN, RM, etc.",
                            ocr_text=ocr_text,
                            extracted_data=additional_data
                        )
        
        except Exception:
            # Si falla la validación, no afectar el flujo normal
            pass
    
    def save_results(self, results: List[Dict], pdf_name: str) -> None:
        """
        Guarda los JSONs generados.
        
        Args:
            results: Lista de resultados por página
            pdf_name: Nombre del PDF
        """
        for page_result in results:
            page_num = page_result.get("page_number")
            
            # Guardar JSON 1
            raw_filename = f"{pdf_name}_page_{page_num}_raw.json"
            self.file_manager.save_json(
                page_result.get("json_1_raw"), 
                raw_filename, 
                subfolder="raw"
            )
            
            # Guardar JSON 2
            struct_filename = f"{pdf_name}_page_{page_num}_structured.json"
            self.file_manager.save_json(
                page_result.get("json_2_structured"),
                struct_filename,
                subfolder="structured"
            )
            
            print(f"JSONs guardados para página {page_num}")

