"""
Main Window Module - Interfaz gráfica principal
Responsabilidad: GUI para configuración y ejecución del OCR
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
from typing import Optional

from ..core.file_manager import FileManager
from ..core.ocr_extractor import OCRExtractor
from ..services.gemini_service import GeminiService
from ..services.data_mapper import DataMapper


class MainWindow:
    """
    Ventana principal de la aplicación.
    
    Responsabilidades:
    - Configurar carpetas
    - Ejecutar procesamiento OCR
    - Mostrar progreso
    """
    
    def __init__(self):
        """Inicializa la ventana principal."""
        self.root = tk.Tk()
        self.root.title("ExtractorOCR v1.0 - Newmont")
        self.root.geometry("700x700")
        self.root.resizable(True, True)
        
        self.file_manager = FileManager()
        self.gemini_service = None
        self.data_mapper = None
        self.ocr_extractor = None
        
        self._init_services()
        self._create_widgets()
        self._load_current_config()
    
    def _init_services(self):
        """Inicializa servicios de Gemini y DataMapper."""
        try:
            self.gemini_service = GeminiService()
            self.data_mapper = DataMapper(self.gemini_service)
            self.ocr_extractor = OCRExtractor(
                self.gemini_service, 
                self.data_mapper,
                max_workers=7  # Procesar hasta 7 páginas en paralelo
            )
        except Exception as e:
            messagebox.showerror(
                "Error de configuración",
                f"No se pudo inicializar los servicios:\n{e}"
            )
    
    def _create_widgets(self):
        """Crea todos los widgets de la interfaz."""
        self._create_header()
        self._create_config_section()
        self._create_action_section()
        self._create_progress_section()
        self._create_log_section()
    
    def _create_header(self):
        """Crea el encabezado de la ventana."""
        header_frame = tk.Frame(self.root, bg="#2c3e50")
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        
        title_label = tk.Label(
            header_frame,
            text="ExtractorOCR v1.0",
            font=("Arial", 16, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(pady=10)
        
        subtitle_label = tk.Label(
            header_frame,
            text="Extracción de datos con Gemini Vision API",
            font=("Arial", 9),
            bg="#2c3e50",
            fg="#ecf0f1"
        )
        subtitle_label.pack(pady=(0, 10))
    
    def _create_config_section(self):
        """Crea la sección de configuración de carpetas."""
        config_frame = ttk.LabelFrame(
            self.root, 
            text="Configuración de Carpetas",
            padding="10"
        )
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self._create_folder_input(
            config_frame, "Carpeta OneDrive (Input):", 0, "input"
        )
        self._create_folder_input(
            config_frame, "Carpeta Procesamiento:", 1, "processing"
        )
        self._create_folder_input(
            config_frame, "Carpeta Salida (JSON):", 2, "output"
        )
        
        # Campo para número de páginas
        pages_label = ttk.Label(config_frame, text="Páginas a procesar:")
        pages_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        
        pages_frame = ttk.Frame(config_frame)
        pages_frame.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        self.pages_entry = ttk.Entry(pages_frame, width=10)
        self.pages_entry.grid(row=0, column=0, padx=(0, 5))
        self.pages_entry.insert(0, "Max")
        
        hint_label = ttk.Label(
            pages_frame, 
            text="(Número o 'Max' para todas)",
            font=("Arial", 8)
        )
        hint_label.grid(row=0, column=1, sticky=tk.W)
    
    def _create_folder_input(self, parent, label_text, row, folder_type):
        """Crea un input de carpeta."""
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, pady=5)
        
        entry = ttk.Entry(parent, width=45)
        entry.grid(row=row, column=1, padx=5, pady=5)
        
        button = ttk.Button(
            parent,
            text="Seleccionar",
            command=lambda: self._select_folder(entry, folder_type)
        )
        button.grid(row=row, column=2, pady=5)
        
        setattr(self, f"{folder_type}_entry", entry)
    
    def _select_folder(self, entry, folder_type):
        """Abre diálogo para seleccionar carpeta."""
        folder_path = filedialog.askdirectory(
            title=f"Seleccionar carpeta {folder_type}"
        )
        
        if folder_path:
            entry.delete(0, tk.END)
            entry.insert(0, folder_path)
    
    def _create_action_section(self):
        """Crea la sección de acciones."""
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.save_config_btn = ttk.Button(
            action_frame,
            text="Guardar Configuración",
            command=self._save_config
        )
        self.save_config_btn.pack(side=tk.LEFT, padx=5)
        
        self.process_btn = ttk.Button(
            action_frame,
            text="Iniciar Procesamiento",
            command=self._start_processing,
            style="Accent.TButton"
        )
        self.process_btn.pack(side=tk.RIGHT, padx=5)
    
    def _create_progress_section(self):
        """Crea la sección de progreso."""
        progress_frame = ttk.LabelFrame(
            self.root,
            text="Progreso",
            padding="10"
        )
        progress_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.progress_var = tk.StringVar(value="Esperando inicio...")
        progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_var
        )
        progress_label.pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='determinate',
            length=600
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
    
    def _create_log_section(self):
        """Crea la sección de log."""
        log_frame = ttk.LabelFrame(
            self.root,
            text="Log de Actividad",
            padding="10"
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap=tk.WORD,
            font=("Courier", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
    
    def _load_current_config(self):
        """Carga la configuración actual."""
        self.input_entry.insert(0, self.file_manager.get_input_folder() or "")
        self.processing_entry.insert(0, self.file_manager.get_processing_folder() or "")
        self.output_entry.insert(0, self.file_manager.get_output_folder() or "")
    
    def _save_config(self):
        """Guarda la configuración de carpetas."""
        input_path = self.input_entry.get()
        processing_path = self.processing_entry.get()
        output_path = self.output_entry.get()
        
        if not all([input_path, processing_path, output_path]):
            messagebox.showwarning(
                "Configuración incompleta",
                "Por favor, configure las 3 carpetas."
            )
            return
        
        try:
            config_data = {
                "folders": {
                    "input_pdf": input_path,
                    "processing_results": processing_path,
                    "output_json": output_path
                }
            }
            
            self.file_manager.config.update(config_data)
            self.file_manager._save_config()
            
            self._log_message("Configuración guardada correctamente.")
            messagebox.showinfo(
                "Éxito",
                "Configuración guardada exitosamente."
            )
            
        except Exception as e:
            self._log_message(f"Error guardando configuración: {e}")
            messagebox.showerror("Error", f"Error guardando configuración:\n{e}")
    
    def _log_message(self, message):
        """Agrega mensaje al log."""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update()
    
    def _start_processing(self):
        """Inicia el procesamiento en un hilo separado."""
        if self.ocr_extractor is None:
            messagebox.showerror(
                "Error",
                "Servicios no inicializados correctamente."
            )
            return
        
        input_folder = self.input_entry.get()
        
        if not input_folder:
            messagebox.showwarning(
                "Configuración requerida",
                "Configure la carpeta de entrada primero."
            )
            return
        
        self.process_btn.config(state=tk.DISABLED)
        self.save_config_btn.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self._process_files)
        thread.daemon = True
        thread.start()
    
    def _process_files(self):
        """Procesa los archivos PDF."""
        try:
            pdf_files = self.file_manager.list_pdf_files()
            
            if not pdf_files:
                self._log_message("No se encontraron PDFs para procesar.")
                self.progress_var.set("No hay PDFs para procesar")
                return
            
            total_files = len(pdf_files)
            self._log_message(f"Encontrados {total_files} archivo(s) PDF.")
            
            for idx, pdf_file in enumerate(pdf_files):
                self._process_single_pdf(pdf_file, idx + 1, total_files)
            
            self._log_message("Procesamiento completado.")
            self.progress_var.set("Completado")
            messagebox.showinfo("Éxito", "Procesamiento completado correctamente.")
            
        except Exception as e:
            self._log_message(f"Error en procesamiento: {e}")
            messagebox.showerror("Error", f"Error en procesamiento:\n{e}")
        
        finally:
            self.process_btn.config(state=tk.NORMAL)
            self.save_config_btn.config(state=tk.NORMAL)
    
    def _process_single_pdf(self, pdf_file, current, total):
        """Procesa un PDF individual."""
        pdf_name = pdf_file.stem
        
        self._log_message(f"Procesando: {pdf_name} ({current}/{total})")
        
        # Definir callback para actualizar progreso
        def update_progress(message, percentage):
            if message:
                self.progress_var.set(message)
                self._log_message(f"  → {message}")
            
            if percentage is not None:
                # Calcular progreso total considerando archivos anteriores
                base_progress = ((current - 1) / total) * 100
                current_file_progress = (percentage / total)
                total_progress = int(base_progress + current_file_progress)
                self.progress_bar['value'] = min(total_progress, 100)
        
        # Leer número de páginas a procesar
        pages_value = self.pages_entry.get().strip()
        
        if pages_value.lower() == 'max' or pages_value == '':
            max_pages = None
            self._log_message(f"  → Procesando TODAS las páginas")
        else:
            try:
                max_pages = int(pages_value)
                if max_pages <= 0:
                    max_pages = None
                    self._log_message(f"  → Número inválido, procesando TODAS las páginas")
                else:
                    self._log_message(f"  → Procesando máximo {max_pages} páginas")
            except ValueError:
                max_pages = None
                self._log_message(f"  → Valor inválido, procesando TODAS las páginas")
        
        results = self.ocr_extractor.process_pdf(
            str(pdf_file), 
            progress_callback=update_progress,
            max_pages=max_pages
        )
        
        if results:
            self._log_message(f"Guardando resultados de: {pdf_name}")
            self.ocr_extractor.save_results(results, pdf_name)
            self._log_message(f"PDF procesado exitosamente: {pdf_name}")
        else:
            self._log_message(f"[ERROR] Error procesando: {pdf_name}")
        
        # Actualizar barra final
        progress_value = int((current / total) * 100)
        self.progress_bar['value'] = progress_value
    
    def run(self):
        """Ejecuta la aplicación."""
        self.root.mainloop()


def main():
    """Punto de entrada para la GUI."""
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()

