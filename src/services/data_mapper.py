"""
Data Mapper Module - Mapeo de datos extraídos a estructura SQL
Responsabilidad: Transformar JSON OCR a estructura de BD
"""

from typing import Dict, List, Optional, Any
import re
from decimal import Decimal


class DataMapper:
    """
    Mapeador de datos para estructura SQL.
    
    Responsabilidades:
    - Identificar tipo de documento
    - Extraer campos específicos
    - Mapear a estructura de BD
    """
    
    def __init__(self, gemini_service: Optional[Any] = None):
        """Inicializa el mapeador de datos.
        
        Args:
            gemini_service: Servicio de Gemini para inferencias de respaldo.
        """
        self.stamp_patterns = self._initialize_patterns()
        self.gemini_service = gemini_service
    
    def _initialize_patterns(self) -> Dict[str, List[str]]:
        """Inicializa patrones de reconocimiento."""
        return {
            "comprobante": [
                "invoice", "factura", "boleta", "bill", "recibo",
                "fattura", "invoice no",
                # Encabezados comunes en boletas/recibos malayos/chinos
                "tarikh", "kuantiti", "harga", "jumlah", "no.",
                "jumlah/", "總計", "总计", "cash / invoice", "cash/invoice",
                # Encabezados de tablas en español
                "cant.", "descripción", "precio unitario", "importe"
            ],
            "resumen": [
                "summary", "resumen", "consolidado", 
                "reimbursable expenditure"
            ],
            "jornada": [
                "empl no", "full name", "labor",
                "total hours", "employee", "empl"
            ],
            "expense_report": [
                "bechtel expense report", "expense report",
                "report key", "report number", "report date",
                "bechexprpt", "report purpose", "bechtel owes",
                "concur expense", "concur"
            ]
        }
    
    def identify_document_type(self, ocr_text: str) -> str:
        """Identifica el tipo de documento según su contenido."""
        text_lower = ocr_text.lower()
        
        # Priorizar "ATTACHMENT TO INVOICE" como comprobante (es un anexo de factura, no un expense report)
        if "attachment to invoice" in text_lower:
            return "comprobante"
        
        # Priorizar Expense Report (OnShore) antes de otros tipos
        # Verificar si es Concur Expense específicamente
        if "concur expense" in text_lower:
            return "concur_expense"
        elif any(pattern in text_lower for pattern in self.stamp_patterns["expense_report"]):
            return "expense_report"
        elif any(pattern in text_lower for pattern in self.stamp_patterns["comprobante"]):
            return "comprobante"
        elif any(pattern in text_lower for pattern in self.stamp_patterns["resumen"]):
            return "resumen"
        elif any(pattern in text_lower for pattern in self.stamp_patterns["jornada"]):
            return "jornada"
        
        return "unknown"
    
    def extract_stamp_info(self, ocr_text: str) -> Dict[str, Optional[str]]:
        """Extrae información de Stamp Name y Sequential Number."""
        stamp_name = None
        sequential_number = None
        
        # MEJORA: Buscar stamp name y sequential number en líneas separadas también
        # Buscar stamp name (puede estar en línea separada del número)
        stamp_match = re.search(r'(BSQE|OTEM|OTRE|OTRU)', ocr_text, re.IGNORECASE)
        if stamp_match:
            stamp_name = stamp_match.group(1).upper()
        
        # Buscar sequential number - mejorar para capturar cuando está en línea separada
        # Patrón 1: En la misma línea (BSQE1234, OE0001, etc.)
        seq_match = re.search(r'\b(BS|OE|OR|ORU)(\d{4,})\b', ocr_text, re.IGNORECASE)
        if seq_match:
            sequential_number = f"{seq_match.group(1).upper()}{seq_match.group(2)}"
        else:
            # Patrón 2: En líneas separadas (OTEM\nOE0001) - buscar cerca del stamp name
            if stamp_name:
                # Buscar número cerca del stamp (dentro de 200 caracteres)
                stamp_pos = stamp_match.end() if stamp_match else 0
                text_after_stamp = ocr_text[max(0, stamp_pos):min(len(ocr_text), stamp_pos + 200)]
                seq_match_separated = re.search(r'\b(BS|OE|OR|ORU)(\d{4,})\b', text_after_stamp, re.IGNORECASE)
                if seq_match_separated:
                    sequential_number = f"{seq_match_separated.group(1).upper()}{seq_match_separated.group(2)}"
                else:
                    # Patrón 3: Buscar cualquier número de 4+ dígitos cerca de stamp name
                    number_near_stamp = re.search(r'\b(\d{4,})\b', text_after_stamp)
                    if number_near_stamp and stamp_name:
                        # Si encontramos stamp pero no el código, intentar construir desde stamp
                        # Por ejemplo: OTEM -> OE, OTRE -> OR
                        stamp_to_code = {
                            'BSQE': 'BS',
                            'OTEM': 'OE',
                            'OTRE': 'OR',
                            'OTRU': 'ORU'
                        }
                        code = stamp_to_code.get(stamp_name, stamp_name[:2])
                        sequential_number = f"{code}{number_near_stamp.group(1)}"
        
        return {
            "stamp_name": stamp_name,
            "sequential_number": sequential_number
        }
    
    def map_to_hoja_structure(self, ocr_data: Dict) -> Dict[str, Any]:
        """Mapea datos OCR a estructura de MHOJA."""
        ocr_text = ocr_data.get("text", "")
        
        document_type = self.identify_document_type(ocr_text)
        stamp_info = self.extract_stamp_info(ocr_text)
        
        language_code = self._detect_language(ocr_text)
        
        return {
            "tJson": ocr_text,
            "tJsonTraducido": None,  # Se llenará después si es necesario
            "lFormato": self._determine_format(document_type),
            "iMIdioma": self._get_language_id(language_code),
            "iMDocumentoTipo": self._get_document_type_id(document_type),
            "tSequentialNumber": stamp_info.get("sequential_number"),
            "_language_code": language_code  # Guardar código para usar en traducción
        }
    
    def _determine_format(self, doc_type: str) -> bool:
        """Determina si es formato de resumen (True) o detalle (False)."""
        return doc_type == "resumen"
    
    def _detect_language(self, text: str) -> str:
        """
        Detecta el idioma del texto.
        
            Returns:
            str: 'es' (español), 'en' (inglés), 'it' (italiano), 'zh' (chino), 'other' (otros idiomas)
        """
        text_lower = text.lower()
        
        # Palabras comunes en español
        spanish_words = ['factura', 'boleta', 'servicios', 'empresa', 'cliente',
                        'proveedor', 'total', 'fecha', 'descripción', 'cantidad',
                        'precio', 'impuesto', 'jornada', 'empleado']
        
        # Palabras comunes en inglés
        english_words = ['invoice', 'summary', 'bill', 'services', 'company',
                        'client', 'supplier', 'total', 'date', 'description',
                        'quantity', 'price', 'tax', 'labor', 'employee',
                        'arrival', 'departure', 'charge', 'payment']
        
        # Palabras comunes en italiano
        italian_words = ['fattura', 'servizi', 'azienda', 'cliente', 'fornitore',
                        'totale', 'data', 'descrizione', 'quantità', 'prezzo',
                        'imposta', 'giornata', 'dipendente']
        
        # Palabras comunes en malayo
        malay_words = ['tarikh', 'jumlah', 'terima', 'disahkan', 'makan', 
                      'kuantiti', 'harga', 'barang']
        
        # Detectar caracteres chinos/japoneses
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
        
        # Contar ocurrencias
        spanish_count = sum(1 for word in spanish_words if word in text_lower)
        english_count = sum(1 for word in english_words if word in text_lower)
        italian_count = sum(1 for word in italian_words if word in text_lower)
        malay_count = sum(1 for word in malay_words if word in text_lower)
        
        # Determinar idioma por mayor cantidad de matches
        # Prioridad: Chino primero si tiene caracteres chinos
        if has_chinese:
            return 'zh'  # Chino
        elif malay_count > 2:
            return 'other'  # Malayo/otros idiomas asiáticos
        elif italian_count > 2:
            return 'it'  # Italiano
        elif spanish_count > english_count and spanish_count > 2:
            return 'es'  # Español
        elif english_count > spanish_count and english_count > 2:
            return 'en'  # Inglés
        elif spanish_count > 0:
            return 'es'
        elif english_count > 0:
            return 'en'
        else:
            return 'other'  # Otro idioma
    
    def _get_language_id(self, language_code: str) -> int:
        """Convierte código de idioma a ID de BD."""
        language_map = {
            'es': 1,  # Español
            'en': 2,  # Inglés
            'it': 3,  # Italiano
            'zh': 5,  # Chino
            'other': 4  # Otro
        }
        return language_map.get(language_code, 4)
    
    def _get_document_type_id(self, doc_type: str) -> int:
        """Retorna el ID del tipo de documento."""
        type_map = {
            "comprobante": 1,
            "resumen": 2,
            "jornada": 3,
            "expense_report": 4,  # Bechtel Expense Report (OnShore)
            "concur_expense": 4,  # Concur Expense Report (también es tipo Expense Report)
            "unknown": 99
        }
        return type_map.get(doc_type, 99)
    
    def extract_structured_data(self, ocr_text: str, doc_type: str) -> Optional[Dict]:
        """
        Extrae datos estructurados según el tipo de documento.
        
        Args:
            ocr_text: Texto extraído del OCR
            doc_type: Tipo de documento identificado
            
        Returns:
            Diccionario con datos estructurados según tipo + tablas ancla
        """
        result = {}
        
        # Verificar si es GL Journal Details con cálculo destacado ANTES de extraer datos por tipo
        is_gl_journal = 'gl journal details'.lower() in ocr_text.lower()
        has_highlighted_calc = bool(re.search(r'USD\s+[\d,]+\.\d{2}\s*\+\s*USD\s+[\d,]+\.\d{2}\s*\+\s*USD\s+[\d,]+\.\d{2}\s*=\s*USD\s+[\d,]+\.\d{2}', ocr_text, re.IGNORECASE))
        
        # Si es GL Journal Details con cálculo destacado, NO extraer datos por tipo (solo valores destacados)
        if not (is_gl_journal and has_highlighted_calc):
            # Extraer datos específicos según tipo
            if doc_type == "concur_expense":
                concur_data = self._extract_concur_expense_data(ocr_text)
                if concur_data:
                    result.update(concur_data)
            elif doc_type == "expense_report":
                expense_report_data = self._extract_expense_report_data(ocr_text)
                if expense_report_data:
                    result.update(expense_report_data)
            elif doc_type == "resumen":
                resumen_data = self._extract_resumen_data(ocr_text)
                if resumen_data:
                    result.update(resumen_data)
            elif doc_type == "comprobante":
                comprobante_data = self._extract_comprobante_data(ocr_text)
                if comprobante_data:
                    result.update(comprobante_data)
            elif doc_type == "jornada":
                jornada_data = self._extract_jornada_data(ocr_text)
                if jornada_data:
                    result.update(jornada_data)

        # Si el documento contiene "GL Journal Details", verificar si hay cálculo destacado
        # Si hay cálculo destacado, SOLO extraer esos valores (no todo el documento)
        # (is_gl_journal y has_highlighted_calc ya están definidos arriba)
        
        # Si es GL Journal Details con cálculo destacado, NO extraer todo el documento
        # Solo extraeremos los valores destacados en highlighted_calculations más adelante
        if is_gl_journal and has_highlighted_calc:
            # NO extraer journal_items ni resumen_data completo
            # Solo extraeremos los valores destacados
            pass
        elif is_gl_journal:
            # Si es GL Journal Details pero sin cálculo destacado, extraer líneas como detalle
            journal_items = self._extract_journal_details_items(ocr_text)
            if journal_items:
                # No sobrescribir si ya existen, concatenar
                if 'mcomprobante_detalle' in result:
                    result['mcomprobante_detalle'].extend(journal_items)
                else:
                    result['mcomprobante_detalle'] = journal_items
        
        # Extraer información de tablas ancla (siempre)
        catalog_data = self._extract_catalog_data(ocr_text, doc_type)
        if catalog_data:
            result.update(catalog_data)
        
        # Extraer departamentos y disciplinas para documentos OnShore
        if doc_type in ["expense_report", "concur_expense"]:
            dept_disc_data = self._extract_departments_and_disciplines(ocr_text)
            if dept_disc_data:
                # Agregar a result sin sobrescribir datos existentes
                for key, value in dept_disc_data.items():
                    if key not in result:
                        result[key] = value
                    elif isinstance(result[key], list) and isinstance(value, list):
                        result[key].extend(value)
        
        # Extraer cálculos destacados (cuadros rojos, boxes, etc.)
        highlighted_calculations = self._extract_highlighted_calculations(ocr_text)
        
        # Para documentos jornada, también extraer valores destacados de filas "Total"
        if doc_type == "jornada":
            jornada_highlights = self._extract_jornada_highlighted_values(ocr_text)
            if jornada_highlights:
                highlighted_calculations.extend(jornada_highlights)
        
        # Si es GL Journal Details con cálculo destacado, extraer SOLO los valores destacados
        if is_gl_journal and has_highlighted_calc:
            # Extraer valores individuales del cálculo destacado
            gl_highlighted_values = self._extract_gl_journal_highlighted_values(ocr_text)
            if gl_highlighted_values:
                highlighted_calculations.extend(gl_highlighted_values)
        
        if highlighted_calculations:
            # Agregar a mresumen si está vacío o crear campo específico
            if 'mresumen' not in result or not result.get('mresumen'):
                result['mresumen'] = highlighted_calculations
            else:
                # Agregar a mresumen existente
                result['mresumen'].extend(highlighted_calculations)
        
        # Extracción general de valores monetarios (para cualquier tipo de documento)
        # Esto captura TODOS los valores económicos, sin importar el formato
        # EXCEPCIÓN: Para documentos jornada, comprobante o GL Journal Details con valores destacados (rectángulo rojo),
        # NO extraer todos los valores, solo usar los destacados que ya están en mresumen
        general_monetary_values = []
        has_highlighted_total = any(calc.get("_total_highlighted", False) or calc.get("_highlighted", False) for calc in highlighted_calculations)
        
        # Si es GL Journal Details con cálculo destacado, NO extraer todos los valores
        if (is_gl_journal and has_highlighted_calc) or (doc_type == "jornada" and highlighted_calculations) or (doc_type == "comprobante" and has_highlighted_total):
            # Si tiene valores destacados, NO extraer todos los valores
            # Solo usar los valores destacados que ya están en mresumen
            pass  # No ejecutar _extract_all_monetary_values
        else:
            general_monetary_values = self._extract_all_monetary_values(ocr_text)
        if general_monetary_values:
            # Si no hay mcomprobante_detalle, crear uno con los valores encontrados
            if 'mcomprobante_detalle' not in result or not result.get('mcomprobante_detalle'):
                result['mcomprobante_detalle'] = general_monetary_values
            else:
                # Agregar valores que no estén duplicados
                existing_amounts = {item.get('nPrecioTotal', 0) for item in result.get('mcomprobante_detalle', [])}
                for item in general_monetary_values:
                    if item.get('nPrecioTotal', 0) not in existing_amounts:
                        result['mcomprobante_detalle'].append(item)
        
        # IMPORTANTE: Siempre retornar un diccionario, aunque esté vacío
        # Esto asegura que siempre se genere un JSON estructurado, incluso sin datos
        return result
    
    def _extract_catalog_data(self, ocr_text: str, doc_type: str = None) -> Dict:
        """Extrae información de tablas ancla/catálogo."""
        catalogs = {}
        
        # MIDIOMA - Agregar idioma detectado
        language_code = self._detect_language(ocr_text)
        language_id = self._get_language_id(language_code)
        language_names = {'es': 'Español', 'en': 'Inglés', 'it': 'Italiano', 'zh': 'Chino', 'other': 'Otro'}
        language_name = language_names.get(language_code, 'Otro')
        catalogs["midioma"] = [{
            "iMIdioma": language_id,
            "tIdioma": language_name
        }]
        
        # MDOCUMENTO_TIPO - Agregar tipo de documento detectado
        if doc_type:
            doc_type_id = self._get_document_type_id(doc_type)
            doc_type_names = {
                "comprobante": "Comprobante",
                "resumen": "Resumen",
                "jornada": "Jornada",
                "expense_report": "Expense Report",
                "concur_expense": "Concur Expense Report",
                "unknown": "Desconocido"
            }
            doc_type_name = doc_type_names.get(doc_type, "Desconocido")
            catalogs["mdocumento_tipo"] = [{
                "iMDocumentoTipo": doc_type_id,
                "tTipo": doc_type_name
            }]
        
        # MDIVISA - Detectar divisas en el texto
        # MEJORA: Basado en análisis - mejor detección de divisas (especialmente chinas)
        
        # Patrón 1: Divisas con espacio o límite de palabra (USD, PEN, etc.)
        all_divisas = re.findall(r'\b(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\b', ocr_text, re.IGNORECASE)
        # Patrón 2: Divisas seguidas directamente de números (USD6.40, RM25.50, etc.)
        direct_divisas = re.findall(r'\b(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)(\d)', ocr_text, re.IGNORECASE)
        for div, _ in direct_divisas:
            if div.upper() not in [d.upper() for d in all_divisas]:
                all_divisas.append(div)
        
        # Patrón 3: Símbolo $ seguido de montos (generalmente USD)
        dollar_sign_match = re.search(r'\$\s*[\d,]+(?:\.\d{2})?', ocr_text)
        if dollar_sign_match and 'USD' not in [d.upper() for d in all_divisas]:
            all_divisas.append('USD')
        
        # Patrón 4: Símbolo ¥ (yuan chino/japonés) - generalmente CNY para documentos chinos
        yuan_symbol_match = re.search(r'¥\s*[\d,]+(?:\.\d{2})?', ocr_text)
        if yuan_symbol_match and 'CNY' not in [d.upper() for d in all_divisas]:
            # Si hay caracteres chinos, es CNY; si hay caracteres japoneses, podría ser JPY
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', ocr_text))
            if has_chinese:
                all_divisas.append('CNY')
        
        # Patrón 5: Carácter "元" (yuan chino) - siempre CNY
        yuan_char_match = re.search(r'[\d,]+(?:\.\d{2})?\s*元', ocr_text)
        if yuan_char_match and 'CNY' not in [d.upper() for d in all_divisas]:
            all_divisas.append('CNY')
        
        # Patrón 6: "总计" o "金额" seguido de número y "元" (total en yuan)
        total_yuan_match = re.search(r'(?:总计|金额|总金额|合计)[:：]?\s*[\d,]+(?:\.\d{2})?\s*元', ocr_text)
        if total_yuan_match and 'CNY' not in [d.upper() for d in all_divisas]:
            all_divisas.append('CNY')
        
        # Patrón 7: Buscar divisa cerca del total (mejor precisión)
        total_divisa_patterns = [
            r'(?:Total|TOTAL|Amount|AMOUNT|总计|JUMLAH|金额|总金额)\s*(?:[:=]?\s*)?(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)',
            r'(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\s*(?:Total|TOTAL|Amount|AMOUNT|总计|金额)',
            r'(?:Total|TOTAL|总计|金额)\s*[\d,]+(?:\.\d{2})?\s*(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)',
            r'(?:总计|金额|总金额)[:：]?\s*[\d,]+(?:\.\d{2})?\s*元',  # Total en yuan chino
        ]
        for pattern in total_divisa_patterns:
            total_match = re.search(pattern, ocr_text, re.IGNORECASE)
            if total_match:
                # Si el patrón contiene "元", es CNY
                if '元' in total_match.group(0) and 'CNY' not in [d.upper() for d in all_divisas]:
                    all_divisas.append('CNY')
                elif total_match.lastindex:
                    div = total_match.group(1).upper()
                    if div not in [d.upper() for d in all_divisas]:
                        all_divisas.append(div)
                break
        
        divisas_unicas = []
        if all_divisas:
            # Convertir a mayúsculas y eliminar duplicados manteniendo orden
            divisas_unicas = []
            for d in all_divisas:
                d_upper = d.upper()
                if d_upper not in divisas_unicas:
                    divisas_unicas.append(d_upper)
            
            # Priorizar divisa del total (总计, JUMLAH, Total, etc.)
            # Buscar "总计" o "金额" con "元" (yuan chino)
            total_yuan_match = re.search(r'(?:总计|金额|总金额)[:：]?\s*[\d,]+(?:\.\d{2})?\s*元', ocr_text)
            if total_yuan_match and 'CNY' in divisas_unicas:
                divisas_unicas.remove('CNY')
                divisas_unicas.insert(0, 'CNY')
            else:
                total_divisa_match = re.search(r'(?:总计|JUMLAH|Total|TOTAL|Amount|AMOUNT|金额)\s*(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)', ocr_text, re.IGNORECASE)
                if total_divisa_match:
                    total_divisa = total_divisa_match.group(1).upper()
                    # Mover divisa del total al inicio si existe
                    if total_divisa in divisas_unicas:
                        divisas_unicas.remove(total_divisa)
                        divisas_unicas.insert(0, total_divisa)
            
            # Crear lista de divisas
            catalogs["mdivisa"] = [{"tDivisa": d} for d in divisas_unicas]
        else:
            # MEJORA: Si no hay divisa explícita, inferir desde contexto
            # 1. Si hay símbolo ¥ o carácter 元, asumir CNY (yuan chino)
            if re.search(r'[¥元]', ocr_text) or re.search(r'[\d,]+(?:\.\d{2})?\s*元', ocr_text):
                catalogs["mdivisa"] = [{"tDivisa": "CNY"}]
            # 2. Si hay símbolo $, asumir USD
            elif re.search(r'\$\s*[\d,]+', ocr_text):
                catalogs["mdivisa"] = [{"tDivisa": "USD"}]
            # 3. Si el texto está en chino y tiene valores numéricos, asumir CNY
            elif language_code == 'zh':
                has_monetary_values = (
                    re.search(r'[\d,]+(?:\.\d{2})?\s*元', ocr_text) or  # Números seguidos de 元
                    re.search(r'(?:总计|金额|总金额|合计)[:：]?\s*[\d,]+', ocr_text) or  # Totales en chino
                    re.search(r'¥\s*[\d,]+', ocr_text)  # Símbolo ¥
                )
                if has_monetary_values:
                    catalogs["mdivisa"] = [{"tDivisa": "CNY"}]
            # 4. Si el texto está en inglés y tiene valores numéricos, asumir USD
            elif language_code == 'en':
                # Verificar si hay valores numéricos que parezcan montos
                has_monetary_values = (
                    re.search(r'\b[\d,]+\.\d{2}\b', ocr_text) or  # Números con 2 decimales
                    re.search(r'(?:Total|Amount|Price|Cost|Fee|Charge)\s*[\d,]+', ocr_text, re.IGNORECASE)  # Palabras monetarias + números
                )
                if has_monetary_values:
                    catalogs["mdivisa"] = [{"tDivisa": "USD"}]
            # 5. Si el texto está en español y tiene valores, podría ser PEN o CLP
            elif language_code == 'es':
                has_monetary_values = (
                    re.search(r'\b[\d,]+\.\d{2}\b', ocr_text) or
                    re.search(r'(?:Total|Monto|Importe|Precio)\s*[\d,]+', ocr_text, re.IGNORECASE)
                )
                if has_monetary_values:
                    # Por defecto PEN para documentos en español (ajustable)
                    catalogs["mdivisa"] = [{"tDivisa": "PEN"}]
        
        # MIDIOMA - Ya está en hoja, pero podemos agregarlo aquí también si se necesita
        # (Se maneja en map_to_hoja_structure)

        # Fallback con Gemini para tablas ancla faltantes
        missing_anchor = any(key not in catalogs for key in ["mdivisa", "mproveedor", "mnaturaleza", "mdocumento_tipo"])
        if missing_anchor and self.gemini_service is not None:
            inferred = self.gemini_service.infer_anchor_tables(ocr_text)
            if isinstance(inferred, dict):
                # Mapear campos si están presentes y aún no definidos
                if "mdivisa" not in catalogs and inferred.get("mdivisa"):
                    try:
                        divs = inferred.get("mdivisa")
                        if isinstance(divs, list):
                            catalogs["mdivisa"] = [{"tDivisa": str(d).upper()} for d in divs]
                    except Exception:
                        pass
                if "mproveedor" not in catalogs and inferred.get("mproveedor"):
                    prov = inferred.get("mproveedor")
                    if isinstance(prov, dict) and prov.get("tRazonSocial"):
                        catalogs["mproveedor"] = [{"tRazonSocial": prov.get("tRazonSocial")}]
                    elif isinstance(prov, str):
                        catalogs["mproveedor"] = [{"tRazonSocial": prov}]
                if "mnaturaleza" not in catalogs and inferred.get("mnaturaleza"):
                    nats = inferred.get("mnaturaleza")
                    if isinstance(nats, list):
                        catalogs["mnaturaleza"] = [{"tNaturaleza": n} for n in nats]
                if "mdocumento_tipo" not in catalogs and inferred.get("mdocumento_tipo"):
                    tip = inferred.get("mdocumento_tipo")
                    # Aceptar string o dict {tTipo: "Comprobante"}
                    tipo_nombre = tip.get("tTipo") if isinstance(tip, dict) else str(tip)
                    if tipo_nombre:
                        catalogs["mdocumento_tipo"] = [{
                            "iMDocumentoTipo": self._get_document_type_id(tipo_nombre.lower()),
                            "tTipo": "Comprobante" if tipo_nombre.lower().startswith("comp") else (
                                "Resumen" if tipo_nombre.lower().startswith("resu") else (
                                    "Jornada" if tipo_nombre.lower().startswith("jor") else "Desconocido"
                                )
                            )
                        }]

        # MNATURALEZA - Detectar naturaleza del documento
        # Buscar palabras clave relacionadas con alimentación/comida al inicio del documento
        naturaleza_detectada = None
        lines_start = ocr_text[:500].upper()  # Primeras 500 caracteres
        alimentacion_keywords = ['MEAL', 'FOOD', 'ALIMENTACIÓN', 'ALIMENTACION', 'COMIDA', 
                                'RESTAURANT', 'RESTAURANTE', 'CAFE', 'CAFÉ', 'MENU', 'MENÚ',
                                'TAKEAWAY', 'DELIVERY', 'ORDER', 'PEDIDO']
        if any(keyword in lines_start for keyword in alimentacion_keywords):
            naturaleza_detectada = "Alimentación"
        
        # Si se detectó naturaleza, agregarla
        if naturaleza_detectada:
            catalogs["mnaturaleza"] = [{"tNaturaleza": naturaleza_detectada}]
        # Si aún no hay naturaleza, establecer por defecto "Otro" para no dejar vacío
        elif "mnaturaleza" not in catalogs:
            catalogs["mnaturaleza"] = [{"tNaturaleza": "Otro"}]

        # MDOCUMENTO_TIPO - Ya se detecta en identify_document_type
        # (Se maneja en map_to_hoja_structure)
        
        # MPROVEEDOR - Detectar información de proveedor/vendor
        # Primero buscar en sección "Supplier Data" o "Supplier Name"
        supplier_match = re.search(r'Supplier\s+Name[:\s]+([A-Z][A-Z\s&\.]{5,}(?:SDN\s+BHD|LLC|Inc|Company|S\.A\.|S\.L\.|SRL)?)', ocr_text, re.IGNORECASE)
        if supplier_match:
            vendor_name = supplier_match.group(1).strip()
            catalogs["mproveedor"] = [{"tRazonSocial": vendor_name}]
        else:
            # Buscar nombres de empresas/vendors comunes
            vendor_patterns = [
                r'Hawk\s+International',
                r'SGS[- ]?CSTC',
                r'The Light Hotel',
                r'BERJAYA\s+STARBUCKS\s+COFFEE',
                r'Bechtel',
                r'Starbucks'
            ]
            
            for pattern in vendor_patterns:
                vendor_match = re.search(pattern, ocr_text, re.IGNORECASE)
                if vendor_match:
                    # Intentar capturar nombre completo de la empresa
                    vendor_start = vendor_match.start()
                    vendor_line = ocr_text[max(0, vendor_start-50):vendor_start+100]
                    # Buscar nombre completo hasta SDN BHD, LLC, Inc, etc.
                    full_match = re.search(r'([A-Z][A-Z\s&\.]+(?:SDN\s+BHD|LLC|Inc|Company|S\.A\.|S\.L\.|SRL)?)', vendor_line, re.IGNORECASE)
                    if full_match:
                        vendor_name = full_match.group(1).strip()
                    else:
                        vendor_name = vendor_match.group(0)
                    catalogs["mproveedor"] = [{"tRazonSocial": vendor_name}]
                    break
            
            # Si no se encontró con patrones, buscar nombres de empresa al inicio del documento
            if "mproveedor" not in catalogs:
                lines = ocr_text.split('\n')
                for i, line in enumerate(lines[:10]):  # Buscar en primeras 10 líneas
                    line = line.strip()
                    # Buscar nombres que parecen empresas (múltiples palabras mayúsculas)
                    company_match = re.search(r'^([A-Z][A-Z\s&\.]{10,}(?:SDN\s+BHD|LLC|Inc|Company|S\.A\.|S\.L\.|SRL)?)', line)
                    if company_match:
                        vendor_name = company_match.group(1).strip()
                        catalogs["mproveedor"] = [{"tRazonSocial": vendor_name}]
                        break
        
        return catalogs
    
    def _extract_resumen_data(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """
        Extrae datos estructurados de documentos tipo RESUMEN.
        
        Args:
            ocr_text: Texto del OCR
            
        Returns:
            Diccionario con lista de registros MRESUMEN
        """
        resumen_items = []
        lines = ocr_text.split('\n')
        
        # Variables para tracking
        current_job_no = None
        current_type = None
        in_table = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detectar encabezado de tabla
            if 'Job No' in line and 'TYPE' in line:
                in_table = True
                continue
            
            # Detectar subtotales o totales
            if line.startswith('$') and ('TOTAL' in ocr_text[ocr_text.find(line)-100:ocr_text.find(line)].upper() or 
                                        'Supplier Quality' in line or 'Other Reimbursables' in line):
                continue
            
            if in_table and line:
                # Intentar parsear fila de tabla
                resumen_item = self._parse_resumen_row(line, current_job_no, current_type)
                
                if resumen_item:
                    # Actualizar job_no y type si están presentes
                    if resumen_item.get('tjobno'):
                        current_job_no = resumen_item['tjobno']
                    if resumen_item.get('ttype'):
                        current_type = resumen_item['ttype']
                    
                    resumen_items.append(resumen_item)
        
        return {"mresumen": resumen_items} if resumen_items else None
    
    def _parse_resumen_row(self, line: str, default_job_no: str = None, 
                          default_type: str = None) -> Optional[Dict]:
        """
        Parsea una fila de la tabla RESUMEN.
        
        Args:
            line: Línea de texto de la tabla
            default_job_no: Job No por defecto si no se encuentra en línea
            default_type: Type por defecto si no se encuentra en línea
            
        Returns:
            Diccionario con campos de MRESUMEN
        """
        # Buscar stamp name y sequential number
        stamp_match = re.search(r'\b(BSQE|OTEM|OTRE|OTRU)\b', line, re.IGNORECASE)
        stamp_name = stamp_match.group(1).upper() if stamp_match else None
        
        seq_match = re.search(r'\b(BS|OE|OR|ORU)(\d{4})\b', line, re.IGNORECASE)
        sequential_number = f"{seq_match.group(1).upper()}{seq_match.group(2)}" if seq_match else None
        
        # Buscar monto
        amount_match = re.search(r'\$\s*([\d,]+)', line)
        amount_str = amount_match.group(1).replace(',', '') if amount_match else None
        amount = float(amount_str) if amount_str else None
        
        # Buscar Job No (formato: 26442-OFFSHORE o similar)
        job_match = re.search(r'(\d+-[A-Z\-]+)', line)
        job_no = job_match.group(1) if job_match else default_job_no
        
        # Buscar Type (Supplier Quality, Other Reimbursables, etc.)
        type_match = re.search(r'Supplier Quality|Other Reimbursables', line, re.IGNORECASE)
        doc_type = type_match.group(0) if type_match else default_type
        
        # Extraer Source Reference y Source Ref ID
        # Patrón: números y letras separados por espacios al inicio
        parts = line.split()
        source_ref = None
        source_ref_id = None
        
        for i, part in enumerate(parts):
            # Buscar Source Reference (alphanuméricos largos)
            if re.match(r'^[A-Z0-9]{10,}', part):
                source_ref = part
                # El siguiente campo podría ser Source Ref ID
                if i + 1 < len(parts) and not parts[i+1].startswith('$'):
                    potential_id = ' '.join(parts[i+1:i+3]) if i+2 < len(parts) else parts[i+1]
                    if potential_id and len(potential_id) > 5:
                        source_ref_id = potential_id
                break
        
        # Extraer Description (texto entre Source Ref ID y monto)
        if stamp_name:
            description = stamp_name
        else:
            # Intentar extraer description del texto restante
            description_match = re.search(r'([A-Z][^$]+?)(?=\$|BSQE|OTEM|OTRE|OTRU)', line)
            description = description_match.group(1).strip() if description_match else None
        
        # Solo retornar si tenemos al menos algunos campos esenciales
        if stamp_name or sequential_number or amount:
            return {
                "tjobno": job_no,
                "ttype": doc_type,
                "tsourcereference": source_ref,
                "tsourcerefid": source_ref_id,
                "tdescription": description,
                "nImporte": amount,
                "tStampname": stamp_name,
                "tsequentialnumber": sequential_number
            }
        
        return None
    
    def _extract_comprobante_data(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """Extrae datos de comprobantes (facturas, boletas)."""
        comprobante_items = []
        comprobante = {}
        
        # Extraer Stamp Name y Sequential Number (si existen)
        stamp_info = self.extract_stamp_info(ocr_text)
        if stamp_info.get("stamp_name"):
            comprobante['_stamp_name'] = stamp_info["stamp_name"]
        if stamp_info.get("sequential_number"):
            comprobante['_sequential_number'] = stamp_info["sequential_number"]
        
        # Buscar número de factura/invoice (múltiples formatos)
        # MEJORA: Basado en análisis de errores - agregar más patrones (incluyendo chinos)
        comprobante['tNumero'] = None
        
        # Patrón 1: Source Ref (GL Journal Details) - ALTA PRIORIDAD
        source_ref_match = re.search(r'Source\s+Ref[:]\s*([A-Z0-9\-]+)', ocr_text, re.IGNORECASE)
        if source_ref_match:
            comprobante['tNumero'] = source_ref_match.group(1).strip()
        # Patrón 1.5: Oracle AP Invoice Num (formato F581-06891423)
        elif re.search(r'Invoice\s+Num[:\s]+([A-Z0-9\-]+)', ocr_text, re.IGNORECASE):
            invoice_num_match = re.search(r'Invoice\s+Num[:\s]+([A-Z0-9\-]+)', ocr_text, re.IGNORECASE)
            comprobante['tNumero'] = invoice_num_match.group(1).strip()
        # Patrón 2: Invoice Number: formato explícito
        elif re.search(r'Invoice\s+Number[:\s]+(\d+)', ocr_text, re.IGNORECASE):
            invoice_num_match = re.search(r'Invoice\s+Number[:\s]+(\d+)', ocr_text, re.IGNORECASE)
            comprobante['tNumero'] = invoice_num_match.group(1)
        else:
            # Patrón 2: BOLETA ELECTRÓNICA N° (formato chileno)
            boleta_match = re.search(r'BOLETA\s+ELECTR[ÓO]NICA\s+N°\s*(\d+)', ocr_text, re.IGNORECASE)
            if boleta_match:
                comprobante['tNumero'] = boleta_match.group(1)
            else:
                # Patrón 3: Números de factura chinos (发票号码)
                invoice_chinese_match = re.search(r'发票号码[:：]?\s*(\d{8,})', ocr_text)
                if invoice_chinese_match:
                    comprobante['tNumero'] = invoice_chinese_match.group(1)
                else:
                    # Patrón 4: Códigos de factura chinos (发票代码)
                    invoice_code_match = re.search(r'发票代码[:：]?\s*(\d{10,})', ocr_text)
                    if invoice_code_match:
                        comprobante['tNumero'] = invoice_code_match.group(1)
                    else:
                        # Patrón 5: N° seguido de número (formato genérico)
                        n_numero_match = re.search(r'N°\s*(\d{4,})', ocr_text, re.IGNORECASE)
                        if n_numero_match:
                            comprobante['tNumero'] = n_numero_match.group(1)
                        else:
                            # Patrón 6: Folio No. o Folio:
                            folio_match = re.search(r'Folio\s*(?:No\.?|:)?\s*(\d+)', ocr_text, re.IGNORECASE)
                            if folio_match:
                                comprobante['tNumero'] = folio_match.group(1)
                            else:
                                # Patrón 6.5: Recibo XXX (formato español)
                                recibo_match = re.search(r'Recibo\s+(\d+)', ocr_text, re.IGNORECASE)
                                if recibo_match:
                                    comprobante['tNumero'] = recibo_match.group(1)
                                else:
                                    # Patrón 6.7: FATTURA NO.: 333/25 (facturas italianas con formato específico)
                                    # El número puede estar en la misma línea o en la siguiente línea
                                    fattura_no_match = re.search(r'FATTURA\s+(?:NO\.?|No\.?|N°)\s*:?\s*([A-Z0-9/\-]+)', ocr_text, re.IGNORECASE)
                                    if fattura_no_match:
                                        comprobante['tNumero'] = fattura_no_match.group(1).strip()
                                    else:
                                        # Buscar "FATTURA NO.:" y luego buscar el número en las siguientes líneas (formato XXX/XX)
                                        fattura_header_match = re.search(r'FATTURA\s+(?:NO\.?|No\.?|N°)\s*:', ocr_text, re.IGNORECASE)
                                        if fattura_header_match:
                                            # Buscar después del header un número con formato XXX/XX o similar
                                            after_header = ocr_text[fattura_header_match.end():]
                                            # Buscar patrón de número con slash: "335/25" o "333/25"
                                            numero_match = re.search(r'(\d{2,4}/\d{1,3})', after_header[:200])  # Buscar en los siguientes 200 caracteres
                                            if numero_match:
                                                comprobante['tNumero'] = numero_match.group(1).strip()
                                    # Si aún no se encontró, intentar Patrón 7
                                    if not comprobante.get('tNumero'):
                                        # Patrón 7: INVOICE No. XXXX (evitando "Invoice Numb")
                                        invoice_match = None
                                        for m in re.finditer(r'(?:^|\s)(INVOICE|FATTURA|CASH|CASD|FACTURA|BOLETA|RECIBO)\s+(?:No\.?|NO\.?|N°|#)?\s*([A-Z0-9/\-]+)', ocr_text, re.IGNORECASE):
                                            if 'Numb' not in m.group(0):
                                                invoice_match = m
                                                break
                                        if invoice_match:
                                            comprobante['tNumero'] = invoice_match.group(2).strip()
                                        else:
                                            # Patrón 8: NO. seguido de número cerca de TOTAL
                                            no_total_match = re.search(r'NO\.\s+(\d{3,})\s+(?:总计|JUMLAH|TOTAL|Total)', ocr_text, re.IGNORECASE)
                                            if no_total_match:
                                                comprobante['tNumero'] = no_total_match.group(1)
                                            else:
                                                # Patrón 9: Palabras clave chinas con números (号码)
                                                chinese_num_match = re.search(r'(?:号码|发票号码|发票代码)[:：]?\s*(\d{8,})', ocr_text)
                                                if chinese_num_match:
                                                    comprobante['tNumero'] = chinese_num_match.group(1)
                                                else:
                                                    # Patrón 10: Patrones genéricos con palabras clave
                                                    generic_match = re.search(r'(?:总计|JUMLAH|No\.|NO\.|#)\s*([A-Z0-9\-]{4,})', ocr_text, re.IGNORECASE)
                                                    if generic_match and re.search(r'\d', generic_match.group(1)):
                                                        invoice_num = generic_match.group(1).strip()
                                                        if ' ' in invoice_num:
                                                            invoice_num = invoice_num.split()[0]
                                                        comprobante['tNumero'] = invoice_num
        
        # Buscar serie o código de contrato
        contract_match = re.search(r'Contract\s*no\s*(\d+)', ocr_text, re.IGNORECASE)
        comprobante['tSerie'] = contract_match.group(1) if contract_match else None
        
        # Buscar fecha de emisión (múltiples formatos)
        # Buscar "Date:" seguido de fecha
        date_match = re.search(r'(?:Date|Fecha|Tarikh)[:\s]+(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})', ocr_text, re.IGNORECASE)
        if not date_match:
            # Buscar formato DD/MM/YY o DD-MM-YY (evitar números de teléfono)
            date_match = re.search(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', ocr_text)
            # Validar que no sea un número de teléfono (ej: 1300-80-8989)
            if date_match:
                potential_date = date_match.group(1)
                # Filtrar números que parecen teléfonos (muchos dígitos juntos)
                if len(potential_date.replace('-', '').replace('/', '')) <= 8:
                    comprobante['fEmision'] = potential_date
                else:
                    # Buscar otra fecha
                    dates = re.findall(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', ocr_text)
                    for d in dates:
                        if len(d.replace('-', '').replace('/', '')) <= 8:
                            comprobante['fEmision'] = d
                            break
        else:
            comprobante['fEmision'] = date_match.group(1)
        
        # Buscar total/precio (múltiples formatos)
        # Priorizar valores en cuadros rojos/highlighted (ATTACHMENT TO INVOICE)
        # Patrón 1: "TOTAL AMOUNT IN US$ ... $ 120.60" (valor en cuadro rojo de tabla)
        total_match = re.search(r'TOTAL\s+AMOUNT\s+IN\s+US\$\s+[^\$]*\$\s*([\d,]+\.\d{2})', ocr_text, re.IGNORECASE)
        if not total_match:
            # Patrón 2: "TOTAL $ 3,758.14" (valor en cuadro rojo de resumen - facturas italianas)
            # Buscar "TOTAL" seguido de "$" y luego el valor (puede estar en la misma línea o siguiente)
            total_match = re.search(r'TOTAL\s+\$\s*([\d,]+\.\d{2})', ocr_text, re.IGNORECASE)
            if not total_match:
                # Buscar "TOTAL" en una línea y "$ XXX.XX" en líneas siguientes (formato multilínea)
                # Para facturas italianas: "TOTAL\n$\n3,755.80\n$ 2.34\n$ 3,758.14" - capturar el ÚLTIMO valor
                total_header_match = re.search(r'TOTAL\s*$', ocr_text, re.IGNORECASE | re.MULTILINE)
                if total_header_match:
                    # Buscar después del header TODOS los valores monetarios y tomar el ÚLTIMO (el total final)
                    after_total = ocr_text[total_header_match.end():]
                    # Buscar todos los valores con formato $ XXX.XX en los siguientes 200 caracteres
                    all_values = list(re.finditer(r'\$\s*([\d,]+\.\d{2})', after_total[:200]))
                    if all_values:
                        # Tomar el ÚLTIMO valor encontrado (es el total final después del stamp duty)
                        total_match = all_values[-1]
        if not total_match:
            # Priorizar Grand Total explícito primero
            total_match = re.search(r'(?:Grand\s+Total|GRAND\s+TOTAL)\s*([\d,]+(?:[\.\s\-]?\d{2})?)', ocr_text, re.IGNORECASE)
            if total_match and ' ' in total_match.group(1):
                g = total_match.group(1).replace(',', '').strip()
                g = re.sub(r'\s', '.', g) if re.match(r'^\d+\s\d{2}$', g.replace(',', '')) else g
        if not total_match:
            # Buscar "Total $XXX" o "Total $XXX,XXX" sin decimales (formato español)
            total_match = re.search(r'Total\s+\$?\s*([\d,]+)', ocr_text, re.IGNORECASE)
        # Priorizar "Invoice Amount" para Invoice Approval Reports y Oracle AP
        if not total_match:
            # Oracle AP: "Invoice Invoice Amount USD 655740.75" o "Invoice Amount USD 655740.75"
            oracle_amount_match = re.search(r'Invoice\s+(?:Invoice\s+)?Amount\s+(?:USD|PEN|EUR)\s+([\d,]+[\.\-]?\d*)', ocr_text, re.IGNORECASE)
            if oracle_amount_match:
                total_match = oracle_amount_match
            else:
                total_match = re.search(r'Invoice\s+Amount\s+([\d,]+[\.\-]?\d*)', ocr_text, re.IGNORECASE)
        if not total_match:
            # Buscar "总计" o "JUMLAH RM" seguido de número (para documentos chinos/malayos)
            total_match = re.search(r'(?:总计|JUMLAH)\s*(?:RM\s+)?([\d,]+[\.\-]?\d{2})', ocr_text, re.IGNORECASE)
        if not total_match:
            # Buscar otros formatos: "Total Sale", "Total", "TOTAL", etc.
            total_match = re.search(r'(?:Total\s+Sale|TOTAL|Total\s+Amount|Grand\s+Total|Amount\s+Due)(?:\s*\([^)]+\))?\s*(?:RM|USD|MYR|US\$|\$|Inci\.\s*ST)?\s*([\d,]+[\.\-]?\d*)', ocr_text, re.IGNORECASE)
        if not total_match:
            # Si no hay total final, buscar cualquier total
            total_match = re.search(r'(?:Sub-?Total|TOTAL)\s*(?:RM|USD|MYR|US\$|\$)?\s*([\d,]+[\.\-]?\d*)', ocr_text, re.IGNORECASE)
        if total_match:
            val = total_match.group(1)
            total_str = val.replace(',', '')
            # Corregir OCR donde el punto decimal fue leído como guion: 25-20 -> 25.20
            if re.match(r'^\d+\-\d{2}$', total_str):
                total_str = total_str.replace('-', '.')
            # Corregir espacio por punto: 32 40 -> 32.40
            if re.match(r'^\d+\s\d{2}$', val):
                total_str = val.replace(' ', '.').strip()
            comprobante['nPrecioTotal'] = float(total_str)
        
        # Buscar información del cliente
        client_match = re.search(r'Attn\.?:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', ocr_text)
        comprobante['tCliente'] = client_match.group(1) if client_match else None
        
        # Si tiene al menos un campo identificador, agregarlo
        if comprobante.get('tNumero') or comprobante.get('tSerie') or comprobante.get('_stamp_name'):
            comprobante_items.append(comprobante)
        
        result = {"mcomprobante": comprobante_items} if comprobante_items else {}
        
        # Extraer detalles del comprobante (items/productos)
        detalles = self._extract_comprobante_detalle(ocr_text)
        
        # Extraer datos específicos de Oracle AP si es un documento de Oracle
        oracle_ap_data = self._extract_oracle_ap_data(ocr_text)
        if oracle_ap_data:
            # Agregar datos de Oracle AP a mcomprobante
            if comprobante_items:
                comprobante_items[0].update(oracle_ap_data.get('comprobante_fields', {}))
                
                # Si no se encontró nPrecioTotal pero hay Invoice Amount, usarlo
                if 'nPrecioTotal' not in comprobante_items[0] or not comprobante_items[0].get('nPrecioTotal'):
                    invoice_amount = oracle_ap_data.get('comprobante_fields', {}).get('_oracle_invoice_amount')
                    if invoice_amount:
                        comprobante_items[0]['nPrecioTotal'] = invoice_amount
                
                # Si no se encontró tNumero pero hay Invoice Num, usarlo
                if not comprobante_items[0].get('tNumero'):
                    invoice_num = oracle_ap_data.get('comprobante_fields', {}).get('_oracle_invoice_num')
                    if invoice_num:
                        comprobante_items[0]['tNumero'] = invoice_num
            
            # Agregar detalles de pago a mcomprobante_detalle
            if oracle_ap_data.get('payment_details'):
                if not detalles:
                    detalles = []
                detalles.extend(oracle_ap_data['payment_details'])
            
            # Agregar proveedor de Oracle AP a result si existe
            if oracle_ap_data.get('comprobante_fields', {}).get('_oracle_supplier_name'):
                # Agregar proveedor a catálogos si no existe
                if 'mproveedor' not in result:
                    result['mproveedor'] = []
                # Verificar que no esté duplicado
                supplier_name = oracle_ap_data['comprobante_fields']['_oracle_supplier_name']
                if not any(p.get('tRazonSocial') == supplier_name for p in result.get('mproveedor', [])):
                    result['mproveedor'].append({
                        "tRazonSocial": supplier_name
                    })
        
        # Detectar y corregir totales semanales mal clasificados (WEEK 27, WEEK 28, etc.)
        weekly_totals = self._extract_weekly_totals(ocr_text)
        if weekly_totals:
            # Si hay totales semanales, agregarlos a mresumen
            if 'mresumen' not in result:
                result['mresumen'] = []
            result['mresumen'].extend(weekly_totals)
        
        # Extraer valores de Cash Flow (Total Disbursement, Period Balance, etc.)
        cash_flow_values = self._extract_cash_flow_values(ocr_text)
        if cash_flow_values:
            if 'mresumen' not in result:
                result['mresumen'] = []
            result['mresumen'].extend(cash_flow_values)
        
        if detalles:
            result["mcomprobante_detalle"] = detalles
            # Si no se detectó total del comprobante, usar suma de detalles
            if comprobante_items and 'nPrecioTotal' not in comprobante_items[0]:
                total_sum = round(sum(d.get('nPrecioTotal', 0.0) for d in detalles), 2)
                if total_sum > 0:
                    comprobante_items[0]['nPrecioTotal'] = total_sum
        
        # Extraer filas de "BSQE SERVICE CHARGES" (labor) como detalle: horas → cantidad, rate → unitario, amount → total
        labor_items = self._extract_labor_details(ocr_text)
        if labor_items:
            if 'mcomprobante_detalle' in result:
                result['mcomprobante_detalle'].extend(labor_items)
            else:
                result['mcomprobante_detalle'] = labor_items

        # Fallback: pedir SIEMPRE a Gemini e integrar con lo ya detectado
        existing = result.get('mcomprobante_detalle', [])
        if getattr(self, 'gemini_service', None) is not None:
            inferred_items = self.gemini_service.infer_line_items(ocr_text)
            merged = []
            if isinstance(inferred_items, list):
                for it in inferred_items:
                    try:
                        cantidad = float(it.get('nCantidad', 1) or 1)
                        desc = str(it.get('tDescripcion', '')).strip()
                        unit = it.get('nPrecioUnitario', it.get('nPrecioTotal'))
                        total = it.get('nPrecioTotal', None)
                        if unit is None and total is not None:
                            unit = float(total) / max(cantidad, 1)
                        unit = float(unit)
                        total = float(total if total is not None else unit * cantidad)
                        if desc and total > 0:
                            merged.append({
                                'nCantidad': cantidad,
                                'tDescripcion': desc,
                                'nPrecioUnitario': round(unit, 2),
                                'nPrecioTotal': round(total, 2)
                            })
                    except Exception:
                        continue
            if existing:
                sigs = set((d['tDescripcion'], d['nPrecioTotal']) for d in existing)
                for m in merged:
                    key = (m['tDescripcion'], m['nPrecioTotal'])
                    if key not in sigs:
                        existing.append(m)
                result['mcomprobante_detalle'] = existing
            elif merged:
                result['mcomprobante_detalle'] = merged
        
        return result if result else None

    def _extract_journal_details_items(self, ocr_text: str) -> List[Dict]:
        """
        Extrae líneas con montos de GL Journal Details como items.
        Solo extrae nPrecioUnitario (Entered Debits en USD), NO nPrecioTotal.
        """
        detalles: List[Dict] = []
        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
        in_table = False
        header_line_found = False
        
        for i, line in enumerate(lines):
            # Detectar inicio de tabla por encabezados típicos
            if not in_table and ('GL Journal Details' in line or ('Line' in line and 'Entered' in line and 'Debits' in line)):
                in_table = True
                header_line_found = True
                continue
            
            if not in_table:
                continue
            
            # Detectar línea de encabezados de columna (después de "GL Journal Details")
            if header_line_found and ('Line' in line and 'Entered' in line and 'Debits' in line):
                header_line_found = False
                continue
            
            # Saltar separadores/footers/totales
            if re.search(r'^(Page No\.|Run Date|Report No\.|^[-\s\.]{5,}$)', line, re.IGNORECASE):
                continue
            
            # Detectar totales (líneas que solo tienen números grandes al final)
            if re.search(r'^\d{1,2}\s+[VA-Z0-9\s]+\s+(\d{1,3}(?:,\d{3})*\.\d{2}\s+){3,}', line):
                # Probablemente es una línea de totales, saltarla
                continue
            
            # Detectar cálculos destacados (el cuadro rojo) - NO extraer como item
            if re.search(r'USD\s+\d{1,3}(?:,\d{3})*\.\d{2}\s*\+\s*USD', line, re.IGNORECASE):
                continue
            
            # Buscar patrón de línea de datos: número de línea + códigos + montos
            # Formato típico: "1 V52T 000 0000 890 26442 007 8NJ2500 4,301.00 0.00 ..."
            line_match = re.match(r'^(\d{1,2})\s+([VA-Z0-9\s]+?)\s+(\d{1,3}(?:,\d{3})*\.\d{2})', line)
            if not line_match:
                continue
            
            line_no = line_match.group(1)
            codes_part = line_match.group(2).strip()
            entered_debits_str = line_match.group(3).replace(',', '')
            
            try:
                entered_debits = float(entered_debits_str)
            except (ValueError, AttributeError):
                continue
            
            # Solo extraer si el monto de Entered Debits es > 0
            if entered_debits <= 0:
                continue
            
            # Extraer descripción: buscar al final de la línea (después de los números)
            # Buscar patrones como "JUL-25 BSQE OH RECOVERY" o similar
            desc = None
            desc_match = re.search(r'(JUL|AUG|SEP|OCT|NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN)[\-\s]+(?:25|24|23|26)\s+(BSQE|OH\s+RECOVERY|RECOVERY|Labor)[A-Z\s\-]*', line, re.IGNORECASE)
            if desc_match:
                desc = desc_match.group(0).strip()
            else:
                # Fallback: tomar texto después del último monto grande
                # Remover todos los números y códigos, dejar solo texto descriptivo
                desc = re.sub(r'\b[VA-Z0-9]{3,}\b', '', line)
                desc = re.sub(r'(\d{1,3}(?:,\d{3})*\.\d{2})', '', desc)
                desc = re.sub(r'\s{2,}', ' ', desc).strip()
                # Si la descripción es muy corta o solo espacios, usar default
                if len(desc) < 3:
                    desc = 'GL Journal Line'
            
            # Agregar item SOLO con nPrecioUnitario (NO nPrecioTotal)
            detalles.append({
                'nCantidad': 1.0,
                'tDescripcion': desc or 'GL Journal Line',
                'nPrecioUnitario': entered_debits
                # NO incluir nPrecioTotal
            })
        
        return detalles
    
    def _extract_comprobante_detalle(self, ocr_text: str) -> List[Dict]:
        """Extrae items/detalles de un comprobante."""
        detalles = []
        lines = ocr_text.split('\n')
        
        in_items_section = False
        skip_invoice_group = False  # Flag para excluir "Invoice Group Detail"
        
        # Detectar si es "Invoice Approval Report" - estos documentos NO tienen items reales en "Line Item Details"
        # Los valores en "Line Item Details" son solo columnas de datos, no items de compra
        is_invoice_approval_report = 'Invoice Approval Report' in ocr_text or 'Invoice Approval' in ocr_text
        in_line_item_details = False
        
        last_item_index = None
        for i, line in enumerate(lines):
            line = line.strip()
            # Normalizar decimales con espacio: "12 74" -> "12.74"
            line = re.sub(r'(\b\d{1,4})\s(\d{2}\b)', r'\1.\2', line)
            if not line or len(line) < 5:
                continue
            
            # Detectar y excluir sección "Invoice Group Detail" (no son items reales)
            if 'Invoice Group Detail' in line or 'INV Group ID' in line:
                skip_invoice_group = True
                continue
            
            # Detectar fin de sección "Invoice Group Detail"
            if skip_invoice_group:
                # Verificar si la línea tiene patrón de Invoice Group Detail: "BSQEUSD 751671 33025"
                if re.match(r'^[A-Z]+USD?\s+\d{5,}\s+\d{5}$', line):
                    continue  # Saltar líneas de Invoice Group Detail
                # Si encontramos otra sección, dejar de saltar
                if any(s in line for s in ['Invoice Data', 'Line Item', 'Supplier Data', 'Approval History', 'Line Type']):
                    skip_invoice_group = False
                    # Si es "Invoice Approval Report" y encontramos "Line Item", marcar que estamos en esa sección
                    if is_invoice_approval_report and 'Line Item' in line:
                        in_line_item_details = True
                else:
                    continue  # Continuar saltando hasta encontrar otra sección
            
            # Para "Invoice Approval Report", NO extraer valores de "Line Item Details" como items
            # Estos son solo columnas de datos (Line Amount, Nat Class, Job, Sub Job, etc.), no items reales
            if is_invoice_approval_report and in_line_item_details:
                # Detectar si estamos en la sección de headers de "Line Item Details"
                if any(keyword in line for keyword in ['Line Type', 'Line Amount', 'Nat Class', 'Job', 'Sub Job', 'Cost Code']):
                    continue  # Saltar headers
                # Detectar si encontramos otra sección (Approval History, etc.)
                if 'Approval History' in line or 'Supplier Data' in line or 'Invoice Data' in line:
                    in_line_item_details = False
                    continue
                # Si estamos en "Line Item Details", NO extraer estos valores como items
                # Los valores como "890 264 223" o "42" son solo datos de columnas, no items
                if re.match(r'^(\d{1,4}\s+){0,3}\d{1,4}$', line.strip()):
                    # Línea que solo contiene números separados por espacios (valores de columnas)
                    continue
                # Si la línea contiene solo números pequeños sin descripción textual, probablemente es columna
                if re.match(r'^\d{1,4}(\s+\d{1,4}){0,5}$', line.strip()) and len(line.strip()) < 30:
                    continue
            
            # Detectar inicio de sección de items (evitar totales y subtotales)
            if (
                'Sub-Total' in line or 'SUB-TOTAL' in line or
                ('Total' in line and 'Amount' not in line) or 'TOTAL:' in line or
                'Tax' in line or 'DISCOUNT' in line or 'AMOUNT TO BE PAID' in line or
                line.upper().startswith('TOTAL') or line.upper().startswith('DISCOUNT') or
                line.upper().startswith('SUB-TOTAL') or line.upper().startswith('AMOUNT TO BE PAID')
            ):
                in_items_section = False
                continue
            # Si es línea de variante/detalle adicional, anexarla al último ítem detectado
            if last_item_index is not None and (line.upper().startswith('VARIANT') or line.upper().startswith('ADD-ON') or line.upper().startswith('OPTION')):
                detalles[last_item_index]["tDescripcion"] += f" - {line}"
                continue
            # Omitir encabezados de tabla y líneas administrativas
            if (line.upper().startswith('QTY ') or ' ITEM NAME ' in line or line.upper().startswith('TOPUP') or
                line.upper().startswith('CANT.') or 'DESCRIPCIÓN' in line.upper() or 
                'PRECIO UNITARIO' in line.upper() or 'IMPORTE' in line.upper()):
                # Si encontramos encabezados de tabla en español, activar detección de items
                if 'CANT.' in line.upper() or 'DESCRIPCIÓN' in line.upper():
                    in_items_section = True
                continue
            
            # Detectar formato español de tabla: "1 7 de julio 2025 90,000 90,000"
            # Patrón: cantidad (1-2 dígitos), descripción (texto), precio unitario (con comas), importe (con comas)
            spanish_table_match = re.search(r'^(\d{1,2})\s+([A-Za-záéíóúñÁÉÍÓÚÑ0-9\s\-\/]+?)\s+([\d,]+)\s+([\d,]+)$', line)
            if spanish_table_match:
                cantidad = float(spanish_table_match.group(1))
                descripcion = spanish_table_match.group(2).strip()
                precio_unitario_str = spanish_table_match.group(3).replace(',', '')
                importe_str = spanish_table_match.group(4).replace(',', '')
                
                try:
                    precio_unitario = float(precio_unitario_str)
                    importe = float(importe_str)
                    
                    # Verificar que la descripción no sea solo números o totales
                    if (descripcion and len(descripcion) > 3 and 
                        'total' not in descripcion.lower() and 
                        'subtotal' not in descripcion.lower()):
                        # Buscar si la siguiente línea tiene más descripción
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            # Si la siguiente línea no tiene números al inicio, probablemente es continuación de descripción
                            if not re.match(r'^\d', next_line) and not re.match(r'^Total|^Subtotal', next_line, re.IGNORECASE):
                                descripcion += " " + next_line
                        
                        detalles.append({
                            "nCantidad": cantidad,
                            "tDescripcion": descripcion,
                            "nPrecioUnitario": precio_unitario,
                            "nPrecioTotal": importe  # Usar el importe calculado
                        })
                        last_item_index = len(detalles) - 1
                        continue
                except ValueError:
                    pass
            
            # Detectar líneas que parecen items
            # Patrón 1: Número de línea seguido de divisa y monto (ej: "9 USD6.20", "9 RM25.50")
            simple_item_match = re.search(r'^(\d{1,2})\s+(USD|RM|EUR|PEN|MYR)\s*([\d,]+[\.\-]?\d{2})', line, re.IGNORECASE)
            if not simple_item_match:
                # Patrón 1b: Número de línea seguido de monto simple (ej: "1 25.50")
                simple_item_match = re.search(r'^(\d{1,2})\s+([\d,]+[\.\-]?\d{2})$', line)
            
            # Patrón 2: Descripción cantidad precio (ej: "ICE VANILLA LATT - V W E 1 17.50")
            # O solo descripción y precio (ej: "ADD ESP SHT 1 2.00")
            item_match = None
            if not simple_item_match:
                item_match = re.search(r'^([A-Z][A-Z\s\-\&]+?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.?\d{1,2})$', line)
                
                if not item_match:
                    # Intentar otro patrón: descripción al inicio, números al final
                    item_match = re.search(r'^([A-Z][^0-9]{5,}?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.?\d{1,2})$', line)
            # Patrón 3: cantidad, descripción, monto (ej: "1 SET B 13.80")
            qty_desc_amt_match = None
            if not simple_item_match and not item_match:
                qty_desc_amt_match = re.search(r'^(\d{1,3})\s+([A-Za-z][A-Za-z0-9\s\-\(\)\/,&\.]+?)\s+([\d,]+[\.\-]?\d{2})$', line)
            
            # Procesar item simple (número de línea + monto)
            if simple_item_match:
                num_linea = int(simple_item_match.group(1))
                if simple_item_match.lastindex >= 3:
                    # Caso: "9 USD6.20" (con divisa) - Este es válido
                    divisa = simple_item_match.group(2).upper()
                    monto_str = simple_item_match.group(3).replace(',', '')
                    if re.match(r'^\d+\-\d{2}$', monto_str):
                        monto_str = monto_str.replace('-', '.')
                    precio_total = float(monto_str)
                    detalles.append({
                        "nCantidad": 1.0,
                        "tDescripcion": f"Item {num_linea} ({divisa})",
                        "nPrecioUnitario": precio_total,
                        "nPrecioTotal": round(precio_total, 2)
                    })
                    last_item_index = len(detalles) - 1
                else:
                    # Caso: "1 25.50" (sin divisa) - Solo aceptar si está en contexto de items reales
                    # Ignorar si parece ser solo número de línea de tabla sin descripción
                    # Validar: si la siguiente línea tiene texto descriptivo, entonces sí es válido
                    # Por ahora, solo aceptamos si tiene divisa explícita o descripción
                    # Este patrón puede ser parte de una tabla, así que lo omitimos por seguridad
                    pass  # Omitir items sin divisa explícita para evitar falsos positivos
            elif item_match:
                descripcion = item_match.group(1).strip()
                cantidad = float(item_match.group(2))
                precio_str = item_match.group(3).replace(',', '')
                precio_unitario = float(precio_str)
                precio_total = cantidad * precio_unitario
                
                # Validar que no sea una línea de total o subtotal
                # Y que no sea de Invoice Group Detail (ej: "BSQEUSD" o números muy grandes)
                if ('total' not in descripcion.lower() and 'tax' not in descripcion.lower() and 
                    'BSQEUSD' not in descripcion and cantidad < 1000000):  # Excluir IDs muy grandes como INV Group ID
                    detalles.append({
                        "nCantidad": cantidad,
                        "tDescripcion": descripcion,
                        "nPrecioUnitario": precio_unitario,
                        "nPrecioTotal": round(precio_total, 2)
                    })
                    last_item_index = len(detalles) - 1
            elif qty_desc_amt_match:
                cantidad = float(qty_desc_amt_match.group(1))
                descripcion = qty_desc_amt_match.group(2).strip()
                monto_str = qty_desc_amt_match.group(3).replace(',', '')
                if re.match(r'^\d+\-\d{2}$', monto_str):
                    monto_str = monto_str.replace('-', '.')
                precio_unitario = float(monto_str)
                precio_total = cantidad * precio_unitario
                detalles.append({
                    "nCantidad": cantidad,
                    "tDescripcion": descripcion,
                    "nPrecioUnitario": round(precio_unitario, 2),
                    "nPrecioTotal": round(precio_total, 2)
                })
                last_item_index = len(detalles) - 1
        
        # Si no se detectaron ítems por patrón estándar, intentar con adjuntos (Attachment) y columna "Total Amount"
        if not detalles and ('ATTACHMENT' in ocr_text.upper() or 'Total Amount' in ocr_text):
            attach_lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
            in_table = False
            for i, l in enumerate(attach_lines):
                # Detectar inicio de tabla (header con "Resource", "Vendor", "Total Amount", etc.)
                if any(keyword in l for keyword in ['Resource', 'Vendor', 'Total Amount', 'Assignment no', 'Report Number']):
                    in_table = True
                    continue
                
                # Si estamos en la tabla, buscar filas con datos
                if in_table:
                    # Detectar líneas de total (saltarlas, se procesarán después)
                    if 'TOTAL AMOUNT' in l.upper() or l.upper().startswith('TOTAL'):
                        in_table = False
                        continue
                    
                    # Patrón mejorado para filas de tabla: buscar valores monetarios al final
                    # Ejemplo: "... $ 1,305.05 $ 1,305.05 # 01" o "... $ 60.30 $ 60.30"
                    # Buscar múltiples valores monetarios al final de la línea (últimos 2 valores)
                    amount_end_match = re.search(r'\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})(?:\s*#|\s*$)', l)
                    if amount_end_match:
                        # Verificar que no sea una línea de total
                        if 'TOTAL' not in l.upper() and len(l) > 30:  # Filtrar líneas muy cortas
                            amount1 = float(amount_end_match.group(1).replace(',', ''))
                            amount2 = float(amount_end_match.group(2).replace(',', ''))
                            # Usar el segundo valor (Total Amount) - es el valor final
                            final_amount = amount2 if amount2 > 0 else amount1
                            
                            # Extraer descripción (todo antes de los valores monetarios)
                            # Buscar nombre del recurso (primeras palabras con mayúsculas)
                            resource_match = re.search(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)', l)
                            if resource_match:
                                resource_name = resource_match.group(1)
                                # Buscar vendor (después del resource name)
                                vendor_match = re.search(rf'{re.escape(resource_name)}\s+([A-Z][^$]+?)(?:\s+\d|\s+\$)', l)
                                if vendor_match:
                                    vendor_info = vendor_match.group(1).strip()[:50]
                                    descripcion = f'{resource_name} - {vendor_info}'
                                else:
                                    descripcion = resource_name
                            else:
                                # Si no hay nombre de recurso, usar todo antes de los valores monetarios
                                desc_match = re.search(r'^(.+?)(?:\s+\$\s*[\d,]+\.\d{2})', l)
                                descripcion = desc_match.group(1).strip()[:100] if desc_match else 'Attachment line'
                            
                            detalles.append({
                                'nCantidad': 1.0,
                                'tDescripcion': descripcion,
                                'nPrecioUnitario': final_amount,
                                'nPrecioTotal': final_amount
                            })
                            continue
                    
                    # Patrón alternativo: buscar solo un valor monetario al final (formato más simple)
                    single_amount_match = re.search(r'\$\s*([\d,]+\.\d{2})\s*$', l)
                    if single_amount_match and 'TOTAL' not in l.upper() and len(l) > 30:
                        amount = float(single_amount_match.group(1).replace(',', ''))
                        # Extraer descripción
                        desc_match = re.search(r'^(.+?)(?:\s+\$\s*[\d,]+\.\d{2})', l)
                        descripcion = desc_match.group(1).strip()[:100] if desc_match else 'Attachment line'
                        
                        detalles.append({
                            'nCantidad': 1.0,
                            'tDescripcion': descripcion,
                            'nPrecioUnitario': amount,
                            'nPrecioTotal': amount
                        })
        return detalles if detalles else []

    def _extract_labor_details(self, ocr_text: str) -> List[Dict]:
        """Extrae filas de tablas de labor (Emp Name ... Hours Hrly Rate Amount)."""
        if 'Emp Name' not in ocr_text and 'SERVICE CHARGES' not in ocr_text:
            return []
        detalles: List[Dict] = []
        for line in ocr_text.split('\n'):
            line = line.strip()
            if not line or len(line) < 20:
                continue
            # Buscar patrón ... Hours <h> Hrly Rate <r> ... Amount <a>
            m = re.search(r'([A-Z][A-Za-z\s\./&]+?)\s+BSQE\d{4,}\s+\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}.*?\s(\d+(?:\.\d+)?)\s+(\d+|\d+\.\d{2})\s+[A-Z]{2,3}\s+([\d,]+\.\d{2})$', line)
            if not m:
                # Variación sin clase al medio
                m = re.search(r'([A-Z][A-Za-z\s\./&]+?)\s+BSQE\d{4,}.*?\s(\d+(?:\.\d+)?)\s+(\d+|\d+\.\d{2})\s+[A-Z]{2,3}\s+([\d,]+\.\d{2})$', line)
            if m:
                nombre = m.group(1).strip()
                horas = float(m.group(2))
                rate = float(m.group(3))
                amount = float(m.group(4).replace(',', ''))
                detalles.append({
                    'nCantidad': horas,
                    'tDescripcion': f'{nombre} INSPECTING',
                    'nPrecioUnitario': rate,
                    'nPrecioTotal': amount
                })
        return detalles
    
    def _extract_highlighted_calculations(self, ocr_text: str) -> List[Dict]:
        """
        Extrae cálculos destacados (cuadros rojos, boxes, etc.) del texto OCR.
        
        Estos cálculos suelen estar en secciones destacadas y contienen operaciones
        matemáticas con monedas, como: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00"
        
        También detecta valores TOTAL destacados en rectángulos rojos, como: "TOTAL $ 122.94"
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con cálculos destacados en formato mresumen
        """
        calculations = []
        
        # Patrón para detectar cálculos con monedas y operadores
        # Ejemplo: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00"
        calculation_pattern = r'([A-Z]{3})\s+([\d,]+\.\d{2})\s*\+\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s*\+\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s*=\s*([A-Z]{3})\s+([\d,]+\.\d{2})'
        
        matches = re.finditer(calculation_pattern, ocr_text, re.IGNORECASE)
        for match in matches:
            calculation_text = match.group(0)
            
            # Extraer el resultado (último valor después del =)
            result_match = re.search(r'=\s*[A-Z]{3}\s+([\d,]+\.\d{2})', calculation_text, re.IGNORECASE)
            if result_match:
                try:
                    result_amount = float(result_match.group(1).replace(',', ''))
                    
                    # Detectar moneda
                    currency_match = re.search(r'\b(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\b', calculation_text, re.IGNORECASE)
                    currency = currency_match.group(1).upper() if currency_match else "USD"
                    
                    # Crear entrada en formato mresumen
                    calculations.append({
                        "tDescripcion": f"Cálculo destacado: {calculation_text}",
                        "tjobno": None,
                        "ttype": None,
                        "nMonto": result_amount,
                        "tDivisa": currency,
                        "_calculation": True,
                        "_calculation_text": calculation_text
                    })
                except ValueError:
                    continue
        
        # Si no se encontraron con el patrón exacto, buscar líneas con operadores
        if not calculations:
            lines = ocr_text.split('\n')
            for line in lines:
                line = line.strip()
                # Buscar líneas con +, = y códigos de moneda
                if re.search(r'[A-Z]{3}\s+[\d,]+\.\d{2}\s*\+\s*[A-Z]{3}\s+[\d,]+\.\d{2}', line, re.IGNORECASE) and '=' in line:
                    currency_match = re.search(r'\b(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\b', line, re.IGNORECASE)
                    currency = currency_match.group(1).upper() if currency_match else "USD"
                    
                    result_match = re.search(r'=\s*[A-Z]{3}\s+([\d,]+\.\d{2})', line, re.IGNORECASE)
                    if result_match:
                        try:
                            result_amount = float(result_match.group(1).replace(',', ''))
                            calculations.append({
                                "tDescripcion": f"Cálculo destacado: {line}",
                                "tjobno": None,
                                "ttype": None,
                                "nMonto": result_amount,
                                "tDivisa": currency,
                                "_calculation": True,
                                "_calculation_text": line
                            })
                        except ValueError:
                            continue
        
        # NUEVO: Detectar valores TOTAL destacados (rectángulos rojos en comprobantes)
        # Patrón 1: "TOTAL $ 122.94" o "TOTAL $122.94" o "TOTAL USD 122.94"
        # Estos suelen estar en rectángulos rojos y son el valor final destacado
        total_highlighted_pattern = r'TOTAL\s+(?:\$|USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\s*([\d,]+\.\d{2})'
        total_matches = re.finditer(total_highlighted_pattern, ocr_text, re.IGNORECASE)
        for match in total_matches:
            try:
                total_amount = float(match.group(1).replace(',', ''))
                # Detectar moneda en la línea
                line_with_total = ocr_text[max(0, match.start()-50):match.end()+50]
                currency_match = re.search(r'\b(USD|PEN|EUR|RM|MYR|CLP|GBP|JPY|CNY|COP|MXN|ARS|BRL)\b', line_with_total, re.IGNORECASE)
                currency = currency_match.group(1).upper() if currency_match else "USD"
                
                # Verificar que no sea un duplicado de un cálculo ya encontrado
                is_duplicate = False
                for calc in calculations:
                    if abs(calc.get("nMonto", 0) - total_amount) < 0.01:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    calculations.append({
                        "tDescripcion": f"TOTAL destacado: ${total_amount:,.2f}",
                        "tjobno": None,
                        "ttype": None,
                        "nMonto": total_amount,
                        "tDivisa": currency,
                        "_highlighted": True,
                        "_total_highlighted": True,
                        "_source_line": match.group(0)
                    })
            except (ValueError, AttributeError):
                continue
        
        # Patrón 2: "TOTAL AMOUNT IN US$" con valores destacados
        # Ejemplo: "TOTAL AMOUNT IN US$ 22 180 $ - $ - $ 120.60 $ 120.60"
        # El último valor es el total destacado
        total_amount_pattern = r'TOTAL\s+AMOUNT\s+IN\s+US\$\s+.*?\$\s*([\d,]+\.\d{2})\s*$'
        total_amount_matches = re.finditer(total_amount_pattern, ocr_text, re.IGNORECASE | re.MULTILINE)
        for match in total_amount_matches:
            try:
                total_amount = float(match.group(1).replace(',', ''))
                
                # Verificar que no sea un duplicado
                is_duplicate = False
                for calc in calculations:
                    if abs(calc.get("nMonto", 0) - total_amount) < 0.01:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    calculations.append({
                        "tDescripcion": f"TOTAL AMOUNT destacado: ${total_amount:,.2f}",
                        "tjobno": None,
                        "ttype": None,
                        "nMonto": total_amount,
                        "tDivisa": "USD",
                        "_highlighted": True,
                        "_total_highlighted": True,
                        "_source_line": match.group(0)
                    })
            except (ValueError, AttributeError):
                continue
        
        # Patrón 3: Detectar valores de columna "Total Amount" destacados en tablas
        # Cuando hay "ATTACHMENT TO INVOICE" y una tabla con columna "Total Amount"
        # Los valores de esa columna están en el rectángulo rojo
        if 'ATTACHMENT TO INVOICE' in ocr_text.upper() and 'Total Amount' in ocr_text:
            # Buscar líneas que contengan valores en la columna "Total Amount"
            # Formato típico: "... $ 60.30" o "... $ 120.60" al final de líneas de datos
            lines = ocr_text.split('\n')
            for line in lines:
                line = line.strip()
                # Buscar patrón: texto seguido de "$ XX.XX" al final (valores de Total Amount)
                # Evitar líneas que son totales o headers
                if 'TOTAL AMOUNT' in line.upper() or 'Total Amount' in line:
                    continue
                
                # Buscar valores "$ XX.XX" al final de líneas que parecen filas de datos
                # Patrón: texto con información (nombres, códigos) seguido de "$ XX.XX" al final
                amount_at_end = re.search(r'\$\s*([\d,]+\.\d{2})\s*$', line)
                if amount_at_end:
                    try:
                        amount = float(amount_at_end.group(1).replace(',', ''))
                        # Solo valores razonables (evitar valores muy pequeños o muy grandes)
                        if 1.0 <= amount <= 1000000.0:
                            # Verificar que no sea un duplicado
                            is_duplicate = False
                            for calc in calculations:
                                if abs(calc.get("nMonto", 0) - amount) < 0.01:
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                calculations.append({
                                    "tDescripcion": f"Total Amount destacado: ${amount:,.2f}",
                                    "tjobno": None,
                                    "ttype": None,
                                    "nMonto": amount,
                                    "tDivisa": "USD",
                                    "_highlighted": True,
                                    "_column_total_amount": True,
                                    "_source_line": line
                                })
                    except (ValueError, AttributeError):
                        continue
        
        return calculations
    
    def _extract_gl_journal_highlighted_values(self, ocr_text: str) -> List[Dict]:
        """
        Extrae SOLO los valores destacados (en cuadros rojos) de un GL Journal Details.
        
        Cuando hay un cálculo destacado como "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00",
        extrae solo esos valores individuales (4,301.00, 616.00, 1,452.00) y el total (6,369.00).
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con valores destacados en formato mresumen
        """
        highlighted_values = []
        
        # Buscar el cálculo destacado: "USD X + USD Y + USD Z = USD TOTAL"
        calculation_pattern = r'([A-Z]{3})\s+([\d,]+\.\d{2})\s*\+\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s*\+\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s*=\s*([A-Z]{3})\s+([\d,]+\.\d{2})'
        match = re.search(calculation_pattern, ocr_text, re.IGNORECASE)
        
        if match:
            currency = match.group(1).upper()
            value1 = float(match.group(2).replace(',', ''))
            value2 = float(match.group(4).replace(',', ''))
            value3 = float(match.group(6).replace(',', ''))
            total = float(match.group(8).replace(',', ''))
            
            # Agregar cada valor individual destacado
            highlighted_values.append({
                "tjobno": None,
                "ttype": "GL Journal Highlighted",
                "tsourcereference": None,
                "tsourcerefid": None,
                "tdescription": f"GL Journal Highlighted Value 1",
                "nImporte": value1,
                "tStampname": None,
                "tsequentialnumber": None
            })
            
            highlighted_values.append({
                "tjobno": None,
                "ttype": "GL Journal Highlighted",
                "tsourcereference": None,
                "tsourcerefid": None,
                "tdescription": f"GL Journal Highlighted Value 2",
                "nImporte": value2,
                "tStampname": None,
                "tsequentialnumber": None
            })
            
            highlighted_values.append({
                "tjobno": None,
                "ttype": "GL Journal Highlighted",
                "tsourcereference": None,
                "tsourcerefid": None,
                "tdescription": f"GL Journal Highlighted Value 3",
                "nImporte": value3,
                "tStampname": None,
                "tsequentialnumber": None
            })
            
            # Agregar el total
            highlighted_values.append({
                "tjobno": None,
                "ttype": "GL Journal Highlighted",
                "tsourcereference": None,
                "tsourcerefid": None,
                "tdescription": f"GL Journal Highlighted Total",
                "nImporte": total,
                "tStampname": None,
                "tsequentialnumber": None
            })
        
        return highlighted_values
    
    def _extract_jornada_data(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """Extrae datos de jornadas (horas trabajadas por empleados)."""
        jornada_data = []
        empleados = []
        
        # Buscar información principal de jornada
        period_match = re.search(r'Period\s+(\w{3}\s+\d{4})', ocr_text, re.IGNORECASE)
        period = period_match.group(1) if period_match else None
        
        # Buscar total de horas
        total_hours_match = re.search(r'Total\s+H(?:ours|rs)?\s+([\d.]+)', ocr_text, re.IGNORECASE)
        total_hours = float(total_hours_match.group(1)) if total_hours_match else None
        
        # Información de jornada principal
        if period or total_hours:
            jornada_data.append({
                "fRegistro": period,
                "nTotalHoras": total_hours
            })
        
        # Extraer datos de empleados
        lines = ocr_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Buscar filas con datos de empleados (número + nombre)
            emp_match = re.search(r'(\d{6})\s+([A-Z][^,]+,[\sA-Z]+)', line)
            if emp_match:
                emp_num = emp_match.group(1)
                emp_name = emp_match.group(2).strip()
                
                # Buscar organización (código alphanumérico de 4+ caracteres)
                org_code = None
                if i + 1 < len(lines):
                    org_match = re.search(r'([A-Z0-9]{4,})\s+[\d.]+', lines[i+1])
                    if org_match:
                        org_code = org_match.group(1)
                
                empleados.append({
                    "tNumero": emp_num,
                    "tNombre": emp_name,
                    "tOrganizacion": org_code
                })
        
        result = {}
        if jornada_data:
            result["mjornada"] = jornada_data
        if empleados:
            result["mjornada_empleado"] = empleados
        
        return result if result else None
    
    def _extract_expense_report_data(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """
        Extrae datos de Bechtel Expense Report (OnShore).
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Diccionario con datos estructurados en formato mresumen
        """
        expense_reports = []
        
        # Extraer campos específicos del Expense Report
        report_key_match = re.search(r'Report\s+Key\s*:\s*(\d+)', ocr_text, re.IGNORECASE)
        report_key = report_key_match.group(1) if report_key_match else None
        
        report_number_match = re.search(r'Report\s+Number\s*:\s*([A-Z0-9]+)', ocr_text, re.IGNORECASE)
        report_number = report_number_match.group(1) if report_number_match else None
        
        employee_id_match = re.search(r'Employee\s+ID\s*:\s*(\d+)', ocr_text, re.IGNORECASE)
        employee_id = employee_id_match.group(1) if employee_id_match else None
        
        employee_name_match = re.search(r'Employee\s+Name\s*:\s*([A-Z][^:\n]+)', ocr_text, re.IGNORECASE)
        employee_name = employee_name_match.group(1).strip() if employee_name_match else None
        
        org_code_match = re.search(r'Org\s+Code\s*:\s*([A-Z0-9]+)', ocr_text, re.IGNORECASE)
        org_code = org_code_match.group(1) if org_code_match else None
        
        default_approver_match = re.search(r'Default\s+Approver\s*:\s*([A-Z][^:\n]+)', ocr_text, re.IGNORECASE)
        default_approver = default_approver_match.group(1).strip() if default_approver_match else None
        
        final_approver_match = re.search(r'Final\s+Approver\s*:\s*([A-Z][^:\n]+)', ocr_text, re.IGNORECASE)
        final_approver = final_approver_match.group(1).strip() if final_approver_match else None
        
        report_name_match = re.search(r'Report\s+Name\s*:\s*([^:\n]+)', ocr_text, re.IGNORECASE)
        report_name = report_name_match.group(1).strip() if report_name_match else None
        
        report_date_match = re.search(r'Report\s+Date\s*:\s*([^:\n]+)', ocr_text, re.IGNORECASE)
        report_date = report_date_match.group(1).strip() if report_date_match else None
        
        report_purpose_match = re.search(r'Report\s+Purpose\s*:\s*([^:\n]+)', ocr_text, re.IGNORECASE)
        report_purpose = report_purpose_match.group(1).strip() if report_purpose_match else None
        
        # Extraer montos (pueden tener comas como separadores de miles)
        # Primero intentar extraer del texto normal
        report_total_match = re.search(r'Report\s+Total\s*:\s*([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        report_total = None
        if report_total_match:
            try:
                report_total = float(report_total_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # Si no se encontró, buscar valores destacados (en rojo/boxed) cerca de "Report Total"
        if not report_total:
            # Buscar líneas que contengan "Report Total" y valores monetarios destacados
            lines = ocr_text.split('\n')
            for i, line in enumerate(lines):
                if 'report total' in line.lower():
                    # Buscar en la misma línea o líneas cercanas valores monetarios
                    search_lines = lines[max(0, i-1):min(len(lines), i+3)]
                    for search_line in search_lines:
                        # Buscar valores con formato: 180,000.00 o 180000.00
                        monetary_values = re.findall(r'([\d,]+\.\d{2})', search_line)
                        if monetary_values:
                            try:
                                # Tomar el último valor (generalmente es el total)
                                report_total = float(monetary_values[-1].replace(',', ''))
                                break
                            except ValueError:
                                continue
                    if report_total:
                        break
        
        bechtel_owes_card_match = re.search(r'Bechtel\s+owes\s+Card\s*:\s*([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        bechtel_owes_card = None
        if bechtel_owes_card_match:
            try:
                bechtel_owes_card = float(bechtel_owes_card_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        bechtel_owes_employee_match = re.search(r'Bechtel\s+owes\s+Employee\s*:\s*([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        bechtel_owes_employee = None
        if bechtel_owes_employee_match:
            try:
                bechtel_owes_employee = float(bechtel_owes_employee_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        policy_match = re.search(r'Policy\s*:\s*([^:\n]+)', ocr_text, re.IGNORECASE)
        policy = policy_match.group(1).strip() if policy_match else None
        
        # Extraer stamp name y sequential number (OTHBP, OE0003, etc.)
        stamp_info = self.extract_stamp_info(ocr_text)
        stamp_name = stamp_info.get("stamp_name")
        sequential_number = stamp_info.get("sequential_number")
        
        # Construir descripción completa con todos los campos
        description_parts = []
        if report_name:
            description_parts.append(f"Report: {report_name}")
        if report_purpose:
            description_parts.append(f"Purpose: {report_purpose}")
        if employee_name:
            description_parts.append(f"Employee: {employee_name}")
        if org_code:
            description_parts.append(f"Org: {org_code}")
        if policy:
            description_parts.append(f"Policy: {policy}")
        description = " | ".join(description_parts) if description_parts else "Bechtel Expense Report"
        
        # Crear registro principal en mresumen
        # Usar report_number como tsourcereference y report_key como tsourcerefid
        expense_reports.append({
            "tjobno": org_code,  # Org Code como Job No
            "ttype": "Expense Report",  # Tipo fijo para Expense Reports
            "tsourcereference": report_number,  # Report Number
            "tsourcerefid": f"Key:{report_key}" if report_key else None,  # Report Key
            "tdescription": description,
            "nImporte": report_total,  # Report Total como importe principal
            "tStampname": stamp_name,
            "tsequentialnumber": sequential_number,
            # Campos adicionales específicos de Expense Report (se guardarán pero no en BD)
            "_expense_report_data": {
                "report_key": report_key,
                "report_number": report_number,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "org_code": org_code,
                "default_approver": default_approver,
                "final_approver": final_approver,
                "report_name": report_name,
                "report_date": report_date,
                "report_purpose": report_purpose,
                "report_total": report_total,
                "bechtel_owes_card": bechtel_owes_card,
                "bechtel_owes_employee": bechtel_owes_employee,
                "policy": policy
            }
        })
        
        # Si hay bechtel_owes_employee diferente al report_total, crear registro adicional
        if bechtel_owes_employee and bechtel_owes_employee != report_total:
            expense_reports.append({
                "tjobno": org_code,
                "ttype": "Expense Report - Employee Owed",
                "tsourcereference": report_number,
                "tsourcerefid": f"Key:{report_key}" if report_key else None,
                "tdescription": f"Bechtel owes Employee: {employee_name or 'N/A'}",
                "nImporte": bechtel_owes_employee,
                "tStampname": stamp_name,
                "tsequentialnumber": sequential_number
            })
        
        # Extraer valores destacados (en rojo/boxed) específicos de Expense Reports
        highlighted_values = self._extract_expense_report_highlighted_values(ocr_text, report_number, org_code, stamp_name, sequential_number)
        if highlighted_values:
            expense_reports.extend(highlighted_values)
        
        result = {}
        if expense_reports:
            result["mresumen"] = expense_reports
        
        return result if result else None
    
    def _extract_expense_report_highlighted_values(self, ocr_text: str, report_number: str = None, 
                                                   org_code: str = None, stamp_name: str = None, 
                                                   sequential_number: str = None) -> List[Dict]:
        """
        Extrae valores destacados (en rojo/boxed) de Bechtel Expense Reports.
        
        Busca específicamente valores destacados cerca de "Report Total" y otros campos importantes.
        
        Args:
            ocr_text: Texto extraído del OCR
            report_number: Número de reporte (para asociar)
            org_code: Código de organización (para asociar)
            stamp_name: Nombre del stamp (para asociar)
            sequential_number: Número secuencial (para asociar)
            
        Returns:
            Lista de diccionarios con valores destacados en formato mresumen
        """
        highlights = []
        
        # Buscar valores destacados cerca de "Report Total"
        lines = ocr_text.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Buscar líneas que contengan "Report Total" o valores destacados cerca
            if 'report total' in line_lower:
                # Buscar valores monetarios en la misma línea o líneas cercanas
                search_range = lines[max(0, i-2):min(len(lines), i+3)]
                for search_line in search_range:
                    # Buscar valores con formato monetario: 180,000.00, 180000.00, etc.
                    # También buscar valores sin decimales: 180000
                    monetary_patterns = [
                        r'([\d,]+\.\d{2})',  # Formato con decimales: 180,000.00
                        r'([\d,]+)',  # Formato sin decimales: 180,000
                    ]
                    
                    for pattern in monetary_patterns:
                        monetary_values = re.findall(pattern, search_line)
                        for val_str in monetary_values:
                            try:
                                # Limpiar el valor (quitar comas)
                                clean_val = val_str.replace(',', '')
                                val = float(clean_val)
                                
                                # Filtrar valores muy pequeños (probablemente no son totales)
                                if val >= 1.0:
                                    # Verificar si este valor ya está en los highlights
                                    if not any(h.get("nImporte") == val for h in highlights):
                                        highlights.append({
                                            "tjobno": org_code,
                                            "ttype": "Expense Report - Highlighted Value",
                                            "tsourcereference": report_number,
                                            "tsourcerefid": None,
                                            "tdescription": f"Valor destacado (Report Total): {val:,.2f}",
                                            "nImporte": val,
                                            "tStampname": stamp_name,
                                            "tsequentialnumber": sequential_number,
                                            "_highlighted": True,
                                            "_source_field": "Report Total",
                                            "_source_line": search_line.strip()
                                        })
                            except ValueError:
                                continue
            
            # También buscar otros valores destacados cerca de campos importantes
            # como "Bechtel owes Employee", "Bechtel owes Card", etc.
            if 'bechtel owes' in line_lower:
                search_range = lines[max(0, i-1):min(len(lines), i+2)]
                for search_line in search_range:
                    monetary_values = re.findall(r'([\d,]+\.?\d*)', search_line)
                    for val_str in monetary_values:
                        try:
                            clean_val = val_str.replace(',', '')
                            val = float(clean_val)
                            if val >= 1.0:
                                field_name = "Bechtel owes Employee" if "employee" in line_lower else "Bechtel owes Card"
                                if not any(h.get("nImporte") == val and h.get("_source_field") == field_name for h in highlights):
                                    highlights.append({
                                        "tjobno": org_code,
                                        "ttype": "Expense Report - Highlighted Value",
                                        "tsourcereference": report_number,
                                        "tsourcerefid": None,
                                        "tdescription": f"Valor destacado ({field_name}): {val:,.2f}",
                                        "nImporte": val,
                                        "tStampname": stamp_name,
                                        "tsequentialnumber": sequential_number,
                                        "_highlighted": True,
                                        "_source_field": field_name,
                                        "_source_line": search_line.strip()
                                    })
                        except ValueError:
                            continue
        
        return highlights
    
    def _extract_weekly_totals(self, ocr_text: str) -> List[Dict]:
        """
        Extrae totales semanales de tablas (WEEK 27, WEEK 28, etc.).
        
        Detecta líneas que contienen múltiples valores monetarios al final de tablas,
        que generalmente son totales por semana.
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con totales semanales en formato mresumen
        """
        totals = []
        lines = ocr_text.split('\n')
        
        # Buscar patrones de semanas (WEEK 27, WEEK 28, etc.)
        week_pattern = re.compile(r'WEEK\s+(\d+)', re.IGNORECASE)
        weeks_found = []
        
        # Primero identificar qué semanas están en el documento
        for line in lines:
            week_matches = week_pattern.findall(line)
            for week_num in week_matches:
                if week_num not in weeks_found:
                    weeks_found.append(week_num)
        
        # Buscar líneas que contengan múltiples valores monetarios grandes
        # Estas suelen ser los totales al final de las tablas
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Buscar líneas con 2 o más valores monetarios grandes (probablemente totales)
            # Patrón mejorado: solo números y comas/puntos (sin texto descriptivo)
            line_clean = re.sub(r'[^\d,.\s]', '', line).strip()
            monetary_values = re.findall(r'([\d,]+\.\d{2})', line_clean)
            
            # Si hay múltiples valores y son grandes (probablemente totales)
            if len(monetary_values) >= 2:
                # Verificar que los valores sean grandes (más de 1000)
                large_values = []
                for val_str in monetary_values:
                    try:
                        val = float(val_str.replace(',', ''))
                        if val >= 1000:  # Filtrar valores pequeños
                            large_values.append((val_str, val))
                    except ValueError:
                        continue
                
                # Si hay al menos 2 valores grandes, probablemente son totales semanales
                if len(large_values) >= 2:
                    # Verificar que la línea NO tenga descripciones de items (solo números)
                    # Si la línea tiene menos de 10 caracteres no numéricos, probablemente es totales
                    non_numeric_chars = len(re.sub(r'[\d,.\s]', '', line))
                    
                    # Verificar contexto: líneas anteriores/siguientes
                    context_lines = lines[max(0, i-3):min(len(lines), i+4)]
                    has_item_descriptions = any(
                        any(keyword in ctx.lower() for keyword in [
                            'cajamarca', 'oficina', 'vigilancia', 'bancarios', 
                            'proveedor', 'rimac', 'seguros', 'cbp', 'travel',
                            'remodelacion', 'alquiler', 'servicio', 'gastos'
                        ])
                        for ctx in context_lines
                    )
                    
                    # Si la línea tiene pocos caracteres no numéricos Y no tiene descripciones de items
                    # Y está después de una línea con items, probablemente es totales
                    is_after_items = False
                    if i > 0:
                        prev_lines = lines[max(0, i-5):i]
                        is_after_items = any(
                            any(keyword in prev.lower() for keyword in [
                                'cajamarca', 'oficina', 'vigilancia', 'bancarios', 
                                'proveedor', 'rimac', 'seguros', 'cbp', 'travel'
                            ])
                            for prev in prev_lines
                        )
                    
                    # Si cumple las condiciones, es una línea de totales
                    if (non_numeric_chars < 10 and not has_item_descriptions) or (is_after_items and non_numeric_chars < 20):
                        # Asociar cada valor con su semana correspondiente
                        # Ordenar semanas encontradas para asociar correctamente
                        weeks_sorted = sorted(weeks_found, key=int)
                        for j, (val_str, val) in enumerate(large_values):
                            if j < len(weeks_sorted):
                                week_num = weeks_sorted[j]
                                totals.append({
                                    "tjobno": None,
                                    "ttype": f"Week {week_num} Total",
                                    "tsourcereference": None,
                                    "tsourcerefid": f"Week {week_num}",
                                    "tdescription": f"Total Week {week_num}",
                                    "nImporte": val,
                                    "tStampname": None,
                                    "tsequentialnumber": None,
                                    "_weekly_total": True,
                                    "_week_number": week_num
                                })
        
        return totals
    
    def _extract_cash_flow_values(self, ocr_text: str) -> List[Dict]:
        """
        Extrae valores de Cash Flow (Total Disbursement, Period Balance, Cumulative Cash Flow).
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con valores de Cash Flow en formato mresumen
        """
        cash_flow_items = []
        lines = ocr_text.split('\n')
        
        # Buscar "Total Disbursement"
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            if 'total disbursement' in line_lower:
                # Buscar valores monetarios en esta línea o líneas siguientes
                search_lines = lines[i:min(len(lines), i+2)]
                for search_line in search_lines:
                    monetary_values = re.findall(r'([\d,]+\.?\d*)', search_line)
                    for val_str in monetary_values:
                        try:
                            val = float(val_str.replace(',', ''))
                            if val >= 1.0:
                                cash_flow_items.append({
                                    "tjobno": None,
                                    "ttype": "Cash Flow - Total Disbursement",
                                    "tsourcereference": None,
                                    "tsourcerefid": None,
                                    "tdescription": f"Total Disbursement: {val:,.2f}",
                                    "nImporte": val,
                                    "tStampname": None,
                                    "tsequentialnumber": None,
                                    "_cash_flow": True,
                                    "_cash_flow_type": "Total Disbursement"
                                })
                        except ValueError:
                            continue
            
            # Buscar "Period Balance"
            if 'period balance' in line_lower:
                # Buscar valores entre paréntesis (valores negativos) o valores normales
                search_lines = lines[i:min(len(lines), i+2)]
                for search_line in search_lines:
                    # Buscar valores entre paréntesis: (305,350)
                    negative_values = re.findall(r'\(([\d,]+\.?\d*)\)', search_line)
                    for val_str in negative_values:
                        try:
                            val = float(val_str.replace(',', ''))
                            if val >= 1.0:
                                cash_flow_items.append({
                                    "tjobno": None,
                                    "ttype": "Cash Flow - Period Balance",
                                    "tsourcereference": None,
                                    "tsourcerefid": None,
                                    "tdescription": f"Period Balance: ({val:,.2f})",
                                    "nImporte": -val,  # Negativo porque está entre paréntesis
                                    "tStampname": None,
                                    "tsequentialnumber": None,
                                    "_cash_flow": True,
                                    "_cash_flow_type": "Period Balance"
                                })
                        except ValueError:
                            continue
                    
                    # También buscar valores positivos sin paréntesis
                    positive_values = re.findall(r'(?<!\()([\d,]+\.\d{2})(?!\))', search_line)
                    for val_str in positive_values:
                        try:
                            val = float(val_str.replace(',', ''))
                            if val >= 1000:  # Filtrar valores pequeños
                                cash_flow_items.append({
                                    "tjobno": None,
                                    "ttype": "Cash Flow - Period Balance",
                                    "tsourcereference": None,
                                    "tsourcerefid": None,
                                    "tdescription": f"Period Balance: {val:,.2f}",
                                    "nImporte": val,
                                    "tStampname": None,
                                    "tsequentialnumber": None,
                                    "_cash_flow": True,
                                    "_cash_flow_type": "Period Balance"
                                })
                        except ValueError:
                            continue
            
            # Buscar "Cumulative Cash Flow"
            if 'cumulative cash flow' in line_lower:
                search_lines = lines[i:min(len(lines), i+2)]
                for search_line in search_lines:
                    monetary_values = re.findall(r'([\d,]+\.\d{2})', search_line)
                    for val_str in monetary_values:
                        try:
                            val = float(val_str.replace(',', ''))
                            # Incluir valores negativos también
                            if abs(val) >= 1.0:
                                cash_flow_items.append({
                                    "tjobno": None,
                                    "ttype": "Cash Flow - Cumulative",
                                    "tsourcereference": None,
                                    "tsourcerefid": None,
                                    "tdescription": f"Cumulative Cash Flow: {val:,.2f}",
                                    "nImporte": val,
                                    "tStampname": None,
                                    "tsequentialnumber": None,
                                    "_cash_flow": True,
                                    "_cash_flow_type": "Cumulative Cash Flow"
                                })
                        except ValueError:
                            continue
            
            # Buscar valores mencionados en el texto (ej: "305,349.84 USD" en Week 28)
            week_amount_match = re.search(r'Week\s+(\d+).*?([\d,]+\.\d{2})\s*USD', ocr_text, re.IGNORECASE)
            if week_amount_match:
                week_num = week_amount_match.group(1)
                amount_str = week_amount_match.group(2)
                try:
                    amount = float(amount_str.replace(',', ''))
                    if amount >= 1.0:
                        cash_flow_items.append({
                            "tjobno": None,
                            "ttype": f"Cash Flow - Week {week_num}",
                            "tsourcereference": None,
                            "tsourcerefid": f"Week {week_num}",
                            "tdescription": f"Amount Week {week_num}: {amount:,.2f} USD",
                            "nImporte": amount,
                            "tStampname": None,
                            "tsequentialnumber": None,
                            "_cash_flow": True,
                            "_cash_flow_type": f"Week {week_num} Amount"
                        })
                except ValueError:
                    pass
        
        return cash_flow_items
    
    def _extract_oracle_ap_data(self, ocr_text: str) -> Optional[Dict]:
        """
        Extrae datos específicos de documentos Oracle AP (Accounts Payable).
        
        Detecta campos como Invoice Num, Invoice Amount, Tax Amount, Due Date,
        Gross Amount, Payment Method, Supplier information, etc.
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Diccionario con datos de Oracle AP o None si no es un documento Oracle
        """
        # Verificar si es un documento Oracle AP
        if not any(keyword in ocr_text for keyword in ['Operating Unit', 'Invoice Num', 'Scheduled Payments', 'Oracle']):
            return None
        
        oracle_data = {
            'comprobante_fields': {},
            'payment_details': []
        }
        
        # Extraer datos de tabla Oracle AP (headers en una línea, valores en la siguiente)
        lines = ocr_text.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Buscar línea con headers de Oracle AP
            if 'operating unit' in line_lower and 'invoice num' in line_lower:
                # La siguiente línea debería tener los valores
                if i + 1 < len(lines):
                    values_line = lines[i + 1].strip()
                    # Extraer valores de la línea (están separados por espacios)
                    # Formato: "PEN - BECHTEL PE Standard RIMAC SE 934001256 XYQN-WIRE 20-JUN-2025 F581-06891423 USD 655740.75 100028.25"
                    parts = values_line.split()
                    
                    # Buscar Operating Unit (primeros elementos hasta encontrar "Standard" o similar)
                    if 'Standard' in values_line or 'PEN' in values_line or 'USD' in values_line:
                        # Buscar "PEN - BECHTEL PE" o similar
                        operating_unit_match = re.search(r'([A-Z]{3}\s*-\s*[A-Z\s]+)', values_line)
                        if operating_unit_match:
                            oracle_data['comprobante_fields']['_oracle_operating_unit'] = operating_unit_match.group(1).strip()
                    
                    # Buscar Supplier Name (después de "Standard", generalmente "RIMAC SE")
                    supplier_match = re.search(r'Standard\s+([A-Z][A-Z\s]+(?:SE|S\.A\.|SRL|LLC|INC|LTD)?)', values_line, re.IGNORECASE)
                    if supplier_match:
                        supplier_name = supplier_match.group(1).strip()
                        supplier_name = ' '.join(supplier_name.split())
                        if len(supplier_name) <= 100:
                            oracle_data['comprobante_fields']['_oracle_supplier_name'] = supplier_name
                    
                    # Buscar Supplier Num (número de 9 dígitos)
                    supplier_num_match = re.search(r'\b(\d{9})\b', values_line)
                    if supplier_num_match:
                        oracle_data['comprobante_fields']['_oracle_supplier_num'] = supplier_num_match.group(1)
                    
                    # Buscar Supplier Site (formato XYQN-WIRE)
                    supplier_site_match = re.search(r'([A-Z0-9]+-[A-Z]+)', values_line)
                    if supplier_site_match:
                        oracle_data['comprobante_fields']['_oracle_supplier_site'] = supplier_site_match.group(1)
                    
                    # Buscar Invoice Date (formato 20-JUN-2025)
                    invoice_date_match = re.search(r'(\d{1,2}-[A-Z]{3}-\d{4})', values_line)
                    if invoice_date_match:
                        oracle_data['comprobante_fields']['_oracle_invoice_date'] = invoice_date_match.group(1)
                    
                    # Buscar Invoice Num (formato F581-06891423)
                    invoice_num_match = re.search(r'([A-Z]\d+-\d+)', values_line)
                    if invoice_num_match:
                        oracle_data['comprobante_fields']['_oracle_invoice_num'] = invoice_num_match.group(1)
                    
                    # Buscar Invoice Amount (USD seguido de número grande)
                    invoice_amount_match = re.search(r'USD\s+([\d,]+\.?\d*)', values_line, re.IGNORECASE)
                    if invoice_amount_match:
                        try:
                            amount = float(invoice_amount_match.group(1).replace(',', ''))
                            oracle_data['comprobante_fields']['_oracle_invoice_amount'] = amount
                        except ValueError:
                            pass
                    
                    # Buscar Tax Amount (número después del Invoice Amount)
                    # Generalmente está después del Invoice Amount
                    tax_amount_match = re.search(r'USD\s+[\d,]+\.?\d*\s+([\d,]+\.?\d*)', values_line, re.IGNORECASE)
                    if tax_amount_match:
                        try:
                            tax = float(tax_amount_match.group(1).replace(',', ''))
                            oracle_data['comprobante_fields']['_oracle_tax_amount'] = tax
                        except ValueError:
                            pass
                    break
        
        # Extraer datos de la tabla "Scheduled Payments"
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Buscar línea con headers de Scheduled Payments
            if 'scheduled payments' in line_lower or ('due date' in line_lower and 'gross amount' in line_lower):
                # Buscar valores en líneas siguientes
                for j in range(i + 1, min(len(lines), i + 5)):
                    payment_line = lines[j].strip()
                    if not payment_line:
                        continue
                    
                    # Buscar Due Date (formato 30-JUN-2025)
                    due_date_match = re.search(r'(\d{1,2}-[A-Z]{3}-\d{4})', payment_line)
                    if due_date_match:
                        oracle_data['comprobante_fields']['_oracle_due_date'] = due_date_match.group(1)
                    
                    # Buscar Gross Amount (número grande, generalmente sin comas en Oracle)
                    gross_amount_match = re.search(r'(\d{6,}\.?\d*)', payment_line)
                    if gross_amount_match:
                        try:
                            gross = float(gross_amount_match.group(1).replace(',', ''))
                            if gross >= 1000:  # Filtrar valores pequeños
                                if not oracle_data['comprobante_fields'].get('_oracle_gross_amount'):
                                    oracle_data['comprobante_fields']['_oracle_gross_amount'] = gross
                        except ValueError:
                            pass
                    
                    # Buscar Payment Currency (USD, PEN, EUR)
                    payment_currency_match = re.search(r'\b(USD|PEN|EUR)\b', payment_line, re.IGNORECASE)
                    if payment_currency_match:
                        oracle_data['comprobante_fields']['_oracle_payment_currency'] = payment_currency_match.group(1).upper()
                    
                    # Buscar Payment Method (Wire, Check, etc.)
                    if 'wire' in payment_line.lower():
                        oracle_data['comprobante_fields']['_oracle_payment_method'] = 'Wire'
                    elif 'check' in payment_line.lower():
                        oracle_data['comprobante_fields']['_oracle_payment_method'] = 'Check'
                    elif 'transfer' in payment_line.lower():
                        oracle_data['comprobante_fields']['_oracle_payment_method'] = 'Transfer'
                    
                    # Si encontramos al menos un campo, continuar buscando en esta sección
                    if any(key in oracle_data['comprobante_fields'] for key in ['_oracle_due_date', '_oracle_gross_amount', '_oracle_payment_currency']):
                        continue
                    else:
                        break
        
        # Extraer Invoice Num (ya se extrae arriba, pero lo verificamos también con regex general)
        if not oracle_data['comprobante_fields'].get('_oracle_invoice_num'):
            invoice_num_match = re.search(r'Invoice\s+Num[:\s]+([A-Z0-9\-]+)', ocr_text, re.IGNORECASE)
            if invoice_num_match:
                oracle_data['comprobante_fields']['_oracle_invoice_num'] = invoice_num_match.group(1).strip()
        
        # Extraer Invoice Amount
        # Patrón 1: "Invoice Invoice Amount USD 655740.75"
        invoice_amount_match = re.search(r'Invoice\s+(?:Invoice\s+)?Amount\s+(?:USD|PEN|EUR)\s+([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        if not invoice_amount_match:
            # Patrón 2: "Invoice Amount" seguido de currency y amount en líneas cercanas
            lines = ocr_text.split('\n')
            for i, line in enumerate(lines):
                if 'invoice amount' in line.lower():
                    # Buscar en la misma línea o líneas siguientes
                    search_lines = lines[i:min(len(lines), i+2)]
                    for search_line in search_lines:
                        # Buscar patrón: "USD 655740.75" o "655740.75 USD"
                        amount_match = re.search(r'(?:USD|PEN|EUR)\s+([\d,]+\.?\d*)|([\d,]+\.?\d*)\s+(?:USD|PEN|EUR)', search_line, re.IGNORECASE)
                        if amount_match:
                            amount_str = amount_match.group(1) or amount_match.group(2)
                            try:
                                amount = float(amount_str.replace(',', ''))
                                oracle_data['comprobante_fields']['_oracle_invoice_amount'] = amount
                                break
                            except ValueError:
                                continue
                    if oracle_data['comprobante_fields'].get('_oracle_invoice_amount'):
                        break
        else:
            try:
                amount = float(invoice_amount_match.group(1).replace(',', ''))
                oracle_data['comprobante_fields']['_oracle_invoice_amount'] = amount
            except ValueError:
                pass
        
        # Extraer Tax Amount
        tax_amount_match = re.search(r'Tax\s+Amount[:\s]+([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        if tax_amount_match:
            try:
                tax = float(tax_amount_match.group(1).replace(',', ''))
                oracle_data['comprobante_fields']['_oracle_tax_amount'] = tax
            except ValueError:
                pass
        
        # Extraer Invoice Date
        invoice_date_match = re.search(r'Invoice\s+Date[:\s]+([\d]{1,2}[-/][A-Z]{3}[-/][\d]{4})', ocr_text, re.IGNORECASE)
        if invoice_date_match:
            oracle_data['comprobante_fields']['_oracle_invoice_date'] = invoice_date_match.group(1).strip()
        
        # Extraer Due Date
        due_date_match = re.search(r'Due\s+Date[:\s]+([\d]{1,2}[-/][A-Z]{3}[-/][\d]{4})', ocr_text, re.IGNORECASE)
        if due_date_match:
            oracle_data['comprobante_fields']['_oracle_due_date'] = due_date_match.group(1).strip()
        
        # Extraer Gross Amount (Payment Gross Amount)
        gross_amount_match = re.search(r'Gross\s+Amount[:\s]+([\d,]+\.?\d*)', ocr_text, re.IGNORECASE)
        if gross_amount_match:
            try:
                gross = float(gross_amount_match.group(1).replace(',', ''))
                oracle_data['comprobante_fields']['_oracle_gross_amount'] = gross
            except ValueError:
                pass
        
        # Extraer Payment Currency
        payment_currency_match = re.search(r'Payment[:\s]+Currency[:\s]+([A-Z]{3})', ocr_text, re.IGNORECASE)
        if payment_currency_match:
            oracle_data['comprobante_fields']['_oracle_payment_currency'] = payment_currency_match.group(1).strip()
        
        # Extraer Payment Method
        payment_method_match = re.search(r'Method[:\s]+([A-Za-z]+)', ocr_text, re.IGNORECASE)
        if payment_method_match:
            oracle_data['comprobante_fields']['_oracle_payment_method'] = payment_method_match.group(1).strip()
        
        # Extraer Supplier Num
        supplier_num_match = re.search(r'Supplier\s+Num[:\s]+([\d]+)', ocr_text, re.IGNORECASE)
        if supplier_num_match:
            oracle_data['comprobante_fields']['_oracle_supplier_num'] = supplier_num_match.group(1).strip()
        
        # Extraer Operating Unit
        operating_unit_match = re.search(r'Operating\s+Unit[:\s]+([^:\n]+)', ocr_text, re.IGNORECASE)
        if operating_unit_match:
            oracle_data['comprobante_fields']['_oracle_operating_unit'] = operating_unit_match.group(1).strip()
        
        # Extraer Supplier Name (PO Trading Pa o Supplier Name)
        # Buscar en líneas específicas para evitar capturar texto incorrecto
        lines = ocr_text.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            # Buscar "PO Trading Pa" o "Supplier Name" en la línea
            if 'po trading pa' in line_lower or 'supplier name' in line_lower:
                # Buscar el valor en la misma línea o línea siguiente
                # Patrón: "PO Trading Pa RIMAC SE" o "Supplier Name: RIMAC SE"
                supplier_match = re.search(r'(?:PO\s+Trading\s+Pa|Supplier\s+Name)[:\s]+([A-Z][A-Z\s]+(?:SE|S\.A\.|SRL|LLC|INC|LTD)?)', line, re.IGNORECASE)
                if supplier_match:
                    supplier_name = supplier_match.group(1).strip()
                    # Limpiar espacios múltiples
                    supplier_name = ' '.join(supplier_name.split())
                    # Limitar longitud
                    if len(supplier_name) > 100:
                        supplier_name = supplier_name[:100]
                    oracle_data['comprobante_fields']['_oracle_supplier_name'] = supplier_name
                    break
                # Si no se encontró en la misma línea, buscar en la siguiente
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Buscar nombre de proveedor (generalmente en mayúsculas)
                    supplier_match_next = re.search(r'^([A-Z][A-Z\s]+(?:SE|S\.A\.|SRL|LLC|INC|LTD)?)', next_line)
                    if supplier_match_next:
                        supplier_name = supplier_match_next.group(1).strip()
                        supplier_name = ' '.join(supplier_name.split())
                        if len(supplier_name) > 100:
                            supplier_name = supplier_name[:100]
                        oracle_data['comprobante_fields']['_oracle_supplier_name'] = supplier_name
                        break
        
        # Extraer Supplier Site
        supplier_site_match = re.search(r'Supplier\s+Site[:\s]+([A-Z0-9\-]+)', ocr_text, re.IGNORECASE)
        if supplier_site_match:
            oracle_data['comprobante_fields']['_oracle_supplier_site'] = supplier_site_match.group(1).strip()
        
        # Crear detalles de pago programado
        if oracle_data['comprobante_fields'].get('_oracle_gross_amount'):
            payment_detail = {
                "nCantidad": 1.0,
                "tDescripcion": f"Oracle AP Payment - {oracle_data['comprobante_fields'].get('_oracle_payment_method', 'N/A')}",
                "nPrecioUnitario": oracle_data['comprobante_fields']['_oracle_gross_amount'],
                "nPrecioTotal": oracle_data['comprobante_fields']['_oracle_gross_amount'],
                "_oracle_payment": True,
                "_oracle_due_date": oracle_data['comprobante_fields'].get('_oracle_due_date'),
                "_oracle_payment_method": oracle_data['comprobante_fields'].get('_oracle_payment_method'),
                "_oracle_payment_currency": oracle_data['comprobante_fields'].get('_oracle_payment_currency')
            }
            oracle_data['payment_details'].append(payment_detail)
        
        # Si hay Tax Amount, agregarlo como detalle separado
        if oracle_data['comprobante_fields'].get('_oracle_tax_amount'):
            tax_detail = {
                "nCantidad": 1.0,
                "tDescripcion": "Oracle AP Tax Amount",
                "nPrecioUnitario": oracle_data['comprobante_fields']['_oracle_tax_amount'],
                "nPrecioTotal": oracle_data['comprobante_fields']['_oracle_tax_amount'],
                "_oracle_tax": True
            }
            oracle_data['payment_details'].append(tax_detail)
        
        return oracle_data if oracle_data['comprobante_fields'] or oracle_data['payment_details'] else None
    
    def _extract_concur_expense_data(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """
        Extrae datos de Concur Expense Reports.
        
        Captura:
        - Report Total
        - Subtotal
        - Total for XXX (totales por código)
        - Amount Less Tax
        - Tax
        - Transacciones individuales
        - Job Section
        - Expense Type
        - Merchant information
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Diccionario con datos estructurados en formato mresumen y mcomprobante_detalle
        """
        result = {}
        resumen_items = []
        detalle_items = []
        
        # Extraer Stamp Name y Sequential Number
        stamp_info = self.extract_stamp_info(ocr_text)
        stamp_name = stamp_info.get("stamp_name")
        sequential_number = stamp_info.get("sequential_number")
        
        # Extraer Job Section (ej: "26443-331-----")
        job_section_match = re.search(r'Line\s+Item\s+by\s+Job\s+Section\s+([\d\-]+)', ocr_text, re.IGNORECASE)
        job_section = job_section_match.group(1).strip() if job_section_match else None
        
        # Extraer Report Name (ej: "Concur Expense - Transportes Terrestres")
        report_name_match = re.search(r'Concur\s+Expense\s*-\s*([^\n]+)', ocr_text, re.IGNORECASE)
        report_name = report_name_match.group(1).strip() if report_name_match else None
        
        lines = ocr_text.split('\n')
        
        # Extraer TODOS los totales (Report Total, Subtotal, Total for XXX, Amount Less Tax, Tax)
        totals_found = {}
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Report Total
            if 'report total' in line_lower:
                total_match = re.search(r'Report\s+Total[:\s]+([\d,]+\.?\d*)', line, re.IGNORECASE)
                if total_match:
                    try:
                        amount = float(total_match.group(1).replace(',', ''))
                        totals_found['report_total'] = amount
                    except ValueError:
                        pass
            
            # Subtotal
            if 'subtotal' in line_lower and 'report total' not in line_lower:
                subtotal_match = re.search(r'Subtotal[:\s]+([\d,]+\.?\d*)', line, re.IGNORECASE)
                if subtotal_match:
                    try:
                        amount = float(subtotal_match.group(1).replace(',', ''))
                        totals_found['subtotal'] = amount
                    except ValueError:
                        pass
            
            # Total for XXX (ej: "Total for 611")
            total_for_match = re.search(r'Total\s+for\s+(\d+)[:\s]+([\d,]+\.?\d*)', line, re.IGNORECASE)
            if total_for_match:
                code = total_for_match.group(1)
                try:
                    amount = float(total_for_match.group(2).replace(',', ''))
                    totals_found[f'total_for_{code}'] = amount
                except ValueError:
                    pass
            
            # Amount Less Tax
            if 'amount less tax' in line_lower:
                amount_less_tax_match = re.search(r'Amount\s+Less\s+Tax[:\s]+([\d,]+\.?\d*)', line, re.IGNORECASE)
                if amount_less_tax_match:
                    try:
                        amount = float(amount_less_tax_match.group(1).replace(',', ''))
                        totals_found['amount_less_tax'] = amount
                    except ValueError:
                        pass
            
            # Tax
            if 'tax' in line_lower and 'amount less tax' not in line_lower and 'taxi' not in line_lower:
                tax_match = re.search(r'Tax[:\s]+([\d,]+\.?\d*)', line, re.IGNORECASE)
                if tax_match:
                    try:
                        amount = float(tax_match.group(1).replace(',', ''))
                        totals_found['tax'] = amount
                    except ValueError:
                        pass
        
        # Agregar todos los totales a mresumen
        for total_name, amount in totals_found.items():
            resumen_items.append({
                "tjobno": job_section,
                "ttype": f"Concur Expense - {total_name.replace('_', ' ').title()}",
                "tsourcereference": sequential_number,
                "tsourcerefid": None,
                "tdescription": f"{total_name.replace('_', ' ').title()}: {amount:,.2f}",
                "nImporte": amount,
                "tStampname": stamp_name,
                "tsequentialnumber": sequential_number,
                "_concur_total": True,
                "_total_type": total_name,
                "_report_name": report_name
            })
        
        # Extraer transacciones individuales (items de la tabla)
        # Buscar líneas con fechas y montos
        for i, line in enumerate(lines):
            # Buscar líneas con formato de fecha (Jun 23, 2025 o 2025-06-23)
            date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})', line)
            if date_match:
                # Buscar monto en la línea (formato 90,000.00)
                amount_match = re.search(r'([\d,]+\.\d{2})', line)
                if amount_match:
                    try:
                        amount = float(amount_match.group(1).replace(',', ''))
                        # Buscar Expense Type en líneas cercanas
                        expense_type = None
                        for j in range(max(0, i-2), min(len(lines), i+3)):
                            if 'taxi' in lines[j].lower() or 'ground trans' in lines[j].lower():
                                expense_type_match = re.search(r'([A-Z][^0-9]+(?:Taxi|Ground|Trans)[^0-9]*)', lines[j], re.IGNORECASE)
                                if expense_type_match:
                                    expense_type = expense_type_match.group(1).strip()
                                    break
                        
                        # Buscar Merchant
                        merchant = None
                        for j in range(i, min(len(lines), i+5)):
                            if 'merchant:' in lines[j].lower():
                                merchant_match = re.search(r'Merchant:\s*([^\n]+)', lines[j], re.IGNORECASE)
                                if merchant_match:
                                    merchant = merchant_match.group(1).strip()
                                    break
                        
                        # Buscar Location
                        location = None
                        location_match = re.search(r'\b(Quilpué|Santiago|Lima|Arequipa|Cusco)\b', line, re.IGNORECASE)
                        if location_match:
                            location = location_match.group(1)
                        
                        # Buscar NC (código numérico)
                        nc_match = re.search(r'\b(\d{3})\b', line)
                        nc_code = nc_match.group(1) if nc_match else None
                        
                        detalle_items.append({
                            "nCantidad": 1.0,
                            "tDescripcion": f"{expense_type or 'Expense'} - {merchant or 'N/A'} - {location or 'N/A'}",
                            "nPrecioUnitario": amount,
                            "nPrecioTotal": amount,
                            "_concur_transaction": True,
                            "_transaction_date": date_match.group(1),
                            "_expense_type": expense_type,
                            "_merchant": merchant,
                            "_location": location,
                            "_nc_code": nc_code,
                            "_job_section": job_section
                        })
                    except ValueError:
                        continue
        
        # Crear comprobante principal con Report Total
        if totals_found.get('report_total'):
            comprobante_items = [{
                "tNumero": sequential_number,
                "tSerie": None,
                "nPrecioTotal": totals_found['report_total'],
                "_stamp_name": stamp_name,
                "_sequential_number": sequential_number,
                "_concur_expense": True,
                "_report_name": report_name,
                "_job_section": job_section
            }]
            result["mcomprobante"] = comprobante_items
        
        if resumen_items:
            result["mresumen"] = resumen_items
        
        if detalle_items:
            result["mcomprobante_detalle"] = detalle_items
        
        return result if result else None
    
    def _extract_jornada_highlighted_values(self, ocr_text: str) -> List[Dict]:
        """
        Extrae valores destacados (cuadros rojos) de documentos jornada.
        
        Busca filas "Total" con valores monetarios destacados, como:
        "$ 6,589.00 Total $ 6,589.00 $ 4,301.00 $ 2,068.00 $ - $ - $ - $ - $ - $ 220.00"
        
        También extrae totales de horas destacados como:
        "195.50 94.00" en filas de totales
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con valores destacados en formato mresumen
        """
        highlights = []
        
        # Buscar todas las filas que contengan "Total" y valores monetarios
        lines = ocr_text.split('\n')
        for line in lines:
            line = line.strip()
            if 'Total' in line and '$' in line:
                # Extraer todos los valores monetarios de la línea
                monetary_values = re.findall(r'\$\s*([\d,]+\.\d{2})', line)
                
                if len(monetary_values) >= 3:  # Al menos total general + 2 valores destacados
                    # El primer valor suele ser el total general
                    # Los siguientes son valores destacados por columna
                    # Extraer valores destacados (excluyendo el total general duplicado)
                    highlighted_values = []
                    seen_first = False
                    for val_str in monetary_values:
                        if val_str != '-' and val_str.replace(',', '').replace('.', '').isdigit():
                            try:
                                val = float(val_str.replace(',', ''))
                                if val > 0:  # Solo valores positivos
                                    # Saltar el primer valor (total general) y su duplicado
                                    if not seen_first:
                                        seen_first = True
                                        continue
                                    # Agregar valores destacados (4,301.00, 2,068.00, etc.)
                                    if val < 10000:  # Valores destacados suelen ser menores que el total
                                        highlighted_values.append(val)
                            except ValueError:
                                continue
                    
                    # Crear entrada para cada valor destacado
                    for i, val in enumerate(highlighted_values):
                        column_info = f"Columna {i+1}" if i < len(highlighted_values) else "Destacado"
                        
                        highlights.append({
                            "tDescripcion": f"Valor destacado {column_info}: ${val:,.2f} (de fila Total)",
                            "tjobno": None,
                            "ttype": None,
                            "nMonto": val,
                            "tDivisa": "USD",  # Generalmente USD en estos documentos
                            "_highlighted": True,
                            "_source_line": line,
                            "_column_position": i + 1
                        })
        
        # Patrón 2: Totales de horas destacados
        # Buscar líneas con totales de horas que puedan estar en cuadros rojos
        # Ejemplo: "195.50 94.00" en filas de totales (después de filas de empleados)
        for i, line in enumerate(lines):
            line = line.strip()
            # Buscar líneas con múltiples valores numéricos que parezcan totales de horas
            # Estas suelen estar después de filas de empleados y antes de "Plan OH/hr"
            if i > 0 and i < len(lines) - 2:  # No primera ni últimas líneas
                prev_line = lines[i-1].strip() if i > 0 else ""
                next_line = lines[i+1].strip() if i < len(lines) - 1 else ""
                
                # Si la línea anterior tiene datos de empleado y la siguiente tiene "Plan" o "check"
                if (re.search(r'\d{6}\s+[A-Z]', prev_line) or '195.50' in prev_line) and ('Plan' in next_line or 'check' in next_line):
                    hours_values = re.findall(r'(\d{1,3}\.\d{2})', line)
                    if len(hours_values) >= 2:
                        # Estos son totales de horas por columna (los primeros 2 son los destacados)
                        for j, hours_str in enumerate(hours_values[:2]):
                            try:
                                hours = float(hours_str)
                                if hours > 0 and hours < 1000:  # Horas razonables
                                    highlights.append({
                                        "tDescripcion": f"Total horas destacado Columna {j+1}: {hours} horas",
                                        "tjobno": None,
                                        "ttype": None,
                                        "nMonto": hours,
                                        "tDivisa": None,  # Horas no tienen divisa
                                        "_highlighted": True,
                                        "_hours_total": True,
                                        "_source_line": line,
                                        "_column_position": j + 1
                                    })
                            except ValueError:
                                continue
        
        return highlights
    
    def _extract_all_monetary_values(self, ocr_text: str) -> List[Dict]:
        """
        Extrae TODOS los valores monetarios y numéricos del texto, sin importar el formato.
        Esta función es muy general y captura cualquier valor que parezca monetario.
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Lista de diccionarios con valores monetarios encontrados
        """
        if not ocr_text or not ocr_text.strip():
            return []
        
        monetary_values = []
        lines = ocr_text.split('\n')
        
        # Patrones para valores monetarios (muy amplios)
        # Patrón 1: $ XXX.XX o $ X,XXX.XX o $XXX.XX (con o sin espacio)
        pattern1 = r'\$\s*([\d,]+\.\d{2})'
        # Patrón 1b: $XX o $XXX (sin decimales, pero con símbolo $)
        pattern1b = r'\$\s*(\d{1,6})\b'
        # Patrón 2: USD XXX.XX o USD X,XXX.XX (con espacio)
        pattern2 = r'USD\s+([\d,]+\.\d{2})'
        # Patrón 2b: USDXXX.XX (sin espacio entre USD y el número, como "USD5.30")
        pattern2b = r'USD([\d,]+\.\d{2})\b'
        # Patrón 2c: USDXX o USDXXX (sin espacio y sin decimales)
        pattern2c = r'USD(\d{1,6})\b'
        # Patrón 3: Números con decimales que parecen montos (XX.XX, XXX.XX o X,XXX.XX)
        # Cambiado de {3,} a {2,} para capturar valores como 41.35
        pattern3 = r'\b([\d,]{2,}\.\d{2})\b'
        # Patrón 4: Números con formato XXX,XXX.XX (sin símbolo de moneda)
        pattern4 = r'\b([\d]{1,3}(?:,\d{3})+\.\d{2})\b'
        # Patrón 5: Números pequeños que pueden ser montos (10, 20, etc.) cuando están en contexto monetario
        # Solo capturar si están en líneas que contienen palabras monetarias o están cerca de otros valores monetarios
        pattern5 = r'\b(\d{1,2})\b'
        
        seen_amounts = set()  # Para evitar duplicados
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Buscar todos los patrones en la línea
            all_matches = []
            
            # Buscar con patrón 1 ($ XXX.XX o $XXX.XX)
            for match in re.finditer(pattern1, line):
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    if amount > 0 and amount < 100000000:  # Valores razonables
                        all_matches.append(('$', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 1b ($XX o $XXX sin decimales)
            for match in re.finditer(pattern1b, line):
                amount_str = match.group(1)
                try:
                    amount = float(amount_str)
                    if amount > 0 and amount < 1000000:  # Valores razonables
                        all_matches.append(('$', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 2 (USD XXX.XX con espacio)
            for match in re.finditer(pattern2, line, re.IGNORECASE):
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    if amount > 0 and amount < 100000000:
                        all_matches.append(('USD', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 2b (USDXXX.XX sin espacio, como "USD5.30")
            for match in re.finditer(pattern2b, line, re.IGNORECASE):
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    if amount > 0 and amount < 100000000:
                        all_matches.append(('USD', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 2c (USDXX o USDXXX sin espacio y sin decimales)
            for match in re.finditer(pattern2c, line, re.IGNORECASE):
                amount_str = match.group(1)
                try:
                    amount = float(amount_str)
                    if amount > 0 and amount < 1000000:
                        all_matches.append(('USD', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 3 (números con decimales: XX.XX, XXX.XX, etc.)
            for match in re.finditer(pattern3, line):
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    # Filtrar: debe ser >= 1.00 y < 100000000, y tener al menos 2 dígitos antes del punto
                    if amount >= 1.00 and amount < 100000000 and len(amount_str.split('.')[0]) >= 2:
                        # Verificar que no sea parte de una fecha o código
                        context = line[max(0, match.start()-10):match.end()+10]
                        if not re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', context):
                            # Verificar que no sea parte de un código alfanumérico
                            if not re.search(r'[A-Za-z]\d+\.\d{2}|\d+\.\d{2}[A-Za-z]', context):
                                all_matches.append(('USD', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 4 (formato con comas: XXX,XXX.XX)
            for match in re.finditer(pattern4, line):
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    if amount >= 1.00 and amount < 100000000:
                        all_matches.append(('USD', amount, match.start()))
                except ValueError:
                    continue
            
            # Buscar con patrón 5 (números pequeños en contexto monetario)
            # Solo si la línea contiene palabras monetarias o está cerca de otros valores
            if any(keyword in line.lower() for keyword in ['currency', 'us currency', 'malaysia currency', 'total', 'tot', 'amount', 'fee', 'toll', '$']):
                for match in re.finditer(pattern5, line):
                    amount_str = match.group(1)
                    try:
                        amount = float(amount_str)
                        # Solo capturar números pequeños (1-99) en contexto monetario
                        if 1 <= amount <= 99:
                            # Verificar que no sea parte de una fecha (8-Jun-25, 15-Jun-25)
                            context = line[max(0, match.start()-15):match.end()+15]
                            if not re.search(r'\d{1,2}[-/](?:Jun|Jan|Feb|Mar|Apr|May|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/]\d{2,4}', context, re.IGNORECASE):
                                # Verificar que no sea parte de un código (BS0003, etc.)
                                if not re.search(r'[A-Z]{2,}\d+', context):
                                    all_matches.append(('USD', amount, match.start()))
                    except ValueError:
                        continue
            
            # Procesar matches encontrados
            for currency, amount, position in all_matches:
                # Evitar duplicados exactos
                amount_key = (amount, currency)
                if amount_key in seen_amounts:
                    continue
                seen_amounts.add(amount_key)
                
                # Extraer contexto/descripción de la línea
                # Limpiar la línea para obtener descripción
                desc_line = line[:position].strip() if position > 0 else line
                # Remover valores monetarios de la descripción
                desc_line = re.sub(r'\$\s*[\d,]+\.\d{2}', '', desc_line)  # $ XXX.XX
                desc_line = re.sub(r'\$\s*\d{1,6}\b', '', desc_line)  # $XX o $XXX
                desc_line = re.sub(r'USD\s+[\d,]+\.\d{2}', '', desc_line, flags=re.IGNORECASE)  # USD XXX.XX
                desc_line = re.sub(r'USD[\d,]+\.\d{2}\b', '', desc_line, flags=re.IGNORECASE)  # USDXXX.XX (sin espacio)
                desc_line = re.sub(r'USD\d{1,6}\b', '', desc_line, flags=re.IGNORECASE)  # USDXX o USDXXX (sin espacio)
                desc_line = re.sub(r'\b[\d,]{2,}\.\d{2}\b', '', desc_line)  # XX.XX o XXX.XX
                desc_line = desc_line.strip()[:100]  # Limitar longitud
                
                # Si no hay descripción, usar contexto de la línea
                if not desc_line or len(desc_line) < 3:
                    # Buscar palabras clave antes del valor
                    before_text = line[max(0, position-50):position].strip()
                    if before_text:
                        # Extraer últimas palabras antes del valor
                        words = before_text.split()[-3:]
                        desc_line = ' '.join(words) if words else f'Valor monetario línea {line_num+1}'
                    else:
                        desc_line = f'Valor monetario línea {line_num+1}'
                
                monetary_values.append({
                    'nCantidad': 1.0,
                    'tDescripcion': desc_line or f'Valor monetario {amount}',
                    'nPrecioUnitario': round(amount, 2),
                    'nPrecioTotal': round(amount, 2),
                    '_currency': currency,
                    '_source_line': line_num + 1,
                    '_auto_extracted': True
                })
        
        # Ordenar por monto descendente (los totales suelen ser más grandes)
        monetary_values.sort(key=lambda x: x['nPrecioTotal'], reverse=True)
        
        return monetary_values
    
    def _extract_departments_and_disciplines(self, ocr_text: str) -> Dict[str, List[Dict]]:
        """
        Extrae departamentos y disciplinas de documentos OnShore.
        
        Args:
            ocr_text: Texto extraído del OCR
            
        Returns:
            Diccionario con listas de departamentos y disciplinas encontrados
        """
        result = {
            "departments": [],
            "disciplines": []
        }
        
        text_lower = ocr_text.lower()
        
        # Lista de departamentos comunes en OnShore
        department_patterns = {
            "Engineering": ["engineering", "engineering department", "dept: engineering", "department: engineering"],
            "Operations": ["operations", "operations department", "dept: operations", "department: operations"],
            "Maintenance": ["maintenance", "maintenance department", "dept: maintenance", "department: maintenance"],
            "Safety": ["safety", "safety department", "health & safety", "health and safety", "dept: safety"],
            "Environmental": ["environmental", "environmental department", "dept: environmental", "department: environmental"],
            "Human Resources": ["human resources", "hr", "hr department", "human resources department"],
            "Finance": ["finance", "finance department", "financial", "financial department"],
            "IT Services": ["it services", "it", "information technology", "it department"],
            "Other Services": ["other services", "other", "miscellaneous", "misc"]
        }
        
        # Lista de disciplinas comunes en OnShore
        discipline_patterns = {
            "Engineering": ["engineering", "discipline: engineering", "type: engineering", "category: engineering"],
            "Operations": ["operations", "discipline: operations", "type: operations"],
            "Maintenance": ["maintenance", "discipline: maintenance", "type: maintenance"],
            "Safety": ["safety", "discipline: safety", "type: safety"],
            "Environmental": ["environmental", "discipline: environmental", "type: environmental"],
            "Project Management": ["project management", "discipline: project management"],
            "Quality Control": ["quality control", "qc", "discipline: quality control"],
            "Procurement": ["procurement", "discipline: procurement"],
            "Construction": ["construction", "discipline: construction"],
            "Logistics": ["logistics", "discipline: logistics"]
        }
        
        # Buscar departamentos
        found_departments = set()
        for dept_name, patterns in department_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    found_departments.add(dept_name)
                    # Buscar montos asociados al departamento
                    # Patrón: "Engineering Department - $450,000.00" o "Engineering: 450000"
                    dept_with_amount = re.search(
                        rf'{re.escape(pattern)}[:\s\-]+[\$]?\s*([\d,]+\.?\d*)',
                        ocr_text,
                        re.IGNORECASE
                    )
                    amount = None
                    if dept_with_amount:
                        try:
                            amount_str = dept_with_amount.group(1).replace(',', '')
                            amount = float(amount_str)
                        except (ValueError, AttributeError):
                            pass
                    
                    result["departments"].append({
                        "name": dept_name,
                        "amount": amount,
                        "pattern_found": pattern
                    })
                    break  # No duplicar si ya se encontró
        
        # Buscar disciplinas
        found_disciplines = set()
        for disc_name, patterns in discipline_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    found_disciplines.add(disc_name)
                    # Buscar valores asociados a la disciplina
                    # Patrón: "Discipline: Engineering - 1250.00" o "Type: Operations: 980"
                    disc_with_value = re.search(
                        rf'{re.escape(pattern)}[:\s\-]+([\d,]+\.?\d*)',
                        ocr_text,
                        re.IGNORECASE
                    )
                    value = None
                    if disc_with_value:
                        try:
                            value_str = disc_with_value.group(1).replace(',', '')
                            value = float(value_str)
                        except (ValueError, AttributeError):
                            pass
                    
                    result["disciplines"].append({
                        "name": disc_name,
                        "value": value,
                        "pattern_found": pattern
                    })
                    break  # No duplicar si ya se encontró
        
        # Buscar NC Codes que puedan mapear a disciplinas
        # NC Code 611 suele ser Engineering, etc.
        nc_code_pattern = re.compile(r'NC\s+Code[:\s]+(\d+)', re.IGNORECASE)
        nc_codes = nc_code_pattern.findall(ocr_text)
        for nc_code in nc_codes:
            # Mapeo común de NC Codes a disciplinas
            nc_mapping = {
                "611": "Engineering",
                "612": "Operations",
                "613": "Maintenance",
                "614": "Safety",
                "615": "Environmental"
            }
            if nc_code in nc_mapping:
                disc_name = nc_mapping[nc_code]
                if disc_name not in found_disciplines:
                    result["disciplines"].append({
                        "name": disc_name,
                        "value": None,
                        "pattern_found": f"NC Code {nc_code}",
                        "nc_code": nc_code
                    })
                    found_disciplines.add(disc_name)
        
        # Buscar Org Codes que puedan mapear a departamentos
        org_code_pattern = re.compile(r'Org\s+Code[:\s]+([A-Z0-9]+)', re.IGNORECASE)
        org_codes = org_code_pattern.findall(ocr_text)
        for org_code in org_codes:
            # Algunos org codes pueden indicar departamentos
            # Esto se puede expandir con un mapeo real si se conoce
            if org_code and org_code not in [item.get("org_code") for item in result["departments"]]:
                # Por ahora, solo registrar que se encontró un org code
                # El mapeo real se puede hacer después con datos reales
                pass
        
        # Eliminar duplicados manteniendo el primero encontrado
        seen_depts = set()
        unique_departments = []
        for dept in result["departments"]:
            if dept["name"] not in seen_depts:
                seen_depts.add(dept["name"])
                unique_departments.append(dept)
        result["departments"] = unique_departments
        
        seen_discs = set()
        unique_disciplines = []
        for disc in result["disciplines"]:
            if disc["name"] not in seen_discs:
                seen_discs.add(disc["name"])
                unique_disciplines.append(disc)
        result["disciplines"] = unique_disciplines
        
        # Solo retornar si se encontró algo
        if result["departments"] or result["disciplines"]:
            return result
        
        return {}

