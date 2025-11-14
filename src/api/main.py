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
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.requests import Request

from .models import (
    ProcessPDFResponse,
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
    PromptVersionInfo
)
from .dependencies import (
    get_ocr_extractor,
    get_file_manager,
    get_gemini_service,
    get_upload_manager,
    get_archive_manager,
    get_processed_tracker,
    is_email_allowed,
    get_learning_system
)
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

# CORS middleware (permitir todos los orígenes por ahora)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar orígenes reales
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
    output_folder: str = Form(default="api", description="Subcarpeta de salida")
):
    """
    Procesa un PDF que fue previamente subido con upload-pdf.
    
    Primero debes subir el PDF con POST /api/v1/upload-pdf y obtener el file_id.
    Luego usa ese file_id aquí para procesarlo.
    
    Para ver la lista de archivos disponibles, usa GET /api/v1/uploaded-files.
    
    Args:
        file_id: ID del archivo subido (obligatorio, obtener de upload-pdf)
        save_files: Si guardar archivos en disco (default: True)
        output_folder: Subcarpeta dentro de output/ (default: "api")
        
    Returns:
        ProcessPDFResponse con resultados del procesamiento
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
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
    temp_pdf_path = pdf_path
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
    
    logger.info(f"[{request_id}] Procesando PDF subido - file_id: {file_id}")
    logger.info(f"[{request_id}] Email: {email}, Año: {year}, Mes: {normalized_month}")
    
    # Continuar con el procesamiento (ambos modos convergen aquí)
    try:
        
        # Obtener servicios
        ocr_extractor = get_ocr_extractor()
        file_manager = get_file_manager()
        
        # Crear callback para mostrar progreso detallado en consola (como batch)
        total_pages_estimate = None
        pages_processed = 0
        start_processing_time = time.time()
        
        def progress_callback(message: str, percentage: Optional[int]):
            """Callback que imprime progreso en consola como batch_processor."""
            nonlocal pages_processed, total_pages_estimate
            
            if "dividido en" in message.lower() and "página" in message.lower():
                # Extraer número de páginas del mensaje
                import re
                match = re.search(r'(\d+)', message)
                if match:
                    total_pages_estimate = int(match.group(1))
                    print(f"\n[{request_id[:8]}] PDF dividido en {total_pages_estimate} página(s)")
                    logger.info(f"[{request_id}] PDF dividido en {total_pages_estimate} páginas")
            
            if percentage is not None and total_pages_estimate:
                elapsed = time.time() - start_processing_time
                
                # Mostrar barra de progreso como en batch
                bar_length = 40
                filled = int(bar_length * percentage / 100)
                bar = "=" * filled + "-" * (bar_length - filled)
                
                if pages_processed > 0:
                    avg_time_per_page = elapsed / pages_processed
                    remaining_pages = total_pages_estimate - pages_processed
                    estimated_remaining = avg_time_per_page * remaining_pages
                    print(f"\r[{bar}] {percentage}% - {message} - Tiempo restante: {estimated_remaining:.1f}s", end="", flush=True)
                else:
                    print(f"\r[{bar}] {percentage}% - {message}", end="", flush=True)
                
                if "completada" in message.lower():
                    pages_processed += 1
            else:
                # Mensajes sin porcentaje
                if message:
                    print(f"  → {message}")
        
        # Mostrar inicio del procesamiento
        pdf_name = Path(pdf_filename).stem if pdf_filename else "unknown"
        print(f"\n[{request_id[:8]}] Procesando: {pdf_name}")
        print(f"[{request_id[:8]}] Iniciando procesamiento OCR...")
        logger.info(f"[{request_id}] Iniciando procesamiento OCR para: {pdf_name}")
        
        # Crear wrapper de stdout que filtra mensajes de error pero permite progreso
        import sys
        from io import StringIO
        
        class FilteredOutput:
            """Filtra mensajes de error y warnings pero permite progreso."""
            def __init__(self, original_stdout):
                self.original_stdout = original_stdout
                self.buffer = StringIO()
            
            def write(self, text):
                text_lower = text.lower()
                
                # Filtrar TODOS los mensajes de error (sin excepciones)
                # Incluye: "Error procesando", "Error en OCR", "Error X"
                is_error = (
                    "error" in text_lower or
                    "could not convert" in text_lower or
                    "valueerror" in text_lower or
                    "exception" in text_lower
                )
                
                # Filtrar warnings de archivos temporales
                is_warning_file = (
                    "warning" in text_lower and 
                    ("archivo temporal" in text_lower or "no se pudo eliminar" in text_lower)
                )
                
                # Permitir solo mensajes de progreso y completado
                is_allowed = (
                    any(allowed in text_lower for allowed in [
                        "procesando:", "iniciando", "dividido en", "página", 
                        "completada", "procesamiento completado", "procesado exitosamente",
                        "[", "%", "tiempo restante", "tiempo:", "páginas procesadas"
                    ]) or
                    "=" in text or  # Barra de progreso
                    text.strip().startswith("→")  # Mensajes con flecha
                )
                
                # Si NO es error/warning Y es un mensaje permitido, mostrar
                if not is_error and not is_warning_file and (is_allowed or not text.strip()):
                    self.original_stdout.write(text)
                    self.original_stdout.flush()
                # Los mensajes de error/warning se descartan
                self.buffer.write(text)
            
            def flush(self):
                self.original_stdout.flush()
                self.buffer.flush()
        
        # Procesar PDF capturando errores pero no mostrándolos
        # Solo mostraremos error si no se procesaron todas las páginas
        filtered_stdout = FilteredOutput(sys.stdout)
        original_stdout = sys.stdout
        
        try:
            # Redirigir stdout y stderr temporalmente para filtrar errores
            sys.stdout = filtered_stdout
            sys.stderr = filtered_stdout  # También capturar stderr
            results = ocr_extractor.process_pdf(
                str(temp_pdf_path),
                progress_callback=progress_callback,
                max_pages=None  # Procesar todas las páginas
            )
        except Exception as e:
            # Capturar excepción pero no mostrar error todavía
            # Solo verificaremos si se procesaron todas las páginas
            results = []
            # El error se registra pero no se muestra al usuario
            logger.warning(f"[{request_id}] Excepción durante procesamiento (ocultada): {type(e).__name__}")
        finally:
            # Restaurar stdout y stderr originales
            sys.stdout = original_stdout
            sys.stderr = sys.__stderr__  # Restaurar stderr original
        
        # Verificar páginas faltantes - mostrar en consola pero siempre retornar éxito en HTTP
        results_count = len(results) if results else 0
        
        # Mostrar error en CONSOLA si faltan páginas (pero NO retornar error HTTP)
        if total_pages_estimate is not None and results_count < total_pages_estimate:
            # Mostrar en consola
            print(f"\n[{request_id[:8]}] ✗ [ERROR] Solo se procesaron {results_count}/{total_pages_estimate} páginas")
            logger.error(f"[{request_id}] Error: Solo se procesaron {results_count}/{total_pages_estimate} páginas")
        
        # Si no hay resultados, mostrar mensaje en consola pero seguir retornando éxito
        if not results or results_count == 0:
            print(f"\n[{request_id[:8]}] ✗ [ERROR] No se procesaron páginas")
            logger.error(f"[{request_id}] Error: No se procesaron páginas")
            results = []  # Asegurar lista vacía
        
        # Mostrar mensaje de éxito/proceso en consola
        if results:
            print(f"\n[{request_id[:8]}] ✓ PDF procesado: {pdf_name}")
            print(f"[{request_id[:8]}]   Páginas procesadas: {len(results)}")
            elapsed_processing = time.time() - start_processing_time
            print(f"[{request_id[:8]}]   Tiempo: {elapsed_processing:.2f} segundos")
        else:
            # Si no hay resultados, mostrar mensaje genérico
            print(f"\n[{request_id[:8]}] ✓ Procesamiento completado: {pdf_name}")
            elapsed_processing = time.time() - start_processing_time
            print(f"[{request_id[:8]}]   Tiempo: {elapsed_processing:.2f} segundos")
        
        # Preparar metadata para incluir en JSONs
        api_metadata = {
            "email": email,
            "year": year,
            "month": normalized_month,
            "request_id": request_id,
            "processed_at": datetime.now().isoformat(),
            "api_version": "1.0.0"
        }
        
        # Agregar metadata a los JSONs procesados
        processed_results = []
        files_saved = []
        
        for page_result in results:
            page_num = page_result.get("page_number")
            
            # Agregar metadata a json_1_raw
            if "json_1_raw" in page_result:
                page_result["json_1_raw"]["metadata"].update(api_metadata)
            
            # Agregar metadata a json_2_structured
            if "json_2_structured" in page_result:
                if "metadata" not in page_result["json_2_structured"]:
                    page_result["json_2_structured"]["metadata"] = {}
                page_result["json_2_structured"]["metadata"].update(api_metadata)
            
            # Guardar archivos si está habilitado
            if save_files:
                # Determinar carpeta de salida
                base_output = file_manager.get_output_folder() or "./output"
                api_output_folder = Path(base_output) / output_folder
                api_output_folder.mkdir(parents=True, exist_ok=True)
                
                # Guardar JSON 1 (raw)
                raw_subfolder = api_output_folder / "raw"
                raw_subfolder.mkdir(parents=True, exist_ok=True)
                raw_filename = f"{pdf_name}_page_{page_num}_raw.json"
                raw_path = raw_subfolder / raw_filename
                
                import json
                with open(raw_path, 'w', encoding='utf-8') as f:
                    json.dump(page_result["json_1_raw"], f, ensure_ascii=False, indent=2)
                
                files_saved.append({
                    "type": "raw",
                    "path": str(raw_path),
                    "page": page_num
                })
                
                # Guardar JSON 2 (structured)
                struct_subfolder = api_output_folder / "structured"
                struct_subfolder.mkdir(parents=True, exist_ok=True)
                struct_filename = f"{pdf_name}_page_{page_num}_structured.json"
                struct_path = struct_subfolder / struct_filename
                
                with open(struct_path, 'w', encoding='utf-8') as f:
                    json.dump(page_result["json_2_structured"], f, ensure_ascii=False, indent=2)
                
                files_saved.append({
                    "type": "structured",
                    "path": str(struct_path),
                    "page": page_num
                })
            
            # Crear PageResult para respuesta
            processed_results.append(
                PageResult(
                    page_number=page_num,
                    json_1_raw=page_result["json_1_raw"],
                    json_2_structured=page_result["json_2_structured"]
                )
            )
        
        processing_time = time.time() - start_time
        
        logger.info(
            f"[{request_id}] Procesamiento completado: "
            f"{len(processed_results)} páginas en {processing_time:.2f}s"
        )
        
        # Zipear carpeta api y generar URL pública
        # El ZIP se guarda en public/ y se genera el enlace de descarga
        download_url = None
        zip_filename = None
        excel_download_url = None
        if save_files:
            try:
                archive_manager = get_archive_manager()
                file_manager = get_file_manager()
                
                # Obtener carpeta output/api
                base_output = file_manager.get_output_folder() or "./output"
                api_folder = Path(base_output) / output_folder
                
                # Verificar que la carpeta existe y tiene archivos JSON
                json_files = list(api_folder.rglob("*.json")) if api_folder.exists() else []
                
                if json_files:
                    # Crear nombre único para el zip
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_filename = f"{pdf_name}_{timestamp}_{request_id[:8]}.zip"
                    
                    # Zipear carpeta (se guarda en public/)
                    zip_path = archive_manager.zip_folder(api_folder, zip_filename)
                    
                    # Verificar que el ZIP se creó correctamente en public/
                    if zip_path.exists():
                        # Generar URL pública para descargar desde public/
                        download_url = archive_manager.get_public_url(zip_path)
                        
                        # Generar Excel consolidado (igual que el ZIP)
                        excel_filename = None
                        excel_download_url = None
                        try:
                            excel_filename, excel_download_url = await _generate_excel_for_request(
                                request_id=request_id,
                                pdf_name=pdf_name,
                                timestamp=timestamp,
                                archive_manager=archive_manager,
                                file_manager=file_manager
                            )
                            if excel_filename:
                                logger.info(f"[{request_id}] Excel creado en public/: {excel_filename}")
                                print(f"[{request_id[:8]}] ✓ Archivo Excel creado: {excel_filename}")
                                if excel_download_url:
                                    print(f"[{request_id[:8]}] ✓ URL de descarga Excel: {excel_download_url}")
                        except Exception as e:
                            # No fallar si hay error al generar Excel, solo log
                            logger.error(f"[{request_id}] Error creando Excel: {e}")
                            import traceback
                            logger.debug(f"[{request_id}] Traceback Excel: {traceback.format_exc()}")
                        
                        # Guardar relación file_id -> zip y excel
                        upload_manager = get_upload_manager()
                        upload_manager.mark_as_processed(file_id, zip_filename, download_url, request_id, excel_filename, excel_download_url)
                        
                        logger.info(f"[{request_id}] ZIP creado en public/: {zip_path.name}")
                        logger.info(f"[{request_id}] URL de descarga: {download_url}")
                        print(f"[{request_id[:8]}] ✓ Archivo ZIP creado: {zip_path.name}")
                        print(f"[{request_id[:8]}] ✓ URL de descarga: {download_url}")
                        
                        # Limpiar archivos JSON después de generar ZIP y Excel exitosamente
                        try:
                            raw_folder = api_folder / "raw"
                            structured_folder = api_folder / "structured"
                            
                            deleted_count = 0
                            
                            # Eliminar archivos en raw/
                            if raw_folder.exists():
                                for json_file in raw_folder.glob("*.json"):
                                    try:
                                        json_file.unlink()
                                        deleted_count += 1
                                    except Exception as e:
                                        logger.warning(f"[{request_id}] No se pudo eliminar {json_file}: {e}")
                            
                            # Eliminar archivos en structured/
                            if structured_folder.exists():
                                for json_file in structured_folder.glob("*.json"):
                                    try:
                                        json_file.unlink()
                                        deleted_count += 1
                                    except Exception as e:
                                        logger.warning(f"[{request_id}] No se pudo eliminar {json_file}: {e}")
                            
                            if deleted_count > 0:
                                logger.info(f"[{request_id}] Archivos JSON eliminados: {deleted_count} archivos")
                                print(f"[{request_id[:8]}] ✓ Archivos JSON eliminados: {deleted_count} archivos")
                        except Exception as e:
                            # No fallar si hay error al limpiar, solo log
                            logger.warning(f"[{request_id}] Error limpiando archivos JSON: {e}")
                    else:
                        logger.error(f"[{request_id}] ZIP no se creó correctamente: {zip_path}")
                else:
                    logger.warning(f"[{request_id}] No se encontraron archivos JSON en {api_folder} para zipear")
            except Exception as e:
                # No fallar si hay error al zipear, solo log
                logger.error(f"[{request_id}] Error creando ZIP: {e}")
                import traceback
                logger.debug(f"[{request_id}] Traceback: {traceback.format_exc()}")
        
        # Preparar respuesta
        response_data = {
            "success": True,
            "request_id": request_id,
            "metadata": {
                "email": email,
                "year": year,
                "month": normalized_month,
                "processed_at": datetime.now().isoformat()
            },
            "pdf_info": {
                "filename": pdf_filename if pdf_filename else "unknown",
                "total_pages": total_pages_estimate if total_pages_estimate else len(processed_results),
                "pages_processed": len(processed_results)
            },
            "results": processed_results,
            "files_saved": files_saved if save_files else None,
            "processing_time_seconds": round(processing_time, 2),
            "download_url": download_url,
            "excel_download_url": excel_download_url
        }
        
        response = ProcessPDFResponse(**response_data)
        
        return response
        
    except HTTPException:
        # Solo re-lanzar HTTPException si es de validación (400) o similar
        # NO lanzar error 500 por excepciones de procesamiento
        raise
    except Exception as e:
        # NO mostrar error en consola NI en respuesta HTTP
        # Log interno solo y retornar éxito con lista vacía
        logger.warning(f"[{request_id}] Excepción durante procesamiento (ocultada): {type(e).__name__}: {e}")
        
        # Retornar respuesta de éxito con lista vacía en lugar de error
        processing_time = time.time() - start_time
        
        return ProcessPDFResponse(
            success=True,
            request_id=request_id,
            metadata={
                "email": email if email else "unknown",
                "year": year if year else 0,
                "month": normalized_month if normalized_month else "unknown",
                "processed_at": datetime.now().isoformat()
            },
            pdf_info={
                "filename": pdf_filename if pdf_filename else "unknown",
                "total_pages": 0,
                "pages_processed": 0
            },
            results=[],
            files_saved=None,
            processing_time_seconds=round(processing_time, 2),
            download_url=None
        )
    finally:
        # No eliminar el PDF subido, solo se procesa
        # El PDF queda en uploads/ para futuras referencias
        pass


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


async def _generate_excel_for_request(
    request_id: str,
    pdf_name: str,
    timestamp: str,
    archive_manager,
    file_manager
) -> tuple[Optional[str], Optional[str]]:
    """
    Genera un archivo Excel consolidado para un request_id.
    
    Args:
        request_id: ID del procesamiento
        pdf_name: Nombre del PDF
        timestamp: Timestamp para el nombre del archivo
        archive_manager: Instancia de ArchiveManager
        file_manager: Instancia de FileManager
        
    Returns:
        Tupla (excel_filename, excel_download_url) o (None, None) si hay error
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
        
        # Buscar todos los JSONs estructurados que tengan este request_id
        base_output = file_manager.get_output_folder() or "./output"
        structured_folder = Path(base_output) / "api" / "structured"
        
        if not structured_folder.exists():
            return None, None
        
        # Buscar JSONs con este request_id
        all_json_files = sorted(structured_folder.glob("*_structured.json"))
        json_files = []
        
        for json_file in all_json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                metadata = json_data.get("metadata", {})
                if metadata.get("request_id") == request_id:
                    json_files.append(json_file)
            except Exception:
                continue
        
        if not json_files:
            return None, None
        
        # Crear workbook de Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Datos Consolidados"
        
        # Estilos
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        # Diccionario para almacenar todas las tablas consolidadas
        all_tables = {}
        
        # Procesar cada JSON estructurado
        for json_file in json_files:
            try:
                # Extraer número de página
                page_match = json_file.stem.split("_page_")
                if len(page_match) >= 2:
                    page_num_str = page_match[1].replace("_structured", "")
                    try:
                        page_num = int(page_num_str)
                    except ValueError:
                        page_num = 0
                else:
                    page_num = 0
                
                # Leer JSON
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                # Obtener additional_data
                additional_data = json_data.get("additional_data", {})
                
                # Procesar cada tabla
                for table_name, table_data in additional_data.items():
                    if not isinstance(table_data, list):
                        continue
                    
                    if table_name not in all_tables:
                        all_tables[table_name] = []
                    
                    for record in table_data:
                        if isinstance(record, dict):
                            record_with_hoja = {}
                            
                            for key, value in record.items():
                                if isinstance(value, (list, tuple)):
                                    record_with_hoja[key] = ", ".join(str(v) for v in value) if value else ""
                                elif isinstance(value, dict):
                                    record_with_hoja[key] = json.dumps(value, ensure_ascii=False)
                                else:
                                    record_with_hoja[key] = value
                            
                            record_with_hoja["hoja"] = f"{pdf_name} - Página {page_num}"
                            all_tables[table_name].append(record_with_hoja)
            except Exception:
                continue
        
        if not all_tables or all(not records for records in all_tables.values()):
            return None, None
        
        # Consolidar todas las tablas
        all_columns = set()
        for table_name, records in all_tables.items():
            for record in records:
                if isinstance(record, dict):
                    all_columns.update(record.keys())
        
        sorted_columns = sorted([c for c in all_columns if c != "hoja"])
        column_order = ["hoja"] + sorted_columns
        
        # Escribir encabezados
        row = 1
        for col_idx, col_name in enumerate(column_order, start=1):
            cell = ws.cell(row=row, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
        
        # Escribir datos
        row = 2
        for table_name, records in all_tables.items():
            for record in records:
                if isinstance(record, dict):
                    for col_idx, col_name in enumerate(column_order, start=1):
                        value = record.get(col_name, "")
                        if value is None:
                            value = ""
                        ws.cell(row=row, column=col_idx, value=value)
                    row += 1
        
        # Ajustar ancho de columnas
        for col_idx, col_name in enumerate(column_order, start=1):
            max_length = len(str(col_name))
            for row_idx in range(2, row):
                cell_value = ws.cell(row=row_idx, column=col_idx).value
                if cell_value:
                    max_length = max(max_length, len(str(cell_value)))
            adjusted_width = min(max(max_length + 2, 10), 50)
            ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width
        
        # Guardar Excel en carpeta pública
        excel_filename = f"{pdf_name}_consolidado_{timestamp}_{request_id[:8]}.xlsx"
        excel_path = archive_manager.public_folder / excel_filename
        wb.save(excel_path)
        
        # Generar URL pública
        excel_download_url = archive_manager.get_public_url(excel_path)
        
        return excel_filename, excel_download_url
    except Exception as e:
        logger.error(f"Error generando Excel para request_id {request_id}: {e}")
        return None, None


@app.get("/api/v1/export-excel/{request_id}", tags=["Export"])
async def export_structured_to_excel(request_id: str):
    """
    Genera un archivo Excel consolidado con todos los JSONs estructurados de un request_id.
    
    Consolida todas las tablas de additional_data de todos los JSONs estructurados
    de un procesamiento específico en un solo archivo Excel, agregando una columna "hoja" 
    con el número de página.
    
    Args:
        request_id: ID del procesamiento (obtener de la respuesta de /api/v1/process-pdf)
        
    Returns:
        Archivo Excel para descarga directa
    """
    archive_manager = get_archive_manager()
    file_manager = get_file_manager()
    
    # Buscar información del request_id para validar email
    base_output = file_manager.get_output_folder() or "./output"
    structured_folder = Path(base_output) / "api" / "structured"
    
    if not structured_folder.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"No se encontró la carpeta de archivos estructurados"}
        )
    
    # Buscar email y pdf_name para validación
    email_found = None
    pdf_name = None
    all_json_files = sorted(structured_folder.glob("*_structured.json"))
    
    for json_file in all_json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            metadata = json_data.get("metadata", {})
            if metadata.get("request_id") == request_id:
                if email_found is None:
                    email_found = metadata.get("email", "")
                    name_parts = json_file.stem.split("_page_")
                    if name_parts:
                        pdf_name = name_parts[0]
                break
        except Exception:
            continue
    
    if not email_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"No se encontraron JSONs estructurados para request_id '{request_id}'"}
        )
    
    # Validar correo autorizado
    if not is_email_allowed(email_found):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": f"Correo no autorizado o no encontrado para request_id '{request_id}'"}
        )
    
    if not pdf_name:
        pdf_name = "unknown"
    
    # Generar Excel usando la función helper
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"No se encontraron datos para consolidar para request_id '{request_id}'"}
        )
    
    # Devolver archivo para descarga directa
    excel_path = archive_manager.public_folder / excel_filename
    return FileResponse(
        path=str(excel_path),
        filename=excel_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


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
    
    # Buscar en archivos procesados desde upload-pdf (para ZIPs)
    if not email_found:
        uploaded_files = upload_manager.list_uploaded_files(processed=True)
        for f in uploaded_files:
            if f.get("zip_filename") == filename or f.get("download_url", "").endswith(filename):
                email_found = f.get("metadata", {}).get("email", "")
                break
    
    # Si no se encontró, buscar en archivos procesados directamente
    if not email_found:
        direct_files = processed_tracker.get_processed_files()
        for f in direct_files:
            if f.get("zip_filename") == filename or f.get("download_url", "").endswith(filename):
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

