"""
Excel Generator - Generación de archivos Excel consolidados
Responsabilidad: Crear archivos Excel a partir de JSONs estructurados
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


async def generate_excel_for_request(
    request_id: str,
    pdf_name: str,
    timestamp: str,
    archive_manager,
    file_manager
) -> tuple[Optional[str], Optional[str]]:
    """
    Genera un archivo Excel consolidado para un request_id.
    SIEMPRE genera el Excel, incluso si no hay datos (solo con encabezados).
    
    Args:
        request_id: ID del procesamiento
        pdf_name: Nombre del PDF
        timestamp: Timestamp para el nombre del archivo
        archive_manager: Instancia de ArchiveManager
        file_manager: Instancia de FileManager
        
    Returns:
        Tupla (excel_filename, excel_download_url) o (None, None) solo si hay error crítico
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
        
        # Buscar todos los JSONs estructurados que tengan este request_id
        base_output = file_manager.get_output_folder() or "./output"
        structured_folder = Path(base_output) / "api" / "structured"
        
        # Crear workbook de Excel (siempre se crea)
        wb = Workbook()
        ws = wb.active
        ws.title = "Datos Consolidados"
        
        # Estilos
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        # Diccionario para almacenar todas las tablas consolidadas
        all_tables = {}
        all_columns = set()
        
        # Lista de campos estándar conocidos (por si no hay JSONs o están vacíos)
        standard_fields = {
            "hoja",  # Siempre presente
            # Campos comunes de mcomprobante
            "tNumero", "nPrecioTotal", "tFecha", "tRazonSocial",
            # Campos comunes de mcomprobante_detalle
            "tDescripcion", "nCantidad", "nPrecioUnitario", "nImporte",
            # Campos comunes de mresumen
            "tConcepto", "nMonto", "tMoneda",
            # Campos comunes de mproveedor
            "tRazonSocial", "tRUC", "tDireccion",
            # Campos comunes de mjornada
            "tEmpleado", "nHoras", "tFechaTrabajo"
        }
        
        # Buscar JSONs con este request_id (si la carpeta existe)
        json_files = []
        if structured_folder.exists():
            all_json_files = sorted(structured_folder.glob("*_structured.json"))
            
            for json_file in all_json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    metadata = json_data.get("metadata", {})
                    if metadata.get("request_id") == request_id:
                        json_files.append(json_file)
                except Exception:
                    continue
        
        # Procesar cada JSON estructurado (si existen)
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
                            
                            # Agregar todas las columnas encontradas
                            all_columns.update(record_with_hoja.keys())
            except Exception:
                continue
        
        # Si no hay columnas de datos, usar campos estándar conocidos
        if not all_columns:
            all_columns = standard_fields
        
        # Consolidar todas las tablas en una sola lista
        all_records = []
        for table_name, records in all_tables.items():
            all_records.extend(records)
        
        # Ordenar columnas (hoja siempre primero)
        sorted_columns = sorted([c for c in all_columns if c != "hoja"])
        column_order = ["hoja"] + sorted_columns
        
        # Escribir encabezados (siempre se escriben, aunque no haya datos)
        row = 1
        for col_idx, col_name in enumerate(column_order, start=1):
            cell = ws.cell(row=row, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
        
        # Escribir datos (si hay)
        row = 2
        for record in all_records:
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
            if row > 2:  # Solo si hay datos
                for row_idx in range(2, row):
                    cell_value = ws.cell(row=row_idx, column=col_idx).value
                    if cell_value:
                        max_length = max(max_length, len(str(cell_value)))
            adjusted_width = min(max(max_length + 2, 10), 50)
            ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width
        
        # Guardar Excel en carpeta pública (SIEMPRE se guarda, aunque esté vacío)
        excel_filename = f"{pdf_name}_consolidado_{timestamp}_{request_id[:8]}.xlsx"
        excel_path = archive_manager.public_folder / excel_filename
        
        # Asegurar que la carpeta pública existe
        excel_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Guardar el Excel
        wb.save(excel_path)
        
        # Verificar que se guardó correctamente
        if not excel_path.exists():
            logger.error(f"Excel no se guardó correctamente: {excel_path}")
            return None, None
        
        # Generar URL pública
        excel_download_url = archive_manager.get_public_url(excel_path)
        
        logger.info(f"[{request_id}] Excel generado exitosamente: {excel_filename} ({len(all_records)} registros, {len(column_order)} columnas)")
        
        return excel_filename, excel_download_url
    except Exception as e:
        logger.error(f"Error generando Excel para request_id {request_id}: {e}")
        import traceback
        logger.debug(f"Traceback Excel: {traceback.format_exc()}")
        return None, None

