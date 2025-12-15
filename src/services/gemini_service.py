"""
Gemini Service Module - Integración con Gemini Vision API
Responsabilidad: Llamadas a la API de Gemini para OCR
"""

import os
import json
import base64
import re
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
        
        # Cache para el prompt (evitar recalcularlo cada vez)
        # NOTA: El cache se invalida si cambian las conversiones de moneda
        self._prompt_cache = None
        self._currency_conversions_hash = None
        
        # Cargar conversiones de moneda
        self.currency_conversions = self._load_currency_conversions()
        
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
    
    def _load_currency_conversions(self) -> Dict[str, float]:
        """Carga las tasas de conversión de monedas desde archivo de configuración."""
        try:
            # Buscar el archivo en la misma carpeta que gemini_config.json
            config_dir = Path(self.config_path).parent
            currency_config_path = config_dir / "currency_conversions.json"
            
            if not currency_config_path.exists():
                # Fallback a valores por defecto si no existe el archivo
                print(f"Warning: currency_conversions.json not found at {currency_config_path}. Using default rates.")
                return {
                    "MYR": 0.21,
                    "CLP": 0.001,
                    "MXN": 0.05,
                    "PEN": 0.27
                }
            
            with open(currency_config_path, 'r', encoding='utf-8') as f:
                currency_data = json.load(f)
                return currency_data.get("currency_conversions", {})
        except Exception as e:
            print(f"Warning: Error loading currency conversions: {e}. Using default rates.")
            return {
                "MYR": 0.21,
                "CLP": 0.001,
                "MXN": 0.05,
                "PEN": 0.27
            }
    
    def _generate_currency_conversion_section(self) -> str:
        """
        Genera la sección de conversiones de moneda para el prompt dinámicamente.
        
        Returns:
            String con la sección de conversiones formateada para el prompt
        """
        if not self.currency_conversions:
            return ""
        
        lines = ["**CURRENCY CONVERSION RULES (DYNAMIC):**"]
        lines.append("- **CRITICAL**: nPrecioTotal MUST always be in USD")
        lines.append("- If document contains values in a currency other than USD and NO USD values are found, convert to USD using the rates below:")
        lines.append("")
        
        # Generar tabla de conversiones
        for currency, rate in sorted(self.currency_conversions.items()):
            lines.append(f"- {currency} → USD: 1 {currency} = {rate} USD")
        
        lines.append("")
        lines.append("**CONVERSION PROCESS:**")
        lines.append("1. Detect the original currency from the document (CLP, MXN, MYR, PEN, etc.)")
        lines.append("2. If document has ONLY non-USD currency (no USD found): Convert using the rate above")
        lines.append("3. If document has BOTH non-USD and USD: Use USD values (do NOT convert)")
        lines.append("4. If document has ONLY USD: Use USD values as-is")
        lines.append("5. Store original value in nPrecioTotalOriginal field and currency code in tMonedaOriginal field")
        lines.append("")
        lines.append("**EXAMPLES:**")
        
        # Generar ejemplos dinámicos
        example_currencies = list(self.currency_conversions.keys())[:3]  # Primeras 3 para ejemplos
        for currency in example_currencies:
            rate = self.currency_conversions[currency]
            example_value = 1000
            converted = example_value * rate
            lines.append(f"- If total is \"{currency} {example_value:.2f}\" and no USD found → nPrecioTotal: \"{converted:.2f}\" (USD), nPrecioTotalOriginal: \"{example_value:.2f}\", tMonedaOriginal: \"{currency}\"")
        
        lines.append("- If total is already in USD → nPrecioTotal: \"[value]\", nPrecioTotalOriginal: null, tMonedaOriginal: null")
        lines.append("")
        
        return "\n".join(lines)
    
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
                "max_output_tokens": self.config.get("max_output_tokens", 65536),  # Configurable, default: 65536 (máximo de Gemini 2.5)
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
            
            # Verificar que la imagen sea válida
            if img.size[0] == 0 or img.size[1] == 0:
                print(f"Error: Imagen inválida (tamaño: {img.size})")
                return {
                    "success": False,
                    "error": "Invalid image dimensions",
                    "text": "",
                    "timestamp": time.time()
                }
            
            # Prompt para OCR
            prompt = self._create_ocr_prompt()
            
            # Generar contenido con manejo de errores mejorado
            try:
                response = self.model.generate_content([prompt, img])
            except Exception as api_error:
                error_msg = str(api_error)
                error_str_lower = error_msg.lower()
                
                # Detectar error 429 (quota exceeded) - ser más específico para evitar falsos positivos
                # Buscar primero "429" explícitamente, luego verificar contexto de quota
                is_429_error = "429" in error_msg or (
                    ("quota" in error_str_lower or "exceeded" in error_str_lower) and 
                    ("rate" in error_str_lower or "limit" in error_str_lower or "per minute" in error_str_lower or "per day" in error_str_lower)
                )
                
                if is_429_error:
                    # Intentar extraer el tiempo de retry sugerido
                    retry_delay = 20  # Default: 20 segundos
                    if "retry" in error_str_lower:
                        # Buscar "retry in Xs" o "retry_delay"
                        import re
                        retry_match = re.search(r'retry.*?(\d+(?:\.\d+)?)\s*s', error_str_lower)
                        if retry_match:
                            retry_delay = int(float(retry_match.group(1))) + 1  # Agregar 1 segundo de margen
                        else:
                            # Buscar en formato "seconds: X"
                            seconds_match = re.search(r'seconds?[:\s]+(\d+)', error_str_lower)
                            if seconds_match:
                                retry_delay = int(seconds_match.group(1)) + 1
                    
                    print(f"Error 429 - Quota exceeded. Retry delay: {retry_delay}s")
                    print(f"Error details: {error_msg[:500]}")  # Limitar longitud del mensaje
                    
                    return {
                        "success": False,
                        "error": f"429 Quota exceeded. Please retry in {retry_delay}s. Check your Gemini API quota limits.",
                        "text": "",
                        "timestamp": time.time(),
                        "retry_after": retry_delay,  # Información para el sistema de reintentos
                        "error_type": "quota_exceeded"
                    }
                
                # Verificar si es un error de timeout o conexión
                if "timeout" in error_str_lower or "connection" in error_str_lower:
                    return {
                        "success": False,
                        "error": f"API timeout/connection error: {error_msg}",
                        "text": "",
                        "timestamp": time.time()
                    }
                raise  # Re-lanzar otros errores
            
            # Verificar si hay respuesta válida
            if not response.text:
                # Verificar finish_reason para obtener más información
                error_msg = "Empty response from Gemini"
                finish_reason = None
                
                # Intentar obtener más información del error
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    error_msg = f"Content filtered: {response.prompt_feedback.block_reason}"
                elif hasattr(response, 'candidates') and response.candidates:
                    # Verificar finish_reason en candidates
                    for candidate in response.candidates:
                        if hasattr(candidate, 'finish_reason'):
                            finish_reason = candidate.finish_reason
                            if finish_reason == 'SAFETY':
                                error_msg = "Content blocked by safety filters"
                            elif finish_reason == 'RECITATION':
                                error_msg = "Content blocked due to recitation"
                            elif finish_reason == 'OTHER':
                                error_msg = f"Content blocked: {finish_reason}"
                            break
                
                print(f"Warning: {error_msg} (finish_reason: {finish_reason})")
                # IMPORTANTE: Aunque falle, intentar extraer texto parcial si existe
                # A veces Gemini puede tener texto en otras partes de la respuesta
                partial_text = ""
                if hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    partial_text += part.text + "\n"
                
                # Si hay texto parcial, usarlo; si no, retornar error pero con texto vacío
                if partial_text:
                    cleaned_partial = self._clean_extracted_text(partial_text)
                    print(f"Info: Se encontró texto parcial ({len(cleaned_partial)} caracteres)")
                    return {
                        "success": True,  # Marcar como éxito si hay texto parcial
                        "text": cleaned_partial,
                        "model": self.model_name,
                        "timestamp": time.time(),
                        "warning": error_msg  # Pero incluir advertencia
                    }
                
                return {
                    "success": False,
                    "error": error_msg,
                    "text": "",  # Asegurar que siempre haya campo text
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
9. **PRIORITY: Extract highlighted/boxed/colored sections** - If you see text in colored boxes, highlighted areas, or visually emphasized sections (especially red boxes, yellow highlights, or bordered sections), extract them with special attention. These are often key calculations, summaries, or important validations. When you see red rectangular boxes or highlighted areas, extract ALL text and numbers within those boxes completely.
10. **PRIORITY: Extract calculations and formulas** - If you see mathematical expressions with +, -, =, ×, ÷, extract them completely. Examples: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00". Pay special attention to calculations that appear in colored boxes or highlighted areas - these are critical.
11. **PRIORITY: GL Journal Details with highlighted values** - If this is a "GL Journal Details" document and you see red boxes highlighting specific "Entered Debits" values in a table, extract those highlighted values AND any calculation that sums them (e.g., "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00"). These highlighted values are the ONLY ones needed from this document type.
12. **HIGHEST PRIORITY: Handwritten text with USD** - If you see ANY text written by hand (handwritten, manually written) that contains "USD" followed by a monetary value, extract it with HIGHEST PRIORITY. Handwritten values are often corrections, validations, or final amounts that override printed values. Examples: "USD 1,234.56" written by hand, "USD 500.00" in handwriting. 
   - **CRITICAL**: When you detect handwritten text with "USD", include a marker like "[HANDWRITTEN]" or "[MANUAL]" before or after the value in your extraction, so it can be identified and prioritized. Example: "[HANDWRITTEN] USD 1,234.56" or "USD 1,234.56 [MANUAL]"
   - If you see a value that appears to be written by hand (different style, appears to be an annotation or correction), mark it as handwritten even if you're not 100% certain
   - Handwritten USD values take precedence over ANY printed values in the document

SPECIFIC ITEMS TO EXTRACT WITH EXAMPLES:

CURRENCY (mdivisa): Look for currency codes near amounts or totals
- Examples: USD, PEN, EUR, RM, MYR, CLP, GBP, JPY, CNY, COP, MXN, ARS, BRL
- Location: Usually near "Total", "Amount", "总计", "JUMLAH", "金额", or after $, ¥ symbols
- Patterns: "Total USD 1,234.56", "Amount: 100.00 PEN", "$ 50.00" = USD
- Chinese currency: "总计:1060元" = CNY, "¥ 100.00" = CNY, "金额: 50元" = CNY
- Symbol mapping: $ = USD, ¥ = CNY (Chinese yuan), 元 = CNY

DOCUMENT NUMBERS (tNumero): Extract invoice/boleta/receipt numbers
- Examples: "N° 0000155103", "Invoice No. 1234", "Folio: 5678", "NO. 2972", "发票号码:25379166812000866769", "Recibo 221"
- Location: Usually in header, after "BOLETA ELECTRÓNICA", "INVOICE", "FACTURA", "发票号码", "Recibo"
- Patterns: "BOLETA ELECTRÓNICA N° 0000155103", "Invoice Number: 1234", "Folio No. 5678", "Recibo 221"
- Spanish receipts: "Recibo" followed by number (e.g., "Recibo 221")
- Chinese patterns: "发票号码:25379166812000866769", "发票代码:113002334010", "号码 40458905"
- Key words: "N°", "No.", "NO.", "Number", "Folio", "Invoice", "Factura", "Boleta", "Recibo", "发票号码", "发票代码", "号码"

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
- **CRITICAL: Extract ALL totals from documents**:
  - **Report Total**: Extract "Report Total:" followed by amount (e.g., "Report Total: 180,000.00")
  - **Subtotal**: Extract "Subtotal:" followed by amount
  - **Total for XXX**: Extract "Total for [code]:" followed by amount (e.g., "Total for 611: 180,000.00")
  - **Amount Less Tax**: Extract "Amount Less Tax:" followed by amount
  - **Tax**: Extract "Tax:" followed by amount (even if 0)
  - **Grand Total**: Extract "Grand Total:" followed by amount
  - **Any other totals**: Extract ANY line that contains "Total" followed by a monetary value
- **IMPORTANT**: All totals must be extracted and saved, regardless of document type (Concur, Bechtel, Oracle, invoices, etc.)

WEEKLY TOTALS (OnShore): Extract totals by week (WEEK 27, WEEK 28, etc.)
- Look for lines with multiple large monetary values at the end of tables
- These are usually weekly totals: "7,816,974.79 305,349.84 6,333,781.02"
- **CRITICAL**: If you see a line with ONLY numbers (no item descriptions) containing 2+ large values, it's likely weekly totals
- Extract these values even if they appear after item rows
- Example: After "Rimac Seguros 655,740.75 18,231.00" you might see "7,816,974.79 305,349.84 6,333,781.02" - these are WEEKLY TOTALS, not items

CASH FLOW VALUES (OnShore): Extract Cash Flow table values
- **Total Disbursement**: Look for "Total Disbursement" followed by monetary values
- **Period Balance**: Look for "Period Balance" followed by values (may be in parentheses for negatives)
- **Cumulative Cash Flow**: Look for "Cumulative Cash Flow" followed by running totals
- **Opening Balance**: Look for "Opening Balance" values
- **Total Receipts**: Look for "Total Receipts" values
- Extract ALL values from Cash Flow tables, including negative values in parentheses
- Example: "Period Balance (305,350) (6,333,781) (7,080,000)" - extract all values

DEPARTMENTS (OnShore Documents) - CRITICAL FOR ANALYTICS:
- **Department Names**: Look for department labels in tables, headers, or classification sections
- Common department names to extract:
  * "Engineering" or "Engineering Department"
  * "Operations" or "Operations Department"
  * "Maintenance" or "Maintenance Department"
  * "Safety" or "Safety Department" or "Health & Safety"
  * "Environmental" or "Environmental Department"
  * "Human Resources" or "HR" or "HR Department"
  * "Finance" or "Finance Department" or "Financial"
  * "IT Services" or "IT" or "Information Technology"
  * "Other Services" or "Other" or "Miscellaneous"
- **Location**: Departments may appear in:
  * Table headers (e.g., "Department", "Dept", "Department Name")
  * Classification columns in expense reports
  * Summary sections with department breakdowns
  * Organization charts or org codes
- **Patterns**: Look for patterns like:
  * "Department: Engineering"
  * "Dept: Operations"
  * "Engineering Department - $450,000.00"
  * Table columns with department names
  * Org codes that map to departments (e.g., "HXH0009" might indicate a department)
- **CRITICAL**: Extract department names even if they appear abbreviated or in different formats
- If you see department-related information, extract it completely

DISCIPLINES (OnShore Documents) - CRITICAL FOR ANALYTICS:
- **Discipline Names**: Look for discipline labels in tables, classifications, or job sections
- Common discipline names to extract:
  * "Engineering" (may appear as discipline AND department)
  * "Operations"
  * "Maintenance"
  * "Safety"
  * "Environmental"
  * "Project Management"
  * "Quality Control" or "QC"
  * "Procurement"
  * "Construction"
  * "Logistics"
- **Location**: Disciplines may appear in:
  * Job section classifications (e.g., "Line Item by Job Section")
  * NC Codes or cost codes that map to disciplines
  * Table columns labeled "Discipline", "Type", "Category"
  * Expense type classifications
  * Labor classifications in time sheets
- **Patterns**: Look for patterns like:
  * "Discipline: Engineering"
  * "Type: Operations"
  * "Category: Maintenance"
  * Job codes that indicate disciplines (e.g., "611" might map to a discipline)
  * NC Codes in expense reports (e.g., "NC Code: 611" might indicate Engineering discipline)
- **CRITICAL**: Extract discipline names even if they appear in codes or abbreviated formats
- If you see discipline-related information, extract it completely
- Note: Disciplines are often more granular than departments (e.g., "Engineering" department might have "Civil Engineering", "Mechanical Engineering" disciplines)

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

CONCUR EXPENSE REPORT - SPECIFIC FIELDS:
- **Report Name**: Look for "Concur Expense - [Name]" (e.g., "Concur Expense - Transportes Terrestres")
- **Job Section**: Look for "Line Item by Job Section" followed by code (e.g., "Line Item by Job Section 26443-331-----")
- **Transaction Date**: Extract transaction dates (e.g., "Jun 23, 2025", "2025-06-23")
- **Expense Type**: Look for expense types (e.g., "Leave (Any) Taxi/Ground Trans - LT")
- **Merchant**: Look for "Merchant:" followed by merchant name (e.g., "Merchant: RV Transportes Ltda.")
- **Location**: Extract location names (e.g., "Quilpué", "Santiago")
- **NC Code**: Extract numerical codes (e.g., "611")
- **Amount**: Extract transaction amounts (e.g., "90,000.00")
- **Payment Currency**: Extract currency codes (e.g., "CLP", "USD")
- **Report Total**: Look for "Report Total:" followed by amount (e.g., "Report Total: 180,000.00")
  - **CRITICAL**: This is the most important total - extract it completely
- **Subtotal**: Look for "Subtotal:" followed by amount
- **Total for XXX**: Look for "Total for [code]:" followed by amount (e.g., "Total for 611: 180,000.00")
- **Amount Less Tax**: Look for "Amount Less Tax:" followed by amount
- **Tax**: Look for "Tax:" followed by amount (even if 0)
- **CRITICAL**: Extract ALL totals from Concur Expense Reports - they are essential for financial tracking

BECHTEL EXPENSE REPORT (OnShore) - SPECIFIC FIELDS:
- **Report Key**: Look for "Report Key:" followed by numbers (e.g., "Report Key : 1312161")
- **Report Number**: Look for "Report Number:" followed by alphanumeric code (e.g., "Report Number: 0ON74Y")
- **Employee ID**: Look for "Employee ID :" followed by numbers (e.g., "Employee ID : 063573")
- **Employee Name**: Look for "Employee Name :" followed by full name (e.g., "Employee Name : AYALA SEHLKE, ANA MARIA")
- **Org Code**: Look for "Org Code :" followed by code (e.g., "Org Code : HXH0009")
- **Default Approver**: Look for "Default Approver:" followed by name (e.g., "Default Approver: QUISPE VERASTEGUI, CARLOS ALEJANDRO")
- **Final Approver**: Look for "Final Approver:" followed by name (e.g., "Final Approver: SHOME, AYON")
- **Report Name**: Look for "Report Name:" followed by description (e.g., "Report Name: Transportes Terrestres")
- **Report Date**: Look for "Report Date :" followed by date (e.g., "Report Date : Jul 23, 2025")
- **Report Purpose**: Look for "Report Purpose:" followed by description (e.g., "Report Purpose: Viaje a turno")
- **Report Total**: Look for "Report Total:" followed by amount (e.g., "Report Total: 180,000.00")
  - **CRITICAL**: If "Report Total" appears in a RED BOX or HIGHLIGHTED area, extract the value from that box even if it's not on the same line as "Report Total:"
  - **CRITICAL**: Values in red boxes or highlighted areas near "Report Total" are PRIORITY - extract them completely
  - Look for monetary values (with or without commas) near "Report Total" text, especially in colored/highlighted sections
- **Bechtel owes Card**: Look for "Bechtel owes Card:" followed by amount (may be blank)
- **Bechtel owes Employee**: Look for "Bechtel owes Employee :" followed by amount (e.g., "Bechtel owes Employee : 180,000.00")
  - **CRITICAL**: If these values appear in RED BOXES or HIGHLIGHTED areas, extract them with priority
- **Policy**: Look for "Policy:" followed by policy type (e.g., "Policy: Assignment Long Term")
- **Document Identifier**: Look for format "BECHEXPRPT_{EmployeeID}_{ReportNumber}" in header (e.g., "BECHEXPRPT_063573_0ON74Y")
- **Sequential Codes**: Look for codes like "OTHBP", "OE0003", "OR0001" - these are stamp names and sequential numbers
- **Variants**: Document may also appear as "Expense Report", "Bechtel Expense", or similar variations
- **HIGHLIGHTED VALUES PRIORITY**: For Expense Reports, values in RED BOXES or HIGHLIGHTED areas are especially important:
  - Report Total values in red boxes must be extracted completely
  - Employee information in red boxes (Employee ID, Employee Name) must be captured
  - Any monetary values in colored/highlighted sections near "Report Total" or "Bechtel owes" fields are critical

HIGHLIGHTED/BOXED SECTIONS (HIGH PRIORITY):
- Extract ALL text from colored boxes, highlighted areas, or visually emphasized sections
- These often contain: calculations, validations, summaries, totals, or key information
- Examples: "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00" in a red box
- If you see a calculation with currency symbols and operators (+, -, =), extract it completely
- Mark these sections clearly in your output if possible (or just extract the text)
- **ITALIAN INVOICES (FATTURA)**: Pay special attention to red boxes or highlighted areas containing:
  - Invoice numbers (e.g., "FATTURA NO.: 333/25" in a red box)
  - Total amounts (e.g., "TOTAL $ 122.94" in a red box)
  - Any monetary values in colored/highlighted sections
  - Extract these values with their complete format, including slashes in invoice numbers and decimal points in amounts
- **ATTACHMENT TO INVOICE DOCUMENTS**: Pay special attention to red boxes or highlighted areas containing:
  - **"TOTAL AMOUNT IN US$"** values in red boxes at the bottom of tables (e.g., "TOTAL AMOUNT IN US$ 22 180 $ - $ - $ 120.60 $ 120.60" - extract the final "$ 120.60")
  - **"TOTAL $ XXX.XX"** values in red boxes in summary sections (e.g., "TOTAL $ 122.94")
  - Table row values with "Total Amount" column (e.g., "Martin Loges ... $ 60.30 $ 60.30")
  - Extract ALL table rows completely, including Resource, Vendor, Assignment no., Report Number, Date, hrs, rates, and amounts
  - **CRITICAL**: Values in red boxes are PRIORITY - extract them completely with all decimal places

GL JOURNAL SPECIFIC FIELDS:
- Source Ref: Extract as document number (tNumero) - usually format like "2336732507B0032"
- Batch Name: May contain document identifiers
- Journal Name: May contain batch IDs or reference numbers
- Look for "Source Ref:", "Batch Name:", "Journal Name:" patterns

ORACLE AP (Accounts Payable) - SPECIFIC FIELDS:
- **Invoice Num**: Look for "Invoice Num:" followed by alphanumeric code (e.g., "Invoice Num F581-06891423")
- **Invoice Amount**: Look for "Invoice Invoice Amount" or "Invoice Amount" followed by currency and amount (e.g., "Invoice Invoice Amount USD 655740.75")
- **Tax Amount**: Look for "Tax Amount:" followed by amount (e.g., "Tax Amount 100028.25")
- **Due Date**: Look for "Due Date:" followed by date (e.g., "Due Date 30-JUN-2025")
- **Gross Amount**: Look for "Gross Amount:" or "Payment Gross Amount:" followed by amount (e.g., "Gross Amount 655740.75")
- **Payment Currency**: Look for "Payment Currency:" followed by currency code (e.g., "Payment Currency USD")
- **Payment Method**: Look for "Method:" followed by payment type (e.g., "Method Wire")
- **Supplier Num**: Look for "Supplier Num:" followed by number (e.g., "Supplier Num 934001256")
- **Operating Unit**: Look for "Operating Unit:" followed by unit name (e.g., "Operating Unit PEN - BECHTEL PE")
- **Supplier Name**: Look for "PO Trading Pa:" or "Supplier Name:" followed by supplier name (e.g., "PO Trading Pa RIMAC SE")
- **Supplier Site**: Look for "Supplier Site:" followed by site code (e.g., "Supplier Site XYQN-WIRE")
- **Invoice Date**: Look for "Invoice Date:" followed by date (e.g., "Invoice Date 20-JUN-2025")
- **CRITICAL**: Extract ALL table data from Oracle AP screens, especially from "Scheduled Payments" tab
- **CRITICAL**: Extract values from payment tables even if they appear in separate columns

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
            Resultado del OCR (nunca None, siempre retorna dict con al menos error)
        """
        max_retries = retries or self.max_retries
        
        last_error = None
        for attempt in range(max_retries):
            result = self.extract_text_from_image(image_path)
            
            # Si hay éxito (incluso con texto parcial), retornar
            if result and result.get("success"):
                return result
            
            # Guardar el último error para retornarlo si todos los intentos fallan
            if result:
                last_error = result.get("error", "Unknown error")
            else:
                last_error = "OCR returned None"
            
            # CRITICAL: NO reintentar si es error 429 (quota exceeded)
            # Cada reintento consume tokens de entrada aunque falle, multiplicando el consumo innecesariamente
            if result and result.get("error_type") == "quota_exceeded":
                # Si es error de cuota, NO reintentar - retornar inmediatamente
                print(f"Quota exceeded. Stopping retries to avoid consuming more tokens.")
                print(f"Note: You've exceeded your Gemini API quota. Check: https://ai.google.dev/gemini-api/docs/rate-limits")
                break  # Salir del loop de reintentos inmediatamente
            
            # Para otros errores, reintentar normalmente
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
        
        # IMPORTANTE: Nunca retornar None, siempre retornar un dict con error
        # Esto asegura que el procesamiento continúe y se genere JSON (aunque vacío)
        print(f"Error: Todos los reintentos fallaron. Último error: {last_error}")
        return {
            "success": False,
            "error": last_error or "All retry attempts failed",
            "text": "",  # Asegurar que siempre haya campo text
            "model": self.model_name,
            "timestamp": time.time()
        }

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
                "mdocumento_tipo.tTipo (one of: Ticket, Factura Electrónica, Comprobante, Nota-Bill, Resumen, Jornada). "
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
    
    def extract_structured_data_from_image(self, image_path: str) -> Optional[Dict]:
        """
        Extrae texto OCR y datos estructurados directamente de una imagen en una sola llamada.
        Combina OCR completo + identificación de tipo + extracción estructurada.
        
        Args:
            image_path: Ruta a la imagen
            
        Returns:
            Diccionario con:
            - success: bool
            - text: str (texto OCR completo)
            - structured_data: dict (datos estructurados según tipo de documento)
            - document_type: str (tipo identificado)
            - model: str
            - timestamp: float
            - error: str (si hay error)
        """
        if not os.path.exists(image_path):
            print(f"Image not found: {image_path}")
            return {
                "success": False,
                "error": "Image not found",
                "text": "",
                "structured_data": {},
                "document_type": "unknown",
                "timestamp": time.time()
            }
        
        try:
            img = Image.open(image_path)
            
            # Verificar que la imagen sea válida
            if img.size[0] == 0 or img.size[1] == 0:
                print(f"Error: Imagen inválida (tamaño: {img.size})")
                return {
                    "success": False,
                    "error": "Invalid image dimensions",
                    "text": "",
                    "structured_data": {},
                    "document_type": "unknown",
                    "timestamp": time.time()
                }
            
            # Prompt comprehensivo que combina OCR + estructuración
            prompt = self._create_ocr_and_structure_prompt()
            
            # Generar contenido con manejo de errores mejorado
            try:
                response = self.model.generate_content([prompt, img])
            except Exception as api_error:
                error_msg = str(api_error)
                error_str_lower = error_msg.lower()
                
                # Detectar error 429 (quota exceeded) - ser más específico para evitar falsos positivos
                is_429_error = "429" in error_msg or (
                    ("quota" in error_str_lower or "exceeded" in error_str_lower) and 
                    ("rate" in error_str_lower or "limit" in error_str_lower or "per minute" in error_str_lower or "per day" in error_str_lower)
                )
                
                if is_429_error:
                    retry_delay = 20  # Default: 20 segundos
                    if "retry" in error_str_lower:
                        import re
                        retry_match = re.search(r'retry.*?(\d+(?:\.\d+)?)\s*s', error_str_lower)
                        if retry_match:
                            retry_delay = int(float(retry_match.group(1))) + 1
                        else:
                            seconds_match = re.search(r'seconds?[:\s]+(\d+)', error_str_lower)
                            if seconds_match:
                                retry_delay = int(seconds_match.group(1)) + 1
                    
                    print(f"Error 429 - Quota exceeded in structured extraction. Retry delay: {retry_delay}s")
                    
                    return {
                        "success": False,
                        "error": f"429 Quota exceeded. Please retry in {retry_delay}s. Check your Gemini API quota limits.",
                        "text": "",
                        "structured_data": {},
                        "document_type": "unknown",
                        "timestamp": time.time(),
                        "retry_after": retry_delay,
                        "error_type": "quota_exceeded"
                    }
                
                # Verificar si es un error de timeout o conexión
                if "timeout" in error_str_lower or "connection" in error_str_lower:
                    return {
                        "success": False,
                        "error": f"API timeout/connection error: {error_msg}",
                        "text": "",
                        "structured_data": {},
                        "document_type": "unknown",
                        "timestamp": time.time()
                    }
                raise
            
            # Verificar finish_reason para detectar truncamiento o problemas
            finish_reason = None
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'finish_reason'):
                        finish_reason = candidate.finish_reason
                        break
            
            # Verificar si hay respuesta válida
            if not response.text:
                error_msg = "Empty response from Gemini"
                
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    error_msg = f"Content filtered: {response.prompt_feedback.block_reason}"
                elif finish_reason == 'SAFETY':
                    error_msg = "Content blocked by safety filters"
                elif finish_reason == 'RECITATION':
                    error_msg = "Content blocked due to recitation"
                elif finish_reason == 'MAX_TOKENS':
                    error_msg = "Response truncated: reached maximum output tokens limit. Consider increasing max_output_tokens in config."
                elif finish_reason == 'STOP':
                    error_msg = "Response stopped early. Content may be incomplete."
                
                print(f"Warning: {error_msg} (finish_reason: {finish_reason})")
                return {
                    "success": False,
                    "error": error_msg,
                    "text": "",
                    "structured_data": {},
                    "document_type": "unknown",
                    "timestamp": time.time()
                }
            
            # ADVERTENCIA: Verificar si la respuesta fue truncada (aunque haya texto)
            if finish_reason == 'MAX_TOKENS':
                print(f"⚠️ WARNING: Response was truncated due to max_output_tokens limit ({self.config.get('max_output_tokens', 65536)}). Some elements may be missing!")
                print(f"   Consider increasing max_output_tokens in gemini_config.json if document has many elements.")
            elif finish_reason == 'STOP':
                print(f"⚠️ WARNING: Response stopped early (finish_reason: {finish_reason}). Content may be incomplete.")
            
            # Parsear respuesta JSON
            response_text = response.text.strip()
            
            # Intentar extraer JSON de la respuesta
            try:
                # Limpiar markdown code blocks si existen
                if response_text.startswith('```'):
                    # Remover ```json o ``` del inicio y fin
                    response_text = response_text.strip('`')
                    if response_text.startswith('json'):
                        response_text = response_text[4:].strip()
                    if response_text.endswith('```'):
                        response_text = response_text[:-3].strip()
                
                # Parsear JSON
                parsed_response = json.loads(response_text)
                
                # Extraer campos
                ocr_text = parsed_response.get("ocr_text", "")
                ocr_text_translated = parsed_response.get("ocr_text_translated", ocr_text)  # Fallback a ocr_text si no viene traducido
                structured_data = parsed_response.get("structured_data", {})
                document_type = parsed_response.get("document_type", "unknown")
                
                # CRITICAL: Si ocr_text ES un JSON string (el JSON completo que Gemini retornó),
                # extraer el texto limpio Y los structured_data del JSON anidado
                if ocr_text and isinstance(ocr_text, str):
                    ocr_text_stripped = ocr_text.strip()
                    
                    # Si ocr_text empieza con JSON, probablemente es el JSON completo de Gemini
                    if ocr_text_stripped.startswith('{') or ocr_text_stripped.startswith('[\n'):
                        try:
                            # Intentar parsear como JSON
                            json_check = json.loads(ocr_text)
                            # Si es un objeto JSON completo de Gemini, extraer TODO
                            if isinstance(json_check, dict):
                                # PRIORIDAD 1: Si tiene "structured_data" dentro, usar esos datos (SIEMPRE tienen prioridad)
                                if "structured_data" in json_check:
                                    nested_structured = json_check["structured_data"]
                                    if isinstance(nested_structured, dict) and nested_structured:
                                        # CRITICAL: Los structured_data del JSON anidado SIEMPRE tienen prioridad
                                        # porque son los datos reales extraídos por Gemini
                                        # Reemplazar completamente structured_data del nivel superior
                                        structured_data = nested_structured.copy()  # Usar copia completa
                                        keys_count = len(nested_structured)
                                        total_items = sum(len(v) if isinstance(v, list) else 1 for v in nested_structured.values() if v)
                                        print(f"Warning: Using structured_data from nested JSON (found {keys_count} keys, {total_items} total items)")
                                
                                # PRIORIDAD 2: Extraer el texto limpio de "ocr_text" interno
                                if "ocr_text" in json_check:
                                    inner_text = json_check["ocr_text"]
                                    if inner_text and isinstance(inner_text, str):
                                        ocr_text = inner_text
                                        print(f"Warning: Extracted clean ocr_text from nested JSON structure ({len(ocr_text)} chars)")
                                
                                # PRIORIDAD 3: Extraer document_type si no se había extraído antes
                                if "document_type" in json_check:
                                    nested_doc_type = json_check["document_type"]
                                    if nested_doc_type and nested_doc_type != "unknown":
                                        document_type = nested_doc_type
                                        print(f"Warning: Extracted document_type from nested JSON: {document_type}")
                                
                                # PRIORIDAD 4: Extraer ocr_text_translated (puede ser texto plano o también JSON)
                                if "ocr_text_translated" in json_check:
                                    nested_translated = json_check["ocr_text_translated"]
                                    if nested_translated and isinstance(nested_translated, str):
                                        # Si ocr_text_translated también es un JSON string, extraer el texto interno
                                        nested_translated_stripped = nested_translated.strip()
                                        if nested_translated_stripped.startswith('{'):
                                            try:
                                                nested_translated_json = json.loads(nested_translated)
                                                if isinstance(nested_translated_json, dict):
                                                    # Priorizar "ocr_text_translated" interno, luego "ocr_text"
                                                    if "ocr_text_translated" in nested_translated_json:
                                                        ocr_text_translated = nested_translated_json["ocr_text_translated"]
                                                    elif "ocr_text" in nested_translated_json:
                                                        ocr_text_translated = nested_translated_json["ocr_text"]
                                                    else:
                                                        ocr_text_translated = nested_translated
                                                else:
                                                    ocr_text_translated = nested_translated
                                            except (json.JSONDecodeError, ValueError, TypeError) as e:
                                                # Si falla el parseo, usar el texto tal como está
                                                ocr_text_translated = nested_translated
                                                print(f"Warning: Could not parse nested ocr_text_translated JSON: {e}")
                                        else:
                                            # Es texto plano, usar directamente
                                            ocr_text_translated = nested_translated
                                        print(f"Warning: Extracted ocr_text_translated from nested JSON structure ({len(ocr_text_translated)} chars)")
                        except (json.JSONDecodeError, ValueError, TypeError) as e:
                            # Si falla el parseo, intentar buscar "ocr_text": "..." en el string usando regex
                            import re
                            match = re.search(r'"ocr_text"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', ocr_text)
                            if match:
                                extracted = match.group(1)
                                # Unescape JSON strings
                                extracted = extracted.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                                ocr_text = extracted
                                print(f"Warning: Extracted ocr_text from JSON string using regex (parse error: {e})")
                
                # Limpiar texto OCR (pero preservar estructura de líneas y contenido)
                cleaned_text = self._clean_extracted_text(ocr_text)
                cleaned_translated = self._clean_extracted_text(ocr_text_translated)
                
                # DEBUG: Verificar que structured_data tenga contenido
                if not structured_data or (isinstance(structured_data, dict) and len(structured_data) == 0):
                    print(f"Warning: structured_data is empty after extraction. ocr_text length: {len(ocr_text) if ocr_text else 0}")
                else:
                    data_keys = list(structured_data.keys())
                    print(f"Info: structured_data extracted with keys: {data_keys}")
                
                return {
                    "success": True,
                    "text": cleaned_text,
                    "translated_text": cleaned_translated,  # Texto traducido
                    "structured_data": structured_data,  # Asegurar que siempre sea un dict, nunca None
                    "document_type": document_type,
                    "model": self.model_name,
                    "timestamp": time.time()
                }
                
            except json.JSONDecodeError as e:
                # Si falla el parseo JSON, intentar extraer texto plano como fallback
                print(f"Warning: No se pudo parsear JSON de respuesta. Error: {e}")
                print(f"Respuesta recibida (primeros 500 chars): {response_text[:500]}")
                
                # Intentar usar el texto completo como OCR y crear estructura vacía
                cleaned_text = self._clean_extracted_text(response_text)
                
                return {
                    "success": True,  # Marcar como éxito porque al menos tenemos texto
                    "text": cleaned_text,
                    "translated_text": cleaned_text,  # Usar mismo texto si no hay traducción
                    "structured_data": {},  # Estructura vacía, se llenará con data_mapper como fallback
                    "document_type": "unknown",
                    "model": self.model_name,
                    "timestamp": time.time(),
                    "warning": "JSON parsing failed, using text-only extraction"
                }
        
        except Exception as e:
            error_msg = str(e)
            print(f"Error in Gemini structured extraction: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "text": "",
                "structured_data": {},
                "document_type": "unknown",
                "timestamp": time.time()
            }
    
    def _create_ocr_and_structure_prompt(self) -> str:
        """
        Crea un prompt comprehensivo que combina OCR + extracción estructurada.
        Este prompt le pide a Gemini que:
        1. Extraiga TODO el texto visible (OCR completo)
        2. Identifique el tipo de documento
        3. Extraiga campos estructurados según el tipo
        4. Retorne todo en formato JSON estructurado
        
        El prompt se cachea para evitar recalcularlo en cada llamada.
        """
        # Generar hash de conversiones actuales para validar cache
        import hashlib
        import json as json_module
        current_conversions_hash = hashlib.md5(
            json_module.dumps(self.currency_conversions, sort_keys=True).encode()
        ).hexdigest()
        
        # Usar cache solo si está disponible Y las conversiones no han cambiado
        if self._prompt_cache is not None and self._currency_conversions_hash == current_conversions_hash:
            return self._prompt_cache
        
        # Generar sección de conversiones de moneda dinámicamente
        currency_conversion_section = self._generate_currency_conversion_section()
        
        prompt = """You are an expert document processing system with advanced reasoning capabilities. Your task is to extract ALL text from this financial document AND structure the data according to the document type.

**CRITICAL: MONETARY VALUE FORMATTING (READ THIS FIRST - MANDATORY)**
Before you extract any monetary values, remember this MANDATORY rule:
- ALL monetary values >= 1000 MUST be formatted as STRINGS with thousands separators (commas)
- Examples: 5693.07 → "5,693.07", 35800 → "35,800.00", 1000 → "1,000.00"
- Values < 1000 can be numbers or strings: 500.00 or "500.00"
- This applies to: nPrecioTotal, nPrecioUnitario, nImporte, precioTotal, entered_amount, total_usd
- DO NOT return numbers >= 1000 without commas - always format as strings with commas

**CRITICAL: CHINESE TO ENGLISH TRANSLATION (MANDATORY FOR ALL TEXT FIELDS)**
- **MANDATORY RULE**: ALL text fields that contain Chinese characters (中文) MUST be automatically translated to English
- This applies to ALL text/string fields in the JSON output, including but not limited to:
  * tDescripcion, tdescription, tDescripcion (all description fields)
  * tCliente, tRazonSocial, tEmployeeName (all name fields)
  * tNumero, tSerie, tStampname, tsequentialnumber (all identifier fields)
  * tTipo, tNaturaleza, tDepartamento, tDisciplina (all category/type fields)
  * tUnidad, tDivisa, tIdioma (all code/unit fields)
  * tInvoiceAmount, tTaxAmount, tGrossAmount (all label fields)
  * ANY other text field that contains Chinese characters
- **TRANSLATION EXAMPLES**:
  * "住宿服务*住宿费" → "Accommodation service*Accommodation fee"
  * "出租汽车公司" → "Taxi company"
  * "里程" → "Mileage"
  * "金额" → "Amount"
  * "合计" → "Total"
  * "车号:冀 F-TU275" → "Car number: Ji F-TU275"
  * "里程:81.7千" → "Mileage: 81.7 thousand"
  * "等候时间:00:20:00" → "Waiting time: 00:20:00"
  * "附加费:" → "Surcharge:"
  * "天津市客运出租专用发票" → "Tianjin Passenger Transport Taxi Special Invoice"
  * "发票号码" → "Invoice number"
  * "发票代码" → "Invoice code"
- **PROCESS**: When you extract any text field:
  1. Check if it contains Chinese characters (中文)
  2. If YES: Translate to English while preserving structure, numbers, codes, and special characters
  3. If NO: Keep the original text as-is
- **PRESERVE**: Keep numbers, codes, special characters, and formatting exactly as they appear
- **DO NOT**: Leave Chinese text untranslated in any JSON field - always translate to English

**IMPORTANT: USE YOUR REASONING ABILITY**
- **ANALYZE THE CONTEXT**: Look at the entire document to understand relationships between values, sections, and elements
- **RELATE INFORMATION**: Connect related pieces of information across different parts of the document (e.g., handwritten values near printed totals, highlighted boxes containing summaries)
- **INTERPRET VISUAL CUES**: Pay attention to visual emphasis (boxes, highlights, positioning) to identify important values like totals or conversions
- **THINK LOGICALLY**: If you see multiple monetary values, use reasoning to determine which one is the correct total:
  * Handwritten USD values near printed RM/MYR totals are likely currency conversions
  * Values in highlighted boxes are usually final totals or summaries
  * Values that match payment amounts are likely the correct totals
- **EXTRAPOLATE MEANING**: If information is partially visible or unclear, use context clues to infer the correct value
- **VALIDATE CONSISTENCY**: Check that extracted totals match sums of line items when possible

**MONETARY VALUE FORMATTING RULES (CRITICAL - MANDATORY):**
- For ALL monetary values (nPrecioTotal, nPrecioUnitario, nImporte, precioTotal, entered_amount, total_usd, etc.):
  - **MANDATORY RULE**: Values >= 1000 MUST ALWAYS be formatted with thousands separators (commas) as STRINGS, NOT as numbers
  - **MANDATORY RULE**: Values < 1000 can be numbers or strings: 500.00 or "500.00"
  - **CRITICAL EXAMPLES** (you MUST follow these exactly):
    * If you extract 35800 → MUST return "35,800.00" (as string with quotes)
    * If you extract 258000 → MUST return "258,000.00" (as string with quotes)
    * If you extract 5693.07 → MUST return "5,693.07" (as string with quotes)
    * If you extract 1234.56 → MUST return "1,234.56" (as string with quotes)
    * If you extract 1000 → MUST return "1,000.00" (as string with quotes)
    * If you extract 500.00 → Can return 500.00 (number) or "500.00" (string)
  - **FORMATTING PROCESS**:
    1. Extract the numeric value from the document (e.g., 5693.07)
    2. Check if value >= 1000
    3. If YES: Format with commas and 2 decimals as STRING: "5,693.07"
    4. If NO: Can use number or string format
  - If document already shows formatted values (e.g., "35,800.00"), preserve that format as string
  - If document shows unformatted values (e.g., "35800" or "5693.07"), format them with commas: "35,800.00" or "5,693.07"
  - Always include 2 decimal places for monetary values: "35,800.00" not "35,800"
  - **THIS IS MANDATORY**: Do NOT return numbers >= 1000 without commas. Always format them as strings with commas.
  - This applies to ALL monetary fields: nPrecioTotal, nPrecioUnitario, nImporte, precioTotal, entered_amount, total_usd, etc.

CRITICAL: You must return a STRICT JSON object with this exact structure:
{
  "ocr_text": "ALL extracted text from the document as PLAIN TEXT (NOT JSON - just raw text with line breaks, complete, nothing missing)",
  "ocr_text_translated": "Translated text to English as PLAIN TEXT (if original is not English/Spanish, otherwise same as ocr_text)",
  "document_type": "ticket|factura_electronica|comprobante|nota_bill|resumen|jornada|expense_report|concur_expense|unknown",
  "structured_data": {
    // See detailed structure below based on document_type
  }
}

CRITICAL INSTRUCTIONS FOR ocr_text FIELD:
1. The "ocr_text" field MUST contain ONLY plain text extracted from the document - NO JSON structures, NO nested objects, NO arrays, NO quotes around the text, NO JSON field names.
2. DO NOT put JSON structures inside ocr_text - it should be plain text only.
3. Example of CORRECT ocr_text: "BSQE\nBS0003\nRound Trips Toll Fees\nDate Visit\nMalaysia Currency\nUS Currency\n24-Jun-25\n41.35\n10\n29-Jun-25\n41.35\n10\n$26"
4. Example of INCORRECT ocr_text: 
   - "{\n  \"ocr_text\": \"BSQE...\" }" - WRONG!
   - "\"ocr_text\": \"...\"" - WRONG!
   - Any JSON structure - WRONG!
5. Extract structured data ONLY in the "structured_data" section, NOT in ocr_text.
6. The ocr_text value should be a simple string containing the raw text, not a JSON-encoded string. When you return the JSON response, the ocr_text field should look like: "ocr_text": "Actual text here\nwith newlines\nand content" - NOT "ocr_text": "{\"ocr_text\": \"...\"}"

CRITICAL INSTRUCTIONS FOR structured_data:
1. Extract each item ONLY ONCE per page - if you see the same value appearing multiple times in tables, extract it as separate rows but do NOT create duplicate identical entries.
2. Only include data in structured_data if it appears in the OCR text you extracted - do NOT infer or create data that is not visible in the document.
3. For mcomprobante_detalle: Extract each table row as a separate item only if it appears in the OCR text. Do NOT extract the same row multiple times.
4. Avoid duplicate values - if a value appears once in OCR, it should appear once in structured_data (unless it's genuinely different rows in a table).
5. Handle each page independently - extract data from THIS page only, not from other pages.
6. **CRITICAL FOR MULTIPLE RECEIPTS**: If document contains multiple receipts/invoices (e.g., train ticket + taxi receipts, or multiple small receipts):
   - Extract EACH receipt as a separate entry in mcomprobante array
   - Each receipt should have its own tNumero, dFecha, nPrecioTotal
   - For Chinese taxi receipts: Extract invoice code (发票代码) or invoice number (发票号码) as tNumero, date (日期) as dFecha, amount (金额) as nPrecioTotal
   - For train tickets: Extract ticket number (电子客票号) as tNumero, issue date (开票日期) as dFecha, fare (票价) as nPrecioTotal
   - Do NOT combine multiple receipts into one comprobante entry
   - If document has 1 train ticket + 5 taxi receipts, you should have 6 entries in mcomprobante array
6. TEXT FIELDS (ALL fields containing text/strings): MUST be CLEAN, PROFESSIONAL text extracted DIRECTLY from the document itself.
   - **CRITICAL: CHINESE TRANSLATION REQUIREMENT (MANDATORY)**: If ANY text field contains Chinese characters (中文), you MUST automatically translate it to English while preserving structure, numbers, codes, and special characters. This applies to ALL text fields, not just descriptions.
   - **TRANSLATION EXAMPLES FOR ALL TEXT FIELDS**:
     * "住宿服务*住宿费" → "Accommodation service*Accommodation fee"
     * "出租汽车公司" → "Taxi company"
     * "里程" → "Mileage"
     * "金额" → "Amount"
     * "合计" → "Total"
     * "车号:冀 F-TU275" → "Car number: Ji F-TU275"
     * "里程:81.7千" → "Mileage: 81.7 thousand"
     * "等候时间:00:20:00" → "Waiting time: 00:20:00"
     * "附加费:" → "Surcharge:"
     * "天津市客运出租专用发票" → "Tianjin Passenger Transport Taxi Special Invoice"
     * "发票号码" → "Invoice number"
     * "发票代码" → "Invoice code"
   - **DESCRIPTION FIELDS (tDescripcion, tdescription)**: 
     * GOOD examples: "Toll", "Hotel", "Meal", "ICE VANILLA LATT", "ADD ESP SHT", "Room Charge", "Transportation Fee", "Grand Total USD", "TOTAL EXPENSES", "JENIS BARANG-BARANG" (if that's what the document shows)
     * BAD examples (NEVER DO THIS): 
       - "\"ocr_text\": \"BECHTEL JOBS NO.\"" - WRONG!
       - "\"nImporte\":" - WRONG!
       - "\"_myr_amount\":" - WRONG!
       - "\"nPrecioTotal\": 5." - WRONG!
       - "\"ocr_text\": \"...\"" - WRONG!
       - Any JSON field names or structures - WRONG!
     * HOW TO EXTRACT CORRECTLY: 
       - Look at the ACTUAL document. Find the "Description" or "PARTICULARS" or "摘要" column in the table.
       - Extract EXACTLY what is written in that column - if it says "ICE VANILLA LATT", extract "ICE VANILLA LATT". If it says "Toll", extract "Toll". If it says "Hotel", extract "Hotel".
       - For receipt/coffee shop items: Extract item names like "ICE VANILLA LATT", "ADD ESP SHT", etc. exactly as shown.
       - For expense summaries: Extract "Toll", "Hotel", "Meal" exactly as shown in Description column.
       - For empty receipts: If there are table headers but no items filled, do NOT create items. Only extract items that actually have values in the table.
       - **If text is in Chinese, translate to English**: "住宿服务*住宿费" → "Accommodation service*Accommodation fee"
   - **ALL OTHER TEXT FIELDS** (tCliente, tRazonSocial, tNumero, tSerie, tStampname, tTipo, tNaturaleza, tDepartamento, tDisciplina, tUnidad, tDivisa, tIdioma, etc.):
     * Extract the text as it appears in the document
     * **If the text contains Chinese characters, translate to English automatically**
     * Preserve numbers, codes, special characters, and formatting
   - DO NOT extract JSON structures, OCR metadata fields, technical field names, or anything that is NOT visible in the document itself.
   - DO NOT extract table headers as item descriptions - only extract actual item descriptions from filled table rows.
7. **CRITICAL: DO NOT INCLUDE ANY FIELDS STARTING WITH "_" (MANDATORY)**
   - **MANDATORY RULE**: NEVER include ANY field that starts with underscore "_" in the structured_data output
   - **EXAMPLES OF FORBIDDEN FIELDS** (DO NOT INCLUDE):
     * "_currency", "_source_line", "_auto_extracted", "_currency_code"
     * "_myr_amount", "_highlighted", "_is_total_row", "_total"
     * "_metadata", "_internal", "_processing", "_temp"
     * ANY field name that starts with "_" - FORBIDDEN
   - These are internal processing/metadata fields and should NEVER appear in the final JSON response
   - Only include standard fields without underscore prefix (e.g., nCantidad, tDescripcion, nPrecioUnitario, nPrecioTotal, tjobno, ttype, nImporte, tStampname, tsequentialnumber, etc.)
   - **VALIDATION**: Before returning the JSON, check that NO field names start with "_" - if you find any, remove them

=== SPECIAL PRIORITIES (READ FIRST - THESE OVERRIDE OTHER INSTRUCTIONS) ===
1. HANDWRITTEN VALUES (HIGHEST PRIORITY - USE REASONING): 
   **CRITICAL**: Handwritten text with monetary values has HIGHEST PRIORITY and overrides ANY printed values.
   - **DETECTION**: Look for text that appears manually written - different style, position, annotation-like appearance, or clearly added by hand
   - **PATTERNS**: Handwritten values often appear near printed totals as corrections/conversions, at bottom of receipts as final validations, in boxes/highlighted areas, or with slight misalignment
   - **EXAMPLES**: "USD 5.55" written by hand near printed "Total RM22.80" → Use 5.55 as nPrecioTotal; "USD425" handwritten at bottom → Use 425.00 as nPrecioTotal
   - **REASONING**: Handwritten USD values are usually final validations, currency conversions, or corrections. If you see both printed RM/MYR and handwritten USD, the handwritten USD is the authoritative conversion.
   - **EXTRACTION**: Mark handwritten values with [HANDWRITTEN] in ocr_text. Extract handwritten USD value in ocr_text AND use it as nPrecioTotal in structured data. Handwritten USD is ALWAYS the PRIMARY total.

2. HIGHLIGHTED VALUES: Values in red boxes, yellow highlights, or visually emphasized sections are PRIORITY - extract them completely:
   - "TOTAL AMOUNT IN US$" values in red boxes at bottom of tables (Attachment to Invoice) - Extract as separate item in mcomprobante_detalle
   - "TOTAL $ XXX.XX" in red boxes (Italian invoices) - Extract the final total after stamp duty (the LAST value)
   - Report Total amounts in red boxes (Expense Reports)
   - For "ATTACHMENT TO INVOICE": Extract red box total as separate mcomprobante_detalle entry

3. CALCULATIONS: Extract calculations like "USD 4,301.00 + USD 616.00 = USD 6,369.00" completely. Extract both individual values AND final total.

4. GL JOURNAL DETAILS: If document is "GL Journal Details" WITH highlighted calculations (red box), extract ONLY the highlighted calculation values, NOT all table rows. If WITHOUT highlighted calculations, extract all table rows as items (use ONLY nPrecioUnitario, NOT nPrecioTotal).

5. ATTACHMENT TO INVOICE: For "ATTACHMENT TO INVOICE" documents - THIS IS CRITICAL AND MANDATORY:
   - Extract ALL table rows as separate items in mcomprobante_detalle - DO NOT skip any rows
   - Table structure: Resource | Vendor | Assignment no. | Report Number | Request | Type of Activity | Date of visit | hrs | hrly rate | km/miles | mileage rate | Expenses | Total Labor | Total Expenses | Total Amount
   - For EACH data row: Extract Resource Name, Vendor Name, Type of Activity, Date of visit, hrs, hrly rate OR mileage rate, Total Amount (REQUIRED)
   - Mapping to mcomprobante_detalle: tDescripcion: "Resource Name - Vendor Name - Type of Activity"; nCantidad: from "hrs" OR "km/miles"; nPrecioUnitario: from "hrly rate" OR "mileage rate"; nPrecioTotal: from "Total Amount" (REQUIRED)
   - For "TOTAL AMOUNT IN US$" row at bottom (usually in red box): Extract as SEPARATE entry with tDescripcion: "TOTAL AMOUNT IN US$", nPrecioTotal: value from red box (CRITICAL)

6. ITALIAN INVOICES (FATTURA): Pay special attention to red boxes containing invoice numbers (e.g., "FATTURA NO.: 333/25") and total amounts. If "TOTAL" is on one line and "$ XXX.XX" values on following lines, extract ALL values but prioritize the LAST value (final total after stamp duty). Example: "TOTAL\n$\n120.60\n$\n2.34\n$\n122.94" → extract 122.94 as nPrecioTotal.

7. WEEKLY TOTALS (OnShore): Extract lines with multiple large monetary values at the end of tables (e.g., "7,816,974.79 305,349.84 6,333,781.02"). Look for lines with ONLY numbers (>=2 large values >=1000) and no item descriptions.

8. CASH FLOW VALUES (OnShore): Extract "Total Disbursement", "Period Balance", "Cumulative Cash Flow", "Opening Balance", "Total Receipts" values from cash flow tables. Include negative values correctly (from parentheses like (305,350) → -305350).

9. DEPARTMENTS & DISCIPLINES (OnShore): Extract department names and discipline names from tables, headers, or classification sections. Map NC Codes (611=Engineering, 612=Operations, etc.).

10. INVOICE APPROVAL REPORT: Do NOT extract "Line Item Details" as items. Those are data columns (Line Amount, Nat Class, Job, Sub Job, Cost Code), NOT purchase items.

11. INVOICE GROUP DETAIL: Do NOT extract "Invoice Group Detail" section as items. Skip lines matching pattern like "BSQEUSD 751671 33025" or containing "INV Group ID".

12. LABOR DETAILS: For "BSQE SERVICE CHARGES" or labor tables with "Emp Name", extract rows with pattern: Employee Name + BSQE code + date + Hours + Hrly Rate + Currency + Amount. Map: hours → nCantidad, rate → nPrecioUnitario, amount → nPrecioTotal, description → "Employee Name INSPECTING".

13. PROJECT MONTHLY EXPENSE REPORTS: For "Project Monthly Expense" type documents - CRITICAL: Extract EVERY data row from the table as a separate mresumen entry. Extract Assignment No., Charge No., Report No., Country, Type of Activity, Type, Transportation amount, Hotel amount, Total amount. Extract company name from header → mproveedor. Extract month/period from header → dFecha. Extract sequential number and stamp name from header. For "Total" row at bottom: Extract as separate mresumen entry (DO NOT include _is_total_row or any field starting with "_"). DO NOT skip any rows.

14. EXPENSE SUMMARY TABLES: For documents with multiple expense tables (like Bechtel expense summaries with Toll/Hotel/Meal):
   - Extract EVERY row from EVERY table as a separate mresumen entry
   - CRITICAL FOR DESCRIPTIONS: Look at the actual "Description" column. If it says "Toll", extract "Toll". If it says "Hotel", extract "Hotel". Extract ONLY what the document shows, NOT JSON structures, NOT OCR metadata.
   - Use USD amount as nImporte (prioritize USD over MYR)
   - Extract job number from header (e.g., "BECHTEL JOBS NO.: 26443") as tjobno
   - For "Grand Total USD" rows: Extract "Grand Total USD" as tdescription, extract USD amount as nImporte (DO NOT include _highlighted or any field starting with "_")
   - For "TOTAL EXPENSES" rows: Extract "TOTAL EXPENSES" as tdescription, extract USD amount as nImporte (DO NOT include _highlighted or any field starting with "_") - these have highest priority
   - Do NOT skip any rows - extract ALL items from ALL tables completely

=== STEP 1: EXTRACT ALL TEXT (OCR) ===
Extract 100% of ALL visible text from this document. Read EVERYTHING line by line, character by character:
**CRITICAL FOR MULTIPLE RECEIPTS**: If document contains multiple receipts/invoices on one page (e.g., train ticket + multiple taxi receipts, or multiple small receipts arranged in grid):
- Extract ALL text from ALL receipts completely
- Do NOT skip any receipt, even if they are small or arranged in a grid
- Each receipt may have its own header, date, amount, vehicle number, etc.
- For Chinese taxi receipts: Extract ALL receipts with their "车号" (Car No.), "日期" (Date), "上车" (Boarding time), "下车" (Alighting time), "单价" (Unit price), "里程" (Mileage), "等候" (Waiting time), "金额" (Amount)
- For train tickets: Extract ticket number, date, origin station, destination station, train number, seat, fare, passenger name, etc.
- Look for patterns that indicate multiple documents: multiple "发票联" (Invoice Copy), multiple "发票代码" (Invoice Code), multiple dates, multiple amounts
- Every row of every table completely (including Resource, Vendor, Assignment no., Report Number, Date, hrs, rates, amounts)
- For expense summary tables: Extract ALL rows from ALL tables, including Item No., Description (Toll/Hotel/Meal), MYR amounts, USD amounts
- For expense summary tables: Extract "Grand Total USD" values and "TOTAL EXPENSES" values completely
- For Bechtel expense summaries: Extract job number from "BECHTEL JOBS NO.:" and project name from "Project:"
- For hotel invoices: Extract ALL room charges, dates, guest names, invoice numbers, folio numbers, room numbers, arrival/departure dates, adult/child counts
- For hotel invoices: Extract ALL line items including: Date, Description, Charge (MYR), Credits (MYR), Room Charges, Local Government Fees, Tourism Tax, Total MYR, Balance Due
- For hotel invoices: Extract ALL details: Print Date, SST No., TTX Reg. No., Arrival, Departure, Adult/Child, Room No., Invoice No., Folio No., Conf. No., Page No., Cashier No., User ID
- For hotel invoices: Extract guest information: Guest Name, Group Code, Travel Company Name, Travel Agent, Account No., full address
- All text, numbers, symbols, codes
- Headers, footers, stamps, watermarks, logos
- All dates in any format (but validate - avoid phone numbers like 1300-80-8989)
- All currency symbols and amounts (including handwritten USD values like "USD 192.25")
- Highlighted/boxed/colored sections (especially red boxes, yellow highlights, highlighted totals like "Grand Total USD")
- Handwritten text (mark with [HANDWRITTEN] if detected, especially handwritten USD values)
- Calculations and formulas (e.g., "USD 4,301.00 + USD 616.00 = USD 6,369.00")
- Labor details (Emp Name, Hours, Hrly Rate, Amount, BSQE codes, Employee Numbers, Org Codes, Project allocations, Period dates)
- For labor/jornada documents: Extract ALL employee rows with employee numbers, full names, dates (Labor PPE), currencies (CLP, PEN), org codes, total hours per employee, hours allocated to each project/cost center (26442-007, 26443-353, etc.), and cost breakdowns by project
- For labor/jornada documents: Extract ALL cost summaries: Plan OH/hr rates (e.g., "$ 22.00"), total costs by project (e.g., "$ 4,301.00" for 26442-007), total costs by section/company (V52T Bechtel Chile: $ 6,589.00, XYQN Bechtel Peru: $ 7,744.00), overall totals (Total Amt: $14,333.00, Total Hrs: 651.50)
- For labor/jornada documents with multiple sections: Extract employees from EACH section separately (e.g., "V52T Bechtel Chile" section and "XYQN Bechtel Peru" section)
- For labor/jornada documents: Extract Period from "Period Jul 2025" → use "JUL 2025" as fRegistro
- For labor/jornada documents: Extract sequential number from "BSQE BS0001" → use "BS0001" as tsequentialnumber
- Weekly totals (lines with multiple large monetary values at end of tables)
- Cash flow values (Total Disbursement, Period Balance, Cumulative, Opening Balance, Total Receipts)
- Departments and disciplines (Engineering, Operations, Maintenance, etc.)
- Org codes, NC codes, Job sections
- Hotel names, supplier names, company names in headers
- ALL table headers and ALL table rows completely - if there are multiple tables on the page, extract ALL rows from ALL tables
- Do NOT skip any text, even if it seems redundant
- Do NOT summarize - extract EVERYTHING exactly as it appears
- Use [unclear] only if truly illegible
- For hotel invoices, ensure you extract ALL charges, dates, guest details, and totals
- For expense summaries, ensure you extract ALL items from ALL tables, including Item Numbers, Descriptions, MYR and USD amounts
- For purchase orders and equipment documents: Extract ALL item details including codes, descriptions, quantities, units of measure, unit prices, extended prices, and totals
- For vehicle/transport documents (Guías de Remisión): Extract ALL vehicle information (brand, license plate, TUCE), driver information (name, document number, license number), transport details (origin, destination, weight, modality)
- For machinery/equipment tables: Extract ALL rows with descriptions, serial numbers, model numbers, codes, quantities, units, and ALL monetary values (unit prices, totals, extended prices)

=== STEP 2: IDENTIFY DOCUMENT TYPE ===
Classify the document as one of (PRIORITY ORDER - check top to bottom):

PRIORITY 1: Classify document as one of these types (check in order - if none match, use "nota_bill"):

PRIORITY 1A: "ticket" if document contains ANY of these patterns:
- Ticket keywords: "ticket", "boleto", "pasaje", "railway", "train ticket", "bus ticket", "flight ticket", "boarding pass"
- Chinese ticket keywords: "票", "车票" (train ticket), "机票" (flight ticket), "电子客票" (electronic ticket), "铁路电子客票" (railway electronic ticket), "客票号" (ticket number)
- Ticket-specific patterns: "ticket number", "ticket no", "ticket no.", "电子客票号" (electronic ticket number), "座位" (seat), "席别" (seat class)
- Train/railway keywords: "railway", "train", "高铁" (high-speed rail), "火车" (train), "列车" (train), "出发站" (departure station), "到达站" (arrival station)

PRIORITY 1B: "factura_electronica" if document contains ANY of these patterns:
- Electronic invoice keywords: "factura electrónica", "boleta electrónica", "electronic invoice", "e-invoice", "e-factura"
- Chinese electronic invoice keywords: "电子发票" (electronic invoice), "电子普通发票" (electronic ordinary invoice)
- Digital invoice indicators: "Código de Autorización" (Authorization Code - common in electronic invoices), "Número de Autorización" (Authorization Number)
- Electronic invoice numbers: Patterns like long authorization codes or digital signatures typical of electronic invoices

PRIORITY 1C: "comprobante" if document contains ANY of these patterns (EXCLUDE patterns from Ticket and Factura Electrónica above):
- Invoice keywords: "invoice", "factura", "boleta", "bill", "recibo", "fattura", "invoice no", "invoice number", "invoice num"
- Table headers in Spanish: "cant.", "descripción", "precio unitario", "importe"
- Table headers in Malay/Chinese: "tarikh", "kuantiti", "harga", "jumlah", "no.", "jumlah/", "總計", "总计", "cash / invoice", "cash/invoice"
- Chinese invoice keywords: "发票", "发票号码", "发票代码", "发票联" (Invoice Copy) - BUT NOT "电子发票" (which goes to Factura Electrónica)
- Chinese taxi receipt keywords: "车号" (Car No.), "证号" (Certificate No.), "日期" (Date), "上车" (Boarding), "下车" (Alighting), "金额" (Amount), "里程" (Mileage)
- Receipt keywords: "receipt", "recibo", "NO. KUANTITI", "PARTICULARS", "BUTIR-BUTIR"
- Other: "GL Journal Details", Oracle AP invoices, "Invoice Approval Report"
- **CRITICAL**: Documents with multiple receipts (e.g., multiple taxi receipts) should be classified as "comprobante" and EACH receipt should be extracted separately

PRIORITY 1D: "nota_bill" (FALLBACK) - Use this if document does NOT match Ticket, Factura Electrónica, or Comprobante patterns above:
- This is the default type for documents that contain billing/invoice-like information but don't match the specific patterns above
- Use when document appears to be a bill/invoice/receipt but doesn't clearly fit into Ticket, Factura Electrónica, or Comprobante categories

PRIORITY 2: "concur_expense" if document contains (check BEFORE comprobante-related types):
- "concur expense", "concur", "Line Item by Job Section"
- Check BEFORE expense_report

PRIORITY 3: "expense_report" if document contains:
- "bechtel expense report", "expense report", "report key", "report number", "report date", "bechexprpt", "BECHEXPRPT", "report purpose", "bechtel owes"
- "Project Monthly Expense" (with table structure showing Assignment No., Charge No., Report No., Country, Type of Activity, Transportation, Hotel, Total)
- Tables with columns: "Assignment No.", "Charge No.", "Report No.", "Country", "Type of Activity", "Type", "Transportation (USD)", "Hotel (USD)", "Total (USD)"

PRIORITY 4: "resumen" if document contains:
- "summary", "resumen", "consolidado", "reimbursable expenditure"
- "BECHTEL JOBS NO.:" with expense tables (Toll, Hotel, Meal)
- Multiple expense tables with "Grand Total USD" or "TOTAL EXPENSES"
- Documents showing multiple expense categories (Toll, Hotel, Meal) in separate tables

PRIORITY 5: "jornada" if document contains:
- "empl no", "full name", "labor", "total hours", "employee", "empl", "period", "hours worked"

PRIORITY 6: "unknown" if none of the above match

SPECIAL CASES (OVERRIDE RULES):
- "ATTACHMENT TO INVOICE" → ALWAYS comprobante (highest priority)
- "BECHTEL JOBS NO.:" with expense tables (Toll, Hotel, Meal) → resumen
- Documents with multiple expense tables and "Grand Total USD" → resumen
- Documents with "TOTAL EXPENSES" at the bottom → resumen
- "GL Journal Details" with highlighted calculations → comprobante (extract ONLY highlighted values)
- "GL Journal Details" without highlighted calculations → comprobante (extract all table rows as items)
- Oracle AP screens → comprobante
- "Invoice Approval Report" → comprobante (do NOT extract "Line Item Details" as items)
- Documents with train ticket + taxi receipts: Train ticket → ticket, each taxi receipt → comprobante (extract separately)

=== STEP 3: EXTRACT STRUCTURED DATA ===
Based on the document_type, extract structured fields:

FOR ALL DOCUMENT TYPES - Extract these catalog tables:

1. mdivisa (currencies): Array of currency codes found
   Example: [{"tDivisa": "USD"}, {"tDivisa": "PEN"}]
   DETECTION PATTERNS (check ALL of these):
   a) Explicit currency codes: Look for "USD", "PEN", "EUR", "RM", "MYR", "CLP", "GBP", "JPY", "CNY", "COP", "MXN", "ARS", "BRL" as standalone words or followed directly by numbers (e.g., "USD6.40", "RM25.50")
   b) Symbol detection:
      - $ = USD (if $ appears before or after monetary values)
      - ¥ = CNY (Chinese yuan) if document has Chinese characters, otherwise might be JPY
      - 元 = CNY (Chinese yuan character - always CNY)
   c) Chinese currency patterns:
      - Numbers followed by "元" (yuan character) → CNY
      - "总计" (total) or "金额" (amount) or "总金额" (total amount) or "合计" (total) followed by numbers and "元" → CNY
      - "¥" symbol with Chinese text → CNY
   d) Near total/amount keywords:
      - Look for currency codes near "Total", "TOTAL", "Amount", "AMOUNT", "总计", "JUMLAH", "金额"
      - Format: "Total USD 1,234.56" OR "USD Total 1,234.56" OR "总计 1,234.56 元"
      - Prioritize currency found near totals
   e) Context inference (if no explicit currency found):
      - If document has Chinese characters and monetary values → CNY
      - If document has "$" symbol and monetary values → USD
      - If document is in English and has monetary values → USD
      - If document is in Spanish and has monetary values → PEN (default for Spanish documents)
   f) Multiple currencies: Extract ALL currencies found (e.g., if document shows "RM 19.50" and "USD 5.00", include both)

2. mproveedor (suppliers): Array of supplier/company names
   Example: [{"tRazonSocial": "Company Name SDN BHD"}]
   Look for: "Supplier Name:", "Vendor:", "PO Trading Pa:", "Supplier Name", company names in headers
   CRITICAL: For expense reports, look for company names in document headers/titles:
   - "Project Monthly Expense" reports: Extract company name from header (e.g., "SGS-CSTC Standards Technical Service., Ltd. Shanghai Branch")
   - Look for company names at the top of the document, before the table
   - Look for company names in document titles or headers
   - For "Attachment to Invoice": Extract "Vendor" name from table columns
   Include legal suffixes: SDN BHD, LLC, Inc, Company, S.A., S.L., SRL, Ltd., Branch
   IMPORTANT TRANSLATION FORMAT: If the company name is NOT in English or Spanish (e.g., Chinese, Italian, etc.), you MUST include BOTH the Spanish translation AND the original name in this EXACT format: "Spanish Translation (Original Name)"
   - The Spanish translation goes FIRST
   - The original name goes in parentheses SECOND
   - Example: "蟠龙公司" → "Compañía Panlong (蟠龙公司)"
   - Example: "辰州公司" → "Compañía Chenzhou (辰州公司)"
   - Example: "联运公司" → "Compañía Lianyun (联运公司)"
   - Example: "兴达公司" → "Compañía Xingda (兴达公司)"
   - For English/Spanish names, keep as-is without translation

3. mnaturaleza (categories): Array from: ['Alimentación','Hospedaje','Transporte','Combustible','Materiales','Servicios','Otros']
   Example: [{"tNaturaleza": "Alimentación"}]
   DETECTION PATTERNS (check in first 500 characters of document):
   - Alimentación: 'MEAL', 'FOOD', 'ALIMENTACIÓN', 'ALIMENTACION', 'COMIDA', 'RESTAURANT', 'RESTAURANTE', 'CAFE', 'CAFÉ', 'MENU', 'MENÚ', 'TAKEAWAY', 'DELIVERY', 'ORDER', 'PEDIDO'
   - Hospedaje: 'HOTEL', 'HOSPEDAJE', 'LODGING', 'ACCOMMODATION', 'ROOM', 'GUEST', 'CHECK-IN', 'CHECK-OUT'
   - Transporte: 'TRANSPORT', 'TRANSPORTE', 'TAXI', 'TOLL', 'PEAJE', 'GASOLINE', 'GASOLINA', 'FUEL'
   - Combustible: 'FUEL', 'COMBUSTIBLE', 'GASOLINE', 'GASOLINA', 'PETROL', 'DIESEL'
   - Materiales: 'MATERIALS', 'MATERIALES', 'SUPPLIES', 'SUMINISTROS'
   - Servicios: 'SERVICES', 'SERVICIOS', 'SERVICE', 'SERVICIO'
   - Otros: Default if none of above match

4. mdocumento_tipo: Document type catalog
   Example: [{"iMDocumentoTipo": 1, "tTipo": "Ticket"}]
   Mapping: ticket=1, factura_electronica=1, comprobante=1, nota_bill=1, resumen=2, jornada=3, expense_report=4, concur_expense=5
   NOTE: All invoice/receipt types (ticket, factura_electronica, comprobante, nota_bill) map to the same catalog ID (1) but have different tTipo names:
   - "Ticket" for ticket type
   - "Factura Electrónica" for factura_electronica type
   - "Comprobante" for comprobante type
   - "Nota-Bill" for nota_bill type

5. midioma (language): Detect language from keywords and characters - CRITICAL: This MUST be extracted correctly
   Example: [{"iMIdioma": 1, "tIdioma": "Español"}]
   Mapping: es=Español(1), en=Inglés(2), it=Italiano(3), zh=Chino(4), other=Otro(5)
   DETECTION PATTERNS (check ALL - highest priority first):
   a) Chinese characters ([\u4e00-\u9fff]) → zh (Chino)
   b) Spanish keywords: "factura", "boleta", "servicios", "empresa", "cliente", "proveedor", "total", "fecha", "descripción", "cantidad", "precio", "impuesto", "jornada", "empleado" → es (Español)
   c) English keywords: "invoice", "summary", "bill", "services", "company", "client", "supplier", "total", "date", "description", "quantity", "price", "tax", "labor", "employee", "arrival", "departure", "charge", "payment" → en (Inglés)
   d) Italian keywords: "fattura", "servizi", "azienda", "cliente", "fornitore", "totale", "data", "descrizione", "quantità", "prezzo", "imposta", "giornata", "dipendente" → it (Italiano)
   e) Malay keywords: "tarikh", "jumlah", "terima", "disahkan", "makan", "kuantiti", "harga", "barang" → other (Otro)
   f) Count matches: Language with most keyword matches wins (minimum 2 matches required, except for Chinese which is detected by characters)

6. munidad_medida (units of measure): Array of unit codes found - FLEXIBLE: Extract ANY unit you find, even if not in the list below
   Example: [{"tUnidad": "kg"}, {"tUnidad": "EACH"}, {"tUnidad": "KT"}, {"tUnidad": "MT2"}]
   DETECTION PATTERNS (check ALL of these, but be FLEXIBLE - extract ANY unit you find):
   a) Explicit unit codes in tables: Look for unit columns in item tables (e.g., "Unit", "Unidad", "U.M.", "Unit of Measure", "UOM")
   b) Common standard units:
      - Weight: "kg", "lb", "g", "oz", "ton", "tonelada", "KGM"
      - Count/Quantity: "unidades", "units", "pcs", "pieces", "NIU", "EACH", "KT" (kit)
      - Length: "m", "ft", "cm", "in", "mt", "metros", "pies"
      - Area: "m2", "mt2", "MT2", "ft2", "sqm", "sqft"
      - Volume: "L", "gal", "ml", "litros", "galones"
      - Time: "hrs", "hours", "horas", "dias", "days"
   c) Context inference from item descriptions:
      - If quantity is 1 and no unit specified → default to "unidades" (Spanish) or "units" (English)
      - If document is in Spanish and no unit → default to "unidades"
      - If document is in English and no unit → default to "units"
      - Look for units mentioned in descriptions (e.g., "2 kg", "5 lb", "10 unidades")
   d) Extract from mcomprobante_detalle context: If items have units mentioned in table columns or descriptions, extract the unit
   e) FLEXIBILITY: If you find ANY unit code that is NOT in the list above, STILL EXTRACT IT. Examples: "KT", "NIU", "MT2", "KGM", or any other unit code you see in the document
   f) If no unit found anywhere → use "unidades" (Spanish) or "units" (English) as default based on document language

7. mdepartamento (departments): Array of department names INFERRED from document context - CRITICAL FOR DASHBOARD ANALYTICS
   Example: [{"tDepartamento": "Engineering"}, {"tDepartamento": "Other Services"}]
   IMPORTANT: Departments do NOT appear explicitly in documents - you must INFER them from context using REASONING
   INFERENCE PATTERNS (use REASONING to determine department based on document content):
   a) Standard department names to assign (based on document analysis):
      **FOR OFFSHORE DOCUMENTS - CRITICAL: Use these EXACT department names:**
      - "Engineering": If document contains engineering-related items (design, technical specifications, engineering services, technical drawings, engineering equipment, civil engineering, structural engineering, architectural engineering, control systems, electrical engineering, mechanical engineering, pipeline engineering, tanks engineering, plant design, piping, materials engineering, engineering automation, engineering management, G&HES)
      - "Other Services": If document contains items that don't fit Engineering category (admin support, F&A, BEO, contracts, ES&H, field engineering, IS&T, procurement, project controls, project management, quality assurance, workforce services, constructability, off project support, tanks business line support)
      
      **FOR ONSHORE DOCUMENTS:**
      - "Engineering": If document contains engineering-related items (design, technical specifications, engineering services, technical drawings, engineering equipment)
      - "Procurement": If document contains procurement-related items (purchase orders, supplier contracts, material purchases, vendor invoices for materials)
      - "Construction": If document contains construction-related items (construction materials, construction services, building supplies, construction equipment)
      - "Project Management": If document contains project management items (project coordination, project services, management fees, project planning)
      - "Quality Control": If document contains QC/QA items (quality inspections, testing services, quality assurance, QC equipment)
      - "Health & Safety": If document contains safety items (safety equipment, safety services, PPE, safety training, H&S supplies)
      - "Environmental": If document contains environmental items (environmental services, environmental equipment, environmental compliance, environmental monitoring)
      - "Logistics": If document contains logistics items (transportation, shipping, logistics services, freight, delivery services)
      - "Other Services": If document contains items that don't fit other categories (general services, miscellaneous items)
   b) Context clues for inference:
      - Item descriptions: Analyze what the items/services are (e.g., "welding equipment" → Construction, "engineering software" → Engineering)
      - Supplier types: If supplier is an engineering firm → Engineering, if construction company → Construction
      - Project codes: Job numbers or project codes may indicate department (e.g., engineering projects → Engineering)
      - Document purpose: What is the document for? (e.g., purchase of construction materials → Construction)
   c) For mcomprobante_detalle items: Infer department for EACH item based on its description
      - Example: "Welding equipment" → Construction
      - Example: "Engineering software license" → Engineering
      - Example: "Safety helmets" → Health & Safety
   d) For mresumen items: Infer department based on expense type and description
      - Example: "Construction materials" → Construction
      - Example: "Engineering services" → Engineering
      - Example: "SQR" (Type of Activity code) → Could be Quality Control (SQR often means "Supplier Quality Review" or similar quality-related activity) or Engineering (if context suggests engineering review)
      - Example: "AEX" (Type of Activity code) → Could be Engineering or Operations (infer from context)
      - Look at Assignment No. patterns: Engineering projects often have specific codes (e.g., "26497-200-318358-PB03" might indicate project type)
      - Look at expense types: Transportation/Hotel for project work → Project Management or Operations
      - Look at country/location context: Different locations may indicate different departments (e.g., China-based expenses might be for specific project departments)
      - Look at document title: "Project Monthly Expense" suggests project-related work → Project Management or Operations
      - Example: "SQR" (Type of Activity) → Could be Quality Control or Engineering (infer from context)
      - Example: "AEX" (Type of Activity) → Could be Engineering or Operations (infer from context)
      - Look at Assignment No. patterns: Engineering projects often have specific codes
      - Look at expense types: Transportation/Hotel for project work → Project Management or Operations
      - Look at country/location context: Different locations may indicate different departments
   e) For mjornada: Usually Engineering or Operations based on employee roles and project allocations
   f) CRITICAL: Use REASONING to analyze item descriptions, supplier names, project context, and document purpose
   g) If you cannot determine with reasonable confidence → use "Other Services" or leave empty
   h) You can assign MULTIPLE departments if document contains items from different departments

8. mdisciplina (disciplines): Array of discipline names INFERRED from document context - CRITICAL FOR DASHBOARD ANALYTICS
   Example: [{"tDisciplina": "Civil/Structural/Architectural Engineering"}, {"tDisciplina": "Project Management"}]
   IMPORTANT: Disciplines do NOT appear explicitly in documents - you must INFER them from context using REASONING
   INFERENCE PATTERNS (similar to departments, but more granular):
   a) Standard discipline names to assign (based on document analysis):
      **FOR OFFSHORE DOCUMENTS - CRITICAL: Use these EXACT discipline names when inferring:**
      
      **Under "Engineering" department:**
      - "Civil/Structural/Architectural Engineering": Civil engineering, structural engineering, architectural engineering, structural design, building design, civil works
      - "Control Systems Engineering": Control systems, automation systems, SCADA, control engineering, instrumentation
      - "Electrical Engineering": Electrical engineering, electrical systems, power systems, electrical design
      - "Engineering Automation": Engineering automation, automated systems, automation engineering
      - "Engineering Management": Engineering management, project engineering management, engineering coordination
      - "G&HES": G&HES (may appear as code or abbreviation), geotechnical, health, environmental, safety engineering
      - "Materials Engineering Technology": Materials engineering, materials technology, material science, materials testing
      - "Mechanical Engineering": Mechanical engineering, mechanical systems, mechanical design, mechanical equipment
      - "Pipeline Engineering": Pipeline engineering, pipeline design, pipeline systems, pipeline construction
      - "Plant Design & Piping": Plant design, piping design, piping systems, plant layout, piping engineering
      - "Tanks Engineering": Tanks engineering, tank design, storage tanks, tank systems
      
      **Under "Other Services" department:**
      - "Admin Support/F&A": Administrative support, finance and accounting, F&A, admin services, financial administration
      - "BEO": BEO (may appear as code or abbreviation), business engineering operations
      - "Constructability": Constructability, construction support, construction engineering, constructability reviews
      - "Contracts": Contracts, contract management, contract administration, procurement contracts
      - "ES&H": ES&H (Environment, Safety & Health), environmental safety health, EHS, safety and environmental
      - "Field Engineering": Field engineering, field support, field services, on-site engineering
      - "IS&T": IS&T (Information Systems & Technology), IT services, information technology, systems and technology
      - "Off Project Support": Off project support, non-project support, general support services
      - "Procurement": Procurement, purchasing, supply chain, material acquisition, procurement services
      - "Project Controls": Project controls, project planning, scheduling, cost control, project management controls
      - "Project Management": Project management, project coordination, project oversight, project administration
      - "Quality Assurance": Quality assurance, QA, quality control, quality management, quality services
      - "Tanks Business Line Support": Tanks business line support, tanks support services, business line support
      - "Workforce Services": Workforce services, human resources, HR services, workforce management, staffing services
      
      **FOR ONSHORE DOCUMENTS:**
      - "Project Management": Project coordination, project planning, project oversight
      - "Quality Control": Quality inspections, testing, quality assurance activities
      - "Procurement": Purchasing activities, supplier management, material acquisition
      - "Construction": Construction activities, building, installation
      - "Logistics": Transportation, shipping, material handling, supply chain
      - "Engineering": Engineering design, technical analysis, engineering services
      - "Operations": Operational activities, plant operations, facility operations
      - "Maintenance": Maintenance services, equipment maintenance, facility maintenance
      - "Safety": Safety activities, safety compliance, safety training
      - "Environmental": Environmental compliance, environmental monitoring, environmental services
   b) Disciplines are more granular than departments - same inference logic but more specific
   c) For items: Infer discipline based on what the item/service actually does
   d) NC Codes mapping: If NC codes are present (611=Engineering, 612=Operations, etc.), use them to infer discipline
   e) CRITICAL: Use REASONING to analyze the actual purpose and nature of items/services in the document

9. tSequentialNumber: Sequential codes like BSQE1234, OE0001, OR0001, ORU1234
   EXTRACTION PATTERNS (check ALL):
   a) Stamp name patterns: Look for "BSQE", "OTEM", "OTRE", "OTRU" (case insensitive)
   b) Sequential number patterns:
      - Same line: "BSQE1234", "OE0001", "OR0001", "ORU1234" (stamp + 4+ digits on same line)
      - Separated lines: "OTEM\nOE0001" or "ORRE OR0001" (stamp on one line, code on next line within 200 chars)
      - Format: (BS|OE|OR|ORU) followed by 4+ digits
   c) Stamp to code mapping: OTEM → OE, OTRE → OR, OTRU → ORU, BSQE → BS
   d) If stamp name found but no code: Look for any 4+ digit number near stamp (within 200 chars), then construct code using mapping
   e) Priority: Extract sequential number if found anywhere in document header/top section

FOR "ticket", "factura_electronica", "comprobante", OR "nota_bill" TYPES - Extract:
**CRITICAL: If document contains MULTIPLE receipts/invoices (e.g., train ticket + multiple taxi receipts), extract EACH ONE as a separate entry in mcomprobante array.**
**For documents with multiple small receipts (like multiple taxi receipts on one page):**
- Extract EACH receipt as a separate mcomprobante entry
- Each receipt should have its own tNumero, dFecha, nPrecioTotal, etc.
- Look for patterns like: multiple "发票联" (Invoice Copy), multiple "车号" (Car No.), multiple dates, multiple amounts
- For Chinese taxi receipts: Each receipt has its own "车号" (Car No.), "日期" (Date), "金额" (Amount) - extract each as separate entry
- For train tickets + taxi receipts: Extract train ticket as one entry (type "ticket"), each taxi receipt as separate entries (type "comprobante")

{
  "mcomprobante": [{
    "tNumero": "invoice/boleta number - EXTRACT USING THESE PATTERNS (priority order):\n     1. Source Ref (GL Journal Details): 'Source Ref: 2336732507B0032' OR 'Source Ref: 2336732507B0032'\n     2. Oracle AP Invoice Num: 'Invoice Num F581-06891423' (format: FXXX-XXXXXXXX)\n     3. Invoice Number explicit: 'Invoice Number: 1234' OR 'Invoice No.: 18294'\n     4. BOLETA ELECTRÓNICA: 'BOLETA ELECTRÓNICA N° 0000155103' (Chilean format)\n     5. Chinese invoice number: '发票号码:25379166812000866769' (8+ digits) OR '发票代码:121082271141' (10+ digits)\n     6. N° format: 'N° 0000155103' (4+ digits after N°)\n     7. Folio: 'Folio No.: 18294' OR 'Folio: 18294'\n     8. Recibo: 'Recibo 221' (Spanish receipt format)\n     9. FATTURA NO.: 'FATTURA NO.: 333/25' (Italian format - can be same line or next line, format XXX/XX)\n     10. Generic Invoice: 'INVOICE No. XXXX', 'FATTURA N° XXX', 'CASH NO. XXX' (avoid 'Invoice Numb')\n     11. NO. near TOTAL: 'NO. 1234 TOTAL' (3+ digits near total keywords)\n     12. Chinese 号码: '号码' or '发票号码' or '发票代码' followed by 8+ digits\n     13. Generic with numbers: Any pattern with '总计', 'JUMLAH', 'No.', 'NO.', '#' followed by 4+ alphanumeric chars containing digits\n     IMPORTANT: Extract the FULL number/identifier, not partial. If multiple formats match, use highest priority.",
    "tSerie": "series number or Contract no. if present (e.g., 'Contract no 12345')" or null,
    "dFecha": "date in YYYY-MM-DD format - EXTRACT USING THESE PATTERNS:\n     - 'Date:' or 'Fecha:' or 'Tarikh:' followed by date\n     - Format 1: 'DD/MM/YYYY' or 'DD-MM-YYYY' (e.g., '28/05/2025', '28-05-2025')\n     - Format 2: 'May 28, 2025' or '28 May 2025'\n     - Format 3: '28-May-2025' or '30-JUN-2025'\n     - Format 4: 'JUL 23, 2025'\n     IMPORTANT VALIDATION: Do NOT extract phone numbers as dates:\n     - Avoid '1300-80-8989' (phone number)\n     - Numbers with >8 digits when removing separators are likely NOT dates\n     - If pattern looks like date but has >8 digits total, it's probably a phone number\n     - Validate: date should have max 8 digits (2+2+4) or reasonable month/day values",
    "fEmision": "emission date in YYYY-MM-DD format (same as dFecha if not separately specified)" or null,
    "nPrecioTotal": number or string (total amount in USD - EXTRACT USING REASONING AND THESE PATTERNS in priority order):
     **CRITICAL: This field MUST be in USD. If document has values in a currency other than USD and NO USD values, convert to USD using the exchange rates provided below.**
     **FORMAT RULES FOR MONETARY VALUES (MANDATORY):**
     - **MANDATORY**: For values >= 1000, you MUST format with thousands separators (commas) as STRING: "35,800.00", "258,000.00", "1,234.56", "5,693.07"
     - **MANDATORY**: For values < 1000, can be number or string: 500.00 or "500.00"
     - **CRITICAL EXAMPLES** (follow exactly):
       * 35800 → MUST return "35,800.00" (as string)
       * 258000 → MUST return "258,000.00" (as string)
       * 5693.07 → MUST return "5,693.07" (as string)
       * 1234.56 → MUST return "1,234.56" (as string)
       * 1000 → MUST return "1,000.00" (as string)
       * 500.00 → Can return 500.00 (number) or "500.00" (string)
     - **PROCESS**: When you extract a monetary value >= 1000, format it with commas before returning it
     - If document already shows formatted values (e.g., "35,800.00"), preserve that format as string
     - If document shows unformatted values (e.g., "35800" or "5693.07"), format them with commas: "35,800.00" or "5,693.07"
     - **DO NOT** return numbers >= 1000 without commas - always format as strings with commas
     """ + currency_conversion_section + """
     **CRITICAL: Use your reasoning ability to identify the CORRECT total by analyzing the document context, relationships between values, and visual emphasis.**
     1. HANDWRITTEN USD VALUES (HIGHEST PRIORITY - USE REASONING):
        - If you see ANY handwritten/manually written text containing "USD" followed by a number (e.g., "USD 5.00", "USD425", "USD 4/25" written by hand), use that amount as nPrecioTotal
        - Handwritten values often appear as corrections, annotations, or final validations
        - Look for text that appears different in style, position, or format - these are likely handwritten
        - Examples: "USD 5.55" written near a printed "RM22.80", "USD425" at bottom of receipt, "USD4/25" as annotation
        - **REASONING**: If you see both printed RM/MYR and handwritten USD, the handwritten USD is the authoritative total
        - **IMPORTANT**: Handwritten USD values override ANY printed values, even if printed totals are present
     2. HANDWRITTEN VALUES WITHOUT CURRENCY (HIGH PRIORITY):
        - If you see handwritten numbers that appear to be totals (often near printed totals, in boxes, or highlighted), analyze the context
        - If handwritten value is USD amount and printed is RM/MYR, prioritize handwritten USD
        - Use reasoning: handwritten totals are usually final validations or conversions
     3. Highlighted/Boxed values (PRIORITY - USE REASONING):
        - Values in red boxes, yellow highlights, bordered sections, or visually emphasized areas are CRITICAL
        - Extract values INSIDE colored boxes or highlighted areas - these are often final totals
        - Examples: 'TOTAL AMOUNT IN US$ ... $ 120.60' in red box, totals in highlighted rectangles
        - **REASONING**: Visually emphasized values indicate importance - prioritize these over regular text
     4. Printed Totals (USE REASONING TO IDENTIFY CORRECT ONE):
        - Look for "Total", "TOTAL", "Total Amount", "总计", "JUMLAH", "Grand Total", "Amount Due" followed by currency and number
        - **REASONING**: If multiple totals appear (subtotal, tax, final total), use the FINAL total after all calculations
        - For Italian invoices: If 'TOTAL' appears on one line with '$ XXX.XX' values below, extract the LAST value (final total after stamp duty)
        - Example: 'TOTAL\n$\n120.60\n$\n2.34\n$\n122.94' → extract 122.94 (the LAST value after stamp duty of 2.34)
     5. Oracle AP: 'Invoice Amount USD 655740.75' or 'Invoice Invoice Amount USD 655740.75' or 'Invoice Amount 655740.75'
     6. Chinese/Malay totals: '总计' or 'JUMLAH RM' followed by number (e.g., '总计 RM 17.50' or '总计 1,234.56 元')
     7. Calculation-based totals: If you see calculations like "USD 4,301.00 + USD 616.00 = USD 6,369.00", use the final sum (6,369.00)
     8. **REASONING FALLBACK**: If no explicit total found, analyze the document structure:
        - Look for patterns: printed totals usually appear after item lists, at bottom of tables, or near payment information
        - If document has line items in mcomprobante_detalle, sum them as fallback
        - Consider relationships: if there's a "Cash" payment matching a total, that's likely the correct total
     9. OCR corrections: Fix spaces as decimals (32 40 → 32.40), hyphens as decimals (25-20 → 25.20)
     **REMEMBER**: Use reasoning to relate information across the document - handwritten values near totals, highlighted boxes, and relationships between printed amounts all provide context for the CORRECT total.
    "nPrecioTotalOriginal": number or string or null (original total amount in the original currency if conversion was performed - format with thousands separators if >= 1000, e.g., "220,000.00" for CLP, "5,000.00" for MXN - only include if conversion was performed),
    "tMonedaOriginal": "currency code of the original amount (CLP, MXN, MYR, PEN, etc.) - only include if conversion was performed, null if document was already in USD)",
    "precioTotal": number or string (sum of ALL nPrecioTotal values from mcomprobante_detalle array for this comprobante - calculate by adding all nPrecioTotal from items - **MANDATORY: If value >= 1000, MUST format as string with thousands separators: "35,800.00", "258,000.00", "5,693.07", etc. Examples: 5693.07 → "5,693.07", 1000 → "1,000.00"**),
    "tCliente": "client name from 'Attn.:' or 'Attn' field - **If in Chinese, translate to English**" or null,
    "tStampname": "Extract stamp name ONLY if you find one of these EXACT codes: 'BSQE', 'OTEM', 'OTRE', 'OTRU', 'OTHBP' (case insensitive). These are specific stamp identifiers, NOT company names or supplier names. If you see 'RV TRANSPORTES LTDA.' or any other company name, that is NOT a stamp name - use null instead. Stamp names are usually short codes (4-5 characters) that appear in document headers or near sequential numbers." or null,
    "tsequentialnumber": "Extract sequential number using patterns: 'BSQE1234', 'OE0001', 'OR0001', 'ORU1234' OR separated format 'OTEM\\nOE0001' (stamp on one line, code on next within 200 chars). Format: (BS|OE|OR|ORU) followed by 4+ digits. If stamp found but no code, look for 4+ digit number near stamp and construct using mapping: OTEM→OE, OTRE→OR, OTRU→ORU, BSQE→BS" or null,
    // For Oracle AP invoices, also extract:
    "tInvoiceAmount": "Invoice Amount" or null,
    "tTaxAmount": "Tax Amount" or null,
    "tDueDate": "Due Date in YYYY-MM-DD" or null,
    "tGrossAmount": "Gross Amount" or null,
    "tPaymentCurrency": "Payment Currency code" or null,
    "tPaymentMethod": "Payment Method (Wire, Check, etc.)" or null,
    "tSupplierNum": "Supplier Num" or null,
    "tOperatingUnit": "Operating Unit" or null,
    "tSupplierSite": "Supplier Site" or null,
    "tInvoiceDate": "Invoice Date in YYYY-MM-DD" or null
  }],
  "mcomprobante_detalle": [{
    "nCantidad": number,
    "tUnidad": "unit of measure (e.g., 'kg', 'lb', 'unidades', 'units', 'EACH', 'KT', 'MT2', 'KGM', 'NIU') - Extract from 'Unit'/'U.M.'/'UOM' column in table OR infer from context. If not found, use 'unidades' (Spanish) or 'units' (English) as default. BE FLEXIBLE - extract ANY unit code you find, even if not in standard list.",
    "tDescripcion": "item description - Extract EXACTLY what the document shows in the Description/Particulars/摘要 column of the table. Examples: 'ICE VANILLA LATT', 'ADD ESP SHT', 'Toll', 'Hotel', 'Meal', 'Room Charge', etc. Look at the ACTUAL table row - if it says 'ICE VANILLA LATT' in the description column, extract 'ICE VANILLA LATT'. If it says 'Toll', extract 'Toll'. DO NOT extract JSON field names like '\"ocr_text\"', '\"nImporte\"', '\"nPrecioTotal\"', '\"_myr_amount\"' - these are WRONG. Only extract what is actually visible in the document table. For empty receipts with no items filled, do NOT create items. **CRITICAL: If the description is in Chinese (中文), automatically translate it to English. Examples: '住宿服务*住宿费' → 'Accommodation service*Accommodation fee', '出租汽车公司' → 'Taxi company', '里程' → 'Mileage', '金额' → 'Amount', '合计' → 'Total'. Always translate Chinese text to English while preserving the structure and meaning.**",
    "nPrecioUnitario": number or string (unit price - **MANDATORY: If value >= 1000, MUST format as string with thousands separators: "35,800.00", "258,000.00", "5,693.07", etc. Examples: 5693.07 → "5,693.07", 1000 → "1,000.00", 500.00 → 500.00 or "500.00"**),
    "nPrecioTotal": number or string (total amount in USD for this item - **MANDATORY: If value >= 1000, MUST format as string with thousands separators: "35,800.00", "258,000.00", "5,693.07", etc. Examples: 5693.07 → "5,693.07", 1000 → "1,000.00", 500.00 → 500.00 or "500.00"** - if document has values in a currency other than USD and NO USD values, convert to USD using the exchange rates provided in the conversion rules),
    "nPrecioTotalOriginal": number or string or null (original total amount in the original currency for this item if conversion was performed - format with thousands separators if >= 1000, e.g., "110,000.00" for CLP - only include if conversion was performed),
    "tMonedaOriginal": "currency code of the original amount for this item (CLP, MXN, MYR, PEN, etc.) - only include if conversion was performed, null if item was already in USD)"
  }],
  // EXTRACTION RULES FOR mcomprobante_detalle:
  // CRITICAL: tDescripcion must be EXACTLY what the document shows, NOT JSON field names
  // 1. For receipts/coffee shop: Extract item names from table (e.g., "ICE VANILLA LATT", "ADD ESP SHT") exactly as shown in the Description/Item column
  // 2. For "ATTACHMENT TO INVOICE": Extract ALL table rows - THIS IS CRITICAL AND MANDATORY!
  //    Table structure: Resource | Vendor | Assignment no. | Report Number | Request | Type of Activity | Date of visit | hrs | hrly rate | km/miles | mileage rate | Expenses | Total Labor | Total Expenses | Total Amount
  //    Example rows to extract:
  //      Row 1: "Martin Loges | Duchting Pumpen, Witten, Germany | 26443-220-YZA-MPVE-1C001 | 26443-220-YQA-MPVE-1C001 | 29018 | Inspection | 11-Jun-25 | 12 | (empty) | 90 | $ 0.67 | $ - | $ - | $ 60.30 | $ 60.30"
  //      Row 2: "Martin Loges | Duchting Pumpen, Witten, Germany | 26443-220-YZA-MPVE-1C001 | 26443-220-YQA-MPVE-1C002 | 29018 | Inspection | 30-Jun-25 | 10 | (empty) | 90 | $ 0.67 | $ - | $ - | $ 60.30 | $ 60.30"
  //      Total Row: "TOTAL AMOUNT IN US$ | 22 | 180 | $ - | $ - | $ 120.60 | $ 120.60" (this is in a red box/highlighted)
  //    Extraction rules:
  //      - tDescripcion: Format as "Resource Name - Vendor Name - Type of Activity" (e.g., "Martin Loges - Duchting Pumpen, Witten, Germany - Inspection")
  //        For total row: Use "TOTAL AMOUNT IN US$" exactly as shown
  //      - nCantidad: Extract from "hrs" column (e.g., 12, 10) OR from "km/miles" column if hours is empty (e.g., 90)
  //        For total row: Extract from "hrs" column (e.g., 22) OR from "km/miles" column (e.g., 180)
  //      - nPrecioUnitario: Extract from "hrly rate" column OR "mileage rate" column (e.g., 0.67). If both empty, use 1.0
  //        For total row: Can be null or use mileage rate if available
  //      - nPrecioTotal: Extract from "Total Amount" column (e.g., 60.30 for individual rows, 120.60 for total row) - THIS IS MANDATORY
  //        For total row: PRIORITIZE value from red box/highlighted area (e.g., 120.60)
  //    IMPORTANT: 
  //      - Extract EACH data row from the table (e.g., both Martin Loges rows)
  //      - Extract the "TOTAL AMOUNT IN US$" row at the bottom as a SEPARATE entry in mcomprobante_detalle
  //      - DO NOT skip any rows - extract ALL rows from the table, including the total row
  //      - If you see section headers like "GERMANY" before rows, still extract all rows under that section
  //      - The total row is CRITICAL - it shows the final amount in a red box/highlighted area
  // 3. For "Invoice Approval Report": Do NOT extract "Line Item Details" as items (those are data columns like Line Amount, Nat Class, Job, Sub Job, Cost Code - NOT purchase items)
  // 4. Do NOT extract "Invoice Group Detail" section as items (skip lines matching pattern like "BSQEUSD 751671 33025")
  // 5. For GL Journal Details WITHOUT highlighted calculations: Extract all table rows as items, use ONLY nPrecioUnitario (Entered Debits in USD), do NOT include nPrecioTotal
  // 6. For GL Journal Details WITH highlighted calculations: Extract ONLY highlighted values (see SPECIAL PRIORITIES #4)
  // 7. For Labor details (BSQE SERVICE CHARGES): Extract rows with pattern "Emp Name ... Hours <h> Hrly Rate <r> ... Amount <a>"
  //    - nCantidad = hours, nPrecioUnitario = rate, nPrecioTotal = amount, tDescripcion = "Employee Name INSPECTING"
  // 8. For Spanish table format: "1 7 de julio 2025 90,000 90,000" → cantidad, descripción, precio unitario, importe
  // 9. For empty receipts/forms: If a receipt has table headers but NO items filled in (only row numbers 1-10), do NOT create items - only extract items that actually have values filled in
  // 10. OCR corrections: Fix spaces as decimals (32 40 → 32.40), hyphens as decimals (25-20 → 25.20)
  // 11. For Italian invoices: Extract items if present in table format
  // 12. DO NOT extract table headers, column names, or empty rows as items
}

FOR "resumen" TYPE - Extract:
{
  "mresumen": [{
    "tjobno": "job number - EXTRACT USING PATTERNS:\n     - 'BECHTEL JOBS NO.: 26443' → extract '26443' or full job code\n     - Format: '26442-OFFSHORE', '26443-331-----', '26443-331'\n     - Look for pattern: digits followed by dash and alphanumeric (e.g., '26442-OFFSHORE')\n     - Can appear in table rows or header",
    "ttype": "Extract type from patterns: 'Supplier Quality', 'Other Reimbursables', 'Week XX Total', 'Cash Flow - XXX', 'Toll', 'Hotel', 'Meal', 'Expense Summary', or null if not found",
    "tsourcereference": "source reference code - EXTRACT USING PATTERNS:\n     - Alphanumeric codes 10+ characters (e.g., 'Yanacocha AWTP Onshore', alphanumeric strings in table rows)\n     - Project names from headers (e.g., 'Project: Yanacocha AWTP Onshore')\n     - Look for patterns: [A-Z0-9]{10,} (alphanumeric codes)\n     - Often appears in table rows as first column or near job numbers",
    "tsourcerefid": "source ref ID - EXTRACT USING PATTERNS:\n     - Week numbers: 'Week 1', 'Week 2', etc.\n     - Item numbers from tables: 'Item No. 1', 'Item No. 2'\n     - Source reference IDs: alphanumeric strings (5+ chars) following source reference\n     - Often appears after source reference code in table rows" or null,
    "tdescription": "description - CLEAN, PROFESSIONAL text extracted from the document. Examples: 'Toll', 'Hotel', 'Meal', 'Expense Summary', 'Grand Total USD', 'TOTAL EXPENSES', etc. Extract ONLY the meaningful description from the document row or table, NOT the raw OCR text, NOT JSON fields (like '\"ocr_text\"', '\"nImporte\"', '\"_myr_amount\"'), NOT technical metadata. If the table shows 'Description: Toll', extract 'Toll'. If it shows 'Description: Meal', extract 'Meal'. For totals, extract 'Grand Total USD' or 'TOTAL EXPENSES'. Keep it simple and clean.",
    "nImporte": number or string (USD amount - **MANDATORY: If value >= 1000, MUST format as string with thousands separators: "35,800.00", "258,000.00", "5,693.07", etc. Examples: 5693.07 → "5,693.07", 1000 → "1,000.00", 500.00 → 500.00 or "500.00"** - prioritize USD column values, use USD not MYR for nImporte),
    "tStampname": "BSQE|OTEM|OTRE|OTRU" or null,
    "tsequentialnumber": "sequential code" or null
  }],
  // IMPORTANT: For expense summary documents with multiple tables (like Bechtel expense summaries):
  // Extract EACH row from EACH table as a separate mresumen entry
  // Example: If you see 3 tables, extract ALL rows from table 1, then ALL rows from table 2, then ALL rows from table 3
  // Each row should have: tdescription (Toll/Hotel/Meal), nImporte (USD amount), tjobno (job number from header), etc.
    // "Grand Total USD" values should also be extracted as separate mresumen entries
  
  // Weekly totals: lines with ONLY numbers (no item descriptions) containing 2+ large monetary values
  // These appear at the end of tables and represent totals by week
  "weekly_totals": [{
    "tjobno": null,
    "ttype": "Week XX Total",
    "tsourcereference": null,
    "tsourcerefid": "Week XX",
    "tdescription": "Total Week XX",
    "nImporte": number or string (FORMAT WITH THOUSANDS SEPARATORS if >= 1000: "35,800.00", "258,000.00", etc.),
    "tStampname": null,
    "tsequentialnumber": null
  }] or [],
  // Cash Flow values: extract ALL cash flow related values
  "cash_flow": [{
    "tjobno": null,
    "ttype": "Cash Flow - Total Disbursement|Period Balance|Cumulative Cash Flow|Opening Balance|Total Receipts",
    "tsourcereference": null,
    "tsourcerefid": "Week XX" if applicable,
    "tdescription": "Cash Flow description with amount",
    "nImporte": number or string (NEGATIVE if in parentheses like (305,350), POSITIVE otherwise - FORMAT WITH THOUSANDS SEPARATORS if >= 1000: "35,800.00", "258,000.00", etc.),
    "tStampname": null,
    "tsequentialnumber": null
  }] or []
}

FOR "expense_report" TYPE - Extract:
{
  "mcomprobante": [{
    "tNumero": "Report Number (e.g., '0ON74Y', '26497-200-318358-PB03-YQ-A-014')",
    "dFecha": "Report Date in YYYY-MM-DD (convert from 'Jul 23, 2025' format, or extract from 'Month: Jun-25' → '2025-06-01')",
    "nPrecioTotal": number or string (Report Total amount - FORMAT WITH THOUSANDS SEPARATORS if >= 1000: "35,800.00", "258,000.00", etc. - PRIORITY if in red box/highlighted, or sum of all expenses),
    "tEmployeeID": "Employee ID (e.g., '063573')" or null,
    "tEmployeeName": "Employee Name (e.g., 'AYALA SEHLKE, ANA MARIA', 'Michael-x Xu')" or null,
    "tOrgCode": "Org Code (e.g., 'HXH0009')" or null,
    "tReportPurpose": "Report Purpose (e.g., 'Viaje a turno')" or null,
    "tReportName": "Report Name (e.g., 'Project Monthly Expense')" or null,
    "tDefaultApprover": "Default Approver" or null,
    "tFinalApprover": "Final Approver" or null,
    "tPolicy": "Policy (e.g., 'Assignment Long Term')" or null,
    "tBechtelOwesEmployee": number (Bechtel owes Employee amount) or null,
    "tBechtelOwesCard": number (Bechtel owes Card amount) or null,
    "tReportKey": "Report Key" or null,
    "tDocumentIdentifier": "BECHEXPRPT_{EmployeeID}_{ReportNumber}" or null,
    "tStampname": "BSQE|OTEM|OTRE|OTRU|OTHBP" or null,
    "tsequentialnumber": "sequential code (e.g., 'BS0004')" or null
  }],
  "mresumen": [{
    // CRITICAL: Extract EACH ROW from expense report tables as a separate mresumen entry
    // For "Project Monthly Expense" type reports with table structure:
    // Extract ALL data rows (not header rows, not empty rows)
    // Each row should have: Assignment No., Charge No., Report No., Country, Type of Activity, Type, Transportation Amount, Hotel Amount, Total Amount
    "tjobno": "Assignment No. (e.g., '26497-200-318358-PB03-YZ-A') - Extract from 'Assignment No.' column",
    "ttype": "Type of Activity (e.g., 'SQR', 'AEX') - Extract from 'Type of Activity' column, or 'Expense Report' if not available",
    "tsourcereference": "Report No. (e.g., '26497-200-318358-PB03-YQ-A-014') - Extract from 'Report No.' column",
    "tsourcerefid": "Charge No. (e.g., '26497-130') - Extract from 'Charge No.' column, or Report Key if available",
    "tdescription": "Description combining Type of Activity + Type (e.g., 'SQR Train+Taxi', 'SQR Taxi') - Extract from 'Type of Activity' and 'Type' columns. Include country if relevant (e.g., 'SQR Train+Taxi - China')",
    "nImporte": number (Total amount in USD - Extract from 'Total (USD)' column, prioritize USD over other currencies),
    "tStampname": "stamp name (e.g., 'BSQE')" or null,
    "tsequentialnumber": "sequential number (e.g., 'BS0004')" or null
  }],
  // IMPORTANT: For expense report tables, extract EVERY data row as a separate mresumen entry
  // Do NOT skip rows - extract ALL rows that contain data (Assignment No., Charge No., Report No., amounts, etc.)
    // Include the "Total" row at the bottom as a separate mresumen entry
  // For each row, extract ALL available fields (Assignment No., Charge No., Report No., Country, Type of Activity, Type, amounts, etc.)
  
  // For OnShore documents (deprecated - use mdepartamento and mdisciplina instead):
  "departments": [{
    "name": "Engineering|Operations|Maintenance|Safety|Environmental|Human Resources|Finance|IT Services|Other Services",
    "amount": number (if associated with monetary value) or null,
    "pattern_found": "pattern that matched" or null,
    "org_code": "organization code if mapped" or null
  }] or [],
  "disciplines": [{
    "name": "Engineering|Operations|Maintenance|Safety|Environmental|Project Management|Quality Control|Procurement|Construction|Logistics",
    "value": number (if associated with value) or null,
    "pattern_found": "pattern that matched" or null,
    "nc_code": "NC Code if mapped (e.g., 611=Engineering, 612=Operations)" or null
  }] or []
}

FOR "concur_expense" TYPE - Extract:
{
  "mcomprobante": [{
    "tNumero": "Report identifier or sequential number",
    "dFecha": "Transaction Date in YYYY-MM-DD (convert from 'Jun 23, 2025' format)",
    "nPrecioTotal": number (Report Total - MOST IMPORTANT),
    "tJobSection": "Line Item by Job Section code (e.g., '26443-331-----')",
    "tExpenseType": "Expense Type (e.g., 'Leave (Any) Taxi/Ground Trans - LT')",
    "tMerchant": "Merchant name (e.g., 'RV Transportes Ltda.')",
    "tLocation": "Location (e.g., 'Quilpué', 'Santiago')",
    "tNCCode": "NC Code (e.g., '611')",
    "tReportName": "Concur Expense - [Name]" or null,
    "tPaymentCurrency": "Payment Currency (CLP, USD, etc.)" or null,
    "tStampname": "stamp name" or null,
    "tsequentialnumber": "sequential number" or null
  }],
  "mresumen": [{
    // Extract ALL totals from Concur Expense Reports:
    // - Report Total (MOST IMPORTANT)
    // - Subtotal
    // - Total for XXX (e.g., "Total for 611: 180,000.00")
    // - Amount Less Tax
    // - Tax (even if 0)
    "tjobno": "Job Section code",
    "ttype": "Concur Expense - Report Total|Subtotal|Total for XXX|Amount Less Tax|Tax",
    "tsourcereference": "sequential number",
    "tsourcerefid": null,
    "tdescription": "Total description",
    "nImporte": number,
    "tStampname": "stamp name" or null,
    "tsequentialnumber": "sequential number" or null
  }],
  "mcomprobante_detalle": [{
    "nCantidad": 1 (default),
    "tUnidad": "unit of measure (e.g., 'kg', 'lb', 'unidades', 'units', 'EACH', 'KT', 'MT2', 'KGM', 'NIU') - Extract from 'Unit'/'U.M.'/'UOM' column in table OR infer from context. If not found, use 'unidades' (Spanish) or 'units' (English) as default. BE FLEXIBLE - extract ANY unit code you find, even if not in standard list.",
    "tDescripcion": "expense description with merchant and location - **CRITICAL: If the description is in Chinese (中文), automatically translate it to English. Examples: '住宿服务*住宿费' → 'Accommodation service*Accommodation fee', '出租汽车公司' → 'Taxi company'. Always translate Chinese text to English while preserving the structure and meaning.**",
    "nPrecioUnitario": number,
    "nPrecioTotal": number,
    "tTransactionDate": "Transaction Date in YYYY-MM-DD" or null,
    "tExpenseType": "Expense Type" or null,
    "tMerchant": "Merchant name" or null,
    "tLocation": "Location" or null,
    "tNCCode": "NC Code" or null
  }]
}

FOR "jornada" TYPE - Extract:
{
  "mjornada": [{
    // General jornada information
    "dFecha": "date in YYYY-MM-DD (convert from Period date like 'Jul 2025' → use first day of month, e.g., '2025-07-01')",
    "fRegistro": "Period (e.g., 'JUL 2025', 'Jul 2025', extract from 'Period Jul 2025')",
    "nTotalHoras": number (total hours for entire document - extract from 'Total Hrs: 651.50' or sum of all employee hours),
    "tEmpleado": null (employee names go in mjornada_empleado, not here),
    "tEmpleadoID": null,
    "nHoras": null,
    "nTarifa": number (extract Plan OH/hr rate, e.g., 22.00 if 'Plan OH/hr $ 22.00' is shown),
    "nTotal": number (total amount for entire document - extract from 'Total Amt: $14,333.00' or sum of all section totals)
  }],
  "mjornada_empleado": [{
    // CRITICAL: Extract EACH employee row from the table as a separate entry
    // Look for table with columns: Empl No, Full Name, Labor PPE (orig), Curr, Org Code, Total Hours, and project allocation columns
    // Example row: "168474 Saavedra Oportus, Hector Alejandro 30-Jun-2025 CLP 8NJ2100 4.75" with project allocations
    "tNumero": "employee number - extract from 'Empl No' column (e.g., '168474', '174618', '069033', '081383')",
    "tNombre": "employee full name - extract from 'Full Name' column (e.g., 'Saavedra Oportus, Hector Alejandro', 'Vera Diaz, Boris Haendel', 'Tovar Arredondo, Jose Carlos') - EXACTLY as shown in document",
    "tOrganizacion": "organization code - extract from 'Org Code' column (e.g., '8NJ2100', '8NJ2500')",
    "dFecha": "date in YYYY-MM-DD - extract from 'Labor PPE (orig)' column (e.g., '30-Jun-2025' → '2025-06-30', '31-Jul-2025' → '2025-07-31')",
    "nHoras": number (total hours for this employee/date - extract from 'Total Hours' column, e.g., 4.75, 47.50, 176.00),
    "nTarifa": number (hourly rate - extract from 'Plan OH/hr' if shown for this employee/section, or use document-wide rate, e.g., 22.00),
    "nTotal": number (total cost for this employee/date = nHoras * nTarifa, e.g., 4.75 * 22.00 = 104.50)
    // NOTE: If employee has multiple rows (same employee, different dates), create separate mjornada_empleado entries for each date
    // Example: If "168474 Saavedra Oportus" appears twice with dates 30-Jun-2025 (4.75 hrs) and 31-Jul-2025 (47.50 hrs), create 2 entries
  }],
  // IMPORTANT: For jornada documents, ALSO extract cost breakdowns by project/section as mresumen entries
  "mresumen": [{
    // Extract cost summaries by section/company and by project
    // CRITICAL: Extract ALL cost breakdowns from the document:
    // 1. Section totals: "V52T Bechtel Chile: Total $ 6,589.00" → one mresumen entry with tjobno: "V52T Bechtel Chile", nImporte: 6589.00
    // 2. Section totals: "XYQN Bechtel Peru: Total $ 7,744.00" → another mresumen entry with tjobno: "XYQN Bechtel Peru", nImporte: 7744.00
    // 3. Project costs: "26442-007: $ 4,301.00" → one mresumen entry with tjobno: "26442-007", nImporte: 4301.00
    // 4. Project costs: "26442-223: $ 2,068.00" → one mresumen entry with tjobno: "26442-223", nImporte: 2068.00
    // 5. Project costs: "26443-353: $ 7,744.00" → one mresumen entry with tjobno: "26443-353", nImporte: 7744.00
    // 6. Project costs: "26775-138: $ 220.00" → one mresumen entry with tjobno: "26775-138", nImporte: 220.00
    // 7. Overall total: "Total Amt: $14,333.00" → one mresumen entry with tdescription: "Overall Total", nImporte: 14333.00
    // 8. Total hours: "Total Hrs: 651.50" → can be stored as additional info
    "tjobno": "project/cost center code (e.g., '26442-007', '26442-223', '26443-353', '26775-138') or section name (e.g., 'V52T Bechtel Chile', 'XYQN Bechtel Peru') or null for overall totals",
    "ttype": "Jornada Cost Summary|Project Cost|Section Total|Overall Total" or null,
    "tsourcereference": "section/company name (e.g., 'V52T Bechtel Chile', 'XYQN Bechtel Peru')" or null,
    "tsourcerefid": "project/cost center code (e.g., '26442-007', '26442-223', '26443-353', '26775-138')" or null,
    "tdescription": "description of cost - extract from document (e.g., 'V52T Bechtel Chile Total', '26442-007 Cost', '26442-223 Cost', '26443-353 Cost', '26775-138 Cost', 'Overall Total', 'Total Amt')",
    "nImporte": number (cost amount - extract from cost breakdowns shown in document, e.g., 6589.00 for V52T section, 7744.00 for XYQN section, 4301.00 for 26442-007 project, 2068.00 for 26442-223 project, 220.00 for 26775-138 project, 14333.00 for overall total) - REQUIRED field,
    "tStampname": "extract stamp name if present (e.g., 'BSQE' from 'BSQE BS0001')" or null,
    "tsequentialnumber": "extract sequential number if present (e.g., 'BS0001' from 'BSQE BS0001')" or null
  }],
  // EXTRACTION RULES FOR jornada TYPE:
  // 1. Extract Period from "Period Jul 2025" → fRegistro: "JUL 2025"
  // 2. Extract Total Hours from "Total Hrs: 651.50" → nTotalHoras: 651.50
  // 3. Extract Total Amount from "Total Amt: $14,333.00" → nTotal: 14333.00
  // 4. Extract Plan OH/hr rate from "Plan OH/hr $ 22.00" → nTarifa: 22.00 (for all employees if uniform)
  // 5. Extract EACH employee row from table:
  //    - Look for employee number (6 digits) at start of row
  //    - Extract full name (usually "Lastname, Firstname" format)
  //    - Extract date from "Labor PPE (orig)" column (format: "30-Jun-2025")
  //    - Extract currency from "Curr" column (CLP, PEN)
  //    - Extract org code from "Org Code" column (8NJ2100, 8NJ2500)
  //    - Extract total hours from "Total Hours" column
  //    - Extract hours allocated to each project from project columns (26442-007, 26442-223, etc.)
  //    - Calculate total cost = total hours * Plan OH/hr rate
  // 6. If same employee appears multiple times with different dates, create separate entries for each date
  // 7. Extract cost breakdowns:
  //    - Extract totals by section: "V52T Bechtel Chile: Total $ 6,589.00"
  //    - Extract totals by project: "26442-007: $ 4,301.00", "26442-223: $ 2,068.00", etc.
  //    - Extract overall total: "Total Amt: $14,333.00"
  // 8. Store cost breakdowns in mresumen array (one entry per project/section/total)
}

FOR ALL DOCUMENT TYPES - Extract mmaquinaria_equipos (machinery/equipment/vehicles) if present:
**CRITICAL: For taxi receipts and transportation receipts, ALSO extract them in mmaquinaria_equipos as "Vehículo" type:**
- Chinese taxi receipts (发票联 with 车号): Extract vehicle information (车号/Car No., 证号/Certificate No., dates, times, mileage, amounts)
- Each taxi receipt should be a separate entry in mmaquinaria_equipos
- Extract: tTipo: "Vehículo", tPlaca: Car No. (车号), dFecha: Date (日期), nValorMonetario: Amount (金额), tMoneda: Currency (usually CNY for Chinese receipts)
- Also extract: boarding time (上车), alighting time (下车), mileage (里程), waiting time (等候), unit price (单价)

{
  "mmaquinaria_equipos": [{
    // CRITICAL: PRIORITIZE MONETARY VALUES - Extract ALL monetary values related to machinery/equipment/vehicles
    // This table is used for validation between summaries and individual records, so monetary values are ESSENTIAL
    
    // Fields principales (prioritarios - especialmente valores monetarios)
    "tTipo": "Vehículo|Equipo|Maquinaria|Herramienta|Orden de Compra|Guía de Remisión|Taxi Receipt" or null,
    "tDescripcion": "Complete description of the item/equipment/machinery/vehicle - extract from document - **CRITICAL: If the description is in Chinese (中文), automatically translate it to English. Examples: '住宿服务*住宿费' → 'Accommodation service*Accommodation fee', '出租汽车公司' → 'Taxi company'. Always translate Chinese text to English while preserving the structure and meaning.**",
    "nValorMonetario": number, // PRIORITY: Price, cost, value, total amount - EXTRACT IF PRESENT (REQUIRED for validation)
    "tMoneda": "USD|PEN|EUR|CLP|MYR" or null, // Currency of the monetary value
    
    // Información de vehículos (si aplica)
    "tMarca": "Vehicle brand (e.g., 'NISSAN', 'TOYOTA')" or null,
    "tPlaca": "License plate (e.g., 'C1J-905')" or null,
    "tTUCE": "TUCE number" or null,
    "tConductor": "Driver name (e.g., 'SEGUNDO KELVIN JULON VASQUEZ')" or null,
    "tNumeroDocumento": "Driver document number (e.g., 'D.N.I.-47799028')" or null,
    "tNumeroLicencia": "Driver license number (e.g., '847799028')" or null,
    
    // Información de equipos/maquinaria (si aplica)
    "tModelo": "Model number or name" or null,
    "tSerial": "Serial number" or null,
    "tNumeroOrden": "Order number (e.g., '548125', '543403', '557177')" or null,
    "tCodigoItem": "Item code (e.g., 'FPOUSSC000000391', 'KITS000171')" or null,
    "nCantidad": number or null, // Quantity of items
    "tUnidadMedida": "Unit of measure (e.g., 'EACH', 'KT', 'MT2', 'KGM', 'NIU')" or null,
    "nPrecioUnitario": number or null, // Unit price if available
    "nPrecioTotal": number or null, // Total price if available (PRIORITY if present)
    
    // Información de órdenes de compra (si aplica)
    "tProveedor": "Supplier name" or null,
    "tRUC": "RUC or tax ID" or null,
    "dFecha": "Date in YYYY-MM-DD format" or null,
    "dFechaEmision": "Emission date in YYYY-MM-DD" or null,
    "dFechaInicioTraslado": "Transport start date in YYYY-MM-DD" or null,
    "tPuntoPartida": "Origin point" or null,
    "tPuntoLlegada": "Destination point" or null,
    "tModalidadTraslado": "Transport modality (e.g., 'PUBLICO')" or null,
    "tPesoBrutoTotal": "Gross weight (e.g., 'KGM 2639')" or null,
    
    // Información adicional (flexible - extraer cualquier campo que encuentre)
    "tUbicacion": "Location" or null,
    "tEstado": "Status" or null,
    "tReferencia": "Reference number" or null,
    "tObservaciones": "Observations or notes" or null,
    "tDescripcionDetallada": "Detailed description from item tables" or null,
    "tCatalogo": "Catalog number" or null,
    "tMarcaProducto": "Product brand" or null,
    "tFechaEntrega": "Delivery date in YYYY-MM-DD" or null,
    // ... ANY OTHER FIELD you find in the document that is relevant - be flexible and extract what you see
  }],
  // EXTRACTION RULES FOR mmaquinaria_equipos:
  // 1. PRIORITY: Extract ALL monetary values (nValorMonetario, nPrecioUnitario, nPrecioTotal) - these are CRITICAL for validation
  // 2. For purchase orders (Órdenes de Compra): Extract ALL items from pricing tables with their monetary values
  // 3. For vehicle information (Guías de Remisión): Extract vehicle details (marca, placa, TUCE, conductor, license)
  // 4. For equipment/machinery: Extract descriptions, serial numbers, model numbers, codes
  // 5. For order tables: Extract each row as a separate entry if it has monetary values
  // 6. BE FLEXIBLE: Extract ANY additional fields you find that are relevant to machinery/equipment/vehicles/orders
  // 7. If document has multiple items in a table, create separate entries for EACH item
  // 8. Always include monetary values if present - they are essential for validation purposes
  // 9. **CRITICAL FOR TAXI RECEIPTS**: For Chinese taxi receipts (发票联 with 车号):
  //    - Extract EACH taxi receipt as a separate mmaquinaria_equipos entry
  //    - tTipo: "Vehículo" or "Taxi Receipt"
  //    - tPlaca: Extract from "车号" (Car No.) column (e.g., "K-T0116", "K-T5962", "K-T6601", "K-T0272", "A.AN0942")
  //    - dFecha: Extract from "日期" (Date) column (e.g., "2025年06月11日" → "2025-06-11")
  //    - nValorMonetario: Extract from "金额" (Amount) column (e.g., 88.00, 68.00, 57.00, 72.00)
  //    - tMoneda: "CNY" (Chinese Yuan) for Chinese receipts
  //    - tDescripcion: Combine boarding/alighting info (e.g., "Taxi from 06:09 to 06:53, 28.4km")
  //    - Also extract: boarding time (上车), alighting time (下车), mileage (里程), waiting time (等候), unit price (单价)
  //    - If document has multiple taxi receipts, create separate entry for EACH one
}

=== DATE FORMAT CONVERSION ===
Convert ALL dates to YYYY-MM-DD format. Accept these input formats:
- DD/MM/YYYY → YYYY-MM-DD (e.g., "28/05/2025" → "2025-05-28")
- MM-DD-YYYY → YYYY-MM-DD (e.g., "05-28-2025" → "2025-05-28")
- "May 28, 2025" → 2025-05-28
- "28-May-2025" → 2025-05-28
- "30-JUN-2025" → 2025-06-30
- "JUL 23, 2025" → 2025-07-23
- "Date: 28 May 2025" → 2025-05-28
- "Fecha: 28/05/2025" → 2025-05-28
- "Tarikh: 28/05/2025" → 2025-05-28
- Any other format → convert to YYYY-MM-DD

IMPORTANT: Validate dates - do NOT extract phone numbers as dates. Examples to avoid:
- "1300-80-8989" (phone number, not date)
- Numbers with more than 8 digits when removing separators are likely NOT dates
- If a pattern looks like DD/MM/YYYY or MM-DD-YYYY but has >8 digits total, it's probably a phone number
- Validate month values: should be 01-12 (not 13-99)
- Validate day values: should be reasonable (01-31, considering month)

=== OCR CORRECTIONS ===
Apply these corrections to extracted numbers:
- Fix spaces as decimal points: "32 40" → 32.40, "12 74" → 12.74
- Fix hyphens as decimal points: "25-20" → 25.20, "6-50" → 6.50
- Normalize decimal separators: ensure consistent decimal format
- Remove thousand separators: "1,234.56" → 1234.56 (keep as number, not string)

=== OUTPUT FORMAT ===
Return ONLY valid JSON. No explanations, no markdown, just the JSON object.
- The "ocr_text" field should be a SIMPLE STRING with the raw text, NOT a JSON-encoded string
  * CORRECT: "ocr_text": "BSQE\nBS0003\nActual text here..."
  * WRONG: "ocr_text": "{\"ocr_text\": \"...\"}"
- All description fields (tDescripcion, tdescription) must contain ONLY text from the document, NEVER JSON field names
  * CORRECT: "tDescripcion": "ICE VANILLA LATT"
  * WRONG: "tDescripcion": "\"nPrecioTotal\": 5."
- All numbers must be actual numbers (not strings)
- Dates must be in YYYY-MM-DD format
- Arrays must be properly formatted
- If a field is not found, use null (not empty string)
- For arrays, use [] if empty, not null
- Negative values: use negative numbers (e.g., -305350), not strings with parentheses
- Apply OCR corrections (spaces/hyphens as decimals) before returning numbers
- For empty receipts/forms with no items filled: Return empty arrays for mcomprobante_detalle, do NOT create items from headers or row numbers

Example response structure:
{
  "ocr_text": "Complete extracted text here...",
  "ocr_text_translated": "Complete translated text to English (if original is not English/Spanish, otherwise same as ocr_text)",
  "document_type": "comprobante",
  "structured_data": {
    "mdivisa": [{"tDivisa": "USD"}],
    "mproveedor": [{"tRazonSocial": "Company Name"}],
    "mnaturaleza": [{"tNaturaleza": "Alimentación"}],
    "mdocumento_tipo": [{"iMDocumentoTipo": 1, "tTipo": "Comprobante"}],
    "midioma": [{"iMIdioma": 2, "tIdioma": "Inglés"}],
    "munidad_medida": [{"tUnidad": "kg"}, {"tUnidad": "unidades"}],
    "mdepartamento": [{"tDepartamento": "Engineering"}, {"tDepartamento": "Procurement"}],
    "mdisciplina": [{"tDisciplina": "Project Management"}],
    "mcomprobante": [...],
    "mcomprobante_detalle": [{
      "nCantidad": 2,
      "tUnidad": "kg",
      "tDescripcion": "Item description",
      "nPrecioUnitario": 10.50,
      "nPrecioTotal": 21.00
    }],
    "mmaquinaria_equipos": [{
      "tTipo": "Vehículo",
      "tMarca": "NISSAN",
      "tPlaca": "C1J-905",
      "nValorMonetario": 5000.00,
      "tMoneda": "USD"
    }]
  }
}

=== STEP 4: TRANSLATE TEXT (if needed) ===
After extracting the OCR text, translate it to English IF the original language is NOT English or Spanish:
- If original language is Italian, Chinese, Malay, or any other language → translate to English
- If original language is English or Spanish → keep ocr_text_translated the same as ocr_text
- Maintain all formatting, numbers, dates, and technical terms exactly as they appear
- Only translate natural language parts
- Preserve structure, line breaks, and special characters

CRITICAL: Extract EVERYTHING. Leave NOTHING behind. Return complete, accurate JSON. Prioritize highlighted/handwritten values.

=== CRITICAL: DO NOT INCLUDE FIELDS STARTING WITH "_" (MANDATORY) ===
**MANDATORY RULE**: Do NOT extract or include ANY fields that start with underscore "_" in the structured_data output.
- All fields starting with "_" are internal metadata/processing fields and should NEVER appear in the final JSON response
- **FORBIDDEN FIELDS** (examples - DO NOT include any of these or similar):
  * "_currency", "_source_line", "_auto_extracted", "_currency_code"
  * "_myr_amount", "_highlighted", "_is_total_row", "_total"
  * "_metadata", "_internal", "_processing", "_temp", "_is_total"
  * ANY field name that starts with "_" - FORBIDDEN
- **ONLY INCLUDE**: Standard fields without underscore prefix (e.g., tjobno, ttype, nImporte, tStampname, tsequentialnumber, nCantidad, tDescripcion, nPrecioUnitario, nPrecioTotal, etc.)
- **VALIDATION**: Before returning the JSON, verify that NO field names start with "_" - if you find any, remove them completely

=== CRITICAL: COMPLETE EXTRACTION REQUIREMENT ===
You MUST extract ALL fields completely. Do NOT return partial data:
- If document is "ticket", "factura_electronica", "comprobante", OR "nota_bill": 
  * Extract mcomprobante (with tNumero, dFecha, nPrecioTotal, tStampname, tsequentialnumber) - REQUIRED
  * Extract mcomprobante_detalle (ALL items from tables) - REQUIRED if document has a table with items
  * For "ATTACHMENT TO INVOICE": Extract ALL table rows including "TOTAL AMOUNT IN US$" row - MANDATORY
  * For Italian invoices: Extract all monetary values including base amount and stamp duty, prioritize final total after stamp duty
- If document is "resumen": Extract mresumen (with tjobno, ttype, tsourcereference, tsourcerefid, tdescription, nImporte, tStampname, tsequentialnumber) - ALL rows from ALL tables
- If document is "jornada": Extract mjornada AND mjornada_empleado (ALL employees with hours, dates, org codes, project allocations, costs) - MANDATORY
- ALWAYS extract catalog tables: mdivisa, mproveedor, mnaturaleza, mdocumento_tipo, midioma, munidad_medida, mdepartamento, mdisciplina
- ALWAYS extract stamp info: tStampname (BSQE/OTEM/OTRE/OTRU) and tsequentialnumber (BS1234/OE0001/etc.)
- ALWAYS extract mmaquinaria_equipos if document contains vehicle, equipment, machinery, or order information (see details below)
- NOTE: onshore_offshore is NOT extracted from document - it will be added by backend based on periodo_id
- If ANY field can be extracted from the document, extract it. Do NOT skip fields just because they seem optional.
- For documents with tables: Extract ALL rows from ALL tables - do NOT skip rows
- For documents with totals in red boxes: Extract those totals as separate items with highest priority

DO NOT return empty structured_data {} unless the document is completely blank. If the document has ANY text or tables, extract what you can find.

IMPORTANT REMINDERS:
- Handwritten USD values have HIGHEST PRIORITY - they override any printed values
- Values in red boxes/highlights are CRITICAL - extract them completely
- For GL Journal Details with calculations, extract ONLY highlighted values, not all table rows
- For Invoice Approval Report, do NOT extract "Line Item Details" as items
- For Invoice Group Detail, do NOT extract as items
- Weekly totals: lines with ONLY numbers (>=2 large values >=1000)
- Cash Flow: extract negative values correctly (from parentheses)
- Departments & Disciplines: map NC Codes (611=Engineering, 612=Operations, etc.)
- All dates must be converted to YYYY-MM-DD format
- All numbers must be actual numbers, not strings
- Use null for missing fields, [] for empty arrays"""
        
        # Cachear el prompt y el hash de conversiones para evitar recalcularlo
        self._prompt_cache = prompt
        self._currency_conversions_hash = current_conversions_hash
        
        return prompt