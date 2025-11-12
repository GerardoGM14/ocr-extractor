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
                "invoice", "factura", "boleta", "bill",
                "fattura", "invoice no",
                # Encabezados comunes en boletas/recibos malayos/chinos
                "tarikh", "kuantiti", "harga", "jumlah", "no.",
                "jumlah/", "總計", "总计", "cash / invoice", "cash/invoice"
            ],
            "resumen": [
                "summary", "resumen", "consolidado", 
                "reimbursable expenditure"
            ],
            "jornada": [
                "empl no", "full name", "labor",
                "total hours", "employee", "empl"
            ]
        }
    
    def identify_document_type(self, ocr_text: str) -> str:
        """Identifica el tipo de documento según su contenido."""
        text_lower = ocr_text.lower()
        
        if any(pattern in text_lower for pattern in self.stamp_patterns["comprobante"]):
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
        
        # Extraer datos específicos según tipo
        if doc_type == "resumen":
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

        # Si el documento contiene "GL Journal Details", extraer también líneas como detalle
        if 'gl journal details'.lower() in ocr_text.lower():
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
        
        # Extraer cálculos destacados (cuadros rojos, boxes, etc.)
        highlighted_calculations = self._extract_highlighted_calculations(ocr_text)
        
        # Para documentos jornada, también extraer valores destacados de filas "Total"
        if doc_type == "jornada":
            jornada_highlights = self._extract_jornada_highlighted_values(ocr_text)
            if jornada_highlights:
                highlighted_calculations.extend(jornada_highlights)
        
        if highlighted_calculations:
            # Agregar a mresumen si está vacío o crear campo específico
            if 'mresumen' not in result or not result.get('mresumen'):
                result['mresumen'] = highlighted_calculations
            else:
                # Agregar a mresumen existente
                result['mresumen'].extend(highlighted_calculations)
        
        return result if result else None
    
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
                                # Patrón 7: INVOICE No. XXXX (evitando "Invoice Numb")
                                invoice_match = None
                                for m in re.finditer(r'(?:^|\s)(INVOICE|FATTURA|CASH|CASD|FACTURA|BOLETA)\s+(?:No\.?|NO\.?|N°|#)\s*([A-Z0-9\-]+)', ocr_text, re.IGNORECASE):
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
        # Priorizar Grand Total explícito primero
        total_match = re.search(r'(?:Grand\s+Total|GRAND\s+TOTAL)\s*([\d,]+(?:[\.\s\-]?\d{2})?)', ocr_text, re.IGNORECASE)
        if total_match and ' ' in total_match.group(1):
            g = total_match.group(1).replace(',', '').strip()
            g = re.sub(r'\s', '.', g) if re.match(r'^\d+\s\d{2}$', g.replace(',', '')) else g
        # Priorizar "Invoice Amount" para Invoice Approval Reports
        if not total_match:
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
        """Extrae líneas con montos de GL Journal Details como items."""
        detalles: List[Dict] = []
        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
        in_table = False
        for line in lines:
            # detectar inicio de tabla por encabezados típicos
            if not in_table and ('GL Journal Details' in line or ('Line' in line and 'Entered' in line and 'Debits' in line)):
                in_table = True
                continue
            if not in_table:
                continue
            # Saltar separadores/footers
            if re.search(r'^(Page No\.|Run Date|USD\s+\d|TOTAL|^[-\s\.]{5,}$)', line, re.IGNORECASE):
                continue
            # Buscar monto en la columna Entered Debits con formato 4,301.00
            money = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
            if not money:
                continue
            # Heurística: último monto suele ser el de Debits si no hay Credits
            amount_str = money[-1].replace(',', '')
            try:
                amount = float(amount_str)
            except Exception:
                continue
            # Descripción: tomar texto al final de la línea después del último número grande, o última frase significativa
            desc = None
            m_desc = re.search(r'(JUL|AUG|SEP|OCT|NOV|DEC|BSQE|OH\s+RECOVERY|RECOVERY|Labor)[A-Z\s\-]*$', line, re.IGNORECASE)
            if m_desc:
                desc = m_desc.group(0).strip()
            if not desc:
                # fallback: quitar columnas numéricas y códigos
                desc = re.sub(r'\b[VA-Z0-9]{3,}\b', '', line)
                desc = re.sub(r'(\d{1,3}(?:,\d{3})*\.\d{2})', '', desc)
                desc = re.sub(r'\s{2,}', ' ', desc).strip()
            if amount > 0:
                detalles.append({
                    'nCantidad': 1.0,
                    'tDescripcion': desc or 'GL Journal Line',
                    'nPrecioUnitario': amount,
                    'nPrecioTotal': amount
                })
        return detalles
    
    def _extract_comprobante_detalle(self, ocr_text: str) -> List[Dict]:
        """Extrae items/detalles de un comprobante."""
        detalles = []
        lines = ocr_text.split('\n')
        
        in_items_section = False
        skip_invoice_group = False  # Flag para excluir "Invoice Group Detail"
        
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
                else:
                    continue  # Continuar saltando hasta encontrar otra sección
            
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
            if line.upper().startswith('QTY ') or ' ITEM NAME ' in line or line.upper().startswith('TOPUP'):
                continue
            
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
            for l in attach_lines:
                # Capturar montos al final de la línea (columna Total Amount)
                m_end = re.search(r'\$\s*([\d,]+\.\d{2})\s*$', l)
                if m_end:
                    amount = float(m_end.group(1).replace(',', ''))
                    # Evitar líneas de "TOTAL AMOUNT IN US$" (sumatoria) como detalle individual
                    if 'TOTAL AMOUNT' in l.upper():
                        continue
                    detalles.append({
                        'nCantidad': 1.0,
                        'tDescripcion': 'Attachment line',
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
        
        return calculations
    
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

