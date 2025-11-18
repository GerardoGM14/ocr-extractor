"""
Processing Worker - Sistema de workers para procesamiento asíncrono de PDFs
Responsabilidad: Gestionar pool de workers y cola de procesamiento
"""

import threading
import queue
import time
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path
import uuid

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
        periodo_id: Optional[str] = None
    ):
        self.request_id = request_id
        self.file_id = file_id
        self.pdf_path = pdf_path
        self.metadata = metadata
        self.save_files = save_files
        self.output_folder = output_folder
        self.periodo_id = periodo_id
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
            
            pdf_name = Path(job.metadata.get("filename", "unknown")).stem
            
            # Callback de progreso
            def progress_callback(message: str, percentage: Optional[int]):
                with self.jobs_lock:
                    if percentage is not None:
                        job.progress = percentage
                    job.message = message
            
            # Procesar PDF
            with self.jobs_lock:
                job.message = "Procesando PDF con OCR..."
            
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
                    
                    # Guardar JSONs
                    import json
                    
                    raw_subfolder = api_output_folder / "raw"
                    raw_subfolder.mkdir(parents=True, exist_ok=True)
                    raw_filename = f"{pdf_name}_page_{page_num}_raw.json"
                    raw_path = raw_subfolder / raw_filename
                    with open(raw_path, 'w', encoding='utf-8') as f:
                        json.dump(page_result["json_1_raw"], f, ensure_ascii=False, indent=2)
                    
                    struct_subfolder = api_output_folder / "structured"
                    struct_subfolder.mkdir(parents=True, exist_ok=True)
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
                        zip_filename = f"{pdf_name}_{timestamp}_{job.request_id[:8]}.zip"
                        zip_path = archive_manager.zip_folder(api_folder, zip_filename)
                        
                        if zip_path.exists():
                            download_url = archive_manager.get_public_url(zip_path)
                            
                            # Generar Excel (función async, pero en thread síncrono)
                            # Necesitamos ejecutar la función async en el thread
                            import asyncio
                            try:
                                # Crear nuevo event loop para este thread
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

