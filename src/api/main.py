"""
API Main - FastAPI application principal
Responsabilidad: Endpoints REST para procesamiento OCR
"""

import os
import sys
import time
import uuid
import tempfile
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.requests import Request

from .models import (
    ProcessPDFResponse,
    ProcessStatusResponse,
    ErrorResponse,
    HealthResponse,
    PageResult,
    UploadPDFResponse,
    UploadedFilesResponse,
    ProcessedFilesResponse,
    UploadedFileInfo,
    ErrorsResponse,
    ErrorsSummaryResponse,
    AnalysisResponse,
    PromptsResponse,
    ApplyPromptResponse,
    ErrorInfo,
    PromptVersionInfo,
    # Dashboard Models
    DashboardStatsResponse,
    DashboardAnalyticsResponse,
    AnalyticsItem,
    DepartamentoItem,
    DisciplinaItem,
    RejectedConceptsResponse,
    RejectedConcept,
    # Periodos Models
    PeriodoInfo,
    PeriodoArchivoInfo,
    CreatePeriodoRequest,
    PeriodoResponse,
    PeriodosListResponse,
    PeriodoDetailResponse,
    PeriodoResumenPSResponse,
    PeriodoResumenPSItem
)
from .dependencies import (
    get_ocr_extractor,
    get_file_manager,
    get_gemini_service,
    get_upload_manager,
    get_archive_manager,
    get_processed_tracker,
    is_email_allowed,
    get_learning_system,
    get_periodo_manager,
    get_database_service
)
from .processing_worker import get_worker_manager, ProcessingJob
from .middleware import AuthMiddleware

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suprimir warnings de archivos temporales en consola
logging.getLogger(__name__).setLevel(logging.INFO)

# Crear aplicación FastAPI
app = FastAPI(
    title="ExtractorOCR API",
    description="API REST para procesamiento de PDFs con OCR usando Gemini Vision",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://newmont-pdf.netlify.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de autenticación (preparado pero desactivado)
auth_middleware = AuthMiddleware()
# app.middleware("http")(auth_middleware)  # Descomentar cuando se active auth


def _normalize_month(month: str) -> str:
    """
    Normaliza el mes a formato estándar.
    
    Args:
        month: Mes en formato string o int
        
    Returns:
        Nombre del mes en español (normalizado)
    """
    month_lower = month.lower().strip()
    
    # Si es número, convertir a nombre
    month_map_int = {
        '1': 'enero', '2': 'febrero', '3': 'marzo', '4': 'abril',
        '5': 'mayo', '6': 'junio', '7': 'julio', '8': 'agosto',
        '9': 'septiembre', '10': 'octubre', '11': 'noviembre', '12': 'diciembre'
    }
    
    if month_lower in month_map_int:
        return month_map_int[month_lower].capitalize()
    
    # Mapeo de meses en diferentes idiomas/formats
    month_map = {
        'enero': 'Enero', 'january': 'Enero', 'jan': 'Enero',
        'febrero': 'Febrero', 'february': 'Febrero', 'feb': 'Febrero',
        'marzo': 'Marzo', 'march': 'Marzo', 'mar': 'Marzo',
        'abril': 'Abril', 'april': 'Abril', 'apr': 'Abril',
        'mayo': 'Mayo', 'may': 'Mayo',
        'junio': 'Junio', 'june': 'Junio', 'jun': 'Junio',
        'julio': 'Julio', 'july': 'Julio', 'jul': 'Julio',
        'agosto': 'Agosto', 'august': 'Agosto', 'aug': 'Agosto',
        'septiembre': 'Septiembre', 'september': 'Septiembre', 'sep': 'Septiembre',
        'octubre': 'Octubre', 'october': 'Octubre', 'oct': 'Octubre',
        'noviembre': 'Noviembre', 'november': 'Noviembre', 'nov': 'Noviembre',
        'diciembre': 'Diciembre', 'december': 'Diciembre', 'dec': 'Diciembre'
    }
    
    return month_map.get(month_lower, month.capitalize())


@app.get("/", tags=["General"])
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "name": "ExtractorOCR API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """
    Health check endpoint.
    Verifica que la API esté funcionando correctamente.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now()
    )


@app.post("/api/v1/upload-pdf", response_model=UploadPDFResponse, tags=["Upload"])
async def upload_pdf(
    pdf_file: UploadFile = File(..., description="Archivo PDF a subir"),
    email: str = Form(..., description="Email del usuario"),
    year: int = Form(..., description="Año a procesar (2000-2100)"),
    month: str = Form(..., description="Mes a procesar (ej: 'Marzo' o '3')")
):
    """
    Sube y valida un PDF para procesamiento posterior.
    
    Args:
        pdf_file: Archivo PDF a subir
        email: Email del usuario
        year: Año a procesar
        month: Mes a procesar (string o int)
        
    Returns:
        UploadPDFResponse con file_id para usar en process-pdf
    """
    # Validar que sea PDF
    if not pdf_file.filename.lower().endswith('.pdf'):
        error_response = ErrorResponse(
            request_id="",
            error="El archivo debe ser un PDF",
            details={"filename": pdf_file.filename}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response.model_dump()
        )
    
    # Validar correo autorizado
    if not is_email_allowed(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": f"Correo no autorizado: {email}. Acceso denegado."}
        )
    
    # Normalizar mes
    normalized_month = _normalize_month(month)
    
    # Leer contenido del PDF
    try:
        pdf_content = await pdf_file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Error leyendo archivo: {str(e)}"}
        )
    
    # Guardar PDF y metadata
    upload_manager = get_upload_manager()
    metadata = {
        "email": email,
        "year": year,
        "month": normalized_month
    }
    
    try:
        file_id = upload_manager.save_uploaded_pdf(
            pdf_content,
            pdf_file.filename,
            metadata
        )
    except Exception as e:
        logger.error(f"Error guardando PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Error guardando archivo en servidor"}
        )
    
    return UploadPDFResponse(
        success=True,
        file_id=file_id,
        filename=pdf_file.filename,
        uploaded_at=datetime.now(),
        metadata=metadata,
        file_size_bytes=len(pdf_content)
    )


@app.post("/api/v1/process-pdf", response_model=ProcessPDFResponse, tags=["Processing"])
async def process_pdf(
    request: Request,
    file_id: str = Form(..., description="ID del archivo subido (obtener de /api/v1/uploaded-files)"),
    save_files: bool = Form(default=True, description="Guardar archivos en disco"),
    output_folder: str = Form(default="api", description="Subcarpeta de salida"),
    periodo_id: Optional[str] = Form(default=None, description="ID del periodo para asociar el archivo procesado")
):
    """
    Procesa un PDF que fue previamente subido con upload-pdf (ASÍNCRONO).
    
    Primero debes subir el PDF con POST /api/v1/upload-pdf y obtener el file_id.
    Luego usa ese file_id aquí para procesarlo.
    
    Este endpoint ahora es ASÍNCRONO: responde inmediatamente con un request_id.
    Usa GET /api/v1/process-status/{request_id} para consultar el estado del procesamiento.
    
    Para ver la lista de archivos disponibles, usa GET /api/v1/uploaded-files.
    
    Args:
        file_id: ID del archivo subido (obligatorio, obtener de upload-pdf)
        save_files: Si guardar archivos en disco (default: True)
        output_folder: Subcarpeta dentro de output/ (default: "api")
        periodo_id: ID del periodo para asociar el archivo procesado (opcional)
        
    Returns:
        ProcessPDFResponse con request_id y status inicial (queued/processing)
    """
    request_id = str(uuid.uuid4())
    
    upload_manager = get_upload_manager()
    
    # Validar que el file_id existe
    if not upload_manager.file_exists(file_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Archivo con file_id '{file_id}' no encontrado. Usa GET /api/v1/uploaded-files para ver archivos disponibles."}
        )
    
    # Obtener PDF y metadata
    pdf_path = upload_manager.get_uploaded_pdf_path(file_id)
    metadata = upload_manager.get_uploaded_metadata(file_id)
    
    if not pdf_path or not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Error obteniendo archivo o metadata para file_id '{file_id}'"}
        )
    
    # Obtener datos del PDF subido
    pdf_filename = metadata["filename"]
    email = metadata["metadata"]["email"]
    year = metadata["metadata"]["year"]
    normalized_month = metadata["metadata"]["month"]
    
    # Validar correo autorizado
    if not is_email_allowed(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": f"Correo no autorizado: {email}. Acceso denegado para procesar este archivo."}
        )
    
    logger.info(f"[{request_id}] Agregando PDF a cola de procesamiento - file_id: {file_id}")
    logger.info(f"[{request_id}] Email: {email}, Año: {year}, Mes: {normalized_month}")
    
    # Crear job y agregarlo a la cola
    worker_manager = get_worker_manager()
    
    job = ProcessingJob(
        request_id=request_id,
        file_id=file_id,
        pdf_path=Path(pdf_path),
        metadata={
            "filename": pdf_filename,
            "email": email,
            "year": year,
            "month": normalized_month
        },
        save_files=save_files,
        output_folder=output_folder,
        periodo_id=periodo_id
    )
    
    # Agregar job a la cola
    worker_manager.add_job(job)
    
    # Determinar estado inicial (puede ser "queued" o "processing" si hay workers disponibles)
    initial_status = "queued"
    if worker_manager.get_active_jobs_count() < worker_manager.max_workers:
        initial_status = "processing"
        job.status = "processing"
        job.message = "Iniciando procesamiento..."
    
    # Retornar respuesta inmediata
    return ProcessPDFResponse(
        success=True,
        request_id=request_id,
        status=initial_status,
        message="PDF agregado a cola de procesamiento. Usa GET /api/v1/process-status/{request_id} para consultar el estado."
    )


@app.get("/api/v1/process-status/{request_id}", response_model=ProcessStatusResponse, tags=["Processing"])
async def get_process_status(request_id: str):
    """
    Consulta el estado de un procesamiento de PDF.
    
    Args:
        request_id: ID del request de procesamiento (obtenido de POST /api/v1/process-pdf)
        
    Returns:
        ProcessStatusResponse con estado actual del procesamiento
    """
    worker_manager = get_worker_manager()
    job = worker_manager.get_job_status(request_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Request ID '{request_id}' no encontrado. Verifica que el ID sea correcto."}
        )
    
    return ProcessStatusResponse(
        success=True,
        request_id=job.request_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        pages_processed=job.pages_processed,
        processing_time=job.processing_time,
        download_url=job.download_url,
        excel_download_url=job.excel_download_url,
        error=job.error
    )


@app.get("/api/v1/uploaded-files", response_model=UploadedFilesResponse, tags=["Files"])
async def get_uploaded_files():
    """
    Obtiene lista de archivos subidos que NO han sido procesados.
    Solo muestra archivos de correos autorizados.
    
    Returns:
        Lista de archivos subidos sin procesar (solo correos autorizados)
    """
    upload_manager = get_upload_manager()
    files = upload_manager.list_uploaded_files(processed=False)
    
    # Filtrar solo archivos de correos autorizados
    file_info_list = [
        UploadedFileInfo(
            file_id=f["file_id"],
            filename=f["filename"],
            uploaded_at=f["uploaded_at"],
            file_size_bytes=f["file_size_bytes"],
            metadata=f["metadata"],
            processed=f.get("processed", False)
        )
        for f in files
        if is_email_allowed(f.get("metadata", {}).get("email", ""))
    ]
    
    return UploadedFilesResponse(
        success=True,
        total=len(file_info_list),
        files=file_info_list
    )


@app.get("/api/v1/process-status/{request_id}", response_model=ProcessStatusResponse, tags=["Processing"])
async def get_process_status(request_id: str):
    """
    Consulta el estado de un procesamiento de PDF.
    
    Args:
        request_id: ID del request de procesamiento (obtenido de POST /api/v1/process-pdf)
        
    Returns:
        ProcessStatusResponse con estado actual del procesamiento
    """
    worker_manager = get_worker_manager()
    job = worker_manager.get_job_status(request_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Request ID '{request_id}' no encontrado. Verifica que el ID sea correcto."}
        )
    
    return ProcessStatusResponse(
            success=True,
        request_id=job.request_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        pages_processed=job.pages_processed,
        processing_time=job.processing_time,
        download_url=job.download_url,
        excel_download_url=job.excel_download_url,
        error=job.error
    )


@app.get("/api/v1/uploaded-files", response_model=UploadedFilesResponse, tags=["Files"])
async def get_uploaded_files():
    """
    Obtiene lista de archivos subidos que NO han sido procesados.
    Solo muestra archivos de correos autorizados.
    
    Returns:
        Lista de archivos subidos sin procesar (solo correos autorizados)
    """
    upload_manager = get_upload_manager()
    files = upload_manager.list_uploaded_files(processed=False)
    
    # Filtrar solo archivos de correos autorizados
    file_info_list = [
        UploadedFileInfo(
            file_id=f["file_id"],
            filename=f["filename"],
            uploaded_at=f["uploaded_at"],
            file_size_bytes=f["file_size_bytes"],
            metadata=f["metadata"],
            processed=f.get("processed", False)
        )
        for f in files
        if is_email_allowed(f.get("metadata", {}).get("email", ""))
    ]
    
    return UploadedFilesResponse(
        success=True,
        total=len(file_info_list),
        files=file_info_list
    )


@app.get("/api/v1/processed-files", response_model=ProcessedFilesResponse, tags=["Files"])
async def get_processed_files(limit: int = 10):
    """
    Obtiene lista de archivos que han sido procesados con sus enlaces de descarga.
    Solo muestra archivos de correos autorizados.
    
    Incluye:
    - Archivos procesados desde upload-pdf (con file_id)
    - Archivos procesados directamente (sin file_id)
    
    Args:
        limit: Número máximo de archivos a retornar (default: 10, los más recientes)
    
    Returns:
        Lista de archivos procesados con download_url (limitada a los más recientes, solo correos autorizados)
    """
    upload_manager = get_upload_manager()
    processed_tracker = get_processed_tracker()
    archive_manager = get_archive_manager()
    
    # Archivos procesados desde upload-pdf
    uploaded_files = upload_manager.list_uploaded_files(processed=True)
    
    # Archivos procesados directamente (sin upload previo)
    direct_files = processed_tracker.get_processed_files()
    
    # Buscar archivos Excel en la carpeta pública y mapearlos por request_id
    public_folder = archive_manager.public_folder
    excel_files = {}  # Mapa: request_id -> nombre_archivo_excel
    if public_folder.exists():
        # Buscar todos los archivos Excel
        for excel_file in public_folder.glob("*.xlsx"):
            # Formato: {pdf_name}_consolidado_{timestamp}_{request_id[:8]}.xlsx
            # Extraer request_id del nombre del archivo
            excel_name = excel_file.stem  # Sin extensión
            if "_consolidado_" in excel_name:
                # El formato es: ..._consolidado_{timestamp}_{request_id[:8]}
                # Extraer el request_id[:8] (último segmento antes de .xlsx)
                parts = excel_name.split("_")
                if len(parts) >= 2:
                    request_id_prefix = parts[-1]  # Último segmento es request_id[:8]
                    
                    # Buscar en los JSONs estructurados para encontrar el request_id completo
                    try:
                        file_manager = get_file_manager()
                        base_output = file_manager.get_output_folder() or "./output"
                        structured_folder = Path(base_output) / "api" / "structured"
                        
                        if structured_folder.exists() and request_id_prefix:
                            # Buscar JSONs que tengan request_id con este prefijo
                            for json_file in structured_folder.glob("*_structured.json"):
                                try:
                                    with open(json_file, 'r', encoding='utf-8') as jf:
                                        json_data = json.load(jf)
                                    metadata = json_data.get("metadata", {})
                                    json_request_id = metadata.get("request_id", "")
                                    if json_request_id and json_request_id[:8] == request_id_prefix:
                                        # Encontramos el request_id completo
                                        excel_files[json_request_id] = excel_file.name
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        pass
    
    file_info_list = []
    
    # Agregar archivos de upload-pdf (solo correos autorizados)
    for f in uploaded_files:
        email = f.get("metadata", {}).get("email", "")
        if is_email_allowed(email):
            request_id = f.get("request_id")
            excel_url = None
            # Buscar Excel por request_id en el mapa
            if request_id and request_id in excel_files:
                excel_url = f"/public/{excel_files[request_id]}"
            # Si no se encontró en el mapa, intentar leer de la metadata
            elif not excel_url:
                excel_url = f.get("excel_download_url")
            
            file_info_list.append(
                UploadedFileInfo(
                    file_id=f["file_id"],
                    filename=f["filename"],
                    uploaded_at=f["uploaded_at"],
                    file_size_bytes=f["file_size_bytes"],
                    metadata=f["metadata"],
                    processed=True,
                    processed_at=f.get("processed_at"),
                    download_url=f.get("download_url"),
                    request_id=request_id,
                    excel_download_url=excel_url
                )
            )
    
    # Agregar archivos procesados directamente (solo correos autorizados)
    for f in direct_files:
        email = f.get("metadata", {}).get("email", "")
        if is_email_allowed(email):
            request_id = f.get("request_id")
            excel_url = None
            # Buscar Excel por request_id en el mapa
            if request_id and request_id in excel_files:
                excel_url = f"/public/{excel_files[request_id]}"
            # Si no se encontró en el mapa, intentar leer de la metadata
            elif not excel_url:
                excel_url = f.get("excel_download_url")
            
            file_info_list.append(
                UploadedFileInfo(
                    file_id=f.get("request_id", "unknown"),  # Usar request_id como file_id
                    filename=f["filename"],
                    uploaded_at=f.get("processed_at", ""),  # Usar processed_at como uploaded_at
                    file_size_bytes=0,  # No tenemos info de tamaño
                    metadata=f["metadata"],
                    processed=True,
                    processed_at=f.get("processed_at"),
                    download_url=f.get("download_url"),
                    request_id=request_id,
                    excel_download_url=excel_url
                )
            )
    
    # Ordenar por fecha de procesamiento (más reciente primero)
    file_info_list.sort(key=lambda x: x.processed_at or "", reverse=True)
    
    # Limitar a los N más recientes
    total_files = len(file_info_list)
    file_info_list = file_info_list[:limit]
    
    return ProcessedFilesResponse(
        success=True,
        total=total_files,  # Total real (antes de limitar)
        files=file_info_list  # Lista limitada
    )


# ===== Learning System Endpoints =====

@app.get("/api/v1/learning/errors", response_model=ErrorsResponse, tags=["Learning"])
async def get_learning_errors(limit: int = 100):
    """
    Obtiene lista de errores registrados por el sistema de aprendizaje.
    
    Args:
        limit: Número máximo de errores a retornar (default: 100)
        
    Returns:
        Lista de errores registrados
    """
    error_tracker, _, _ = get_learning_system()
    
    if error_tracker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        errors = error_tracker.get_recent_errors(limit=limit)
        
        error_list = [
            ErrorInfo(
                error_id=err.get("error_id", ""),
                timestamp=err.get("timestamp", ""),
                pdf_name=err.get("pdf_name", ""),
                page_number=err.get("page_number", 0),
                error_type=err.get("error_type", ""),
                error_message=err.get("error_message", ""),
                field_name=err.get("context", {}).get("field_name"),
                context=err.get("context", {})
            )
            for err in errors
        ]
        
        return ErrorsResponse(
            success=True,
            total=len(error_list),
            errors=error_list
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo errores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener errores: {str(e)}"
        )


@app.get("/api/v1/learning/errors/summary", response_model=ErrorsSummaryResponse, tags=["Learning"])
async def get_learning_errors_summary():
    """
    Obtiene un resumen de errores registrados.
    
    Returns:
        Resumen con estadísticas de errores
    """
    error_tracker, _, _ = get_learning_system()
    
    if error_tracker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        summary = error_tracker.get_errors_summary()
        
        error_list = [
            ErrorInfo(
                error_id=err.get("error_id", ""),
                timestamp=err.get("timestamp", ""),
                pdf_name=err.get("pdf_name", ""),
                page_number=err.get("page_number", 0),
                error_type=err.get("error_type", ""),
                error_message=err.get("error_message", ""),
                field_name=err.get("context", {}).get("field_name"),
                context=err.get("context", {})
            )
            for err in summary.get("recent_errors", [])
        ]
        
        return ErrorsSummaryResponse(
            success=True,
            total_errors=summary.get("total_errors", 0),
            error_types=summary.get("error_types", {}),
            most_common_fields=summary.get("most_common_fields", {}),
            recent_errors=error_list
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo resumen de errores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener resumen: {str(e)}"
        )


@app.post("/api/v1/learning/analyze", response_model=AnalysisResponse, tags=["Learning"])
async def analyze_learning_errors(limit: int = Query(default=20, ge=1, le=100)):
    """
    Analiza errores registrados usando Gemini para generar sugerencias de mejora.
    
    Este endpoint analiza los errores acumulados y genera sugerencias automáticas
    usando Gemini AI. Las sugerencias se guardan en learning/suggestions/.
    
    Args:
        limit: Número máximo de errores a analizar (default: 20, máximo recomendado: 50)
        
    Returns:
        Análisis de errores con patrones y sugerencias
    """
    error_tracker, _, learning_service = get_learning_system()
    
    if error_tracker is None or learning_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        # Obtener errores
        errors = error_tracker.get_recent_errors(limit=limit)
        
        if not errors:
            return AnalysisResponse(
                success=True,
                analysis={"message": "No hay errores para analizar"},
                patterns=[],
                suggestions=[],
                analyzed_at=datetime.now().isoformat(),
                total_errors_analyzed=0
            )
        
        # Analizar con Gemini
        analysis = learning_service.analyze_with_gemini(errors, limit=limit)
        
        # También analizar sin Gemini para obtener patrones básicos
        basic_analysis = learning_service.analyze_errors(errors)
        
        return AnalysisResponse(
            success=True,
            analysis=analysis,
            patterns=basic_analysis.get("patterns", []),
            suggestions=basic_analysis.get("suggestions", []),
            analyzed_at=analysis.get("analyzed_at", datetime.now().isoformat()),
            total_errors_analyzed=len(errors)
        )
    
    except Exception as e:
        logger.exception(f"Error analizando errores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar errores: {str(e)}"
        )


@app.get("/api/v1/learning/prompts", response_model=PromptsResponse, tags=["Learning"])
async def get_learning_prompts(history_limit: int = 10):
    """
    Obtiene información sobre las versiones de prompts.
    
    Args:
        history_limit: Número máximo de versiones históricas a retornar (default: 10)
        
    Returns:
        Información del prompt actual e historial
    """
    _, prompt_manager, _ = get_learning_system()
    
    if prompt_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        current_version_info = prompt_manager.get_current_version_info()
        history = prompt_manager.get_history(limit=history_limit)
        
        current_version = PromptVersionInfo(
            version=current_version_info.get("version", 1),
            created_at=current_version_info.get("created_at", ""),
            description=current_version_info.get("description", ""),
            improvements=current_version_info.get("improvements", []),
            source=None
        )
        
        history_list = [
            PromptVersionInfo(
                version=h.get("version", 1),
                created_at=h.get("created_at", ""),
                description=h.get("description", ""),
                improvements=h.get("improvements", []),
                source=h.get("source")
            )
            for h in history
        ]
        
        return PromptsResponse(
            success=True,
            current_version=current_version,
            history=history_list
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo prompts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener prompts: {str(e)}"
        )


@app.post("/api/v1/learning/prompts/apply", response_model=ApplyPromptResponse, tags=["Learning"])
async def apply_new_prompt(
    new_prompt: str = Form(..., description="Nuevo prompt a aplicar"),
    description: str = Form(..., description="Descripción de los cambios"),
    improvements: str = Form(default="", description="Lista de mejoras separadas por comas")
):
    """
    Aplica una nueva versión del prompt.
    
    Args:
        new_prompt: Nuevo prompt a aplicar
        description: Descripción de los cambios
        improvements: Lista de mejoras separadas por comas
        
    Returns:
        Confirmación de la nueva versión aplicada
    """
    _, prompt_manager, _ = get_learning_system()
    
    if prompt_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        improvements_list = [imp.strip() for imp in improvements.split(",") if imp.strip()] if improvements else []
        
        new_version = prompt_manager.save_new_version(
            new_prompt=new_prompt,
            description=description,
            improvements=improvements_list,
            source="api"
        )
        
        return ApplyPromptResponse(
            success=True,
            new_version=new_version,
            message=f"Prompt versión {new_version} aplicado exitosamente"
        )
    
    except Exception as e:
        logger.exception(f"Error aplicando nuevo prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al aplicar prompt: {str(e)}"
        )


@app.get("/api/v1/learning/suggestions", tags=["Learning"])
async def get_learning_suggestions():
    """
    Obtiene sugerencias de mejora generadas por el sistema.
    
    Returns:
        Lista de archivos de sugerencias disponibles
    """
    _, _, learning_service = get_learning_system()
    
    if learning_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistema de aprendizaje no está activado. Activa 'learning.enabled: true' en config.json"
        )
    
    try:
        suggestions_folder = learning_service.suggestions_folder
        
        if not suggestions_folder.exists():
            return {
                "success": True,
                "total": 0,
                "suggestions": []
            }
        
        suggestion_files = sorted(suggestions_folder.glob("analysis_*.json"), reverse=True)
        
        suggestions_list = []
        for sf in suggestion_files[:10]:  # Últimas 10 sugerencias
            try:
                import json
                with open(sf, 'r', encoding='utf-8') as f:
                    suggestion_data = json.load(f)
                    suggestions_list.append({
                        "file": sf.name,
                        "analyzed_at": suggestion_data.get("analyzed_at", ""),
                        "errors_analyzed": suggestion_data.get("errors_analyzed", 0),
                        "analysis": suggestion_data.get("analysis", {})
                    })
            except Exception:
                continue
        
        return {
            "success": True,
            "total": len(suggestions_list),
            "suggestions": suggestions_list
        }
    
    except Exception as e:
        logger.exception(f"Error obteniendo sugerencias: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener sugerencias: {str(e)}"
        )


# Función movida a excel_generator.py para evitar problemas de imports
from .excel_generator import generate_excel_for_request as _generate_excel_for_request


@app.get("/api/v1/export-excel/{request_id}", tags=["Export"])
async def export_structured_to_excel(request_id: str):
    """
    Redirige a la descarga del Excel consolidado para un request_id.
    
    Busca el excel_filename en la metadata (igual que el ZIP) y redirige a /public/{excel_filename}.
    Si no existe, intenta generarlo.
    
    Args:
        request_id: ID del procesamiento (obtener de la respuesta de /api/v1/process-pdf)
        
    Returns:
        Redirección a /public/{excel_filename} o archivo Excel para descarga directa
    """
    from fastapi.responses import RedirectResponse
    
    upload_manager = get_upload_manager()
    processed_tracker = get_processed_tracker()
    archive_manager = get_archive_manager()
    
    # Buscar excel_filename en metadata (igual que se busca zip_filename para el ZIP)
    excel_filename = None
    email_found = None
    pdf_name = None
    
    # Buscar en archivos procesados desde upload-pdf
    uploaded_files = upload_manager.list_uploaded_files(processed=True)
    for f in uploaded_files:
        if f.get("request_id") == request_id:
            excel_filename = f.get("excel_filename")
            email_found = f.get("metadata", {}).get("email", "")
            filename = f.get("filename", "")
            if filename:
                pdf_name = Path(filename).stem
            break
    
    # Si no se encontró, buscar en archivos procesados directamente
    if not excel_filename:
        direct_files = processed_tracker.get_processed_files()
        for f in direct_files:
            if f.get("request_id") == request_id:
                excel_filename = f.get("excel_filename")
                email_found = f.get("metadata", {}).get("email", "")
                filename = f.get("filename", "")
                if filename:
                    pdf_name = Path(filename).stem
                break
    
    # Validar correo autorizado
    if email_found and not is_email_allowed(email_found):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": f"Correo no autorizado para request_id '{request_id}'"}
        )
    
    # Si se encontró el excel_filename, redirigir a /public/{excel_filename}
    if excel_filename:
        excel_path = archive_manager.public_folder / excel_filename
        if excel_path.exists():
            # Redirigir a /public/{excel_filename} (igual que el ZIP)
            return RedirectResponse(url=f"/public/{excel_filename}", status_code=302)
        else:
            # El Excel no existe físicamente, intentar generarlo
            logger.warning(f"[{request_id}] Excel en metadata no existe físicamente: {excel_filename}")
    
    # Si no se encontró excel_filename o no existe físicamente, intentar generarlo
    if not pdf_name:
        pdf_name = "unknown"
    
    # Generar Excel usando la función helper (generará Excel vacío si no hay JSONs)
    file_manager = get_file_manager()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename, excel_download_url = await _generate_excel_for_request(
        request_id=request_id,
        pdf_name=pdf_name,
        timestamp=timestamp,
        archive_manager=archive_manager,
        file_manager=file_manager
    )
    
    if not excel_filename:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Error generando Excel para request_id '{request_id}'"}
        )
    
    # Redirigir a /public/{excel_filename}
    return RedirectResponse(url=f"/public/{excel_filename}", status_code=302)


@app.get("/public/{filename}", tags=["Public"])
async def serve_public_file(filename: str):
    """
    Endpoint para servir archivos públicos (zips) para descarga.
    Solo permite descargar archivos de correos autorizados.
    
    Args:
        filename: Nombre del archivo a descargar
        
    Returns:
        Archivo para descarga
    """
    from fastapi.responses import FileResponse
    
    archive_manager = get_archive_manager()
    file_path = archive_manager.public_folder / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Archivo no encontrado: {filename}"}
        )
    
    # Verificar que sea un archivo zip o excel
    if not (filename.lower().endswith('.zip') or filename.lower().endswith('.xlsx')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Solo se permiten archivos .zip o .xlsx"}
        )
    
    # Buscar el correo asociado a este archivo (ZIP o Excel)
    upload_manager = get_upload_manager()
    processed_tracker = get_processed_tracker()
    file_manager = get_file_manager()
    
    email_found = None
    
    # Si es un Excel, extraer request_id del nombre del archivo
    # Formato: {pdf_name}_consolidado_{timestamp}_{request_id[:8]}.xlsx
    if filename.lower().endswith('.xlsx'):
        # Intentar extraer request_id del nombre
        parts = filename.replace('.xlsx', '').split('_')
        if len(parts) >= 3:
            # El request_id está en los últimos caracteres (8 caracteres)
            potential_request_id_short = parts[-1]
            # Buscar request_id en los JSONs estructurados
            base_output = file_manager.get_output_folder() or "./output"
            structured_folder = Path(base_output) / "api" / "structured"
            
            if structured_folder.exists():
                all_json_files = structured_folder.glob("*_structured.json")
                for json_file in all_json_files:
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        metadata = json_data.get("metadata", {})
                        request_id = metadata.get("request_id", "")
                        if request_id and request_id[:8] == potential_request_id_short:
                            email_found = metadata.get("email", "")
                            break
                    except Exception:
                        continue
    
    # Buscar en archivos procesados desde upload-pdf (para ZIPs y Excel)
    if not email_found:
        uploaded_files = upload_manager.list_uploaded_files(processed=True)
        for f in uploaded_files:
            # Verificar si es el ZIP o el Excel
            if (f.get("zip_filename") == filename or 
                f.get("excel_filename") == filename or 
                f.get("download_url", "").endswith(filename) or
                f.get("excel_download_url", "").endswith(filename)):
                email_found = f.get("metadata", {}).get("email", "")
                break
    
    # Si no se encontró, buscar en archivos procesados directamente
    if not email_found:
        direct_files = processed_tracker.get_processed_files()
        for f in direct_files:
            # Verificar si es el ZIP o el Excel
            if (f.get("zip_filename") == filename or 
                f.get("excel_filename") == filename or 
                f.get("download_url", "").endswith(filename) or
                f.get("excel_download_url", "").endswith(filename)):
                email_found = f.get("metadata", {}).get("email", "")
                break
    
    # Validar correo autorizado
    if not email_found or not is_email_allowed(email_found):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": f"Acceso denegado. Este archivo no pertenece a un correo autorizado."}
        )
    
    # Determinar media type según extensión
    if filename.lower().endswith('.xlsx'):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media_type = "application/zip"
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type
    )


# ===== Dashboard Endpoints =====

@app.get("/api/v1/dashboard/stats", response_model=DashboardStatsResponse, tags=["Dashboard"])
async def get_dashboard_stats(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    moneda: str = Query("USD", description="Moneda (USD, PEN, EUR)"),
    tipo_documento: Optional[str] = Query(None, description="Tipo de documento"),
    departamento: Optional[str] = Query(None, description="Departamento"),
    disciplina: Optional[str] = Query(None, description="Disciplina")
):
    """
    Obtiene estadísticas globales del dashboard.
    
    Args:
        fecha_inicio: Fecha de inicio para filtrar
        fecha_fin: Fecha de fin para filtrar
        moneda: Moneda para los cálculos
        tipo_documento: Filtrar por tipo de documento
        departamento: Filtrar por departamento
        disciplina: Filtrar por disciplina
        
    Returns:
        Estadísticas globales (Monto Total, Total Horas)
    """
    try:
        # ============================================================
        # NOTA: Actualmente lee de JSONs estructurados (temporal)
        # Cuando tengas conexión a SQL Server, cambiar a leer de BD:
        # 
        # SELECT 
        #   SUM(nPrecioTotal) as monto_total,
        #   SUM(nTotalHoras) as total_horas
        # FROM MCOMPROBANTE c
        # LEFT JOIN MJORNADA j ON j.iMHoja = c.iMHoja
        # WHERE ... (aplicar filtros de fecha, moneda, etc.)
        # ============================================================
        
        # ============================================================
        # DATOS MOCKEADOS PARA PRUEBAS (TEMPORAL)
        # TODO: Reemplazar con lectura real de JSONs o SQL Server
        # ============================================================
        
        # Intentar leer de JSONs reales primero
        file_manager = get_file_manager()
        base_output = file_manager.get_output_folder() or "./output"
        structured_folder = Path(base_output) / "api" / "structured"
        
        monto_total = 0.0
        total_horas = 0.0
        has_real_data = False
        
        # TEMPORAL: Leer todos los JSONs estructurados y agregar
        # TODO: Migrar a SQL Server cuando tengas conexión a BD
        if structured_folder.exists():
            for json_file in structured_folder.glob("*_structured.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    has_real_data = True
                    
                    # Aplicar filtros aquí si es necesario
                    metadata = json_data.get("metadata", {})
                    
                    # Filtrar por fecha si se proporciona
                    if fecha_inicio or fecha_fin:
                        processed_at = metadata.get("processed_at", "")
                        if processed_at:
                            # TODO: Implementar filtro de fechas
                            # Cuando tengas BD: WHERE fEmision BETWEEN fecha_inicio AND fecha_fin
                            pass
                    
                    # Extraer montos y horas de additional_data
                    # TODO: Cuando tengas BD, esto vendrá de:
                    # - MCOMPROBANTE.nPrecioTotal
                    # - MJORNADA.nTotalHoras
                    additional_data = json_data.get("additional_data", {})
                    
                    # Buscar en mcomprobante
                    comprobantes = additional_data.get("mcomprobante", [])
                    for comp in comprobantes:
                        if isinstance(comp, dict):
                            precio_total = comp.get("nPrecioTotal", 0)
                            if precio_total:
                                monto_total += float(precio_total)
                    
                    # Buscar en mjornada
                    jornadas = additional_data.get("mjornada", [])
                    for jornada in jornadas:
                        if isinstance(jornada, dict):
                            horas = jornada.get("nTotalHoras", 0)
                            if horas:
                                total_horas += float(horas)
                
                except Exception as e:
                    logger.warning(f"Error leyendo {json_file}: {e}")
                    continue
        
        # Si no hay datos reales, usar datos mockeados para pruebas
        if not has_real_data:
            # Datos mockeados realistas
            monto_total = 2450000.75
            total_horas = 1875.5
        
        return DashboardStatsResponse(
            success=True,
            monto_total_global=round(monto_total, 2),
            total_horas_global=round(total_horas, 2),
            currency=moneda.upper()  # Asegurar formato consistente (USD, PEN, EUR)
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo estadísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener estadísticas: {str(e)}"
        )


@app.get("/api/v1/dashboard/analytics", response_model=DashboardAnalyticsResponse, tags=["Dashboard"])
async def get_dashboard_analytics(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    moneda: str = Query("USD", description="Moneda (USD, PEN, EUR)")
):
    """
    Obtiene análisis Off-Shore y On-Shore.
    
    Returns:
        Análisis con totales, distribución por departamento y top 5 disciplinas
    """
    try:
        # ============================================================
        # DATOS MOCKEADOS PARA PRUEBAS (TEMPORAL)
        # TODO: Reemplazar con lectura real de JSONs o SQL Server
        # ============================================================
        
        # Datos mockeados para Offshore
        # Valores absolutos de departamentos
        offshore_dept_values = {
            "Engineering": 850000.00,
            "Procurement": 320000.00,
            "Construction": 180000.00,
            "Project Management": 95000.00,
            "Quality Control": 45000.00,
            "Health & Safety": 35000.00,
            "Environmental": 28000.00,
            "Logistics": 22000.00,
            "Other Services": 100000.50
        }
        
        # Calcular total de departamentos y convertir a porcentajes
        offshore_dept_total = sum(offshore_dept_values.values())
        offshore_departamentos = [
            DepartamentoItem(
                label=label,
                value=round((valor / offshore_dept_total) * 100, 2)
            )
            for label, valor in offshore_dept_values.items()
        ]
        # Ordenar de mayor a menor por porcentaje
        offshore_departamentos.sort(key=lambda x: x.value, reverse=True)
        
        # Valores absolutos de disciplinas
        offshore_disc_values = {
            "Procurement": 1800.00,
            "Engineering": 1450.00,
            "Construction": 1200.00,
            "Project Management": 950.00,
            "Quality Control": 680.00
        }
        
        # Calcular total de disciplinas y convertir a porcentajes
        offshore_disc_total = sum(offshore_disc_values.values())
        offshore_disciplinas = [
            DisciplinaItem(
                label=label,
                value=round((valor / offshore_disc_total) * 100, 2)
            )
            for label, valor in offshore_disc_values.items()
        ]
        # Ordenar de mayor a menor por porcentaje
        offshore_disciplinas.sort(key=lambda x: x.value, reverse=True)
        
        offshore_item = AnalyticsItem(
            total_gasto=1450000.50,
            total_horas=1125.25,
            total_disciplinas=12,
            distribucion_departamento=offshore_departamentos,
            top_5_disciplinas=offshore_disciplinas
        )
        
        # Datos mockeados para Onshore
        # Valores absolutos de departamentos
        onshore_dept_values = {
            "Engineering": 450000.00,
            "Operations": 280000.00,
            "Maintenance": 150000.00,
            "Safety": 85000.00,
            "Environmental": 45000.00,
            "Human Resources": 35000.00,
            "Finance": 28000.00,
            "IT Services": 22000.00,
            "Other Services": 120000.25
        }
        
        # Calcular total de departamentos y convertir a porcentajes
        onshore_dept_total = sum(onshore_dept_values.values())
        onshore_departamentos = [
            DepartamentoItem(
                label=label,
                value=round((valor / onshore_dept_total) * 100, 2)
            )
            for label, valor in onshore_dept_values.items()
        ]
        # Ordenar de mayor a menor por porcentaje
        onshore_departamentos.sort(key=lambda x: x.value, reverse=True)
        
        # Valores absolutos de disciplinas
        onshore_disc_values = {
            "Engineering": 1250.00,
            "Operations": 980.00,
            "Maintenance": 720.00,
            "Safety": 550.00,
            "Environmental": 420.00
        }
        
        # Calcular total de disciplinas y convertir a porcentajes
        onshore_disc_total = sum(onshore_disc_values.values())
        onshore_disciplinas = [
            DisciplinaItem(
                label=label,
                value=round((valor / onshore_disc_total) * 100, 2)
            )
            for label, valor in onshore_disc_values.items()
        ]
        # Ordenar de mayor a menor por porcentaje
        onshore_disciplinas.sort(key=lambda x: x.value, reverse=True)
        
        onshore_item = AnalyticsItem(
            total_gasto=1000000.25,
            total_horas=750.25,
            total_disciplinas=10,
            distribucion_departamento=onshore_departamentos,
            top_5_disciplinas=onshore_disciplinas
        )
        
        return DashboardAnalyticsResponse(
            success=True,
            offshore=offshore_item,
            onshore=onshore_item
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener analytics: {str(e)}"
        )


@app.get("/api/v1/dashboard/rejected-concepts", response_model=RejectedConceptsResponse, tags=["Dashboard"])
async def get_rejected_concepts(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)")
):
    """
    Obtiene lista de conceptos rechazados.
    
    Returns:
        Lista de conceptos rechazados con cantidad, monto y porcentaje
    """
    try:
        # ============================================================
        # DATOS MOCKEADOS PARA PRUEBAS (TEMPORAL)
        # TODO: Reemplazar con lectura real de JSONs o SQL Server
        # ============================================================
        
        # Calcular total para porcentajes
        total_monto_rechazado = 125000.00
        
        concepts_mock = [
            RejectedConcept(
                concepto="Materiales no especificados",
                cantidad_total=15,
                monto_total=45000.00,
                porcentaje_total=36.0
            ),
            RejectedConcept(
                concepto="Servicios sin factura",
                cantidad_total=8,
                monto_total=32000.00,
                porcentaje_total=25.6
            ),
            RejectedConcept(
                concepto="Conceptos duplicados",
                cantidad_total=12,
                monto_total=28000.00,
                porcentaje_total=22.4
            ),
            RejectedConcept(
                concepto="Documentación incompleta",
                cantidad_total=6,
                monto_total=15000.00,
                porcentaje_total=12.0
            ),
            RejectedConcept(
                concepto="Fechas fuera de rango",
                cantidad_total=4,
                monto_total=5000.00,
                porcentaje_total=4.0
            )
        ]
        
        return RejectedConceptsResponse(
            success=True,
            total=len(concepts_mock),
            concepts=concepts_mock
        )
    
    except Exception as e:
        logger.exception(f"Error obteniendo conceptos rechazados: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener conceptos rechazados: {str(e)}"
        )


# ===== Periodos Endpoints =====

@app.post("/api/v1/periodos", response_model=PeriodoResponse, tags=["Periodos"])
async def create_periodo(request: CreatePeriodoRequest):
    """
    Crea un nuevo periodo.
    
    Args:
        request: Datos del periodo a crear (periodo: "MM/AAAA", tipo: "onshore"|"offshore")
        
    Returns:
        Periodo creado
    """
    try:
        periodo_manager = get_periodo_manager()
        
        # Validar tipo
        if request.tipo.lower() not in ["onshore", "offshore"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tipo debe ser 'onshore' o 'offshore'"
            )
        
        periodo_data = periodo_manager.create_periodo(request.periodo, request.tipo)
        
        # Función helper para formatear fechas
        def format_date(date_str: Optional[str]) -> Optional[str]:
            """Formatea fecha ISO a formato DD/MM/YYYY, HH:MM"""
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime("%d/%m/%Y, %H:%M")
            except Exception:
                return date_str  # Si falla, retornar original
        
        periodo_info = PeriodoInfo(
            periodo_id=periodo_data["periodo_id"],
            periodo=periodo_data["periodo"],
            tipo=periodo_data["tipo"],
            estado=periodo_data["estado"],
            registros=periodo_data["registros"],
            ultimo_procesamiento=format_date(periodo_data.get("ultimo_procesamiento")),
            created_at=format_date(periodo_data.get("created_at"))
        )
        
        return PeriodoResponse(success=True, periodo=periodo_info)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error creando periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear periodo: {str(e)}"
        )


@app.get("/api/v1/periodos", response_model=PeriodosListResponse, tags=["Periodos"])
async def list_periodos(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (onshore/offshore)"),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Buscar en periodo"),
    limit: int = Query(15, ge=1, le=100, description="Límite de resultados por página"),
    page: int = Query(1, ge=1, description="Número de página (empieza desde 1)")
):
    """
    Lista periodos con filtros opcionales y paginación.
    
    Args:
        tipo: Filtrar por tipo (onshore/offshore)
        estado: Filtrar por estado
        search: Buscar en periodo
        limit: Límite de resultados por página (default: 15)
        page: Número de página, empieza desde 1 (default: 1)
    
    Returns:
        Lista de periodos con información de paginación
    """
    try:
        import math
        
        periodo_manager = get_periodo_manager()
        periodos_data = periodo_manager.list_periodos(tipo=tipo, estado=estado, search=search)
        
        # Calcular paginación (page empieza desde 1)
        total_periodos = len(periodos_data)
        offset = (page - 1) * limit
        paginas = math.ceil(total_periodos / limit) if total_periodos > 0 else 1
        
        # Aplicar paginación
        periodos_data = periodos_data[offset:offset + limit]
        
        # Función helper para formatear fechas
        def format_date(date_str: Optional[str]) -> Optional[str]:
            """Formatea fecha ISO a formato DD/MM/YYYY, HH:MM"""
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime("%d/%m/%Y, %H:%M")
            except Exception:
                return date_str  # Si falla, retornar original
        
        periodos = [
            PeriodoInfo(
                periodo_id=p["periodo_id"],
                periodo=p["periodo"],
                tipo=p["tipo"],
                estado=p["estado"],
                registros=p["registros"],
                ultimo_procesamiento=format_date(p.get("ultimo_procesamiento")),
                created_at=format_date(p.get("created_at"))
            )
            for p in periodos_data
        ]
        
        return PeriodosListResponse(
            success=True,
            totalPeriodos=total_periodos,
            paginas=paginas,
            periodos=periodos
        )
    
    except Exception as e:
        logger.exception(f"Error listando periodos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar periodos: {str(e)}"
        )


@app.get("/api/v1/periodos/{periodo_id}", response_model=PeriodoDetailResponse, tags=["Periodos"])
async def get_periodo_detail(periodo_id: str):
    """
    Obtiene el detalle completo de un periodo incluyendo sus archivos.
    
    Args:
        periodo_id: ID del periodo
        
    Returns:
        Detalle del periodo con lista de archivos
    """
    try:
        periodo_manager = get_periodo_manager()
        periodo_data = periodo_manager.get_periodo(periodo_id)
        
        if not periodo_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Periodo {periodo_id} no encontrado"
            )
        
        # Obtener archivos asociados
        request_ids = periodo_manager.get_archivos_from_periodo(periodo_id)
        archivos = []
        
        # Buscar información de cada archivo en los JSONs estructurados
        file_manager = get_file_manager()
        base_output = file_manager.get_output_folder() or "./output"
        structured_folder = Path(base_output) / "api" / "structured"
        
        for request_id in request_ids:
            # Buscar JSONs con este request_id
            archivo_info = None
            if structured_folder.exists():
                for json_file in structured_folder.glob("*_structured.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        metadata = json_data.get("metadata", {})
                        if metadata.get("request_id") == request_id:
                            # Extraer información del archivo
                            additional_data = json_data.get("additional_data", {})
                            # TODO: Extraer job_no, type, etc. de additional_data
                            archivo_info = PeriodoArchivoInfo(
                                archivo_id=request_id[:8],
                                request_id=request_id,
                                filename=metadata.get("filename", "unknown"),
                                estado="procesado",
                                processed_at=metadata.get("processed_at")
                            )
                            break
                    except Exception:
                        continue
            
            if archivo_info:
                archivos.append(archivo_info)
        
        # Función helper para formatear fechas
        def format_date(date_str: Optional[str]) -> Optional[str]:
            """Formatea fecha ISO a formato DD/MM/YYYY, HH:MM"""
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime("%d/%m/%Y, %H:%M")
            except Exception:
                return date_str  # Si falla, retornar original
        
        periodo_info = PeriodoInfo(
            periodo_id=periodo_data["periodo_id"],
            periodo=periodo_data["periodo"],
            tipo=periodo_data["tipo"],
            estado=periodo_data["estado"],
            registros=periodo_data["registros"],
            ultimo_procesamiento=format_date(periodo_data.get("ultimo_procesamiento")),
            created_at=format_date(periodo_data.get("created_at"))
        )
        
        return PeriodoDetailResponse(
            success=True,
            periodo=periodo_info,
            archivos=archivos,
            total_archivos=len(archivos)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error obteniendo detalle de periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener detalle: {str(e)}"
        )


@app.put("/api/v1/periodos/{periodo_id}", response_model=PeriodoResponse, tags=["Periodos"])
async def update_periodo(periodo_id: str, updates: Dict[str, Any]):
    """
    Actualiza un periodo.
    
    Args:
        periodo_id: ID del periodo
        updates: Campos a actualizar
        
    Returns:
        Periodo actualizado
    """
    try:
        periodo_manager = get_periodo_manager()
        periodo_data = periodo_manager.update_periodo(periodo_id, updates)
        
        if not periodo_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Periodo {periodo_id} no encontrado"
            )
        
        # Función helper para formatear fechas
        def format_date(date_str: Optional[str]) -> Optional[str]:
            """Formatea fecha ISO a formato DD/MM/YYYY, HH:MM"""
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime("%d/%m/%Y, %H:%M")
            except Exception:
                return date_str  # Si falla, retornar original
        
        periodo_info = PeriodoInfo(
            periodo_id=periodo_data["periodo_id"],
            periodo=periodo_data["periodo"],
            tipo=periodo_data["tipo"],
            estado=periodo_data["estado"],
            registros=periodo_data["registros"],
            ultimo_procesamiento=format_date(periodo_data.get("ultimo_procesamiento")),
            created_at=format_date(periodo_data.get("created_at"))
        )
        
        return PeriodoResponse(success=True, periodo=periodo_info)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error actualizando periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar periodo: {str(e)}"
        )


@app.delete("/api/v1/periodos/{periodo_id}", tags=["Periodos"])
async def delete_periodo(periodo_id: str):
    """
    Elimina un periodo.
    
    Args:
        periodo_id: ID del periodo
        
    Returns:
        Confirmación de eliminación
    """
    try:
        periodo_manager = get_periodo_manager()
        deleted = periodo_manager.delete_periodo(periodo_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Periodo {periodo_id} no encontrado"
            )
        
        return {"success": True, "message": f"Periodo {periodo_id} eliminado"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error eliminando periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar periodo: {str(e)}"
        )


@app.get("/api/v1/periodos/{periodo_id}/resumen-ps", response_model=PeriodoResumenPSResponse, tags=["Periodos"])
async def get_periodo_resumen_ps(periodo_id: str):
    """
    Obtiene el resumen PS (Off-Shore/On-Shore) de un periodo.
    
    Args:
        periodo_id: ID del periodo
        
    Returns:
        Resumen PS con Department, Discipline, Total US $, Total Horas, Ratios EDP
    """
    try:
        periodo_manager = get_periodo_manager()
        periodo_data = periodo_manager.get_periodo(periodo_id)
        
        if not periodo_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Periodo {periodo_id} no encontrado"
            )
        
        # TODO: Implementar lógica para generar resumen PS desde los JSONs estructurados
        # Por ahora retornar estructura vacía
        return PeriodoResumenPSResponse(
            success=True,
            periodo_id=periodo_id,
            tipo=periodo_data["tipo"],
            items=[],
            total=0
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error obteniendo resumen PS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener resumen PS: {str(e)}"
        )


@app.post("/api/v1/periodos/{periodo_id}/exportar", tags=["Periodos"])
async def exportar_periodo(periodo_id: str):
    """
    Exporta un periodo (genera Excel/ZIP consolidado).
    
    Args:
        periodo_id: ID del periodo
        
    Returns:
        URL de descarga del archivo exportado
    """
    # TODO: Implementar exportación del periodo
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Exportación de periodo aún no implementada"
    )


@app.post("/api/v1/periodos/{periodo_id}/bloquear", tags=["Periodos"])
async def bloquear_periodo(periodo_id: str):
    """
    Bloquea un periodo (cambia estado a "cerrado").
    
    Args:
        periodo_id: ID del periodo
        
    Returns:
        Confirmación de bloqueo
    """
    try:
        periodo_manager = get_periodo_manager()
        periodo_data = periodo_manager.update_periodo(periodo_id, {"estado": "cerrado"})
        
        if not periodo_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Periodo {periodo_id} no encontrado"
            )
        
        return {"success": True, "message": f"Periodo {periodo_id} bloqueado"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error bloqueando periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al bloquear periodo: {str(e)}"
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Handler global para excepciones no capturadas.
    """
    logger.exception(f"Excepción no capturada: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Error interno del servidor",
            "details": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else None
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

