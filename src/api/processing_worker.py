"""
Processing Worker - Sistema de workers para procesamiento asíncrono de PDFs
Responsabilidad: Gestionar pool de workers y cola de procesamiento
"""

import threading
import queue
import time
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime
from pathlib import Path
import uuid

from ..core.file_manager import truncate_pdf_name_base, truncate_filename_for_path

logger = logging.getLogger(__name__)


class ProcessingJob:
    """Representa un job de procesamiento."""
    
    def __init__(
        self,
        request_id: str,
        file_id: str,
        pdf_path: Path,
        metadata: Dict[str, Any],
        save_files: bool = True,
        output_folder: str = "api",
        periodo_id: Optional[str] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        batch_id: Optional[str] = None,
        is_batch_job: bool = False
    ):
        self.request_id = request_id
        self.file_id = file_id
        self.pdf_path = pdf_path
        self.metadata = metadata
        self.save_files = save_files
        self.output_folder = output_folder
        self.periodo_id = periodo_id
        self.start_page = start_page  # Página inicial (1-indexed, None = todas)
        self.end_page = end_page  # Página final (1-indexed, None = todas)
        self.batch_id = batch_id  # ID para agrupar lotes del mismo PDF
        self.is_batch_job = is_batch_job  # Si es parte de un procesamiento por lotes
        self.created_at = datetime.now()
        self.status = "queued"
        self.progress = 0
        self.message = "Esperando en cola..."
        self.download_url = None
        self.excel_download_url = None
        self.pages_processed = 0
        self.processing_time = None
        self.error = None


class ProcessingWorkerManager:
    """
    Gestiona pool de workers para procesamiento asíncrono de PDFs.
    
    Características:
    - Pool configurable de workers (por defecto 3)
    - Cola interna en memoria
    - Tracking de estados de jobs
    - Procesamiento en paralelo de múltiples PDFs
    """
    
    def __init__(self, max_workers: int = 3):
        """
        Inicializa el manager de workers.
        
        Args:
            max_workers: Número máximo de workers simultáneos
        """
        self.max_workers = max_workers
        self.job_queue = queue.Queue()
        self.jobs: Dict[str, ProcessingJob] = {}  # request_id -> Job
        self.jobs_lock = threading.Lock()
        self.workers = []
        self.running = False
        self._start_workers()
    
    def _start_workers(self):
        """Inicia los workers del pool."""
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"PDFWorker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        logger.info(f"Iniciados {self.max_workers} workers para procesamiento de PDFs")
    
    def _worker_loop(self):
        """Loop principal de cada worker."""
        while self.running:
            try:
                # Obtener job de la cola (timeout para poder verificar self.running)
                try:
                    job = self.job_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Procesar job
                try:
                    self._process_job(job)
                except Exception as e:
                    logger.exception(f"Error procesando job {job.request_id}: {e}")
                    with self.jobs_lock:
                        job.status = "failed"
                        job.error = str(e)
                        job.message = f"Error: {e}"
                finally:
                    self.job_queue.task_done()
            
            except Exception as e:
                logger.exception(f"Error en worker loop: {e}")
                time.sleep(1)
    
    def _process_job(self, job: ProcessingJob):
        """
        Procesa un job de PDF.
        
        Esta función contiene toda la lógica de procesamiento que actualmente
        está en el endpoint process-pdf. Se ejecuta en un worker.
        """
        # Importar aquí para evitar imports circulares
        from .dependencies import (
            get_ocr_extractor,
            get_file_manager,
            get_archive_manager,
            get_upload_manager,
            get_periodo_manager,
            get_database_service,
            is_email_allowed
        )
        # Importar función async para generar Excel
        from .excel_generator import generate_excel_for_request
        
        try:
            with self.jobs_lock:
                job.status = "processing"
                job.progress = 0
                job.message = "Iniciando procesamiento..."
            
            start_time = time.time()
            
            # Validar email
            email = job.metadata.get("email")
            if not is_email_allowed(email):
                raise ValueError(f"Correo no autorizado: {email}")
            
            # Obtener servicios
            ocr_extractor = get_ocr_extractor()
            file_manager = get_file_manager()
            upload_manager = get_upload_manager()
            
            pdf_name_full = Path(job.metadata.get("filename", "unknown")).stem
            # Truncar SOLO el nombre base del PDF (sin extensiones ni sufijos)
            # Esto garantiza que _page_1, _page_2, etc. se mantengan intactos
            pdf_name = truncate_pdf_name_base(pdf_name_full, max_length=50)
            
            # Callback de progreso
            def progress_callback(message: str, percentage: Optional[int]):
                with self.jobs_lock:
                    if percentage is not None:
                        job.progress = percentage
                    job.message = message
                    
                    # Extraer número de páginas procesadas del mensaje
                    # Formato esperado: "Página X completada (47/164)"
                    import re
                    pages_match = re.search(r'\((\d+)/(\d+)\)', message)
                    if pages_match:
                        pages_processed = int(pages_match.group(1))
                        job.pages_processed = pages_processed
            
            # Procesar PDF (con rango de páginas si es un lote)
            with self.jobs_lock:
                if job.is_batch_job and job.start_page is not None and job.end_page is not None:
                    job.message = f"Procesando lote: páginas {job.start_page}-{job.end_page}..."
                else:
                    job.message = "Procesando PDF con OCR..."
            
            # Procesar PDF con rango si es un lote
            if job.is_batch_job and job.start_page is not None and job.end_page is not None:
                # Procesar solo el rango de páginas del lote
                results = ocr_extractor.process_pdf(
                    str(job.pdf_path),
                    progress_callback=progress_callback,
                    max_pages=None,
                    start_page=job.start_page,
                    end_page=job.end_page
                )
            else:
                results = ocr_extractor.process_pdf(
                    str(job.pdf_path),
                    progress_callback=progress_callback,
                    max_pages=None
                )
            
            # Preparar metadata
            api_metadata = {
                "email": email,
                "year": job.metadata.get("year"),
                "month": job.metadata.get("month"),
                "request_id": job.request_id,
                "processed_at": datetime.now().isoformat(),
                "api_version": "1.0.0"
            }
            
            # Asociar con periodo si se proporcionó
            if job.periodo_id:
                api_metadata["periodo_id"] = job.periodo_id
                try:
                    periodo_manager = get_periodo_manager()
                    periodo = periodo_manager.get_periodo(job.periodo_id)
                    if periodo:
                        periodo_manager.add_archivo_to_periodo(job.periodo_id, job.request_id)
                        # Agregar onshore_offshore desde el tipo del periodo
                        periodo_tipo = periodo.get("tipo", "").lower()
                        if periodo_tipo in ["onshore", "offshore"]:
                            api_metadata["onshore_offshore"] = periodo_tipo
                        
                        # Consolidar resumen PS del periodo (después de guardar JSONs)
                        # Esto se hará después de guardar los JSONs estructurados
                except Exception as e:
                    logger.warning(f"[{job.request_id}] Error asociando a periodo: {e}")
            
            # Guardar JSONs
            if job.save_files:
                base_output = file_manager.get_output_folder() or "./output"
                api_output_folder = Path(base_output) / job.output_folder
                api_output_folder.mkdir(parents=True, exist_ok=True)
                
                for page_result in results:
                    page_num = page_result.get("page_number")
                    
                    # Agregar metadata
                    if "json_1_raw" in page_result:
                        page_result["json_1_raw"]["metadata"].update(api_metadata)
                    if "json_2_structured" in page_result:
                        if "metadata" not in page_result["json_2_structured"]:
                            page_result["json_2_structured"]["metadata"] = {}
                        page_result["json_2_structured"]["metadata"].update(api_metadata)
                        
                        # Agregar onshore_offshore al nivel raíz si está disponible
                        # (ya no está en additional_data)
                        if "onshore_offshore" in api_metadata:
                            page_result["json_2_structured"]["onshore_offshore"] = api_metadata["onshore_offshore"]
                    
                    # Guardar JSONs
                    import json
                    
                    raw_subfolder = api_output_folder / "raw"
                    raw_subfolder.mkdir(parents=True, exist_ok=True)
                    # El pdf_name ya está truncado, solo agregamos _page_X
                    raw_filename = f"{pdf_name}_page_{page_num}_raw.json"
                    raw_path = raw_subfolder / raw_filename
                    with open(raw_path, 'w', encoding='utf-8') as f:
                        json.dump(page_result["json_1_raw"], f, ensure_ascii=False, indent=2)
                    
                    struct_subfolder = api_output_folder / "structured"
                    struct_subfolder.mkdir(parents=True, exist_ok=True)
                    # El pdf_name ya está truncado, solo agregamos _page_X
                    struct_filename = f"{pdf_name}_page_{page_num}_structured.json"
                    struct_path = struct_subfolder / struct_filename
                    with open(struct_path, 'w', encoding='utf-8') as f:
                        json.dump(page_result["json_2_structured"], f, ensure_ascii=False, indent=2)
            
            # Guardar en BD, crear ZIP/Excel, borrar JSONs
            if job.save_files:
                archive_manager = get_archive_manager()
                api_folder = Path(base_output) / job.output_folder
                json_files = list(api_folder.rglob("*.json")) if api_folder.exists() else []
                
                if json_files:
                    # Si es un lote, solo guardar JSONs y verificar si todos los lotes terminaron
                    if job.is_batch_job and job.batch_id:
                        # Este es un lote, verificar si todos los lotes terminaron
                        logger.info(f"[{job.request_id}] Lote completado. Verificando si todos los lotes terminaron...")
                        
                        # Buscar todos los jobs del mismo batch_id
                        with self.jobs_lock:
                            batch_jobs = [
                                j for j in self.jobs.values() 
                                if j.batch_id == job.batch_id and j.is_batch_job
                            ]
                            
                            # Verificar si todos los lotes terminaron
                            all_batches_complete = all(
                                j.status in ["completed", "failed"] for j in batch_jobs
                            )
                            
                            if all_batches_complete:
                                # Todos los lotes terminaron, consolidar
                                logger.info(f"[{job.batch_id}] Todos los lotes completados. Consolidando resultados...")
                                
                                # Buscar job maestro
                                master_job = self.jobs.get(job.batch_id)
                                if master_job and not master_job.is_batch_job:
                                    # Consolidar y generar ZIP/Excel usando el request_id maestro
                                    self._consolidate_batch_results(master_job, batch_jobs, api_folder, 
                                                                   pdf_name, upload_manager, archive_manager, 
                                                                   file_manager)
                            else:
                                # Aún hay lotes pendientes
                                completed_count = sum(1 for j in batch_jobs if j.status == "completed")
                                total_batches = len(batch_jobs)
                                logger.info(f"[{job.batch_id}] Lotes completados: {completed_count}/{total_batches}")
                    else:
                        # Procesamiento normal (no es lote)
                        # Guardar en BD
                        db_service = get_database_service()
                        db_saved_successfully = False
                        
                        structured_folder = api_folder / "structured"
                        structured_json_files = []
                        if structured_folder.exists():
                            structured_json_files = list(structured_folder.glob("*_structured.json"))
                        
                        if structured_json_files:
                            try:
                                db_saved_successfully = db_service.save_structured_data(
                                    request_id=job.request_id,
                                    json_files=structured_json_files
                                )
                            except Exception as e:
                                logger.error(f"[{job.request_id}] Error guardando en BD: {e}")
                                db_saved_successfully = False
                        else:
                            db_saved_successfully = True
                        
                        # Crear ZIP y Excel
                        if db_saved_successfully or not db_service.is_enabled():
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            zip_filename_base = f"{pdf_name}_{timestamp}_{job.request_id[:8]}.zip"
                            zip_filename = truncate_filename_for_path(zip_filename_base, max_length=50)
                            zip_path = archive_manager.zip_folder(api_folder, zip_filename)
                            
                            if zip_path.exists():
                                download_url = archive_manager.get_public_url(zip_path)
                                
                                # Generar Excel (función async, pero en thread síncrono)
                                import asyncio
                                try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    excel_filename, excel_download_url = loop.run_until_complete(
                                        generate_excel_for_request(
                                            request_id=job.request_id,
                                            pdf_name=pdf_name,
                                            timestamp=timestamp,
                                            archive_manager=archive_manager,
                                            file_manager=file_manager
                                        )
                                    )
                                    loop.close()
                                except Exception as e:
                                    logger.error(f"[{job.request_id}] Error generando Excel: {e}")
                                    excel_filename, excel_download_url = None, None
                                
                                # Marcar como procesado
                                upload_manager.mark_as_processed(
                                    job.file_id,
                                    zip_filename,
                                    download_url,
                                    job.request_id,
                                    excel_filename,
                                    excel_download_url
                                )
                                
                                with self.jobs_lock:
                                    job.download_url = download_url
                                    job.excel_download_url = excel_download_url
                                
                                # Consolidar resumen PS del periodo ANTES de borrar JSONs
                                if job.periodo_id:
                                    try:
                                        from ..services.resumen_consolidator import ResumenConsolidator
                                        consolidator = ResumenConsolidator(output_folder=file_manager.get_output_folder() or Path("./output"))
                                        periodo_manager = get_periodo_manager()
                                        periodo = periodo_manager.get_periodo(job.periodo_id)
                                        if periodo:
                                            request_ids = periodo_manager.get_archivos_from_periodo(job.periodo_id)
                                            periodo_tipo = periodo.get("tipo", "offshore")
                                            # Usar la carpeta estándar output/api/structured para consolidar
                                            standard_structured_folder = Path(file_manager.get_output_folder() or "./output") / "api" / "structured"
                                            consolidator.consolidate_periodo(
                                                periodo_id=job.periodo_id,
                                                periodo_tipo=periodo_tipo,
                                                request_ids=request_ids,
                                                structured_folder=standard_structured_folder
                                            )
                                            logger.info(f"[{job.request_id}] Resumen PS consolidado para periodo {job.periodo_id}")
                                    except Exception as e:
                                        logger.warning(f"[{job.request_id}] Error consolidando resumen PS: {e}")
                                
                                # Borrar JSONs si BD fue exitoso
                                if db_saved_successfully:
                                    deleted_count = 0
                                    raw_folder = api_folder / "raw"
                                    structured_folder = api_folder / "structured"
                                    
                                    if raw_folder.exists():
                                        for json_file in raw_folder.glob("*.json"):
                                            try:
                                                json_file.unlink()
                                                deleted_count += 1
                                            except Exception:
                                                pass
                                    
                                    if structured_folder.exists():
                                        for json_file in structured_folder.glob("*.json"):
                                            try:
                                                json_file.unlink()
                                                deleted_count += 1
                                            except Exception:
                                                pass
                                    
                                    logger.info(f"[{job.request_id}] Archivos JSON eliminados: {deleted_count}")
            
            # Actualizar estado final
            processing_time = time.time() - start_time
            with self.jobs_lock:
                job.status = "completed"
                job.progress = 100
                job.message = f"Procesamiento completado: {len(results)} páginas"
                job.pages_processed = len(results)
                job.processing_time = round(processing_time, 2)
            
            logger.info(f"[{job.request_id}] Job completado exitosamente")
        
        except Exception as e:
            logger.exception(f"[{job.request_id}] Error procesando job: {e}")
            with self.jobs_lock:
                job.status = "failed"
                job.error = str(e)
                job.message = f"Error: {e}"
            raise
    
    def _consolidate_batch_results(self, master_job: ProcessingJob, batch_jobs: List[ProcessingJob],
                                   api_folder: Path, pdf_name: str, upload_manager, archive_manager,
                                   file_manager):
        """
        Consolida los resultados de todos los lotes y genera ZIP/Excel final.
        
        Args:
            master_job: Job maestro que representa el procesamiento completo
            batch_jobs: Lista de jobs de lotes que ya terminaron
            api_folder: Carpeta donde están los JSONs
            pdf_name: Nombre del PDF
            upload_manager: Manager de uploads
            archive_manager: Manager de archivos
            file_manager: Manager de archivos
            periodo_id_to_use: ID del periodo si existe
        """
        try:
            from .dependencies import get_database_service, get_periodo_manager
            from .excel_generator import generate_excel_for_request
            import asyncio
            
            logger.info(f"[{master_job.request_id}] Iniciando consolidación de {len(batch_jobs)} lotes...")
            
            # Guardar en BD
            db_service = get_database_service()
            db_saved_successfully = False
            
            structured_folder = api_folder / "structured"
            structured_json_files = []
            if structured_folder.exists():
                structured_json_files = list(structured_folder.glob("*_structured.json"))
            
            if structured_json_files:
                try:
                    db_saved_successfully = db_service.save_structured_data(
                        request_id=master_job.request_id,
                        json_files=structured_json_files
                    )
                    logger.info(f"[{master_job.request_id}] Datos guardados en BD: {len(structured_json_files)} archivos")
                except Exception as e:
                    logger.error(f"[{master_job.request_id}] Error guardando en BD: {e}")
                    db_saved_successfully = False
            else:
                db_saved_successfully = True
            
            # Crear ZIP y Excel usando el request_id maestro
            if db_saved_successfully or not db_service.is_enabled():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                zip_filename_base = f"{pdf_name}_{timestamp}_{master_job.request_id[:8]}.zip"
                zip_filename = truncate_filename_for_path(zip_filename_base, max_length=50)
                zip_path = archive_manager.zip_folder(api_folder, zip_filename)
                
                if zip_path.exists():
                    download_url = archive_manager.get_public_url(zip_path)
                    
                    # Generar Excel
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        excel_filename, excel_download_url = loop.run_until_complete(
                            generate_excel_for_request(
                                request_id=master_job.request_id,
                                pdf_name=pdf_name,
                                timestamp=timestamp,
                                archive_manager=archive_manager,
                                file_manager=file_manager
                            )
                        )
                        loop.close()
                    except Exception as e:
                        logger.error(f"[{master_job.request_id}] Error generando Excel: {e}")
                        excel_filename, excel_download_url = None, None
                    
                    # Marcar como procesado
                    upload_manager.mark_as_processed(
                        master_job.file_id,
                        zip_filename,
                        download_url,
                        master_job.request_id,
                        excel_filename,
                        excel_download_url
                    )
                    
                    # Asociar con periodo si se proporcionó
                    if master_job.periodo_id:
                        try:
                            periodo_manager = get_periodo_manager()
                            periodo = periodo_manager.get_periodo(master_job.periodo_id)
                            if periodo:
                                periodo_manager.add_archivo_to_periodo(master_job.periodo_id, master_job.request_id)
                                
                                # Consolidar resumen PS del periodo
                                try:
                                    from ..services.resumen_consolidator import ResumenConsolidator
                                    consolidator = ResumenConsolidator(output_folder=file_manager.get_output_folder() or Path("./output"))
                                    request_ids = periodo_manager.get_archivos_from_periodo(master_job.periodo_id)
                                    periodo_tipo = periodo.get("tipo", "offshore")
                                    consolidator.consolidate_periodo(
                                        periodo_id=master_job.periodo_id,
                                        periodo_tipo=periodo_tipo,
                                        request_ids=request_ids,
                                        structured_folder=structured_folder  # Usar la carpeta local del archivo
                                    )
                                    logger.info(f"[{master_job.request_id}] Resumen PS consolidado para periodo {master_job.periodo_id}")
                                except Exception as e:
                                    logger.warning(f"[{master_job.request_id}] Error consolidando resumen PS: {e}")
                        except Exception as e:
                            logger.warning(f"[{master_job.request_id}] Error asociando a periodo: {e}")
                    
                    # Actualizar job maestro
                    total_pages = sum(job.pages_processed for job in batch_jobs if job.status == "completed")
                    with self.jobs_lock:
                        master_job.status = "completed"
                        master_job.progress = 100
                        master_job.message = f"Procesamiento completado: {total_pages} páginas (procesadas en {len(batch_jobs)} lotes)"
                        master_job.pages_processed = total_pages
                        master_job.download_url = download_url
                        master_job.excel_download_url = excel_download_url
                    
                    # Consolidar resumen PS del periodo ANTES de borrar JSONs (para batch jobs)
                    if master_job.periodo_id:
                        try:
                            from ..services.resumen_consolidator import ResumenConsolidator
                            consolidator = ResumenConsolidator(output_folder=file_manager.get_output_folder() or Path("./output"))
                            periodo_manager = get_periodo_manager()
                            periodo = periodo_manager.get_periodo(master_job.periodo_id)
                            if periodo:
                                request_ids = periodo_manager.get_archivos_from_periodo(master_job.periodo_id)
                                periodo_tipo = periodo.get("tipo", "offshore")
                                # Usar la carpeta estándar output/api/structured para consolidar
                                standard_structured_folder = Path(file_manager.get_output_folder() or "./output") / "api" / "structured"
                                consolidator.consolidate_periodo(
                                    periodo_id=master_job.periodo_id,
                                    periodo_tipo=periodo_tipo,
                                    request_ids=request_ids,
                                    structured_folder=standard_structured_folder
                                )
                                logger.info(f"[{master_job.request_id}] Resumen PS consolidado para periodo {master_job.periodo_id}")
                        except Exception as e:
                            logger.warning(f"[{master_job.request_id}] Error consolidando resumen PS: {e}")
                    
                    # Borrar JSONs si BD fue exitoso
                    if db_saved_successfully:
                        deleted_count = 0
                        raw_folder = api_folder / "raw"
                        structured_folder = api_folder / "structured"
                        
                        if raw_folder.exists():
                            for json_file in raw_folder.glob("*.json"):
                                try:
                                    json_file.unlink()
                                    deleted_count += 1
                                except Exception:
                                    pass
                        
                        if structured_folder.exists():
                            for json_file in structured_folder.glob("*.json"):
                                try:
                                    json_file.unlink()
                                    deleted_count += 1
                                except Exception:
                                    pass
                        
                        logger.info(f"[{master_job.request_id}] Archivos JSON eliminados: {deleted_count}")
                    
                    logger.info(f"[{master_job.request_id}] Consolidación completada exitosamente")
        except Exception as e:
            logger.exception(f"[{master_job.request_id}] Error en consolidación: {e}")
            with self.jobs_lock:
                master_job.status = "failed"
                master_job.error = f"Error en consolidación: {str(e)}"
                master_job.message = f"Error: {e}"
    
    def add_job(self, job: ProcessingJob) -> str:
        """
        Agrega un job a la cola de procesamiento.
        
        Args:
            job: Job a procesar
            
        Returns:
            request_id del job
        """
        with self.jobs_lock:
            self.jobs[job.request_id] = job
        
        self.job_queue.put(job)
        logger.info(f"[{job.request_id}] Job agregado a cola (estado: {job.status})")
        
        return job.request_id
    
    def get_job_status(self, request_id: str) -> Optional[ProcessingJob]:
        """
        Obtiene el estado de un job.
        
        Args:
            request_id: ID del job
            
        Returns:
            ProcessingJob o None si no existe
        """
        with self.jobs_lock:
            return self.jobs.get(request_id)
    
    def get_queue_size(self) -> int:
        """Retorna el tamaño actual de la cola."""
        return self.job_queue.qsize()
    
    def get_active_jobs_count(self) -> int:
        """Retorna el número de jobs en procesamiento."""
        with self.jobs_lock:
            return sum(1 for job in self.jobs.values() if job.status == "processing")
    
    def get_jobs_by_periodo_id(self, periodo_id: str) -> List[ProcessingJob]:
        """
        Obtiene todos los jobs activos asociados a un periodo.
        
        Args:
            periodo_id: ID del periodo
            
        Returns:
            Lista de ProcessingJob con el periodo_id especificado
        """
        with self.jobs_lock:
            return [
                job for job in self.jobs.values()
                if job.periodo_id == periodo_id
            ]
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Limpia jobs antiguos de la memoria.
        
        Args:
            max_age_hours: Máxima antigüedad en horas para mantener jobs
        """
        with self.jobs_lock:
            now = datetime.now()
            to_remove = []
            
            for request_id, job in self.jobs.items():
                age = (now - job.created_at).total_seconds() / 3600
                if age > max_age_hours and job.status in ["completed", "failed"]:
                    to_remove.append(request_id)
            
            for request_id in to_remove:
                del self.jobs[request_id]
            
            if to_remove:
                logger.info(f"Limpiados {len(to_remove)} jobs antiguos")


# Singleton global del worker manager
_worker_manager: Optional[ProcessingWorkerManager] = None
_worker_manager_lock = threading.Lock()


def get_worker_manager() -> ProcessingWorkerManager:
    """
    Obtiene la instancia singleton del worker manager.
    
    Returns:
        Instancia de ProcessingWorkerManager
    """
    global _worker_manager
    
    if _worker_manager is None:
        with _worker_manager_lock:
            if _worker_manager is None:
                # Leer configuración de workers desde config.json
                max_workers = 3  # Por defecto
                try:
                    import json
                    from pathlib import Path
                    config_path = Path("config/config.json")
                    if config_path.exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        api_config = config.get("api", {})
                        max_workers = api_config.get("max_workers", 3)
                except Exception as e:
                    logger.warning(f"No se pudo leer configuración de workers: {e}")
                
                _worker_manager = ProcessingWorkerManager(max_workers=max_workers)
    
    return _worker_manager

