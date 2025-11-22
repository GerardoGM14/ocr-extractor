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
                print(f"Error en llamada a Gemini API: {error_msg}")
                # Verificar si es un error de timeout o conexión
                if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
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
                print(f"Error en llamada a Gemini API: {error_msg}")
                if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                    return {
                        "success": False,
                        "error": f"API timeout/connection error: {error_msg}",
                        "text": "",
                        "structured_data": {},
                        "document_type": "unknown",
                        "timestamp": time.time()
                    }
                raise
            
            # Verificar si hay respuesta válida
            if not response.text:
                error_msg = "Empty response from Gemini"
                finish_reason = None
                
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    error_msg = f"Content filtered: {response.prompt_feedback.block_reason}"
                elif hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'finish_reason'):
                            finish_reason = candidate.finish_reason
                            if finish_reason == 'SAFETY':
                                error_msg = "Content blocked by safety filters"
                            elif finish_reason == 'RECITATION':
                                error_msg = "Content blocked due to recitation"
                            break
                
                print(f"Warning: {error_msg} (finish_reason: {finish_reason})")
                return {
                    "success": False,
                    "error": error_msg,
                    "text": "",
                    "structured_data": {},
                    "document_type": "unknown",
                    "timestamp": time.time()
                }
            
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
        """
        return """You are an expert document processing system with advanced reasoning capabilities. Your task is to extract ALL text from this financial document AND structure the data according to the document type.

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

CRITICAL: You must return a STRICT JSON object with this exact structure:
{
  "ocr_text": "ALL extracted text from the document as PLAIN TEXT (NOT JSON - just raw text with line breaks, complete, nothing missing)",
  "ocr_text_translated": "Translated text to English as PLAIN TEXT (if original is not English/Spanish, otherwise same as ocr_text)",
  "document_type": "comprobante|resumen|jornada|expense_report|concur_expense|unknown",
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
6. DESCRIPTION FIELDS (tDescripcion, tdescription): MUST be CLEAN, PROFESSIONAL text extracted DIRECTLY from the document itself. 
   - GOOD examples: "Toll", "Hotel", "Meal", "ICE VANILLA LATT", "ADD ESP SHT", "Room Charge", "Transportation Fee", "Grand Total USD", "TOTAL EXPENSES", "JENIS BARANG-BARANG" (if that's what the document shows)
   - BAD examples (NEVER DO THIS): 
     * "\"ocr_text\": \"BECHTEL JOBS NO.\"" - WRONG!
     * "\"nImporte\":" - WRONG!
     * "\"_myr_amount\":" - WRONG!
     * "\"nPrecioTotal\": 5." - WRONG!
     * "\"ocr_text\": \"...\"" - WRONG!
     * Any JSON field names or structures - WRONG!
   - HOW TO EXTRACT CORRECTLY: 
     * Look at the ACTUAL document. Find the "Description" or "PARTICULARS" or "摘要" column in the table.
     * Extract EXACTLY what is written in that column - if it says "ICE VANILLA LATT", extract "ICE VANILLA LATT". If it says "Toll", extract "Toll". If it says "Hotel", extract "Hotel".
     * For receipt/coffee shop items: Extract item names like "ICE VANILLA LATT", "ADD ESP SHT", etc. exactly as shown.
     * For expense summaries: Extract "Toll", "Hotel", "Meal" exactly as shown in Description column.
     * For empty receipts: If there are table headers but no items filled, do NOT create items. Only extract items that actually have values in the table.
   - DO NOT extract JSON structures, OCR metadata fields, technical field names, or anything that is NOT visible in the document itself.
   - DO NOT extract table headers as item descriptions - only extract actual item descriptions from filled table rows.
7. DO NOT include any technical/metadata fields in structured_data such as: "_currency", "_source_line", "_auto_extracted", "_currency_code", etc.
   - These are internal processing fields and should NEVER appear in the final structured_data output
   - Only include the fields specified in the schema (nCantidad, tDescripcion, nPrecioUnitario, nPrecioTotal, etc.)

=== STEP 1: EXTRACT ALL TEXT (OCR) ===
Extract 100% of ALL visible text from this document. Read EVERYTHING line by line, character by character:
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

=== STEP 2: IDENTIFY DOCUMENT TYPE ===
Classify the document as one of (PRIORITY ORDER - check top to bottom):

PRIORITY 1: "comprobante" if document contains ANY of these patterns:
- "attachment to invoice" (HIGHEST PRIORITY - this is an invoice attachment, not expense report)
- Invoice keywords: "invoice", "factura", "boleta", "bill", "recibo", "fattura", "invoice no", "invoice number", "invoice num"
- Table headers in Spanish: "cant.", "descripción", "precio unitario", "importe"
- Table headers in Malay/Chinese: "tarikh", "kuantiti", "harga", "jumlah", "no.", "jumlah/", "總計", "总计", "cash / invoice", "cash/invoice"
- Chinese invoice keywords: "发票", "发票号码", "发票代码"
- Receipt keywords: "receipt", "recibo", "NO. KUANTITI", "PARTICULARS", "BUTIR-BUTIR"
- Other: "GL Journal Details", Oracle AP invoices, "Invoice Approval Report"

PRIORITY 2: "concur_expense" if document contains:
- "concur expense", "concur", "Line Item by Job Section"
- Check BEFORE expense_report

PRIORITY 3: "expense_report" if document contains:
- "bechtel expense report", "expense report", "report key", "report number", "report date", "bechexprpt", "BECHEXPRPT", "report purpose", "bechtel owes"

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
   Include legal suffixes: SDN BHD, LLC, Inc, Company, S.A., S.L., SRL
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
   Example: [{"iMDocumentoTipo": 1, "tTipo": "Comprobante"}]
   Mapping: comprobante=1, resumen=2, jornada=3, expense_report=4, concur_expense=5

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

6. tSequentialNumber: Sequential codes like BSQE1234, OE0001, OR0001, ORU1234
   EXTRACTION PATTERNS (check ALL):
   a) Stamp name patterns: Look for "BSQE", "OTEM", "OTRE", "OTRU" (case insensitive)
   b) Sequential number patterns:
      - Same line: "BSQE1234", "OE0001", "OR0001", "ORU1234" (stamp + 4+ digits on same line)
      - Separated lines: "OTEM\nOE0001" or "ORRE OR0001" (stamp on one line, code on next line within 200 chars)
      - Format: (BS|OE|OR|ORU) followed by 4+ digits
   c) Stamp to code mapping: OTEM → OE, OTRE → OR, OTRU → ORU, BSQE → BS
   d) If stamp name found but no code: Look for any 4+ digit number near stamp (within 200 chars), then construct code using mapping
   e) Priority: Extract sequential number if found anywhere in document header/top section

FOR "comprobante" TYPE - Extract:
{
  "mcomprobante": [{
    "tNumero": "invoice/boleta number - EXTRACT USING THESE PATTERNS (priority order):\n     1. Source Ref (GL Journal Details): 'Source Ref: 2336732507B0032' OR 'Source Ref: 2336732507B0032'\n     2. Oracle AP Invoice Num: 'Invoice Num F581-06891423' (format: FXXX-XXXXXXXX)\n     3. Invoice Number explicit: 'Invoice Number: 1234' OR 'Invoice No.: 18294'\n     4. BOLETA ELECTRÓNICA: 'BOLETA ELECTRÓNICA N° 0000155103' (Chilean format)\n     5. Chinese invoice number: '发票号码:25379166812000866769' (8+ digits) OR '发票代码:121082271141' (10+ digits)\n     6. N° format: 'N° 0000155103' (4+ digits after N°)\n     7. Folio: 'Folio No.: 18294' OR 'Folio: 18294'\n     8. Recibo: 'Recibo 221' (Spanish receipt format)\n     9. FATTURA NO.: 'FATTURA NO.: 333/25' (Italian format - can be same line or next line, format XXX/XX)\n     10. Generic Invoice: 'INVOICE No. XXXX', 'FATTURA N° XXX', 'CASH NO. XXX' (avoid 'Invoice Numb')\n     11. NO. near TOTAL: 'NO. 1234 TOTAL' (3+ digits near total keywords)\n     12. Chinese 号码: '号码' or '发票号码' or '发票代码' followed by 8+ digits\n     13. Generic with numbers: Any pattern with '总计', 'JUMLAH', 'No.', 'NO.', '#' followed by 4+ alphanumeric chars containing digits\n     IMPORTANT: Extract the FULL number/identifier, not partial. If multiple formats match, use highest priority.",
    "tSerie": "series number or Contract no. if present (e.g., 'Contract no 12345')" or null,
    "dFecha": "date in YYYY-MM-DD format - EXTRACT USING THESE PATTERNS:\n     - 'Date:' or 'Fecha:' or 'Tarikh:' followed by date\n     - Format 1: 'DD/MM/YYYY' or 'DD-MM-YYYY' (e.g., '28/05/2025', '28-05-2025')\n     - Format 2: 'May 28, 2025' or '28 May 2025'\n     - Format 3: '28-May-2025' or '30-JUN-2025'\n     - Format 4: 'JUL 23, 2025'\n     IMPORTANT VALIDATION: Do NOT extract phone numbers as dates:\n     - Avoid '1300-80-8989' (phone number)\n     - Numbers with >8 digits when removing separators are likely NOT dates\n     - If pattern looks like date but has >8 digits total, it's probably a phone number\n     - Validate: date should have max 8 digits (2+2+4) or reasonable month/day values",
    "fEmision": "emission date in YYYY-MM-DD format (same as dFecha if not separately specified)" or null,
    "nPrecioTotal": number (total amount - EXTRACT USING REASONING AND THESE PATTERNS in priority order):\n     **CRITICAL: Use your reasoning ability to identify the CORRECT total by analyzing the document context, relationships between values, and visual emphasis.**\n     1. HANDWRITTEN USD VALUES (HIGHEST PRIORITY - USE REASONING): \n        - If you see ANY handwritten/manually written text containing "USD" followed by a number (e.g., "USD 5.00", "USD425", "USD 4/25" written by hand), use that amount as nPrecioTotal\n        - Handwritten values often appear as corrections, annotations, or final validations\n        - Look for text that appears different in style, position, or format - these are likely handwritten\n        - Examples: "USD 5.55" written near a printed "RM22.80", "USD425" at bottom of receipt, "USD4/25" as annotation\n        - **REASONING**: If you see both printed RM/MYR and handwritten USD, the handwritten USD is the authoritative total\n        - **IMPORTANT**: Handwritten USD values override ANY printed values, even if printed totals are present\n     2. HANDWRITTEN VALUES WITHOUT CURRENCY (HIGH PRIORITY):\n        - If you see handwritten numbers that appear to be totals (often near printed totals, in boxes, or highlighted), analyze the context\n        - If handwritten value is USD amount and printed is RM/MYR, prioritize handwritten USD\n        - Use reasoning: handwritten totals are usually final validations or conversions\n     3. Highlighted/Boxed values (PRIORITY - USE REASONING):\n        - Values in red boxes, yellow highlights, bordered sections, or visually emphasized areas are CRITICAL\n        - Extract values INSIDE colored boxes or highlighted areas - these are often final totals\n        - Examples: 'TOTAL AMOUNT IN US$ ... $ 120.60' in red box, totals in highlighted rectangles\n        - **REASONING**: Visually emphasized values indicate importance - prioritize these over regular text\n     4. Printed Totals (USE REASONING TO IDENTIFY CORRECT ONE):\n        - Look for "Total", "TOTAL", "Total Amount", "总计", "JUMLAH", "Grand Total", "Amount Due" followed by currency and number\n        - **REASONING**: If multiple totals appear (subtotal, tax, final total), use the FINAL total after all calculations\n        - For Italian invoices: If 'TOTAL' appears on one line with '$ XXX.XX' values below, extract the LAST value (final total after stamp duty)\n        - Example: 'TOTAL\n$\n120.60\n$\n2.34\n$\n122.94' → extract 122.94 (the LAST value after stamp duty of 2.34)\n     5. Oracle AP: 'Invoice Amount USD 655740.75' or 'Invoice Invoice Amount USD 655740.75' or 'Invoice Amount 655740.75'\n     6. Chinese/Malay totals: '总计' or 'JUMLAH RM' followed by number (e.g., '总计 RM 17.50' or '总计 1,234.56 元')\n     7. Calculation-based totals: If you see calculations like "USD 4,301.00 + USD 616.00 = USD 6,369.00", use the final sum (6,369.00)\n     8. **REASONING FALLBACK**: If no explicit total found, analyze the document structure:\n        - Look for patterns: printed totals usually appear after item lists, at bottom of tables, or near payment information\n        - If document has line items in mcomprobante_detalle, sum them as fallback\n        - Consider relationships: if there's a "Cash" payment matching a total, that's likely the correct total\n     9. OCR corrections: Fix spaces as decimals (32 40 → 32.40), hyphens as decimals (25-20 → 25.20)\n     **REMEMBER**: Use reasoning to relate information across the document - handwritten values near totals, highlighted boxes, and relationships between printed amounts all provide context for the CORRECT total.
    "tCliente": "client name from 'Attn.:' or 'Attn' field" or null,
    "tStampname": "Extract stamp name using patterns: 'BSQE', 'OTEM', 'OTRE', 'OTRU' (case insensitive, can be on same line or nearby lines)" or null,
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
    "tDescripcion": "item description - Extract EXACTLY what the document shows in the Description/Particulars/摘要 column of the table. Examples: 'ICE VANILLA LATT', 'ADD ESP SHT', 'Toll', 'Hotel', 'Meal', 'Room Charge', etc. Look at the ACTUAL table row - if it says 'ICE VANILLA LATT' in the description column, extract 'ICE VANILLA LATT'. If it says 'Toll', extract 'Toll'. DO NOT extract JSON field names like '\"ocr_text\"', '\"nImporte\"', '\"nPrecioTotal\"', '\"_myr_amount\"' - these are WRONG. Only extract what is actually visible in the document table. For empty receipts with no items filled, do NOT create items.",
    "nPrecioUnitario": number,
    "nPrecioTotal": number
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
    "nImporte": number (USD amount - prioritize USD column values, use USD not MYR for nImporte),
    "tStampname": "BSQE|OTEM|OTRE|OTRU" or null,
    "tsequentialnumber": "sequential code" or null,
    // Additional metadata fields:
    "_weekly_total": true if weekly total, or null,
    "_week_number": "week number" or null,
    "_cash_flow": true if cash flow value, or null,
    "_cash_flow_type": "Total Disbursement|Period Balance|Cumulative Cash Flow|Opening Balance|Total Receipts" or null,
    "_calculation": true if highlighted calculation, or null,
    "_calculation_text": "calculation text" or null,
    "_highlighted": true if highlighted value (e.g., "Grand Total USD" or "TOTAL EXPENSES"), or null,
    "_handwritten": true if handwritten value, or null,
    "_priority": true if handwritten (highest priority), or null,
    // For expense summaries with tables:
    "_myr_amount": number (MYR amount if present in table) or null,
    "_item_number": "Item No. from table" or null
  }],
  // IMPORTANT: For expense summary documents with multiple tables (like Bechtel expense summaries):
  // Extract EACH row from EACH table as a separate mresumen entry
  // Example: If you see 3 tables, extract ALL rows from table 1, then ALL rows from table 2, then ALL rows from table 3
  // Each row should have: tdescription (Toll/Hotel/Meal), nImporte (USD amount), tjobno (job number from header), etc.
  // "Grand Total USD" values should also be extracted as separate mresumen entries with _highlighted: true
  
  // Weekly totals: lines with ONLY numbers (no item descriptions) containing 2+ large monetary values
  // These appear at the end of tables and represent totals by week
  "weekly_totals": [{
    "tjobno": null,
    "ttype": "Week XX Total",
    "tsourcereference": null,
    "tsourcerefid": "Week XX",
    "tdescription": "Total Week XX",
    "nImporte": number,
    "tStampname": null,
    "tsequentialnumber": null,
    "_weekly_total": true,
    "_week_number": "week number"
  }] or [],
  // Cash Flow values: extract ALL cash flow related values
  "cash_flow": [{
    "tjobno": null,
    "ttype": "Cash Flow - Total Disbursement|Period Balance|Cumulative Cash Flow|Opening Balance|Total Receipts",
    "tsourcereference": null,
    "tsourcerefid": "Week XX" if applicable,
    "tdescription": "Cash Flow description with amount",
    "nImporte": number (NEGATIVE if in parentheses like (305,350), POSITIVE otherwise),
    "tStampname": null,
    "tsequentialnumber": null,
    "_cash_flow": true,
    "_cash_flow_type": "Total Disbursement|Period Balance|Cumulative Cash Flow|Opening Balance|Total Receipts"
  }] or []
}

FOR "expense_report" TYPE - Extract:
{
  "mcomprobante": [{
    "tNumero": "Report Number (e.g., '0ON74Y')",
    "dFecha": "Report Date in YYYY-MM-DD (convert from 'Jul 23, 2025' format)",
    "nPrecioTotal": number (Report Total amount - PRIORITY if in red box/highlighted),
    "tEmployeeID": "Employee ID (e.g., '063573')",
    "tEmployeeName": "Employee Name (e.g., 'AYALA SEHLKE, ANA MARIA')",
    "tOrgCode": "Org Code (e.g., 'HXH0009')",
    "tReportPurpose": "Report Purpose (e.g., 'Viaje a turno')",
    "tReportName": "Report Name" or null,
    "tDefaultApprover": "Default Approver" or null,
    "tFinalApprover": "Final Approver" or null,
    "tPolicy": "Policy (e.g., 'Assignment Long Term')" or null,
    "tBechtelOwesEmployee": number (Bechtel owes Employee amount) or null,
    "tBechtelOwesCard": number (Bechtel owes Card amount) or null,
    "tReportKey": "Report Key" or null,
    "tDocumentIdentifier": "BECHEXPRPT_{EmployeeID}_{ReportNumber}" or null,
    "tStampname": "BSQE|OTEM|OTRE|OTRU|OTHBP" or null,
    "tsequentialnumber": "sequential code" or null
  }],
  "mresumen": [{
    // Same structure as resumen type, with expense report specific data
    "tjobno": "Org Code",
    "ttype": "Expense Report",
    "tsourcereference": "Report Number",
    "tsourcerefid": "Report Key",
    "tdescription": "Report description with purpose",
    "nImporte": number,
    "tStampname": "stamp name" or null,
    "tsequentialnumber": "sequential number" or null
  }],
  // For OnShore documents:
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
    "tDescripcion": "expense description with merchant and location",
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

=== SPECIAL PRIORITIES ===
1. HANDWRITTEN VALUES (HIGHEST PRIORITY - USE REASONING): 
   **CRITICAL**: Handwritten text with monetary values has HIGHEST PRIORITY and overrides ANY printed values.
   - **DETECTION**: Look for text that appears manually written - different style, position, annotation-like appearance, or clearly added by hand
   - **PATTERNS**: Handwritten values often appear:
     * Near printed totals as corrections or conversions (e.g., "USD 5.55" written next to "RM22.80")
     * At bottom of receipts/invoices as final validations
     * In boxes or highlighted areas as annotations
     * With slight misalignment or different font style
   - **EXAMPLES**: 
     * "USD 5.55" written by hand near printed "Total RM22.80" → Use 5.55 as nPrecioTotal
     * "USD425" handwritten at bottom of receipt → Use 425.00 as nPrecioTotal  
     * "USD4/25" or "USD 4/25" as annotation → Interpret as "USD 4.25" or "USD 425" based on context
     * Handwritten "$20" near printed totals → Use 20.00 as nPrecioTotal if it appears to be a final total
   - **REASONING**: 
     * Handwritten USD values are usually final validations, currency conversions, or corrections
     * If you see both printed RM/MYR and handwritten USD, the handwritten USD is the authoritative conversion
     * Handwritten totals often represent the amount actually paid or required
   - **EXTRACTION**: 
     * Mark handwritten values with [HANDWRITTEN] in ocr_text for identification
     * Extract the handwritten USD value in ocr_text AND use it as nPrecioTotal in structured data (mcomprobante)
     * Store the original RM/MYR printed amount separately if needed, but handwritten USD is ALWAYS the PRIMARY total
   - **CONTEXT ANALYSIS**: 
     * If handwritten value appears near a printed total, analyze which one represents the final amount
     * Look for visual cues: boxes, arrows, or positioning that indicate the handwritten value is the final total
     * Consider document purpose: handwritten USD on Malaysian receipts often indicates currency conversion
2. HIGHLIGHTED VALUES: Values in red boxes, yellow highlights, or visually emphasized sections are PRIORITY - extract them completely. Especially important for:
   - "TOTAL AMOUNT IN US$" values in red boxes at bottom of tables (Attachment to Invoice) - CRITICAL: Extract this as a separate item in mcomprobante_detalle with tDescripcion: "TOTAL AMOUNT IN US$", nPrecioTotal: value from red box
   - "TOTAL $ XXX.XX" in red boxes (Italian invoices) - Extract the final total after stamp duty (the LAST value)
   - Report Total amounts in red boxes (Expense Reports)
   - For "ATTACHMENT TO INVOICE": The red box at the bottom contains the total amount - extract this value and use it as nPrecioTotal in a separate mcomprobante_detalle entry
3. CALCULATIONS: Extract calculations like "USD 4,301.00 + USD 616.00 + USD 1,452.00 = USD 6,369.00" completely. Extract both individual values (4,301.00, 616.00, 1,452.00) AND final total (6,369.00).
4. GL JOURNAL DETAILS: If document is "GL Journal Details" WITH highlighted calculations (red box), extract ONLY the highlighted calculation values, NOT all table rows. If WITHOUT highlighted calculations, extract all table rows as items (use ONLY nPrecioUnitario, NOT nPrecioTotal).
5. ATTACHMENT TO INVOICE: For "ATTACHMENT TO INVOICE" documents - THIS IS CRITICAL AND MANDATORY:
   - Extract ALL table rows as separate items in mcomprobante_detalle - DO NOT skip any rows
   - Table structure: Resource | Vendor | Assignment no. | Report Number | Request | Type of Activity | Date of visit | hrs | hrly rate | km/miles | mileage rate | Expenses | Total Labor | Total Expenses | Total Amount
   - For EACH data row (not headers):
     * Extract Resource Name (e.g., "Martin Loges")
     * Extract Vendor Name (e.g., "Duchting Pumpen, Witten, Germany")
     * Extract Type of Activity (e.g., "Inspection")
     * Extract Date of visit (e.g., "11-Jun-25", "30-Jun-25")
     * Extract hrs (e.g., 12, 10)
     * Extract hrly rate OR mileage rate (e.g., $ 0.67)
     * Extract Total Amount (e.g., $ 60.30) - THIS IS MANDATORY
   - Mapping to mcomprobante_detalle:
     * tDescripcion: "Resource Name - Vendor Name - Type of Activity" (e.g., "Martin Loges - Duchting Pumpen, Witten, Germany - Inspection")
     * nCantidad: Extract from "hrs" column (e.g., 12, 10) OR from "km/miles" if hrs is empty
     * nPrecioUnitario: Extract from "hrly rate" OR "mileage rate" column (e.g., 0.67)
     * nPrecioTotal: Extract from "Total Amount" column (e.g., 60.30) - REQUIRED
   - For "TOTAL AMOUNT IN US$" row at the bottom (usually in red box/highlighted):
     * Extract this as a SEPARATE entry in mcomprobante_detalle
     * tDescripcion: "TOTAL AMOUNT IN US$" (exactly as shown)
     * nCantidad: Extract from "hrs" column if shown (e.g., 22) OR from "km/miles" (e.g., 180) OR use 1
     * nPrecioUnitario: Can be null or use rate if available
     * nPrecioTotal: Extract from "Total Amount" column from red box/highlighted area (e.g., 120.60) - THIS IS THE CRITICAL VALUE
   - CRITICAL: Extract ALL rows including the total row - do NOT skip any rows
6. ITALIAN INVOICES (FATTURA): Pay special attention to red boxes or highlighted areas containing invoice numbers (e.g., "FATTURA NO.: 333/25") and total amounts.
   - Invoice number format: "FATTURA NO.: 333/25" or "INVOICE No. 333/25" → extract "333/25" as tNumero
   - Total extraction: Look for "TOTAL" keyword followed by values
   - If "TOTAL" is on one line and "$ XXX.XX" values on following lines, extract ALL values but prioritize the LAST value (final total after stamp duty)
   - Example: If you see "TOTAL\n$\n120.60\n$\n2.34\n$\n122.94", extract 122.94 as nPrecioTotal (the LAST value after stamp duty)
   - Also extract stamp duty separately if visible: "Stamp duty excl art. 15 DPR 633/1972 (€ 2,00)" → $ 2.34
   - Extract ALL monetary values shown: base amount (120.60), stamp duty (2.34), final total (122.94)
   - If there's a "Total amount in Euro:" with conversion, extract that too but prioritize USD amounts
7. WEEKLY TOTALS (OnShore): Extract lines with multiple large monetary values at the end of tables (e.g., "7,816,974.79 305,349.84 6,333,781.02"). These are usually weekly totals. Look for lines with ONLY numbers (>=2 large values >=1000) and no item descriptions.
8. CASH FLOW VALUES (OnShore): Extract "Total Disbursement", "Period Balance", "Cumulative Cash Flow", "Opening Balance", "Total Receipts" values from cash flow tables. Include negative values correctly (from parentheses like (305,350) → -305350).
9. DEPARTMENTS & DISCIPLINES (OnShore): Extract department names (Engineering, Operations, Maintenance, Safety, Environmental, Human Resources, Finance, IT Services, Other Services) and discipline names (Project Management, Quality Control, Procurement, Construction, Logistics) from tables, headers, or classification sections. Map NC Codes (611=Engineering, 612=Operations, etc.).
10. INVOICE APPROVAL REPORT: Do NOT extract "Line Item Details" as items. Those are data columns (Line Amount, Nat Class, Job, Sub Job, Cost Code), NOT purchase items. Only extract actual purchase items if they exist elsewhere.
11. INVOICE GROUP DETAIL: Do NOT extract "Invoice Group Detail" section as items. Skip lines matching pattern like "BSQEUSD 751671 33025" or containing "INV Group ID".
12. LABOR DETAILS: For "BSQE SERVICE CHARGES" or labor tables with "Emp Name", extract rows with pattern: Employee Name + BSQE code + date + Hours + Hrly Rate + Currency + Amount. Map: hours → nCantidad, rate → nPrecioUnitario, amount → nPrecioTotal, description → "Employee Name INSPECTING".
13. EXPENSE SUMMARY TABLES: For documents with multiple expense tables (like Bechtel expense summaries with Toll/Hotel/Meal):
    - Extract EVERY row from EVERY table as a separate mresumen entry
    - Include Item No. if present in the table
    - CRITICAL FOR DESCRIPTIONS: Look at the actual "Description" column in the table. If it says "Toll", extract "Toll". If it says "Hotel", extract "Hotel". If it says "Meal", extract "Meal". Extract ONLY what the document shows in the Description column, NOT JSON structures, NOT OCR metadata.
    - Use USD amount as nImporte (prioritize USD over MYR)
    - Store MYR amount in _myr_amount if needed
    - Extract job number from header (e.g., "BECHTEL JOBS NO.: 26443") as tjobno
    - Extract project name (e.g., "Project: Yanacocha AWTP Onshore") as tsourcereference
    - For "Grand Total USD" rows: Extract "Grand Total USD" as tdescription (literally from the document), extract the USD amount as nImporte, set _highlighted: true
    - For "TOTAL EXPENSES" rows: Extract "TOTAL EXPENSES" as tdescription (literally from the document), extract the USD amount as nImporte, set _highlighted: true and highest priority
    - Do NOT skip any rows - extract ALL items from ALL tables completely

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
    "mcomprobante": [...],
    "mcomprobante_detalle": [...]
  }
}

=== STEP 4: TRANSLATE TEXT (if needed) ===
After extracting the OCR text, translate it to English IF the original language is NOT English or Spanish:
- If original language is Italian, Chinese, Malay, or any other language → translate to English
- If original language is English or Spanish → keep ocr_text_translated the same as ocr_text
- Maintain all formatting, numbers, dates, and technical terms exactly as they appear
- Only translate natural language parts
- Preserve structure, line breaks, and special characters

=== STEP 4: TRANSLATE TEXT (if needed) ===
After extracting the OCR text, translate it to English IF the original language is NOT English or Spanish:
- If original language is Italian, Chinese, Malay, or any other language → translate to English
- If original language is English or Spanish → keep ocr_text_translated the same as ocr_text
- Maintain all formatting, numbers, dates, and technical terms exactly as they appear
- Only translate natural language parts
- Preserve structure, line breaks, and special characters

CRITICAL: Extract EVERYTHING. Leave NOTHING behind. Return complete, accurate JSON. Prioritize highlighted/handwritten values.

=== CRITICAL: COMPLETE EXTRACTION REQUIREMENT ===
You MUST extract ALL fields completely. Do NOT return partial data:
- If document is "comprobante": 
  * Extract mcomprobante (with tNumero, dFecha, nPrecioTotal, tStampname, tsequentialnumber) - REQUIRED
  * Extract mcomprobante_detalle (ALL items from tables) - REQUIRED if document has a table with items
  * For "ATTACHMENT TO INVOICE": Extract ALL table rows including "TOTAL AMOUNT IN US$" row - MANDATORY
  * For Italian invoices: Extract all monetary values including base amount and stamp duty, prioritize final total after stamp duty
- If document is "resumen": Extract mresumen (with tjobno, ttype, tsourcereference, tsourcerefid, tdescription, nImporte, tStampname, tsequentialnumber) - ALL rows from ALL tables
- If document is "jornada": Extract mjornada AND mjornada_empleado (ALL employees with hours, dates, org codes, project allocations, costs) - MANDATORY
- ALWAYS extract catalog tables: mdivisa, mproveedor, mnaturaleza, mdocumento_tipo, midioma
- ALWAYS extract stamp info: tStampname (BSQE/OTEM/OTRE/OTRU) and tsequentialnumber (BS1234/OE0001/etc.)
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