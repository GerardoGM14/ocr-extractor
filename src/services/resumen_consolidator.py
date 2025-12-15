"""
Resumen Consolidator - Servicio para consolidar resúmenes PS
Responsabilidad: Consolidar datos de JSONs estructurados en resúmenes PS (OnShore/OffShore)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict
from decimal import Decimal

logger = logging.getLogger(__name__)


class ResumenConsolidator:
    """
    Servicio para consolidar resúmenes PS desde JSONs estructurados.
    """
    
    def __init__(self, output_folder: Optional[Path] = None):
        """
        Inicializa el consolidador.
        
        Args:
            output_folder: Carpeta base de salida (default: ./output)
        """
        if output_folder is None:
            output_folder = Path("./output")
        self.output_folder = output_folder
        self.consolidated_folder = output_folder / "consolidated"
        self.consolidated_folder.mkdir(parents=True, exist_ok=True)
    
    def consolidate_periodo(
        self,
        periodo_id: str,
        periodo_tipo: str,
        request_ids: List[str],
        structured_folder: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Consolida el resumen PS de un periodo desde los JSONs estructurados.
        
        Args:
            periodo_id: ID del periodo
            periodo_tipo: "onshore" | "offshore"
            request_ids: Lista de request_ids asociados al periodo
            structured_folder: Carpeta donde están los JSONs estructurados (default: output/api/structured)
            
        Returns:
            Diccionario con el resumen consolidado
        """
        # Leer todos los JSONs estructurados del periodo desde carpetas específicas por request_id
        json_data_list = []
        for request_id in request_ids:
            # Para batch jobs, extraer el request_id maestro (antes de _batch_)
            request_id_to_search = request_id
            if "_batch_" in request_id:
                request_id_to_search = request_id.split("_batch_")[0]
            
            # Truncar request_id para buscar en la carpeta (mismo truncamiento que al crear)
            # Función helper para truncar (mismo que en main.py)
            def truncate_request_id_for_folder(req_id: str, max_length: int = 30) -> str:
                if len(req_id) <= max_length:
                    return req_id
                return req_id[:max_length]
            
            request_id_folder = truncate_request_id_for_folder(request_id_to_search)
            
            # Buscar en la carpeta específica por request_id: output/api/{request_id}/structured/
            structured_folder = self.output_folder / "api" / request_id_folder / "structured"
            
            if not structured_folder.exists():
                logger.warning(f"Carpeta de JSONs estructurados no existe: {structured_folder}")
                continue
            
            # Buscar todos los JSONs en esta carpeta específica
            json_files = list(structured_folder.glob("*_structured.json"))
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    json_data_list.append(json_data)
                except Exception as e:
                    logger.error(f"Error leyendo {json_file}: {e}")
                    continue
        
        if not json_data_list:
            logger.warning(f"No se encontraron JSONs estructurados para el periodo {periodo_id}")
            return self._create_empty_consolidado(periodo_id, periodo_tipo)
        
        # Consolidar datos
        if periodo_tipo.lower() == "onshore":
            items = self._consolidate_onshore(json_data_list)
        else:
            items = self._consolidate_offshore(json_data_list)
        
        # Calcular totales generales
        total_us = sum(item.get("total_us", 0) for item in items)
        total_horas = sum(item.get("total_horas", 0) for item in items) if periodo_tipo.lower() == "offshore" else sum(item.get("total_hours", 0) for item in items)
        
        consolidado = {
            "periodo_id": periodo_id,
            "tipo": periodo_tipo.lower(),
            "ultima_actualizacion": datetime.now().isoformat(),
            "archivos_procesados": request_ids,
            "resumen_ps": {
                periodo_tipo.lower(): items
            },
            "totales_generales": {
                "total_us": float(total_us),
                "total_horas": float(total_horas)
            }
        }
        
        # Guardar consolidado
        self._save_consolidado(periodo_id, consolidado)
        
        return consolidado
    
    def _find_json_files_for_request(self, structured_folder: Path, request_id: str) -> List[Path]:
        """
        Encuentra todos los JSONs estructurados para un request_id.
        NOTA: Este método ya no se usa, pero se mantiene por compatibilidad.
        Los JSONs ahora se buscan directamente en carpetas específicas por request_id.
        """
        # Este método ya no se usa, pero se mantiene por compatibilidad
        json_files = []
        if structured_folder.exists():
            for json_file in structured_folder.glob("*_structured.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    metadata = json_data.get("metadata", {})
                    if metadata.get("request_id") == request_id:
                        json_files.append(json_file)
                except Exception:
                    continue
        return json_files
    
    def _consolidate_onshore(self, json_data_list: List[Dict]) -> List[Dict]:
        """
        Consolida datos para OnShore.
        Agrupa por: job_no + department + discipline
        """
        # Agrupar por job_no + department + discipline
        grouped = defaultdict(lambda: {
            "job_no": None,
            "department": None,
            "discipline": None,
            "wages": Decimal("0"),
            "expatriate_allowances": Decimal("0"),
            "odc": Decimal("0"),
            "epp": Decimal("0"),
            "total_us": Decimal("0"),
            "total_hours": Decimal("0"),
            "multiplier": None
        })
        
        for json_data in json_data_list:
            # Las tablas ahora están en el nivel raíz, no en additional_data
            
            # Extraer mcomprobante para total_us
            mcomprobante = json_data.get("mcomprobante", [])
            for comp in mcomprobante:
                if isinstance(comp, dict):
                    precio_total = comp.get("nPrecioTotal") or comp.get("precioTotal")
                    if precio_total:
                        # Necesitamos asociar este comprobante a un job_no, department, discipline
                        # Buscar en mresumen para encontrar el job_no asociado
                        pass
            
            # Extraer mresumen para cost breakdowns
            mresumen = json_data.get("mresumen", [])
            for resumen in mresumen:
                if isinstance(resumen, dict):
                    job_no = resumen.get("tjobno") or resumen.get("job_no")
                    n_importe = resumen.get("nImporte", 0)
                    
                    # Buscar department y discipline desde mdepartamento y mdisciplina
                    department = self._extract_department(json_data)
                    discipline = self._extract_discipline(json_data)
                    
                    if not job_no:
                        # Si no hay job_no, usar un valor por defecto o el primer job_no encontrado
                        job_no = "UNKNOWN"
                    
                    key = f"{job_no}|{department}|{discipline}"
                    
                    # Sumar total_us
                    if n_importe:
                        grouped[key]["total_us"] += Decimal(str(n_importe))
                    
                    # Extraer campos OnShore desde mresumen
                    wages = resumen.get("_wages") or 0
                    expat_allowances = resumen.get("_expatriate_allowances") or 0
                    odc = resumen.get("_odc") or 0
                    epp = resumen.get("_epp") or 0
                    multiplier = resumen.get("_multiplier")
                    
                    if wages:
                        grouped[key]["wages"] += Decimal(str(wages))
                    if expat_allowances:
                        grouped[key]["expatriate_allowances"] += Decimal(str(expat_allowances))
                    if odc:
                        grouped[key]["odc"] += Decimal(str(odc))
                    if epp:
                        grouped[key]["epp"] += Decimal(str(epp))
                    if multiplier and not grouped[key]["multiplier"]:
                        grouped[key]["multiplier"] = multiplier
                    
                    # Guardar job_no, department, discipline
                    if not grouped[key]["job_no"]:
                        grouped[key]["job_no"] = job_no
                    if not grouped[key]["department"]:
                        grouped[key]["department"] = department
                    if not grouped[key]["discipline"]:
                        grouped[key]["discipline"] = discipline
            
            # Extraer mjornada para total_hours
            mjornada = json_data.get("mjornada", [])
            for jornada in mjornada:
                if isinstance(jornada, dict):
                    total_horas = jornada.get("nTotalHoras") or jornada.get("nHoras") or 0
                    if total_horas:
                        # Asociar horas a job_no, department, discipline
                        # Por ahora, sumar a todos los grupos (esto se puede mejorar)
                        for key in grouped:
                            grouped[key]["total_hours"] += Decimal(str(total_horas))
        
        # Convertir a lista y formatear
        items = []
        for key, data in grouped.items():
            items.append({
                "job_no": data["job_no"] or "---",
                "department": data["department"] or "---",
                "discipline": data["discipline"] or "---",
                "wages": float(data["wages"]),
                "expatriate_allowances": float(data["expatriate_allowances"]),
                "odc": float(data["odc"]),
                "epp": float(data["epp"]),
                "multiplier": data["multiplier"] or 0,
                "total_us": float(data["total_us"]),
                "total_hours": float(data["total_hours"])
            })
        
        return items
    
    def _consolidate_offshore(self, json_data_list: List[Dict]) -> List[Dict]:
        """
        Consolida datos para OffShore.
        Agrupa por: department + discipline
        """
        # Agrupar por department + discipline
        grouped = defaultdict(lambda: {
            "department": None,
            "discipline": None,
            "total_us": Decimal("0"),
            "total_horas": Decimal("0"),
            "ratios_edp": Decimal("0")
        })
        
        for json_data in json_data_list:
            # Las tablas ahora están en el nivel raíz, no en additional_data
            
            # Extraer department y discipline
            department = self._extract_department(json_data)
            discipline = self._extract_discipline(json_data)
            
            # Si no se encontró department o discipline, intentar desde múltiples fuentes
            if department == "---" or discipline == "---":
                # Intentar desde mdepartamento y mdisciplina completos
                # Nota: Estos catálogos pueden estar en catalogos dentro de mcomprobante_detalle
                # Por ahora, intentar leerlos del nivel raíz si existen (compatibilidad)
                mdepartamento = json_data.get("mdepartamento", [])
                mdisciplina = json_data.get("mdisciplina", [])
                
                if mdepartamento and isinstance(mdepartamento, list):
                    for dept in mdepartamento:
                        if isinstance(dept, dict):
                            dept_name = dept.get("tDepartamento")
                            if dept_name and dept_name != "---":
                                department = dept_name
                                break
                
                if mdisciplina and isinstance(mdisciplina, list):
                    for disc in mdisciplina:
                        if isinstance(disc, dict):
                            disc_name = disc.get("tDisciplina")
                            if disc_name and disc_name != "---":
                                discipline = disc_name
                                break
            
            # Si aún no hay department/discipline, usar valores por defecto
            if department == "---":
                department = "Other Services"  # Default para OffShore
            if discipline == "---":
                discipline = "Other Services"  # Default para OffShore
            
            key = f"{department}|{discipline}"
            
            # Extraer mcomprobante para total_us
            mcomprobante = json_data.get("mcomprobante", [])
            for comp in mcomprobante:
                if isinstance(comp, dict):
                    precio_total = comp.get("nPrecioTotal") or comp.get("precioTotal")
                    if precio_total:
                        grouped[key]["total_us"] += Decimal(str(precio_total))
            
            # Extraer mjornada para total_horas
            mjornada = json_data.get("mjornada", [])
            for jornada in mjornada:
                if isinstance(jornada, dict):
                    total_horas = jornada.get("nTotalHoras") or jornada.get("nHoras") or 0
                    if total_horas:
                        grouped[key]["total_horas"] += Decimal(str(total_horas))
            
            # Guardar department y discipline (usar el primero encontrado si hay múltiples)
            if not grouped[key]["department"] or grouped[key]["department"] == "---":
                grouped[key]["department"] = department
            if not grouped[key]["discipline"] or grouped[key]["discipline"] == "---":
                grouped[key]["discipline"] = discipline
        
        # Calcular ratios y convertir a lista
        items = []
        for key, data in grouped.items():
            total_horas = data["total_horas"]
            total_us = data["total_us"]
            ratios_edp = (total_us / total_horas) if total_horas > 0 else Decimal("0")
            
            items.append({
                "department": data["department"] or "---",
                "discipline": data["discipline"] or "---",
                "total_us": float(total_us),
                "total_horas": float(total_horas),
                "ratios_edp": float(ratios_edp)
            })
        
        return items
    
    def _extract_department(self, json_data: Dict) -> str:
        """Extrae el department desde mdepartamento o infiere desde el documento."""
        # Las tablas ahora están en el nivel raíz
        # Nota: mdepartamento puede estar en catalogos dentro de mcomprobante_detalle
        # Por ahora, intentar leerlo del nivel raíz si existe (compatibilidad)
        mdepartamento = json_data.get("mdepartamento", [])
        
        # Buscar en todos los departamentos extraídos
        if mdepartamento and isinstance(mdepartamento, list):
            for dept in mdepartamento:
                if isinstance(dept, dict):
                    dept_name = dept.get("tDepartamento")
                    if dept_name and dept_name != "---":
                        return dept_name
        
        # Si no hay department explícito, intentar inferir desde onshore_offshore
        onshore_offshore = json_data.get("onshore_offshore", "").lower()
        if onshore_offshore == "offshore":
            # Para OffShore, los departamentos principales son Engineering y Other Services
            # Intentar inferir desde mresumen o mcomprobante_detalle
            mresumen = json_data.get("mresumen", [])
            mcomprobante_detalle = json_data.get("mcomprobante_detalle", [])
            
            # Buscar pistas en las descripciones
            all_text = ""
            for item in mresumen + mcomprobante_detalle:
                if isinstance(item, dict):
                    desc = str(item.get("tdescription", "")).lower() + " " + str(item.get("tDescripcion", "")).lower()
                    all_text += desc + " "
            
            # Inferir department basado en palabras clave
            if any(keyword in all_text for keyword in ["engineering", "civil", "structural", "electrical", "mechanical", "pipeline", "tanks", "control systems", "plant design", "piping", "materials engineering"]):
                return "Engineering"
            else:
                return "Other Services"
        
        return "---"
    
    def _extract_discipline(self, json_data: Dict) -> str:
        """Extrae el discipline desde mdisciplina o infiere desde el documento."""
        # Las tablas ahora están en el nivel raíz
        # Nota: mdisciplina puede estar en catalogos dentro de mcomprobante_detalle
        # Por ahora, intentar leerlo del nivel raíz si existe (compatibilidad)
        mdisciplina = json_data.get("mdisciplina", [])
        
        # Buscar en todas las disciplinas extraídas
        if mdisciplina and isinstance(mdisciplina, list):
            for disc in mdisciplina:
                if isinstance(disc, dict):
                    disc_name = disc.get("tDisciplina")
                    if disc_name and disc_name != "---":
                        return disc_name
        
        # Si no hay discipline explícito, intentar inferir desde onshore_offshore
        onshore_offshore = json_data.get("onshore_offshore", "").lower()
        if onshore_offshore == "offshore":
            # Para OffShore, intentar inferir desde mresumen o mcomprobante_detalle
            mresumen = json_data.get("mresumen", [])
            mcomprobante_detalle = json_data.get("mcomprobante_detalle", [])
            
            # Buscar pistas en las descripciones
            all_text = ""
            for item in mresumen + mcomprobante_detalle:
                if isinstance(item, dict):
                    desc = str(item.get("tdescription", "")).lower() + " " + str(item.get("tDescripcion", "")).lower()
                    all_text += desc + " "
            
            # Mapeo de palabras clave a disciplinas OffShore
            discipline_keywords = {
                "Civil/Structural/Architectural Engineering": ["civil", "structural", "architectural", "building design", "civil works"],
                "Control Systems Engineering": ["control systems", "scada", "automation systems", "instrumentation", "control engineering"],
                "Electrical Engineering": ["electrical", "power systems", "electrical design", "electrical systems"],
                "Engineering Automation": ["engineering automation", "automated systems", "automation engineering"],
                "Engineering Management": ["engineering management", "project engineering", "engineering coordination"],
                "G&HES": ["g&hes", "geotechnical", "health environmental safety"],
                "Materials Engineering Technology": ["materials engineering", "materials technology", "material science", "materials testing"],
                "Mechanical Engineering": ["mechanical", "mechanical systems", "mechanical design", "mechanical equipment"],
                "Pipeline Engineering": ["pipeline", "pipeline design", "pipeline systems", "pipeline construction"],
                "Plant Design & Piping": ["plant design", "piping", "piping design", "piping systems", "plant layout"],
                "Tanks Engineering": ["tanks", "tank design", "storage tanks", "tank systems"],
                "Admin Support/F&A": ["admin support", "f&a", "finance", "accounting", "administrative"],
                "BEO": ["beo", "business engineering operations"],
                "Constructability": ["constructability", "construction support", "construction engineering"],
                "Contracts": ["contracts", "contract management", "contract administration"],
                "ES&H": ["es&h", "environmental safety health", "ehs", "safety environmental"],
                "Field Engineering": ["field engineering", "field support", "field services", "on-site engineering"],
                "IS&T": ["is&t", "information systems", "information technology", "it services", "systems technology"],
                "Off Project Support": ["off project support", "non-project support", "general support"],
                "Procurement": ["procurement", "purchasing", "supply chain", "material acquisition"],
                "Project Controls": ["project controls", "project planning", "scheduling", "cost control"],
                "Project Management": ["project management", "project coordination", "project oversight"],
                "Quality Assurance": ["quality assurance", "qa", "quality control", "quality management"],
                "Tanks Business Line Support": ["tanks business line", "tanks support", "business line support"],
                "Workforce Services": ["workforce services", "human resources", "hr services", "workforce management", "staffing"]
            }
            
            # Buscar la disciplina que mejor coincida
            best_match = None
            max_matches = 0
            for discipline, keywords in discipline_keywords.items():
                matches = sum(1 for keyword in keywords if keyword in all_text)
                if matches > max_matches:
                    max_matches = matches
                    best_match = discipline
            
            if best_match:
                return best_match
        
        return "---"
    
    def _create_empty_consolidado(self, periodo_id: str, periodo_tipo: str) -> Dict[str, Any]:
        """Crea un consolidado vacío."""
        return {
            "periodo_id": periodo_id,
            "tipo": periodo_tipo.lower(),
            "ultima_actualizacion": datetime.now().isoformat(),
            "archivos_procesados": [],
            "resumen_ps": {
                periodo_tipo.lower(): []
            },
            "totales_generales": {
                "total_us": 0.0,
                "total_horas": 0.0
            }
        }
    
    def _save_consolidado(self, periodo_id: str, consolidado: Dict[str, Any]):
        """Guarda el consolidado en un archivo JSON."""
        filename = f"resumen_ps_{periodo_id}.json"
        filepath = self.consolidated_folder / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(consolidado, f, ensure_ascii=False, indent=2)
            logger.info(f"Consolidado guardado: {filepath}")
        except Exception as e:
            logger.error(f"Error guardando consolidado {filepath}: {e}")
            raise
    
    def load_consolidado(self, periodo_id: str) -> Optional[Dict[str, Any]]:
        """Carga un consolidado desde el archivo."""
        filename = f"resumen_ps_{periodo_id}.json"
        filepath = self.consolidated_folder / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando consolidado {filepath}: {e}")
            return None

