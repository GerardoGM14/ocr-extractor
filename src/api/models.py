"""
API Models - Modelos Pydantic para requests y responses
Responsabilidad: Definir estructura de datos de la API
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any, List, Optional
from datetime import datetime


class UploadPDFResponse(BaseModel):
    """Respuesta del endpoint de upload."""
    success: bool
    file_id: str
    filename: str
    uploaded_at: datetime
    metadata: Dict[str, Any]
    file_size_bytes: int


class PageResult(BaseModel):
    """Resultado de procesamiento de una página."""
    page_number: int
    json_1_raw: Dict[str, Any]
    json_2_structured: Dict[str, Any]


class ProcessPDFResponse(BaseModel):
    """Respuesta del endpoint de procesamiento."""
    success: bool
    request_id: str
    metadata: Dict[str, Any]
    pdf_info: Dict[str, Any]
    results: List[PageResult]
    files_saved: Optional[List[Dict[str, str]]] = None
    processing_time_seconds: float
    download_url: Optional[str] = None
    excel_download_url: Optional[str] = None  # URL para descargar el Excel consolidado
    error: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "request_id": "abc123-def456-ghi789",
                "metadata": {
                    "email": "usuario@ejemplo.com",
                    "year": 2024,
                    "month": "Marzo",
                    "processed_at": "2024-01-15T10:30:00Z"
                },
                "pdf_info": {
                    "filename": "documento.pdf",
                    "total_pages": 5,
                    "pages_processed": 5
                },
                "results": [],
                "files_saved": [
                    {"type": "raw", "path": "output/api/documento_page_1_raw.json"},
                    {"type": "structured", "path": "output/api/documento_page_1_structured.json"}
                ],
                "processing_time_seconds": 45.2,
                "download_url": "/public/documento_20240115_103000_abc12345.zip"
            }
        }


class ErrorResponse(BaseModel):
    """Respuesta de error."""
    success: bool = False
    request_id: str
    error: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Respuesta de health check."""
    status: str
    version: str
    timestamp: datetime


class UploadedFileInfo(BaseModel):
    """Información de un archivo subido."""
    file_id: str
    filename: str
    uploaded_at: str
    file_size_bytes: int
    metadata: Dict[str, Any]
    processed: bool = False
    processed_at: Optional[str] = None
    download_url: Optional[str] = None
    request_id: Optional[str] = None
    excel_download_url: Optional[str] = None  # URL para descargar el Excel consolidado


class UploadedFilesResponse(BaseModel):
    """Respuesta con lista de archivos subidos."""
    success: bool
    total: int
    files: List[UploadedFileInfo]


class ProcessedFilesResponse(BaseModel):
    """Respuesta con lista de archivos procesados."""
    success: bool
    total: int
    files: List[UploadedFileInfo]


# ===== Learning System Models =====

class ErrorInfo(BaseModel):
    """Información de un error registrado."""
    error_id: str
    timestamp: str
    pdf_name: str
    page_number: int
    error_type: str
    error_message: str
    field_name: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ErrorsSummaryResponse(BaseModel):
    """Resumen de errores registrados."""
    success: bool
    total_errors: int
    error_types: Dict[str, int]
    most_common_fields: Dict[str, int]
    recent_errors: List[ErrorInfo]


class ErrorsResponse(BaseModel):
    """Respuesta con lista de errores."""
    success: bool
    total: int
    errors: List[ErrorInfo]


class AnalysisResponse(BaseModel):
    """Respuesta del análisis de errores."""
    success: bool
    analysis: Dict[str, Any]
    patterns: List[Dict[str, Any]]
    suggestions: List[Dict[str, Any]]
    analyzed_at: str
    total_errors_analyzed: int


class PromptVersionInfo(BaseModel):
    """Información de una versión de prompt."""
    version: int
    created_at: str
    description: str
    improvements: List[str]
    source: Optional[str] = None


class PromptsResponse(BaseModel):
    """Respuesta con información de prompts."""
    success: bool
    current_version: PromptVersionInfo
    history: List[PromptVersionInfo]


class ApplyPromptResponse(BaseModel):
    """Respuesta al aplicar nuevo prompt."""
    success: bool
    new_version: int
    message: str


# ===== Dashboard Models =====

class DashboardStatsResponse(BaseModel):
    """Estadísticas globales del dashboard."""
    success: bool
    monto_total_global: float
    total_horas_global: float
    currency: str = "USD"


class DepartamentoItem(BaseModel):
    """Item de departamento."""
    label: str
    value: float


class DisciplinaItem(BaseModel):
    """Item de disciplina."""
    label: str
    value: float


class AnalyticsItem(BaseModel):
    """Item de análisis (Off-Shore/On-Shore)."""
    total_gasto: float
    total_horas: float
    total_disciplinas: int
    distribucion_departamento: List[DepartamentoItem]  # [{"label": "Engineering", "value": 850000.00}, ...]
    top_5_disciplinas: List[DisciplinaItem]  # [{"label": "Procurement", "value": 1800.00}, ...]


class DashboardAnalyticsResponse(BaseModel):
    """Análisis Off-Shore y On-Shore."""
    success: bool
    offshore: Optional[AnalyticsItem] = None
    onshore: Optional[AnalyticsItem] = None


class RejectedConcept(BaseModel):
    """Concepto rechazado."""
    concepto: str
    cantidad_total: int
    monto_total: float
    porcentaje_total: float


class RejectedConceptsResponse(BaseModel):
    """Lista de conceptos rechazados."""
    success: bool
    total: int
    concepts: List[RejectedConcept]


# ===== Periodos Models =====

class PeriodoInfo(BaseModel):
    """Información de un periodo."""
    periodo_id: str
    periodo: str  # "10/2025"
    tipo: str  # "onshore" | "offshore"
    estado: str  # "procesado" | "vacio" | "pendiente" | "procesando" | "cerrado"
    registros: int
    ultimo_procesamiento: Optional[str] = None
    created_at: str


class PeriodoArchivoInfo(BaseModel):
    """Información de un archivo dentro de un periodo."""
    archivo_id: str
    request_id: str
    filename: str
    estado: str  # "procesado" | "pendiente" | "procesando"
    job_no: Optional[str] = None
    type: Optional[str] = None
    source_reference: Optional[str] = None
    source_ref_id: Optional[str] = None
    entered_curr: Optional[str] = None
    entered_amount: Optional[float] = None
    total_usd: Optional[float] = None
    fecha_valoracion: Optional[str] = None
    processed_at: Optional[str] = None


class CreatePeriodoRequest(BaseModel):
    """Request para crear un periodo."""
    periodo: str  # "10/2025" formato MM/AAAA
    tipo: str  # "onshore" | "offshore"


class PeriodoResponse(BaseModel):
    """Respuesta de un periodo."""
    success: bool
    periodo: PeriodoInfo


class PeriodosListResponse(BaseModel):
    """Lista de periodos."""
    success: bool
    total: int
    periodos: List[PeriodoInfo]


class PeriodoDetailResponse(BaseModel):
    """Detalle completo de un periodo."""
    success: bool
    periodo: PeriodoInfo
    archivos: List[PeriodoArchivoInfo]
    total_archivos: int


class PeriodoResumenPSItem(BaseModel):
    """Item del resumen PS."""
    department: str
    discipline: str
    total_us: float
    total_horas: float
    ratios_edp: float


class PeriodoResumenPSResponse(BaseModel):
    """Resumen PS de un periodo."""
    success: bool
    periodo_id: str
    tipo: str
    items: List[PeriodoResumenPSItem]
    total: int