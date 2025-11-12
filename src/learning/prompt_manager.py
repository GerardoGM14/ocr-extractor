"""
Prompt Manager Module - Gestión de versiones de prompts
Responsabilidad: Gestionar versiones de prompts y aplicar mejoras
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime


class PromptManager:
    """
    Gestiona versiones de prompts para OCR.
    
    Responsabilidades:
    - Almacenar versiones de prompts
    - Cargar prompt actual
    - Aplicar nuevas versiones de prompts
    - Mantener historial de cambios
    """
    
    def __init__(self, learning_folder: str = "learning", default_prompt: Optional[str] = None):
        """
        Inicializa el gestor de prompts.
        
        Args:
            learning_folder: Carpeta base para almacenar datos de learning
            default_prompt: Prompt por defecto (si no existe uno guardado)
        """
        self.learning_folder = Path(learning_folder)
        self.prompts_folder = self.learning_folder / "prompts"
        self.prompts_folder.mkdir(parents=True, exist_ok=True)
        
        self.current_version_file = self.prompts_folder / "current_version.json"
        self.prompts_history_file = self.prompts_folder / "prompts_history.json"
        
        self.default_prompt = default_prompt or self._get_default_prompt()
        
        # Cargar versión actual
        self.current_version = self._load_current_version()
    
    def _get_default_prompt(self) -> str:
        """Retorna el prompt por defecto (el actual del sistema)."""
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

SPECIFIC ITEMS TO EXTRACT:
- Header information (company names, logos, addresses, contact info)
- Document type indicators (Invoice, Receipt, Summary, etc.)
- Document numbers, serials, reference codes
- Dates (issue date, due date, period dates, etc.)
- Stamp names (BSQE, OTEM, OTRE, OTRU, or similar)
- Sequential numbers (BS####, OE####, OR####, ORU####, etc.)
- Vendor/Supplier information (name, address, tax ID)
- Client/Customer information (name, address, contact)
- Table data (item descriptions, quantities, prices, totals)
- Line items with descriptions, units, quantities, rates
- Subtotal, tax amounts, discounts, total amounts
- Currency information (USD, PEN, EUR, etc.)
- Payment terms, conditions, notes
- Authentication codes, QR codes text, barcodes
- Period information (from date, to date)
- Job numbers, source references, classifications
- Employee names, IDs, organizations (for time sheets)
- Hours worked, rates, totals
- Any metadata, tags, or classification data

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
Do not skip content. Scan thoroughly. Extract completely. Nothing should be left unread.
        """
    
    def _load_current_version(self) -> Dict:
        """Carga la versión actual del prompt."""
        if self.current_version_file.exists():
            try:
                with open(self.current_version_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Si no existe, crear versión inicial con prompt por defecto
        return {
            "version": 1,
            "prompt": self.default_prompt,
            "created_at": datetime.now().isoformat(),
            "description": "Prompt inicial por defecto",
            "improvements": []
        }
    
    def get_current_prompt(self) -> str:
        """
        Obtiene el prompt actual.
        
        Returns:
            Prompt actual como string
        """
        return self.current_version.get("prompt", self.default_prompt)
    
    def get_current_version_info(self) -> Dict:
        """
        Obtiene información de la versión actual.
        
        Returns:
            Diccionario con información de la versión
        """
        return {
            "version": self.current_version.get("version", 1),
            "created_at": self.current_version.get("created_at"),
            "description": self.current_version.get("description", ""),
            "improvements": self.current_version.get("improvements", [])
        }
    
    def save_new_version(self,
                        new_prompt: str,
                        description: str,
                        improvements: List[str],
                        source: str = "manual") -> int:
        """
        Guarda una nueva versión del prompt.
        
        Args:
            new_prompt: Nuevo prompt
            description: Descripción de los cambios
            improvements: Lista de mejoras implementadas
            source: Origen del cambio ("manual", "learning", "gemini_suggestion")
            
        Returns:
            Número de versión creada
        """
        # Obtener siguiente versión
        current_version_num = self.current_version.get("version", 1)
        new_version_num = current_version_num + 1
        
        # Crear nueva versión
        new_version = {
            "version": new_version_num,
            "prompt": new_prompt,
            "created_at": datetime.now().isoformat(),
            "description": description,
            "improvements": improvements,
            "source": source,
            "previous_version": current_version_num
        }
        
        # Guardar versión actual
        with open(self.current_version_file, 'w', encoding='utf-8') as f:
            json.dump(new_version, f, ensure_ascii=False, indent=2)
        
        # Agregar al historial
        self._add_to_history(new_version)
        
        # Actualizar versión actual
        self.current_version = new_version
        
        return new_version_num
    
    def _add_to_history(self, version_data: Dict):
        """Agrega versión al historial."""
        history = []
        
        if self.prompts_history_file.exists():
            try:
                with open(self.prompts_history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        # Agregar nueva versión al historial
        history.append(version_data)
        
        # Mantener solo últimas 50 versiones
        if len(history) > 50:
            history = history[-50:]
        
        # Guardar historial
        with open(self.prompts_history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """
        Obtiene el historial de versiones.
        
        Args:
            limit: Número máximo de versiones a retornar
            
        Returns:
            Lista de versiones (más recientes primero)
        """
        if not self.prompts_history_file.exists():
            return []
        
        try:
            with open(self.prompts_history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                return list(reversed(history[-limit:]))
        except Exception:
            return []
    
    def revert_to_version(self, version_num: int) -> bool:
        """
        Revierte a una versión anterior.
        
        Args:
            version_num: Número de versión a la que revertir
            
        Returns:
            True si se revirtió exitosamente, False en caso contrario
        """
        history = self.get_history(limit=100)
        
        for version in history:
            if version.get("version") == version_num:
                # Restaurar esta versión como actual
                with open(self.current_version_file, 'w', encoding='utf-8') as f:
                    json.dump(version, f, ensure_ascii=False, indent=2)
                
                self.current_version = version
                return True
        
        return False

