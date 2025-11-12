"""
Gemini Service Module - Integración con Gemini Vision API
Responsabilidad: Llamadas a la API de Gemini para OCR
"""

import os
import json
import base64
import time
from pathlib import Path
from typing import Dict, Optional, Any
import google.generativeai as genai
from PIL import Image


class GeminiService:
    """
    Servicio para interactuar con Gemini Vision API.
    
    Responsabilidades:
    - Configurar API Key
    - Enviar imágenes para OCR
    - Procesar respuestas de Gemini
    """
    
    def __init__(self, config_path: str = "config/gemini_config.json"):
        """Inicializa el servicio de Gemini."""
        self.config_path = config_path
        self.config = self._load_config()
        self.api_key = self.config.get("api_key")
        self.model_name = self.config.get("model", "gemini-2.5-flash")
        self.timeout = self.config.get("timeout", 300)
        self.max_retries = self.config.get("max_retries", 3)
        
        self._configure_api()
        self.model = self._load_model()
    
    def _load_config(self) -> Dict:
        """Carga la configuración de Gemini."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid config JSON: {e}")
    
    def _configure_api(self) -> None:
        """Configura la API Key de Gemini."""
        if not self.api_key:
            raise ValueError("Gemini API Key not configured")
        
        genai.configure(api_key=self.api_key)
    
    def _load_model(self) -> Any:
        """Carga el modelo de Gemini."""
        try:
            generation_config = {
                "temperature": self.config.get("temperature", 0.1),
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 32768,  # Máximo para obtener todo el texto
            }
            
            # Configuración de seguridad más permisiva
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            return genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
        except Exception as e:
            raise RuntimeError(f"Error loading Gemini model: {e}")
    
    def extract_text_from_image(self, image_path: str) -> Optional[Dict]:
        """
        Extrae texto de una imagen usando Gemini Vision.
        
        Args:
            image_path: Ruta a la imagen
            
        Returns:
            Diccionario con el texto extraído
        """
        if not os.path.exists(image_path):
            print(f"Image not found: {image_path}")
            return None
        
        try:
            img = Image.open(image_path)
            
            # Prompt para OCR
            prompt = self._create_ocr_prompt()
            
            # Generar contenido
            response = self.model.generate_content([prompt, img])
            
            # Verificar si hay respuesta válida
            if not response.text:
                # Verificar finish_reason
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    error_msg = f"Content filtered: {response.prompt_feedback.block_reason}"
                else:
                    error_msg = "Empty response from Gemini"
                
                print(f"Warning: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "timestamp": time.time()
                }
            
            # Limpiar el texto extraído
            cleaned_text = self._clean_extracted_text(response.text)
            
            return {
                "success": True,
                "text": cleaned_text,
                "model": self.model_name,
                "timestamp": time.time()
            }
        
        except Exception as e:
            error_msg = str(e)
            
            # Manejo específico para finish_reason
            if "finish_reason" in error_msg.lower() or "block_reason" in error_msg.lower():
                error_msg = "Content blocked by safety filters. Trying with alternative prompt..."
            
            print(f"Error in Gemini OCR: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "timestamp": time.time()
            }
    
    def _clean_extracted_text(self, text: str) -> str:
        """
        Limpia el texto extraído eliminando espacios excesivos.
        
        Args:
            text: Texto sin limpiar
            
        Returns:
            Texto limpio sin espacios excesivos
        """
        import re
        
        if not text:
            return text
        
        # Eliminar líneas que son solo espacios en blanco
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Si la línea tiene contenido real (no solo espacios)
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1].strip():
                # Permitir máximo 1 línea en blanco entre contenido
                continue
        
        text = '\n'.join(cleaned_lines)
        
        # Reemplazar múltiples espacios consecutivos (más de 5) con espacio simple
        # Pero preservar tabs y estructura mínima
        text = re.sub(r' {6,}', ' ', text)
        
        # Eliminar espacios en blanco al inicio y final
        text = text.strip()
        
        return text
    
    def _create_ocr_prompt(self) -> str:
        """
        Crea el prompt comprehensivo para extracción OCR completa.
        Si existe un prompt_manager conectado, usa el prompt actualizado.
        """
        # Intentar cargar prompt dinámico si existe prompt_manager
        try:
            if hasattr(self, '_prompt_manager') and self._prompt_manager:
                prompt = self._prompt_manager.get_current_prompt()
                if prompt and prompt.strip():
                    return prompt
        except Exception:
            # Si falla, continuar con prompt por defecto
            pass
        
        # Prompt por defecto (mejorado basado en análisis de errores)
        return """
⚠️ CRITICAL MISSION: Extract 100% of ALL visible text from this financial document. Read the ENTIRE document completely - leave NOTHING behind.

EXTRACTION REQUIREMENTS:
1. Read EVERY row of EVERY table completely - DO NOT skip any rows
2. Extract ALL text, numbers, symbols, codes from the ENTIRE document
3. Capture ALL information including headers, footers, stamps, watermarks
4. Read tables row by row - extract each row completely with all fields
5. Include ALL codes, serials, reference numbers, IDs visible anywhere
6. Extract ALL dates in any format (DD/MM/YYYY, MM-DD-YYYY, etc.)
7. Capture ALL currency symbols, amounts, totals visible in the document
8. Include partial or unclear text - extract what you can (use [?] only if truly illegible)
9. **PRIORITY: Extract highlighted/boxed/colored sections** - If you see text in colored boxes, highlighted areas, or visually emphasized sections (especially red boxes, yellow highlights, or bordered sections), extract them with special attention. These are often key calculations, summaries, or important validations.
10. **PRIORITY: Extract calculations and formulas** - If you see mathematical expressions with +, -, =, ×, ÷, extract them completely. Examples: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00"

SPECIFIC ITEMS TO EXTRACT WITH EXAMPLES:

CURRENCY (mdivisa): Look for currency codes near amounts or totals
- Examples: USD, PEN, EUR, RM, MYR, CLP, GBP, JPY, CNY, COP, MXN, ARS, BRL
- Location: Usually near "Total", "Amount", "总计", "JUMLAH", "金额", or after $, ¥ symbols
- Patterns: "Total USD 1,234.56", "Amount: 100.00 PEN", "$ 50.00" = USD
- Chinese currency: "总计:1060元" = CNY, "¥ 100.00" = CNY, "金额: 50元" = CNY
- Symbol mapping: $ = USD, ¥ = CNY (Chinese yuan), 元 = CNY

DOCUMENT NUMBERS (tNumero): Extract invoice/boleta/receipt numbers
- Examples: "N° 0000155103", "Invoice No. 1234", "Folio: 5678", "NO. 2972", "发票号码:25379166812000866769"
- Location: Usually in header, after "BOLETA ELECTRÓNICA", "INVOICE", "FACTURA", "发票号码"
- Patterns: "BOLETA ELECTRÓNICA N° 0000155103", "Invoice Number: 1234", "Folio No. 5678"
- Chinese patterns: "发票号码:25379166812000866769", "发票代码:113002334010", "号码 40458905"
- Key words: "N°", "No.", "NO.", "Number", "Folio", "Invoice", "Factura", "Boleta", "发票号码", "发票代码", "号码"

SEQUENTIAL NUMBERS (tSequentialNumber): Extract codes like BSQE1234, OE0001, OR0001
- Examples: "BSQE1234", "OE0001", "OR0001", "ORU1234"
- Location: Usually near stamp names (BSQE, OTEM, OTRE, OTRU) - may be on same or next line
- Patterns: "OTEM\nOE0001", "BSQE 1234", "ORRE OR0001"
- Key words: Look for "BSQE", "OTEM", "OTRE", "OTRU" followed by numbers

STAMP NAMES: Extract stamp identifiers
- Examples: BSQE, OTEM, OTRE, OTRU
- Location: Usually in header or near document title
- Note: These may be on separate lines from sequential numbers

HEADER INFORMATION: Company names, logos, addresses, contact info
- Extract complete company names with legal suffixes (SDN BHD, LLC, Inc, S.A., S.L., SRL)

DATES: Extract all dates in any format
- Formats: DD/MM/YYYY, MM-DD-YYYY, DD-MM-YY, "10-06-2025", "May 28, 2025"
- Location: Usually near "Date:", "Fecha:", "Tarikh:", or in header/footer

VENDOR/SUPPLIER: Name, address, tax ID
- Look for "Supplier Name:", "Vendor:", "Proveedor:", or company names in header

CLIENT/CUSTOMER: Name, address, contact
- Look for "Attn.:", "Client:", "Cliente:", or customer information sections

TABLE DATA: Item descriptions, quantities, prices, totals
- Extract EVERY row completely
- Include item names, quantities, unit prices, line totals
- Preserve table structure

TOTALS: Subtotal, tax amounts, discounts, grand total
- Look for "Total", "TOTAL", "Subtotal", "Tax", "Discount", "总计", "JUMLAH"
- Include currency if present: "Total USD 1,234.56"

PAYMENT TERMS: Conditions, notes, payment information
- Extract payment terms, due dates, payment methods

AUTHENTICATION: QR codes text, barcodes, authentication codes
- Extract any codes, serials, or authentication information

PERIOD INFORMATION: From date, to date
- Look for "Period:", "From:", "To:", date ranges

JOB NUMBERS: Source references, classifications
- Look for "Job No:", "Source Ref:", reference codes

EMPLOYEE INFORMATION: Names, IDs, organizations (for time sheets)
- Look for "Employee ID:", "Emp No:", employee names, organization codes

HOURS WORKED: Rates, totals (for time sheets)
- Extract hours, rates, totals for labor documents

HIGHLIGHTED/BOXED SECTIONS (HIGH PRIORITY):
- Extract ALL text from colored boxes, highlighted areas, or visually emphasized sections
- These often contain: calculations, validations, summaries, totals, or key information
- Examples: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00" in a red box
- If you see a calculation with currency symbols and operators (+, -, =), extract it completely
- Mark these sections clearly in your output if possible (or just extract the text)

GL JOURNAL SPECIFIC FIELDS:
- Source Ref: Extract as document number (tNumero) - usually format like "2336732507B0032"
- Batch Name: May contain document identifiers
- Journal Name: May contain batch IDs or reference numbers
- Look for "Source Ref:", "Batch Name:", "Journal Name:" patterns

IGNORE TEXT:
- Do NOT ignore relevant text, but be aware that "OTEM", "OE0001", "OR0001" etc. are part of the document structure
- These codes (stamp names and sequential numbers) are IMPORTANT and should be extracted

FORMAT REQUIREMENTS:
- Maintain paragraph structure and spacing
- Preserve table alignment using spaces or tabs
- Keep line breaks as they appear in the original
- Do NOT summarize or paraphrase
- Do NOT skip any text, even if it seems redundant
- If text is partially visible, include what you can see
- Use placeholders like [unclear] only if absolutely illegible

OUTPUT INSTRUCTIONS:
- Return ONLY visible text content, NOT spaces or formatting
- Do NOT include excessive whitespace or blank lines
- Condense multiple spaces to single space when preserving structure isn't critical
- For tables: preserve column separation with reasonable spacing (max 3-5 spaces)
- Skip completely blank lines or lines with only formatting elements
- Return clean, readable text without unnecessary whitespace padding

CRITICAL: Your goal is to extract EVERYTHING. Read EVERY table row, EVERY field, EVERY piece of information.
Pay special attention to:
- Currency codes near totals or amounts
- Document numbers after "N°", "No.", "Invoice", "Boleta", "Folio"
- Sequential numbers near stamp names (BSQE, OTEM, OTRE, OTRU)
- All monetary values with their associated currencies

Do not skip content. Scan thoroughly. Extract completely. Nothing should be left unread.
        """
    
    def process_image_with_retry(self, image_path: str, 
                                 retries: int = None) -> Optional[Dict]:
        """
        Procesa una imagen con reintentos automáticos.
        
        Args:
            image_path: Ruta a la imagen
            retries: Número de reintentos (None usa config)
            
        Returns:
            Resultado del OCR o None
        """
        max_retries = retries or self.max_retries
        
        for attempt in range(max_retries):
            result = self.extract_text_from_image(image_path)
            
            if result and result.get("success"):
                return result
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
        
        return None

    def translate_text(self, text: str, source_language: str = None) -> Optional[str]:
        """
        Traduce texto a inglés usando Gemini.
        
        Args:
            text: Texto a traducir
            source_language: Idioma origen ('it', 'other', etc.) - None para auto-detectar
            
        Returns:
            Texto traducido a inglés o None si hay error
        """
        if not text or not text.strip():
            return text
        
        try:
            # Prompt para traducción
            if source_language:
                prompt = f"Translate the following text from {source_language} to English. Maintain all formatting, numbers, dates, and technical terms exactly as they appear. Only translate the natural language parts.\n\nText to translate:\n{text}"
            else:
                prompt = f"Translate the following text to English. Detect the source language automatically. Maintain all formatting, numbers, dates, and technical terms exactly as they appear. Only translate the natural language parts.\n\nText to translate:\n{text}"
            
            response = self.model.generate_content(prompt)
            
            if response and response.text:
                return response.text.strip()
            
            return text  # Si falla, devolver original
            
        except Exception as e:
            print(f"Error en traducción: {e}")
            return text  # En caso de error, devolver original

    def infer_anchor_tables(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Pide a Gemini que infiera valores para tablas ancla a partir del texto OCR.

        Retorna un diccionario con claves opcionales: midioma, mdivisa, mproveedor,
        mnaturaleza, mdocumento_tipo, munidad_medida, marchivo_tipo.
        """
        if not text or not text.strip():
            return None
        try:
            prompt = (
                "You are classifying anchor metadata for an accounting document. "
                "Given the following extracted text, infer ONLY the requested fields and "
                "return STRICT JSON with these keys if you can infer them: "
                "midioma.tIdioma (language name), mdivisa (array of currency codes like USD, RM, PEN, EUR), "
                "mproveedor.tRazonSocial (supplier/company name if any), "
                "mnaturaleza (array of categories from this controlled set: ['Alimentación','Hospedaje','Transporte','Combustible','Materiales','Servicios','Otros']), "
                "mdocumento_tipo.tTipo (one of: Comprobante, Resumen, Jornada). "
                "Rules: detect multi-language; keep numbers/dates unchanged; do not invent. "
                "If unsure, omit the field. Respond ONLY with JSON.\n\nText:\n" + text
            )

            response = self.model.generate_content(prompt)
            if response and response.text:
                raw = response.text.strip()
                # Intentar parsear JSON directo
                try:
                    data = json.loads(raw)
                except Exception:
                    # A veces Gemini envuelve en bloques; intentar limpiar backticks
                    cleaned = raw.strip().strip('`')
                    data = json.loads(cleaned)
                return data
        except Exception as e:
            print(f"Error infiriendo tablas ancla: {e}")
        return None

    def infer_line_items(self, text: str) -> Optional[Any]:
        """
        Pide a Gemini que extraiga ítems (cantidad, descripción, precio unitario/total) en JSON.
        Estructura solicitada: [{"nCantidad": float, "tDescripcion": str, "nPrecioUnitario": float, "nPrecioTotal": float}]
        """
        if not text or not text.strip():
            return None
        try:
            prompt = (
                "Extract line items from the following receipt/invoice text. "
                "Return STRICT JSON array with objects having exactly these keys: "
                "nCantidad (number), tDescripcion (string), nPrecioUnitario (number), nPrecioTotal (number). "
                "Use decimals with dot. Infer unit price vs total if columns show Qty, U Price, S.Total; "
                "otherwise assume total equals unit price when Qty=1. Do not include totals/discounts/taxes rows. "
                "Respond ONLY with JSON.\n\nText:\n" + text
            )
            response = self.model.generate_content(prompt)
            if response and response.text:
                raw = response.text.strip().strip('`')
                try:
                    return json.loads(raw)
                except Exception:
                    # Extraer el primer arreglo JSON válido
                    start = raw.find('[')
                    end = raw.rfind(']')
                    if start != -1 and end != -1 and end > start:
                        snippet = raw[start:end+1]
                        return json.loads(snippet)
        except Exception as e:
            print(f"Error infiriendo line items: {e}")
        return None
