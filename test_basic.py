"""
Script de prueba básico para verificar módulos core.
NO USA API DE GEMINI - Solo valida la estructura.
"""

import sys
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.file_manager import FileManager
from core.pdf_processor import PDFProcessor


def test_file_manager():
    """Prueba el FileManager."""
    print("=" * 60)
    print("TEST: FileManager")
    print("=" * 60)
    
    try:
        fm = FileManager()
        print("[OK] FileManager inicializado correctamente")
        
        input_folder = fm.get_input_folder()
        output_folder = fm.get_output_folder()
        temp_folder = fm.get_temp_folder()
        
        print(f"  Input folder: {input_folder}")
        print(f"  Output folder: {output_folder}")
        print(f"  Temp folder: {temp_folder}")
        
        pdf_files = fm.list_pdf_files()
        print(f"  PDFs encontrados: {len(pdf_files)}")
        
        return True
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def test_pdf_processor():
    """Prueba el PDFProcessor."""
    print("\n" + "=" * 60)
    print("TEST: PDFProcessor")
    print("=" * 60)
    
    try:
        processor = PDFProcessor()
        print("[OK] PDFProcessor inicializado correctamente")
        
        # Buscar PDFs
        fm = FileManager()
        pdf_files = fm.list_pdf_files()
        
        if pdf_files:
            pdf_path = str(pdf_files[0])
            print(f"  Procesando: {pdf_path}")
            
            if processor.open_pdf(pdf_path):
                page_count = processor.get_page_count()
                print(f"  Páginas encontradas: {page_count}")
                processor.close()
                
                if page_count > 0:
                    print("[OK] PDF se puede procesar")
                    return True
            else:
                print("[ERROR] No se pudo abrir el PDF")
                return False
        else:
            print("  No hay PDFs en la carpeta de entrada")
            print("[OK] Estructura OK (sin PDFs para probar)")
            return True
            
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    """Ejecuta tests básicos."""
    print("\nExtractorOCR - Tests Básicos")
    print("=" * 60)
    
    results = []
    
    # Test FileManager
    results.append(test_file_manager())
    
    # Test PDFProcessor
    results.append(test_pdf_processor())
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    
    if all(results):
        print("[OK] Todos los tests pasaron correctamente")
        return 0
    else:
        print("[ERROR] Algunos tests fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(main())

