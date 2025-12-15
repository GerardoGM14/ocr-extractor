"""
API Models - Modelos Pydantic para requests y responses
Responsabilidad: Definir estructura de datos de la API
"""

from pydantic import BaseModel, EmailStr, Field, validator
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


class DeleteUploadResponse(BaseModel):
    """Respuesta al eliminar un PDF subido."""
    success: bool
    message: str
    file_id: str
    filename: Optional[str] = None


class PageResult(BaseModel):
    """Resultado de procesamiento de una página."""
    page_number: int
    json_1_raw: Dict[str, Any]
    json_2_structured: Dict[str, Any]


class ProcessPDFResponse(BaseModel):
    """Respuesta del endpoint de procesamiento (ahora asíncrono)."""
    success: bool
    request_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    message: str
    metadata: Optional[Dict[str, Any]] = None
    pdf_info: Optional[Dict[str, Any]] = None
    results: Optional[List[PageResult]] = None  # Solo disponible cuando status="completed"
    files_saved: Optional[List[Dict[str, str]]] = None
    processing_time_seconds: Optional[float] = None
    download_url: Optional[str] = None
    excel_download_url: Optional[str] = None
    error: Optional[str] = None


class ProcessStatusResponse(BaseModel):
    """Respuesta del estado de procesamiento."""
    success: bool
    request_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    progress: int  # 0-100
    message: str
    pages_processed: Optional[int] = None
    processing_time: Optional[float] = None
    download_url: Optional[str] = None
    excel_download_url: Optional[str] = None
    error: Optional[str] = None


class BatchJobInfo(BaseModel):
    """Información de un job en el batch."""
    file_id: str
    request_id: str
    status: str  # "queued" | "processing"
    message: str


class BatchProcessRequest(BaseModel):
    """Request para procesar múltiples PDFs en batch."""
    file_ids: List[str] = Field(..., description="Lista de file_ids a procesar", min_items=1)
    save_files: bool = Field(default=True, description="Guardar archivos en disco")
    output_folder: str = Field(default="api", description="Subcarpeta de salida")
    periodo_id: Optional[str] = Field(default=None, description="ID del periodo para asociar los archivos procesados")


class ProcessSelectedRequest(BaseModel):
    """Request para procesar archivos seleccionados de un periodo."""
    file_ids: List[str] = Field(..., description="Lista de file_ids (request_ids) a procesar", min_items=1)


class BatchProcessResponse(BaseModel):
    """Respuesta del procesamiento batch."""
    success: bool
    total: int
    procesados: int
    jobs: List[BatchJobInfo]
    errores: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None  # Mensaje adicional (ej: "No hay archivos pendientes")


class TokenUsageStats(BaseModel):
    """Estadísticas de uso de tokens."""
    input_tokens_estimated: int
    output_tokens_estimated: int
    total_tokens_estimated: int
    input_tokens_actual: Optional[int] = None  # Si Gemini retorna usage_metadata
    output_tokens_actual: Optional[int] = None
    total_tokens_actual: Optional[int] = None
    prompt_length_chars: int
    response_length_chars: int
    image_size_bytes: int
    image_dimensions: Optional[Dict[str, int]] = None


class PageTokenStats(BaseModel):
    """Estadísticas de tokens por página."""
    page_number: int
    token_stats: TokenUsageStats
    processing_time_seconds: float
    error: Optional[str] = None


class TokenTestResponse(BaseModel):
    """Respuesta del endpoint de prueba de tokens."""
    success: bool
    filename: str
    total_pages: int
    pages_processed: int  # Número de páginas procesadas (1 o todas)
    page_stats: List[PageTokenStats]  # Estadísticas por página
    total_token_stats: TokenUsageStats  # Suma total de todas las páginas
    total_processing_time_seconds: float
    model_used: str
    max_output_tokens: int
    error: Optional[str] = None


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


# ===== Auth Models =====

class LoginRequest(BaseModel):
    """Request para login."""
    email: EmailStr = Field(..., description="Email del usuario para autenticación")
    password: str = Field(..., description="Contraseña del usuario (requerida)")


class LoginResponse(BaseModel):
    """Respuesta del login."""
    success: bool
    token: Optional[str] = None
    email: str
    nombre: str  # Nombre formateado extraído del email (ej: "victor.cabeza@newmont.com" -> "Victor Cabeza")
    message: str
    expires_at: Optional[str] = None  # ISO format datetime
    fuente_validacion: Optional[str] = None  # "BD" o "JSON" - indica qué fuente se usó para validar
    role: Optional[str] = None  # "admin" o "user" - rol del usuario


# ===== User Management Models =====

class UserInfo(BaseModel):
    """Información de un usuario."""
    email: str
    nombre: str
    role: str  # "admin" o "user"
    status: str  # "active" o "inactive"
    ultima_edicion: Optional[str] = None


class UserCreateRequest(BaseModel):
    """Request para crear un usuario."""
    email: EmailStr
    nombre: str = Field(..., min_length=1)
    password: Optional[str] = None  # Si no se proporciona, se genera automáticamente
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdateRequest(BaseModel):
    """Request para actualizar un usuario."""
    nombre: Optional[str] = None
    password: Optional[str] = None  # Para cambiar contraseña propia
    avatar_url: Optional[str] = None


class UserUpdateByAdminRequest(BaseModel):
    """Request para actualizar un usuario (solo admin)."""
    nombre: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class UserPasswordResetRequest(BaseModel):
    """Request para restaurar contraseña de un usuario (solo admin)."""
    new_password: Optional[str] = None  # Si no se proporciona, se genera automáticamente


class UsersListResponse(BaseModel):
    """Respuesta de lista de usuarios."""
    success: bool
    users: List[UserInfo]
    total: int


class UserResponse(BaseModel):
    """Respuesta de operación de usuario."""
    success: bool
    message: str
    user: Optional[UserInfo] = None
    new_password: Optional[str] = None


class LogoutRequest(BaseModel):
    """Request para logout."""
    token: Optional[str] = Field(None, description="Token a invalidar (opcional si se envía en header)")


class LogoutResponse(BaseModel):
    """Respuesta del logout."""
    success: bool
    message: str


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


class BulkExportRequest(BaseModel):
    """Request para exportar múltiples archivos por request_id."""
    request_ids: List[str] = Field(..., description="Array de request_ids a exportar", min_items=1)


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
    estado: str  # "vacio" | "pendiente" | "procesando" | "procesado" | "subiendo" | "cerrado"
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
    file_size_bytes: Optional[int] = None
    uploaded_at: Optional[str] = None


class CreatePeriodoRequest(BaseModel):
    """Request para crear un periodo."""
    periodo: str = Field(..., min_length=1, description="Periodo en formato MM/AAAA (ej: '10/2025')")
    tipo: str = Field(..., description="Tipo de periodo: 'onshore' o 'offshore'")
    
    @validator('periodo')
    def periodo_not_empty(cls, v):
        """Valida que el periodo no esté vacío o solo contenga espacios."""
        if not v or not v.strip():
            raise ValueError('Debe agregar un periodo correctamente')
        return v.strip()
    
    @validator('tipo')
    def tipo_valid(cls, v):
        """Valida que el tipo sea válido."""
        if not v or not v.strip():
            raise ValueError('El campo "Tipo" es obligatorio')
        v_lower = v.strip().lower()
        if v_lower not in ["onshore", "offshore"]:
            raise ValueError('El tipo debe ser "onshore" o "offshore"')
        return v_lower


class PeriodoResponse(BaseModel):
    """Respuesta de un periodo."""
    success: bool
    periodo: PeriodoInfo


class PeriodosListResponse(BaseModel):
    """Lista de periodos."""
    success: bool
    totalPeriodos: int  # Total de periodos (sin paginación)
    paginas: int  # Total de páginas
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
    # Campos adicionales para OnShore (opcionales)
    job_no: Optional[str] = None
    wages: Optional[float] = None
    expatriate_allowances: Optional[float] = None
    multiplier: Optional[float] = None
    odc: Optional[float] = None
    epp: Optional[float] = None
    total_hours: Optional[float] = None  # Alias para total_horas en OnShore


class PeriodoResumenPSResponse(BaseModel):
    """Resumen PS de un periodo."""
    success: bool
    periodo_id: str
    tipo: str
    items: List[PeriodoResumenPSItem]
    total: int


# ===== Maestros Models =====

class ApartadoInfo(BaseModel):
    """Información de un apartado (concepto)."""
    id: str = Field(..., description="ID único del apartado")
    nombre: str = Field(..., description="Nombre del concepto a identificar")
    orden: int = Field(..., description="Orden del apartado", ge=0)


class MaestrosSaveRequest(BaseModel):
    """Request para guardar apartados."""
    apartados: List[ApartadoInfo] = Field(..., description="Lista de apartados a guardar")


class MaestrosResponse(BaseModel):
    """Respuesta de los endpoints de maestros."""
    success: bool
    apartados: List[ApartadoInfo]
    message: Optional[str] = None