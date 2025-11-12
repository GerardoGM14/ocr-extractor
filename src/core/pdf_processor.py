"""
PDF Processor Module - Procesamiento de PDFs
Responsabilidad: Dividir PDFs en páginas individuales
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image
import io


class PDFProcessor:
    """
    Procesador de PDFs para extracción de páginas.
    
    Responsabilidades:
    - Abrir PDFs
    - Extraer páginas como imágenes
    - Dividir PDF en páginas individuales
    """
    
    def __init__(self):
        """Inicializa el procesador de PDFs."""
        self.doc = None
    
    def open_pdf(self, pdf_path: str) -> bool:
        """
        Abre un archivo PDF.
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            True si se abrió correctamente
        """
        try:
            self.doc = fitz.open(pdf_path)
            return True
        except Exception as e:
            print(f"Error abriendo PDF: {e}")
            return False
    
    def get_page_count(self) -> int:
        """Retorna el número total de páginas del PDF."""
        if self.doc is None:
            return 0
        return len(self.doc)
    
    def extract_page_as_image(self, page_num: int, 
                             dpi: int = 300) -> Optional[Image.Image]:
        """
        Extrae una página del PDF como imagen PIL.
        
        Args:
            page_num: Número de página (índice 0)
            dpi: Resolución de la imagen
            
        Returns:
            Imagen PIL o None si hay error
        """
        if self.doc is None:
            return None
        
        try:
            page = self.doc[page_num]
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix)
            
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            
            return image
        except Exception as e:
            print(f"Error extrayendo página {page_num}: {e}")
            return None
    
    def save_page_as_image(self, page_num: int, output_path: Path, 
                          dpi: int = 300) -> bool:
        """
        Guarda una página del PDF como imagen.
        
        Args:
            page_num: Número de página (índice 0)
            output_path: Ruta donde guardar la imagen
            dpi: Resolución de la imagen
            
        Returns:
            True si se guardó correctamente
        """
        try:
            image = self.extract_page_as_image(page_num, dpi)
            
            if image is None:
                return False
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, 'PNG')
            
            return True
        except Exception as e:
            print(f"Error guardando página {page_num}: {e}")
            return False
    
    def process_pdf_to_images(self, pdf_path: str, 
                             output_folder: str,
                             max_pages: int = None) -> List[Tuple[int, Path]]:
        """
        Procesa un PDF dividiéndolo en imágenes de páginas.
        
        Args:
            pdf_path: Ruta al PDF
            output_folder: Carpeta donde guardar las imágenes
            max_pages: Número máximo de páginas a procesar (None = todas)
            
        Returns:
            Lista de tuplas (número_página, path_imagen)
        """
        if not self.open_pdf(pdf_path):
            return []
        
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        processed_pages = []
        pdf_name = Path(pdf_path).stem
        
        total_pages = self.get_page_count()
        pages_to_process = min(total_pages, max_pages) if max_pages else total_pages
        
        for page_num in range(pages_to_process):
            img_filename = f"{pdf_name}_page_{page_num + 1}.png"
            img_path = output_path / img_filename
            
            if self.save_page_as_image(page_num, img_path):
                processed_pages.append((page_num + 1, img_path))
        
        return processed_pages
    
    def close(self) -> None:
        """Cierra el documento PDF."""
        if self.doc is not None:
            self.doc.close()
            self.doc = None

