"""
Learning Service Module - Análisis de errores y sugerencias de mejora
Responsabilidad: Analizar errores con Gemini y proponer mejoras
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..services.gemini_service import GeminiService


class LearningService:
    """
    Servicio de aprendizaje que analiza errores y propone mejoras.
    
    Responsabilidades:
    - Analizar errores acumulados
    - Identificar patrones comunes
    - Proponer mejoras al prompt
    - Sugerir cambios en data_mapper
    """
    
    def __init__(self, gemini_service: GeminiService, learning_folder: str = "learning"):
        """
        Inicializa el servicio de aprendizaje.
        
        Args:
            gemini_service: Instancia de GeminiService
            learning_folder: Carpeta base para almacenar datos de learning
        """
        self.gemini_service = gemini_service
        self.learning_folder = Path(learning_folder)
        self.suggestions_folder = self.learning_folder / "suggestions"
        self.suggestions_folder.mkdir(parents=True, exist_ok=True)
    
    def analyze_errors(self, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analiza una lista de errores y genera sugerencias.
        
        Args:
            errors: Lista de errores a analizar
            
        Returns:
            Diccionario con análisis y sugerencias
        """
        if not errors:
            return {
                "total_errors": 0,
                "patterns": [],
                "suggestions": []
            }
        
        # Agrupar errores por tipo
        error_types = {}
        field_errors = {}
        
        for error in errors:
            error_type = error.get("error_type", "unknown")
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(error)
            
            # Si es error de campo, agrupar por campo
            if error_type in ["missing_field", "incorrect_value"]:
                field_name = error.get("context", {}).get("field_name", "unknown")
                if field_name not in field_errors:
                    field_errors[field_name] = []
                field_errors[field_name].append(error)
        
        # Analizar patrones
        patterns = self._identify_patterns(error_types, field_errors)
        
        # Generar sugerencias
        suggestions = self._generate_suggestions(patterns, errors)
        
        return {
            "total_errors": len(errors),
            "error_types": {k: len(v) for k, v in error_types.items()},
            "field_errors": {k: len(v) for k, v in field_errors.items()},
            "patterns": patterns,
            "suggestions": suggestions,
            "analyzed_at": datetime.now().isoformat()
        }
    
    def _identify_patterns(self, error_types: Dict, field_errors: Dict) -> List[Dict[str, Any]]:
        """
        Identifica patrones en los errores.
        
        Args:
            error_types: Errores agrupados por tipo
            field_errors: Errores agrupados por campo
            
        Returns:
            Lista de patrones identificados
        """
        patterns = []
        
        # Patrón 1: Campos faltantes frecuentes
        for field_name, errors in field_errors.items():
            if len(errors) >= 3:  # Al menos 3 errores del mismo campo
                # Analizar contexto común
                pdf_names = [e.get("pdf_name", "") for e in errors]
                error_messages = [e.get("error_message", "") for e in errors]
                
                patterns.append({
                    "type": "frequent_missing_field",
                    "field_name": field_name,
                    "frequency": len(errors),
                    "affected_pdfs": list(set(pdf_names)),
                    "description": f"Campo '{field_name}' falta en {len(errors)} documentos",
                    "severity": "high" if len(errors) >= 10 else "medium"
                })
        
        # Patrón 2: Valores incorrectos en campos específicos
        incorrect_value_errors = error_types.get("incorrect_value", [])
        if len(incorrect_value_errors) >= 3:
            # Agrupar por campo
            field_incorrect = {}
            for error in incorrect_value_errors:
                field_name = error.get("context", {}).get("field_name", "unknown")
                if field_name not in field_incorrect:
                    field_incorrect[field_name] = []
                field_incorrect[field_name].append(error)
            
            for field_name, errors in field_incorrect.items():
                if len(errors) >= 3:
                    patterns.append({
                        "type": "frequent_incorrect_value",
                        "field_name": field_name,
                        "frequency": len(errors),
                        "description": f"Campo '{field_name}' tiene valores incorrectos en {len(errors)} documentos",
                        "severity": "high" if len(errors) >= 10 else "medium"
                    })
        
        return patterns
    
    def _generate_suggestions(self, patterns: List[Dict], errors: List[Dict]) -> List[Dict[str, Any]]:
        """
        Genera sugerencias basadas en patrones.
        
        Args:
            patterns: Patrones identificados
            errors: Lista completa de errores
            
        Returns:
            Lista de sugerencias
        """
        suggestions = []
        
        for pattern in patterns:
            if pattern["type"] == "frequent_missing_field":
                field_name = pattern["field_name"]
                
                # Analizar errores de este campo para encontrar contexto común
                field_errors = [e for e in errors 
                              if e.get("context", {}).get("field_name") == field_name]
                
                # Extraer muestras de OCR text
                ocr_samples = []
                for error in field_errors[:5]:  # Primeros 5 errores
                    ocr_text = error.get("ocr_text") or error.get("ocr_text_preview")
                    if ocr_text:
                        ocr_samples.append(ocr_text[:500])  # Primeros 500 chars
                
                suggestion = {
                    "type": "improve_field_extraction",
                    "field_name": field_name,
                    "pattern": pattern,
                    "description": f"Mejorar extracción del campo '{field_name}'",
                    "recommendation": f"Revisar regex o lógica de extracción para '{field_name}'. "
                                    f"Este campo falta en {pattern['frequency']} documentos.",
                    "ocr_samples": ocr_samples,
                    "priority": "high" if pattern["severity"] == "high" else "medium"
                }
                suggestions.append(suggestion)
            
            elif pattern["type"] == "frequent_incorrect_value":
                field_name = pattern["field_name"]
                
                suggestion = {
                    "type": "improve_value_parsing",
                    "field_name": field_name,
                    "pattern": pattern,
                    "description": f"Mejorar parsing de valores para '{field_name}'",
                    "recommendation": f"Revisar lógica de parsing para '{field_name}'. "
                                    f"Valores incorrectos en {pattern['frequency']} documentos.",
                    "priority": "high" if pattern["severity"] == "high" else "medium"
                }
                suggestions.append(suggestion)
        
        return suggestions
    
    def analyze_with_gemini(self, errors: List[Dict[str, Any]], limit: int = 20) -> Dict[str, Any]:
        """
        Analiza errores usando Gemini para obtener insights más profundos.
        
        Args:
            errors: Lista de errores a analizar
            limit: Número máximo de errores a analizar (para no exceder límites)
            
        Returns:
            Diccionario con análisis de Gemini
        """
        if not errors:
            return {
                "analysis": "No hay errores para analizar",
                "suggestions": []
            }
        
        # Limitar número de errores para análisis
        errors_to_analyze = errors[:limit]
        
        # Preparar contexto para Gemini
        error_summary = self._prepare_error_summary(errors_to_analyze)
        
        # Prompt para Gemini
        prompt = f"""
Analiza los siguientes errores de extracción OCR y proporciona recomendaciones específicas para mejorar la precisión.

ERRORES ENCONTRADOS:
{error_summary}

Por favor, analiza:
1. Patrones comunes en los errores
2. Causas probables de los errores
3. Sugerencias específicas para mejorar el prompt de OCR
4. Sugerencias para mejorar la lógica de extracción de campos

Responde en formato JSON con esta estructura:
{{
    "patterns": ["patrón 1", "patrón 2", ...],
    "root_causes": ["causa 1", "causa 2", ...],
    "prompt_improvements": ["mejora 1", "mejora 2", ...],
    "extraction_improvements": ["mejora 1", "mejora 2", ...],
    "recommendations": ["recomendación 1", "recomendación 2", ...]
}}
"""
        
        try:
            # Usar Gemini para analizar
            response = self.gemini_service.model.generate_content(prompt)
            
            if response and response.text:
                # Intentar parsear JSON de la respuesta
                text = response.text.strip()
                
                # Limpiar markdown si existe
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
                
                # Parsear JSON
                try:
                    analysis = json.loads(text)
                except json.JSONDecodeError:
                    # Si no es JSON válido, crear estructura manual
                    analysis = {
                        "analysis_text": text,
                        "patterns": [],
                        "root_causes": [],
                        "prompt_improvements": [],
                        "extraction_improvements": [],
                        "recommendations": []
                    }
                
                # Guardar análisis
                self._save_analysis(analysis, errors_to_analyze)
                
                return analysis
            else:
                return {
                    "error": "No se pudo obtener análisis de Gemini",
                    "suggestions": []
                }
        
        except Exception as e:
            return {
                "error": f"Error al analizar con Gemini: {str(e)}",
                "suggestions": []
            }
    
    def _prepare_error_summary(self, errors: List[Dict[str, Any]]) -> str:
        """Prepara un resumen de errores para Gemini."""
        summary_lines = []
        
        for i, error in enumerate(errors[:10], 1):  # Primeros 10 errores
            error_type = error.get("error_type", "unknown")
            error_message = error.get("error_message", "")
            field_name = error.get("context", {}).get("field_name", "N/A")
            pdf_name = error.get("pdf_name", "unknown")
            ocr_preview = error.get("ocr_text_preview", "")[:200]  # Primeros 200 chars
            
            summary_lines.append(f"""
Error #{i}:
- Tipo: {error_type}
- Campo: {field_name}
- Mensaje: {error_message}
- PDF: {pdf_name}
- OCR Preview: {ocr_preview[:200]}...
""")
        
        return "\n".join(summary_lines)
    
    def _save_analysis(self, analysis: Dict[str, Any], errors: List[Dict[str, Any]]):
        """Guarda el análisis generado."""
        analysis_file = self.suggestions_folder / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        analysis_data = {
            "analysis": analysis,
            "errors_analyzed": len(errors),
            "analyzed_at": datetime.now().isoformat(),
            "errors": errors
        }
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
    
    def suggest_prompt_improvement(self, analysis: Dict[str, Any], current_prompt: str) -> Optional[str]:
        """
        Sugiere una mejora al prompt basada en el análisis.
        
        Args:
            analysis: Análisis de errores
            current_prompt: Prompt actual
            
        Returns:
            Nuevo prompt sugerido o None
        """
        prompt_improvements = analysis.get("prompt_improvements", [])
        
        if not prompt_improvements:
            return None
        
        # Crear prompt mejorado basado en sugerencias
        # Por ahora, retornar el prompt actual con mejoras agregadas
        improved_prompt = current_prompt
        
        # Agregar mejoras como comentarios o secciones adicionales
        improvements_text = "\n\n".join([f"- {imp}" for imp in prompt_improvements])
        
        improved_prompt += f"""

IMPROVEMENTS BASED ON ERROR ANALYSIS:
{improvements_text}
"""
        
        return improved_prompt

